"""M1 file identity and original review-scope safety regression tests."""
from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from cleanup_actions import recycle_old_files
from core import is_unchanged, safe_scan_root, scan_old_files


class OriginalScopeSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "ChosenDownloads"
        self.root.mkdir()
        self.outside = Path(self.tmp.name) / "OtherDownloads"
        self.outside.mkdir()

    def _old(self, folder, name="skyrim-mod.zip"):
        file = folder / name
        file.write_bytes(b"Game Grave test archive")
        old = time.time() - 700 * 86400
        os.utime(file, (old, old))
        return file

    def test_inventory_carries_file_identity_and_detects_same_metadata_replacement(self):
        original = self._old(self.root)
        inventory = scan_old_files(self.root, min_days=365)
        self.assertEqual(len(inventory), 1)
        candidate = inventory[0]
        self.assertIsNotNone(candidate.inode)
        self.assertIsNotNone(candidate.modified_ns)
        self.assertTrue(is_unchanged(candidate))
        # Replacement may preserve size and timestamp, so the scan must also
        # compare the inode / file ID rather than trusting only metadata.
        alternate = self.root / "replacement.tmp"
        alternate.write_bytes(original.read_bytes())
        os.utime(alternate, ns=(candidate.modified_ns, candidate.modified_ns))
        os.replace(alternate, original)
        self.assertEqual(original.stat().st_size, candidate.size)
        self.assertEqual(original.stat().st_mtime_ns, candidate.modified_ns)
        self.assertFalse(is_unchanged(candidate))

    def test_old_files_reviewer_refuses_candidate_from_other_scan_folder(self):
        foreign = self._old(self.outside)
        inventory = scan_old_files(self.outside, min_days=365)
        with patch("cleanup_actions.log_event"), \
             patch("cleanup_actions.recycle_file") as mover:
            outcome = recycle_old_files(inventory, [], "qa", review_root=self.root,
                                        min_age_days=365)
        self.assertEqual(outcome["completed"], 0)
        self.assertIn("outside", outcome["skipped"][0])
        mover.assert_not_called()
        self.assertTrue(foreign.is_file())

    def test_old_files_reviewer_stops_after_source_root_becomes_linked(self):
        f = self._old(self.root)
        inventory = scan_old_files(self.root, min_days=365)
        move = Path(self.tmp.name) / "original-still-ordinary"
        self.root.rename(move)
        try:
            self.root.symlink_to(move, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Cannot create a directory symlink on this runner")
        self.assertFalse(safe_scan_root(self.root))
        with patch("cleanup_actions.log_event"), \
             patch("cleanup_actions.recycle_file") as mover:
            outcome = recycle_old_files(inventory, [], "qa",
                                        review_root=self.root, min_age_days=365)
        self.assertEqual(outcome["completed"], 0)
        mover.assert_not_called()
        self.assertTrue((move / f.name).exists())

    def test_scan_does_not_follow_linked_nested_directories(self):
        external = self._old(self.outside)
        nested = self.root / "Redirected"
        try:
            nested.symlink_to(self.outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink unavailable")
        inventory = scan_old_files(self.root, min_days=365)
        self.assertFalse(inventory)
        self.assertTrue(external.exists())

    def test_direct_reparse_root_is_refused_as_scan_scope(self):
        original = self._old(self.root)
        alias = Path(self.tmp.name) / "AliasedDownloads"
        try:
            alias.symlink_to(self.root, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks unavailable")
        with self.assertRaises(ValueError):
            scan_old_files(alias)
        self.assertTrue(original.exists())

    def test_time_threshold_revalidated_just_before_cleanup(self):
        original = self._old(self.root)
        inventory = scan_old_files(self.root, min_days=365)
        with patch("cleanup_actions.time.time",
                   return_value=inventory[0].modified + 300 * 86400), \
             patch("cleanup_actions.log_event"), \
             patch("cleanup_actions.recycle_file") as mover:
            outcome = recycle_old_files(inventory, [], "qa",
                                        review_root=self.root, min_age_days=365)
        self.assertEqual(outcome["completed"], 0)
        self.assertIn("age", outcome["skipped"][0])
        mover.assert_not_called()
        self.assertTrue(original.exists())


if __name__ == "__main__":
    unittest.main()
