"""Render and exercise Ready Room without scanning or changing a real user profile.

python tools/ready_room_ui_smoke.py --output /tmp/ready-room-review
Works with Qt's offscreen platform on Linux and native Qt on Windows.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("_ci_temp"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt
    from PySide6.QtGui import QPixmap
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QPushButton
    from core import default_settings
    from gg_desktop.app import CrimsonWindow, ROUTES
    from gg_desktop.models import merge_games
    from gg_desktop.ready_room import ASSETS, ReadyRoomPage
    from gg_desktop.theme import STYLE

    app = QApplication.instance() or QApplication([])

    def settle():
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()

    def capture(window, name):
        settle()
        target = args.output / name
        assert window.grab().save(str(target)), target
        assert target.stat().st_size > 20_000, "Blank screenshot: " + name

    def check_page_reachable(window):
        # The original native window may be fitted to the Windows work area.
        # Its Ready Room must allow the footer to be reached by scrolling.
        page = window.page
        assert page.horizontalScrollBar().maximum() == 0
        page.verticalScrollBar().setValue(page.verticalScrollBar().maximum())
        settle()
        bottom = page.health_panel.mapTo(page.viewport(), QPoint(0, page.health_panel.height() - 1)).y()
        assert 0 <= bottom < page.viewport().height(), "Ready Room footer cannot be reached"
        page.verticalScrollBar().setValue(0)
        settle()

    # Patch before construction so every signal points at a safe test double.
    with patch("gg_desktop.app.load_settings", side_effect=default_settings), \
            patch.object(CrimsonWindow, "start_scan") as scan, \
            patch.object(CrimsonWindow, "_create_save_backup") as backup, \
            patch.object(CrimsonWindow, "info") as info:
        window = CrimsonWindow(reference_preview=True)
        window.resize(1280, 900)
        window.show()
        settle()
        # Windows may fit a newly created native frame to the runner's desktop.
        # Set the review size after showing it, as the original UI smoke does.
        window.resize(1280, 900)
        settle()
        assert isinstance(window.page, ReadyRoomPage)
        assert window.current_route == "Ready Room"
        assert window.page.data.reference
        assert window.windowTitle() == "Game Grave  |  Crimson Command preview"
        assert window.styleSheet() == STYLE
        original_inventory = asdict(window.inventory)
        for path in ASSETS.glob("*.png"):
            assert not QPixmap(str(path)).isNull(), "Undecodable local asset: " + str(path)
        check_page_reachable(window)
        assert window.nav_buttons["Ready Room"].property("active")
        # Compare primary reference rectangles, not fragile raster/font hashes.
        assert window.page.patches.mapTo(window.page.body, window.page.patches.rect().topLeft()).y() == (
            273 if window.page.compact else 215)
        expected_width = (window.page.body.width() - 20 if window.page.compact else
                          (window.page.body.width() - 32) * 626 / 1030)
        assert abs(window.page.patches.width() - expected_width) <= 3

        window.page.search.setText("WITCHER")
        settle()
        assert len(window.page.visible_games) == len(window.page.visible_patches) == 1
        window.page.search.setText("nonexistent title")
        settle()
        assert not window.page.visible_games and not window.page.visible_patches
        window.page.search.clear()
        settle()
        assert len(window.page.visible_games) == len(window.page.visible_patches) == 5
        window.activateWindow()
        QTest.keyClick(window, Qt.Key_K, Qt.ControlModifier)
        settle()
        assert window.page.search.hasFocus(), "Ctrl+K did not focus Ready Room search"
        window.page.search.setText("Starfield")
        QTest.keyClick(window.page.search, Qt.Key_Escape)
        settle()
        assert not window.page.search.text(), "Escape did not clear search"
        # Mouse events on child text should still activate their real row button.
        first = window.page.patches.findChild(QPushButton, "readyItem")
        QTest.mouseClick(first, Qt.LeftButton)
        info.assert_called()
        buttons = window.page.findChildren(QPushButton)
        next(b for b in buttons if b.text() == "Run Mod Scan").click()
        scan.assert_called_once()
        next(b for b in buttons if b.text() == "Backup Now").click()
        backup.assert_called_once()
        next(b for b in buttons if b.text() == "Manage Saves  →").click()
        settle()
        assert window.current_route == "More Tools"
        assert window.nav_buttons["More Tools"].property("active")
        window.navigate("Ready Room")
        window.page.setFocus()
        capture(window, "ready-room-reference-1280.png")

        for width, height in ((1440, 900), (960, 650)):
            window.resize(width, height)
            settle()
            check_page_reachable(window)
            if width == 960:
                assert window.page.verticalScrollBar().maximum() > 0
                assert window.page.metrics.height() == 116
                for metric in window.page.metric_buttons:
                    assert metric.width() > 190
            capture(window, f"ready-room-reference-{width}.png")
        # Re-expanding must restore the exact reference layout and clear scrolling.
        window.resize(1280, 900)
        settle()
        check_page_reachable(window)
        assert window.page.metrics.height() == (116 if window.page.compact else 58)

        for route, _glyph in ROUTES:
            window.nav_buttons[route].click()
            settle()
            assert window.current_route == route, route
        assert asdict(window.inventory) == original_inventory
        scan.assert_called_once()  # navigation and rendering never start a scan
        window.close()

        live = CrimsonWindow()
        assert live.current_route == "Overview", "Original startup page was changed"
        live.resize(1280, 900)
        live.navigate("Ready Room")
        live.show()
        settle()
        assert not live.page.data.reference
        assert not live.page.data.games and not live.page.data.patches
        assert live.page.data.health_score is None
        capture(live, "ready-room-live-1280.png")
        live.inventory.games = merge_games([SimpleNamespace(
            app_id="test", name="Synthetic local installation", install_path="C:/QA/TestGame",
            size=1024, last_played=None, source="Unknown")], [])
        live.inventory.scanned_at = "Synthetic UI QA"
        live.navigate("Ready Room")
        settle()
        assert len(live.page.visible_games) == 1
        game = live.page.visible_games[0]
        assert game.hours == "— hrs" and game.status == "Recorded install"
        live.ready_game_details(game)
        settle()
        assert live.current_route == "Games"
        assert live.game_search.text() == game.name
        assert len(live._shown_games) == 1
        live.close()
        settle()

    print("PASS: Ready Room reference geometry, 3 window sizes, local artwork, search and keyboard, "
          "row actions, scan/backup routing, all navigation, live/fixture isolation. "
          "4 screenshots saved to " + str(args.output.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
