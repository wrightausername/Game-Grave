"""Native Qt check of the Graveyard page: evidence, live filter counts, leftover scan, protection and the verified Recycle Bin path."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import os
from pathlib import Path
import shutil
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
    from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QFileDialog, QLabel, QPushButton, QWidget
    from core import ModFolder, OldFile, SteamGame, default_settings, human_size
    from gg_desktop import grave_page
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.backend import Inventory, refresh_graveyard
    from gg_desktop.grave_page import state_of

    app = QApplication.instance() or QApplication([])
    day = 86400

    def settle():
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()

    def wait_for(predicate, what="Graveyard did not finish its task"):
        deadline = time.monotonic() + 40
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
            time.sleep(.004)
        assert predicate(), what
        settle()

    def make(path, size, age=0):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"g" * size)
        moment = time.time() - age * day
        os.utime(path, (moment, moment))
        return path

    def old(path):
        info = path.stat()
        return OldFile(str(path), info.st_size, info.st_mtime, info.st_dev, info.st_ino, info.st_mtime_ns, info.st_nlink)

    def tree_bytes(folder):
        return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in folder.rglob("*") if p.is_file()}

    def shown(window):
        return [i.name for i in window._shown_graves]

    def every(window):
        return [i.name for i in window._grave_rows]

    def open_tab(window, name):
        window.grave_tabs.buttons[name].click()
        settle()
        assert state_of(window).tab == name, name

    def row_of(window, name):
        return shown(window).index(name)

    def tick(window, name, on=True):
        window.grave_table.item(row_of(window, name), 0).setCheckState(Qt.Checked if on else Qt.Unchecked)
        settle()

    def pick(window, name):
        window.grave_table.selectRow(row_of(window, name))
        settle()

    def detail_text(window):
        return " ".join([w.text() for w in window.grave_details.findChildren(QLabel)] +
                        [b.text() for b in window.grave_details.findChildren(QPushButton)])

    def box(window, group, name, on=True):
        control = getattr(window, "grave_" + group + "_rows")[name].box
        control.setChecked(on)
        settle()

    def idle(window):
        wait_for(lambda: not state_of(window).busy and not window.workers and not window.cleaning)

    with tempfile.TemporaryDirectory(prefix="GG-grave-page-") as temp:
        root = Path(temp)
        local, program_data, home = root / "Local", root / "ProgramData", root / "Home"
        library, steam_root = root / "SteamLibrary", root / "Steam"
        for folder in (local, program_data, home, library, steam_root):
            folder.mkdir()
        # Engine findings (what a PC scan would have found)
        archive = make(root / "Stash" / "skyrim mod pack.zip", 5000, age=500)
        clip = make(root / "Stash" / "clip.mp4", 6000, age=400)
        shot = make(root / "Stash" / "shot.png", 4000, age=380)
        pack = root / "Leftover Stuff" / "Old Pack"
        make(pack / "a.txt", 700, age=800)
        make(pack / "b.txt", 300, age=800)
        os.utime(pack, (time.time() - 800 * day,) * 2)
        # Known leftover locations the Scan Leftovers button reads
        for index in range(3):
            make(local / "D3DSCache" / f"d{index}.bin", 1000)
        for index in range(3):
            make(local / "Battle.net" / "Cache" / f"c{index}.dat", 300)
        for index in range(2):
            make(local / "Battle.net" / "Logs" / f"l{index}.log", 200)
        make(home / "Documents" / "My Games" / "Skyrim" / "Skyrim.ini", 100)
        make(library / "steamapps" / "shadercache" / "1091500" / "a.bin", 700)
        make(library / "steamapps" / "shadercache" / "999999" / "x.bin", 600)
        make(library / "steamapps" / "temp" / "t.tmp", 50)
        before = tree_bytes(root)
        game = SteamGame("1091500", "Cyberpunk 2077", str(steam_root), str(library / "steamapps" / "common" / "Cyberpunk 2077"),
                         120000000, time.time() - 500 * day, "Scope fixture")
        mod = ModFolder("Old Pack", str(pack), "", "Installed: possible mods", (), 1000, 2, False, "Manual / Other", "Review in Mods")
        settings = default_settings()
        settings["never_touch"] = []
        saved = []
        env = {"LOCALAPPDATA": str(local), "PROGRAMDATA": str(program_data), "USERPROFILE": str(home), "HOME": str(home)}
        shell_bin = root / "DisposableShell"
        shell_bin.mkdir()
        recycled = []

        def fake_recycle(path):
            recycled.append(Path(path))
            shutil.move(str(path), str(shell_bin / (str(len(recycled)) + "-" + Path(path).name)))

        def keep_settings(updated):
            saved.append(dict(updated))

        stack = ExitStack()
        stack.enter_context(patch.dict(os.environ, env))
        for target, options in (
            ("gg_desktop.app.load_settings", dict(return_value=settings)),
            ("core._steam_roots", dict(return_value=[steam_root])),
            ("core.steam_libraries", dict(return_value=[library])),
            ("core.save_settings", dict(side_effect=keep_settings)),
            ("gg_desktop.backend.save_settings", dict(side_effect=keep_settings)),
            ("gg_desktop.backend.log_event", {}),
            ("gg_desktop.recovery_screens.save_settings", dict(side_effect=keep_settings)),
            ("gg_desktop.reference_library.save_settings", {}),
            ("gg_desktop.ready_room_services.config_dir", dict(return_value=root / "Preferences")),
            ("gg_desktop.game_artwork.artwork_dir", dict(return_value=root / "Artwork")),
            ("gg_desktop.game_artwork._request", dict(side_effect=AssertionError("No automatic network"))),
        ):
            stack.enter_context(patch(target, **options))
        info = stack.enter_context(patch.object(CrimsonWindow, "info"))
        errors = stack.enter_context(patch.object(CrimsonWindow, "error"))
        confirm = stack.enter_context(patch.object(CrimsonWindow, "confirm", return_value=False))
        saver = stack.enter_context(patch.object(QFileDialog, "getSaveFileName"))
        previewer = stack.enter_context(patch.object(CrimsonWindow, "_preview_grave_image"))
        with stack:
            window = CrimsonWindow()
            window.inventory = Inventory(steam=[game], mods=[mod], files=[old(archive)], recordings=[old(clip)],
                                         screenshots=[old(shot)], scanned_at="2026-11-06 12:00")
            refresh_graveyard(window.inventory, window.settings)
            window.show()
            window.resize(1280, 720)
            window.navigate("Graveyard")
            settle()
            state = state_of(window)

            # Before any leftover scan: only what the PC scan found, with honest metrics and tab counts.
            names = {"skyrim mod pack.zip", "clip.mp4", "shot.png", "Cyberpunk 2077", "Old Pack"}
            assert set(every(window)) == names, every(window)
            strip = [v.text() for v in window.grave_metrics.values]
            assert strip[0] == "5" and strip[3] == "1" and strip[4] == "1" and strip[5] == "1", strip
            assert strip[6] == "2", "Reviewable counts only the archive and the recording: " + str(strip)
            assert strip[2] == "5", strip
            labels = {n: b.text() for n, b in window.grave_tabs.buttons.items()}
            assert labels["All Items"] == "All Items (5)" and labels["Games"] == "Games (1)" and labels["Mods"] == "Mods (1)", labels
            assert labels["Downloads"] == "Downloads (1)" and labels["Leftovers"] == "Leftovers (2)", labels
            assert labels["Configs"] == "Configs (0)" and labels["Orphans"] == "Orphans (0)", labels
            assert window.grave_action.text() == "Scan Leftovers" and "Scan Leftovers" in window.grave_notice.text()
            assert window.grab().save(str(args.output / "graveyard-results-1280.png"))

            # Easy ticking: Select all / Clear selection, Shift+click range, Ctrl+click flip, double-click.
            table = window.grave_table

            def at(row):
                return table.visualRect(table.model().index(row, 1)).center()
            assert window.grave_select_button.text() == "Select all"
            window.grave_select_button.click()
            settle()
            assert len(state.checked) == 5 and window.grave_select_button.text() == "Clear selection"
            window.grave_select_button.click()
            settle()
            assert not state.checked and window.grave_select_button.text() == "Select all"
            QTest.mouseDClick(table.viewport(), Qt.LeftButton, Qt.NoModifier, at(0))
            settle()
            first = window._shown_graves[0].key
            assert state.checked == {first}, state.checked
            QTest.mouseClick(table.viewport(), Qt.LeftButton, Qt.ShiftModifier, at(2))
            settle()
            assert state.checked == {i.key for i in window._shown_graves[:3]}, state.checked
            assert window.grave_select_all.text().startswith("3 selected")
            QTest.mouseClick(table.viewport(), Qt.LeftButton, Qt.ControlModifier, at(1))
            settle()
            assert state.checked == {window._shown_graves[0].key, window._shown_graves[2].key}, state.checked
            grave_page.select_visible(window, False)
            settle()
            assert not state.checked

            # Details are evidence, never a safe-to-remove claim.
            pick(window, "Cyberpunk 2077")
            text = detail_text(window)
            assert "Cyberpunk 2077" in text and "Why It's in the Graveyard" in text and "What You Can Do" in text, text
            assert "safe to remove" not in text.lower() and "Direct" in text, text
            assert "only through Steam" in text, text
            pick(window, "skyrim mod pack.zip")
            assert "Name hint" in detail_text(window)
            pick(window, "Old Pack")
            state.subtab = "Contents"
            grave_page.details(window)
            contents_text = detail_text(window)
            assert "a.txt" in contents_text and "b.txt" in contents_text and "Names only" in contents_text, contents_text
            state.subtab = "References"
            grave_page.details(window)
            assert "Never Touch" in detail_text(window)
            state.subtab = "Details"

            # Filters: age (cumulative), size, type, search, sort, tabs and Clear All, with live counts.
            assert window.grave_age_rows["30+ Days"].count.text() == "5" and window.grave_age_rows["24+ Months"].count.text() == "1"
            box(window, "age", "24+ Months")
            assert every(window) == ["Old Pack"], every(window)
            assert window.grave_age_rows["30+ Days"].count.text() == "5", "age counts ignore the age choice"
            box(window, "age", "24+ Months", False)
            box(window, "size", "100 MB - 1 GB")
            assert every(window) == ["Cyberpunk 2077"], every(window)
            box(window, "size", "100 MB - 1 GB", False)
            for kind in list(window.grave_type_rows):
                box(window, "type", kind, False)
            assert not every(window) and "No items match" in window.grave_notice.text(), window.grave_notice.text()
            box(window, "type", "Possible Downloads")
            assert every(window) == ["skyrim mod pack.zip"], every(window)
            window.grave_search.setText("zip")
            settle()
            assert every(window) == ["skyrim mod pack.zip"]
            window.grave_search.clear()
            grave_page.clear_filters(window)
            settle()
            assert set(every(window)) == names and all(c.box.isChecked() for c in window.grave_type_rows.values())
            window.global_search.setText("clip")
            settle()
            assert every(window) == ["clip.mp4"], every(window)
            window.global_search.clear()
            window.grave_sort.setCurrentText("Name (A-Z)")
            settle()
            assert every(window) == sorted(every(window), key=str.casefold)
            window.grave_sort.setCurrentText("Size (Largest)")
            settle()
            assert every(window)[0] == "Cyberpunk 2077"
            window.grave_sort.setCurrentText("Last Touched (Oldest)")
            settle()
            assert every(window)[0] == "Old Pack", every(window)
            open_tab(window, "Games")
            assert every(window) == ["Cyberpunk 2077"]
            open_tab(window, "Downloads")
            assert every(window) == ["skyrim mod pack.zip"]
            open_tab(window, "Configs")
            assert not every(window) and "Scan Leftovers" in window.grave_notice.text(), window.grave_notice.text()
            open_tab(window, "All Items")
            grave_page.set_compact(window, True)
            assert window.grave_table.rowHeight(0) == 30
            grave_page.set_compact(window, False)
            assert window.grave_table.rowHeight(0) == 44

            # The Overview and Game DNA hand-offs still land on the right row.
            key = next(i.key for i in window._shown_graves if i.name == "clip.mp4")
            window._pending_grave_key = key
            window.navigate("Graveyard")
            settle()
            assert grave_page.current_item(window).key == key
            window.grave_search.setText(str(clip))
            settle()
            assert shown(window) == ["clip.mp4"] and window.grave_table.currentRow() == 0
            window.grave_search.clear()
            settle()

            # Scan Leftovers reads known locations only, when asked.
            assert not state.scanned
            window.grave_action.click()
            idle(window)
            expected = names | {"DirectX Shader Cache", "Battle.net Cache", "Battle.net Logs", "Skyrim",
                                "Cyberpunk 2077 Shader Cache", "Steam app 999999 Shader Cache", "Steam Temp"}
            assert set(every(window)) == expected, set(every(window)) ^ expected
            labels = {n: b.text() for n, b in window.grave_tabs.buttons.items()}
            assert labels["All Items"] == "All Items (12)" and labels["Configs"] == "Configs (1)" and labels["Orphans"] == "Orphans (1)", labels
            assert labels["Leftovers"] == "Leftovers (7)", labels
            assert window.grave_metrics.values[0].text() == "12" and window.grave_metrics.values[6].text() == "2"
            assert window.grave_metrics.values[3].text() == "1", "A proven game counts once"
            assert not window.grave_action.isVisible()
            assert window.grab().save(str(args.output / "graveyard-scanned-1280.png"))
            open_tab(window, "Orphans")
            assert every(window) == ["Steam app 999999 Shader Cache"], every(window)
            assert window.grave_notice.text().startswith("Orphan means"), window.grave_notice.text()
            pick(window, "Steam app 999999 Shader Cache")
            assert "Direct" in detail_text(window) and "No installed game" in detail_text(window)
            assert window.grab().save(str(args.output / "graveyard-orphans-1280.png"))
            open_tab(window, "Configs")
            assert every(window) == ["Skyrim"]
            pick(window, "Skyrim")
            assert "Protected" in detail_text(window) and "never removed" in detail_text(window), detail_text(window)
            tick(window, "Skyrim")
            info.reset_mock()
            grave_page.protect(window)
            info.assert_called()
            assert not saved, "Settings and saves need no rule and nothing was saved"
            tick(window, "Skyrim", False)
            open_tab(window, "Leftovers")
            pick(window, "Battle.net Cache")
            assert "Other Storage" in detail_text(window), detail_text(window)
            open_tab(window, "All Items")

            # Delete choices only offer what applies, and screenshots and folders can never be batched.
            tick(window, "shot.png")
            tick(window, "skyrim mod pack.zip")
            window.grave_delete_menu.aboutToShow.emit()
            options = {a.text(): a.isEnabled() for a in window.grave_delete_menu.actions()}
            assert not options["Move Files to Recycle Bin…"], options
            errors.reset_mock()
            grave_page.recycle(window)
            errors.assert_called()
            assert "preview" in errors.call_args[0][1], errors.call_args
            errors.reset_mock()
            tick(window, "skyrim mod pack.zip", False)
            window.grave_delete_menu.aboutToShow.emit()
            options = {a.text(): a.isEnabled() for a in window.grave_delete_menu.actions()}
            assert options["Preview Screenshot Then Remove…"] and not options["Move Files to Recycle Bin…"], options
            grave_page.preview(window)
            previewer.assert_called_once()
            tick(window, "shot.png", False)
            tick(window, "Cyberpunk 2077")
            window.grave_delete_menu.aboutToShow.emit()
            options = {a.text(): a.isEnabled() for a in window.grave_delete_menu.actions()}
            assert options["Uninstall in Steam…"] and not options["Move Files to Recycle Bin…"], options
            confirm.reset_mock()
            grave_page.steam_uninstall(window)
            assert confirm.call_args[0][0] == "Open Steam uninstall?" and "will not remove the installation directly" in confirm.call_args[0][1]
            tick(window, "Cyberpunk 2077", False)
            tick(window, "Old Pack")
            window.grave_delete_menu.aboutToShow.emit()
            options = {a.text(): a.isEnabled() for a in window.grave_delete_menu.actions()}
            assert options["Review in Mods"] and not options["Move Files to Recycle Bin…"], options
            tick(window, "Old Pack", False)

            # Copy and export touch nothing.
            tick(window, "clip.mp4")
            grave_page.copy_paths(window)
            assert QGuiApplication.clipboard().text() == str(clip)
            tick(window, "clip.mp4", False)
            saver.return_value = (str(root / "Export" / "graveyard.csv"), "CSV (*.csv)")
            (root / "Export").mkdir()
            grave_page.export_csv(window)
            lines = (root / "Export" / "graveyard.csv").read_text(encoding="utf-8").splitlines()
            assert lines[0].startswith("Name,Path") and len(lines) >= 13, len(lines)
            (root / "Export" / "graveyard.csv").unlink()
            (root / "Export").rmdir()

            # Protect keeps an item out of removal; Unprotect works from the row and removes only that rule.
            tick(window, "skyrim mod pack.zip")
            grave_page.protect(window)
            settle()
            assert saved and saved[-1]["never_touch"] == [os.path.abspath(archive)], saved[-1]["never_touch"]
            window.settings["never_touch"] = saved[-1]["never_touch"]
            refresh_graveyard(window.inventory, window.settings)
            grave_page.refresh(window)
            settle()
            assert window.grave_metrics.values[6].text() == "1", "A protected file is no longer reviewable"
            i = row_of(window, "skyrim mod pack.zip")
            unlock = window.grave_table.cellWidget(i, 5)
            assert isinstance(unlock, QPushButton) and "Unprotect" in unlock.text()
            assert "Protected" in window.grave_table.item(i, 1).data(Qt.UserRole)
            pick(window, "skyrim mod pack.zip")
            assert "Protected" in detail_text(window)
            confirm.return_value = True
            unlock.click()
            settle()
            assert archive.is_file() and not window.settings["never_touch"], window.settings["never_touch"]
            confirm.return_value = False
            assert window.grave_metrics.values[6].text() == "2"

            # Recycle Bin: nothing moves until confirmed, then only the checked, re-verified files go.
            window.navigate("Graveyard")
            settle()
            tick(window, "skyrim mod pack.zip")
            tick(window, "clip.mp4")
            window.grave_delete_menu.aboutToShow.emit()
            options = {a.text(): a.isEnabled() for a in window.grave_delete_menu.actions()}
            assert options["Move Files to Recycle Bin…"], options
            grave_page.recycle(window)
            settle()
            assert archive.is_file() and clip.is_file() and not recycled, "Declining the confirmation moves nothing"
            confirm.return_value = True
            with patch("cleanup_actions.recycle_file", side_effect=fake_recycle), \
                 patch("cleanup_actions.register_recycle", return_value="test"), patch("cleanup_actions.log_event"):
                grave_page.recycle(window)
                wait_for(lambda: len(recycled) == 2 and not window.cleaning and not window.workers)
            confirm.return_value = False
            assert not archive.exists() and not clip.exists() and shot.is_file() and pack.is_dir(), "Only the checked files moved"
            wait_for(lambda: window.current_route == "Graveyard" and "skyrim mod pack.zip" not in shown(window))
            assert set(every(window)) == expected - {"skyrim mod pack.zip", "clip.mp4"}, every(window)
            assert window.grave_metrics.values[6].text() == "0"
            assert window.grave_tabs.buttons["Downloads"].text() == "Downloads (0)"

            # Restore opens Undo Center instead of acting itself.
            window.navigate("Overview")
            settle()
            window.navigate("Graveyard")
            settle()
            assert state.scanned and len(grave_page.universe(window)) == 10

            # Narrower windows keep every action visible.
            for width, height in ((1280, 720), (1440, 900), (960, 650)):
                window.resize(width, height)
                settle()
                QTest.qWait(40)
                settle()
                if height >= 720:
                    bottom = window.grave_more.mapTo(window, QPoint(0, window.grave_more.height())).y()
                    assert bottom <= window.height(), ("Footer actions are cut off", (width, height), bottom)
                if window.page.horizontalScrollBar().maximum() != 0:
                    wide = sorted(((w.minimumSizeHint().width(), type(w).__name__, w.objectName())
                                   for w in window.page.findChildren(QWidget)), reverse=True)[:12]
                    print("Horizontal overflow at", (width, height), "viewport", window.page.viewport().width(), "widest:", wide)
                assert window.page.horizontalScrollBar().maximum() == 0, (width, height)
                assert window.grab().save(str(args.output / f"graveyard-page-{width}.png"))
            errors.assert_not_called()
            window.close()
            settle()
        after = tree_bytes(root)
        gone = {k for k in before if k not in after and not k.startswith("DisposableShell")}
        assert gone == {str(Path("Stash") / "skyrim mod pack.zip"), str(Path("Stash") / "clip.mp4")}, gone
        changed = {k for k in before if k in after and before[k] != after[k]}
        assert not changed, changed
    print("PASS: Graveyard page: evidence-only metrics, live filter counts, leftover scan on request, Orphans and Configs, "
          "protection and in-row Unprotect, no batching of screenshots, games, mods or folders, and a confirmed Recycle Bin move "
          "of exactly the two checked files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
