"""Native Qt check of the shell polish: HD logo and backdrop, nav order, optional AI Assistant, and a scan bar that
floats over the bottom edge so it never cuts through banner artwork."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
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
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication, QWidget
    from PySide6.QtTest import QTest
    import core
    from gg_desktop import reference_widgets as rw
    from gg_desktop.app import CrimsonWindow, ROUTES

    app = QApplication.instance() or QApplication([])

    def settle():
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()

    with tempfile.TemporaryDirectory(prefix="GG-shell-") as temp:
        root = Path(temp)
        stack = ExitStack()
        for target, options in (
            ("core.config_dir", dict(return_value=root / "Config")),
            ("gg_desktop.recovery_screens.get_records", dict(return_value=[])),
            ("gg_desktop.recovery_screens.get_activity", dict(return_value=[])),
            ("gg_desktop.undo_page.get_records", dict(return_value=[])),
            ("gg_desktop.undo_page.get_activity", dict(return_value=[])),
            ("gg_desktop.assistant_page.get_records", dict(return_value=[])),
            ("gg_desktop.assistant_page.get_activity", dict(return_value=[])),
            ("gg_desktop.settings_page.get_records", dict(return_value=[])),
            ("gg_desktop.tools_page.get_activity", dict(return_value=[])),
            ("gg_desktop.ready_room_services.config_dir", dict(return_value=root / "Preferences")),
            ("gg_desktop.game_artwork.artwork_dir", dict(return_value=root / "Artwork")),
            ("gg_desktop.game_artwork._request", dict(side_effect=AssertionError("No automatic network"))),
        ):
            stack.enter_context(patch(target, **options))
        with stack:
            core.save_settings(core.default_settings())
            window = CrimsonWindow()
            window.show()
            window.resize(1280, 720)
            window.navigate("Overview")
            settle()

            # The sidebar: everyday entries first, sections that never fold, Assistant / Undo / Settings pinned at the
            # bottom, one line per entry (no subtitle), hub tabs only under the hub you are in, Collapse to icons.
            from PySide6.QtCore import QPoint
            from gg_desktop import nav_groups, nav_rail
            order = [route for route, _ in ROUTES]
            assert order[-3:] == ["AI Assistant", "Undo Center", "Settings"], order
            names = [e for e, item in window.nav_entries.items() if not item.isHidden()]
            assert names[:4] == ["Home", "Games", "Mods", "Deals"] and names[-2:] == ["Undo", "Settings"], names
            assert not window.nav_entries["Assistant"].isVisibleTo(window), "the assistant starts off"
            assert window.nav_entries["Home"].property("active") and window.nav_hubs["Home"].isVisible()
            assert not window.nav_hubs["Free up space"].isVisible(), "a hub's tabs show only while you are in it"
            heights = {e: item.height() for e, item in window.nav_entries.items() if item.isVisibleTo(window)}
            assert set(heights.values()) == {nav_rail.ITEM_HEIGHT}, heights
            assert all(not lbl.isHidden() for lbl, _ in window.nav_sections.values())
            pinned_top = window.nav_entries["Settings"].mapTo(window.nav_rail, QPoint(0, 0)).y()
            assert pinned_top > window.nav_rail.height() - 160, ("Settings is pinned at the bottom", pinned_top)
            window.nav_entries["Free up space"].click()
            settle()
            assert window.current_route == "Old Files" and window.nav_hubs["Free up space"].isVisible()
            assert not window.nav_hubs["Home"].isVisible()
            window.nav_buttons["Graveyard"].click()
            settle()
            assert window.current_route == "Graveyard" and window.nav_buttons["Graveyard"].property("active")
            assert window.nav_entries["Free up space"].property("active")
            window.navigate("Games")
            settle()
            window.nav_entries["Free up space"].click()
            settle()
            assert window.current_route == "Graveyard", "a hub opens the tab you were last on"
            assert window.settings.get(nav_groups.HUB_KEY, {}).get("Free up space") == "Graveyard"
            window.nav_entries["Fix a game"].click()
            settle()
            assert window.current_route == "Fix Kit"
            tops = sorted(item.mapTo(window.nav_rail, QPoint(0, 0)).y() for item in window.nav_entries.values()
                          if item.isVisibleTo(window))
            assert all(b - a >= nav_rail.ITEM_HEIGHT for a, b in zip(tops, tops[1:])), ("Sidebar rows overlap", tops)
            widths = {item.width() for item in window.nav_entries.values()}
            assert widths == {nav_rail.ITEM_WIDTH}, ("Every sidebar row keeps one width", widths)
            assert window.grab().save(str(args.output / "shell-sidebar.png"))
            window.nav_collapse_button.click()
            settle()
            assert window.nav_collapsed and window.nav_rail.width() == nav_rail.NARROW
            assert all(not item.title.isVisible() for item in window.nav_entries.values())
            assert window.settings.get(nav_groups.COLLAPSED_KEY) is True
            window.nav_entries["Games"].click()
            settle()
            assert window.current_route == "Games", "icons still navigate when collapsed"
            assert window.grab().save(str(args.output / "shell-sidebar-collapsed.png"))
            window.nav_collapse_button.click()
            settle()
            assert not window.nav_collapsed and window.nav_rail.width() == nav_rail.WIDE
            visible = nav_rail.visible_routes(window)
            window.navigate("Overview")
            settle()

            # The AI Assistant is optional and starts off: hidden, and unreachable until it is switched on.
            assert window.settings.get("assistant_enabled") is not True
            assert window.nav_buttons["AI Assistant"].isHidden() and "AI Assistant" not in visible
            window.navigate("AI Assistant")
            settle()
            assert window.current_route == "Settings" and "AI Assistant is off" in window.status.text()
            window.settings_controls["assistant_enabled"][0].click()
            settle()
            assert window.nav_buttons["AI Assistant"].isHidden(), "A staged change is not applied until Apply"
            window.settings_apply.click()
            settle()
            assert not window.nav_buttons["AI Assistant"].isHidden()
            assert window.settings.get("assistant_enabled") is True
            window.navigate("AI Assistant")
            settle()
            assert window.current_route == "AI Assistant"
            window.navigate("Settings")
            settle()
            window.settings_controls["assistant_enabled"][0].click()
            window.settings_apply.click()
            settle()
            assert window.nav_buttons["AI Assistant"].isHidden() and window.settings.get("assistant_enabled") is False

            # The scan bar sits at the bottom edge: clearly visible, with step, percent, elapsed time and an estimate,
            # and starting a scan moves nothing at the top (the banner is never cut or shifted).
            for route in ("Mods", "Old Files", "Games", "Ready Room", "Overview"):
                window.navigate(route)
                settle()
                before = (window.page.geometry().topLeft(), window.page.geometry().width(), window.top_bar.geometry())
                window.progress.begin(None)
                window.progress.report(40, "Mod Radar")
                settle()
                after = (window.page.geometry().topLeft(), window.page.geometry().width(), window.top_bar.geometry())
                assert after == before, route + " shifted at the top when the bar appeared"
                main = window.progress.parentWidget()
                bar = window.progress
                assert bar.isVisible() and bar.height() >= 40, "The scan bar is a clear, full-width strip"
                assert bar.geometry().bottom() == main.height() - 1 and bar.width() == main.width()
                assert bar.geometry().top() >= window.page.geometry().bottom() - 1, "The bar does not cover the page"
                assert "step" in bar.stage_label.text() and "Mod Radar" in bar.stage_label.text(), bar.stage_label.text()
                assert bar.percent_label.text().endswith("%") and int(bar.percent_label.text()[:-1]) >= 40
                assert "left" in bar.eta_label.text() and bar.elapsed_label.text().count(":") == 1
                assert bar.cancel_button.isEnabled() and bar.bar.value() >= 400
                if route == "Mods":
                    assert window.grab().save(str(args.output / "scan-bar-1280.png"))
                bar.finish()
                settle()
                assert not bar.isVisible()
            assert window.grab().save(str(args.output / "shell-polish-1280.png"))

            # HD brand art: full-resolution transparent PNGs, resampled to the real pixel size of the widget.
            logo, forest = rw.brand_source("game_grave_logo.png"), rw.brand_source("nav_backdrop.png")
            assert logo.width() >= 1600 and logo.hasAlphaChannel(), "The logo is a transparent HD PNG"
            assert forest.width() >= 1184 and forest.height() >= 960 and forest.hasAlphaChannel()
            for dpr in (1.0, 2.0):
                fitted = rw.brand_scaled("game_grave_logo.png", 200, 48, dpr, False)
                assert fitted.width() <= round(200 * dpr) and fitted.height() <= round(48 * dpr) and fitted.devicePixelRatio() == dpr
                assert fitted.width() >= round(200 * dpr) - 1, "The logo fills its box instead of being a small upscaled crop"
            image = window.brand.grab().toImage()
            reds = sum(1 for x in range(0, image.width(), 2) for y in range(0, image.height(), 2)
                       if image.pixelColor(x, y).red() > 170 and image.pixelColor(x, y).green() < 90)
            whites = sum(1 for x in range(0, image.width(), 2) for y in range(0, image.height(), 2)
                         if image.pixelColor(x, y).red() > 235 and image.pixelColor(x, y).green() > 235)
            assert reds > 40 and whites > 60, (reds, whites)
            # Sidebar backdrop: abstract art in the free space between the menu and the pinned buttons; never behind a row.
            from PySide6.QtCore import QPoint
            window.resize(1280, 1000)
            settle()
            window.navigate("Mods")
            settle()
            rail = window.nav_rail
            image = rail.grab().toImage()
            pinned = next(w for w in rail.findChildren(QWidget) if w.objectName() == "navPinned")
            floor = pinned.mapTo(rail, QPoint(0, 0)).y()
            last = max(item.mapTo(rail, QPoint(0, item.height())).y() for e, item in window.nav_entries.items()
                       if item.isVisibleTo(rail) and not pinned.isAncestorOf(item))
            assert floor - last > 104, ("There is room under the menu for the backdrop at this size", floor, last)
            drawn = [(x, y) for y in range(floor - 90, floor, 3) for x in range(0, image.width(), 5)
                     if image.pixelColor(x, y).red() > 28 and image.pixelColor(x, y).red() > image.pixelColor(x, y).blue() + 8]
            assert drawn, "The abstract backdrop is visible in the free space above the pinned buttons"
            window.close()
            settle()
    print("PASS: shell polish: HD logo and backdrop, the organised sidebar (hubs, pinned, collapse), optional AI Assistant off by default, scan bar floats without shifting any page.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
