"""Validate restored photo composition and live behavior, not the fallback UI."""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("_ci_temp"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo))
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QCoreApplication, QEvent, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QPushButton
    from core import SteamGame, default_settings
    from gg_desktop.app import CrimsonWindow, ROUTES
    from gg_desktop.backend import Inventory
    from gg_desktop.models import merge_games
    from gg_desktop.reference_widgets import CoverGrid, reference
    from gg_desktop.mods import ModDetails
    from tests.test_mods_functionality import mo2_fixture
    from tests.test_old_files_functionality import drive_fixture, old_file

    app = QApplication.instance() or QApplication([])
    def settle():
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
    def wait_for(predicate):
        deadline = time.monotonic() + 20
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
            time.sleep(.004)
        assert predicate(), "Photo UI operation did not finish"
        settle()
    def click(parent, text):
        control = next(b for b in parent.findChildren(QPushButton) if b.text() == text)
        assert control.isEnabled(), "Disabled: " + text
        control.click()
        settle()
    def idle(window):
        QTest.qWait(60)
        wait_for(lambda: not window.workers and not window.artwork.busy and not window.artwork.queue)
    def screenshot(window, name):
        settle()
        assert window.grab().save(str(args.output / name))

    for name in ("games", "mods", "old_files", "other_storage", "captures", "graveyard", "dna", "undo"):
        assert not reference(name).isNull() and reference(name).size().width() == 1280

    with tempfile.TemporaryDirectory(prefix="GG-photo-UI-") as temp:
        root = Path(temp)
        drive, other_drive, home, downloads, drives = drive_fixture(root)
        records = [old_file(downloads / f"old-mod-{i:04}.zip") for i in range(507)]
        deep = old_file(drive / "OtherFiles" / "deep.log")
        mod_inventory, storage, profiles, ini = mo2_fixture(root)
        steam_root = root / "Steam"
        titles = [("1091500", "Cyberpunk 2077"), ("1086940", "Baldur's Gate 3"),
                  ("292030", "The Witcher 3: Wild Hunt"), ("1716740", "Starfield"),
                  ("489830", "Skyrim Special Edition"), ("1174180", "Red Dead Redemption 2"),
                  ("2933620", "Call of Duty: Black Ops 6"), ("1245620", "Elden Ring"),
                  ("553850", "Helldivers 2"), ("1845910", "Dragon Age: The Veilguard")]
        steam = []
        for index, (ident, name) in enumerate(titles):
            # App IDs are valid Windows folders, including titles containing ':'.
            install = steam_root / "steamapps" / "common" / ident
            install.mkdir(parents=True)
            (steam_root / "steamapps" / ("appmanifest_" + ident + ".acf")).write_text(
                '"AppState" { "appid" "' + ident + '" "installdir" "' + ident + '" "StateFlags" "4" }')
            steam.append(SteamGame(ident, name, str(steam_root), str(install), 1000000 + index,
                                   time.time() - index * 86400, "Disposable photo fixture"))
        ini.write_text(ini.read_text().replace(mod_inventory.games[0].install_path, steam[0].install_path))
        inventory = Inventory(steam=steam, games=merge_games(steam, []), mods=mod_inventory.mods,
                              files=records[:1], scanned_at="2026-11-06 12:00")
        settings = default_settings()
        settings["scan_folder"] = str(downloads)
        settings["never_touch"] = []
        with patch("gg_desktop.app.load_settings", return_value=settings), \
             patch("gg_desktop.old_files.local_drives", return_value=drives), \
             patch("gg_desktop.old_files_data.local_drives", return_value=drives), \
             patch("gg_desktop.old_files.save_settings"), patch("core.save_settings"), \
             patch("gg_desktop.reference_library.save_settings"), \
             patch("gg_desktop.ready_room_services.config_dir", return_value=root / "Preferences"), \
             patch("gg_desktop.game_artwork.artwork_dir", return_value=root / "Artwork"), \
             patch("gg_desktop.game_artwork._request", side_effect=AssertionError("No automatic network")) as network, \
             patch.object(CrimsonWindow, "info") as info, patch.object(CrimsonWindow, "error") as errors, \
             patch.object(CrimsonWindow, "confirm", return_value=False) as confirm:
            window = CrimsonWindow()
            window.inventory = inventory
            window.show()
            window.resize(1280, 720)
            window.navigate("Games")
            idle(window)
            assert window.windowFlags() & Qt.FramelessWindowHint
            assert window.nav_rail.width() == 219 and window.top_bar.height() == 46
            assert len(ROUTES) == 14 and isinstance(window.game_grid, CoverGrid)
            assert window.game_grid.count() == 10
            first = window.game_grid.visualItemRect(window.game_grid.item(0))
            point = window.game_grid.viewport().mapTo(window, first.topLeft())
            assert 237 <= point.x() <= 251 and 340 <= point.y() <= 360, (point.x(), point.y())
            screenshot(window, "photo-games-functional-1280.png")
            window.global_search.setText("Witcher")
            assert len(window._shown_games) == 1
            window.global_search.clear()
            window.game_tabs.buttons["Favorites"].click()
            assert not window._shown_games
            window.game_tabs.buttons["Library"].click()
            game = window._current_game()
            window._toggle_favorite(game)
            assert game.key in window.settings["desktop_favorites"]
            window.game_tabs.buttons["Favorites"].click()
            assert len(window._shown_games) == 1
            window.game_tabs.buttons["Library"].click()
            with patch("gg_desktop.games.QDesktopServices.openUrl", return_value=True) as opened:
                window.page.games.launch(game)
                assert opened.call_args[0][0].toString() == "steam://rungameid/" + game.app_id
                confirm.return_value = True
                window.page.games.uninstall(game)
                assert opened.call_args[0][0].toString() == "steam://uninstall/" + game.app_id
            window._photo_game_dna(game)
            assert window.current_route == "Game DNA"
            assert window._shown_dna_games[window.dna_games.currentRow()].key == game.key
            idle(window)

            window.navigate("Mods")
            idle(window)
            control = window.page.mods
            assert control.report is not None and control.report.findings
            assert window.mod_game_filters.count() >= 2
            window.mod_search.setText("Mountain")
            assert len(window._shown_mods) == 1
            assert "High resolution mountain textures" in window.mod_table.item(0, 1).toolTip()
            assert "File overlap" in window.mod_table.item(0, 1).toolTip()
            window._photo_mod_explain()
            details = next(v for v in control.views if isinstance(v, ModDetails))
            assert "textures/mountain.dds" in details.text.toPlainText()
            details.close()
            settle()
            window.mod_search.clear()
            screenshot(window, "photo-mods-functional-1280.png")
            tools = control.open_tools()
            assert tools.isVisible() and tools.export_button.isEnabled()
            tools.close()
            settle()
            window.navigate("Old Files")
            state = window.page.old_files.state
            window.photo_drives.setCurrentIndex(1)
            window.photo_full.setChecked(True)
            window._old_scan()
            wait_for(lambda: not window.workers and not state.busy)
            assert len(state.result.files) == 508 and state.result.plan.mode == "full"
            assert deep.path in {f.path for f in state.result.files}
            assert len(window.inventory.files) == 1, "Read-only scan changed accepted PC inventory"
            assert window.old_pager.isVisible()
            window.old_pager.next.click()
            assert window.old_pager.page == 1
            window.global_search.setText("old-mod-0506")
            assert len(window._shown_old_files) == 1
            window.global_search.clear()
            screenshot(window, "photo-old-files-functional-1280.png")
            window.old_table.item(0, 0).setCheckState(Qt.Checked)
            selected = window._selected_old()[0]
            window._add_old_to_graveyard()
            review = next(entry for entry in window.inventory.graveyard if entry.path == selected.path)
            assert not review.can_recycle and review.category == "Manual review"
            assert window.settings["manual_review_files"][0]["path"] == selected.path
            assert Path(selected.path).exists(), "Adding a review item moved the source"
            confirm.return_value = False
            window._recycle_old_selected()
            assert Path(selected.path).exists()
            confirm.return_value = True
            shell_bin = root / "DisposableShell"
            shell_bin.mkdir()
            with patch("cleanup_actions.recycle_file", side_effect=lambda path: shutil.move(str(path), str(shell_bin / Path(path).name))), \
                 patch("cleanup_actions.register_recycle", return_value="test"), patch("cleanup_actions.log_event"):
                window._recycle_old_selected()
                wait_for(lambda: not window.cleaning and not window.workers)
            assert not Path(selected.path).exists() and (shell_bin / Path(selected.path).name).exists()
            previous = state.result
            entered = threading.Event()
            def held(plan, canceled, progress):
                entered.set()
                while not canceled():
                    time.sleep(.005)
                raise InterruptedError("Canceled")
            with patch("gg_desktop.old_files.scan_files", side_effect=held):
                window._old_scan()
                wait_for(entered.is_set)
                window.photo_cancel.click()
                wait_for(lambda: not state.busy and not window.workers)
            assert state.result is previous and not window.scanning

            for route, _ in ROUTES:
                window.navigate(route)
                idle(window)
                wait_for(lambda: window.page.isVisible())
                # The AI Assistant is optional and off by default: its route sends people to Settings.
                expected = "Settings" if route == "AI Assistant" and not window.assistant_enabled() else route
                assert window.current_route == expected, (route, window.current_route)
            window.reference_preview = True
            window.navigate("Ready Room")
            window.resize(1280, 720)
            settle()
            y = window.page.reference_point(window.page.patches).y()
            assert abs(y - 215) <= 3, (y, window.size().width(), window.size().height())
            screenshot(window, "ready-room-reference-1280.png")
            window.global_search.setText("WITCHER")
            assert len(window.page.visible_games) == len(window.page.visible_patches) == 1
            window.global_search.clear()
            for width, height in ((1440, 900), (960, 650)):
                window.resize(width, height)
                for route in ("Games", "Mods", "Old Files", "Ready Room"):
                    window.navigate(route)
                    idle(window)
                    assert window.page.horizontalScrollBar().maximum() == 0
                    screenshot(window, f"photo-{route.lower().replace(' ', '-')}-{width}.png")
            network.assert_not_called()
            errors.assert_not_called()
            window.close()
            settle()
    print("PASS: Photo shell, native cover grid and three-column inspectors, locked 1280 geometry, "
          "Games actions/favorites/artwork, mod hover/conflict tools, drive/full scan/paging/cancel/recycling, "
          "Ready Room search/layout, all 14 routes and three sizes; no automatic network.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
