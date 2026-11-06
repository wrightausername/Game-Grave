"""Real Games UI controls and artwork, using only disposable game fixtures."""
from __future__ import annotations

import argparse
from dataclasses import replace
from io import BytesIO
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
    from PIL import Image
    from PySide6.QtCore import QCoreApplication, QEvent, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QComboBox, QPushButton
    from core import SteamGame, default_settings
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.games import fallback_artwork
    from gg_desktop.game_artwork import local_artwork, load_preferences
    from gg_desktop.models import merge_games
    from launchers import LauncherGame

    app = QApplication.instance() or QApplication([])
    def settle():
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
    def wait_for(predicate):
        deadline = time.monotonic() + 12
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(20)
        assert predicate(), "Games did not finish its task"
        settle()
    def idle(window):
        QTest.qWait(90)
        wait_for(lambda: not window.workers and not window.page.games.loading)
    def png(color):
        stream = BytesIO()
        Image.new("RGB", (200, 300), color).save(stream, format="PNG")
        return stream.getvalue()

    with tempfile.TemporaryDirectory(prefix="GG-games-live-") as temp:
        root = Path(temp)
        steam_root = root / "Steam"
        steam = []
        for ident, name in (("1091500", "Cyberpunk 2077"), ("292030", "The Witcher 3")):
            install = steam_root / "steamapps" / "common" / name
            install.mkdir(parents=True)
            manifest = steam_root / "steamapps" / ("appmanifest_" + ident + ".acf")
            manifest.write_text('"AppState" { "appid" "' + ident + '" "installdir" "' + name + '" "StateFlags" "4" }')
            steam.append(SteamGame(ident, name, str(steam_root), str(install), 1000, None, "Unknown"))
        local_cover = steam_root / "appcache" / "librarycache" / "1091500" / ("a" * 40)
        local_cover.mkdir(parents=True)
        supplied_art = Path(__file__).resolve().parents[1] / "gg_desktop" / "assets" / "ready_room"
        (local_cover / "library_600x900.jpg").write_bytes((supplied_art / "cyberpunk_portrait.png").read_bytes())
        epic_path, gog_path, unknown_path = root / "Epic" / "Control", root / "GOG" / "OfflineGame", root / "Custom" / "Unverified"
        for folder in (epic_path, gog_path, unknown_path):
            folder.mkdir(parents=True)
        (epic_path / "cover.png").write_bytes(png("#1F7D8C"))
        executable = gog_path / "Game.exe"
        executable.write_bytes(b"MZdisposable game fixture, never executed")
        other = [LauncherGame("Control", "Epic Games", str(epic_path), "catalog:control", None, "Manifest verified"),
                 LauncherGame("Offline Game", "GOG", str(gog_path), "gog123", 0, "Registry verified"),
                 LauncherGame("Unlisted Custom Game", "Custom library", str(unknown_path), "custom", None, "Not verified")]
        base = merge_games(steam, other)
        fake = base[0]
        extras = [replace(fake, key="fixture" + str(i), name=f"Synthetic Game {i:04}",
                          launcher="Fixture launcher", app_id="fixture" + str(i),
                          install_path=str(root / ("Fixture" + str(i))), capabilities=("inspect",),
                          claimed_by=("Fixture launcher",)) for i in range(1002)]
        all_games = base + extras
        custom_cover = root / "chosen-cover.png"
        custom_cover.write_bytes(png("#7134A8"))
        source_before = custom_cover.read_bytes()

        with patch("gg_desktop.app.load_settings", side_effect=default_settings), \
             patch("gg_desktop.game_artwork.artwork_dir", return_value=root / "Preferences" / "Games"), \
             patch("gg_desktop.games.artwork_roots", return_value=[steam_root]), \
             patch("gg_desktop.game_artwork._request", side_effect=AssertionError("No network during rendering")) as network, \
             patch.object(CrimsonWindow, "info"), patch.object(CrimsonWindow, "error") as errors, \
             patch.object(CrimsonWindow, "_approve_recycle") as recycle:
            window = CrimsonWindow()
            window.show()
            window.resize(1450, 900)
            window.inventory.steam = steam
            window.inventory.other = other
            window.inventory.games = all_games
            window.inventory.scanned_at = "Disposable Games QA"
            window.navigate("Games")
            settle()
            idle(window)
            assert len(window.page.games.rows) == 1007
            assert len(window._shown_games) == 500
            assert window.page.games.paging.isVisible()
            assert all(not window.game_table.item(i, 0).icon().isNull() for i in range(window.game_table.rowCount()))
            assert not window.page.games.art_picture.pixmap().isNull()
            assert window.game_table.horizontalHeaderItem(0).text() == "GAME"
            assert window.game_table.rowHeight(0) == 36
            network.assert_not_called()
            window.page.games.change_page(1)
            assert window.page.games.index == 1 and len(window._shown_games) == 500
            window.page.games.change_page(1)
            assert window.page.games.index == 2 and len(window._shown_games) == 7
            assert all(not window.game_table.item(i, 0).icon().isNull() for i in range(7))
            window.game_search.setText("SYNTHETIC 1001")
            assert len(window._shown_games) == 1 and window._shown_games[0].name == "Synthetic Game 1001"
            kept = window._shown_games[0].key
            window.game_sort.setCurrentText("Name A to Z")
            assert window.page.games.selected().key == kept
            window.game_search.setText("no matching title anywhere")
            assert window.game_table.rowCount() == 0
            window.game_search.clear()
            window.game_filter.setCurrentText("GOG")
            assert len(window._shown_games) == 1 and window.game_table.item(0, 2).text() == "0 B"
            window.game_filter.setCurrentText("All launchers")

            def pick(record):
                window.game_filter.setCurrentText("All launchers")
                window.game_search.setText(record.install_path)
                idle(window)
                assert window.page.games.selected().key == record.key
                return window.page.games
            cyberpunk = next(g for g in base if g.app_id == "1091500")
            witcher = next(g for g in base if g.app_id == "292030")
            epic = next(g for g in base if g.launcher == "Epic Games")
            gog = next(g for g in base if g.launcher == "GOG")
            unknown = next(g for g in base if g.launcher == "Custom library")
            control = pick(cyberpunk)
            assert control.pictures[cyberpunk.key][1] == "Local Steam library artwork"
            assert not control.art_picture.pixmap().isNull()
            control = pick(epic)
            assert control.pictures[epic.key][1] == "Local game-folder artwork"
            control = pick(unknown)
            assert "fallback" in control.art_label.text().casefold()
            assert not control.art_picture.pixmap().isNull()
            assert fallback_artwork(cyberpunk).toImage() != fallback_artwork(unknown).toImage()
            assert not next(b for b in window.game_details.findChildren(QPushButton) if b.text() == "Launch game").isEnabled()

            control = pick(witcher)
            with patch("gg_desktop.games.QFileDialog.getOpenFileName", return_value=(str(custom_cover), "PNG")):
                control.choose_picture(witcher)
                wait_for(lambda: not window.workers)
            assert local_artwork(witcher).source == "Your chosen artwork"
            assert control.art_label.text() == "Your chosen artwork"
            assert custom_cover.read_bytes() == source_before

            request_url = []
            def official(url, limit):
                request_url.append(url)
                if "IStoreBrowseService" in url:
                    return json.dumps({"response": {"store_items": [{"appid": 292030, "name": "The Witcher 3",
                        "assets": {"library_capsule": "c" * 40 + "/library_600x900.jpg"}}]}}).encode()
                return (supplied_art / "witcher_portrait.png").read_bytes()
            control.reset_picture(witcher)
            idle(window)
            with patch("gg_desktop.game_artwork._request", side_effect=official):
                control.download_artwork([witcher])
                wait_for(lambda: not control.downloading and not window.workers)
                idle(window)
            assert request_url and local_artwork(witcher).source == "Cached official Steam artwork"
            assert control.pictures[witcher.key][1] == "Cached official Steam artwork"
            network.assert_not_called()

            control = pick(gog)
            with patch("gg_desktop.games.QFileDialog.getOpenFileName", return_value=(str(executable), "EXE")), \
                 patch("gg_desktop.games.os.startfile", create=True) as run:
                control.choose_executable(gog)
                run.assert_not_called()
            assert load_preferences()["executables"]
            with patch("gg_desktop.games.sys.platform", "win32"), patch("gg_desktop.games.os.startfile", create=True) as run:
                control.launch(gog)
                run.assert_called_once_with(str(executable), cwd=str(gog_path))

            control = pick(cyberpunk)
            with patch("gg_desktop.games.QDesktopServices.openUrl", return_value=True) as opened:
                control.launch(cyberpunk)
                assert opened.call_args[0][0].toString() == "steam://rungameid/1091500"
                with patch.object(window, "confirm", return_value=False):
                    control.uninstall(cyberpunk)
                assert opened.call_count == 1
                with patch.object(window, "confirm", return_value=True):
                    control.uninstall(cyberpunk)
                assert opened.call_args[0][0].toString() == "steam://uninstall/1091500"
                manifest = steam_root / "steamapps" / "appmanifest_1091500.acf"
                original_manifest = manifest.read_text()
                manifest.write_text('"AppState" { "appid" "999" }')
                before = opened.call_count
                with patch.object(window, "confirm", return_value=True):
                    control.uninstall(cyberpunk)
                assert opened.call_count == before
                manifest.write_text(original_manifest)
            assert errors.call_count == 1

            control = pick(witcher)
            control.show_dna(witcher)
            settle()
            assert window.current_route == "Game DNA"
            chooser = window.page.findChild(QComboBox)
            assert chooser.currentText().startswith("The Witcher 3")
            window.navigate("Games")
            settle()
            idle(window)
            pick(witcher)
            assert window.page.games.pictures[witcher.key][1] == "Cached official Steam artwork"
            window.activateWindow()
            QTest.keyClick(window, Qt.Key_K, Qt.ControlModifier)
            settle()
            assert window.game_search.hasFocus()
            QTest.keyClick(window.game_search, Qt.Key_Escape)
            settle()
            assert not window.game_search.text()

            window.inventory.games = base
            window.navigate("Games")
            settle()
            idle(window)
            old_control = window.page.games
            def refreshed_picker(*_args, **_kwargs):
                window.navigate("Games")
                return str(custom_cover), "PNG"
            with patch("gg_desktop.games.QFileDialog.getOpenFileName", side_effect=refreshed_picker):
                old_control.choose_picture(witcher)
            settle()
            idle(window)
            assert window.page.games is not old_control
            assert local_artwork(witcher).source == "Cached official Steam artwork", "A stale picker overwrote artwork after a page refresh"
            for width, height in ((1450, 900), (1280, 790), (960, 650)):
                window.resize(width, height)
                settle()
                assert window.page.horizontalScrollBar().maximum() == 0
                assert all(not window.game_table.item(i, 0).icon().isNull() for i in range(window.game_table.rowCount()))
                assert window.grab().save(str(args.output / f"games-functional-{width}.png"))
                window.page.ensureWidgetVisible(window.game_details)
                settle()
                assert window.grab().save(str(args.output / f"games-artwork-details-{width}.png"))
                window.page.verticalScrollBar().setValue(0)
            assert window.inventory.games == base
            recycle.assert_not_called()
            assert executable.read_bytes() == b"MZdisposable game fixture, never executed"
            assert custom_cover.read_bytes() == source_before
            network.assert_not_called()
            window.close()
            settle()
    print("PASS: 1,007-game paging/search/filter/sort/selection, artwork on every row and details, local/official/custom/offline art, "
          "persistent choices, launch handoff and revalidated Steam uninstall, exact DNA routing and 3 window sizes; no automatic network or game-file changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
