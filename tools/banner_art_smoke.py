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
    from PySide6.QtWidgets import QApplication, QLabel
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
                    if route != "Ready Room":
                        heading = page.content.itemAt(0).widget()
                        marks = [w for w in heading.findChildren(QLabel) if w.text() == "╱"]
                        assert not marks, route + " heading still uses the slash instead of the menu symbol"
                        pictured = [w for w in heading.findChildren(QLabel) if w.pixmap() is not None and not w.pixmap().isNull()]
                        assert pictured, route + " heading shows no menu symbol"
                    shot = window.grab().toImage()
                    left = window.top_bar.mapTo(window, QPoint()).x()
                    top = window.top_bar.mapTo(window, QPoint()).y()
                    seam = top + window.top_bar.height()
                    span = window.top_bar.width()
                    for fraction in (.62, .78, .9):
                        x = left + int(span * fraction)
                        lights = [sum(shot.pixelColor(x + dx, y).getRgb()[:3]) / 3
                                  for y in range(top + 6, seam - 6, 4) for dx in (-6, 0, 6)]
                        assert sum(lights) / len(lights) > 8, f"{route} {width}px: the picture is missing at {fraction:.0%} of the width"
                    # A real seam is a jump the picture itself does not have. Compare the jump across the join with the
                    # jump the same picture has at that spot, so busy artwork is never mistaken for a seam. Buttons and
                    # text on the banner only break a few columns.
                    artwork = getattr(page, "banner_artwork", None)
                    if artwork is not None:
                        banner = artwork.banner
                        banner_x = banner.mapTo(window, QPoint()).x()
                        picture_width = banner.width()
                        picture_height = banner.mapTo(window, QPoint()).y() + banner.height() - top
                    else:  # Ready Room draws its own slice of the same picture
                        banner_x, picture_width, picture_height = left, span, window.top_bar.height() + 98
                    expected = rw.brand_cover(header_banner.ROUTE_ART[route], picture_width, picture_height, 1.0, 1.0, .5).toImage()
                    row = seam - top
                    ground = (2, 7, 10)
                    diffs = []
                    for step in range(14):
                        x = left + int(span * (.60 + .027 * step))
                        rel = min(max(x - banner_x, 0), picture_width - 1)
                        fraction = rel / picture_width
                        fade = 70 * (1 - (fraction - .55) / .45) / 255 if fraction >= .55 else 0.0
                        calm = 150 / 255 * max(0.0, (rel - (picture_width - 235)) / 235)  # top bar only

                        def shown(y, calmed):
                            art = expected.pixelColor(rel, y).getRgb()[:3]
                            out = []
                            for c, g in zip(art, ground):
                                if calmed:
                                    c = c * (1 - calm) + g * calm
                                out.append(c * (1 - fade) + g * fade)
                            return out
                        want = [lo - hi for hi, lo in zip(shown(row - 2, True), shown(row + 2, False))]
                        got = [lo - hi for hi, lo in zip(shot.pixelColor(x, seam - 2).getRgb()[:3],
                                                         shot.pixelColor(x, seam + 2).getRgb()[:3])]
                        diffs.append(max(abs(g - w) for g, w in zip(got, want)))
                    assert min(diffs) < 28 and sorted(diffs)[len(diffs) // 2] < 60, f"{route} {width}px: visible seam in the header picture {diffs}"
                    if width in (1100, 2400) or route in ("Overview", "Games", "Mods"):
                        shot.copy(left, top, span, seam + 130 - top).save(str(args.output / f"banner-{route.lower().replace(' ', '-')}-{width}.png"))
            window.close()
            settle()
    print("PASS: every tab's header picture fills the full width at 1100, 1440 and 2400 px and joins the top bar without a seam.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
