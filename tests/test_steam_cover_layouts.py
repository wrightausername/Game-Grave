"""Steam cover layouts based on real Steam library cache structure.

The image bytes are disposable fixtures: no network, scraping or game files.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest

from gg_desktop.local_art import game_cover_path, invalidate_cover_cache


class SteamCoverLayoutsTests(unittest.TestCase):
    def setUp(self):
        invalidate_cover_cache()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "SteamLibrary"
        self.install = self.root / "steamapps" / "common" / "Example Game"
        self.install.mkdir(parents=True)
        self.game = SimpleNamespace(
            launcher="Steam", app_id="322", install_path=str(self.install))

    def _file(self, suffix):
        art = self.root / "appcache" / "librarycache" / suffix
        art.parent.mkdir(parents=True, exist_ok=True)
        art.write_bytes(b"\xff\xd8\xff" + b"fixture" * 500)
        invalidate_cover_cache()
        return str(art)

    def test_finds_older_flat_steam_cache_art(self):
        expected = self._file("322_library_600x900.jpg")
        self.assertEqual(game_cover_path(self.game), expected)

    def test_finds_newer_app_id_directory_art(self):
        expected = self._file("322/library_600x900_2x.jpg")
        self.assertEqual(game_cover_path(self.game), expected)

    def test_finds_content_hash_app_id_directory_art(self):
        expected = self._file("322/" + "a" * 40 + "/library_600x900.jpg")
        self.assertEqual(game_cover_path(self.game), expected)

    def test_similar_app_ids_cannot_cross_assign_artwork(self):
        self._file("322/" + "a" * 40 + "/library_600x900.jpg")
        unrelated = SimpleNamespace(
            launcher="Steam", app_id="323", install_path=str(self.install))
        self.assertEqual(game_cover_path(unrelated), "")

    def test_no_fake_fallback_or_entire_disk_crawl(self):
        deep = self.install / "Nested" / "Another"
        deep.mkdir(parents=True)
        (deep / "cover.jpg").write_bytes(b"x" * 2200)
        self.assertEqual(game_cover_path(self.game), "")


if __name__ == "__main__":
    unittest.main()
