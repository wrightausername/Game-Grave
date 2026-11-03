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
    from PySide6.QtWidgets import QApplication, QTableWidget
    from core import SteamGame, OldFile
    from launchers import LauncherGame
    from graveyard import build_graveyard
    from gg_desktop.models import merge_games
    from gg_desktop.app import CrimsonWindow, configure_crimson_dialog_palette
    from gg_desktop.capture_image import ScreenshotImage
    from gg_desktop.widgets import HeroBanner
    from gg_desktop.visuals import SceneHeader, RelationshipMap, RecoveryRoute
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
        steam = [SteamGame("455", "Sample Steam Game", str(synthetic),
                           str(synthetic / "Steam" / "Sample"),
                           1200000, None, "Unknown")]
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
            from PySide6.QtWidgets import QPushButton, QComboBox, QCheckBox, QLabel, QListWidget, QFrame
            from PySide6.QtSvg import QSvgRenderer
            from gg_desktop.approved_overview import RecycledRing
            window.navigate("Overview")
            app.processEvents()
            # The owner-approved dashboard has five evidence-backed metrics
            # and functional actions, not an embedded static mockup image.
            assert window.notification_button.isVisible()
            assert window.help_button.isVisible()
            assert not window.scan_button.isVisible()
            assert not window.notification_button.icon().isNull()
            assert len(window.page.findChildren(QPushButton, "approvedMetric")) == 5
            assert len(window.page.findChildren(RecycledRing)) == 1
            buttons = {b.accessibleName() for b in
                       window.page.findChildren(QPushButton)}
            for expected in ("Scan Library", "Find Unused Mods",
                             "Review Old Files", "Open Graveyard",
                             "Manage Captures", "Undo Center",
                             "View all games"):
                assert any(expected in t for t in buttons), (
                    "Locked Overview action missing: " + expected)
            assert len(window.page.findChildren(QPushButton, "approvedCover")) == 3, (
                "Library strip must be backed by all three verified test game records")
            labels = {b.text() for b in window.page.findChildren(QLabel)}
            assert any("RECENT ACTIVITY" in t for t in labels)
            assert any("RECYCLE BIN ACTIVITY" in t for t in labels)
            assert any("QUICK ACTIONS" in t for t in labels)
            for name in ("gg_cinematic_hero.svg", "crimson_sunset.svg",
                         "crimson_fog.svg", "crimson_footer.svg"):
                asset = root / "gg_desktop" / "assets" / name
                assert QSvgRenderer(str(asset)).isValid(), (
                    "Invalid cinematic local visual: " + name)
            assert oldzip.read_bytes() == b"not an actual mod or game"
            # Read-only Ctrl+K inventory search must not fabricate results
            # or touch scanned files. Reject dialog rather than blocking smoke.
            from unittest.mock import patch
            from PySide6.QtWidgets import QDialog
            window.global_search.setText("Sample Steam")
            with patch("gg_desktop.app.QDialog.exec", return_value=QDialog.Rejected):
                window.open_global_search()
            assert window.global_search.text() == "Sample Steam"
            window.global_search.clear()
            for route in ("Overview", "Ready Room", "Games", "Graveyard",
                          "Game DNA", "Mods", "Old Files", "Captures",
                          "Other Storage", "Undo Center", "AI Assistant",
                          "Settings", "More Tools"):
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
                    assert window.grave_table.columnCount() == 6
                    assert window.grave_drive.count() >= 1
                    assert window.grave_age.count() == 4
                    window.grave_age.setCurrentText("3+ years")
                    app.processEvents()
                    assert window.grave_table.rowCount() == 0, (
                        "Age filter must use verified last-modified evidence")
                    window.grave_age.setCurrentText("All ages")
                    app.processEvents()
                    assert window.grave_table.rowCount() == 1
                if route == "Undo Center":
                    assert len(window.page.findChildren(QFrame, "approvedUndoStat")) == 5, (
                        "Approved Undo summary must use real ledger counts")
                    assert any(t.columnCount() == 5 for t in
                               window.page.findChildren(QTableWidget)), (
                        "Undo Center must show the evidence ledger and status")
                if route == "Game DNA":
                    assert len(window.page.findChildren(QFrame, "approvedDNAMetric")) == 6, (
                        "Six owner-approved DNA metrics need real evidence, no mockup values")
                if route == "AI Assistant":
                    from PySide6.QtWidgets import QPlainTextEdit
                    assert window.page.findChildren(QPlainTextEdit), (
                        "Approved AI page needs a real in-page conversation")
                    sends = [w for w in window.page.findChildren(QPushButton)
                             if w.text() == "Send"]
                    assert len(sends) == 1
                    assert not sends[0].isEnabled(), (
                        "Optional AI must remain disabled before explicit consent")
                if route == "Settings":
                    nav = window.page.findChildren(QListWidget, "settingsCategories")
                    assert len(nav) == 1 and not nav[0].isVisible(), (
                        "Approved Settings uses horizontal categories")
                    assert len(window.page.findChildren(
                        QPushButton, "approvedSettingsTab")) == 7
                if route == "More Tools":
                    assert window.page.findChildren(QFrame, "approvedKitArt")
                    assert window.page.findChildren(QFrame, "approvedVaultArt")
                if route in ("Ready Room", "Games", "Mods", "Old Files", "Graveyard",
                             "Game DNA", "Undo Center", "Captures", "Settings",
                             "AI Assistant", "More Tools"):
                    art = window.page.findChildren(SceneHeader)
                    assert len(art) == 1 and art[0].kind, (
                        "Missing high-DPI, tab-specific scene for " + route)
                if route == "Games":
                    assert len(window.page.findChildren(GameCover)) == 3, (
                        "Games gallery must present actual verified game records")
                    hero = window.page.findChildren(ReferenceHero)
                    assert len(hero) == 1 and hero[0].height() >= 215, (
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
                if route == "Undo Center":
                    assert len(window.page.findChildren(RecoveryRoute)) == 1
                if route == "Settings":
                    categories = window.page.findChildren(QStackedWidget)
                    assert len(categories) == 1 and categories[0].count() == 10, (
                        "Seven locked categories plus real captures/privacy/about controls")
                    category_tabs = {
                        t.text(): t for t in window.page.findChildren(
                            QPushButton, "approvedSettingsTab")}
                    assert list(category_tabs) == [
                        "General", "Libraries", "Safety", "Performance",
                        "AI Assistant", "Notifications", "Advanced"], (
                        "Owner-approved Settings category labels must not drift")
                    category_tabs["Performance"].click()
                    app.processEvents()
                    assert categories[0].currentIndex() == 8
                    category_tabs["Notifications"].click()
                    app.processEvents()
                    assert categories[0].currentIndex() == 9
                    category_tabs["Advanced"].click()
                    app.processEvents()
                    assert categories[0].currentIndex() == 6
            # Locked design provides an AI hub page AND the existing optional
            # dockable companion. Never invoke inference or install a model.
            window.settings["ai_assistant_enabled"] = True
            window.navigate("AI Assistant")
            app.processEvents()
            assert window.current_route == "AI Assistant"
            assert window.page.isVisible()
            window.open_ai_companion()
            app.processEvents()
            docks = window.findChildren(QDockWidget)
            assert len(docks) == 1 and docks[0].isVisible()
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
            assert any("Analyze Other storage" in txt for txt in buttons), (
                "Other Storage must have an explicit-click read-only analyzer")
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
            unlock = window.grave_table.cellWidget(0, 5)
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
                ("Ready Room", "crimson-ready-room-1440.png"),
                ("Games", "crimson-games-1440.png"),
                ("Mods", "crimson-mods-1440.png"),
                ("Old Files", "crimson-old-files-1440.png"),
                ("Graveyard", "crimson-graveyard-1440.png"),
                ("Game DNA", "crimson-dna-1440.png"),
                ("Undo Center", "crimson-undo-1440.png"),
                ("Captures", "crimson-captures-1440.png"),
                ("Other Storage", "crimson-other-storage-1440.png"),
                ("AI Assistant", "crimson-ai-1440.png"),
                ("Settings", "crimson-settings-1440.png"),
                ("More Tools", "crimson-more-tools-1440.png"),
            ):
                window.navigate(route)
                window.resize(1440, 900)
                app.processEvents()
                path = root / "_ci_temp" / filename
                assert window.grab().save(str(path)), "Cannot render Qt screenshot: " + route
                assert path.stat().st_size > 9000, "Blank Qt screenshot: " + route
            # The seven owner-locked references have real cropped artwork
            # shipped with the package. A fabricated fallback is not parity.
            from gg_desktop.owner_art import load_approved_hero
            for route_kind in ("overview", "graveyard", "dna", "undo",
                               "assistant", "settings", "tools"):
                assert not load_approved_hero(route_kind).isNull(), (
                    "Missing approved source artwork for " + route_kind)
            # Locked owner references are 1672 x 941. Capture the same native
            # Qt window size for direct review against each approved image.
            for route, slug in (
                ("Overview", "overview"),
                ("Graveyard", "graveyard"),
                ("Game DNA", "dna"),
                ("Undo Center", "undo"),
                ("AI Assistant", "ai"),
                ("Settings", "settings"),
                ("More Tools", "more-tools"),
            ):
                window.navigate(route)
                window.resize(1672, 941)
                app.processEvents()
                shot = root / "_ci_temp" / ("crimson-" + slug + "-1672.png")
                assert window.grab().save(str(shot)), (
                    "Cannot render exact-resolution owner reference: " + route)
                assert shot.stat().st_size > 9000, (
                    "Blank exact-resolution screenshot: " + route)
            # Smaller-window evidence: owners should not have to guess
            # which controls vanished at 1366x768. Save every real Qt route.
            for route, slug in (
                ("Overview", "overview"), ("Ready Room", "ready-room"),
                ("Games", "games"), ("Mods", "mods"),
                ("Old Files", "old-files"), ("Other Storage", "other-storage"),
                ("Captures", "captures"), ("Graveyard", "graveyard"),
                ("Game DNA", "dna"), ("Undo Center", "undo"),
                ("AI Assistant", "ai"), ("Settings", "settings"),
                ("More Tools", "more-tools"),
            ):
                window.navigate(route)
                window.resize(1366, 768)
                app.processEvents()
                assert window.global_search.isVisible(), (
                    "Global search hidden at 1366x768: " + route)
                if route in ("Graveyard", "Game DNA", "Undo Center",
                             "AI Assistant", "Settings", "More Tools"):
                    content_width = window.page.body.width()
                    available_width = window.page.viewport().width()
                    assert content_width <= available_width + 6, (
                        f"{route} has horizontally clipped content at 1366: "
                        f"body {content_width}px > viewport {available_width}px")
                path = root / "_ci_temp" / ("crimson-" + slug + "-1366.png")
                assert window.grab().save(str(path)), (
                    "Cannot render smaller-screen reference: " + route)
                assert path.stat().st_size > 9000, (
                    "Blank smaller-screen screenshot: " + route)
            # A manifest joins every rendered route to its native screenshot
            # and hash. Locked source PNGs stay separate; this report never
            # substitutes screenshot output for a human design comparison.
            import hashlib
            import json
            manifest = []
            for image_path in sorted((root / "_ci_temp").glob("crimson-*.png")):
                with Image.open(image_path) as shot:
                    pixel_size = list(shot.size)
                manifest.append({
                    "screenshot": image_path.name,
                    "pixel_size": pixel_size,
                    "sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
                })
            assert len(manifest) >= 35, "Missing per-route Qt acceptance captures"
            (root / "_ci_temp" / "cinematic-screenshot-manifest.json").write_text(
                json.dumps({
                    "visual_authority": "docs/APPROVED_UI_VISUAL_CONTRACT.md",
                    "reference_fidelity": "human review pending",
                    "captures": manifest,
                }, indent=2), encoding="utf-8")

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
