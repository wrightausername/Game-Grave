"""Drive scope, metadata-only traversal and unchanged per-file recovery checks."""
from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from core import OldFile
from gg_desktop.backend import Inventory
from gg_desktop.old_files_data import (Drive, ScanResult, key, make_plan, protected_roots,
    recycle_reviewed, review_reason, scan_files)


def old_file(path, age=400, data=b"Disposable old file"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    moment = time.time() - age * 86400
    os.utime(path, (moment, moment))
    info = path.stat()
    return OldFile(str(path), info.st_size, info.st_mtime, info.st_dev, info.st_ino, info.st_mtime_ns, info.st_nlink)


def drive_fixture(root):
    drive, second = root / "DriveD", root / "DriveE"
    home = drive / "Users" / "Player"
    downloads = home / "Downloads"
    downloads.mkdir(parents=True)
    second.mkdir()
    drives = [Drive(str(drive), "D: • Disposable local drive"), Drive(str(second), "E: • Disposable removable drive", "Removable drive")]
    return drive, second, home, downloads, drives


class OldFilesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="GG-old-files-unit-")
        self.root = Path(self.temp.name)
        self.drive, self.second, self.home, self.downloads, self.drives = drive_fixture(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def plan(self, mode="full", **kwargs):
        return make_plan(str(self.drive), mode, 180, drives=self.drives, home=self.home, **kwargs)

    def test_full_drive_finds_older_files_outside_quick_folders(self):
        quick = old_file(self.downloads / "old.zip")
        deep = old_file(self.drive / "Ordinary" / "Nested" / "deep.log")
        old_file(self.drive / "Ordinary" / "recent.txt", age=2)
        result = scan_files(self.plan())
        self.assertEqual({f.path for f in result.files}, {quick.path, deep.path})
        self.assertFalse(result.limited)
        self.assertIn("2 files", result.summary())

    def test_quick_scope_stays_on_the_selected_drive(self):
        chosen = old_file(self.downloads / "old.zip")
        old_file(self.drive / "Elsewhere" / "deep.log")
        old_file(self.second / "Downloads" / "other.zip")
        result = scan_files(self.plan("quick", folder=str(self.downloads)))
        self.assertEqual([f.path for f in result.files], [chosen.path])
        other = make_plan(str(self.second), "quick", 180, drives=self.drives, home=self.home)
        self.assertEqual(len(scan_files(other).files), 1)

    def test_no_quick_folders_explains_full_scan_option(self):
        with self.assertRaisesRegex(ValueError, "Full scan"):
            make_plan(str(self.second), "quick", 180, drives=self.drives, home=self.home)

    def test_only_enumerated_local_drives_can_use_drive_mode(self):
        with self.assertRaisesRegex(ValueError, "local drive list"):
            make_plan(str(self.root), "full", 180, drives=self.drives)

    def test_folder_mode_does_not_grant_a_drive_root_exception(self):
        with self.assertRaises(ValueError):
            make_plan(Path(self.root.anchor), "folder", 180)

    def test_system_game_save_mod_never_touch_roots_are_excluded(self):
        for name in ("Windows", "Program Files", "Mods", "SteamApps", "Saves", "AppData", "$Recycle.Bin", "Games"):
            old_file(self.drive / name / "KEEP.txt")
        private = self.drive / "PersonalProtected"
        installed = self.drive / "UnusualInstallName"
        old_file(private / "KEEP.txt")
        old_file(installed / "KEEP.txt")
        wanted = old_file(self.downloads / "review.zip")
        result = scan_files(self.plan(protections=(str(private), str(installed))))
        self.assertEqual([f.path for f in result.files], [wanted.path])
        self.assertGreaterEqual(result.skipped, 10)

    def test_inventory_roots_are_part_of_scan_and_recycle_protection(self):
        from types import SimpleNamespace
        inv = Inventory(games=[SimpleNamespace(install_path="install")], mods=[SimpleNamespace(path="staging")], saves=[SimpleNamespace(path="saves")])
        roots = protected_roots(inv, {"never_touch": ["personal"]})
        self.assertTrue({"install", "staging", "saves", "personal"}.issubset(roots))

    def test_symlinks_and_hardlinks_do_not_become_candidates(self):
        original = self.root / "Outside" / "KEEP.txt"
        old_file(original)
        try:
            (self.drive / "Redirected").symlink_to(original.parent, target_is_directory=True)
            os.link(original, self.downloads / "Hardlink.txt")
        except OSError:
            self.skipTest("Link privileges unavailable")
        result = scan_files(self.plan())
        self.assertFalse(result.files)
        self.assertGreaterEqual(result.skipped, 2)

    def test_cancellation_during_enumeration_never_returns_partial_success(self):
        for i in range(8):
            old_file(self.downloads / f"old{i}.zip")
        checks = [0]
        def cancel():
            checks[0] += 1
            return checks[0] > 5
        with self.assertRaises(InterruptedError):
            scan_files(self.plan(), cancel)

    def test_entry_result_and_depth_limits_are_explicit(self):
        for i in range(5):
            old_file(self.downloads / f"old{i}.zip")
        for limit, value in (("MAX_ENTRIES", 1), ("MAX_RESULTS", 1), ("MAX_DEPTH", 0)):
            with patch("gg_desktop.old_files_data." + limit, value):
                result = scan_files(self.plan())
            self.assertTrue(result.limited)
            self.assertTrue(result.issues)
            self.assertIn("Partial scan", result.summary())

    def test_removed_or_replaced_drive_is_not_reused(self):
        plan = self.plan()
        original = self.drive.with_name("PreviousDrive")
        self.drive.rename(original)
        self.drive.mkdir()
        with self.assertRaisesRegex(ValueError, "drive was replaced"):
            scan_files(plan)

    def test_file_content_is_not_opened_during_scan(self):
        record = old_file(self.downloads / "private.txt")
        with patch.object(Path, "open", side_effect=AssertionError("No content reads")):
            result = scan_files(self.plan())
        self.assertEqual(result.files[0], record)

    def test_recycling_keeps_existing_parent_scope_and_age_checks(self):
        record = old_file(self.downloads / "old.zip")
        result = scan_files(self.plan())
        with patch("gg_desktop.old_files_data.recycle_old_files", return_value={"completed": 1, "skipped": [], "recovery_warnings": 0}) as worker:
            outcome = recycle_reviewed(result, [record], (), "test")
        self.assertEqual(outcome["completed"], 1)
        self.assertEqual(worker.call_args.kwargs["review_root"], self.downloads)
        self.assertEqual(worker.call_args.kwargs["min_age_days"], 180)
        self.assertEqual(record.path, str(self.downloads / "old.zip"))

    def test_new_protections_and_out_of_scope_records_block_recycling(self):
        record = old_file(self.downloads / "old.zip")
        result = scan_files(self.plan())
        outside = old_file(self.second / "Other" / "foreign.zip")
        for selected, rules in (([record], (str(self.downloads),)), ([outside], ())):
            with patch("gg_desktop.old_files_data.recycle_old_files") as worker:
                with self.assertRaises(ValueError):
                    recycle_reviewed(result, selected, rules, "test")
                worker.assert_not_called()

    def test_real_worker_refuses_changed_and_recent_files(self):
        record = old_file(self.downloads / "old.zip")
        result = scan_files(self.plan())
        Path(record.path).write_bytes(b"Changed since scan")
        with patch("cleanup_actions.recycle_file") as transport, patch("cleanup_actions.log_event"):
            outcome = recycle_reviewed(result, [record], (), "test")
        self.assertEqual(outcome["completed"], 0)
        self.assertEqual(len(outcome["skipped"]), 1)
        transport.assert_not_called()

    def test_disconnected_drive_blocks_recycling_before_any_worker_call(self):
        record = old_file(self.downloads / "old.zip")
        result = scan_files(self.plan())
        self.drive.rename(self.drive.with_name("GoneDrive"))
        with patch("gg_desktop.old_files_data.recycle_old_files") as worker:
            with self.assertRaises(ValueError):
                recycle_reviewed(result, [record], (), "test")
            worker.assert_not_called()

    def test_invalid_threshold_and_empty_selection_are_rejected(self):
        for age in (0, -1, 10001):
            with self.assertRaises(ValueError):
                make_plan(str(self.downloads), "folder", age)
        with self.assertRaises(ValueError):
            recycle_reviewed(ScanResult(self.plan()), [], (), "test")

    def test_unreadable_subdirectory_marks_results_partial(self):
        old_file(self.downloads / "old.zip")
        denied = self.drive / "PermissionDenied"
        denied.mkdir()
        original = os.scandir
        def inspect(path):
            if key(path) == key(denied):
                raise PermissionError("Disposable access failure")
            return original(path)
        with patch("gg_desktop.old_files_data.os.scandir", side_effect=inspect):
            result = scan_files(self.plan())
        self.assertTrue(result.limited)
        self.assertEqual(len(result.files), 1)
        self.assertTrue(any("could not be read" in issue for issue in result.issues))

    def test_drive_root_files_keep_the_existing_recycle_scope_guard(self):
        record = OldFile(str(Path(self.drive.anchor) / "old.zip"), 10, 1, 1, 1, 1, 1)
        plan = replace(self.plan(), root=self.drive.anchor, roots=(self.drive.anchor,))
        result = ScanResult(plan, [record])
        self.assertTrue(review_reason(record, result, ()).startswith("Review only"))

    def test_cached_directory_entry_identity_is_not_trusted(self):
        from types import SimpleNamespace
        record = old_file(self.downloads / "old.zip")
        original = os.scandir
        class CachedEntries:
            def __init__(self, folder):
                self.stream = original(folder)
            def __enter__(self):
                return (SimpleNamespace(path=item.path, stat=lambda **_: SimpleNamespace(st_dev=0, st_ino=0, st_nlink=0))
                        for item in self.stream)
            def __exit__(self, *_):
                self.stream.close()
        with patch("gg_desktop.old_files_data.os.scandir", side_effect=CachedEntries):
            result = scan_files(self.plan())
        self.assertEqual(result.files, [record])
        self.assertFalse(result.limited)


if __name__ == "__main__":
    unittest.main()
