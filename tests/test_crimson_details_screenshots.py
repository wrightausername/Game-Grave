"""Regression coverage for clickable Crimson details, reviewable old files and capture discovery."""
from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core import OldFile
from graveyard import build_graveyard
from cleanup_actions import recycle_reviewed_entries
from gg_desktop.models import graveyard_detail_text, game_detail_text
from screenshots import find_old_screenshots


class DetailInformationTests(unittest.TestCase):
    def test_graveyard_details_show_why_location_size_protection_and_action(self):
        with tempfile.TemporaryDirectory() as base:
            p = Path(base) / "old-notes.txt"
            p.write_text("scratch")
            old = time.time() - 900 * 86400
            os.utime(p, (old, old))
            s = p.stat()
            f = OldFile(str(p), s.st_size, s.st_mtime,
                        s.st_dev, s.st_ino, s.st_mtime_ns, s.st_nlink)
            entry = build_graveyard([], [], [f], 365)[0]
            details = graveyard_detail_text(entry)
            for text in ("WHY GAME GRAVE FOUND IT", "LOCATION", "PROTECTION",
                         "WHAT YOU CAN DO", "Recycle Bin", "apparent", "old-notes.txt"):
                self.assertIn(text, details)
            blocked = build_graveyard([], [], [f], 365, never_touch=[str(p)])[0]
            protected = graveyard_detail_text(blocked, [str(p)])
            self.assertIn("Unprotect", protected)
            self.assertFalse(blocked.can_recycle)

    def test_game_details_include_real_evidence_not_guessed_metrics(self):
        g = SimpleNamespace(name="Example Game", launcher="Epic", size_bytes=None,
                            size_source="Unknown", last_played_at=None,
                            install_path="C:/Test/Games/Example",
                            install_evidence="Launcher manifest evidence",
                            status="Installed")
        details = game_detail_text(g)
        for word in ("Example Game", "Epic", "Unknown", "Launcher manifest",
                     "INSTALL LOCATION", "WHAT YOU CAN DO"):
            self.assertIn(word, details)

    def test_protected_game_is_information_only(self):
        game = SimpleNamespace(app_id="25", name="Installed", install_path="C:/Games/steamapps/common/Installed",
                               size=1200, last_played=time.time()-600*86400, source="Steam",)
        found = build_graveyard([game], [], [], 365)
        self.assertEqual(len(found), 1)
        self.assertFalse(found[0].can_recycle)
        self.assertIn("launcher", graveyard_detail_text(found[0]).lower())


class ScopedRecycleTests(unittest.TestCase):
    def test_plain_old_file_from_reviewed_folder_is_visible(self):
        with tempfile.TemporaryDirectory() as base:
            p = Path(base) / "old-document.dat"
            p.write_bytes(b"no modification allowed in discovery")
            old = time.time()-600*86400
            os.utime(p, (old, old))
            s = p.stat()
            record = OldFile(str(p), s.st_size, s.st_mtime,
                             s.st_dev, s.st_ino, s.st_mtime_ns, s.st_nlink)
            row = build_graveyard([], [], [record], 365)[0]
            self.assertTrue(row.can_recycle)
            self.assertEqual(row.category, "Old file from reviewed folder")
            self.assertTrue(p.exists())
            with patch("cleanup_actions.log_event"), patch("cleanup_actions.recycle_file") as move:
                # A direct backend call without the original scoped folder
                # cannot acquire delete authority.
                result = recycle_reviewed_entries([row], [], "test")
                self.assertEqual(result["completed"], 0)
                move.assert_not_called()
            self.assertTrue(p.exists())

    def test_image_in_generic_old_folder_cannot_bypass_preview(self):
        with tempfile.TemporaryDirectory() as base:
            p = Path(base) / "personal.png"
            p.write_bytes(b"test")
            s = p.stat()
            record = OldFile(str(p), s.st_size, time.time()-900*86400)
            self.assertFalse(build_graveyard([], [], [record], 365))


class AutomaticScreenshotTests(unittest.TestCase):
    def _write(self, p):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"image bytes never decoded by metadata scan")
        return p

    def test_recent_game_capture_detected_after_scan(self):
        with tempfile.TemporaryDirectory() as root:
            home = Path(root)
            target = self._write(home / "Pictures" / "Example Game" /
                                 "Screenshots" / "today.jpg")
            family = self._write(home / "Pictures" / "Family" / "private.jpg")
            game = SimpleNamespace(name="Example Game")
            found = find_old_screenshots(
                365, home=home, steam_roots=[], games=[game], include_recent=True)
            self.assertIn(str(target), [f.path for f in found])
            self.assertNotIn(str(family), [f.path for f in found])
            self.assertTrue(family.exists())

    def test_auto_capture_detection_never_infers_game_content_from_extension(self):
        with tempfile.TemporaryDirectory() as root:
            home = Path(root)
            screen = self._write(home / "Videos" / "Captures" / "image.png")
            unrelated = self._write(home / "Pictures" / "Family" / "image.png")
            result = find_old_screenshots(365, home=home, steam_roots=[],
                                          include_recent=True)
            self.assertIn(str(screen), [r.path for r in result])
            self.assertNotIn(str(unrelated), [r.path for r in result])

    def test_game_title_cannot_escape_screenshot_scan_scope(self):
        with tempfile.TemporaryDirectory() as root:
            home = Path(root)
            private = self._write(home / "Pictures" / "Private" / "private.jpg")
            games = [SimpleNamespace(name="../Private")]
            discovered = find_old_screenshots(365, home=home, steam_roots=[],
                                              games=games, include_recent=True)
            self.assertEqual(discovered, [])
            self.assertTrue(private.exists())


if __name__ == "__main__":
    unittest.main()
