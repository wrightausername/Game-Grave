"""Exact-AppID official Steam portrait and explicit per-game cover regression."""
from __future__ import annotations
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from gg_desktop import steam_artwork, custom_game_art
from gg_desktop.local_art import game_cover_path, game_needs_portrait, invalidate_cover_cache


class Response:
    def __init__(self, uri, data, typ="application/json"):
        self.uri, self.data = uri, data
        self.headers = {"Content-Type": typ}
    def geturl(self):
        return self.uri
    def read(self, n=-1):
        return self.data if n == -1 else self.data[:n]
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False


class SteamArtworkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        p = patch.object(steam_artwork, "artwork_cache_dir",
                         return_value=self.root / "remote")
        p.start()
        self.addCleanup(p.stop)
        self.game = SimpleNamespace(
            key="Steam:7654321:unique", name="Example",
            launcher="Steam", app_id="7654321",
            install_path=str(self.root / "steamapps" / "common" / "Game"))
        Path(self.game.install_path).mkdir(parents=True)
        invalidate_cover_cache()

    def metadata(self, app_id="7654321", portrait=None, name="Example"):
        if portrait is None:
            portrait = "a" * 40 + "/library_600x900_2x.jpg"
        return json.dumps({"response": {"store_items": [
            {"appid": int(app_id), "name": name,
             "assets": {"library_capsule_2x": portrait,
                        "library_capsule": "library_600x900.jpg"}}
        ]}}).encode("utf-8")

    def test_modern_hashed_steam_art_resolves_to_exact_game(self):
        urls = []
        def fetch(request, timeout):
            uri = request.full_url
            urls.append(uri)
            if "IStoreBrowseService" in uri:
                return Response(uri, self.metadata())
            return Response(uri, b"\xff\xd8\xff"+b"x"*2000, "image/jpeg")
        result = steam_artwork.fetch_steam_cover(
            self.game, opener=fetch, game_active=lambda: False)
        self.assertTrue(result)
        self.assertEqual(game_cover_path(self.game), result)
        self.assertTrue(any("a"*40+"/library_600x900_2x.jpg" in uri for uri in urls))
        self.assertFalse(any("/header.jpg" in uri for uri in urls))

    def test_wrong_appid_and_untrusted_asset_path_rejected(self):
        def wrong(request, timeout):
            return Response(request.full_url, self.metadata(app_id="123"))
        self.assertEqual(steam_artwork._read_store_assets(
            "7654321", opener=wrong), ())
        self.assertEqual(steam_artwork.lookup_steam_game_name(
            "7654321", opener=wrong), "")
        def bad(request, timeout):
            return Response(request.full_url, self.metadata(
                portrait="../../steal/other.jpg"))
        urls = steam_artwork._read_store_assets("7654321", opener=bad)
        self.assertTrue(urls)
        self.assertTrue(all("/steam/apps/7654321/" in url for url in urls))
        self.assertTrue(all("steal" not in url for url in urls))

    def test_manual_title_verification_and_no_network_during_gameplay(self):
        def fetch(request, timeout):
            return Response(request.full_url, self.metadata(name="Verified official title"))
        self.assertEqual(steam_artwork.lookup_steam_game_name(
            "7654321", opener=fetch), "Verified official title")
        def fail(*_args, **_kwargs):
            raise AssertionError("No cover network while gaming")
        self.assertEqual(steam_artwork.fetch_steam_cover(
            self.game, game_active=lambda: True, opener=fail), "")

    def test_local_header_is_not_mistaken_for_portrait(self):
        cache = self.root / "appcache" / "librarycache"
        cache.mkdir(parents=True)
        (cache / "7654321_header.jpg").write_bytes(b"\xff\xd8\xff"+b"x"*2000)
        invalidate_cover_cache()
        self.assertTrue(game_needs_portrait(self.game))
        portrait = cache / "7654321_library_600x900.jpg"
        portrait.write_bytes(b"\xff\xd8\xff"+b"x"*2000)
        invalidate_cover_cache()
        self.assertEqual(game_cover_path(self.game), str(portrait))
        self.assertFalse(game_needs_portrait(self.game))


class UserCoverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        p = patch.object(custom_game_art, "override_dir",
                         return_value=self.root / "custom")
        p.start()
        self.addCleanup(p.stop)
        self.game = SimpleNamespace(
            key="Epic:someid:unique", name="Game", launcher="Epic Games",
            app_id="someid", install_path=str(self.root / "Game"))
        Path(self.game.install_path).mkdir()
        self.src = self.root / "source.png"
        self.src.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 2400)

    def test_explicit_cover_is_local_and_install_never_changes(self):
        output = custom_game_art.choose_custom_cover(self.game, str(self.src))
        self.assertEqual(game_cover_path(self.game), output)
        self.assertEqual(list(Path(self.game.install_path).iterdir()), [])
        another = SimpleNamespace(**{**vars(self.game), "install_path": str(self.root/"Other")})
        self.assertEqual(custom_game_art.override_path(another), "")
        self.assertTrue(custom_game_art.clear_custom_cover(self.game))
        self.assertEqual(custom_game_art.override_path(self.game), "")

    def test_bad_or_fake_image_rejected(self):
        fake = self.root / "fake.jpg"
        fake.write_bytes(b"no image"*200)
        with self.assertRaises(ValueError):
            custom_game_art.choose_custom_cover(self.game, str(fake))


if __name__ == "__main__":
    unittest.main()
