"""Single-frame library graphics backed by verified launcher records.

These paint only on resize/exposure. No timers, overlays, polling or fabricated
storage measurements, so visual polish cannot become a gaming-performance tax.
"""
from __future__ import annotations

from collections import Counter
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QFrame


class LauncherMixGraphic(QFrame):
    """Color-coded mix of the user's actual installed launcher records."""

    PALETTE = ("#F0435A", "#4FC8E7", "#BD8EE8", "#5AD5A4",
               "#EFAD61", "#7AA7EE", "#E178A4")

    def __init__(self, games, parent=None):
        super().__init__(parent)
        self.setObjectName("launcherMixGraphic")
        self.setMinimumHeight(94)
        self.setMaximumHeight(108)
        self.setAccessibleName("Installed games grouped by verified launcher")
        counts = Counter(str(g.launcher) for g in games)
        self.groups = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        self.total = sum(counts.values())
        self.setToolTip("\n".join(
            f"{launcher}: {count} detected game(s)"
            for launcher, count in self.groups) or "No games detected")

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        bg = QLinearGradient(0,0,w,h)
        bg.setColorAt(0, QColor("#161A28"))
        bg.setColorAt(1, QColor("#0C1722"))
        p.setPen(QPen(QColor("#374253"), 1))
        p.setBrush(bg)
        p.drawRoundedRect(QRectF(.5,.5,w-1,h-1),9,9)
        p.setPen(QColor("#EFF4FA"))
        p.setFont(QFont("Segoe UI",12,QFont.Bold))
        p.drawText(QRectF(13,6,w-26,24),Qt.AlignVCenter,
                   "INSTALLED GAMES  /  LAUNCHER MIX")
        p.setPen(QColor("#A7B6C6"))
        p.setFont(QFont("Segoe UI",10))
        p.drawText(QRectF(w-180,6,166,24),
                   Qt.AlignRight|Qt.AlignVCenter,
                   str(self.total)+" verified installations")
        usable = max(1,w-28)
        track = QRectF(14,38,usable,14)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#283747"))
        p.drawRoundedRect(track,6,6)
        if self.total:
            x = 14.
            for i, (_, count) in enumerate(self.groups):
                segment = usable*count/self.total
                p.setBrush(QColor(self.PALETTE[i % len(self.PALETTE)]))
                p.drawRect(QRectF(x,38,segment,14))
                x += segment
        x, y = 14, 63
        p.setFont(QFont("Segoe UI",10))
        for i,(launcher,count) in enumerate(self.groups[:8]):
            short = p.fontMetrics().elidedText(
                f"{launcher}: {count}", Qt.ElideRight, 125)
            advance = max(72,p.fontMetrics().horizontalAdvance(short)+22)
            if x+advance >= w-10:
                break
            p.setBrush(QColor(self.PALETTE[i % len(self.PALETTE)]))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(x,y+4,8,8),2,2)
            p.setPen(QColor("#D9E3EE"))
            p.drawText(QRectF(x+14,y,advance-12,21),
                       Qt.AlignVCenter,short)
            x += advance+8
        p.end()
