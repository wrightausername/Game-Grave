"""Render the Overview storage dial at 1x and 3x and check the GG mark is a real cut-out (no photo box, sharp)."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("_ci_temp"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtGui import QColor, QPixmap
    from PySide6.QtWidgets import QApplication
    from gg_desktop.insight_widgets import FootprintRing
    from gg_desktop.reference_overview import OverviewRing

    app = QApplication.instance() or QApplication([])
    GB = 1024 ** 3
    segments = [("Games", 40 * GB, "#ff3b5c"), ("Mods", 9 * GB, "#42d4f2"), ("Other Storage", 6 * GB, "#ffd08e"),
                ("Captures", 4 * GB, "#69dea7"), ("Old Files", 2 * GB, "#a78bfa")]

    def grab(widget, scale):
        widget.resize(180, 180)
        pix = QPixmap(180 * scale, 180 * scale)
        pix.setDevicePixelRatio(scale)
        pix.fill(QColor("#111922"))
        widget.render(pix)
        return pix.toImage()

    new = OverviewRing(segments, scanned=True)
    old = FootprintRing(caption="DETECTED STORAGE")
    old.set_segments(segments, "61 GB")
    assert new.brand_mark and old.brand_mark, "Every storage dial shows the cut-out brand mark"
    for scale in (1, 3):
        image = grab(new, scale)
        assert image.save(str(args.output / f"overview-ring-{scale}x.png"))
        # The mark sits left of centre above the size text. Count strong red pixels there.
        cx, cy = 90 * scale, 90 * scale
        red = 0
        for x in range(cx - 24 * scale, cx + 24 * scale):
            for y in range(cy - 56 * scale, cy - 14 * scale):
                c = QColor(image.pixel(x, y))
                if c.red() > 170 and c.green() < 90 and c.blue() < 110:
                    red += 1
        assert red > 150 * scale * scale / 3, f"The GG mark is missing at {scale}x ({red} red pixels)"
        # No rectangular photo box: the pixel just outside the mark's left corner matches the dial face on the other side.
        corner = QColor(image.pixel(cx - 23 * scale, cy - 55 * scale))
        beside = QColor(image.pixel(cx + 23 * scale, cy - 55 * scale))
        assert abs(corner.lightness() - beside.lightness()) < 40, (corner.name(), beside.name())
    assert grab(old, 1).save(str(args.output / "other-dial-unchanged.png"))
    print("Overview ring smoke passed")


if __name__ == "__main__":
    main()
