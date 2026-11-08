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

            # More Tools sits above Settings and Settings is the last panel.
            order = [route for route, _ in ROUTES]
            assert order[-2:] == ["More Tools", "Settings"], order
            visible = [route for route, control in window.nav_buttons.items() if not control.isHidden()]
            assert visible[-2:] == ["More Tools", "Settings"], visible
            tops = {route: window.nav_buttons[route].geometry().top() for route in visible}
            assert tops["More Tools"] < tops["Settings"] and max(tops.values()) == tops["Settings"], tops

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

            # The scan bar floats along the bottom edge, so starting a scan moves nothing and cuts through nothing.
            for route in ("Mods", "Old Files", "Games", "Ready Room"):
                window.navigate(route)
                settle()
                before = (window.page.geometry(), window.top_bar.geometry())
                window.progress.setRange(0, 100)
                window.progress.setValue(40)
                window.progress.show()
                settle()
                assert (window.page.geometry(), window.top_bar.geometry()) == before, route + " shifted when the bar appeared"
                main = window.progress.parentWidget()
                assert window.progress.geometry().bottom() == main.height() - 1 and window.progress.width() == main.width()
                assert window.progress.geometry().top() >= window.page.geometry().bottom() - 8, "The bar lives at the bottom edge"
                window.progress.hide()
                settle()
            assert window.grab().save(str(args.output / "shell-polish-1280.png"))

            # HD brand art: full-resolution transparent PNGs, resampled to the real pixel size of the widget.
            logo, forest = rw.brand_source("game_grave_logo.png"), rw.brand_source("forest_hd.png")
            assert logo.width() >= 1600 and logo.hasAlphaChannel(), "The logo is a transparent HD PNG"
            assert forest.width() >= 1736 and forest.height() >= 1432
            for dpr in (1.0, 2.0):
                fitted = rw.brand_scaled("game_grave_logo.png", 200, 48, dpr, False)
                assert fitted.width() <= round(200 * dpr) and fitted.height() <= round(48 * dpr) and fitted.devicePixelRatio() == dpr
                assert fitted.width() >= round(200 * dpr) - 1, "The logo fills its box instead of being a small upscaled crop"
                covered = rw.brand_scaled("forest_hd.png", 219, 205, dpr, True)
                assert (covered.width(), covered.height()) == (round(219 * dpr), round(205 * dpr))
            image = window.brand.grab().toImage()
            reds = sum(1 for x in range(0, image.width(), 2) for y in range(0, image.height(), 2)
                       if image.pixelColor(x, y).red() > 170 and image.pixelColor(x, y).green() < 90)
            whites = sum(1 for x in range(0, image.width(), 2) for y in range(0, image.height(), 2)
                         if image.pixelColor(x, y).red() > 235 and image.pixelColor(x, y).green() > 235)
            assert reds > 40 and whites > 60, (reds, whites)
            rail = window.nav_rail.grab().toImage()
            strip = [rail.pixelColor(x, rail.height() - 120).red() for x in range(0, rail.width(), 6)]
            assert max(strip) - min(strip) > 30, "The bottom-left backdrop shows the red forest glow"
            window.close()
            settle()
    print("PASS: shell polish: HD logo and backdrop, More Tools above Settings, optional AI Assistant off by default, scan bar floats without shifting any page.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
