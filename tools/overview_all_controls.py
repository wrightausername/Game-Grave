"""Expanded Overview checks shared by the three independent click-through runs."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import threading
import time
from unittest.mock import patch


def check_controls(*, window, inventory, storage, root, app, home, drive, clicked,
                   completed, wait_for, settle, readable, native_error, output):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QAbstractButton, QComboBox, QDialogButtonBox, QLabel, QListWidget, QMessageBox, QPushButton, QTableWidget
    from core import ModFolder, OldFile, load_settings, save_settings
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.backend import ScanCanceled
    from gg_desktop.reference_widgets import CARD_ROLE

    def header(tip):
        return next(b for b in window.top_bar.findChildren(QPushButton) if b.toolTip() == tip)
    def dismiss_message(dialog):
        assert isinstance(dialog, QMessageBox)
        readable(dialog)
        QTest.mouseClick(dialog.button(QMessageBox.Ok), Qt.LeftButton)
    def selected_row(table, row=0):
        rect = table.visualItemRect(table.item(row, 0))
        QTest.mouseClick(table.viewport(), Qt.LeftButton, pos=rect.center())
    def record(path):
        st = path.stat()
        return OldFile(str(path), st.st_size, st.st_mtime, st.st_dev, st.st_ino, st.st_mtime_ns, st.st_nlink)

    control = home()
    # Pass one: point at actual displayed controls, rather than invoke slots.
    for name in list(window.overview_metrics):
        metric = window.overview_metrics[name]
        window.page.ensureWidgetVisible(metric)
        QTest.mouseClick(metric, Qt.LeftButton)
        settle()
        assert window.current_route == name
        completed("Mouse: " + name + " metric", "Open the corresponding tab.")
        control = home()
    for title, route in (("Find Mods   ›", "Mods"), ("Review Old Files   ›", "Old Files"),
                         ("Manage Captures   ›", "Captures"), ("Open Graveyard   ›", "Graveyard"),
                         ("Review Cleanup", "Graveyard"), ("View All Games →", "Games"),
                         ("View History →", "Undo Center")):
        clicked(window.page, title)
        assert window.current_route == route
        completed("Mouse: " + title, "Reach " + route + " without launching or deleting anything.")
        control = home()
    window.page.ensureWidgetVisible(window.overview_library)
    item = window.overview_library.item(0)
    with patch.object(CrimsonWindow, "_launch_selected_game") as launch:
        QTest.mouseClick(window.overview_library.viewport(), Qt.LeftButton,
                         pos=window.overview_library.visualItemRect(item).center())
        settle()
        assert window.current_route == "Games" and window._current_game().key == inventory.games[0].key
        launch.assert_not_called()
    completed("Mouse: game artwork", "Inspect that exact installation without launching it.")
    control = home()
    def inspect_button(dialog):
        table = dialog.findChild(QTableWidget)
        selected_row(table)
        clicked(dialog, "Inspect selected")
    drive(control.storage_details, inspect_button)
    assert window.current_route == "Games" and window._current_game().key == inventory.games[0].key
    completed("Mouse: storage Inspect selected", "Open the exact installation represented by the selected row.")
    control = home()
    for category in list(window.overview_legend):
        caption, value, _ = window.overview_legend[category]
        dot = next(l for l in caption.parentWidget().findChildren(QLabel) if l.text() == "●")
        for part, widget in (("dot", dot), ("label", caption), ("value", value)):
            def category_dialog(dialog, category=category):
                assert dialog.findChild(QComboBox).currentText() == category
                clicked(dialog, "Close")
            window.page.ensureWidgetVisible(widget)
            drive(lambda widget=widget: QTest.mouseClick(widget, Qt.LeftButton), category_dialog)
            completed("Mouse: " + category + " legend " + part, "Open the same category from every part of the legend.")
    for tip, title in (("Help", "Game Grave Help"), ("Scan status and warnings", "Scan Status")):
        def message(dialog, title=title):
            assert dialog.windowTitle() == title
            readable(dialog)
            assert dialog.grab().save(str(output/("overview-triple-help.png" if title == "Game Grave Help" else "overview-triple-status.png")))
            dismiss_message(dialog)
        drive(lambda tip=tip: QTest.mouseClick(header(tip), Qt.LeftButton), message)
        completed("Mouse: " + tip, "Open a readable message and close it normally.")
    def activity_history(dialog):
        clicked(dialog, "View History")
    drive(lambda: QTest.mouseClick(window.overview_activity[0][0], Qt.LeftButton), activity_history)
    assert window.current_route == "Undo Center"
    completed("Mouse: activity details → View History", "Reach the recorded history.")
    control = home()

    # Pass two: focus, type and activate using ordinary keyboard conventions.
    window.activateWindow()
    QTest.qWait(60)
    QTest.keyClick(window, Qt.Key_K, Qt.ControlModifier)
    assert window.global_search.hasFocus()
    QTest.keyClicks(window.global_search, "Mountain")
    clear = next(b for b in window.global_search.findChildren(QAbstractButton)
                 if b.isVisible() and b.geometry().center().x() > window.global_search.width()/2)
    QTest.mouseClick(clear, Qt.LeftButton)
    assert not window.global_search.text() and not window.overview_search_hint.isVisible()
    completed("Keyboard/mouse: Ctrl+K, type, click clear", "Focus search, clear it and restore the full library.")
    window.page.ensureWidgetVisible(window.overview_ring)
    window.activateWindow()
    QTest.qWait(40)
    window.overview_ring.setFocus()
    QTest.qWait(20)
    for category in list(window.overview_legend):
        window.activateWindow()
        QTest.qWait(35)
        assert app.focusWidget() is not None, "No focused widget after dialog dismissal"
        QTest.keyClick(app.focusWidget(), Qt.Key_Tab)
        assert app.focusWidget() is window.overview_legend[category][0], "Legend has duplicate or missing Tab stops"
        def keyboard_category(dialog, category=category):
            assert dialog.findChild(QComboBox).currentText() == category
            QTest.keyClick(dialog, Qt.Key_Escape)
        caption = window.overview_legend[category][0]
        drive(lambda caption=caption: QTest.keyClick(caption, Qt.Key_Return), keyboard_category)
        completed("Keyboard: Tab/Enter on " + category, "Reach each category once and dismiss with Escape.")
    for name in list(window.overview_metrics):
        metric = window.overview_metrics[name]
        window.page.ensureWidgetVisible(metric)
        metric.setFocus()
        QTest.keyClick(metric, Qt.Key_Space)
        settle()
        assert window.current_route == name
        completed("Keyboard: Space on " + name, "Activate the same action as a mouse click.")
        control = home()

    for start in ("hero", "quick", "F5"):
        entered = threading.Event()
        def scan(settings, canceled, progress):
            entered.set()
            progress(20, "Disposable click-through scan")
            while not canceled():
                time.sleep(.003)
            raise ScanCanceled("Canceled fixture scan")
        with patch("gg_desktop.app.scan_inventory", side_effect=scan) as scanner:
            if start == "F5":
                window.activateWindow()
                QTest.qWait(50)
                QTest.keyClick(window, Qt.Key_F5)
            else:
                target = window.overview_hero.scan if start == "hero" else window.overview_quick_scan
                window.page.ensureWidgetVisible(target)
                QTest.mouseClick(target, Qt.LeftButton)
            wait_for(entered.is_set)
            assert not window.overview_hero.scan.isEnabled() and not window.overview_quick_scan.isEnabled()
            QTest.mouseClick(window.overview_hero.scan, Qt.LeftButton)
            assert scanner.call_count == 1
            assert window.overview_cancel.text() == "Cancel Scan"
            QTest.mouseClick(window.overview_cancel, Qt.LeftButton)
            wait_for(lambda: not window.workers and not window.scanning)
            assert window.inventory is inventory
        completed("State: start/cancel scan via " + start, "Start once, prevent duplicate scans and keep accepted results on cancellation.")
        control = home()

    window.scanning = True
    window._sync_scan_controls()
    try:
        with patch.object(window, "error", side_effect=lambda title, message: native_error(window, title, message)):
            drive(lambda: QTest.mouseClick(header("Close"), Qt.LeftButton), dismiss_message)
        assert window.isVisible() and control.active.is_set()
        completed("State: Close during an inventory scan", "Explain the busy state and keep the scan/window active.")
    finally:
        window.scanning = False
        window._sync_scan_controls()
        control.sync_controls()

    # Pass three: persistence, paging, cancelled edits and lifecycle state.
    for i in range(205):
        path = root/"Downloads"/(f"archive-{i:03}.zip")
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(b"ARCHIVE")
        inventory.files.append(record(path))
    shot = root/"Captures/shot.png"
    shot.parent.mkdir()
    shot.write_bytes(b"CAPTURE METADATA FIXTURE")
    inventory.screenshots.append(record(shot))
    cache = root/"Cache"
    cache.mkdir()
    (cache/"shader.bin").write_bytes(b"CACHE")
    inventory.mods.append(ModFolder("Shaders", str(cache), str(root), "Shader cache", (), 5, 1, False, "Shader Cache"))
    for i in range(10):
        install = root/"ExtraGames"/str(i)
        install.mkdir(parents=True)
        inventory.games.append(replace(inventory.games[0], key="extra-"+str(i), install_path=str(install), name="Extra "+str(i)))
    control = home()
    def storage_actions(dialog):
        table = dialog.findChild(QTableWidget)
        inspect = next(b for b in dialog.findChildren(QPushButton) if b.text() == "Inspect selected")
        folder = next(b for b in dialog.findChildren(QPushButton) if b.text() == "Open folder")
        assert not inspect.isEnabled() and not folder.isEnabled()
        selected_row(table)
        chosen = table.item(table.currentRow(), 2).text()
        with patch.object(QDesktopServices, "openUrl", return_value=True) as shell:
            clicked(dialog, "Open folder")
            assert Path(shell.call_args.args[0].toLocalFile()) == Path(chosen)
        clicked(dialog, "Refresh measurement")
        wait_for(lambda: not control.storage_busy)
        assert table.currentRow() >= 0 and table.item(table.currentRow(), 2).text() == chosen
        choice = dialog.findChild(QComboBox)
        choice.setCurrentText("Old Files")
        assert table.rowCount() == 200
        first = table.item(0, 2).text()
        clicked(dialog, "Next")
        assert table.rowCount() == 5 and table.item(0, 2).text() != first
        clicked(dialog, "Previous")
        assert table.rowCount() == 200 and table.item(0, 2).text() == first
        clicked(dialog, "Close")
    drive(control.storage_details, storage_actions)
    completed("State: storage selection, folder open, refresh and paging", "Keep the selection, open its folder and reach findings beyond row 200.")
    window.page.ensureWidgetVisible(window.overview_next)
    assert window.overview_next.isEnabled() and not window.overview_previous.isEnabled()
    QTest.mouseClick(window.overview_next, Qt.LeftButton)
    assert window.overview_previous.isEnabled()
    QTest.mouseClick(window.overview_previous, Qt.LeftButton)
    assert not window.overview_previous.isEnabled()
    completed("State: library Previous/Next", "Move through all installations and disable at the ends.")

    preferences = root/"ActualPreferences"
    with patch("core.config_dir", return_value=preferences):
        save_settings(window.settings)
        window.page.ensureWidgetVisible(window.overview_library)
        item = window.overview_library.item(0)
        rect = window.overview_library.visualItemRect(item)
        star = QPoint(rect.right()-15, rect.top()+15)
        QTest.mouseClick(window.overview_library.viewport(), Qt.LeftButton, pos=star)
        saved_favorites = lambda: json.loads((preferences/"settings.json").read_text()).get("desktop_favorites", [])
        assert item.data(CARD_ROLE)["favorite"] and inventory.games[0].key in saved_favorites()
        with patch("gg_desktop.app.load_settings", side_effect=load_settings):
            clone = CrimsonWindow()
            clone.show()
            clone.inventory = inventory
            clone.navigate("Overview")
            QTest.qWait(30)
            wait_for(lambda: not clone.workers)
            assert clone.overview_library.item(0).data(CARD_ROLE)["favorite"]
            clone.navigate("Games")
            wait_for(lambda: not clone.workers)
            index = next(i for i, game in enumerate(clone._shown_games) if game.key == inventory.games[0].key)
            assert clone.game_grid.item(index).data(CARD_ROLE)["favorite"], "Opening game details lost the restored favorite state"
            clone.close()
            clone.deleteLater()
            settle()
        window.activateWindow()
        def save_failed(dialog):
            assert dialog.windowTitle() == "Favorite not saved"
            dismiss_message(dialog)
        with patch("gg_desktop.overview_storage_ui.save_settings", side_effect=OSError("Disposable save failure")), \
             patch.object(window, "error", side_effect=lambda title, message: native_error(window, title, message)):
            drive(lambda: QTest.mouseClick(window.overview_library.viewport(), Qt.LeftButton, pos=star), save_failed)
        assert item.data(CARD_ROLE)["favorite"] and inventory.games[0].key in saved_favorites()
        QTest.mouseClick(window.overview_library.viewport(), Qt.LeftButton, pos=star)
        assert not item.data(CARD_ROLE)["favorite"] and inventory.games[0].key not in saved_favorites()
        completed("State: favorite persistence and failed save", "Persist through a fresh window and retain the prior favorite when saving fails.")

        steam = root/"SteamLibrary"
        (steam/"steamapps").mkdir(parents=True)
        # A scan-location save must also preserve a favorite restored by the
        # Overview adapter instead of silently dropping its extra preference.
        QTest.mouseClick(window.overview_library.viewport(), Qt.LeftButton, pos=star)
        assert inventory.games[0].key in saved_favorites()
        accepted = replace(inventory, scanned_at="Accepted edited-location fixture")
        def save_locations(dialog):
            with patch("gg_desktop.reference_overview.QFileDialog.getExistingDirectory", return_value=str(steam)):
                clicked(dialog, "Add Folder…")
            QTest.mouseClick(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Save), Qt.LeftButton)
        with patch("gg_desktop.app.scan_inventory", return_value=accepted) as scanner:
            drive(window.open_scan_locations, save_locations)
            QTest.qWait(30)
            wait_for(lambda: not window.workers and window.inventory is accepted)
            assert scanner.call_count == 1 and scanner.call_args.args[0]["steam_extra_roots"] == [str(steam)]
        assert inventory.games[0].key in saved_favorites()
        assert json.loads((preferences/"settings.json").read_text())["steam_extra_roots"] == [str(steam)]
        completed("State: Save scan locations", "Persist the chosen folder, rescan once and preserve saved favorites.")
        window.page.ensureWidgetVisible(window.overview_library)
        item = window.overview_library.item(0)
        rect = window.overview_library.visualItemRect(item)
        QTest.mouseClick(window.overview_library.viewport(), Qt.LeftButton, pos=QPoint(rect.right()-15, rect.top()+15))
        steam2 = root/"SteamLibrary2"
        (steam2/"steamapps").mkdir(parents=True)
        def locations(dialog):
            roots = dialog.findChild(QListWidget)
            remove = next(b for b in dialog.findChildren(QPushButton) if b.text() == "Remove Selected")
            assert not remove.isEnabled()
            initial = roots.count()
            with patch("gg_desktop.reference_overview.QFileDialog.getExistingDirectory", return_value=str(steam2)):
                clicked(dialog, "Add Folder…")
            assert roots.count() == initial+1
            QTest.mouseClick(roots.viewport(), Qt.LeftButton, pos=roots.visualItemRect(roots.item(initial)).center())
            assert remove.isEnabled()
            clicked(dialog, "Remove Selected")
            assert roots.count() == initial and not remove.isEnabled()
            QTest.mouseClick(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Cancel), Qt.LeftButton)
        before = (preferences/"settings.json").read_bytes()
        drive(window.open_scan_locations, locations)
        assert (preferences/"settings.json").read_bytes() == before
        completed("State: add/remove folders then Cancel", "Edit a pending copy and leave saved scan locations unchanged on Cancel.")
        def invalid_locations(dialog):
            initial = dialog.findChild(QListWidget).count()
            def rejected(message):
                assert message.windowTitle() == "Folder not allowed"
                dismiss_message(message)
            with patch("gg_desktop.reference_overview.QFileDialog.getExistingDirectory", return_value=str(root.anchor)), \
                 patch.object(window, "error", side_effect=lambda title, message: native_error(window, title, message)):
                drive(lambda: clicked(dialog, "Add Folder…"), rejected)
            assert dialog.findChild(QListWidget).count() == initial
            QTest.keyClick(dialog, Qt.Key_Escape)
        drive(window.open_scan_locations, invalid_locations)
        completed("State: invalid drive-root scan location", "Reject it clearly without changing preferences or starting a scan.")

    control = home()
    original_size = window.size()
    QTest.mouseClick(header("Maximize or restore"), Qt.LeftButton)
    QTest.qWait(80)
    assert window.isMaximized()
    QTest.mouseClick(header("Maximize or restore"), Qt.LeftButton)
    QTest.qWait(80)
    assert not window.isMaximized() and window.size() == original_size
    QTest.mouseClick(header("Minimize"), Qt.LeftButton)
    QTest.qWait(40)
    assert window.isMinimized()
    window.showNormal()  # Equivalent restore request from the window manager.
    window.activateWindow()
    QTest.qWait(50)
    completed("State: maximize, restore and minimize", "Use normal window states without zooming the app.")

    # A separate window verifies closing during a live measurement without
    # interrupting the main fixture's remaining screenshots.
    clone = CrimsonWindow()
    clone.show()
    clone.inventory = inventory
    clone.navigate("Overview")
    QTest.qWait(30)
    wait_for(lambda: not clone.workers)
    closing = clone.page.overview
    entered = threading.Event()
    def slow(_inventory, *, canceled, progress):
        entered.set()
        while not canceled():
            time.sleep(.003)
        raise InterruptedError()
    with patch("gg_desktop.overview_storage_ui.measure_storage", side_effect=slow):
        closing.refresh_storage(force=True)
        wait_for(entered.is_set)
        close = next(b for b in clone.top_bar.findChildren(QPushButton) if b.toolTip() == "Close")
        QTest.mouseClick(close, Qt.LeftButton)
        wait_for(lambda: not clone.workers)
        assert closing.cancel.is_set() and not closing.active.is_set() and not clone.isVisible()
    clone.deleteLater()
    settle()
    window.activateWindow()
    completed("State: close while measuring", "Stop the read-only worker and close promptly without late UI updates.")

    # Verify that Overview's temporary message styling cannot reach a locked tab.
    window.navigate("Games")
    wait_for(lambda: not window.workers)
    def other_tab_message(dialog):
        assert not dialog.property("overviewReadable")
        QTest.mouseClick(dialog.button(QMessageBox.Ok), Qt.LeftButton)
    drive(lambda: QTest.mouseClick(header("Help"), Qt.LeftButton), other_tab_message)
    completed("Isolation: leave Overview and use shared Help", "Preserve the other tab's existing message behavior.")
    home()
