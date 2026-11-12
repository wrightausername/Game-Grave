"""Native Qt check of the Old Files page: scan, tabs, filters, folder view, protection and Recycle Bin path."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
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
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLabel
    from core import default_settings
    from gg_desktop import old_files_insight as oi
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.backend import Inventory
    from gg_desktop.library_models import file_kind
    from tests.test_old_files_functionality import drive_fixture, old_file

    app = QApplication.instance() or QApplication([])

    def settle():
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()

    def wait_for(predicate, what="Old Files did not finish its task"):
        deadline = time.monotonic() + 20
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
            time.sleep(.004)
        assert predicate(), what
        settle()

    def tree_bytes(folder):
        return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in folder.rglob("*") if p.is_file()}

    def pills(window):
        return [window.old_table.item(i, 5).text() for i in range(window.old_table.rowCount())]

    def names(window):
        return [window.old_table.item(i, 1).text() for i in range(window.old_table.rowCount())]

    def open_tab(window, name):
        window.old_tabs.buttons[name].click()
        settle()
        assert window._old_tab == name, name

    with tempfile.TemporaryDirectory(prefix="GG-old-files-page-") as temp:
        root = Path(temp)
        drive, other_drive, home, downloads, drives = drive_fixture(root)
        game = old_file(downloads / "tweak.oiv")
        archive = old_file(downloads / "family-photos.zip")
        archive_b = old_file(downloads / "PackA" / "one.zip")
        archive_c = old_file(downloads / "PackA" / "two.zip")
        installer = old_file(downloads / "setup_tool.exe")
        log = old_file(drive / "OtherFiles" / "crash_dump.log")
        other = old_file(drive / "OtherFiles" / "Sub" / "notes.dat")
        everything = [game, archive, archive_b, archive_c, installer, log, other]
        before = tree_bytes(drive)
        settings = default_settings()
        settings["scan_folder"] = str(downloads)
        settings["never_touch"] = []
        saved = []
        with patch("gg_desktop.app.load_settings", return_value=settings), \
             patch("gg_desktop.old_files.local_drives", return_value=drives), \
             patch("gg_desktop.old_files_data.local_drives", return_value=drives), \
             patch("gg_desktop.old_files.save_settings"), patch("core.save_settings", side_effect=saved.append), \
             patch("gg_desktop.reference_library.save_settings"), \
             patch("gg_desktop.ready_room_services.config_dir", return_value=root / "Preferences"), \
             patch("gg_desktop.game_artwork.artwork_dir", return_value=root / "Artwork"), \
             patch("gg_desktop.game_artwork._request", side_effect=AssertionError("No automatic network")), \
             patch.object(CrimsonWindow, "info") as info, patch.object(CrimsonWindow, "error") as errors, \
             patch.object(CrimsonWindow, "confirm", return_value=False) as confirm:
            window = CrimsonWindow()
            window.inventory = Inventory(scanned_at="2026-11-06 12:00")
            window.show()
            window.resize(1280, 720)
            window.navigate("Old Files")
            settle()

            # Before any scan nothing is claimed and nothing is selectable.
            assert window.old_table.rowCount() == 0
            assert window.old_notice.text() in {"No files match these filters.", "Choose a drive or folder and use Scan Now. No files have been changed."}, repr(window.old_notice.text())
            assert window.old_metrics.values[0].text() == "0"

            # Exactly one location is chosen at a time and mirrors the combo box.
            assert len(window.old_drive_checks) == 3, len(window.old_drive_checks)
            window.photo_drives.setCurrentIndex(1)
            settle()
            assert [c.isChecked() for c in window.old_drive_checks] == [False, True, False]
            window.old_drive_checks[2].setChecked(True)
            settle()
            assert window.photo_drives.currentIndex() == 2
            assert [c.isChecked() for c in window.old_drive_checks] == [False, False, True]
            window.old_drive_checks[1].setChecked(True)
            settle()
            assert window.photo_drives.currentIndex() == 1
            window.photo_full.setChecked(True)

            # Age filters are exclusive.
            window.old_age_controls[3].setChecked(True)
            window.old_age_controls[1].setChecked(True)
            settle()
            assert [c.isChecked() for c in window.old_age_controls] == [False, True, False, False]
            window.old_age_controls[1].setChecked(False)
            settle()

            state = window.page.old_files.state
            window._old_scan()
            wait_for(lambda: not window.workers and not state.busy)
            found = {f.path for f in state.result.files}
            assert found == {f.path for f in everything}, found ^ {f.path for f in everything}

            # Metrics come from the scan result only.
            values = [v.text() for v in window.old_metrics.values]
            assert values[0] == f"{len(everything)}", values
            assert int(values[3]) >= 1, "tweak.oiv resembles game content"
            assert int(values[3]) + int(values[4]) + int(values[5]) == len(everything), values
            assert window.old_table.rowCount() == len(everything)
            assert "Game" in pills(window)
            assert window.old_table.item(0, 1).data(Qt.UserRole), "Name cell needs its second line"
            assert window.grab().save(str(args.output / "old-files-results-1280.png"))

            # Details show evidence, never a safe-to-remove claim.
            window.old_table.selectRow(names(window).index("tweak.oiv"))
            settle()
            text = " ".join(w.text() for w in window.old_details.findChildren(QLabel))
            assert "Why It's Flagged" in text and "Reviewable" in text, text
            assert "Safe to Remove" not in text, text
            assert "Unverified" in text, text

            # Every in-page tab fills from the scan.
            open_tab(window, "Archives")
            assert names(window) and all(file_kind(n) == "Archives" for n in names(window))
            open_tab(window, "Unused Installers")
            assert names(window) == ["setup_tool.exe"] and "cannot establish" in window.old_notice.text()
            open_tab(window, "By Game")
            assert names(window) == ["tweak.oiv"] and "not verified" in window.old_notice.text().lower()
            open_tab(window, "Downloads")
            assert set(names(window)) == {"tweak.oiv", "family-photos.zip", "one.zip", "two.zip", "setup_tool.exe"}
            open_tab(window, "Large Files")
            assert not names(window) and "1 GB" in window.old_notice.text()
            open_tab(window, "Results")
            assert window.old_table.rowCount() == len(everything)
            open_tab(window, "File Scan")
            window.old_tabs.buttons["Settings"].click()
            settle()
            assert window.current_route == "Settings", window.current_route
            window.navigate("Old Files")
            settle()
            assert window.old_table.rowCount() == len(everything), "The page forgot the last scan"

            # File type filters.
            boxes = {c.text(): c for c in window.old_type_controls}
            assert list(boxes) == list(oi.FILTER_GROUPS)
            for name, box in boxes.items():
                box.setChecked(name == "Logs / Crash Reports")
            settle()
            assert names(window) == ["crash_dump.log"]
            for box in boxes.values():
                box.setChecked(False)
            settle()
            assert window.old_table.rowCount() == 0 and "at least one file type" in window.old_notice.text()
            for box in boxes.values():
                box.setChecked(True)
            settle()
            assert window.old_table.rowCount() == len(everything)

            # Search and sort.
            window.global_search.setText("crash")
            assert names(window) == ["crash_dump.log"]
            window.global_search.clear()
            window.old_sort.setCurrentText("Name (A–Z)")
            settle()
            assert names(window) == sorted(names(window), key=str.casefold)
            window.old_sort.setCurrentText("Size (Largest)")

            # Folder view is review-only groups; the individual files stay the unit of removal.
            window.old_view_folders.click()
            settle()
            assert window._shown_old_groups and not window._shown_old_files
            pack = next(i for i, g in enumerate(window._shown_old_groups) if archive_b.path in {f.path for f in g.files})
            group = window._shown_old_groups[pack]
            window.old_table.item(pack, 0).setCheckState(Qt.Checked)
            settle()
            assert "folders" in window.old_selection.text() and f"{len(group.files)} files" in window.old_selection.text(), window.old_selection.text()
            assert {f.path for f in window._selected_old()} == {f.path for f in group.files}
            assert {archive_b.path, archive_c.path} <= {f.path for f in group.files}
            window.old_select_all.setChecked(True)
            settle()
            assert len(window._selected_old()) == len(everything)
            window.old_select_all.setChecked(False)
            settle()
            assert not window._selected_old()
            assert window.grab().save(str(args.output / "old-files-folders-1280.png"))
            window.old_view_files.click()
            settle()
            assert window._shown_old_files and not window._shown_old_groups

            # Easy ticking: double-click ticks a file, Shift+click ticks the range, Ctrl+click flips one.
            from PySide6.QtTest import QTest
            table = window.old_table
            assert table.rowCount() >= 3
            assert "double-click" in window.old_selection.text(), window.old_selection.text()

            def at(row):
                return table.visualRect(table.model().index(row, 1)).center()

            def ticked():
                return [r for r in range(table.rowCount()) if table.item(r, 0).checkState() == Qt.Checked]
            QTest.mouseDClick(table.viewport(), Qt.LeftButton, Qt.NoModifier, at(0))
            settle()
            assert ticked() == [0], ticked()
            QTest.mouseClick(table.viewport(), Qt.LeftButton, Qt.ShiftModifier, at(2))
            settle()
            assert ticked() == [0, 1, 2], ticked()
            assert window.old_selection.text().startswith("3 selected"), window.old_selection.text()
            QTest.mouseClick(table.viewport(), Qt.LeftButton, Qt.ControlModifier, at(1))
            settle()
            assert ticked() == [0, 2], ticked()
            QTest.mouseDClick(table.viewport(), Qt.LeftButton, Qt.NoModifier, at(0))
            settle()
            assert ticked() == [2], ticked()
            window.old_select_all.setChecked(True)
            window.old_select_all.setChecked(False)
            settle()
            assert not ticked()

            # Selection, Graveyard review, Protect: nothing moves.
            window.old_table.item(names(window).index("notes.dat"), 0).setCheckState(Qt.Checked)
            settle()
            assert window.old_selection.text().startswith("1 selected"), window.old_selection.text()
            window._add_old_to_graveyard()
            assert Path(other.path).exists()
            assert any(entry.path == other.path and not entry.can_recycle for entry in window.inventory.graveyard)
            window.old_table.item(names(window).index("notes.dat"), 0).setCheckState(Qt.Unchecked)
            window.old_table.item(names(window).index("crash_dump.log"), 0).setCheckState(Qt.Checked)
            window._protect_old_selected()
            settle()
            assert any("crash_dump.log" in str(rule) for rule in window.settings["never_touch"]), window.settings["never_touch"]
            assert not window.old_delete.isEnabled(), "Protected files cannot be recycled"
            assert Path(log.path).exists()
            window.old_table.item(names(window).index("crash_dump.log"), 0).setCheckState(Qt.Unchecked)

            # Recycle Bin: declined, then approved with a disposable shell bin.
            window.old_table.item(names(window).index("family-photos.zip"), 0).setCheckState(Qt.Checked)
            settle()
            assert window.old_delete.isEnabled()
            window._recycle_old_selected()
            assert Path(archive.path).exists(), "Declined confirmation must not change anything"
            confirm.return_value = True
            shell_bin = root / "DisposableShell"
            shell_bin.mkdir()
            with patch("cleanup_actions.recycle_file", side_effect=lambda path: shutil.move(str(path), str(shell_bin / Path(path).name))), \
                 patch("cleanup_actions.register_recycle", return_value="test"), patch("cleanup_actions.log_event"):
                window._recycle_old_selected()
                wait_for(lambda: not window.cleaning and not window.workers)
            assert not Path(archive.path).exists() and (shell_bin / "family-photos.zip").exists()
            for survivor in everything:
                if survivor is not archive:
                    assert Path(survivor.path).exists(), survivor.path

            # The page survives leaving and returning, and narrower windows still fit.
            window.navigate("Overview")
            settle()
            window.navigate("Old Files")
            settle()
            for width, height in ((1280, 720), (1440, 900), (960, 650)):
                window.resize(width, height)
                settle()
                assert window.page.horizontalScrollBar().maximum() == 0, (width, height)
                assert window.grab().save(str(args.output / f"old-files-page-{width}.png"))
            errors.assert_not_called()
            window.close()
            settle()
        after = tree_bytes(drive)
        removed = set(before) - set(after)
        assert removed == {str(Path(archive.path).relative_to(drive))}, removed
    print("PASS: Old Files page: single drive choice, exclusive age, scan-only metrics, all tabs, type filters, "
          "folder view (review only), evidence without safe-to-remove claims, Graveyard review, Protect, and a "
          "confirmed Recycle Bin move of exactly the selected file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
