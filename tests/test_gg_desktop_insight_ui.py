"""Disposable Qt integration checks for storage, captures, DNA and recovery."""
from __future__ import annotations

from dataclasses import replace
import importlib.util
import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch

HAS_QT = importlib.util.find_spec("PySide6") is not None
if HAS_QT:
    if os.name != "nt":
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import Qt, QPoint
    from PySide6.QtGui import QImage
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLabel
    from core import ModFolder, OldFile
    from graveyard import build_graveyard
    from gg_desktop.insight_widgets import CAPTURE_ROLE


@unittest.skipUnless(HAS_QT, "Optional Qt preview dependencies not installed")
class InsightDesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        # Reuse the disposable profile and library fixture without collecting
        # the other TestCase class a second time during unittest discovery.
        from test_gg_desktop_reference_ui import ReferenceDesktopTests
        ReferenceDesktopTests.setUp(self)
        self.pictures = []
        for i in range(3):
            path = self.root / f"userdata/123/760/remote/1091500/screenshots/shot-{i}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            image = QImage(40, 24, QImage.Format_RGB32)
            image.fill(Qt.red if i == 0 else Qt.blue)
            self.assertTrue(image.save(str(path)))
            modified = time.time() - 800 * 86400
            os.utime(path, (modified, modified))
            st = path.stat()
            self.pictures.append(OldFile(str(path), st.st_size, st.st_mtime,
                st.st_dev, st.st_ino, st.st_mtime_ns, st.st_nlink))
        self.win.inventory.screenshots = self.pictures
        self.win.inventory.graveyard = build_graveyard(self.win.inventory.steam, [], [], 365, screenshots=self.pictures)

    def close_window(self):
        from test_gg_desktop_reference_ui import ReferenceDesktopTests
        ReferenceDesktopTests.close_window(self)

    def navigate(self, route):
        self.win.navigate(route)
        for _ in range(4):
            self.app.processEvents()

    def test_capture_gallery_does_not_decode_on_navigation_or_selection(self):
        with patch("gg_desktop.storage_screens.decode_screenshot_preview") as decode:
            self.navigate("Captures")
            self.win.capture_grid.setCurrentRow(1)
            self.win.capture_sort.setCurrentText("Name (A–Z)")
            decode.assert_not_called()
        with patch.object(self.win, "job", side_effect=lambda fn, done, **_: done(fn(None))), \
             patch.object(self.win, "_approve_recycle") as cleanup:
            self.win._request_capture_preview(0)
            key = self.win._shown_captures[0].key
            self.assertIn(key, self.win._capture_previews)
            self.assertEqual(self.win._capture_previews[key][1], (40, 24))
            self.assertIsNotNone(self.win.capture_grid.item(0).data(CAPTURE_ROLE)["preview"])
            cleanup.assert_not_called()

    def test_capture_checkboxes_are_live_and_cannot_authorize_image_batches(self):
        self.navigate("Captures")
        grid = self.win.capture_grid
        for i in (0, 1):
            rect = grid.visualItemRect(grid.item(i))
            QTest.mouseClick(grid.viewport(), Qt.LeftButton, pos=QPoint(rect.left() + 14, rect.top() + 14))
        self.assertEqual(len(self.win._selected_captures()), 2)
        with patch.object(self.win, "error") as error, patch.object(self.win, "_preview_capture") as preview, \
             patch.object(self.win, "_approve_recycle") as cleanup:
            self.win._review_capture_selection()
            self.assertEqual(error.call_args.args[0], "Individual preview required")
            preview.assert_not_called()
            cleanup.assert_not_called()
        self.assertTrue(all(Path(f.path).is_file() for f in self.pictures))

    def test_cached_capture_preview_is_not_reused_for_a_changed_identity(self):
        self.navigate("Captures")
        with patch.object(self.win, "job", side_effect=lambda fn, done, **_: done(fn(None))):
            self.win._request_capture_preview(0)
        self.win.inventory.screenshots = [replace(self.pictures[0], modified_ns=self.pictures[0].modified_ns + 1)]
        self.navigate("Captures")
        self.assertIsNone(self.win.capture_grid.item(0).data(CAPTURE_ROLE)["preview"])

    def test_capture_preview_keeps_the_separate_single_image_review_flow(self):
        self.navigate("Captures")
        self.win.capture_grid.item(1).setCheckState(Qt.Checked)
        chosen = self.win._shown_captures[1]
        with patch.object(self.win, "_preview_capture") as preview, patch.object(self.win, "_approve_recycle") as cleanup:
            self.win._review_capture_selection()
            preview.assert_called_once_with(chosen.record)
            cleanup.assert_not_called()

    def test_graveyard_protection_action_never_invokes_cleanup(self):
        f = self.files[0]
        path = Path(f.path).with_name("old-skyrim-mod.zip")
        Path(f.path).rename(path)
        old = replace(f, path=str(path))
        self.win.inventory.files = [old]
        self.win.settings["never_touch"] = [str(path)]
        self.win.inventory.graveyard = build_graveyard([], [], [old], 365, [str(path)])
        self.navigate("Graveyard")
        unlock = self.win.grave_table.cellWidget(0, 3)
        self.assertIn("Unprotect", unlock.text())
        with patch.object(self.win, "confirm", return_value=True), patch("gg_desktop.screens.recycle_reviewed_entries") as cleanup:
            unlock.click()
            cleanup.assert_not_called()
        self.assertNotIn(str(path), self.win.settings["never_touch"])
        self.assertTrue(path.is_file())

    def test_graveyard_checkbox_scope_excludes_images_and_active_locations(self):
        entries = list(self.win.inventory.graveyard)
        from graveyard import GraveyardEntry
        entries += [GraveyardEntry("file:review", "Old mod archive", self.files[0].path,
                     "Possible mod / game download", 123, 800, "Unverified", "Review", "Review", True, self.files[0]),
                    GraveyardEntry("game:protected", "Installed game", self.win.inventory.games[0].install_path,
                     "Neglected installed game", 1000, 800, "Installed", "Keep", "Built-in", False)]
        self.win.inventory.graveyard = entries
        self.navigate("Graveyard")
        self.win._select_eligible()
        chosen = self.win._selected_grave_entries()
        self.assertEqual([e.key for e in chosen], ["file:review"])
        with patch.object(self.win, "_approve_recycle") as cleanup:
            self.win._delete_grave_selected()
            cleanup.assert_called_once_with(chosen)

    def test_restore_checks_current_availability_and_never_restores_a_conflict(self):
        records = [{"id": "one", "path": str(self.root / "one.zip"), "size": 100,
                    "time": "2026-11-05T12:00:00Z", "state": "Available"},
                   {"id": "two", "path": str(self.root / "two.zip"), "size": 200,
                    "time": "2026-11-04T12:00:00Z", "state": "Available"}]
        with patch("gg_desktop.recovery_screens.get_records", return_value=records), \
             patch("gg_desktop.recovery_screens.get_activity", return_value=[]):
            self.navigate("Undo Center")
        for i in range(2):
            self.win.undo_table.item(i, 0).setCheckState(Qt.Checked)
        with patch.object(self.win, "confirm", return_value=False), patch.object(self.win, "job") as job:
            self.win._restore_undo_selected()
            job.assert_not_called()
        with patch.object(self.win, "confirm", return_value=True), patch.object(self.win, "job") as job:
            self.win._restore_undo_selected()
            worker = job.call_args.args[0]
        with patch("gg_desktop.recovery_screens.check_restore", side_effect=["AVAILABLE", "ORIGINAL_EXISTS"]) as check, \
             patch("gg_desktop.recovery_screens.restore_recycled", return_value="RESTORED") as restore:
            self.assertEqual(worker(None), ["RESTORED", "ORIGINAL_EXISTS"])
            self.assertEqual([call.args[0] for call in check.call_args_list], ["one", "two"])
            restore.assert_called_once_with("one")

    def test_filtered_history_restores_the_selected_recovery_id(self):
        records = [{"id": "first", "path": str(self.root / "first.zip"), "size": 100},
                   {"id": "target", "path": str(self.root / "target.zip"), "size": 200}]
        with patch("gg_desktop.recovery_screens.get_records", return_value=records), \
             patch("gg_desktop.recovery_screens.get_activity", return_value=[]):
            self.navigate("Undo Center")
        self.win.global_search.setText("target")
        self.assertEqual(self.win._chosen_undo()[0].recovery_id, "target")
        with patch.object(self.win, "job") as job:
            self.win._check_undo_selected()
        with patch("gg_desktop.recovery_screens.check_restore", return_value="AVAILABLE") as check:
            job.call_args.args[0](None)
            check.assert_called_once_with("target")

    def test_storage_source_review_does_not_create_a_new_deletion_path(self):
        mod = ModFolder("Known Shader Cache", str(self.root / "cache"), "", "Shader cache", (), 300, 4,
                        False, "Steam shader cache", "Protected source")
        self.win.inventory.mods.append(mod)
        self.navigate("Other Storage")
        index = next(i for i, r in enumerate(self.win._shown_storage) if r.name == "Known Shader Cache")
        self.win.storage_table.item(index, 0).setCheckState(Qt.Checked)
        with patch.object(self.win, "info") as info, patch.object(self.win, "job") as job:
            self.win._review_storage()
            self.assertEqual(info.call_args.args[0], "Managed storage stays protected")
            job.assert_not_called()

    def test_dna_game_selection_and_nested_bytes_use_verified_links(self):
        self.navigate("Game DNA")
        index = next(i for i, g in enumerate(self.win._shown_dna_games) if g.name == "Cyberpunk 2077")
        self.win.dna_games.setCurrentRow(index)
        game = self.win._shown_dna_games[index]
        self.assertEqual(self.win.dna_metrics.values[1].text(), "112.0 GB")
        self.win.dna_tabs.buttons["Mods & Addons"].click()
        self.assertEqual(self.win.dna_asset_table.rowCount(), 1)
        self.assertIn("Cyberpunk", self.win.dna_asset_table.item(0, 0).text())
        self.assertEqual(self.win.dna_metrics.values[3].text(), "—")

    def test_five_reference_pages_render_at_all_supported_preview_sizes(self):
        with patch("gg_desktop.recovery_screens.get_records", return_value=[]), \
             patch("gg_desktop.recovery_screens.get_activity", return_value=[]):
            for width, height in ((1280, 720), (960, 650), (1440, 900)):
                self.win.resize(width, height)
                for route in ("Other Storage", "Captures", "Graveyard", "Game DNA", "Undo Center"):
                    with self.subTest(route=route, width=width):
                        self.navigate(route)
                        self.assertEqual(self.win.current_route, route)
                        self.assertLessEqual(self.win.page.body.width(), self.win.page.viewport().width())
                        self.assertFalse(self.win.grab().isNull())


if __name__ == "__main__":
    unittest.main()
