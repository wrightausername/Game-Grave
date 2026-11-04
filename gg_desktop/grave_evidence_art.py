"""Cinematic, evidence-only Graveyard inspector graphic.

Pure presentation: no file reads, no usage assertions, no deletion authority.
The design intentionally does not show an unrelated game's promotional art.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QFont
from PySide6.QtWidgets import QFrame


class GraveEvidenceBanner(QFrame):
    """An original red archive illustration for the selected real file."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("graveEvidenceBanner")
        self.setFixedHeight(112)
        self._title = "Select a finding"
        self._category = "LOCAL EVIDENCE"
        self.setAccessibleName("Selected Graveyard file visual context")

    def set_entry(self, entry):
        self._title = str(getattr(entry, "name", "") or "Unnamed finding")
        self._category = str(getattr(entry, "category", "") or "Unknown source")
        self.setToolTip(self._title + "\n" + self._category)
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        rect = QRectF(0, 0, w - 1, h - 1)
        bg = QLinearGradient(0, 0, w, h)
        bg.setColorAt(0, QColor("#20101D"))
        bg.setColorAt(.55, QColor("#111823"))
        bg.setColorAt(1, QColor("#08121B"))
        p.setBrush(bg)
        p.setPen(QPen(QColor("#693147"), 1))
        p.drawRoundedRect(rect, 9, 9)
        # Atmospheric red light behind the archive/folder shape.
        glow = QLinearGradient(12, 0, 112, h)
        glow.setColorAt(0, QColor(242, 41, 69, 110))
        glow.setColorAt(1, QColor(242, 41, 69, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QRectF(5, -14, 133, 138))
        p.setPen(QPen(QColor("#FE4B64"), 2))
        folder = QPainterPath()
        folder.moveTo(18, 40)
        folder.lineTo(38, 40)
        folder.lineTo(45, 30)
        folder.lineTo(76, 30)
        folder.lineTo(83, 40)
        folder.lineTo(103, 40)
        folder.lineTo(99, 88)
        folder.lineTo(21, 88)
        folder.closeSubpath()
        p.setBrush(QColor("#A41D39"))
        p.drawPath(folder)
        p.setPen(QPen(QColor("#FF8691"), 1))
        p.drawLine(QPointF(25, 50), QPointF(96, 50))
        # Real selected item name, never sample/mockup labels.
        p.setPen(QColor("#FFFFFF"))
        p.setFont(QFont("Segoe UI", 13, QFont.Bold))
        fm = p.fontMetrics()
        title = fm.elidedText(self._title, Qt.ElideMiddle, max(50, w-145))
        p.drawText(QRectF(123, 24, max(48, w-139), 34),
                   Qt.AlignLeft | Qt.AlignVCenter, title)
        p.setPen(QColor("#DD9AAA"))
        p.setFont(QFont("Segoe UI", 10))
        category = p.fontMetrics().elidedText(
            self._category.upper(), Qt.ElideRight, max(50, w-145))
        p.drawText(QRectF(123, 59, max(48, w-139), 29),
                   Qt.AlignLeft | Qt.AlignVCenter, category)
        p.end()
