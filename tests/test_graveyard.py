"""Regression checks for Game Grave's read-only Graveyard review rules."""
import tempfile
import time
import unittest
from pathlib import Path

from core import OldFile, SteamGame, ModFolder
from graveyard import build_graveyard, looks_like_game_archive


class GraveyardTests(unittest.TestCase):
    def test_rejects_unrelated_archives(self):
        self.assertFalse(looks_like_game_archive(Path("taxes2020.zip")))
        self.assertFalse(looks_like_game_archive(Path("photos.rar")))
        self.assertTrue(looks_like_game_archive(Path("skyrim-mod-1.7z")))
        self.assertTrue(looks_like_game_archive(Path("addonpack.oiv")))
        self.assertTrue(looks_like_game_archive(Path("something.mrpack")))

    def test_old_game_archive_needs_review_even_when_eligible(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "skyrim-mod-bundle.zip"
            p.write_bytes(b"safe test")
            now = time.time()
            files = [OldFile(str(p), p.stat().st_size, now-86400*1100)]
            entries = build_graveyard([], [], files, min_days=730, now=now)
            self.assertEqual(len(entries), 1)
            self.assertTrue(entries[0].can_recycle)
            self.assertIn("unknown", entries[0].finding.lower())
            self.assertIn("review", entries[0].protection.lower())
            self.assertTrue(p.exists(), "inventory must remain read-only")

    def test_never_touch_prevents_recycling(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "modpack.zip"
            p.write_bytes(b"don't delete")
            now = time.time()
            items = build_graveyard([], [], [OldFile(str(p), 12, now-999*86400)],
                                   min_days=365, never_touch=[folder], now=now)
            self.assertEqual(len(items), 1)
            self.assertFalse(items[0].can_recycle)

    def test_installed_games_not_recycled(self):
        now = time.time()
        game = SteamGame("123", "Really old game", "C:/steam", "C:/steam/common/game",
                         15_000_000_000, now - 900*86400, "Steam account history")
        item = build_graveyard([game], [], [], 365, now=now)[0]
        self.assertFalse(item.can_recycle)
        self.assertEqual(item.category, "Neglected installed game")

    def test_old_mod_folder_is_protected_even_if_unmatched(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"UnmatchedMods"
            p.mkdir()
            now=time.time()
            import os
            os.utime(p,(now-800*86400, now-800*86400))
            mod=ModFolder(p.name, str(p), folder, "Unmatched Steam folder", ("mods",),
                          400, 3, False, "Steam game folder", "May belong to a moved game")
            item=build_graveyard([], [mod], [], 365, now=now)[0]
            self.assertFalse(item.can_recycle)
            self.assertIn("Uncertain", item.protection)
            self.assertTrue(p.exists())

    def test_recent_and_unknown_last_play_excluded(self):
        now = time.time()
        recent = SteamGame("1", "Recent", "lib", "path", 10, now-30*86400, "Steam")
        unknown = SteamGame("2", "Unknown", "lib", "path", 20, None, "Unknown")
        self.assertEqual(build_graveyard([recent, unknown], [], [], 365, now=now), [])

if __name__ == '__main__':
    unittest.main()
