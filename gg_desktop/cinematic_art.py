"""Native, scalable Game Grave decorative art for locked UI panels.

No remote images, fabricated telemetry or expensive animations. Each widget
paints once when exposed/resized; gameplay and scanning paths remain untouched.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen,
    QPolygonF, QRadialGradient,
)
from PySide6.QtWidgets import QWidget, QFrame


class CinematicToolArtwork(QFrame):
    """Unique high-DPI art for Resurrection Kit, Save Vault and local AI."""

    def __init__(self, mode: str = "kit", parent=None):
        super().__init__(parent)
        if mode not in ("kit", "vault", "assistant", "scanner"):
            raise ValueError("Unknown Game Grave artwork mode")
        self.mode = mode
        self.setMinimumHeight(116)
        self.setMaximumHeight(155 if mode == "assistant" else 130)
        self.setAccessibleName(
            {"kit": "Resurrection Kit crimson recovery insignia",
             "vault": "Save Vault cyan protected shield",
             "assistant": "Game Grave local AI red signal artwork",
             "scanner": "Game Grave read-only scan radar artwork"}[mode])

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        w, h = self.width(), self.height()
        p.setPen(Qt.NoPen)
        bounds = QRectF(0, 0, w, h)
        mask = QPainterPath()
        mask.addRoundedRect(bounds, 9, 9)
        p.setClipPath(mask)
        backdrop = QLinearGradient(0, 0, w, h)
        backdrop.setColorAt(0, QColor("#0B1420"))
        backdrop.setColorAt(.44, QColor("#1B1523"))
        backdrop.setColorAt(1, QColor("#07151E" if self.mode == "vault"
                                       else "#2B111D"))
        p.fillRect(bounds, backdrop)
        cyan = self.mode == "vault"
        primary = QColor("#36DBE3" if cyan else "#FD405C")
        secondary = QColor("#66A3FF" if cyan else "#BD3C85")
        center = QPointF(w * .50, h * .51)
        # Low-cost fixed circuit filaments, never a looping animation.
        p.setPen(QPen(QColor(68, 114, 143, 40), 1))
        for j in range(9):
            yy = 10 + j * (h / 9)
            p.drawLine(QPointF(0, yy), QPointF(w, yy))
        for j in range(14):
            xx = j * (w / 13)
            p.drawLine(QPointF(xx, 0), QPointF(xx, h))
        halo = QRadialGradient(center, max(70., h * 1.65))
        shine = QColor(primary)
        shine.setAlpha(130)
        halo.setColorAt(0, shine)
        fade = QColor(primary)
        fade.setAlpha(8)
        halo.setColorAt(.58, fade)
        halo.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(halo)
        p.setPen(Qt.NoPen)
        p.drawEllipse(center, max(90., w * .38), h * .96)
        for radius, alpha, thick in ((55, 47, 1), (45, 80, 1), (34, 130, 2)):
            rim = QColor(primary)
            rim.setAlpha(alpha)
            p.setPen(QPen(rim, thick))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(center, radius, radius * .87)
        # Non-verbal recovery / shield / intelligence symbol.
        p.setBrush(QColor("#101A26"))
        p.setPen(QPen(primary, 2.6))
        if self.mode == "vault":
            # Locked reference: cyan secure-vault silhouette, not a generic
            # checkmark. Original vector art, drawn only on exposure.
            shield = QPainterPath()
            shield.moveTo(center.x(), center.y() - 43)
            shield.lineTo(center.x() + 39, center.y() - 29)
            shield.lineTo(center.x() + 32, center.y() + 16)
            shield.quadTo(center.x() + 18, center.y() + 37,
                          center.x(), center.y() + 44)
            shield.quadTo(center.x() - 18, center.y() + 37,
                          center.x() - 32, center.y() + 16)
            shield.lineTo(center.x() - 39, center.y() - 29)
            shield.closeSubpath()
            p.drawPath(shield)
            p.setPen(QPen(primary, 3.8, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(QRectF(center.x()-19, center.y()-21, 38, 40),
                      0, 180*16)
            p.setPen(QPen(QColor("#89F5F3"), 2.3))
            p.setBrush(QColor("#09212C"))
            p.drawRoundedRect(QRectF(center.x()-23,center.y()-2,46,31),4,4)
            p.setPen(Qt.NoPen)
            p.setBrush(primary)
            p.drawEllipse(QPointF(center.x(),center.y()+9),3.4,3.4)
            p.drawRoundedRect(QRectF(center.x()-2,center.y()+9,4,9),1,1)
        elif self.mode == "kit":
            # The approved Resurrection Kit is a controller framed by a
            # crimson resurrection halo, not a second GG logo.
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(primary, 4.4, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(QRectF(center.x()-42,center.y()-42,84,84),
                      50*16, 262*16)
            arrow = QPolygonF([
                QPointF(center.x()+29,center.y()-36),
                QPointF(center.x()+47,center.y()-28),
                QPointF(center.x()+27,center.y()-17)])
            p.setPen(Qt.NoPen)
            p.setBrush(primary)
            p.drawPolygon(arrow)
            controller = QPainterPath()
            controller.moveTo(center.x()-27,center.y()-4)
            controller.quadTo(center.x()-26,center.y()-16,
                              center.x()-10,center.y()-14)
            controller.lineTo(center.x()+10,center.y()-14)
            controller.quadTo(center.x()+26,center.y()-16,
                              center.x()+27,center.y()-4)
            controller.lineTo(center.x()+33,center.y()+14)
            controller.quadTo(center.x()+34,center.y()+25,
                              center.x()+23,center.y()+20)
            controller.lineTo(center.x()+13,center.y()+12)
            controller.lineTo(center.x()-13,center.y()+12)
            controller.lineTo(center.x()-23,center.y()+20)
            controller.quadTo(center.x()-34,center.y()+25,
                              center.x()-33,center.y()+14)
            controller.closeSubpath()
            p.setBrush(QColor("#170E1B"))
            p.setPen(QPen(QColor("#FF9A9F"), 2.7))
            p.drawPath(controller)
            p.setPen(QPen(QColor("#FFF3F5"), 2.8, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(center.x()-17,center.y()-2),
                       QPointF(center.x()-17,center.y()+9))
            p.drawLine(QPointF(center.x()-23,center.y()+4),
                       QPointF(center.x()-11,center.y()+4))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#F75674"))
            for xx, yy in ((17,0),(22,5),(12,5)):
                p.drawEllipse(QPointF(center.x()+xx,center.y()+yy),2.3,2.3)
        elif self.mode == "assistant":
            p.setPen(QPen(primary, 3, Qt.SolidLine, Qt.RoundCap))
            prev = QPointF(center.x()-55, center.y())
            for n in range(1, 35):
                x = center.x()-55 + n * 3.2
                amp = 25 * math.exp(-abs(x-center.x()) / 34)
                y = center.y() - math.sin(n*.74) * amp
                pt = QPointF(x, y)
                p.drawLine(prev, pt)
                prev = pt
            p.setPen(QPen(primary, 1.5))
            p.drawEllipse(center, 37, 37)
            p.setFont(QFont("Segoe UI", 17, QFont.Bold))
            p.setPen(QColor("#F6F7FB"))
            p.drawText(QRectF(center.x()-27, center.y()-16, 54, 32),
                       Qt.AlignCenter, "GG")
        else:
            p.setPen(QPen(primary, 2))
            for radius in (21, 35, 46):
                p.drawArc(QRectF(center.x()-radius,center.y()-radius,
                                 radius*2,radius*2), 25*16, 280*16)
            p.drawLine(QPointF(center.x(),center.y()),
                       QPointF(center.x()+33,center.y()-28))
        # Small asymmetric highlights give depth without mocked content.
        p.setPen(QPen(secondary, 1.5))
        for side in (-1, 1):
            for n in range(3):
                y = 29 + n * 30
                start = QPointF(center.x()+side*78, y)
                end = QPointF(center.x()+side*(100+n*15), y)
                p.drawLine(start, end)
                p.setBrush(primary)
                p.setPen(Qt.NoPen)
                p.drawEllipse(end, 2.4, 2.4)
                p.setPen(QPen(secondary, 1.5))
        p.setClipping(False)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(primary.red(),primary.green(),primary.blue(),115), 1))
        p.drawRoundedRect(bounds.adjusted(.5,.5,-.5,-.5),9,9)
        p.end()


class CinematicImpactTrack(QWidget):
    """Proportional share of observed candidates; never a disk-free-space claim."""

    def __init__(self, reviewable_bytes: int, protected_bytes: int, parent=None):
        super().__init__(parent)
        self.reviewable = max(0, int(reviewable_bytes))
        self.protected = max(0, int(protected_bytes))
        self.setMinimumHeight(27)
        self.setMaximumHeight(27)
        self.setAccessibleName(
            "Potential candidate size, grouped into reviewable and protected: "
            + str(self.reviewable) + " and " + str(self.protected)
            + " apparent bytes, not actual storage reclaimed.")

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        track = QRectF(0, 7, max(0, self.width()), 13)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#283340"))
        p.drawRoundedRect(track, 6.5, 6.5)
        total = self.reviewable + self.protected
        if total > 0 and track.width() >= 20:
            portion = track.width() * self.reviewable / total
            if portion > 0:
                glow = QLinearGradient(0, 0, portion, 0)
                glow.setColorAt(0, QColor("#CC273F"))
                glow.setColorAt(1, QColor("#FA5068"))
                p.setBrush(glow)
                p.drawRoundedRect(QRectF(0, 7, portion, 13), 6.5, 6.5)
            if self.protected > 0:
                p.setBrush(QColor("#3CCEA5"))
                p.drawRoundedRect(QRectF(portion, 7,
                                         track.width()-portion, 13), 6.5, 6.5)
        p.end()
