"""Evidence-bound storage instrument for the Crimson Map Room.

Only Windows OS disk_usage supplies capacity numbers. Analyzed category totals
remain separate and may represent partial coverage. No filesystem traversal.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QConicalGradient
from PySide6.QtWidgets import QWidget


class DriveUsageDial(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(214)
        self.setMaximumHeight(254)
        self.used = None
        self.total = None
        self.caption = "CHOOSE A LOCAL DRIVE"
        self.setAccessibleName("Drive disk usage information")

    def set_disk_usage(self, *, total: int | None, used: int | None, name=""):
        self.total = int(total) if total is not None and total > 0 else None
        self.used = int(used) if used is not None and used >= 0 else None
        self.caption = str(name or "LOCAL DRIVE")[:45]
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        bounds = self.rect()
        p.fillRect(bounds, QColor("#081723"))
        x, y = bounds.width()*.5, 102
        radius = min(bounds.width()*.31, 71)
        p.setPen(QPen(QColor("#183849"), 16, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(QRectF(x-radius, y-radius, radius*2, radius*2),
                  90*16, -360*16)
        if self.total and self.used is not None:
            fraction = min(1.0, self.used / self.total)
            # Color coding communicates OS usage, NOT safe-to-reclaim storage.
            color = QColor("#D64059") if fraction >= .85 else QColor("#44D3E9")
            p.setPen(QPen(color, 16, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(QRectF(x-radius, y-radius, radius*2, radius*2),
                      90*16, -round(fraction*360)*16)
            caption = f"{fraction:.0%}"
        else:
            caption = "—"
        p.setPen(QColor("#EEF7FA"))
        p.setFont(QFont("Segoe UI", 24, QFont.Bold))
        p.drawText(QRectF(x-65,y-30,130,49), Qt.AlignCenter,caption)
        p.setPen(QColor("#7ACFDF"))
        p.setFont(QFont("Segoe UI", 9, QFont.DemiBold))
        p.drawText(QRectF(x-95,y+19,190,25), Qt.AlignCenter, "DRIVE USED")
        p.setPen(QColor("#A9BAC7"))
        p.setFont(QFont("Segoe UI", 9))
        p.drawText(QRectF(12,192,bounds.width()-24,24),
                   Qt.AlignCenter|Qt.TextWordWrap,self.caption)
        p.end()
