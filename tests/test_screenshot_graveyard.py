"""Old in-game screenshot discovery and preview-only Graveyard deletion tests.

All filesystem fixtures are disposable. Never operates on real screenshots.
"""
from __future__ import annotations

import os
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cleanup_actions import recycle_reviewed_entries
from core import is_unchanged
from graveyard import build_graveyard
from screenshot_preview import decode_screenshot_preview
from screenshots import (
    default_screenshot_roots, find_old_screenshots, looks_like_screenshot,
)
from ui import GameGraveApp


class ScreenshotDiscoveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name) / "SyntheticUserHome"
        self.home.mkdir()
        self.base = Path(temp.name)

    def image(self, name: Path, days: int = 500):
        name.parent.mkdir(parents=True, exist_ok=True)
        name.write_bytes(b"fake screenshot fixture, never sent to decoder")
        old = time.time() - days * 86400
        os.utime(name, (old, old))
        return name

    def test_gamebar_captures_detected_but_personal_pictures_excluded(self):
        target = self.image(self.home / "Videos" / "Captures" / "game.png")
        private = self.image(self.home / "Pictures" / "Family" / "child.png")
        desktop = self.image(self.home / "Pictures" / "Screenshots" / "desktop.png")
        recent = self.image(self.home / "Videos" / "Captures" / "recent.webp", days=3)
        results = find_old_screenshots(365, home=self.home, steam_roots=[])
        paths = {Path(f.path) for f in results}
        self.assertEqual(paths, {target})
        self.assertTrue(all(p.exists() for p in (target, private, desktop, recent)))

    def test_explicit_custom_folder_does_not_trigger_generic_pictures_scan(self):
        custom = self.image(self.home / "Pictures" / "Screenshots" / "modded-skyrim.jpg")
        unrelated = self.image(self.home / "Pictures" / "Other" / "personal.jpg")
        records = find_old_screenshots(
            180, custom_roots=[str(custom.parent)], home=self.home, steam_roots=[])
        self.assertEqual([x.path for x in records], [str(custom)])
        self.assertTrue(unrelated.exists())

    def test_steam_screenshot_scan_inside_program_files_without_crawling_game(self):
        steam = self.base / "Program Files (x86)" / "Steam"
        shot = self.image(steam / "userdata" / "10001" / "760" / "remote" /
                          "1091500" / "screenshots" / "f12-shot.jpg")
        thumb = self.image(shot.parent / "thumbnails" / "f12-shot.jpg")
        external = self.image(steam / "steamapps" / "common" / "Skyrim" / "Data" / "mod.png")
        roots = default_screenshot_roots(home=self.home, steam_roots=[steam])
        self.assertIn(shot.parent, roots)
        from screenshots import _steam_screenshot_root, _read_direct_steam_images
        self.assertTrue(_steam_screenshot_root(shot.parent, [steam]),
                        f"Steam root recognition rejected: {shot.parent.parts!r}")
        direct = _read_direct_steam_images(shot.parent, 365, None, 100)
        self.assertEqual([Path(row.path) for row in direct], [shot],
                         f"Steam direct inventory skipped test image: {shot.stat()!r}")
        records = find_old_screenshots(365, home=self.home, steam_roots=[steam])
        self.assertEqual([Path(r.path) for r in records], [shot])
        self.assertTrue(thumb.exists())
        self.assertTrue(external.exists())

    def test_symlinked_capture_folder_and_photo_are_skipped(self):
        destination = self.home / "Pictures" / "Personal"
        photo = self.image(destination / "personal.png")
        captures = self.home / "Videos" / "Captures"
        captures.parent.mkdir(parents=True)
        try:
            captures.symlink_to(destination, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Directory symlinks unavailable")
        found = find_old_screenshots(365, home=self.home, steam_roots=[])
        self.assertEqual(found, [])
        self.assertTrue(photo.exists())

    def test_linked_photo_in_valid_capture_dir_is_skipped(self):
        captures = self.home / "Videos" / "Captures"
        captures.mkdir(parents=True)
        photo = self.image(self.home / "Pictures" / "hidden.png")
        try:
            (captures / "shortcut.png").symlink_to(photo)
        except (OSError, NotImplementedError):
            self.skipTest("File symlink unavailable")
        records = find_old_screenshots(365, home=self.home, steam_roots=[])
        self.assertFalse(records)
        self.assertTrue(photo.exists())

    def test_recent_files_not_returned_and_scan_cancelled(self):
        p = self.image(self.home / "Videos" / "Captures" / "new.bmp", days=5)
        self.assertFalse(find_old_screenshots(365, home=self.home, steam_roots=[]))
        with self.assertRaises(InterruptedError):
            find_old_screenshots(1, home=self.home, steam_roots=[],
                                 cancel=lambda: True)
        self.assertTrue(p.exists())

    def test_image_and_thumbnail_extensions_are_bounded(self):
        self.assertTrue(looks_like_screenshot(Path("game.PNG")))
        self.assertTrue(looks_like_screenshot(Path("game.jpeg")))
        self.assertFalse(looks_like_screenshot(Path("thumbnails/game.jpg")))
        self.assertFalse(looks_like_screenshot(Path("game.exe")))
        self.assertFalse(looks_like_screenshot(Path("game.svg")))
        self.assertFalse(looks_like_screenshot(Path("game.gif")))


class ScreenshotReviewTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name) / "Captures"
        self.root.mkdir()
        self.path = self.root / "favorite-game.png"
        self.path.write_bytes(b"synthetic png placeholder")
        stamp = time.time() - 900 * 86400
        os.utime(self.path, (stamp, stamp))
        from core import OldFile
        s = self.path.stat()
        record = OldFile(str(self.path), s.st_size, s.st_mtime,
                         s.st_dev, s.st_ino, s.st_mtime_ns, s.st_nlink)
        self.record = record
        self.entry = build_graveyard([], [], [], 365, screenshots=[record])[0]

    def test_screenshot_in_graveyard_always_requires_preview_not_bulk(self):
        self.assertEqual(self.entry.category, "Old game screenshot")
        self.assertFalse(self.entry.can_recycle)
        self.assertFalse(self.entry.screenshot_reviewed)
        self.assertIn("Preview", self.entry.protection)
        self.assertTrue(self.path.exists())

    def test_unpreviewed_screenshot_never_reaches_recycle_or_undo(self):
        with patch("cleanup_actions.log_event"), \
             patch("cleanup_actions.recycle_file") as mover, \
             patch("cleanup_actions.register_recycle") as undo:
            outcome = recycle_reviewed_entries([self.entry], [], "test")
        self.assertEqual(outcome["completed"], 0)
        mover.assert_not_called()
        undo.assert_not_called()
        self.assertTrue(self.path.exists())

    def test_tampered_screenshot_review_flag_alone_not_sufficient(self):
        entry = replace(self.entry, can_recycle=True)
        with patch("cleanup_actions.log_event"), \
             patch("cleanup_actions.recycle_file") as mover:
            outcome = recycle_reviewed_entries([entry], [], "test")
        self.assertEqual(outcome["completed"], 0)
        mover.assert_not_called()
        self.assertTrue(self.path.exists())

    def test_previewed_explicit_single_image_still_uses_windows_undo_worker(self):
        entry = replace(self.entry, can_recycle=True, screenshot_reviewed=True)
        with patch("cleanup_actions.log_event"), \
             patch("cleanup_actions.recycle_file",
                   side_effect=RuntimeError("Recycle Bin unverified")) as mover, \
             patch("cleanup_actions.register_recycle") as undo:
            outcome = recycle_reviewed_entries([entry], [], "test")
        self.assertEqual(outcome["completed"], 0)
        mover.assert_called_once_with(self.path)
        undo.assert_not_called()
        self.assertTrue(self.path.exists())

    def test_never_touch_keeps_screenshot_protected_even_after_preview(self):
        entry = replace(self.entry, can_recycle=True, screenshot_reviewed=True)
        with patch("cleanup_actions.log_event"), \
             patch("cleanup_actions.recycle_file") as mover:
            outcome = recycle_reviewed_entries([entry], [str(self.path)], "test")
        self.assertEqual(outcome["completed"], 0)
        mover.assert_not_called()
        self.assertTrue(self.path.exists())

    def test_ui_rejects_unpreviewed_screenshot_before_approval(self):
        fake = SimpleNamespace(graveyard_lookup={self.entry.key: self.entry},
                               scanning=False, cleanup_running=False)
        with patch("ui.messagebox.showwarning") as warning, \
             patch("ui.messagebox.askyesno") as confirm, \
             patch("ui.threading.Thread") as worker:
            GameGraveApp._grave_recycle_ids(fake, [self.entry.key])
        warning.assert_called_once()
        confirm.assert_not_called()
        worker.assert_not_called()

    def test_exact_preview_ui_starts_only_approved_background_worker(self):
        fake = SimpleNamespace(
            graveyard_lookup={self.entry.key: self.entry}, scanning=False,
            cleanup_running=False, settings={"never_touch": []},
            scan_button=Mock(), status_text=SimpleNamespace(set=Mock()),
            _grave_sync_actions=Mock(), events=Mock())
        with patch("ui.messagebox.askyesno", return_value=True) as confirm, \
             patch("ui.threading.Thread") as worker, \
             patch("ui.recycle_reviewed_entries", return_value={
                 "completed": 0, "skipped": [], "recovery_warnings": 0}) as action:
            GameGraveApp._grave_recycle_ids(
                fake, [self.entry.key], screenshot_reviewed_key=self.entry.key)
            self.assertTrue(fake.cleanup_running)
            worker.assert_called_once()
            action.assert_not_called()
            worker.call_args.kwargs["target"]()
            passed_entry = action.call_args.args[0][0]
            self.assertTrue(passed_entry.can_recycle)
            self.assertTrue(passed_entry.screenshot_reviewed)
            self.assertEqual(passed_entry.key, self.entry.key)
        confirm.assert_called_once()
        self.assertTrue(self.path.exists())

    def test_unrelated_image_cannot_be_promoted_to_previewed_screenshot(self):
        other = build_graveyard([], [], [self.record], 365)
        self.assertEqual(other, [])
        fake = SimpleNamespace(graveyard_lookup={self.entry.key: self.entry},
                               scanning=False, cleanup_running=False,
                               settings={"never_touch": []})
        with patch("ui.messagebox.showwarning") as warning:
            GameGraveApp._grave_recycle_ids(
                fake, [self.entry.key], screenshot_reviewed_key="wrong-image")
        warning.assert_called_once()
        self.assertTrue(self.path.exists())

    def test_preview_after_changed_file_refuses_to_decode(self):
        self.path.write_bytes(b"modified since scan")
        self.assertFalse(is_unchanged(self.record))
        with self.assertRaises(ValueError):
            decode_screenshot_preview(self.record)


class RealSmallPreviewTests(unittest.TestCase):
    def test_bounded_png_preview_preserves_file(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Source app Pillow not installed; Windows installer bundles it")
        with tempfile.TemporaryDirectory() as t:
            folder = Path(t) / "Captures"
            folder.mkdir()
            p = folder / "old-screenshot.png"
            Image.new("RGB", (900, 600), (65, 78, 96)).save(p)
            from core import OldFile
            s = p.stat()
            record = OldFile(str(p), s.st_size, s.st_mtime,
                             s.st_dev, s.st_ino, s.st_mtime_ns, s.st_nlink)
            result = decode_screenshot_preview(record)
            self.assertLessEqual(result.width, 920)
            self.assertLessEqual(result.height, 560)
            self.assertTrue(p.exists())


if __name__ == "__main__":
    unittest.main()
