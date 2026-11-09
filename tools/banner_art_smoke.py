"""Native Qt check that every tab's header picture fills the whole header width (no empty or stretched area) at
small, normal and very wide windows, and that the picture runs unbroken from the top bar into the banner."""
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
    from PySide6.QtCore import QCoreApplication, QEvent, QPoint
    from PySide6.QtWidgets import QApplication
    import core
    from gg_desktop import header_banner
    from gg_desktop import reference_widgets as rw
    from gg_desktop.app import CrimsonWindow, ROUTES

    app = QApplication.instance() or QApplication([])

    def settle():
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()

    with tempfile.TemporaryDirectory(prefix="GG-banner-") as temp:
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
            settings = core.default_settings()
            settings["assistant_enabled"] = True
            core.save_settings(settings)
            window = CrimsonWindow()
            window.show()
            for name in set(header_banner.ROUTE_ART.values()):
                picture = rw.brand_source(name)
                assert not picture.isNull() and picture.width() >= 6000 and picture.width() / picture.height() >= 10, name
            for route, _ in ROUTES:
                assert route in header_banner.ROUTE_ART, route + " has no header picture"
            for width in (1100, 1440, 2400):
                window.resize(width, 760)
                for route, _ in ROUTES:
                    window.navigate(route)
                    settle()
                    assert window.current_route == route, route
                    page = window.page
                    assert getattr(page, "banner_artwork", None) is not None or route == "Ready Room", route + " has no banner artwork"
                    shot = window.grab().toImage()
                    left = window.top_bar.mapTo(window, QPoint()).x()
                    top = window.top_bar.mapTo(window, QPoint()).y()
                    seam = top + window.top_bar.height()
                    span = window.top_bar.width()
                    for fraction in (.62, .78, .9):
                        x = left + int(span * fraction)
                        lights = [sum(shot.pixelColor(x + dx, y).getRgb()[:3]) / 3
                                  for y in range(top + 6, seam - 6, 4) for dx in (-6, 0, 6)]
                        assert sum(lights) / len(lights) > 11, f"{route} {width}px: the picture is missing at {fraction:.0%} of the width"
                    x = left + int(span * .8)
                    above, below = shot.pixelColor(x, seam - 2).getRgb(), shot.pixelColor(x, seam + 2).getRgb()
                    assert max(abs(a - b) for a, b in zip(above[:3], below[:3])) < 28, f"{route} {width}px: visible seam in the header picture"
                    if width in (1100, 2400) or route in ("Overview", "Games", "Mods"):
                        shot.copy(left, top, span, seam + 130 - top).save(str(args.output / f"banner-{route.lower().replace(' ', '-')}-{width}.png"))
            window.close()
            settle()
    print("PASS: every tab's header picture fills the full width at 1100, 1440 and 2400 px and joins the top bar without a seam.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
