"""Old Files C-drive scanning safety and empty-result regression tests.

Use only disposable temporary folders. Production root admission still requires
a verified local Windows fixed-drive root, never an arbitrary caller path.
"""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import time
from unittest.mock import patch
import unittest

from core import OldFile
from old_files_scope import (
    accepted_old_files_scope, drive_file_allowed, scan_old_files_scope,
)
from cleanup_actions import recycle_old_files


class DriveScopeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="gg-drive-fixture-")
        self.addCleanup(tmp.cleanup)
        self.drive = Path(tmp.name)
        self.drive_validator = patch(
            "old_files_scope.is_fixed_drive_root",
            side_effect=lambda item: Path(item).absolute() == self.drive.absolute()
        )
        self.drive_validator.start()
        self.addCleanup(self.drive_validator.stop)

    def create(self, name, *, age_days=300):
        target = self.drive / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"Disposable synthetic test content")
        timestamp = time.time() - age_days * 86400
        os.utime(target, (timestamp, timestamp))
        return target

    def test_drive_scans_old_normal_files_but_never_protected_os_or_game(self):
        good = self.create("Users/Sample/Downloads/old.zip", age_days=300)
        new = self.create("Users/Sample/Downloads/new.zip", age_days=2)
        protected = self.create("Windows/System32/do-not-touch.dll")
        program = self.create("Program Files/OldApp/core.dll")
        appdata = self.create("Users/Sample/AppData/Old/log.txt")
        game = self.create("Games/EpicGame/old-assets.dat")
        result = scan_old_files_scope(
            self.drive, 180, known_game_roots=[str(game.parent)])
        self.assertEqual(result.status, "complete")
        self.assertEqual([v.path for v in result.files], [str(good)])
        self.assertTrue(new.exists())
        self.assertTrue(protected.exists())
        self.assertTrue(program.exists())
        self.assertTrue(appdata.exists())
        self.assertTrue(game.exists())

    def test_no_matches_returns_genuine_completed_empty_result(self):
        self.create("Users/Sample/Downloads/new.txt", age_days=1)
        result = scan_old_files_scope(self.drive, 180)
        self.assertEqual(result.status, "complete")
        self.assertEqual(len(result.files), 0)
        self.assertIn("completed", result.message.lower())

    def test_c_drive_result_limit_is_explicitly_partial(self):
        self.create("Users/Sample/Downloads/old.txt", age_days=500)
        self.create("Users/Sample/Downloads/old2.txt", age_days=500)
        result = scan_old_files_scope(self.drive, 180, max_matches=1)
        self.assertEqual(result.status, "partial")
        self.assertIn("limit", result.message.lower())

    def test_scan_item_limit_is_explicitly_partial(self):
        self.create("Users/Sample/Downloads/old.txt", age_days=500)
        result = scan_old_files_scope(self.drive, 180, max_entries=1)
        self.assertEqual(result.status, "partial")
        self.assertIn("limit", result.message.lower())

    def test_cancel_does_not_touch_any_files(self):
        file = self.create("Users/Sample/Downloads/safe.txt")
        with self.assertRaises(InterruptedError):
            scan_old_files_scope(self.drive, 180, cancel=lambda: True)
        self.assertTrue(file.is_file())
        self.assertEqual(file.read_bytes(), b"Disposable synthetic test content")

    def test_junction_or_symlink_never_followed(self):
        private = self.drive / "secret"
        private.mkdir()
        confidential = self.create("secret/keep.txt", age_days=600)
        link = self.drive / "Users" / "shortcut"
        link.parent.mkdir(exist_ok=True)
        try:
            link.symlink_to(private, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation not supported in this environment")
        found = scan_old_files_scope(self.drive, 180)
        self.assertNotIn(str(link / "keep.txt"), [x.path for x in found.files])
        self.assertTrue(confidential.exists())

    def test_drive_file_eligibility_rejects_os_and_outside(self):
        path = self.create("Users/Sample/Downloads/safe.zip")
        system = self.create("Windows/boot.sys")
        root = self.create("boot.ini")
        self.assertTrue(drive_file_allowed(self.drive, path))
        self.assertFalse(drive_file_allowed(self.drive, system))
        self.assertFalse(drive_file_allowed(self.drive, root))
        with tempfile.TemporaryDirectory() as outside:
            test = Path(outside) / "not-under-selected-drive.dat"
            test.write_bytes(b"private")
            self.assertFalse(drive_file_allowed(self.drive, test))

    def test_folder_scope_selection_retains_strict_original_validation(self):
        self.assertFalse(accepted_old_files_scope(self.drive / "Windows"))
        self.assertTrue(accepted_old_files_scope(self.drive))

    def test_c_drive_cleanup_never_recycles_system_files(self):
        system = self.create("Windows/System32/critical.dat", age_days=500)
        metadata = system.stat()
        record = OldFile(
            str(system), metadata.st_size, metadata.st_mtime,
            metadata.st_dev, metadata.st_ino, metadata.st_mtime_ns,
            metadata.st_nlink,
        )
        with patch("cleanup_actions.is_fixed_drive_root", return_value=True), \
             patch("cleanup_actions.recycle_file") as recycler, \
             patch("cleanup_actions.log_event"):
            result = recycle_old_files(
                [record], [], "test", review_root=self.drive,
                min_age_days=180, managed_roots=())
        self.assertEqual(result["completed"], 0)
        self.assertEqual(len(result["skipped"]), 1)
        recycler.assert_not_called()
        self.assertTrue(system.exists())

    def test_c_drive_cleanup_fails_closed_without_game_ownership(self):
        path = self.create("Users/Sample/Downloads/old.zip", age_days=500)
        state = path.stat()
        file = OldFile(
            str(path), state.st_size, state.st_mtime, state.st_dev,
            state.st_ino, state.st_mtime_ns, state.st_nlink,
        )
        with patch("cleanup_actions.is_fixed_drive_root", return_value=True), \
             patch("cleanup_actions.recycle_file") as recycler, \
             patch("cleanup_actions.log_event"):
            result = recycle_old_files(
                [file], [], "test", review_root=self.drive,
                min_age_days=180)
        self.assertEqual(result["completed"], 0)
        recycler.assert_not_called()
        self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
