"""Native Qt check of the Undo Center page: filters with live counts, honest status, restore through the engine, hide without erasing."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timedelta
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import MagicMock, patch


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
    from PySide6.QtWidgets import QApplication, QFileDialog, QLabel, QPushButton, QWidget
    from core import default_settings
    from gg_desktop import undo_actions, undo_data, undo_insight, undo_page
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.undo_page import state_of

    app = QApplication.instance() or QApplication([])

    def settle():
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()

    def wait_for(predicate, what="Undo Center did not finish its task"):
        deadline = time.monotonic() + 40
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
            time.sleep(.004)
        assert predicate(), what
        settle()

    def idle(window):
        wait_for(lambda: not state_of(window).busy and not window.workers and not window.cleaning)

    def tree_bytes(folder):
        return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in folder.rglob("*") if p.is_file()}

    def names(window):
        return [e.name for e in state_of(window).rows]

    def pick(window, name):
        state = state_of(window)
        index = next(i for i, e in enumerate(state.shown) if e.name == name)
        window.undo_table.selectRow(index)
        settle()

    def tick(window, name, on=True):
        state = state_of(window)
        index = next(i for i, e in enumerate(state.shown) if e.name == name)
        window.undo_table.item(index, 0).setCheckState(Qt.Checked if on else Qt.Unchecked)
        settle()

    def detail_text(window):
        return " ".join([w.text() for w in window.undo_details.findChildren(QLabel)] +
                        [b.text() for b in window.undo_details.findChildren(QPushButton)])

    def button(window, text):
        return next(b for b in window.undo_details.findChildren(QPushButton) if b.text() == text)

    now = datetime.now().astimezone()

    def iso(days):
        return (now - timedelta(days=days)).isoformat(timespec="seconds")

    records = [
        {"id": "r1", "path": "C:\\Games\\Stash\\clip.mp4", "size": 5000, "time": iso(0.5), "action": "Graveyard",
         "state": "Available", "note": "Windows reports a matching Recycle Bin item."},
        {"id": "r2", "path": "C:\\Games\\Stash\\old.zip", "size": 2000, "time": iso(10), "action": "Old Files",
         "state": "Not checked", "note": "In Recycle Bin if Windows has not emptied it."},
        {"id": "r3", "path": "C:\\Games\\Stash\\pic.png", "size": 300, "time": iso(40), "action": "Captures",
         "state": "Restored", "note": "Restored to the original path through Windows Shell."},
        {"id": "r4", "path": "C:\\Games\\Cache\\a.bin", "size": 700, "time": iso(3), "action": "Other Storage",
         "state": "Needs review", "note": "A file already exists at the original path."},
    ]
    events = [
        {"date": iso(0.5), "kind": "Manual recycled", "details": "Graveyard file", "path": records[0]["path"],
         "size_bytes": 5000, "recovery_id": "r1", "session_id": "s1", "source": "Graveyard"},
        {"date": iso(10), "kind": "Manual recycled", "details": "Old File", "path": records[1]["path"],
         "size_bytes": 2000, "recovery_id": "r2", "session_id": "s2", "source": "Old Files"},
        {"date": iso(0.5), "kind": "Cleanup skipped", "details": "C:\\x\\f.tmp: Changed since scan", "path": "C:\\x\\f.tmp",
         "result": "Changed since scan", "session_id": "s1", "source": "Graveyard"},
        {"date": iso(40), "kind": "Restored from Recycle Bin", "details": records[2]["path"], "path": records[2]["path"]},
        {"date": iso(2), "kind": "Scan completed", "details": "3 games"},
        {"date": iso(4), "kind": "Scan failed", "details": "disk", "result": "Scan failed: disk"},
        {"date": iso(6), "kind": "Automation enabled", "details": "Weekly"},
        {"date": iso(8), "kind": "Steam uninstall opened", "details": "Cyberpunk 2077"},
        {"date": iso(9), "kind": "Cleanup started", "details": "internal"},
    ]

    with tempfile.TemporaryDirectory(prefix="GG-undo-page-") as temp:
        root = Path(temp)
        (root / "fixture.txt").write_text("untouched", encoding="utf-8")
        before = tree_bytes(root)
        settings = default_settings()
        saved = []

        def keep(updated):
            saved.append(dict(updated))

        engine = []

        def fake_check(rid):
            engine.append(("check", rid))
            if rid == "boom":
                raise ValueError("Recovery entry missing")
            return "AVAILABLE"

        def fake_restore(rid):
            engine.append(("restore", rid))
            next(r for r in records if r["id"] == rid)["state"] = "Restored"
            return "RESTORED"

        stack = ExitStack()
        for target, options in (
            ("gg_desktop.app.load_settings", dict(return_value=settings)),
            ("core.save_settings", dict(side_effect=keep)),
            ("gg_desktop.backend.save_settings", dict(side_effect=keep)),
            ("gg_desktop.backend.log_event", {}),
            ("gg_desktop.undo_page.save_settings", dict(side_effect=keep)),
            ("gg_desktop.undo_page.get_records", dict(side_effect=lambda: [dict(r) for r in records])),
            ("gg_desktop.undo_page.get_activity", dict(side_effect=lambda: [dict(e) for e in events])),
            ("gg_desktop.undo_page.check_restore", dict(side_effect=fake_check)),
            ("gg_desktop.undo_page.restore_recycled", dict(side_effect=fake_restore)),
            ("gg_desktop.recovery_screens.save_settings", dict(side_effect=keep)),
            ("gg_desktop.reference_library.save_settings", {}),
            ("gg_desktop.ready_room_services.config_dir", dict(return_value=root / "Preferences")),
            ("gg_desktop.game_artwork.artwork_dir", dict(return_value=root / "Artwork")),
            ("gg_desktop.game_artwork._request", dict(side_effect=AssertionError("No automatic network"))),
        ):
            stack.enter_context(patch(target, **options))
        info = stack.enter_context(patch.object(CrimsonWindow, "info"))
        errors = stack.enter_context(patch.object(CrimsonWindow, "error"))
        confirm = stack.enter_context(patch.object(CrimsonWindow, "confirm", return_value=False))
        opened = stack.enter_context(patch.object(CrimsonWindow, "_open_folder"))
        stack.enter_context(patch.object(CrimsonWindow, "_open_recycle_bin"))
        saver = stack.enter_context(patch.object(QFileDialog, "getSaveFileName", return_value=("", "")))
        with stack:
            window = CrimsonWindow()
            window.show()
            window.resize(1280, 720)
            window.navigate("Undo Center")
            settle()
            state = state_of(window)

            # Honest metrics: counts from the records, recycled bytes labelled as not freed, no reversibility percentage.
            entries = undo_data.build_entries(records, events)
            m = undo_insight.metrics(entries, set())
            assert len(state.entries) == len(entries) == 9, (len(state.entries), len(entries))
            strip = [v.text() for v in window.undo_metrics.values]
            assert strip[0] == str(m["total"]) and strip[1] == "4" and strip[3] == "1" and strip[4] == "1", strip
            assert strip[5] == "7.5 KB", strip
            captions = [c.text() for c in window.undo_metrics.captions]
            assert "Recycled Size" in captions and not any("Reversible" in c or "Reclaimed" in c for c in captions), captions
            assert window.undo_heading.text() == f"Cleanup History ({m['total']})"
            assert set(names(window)) >= {"clip.mp4", "old.zip", "pic.png", "a.bin"}
            assert window.grab().save(str(args.output / "undo-history-1280.png"))

            # Details say what Windows last reported, never a blanket promise.
            pick(window, "clip.mp4")
            text = detail_text(window)
            assert "Yes, Windows reported a matching item" in text and "Same Cleanup Run (2)" in text, text
            assert "safe" not in text.lower() and "100%" not in text and button(window, "Restore Item").isEnabled()
            pick(window, "old.zip")
            assert "Not checked yet" in detail_text(window)
            pick(window, "pic.png")
            assert "Already restored" in detail_text(window) and not button(window, "Restore Item").isEnabled()
            scan_row = next(e.name for e in state.shown if e.action == "Scan completed")
            pick(window, scan_row)
            assert "No recovery record" in detail_text(window) and not button(window, "Restore Item").isEnabled()
            assert not button(window, "Check Availability").isEnabled()
            assert not window.undo_restore_button.isEnabled()

            # Filters with live counts.
            window.undo_range_rows["Last 24 Hours"].button.click()
            settle()
            day_rows = names(window)
            assert set(day_rows) == {"clip.mp4", "f.tmp"}, day_rows
            assert window.undo_range_rows["All Time"].count.text() == str(m["total"])
            window.undo_range_rows["Custom Range"].button.click()
            settle()
            assert window.undo_custom.isVisible()
            window.undo_range_rows["All Time"].button.click()
            settle()
            assert len(state.rows) == m["total"]
            window.undo_type_rows["Scans"].box.setChecked(False)
            settle()
            assert all(e.category != "Scans" for e in state.rows) and len(state.rows) == m["total"] - 2
            assert window.undo_type_rows["Scans"].count.text() == "2"
            window.undo_type_rows["Scans"].box.setChecked(True)
            settle()
            state.sources = {"Graveyard"}
            undo_page.fill(window)
            settle()
            assert {e.source for e in state.rows} == {"Graveyard"}, state.rows
            undo_page.clear_filters(window)
            settle()
            assert len(state.rows) == m["total"] and not state.sources
            window.undo_search.setText("clip")
            settle()
            assert names(window) == ["clip.mp4"], names(window)
            window.undo_search.setText("")
            settle()
            window.undo_sort.setCurrentText("Size (Largest)")
            settle()
            assert state.rows[0].name == "clip.mp4"
            window.undo_sort.setCurrentText("Date (Newest)")
            window.undo_view_list.click()
            settle()
            assert window.undo_table.rowHeight(0) == 30
            window.undo_view_grid.click()
            settle()
            assert window.undo_table.rowHeight(0) == 44
            assert window.grab().save(str(args.output / "undo-filters-1280.png"))

            # Select This Run checks only that run's shown rows.
            pick(window, "clip.mp4")
            button(window, "Select This Run").click()
            settle()
            assert {e.key for e in state.entries if e.key in state.checked} == {"recovery:r1", "audit:2"}, state.checked
            window.undo_select_all.setChecked(False)
            undo_page.select_visible(window, False)
            settle()
            assert not state.checked

            # Declining restores nothing. Restore asks Windows first, then the engine restores one matching item.
            pick(window, "clip.mp4")
            window.undo_restore_button.click()
            settle()
            assert not engine, "Declining the confirmation must not touch the engine"
            confirm.return_value = True
            window.undo_restore_button.click()
            idle(window)
            confirm.return_value = False
            assert engine == [("check", "r1"), ("restore", "r1")], engine
            assert any("1 of 1 restored." in str(c.args[1]) for c in info.call_args_list), info.call_args_list
            assert next(e for e in state.entries if e.key == "recovery:r1").state == "Restored"
            assert undo_page.live(window) and not window.cleaning and not state.busy
            engine.clear()

            # A failing record is reported and the page recovers.
            records.append({"id": "boom", "path": "C:\\Games\\Stash\\gone.dat", "size": 10, "time": iso(1), "action": "Old Files",
                            "state": "Not checked", "note": "n"})
            undo_page.reload(window)
            settle()
            pick(window, "gone.dat")
            confirm.return_value = True
            window.undo_restore_button.click()
            idle(window)
            confirm.return_value = False
            assert any("Recovery entry missing" in str(c.args[1]) for c in info.call_args_list)
            errors.assert_not_called()

            # Check Availability is a read of Windows, not a restore.
            engine.clear()
            pick(window, "old.zip")
            button(window, "Check Availability").click()
            idle(window)
            assert engine == [("check", "r2")], engine

            # Hide only hides: nothing is edited or deleted.
            total_before = len(state.rows)
            pick(window, "old.zip")
            window.undo_hide_button.click()
            settle()
            assert saved and "recovery:r2" in saved[-1]["undo_hidden"] and "old.zip" not in names(window)
            assert len(state.rows) == total_before - 1 and window.undo_hidden_row.name.text() == "Show hidden rows (1)"
            assert any(r["id"] == "r2" for r in records), "The recovery record itself must remain"
            window.undo_hidden_row.box.setChecked(True)
            settle()
            assert "old.zip" in names(window)
            pick(window, "old.zip")
            undo_page.unhide_selected(window)
            settle()
            assert saved[-1]["undo_hidden"] == [] and "old.zip" in names(window)
            window.undo_hidden_row.box.setChecked(False)
            settle()

            # Open Location, copy and export change nothing.
            pick(window, "clip.mp4")
            undo_page.open_location(window)
            opened.assert_called_with("C:\\Games\\Stash")
            tick(window, "clip.mp4")
            undo_page.copy_paths(window)
            assert "clip.mp4" in app.clipboard().text()
            target = root / "export.csv"
            saver.return_value = (str(target), "CSV (*.csv)")
            undo_page.export_csv(window)
            text = target.read_text(encoding="utf-8")
            assert text.startswith("Action,Item,Path") and "clip.mp4" in text
            target.unlink()
            assert tree_bytes(root) == before, "Nothing may change on disk"

            # Layout at the supported sizes.
            for width, height in ((1280, 720), (1440, 900), (960, 650)):
                window.resize(width, height)
                settle()
                QTest.qWait(40)
                settle()
                if window.page.horizontalScrollBar().maximum() != 0:
                    wide = sorted(((w.minimumSizeHint().width(), type(w).__name__, w.objectName())
                                   for w in window.page.findChildren(QWidget)), reverse=True)[:12]
                    print("Horizontal overflow at", (width, height), "viewport", window.page.viewport().width(), "widest:", wide)
                assert window.page.horizontalScrollBar().maximum() == 0, (width, height)
                if height >= 720:
                    bottom = window.undo_restore_button.mapTo(window, window.undo_restore_button.rect().bottomLeft()).y()
                    assert bottom <= window.height(), ("Restore Selected is cut off", (width, height), bottom)
                assert window.grab().save(str(args.output / f"undo-page-{width}.png"))
            errors.assert_not_called()
            window.close()
            settle()
        assert tree_bytes(root) == before
    print("PASS: Undo Center page: honest metrics and status, live filter counts, restore only through the engine after a fresh check, "
          "failures reported, hide without editing any record, and no file changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
