"""Original native, evidence-aware layered Game DNA visual.

Never computes fictional game footprint totals. A colored layer means
verified game install or directly linked game-local mods; all other
relationships are outlined as not independently attributed.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget


class GenomeLayerMap(QWidget):
    LAYERS = (
        ("GAME INSTALL", "#43D8F2"),
        ("MODS & ADDONS", "#C36EFE"),
        ("SAVES", "#52B4E7"),
        ("CONFIGS", "#FFCC62"),
        ("LEFTOVERS", "#F05B72"),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(275)
        self.setMaximumHeight(355)
        self._confirmed = set()
        self.setAccessibleName(
            "Layered game DNA evidence map. Only highlighted sources are verified.")

    def set_evidence(self, *, install=False, linked_mods=False):
        self._confirmed = (
            ({"GAME INSTALL"} if install else set()) |
            ({"MODS & ADDONS"} if linked_mods else set()))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#070F1B"))
        width, height = self.width(), self.height()
        sx = max(.53, min(1.1, width/400))
        sy = max(.65, min(1.2, height/330))
        p.save()
        p.translate(width*.46, height*.17)
        p.scale(sx, sy)
        for index, (title, hexcolor) in enumerate(self.LAYERS):
            oy = index*43
            found = title in self._confirmed
            tone = QColor(hexcolor)
            # Perspective outline is authored QPainter geometry, no image cache.
            pts = QPolygonF([
                QPointF(-95, 24+oy), QPointF(0, -4+oy),
                QPointF(110, 24+oy), QPointF(12, 58+oy)])
            face = QColor(tone)
            face.setAlpha(48 if found else 12)
            p.setBrush(face)
            edge = QColor(tone if found else QColor("#446078"))
            edge.setAlpha(238 if found else 112)
            p.setPen(QPen(edge, 2.7 if found else 1.3))
            p.drawPolygon(pts)
            p.drawLine(QPointF(-95,24+oy),QPointF(-95,32+oy))
            p.drawLine(QPointF(-95,32+oy),QPointF(12,66+oy))
            p.drawLine(QPointF(12,66+oy),QPointF(110,32+oy))
            p.drawLine(QPointF(110,24+oy),QPointF(110,32+oy))
            # Ghosted layers don't imply file identity from title similarity.
            p.setPen(QPen(tone if found else QColor("#6A7889"),1.5))
            p.drawLine(QPointF(112,24+oy),QPointF(130,24+oy))
            p.setFont(QFont("Segoe UI",8,QFont.DemiBold))
            p.drawText(QRectF(134,12+oy,134,27),
                       Qt.AlignVCenter,
                       title+("  •" if found else "  ?"))
        p.restore()
        p.end()
