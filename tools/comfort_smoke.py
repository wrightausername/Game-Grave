"""Everyday comforts, driven like the owner would: Back (button, Alt+Left, mouse back), Ctrl+1..9, the shortcut list, the
notification centre and its badge, the pop-up with Open, Copy diagnostics, the "Paused while you play" note, and the tray
(close hides it, Quit really quits). Nothing on this PC is changed."""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("_ci_temp"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    os.environ["GAME_GRAVE_TRAY"] = "1"
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QCoreApplication, QEvent, QPointF, Qt, QTimer
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton
    from core import SteamGame, default_settings
    from gg_desktop import comfort, comfort_core
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.backend import Inventory
    from gg_desktop.models import merge_games

    app = QApplication.instance() or QApplication([])

    def settle():
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()

    def modal(open_it, check):
        seen = []

        def look():
            dialog = app.activeModalWidget()
            try:
                assert isinstance(dialog, QDialog), dialog
                check(dialog)
                seen.append(True)
            finally:
                if dialog is not None:
                    dialog.reject()
        QTimer.singleShot(60, look)
        open_it()
        settle()
        assert seen, "The dialog did not open"

    with tempfile.TemporaryDirectory(prefix="GG-comfort-") as temp:
        root = Path(temp)
        settings = dict(default_settings(), welcome_at_startup=False)
        saved = []
        stack = ExitStack()
        for target, options in (
            ("gg_desktop.app.load_settings", dict(return_value=settings)),
            ("core.save_settings", dict(side_effect=lambda s: saved.append(dict(s)))),
            ("core.config_dir", dict(return_value=root / "Preferences")),
            ("gg_desktop.backend.save_settings", {}),
            ("gg_desktop.backend.log_event", {}),
            ("gg_desktop.ready_room_services.config_dir", dict(return_value=root / "Preferences")),
            ("gg_desktop.game_artwork.artwork_dir", dict(return_value=root / "Artwork")),
            ("gg_desktop.game_artwork._request", dict(side_effect=AssertionError("No automatic network"))),
        ):
            stack.enter_context(patch(target, **options))
        stack.enter_context(patch.object(CrimsonWindow, "error"))
        stack.enter_context(patch.object(CrimsonWindow, "info"))
        with stack:
            window = CrimsonWindow()
            window.show()
            window.resize(1440, 900)
            steam = [SteamGame("1", "Elden Ring", "C:\\Steam", "C:\\Steam\\common\\ELDEN RING", 50 * 1024 ** 3, None, "Steam")]
            window.inventory = Inventory(steam=steam, games=merge_games(steam, []), scanned_at="2026-11-14 17:40",
                                         warnings=[r"Old Files folder C:\Users\someone\Downloads unavailable"])
            settle()

            # Back: the arrow, Alt+Left and the mouse's back button.
            assert not window.back_button.isEnabled()
            window.navigate("Games")
            window.navigate("Mods")
            window.navigate("Hardware")
            settle()
            assert window.back_button.isEnabled() and "Mods" in window.back_button.toolTip()
            window.back_button.click()
            settle()
            assert window.current_route == "Mods", window.current_route
            QTest.keyClick(window, Qt.Key_Left, Qt.AltModifier)
            settle()
            assert window.current_route == "Games", window.current_route
            press = QMouseEvent(QEvent.MouseButtonPress, QPointF(10, 10), QPointF(10, 10), Qt.BackButton, Qt.BackButton,
                                Qt.NoModifier)
            QApplication.sendEvent(window, press)
            settle()
            assert window.current_route == "Overview", window.current_route

            # Ctrl+1..9 follow the sidebar order.
            QTest.keyClick(window, Qt.Key_3, Qt.ControlModifier)
            settle()
            from gg_desktop import nav_groups
            visible = [r for r in nav_groups.routes() if not window.nav_buttons[r].isHidden()]
            assert window.current_route == visible[2], (window.current_route, visible[:4])
            modal(lambda: QTest.keyClick(window, Qt.Key_Slash, Qt.ControlModifier),
                  lambda d: [l.text() for l in d.findChildren(QLabel)].index("Alt+Left") >= 0)

            # A finished job: a pop-up with Open, a badge on the bell, a row in the notification centre.
            window.navigate("Overview")
            settle()
            comfort.notify(window, "Driver updates installed", "2 of 2 installed.", "good", "Hardware")
            settle()
            toast = comfort.state_of(window).toast
            assert toast is not None and toast.isVisible()
            assert window.bell_badge.isVisible() and window.bell_badge.text() == "1"
            assert window.grab().save(str(args.output / "shell-toast.png"))
            open_button = next(b for b in toast.findChildren(type(window.back_button)) if b.text() == "Open")
            open_button.click()
            settle()
            assert window.current_route == "Hardware"
            assert saved and saved[-1]["notices"][0]["title"] == "Driver updates installed"
            undone = []
            comfort.notify(window, "Moved 3 files to the Recycle Bin", "From Old Files.", "good", "Undo Center",
                           action=("Undo", lambda: undone.append(True)))
            settle()
            comfort.state_of(window).toast.action_button.click()
            assert undone == [True], "The extra button (Undo) runs"

            def centre(dialog):
                words = " ".join(l.text() for l in dialog.findChildren(QLabel))
                assert "Driver updates installed" in words and "Moved 3 files" in words and "Scan status:" in words
                assert dialog.grab().save(str(args.output / "shell-notifications.png"))
            modal(window.bell_button.click, centre)
            assert not window.bell_badge.isVisible(), "Opening the list marks everything read"
            modal(lambda: QTest.keyClick(window, Qt.Key_N, Qt.ControlModifier | Qt.ShiftModifier), lambda d: True)

            # Copy diagnostics: version, counts, warnings, no user name.
            comfort.copy_diagnostics(window)
            text = app.clipboard().text()
            assert "Game Grave diagnostics" in text and "games: 1" in text and "someone" not in text.replace(
                os.path.expanduser("~"), "")
            assert "Old Files folder" in text

            # Paused while you play: shown while the Games tracker sees a game running.
            real_tracker = getattr(window, "_games_tracker", None)
            window._games_tracker = SimpleNamespace(ledger=SimpleNamespace(active={window.inventory.games[0].key: 1}))
            comfort.sync_paused(window)
            assert window.paused_chip.isVisible() and window.paused_chip.text() == "Paused while you play Elden Ring"
            assert window.grab().save(str(args.output / "shell-paused.png"))
            window._games_tracker = SimpleNamespace(ledger=SimpleNamespace(active={}))
            comfort.sync_paused(window)
            assert not window.paused_chip.isVisible()
            if real_tracker is not None:
                window._games_tracker = real_tracker
            else:
                del window._games_tracker

            # Sort and filters are remembered per tab.
            window.navigate("Games")
            settle()
            window.game_sort.setCurrentText("Name A to Z")
            settle()
            window.navigate("Overview")
            settle()
            window.navigate("Games")
            settle()
            assert window.game_sort.currentText() == "Name A to Z", window.game_sort.currentText()
            window.game_sort.setCurrentText("Recently played")
            settle()

            # One search for everything: results under the box, arrow + Enter opens the game in Games.
            window.navigate("Overview")
            settle()
            window.activateWindow()
            QTest.mouseClick(window.global_search, Qt.LeftButton)
            QTest.keyClicks(window.global_search, "elden")
            QTest.qWait(300)
            popup = window.search_popup
            assert popup.list.isVisible(), "results show under the search box"
            texts = [popup.list.item(i).text() for i in range(popup.list.count())]
            assert "GAMES" in texts and any(t.startswith("Elden Ring") for t in texts), texts
            assert window.grab().save(str(args.output / "shell-search.png"))
            QTest.keyClick(window.global_search, Qt.Key_Down)
            QTest.keyClick(window.global_search, Qt.Key_Return)
            settle()
            assert window.current_route == "Games" and window.game_search.text() == "Elden Ring", (
                window.current_route, window.game_search.text())
            window.global_search.clear()
            settle()

            # After the first full scan: what was found and three next steps, once.
            from gg_desktop import first_scan
            with patch.dict(os.environ, {"GAME_GRAVE_FIRST_SCAN_CARD": "1"}):
                window.settings = dict(window.settings, first_scan_summary_seen=False)
                dialog = first_scan.after_scan(window)
                settle()
                assert dialog is not None and dialog.isVisible()
                assert window.settings.get("first_scan_summary_seen") is True
                cards = [b for b in dialog.findChildren(QPushButton) if b.objectName() == "primary"]
                assert len(cards) == 3, [b.text() for b in cards]
                assert dialog.grab().save(str(args.output / "shell-first-scan.png"))
                assert first_scan.after_scan(window) is None, "Shown once"
                dialog.close()
                settle()

            # Game Night in Squad Sync: a friend's code shows what you can all play, with Steam's co-op tags.
            from gg_desktop import gamenight_core as gn
            window.settings = dict(window.settings, game_night_name="Alex")
            window.navigate("Ready Room")
            settle()
            squad = window.page.squad
            squad.set_open(True)
            squad.squad_views[1].click()
            settle()
            night = squad.game_night
            friend_code = gn.make_code("Jay", [SimpleNamespace(name=window.inventory.games[0].name, launcher="Steam",
                                                                 app_id=window.inventory.games[0].app_id, size_bytes=1)])
            with patch.object(gn, "fetch_modes", lambda ids, cache, **k: dict(cache, **{i: ("Online co-op",) for i in ids})), \
                    patch.object(gn, "save_modes", lambda cache, path=None: None):
                assert night.paste_code("lets play tonight " + friend_code)
                for _ in range(60):
                    settle()
                    time.sleep(0.05)
                    if night.rows and night.rows[0].modes:
                        break
            assert "can all play 1 game" in night.headline.text(), night.headline.text()
            assert night.rows[0].modes == ("Online co-op",), night.rows[0].modes
            assert window.grab().save(str(args.output / "ready-room-game-night.png"))
            squad.squad_views[0].click()
            window.settings = dict(window.settings, game_night_friends=[])

            # Empty screens offer the next step.
            window.navigate("Other Storage")
            settle()
            step = window.storage_notice.property("gg_next_step")
            if not window._shown_storage:
                assert step is not None and step.isVisible() and step.text() == "Scan Other Storage", step
                assert window.grab().save(str(args.output / "shell-next-step.png"))
            window.navigate("Games")
            settle()

            # Right-click "Ask the assistant about this": answered in the pop-out from the row itself.
            from gg_desktop import ask_about, assistant_page, assistant_popout
            from PySide6.QtWidgets import QMenu
            menu = QMenu(window)
            off = ask_about.add_to_menu(menu, window, "storage", SimpleNamespace(name="x"))
            assert not off.isEnabled() and "turn on the AI Assistant" in off.text()
            window.settings = dict(window.settings, assistant_enabled=True)
            row = SimpleNamespace(name="Battle.net Cache", path=r"C:\ProgramData\Battle.net\Cache", size=4096,
                                  related="Battle.net", category="Launcher cache", summary="Launcher cache folder")
            route = window.current_route
            assert ask_about.ask(window, "storage", row)
            settle()
            pop = assistant_popout.current(window)
            assert pop is not None and pop.isVisible()
            chat = assistant_page.current_chat(window)
            assert chat["messages"][-1]["role"] == "assistant" and "Battle.net Cache is in Other Storage" in chat["messages"][-1]["text"]
            assert window.current_route == route, "Asking never switches the tab"
            assert pop.grab().save(str(args.output / "shell-ask-about.png"))
            pop.close()
            settle()
            window.settings = dict(window.settings, assistant_enabled=False)

            # Update from inside the app: ask, download with the Updater's checks, pop-up, ask, start installer, quit.
            from updater import gg_updater as up
            from gg_desktop import update_install
            release = {"tag": "preview-run-99", "setup": {"url": "u", "size": 2 * 1048576}, "sum": {"url": "s", "size": 80}}
            setup_file = Path(tempfile.mkdtemp()) / "GameGrave-Crimson-Preview-Setup.exe"
            setup_file.write_bytes(b"x")
            questions, started, quits = [], [], []

            def fake_download(rel, token, folder, expected, progress=None, opener=None):
                progress(1048576, 2 * 1048576)
                return setup_file
            with patch.object(up, "find_token", lambda: ""), patch.object(up, "list_releases", lambda t, opener=None: [1]), \
                    patch.object(up, "pick_release", lambda r: release), \
                    patch.object(up, "fetch_checksum", lambda r, t, opener=None: "ab" * 32), \
                    patch.object(up, "download_setup", fake_download), \
                    patch.object(type(window), "confirm", lambda self, t, text, **_: questions.append(text) or True), \
                    patch("subprocess.Popen", lambda *a, **k: started.append(a[0])), \
                    patch.object(comfort, "quit_app", lambda w: quits.append(1)):
                update_install.start(window)
                for _ in range(100):
                    settle()
                    time.sleep(0.05)
                    if getattr(window, "_update_ready", None):
                        break
                assert window._update_ready == (str(setup_file), "preview-run-99"), getattr(window, "_update_ready", None)
                assert "SHA-256" in questions[0] and "preview-run-99" in questions[0]
                toast = comfort.state_of(window).toast
                assert toast.action_button.text() == "Install now"
                assert window.grab().save(str(args.output / "shell-update-ready.png"))
                toast.action_button.click()
                settle()
                assert "Game Grave closes" in questions[-1]
                assert started and started[0][0] == "powershell.exe" and "-EncodedCommand" in started[0], started
                assert quits == [1]
            window._update_ready = None

            # Undo right after a removal: a new Recycle Bin record pops up with Undo, which asks first and then
            # checks and restores through the recovery engine (both faked here; nothing on disk moves).
            import recovery
            records = [{"id": "old", "path": r"C:\Games\kept.txt", "size": 1}]
            calls = []
            with patch.object(recovery, "get_records", lambda: list(records)), \
                    patch.object(recovery, "check_restore", lambda rid: calls.append(("check", rid)) or "AVAILABLE"), \
                    patch.object(recovery, "restore", lambda rid: calls.append(("restore", rid)) or "RESTORED"):
                window.cleaning = True
                records.append({"id": "new", "path": r"D:\Mods\big.zip", "size": 4096})
                window.cleaning = False
                toast = comfort.state_of(window).toast
                assert toast is not None and toast.isVisible() and getattr(toast, "action_button", None) is not None
                assert toast.action_button.text() == "Undo"
                assert window.grab().save(str(args.output / "shell-undo-toast.png"))
                asked = []
                with patch.object(type(window), "confirm", lambda self, title, text, **_: asked.append(text) or True):
                    toast.action_button.click()
                    for _ in range(100):
                        settle()
                        time.sleep(0.05)
                        if not window.cleaning and calls:
                            break
                assert asked and "big.zip" in asked[0] and "overwritten" in asked[0], asked
                assert calls == [("check", "new"), ("restore", "new")], calls
                assert "1 of 1 put back" in window.status.text(), window.status.text()
                # A job that removes nothing adds no record and shows no Undo.
                comfort.state_of(window).toast = None
                window.cleaning = True
                window.cleaning = False
                assert comfort.state_of(window).toast is None

            # Faster rescans: F5 on Games scans only games and keeps the rest of the last scan.
            window.navigate("Games")
            settle()
            kept_files, kept_saves = list(window.inventory.files), list(window.inventory.saves)
            from gg_desktop import backend as scan_backend
            seen = []
            real_scan = scan_backend.scan_inventory
            with patch("gg_desktop.app.scan_inventory", lambda *a, **k: seen.append(k.get("parts")) or real_scan(*a, **k)):
                QTest.keyClick(window, Qt.Key_F5)
                for _ in range(400):
                    settle()
                    time.sleep(0.05)
                    if not window.scanning:
                        break
            assert seen == [("games",)], seen
            assert window.inventory.files == kept_files and window.inventory.saves == kept_saves
            assert comfort.state_of(window).notices[0].title == "Quick scan finished"
            window._sync_scan_time()
            assert window.scan_time.text().startswith("Games scanned Today "), window.scan_time.text()
            menu = window._scan_menu()
            assert [a.text() for a in menu.actions()][:2] == ["Everything", "Games only"]
            menu.close()

            # Tray: closing hides the window and keeps it running; Quit closes it for real.
            tray = comfort.state_of(window).tray
            if tray is not None:
                window.close()
                settle()
                assert not window.isVisible() and comfort.state_of(window).told_tray
                comfort.show_window(window)
                settle()
                assert window.isVisible()
                labels = [a.text() for a in comfort.state_of(window).tray_menu.actions()]
                assert "Keep running when closed" in labels and "Quit Game Grave" in labels, labels
                comfort.quit_app(window)
                settle()
                assert not window.isVisible()
            else:
                print("NOTE: this machine has no system tray; tray checks skipped.")
                window._quitting = True
                window.close()
            settle()
    print("PASS: Back, Ctrl+1..9, shortcut list, notification centre with badge and pop-ups, Copy diagnostics, Undo after "
          "a removal, paused note and tray behave.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
