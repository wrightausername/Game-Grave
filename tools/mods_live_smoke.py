"""Exercise every Mods control in native Qt using disposable manager fixtures."""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("_ci_temp"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QCoreApplication, QEvent, Qt
    from PySide6.QtGui import QHelpEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QComboBox, QPushButton, QToolTip
    from core import SteamGame, default_settings
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.models import merge_games
    from gg_desktop.mods import ModDetails
    from tests.test_mods_functionality import mo2_fixture

    app = QApplication.instance() or QApplication([])
    def settle():
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
    def wait_for(predicate):
        deadline = time.monotonic() + 15
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
            time.sleep(.004)  # Let Python filesystem workers run between Qt's test waits.
        assert predicate(), "Mods did not finish its task"
        settle()
    def click(parent, text):
        widget = next(b for b in parent.findChildren(QPushButton) if b.text() == text)
        assert widget.isEnabled(), text + " was disabled"
        widget.click()
        settle()
        return widget
    def tree_bytes(folder):
        return {str(path.relative_to(folder)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in folder.rglob("*") if path.is_file()}

    with tempfile.TemporaryDirectory(prefix="GG-mods-live-") as temp:
        root = Path(temp)
        inventory, storage, profiles, ini = mo2_fixture(root)
        second_game = root / "Games" / "Another Game"
        second_game.mkdir()
        inventory.steam.insert(0, SteamGame("1", "Another Game", str(root), str(second_game), 100, None, "Unknown"))
        inventory.games = merge_games(inventory.steam, [])
        for i in range(405):
            (storage / f"Synthetic Extra {i:04}").mkdir()
        manifest = storage / "MountainTextures" / "manifest.json"
        data = json.loads(manifest.read_text())
        data["Website"] = "https://www.nexusmods.com/skyrimspecialedition/mods/123"
        manifest.write_text(json.dumps(data))
        source_before = tree_bytes(ini.parent)
        inventory_before = deepcopy(inventory)
        with patch("gg_desktop.app.load_settings", side_effect=default_settings), \
             patch("gg_desktop.ready_room_services.config_dir", return_value=root / "Preferences"), \
             patch.object(CrimsonWindow, "info") as info, patch.object(CrimsonWindow, "error") as errors, \
             patch("gg_desktop.mods.QDesktopServices.openUrl", return_value=True) as opened, \
             patch.object(CrimsonWindow, "_launch_classic_tools", side_effect=AssertionError("Frozen EXE cannot hand off to classic source")), \
             patch.object(CrimsonWindow, "_approve_recycle") as recycle:
            window = CrimsonWindow()
            window.resize(1450, 900)
            window.show()
            window.inventory = inventory
            window.navigate("Mods")
            wait_for(lambda: not window.workers and window.page.mods.report is not None)
            control = window.page.mods
            assert len(control.catalog.entries) == 412
            assert window.mod_table.rowCount() == 400 and control.paging.isVisible()
            assert [window.mod_table.horizontalHeaderItem(i).text() for i in range(4)] == ["LOCATION", "SOURCE", "EVIDENCE", "APPARENT SIZE"]
            assert window.mod_table.item(0, 0).text() == str(storage)
            window.mod_table.clearSelection()
            click(window.page, "Explain selected source")
            assert info.call_args[0][0] == "Choose a mod location"
            click(window.page, "Game DNA")
            assert info.call_args[0][0] == "Game association unverified"
            assert window.current_route == "Mods"

            mountain = next(e for e in control.catalog.entries if e.name == "Mountain Textures")
            index = next(i for i, e in enumerate(control.shown) if e.key == mountain.key)
            window.mod_table.selectRow(index)
            for col in range(4):
                tooltip = window.mod_table.item(index, col).toolTip()
                assert "High resolution mountain textures" in tooltip and "Required dependency not enabled" in tooltip
                assert "File overlap" in tooltip and "Local Author" in tooltip and "unverified" in tooltip
            rect = window.mod_table.visualItemRect(window.mod_table.item(index, 0))
            event = QHelpEvent(QEvent.ToolTip, rect.center(), window.mod_table.viewport().mapToGlobal(rect.center()))
            QApplication.sendEvent(window.mod_table.viewport(), event)
            assert "High resolution mountain textures" in QToolTip.text()
            assert "File overlap" in QToolTip.text()
            QToolTip.hideText()
            click(window.page, "Explain selected source")
            details = next(v for v in control.views if isinstance(v, ModDetails))
            assert "textures/mountain.dds" in details.text.toPlainText()
            assert "Default: enabled in saved profile" in details.text.toPlainText()
            click(details, "Open folder")
            assert opened.call_args[0][0].toLocalFile() == mountain.path
            click(details, "Manager folder")
            assert opened.call_args[0][0].toLocalFile() == str(ini.parent)
            click(details, "Mod page")
            assert opened.call_args[0][0].toString() == data["Website"]
            click(details, "Copy path")
            assert QApplication.clipboard().text() == mountain.path
            assert details.grab().save(str(args.output / "mods-description-and-conflicts-1450.png"))
            click(details, "Close")

            window.activateWindow()
            window.mod_table.setFocus()
            QTest.qWait(25)
            QTest.keyClick(window.mod_table, Qt.Key_F1)
            settle()
            details = next(v for v in control.views if isinstance(v, ModDetails) and __import__("shiboken6").isValid(v))
            click(details, "Close")
            click(window.page, "Open Mod Radar tools")
            tools = control.tools
            assert tools.isVisible() and tools.export_button.isEnabled()
            tools.search.setText("snow surfaces")
            assert len(tools.shown) == 1 and tools.shown[0].name == "Snow Textures"
            click(tools, "Inspect selected")
            details = next(v for v in control.views if isinstance(v, ModDetails) and __import__("shiboken6").isValid(v))
            click(details, "Close")
            click(tools, "Open folder")
            assert opened.call_args[0][0].toLocalFile().endswith("SnowTextures")
            tools.search.setText("zero matches for this phrase")
            assert not tools.shown and not tools.details.isEnabled()
            tools.search.clear()
            assert tools.next.isEnabled()
            click(tools, "Next →")
            assert tools.index == 1 and len(tools.shown) == 12
            click(tools, "← Previous")
            tools.profiles.setCurrentIndex(1)
            assert len(tools.shown) in (3, 5)
            tools.profiles.setCurrentIndex(0)
            tools.search.setText("Extra 0404")
            assert len(tools.shown) == 1 and tools.shown[0].name == "Synthetic Extra 0404"

            first_report = control.report
            def canceled_check(catalog, canceled, progress):
                while not canceled():
                    time.sleep(.005)
                raise InterruptedError("Canceled")
            window.scanning = True
            with patch("gg_desktop.mods.inspect_conflicts", side_effect=canceled_check):
                click(tools, "Check conflicts")
                assert tools.cancel_button.isEnabled() and not tools.check_button.isEnabled()
                click(tools, "Cancel checks")
                wait_for(lambda: not window.workers and not control.busy)
            assert control.report is first_report and window.scanning
            assert "previous report retained" in tools.status.text()
            with patch("gg_desktop.mods.inspect_conflicts", side_effect=OSError("Disposable failure")):
                click(tools, "Check conflicts")
                wait_for(lambda: not window.workers and not control.busy)
            assert control.report is first_report and window.scanning
            window.scanning = False
            click(tools, "Check conflicts")
            wait_for(lambda: not window.workers and not control.busy)
            assert control.report is not first_report

            export = root / "Mod-Report.json"
            with patch("gg_desktop.mods.QFileDialog.getSaveFileName", return_value=(str(export), "JSON")):
                click(tools, "Export report…")
                click(tools, "Export report…")
            document = json.loads(export.read_text(encoding="utf-8"))
            assert document["report"]["profiles_checked"] == 2
            assert info.call_args[0][0] == "Choose a new report filename"
            with patch("gg_desktop.mods.QFileDialog.getSaveFileName", return_value=(str(storage / "Forbidden.json"), "JSON")):
                click(tools, "Export report…")
            assert not (storage / "Forbidden.json").exists()
            assert errors.call_args[0][0] == "Could not export report"
            errors.reset_mock()

            tools.search.setText("Mountain Textures")
            click(tools, "Refresh details")
            wait_for(lambda: not window.workers and not control.busy)
            assert control.report is not None and len(tools.shown) == 1
            tools.search.clear()
            assert tools.grab().save(str(args.output / "mods-tools-1450.png"))
            click(tools, "Close")
            click(window.page, "Next →")
            assert control.index == 1 and len(control.shown) == 12
            click(window.page, "← Previous")
            window.mod_table.selectRow(index)
            for width, height in ((1450, 900), (1280, 790), (960, 650)):
                window.resize(width, height)
                settle()
                assert window.grab().save(str(args.output / f"mods-functional-{width}.png"))
                tools = control.open_tools()
                settle()
                assert tools.geometry().right() - tools.geometry().left() < width
                assert tools.export_button.isVisible() and tools.check_button.isVisible()
                tools.close()
                settle()

            window.mod_table.selectRow(index)
            click(window.page, "Game DNA")
            assert window.current_route == "Game DNA"
            chooser = window.page.findChild(QComboBox)
            assert "Skyrim" in chooser.currentText() and chooser.currentIndex() == 1
            settle()
            window.navigate("Mods")
            wait_for(lambda: not window.workers and not window.page.mods.busy)
            control = window.page.mods
            tools = control.open_tools()
            late = root / "stale-dialog-report.json"
            def late_picker(*_args):
                window.navigate("Overview")
                settle()
                return str(late), "JSON"
            with patch("gg_desktop.mods.QFileDialog.getSaveFileName", side_effect=late_picker):
                control.export(tools)
            assert not late.exists()
            wait_for(lambda: not window.workers)
            assert inventory == inventory_before
            assert tree_bytes(ini.parent) == source_before
            recycle.assert_not_called()
            errors.assert_not_called()
            window.close()
            settle()
    print("PASS: Mods hover descriptions and conflict evidence, every native control, profile filters, "
          "412 reachable entries, cancellation/failure retention, JSON export, stale dialogs, exact Game DNA, "
          "three window sizes and untouched game/manager data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
