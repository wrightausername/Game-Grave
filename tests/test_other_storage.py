"""Bounded, read-only Other Storage explanation tests. No user files involved."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from other_storage import (
    analyze_other_storage, category_for_folder, _same_volume,
)


class OtherStorageTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.disk = Path(t.name) / "TestDrive"
        self.disk.mkdir()
        if os.name == "nt":
            # Production requires a fixed drive root. Unit fixtures are
            # deliberately isolated subfolders rather than the tester's C:.
            mocked_drive = patch(
                "other_storage._check_requested_root",
                side_effect=lambda requested: Path(requested))
            mocked_drive.start()
            self.addCleanup(mocked_drive.stop)
        self.apps = self.disk / "Program Files" / "Game Grave Test"
        self.apps.mkdir(parents=True)
        (self.apps / "app-data.bin").write_bytes(b"APPTEST123")
        self.user_data = self.disk / "Users" / "TestPerson" / "Documents"
        self.user_data.mkdir(parents=True)
        (self.user_data / "important.txt").write_bytes(b"PERSONAL123")
        self.game_dir = self.disk / "SteamLibrary" / "steamapps" / "common" / "Game X"
        self.game_dir.mkdir(parents=True)
        (self.game_dir / "data.bin").write_bytes(b"GAMEDATA123456")
        self.original = {
            str(path): path.read_bytes()
            for path in self.disk.rglob("*") if path.is_file()
        }

    def tearDown(self):
        for name, contents in self.original.items():
            self.assertEqual(Path(name).read_bytes(), contents,
                             "Metadata analysis must not touch test files")

    def test_other_storage_reports_contributors_not_fake_disk_accounting(self):
        report = analyze_other_storage(self.disk, [str(self.game_dir)])
        self.assertEqual(report.root, str(self.disk))
        self.assertGreaterEqual(report.entries_seen, 6)
        self.assertGreaterEqual(report.excluded_games, 1)
        folders = {x.name: x for x in report.folders}
        self.assertEqual(folders["Program Files"].apparent_bytes, 10)
        self.assertEqual(folders["Users"].apparent_bytes, 11)
        self.assertEqual(folders["SteamLibrary"].apparent_bytes, 0)
        self.assertEqual(report.analyzed_bytes, 21)
        self.assertEqual(folders["Users"].category, "User profiles / media / AppData")
        self.assertEqual(folders["Program Files"].category, "Apps and shared app data")

    def test_drilldown_into_subfolder_has_its_own_rows(self):
        report = analyze_other_storage(
            self.disk, scope=self.disk / "Users")
        self.assertEqual({x.name for x in report.folders}, {"TestPerson"})
        self.assertEqual(report.folders[0].apparent_bytes, 11)

    def test_outside_scope_rejected(self):
        with tempfile.TemporaryDirectory() as other:
            with self.assertRaisesRegex(ValueError, "outside"):
                analyze_other_storage(self.disk, scope=Path(other))

    def test_linked_directory_not_followed(self):
        secret = self.disk / "Private"
        secret.mkdir()
        (secret / "secret.txt").write_bytes(b"TOP-SECRET")
        link = self.disk / "Shortcut"
        try:
            link.symlink_to(secret, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("No symlink privileges here")
        report = analyze_other_storage(self.disk)
        self.assertGreaterEqual(report.skipped_entries, 1)
        self.assertFalse(any(x.name == "Shortcut" and x.apparent_bytes > 0
                             for x in report.folders))
        self.assertEqual((secret / "secret.txt").read_bytes(), b"TOP-SECRET")

    def test_stops_after_limit_without_claiming_complete(self):
        report = analyze_other_storage(self.disk, max_entries=1)
        self.assertFalse(report.complete)
        self.assertIn("limit", report.limitation.lower())
        self.assertLessEqual(report.analyzed_bytes, 21)

    def test_cancel_without_touching_files(self):
        report = analyze_other_storage(self.disk, cancel=lambda: True)
        self.assertFalse(report.complete)
        self.assertIn("canceled", report.limitation.lower())
        self.assertEqual(report.analyzed_bytes, 0)

    def test_category_labels_do_not_pretend_other_means_junk(self):
        self.assertEqual(category_for_folder("Windows"), "Windows / system")
        self.assertEqual(category_for_folder("ProgramData"), "Apps and shared app data")
        self.assertEqual(category_for_folder("Users"), "User profiles / media / AppData")
        self.assertEqual(category_for_folder("SteamLibrary"),
                         "Game library directories (not verified)")
        self.assertEqual(category_for_folder("My Work"),
                         "Other folders / root files")


if __name__ == "__main__":
    unittest.main()
