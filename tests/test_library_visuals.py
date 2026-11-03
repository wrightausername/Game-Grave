"""Deterministic tests for real cover art and numeric library sorting."""
from __future__ import annotations

from dataclasses import replace
from io import BytesIO
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from gg_desktop.models import GameRecord
from gg_desktop.library_sort import (
    sort_game_records, filter_game_records, next_header_sort)
from gg_desktop.local_art import (
    game_cover_path, save_custom_cover, invalidate_cover_cache,
    steam_art_hashes)
from gg_desktop.artwork_download import (
    official_steam_urls, download_official_steam_covers)


def game(name, launcher="Steam", app_id="123", size=None, played=None,
         path="C:/Games/Test"):
    return GameRecord(
        key=launcher + ":" + app_id + ":" + path,
        name=name, launcher=launcher, app_id=app_id,
        install_path=path, install_evidence="Test source",
        size_bytes=size, size_source="Test bytes",
        last_played_at=played, last_played_source="Test clock",
        status="Installed", capabilities=("inspect",))


class LibrarySortingTests(unittest.TestCase):
    def setUp(self):
        self.games = [
            game("Big", "Steam", "10", size=100 * 1024**3, played=500),
            game("Small", "EA", "11", size=9 * 1024**3, played=100),
            game("Unknown", "Epic Games", "12", size=None, played=None),
            game("Medium", "GOG", "13", size=28 * 1024**3, played=300),
        ]

    def test_sizes_are_numeric_and_missing_last(self):
        self.assertEqual(
            [g.name for g in sort_game_records(self.games, "Size largest")],
            ["Big", "Medium", "Small", "Unknown"])
        self.assertEqual(
            [g.name for g in sort_game_records(self.games, "Size smallest")],
            ["Small", "Medium", "Big", "Unknown"])

    def test_last_played_is_numeric_and_missing_last(self):
        self.assertEqual(
            [g.name for g in sort_game_records(self.games, "Recently played")],
            ["Big", "Medium", "Small", "Unknown"])
        self.assertEqual(
            [g.name for g in sort_game_records(self.games, "Oldest played")],
            ["Small", "Medium", "Big", "Unknown"])

    def test_names_launchers_and_header_toggle(self):
        self.assertEqual(
            sort_game_records(self.games, "Game A to Z")[0].name, "Big")
        self.assertEqual(
            sort_game_records(self.games, "Game Z to A")[0].name, "Unknown")
        self.assertEqual(
            sort_game_records(self.games, "Launcher A to Z")[0].launcher, "EA")
        self.assertEqual(
            sort_game_records(self.games, "Launcher Z to A")[0].launcher, "Steam")
        self.assertEqual(next_header_sort(3, "Size largest"),
                         "Size smallest")
        self.assertEqual(next_header_sort(2, "Size largest"),
                         "Recently played")
        self.assertEqual([g.name for g in filter_game_records(
            self.games, query="med", launcher="GOG")], ["Medium"])


class RealCoverArtTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {
            "LOCALAPPDATA": str(self.root / "AppData")})
        self.env.start()
        self.addCleanup(self.env.stop)
        invalidate_cover_cache()
        self.addCleanup(invalidate_cover_cache)
        self.steam_root = self.root / "Steam"
        self.install = self.steam_root / "steamapps" / "common" / "Test"
        self.install.mkdir(parents=True)
        self.game = game(
            "A Sample Game", app_id="455", path=str(self.install))
        self.poster = self.root / "art.jpg"
        Image.new("RGB", (320, 480), (49, 67, 91)).save(
            self.poster, quality=95)

    def test_modern_hashed_steam_portrait(self):
        target = (self.steam_root / "appcache" / "librarycache" /
                  "455" / ("d" * 40) / "library_600x900.jpg")
        target.parent.mkdir(parents=True)
        target.write_bytes(self.poster.read_bytes())
        self.assertEqual(game_cover_path(self.game), str(target))
        self.assertIn("d" * 40, steam_art_hashes(self.game))
        self.assertTrue(any(("d" * 40) in url for url in
                            official_steam_urls(self.game)))

    def test_override_for_non_steam_game(self):
        epic = game("Not on Steam", "Epic Games", "epic01",
                    path=str(self.root / "Epic"))
        self.assertEqual(game_cover_path(epic), "")
        result = save_custom_cover(epic, str(self.poster))
        self.assertEqual(game_cover_path(epic), result)
        self.assertIn("GameGrave", result)
        self.assertTrue(Path(result).exists())

    def test_public_steam_fetch_only_on_click(self):
        with Image.open(self.poster) as image:
            payload = BytesIO()
            image.save(payload, "JPEG")
        fetched = []
        def fake_request(url):
            fetched.append(url)
            return payload.getvalue()
        report = download_official_steam_covers(
            [self.game], game_active=lambda: False,
            fetch=fake_request, limit=1)
        self.assertEqual(report["downloaded"], 1)
        self.assertEqual(len(fetched), 1)
        self.assertTrue(game_cover_path(self.game).endswith("455.jpg"))
        fetched.clear()
        another = game("Another Steam Game", app_id="456",
                       path=str(self.install))
        paused = download_official_steam_covers(
            [another], game_active=lambda: True,
            fetch=fake_request, limit=1)
        self.assertTrue(paused["paused_for_game"])
        self.assertFalse(fetched)

    def test_invalid_launcher_and_images_rejected(self):
        self.assertEqual(official_steam_urls(
            game("Wrong", launcher="Epic Games")), ())
        self.assertEqual(official_steam_urls(
            game("Bad", app_id="../etc/passwd")), ())


if __name__ == "__main__":
    unittest.main()
