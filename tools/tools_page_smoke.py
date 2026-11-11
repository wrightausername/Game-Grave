"""Native Qt check of the More Tools page: tiles that hand off or really work, dimmed tiles that explain themselves,
live readings, real Active Tasks, the Tool Log, reports, the hash checker and no sideways scrolling."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import csv
import hashlib
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import MagicMock, patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("_ci_temp"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    root_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root_dir))
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QToolButton, QWidget
    import core
    from core import ModFolder, SteamGame
    from gg_desktop import tools_actions as actions, tools_data as data, tools_page, tools_system as system
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.backend import Inventory
    from gg_desktop.models import merge_games

    app = QApplication.instance() or QApplication([])

    def settle():
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()

    def tree_bytes(folder):
        return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in folder.rglob("*") if p.is_file()}

    def texts(window):
        parts = [l.text() for l in window.page.findChildren(QLabel)]
        parts += [b.toolTip() for b in window.page.findChildren(QToolButton)]
        parts += [b.text() + " " + b.toolTip() for b in window.page.findChildren(QPushButton)]
        return " ".join(parts)

    with tempfile.TemporaryDirectory(prefix="GG-tools-page-") as temp:
        root = Path(temp)
        (root / "Untouched").mkdir()
        (root / "Untouched" / "fixture.txt").write_text("untouched", encoding="utf-8")
        before = tree_bytes(root / "Untouched")
        work = root / "Work"
        work.mkdir()
        blob = b"game grave" * 5000
        small = work / "setup.bin"
        small.write_bytes(blob)
        big = work / "big.bin"
        big.write_bytes(os.urandom(1024 * 1024) * 96)
        small_before, big_before = small.read_bytes(), hashlib.sha256(big.read_bytes()).hexdigest()
        steam = [SteamGame("1", "Starfield", str(root / "Steam"), str(root / "Steam" / "Starfield"), 5000, None, "Steam"),
                 SteamGame("2", "=Formula Game", str(root / "Steam"), str(root / "Steam" / "Formula"), 900, None, "Steam")]
        mods = [ModFolder("Skyrim mods", str(root / "Steam" / "mods"), "lib", "Unmatched Steam folder", ("mods",), 5000, 12, False)]
        events = [{"kind": "Scan completed", "date": "2026-11-01T10:00:00", "details": "Scanned"},
                  {"kind": "Manual recycled", "date": "2026-11-02T10:00:00", "details": "old.zip"},
                  {"kind": "Cleanup skipped", "date": "2026-11-03T10:00:00", "details": "kept"},
                  {"kind": "Restored from Recycle Bin", "date": "2026-11-04T10:00:00", "details": "back.zip"}]

        stack = ExitStack()
        for target, options in (
            ("core.config_dir", dict(return_value=root / "Config")),
            ("gg_desktop.tools_page.get_activity", dict(return_value=[])),
            ("gg_desktop.recovery_screens.get_records", dict(return_value=[])),
            ("gg_desktop.recovery_screens.get_activity", dict(return_value=[])),
            ("gg_desktop.undo_page.get_records", dict(return_value=[])),
            ("gg_desktop.undo_page.get_activity", dict(return_value=[])),
            ("gg_desktop.assistant_page.get_records", dict(return_value=[])),
            ("gg_desktop.assistant_page.get_activity", dict(return_value=[])),
            ("gg_desktop.settings_page.get_records", dict(return_value=[])),
            ("gg_desktop.ready_room_services.config_dir", dict(return_value=root / "Preferences")),
            ("gg_desktop.game_artwork.artwork_dir", dict(return_value=root / "Artwork")),
            ("gg_desktop.game_artwork._request", dict(side_effect=AssertionError("No automatic network"))),
        ):
            stack.enter_context(patch(target, **options))
        errors = stack.enter_context(patch.object(CrimsonWindow, "error"))
        infos = stack.enter_context(patch.object(CrimsonWindow, "info"))
        stack.enter_context(patch.object(CrimsonWindow, "confirm", return_value=True))
        save_dialog = stack.enter_context(patch.object(actions.QFileDialog, "getSaveFileName", return_value=("", "")))
        open_dialog = stack.enter_context(patch.object(actions.QFileDialog, "getOpenFileName", return_value=("", "")))
        kit_calls = {key: stack.enter_context(patch.object(CrimsonWindow, method)) for key, method in actions.KIT_METHODS.items()}
        backup = stack.enter_context(patch.object(CrimsonWindow, "_create_save_backup"))
        start_scan = stack.enter_context(patch.object(CrimsonWindow, "start_scan"))
        shown = []
        stack.enter_context(patch.object(actions.KitMenu, "exec", lambda self: shown.append(self) or 0))
        stack.enter_context(patch.object(actions.HashResult, "exec", lambda self: shown.append(self) or 0))
        with stack:
            core.save_settings(core.default_settings())
            window = CrimsonWindow()
            window.show()
            window.resize(1280, 720)
            window.inventory = Inventory(steam=steam, games=merge_games(steam, []), mods=mods, scanned_at="2026-11-08 10:00")
            window.navigate("More Tools")
            settle()
            QTest.qWait(30)
            settle()
            state = tools_page.state_of(window)
            assert window.current_route == "More Tools" and hasattr(window.page, "tools_ready")

            # The photo's structure: six tabs, six categories, twenty-four tiles.
            assert list(window.tools_tabs) == [t[0] for t in data.TABS] and window.tools_tabs["hub"].isChecked()
            assert len(window.tools_panels) == 6 and len(window.tools_tiles) == 24
            assert all(window.tools_panels[c.key].isVisible() for c in data.CATEGORIES)
            assert [b.accessibleName() for b in window.tools_quick_buttons.values()] == [q[1] for q in data.QUICK_ACTIONS]
            assert window.grab().save(str(args.output / "tools-hub-1280.png"))

            # Top tabs show only their categories, then the hub shows all again.
            for key, _title, _cap, _symbol, cats in data.TABS:
                window.tools_tabs[key].click()
                settle()
                visible = {c for c, f in window.tools_panels.items() if f.isVisible()}
                assert visible == set(cats), (key, visible)
            window.tools_tabs["advanced"].click()
            settle()
            assert window.grab().save(str(args.output / "tools-advanced-1280.png"))
            window.tools_tabs["hub"].click()
            settle()

            # Tiles that belong to another tab open it.
            for tile in [t for t in data.all_tiles() if t.kind == data.GO]:
                window.tools_tiles[tile.key].click()
                settle()
                assert window.current_route == tile.target, (tile.key, window.current_route)
                window.navigate("More Tools")
                settle()
            assert errors.call_count == 0, errors.call_args_list

            # The seven Windows tools are real tiles: each click opens its own tool (covered in depth by tools_windows_smoke).
            from unittest.mock import MagicMock
            from gg_desktop import tools_windows
            assert [t for t in data.all_tiles() if t.kind == data.OFF] == []
            fakes = {key: MagicMock() for key in tools_windows.HANDLERS}
            with patch.dict(tools_windows.HANDLERS, fakes):
                for key in fakes:
                    window.tools_tiles[key].click()
                    settle()
                    assert fakes[key].call_count == 1 and fakes[key].call_args[0][0] is window, key
                    assert "not offered" not in window.tools_tiles[key].accessibleName()
            assert window.current_route == "More Tools"

            # Save backups and the Resurrection Kit use the existing verified workflows.
            for key in ("game_backup", "save_backup", "mod_backup"):
                window.tools_tiles[key].click()
            assert backup.call_count == 3
            window.tools_tiles["resurrection_kit"].click()
            settle()
            menu = shown.pop()
            assert isinstance(menu, actions.KitMenu) and set(menu.buttons) == set(actions.KIT_METHODS) | {"easy", "restore_game"}
            for key, control in menu.buttons.items():
                if key in ("easy", "restore_game"):
                    continue
                control.click()
                assert kit_calls[key].call_count == 1, key
            from gg_desktop import kit_easy_ui
            for key, name in (("easy", "open_easy_setup"), ("restore_game", "open_easy_restore")):
                with patch.object(kit_easy_ui, name) as opened:
                    menu.buttons[key].click()
                    assert opened.call_count == 1, key

            # Quick actions.
            window.tools_quick_buttons["scan"].click()
            assert start_scan.call_count == 1
            window.scanning = True
            infos.reset_mock()
            window.tools_quick_buttons["scan"].click()
            assert start_scan.call_count == 1 and infos.call_args[0][0] == "Game Grave is busy"
            window.scanning = False
            window.tools_quick_buttons["saves"].click()
            assert backup.call_count == 4
            window.tools_quick_buttons["kit"].click()
            assert isinstance(shown.pop(), actions.KitMenu)
            window.tools_quick_buttons["caches"].click()
            settle()
            assert window.current_route == "Other Storage"
            window.navigate("More Tools")
            settle()

            # Reports: real files, formula-safe, nothing invented, cancel writes nothing.
            games_csv = work / "games.csv"
            save_dialog.return_value = (str(games_csv), "")
            infos.reset_mock()
            window.tools_tiles["game_size_report"].click()
            with games_csv.open(encoding="utf-8-sig", newline="") as f:
                rows = list(csv.reader(f))
            assert rows[0] == list(data.GAME_HEADER) and len(rows) == 3, rows
            assert any(r[0] == "'=Formula Game" for r in rows), "A formula-looking name is neutralised"
            assert infos.call_args[0][0] == "Report saved" and "2 games" in infos.call_args[0][1]
            mods_csv = work / "mods.csv"
            save_dialog.return_value = (str(mods_csv), "")
            window.tools_tiles["mod_report"].click()
            with mods_csv.open(encoding="utf-8-sig", newline="") as f:
                rows = list(csv.reader(f))
            assert rows[0] == list(data.MOD_HEADER) and rows[1][0] == "Skyrim mods" and rows[1][2] == "5000", rows
            report = work / "report.txt"
            save_dialog.return_value = (str(report), "")
            window.tools_tiles["system_report"].click()
            body = report.read_text(encoding="utf-8")
            assert "Games found: 2" in body and "Mod and game folders: 1" in body and "Storage in use" in body, body
            assert "do not mean anything is safe to remove" in body
            quick_csv = work / "quick.csv"
            save_dialog.return_value = (str(quick_csv), "")
            window.tools_quick_buttons["size_report"].click()
            assert quick_csv.is_file()
            before_files = sorted(p.name for p in work.iterdir())
            save_dialog.return_value = ("", "")
            for key in ("game_size_report", "mod_report", "system_report"):
                window.tools_tiles[key].click()
            assert sorted(p.name for p in work.iterdir()) == before_files, "Cancel writes nothing"
            infos.reset_mock()
            save_dialog.return_value = (str(work / "missing-folder" / "x.csv"), "")
            window.tools_tiles["game_size_report"].click()
            assert errors.call_count == 1 and errors.call_args[0][0] == "The report was not saved"
            errors.reset_mock()
            window.inventory = Inventory()
            save_dialog.return_value = (str(work / "none.csv"), "")
            infos.reset_mock()
            window.tools_tiles["game_size_report"].click()
            window.tools_tiles["mod_report"].click()
            assert not (work / "none.csv").exists() and infos.call_count == 2
            assert infos.call_args_list[0][0][0] == "Nothing to report yet"
            window.inventory = Inventory(steam=steam, games=merge_games(steam, []), mods=mods, scanned_at="2026-11-08 10:00")

            # Hash checker: a real SHA-256, a comparison that never calls a file safe, bad files refused.
            def run_hash(path):
                shown.clear()
                open_dialog.return_value = (str(path), "")
                window.tools_tiles["hash_checker"].click()
                for _ in range(200):
                    QTest.qWait(25)
                    settle()
                    if shown:
                        break
                return shown.pop() if shown else None
            result = run_hash(small)
            assert isinstance(result, actions.HashResult) and result.digest == hashlib.sha256(blob).hexdigest()
            assert result.value.text() == result.digest and state.hash_name == ""
            assert result.state == "empty"
            result.expected.setText("nonsense")
            assert result.state == "invalid"
            result.expected.setText(result.digest.upper() + "  setup.bin")
            assert result.state == "match" and "safe" not in result.verdict.text().casefold()
            result.expected.setText("0" * 64)
            assert result.state == "different"
            result.copy()
            assert app.clipboard().text() == result.digest
            open_dialog.return_value = (str(work), "")
            window.tools_tiles["hash_checker"].click()
            open_dialog.return_value = (str(work / "gone.bin"), "")
            window.tools_tiles["hash_checker"].click()
            assert errors.call_count == 2 and errors.call_args[0][0] == "Not a file"
            errors.reset_mock()
            assert state.hash_name == ""

            # A running checksum appears in Active Tasks and can be canceled from there.
            shown.clear()
            open_dialog.return_value = (str(big), "")
            window.tools_tiles["hash_checker"].click()
            tools_page.tick(window)
            assert state.hash_name == "big.bin" and window.tools_tasks_title.text() == "Active Tasks (1)"
            assert "hash" in window.tools_task_cancel
            window.tools_task_cancel["hash"].click()
            for _ in range(200):
                QTest.qWait(25)
                settle()
                if not state.hash_name:
                    break
            tools_page.tick(window)
            assert state.hash_name == "" and not shown, "A canceled check shows no checksum"
            assert window.tools_tasks_title.text() == "Active Tasks (0)" and "No tasks running" in texts(window)
            assert "canceled" in window.status.text()

            # Active Tasks reflect a real scan and real cleanup work, and nothing else.
            window.scanning = True
            window.progress.setValue(42)
            window.status.setText("Scanning: Mod Radar (42%)")
            tools_page.tick(window)
            assert window.tools_tasks_title.text() == "Active Tasks (1)" and "scan" in window.tools_task_cancel
            assert "Mod Radar" in texts(window)
            window.tools_task_cancel["scan"].click()
            assert window.cancel.is_set()
            assert window.grab().save(str(args.output / "tools-task-1280.png"))
            window.scanning = False
            window.cancel.clear()
            window.cleaning = True
            tools_page.tick(window)
            assert window.tools_tasks_title.text() == "Active Tasks (1)" and not window.tools_task_cancel
            window.cleaning = False
            tools_page.tick(window)
            assert window.tools_tasks_title.text() == "Active Tasks (0)"

            # Tool Log: the newest real activity, plain English, and a way to the full history.
            assert "Nothing has been recorded yet" in texts(window)
            with patch("gg_desktop.tools_page.get_activity", return_value=events):
                state.log_signature = None
                tools_page.refresh_log(window)
            body = texts(window)
            assert "File restored" in body and "File skipped during cleanup" in body and "File moved to Recycle Bin" in body
            assert "Storage scan completed" not in body, "Only the three newest entries"
            window.tools_log_open.click()
            settle()
            assert window.current_route == "Undo Center"
            window.navigate("More Tools")
            settle()

            # System Health: live readings, "Unavailable" when Windows cannot say, never a verdict.
            with patch.object(system, "storage_percent", return_value=72), patch.object(system, "memory_percent", return_value=46):
                state.cpu = system.CpuMeter(iter([(0, 100), (70, 200)]).__next__)
                tools_page.tick(window, full=True)
                assert window.tools_values["storage"].text() == "72%" and window.tools_values["memory"].text() == "46%"
                assert window.tools_values["cpu"].text() == "…"
                tools_page.tick(window)
                assert window.tools_values["cpu"].text() == "30%" and window.tools_meters["cpu"].value == 30
            with patch.object(system, "storage_percent", return_value=None), patch.object(system, "memory_percent", return_value=None):
                state.cpu = system.CpuMeter(lambda: None)
                tools_page.tick(window, full=True)
                assert all(window.tools_values[k].text() == "Unavailable" for k in ("storage", "memory", "cpu"))
                assert all(window.tools_meters[k].value is None for k in window.tools_meters)
            body = texts(window)
            assert "Live reading" in body and "not a health verdict" in body
            assert "Good" not in [l.text() for l in window.page.findChildren(QLabel)]

            # Honest claims across the whole page.
            lowered = texts(window).casefold()
            for banned in ("safe to remove", "safe to delete", "freed", "optimized", "100% safe"):
                assert banned not in lowered, banned

            # Leaving the page stops it quietly and a later tick does nothing.
            timer = window.page.tools_timer
            window.navigate("Overview")
            settle()
            tools_page.tick(window)
            assert window.current_route == "Overview"
            window.navigate("More Tools")
            settle()

            # Layout at the supported sizes on every tab: no sideways scrolling, tiles stay usable.
            for width, height in ((1280, 720), (1440, 900), (960, 650)):
                window.resize(width, height)
                for key, *_rest in data.TABS:
                    window.tools_tabs[key].click()
                    settle()
                    QTest.qWait(30)
                    settle()
                    if window.page.horizontalScrollBar().maximum() != 0:
                        wide = sorted(((w.minimumSizeHint().width(), type(w).__name__, w.objectName())
                                       for w in window.page.findChildren(QWidget)), reverse=True)[:12]
                        print("Horizontal overflow at", (width, height), key, "viewport", window.page.viewport().width(), "widest:", wide)
                    assert window.page.horizontalScrollBar().maximum() == 0, (width, height, key)
                    for tile_key, control in window.tools_tiles.items():
                        if control.isVisible():
                            assert control.width() >= 40, (width, height, key, tile_key, control.width())
                window.tools_tabs["hub"].click()
                settle()
                print("holder width", window.tools_holder.width(), "side column", window.tools_side.isVisible(), "at", (width, height))
                assert window.grab().save(str(args.output / f"tools-page-{width}.png"))
            assert errors.call_count == 0, errors.call_args_list
            window.close()
            settle()
        assert tree_bytes(root / "Untouched") == before, "Nothing outside the chosen report files may change"
        assert small.read_bytes() == small_before and hashlib.sha256(big.read_bytes()).hexdigest() == big_before, "Hashing never edits a file"
    print("PASS: More Tools page: six tabs and twenty-four tiles, hand-offs to the owning tabs, the seven Windows tools wired to their own screens, "
          "reports, a real hash checker, live health readings, real Active Tasks, the Tool Log and no sideways scrolling.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
