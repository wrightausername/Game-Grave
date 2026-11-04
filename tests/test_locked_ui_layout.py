"""Real Qt layout and navigation regressions using disposable local inventory."""
from __future__ import annotations

import importlib.util
import json
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
    from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QRect, QTimer
    from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QTextBrowser, QPushButton


@unittest.skipUnless(HAS_QT, "Optional Qt preview dependencies are not installed")
class LockedUILayoutTests(unittest.TestCase):
    routes = ("Overview", "Graveyard", "Game DNA", "Undo Center",
              "AI Assistant", "Settings", "More Tools")

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from gg_desktop.app import configure_crimson_dialog_palette
        configure_crimson_dialog_palette(cls.app)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gg-layout-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.environment = patch.dict(os.environ, {
            "LOCALAPPDATA": str(self.root / "Local"),
            "APPDATA": str(self.root / "Roaming"),
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        from core import default_settings
        from gg_desktop.app import CrimsonWindow
        with patch("gg_desktop.app.load_settings", return_value=default_settings()):
            self.window = CrimsonWindow()
        self.window.show()
        self.addCleanup(self.close_window)

    def close_window(self):
        self.window.close()
        self.window.deleteLater()
        self.flush()

    def flush(self):
        for _ in range(8):
            self.app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def populate(self):
        from core import SteamGame, OldFile
        from launchers import LauncherGame
        from graveyard import build_graveyard
        from gg_desktop.models import merge_games
        steam = []
        for index in range(3):
            install = self.root / "Steam" / "steamapps" / "common" / str(index)
            install.mkdir(parents=True)
            steam.append(SteamGame(str(455 + index), "Example game " + str(index),
                                   str(self.root / "Steam"), str(install),
                                   1024**3, None, "Unknown"))
        ea_install = self.root / "EA" / "Example"
        ea_install.mkdir(parents=True)
        others = [LauncherGame("Example EA game", "EA", str(ea_install),
                               "ea455", None, "Registry installation record")]
        archive = self.root / "old-game-mod.zip"
        archive.write_bytes(b"UI fixture, not game data")
        stamp = time.time() - 800*86400
        os.utime(archive, (stamp, stamp))
        stat = archive.stat()
        old = OldFile(str(archive), stat.st_size, stat.st_mtime, stat.st_dev,
                      stat.st_ino, stat.st_mtime_ns, stat.st_nlink)
        inventory = self.window.inventory
        inventory.steam = steam
        inventory.other = others
        inventory.games = merge_games(steam, others)
        inventory.files = [old]
        inventory.scanned_at = "Disposable test inventory"
        inventory.graveyard = build_graveyard(steam, [], [old], 365)

    def assert_page_fits(self):
        self.flush()
        page = self.window.page
        self.assertLessEqual(page.body.width(), page.viewport().width() + 2,
                             self.window.current_route + " clips horizontally")
        self.assertTrue(self.window.global_search.isVisible())
        for metric in page.findChildren(QPushButton, "approvedMetric"):
            for label in metric.findChildren(QLabel):
                bounds = QRect(label.mapTo(metric, QPoint(0, 0)), label.size())
                self.assertTrue(metric.rect().contains(bounds),
                                "Overview metric hides its label or value")

    def capture(self, route, size):
        folder = os.environ.get("GG_LOCKED_UI_CAPTURE_DIR")
        if not folder:
            return
        output = Path(folder)
        output.mkdir(parents=True, exist_ok=True)
        slug = route.casefold().replace(" ", "-")
        self.window.grab().save(str(output / f"crimson-locked-{slug}-{size[0]}.png"))
        (output / "locked-ui-evidence.json").write_text(json.dumps({
            "kind": "Rendered native Qt UI; disposable synthetic inventory",
            "platform": os.name,
            "source_commit": os.environ.get("GITHUB_SHA", "local working tree"),
            "reference_size": [1672, 941],
            "visual_approval": "Rendered against owner-supplied comparison; exact pixel parity is not certified",
        }, indent=2), encoding="utf-8")

    def test_locked_pages_reflow_live_with_populated_inventory(self):
        self.populate()
        for route in self.routes:
            with self.subTest(route=route):
                self.window.resize(1672, 941)
                self.window._settings_category_index = 0
                self.window.navigate(route)
                self.assert_page_fits()
                self.capture(route, (1672, 941))
                page = self.window.page
                for size in ((1366, 768), (1040, 720), (1672, 941)):
                    self.window.resize(*size)
                    self.assert_page_fits()
                    self.assertIs(self.window.page, page,
                                  "Resize must preserve the live page and its controls")
                    self.capture(route, size)

    def test_locked_empty_pages_fit_small_window(self):
        self.window.resize(1040, 720)
        for route in self.routes:
            with self.subTest(route=route):
                self.window.navigate(route)
                self.assert_page_fits()

    def test_graveyard_resize_preserves_search_and_selection(self):
        self.populate()
        self.window.navigate("Graveyard")
        search = self.window.grave_search
        table = self.window.grave_table
        search.setText("old-game-mod")
        table.selectRow(0)
        self.flush()
        selected_key = self.window._shown_graves[0].key
        for width in (1672, 1040, 1366, 1672):
            self.window.resize(width, 768)
            self.assert_page_fits()
            self.assertIs(self.window.grave_search, search)
            self.assertIs(self.window.grave_table, table)
            self.assertEqual(search.text(), "old-game-mod")
            self.assertEqual(len(table.selectionModel().selectedRows()), 1)
            self.assertEqual(self.window._shown_graves[0].key, selected_key)

    def test_settings_does_not_count_steam_installations_as_ea(self):
        self.populate()
        self.window.navigate("Settings")
        self.flush()
        ea = next(label for label in self.window.page.findChildren(QLabel)
                  if label.text() == "EA")
        row = [label.text() for label in ea.parentWidget().findChildren(QLabel)]
        self.assertEqual(row, ["EA", "1 games"])

    def test_checked_findings_preserve_protection_and_drop_hidden_items(self):
        self.populate()
        from core import OldFile
        from gg_desktop.backend import refresh_graveyard
        another = self.root / "another-game-mod.zip"
        another.write_bytes(b"another disposable archive fixture")
        stamp = time.time() - 800*86400
        os.utime(another, (stamp, stamp))
        stat = another.stat()
        self.window.inventory.files.append(OldFile(str(another), stat.st_size,
            stat.st_mtime, stat.st_dev, stat.st_ino, stat.st_mtime_ns, stat.st_nlink))
        self.window.settings["never_touch"] = [self.window.inventory.files[0].path]
        refresh_graveyard(self.window.inventory, self.window.settings)
        self.window.navigate("Graveyard")
        from PySide6.QtCore import Qt
        for index in range(self.window.grave_table.rowCount()):
            self.window.grave_table.item(index, 0).setCheckState(Qt.Checked)
        self.assertEqual(len(self.window._selected_grave_entries()), 2)
        with patch.object(self.window, "error") as error, \
                patch.object(self.window, "_approve_recycle") as recycle:
            self.window._delete_grave_selected()
            error.assert_called_once()
            recycle.assert_not_called()
        self.window.grave_search.setText("another-game-mod")
        self.flush()
        selected = self.window._selected_grave_entries()
        self.assertEqual([entry.path for entry in selected], [str(another)])
        clear = next(button for button in self.window.page.findChildren(QPushButton)
                     if button.text() == "Clear")
        clear.click()
        self.assertEqual(self.window._selected_grave_entries(), [])

    def test_settings_save_and_revert_use_the_last_checkpoint(self):
        self.window.navigate("Settings")
        with patch("core.save_settings") as save, \
                patch.object(self.window, "info"), \
                patch.object(self.window, "confirm", return_value=True):
            self.window.settings["scan_on_launch"] = True
            save_button = next(b for b in self.window.page.findChildren(QPushButton)
                               if b.text() == "Save changes")
            save_button.click()
            self.window.settings["scan_on_launch"] = False
            revert = next(b for b in self.window.page.findChildren(QPushButton)
                          if b.text() == "Revert changes")
            revert.click()
            self.assertTrue(self.window.settings["scan_on_launch"])
            self.assertTrue(save.call_args.args[0]["scan_on_launch"])

    def test_settings_revert_never_removes_personal_rules_without_confirmation(self):
        self.window.navigate("Settings")
        rule = str(self.root / "protected-personal-folder")
        self.window.settings["never_touch"] = [rule]
        with patch("core.save_settings") as save, \
                patch.object(self.window, "confirm", return_value=False) as confirm:
            revert = next(b for b in self.window.page.findChildren(QPushButton)
                          if b.text() == "Revert changes")
            revert.click()
            confirm.assert_called_once()
            self.assertTrue(confirm.call_args.kwargs["destructive"])
            self.assertEqual(self.window.settings["never_touch"], [rule])
            save.assert_not_called()

    def test_editing_tool_pins_does_not_launch_the_tools(self):
        def unpin_first():
            menu = self.app.activePopupWidget()
            if menu is not None:
                menu.actions()[0].setChecked(False)
                menu.close()
        with patch.object(self.window, "_create_kit") as create, \
                patch("gg_desktop.screens.save_settings") as save:
            self.window.navigate("More Tools")
            edit = next(b for b in self.window.page.findChildren(QPushButton)
                        if b.text() == "Edit pins")
            QTimer.singleShot(0, unpin_first)
            edit.click()
            self.assertNotIn("Resurrection Kit", self.window.settings["pinned_tools"])
            self.assertNotIn("Resurrection Kit", save.call_args.args[0]["pinned_tools"])
            create.assert_not_called()

    def test_ai_reply_survives_leaving_and_reopening_page(self):
        self.window.settings["ai_assistant_enabled"] = True
        pending = {}
        def hold_job(function, success, **kwargs):
            pending["success"] = success
            pending["failure"] = kwargs["on_failure"]
        with patch("gg_desktop.approved_ai.is_ai_installed", return_value=True), \
                patch.object(self.window, "job", side_effect=hold_job):
            self.window.navigate("AI Assistant")
            self.flush()
            entry = next(field for field in self.window.page.findChildren(QLineEdit)
                         if field.accessibleName() == "Optional local AI question")
            entry.setText("Explain my findings <b>literally</b>")
            entry.returnPressed.emit()
            self.window.navigate("Overview")
            self.flush()  # Destroy the old conversation widgets before the reply.
            pending["success"]((True, "Review evidence <i>literally</i> before removing a file."))
            self.window.navigate("AI Assistant")
            self.flush()
            transcript = self.window.page.findChildren(QTextBrowser)[0]
            self.assertIn("Explain my findings <b>literally</b>", transcript.toPlainText())
            self.assertIn("Review evidence <i>literally</i>", transcript.toPlainText())
            send = next(button for button in self.window.page.findChildren(QPushButton)
                        if button.text() == "Send")
            self.assertTrue(send.isEnabled())


if __name__ == "__main__":
    unittest.main()
