"""Native Old Files controls with disposable drives and a mocked Shell transport."""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import replace
import os
from pathlib import Path
import shutil
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
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QCoreApplication, QEvent, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QPushButton
    from core import default_settings
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.backend import Inventory
    from gg_desktop.old_files_data import key
    from tests.test_old_files_functionality import drive_fixture, old_file

    app = QApplication.instance() or QApplication([])
    def settle():
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
    def wait_for(predicate):
        deadline = time.monotonic() + 15
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
            time.sleep(.003)
        assert predicate(), "Old Files did not finish its task"
        settle()
    def click(parent, text):
        control = next(b for b in parent.findChildren(QPushButton) if b.text() == text)
        assert control.isEnabled(), text + " was disabled"
        control.click()
        settle()

    with tempfile.TemporaryDirectory(prefix="GG-old-files-live-") as temp:
        root = Path(temp)
        drive, second, home, downloads, drives = drive_fixture(root)
        records = [old_file(downloads / f"old-{i:04}.zip", data=b"DISPOSABLE " + str(i).encode()) for i in range(507)]
        deep = old_file(drive / "OtherFiles" / "deep.log")
        second_file = old_file(second / "Downloads" / "other-drive.zip")
        protected = old_file(drive / "NeverTouch" / "KEEP.txt")
        old_file(drive / "Windows" / "KEEP.txt")
        new_folder = drive / "ChosenFolder"
        new_file = old_file(new_folder / "chosen-old.zip")
        settings = default_settings()
        settings["scan_folder"] = str(downloads)
        settings["never_touch"] = [str(Path(protected.path).parent)]
        shell_bin = root / "DisposableShellTransport"
        shell_bin.mkdir()
        def transport(path):
            shutil.move(str(path), str(shell_bin / Path(path).name))
        with patch("gg_desktop.app.load_settings", return_value=settings), \
             patch("gg_desktop.old_files.local_drives", return_value=drives) as ui_drives, \
             patch("gg_desktop.old_files_data.local_drives", return_value=drives), \
             patch("gg_desktop.old_files.save_settings") as save, \
             patch("gg_desktop.ready_room_services.config_dir", return_value=root / "Preferences"), \
             patch.object(CrimsonWindow, "info") as info, patch.object(CrimsonWindow, "error") as error, \
             patch.object(CrimsonWindow, "confirm", return_value=False) as confirm, \
             patch("cleanup_actions.recycle_file", side_effect=transport) as shell, \
             patch("cleanup_actions.register_recycle", return_value="disposable-recovery-id") as registered, \
             patch("cleanup_actions.log_event"):
            window = CrimsonWindow()
            window.show()
            window.resize(1450, 900)
            window.navigate("Old Files")
            settle()
            assert window.page.old_files.state.result is None
            assert window.page.old_files.rescan.isEnabled() and not window.page.old_files.recycle.isEnabled()
            with patch("gg_desktop.old_files.QFileDialog.getExistingDirectory", return_value=""):
                click(window.page, "Change scan folder")
            assert window.current_route == "Old Files"
            window.inventory = Inventory(scanned_at="Disposable last PC scan", files=records[:1])
            accepted_inventory = deepcopy(window.inventory)
            window.navigate("Old Files")
            settle()
            control, state = window.page.old_files, window.page.old_files.state
            assert control.drives.count() == 3 and control.table.rowCount() == 1
            previous_calls = ui_drives.call_count
            click(window.page, "Refresh drives")
            assert ui_drives.call_count == previous_calls + 1
            click(window.page, "Move reviewed individual files to Recycle Bin…")
            assert info.call_args[0][0] == "Choose files"
            control.table.selectRow(0)
            click(window.page, "Move reviewed individual files to Recycle Bin…")
            assert confirm.call_count == 1 and Path(records[0].path).exists()
            shell.assert_not_called()

            click(window.page, "Rescan")
            assert state.busy and window.scanning
            wait_for(lambda: not state.busy and not window.workers)
            assert len(state.result.files) == 507 and control.table.rowCount() == 500
            assert state.result.plan.mode == "folder" and control.paging.isVisible()
            click(window.page, "Next →")
            assert len(control.shown) == 7 and control.index == 1
            click(window.page, "← Previous")
            control.search.setText("old-0506")
            assert len(control.shown) == 1 and control.shown[0].path == records[506].path
            control.search.setText("nothing matches this name")
            assert control.table.rowCount() == 0
            control.search.clear()

            control.drives.setCurrentIndex(1)
            assert control.full.isEnabled() and not control.full.isChecked()
            click(window.page, "Rescan")
            wait_for(lambda: not state.busy and not window.workers)
            assert state.result.plan.mode == "quick" and len(state.result.files) == 507
            control.full.setChecked(True)
            click(window.page, "Rescan")
            wait_for(lambda: not state.busy and not window.workers)
            paths = {f.path for f in state.result.files}
            assert deep.path in paths and new_file.path in paths and second_file.path not in paths
            assert protected.path not in paths
            assert state.result.plan.mode == "full"
            assert window.inventory == accepted_inventory, "Drive scan changed another tab's accepted inventory"
            previous = state.result
            for width, height in ((1450, 900), (1280, 790), (960, 650)):
                window.resize(width, height)
                settle()
                assert window.grab().save(str(args.output / f"old-files-functional-{width}.png"))
                assert control.rescan.isVisible() and control.choose_folder.isVisible() and control.full.isVisible()
                window.page.ensureWidgetVisible(control.recycle)
                settle()
                position = control.recycle.mapTo(window.page.viewport(), control.recycle.rect().topLeft())
                assert window.page.viewport().rect().intersects(control.recycle.rect().translated(position))
                window.page.verticalScrollBar().setValue(0)
            window.resize(1450, 900)

            entered = threading.Event()
            def held_scan(plan, canceled, progress):
                entered.set()
                progress(0, "Disposable long full scan")
                while not canceled():
                    time.sleep(.005)
                raise InterruptedError("Canceled")
            with patch("gg_desktop.old_files.scan_files", side_effect=held_scan):
                click(window.page, "Rescan")
                wait_for(entered.is_set)
                assert control.cancel.isVisible() and not control.rescan.isEnabled()
                click(window.page, "Cancel scan")
                wait_for(lambda: not state.busy and not window.workers)
            assert state.result is previous and not window.scanning
            assert "Previous results retained" in state.message
            with patch("gg_desktop.old_files.scan_files", side_effect=OSError("Disconnected drive")):
                click(window.page, "Rescan")
                wait_for(lambda: not state.busy and not window.workers)
            assert state.result is previous and "Disconnected drive" in state.message

            # Both the original toolbar cancel and navigation remain usable.
            entered.clear()
            with patch("gg_desktop.old_files.scan_files", side_effect=held_scan):
                click(window.page, "Rescan")
                wait_for(entered.is_set)
                window.navigate("Settings")
                window.cancel_button.click()
                wait_for(lambda: not state.busy and not window.workers)
            assert window.current_route == "Settings" and state.result is previous
            window.navigate("Old Files")
            settle()
            control = window.page.old_files
            assert control.state is state and state.result is previous

            # A folder change stays here, leaves accepted results labeled and
            # safely switches away from full-drive mode.
            old_folder = state.folder
            with patch("gg_desktop.old_files.QFileDialog.getExistingDirectory", return_value=str(Path(protected.path).parent)):
                click(window.page, "Change scan folder")
            assert state.folder == old_folder and error.call_args[0][0] == "Cannot choose this folder"
            error.reset_mock()
            save.side_effect = OSError("Preference storage unavailable")
            with patch("gg_desktop.old_files.QFileDialog.getExistingDirectory", return_value=str(new_folder)):
                click(window.page, "Change scan folder")
            assert state.folder == old_folder and window.settings["scan_folder"] == old_folder
            save.side_effect = None
            error.reset_mock()
            with patch("gg_desktop.old_files.QFileDialog.getExistingDirectory", return_value=str(new_folder)):
                click(window.page, "Change scan folder")
            assert window.current_route == "Old Files" and state.folder == str(new_folder)
            assert not state.location and not state.full and control.drives.currentIndex() == 0
            assert state.result is previous and key(save.call_args[0][0]["scan_folder"]) == key(new_folder)
            click(window.page, "Rescan")
            wait_for(lambda: not state.busy and not window.workers)
            assert [f.path for f in state.result.files] == [new_file.path]
            control.table.selectRow(0)
            control.details()
            assert info.call_args[0][0] == "Old File details"
            confirm.return_value = True
            click(window.page, "Move reviewed individual files to Recycle Bin…")
            wait_for(lambda: not window.cleaning and not window.workers)
            assert not Path(new_file.path).exists() and (shell_bin / Path(new_file.path).name).exists()
            assert registered.call_count == 1 and not state.result.files
            assert window.current_route == "Old Files" and not control.shown

            # A blocked Windows Shell recovery request keeps the source file.
            control.drives.setCurrentIndex(2)
            click(window.page, "Rescan")
            wait_for(lambda: not state.busy and not window.workers)
            control.table.selectRow(0)
            with patch("cleanup_actions.recycle_file", side_effect=RuntimeError("Windows recovery canary failed")):
                click(window.page, "Move reviewed individual files to Recycle Bin…")
                wait_for(lambda: not window.cleaning and not window.workers)
            assert Path(second_file.path).exists() and len(state.result.files) == 1
            assert "0 file(s) moved" in state.message and "1 skipped" in state.message

            # A protection added during confirmation is checked again by the worker.
            control.drives.setCurrentIndex(2)
            click(window.page, "Rescan")
            wait_for(lambda: not state.busy and not window.workers)
            assert [f.path for f in state.result.files] == [second_file.path]
            control.table.selectRow(0)
            def protect_during_review(*_args, **_kwargs):
                window.settings["never_touch"].append(str(Path(second_file.path).parent))
                return True
            confirm.side_effect = protect_during_review
            click(window.page, "Move reviewed individual files to Recycle Bin…")
            wait_for(lambda: not window.cleaning and not window.workers)
            assert Path(second_file.path).exists() and shell.call_count == 1
            error.reset_mock()
            confirm.side_effect = None

            # A late native folder picker cannot act on a departed page.
            last_settings = deepcopy(window.settings)
            def late_picker(*_args):
                window.navigate("Settings")
                settle()
                return str(downloads)
            with patch("gg_desktop.old_files.QFileDialog.getExistingDirectory", side_effect=late_picker):
                control.change_folder()
            assert window.current_route == "Settings" and window.settings == last_settings
            window.navigate("Old Files")
            control = window.page.old_files
            with patch("gg_desktop.old_files.local_drives", return_value=drives[:1]):
                click(window.page, "Refresh drives")
            assert not state.location and "disconnected" in state.message
            assert Path(protected.path).read_bytes() == b"Disposable old file"
            assert Path(deep.path).exists()
            error.assert_not_called()
            window.close()
            settle()
    print("PASS: Old Files existing buttons, drive selection, quick/full scope, all 507 results, "
          "search/paging, progress/cancel, navigation, retained results on failure, in-page folder changes, "
          "review confirmation, unchanged recovery worker, protection rechecks, stale pickers and three window sizes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
