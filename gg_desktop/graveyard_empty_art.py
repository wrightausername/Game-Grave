"""Illustrated, non-decorative empty state for the Crimson Graveyard.

A single crisp vector scene replaces empty tables. No fictitious files,
storage savings, durations, or fake scan results are drawn into the artwork.
"""
from __future__ import annotations

import math
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


class GraveyardEmptyArt(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(270)
        self.setAccessibleName("Holographic game folder above a crimson scan ring; no findings")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor("#08131f"))
        p.save()
        p.translate(w / 2, h * .49)
        factor = min(w / 580, h / 300, 1.65)
        p.scale(factor, factor)

        # Layered holographic scan rings, original vector art.
        for i, alpha in enumerate((85, 155, 225)):
            p.setPen(QPen(QColor(246, 49, 86, alpha), 1.5 + i * 1.1))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QRectF(-160 + i * 12, 76 + i * 6,
                                 320 - i * 24, 46 - i * 12))
        p.setPen(QPen(QColor("#36cee9"), 1.5))
        for n in range(9):
            x = -225 + 55 * n
            p.drawLine(QPointF(x, -130), QPointF(x, -130 + 12 * (n % 3 + 1)))

        # The ghostly floating folder is a recognisable scan icon, not a file.
        halo = QLinearGradient(0, -90, 0, 90)
        halo.setColorAt(0, QColor(50, 176, 207, 125))
        halo.setColorAt(.48, QColor(12, 49, 76, 235))
        halo.setColorAt(1, QColor(9, 26, 46, 180))
        folder = QPainterPath()
        folder.moveTo(-107, -48)
        folder.lineTo(-107, -79)
        folder.quadTo(-107, -90, -95, -90)
        folder.lineTo(-33, -90)
        folder.lineTo(-18, -71)
        folder.lineTo(91, -71)
        folder.quadTo(107, -71, 107, -53)
        folder.lineTo(107, 45)
        folder.quadTo(107, 61, 91, 61)
        folder.lineTo(-92, 61)
        folder.quadTo(-107, 61, -107, 45)
        folder.closeSubpath()
        p.setBrush(halo)
        p.setPen(QPen(QColor("#62d9f5"), 3))
        p.drawPath(folder)
        p.setPen(QPen(QColor(176, 241, 255, 85), 1))
        p.drawLine(QPointF(-88, -55), QPointF(88, -55))
        p.drawLine(QPointF(-87, 40), QPointF(88, 40))

        # Controller pictogram etched into the folder.
        ctrl = QPainterPath()
        ctrl.moveTo(-60, 0)
        ctrl.cubicTo(-66, -29, -37, -32, -18, -24)
        ctrl.lineTo(18, -24)
        ctrl.cubicTo(37, -32, 66, -29, 60, 0)
        ctrl.cubicTo(55, 20, 42, 19, 26, 2)
        ctrl.lineTo(-26, 2)
        ctrl.cubicTo(-42, 19, -55, 20, -60, 0)
        p.setBrush(QColor("#0b2437"))
        p.setPen(QPen(QColor("#86daed"), 3))
        p.drawPath(ctrl)
        p.drawLine(QPointF(-30, -17), QPointF(-30, -2))
        p.drawLine(QPointF(-38, -9), QPointF(-22, -9))
        for x, y in ((31, -15), (40, -6), (22, -6)):
            p.setBrush(QColor("#f44268"))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(x, y), 3, 3)
        p.restore()
        p.end()
