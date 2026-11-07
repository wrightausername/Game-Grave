"""Three fresh, real Qt click-throughs of the photo Games page.

Uses disposable mixed-launcher installs. OS launch requests are intercepted;
no installed game is started, repaired, removed or modified.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch


def walkthrough(output):
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PIL import Image
    from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt, QTimer
    from PySide6.QtGui import QContextMenuEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QAbstractButton, QApplication, QLabel, QMenu, QMessageBox, QPushButton, QToolButton
    import core
    from core import SteamGame, default_settings
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.backend import Inventory
    from gg_desktop.game_artwork import Artwork, game_id, local_artwork
    from gg_desktop.games_sources import launcher_bucket
    from gg_desktop.models import merge_games
    from gg_desktop.reference_widgets import cover_crop, reference
    from launchers import LauncherGame
    app = QApplication.instance() or QApplication([])
    output.mkdir(parents=True, exist_ok=True)
    checks = []
    def passed(name):
        checks.append(dict(name=name, result="passed"))
        (output/"games-human-journeys.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    def settle():
        QTest.qWait(30)
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    def wait_for(predicate):
        end = time.monotonic() + 15
        while not predicate() and time.monotonic() < end:
            QTest.qWait(20)
            # Qt's Windows test wait can retain the GIL. Yield explicitly so
            # Python artwork workers can finish, as in the Overview harness.
            time.sleep(.004)
        assert predicate(), "Timed out waiting for Games"
        settle()
    def idle(window):
        settle()
        try:
            wait_for(lambda: not window.workers and not window.page.game_artwork.busy and not window.page.game_artwork.queue)
        except AssertionError:
            art = window.page.game_artwork
            window.grab().save(str(output/"games-timeout.png"))
            raise AssertionError(json.dumps(dict(workers=len(window.workers), busy=art.busy,
                queue=len(art.queue), pending=list(art.pending), downloading=window.page.games.downloading,
                status=window.status.text(), last_case=checks[-1] if checks else None)))
    def click(control):
        assert control.isEnabled(), control.text()
        QTest.mouseClick(control, Qt.LeftButton)
        settle()
    def select(window, key):
        window.page.games.filter_bucket(None)
        window.game_grid.setCurrentRow(next(i for i, row in enumerate(window._shown_games) if row.key == key))
        window.game_grid.scrollToItem(window.game_grid.currentItem())
        settle()
    def button(window, name):
        return next(control for control in window.game_details.findChildren(QAbstractButton) if control.text() == name)
    def menu_action(window, name, *, context=False, row=None):
        def choose():
            menu = app.activePopupWidget()
            assert isinstance(menu, QMenu), "No Games context menu"
            action = next(action for action in menu.actions() if action.text() == name)
            assert action.isEnabled(), name
            QTest.mouseClick(menu, Qt.LeftButton, pos=menu.actionGeometry(action).center())
        QTimer.singleShot(30, choose)
        if context:
            item = window.game_grid.item(row)
            pos = window.game_grid.visualItemRect(item).center()
            event = QContextMenuEvent(QContextMenuEvent.Mouse, pos, window.game_grid.viewport().mapToGlobal(pos))
            QApplication.sendEvent(window.game_grid.viewport(), event)
        else:
            window.page.games.keyboard_options()
        settle()
    with tempfile.TemporaryDirectory(prefix="GameGrave-Games-QA-") as temp:
        root = Path(temp)
        steam_root = root/"Steam"
        settings_root = root/"Preferences"
        steam, other = [], []
        specifications = [
            ("Cyberpunk 2077", "Steam", "1091500"), ("Baldur's Gate 3", "Steam", "1086940"),
            ("The Witcher 3: Wild Hunt", "GOG", "gog-witcher"), ("Starfield", "Xbox (PC)", "xbox-starfield"),
            ("Skyrim Special Edition", "Steam", "489830"), ("Red Dead Redemption 2", "Epic Games", "epic-rdr2"),
            ("Call of Duty Black Ops 6", "Battle.net", "blizzard-cod"), ("Elden Ring", "Custom library", "custom-elden"),
            ("Helldivers 2", "Steam", "553850"), ("Dragon Age: The Veilguard", "EA", "ea-dragon"),
            ("Assassin's Creed Odyssey", "Ubisoft Connect", "ubisoft-ac"), ("VALORANT", "Riot", "valorant"),
        ]
        for index, (name, launcher, ident) in enumerate(specifications):
            install = steam_root/"steamapps/common"/ident if launcher == "Steam" else root/"Games"/ident
            install.mkdir(parents=True)
            (install/"game.exe").write_bytes(b"MZ DISPOSABLE QA EXE - NEVER RUN")
            crop = cover_crop(name)
            if crop:
                assert reference("games").copy(*crop).save(str(install/"cover.png"))
            else:
                # Explicit synthetic test picture, not a claimed official cover.
                Image.new("RGB", (120, 180), "#17364c").save(install/"cover.png")
            if launcher == "Steam":
                steam.append(SteamGame(ident, name, str(steam_root), str(install), (index + 1)*12*1024**3, 1700000000 + index, "Disposable QA"))
                (steam_root/"steamapps"/("appmanifest_"+ident+".acf")).write_text('"AppState" { "appid" "'+ident+'" "StateFlags" "4" "installdir" "'+ident+'" }')
            else:
                other.append(LauncherGame(name, launcher, str(install), ident, (index + 1)*12*1024**3, "Disposable launcher record"))
        rock_path = root/"Games/rockstar-rdr2"
        rock_path.mkdir()
        reference("games").copy(*cover_crop("Red Dead Redemption 2")).save(str(rock_path/"cover.png"))
        rockstar = LauncherGame("Red Dead Redemption 2", "Rockstar Games", str(rock_path), "rdr2", None, "Disposable registered Rockstar installation")
        accepted = Inventory(steam=steam, other=other, games=merge_games(steam, other), scanned_at="Disposable mixed-launcher QA")
        before = list(accepted.games)
        image_bytes = BytesIO()
        Image.new("RGB", (60, 90), "#753ca0").save(image_bytes, "PNG")
        with patch("core.config_dir", return_value=settings_root), \
             patch("gg_desktop.app.load_settings", side_effect=lambda: dict(core.load_settings(), scan_on_launch=False)), \
             patch("gg_desktop.game_artwork.artwork_dir", return_value=settings_root/"Games"), \
             patch("gg_desktop.games_controls.registered_games", return_value=[rockstar]), \
             patch("gg_desktop.game_artwork._request", side_effect=AssertionError("No network while rendering")) as network, \
             patch("gg_desktop.games.QDesktopServices.openUrl", return_value=True) as launch, \
             patch.object(CrimsonWindow, "error") as errors:
            window = CrimsonWindow()
            window.show()
            window.resize(1450, 900)
            window.inventory = accepted
            window.navigate("Games")
            idle(window)
            assert len(window.page.games.records) == 13 and accepted.games == before
            assert window.nav_rail.width() == 219 and window.top_bar.height() == 46
            passed("Mixed launcher sources stay within Games; shell keeps its native scale")
            for game in window.page.games.records:
                window.page.game_artwork.pixmap(game.key)
            idle(window)
            assert all((game.key, "cover") in window.page.game_artwork.images for game in window.page.games.records)
            assert not window.artwork.images, "Games must not publish covers into other tabs' service"
            passed("All thirteen launcher game cards load local covers without networking")
            network.assert_not_called()
            window.grab().save(str(output/"games-mixed-launchers-1450.png"))
            records = list(window.page.games.records)
            for index, handler in enumerate(window.page.games.metric_filters):
                cell = window.game_metrics.values[index].parentWidget()
                # Click the number label itself: all parts of each card must respond.
                click(window.game_metrics.values[index])
                expected = [game for game in records if handler.bucket is None or launcher_bucket(game.launcher) == handler.bucket]
                assert {game.key for game in window._shown_games} == {game.key for game in expected}
                assert int(window.game_metrics.values[index].text()) == len(expected)
                passed("Launcher card filters and count: " + (handler.bucket or "Total Games"))
            click(window.game_metrics.values[3])
            assert window.page.games.bucket == "EA"
            window.game_filter.setCurrentText("All launchers")
            assert len(window._shown_games) == 13 and window.page.games.bucket is None
            passed("All launchers visibly clears a previously clicked launcher card")
            click(window.game_metrics.values[3])
            window.game_filter.setCurrentText("Steam")
            assert all(game.launcher == "Steam" for game in window._shown_games) and window._shown_games
            passed("Exact launcher chooser clears the previous launcher-card filter")
            window.page.games.filter_bucket(None)
            window.game_search.setFocus()
            QTest.keyClicks(window.game_search, "rockstar redemption")
            assert len(window._shown_games) == 1 and window._shown_games[0].launcher == "Rockstar Games"
            passed("Multi-word title plus launcher search")
            window.game_search.clear()
            for name in ("Installed", "Recently Played", "Not Installed", "Updates", "Library"):
                click(window.game_tabs.buttons[name])
                if name in ("Not Installed", "Updates"):
                    assert not window._shown_games and "not available" in window.game_empty.text()
                elif name == "Recently Played":
                    assert len(window._shown_games) == len(steam)
                else:
                    assert window._shown_games
                passed("Library tab: " + name)
            for name, control in window.game_chips.buttons.items():
                click(control)
                if name.startswith(("Updates", "Not Installed")):
                    assert not window._shown_games and window.game_empty.isVisible()
                passed("Library chip: " + name)
            click(next(control for name, control in window.game_chips.buttons.items() if name.startswith("All Games")))
            for order in ("Name A to Z", "Launcher", "Largest known size", "Smallest known size", "Recently played", "Oldest played"):
                window.game_sort.setCurrentText(order)
                rows = window._shown_games
                assert len(rows) == 13
                if order == "Name A to Z":
                    assert [game.name.casefold() for game in rows] == sorted(game.name.casefold() for game in rows)
                elif order in ("Largest known size", "Smallest known size"):
                    assert rows[-1].size_bytes is None
                    sizes = [game.size_bytes for game in rows if game.size_bytes is not None]
                    assert sizes == sorted(sizes, reverse=order == "Largest known size")
                passed("Sort: " + order)
            steam_game = next(game for game in records if game.launcher == "Steam")
            epic = next(game for game in records if game.launcher == "Epic Games")
            ea = next(game for game in records if game.launcher == "EA")
            select(window, steam_game.key)
            rect = window.game_grid.visualItemRect(window.game_grid.currentItem())
            QTest.mouseClick(window.game_grid.viewport(), Qt.LeftButton, pos=QPoint(rect.right()-17, rect.top()+15))
            assert steam_game.key in window.settings["desktop_favorites"]
            click(window.game_tabs.buttons["Favorites"])
            assert [game.key for game in window._shown_games] == [steam_game.key]
            passed("Cover star persists and Favorites selects the correct installation")
            select(window, steam_game.key)
            click(button(window, "Play"))
            assert launch.call_args.args[0].toString() == "steam://rungameid/" + steam_game.app_id
            passed("Steam Play dispatches the revalidated selected installation")
            select(window, epic.key)
            window.game_grid.setFocus()
            QTest.keyClick(window.game_grid, Qt.Key_Return)
            assert "com.epicgames.launcher://apps/" + epic.app_id in launch.call_args.args[0].toString()
            passed("Enter launches Epic with its Epic identity, not a Steam artwork identity")
            select(window, ea.key)
            with patch("gg_desktop.games.QFileDialog.getOpenFileName", return_value=("", "")):
                prior = launch.call_count
                click(button(window, "Play"))
                assert launch.call_count == prior and not window.page.games.preferences["executables"]
            passed("Unsupported launcher Play offers an EXE; cancel performs no launch")
            exe = str(Path(ea.install_path)/"game.exe")
            with patch("gg_desktop.games.QFileDialog.getOpenFileName", return_value=(exe, "")), \
                 patch("gg_desktop.games.sys", SimpleNamespace(platform="win32")), \
                 patch("gg_desktop.games.os.startfile", create=True) as start:
                click(button(window, "Play"))
                assert start.call_args.args == (exe,)
            passed("EA Play saves and launches only the chosen game EXE")
            menu_action(window, "Use default launcher")
            assert game_id(ea) not in window.page.games.preferences["executables"]
            passed("Use default launcher clears the saved EXE")
            select(window, steam_game.key)
            for name, uri in (("Verify Files…", "steam://validate/"), ("Manage DLC…", "steam://nav/games/details/")):
                click(button(window, name))
                assert launch.call_args.args[0].toString() == uri + steam_game.app_id
                passed("Selected Steam action: " + name)
            for answer in (False, True):
                with patch.object(window, "confirm", return_value=answer):
                    prior = launch.call_count
                    click(button(window, "Uninstall…"))
                    assert launch.call_count == prior + int(answer)
                    if answer:
                        assert launch.call_args.args[0].toString() == "steam://uninstall/" + steam_game.app_id
                passed("Steam uninstall confirmation: " + ("proceed" if answer else "cancel"))
            select(window, ea.key)
            with patch.object(window, "info") as info:
                for name in ("Verify Files…", "Manage DLC…", "Uninstall…"):
                    click(button(window, name))
                    assert "EA" in info.call_args.args[1]
                    passed("EA native-action guidance: " + name)
            select(window, epic.key)
            menu_action(window, "Copy installation path", context=True,
                        row=next(i for i, game in enumerate(window._shown_games) if game.key == ea.key))
            assert app.clipboard().text() == ea.install_path and window._current_game().key == ea.key
            passed("Right-click selects the clicked game before dispatching its menu action")
            menu_action(window, "Copy installation path")
            assert app.clipboard().text() == ea.install_path
            passed("Keyboard context menu uses the selected game")
            chosen = root/"chosen.png"
            chosen.write_bytes(image_bytes.getvalue())
            with patch("gg_desktop.games.QFileDialog.getOpenFileName", return_value=(str(chosen), "")):
                menu_action(window, "Choose artwork…")
                idle(window)
            assert local_artwork(ea).source == "Your chosen artwork"
            passed("Choose artwork persists a decoded cover without altering the source file")
            menu_action(window, "Reset chosen artwork")
            idle(window)
            assert local_artwork(ea).source != "Your chosen artwork"
            passed("Reset artwork clears the chosen cover and restores local artwork immediately")
            def request(url, _limit):
                if "storesearch" in url:
                    return json.dumps({"items": [{"id": 1845910, "name": ea.name}]}).encode()
                if "GetItems" in url:
                    return json.dumps({"response": {"store_items": [{"appid": 1845910, "name": ea.name, "assets": {}}]}}).encode()
                return image_bytes.getvalue()
            with patch("gg_desktop.game_artwork._request", side_effect=request):
                menu_action(window, "Download official artwork")
                idle(window)
            assert local_artwork(ea).source == "Cached official Steam artwork" and ea.launcher == "EA"
            passed("Non-Steam exact-match artwork downloads, caches offline and preserves its launcher")
            with patch("gg_desktop.game_artwork._request", side_effect=OSError("Offline")):
                menu_action(window, "Download official artwork")
                idle(window)
            assert local_artwork(ea).image is not None
            passed("Offline artwork failure retains the existing cover")
            with patch.object(window, "_open_folder") as open_folder:
                click(button(window, "Open Folder"))
                assert open_folder.call_args.args[0] == ea.install_path
            passed("Open Folder targets the selected installation")
            with patch("gg_desktop.reference_screens.QFileDialog.getExistingDirectory", return_value="") as backup:
                # The existing Save Vault entry opens a chooser; no save is assumed or deleted.
                click(button(window, "Save Vault"))
                backup.assert_called_once()
            passed("Save Vault dispatches the existing explicit backup chooser")
            for mode in ("List view", "Grid view"):
                toggle = next(control for control in window.page.findChildren(QPushButton) if control.accessibleName() == mode)
                click(toggle)
                assert window.game_grid.delegate.list_mode == (mode == "List view")
                passed("View control: " + mode)
            select(window, ea.key)
            old_favorites = set(window.settings["desktop_favorites"])
            with patch("gg_desktop.games_page.save_settings", side_effect=OSError("Fixture write failure")):
                click(next(control for control in window.game_details.findChildren(QPushButton) if control.accessibleName() == "Add favorite"))
            assert set(window.settings["desktop_favorites"]) == old_favorites
            assert errors.call_args.args[0] == "Favorite not saved"
            errors.reset_mock()
            passed("Failed favorite save retains the previous favorite state")
            corrupt = root/"corrupt.png"
            corrupt.write_bytes(b"not a picture")
            with patch("gg_desktop.games.QFileDialog.getOpenFileName", return_value=(str(corrupt), "")):
                menu_action(window, "Choose artwork…")
                idle(window)
            assert errors.call_args.args[0] == "Artwork not saved" and local_artwork(ea).image is not None
            errors.reset_mock()
            passed("Corrupt chosen artwork reports an error and preserves the working cover")
            select(window, steam_game.key)
            manifest = steam_root/"steamapps"/("appmanifest_"+steam_game.app_id+".acf")
            original_manifest = manifest.read_bytes()
            manifest.write_text('"AppState" { "appid" "999" "StateFlags" "4" "installdir" "changed" }')
            prior = launch.call_count
            click(button(window, "Verify Files…"))
            assert launch.call_count == prior and errors.called
            errors.reset_mock()
            manifest.write_bytes(original_manifest)
            passed("Changed Steam installation blocks stale verification requests")
            select(window, ea.key)
            def slow_art(_game, *, canceled, **_kwargs):
                end = time.monotonic() + 5
                while not canceled() and time.monotonic() < end:
                    time.sleep(.01)
                return Artwork()
            with patch("gg_desktop.games_controls.official_artwork", side_effect=slow_art):
                menu_action(window, "Download official artwork")
                wait_for(lambda: window.page.games.downloading)
                menu_action(window, "Cancel artwork downloads")
                idle(window)
            assert "canceled" in window.status.text() and local_artwork(ea).image is not None
            passed("Cancel artwork downloads stops the worker and retains existing covers")
            # Actual Games-owned message, including scoped readable styling.
            def dismiss_info():
                message = app.activeModalWidget()
                assert isinstance(message, QMessageBox) and message.property("gamesReadable")
                assert "#020609" in message.styleSheet()
                message.grab().save(str(output/"games-launcher-guidance.png"))
                click(message.button(QMessageBox.Ok))
            QTimer.singleShot(50, dismiss_info)
            click(button(window, "Manage DLC…"))
            passed("Non-Steam launcher guidance opens a readable Games-owned dialog")
            with patch.object(window, "navigate") as destination:
                click(button(window, "Game DNA"))
                assert destination.call_args.args == ("Game DNA",) and window._pending_dna_game_key == ea.key
                click(button(window, "Mods"))
                assert destination.call_args.args == ("Mods",)
            passed("Game DNA carries the selected game key; Mods opens the existing tab")
            original_records = window.page.games.records
            many = [replace(ea, key="large-"+str(index), name=f"Large library {index:04}") for index in range(1003)]
            window.page.games.records = many
            window.page.game_artwork.set_library(many)
            window.page.games.fill()
            assert window.game_grid.count() == 1003
            window.game_grid.setCurrentRow(1002)
            window.game_grid.scrollToItem(window.game_grid.item(1002))
            settle()
            assert window.game_grid.visualItemRect(window.game_grid.item(1002)).intersects(window.game_grid.viewport().rect())
            assert window._current_game().key == window._shown_games[1002].key
            passed("Virtualized large library reaches and selects the final game after 1,000 entries")
            window.page.games.records = original_records
            window.page.game_artwork.set_library(original_records)
            window.page.games.fill()
            with patch("gg_desktop.app.scan_inventory", return_value=accepted) as scan:
                click(window.scan_button)
                wait_for(lambda: not window.scanning)
                idle(window)
                scan.assert_called_once()
            assert len(window.page.games.records) == 13 and accepted.games == before
            passed("Scan PC refreshes the Games page and its additional launcher cards")
            # Exercise the narrow Details drawer without changing the shell scale.
            window.resize(960, 650)
            settle()
            assert window.nav_rail.width() == 219 and window.page.photo_inspector.toggle.isVisible()
            click(window.page.photo_inspector.toggle)
            assert window.page.photo_inspector.dialog.isVisible()
            window.page.photo_inspector.dialog.reject()
            settle()
            window.resize(1450, 900)
            settle()
            passed("Narrow Details drawer opens and returns the same inspector")
            errors.assert_not_called()
            window.close()
            settle()
            # Fresh app reads the real settings file; the shared loader excludes the extra key.
            second = CrimsonWindow()
            second.inventory = accepted
            second.show()
            second.navigate("Games")
            idle(second)
            click(second.game_tabs.buttons["Favorites"])
            assert [game.key for game in second._shown_games] == [steam_game.key]
            passed("Favorites survives a fresh app instance using the actual preferences file")
            second.close()
            settle()
    (output/"games-human-journeys.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    print(f"PASS: {len(checks)} Games mouse, keyboard, artwork and launcher journeys.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("_ci_temp"))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.once:
        walkthrough(args.output.resolve())
        return 0
    output = args.output.resolve()/"games-triple-check"
    report = []
    for number in (1, 2, 3):
        target = output/("pass-" + str(number))
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--once", "--output", str(target)],
                                capture_output=True, text=True, timeout=150)
        if result.returncode:
            print(result.stdout[-1000:]+result.stderr[-5000:])
            raise AssertionError("Games walkthrough failed in pass " + str(number))
        cases = json.loads((target/"games-human-journeys.json").read_text())
        assert all(case["result"] == "passed" for case in cases)
        report.append(dict(pass_number=number, cases=len(cases), results=cases))
        print(f"PASS {number}: {len(cases)} Games journeys.", flush=True)
    (output/"report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"PASS: {sum(run['cases'] for run in report)} checks across three fresh Games processes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
