"""Native Qt check that Games marks and art are drawn at real device pixels, never from low-res photo crops."""
from __future__ import annotations

import argparse
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
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
    from PySide6.QtWidgets import QApplication
    from gg_desktop import reference_widgets as rw

    app = QApplication.instance() or QApplication([])

    # 1. Every launcher mark is a 4x device-pixel render of a vector badge, not a ~35px photo crop.
    for name in rw.LAUNCHER_MARKS:
        pix = rw.launcher_pixmap(name, 22, 4)
        assert pix.width() == 88 and pix.height() == 88 and pix.devicePixelRatio() == 4, (name, pix.size())
        image = pix.toImage()
        assert image.pixelColor(0, 0).alpha() == 0, "corner should be transparent (rounded badge)"
        assert image.pixelColor(44, 44).alpha() > 0
        assert rw.icon(name, size=22).pixmap(22, 22).isNull() is False
    assert rw.launcher_pixmap("epic").toImage() != rw.launcher_pixmap("gog").toImage()
    pix = rw.launcher_pixmap("ea", 40, 4)
    pix.toImage().save(str(args.output / "games-launcher-marks.png"))

    # 2. Official artwork dropped into assets/launchers wins over the monogram.
    with tempfile.TemporaryDirectory(prefix="GG-launcher-") as temp:
        custom = Path(temp)
        solid = QImage(64, 64, QImage.Format_ARGB32)
        solid.fill(QColor("#ff00ff"))
        solid.save(str(custom / "gog.png"))
        with patch.object(rw, "LAUNCHER_ASSETS", custom):
            rw.launcher_pixmap.cache_clear()
            supplied = rw.launcher_pixmap("gog", 22, 4).toImage()
            assert supplied.pixelColor(44, 44) == QColor("#ff00ff"), supplied.pixelColor(44, 44)
        rw.launcher_pixmap.cache_clear()
    assert rw.launcher_pixmap("gog", 22, 4).toImage().pixelColor(44, 44) != QColor("#ff00ff")

    # 3. Cover art is fitted to device pixels: on a 2x surface a 100x150 box paints 200x300 real pixels, no stretch.
    source = QPixmap(600, 900)
    source.fill(QColor("#22aa66"))
    for dpr in (1, 2, 3):
        target = QPixmap(100 * dpr, 150 * dpr)
        target.setDevicePixelRatio(dpr)
        target.fill(Qt.transparent)
        painter = QPainter(target)
        rw.draw_cover(painter, QRectF(0, 0, 100, 150), "Test Game", pixmap=source)
        painter.end()
        image = target.toImage()
        assert image.pixelColor(0, 0) == QColor("#22aa66") and image.pixelColor(100 * dpr - 1, 150 * dpr - 1) == QColor("#22aa66"), dpr
    fit = rw._cover_fit(source, 100, 150, 2)
    assert fit.width() == 200 and fit.height() == 300 and fit.devicePixelRatio() == 2

    # 4. Without art a game gets a crisp monogram placeholder, and photo crops are off outside the design preview.
    assert rw.PHOTO_COVERS["on"] is False
    assert rw._monogram("Cyberpunk 2077") == "C2" and rw._monogram("The Witcher 3: Wild Hunt") == "TW"
    placeholder = QPixmap(200, 120)
    placeholder.fill(Qt.transparent)
    painter = QPainter(placeholder)
    rw.draw_cover(painter, QRectF(0, 0, 200, 120), "Baldur's Gate 3")
    painter.end()
    placeholder.save(str(args.output / "games-placeholder-cover.png"))
    colors = {placeholder.toImage().pixelColor(x, y).rgb() for x in range(60, 140, 4) for y in range(30, 90, 4)}
    assert len(colors) > 6, "monogram should be drawn over the gradient"
    print("PASS: Games launcher marks are 4x vector badges (official art overrides), covers fit to real device "
          "pixels at 1x/2x/3x, and games without art get a monogram instead of a stretched photo crop.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
