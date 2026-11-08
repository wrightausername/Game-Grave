"""Native Qt check of the Mods page: real status, all six tabs, bulk actions, sources, no file changes."""
from __future__ import annotations

import argparse
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
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLabel
    from core import default_settings
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.reference_widgets import MetricStrip
    from gg_desktop import mods_page
    from tests.test_mods_functionality import mo2_fixture

    app = QApplication.instance() or QApplication([])

    def settle():
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()

    def wait_for(predicate, what="Mods did not finish its task"):
        deadline = time.monotonic() + 20
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
            time.sleep(.004)
        assert predicate(), what
        settle()

    def tree_bytes(folder):
        return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in folder.rglob("*") if p.is_file()}

    def open_tab(window, name):
        window.mod_tabs.buttons[name].click()
        settle()
        assert window._mod_tab == name, name

    def headers(window):
        table = window.mod_table
        return [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())]

    def row_of(window, name):
        return next(i for i, view in enumerate(window._shown_mods) if view.name == name)

    with tempfile.TemporaryDirectory(prefix="GG-mods-page-") as temp:
        root = Path(temp)
        inventory, storage, profiles, ini = mo2_fixture(root)
        (storage / "MountainTextures" / "meta.ini").write_text("[General]\nversion=2.0\nnewestVersion=2.5\n", encoding="utf-8")
        extra = root / "ExtraSource"
        extra.mkdir()
        exports = root / "Exports"
        exports.mkdir()
        before = tree_bytes(ini.parent)
        settings = default_settings()
        settings["mod_extra_roots"] = [str(extra)]
        saved = []
        with patch("gg_desktop.app.load_settings", side_effect=lambda: dict(settings)), \
             patch("gg_desktop.ready_room_services.config_dir", return_value=root / "Preferences"), \
             patch("gg_desktop.mods_page.save_settings", side_effect=saved.append), \
             patch.object(CrimsonWindow, "info") as info, \
             patch.object(CrimsonWindow, "error") as errors, \
             patch.object(CrimsonWindow, "confirm", return_value=True), \
             patch.object(CrimsonWindow, "start_scan") as scan:
            window = CrimsonWindow()
            window.resize(1280, 790)
            window.show()
            window.inventory = inventory
            window.settings = dict(settings)
            window.navigate("Mods")
            wait_for(lambda: not window.workers and window.page.mods.report is not None)
            wait_for(lambda: window._mod_updates_scanned and not window.workers, "Update evidence never finished")
            control = window.page.mods

            # Library: layout columns unchanged, status is real, metrics are real.
            assert window.mod_table.columnCount() == 6
            assert not window.mod_profile.isVisible()
            statuses = {view.name: window.mod_table.item(i, 5).text() for i, view in enumerate(window._shown_mods)}
            assert statuses["Mountain Textures"] == "Enabled", statuses
            assert statuses["Framework"] == "Disabled", statuses
            strip = window.page.findChild(MetricStrip)
            assert int(strip.values[0].text()) >= 4, strip.values[0].text()
            assert strip.values[2].text() == "1", "Outdated must come from MO2's saved newestVersion"
            assert int(strip.values[3].text()) >= 2
            assert window.grab().save(str(args.output / "mods-page-library-1280.png"))

            # Details show real load order position and update evidence.
            window.mod_table.selectRow(row_of(window, "Mountain Textures"))
            settle()
            labels = " ".join(w.text() for w in window.mod_details.findChildren(QLabel))
            assert "(relative)" in labels and "2.5" in labels, labels

            # Sorting: every option reorders the Library, header clicks toggle direction, Size and Modified are shown.
            from gg_desktop import mods_sort
            assert [window.mod_table.horizontalHeaderItem(i).text() for i in (4, 6)] == ["Size", "Modified"]
            def library_names():
                return [window.mod_table.item(i, 1).text() for i in range(window.mod_table.rowCount())]
            for option in mods_sort.OPTIONS:
                window.mod_sort.setCurrentText(option)
                settle()
                expected = [v.name for v in mods_sort.sort_views(window._mod_views, option)
                            if v in [x for x in window._mod_views]]
                shown = library_names()
                assert shown == expected[:len(shown)], (option, shown, expected)
            window.mod_sort.setCurrentText("Name (A–Z)")
            settle()
            first_az = library_names()
            window.mod_table.horizontalHeader().sectionClicked.emit(1)
            settle()
            assert window.mod_sort.currentText() == "Name (Z–A)" and library_names() == sorted(first_az, key=str.casefold, reverse=True)
            window.mod_table.horizontalHeader().sectionClicked.emit(4)
            settle()
            assert window.mod_sort.currentText() == "Size (Largest)"
            window.mod_table.horizontalHeader().sectionClicked.emit(6)
            settle()
            assert window.mod_sort.currentText() == "Date (Newest)"
            assert window.grab().save(str(args.output / "mods-page-sorted-1280.png"))
            window.mod_sort.setCurrentText("Name (A–Z)")
            settle()

            # Every in-page tab fills from real data.
            open_tab(window, "Mod Radar")
            assert window.mod_table.rowCount() >= 3 and headers(window)[1].casefold() == "source"
            sources = [window.mod_table.item(i, 1).text() for i in range(window.mod_table.rowCount())]
            assert "ExtraSource" in sources
            assert window.grab().save(str(args.output / "mods-page-radar-1280.png"))

            open_tab(window, "Load Order")
            assert window.mod_profile.isVisible()
            default_index = window.mod_profile.findText("Default", Qt.MatchStartsWith)
            assert default_index >= 0
            window.mod_profile.setCurrentIndex(default_index)
            settle()
            assert window.mod_table.rowCount() == 5, (window.mod_table.rowCount(), window.mod_profile.currentText(), window.mod_notice.text())
            assert window.mod_table.item(0, 1).text() == "MissingFolder" and window.mod_table.item(0, 2).text() == "1"
            assert window.grab().save(str(args.output / "mods-page-load-order-1280.png"))

            open_tab(window, "Profiles")
            assert window.mod_table.rowCount() == 2 and not window.mod_profile.isVisible()
            window.mod_table.selectRow(0)
            settle()
            assert window.grab().save(str(args.output / "mods-page-profiles-1280.png"))

            open_tab(window, "Conflicts")
            assert window.mod_profile.isVisible() and window.mod_profile.currentData() == ""
            assert window.mod_table.rowCount() == len(control.report.findings) > 0
            window.mod_table.selectRow(0)
            settle()
            assert window.grab().save(str(args.output / "mods-page-conflicts-1280.png"))

            open_tab(window, "Cleanup")
            settle()
            assert window.grab().save(str(args.output / "mods-page-cleanup-1280.png"))

            open_tab(window, "Library")
            assert window.mod_table.columnCount() == 6 and window.mod_table.rowCount() >= 5

            # Bulk actions on checked rows: copy and export never touch mod folders.
            for name in ("Mountain Textures", "Snow Textures"):
                window.mod_table.item(row_of(window, name), 0).setCheckState(Qt.Checked)
            picked = mods_page.targets(window, control)
            assert {e.name for e in picked} == {"Mountain Textures", "Snow Textures"}
            mods_page.copy_paths(window, picked)
            assert set(QApplication.clipboard().text().splitlines()) == {e.path for e in picked}
            menu = mods_page.build_menu(window, control, window.page)
            labels = {a.text(): a for a in menu.actions() if a.text()}
            assert labels["Check conflicts"].isEnabled() and labels["Export conflict report…"].isEnabled()
            assert any(text.startswith("Copy paths") for text in labels)
            menu.deleteLater()
            blocked = storage / "Selected.json"
            with patch("gg_desktop.mods_page.QFileDialog.getSaveFileName", return_value=(str(blocked), "")):
                mods_page.export_selected(window, control, picked)
            assert not blocked.exists() and errors.call_count == 1, "Export inside mod storage must be refused"
            errors.reset_mock()
            good = exports / "Selected.json"
            with patch("gg_desktop.mods_page.QFileDialog.getSaveFileName", return_value=(str(good), "")):
                mods_page.export_selected(window, control, picked)
            payload = json.loads(good.read_text(encoding="utf-8"))
            assert payload["count"] == 2 and "unverified" in payload["scope"]
            assert {m["status"] for m in payload["mods"]} == {"Enabled"}

            # Added sources can be removed; the folder itself stays.
            open_tab(window, "Mod Radar")
            window.mod_table.selectRow(next(i for i in range(window.mod_table.rowCount())
                                            if window.mod_table.item(i, 1).text() == "ExtraSource"))
            settle()
            scan.reset_mock()
            mods_page.remove_source(window, str(extra))
            assert saved and saved[-1]["mod_extra_roots"] == [] and extra.exists()
            scan.assert_called_once()

            # Busy state: Check conflicts disables itself while running and finishes.
            open_tab(window, "Conflicts")
            control.check_conflicts()
            settle()
            wait_for(lambda: not control.busy and not window.workers)

            for width, height in ((960, 650), (1536, 864)):
                window.resize(width, height)
                for tab in ("Library", "Conflicts", "Load Order"):
                    open_tab(window, tab)
                    assert window.grab().save(str(args.output / f"mods-page-{tab.lower().replace(' ', '-')}-{width}.png"))

            assert tree_bytes(ini.parent) == before, "Mods work must never change manager files"
            errors.assert_not_called()
            window.close()
            settle()
    print("PASS: Mods status, metrics, six in-page tabs, load order, profiles, conflicts, cleanup, "
          "checked-row copy/export with destination guard, source removal and untouched manager files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
