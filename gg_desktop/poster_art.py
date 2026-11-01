"""Original high-DPI illustrated cover fallback for Game Grave Crimson.

Never presents decorative graphics as a real publisher's cover. Used only when
no legitimate locally installed game artwork is available.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, QPointF, Qt
from PySide6.QtGui import (
    QColor, QFont, QLinearGradient, QPainter, QPainterPath,
    QPen, QPixmap, QRadialGradient,
)


def generated_game_poster(title: str, width: int, height: int) -> QPixmap:
    """Generate stable procedural art, not a fabricated store image."""
    title = str(title or "Unknown game").strip()[:80]
    w, h = max(100, int(width)), max(90, int(height))
    scale = 2
    out = QPixmap(w * scale, h * scale)
    out.fill(QColor("#081019"))
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.scale(scale, scale)
    seed = sum((i + 1) * ord(c) for i, c in enumerate(title))
    colors = [
        ("#EF3C5D", "#12142A", "#30C2D3"),
        ("#25BCD3", "#10182B", "#F74261"),
        ("#F08953", "#1C1528", "#F6405A"),
        ("#A36BDB", "#151329", "#E84D70"),
    ]
    main, dark, edge = colors[seed % len(colors)]
    background = QLinearGradient(0, 0, w, h)
    background.setColorAt(0, QColor(dark))
    background.setColorAt(.49, QColor("#172336"))
    background.setColorAt(1, QColor("#060B11"))
    p.fillRect(QRectF(0, 0, w, h), background)

    # Decorative red moon and distant citadel silhouette.
    cx, cy = w * (.68 + (seed % 4) * .025), h * .30
    radius = min(w * .30, h * .37)
    glow = QRadialGradient(cx, cy, radius * 2.0)
    glow.setColorAt(0, QColor(main))
    soft = QColor(main)
    soft.setAlpha(108)
    glow.setColorAt(.48, soft)
    glow.setColorAt(1, QColor("#00000000"))
    p.setPen(Qt.NoPen)
    p.setBrush(glow)
    p.drawEllipse(QPointF(cx, cy), radius * 2, radius * 2)
    p.setBrush(QColor(main))
    p.drawEllipse(QPointF(cx, cy), radius * .78, radius * .78)
    p.setBrush(QColor("#E6E2E9"))
    p.setOpacity(.10)
    p.drawEllipse(QPointF(cx - radius * .18, cy - radius * .15),
                  radius * .32, radius * .32)
    p.setOpacity(1.0)

    # Ancient broken walls. Vary the roofline deterministically for each card.
    p.setBrush(QColor("#0A1823"))
    mountains = QPainterPath()
    mountains.moveTo(0, h * .63)
    for x, y in [
        (w * .10, .40), (w * .18, .51), (w * .29, .33),
        (w * .39, .56), (w * .55, .41), (w * .67, .55),
        (w * .84, .34), (w, .57)]:
        mountains.lineTo(x, h * y)
    mountains.lineTo(w, h)
    mountains.lineTo(0, h)
    p.drawPath(mountains)
    p.setBrush(QColor("#050D16"))
    for i, xpos in enumerate((.09, .48, .87)):
        bw = w * (.085 if i == 1 else .055)
        bh = h * (.28 + (seed % (i + 4)) * .025)
        bx, by = w * xpos, h * .72 - bh
        p.drawRect(QRectF(bx, by, bw, bh))
        tower = QPainterPath()
        tower.moveTo(bx - 3, by)
        tower.lineTo(bx + bw / 2, by - bh * .19)
        tower.lineTo(bx + bw + 3, by)
        tower.closeSubpath()
        p.drawPath(tower)

    # Sharp red/Cyan highlight accents retain the approved theme.
    pen = QPen(QColor(edge), max(1.0, w / 160))
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    for a, b in ((.12, .44), (.58, .84)):
        p.drawLine(QPointF(w * a, h * .62), QPointF(w * b, h * .62))
    p.setPen(Qt.NoPen)
    shade = QLinearGradient(0, h * .42, 0, h)
    shade.setColorAt(0, QColor("#00000000"))
    shade.setColorAt(.48, QColor(3, 8, 12, 200))
    shade.setColorAt(1, QColor("#010509"))
    p.fillRect(QRectF(0, h * .35, w, h * .65), shade)

    p.setPen(QColor("#D5EBF2"))
    p.setFont(QFont("Segoe UI", max(7, min(9, int(w / 27))), QFont.DemiBold))
    p.drawText(QRectF(9, 7, w - 18, 16),
               Qt.AlignLeft | Qt.AlignVCenter, "GAME GRAVE  /  ORIGINAL ART")
    p.setFont(QFont("Segoe UI", max(10, min(16, int(w / 13))), QFont.Bold))
    p.setPen(QColor("#FFFFFF"))
    p.drawText(QRectF(8, h * .58, w - 16, h * .28),
               Qt.AlignCenter | Qt.TextWordWrap, title.upper())
    p.setPen(QColor(edge))
    p.setFont(QFont("Segoe UI", max(7, min(9, int(w / 25))), QFont.DemiBold))
    p.drawText(QRectF(8, h * .87, w - 16, h * .10),
               Qt.AlignCenter | Qt.AlignVCenter, "LOCAL COVER NOT FOUND")
    p.end()
    out.setDevicePixelRatio(scale)
    return out
