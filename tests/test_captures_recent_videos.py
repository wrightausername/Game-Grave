"""Read-only capture grouping tests: recent game clips, personal privacy, no mutations."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import time
import unittest

from recordings import find_old_recordings


class RecentGameRecordingTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.home = Path(t.name) / "test-user"
        self.home.mkdir()

    def create_file(self, path: Path, age_days: int):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"DISPOSABLE CLIP TEST FILE. Never decode it.")
        stamp = time.time() - age_days * 86400
        os.utime(path, (stamp, stamp))
        return path

    def test_recent_capture_appears_with_age_filter_disabled(self):
        clip = self.create_file(
            self.home / "Videos" / "Captures" / "recent-gameplay.mp4", 1)
        old = self.create_file(
            self.home / "Videos" / "Captures" / "classic-clip.mkv", 600)
        personal = self.create_file(
            self.home / "Videos" / "Family" / "vacation.mp4", 1)
        shots = find_old_recordings(180, home=self.home, include_recent=True)
        self.assertEqual({f.path for f in shots}, {str(clip), str(old)})
        self.assertTrue(personal.exists())
        self.assertEqual(personal.read_bytes(),
                         b"DISPOSABLE CLIP TEST FILE. Never decode it.")

    def test_default_old_only_behavior_retained(self):
        recent = self.create_file(
            self.home / "Videos" / "Captures" / "today.mp4", 1)
        older = self.create_file(
            self.home / "Videos" / "Captures" / "last-year.mp4", 500)
        captures = find_old_recordings(180, home=self.home)
        self.assertEqual([f.path for f in captures], [str(older)])
        self.assertTrue(recent.exists())

    def test_cancel_does_not_change_video_files(self):
        clip = self.create_file(
            self.home / "Videos" / "Captures" / "capture.mp4", 2)
        with self.assertRaises(InterruptedError):
            find_old_recordings(180, home=self.home, include_recent=True,
                                cancel=lambda: True)
        self.assertEqual(clip.read_bytes(),
                         b"DISPOSABLE CLIP TEST FILE. Never decode it.")


if __name__ == "__main__":
    unittest.main()
