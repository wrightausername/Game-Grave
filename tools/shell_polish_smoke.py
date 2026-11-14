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
    from PySide6.QtWidgets import QApplication
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

            # Grouped sidebar: Toolbox (More Tools), then the optional AI Assistant, then Settings last.
            order = [route for route, _ in ROUTES]
            assert order[-3:] == ["More Tools", "AI Assistant", "Settings"], order
            visible = [route for route, control in window.nav_buttons.items() if not control.isHidden()]
            assert visible[-2:] == ["More Tools", "Settings"], visible
            # Dropdown groups: one open at a time, the current tab's group opens by itself, one click folds it.
            from PySide6.QtCore import QPoint
            from gg_desktop import nav_rail
            assert window.nav_open_group == "Home" and window.nav_bodies["Home"].isVisible()
            assert all(not window.nav_bodies[g].isVisible() for g in window.nav_bodies if g != "Home"), "Only one group is open"
            window.nav_heads["Library"].click()
            settle()
            assert window.nav_open_group == "Library" and not window.nav_bodies["Home"].isVisible()
            window.nav_heads["Library"].click()
            settle()
            assert window.nav_open_group == "" and not window.nav_bodies["Library"].isVisible(), "A second click folds it away"
            window.navigate("Hardware")
            settle()
            assert window.nav_open_group == "PC and Help" and window.nav_buttons["Hardware"].isVisibleTo(window)
            QTest.qWait(250)
            settle()
            holder = window.nav_scroll.widget()
            shown = [route for route in visible if window.nav_buttons[route].isVisibleTo(window)]
            assert shown == ["Hardware", "More Tools", "Settings"], shown
            tops = {route: window.nav_buttons[route].mapTo(holder, QPoint(0, 0)).y() for route in shown}
            heights = {route: window.nav_buttons[route].height() for route in shown}
            assert min(heights.values()) >= 38, ("Sidebar rows are squeezed", heights)
            ordered = sorted(tops.values())
            assert all(b - a >= 38 for a, b in zip(ordered, ordered[1:])), ("Sidebar rows overlap", tops)
            assert tops["More Tools"] < tops["Settings"] and max(tops.values()) == tops["Settings"], tops
            widths = {window.nav_buttons[route].width() for route in window.nav_buttons}
            assert len(widths) == 1, ("Every sidebar row keeps one width", widths)
            assert window.grab().save(str(args.output / "shell-sidebar-dropdown.png"))
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
            # Sidebar backdrop: abstract art in the free space under the menu only; the menu itself stays clean.
            for size in ((1280, 800), (1280, 1000)):
                window.resize(*size)
                settle()
                window.navigate("Mods")
                settle()
                rail = window.nav_rail
                image = rail.grab().toImage()
                last = max(b.geometry().bottom() for b in window.nav_buttons.values() if b.isVisibleTo(rail))
                drawn = [(x, y) for y in range(image.height() - 90, image.height(), 3) for x in range(0, image.width(), 5)
                         if image.pixelColor(x, y).red() > 28 and image.pixelColor(x, y).red() > image.pixelColor(x, y).blue() + 8]
                assert drawn, "The abstract backdrop is visible in the free space at the bottom of the sidebar"
                assert image.height() - last > 90, "There is room under the menu for the backdrop at this size"
            window.close()
            settle()
    print("PASS: shell polish: HD logo and backdrop, More Tools above Settings, optional AI Assistant off by default, scan bar floats without shifting any page.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
