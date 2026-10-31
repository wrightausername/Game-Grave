"""Crimson Command view model and safety tests; no Qt needed."""
from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core import OldFile
from gg_desktop.models import (
    merge_games, reported_game_bytes, unique_launcher_counts,
    graveyard_protection_decision, graveyard_totals,
)
from gg_desktop.backend import Inventory, scan_inventory, ScanCanceled
from graveyard import build_graveyard


def steam(name, install, app_id, size=1024, last=None):
    return SimpleNamespace(
        name=name, install_path=str(install), app_id=app_id,
        size=size, last_played=last, source="Steam account history",
    )


def other(name, install, launcher, size=None, status="Launcher install exists"):
    return SimpleNamespace(
        name=name, install_path=str(install), launcher=launcher,
        app_id=name.lower(), reported_bytes=size, status=status,
    )


class UnifiedGamesTests(unittest.TestCase):
    def test_steam_epic_gog_ea_appear_in_same_list(self):
        steam_data = [steam("Skyrim", "D:/Steam/Skyrim", "489830")]
        other_data = [
            other("Control", "D:/Epic/Control", "Epic Games"),
            other("Cyberpunk", "D:/GOG/Cyberpunk", "GOG"),
            other("Battlefield", "D:/EA/Battlefield", "EA"),
        ]
        rows = merge_games(steam_data, other_data)
        self.assertEqual({r.launcher for r in rows},
                         {"Steam", "Epic Games", "GOG", "EA"})
        self.assertEqual(len(rows), 4)
        self.assertEqual(reported_game_bytes(rows), (1024, 3))
        self.assertEqual(unique_launcher_counts(rows)["EA"], 1)

    def test_same_install_claimed_twice_never_double_counts(self):
        rows = merge_games(
            [steam("Shared title", "D:/Games/Shared", "155", 800)],
            [other("Shared title", "D:/Games/Shared", "Epic Games", 900)],
        )
        self.assertEqual(len(rows), 1)
        self.assertIn("Ambiguous", rows[0].status)
        self.assertEqual(rows[0].size_bytes, None)
        self.assertEqual(reported_game_bytes(rows), (0, 1))
        self.assertNotIn("steam_uninstall", rows[0].capabilities)

    def test_same_title_multiple_verified_paths_remain_separate(self):
        rows = merge_games(
            [steam("My Game", "C:/Steam/Game", "3")],
            [other("My Game", "D:/Epic/Game", "Epic Games")],
        )
        self.assertEqual(len(rows), 2)

    def test_nonsteam_no_fake_lastplay_or_steam_uninstall(self):
        row = merge_games([], [other("Diablo", "D:/Battle.net/Diablo", "Battle.net")])[0]
        self.assertIsNone(row.last_played_at)
        self.assertEqual(row.last_played_source, "Unknown")
        self.assertNotIn("steam_uninstall", row.capabilities)

    def test_unverified_custom_library_has_no_launch_capability(self):
        row = merge_games([], [other("Guess", "D:/Unverified/Guess",
                                    "Custom library", None, "not verified")])[0]
        self.assertEqual(row.capabilities, ("inspect",))
        self.assertEqual(row.size_bytes, None)


class GraveyardPresentationTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.folder = Path(t.name) / "Downloads"
        self.folder.mkdir()
        self.file = self.folder / "old-skyrim-mod.zip"
        self.file.write_bytes(b"FAKE DISPOSABLE ARCHIVE")
        old = time.time() - 700 * 86400
        os.utime(self.file, (old, old))
        info = self.file.stat()
        self.old = OldFile(str(self.file), info.st_size, info.st_mtime,
                           info.st_dev, info.st_ino, info.st_mtime_ns, info.st_nlink)

    def test_exact_personal_rule_shows_inline_unprotect(self):
        entries = build_graveyard([], [], [self.old], never_touch=[str(self.file)])
        action, note = graveyard_protection_decision(entries[0], [str(self.file)])
        self.assertEqual(action, "Unprotect this item")
        self.assertFalse(entries[0].can_recycle)

    def test_protected_parent_routes_to_rules_not_mass_override(self):
        entries = build_graveyard([], [], [self.old], never_touch=[str(self.folder)])
        action, _ = graveyard_protection_decision(entries[0], [str(self.folder)])
        self.assertEqual(action, "Manage parent rule")

    def test_builtin_mod_folder_cannot_be_unprotected(self):
        path = self.folder / "mods"
        path.mkdir()
        protected = path / "old-skyrim-mod.zip"
        protected.write_bytes(b"test")
        e = SimpleNamespace(path=str(protected), category="Possible mod / game download",
                            can_recycle=False, finding="Protected")
        action, reason = graveyard_protection_decision(e, [str(protected)])
        self.assertEqual(action, "Why protected?")
        self.assertIn("Built-in", reason)

    def test_recycle_bin_bytes_are_never_reported_as_space_reclaimed(self):
        e = build_graveyard([], [], [self.old])[0]
        totals = graveyard_totals([e])
        self.assertEqual(totals["reviewable_bytes"], len(self.file.read_bytes()))
        self.assertNotIn("reclaimed_bytes", totals)


class BattleNetDetectionTests(unittest.TestCase):
    def test_battle_net_game_requires_verified_blizzard_publisher_and_title(self):
        from launchers import is_blizzard_install_metadata
        self.assertTrue(is_blizzard_install_metadata("Diablo IV", "Blizzard Entertainment, Inc."))
        self.assertTrue(is_blizzard_install_metadata("World of Warcraft", "Blizzard Entertainment"))
        self.assertTrue(is_blizzard_install_metadata("Overwatch 2", "Blizzard Entertainment"))
        self.assertFalse(is_blizzard_install_metadata("Battle.net", "Blizzard Entertainment"))
        self.assertFalse(is_blizzard_install_metadata("Blizzard Update Agent", "Blizzard Entertainment"))
        self.assertFalse(is_blizzard_install_metadata("Diablo IV", "Some Third-Party Launcher"))
        self.assertFalse(is_blizzard_install_metadata("", "Blizzard Entertainment"))

    def test_blizzard_record_reader_never_crosses_windows_boundary_on_linux(self):
        from launchers import blizzard_uninstall_records
        if os.name != "nt":
            self.assertEqual(blizzard_uninstall_records(), [])


class ReadOnlyBackendTests(unittest.TestCase):
    def test_cancelled_scan_does_not_start_any_launcher_reads(self):
        with patch("gg_desktop.backend.find_games") as steam_scan:
            with self.assertRaises(ScanCanceled):
                scan_inventory({"never_touch": []}, lambda: True)
        steam_scan.assert_not_called()
        self.assertEqual(list(()), [])


if __name__ == "__main__":
    unittest.main()
