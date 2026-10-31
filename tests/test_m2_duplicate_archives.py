"""M2 duplicate archives: byte-exact evidence without cleanup authorization."""
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core import OldFile
from duplicates import inspect_duplicate_archives


class DuplicateArchiveTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.folder = self.base / "downloads"
        self.folder.mkdir()

    def file(self, name: str, data: bytes) -> OldFile:
        path = self.folder / name
        path.write_bytes(data)
        when = time.time() - 700 * 86400
        os.utime(path, (when, when))
        state = path.stat()
        return OldFile(str(path), state.st_size, state.st_mtime)

    def test_exact_content_duplicates_not_merely_same_size(self):
        first = self.file("game-patch-a.zip", b"same archive bytes")
        second = self.file("game-patch-b.zip", b"same archive bytes")
        unrelated = self.file("game-patch-c.zip", b"other file content")
        report = inspect_duplicate_archives([first, second, unrelated])
        self.assertEqual(len(report.groups), 1)
        self.assertEqual({Path(p).name for p in report.groups[0].paths},
                         {"game-patch-a.zip", "game-patch-b.zip"})
        self.assertEqual(report.potential_redundant_apparent_bytes, len(b"same archive bytes"))
        self.assertEqual(report.verified_reclaimable_bytes, 0)
        self.assertTrue(all(Path(f.path).exists() for f in (first, second, unrelated)))

    def test_filename_archive_only_and_never_touch_skip(self):
        a = self.file("mod-a.zip", b"xx")
        b = self.file("mod-b.zip", b"xx")
        doc = self.file("notes.txt", b"xx")
        report = inspect_duplicate_archives([a, b, doc], never_touch=[b.path])
        self.assertFalse(report.groups)
        self.assertGreaterEqual(report.skipped, 2)
        self.assertTrue(Path(b.path).is_file())

    def test_hardlinked_files_are_excluded(self):
        first = self.file("one.zip", b"exact")
        second_path = self.folder / "two.zip"
        try:
            os.link(first.path, second_path)
        except OSError:
            self.skipTest("Hardlink creation unavailable")
        state = second_path.stat()
        second = OldFile(str(second_path), state.st_size, state.st_mtime)
        report = inspect_duplicate_archives([first, second])
        self.assertFalse(report.groups)
        self.assertEqual(report.hashed_files, 0)

    def test_changed_since_scan_never_read_for_duplicate_proof(self):
        first = self.file("one.zip", b"old")
        second = self.file("two.zip", b"old")
        Path(first.path).write_bytes(b"NEW DATA")
        report = inspect_duplicate_archives([first, second])
        self.assertFalse(report.groups)
        self.assertTrue(Path(first.path).is_file())

    def test_symlink_ancestor_excluded(self):
        src = self.base / "real"
        src.mkdir()
        (src / "a.zip").write_bytes(b"abc")
        shortcut = self.base / "alias"
        try:
            shortcut.symlink_to(src, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink unavailable")
        state = (shortcut / "a.zip").stat()
        marked = OldFile(str(shortcut / "a.zip"), state.st_size, state.st_mtime)
        report = inspect_duplicate_archives([marked])
        self.assertFalse(report.groups)
        self.assertEqual(report.hashed_files, 0)

    def test_budget_and_explicit_cancel(self):
        a = self.file("a.zip", b"data")
        b = self.file("b.zip", b"data")
        report = inspect_duplicate_archives([a, b], max_hashed_bytes=4)
        self.assertTrue(report.truncated)
        self.assertEqual(report.verified_reclaimable_bytes, 0)
        self.assertFalse(report.groups)
        with self.assertRaises(InterruptedError):
            inspect_duplicate_archives([a, b], cancel=lambda: True)

    def test_reject_unbounded_arguments(self):
        a = self.file("one.zip", b"data")
        for size in (0, -1, 1000000):
            with self.assertRaises(ValueError):
                inspect_duplicate_archives([a], max_candidates=size)
        with self.assertRaises(ValueError):
            inspect_duplicate_archives([a], max_hashed_bytes=0)


if __name__ == "__main__":
    unittest.main()
