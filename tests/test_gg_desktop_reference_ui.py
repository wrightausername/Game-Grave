"""Qt integration checks with disposable files, never a real user's library.

Run with ui-preview-requirements.txt installed. Windows CI uses native Qt;
Linux runs with QT_QPA_PLATFORM=offscreen and does not claim Windows acceptance.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

HAS_QT = importlib.util.find_spec("PySide6") is not None
if HAS_QT:
    if os.name != "nt":
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import Qt, QCoreApplication, QEvent, QPoint
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLabel
    from core import ModFolder, OldFile, SteamGame, default_settings, load_settings
    from gg_desktop.app import CrimsonWindow, ROUTES
    from gg_desktop.models import merge_games


@unittest.skipUnless(HAS_QT, "Optional Qt preview dependencies not installed")
class ReferenceDesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="GG-Reference-UI-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.profile = patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "Local"),
                                               "APPDATA": str(self.root / "Roaming")})
        self.profile.start()
        self.addCleanup(self.profile.stop)
        settings = default_settings()
        settings["steam_artwork_downloads"] = False
        settings["scan_folder"] = str(self.root / "Downloads")
        Path(settings["scan_folder"]).mkdir()
        with patch("gg_desktop.app.load_settings", return_value=settings):
            self.win = CrimsonWindow()
        self.win.show()
        self.addCleanup(self.close_window)
        self.files = []
        for i, name in enumerate(("alpha.zip", "beta.exe", "gamma.log", "picture.png")):
            path = Path(settings["scan_folder"]) / name
            path.write_bytes(b"SYNTHETIC UI FIXTURE " + bytes([i]))
            modified = time.time() - (400 + i * 10) * 86400
            os.utime(path, (modified, modified))
            st = path.stat()
            self.files.append(OldFile(str(path), st.st_size, st.st_mtime,
                                      st.st_dev, st.st_ino, st.st_mtime_ns, st.st_nlink))
        steam = [SteamGame("1091500", "Cyberpunk 2077", str(self.root),
                           str(self.root / "Games" / "Cyberpunk"), 112 * 1024 ** 3,
                           time.time() - 86400, "Synthetic history"),
                 SteamGame("489830", "Skyrim SE", str(self.root),
                           str(self.root / "Games" / "Skyrim"), 50 * 1024 ** 3,
                           None, "Unknown")]
        self.win.inventory.games = merge_games(steam, [])
        self.win.inventory.steam = steam
        self.win.inventory.mods = [
            ModFolder("Cyber Engine Tweaks", str(Path(steam[0].install_path) / "mods"), "",
                      "Installed: possible mods", ("mods",), 400, 2, False, "Vortex"),
            ModFolder("Skyrim Scripts", str(Path(steam[1].install_path) / "mods"), "",
                      "Installed: possible mods", ("scripts",), 200, 4, False, "Mod Organizer 2"),
            ModFolder("Unmatched Library", str(self.root / "unmatched"), "",
                      "Unverified storage", (), 500, 5, False, "Vortex"),
        ]
        self.win.inventory.files = list(self.files)
        self.win.inventory.file_scan_root = settings["scan_folder"]
        self.win.inventory.file_scan_days = 180
        self.win.inventory.scanned_at = "Synthetic test scan"

    def close_window(self):
        self.win.scanning = False
        self.win.cleaning = False
        self.win.close()
        self.win.deleteLater()
        self.app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def navigate(self, route):
        self.win.navigate(route)
        for _ in range(3):
            self.app.processEvents()

    def check_file(self, name):
        index = next(i for i, f in enumerate(self.win._shown_old_files) if Path(f.path).name == name)
        self.win.old_table.item(index, 0).setCheckState(Qt.Checked)

    def test_games_search_launcher_filters_favorites_and_detail_selection(self):
        self.navigate("Games")
        self.assertEqual(self.win.game_grid.count(), 2)
        self.win.global_search.setText("Skyrim")
        self.assertEqual([g.name for g in self.win._shown_games], ["Skyrim SE"])
        self.assertEqual(self.win._current_game().name, "Skyrim SE")
        texts = [x.text() for x in self.win.game_details.findChildren(QLabel)]
        self.assertIn("Unknown", texts)
        self.win.global_search.clear()
        game = self.win._current_game()
        self.win._toggle_favorite(game)
        self.assertIn(game.key, load_settings()["desktop_favorites"])
        self.win.game_tabs.buttons["Favorites"].click()
        self.assertEqual([g.key for g in self.win._shown_games], [game.key])
        self.win.game_grid.set_mode("list")
        self.assertTrue(self.win.game_grid.delegate.list_mode)
        self.win.game_tabs.buttons["Updates"].click()
        self.assertEqual(self.win.game_grid.count(), 0)
        self.assertIn("not available", self.win.game_empty.text())

    def test_cover_star_click_is_a_live_favorite_control(self):
        self.navigate("Games")
        grid = self.win.game_grid
        rect = grid.visualItemRect(grid.item(0))
        key = self.win._shown_games[0].key
        QTest.mouseClick(grid.viewport(), Qt.LeftButton, pos=QPoint(rect.right() - 15, rect.top() + 15))
        self.assertIn(key, self.win.settings["desktop_favorites"])
        QTest.mouseClick(grid.viewport(), Qt.LeftButton, pos=QPoint(rect.right() - 15, rect.top() + 15))
        self.assertNotIn(key, self.win.settings["desktop_favorites"])

    def test_games_inventory_is_not_silently_truncated(self):
        from dataclasses import replace
        base = self.win.inventory.games[0]
        self.win.inventory.games = [replace(base, key=str(i), name=f"Game {i:04}") for i in range(605)]
        self.navigate("Games")
        self.assertEqual(self.win.game_grid.count(), 605)
        self.win.game_grid.setFocus()
        QTest.keyClick(self.win.game_grid, Qt.Key_End)
        self.assertEqual(self.win.game_grid.currentRow(), 604)
        self.win.game_search.setText("Game 0604")
        self.assertEqual(self.win._current_game().name, "Game 0604")

    def test_mod_filters_and_manager_filters_keep_correct_details(self):
        self.navigate("Mods")
        self.win.mod_search.setText("Skyrim")
        self.assertEqual([m.name for m in self.win._shown_mods], ["Skyrim Scripts"])
        texts = [x.text() for x in self.win.mod_details.findChildren(QLabel)]
        self.assertIn("Skyrim Scripts", texts)
        self.assertIn("Protected storage", " ".join(texts))
        self.win._clear_mod_filters()
        vortex = next(c for c in self.win.mod_manager_checks if c.property("manager") == "Vortex")
        vortex.setChecked(True)
        self.assertEqual(len(self.win._shown_mods), 2)
        self.win.mod_tabs.buttons["Conflicts"].click()
        self.assertEqual(self.win.mod_table.rowCount(), 0)
        self.assertIn("unavailable", self.win.mod_notice.text())
        self.assertTrue(all(f.path and Path(f.path).exists() for f in self.files))

    def test_switching_details_immediately_hides_previous_content(self):
        self.navigate("Mods")
        previous = self.win.mod_details.findChildren(QLabel)
        self.assertTrue(any(item.isVisible() for item in previous))
        self.win.mod_table.selectRow(1)
        self.assertTrue(all(not item.isVisible() for item in previous))

    def test_old_file_checkboxes_follow_visible_files_after_sort_and_filter(self):
        self.navigate("Old Files")
        self.check_file("alpha.zip")
        self.check_file("gamma.log")
        self.win.old_sort.setCurrentText("Name (A–Z)")
        self.assertEqual({Path(f.path).name for f in self.win._selected_old()}, {"alpha.zip", "gamma.log"})
        self.win.old_search.setText("gamma")
        self.assertEqual([Path(f.path).name for f in self.win._selected_old()], ["gamma.log"])
        self.win.old_select_all.setChecked(False)
        self.assertEqual(self.win._selected_old(), [])
        self.win.old_select_all.setChecked(True)
        self.assertEqual([Path(f.path).name for f in self.win._selected_old()], ["gamma.log"])
        self.win.old_search.clear()
        self.assertEqual([Path(f.path).name for f in self.win._selected_old()], ["gamma.log"])

    def test_large_file_and_mod_tables_are_bounded_without_losing_findings(self):
        from dataclasses import replace
        self.win.inventory.files = [replace(self.files[0], path=f"{self.win.settings['scan_folder']}/file-{i:05}.zip", size=i)
                                    for i in range(50001)]
        self.navigate("Old Files")
        self.assertEqual(self.win.old_table.rowCount(), 160)
        self.assertIn("50001", self.win.old_pager.caption.text())
        self.win.old_select_all.setChecked(True)
        self.assertEqual(len(self.win._selected_old()), 160)
        self.win.old_pager.next.click()
        self.assertEqual(self.win._selected_old(), [])
        self.win.old_search.setText("file-50000")
        self.assertEqual(self.win.old_table.rowCount(), 1)
        self.assertEqual(Path(self.win._shown_old_files[0].path).name, "file-50000.zip")
        self.win.inventory.mods = [replace(self.win.inventory.mods[0], name=f"Mod {i:04}", path=f"{self.root}/mod-{i}")
                                   for i in range(605)]
        self.navigate("Mods")
        self.assertEqual(self.win.mod_table.rowCount(), 160)
        self.win.mod_pager.next.click()
        self.assertEqual(self.win._shown_mods[0].name, "Mod 0160")
        self.win.mod_search.setText("Mod 0604")
        self.assertEqual(self.win.mod_table.rowCount(), 1)
        self.assertEqual(self.win._shown_mods[0].name, "Mod 0604")

    def test_old_file_recycle_uses_confirmed_snapshot_and_scan_scope(self):
        self.navigate("Old Files")
        self.check_file("alpha.zip")
        selected = tuple(self.win._selected_old())
        self.win.settings["files_stale_days"] = 365
        with patch.object(self.win, "confirm", return_value=False), patch.object(self.win, "job") as job:
            self.win._recycle_old_selected()
            job.assert_not_called()
        with patch.object(self.win, "confirm", return_value=True), patch.object(self.win, "job") as job:
            self.win._recycle_old_selected()
            worker = job.call_args.args[0]
        with patch("gg_desktop.library_screens.recycle_old_files") as recycle:
            worker(None)
            self.assertEqual(recycle.call_args.args[0], selected)
            self.assertEqual(recycle.call_args.kwargs["review_root"], self.win.inventory.file_scan_root)
            self.assertEqual(recycle.call_args.kwargs["min_age_days"], 180)
        self.assertTrue(Path(selected[0].path).is_file())

    def test_protected_and_image_batches_do_not_reach_cleanup(self):
        self.navigate("Old Files")
        self.check_file("picture.png")
        self.assertFalse(self.win.old_delete.isEnabled())
        with patch.object(self.win, "error") as error, patch.object(self.win, "job") as job:
            self.win._recycle_old_selected()
            self.assertEqual(error.call_args.args[0], "Preview required")
            job.assert_not_called()
        self.win.old_select_all.setChecked(False)
        # Explicitly clear every checkbox, even when only some rows were selected.
        self.win._select_old_visible(False)
        self.check_file("alpha.zip")
        self.win._protect_old_selected()
        self.assertFalse(self.win.old_delete.isEnabled())
        with patch.object(self.win, "error") as error, patch.object(self.win, "job") as job:
            self.win._recycle_old_selected()
            self.assertEqual(error.call_args.args[0], "Protected items selected")
            job.assert_not_called()
        self.assertTrue(all(Path(f.path).is_file() for f in self.files))

    def test_changing_scan_folder_cannot_reuse_old_results(self):
        self.navigate("Old Files")
        self.check_file("alpha.zip")
        self.win.settings["scan_folder"] = str(self.root / "another-folder")
        with patch.object(self.win, "error") as error, patch.object(self.win, "job") as job:
            self.win._recycle_old_selected()
            self.assertEqual(error.call_args.args[0], "Scan folder changed")
            job.assert_not_called()
        self.navigate("Old Files")
        self.assertEqual(self.win.old_table.rowCount(), 0)

    def test_all_navigation_routes_render_and_reference_pages_fit(self):
        for route, _ in ROUTES:
            with self.subTest(route=route):
                self.navigate(route)
                self.assertEqual(self.win.current_route, route)
                self.assertTrue(self.win.page.isVisible())
        for width, height in ((1280, 720), (960, 650), (1440, 900)):
            self.win.resize(width, height)
            for route in ("Games", "Mods", "Old Files"):
                with self.subTest(route=route, width=width):
                    self.navigate(route)
                    self.assertLessEqual(self.win.page.body.width(), self.win.page.viewport().width())
                    self.assertFalse(self.win.grab().isNull())


if __name__ == "__main__":
    unittest.main()
