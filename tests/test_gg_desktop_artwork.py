"""Real cache/decoder/worker/render checks without an external network dependency."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HAS_QT = importlib.util.find_spec("PySide6") is not None
if HAS_QT:
    if os.name != "nt": os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QPoint, Qt
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtWidgets import QApplication
    from core import ModFolder, OldFile, SteamGame, default_settings
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.artwork import (SteamArtwork, artwork_urls, decode_artwork, load_artwork,
        valid_app_id, SteamRedirects, fetch_artwork)
    from gg_desktop.models import merge_games
    from gg_desktop.overview import OverviewRing


@unittest.skipUnless(HAS_QT, "Optional Qt preview dependencies not installed")
class ArtworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="GG-Artwork-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache = self.root / "OwnCache"
        self.steam = self.root / "Steam"

    def image(self, color, path=None):
        image = QImage(120, 180, QImage.Format_RGB32)
        image.fill(QColor(color))
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.assertTrue(image.save(str(path)))
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        image.save(buffer, "PNG")
        return bytes(buffer.data())

    def test_current_hashed_and_legacy_steam_cache_images_load_without_network(self):
        for path in (self.steam / "appcache/librarycache/333/hash_library_600x900.jpg",
                     self.steam / "appcache/librarycache/444_library_600x900.jpg"):
            self.image("#12d269", path)
        for app_id in ("333", "444"):
            image, status = load_artwork(app_id, "cover", [str(self.steam)], self.cache, True, lambda: False,
                                        fetch=lambda *args: self.fail("Local Steam artwork must not request the CDN"))
            self.assertFalse(image.isNull())
            self.assertEqual(status, "Cached")
            self.assertGreater(image.pixelColor(40, 40).green(), 195)

    def test_download_is_decoded_cached_and_available_offline(self):
        payload = self.image("#35a4dc")
        fetches = []
        def fetch(url, canceled):
            fetches.append(url)
            return payload
        image, status = load_artwork("555", "cover", [], self.cache, True, lambda: False, fetch=fetch)
        self.assertFalse(image.isNull())
        self.assertEqual(status, "Downloaded")
        self.assertEqual(len(fetches), 1)
        self.assertTrue((self.cache / "555-cover.png").is_file())
        again, status = load_artwork("555", "cover", [], self.cache, False, lambda: False,
                                    fetch=lambda *args: self.fail("Offline artwork must not request the CDN"))
        self.assertEqual(status, "Cached")
        self.assertEqual(image, again)
        header, status = load_artwork("555", "header", [], self.cache, False, lambda: False)
        self.assertFalse(header.isNull())

    def test_bad_ids_images_and_redirects_are_rejected(self):
        for value in ("../secret", "123/456", "0", "-1", "１２３", "4294967296", None):
            self.assertIsNone(valid_app_id(value))
            self.assertEqual(artwork_urls(value), ())
        self.assertTrue(decode_artwork(b"<html>not an image</html>").isNull())
        image = QImage(9000, 20, QImage.Format_RGB32)
        buffer = QBuffer(); buffer.open(QIODevice.WriteOnly); image.save(buffer, "PNG")
        self.assertTrue(decode_artwork(bytes(buffer.data())).isNull())
        with self.assertRaises(ValueError):
            SteamRedirects().redirect_request(None, None, 302, "", {}, "https://other.example/image.png")

    def test_cdn_failure_is_a_cover_fallback_and_does_not_create_a_cache_entry(self):
        def unavailable(*args): raise OSError("Fixture offline")
        image, status = load_artwork("666", "cover", [], self.cache, True, lambda: False, fetch=unavailable)
        self.assertTrue(image.isNull())
        self.assertEqual(status, "Unavailable")
        self.assertFalse(self.cache.exists())

    def test_http_image_response_uses_the_real_bounded_downloader(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        payload = self.image("#3d73db")
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            def log_message(self, *args): pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            data = fetch_artwork(f"http://127.0.0.1:{server.server_port}/image.png", lambda: False)
            self.assertFalse(decode_artwork(data).isNull())
        finally:
            server.shutdown(); server.server_close(); thread.join(2)

    def test_redirected_cache_is_not_read_or_overwritten(self):
        outside = self.root / "Private"
        self.image("#f03b50", outside / "777-cover.png")
        link = self.cache
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("OS cannot create symlinks")
        image, status = load_artwork("777", "cover", [], self.cache, False, lambda: False)
        self.assertTrue(image.isNull())
        self.assertEqual((outside / "777-cover.png").read_bytes(), self.image("#f03b50"))

    def wait_until(self, condition):
        deadline = time.monotonic() + 10
        while not condition() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.assertTrue(condition(), "Artwork worker did not finish")

    def test_real_cached_artwork_appears_in_games_and_overview(self):
        self.image("#12d269", self.steam / "appcache/librarycache/333/hash_library_600x900.jpg")
        settings = default_settings()
        settings["steam_artwork_downloads"] = False
        with patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "Local"), "APPDATA": str(self.root / "Roaming")}), \
             patch("gg_desktop.app.load_settings", return_value=settings):
            window = CrimsonWindow()
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        self.addCleanup(lambda: window.artwork.pool.waitForDone(10000))
        self.addCleanup(window.artwork.close)
        game = SteamGame("333", "New Fixture Outside Reference Covers", str(self.steam), str(self.root / "Game"), 100, None, "Unknown")
        window.inventory.steam = [game]
        window.inventory.games = merge_games([game], [])
        window.inventory.scanned_at = "Fixture"
        window.show()
        window.navigate("Games")
        self.wait_until(lambda: ("333", "cover") in window.artwork.images)
        self.app.processEvents()
        rect = window.game_grid.visualItemRect(window.game_grid.item(0))
        pixel = window.game_grid.viewport().grab().toImage().pixelColor(rect.center().x(), rect.top() + rect.height() // 3)
        self.assertGreater(pixel.green(), 180)
        self.assertLess(pixel.red(), 50)
        self.assertIn("1 ready", window.game_artwork_status.text())
        window.navigate("Overview")
        self.app.processEvents()
        rect = window.overview_library.visualItemRect(window.overview_library.item(0))
        pixel = window.overview_library.viewport().grab().toImage().pixelColor(rect.center().x(), rect.top() + rect.height() // 3)
        self.assertGreater(pixel.green(), 180)
        self.assertLess(pixel.red(), 50)

    def test_pie_pixels_use_category_colors_at_proportional_angles(self):
        import math
        colors = ("#f0bc78", "#40d8d3", "#ce8fe5", "#778dff")
        ring = OverviewRing([(str(i), i + 1, color) for i, color in enumerate(colors)], scanned=True)
        self.addCleanup(ring.close)
        ring.resize(190, 190); ring.show(); self.app.processEvents()
        image = ring.grab().toImage()
        # Sample each proportional arc's midpoint. Bevel lighting may change
        # brightness, but its category hue must remain distinct and correct.
        fraction = 0
        for i, color in enumerate(colors):
            share = (i + 1) / 10
            angle = math.radians(90 - (fraction + share / 2) * 360)
            pixel = image.pixelColor(round(95 + 77 * math.cos(angle)), round(95 - 77 * math.sin(angle)))
            expected = QColor(color)
            difference = abs(pixel.hueF() - expected.hueF())
            self.assertLess(min(difference, 1 - difference) * 360, 12)
            self.assertGreater(pixel.saturationF(), .12)
            fraction += share
        self.assertEqual(sum(v for _, v, _ in ring.segments), 10)


if __name__ == "__main__":
    unittest.main()
