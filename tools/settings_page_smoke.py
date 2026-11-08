"""Native Qt check of the Settings page: staged preferences, real saves that survive a restart, honest fixed controls."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch


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
    from PySide6.QtWidgets import QApplication
    import core
    from core import ModFolder, OldFile, SteamGame, default_settings
    from gg_desktop import settings_page, settings_store
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.backend import Inventory
    from gg_desktop.models import merge_games
    from gg_desktop.settings_page import state_of
    from tests.test_settings import FakeRegistry

    app = QApplication.instance() or QApplication([])

    def settle():
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()

    def tree_bytes(folder):
        return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in folder.rglob("*") if p.is_file()}

    def on_disk():
        return json.loads((core.config_dir() / "settings.json").read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory(prefix="GG-settings-page-") as temp:
        root = Path(temp)
        (root / "Untouched").mkdir()
        (root / "Untouched" / "fixture.txt").write_text("untouched", encoding="utf-8")
        before = tree_bytes(root / "Untouched")
        work = root / "Work"
        picked = {name: work / name for name in ("Mod Backups", "Personal Photos", "Downloads Two", "Videos")}
        for folder in picked.values():
            folder.mkdir(parents=True)
        registry = FakeRegistry()
        steam = [SteamGame("1", "Starfield", str(root / "Steam"), str(work / "Mod Backups" / "Starfield"), 1000, None, "Steam")]

        stack = ExitStack()
        for target, options in (
            ("core.config_dir", dict(return_value=root / "Config")),
            ("gg_desktop.settings_page.get_records", dict(return_value=[])),
            ("gg_desktop.recovery_screens.get_records", dict(return_value=[])),
            ("gg_desktop.recovery_screens.get_activity", dict(return_value=[])),
            ("gg_desktop.undo_page.get_records", dict(return_value=[])),
            ("gg_desktop.undo_page.get_activity", dict(return_value=[])),
            ("gg_desktop.assistant_page.get_records", dict(return_value=[])),
            ("gg_desktop.assistant_page.get_activity", dict(return_value=[])),
            ("gg_desktop.ready_room_services.config_dir", dict(return_value=root / "Preferences")),
            ("gg_desktop.game_artwork.artwork_dir", dict(return_value=root / "Artwork")),
            ("gg_desktop.game_artwork._request", dict(side_effect=AssertionError("No automatic network"))),
            ("gg_desktop.settings_system.available", dict(return_value=True)),
            ("gg_desktop.settings_system._registry", dict(return_value=registry)),
        ):
            stack.enter_context(patch(target, **options))
        errors = stack.enter_context(patch.object(CrimsonWindow, "error"))
        stack.enter_context(patch.object(CrimsonWindow, "info"))
        confirm = stack.enter_context(patch.object(CrimsonWindow, "confirm", return_value=True))
        folder_dialog = stack.enter_context(patch.object(settings_page.QFileDialog, "getExistingDirectory", return_value=""))
        save_dialog = stack.enter_context(patch.object(settings_page.QFileDialog, "getSaveFileName", return_value=("", "")))
        open_dialog = stack.enter_context(patch.object(settings_page.QFileDialog, "getOpenFileName", return_value=("", "")))
        opened = stack.enter_context(patch.object(settings_page.QDesktopServices, "openUrl"))
        with stack:
            # Settings that already hold another tab's saved data (Undo Center hidden rows) and a personal rule.
            seeded = default_settings()
            seeded.update(undo_hidden=["row-1"], assistant_chats=[{"id": "c", "title": "t", "messages": [], "updated": 1.0}])
            core.save_settings(seeded)
            window = CrimsonWindow()
            window.show()
            window.resize(1280, 720)
            window.inventory = Inventory(steam=steam, games=merge_games(steam, []), scanned_at="2026-11-08 10:00")
            assert window.settings["undo_hidden"] == ["row-1"], "Another tab's saved data is loaded at startup"
            window.navigate("Settings")
            settle()
            state = state_of(window)

            # Six tabs, General first, nothing staged, honest footer.
            assert list(window.settings_tab_buttons) == [t[0] for t in settings_page.TABS], list(window.settings_tab_buttons)
            assert window.settings_tab_buttons["General"].isChecked() and window.settings_stack.currentIndex() == 0
            assert not window.settings_apply.isEnabled() and not window.settings_cancel.isEnabled()
            assert window.settings_footer.text() == settings_page.FOOTER
            assert window.settings_path.full() == str(core.config_dir())
            assert window.grab().save(str(args.output / "settings-general-1280.png"))

            # Protection switches are locked on; the update switch is off and unavailable; none stage a change.
            for switch in [s for s in window.findChildren(settings_page.Switch) if s.locked]:
                was = switch.isChecked()
                switch.click()
                assert switch.isChecked() == was
            assert sum(1 for s in window.findChildren(settings_page.Switch) if s.locked and s.isChecked()) == 6, "three locked switches on each of the two pages that show Protection"
            update = next(s for s in window.findChildren(settings_page.Switch) if s.accessibleName() == "Check for updates on launch")
            assert not update.isEnabled() and not update.isChecked()
            assert not window.settings_apply.isEnabled()

            # Staging then Cancel changes nothing on disk.
            window.settings_controls["start_minimized"][0].click()
            assert window.settings_apply.isEnabled() and "1 unapplied change" in window.settings_footer.text()
            assert "Start minimized" in window.settings_footer.text()
            window.settings_cancel.click()
            settle()
            assert not window.settings_controls["start_minimized"][0].isChecked() and not window.settings_apply.isEnabled()
            assert on_disk().get("start_minimized") in (None, False)

            # A scan-on-launch edit shows on both tabs, then Apply saves it and keeps the other tabs' data.
            window.settings_controls["scan_on_launch"][0].click()
            window.settings_tab_buttons["Scanning"].click()
            settle()
            assert window.settings_stack.currentIndex() == 1 and window.settings_controls["scan_on_launch"][1].isChecked()
            combo = window.settings_controls["files_stale_days"][0]
            combo.setCurrentIndex(combo.findData(90))
            graveyard = window.settings_controls["graveyard_days"][0]
            graveyard.setCurrentIndex(graveyard.findData(180))
            assert "3 unapplied changes" in window.settings_footer.text()
            window.settings_apply.click()
            settle()
            saved = on_disk()
            assert saved["scan_on_launch"] is True and saved["files_stale_days"] == 90 and saved["graveyard_days"] == 180, saved
            assert saved["undo_hidden"] == ["row-1"] and saved["assistant_chats"], "Applying keeps other tabs' saved data"
            assert window.settings["scan_on_launch"] is True and not window.settings_apply.isEnabled()
            assert any("Settings changed" in str(e) for e in core.get_activity()), "The change is logged"
            reopened = settings_store.load_settings()
            assert reopened["scan_on_launch"] is True and reopened["undo_hidden"] == ["row-1"], "Survives a restart"

            # Excluded folders: valid ones stage and save; a drive root and a duplicate are refused.
            folder_dialog.return_value = str(picked["Mod Backups"])
            settings_page.add_excluded(window)
            folder_dialog.return_value = str(picked["Videos"])
            settings_page.add_excluded(window)
            assert state.pending["excluded_folders"] == [str(picked["Mod Backups"]), str(picked["Videos"])]
            assert "Excluded Folders (2)" in window.findChild(settings_page.QFrame, "settingsExcluded").heading.text()
            assert len(window.settings_excluded_entries) == 2
            folder_dialog.return_value = str(picked["Videos"])
            settings_page.add_excluded(window)
            folder_dialog.return_value = str(Path(root).anchor)
            settings_page.add_excluded(window)
            assert errors.call_count == 2 and len(state.pending["excluded_folders"]) == 2, errors.call_args_list
            errors.reset_mock()
            window.settings_excluded_entries[1][1].click()
            settle()
            assert state.pending["excluded_folders"] == [str(picked["Mod Backups"])]
            window.settings_apply.click()
            settle()
            assert on_disk()["excluded_folders"] == [str(picked["Mod Backups"])]

            # The scan filter uses what was saved: the game inside the excluded folder is left out of the next scan.
            from gg_desktop.settings_rules import filter_inventory
            probe = Inventory(steam=list(steam), games=merge_games(steam, []))
            assert filter_inventory(probe, window.settings["excluded_folders"]) == 2 and not probe.games

            # Old Files folder: an ordinary folder is saved at once; a drive root is refused.
            window.settings_tab_buttons["Scanning"].click()
            folder_dialog.return_value = str(picked["Downloads Two"])
            settings_page.old_files_folder(window)
            assert on_disk()["scan_folder"] == str(picked["Downloads Two"]), on_disk()["scan_folder"]
            folder_dialog.return_value = str(Path(root).anchor)
            settings_page.old_files_folder(window)
            assert errors.call_count == 1 and on_disk()["scan_folder"] == str(picked["Downloads Two"])
            errors.reset_mock()
            assert window.findChild(settings_page.ElideLabel, "settingsFolder").full() == str(picked["Downloads Two"])
            assert window.grab().save(str(args.output / "settings-scanning-1280.png"))

            # Launch with Windows writes and removes the current user's Run entry only.
            window.settings_tab_buttons["General"].click()
            window.settings_controls["autostart"][0].click()
            window.settings_apply.click()
            settle()
            assert registry.values.get("GameGrave") == settings_page.system.command(), registry.values
            window.settings_controls["autostart"][0].click()
            window.settings_apply.click()
            settle()
            assert "GameGrave" not in registry.values
            with patch("gg_desktop.settings_system.set_enabled", side_effect=OSError("Windows said no")):
                window.settings_controls["autostart"][0].click()
                window.settings_apply.click()
                settle()
            assert errors.call_count == 1 and not window.settings_controls["autostart"][0].isChecked() and not window.settings_apply.isEnabled()
            errors.reset_mock()

            # Never Touch: protect a folder, see it counted, refuse to remove it when not confirmed, then remove it.
            window.settings_tab_buttons["Protection"].click()
            settle()
            folder_dialog.return_value = str(picked["Personal Photos"])
            settings_page.add_rule(window)
            assert on_disk()["never_touch"] == [str(picked["Personal Photos"])], on_disk()["never_touch"]
            assert window.settings_never_list.count() == 1 and "Personal rules  1" in " ".join(
                l.text() for l in window.findChildren(settings_page.QLabel))
            window.settings_never_list.setCurrentRow(0)
            confirm.return_value = False
            settings_page.remove_rule(window)
            assert window.settings_never_list.count() == 1 and on_disk()["never_touch"]
            confirm.return_value = True
            settings_page.remove_rule(window)
            assert window.settings_never_list.count() == 0 and on_disk()["never_touch"] == []
            settings_page.add_rule(window)
            assert window.grab().save(str(args.output / "settings-protection-1280.png"))
            window._focus_never_touch_rule = str(picked["Personal Photos"])
            window.navigate("Overview")
            window.navigate("Settings")
            settle()
            assert window.settings_stack.currentIndex() == 2 and window.settings_never_list.currentRow() == 0, "Manage parent rule opens the rule"

            # Export holds only preferences and folders; a foreign file is refused; Import adds rules, never removes them.
            window.settings_tab_buttons["Data & Privacy"].click()
            settle()
            target = work / "export.json"
            save_dialog.return_value = (str(target), "")
            settings_page.export_settings(window)
            exported = json.loads(target.read_text(encoding="utf-8"))
            assert exported["app"] == "Game Grave" and "assistant_chats" not in exported["settings"] and "undo_hidden" not in exported["settings"]
            assert exported["settings"]["never_touch"] == [str(picked["Personal Photos"])]
            foreign = work / "foreign.json"
            foreign.write_text("[1,2,3]", encoding="utf-8")
            open_dialog.return_value = (str(foreign), "")
            settings_page.import_settings(window)
            assert errors.call_count == 1
            errors.reset_mock()
            incoming = work / "incoming.json"
            incoming.write_text(json.dumps({"app": "Game Grave", "format": 1, "settings": {
                "scan_on_launch": False, "files_stale_days": 30, "never_touch": [], "excluded_folders": []}}), encoding="utf-8")
            open_dialog.return_value = (str(incoming), "")
            confirm.return_value = False
            settings_page.import_settings(window)
            assert on_disk()["files_stale_days"] == 90, "Declining the import changes nothing"
            confirm.return_value = True
            settings_page.import_settings(window)
            after = on_disk()
            assert after["files_stale_days"] == 30 and after["scan_on_launch"] is False and after["excluded_folders"] == []
            assert after["never_touch"] == [str(picked["Personal Photos"])], "Import never removes a protection rule"
            assert after["undo_hidden"] == ["row-1"] and not window.settings_apply.isEnabled()
            facts = " ".join(l.text() for l in window.findChildren(settings_page.QLabel))
            assert "Settings file" in facts and "Activity log entries" in facts and "Recovery records" in facts
            assert window.grab().save(str(args.output / "settings-data-1280.png"))

            # Reset stages the defaults, keeps protection and everything else, and Apply writes them.
            window.settings_tab_buttons["General"].click()
            window.settings_controls["start_minimized"][0].click()
            window.settings_apply.click()
            window.settings_reset.click()
            settle()
            assert window.settings_apply.isEnabled() and state.pending["files_stale_days"] == 180
            window.settings_apply.click()
            settle()
            after = on_disk()
            assert after["files_stale_days"] == 180 and after["start_minimized"] is False
            assert after["never_touch"] == [str(picked["Personal Photos"])] and after["undo_hidden"] == ["row-1"]
            assert after["steam_extra_roots"] == [] and after["scan_folder"] == str(picked["Downloads Two"])

            # Data folder opens through the system, and Notifications and Appearance say what is real.
            window.settings_open.click()
            assert opened.call_count == 1 and Path(opened.call_args[0][0].toLocalFile()) == core.config_dir()
            window.settings_tab_buttons["Notifications"].click()
            settle()
            texts = " ".join(l.text() for l in window.findChildren(settings_page.QLabel))
            assert "no pop-up alerts" in texts and "status line" in texts
            assert window.grab().save(str(args.output / "settings-notifications-1280.png"))
            window.settings_tab_buttons["Appearance"].click()
            settle()
            texts = " ".join(l.text() for l in window.findChildren(settings_page.QLabel))
            assert "Crimson Command" in texts and "100% native" in texts
            assert window.grab().save(str(args.output / "settings-appearance-1280.png"))

            # Unapplied edits survive a page rebuild (a scan finishing re-renders the tab) and show as unapplied.
            window.settings_tab_buttons["General"].click()
            window.settings_controls["scan_on_launch"][0].click()
            window.navigate("Overview")
            window.navigate("Settings")
            settle()
            assert window.settings_window.settings_controls["scan_on_launch"][0].isChecked() and window.settings_apply.isEnabled()
            window.settings_cancel.click()

            # Layout at the supported sizes on every tab: no sideways scrolling.
            for width, height in ((1280, 720), (1440, 900), (960, 650)):
                window.resize(width, height)
                for tab in settings_page.TABS:
                    window.settings_tab_buttons[tab[0]].click()
                    settle()
                    QTest.qWait(30)
                    settle()
                    if window.page.horizontalScrollBar().maximum() != 0:
                        from PySide6.QtWidgets import QWidget
                        wide = sorted(((w.minimumSizeHint().width(), type(w).__name__, w.objectName())
                                       for w in window.page.findChildren(QWidget)), reverse=True)[:12]
                        print("Horizontal overflow at", (width, height), tab[0], "viewport", window.page.viewport().width(), "widest:", wide)
                    assert window.page.horizontalScrollBar().maximum() == 0, (width, height, tab[0])
                window.settings_tab_buttons["General"].click()
                settle()
                assert window.grab().save(str(args.output / f"settings-page-{width}.png"))
            assert errors.call_count == 0, errors.call_args_list
            window.close()
            settle()
        assert tree_bytes(root / "Untouched") == before, "Nothing outside Settings' own files may change"
    print("PASS: Settings page: staged preferences with Apply and Cancel, saved settings survive a restart, excluded folders, "
          "Launch with Windows, Never Touch, export and import that never remove protection, honest fixed controls and no sideways scrolling.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
