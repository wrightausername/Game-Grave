"""Goal-based click-through of Overview; uses real Qt events and disposable data.

This is an agent usability walkthrough, not a study with recruited participants.
The Windows workflow also runs these journeys in native Qt windows.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("_ci_temp"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt, QTimer
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QLabel, QLineEdit, QListWidget, QPushButton, QTableWidget
    from core import default_settings
    from gg_desktop.app import CrimsonWindow
    from tests.test_mods_functionality import mo2_fixture

    app = QApplication.instance() or QApplication([])
    journeys = []
    def settle():
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
    def wait_for(predicate):
        deadline = time.monotonic()+20
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
            time.sleep(.004)
        assert predicate(), "Click-through task did not finish"
        settle()
    def clicked(parent, title):
        control = next(b for b in parent.findChildren(QPushButton) if b.text() == title)
        assert control.isVisible() and control.isEnabled(), title
        QTest.mouseClick(control, Qt.LeftButton)
        settle()
    def drive(open_action, visit):
        errors = []
        def execute():
            dialog = app.activeModalWidget()
            try:
                assert isinstance(dialog, QDialog)
                visit(dialog)
            except Exception as exc:
                errors.append(exc)
                if dialog:
                    dialog.reject()
        QTimer.singleShot(35, execute)
        open_action()
        if errors:
            raise errors[0]
        settle()
    def readable(dialog):
        image = dialog.grab().toImage()
        assert image.pixelColor(3, 3).lightness() < 60, "Overview dialog has a light background behind light text"
    def completed(name, thought):
        journeys.append(dict(task=name, expected_by_user=thought, result="passed"))

    with tempfile.TemporaryDirectory(prefix="GG-Overview-Click-Through-") as temporary:
        root = Path(temporary)
        inventory, storage, *_ = mo2_fixture(root)
        (Path(inventory.games[0].install_path)/"base.bin").write_bytes(b"G"*70000)
        other = root/"AnotherLibrary/Skyrim"
        other.mkdir(parents=True)
        (other/"base.bin").write_bytes(b"H"*11000)
        duplicate = replace(inventory.games[0], key="other-install", install_path=str(other), launcher="Epic Games")
        inventory.games.append(duplicate)
        preferences = default_settings()
        preferences["scan_on_launch"] = False
        event = dict(kind="Scan completed", date="2026-11-06T12:00:00+00:00", details="Disposable walkthrough scan")
        with patch("gg_desktop.app.load_settings", return_value=preferences), \
             patch("gg_desktop.reference_overview.get_activity", return_value=[event]), \
             patch("gg_desktop.reference_overview.get_records", return_value=[]), \
             patch("gg_desktop.ready_room_services.config_dir", return_value=root/"Preferences"), \
             patch("gg_desktop.game_artwork.artwork_dir", return_value=root/"Artwork"), \
             patch("gg_desktop.game_artwork._request", side_effect=AssertionError("Automatic network")) as network, \
             patch.object(CrimsonWindow, "error") as error, \
             patch.object(CrimsonWindow, "_approve_recycle") as recycle:
            window = CrimsonWindow()
            window.resize(1450, 900)
            window.show()
            window.activateWindow()
            def home():
                window.inventory = inventory
                window.navigate("Overview")
                QTest.qWait(30)
                wait_for(lambda: not window.workers)
                window.status.setText("DISPOSABLE CLICK-THROUGH FIXTURE · Actual measured files")
                window.page.overview.sync_controls()
                return window.page.overview
            control = home()
            ring = window.overview_ring
            total = sum(value for _, value, _ in ring.segments)
            start = 90
            for category, size, _ in ring.segments:
                if category == "Mods":
                    angle = start-180*size/total
                    break
                start -= 360*size/total
            radius = min(ring.width(), ring.height())/220*89
            point = QPoint(round(ring.width()/2+radius*math.cos(math.radians(angle))),
                           round(ring.height()/2-radius*math.sin(math.radians(angle))))
            def mod_slice(dialog):
                readable(dialog)
                assert dialog.findChild(QComboBox).currentText() == "Mods"
                table = dialog.findChild(QTableWidget)
                assert table.rowCount() and all(table.item(i, 1).text() == "Mods" for i in range(table.rowCount()))
                assert dialog.grab().save(str(args.output/"overview-human-storage.png"))
                clicked(dialog, "Close")
            drive(lambda: QTest.mouseClick(ring, Qt.LeftButton, pos=point), mod_slice)
            completed("Click the Mods slice", "Show my mods with readable text, not every category.")

            inspected = []
            with patch.object(control, "inspect", side_effect=lambda *a: inspected.append(a)):
                def row_enter(dialog):
                    table = dialog.findChild(QTableWidget)
                    table.selectRow(0)
                    table.setFocus()
                    QTest.keyClick(table, Qt.Key_Return)
                    assert len(inspected) == 1 and not dialog.isVisible()
                drive(control.storage_details, row_enter)
            completed("Select a storage row and press Enter", "Inspect that exact location once, without starting a refresh.")

            inspected.clear()
            with patch.object(control, "inspect", side_effect=lambda *a: inspected.append(a)):
                def row_double_click(dialog):
                    table = dialog.findChild(QTableWidget)
                    table.selectRow(0)
                    rect = table.visualItemRect(table.item(0, 0))
                    QTest.mouseClick(table.viewport(), Qt.LeftButton, pos=rect.center())
                    QTest.mouseDClick(table.viewport(), Qt.LeftButton, pos=rect.center())
                    QTest.qWait(20)
                    assert len(inspected) == 1 and not dialog.isVisible()
                drive(control.storage_details, row_double_click)
            completed("Double-click a storage row", "Open it once, just like Enter.")

            before = control.snapshot
            def filter_enter(dialog):
                search = dialog.findChild(QLineEdit)
                QTest.mouseClick(search, Qt.LeftButton)
                QTest.keyClicks(search, "Mountain")
                QTest.keyClick(search, Qt.Key_Return)
                table = dialog.findChild(QTableWidget)
                assert table.rowCount() == 1 and table.currentRow() == 0
                assert not control.storage_busy and control.snapshot is before
                QTest.keyClick(table, Qt.Key_Escape)
            drive(control.storage_details, filter_enter)
            completed("Filter storage, then press Enter and Escape", "Reach the matching row, then close the dialog without unexpected work.")

            def scan_locations(dialog):
                readable(dialog)
                assert dialog.grab().save(str(args.output/"overview-human-locations.png"))
                QTest.keyClick(dialog, Qt.Key_Escape)
            drive(lambda: QTest.mouseClick(window.overview_hero.locations, Qt.LeftButton), scan_locations)
            completed("Open and dismiss Scan Locations", "Read the coverage and leave without saving or scanning.")

            QTest.mouseClick(window.global_search, Qt.LeftButton)
            QTest.keyClicks(window.global_search, "Mountain")
            assert window.overview_search_hint.isVisible()
            assert "No matching games" in window.overview_search_hint.text()
            assert "Press Enter" in window.overview_search_hint.text()
            assert window.grab().save(str(args.output/"overview-human-search-help.png"))
            def mod_search(dialog):
                readable(dialog)
                entries = dialog.findChild(QListWidget)
                assert entries.count() == 1
                QTest.mouseClick(entries.viewport(), Qt.LeftButton, pos=entries.visualItemRect(entries.item(0)).center())
                path = next(l for l in dialog.findChildren(QLabel) if l.accessibleName() == "Selected search result path")
                assert path.text() == str(storage/"MountainTextures")
                assert dialog.grab().save(str(args.output/"overview-human-search-results.png"))
                clicked(dialog, "Close")
            drive(lambda: QTest.keyClick(window.global_search, Qt.Key_Return), mod_search)
            completed("Search for a mod from Overview", "Explain the empty game shelf and show the matching mod and folder after Enter.")

            window.global_search.selectAll()
            QTest.keyClicks(window.global_search, "Skyrim")
            def choose_install(dialog):
                entries = dialog.findChild(QListWidget)
                matches = [i for i in range(entries.count()) if entries.item(i).data(Qt.UserRole)[1] == str(other)]
                assert len(matches) == 1
                entries.setCurrentRow(matches[0])
                label = next(l for l in dialog.findChildren(QLabel) if l.accessibleName() == "Selected search result path")
                assert label.text() == str(other)
                entries.setFocus()
                QTest.keyClick(entries, Qt.Key_Return)
            drive(lambda: QTest.keyClick(window.global_search, Qt.Key_Return), choose_install)
            assert window.current_route == "Games" and window._current_game().key == duplicate.key
            completed("Choose between two installations with the same game name", "Show the folder before opening the exact installation I chose.")

            control = home()
            gate = threading.Event()
            def delayed(_inventory, *, canceled, progress):
                gate.set()
                while not canceled():
                    time.sleep(.003)
                raise InterruptedError()
            previous = control.snapshot
            with patch("gg_desktop.overview_storage_ui.measure_storage", side_effect=delayed):
                control.refresh_storage(force=True)
                wait_for(gate.is_set)
                assert window.overview_cancel.isVisible() and window.overview_cancel.text() == "Cancel measurement"
                QTest.mouseClick(window.overview_cancel, Qt.LeftButton)
                assert not window.overview_cancel.isEnabled()
                wait_for(lambda: not control.storage_busy)
                assert control.snapshot is previous and "canceled" in control.message
            completed("Stop a long storage measurement from the dashboard", "Keep Cancel available and preserve the last successful totals.")

            def activity(dialog):
                readable(dialog)
                assert dialog.grab().save(str(args.output/"overview-human-activity.png"))
                clicked(dialog, "Close")
            drive(lambda: QTest.mouseClick(window.overview_activity[0][0], Qt.LeftButton), activity)
            completed("Open an activity entry", "Read its details against the app's dark background.")

            window.global_search.setText("NoSuchGameOrMod")
            def zero_results(dialog):
                readable(dialog)
                assert dialog.findChild(QListWidget).count() == 0
                inspect = next(b for b in dialog.findChildren(QPushButton) if b.text() == "Inspect selected")
                assert not inspect.isEnabled()
                QTest.keyClick(dialog, Qt.Key_Escape)
            drive(lambda: QTest.keyClick(window.global_search, Qt.Key_Return), zero_results)
            window.global_search.clear()
            assert not window.overview_search_hint.isVisible()
            assert sum(not window.overview_library.item(i).isHidden() for i in range(2)) == 2
            completed("Get no search results, close, and clear search", "Explain the empty result and restore my whole library when cleared.")

            control.refresh_storage(force=True)
            wait_for(lambda: not control.storage_busy)
            window.overview_library.setCurrentRow(-1)
            window.overview_library.clearSelection()
            for width, height in ((1450, 900), (1280, 720), (960, 650)):
                window.resize(width, height)
                QTest.qWait(60)
                settle()
                assert window.grab().save(str(args.output/f"overview-human-dashboard-{width}.png"))
            assert not error.called
            network.assert_not_called()
            recycle.assert_not_called()
            wait_for(lambda: not window.workers)
            window.close()
            settle()
    (args.output/"overview-human-journeys.json").write_text(json.dumps(journeys, indent=2), encoding="utf-8")
    print(f"PASS: {len(journeys)} goal-based Overview mouse/keyboard journeys; readable dialogs, category clicks, exact row activation, search help, installation identity, visible cancel, safe dismissal and three sizes. No shared UI, game files, network or cleanup changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
