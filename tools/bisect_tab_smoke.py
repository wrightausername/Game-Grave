"""Native Qt check of Mods > Bisect: the tab, the clue fields, a whole search against a disposable Mod Organizer 2 fixture
(test profile built as a copy, the real profile and every mod file untouched), the result, and a saved report."""
from __future__ import annotations

import argparse
import hashlib
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
    from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QPushButton
    from core import default_settings
    from gg_desktop import bisect_clues as clues_mod
    from gg_desktop.app import CrimsonWindow
    from tests.test_mods_functionality import mo2_fixture

    app = QApplication.instance() or QApplication([])

    def settle():
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()

    def wait_for(predicate, what="Bisect did not finish its task"):
        deadline = time.monotonic() + 30
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
            time.sleep(.004)
        assert predicate(), what
        settle()

    def tree_bytes(folder, skip=()):
        return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(folder.rglob("*")) if p.is_file() and not any(s in p.parts for s in skip)}

    def buttons(window):
        return {b.text(): b for b in window.mod_details.findChildren(QPushButton)}

    def press(window, text):
        found = buttons(window)
        assert text in found, (text, sorted(found))
        assert found[text].isEnabled(), text + " is disabled"
        found[text].click()
        settle()
        wait_for(lambda: not window.workers)
        settle()

    def details_text(window):
        return " ".join(w.text() for w in window.mod_details.findChildren(QLabel))

    with tempfile.TemporaryDirectory(prefix="GG-bisect-tab-") as temp:
        root = Path(temp)
        inventory, storage, profiles, ini = mo2_fixture(root)
        manager = ini.parent
        before = tree_bytes(manager)
        settings = default_settings()
        settings["mods_view"] = "advanced"  # this check covers the detailed view
        fake_clues = clues_mod.Clues(hits={}, reports_read=3, notes=("Crash reports were read for the smoke test.",))
        with patch("gg_desktop.app.load_settings", side_effect=lambda: dict(settings)), \
             patch("gg_desktop.ready_room_services.config_dir", return_value=root / "Preferences"), \
             patch("core.config_dir", return_value=root / "Config"), \
             patch("gg_desktop.mods_page.save_settings"), \
             patch("gg_desktop.bisect_tab.collect_reports", return_value=(fake_clues, 3)), \
             patch.object(CrimsonWindow, "info") as info, \
             patch.object(CrimsonWindow, "error") as errors, \
             patch.object(CrimsonWindow, "confirm", return_value=True), \
             patch.object(CrimsonWindow, "start_scan"):
            window = CrimsonWindow()
            window.settings = dict(window.settings, mods_view="advanced")  # this check covers the detailed view
            window.resize(1280, 790)
            window.show()
            window.inventory = inventory
            window.settings = dict(settings)
            window.navigate("Mods")
            wait_for(lambda: not window.workers and window.page.mods.report is not None)

            # The seventh tab exists and opens with the profile choice visible.
            assert "Bisect" in window.mod_tabs.buttons
            window.mod_tabs.buttons["Bisect"].click()
            settle()
            assert window._mod_tab == "Bisect" and window.mod_profile.isVisible()
            index = window.mod_profile.findText("Default", Qt.MatchStartsWith)
            assert index >= 0
            window.mod_profile.setCurrentIndex(index)
            settle()
            from gg_desktop import bisect_tab
            model = bisect_tab.model_for(window)
            wait_for(lambda: not model.loading and model.units, "Mods in the profile were not read")
            headers = [window.mod_table.horizontalHeaderItem(i).text() for i in range(window.mod_table.columnCount())]
            assert headers[1:] == ["Mod", "Added", "Status", "Why look here"], headers
            rows = window.mod_table.rowCount()
            assert rows >= 2, rows
            statuses = {window.mod_table.item(i, 3).text() for i in range(rows)}
            assert statuses == {"Starts on"}, statuses
            assert "Your own profile is never changed" in details_text(window)
            assert {"Start Finding", "Read Crash Reports", "Pick A Downloaded Pack…"} <= set(buttons(window))
            assert window.grab().save(str(args.output / "bisect-setup-1280.png"))

            # Clues: typed dates are kept, a bad date blocks Start and says how to type it, ticked mods become the clue.
            fields = {e.accessibleName(): e for e in window.mod_details.findChildren(QLineEdit)}
            assert {"It last worked", "Crashes started"} <= set(fields), sorted(fields)
            fields["It last worked"].setText("whenever")
            settle()
            window._fill_mods()
            settle()
            assert "2 weeks ago" in details_text(window) and not buttons(window)["Start Finding"].isEnabled()
            fields = {e.accessibleName(): e for e in window.mod_details.findChildren(QLineEdit)}
            fields["It last worked"].setText("2 weeks ago")
            settle()
            window._fill_mods()
            settle()
            assert buttons(window)["Start Finding"].isEnabled()
            snow_row = next(i for i in range(rows) if window.mod_table.item(i, 1).text() == "Snow Textures")
            window.mod_table.item(snow_row, 0).setCheckState(Qt.Checked)
            press(window, "Use Checked Mods As The New Ones")
            assert len(model.hints) == 1, model.hints
            press(window, "Read Crash Reports")
            assert model.clues is not None and "3 read" in details_text(window), details_text(window)

            # Start: the first test must be built before any answer is accepted.
            press(window, "Start Finding")
            assert model.flow is not None and "Test 1" in details_text(window)
            assert not buttons(window)["It Crashed"].isEnabled()
            default_before = tree_bytes(profiles / "Default")
            copy = profiles / "GG Bisect - Default"
            assert not copy.exists(), "Nothing may be written until Build This Test is pressed"

            # A whole search: Snow Textures is the crashing mod; the answer follows what is written in the test profile.
            guard = 0
            while window.mod_details.findChildren(QPushButton) and "Build This Test" in buttons(window):
                guard += 1
                assert guard < 60, "search did not finish"
                press(window, "Build This Test")
                assert copy.is_dir() and (copy / "gg-bisect.json").is_file()
                lines = (copy / "modlist.txt").read_text(encoding="utf-8").splitlines()
                crashed = "+SnowTextures" in lines
                if guard == 1:
                    assert "+MountainTextures" in lines and "+SnowTextures" in lines
                    assert "-Framework" in lines and "-Disabled" in lines, "Mods switched off in the profile stay off"
                    assert "Ready." in details_text(window)
                    assert window.grab().save(str(args.output / "bisect-testing-1280.png"))
                press(window, "It Crashed" if crashed else "It Ran Fine")
            assert model.flow.done()
            text = details_text(window)
            assert "Snow Textures" in text and "changed nothing in your own profile" in text, text
            assert "safe" not in text.lower()
            statuses = {window.mod_table.item(i, 1).text(): window.mod_table.item(i, 3).text() for i in range(window.mod_table.rowCount())}
            assert statuses["Snow Textures"] == "Cause", statuses
            assert window.grab().save(str(args.output / "bisect-result-1280.png"))

            # The real profile and every manager file are byte-identical; only the copy was added.
            assert tree_bytes(profiles / "Default") == default_before
            assert tree_bytes(manager, skip=("GG Bisect - Default",)) == before, "Bisect must never change manager files"
            assert (copy / "GG-original-modlist.txt").read_text(encoding="utf-8") == \
                (profiles / "Default" / "modlist.txt").read_text(encoding="utf-8")

            # Report and starting over.
            press(window, "Save Report")
            saved = list((root / "Config" / "bisect" / "reports").glob("bisect-Default-*.txt"))
            assert len(saved) == 1 and "Snow Textures" in saved[0].read_text(encoding="utf-8")
            assert info.called
            press(window, "Copy Report")
            assert "Snow Textures" in QApplication.clipboard().text()
            press(window, "Start Over")
            assert model.flow is None and "Start Finding" in buttons(window)

            for width, height in ((960, 650), (1536, 864)):
                window.resize(width, height)
                settle()
                assert window.grab().save(str(args.output / f"bisect-setup-{width}.png"))
            errors.assert_not_called()
            window.close()
            settle()
    print("PASS: Mods > Bisect tab: clues, crash reports, a full search that builds only a copy of the profile, the result, the report and Start Over.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
