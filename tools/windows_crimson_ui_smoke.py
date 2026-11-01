"""Disposable native Windows Qt smoke. Never opens or mutates user game data."""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path


def main():
    if os.name != "nt" or os.environ.get("GG_CRIMSON_QA_DISPOSABLE") != "YES":
        print("Refusing to run without Windows disposable CI approval.")
        return 2
    os.environ.setdefault("QT_QPA_PLATFORM", "windows")
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from PySide6.QtWidgets import QApplication, QTableWidget, QFrame
    from core import SteamGame, OldFile
    from launchers import LauncherGame
    from graveyard import build_graveyard
    from gg_desktop.models import merge_games
    from gg_desktop.app import CrimsonWindow, configure_crimson_dialog_palette
    from gg_desktop.capture_image import ScreenshotImage
    from gg_desktop.widgets import HeroBanner
    from gg_desktop.visuals import SceneHeader, RelationshipMap
    from gg_desktop.undo_visuals import UndoStatusDial
    from gg_desktop.tab_panels import GraphicCard, GameCover
    from gg_desktop.premium_panels import GameInspector, ModInspector
    from gg_desktop.reference_hero import ReferenceHero
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QTabWidget, QStackedWidget, QDockWidget
    from PySide6.QtGui import QPalette
    from PIL import Image

    app = QApplication.instance() or QApplication(sys.argv)
    configure_crimson_dialog_palette(app)
    assert app.palette().color(QPalette.Window).lightness() < 90
    assert app.palette().color(QPalette.WindowText).lightness() > 180
    from PySide6.QtGui import QFontDatabase
    families = QFontDatabase.families()
    print("Native Windows Qt font families:", len(families),
          "Segoe UI?", QFontDatabase.hasFamily("Segoe UI"),
          "Arial?", QFontDatabase.hasFamily("Arial"))
    with tempfile.TemporaryDirectory(prefix="GG-Crimson-", dir=root / "_ci_temp") as temp:
        synthetic = Path(temp)
        os.environ["LOCALAPPDATA"] = str(synthetic / "Local")
        os.environ["APPDATA"] = str(synthetic / "Roaming")
        Path(os.environ["LOCALAPPDATA"]).mkdir(parents=True)
        Path(os.environ["APPDATA"]).mkdir(parents=True)
        # Real (disposable) 1920px screenshot and video records exercise
        # actual thumbnail decoding and two separate Captures panels.
        screen_path = synthetic / "Videos" / "Captures" / "latest-game.png"
        screen_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1920, 1080), (38, 132, 185)).save(screen_path)
        video_path = screen_path.parent / "gameplay-2026-11-01.mp4"
        video_path.write_bytes(b"metadata fixture; never launched or decoded")
        def record_file(file):
            data = file.stat()
            return OldFile(str(file), data.st_size, data.st_mtime,
                           data.st_dev, data.st_ino, data.st_mtime_ns,
                           data.st_nlink)
        screenshot_record = record_file(screen_path)
        video_record = record_file(video_path)
        oldzip = synthetic / "old-skyrim-mod.zip"
        oldzip.write_bytes(b"not an actual mod or game")
        stamp = time.time() - 800 * 86400
        os.utime(oldzip, (stamp, stamp))
        st = oldzip.stat()
        old = OldFile(str(oldzip), st.st_size, st.st_mtime,
                      st.st_dev, st.st_ino, st.st_mtime_ns, st.st_nlink)
        # Simulate an actual Steam library-cache image on the disposable drive.
        # Both Games and DNA must render the same cache-backed cover by AppID.
        steam_root = synthetic / "Steam"
        steam_install = steam_root / "steamapps" / "common" / "Sample Steam Game"
        steam_install.mkdir(parents=True)
        art_cache = steam_root / "appcache" / "librarycache"
        art_cache.mkdir(parents=True)
        Image.new("RGB", (600, 900), (112, 38, 70)).save(
            art_cache / "455_library_600x900.jpg")
        steam = [SteamGame("455", "Sample Steam Game", str(steam_root),
                           str(steam_install), 1200000, None, "Unknown")]
        other = [
            LauncherGame("Sample Epic Game", "Epic Games",
                         str(synthetic / "Epic" / "Sample"),
                         "epic455", None, "Manifest and folder verified"),
            LauncherGame("Sample EA Game", "EA",
                         str(synthetic / "EA" / "Sample"),
                         "ea11", None, "Registry installation record"),
        ]
        window = CrimsonWindow()
        window.show()
        app.processEvents()
        try:
            window.settings["scan_on_launch"] = False
            window.inventory.steam = steam
            window.inventory.other = other
            window.inventory.games = merge_games(steam, other)
            window.inventory.files = [old]
            window.inventory.screenshots = [screenshot_record]
            window.inventory.recordings = [video_record]
            window.inventory.scanned_at = "Synthetic test date"
            window.inventory.graveyard = build_graveyard(steam, [], [old], 365)
            # Native reference-dashboard parity: all pictured controls must
            # exist and be wired to the real app, never static screenshot overlays.
            from PySide6.QtWidgets import QPushButton, QComboBox, QCheckBox, QLabel
            from PySide6.QtSvg import QSvgRenderer
            from gg_desktop.widgets import ActionCard
            window.navigate("Overview")
            app.processEvents()
            buttons = {b.text() for b in window.page.findChildren(QPushButton)}
            labels = {b.text() for b in window.page.findChildren(QLabel)}
            cards = window.page.findChildren(ActionCard)
            assert len(cards) == 4, "Four clickable top-level action cards are required"
            assert all(callable(card._action) for card in cards)
            for expected in ("Scan for Old Files", "Review Graveyard",
                             "Open Undo Center", "Quick Settings"):
                assert any(expected in t for t in labels), (
                    f"Missing text label inside actionable reference card: {expected}")
            for expected in ("Delete Selected", "Restore", "Add to Graveyard",
                             "Review Files", "Preview actual image"):
                assert any(expected in t for t in buttons), (
                    f"Missing or unconnected reference dashboard button: {expected}")
            combos = window.page.findChildren(QComboBox)
            drives = [c for c in combos if "local drive" in c.accessibleName().lower()]
            filters = [c for c in combos if "filter launchers" in c.accessibleName().lower()]
            assert len(drives) == 1 and drives[0].count() >= 1
            assert len(filters) == 1 and filters[0].count() >= 9
            assert filters[0].findText("Steam") >= 0
            assert window.page.findChildren(QCheckBox), "Missing Graveyard queue checkboxes"
            scan_control = window.findChild(QPushButton, "mainScanControl")
            cancel_control = window.findChild(QPushButton, "mainCancelScan")
            assert scan_control is window.scan_button and cancel_control is window.cancel_button
            assert scan_control.isVisible() and scan_control.isEnabled(), (
                "Main Scan PC action must be visible and usable on the current page")
            print("Main scan rendered size:", scan_control.width(),
                  scan_control.height(), "minimum:", scan_control.minimumWidth(),
                  scan_control.minimumHeight())
            assert scan_control.width() >= 155 and scan_control.height() >= 50, (
                "Main Scan PC must render as a prominent large button.")
            assert scan_control.mapTo(window, QPoint(0, 0)).x() < window.width() * .50, (
                "Main Scan PC action must not be hidden in the far top-right corner")
            assert cancel_control.isVisible() and not cancel_control.isEnabled(), (
                "Persistent Cancel control remains visible but disabled until a scan starts")
            assert window.progress.objectName() == "mainScanProgress"
            for name in ("crimson_hero.svg", "crimson_sunset.svg",
                         "crimson_fog.svg", "crimson_footer.svg",
                         "crimson_dna_scene.svg", "crimson_undo_scene.svg"):
                asset = root / "gg_desktop" / "assets" / name
                assert QSvgRenderer(str(asset)).isValid(), (
                    "Invalid cinematic local visual: " + name)
            assert oldzip.read_bytes() == b"not an actual mod or game"
            for route in ("Overview", "Games", "Graveyard", "Game DNA",
                          "Mods", "Old Files", "Captures", "Other Storage",
                          "Undo Center", "Settings", "More Tools"):
                window.navigate(route)
                window.resize(1366, 768)
                app.processEvents()
                assert window.page is not None and window.page.isVisible()
                assert window.current_route == route
                assert oldzip.read_bytes() == b"not an actual mod or game"
                if route == "Games":
                    rows = window._shown_games
                    assert len(rows) == 3
                    assert {r.launcher for r in rows} == {"Steam", "Epic Games", "EA"}
                    assert rows[0].last_played_at is None or (
                        rows[0].last_played_source != "Unknown")
                if route == "Graveyard":
                    assert len(window._shown_graves) == 1
                    assert window.grave_table.rowCount() == 1
                if route in ("Games", "Mods", "Old Files", "Graveyard",
                             "Game DNA", "Undo Center", "Captures", "Settings"):
                    art = window.page.findChildren(SceneHeader)
                    assert len(art) == 1 and art[0].kind, (
                        "Missing high-DPI, tab-specific scene for " + route)
                if route == "Games":
                    assert len(window.page.findChildren(GameCover)) == 3, (
                        "Games gallery must present actual verified game records")
                    hero = window.page.findChildren(ReferenceHero)
                    assert len(hero) == 1 and hero[0].height() >= 240, (
                        "Approved Games layout needs a cinematic metrics header")
                    assert not window.game_inventory_panel.isVisible(), (
                        "Advanced game table must not dominate the default visual screen")
                    first = window.page.findChildren(GameCover)[0]
                    gap = first.mapTo(window.game_gallery_frame, QPoint(0, 0)).y()
                    assert 0 <= gap < 145, (
                        f"Qt stretched artwork gallery vertically: first card starts {gap}px down")
                    inspectors = window.page.findChildren(GameInspector)
                    assert len(inspectors) == 1 and inspectors[0].game is not None, (
                        "Games tab requires a live selection-driven inspector")
                    window.game_table.selectRow(1)
                    app.processEvents()
                    assert inspectors[0].game.key == window._shown_games[1].key, (
                        "Selecting a different game must update its right-side inspector")
                if route == "Mods":
                    assert len(window.page.findChildren(ModInspector)) == 1, (
                        "Mod Radar requires a source-aware right-side inspector")
                if route == "Game DNA":
                    dna_art = window.page.findChildren(RelationshipMap)
                    assert dna_art and dna_art[0].game_name == "Sample Steam Game", (
                        "Game DNA visual map must use actual scan data")
                    assert window.page.findChild(QFrame, "dnaRelationshipStudio")
                    assert dna_art[0].minimumHeight() >= 380
                    assert dna_art[0].mapTo(window.page, QPoint(0, 0)).y() < 660, (
                        "Main forensic map must start above the fold.")
                    assert window.page.findChild(QTableWidget, "dnaGamesResults")
                    official = window.page.findChild(QLabel, "dnaOfficialCover")
                    assert official is not None and official.pixmap() is not None and (
                        not official.pixmap().isNull()), (
                        "Game DNA must display the verified Steam cached cover")
                    assert not dna_art[0]._cover.isNull(), (
                        "Game DNA relationship map must share the selected Steam cover")
                if route == "Undo Center":
                    dials = window.page.findChildren(UndoStatusDial)
                    assert len(dials) == 1, "Undo Center needs real recovery status."
                    assert window.page.findChild(QTableWidget, "undoHistoryTable")
                    assert any(b.text().startswith("Browse Recycle Bin")
                               for b in window.page.findChildren(QPushButton))
                if route == "Settings":
                    categories = window.page.findChildren(QStackedWidget)
                    assert len(categories) == 1 and categories[0].count() == 8, (
                        "Settings must show real controls in eight organized sections")
            # Ready Room must be a real navigable page, with no live web traffic
            # in disposable CI. Production network calls are independently tested.
            from unittest.mock import patch
            with patch("gg_desktop.steam_artwork.prime_visible_covers",
                       return_value=0), patch(
                    "gg_desktop.ready_room_data.game_news_batch", return_value=[]):
                window.navigate("Ready Room")
                window.pool.waitForDone(3000)
                app.processEvents()
                assert window.current_route == "Ready Room"
                ready_buttons = {b.text() for b in window.page.findChildren(QPushButton)}
                for expected in ("Record baseline", "Compare changes",
                                 "Game Time Machine…", "Record benchmark results…"):
                    assert expected in ready_buttons, (
                        "Missing Ready Room action: " + expected)

            # The optional assistant stays visible while the user navigates.
            # This test never invokes the model or installs anything.
            window.settings["ai_assistant_enabled"] = True
            window.navigate("Games")
            before = window.current_route
            window.navigate("AI Assistant")
            app.processEvents()
            docks = window.findChildren(QDockWidget)
            assert len(docks) == 1 and docks[0].isVisible(), (
                "AI must open as a companion, not replace the current tab")
            assert window.current_route == before
            docks[0].setFloating(True)
            app.processEvents()
            assert docks[0].isFloating()
            window.navigate("Graveyard")
            app.processEvents()
            assert window.current_route == "Graveyard"
            assert docks[0].isVisible()
            docks[0].setFloating(False)
            docks[0].hide()
            window.settings["ai_assistant_enabled"] = False

            window.navigate("Captures")
            app.processEvents()
            capture_tabs = window.page.findChildren(QTabWidget)
            assert len(capture_tabs) == 1, "Captures must contain two separate tabs"
            assert capture_tabs[0].count() == 2
            assert "Screenshots" in capture_tabs[0].tabText(0)
            assert "Videos" in capture_tabs[0].tabText(1)
            capture_tabs[0].setCurrentIndex(1)
            app.processEvents()
            from PySide6.QtWidgets import QTableWidget
            assert any(t.rowCount() == 1 for t in capture_tabs[0].currentWidget()
                       .findChildren(QTableWidget)), "Video tab must display the real recording"
            capture_tabs[0].setCurrentIndex(0)
            app.processEvents()
            thumbnail_widgets = capture_tabs[0].currentWidget().findChildren(ScreenshotImage)
            assert thumbnail_widgets, "Screenshots tab requires a real image preview"
            preview_deadline = time.monotonic() + 12
            while time.monotonic() < preview_deadline and not thumbnail_widgets[0].has_image():
                app.processEvents()
                time.sleep(0.06)
            assert thumbnail_widgets[0].has_image(), (
                "The actual scanned 1920px screenshot must render, not placeholder art")
            assert screen_path.is_file() and video_path.is_file()
            window.navigate("Other Storage")
            app.processEvents()
            buttons = {w.text() for w in window.page.findChildren(QPushButton)}
            assert "Quick Scan" in buttons and "Full Scan" in buttons
            quick = window.page.findChild(QPushButton, "otherStorageQuickScan")
            full = window.page.findChild(QPushButton, "otherStorageFullScan")
            assert quick is not None and full is not None
            assert full.isVisible() and full.isEnabled(), (
                "Full Scan must be directly visible, not buried in a dropdown.")
            assert full.mapTo(window.page, QPoint(0, 0)).y() < window.page.height()
            window.navigate("Overview")
            app.processEvents()
            assert window.page.findChildren(HeroBanner), "Hero must be a real native vector widget"
            assert not hasattr(window.page.findChildren(HeroBanner)[0], "atlas"), (
                "Overview must not use the old pixelated JPEG artwork")
            # Dialogs must not be white background with white text on Windows.
            assert app.palette().color(QPalette.Window).lightness() < 90
            assert app.palette().color(QPalette.WindowText).lightness() > 180
            # Exact personal Never Touch rule can be removed from the Graveyard
            # with a separate confirmation and WITHOUT a recycle operation.
            from gg_desktop.backend import refresh_graveyard
            from unittest.mock import patch
            window.settings["never_touch"] = [str(oldzip)]
            refresh_graveyard(window.inventory, window.settings)
            window.navigate("Graveyard")
            assert not window.inventory.graveyard[0].can_recycle
            from PySide6.QtWidgets import QPushButton
            window.grave_table.selectRow(0)
            app.processEvents()
            unlock = window.grave_table.cellWidget(0, 3)
            assert isinstance(unlock, QPushButton) and "Unprotect" in unlock.text(), (
                "Missing the user's requested direct in-row Unprotect control")
            protected_image = root / "_ci_temp" / "crimson-unprotect-1440.png"
            assert window.grab().save(str(protected_image)), "Cannot render protected Graveyard row"
            archive = next(e for e in window.inventory.graveyard
                           if e.category == "Possible mod / game download")
            with patch.object(window, "confirm", return_value=True), \
                 patch("gg_desktop.screens.recycle_reviewed_entries") as recycle:
                unlock.click()
                assert oldzip.is_file()
                assert str(oldzip) not in window.settings["never_touch"]
                recycle.assert_not_called()
            window.settings["never_touch"] = []
            refresh_graveyard(window.inventory, window.settings)

            for route, filename in (
                ("Overview", "crimson-desktop-1440.png"),
                ("Games", "crimson-games-1440.png"),
                ("Mods", "crimson-mods-1440.png"),
                ("Old Files", "crimson-old-files-1440.png"),
                ("Graveyard", "crimson-graveyard-1440.png"),
                ("Game DNA", "crimson-dna-1440.png"),
                ("Undo Center", "crimson-undo-1440.png"),
                ("Other Storage", "crimson-other-storage-1440.png"),
                ("Captures", "crimson-captures-1440.png"),
                ("Settings", "crimson-settings-1440.png"),
            ):
                window.navigate(route)
                window.resize(1440, 900)
                app.processEvents()
                path = root / "_ci_temp" / filename
                assert window.grab().save(str(path)), "Cannot render Qt screenshot: " + route
                assert path.stat().st_size > 9000, "Blank Qt screenshot: " + route
            # Full-height capture preserves all three bands of the reference
            # dashboard. The 900px legacy capture deliberately tests scrolling.
            window.navigate("Overview")
            window.resize(1440, 1080)
            app.processEvents()
            full = root / "_ci_temp" / "crimson-desktop-full-1440.png"
            assert window.grab().save(str(full)), "Cannot render full reference dashboard"
            assert full.stat().st_size > 15000, "Full-height overview appears blank"
            print("PASS: Qt Crimson dashboard, all pictured controls, original art, "
                  "9 interactive pages, mixed-launcher data, protected Graveyard, "
                  "and full-height screenshot without changing user data.")
        finally:
            window.close()
            app.processEvents()
        assert oldzip.exists()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
