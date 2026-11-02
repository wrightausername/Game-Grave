"""Visual-only recovery status dial for actual Game Grave audit records.

A logged record is not proof that a file is currently in the Recycle Bin.
Only records explicitly verified as 'Available' by Windows count as verified.
No fictitious retention time, cumulative recoverable bytes, or rate display.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget, QPushButton


class UndoStatusDial(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("undoRecoveryDial")
        self.setAccessibleName("Recovery availability is based on recorded Windows checks, not guaranteed.")
        self.setMinimumHeight(194)
        self.setMaximumHeight(194)
        self._verified = 0
        self._unknown = 0
        self._total = 0

    def set_records(self, records):
        rows = list(records)
        self._verified = sum(r.get("state") == "Available" for r in rows)
        self._unknown = sum(r.get("state") in ("Not checked", "Needs review")
                            for r in rows)
        self._total = len(rows)
        self.setAccessibleDescription(
            f"{self._verified} previously verified as available, "
            f"{self._unknown} not verified, {self._total} logged.")
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0A111B"))
        diameter = min(142, self.height() - 32, self.width() * .6)
        r = QRectF(17, (self.height() - diameter) / 2, diameter, diameter)
        painter.setBrush(Qt.NoBrush)
        pen = QPen(QColor("#263944"), 15)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawArc(r, 0, 360 * 16)
        if self._total:
            length = int(360 * 16 * self._verified / self._total)
            painter.setPen(QPen(QColor("#4FD8E9"), 15, Qt.SolidLine, Qt.RoundCap))
            if length:
                painter.drawArc(r, 90 * 16, -length)
        painter.setPen(QColor("#FFFFFF"))
        painter.setFont(QFont("Segoe UI", 31, QFont.Bold))
        painter.drawText(r.adjusted(8, 24, -8, -32), Qt.AlignCenter,
                         str(self._verified))
        painter.setFont(QFont("Segoe UI", 8, QFont.DemiBold))
        painter.setPen(QColor("#AEC6D3"))
        painter.drawText(r.adjusted(7, 107, -7, 0), Qt.AlignCenter, "VERIFIED")
        # Text must remain legible in a narrow inspector (320px at 1440).
        # A much larger panel may show more text; nothing may run off the edge.
        x = min(185, int(self.width() * .57))
        measure = max(65, self.width() - x - 14)
        painter.setPen(QColor("#F4F7FB"))
        painter.setFont(QFont("Segoe UI", 13, QFont.DemiBold))
        painter.drawText(QRectF(x, 29, measure, 29),
                         Qt.AlignLeft, str(self._total) + " logged")
        painter.setPen(QColor("#65CDDE"))
        painter.setFont(QFont("Segoe UI", 9, QFont.DemiBold))
        painter.drawText(QRectF(x, 69, measure, 31),
                         Qt.AlignLeft | Qt.TextWordWrap,
                         str(self._verified) + " available")
        painter.setPen(QColor("#E0A9B2"))
        painter.drawText(QRectF(x, 102, measure, 31),
                         Qt.AlignLeft | Qt.TextWordWrap,
                         str(self._unknown) + " unverified")
        painter.setPen(QColor("#9CB0C1"))
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(QRectF(x, 139, measure, 45),
                         Qt.AlignLeft | Qt.TextWordWrap,
                         "Windows rechecks when restoring; recovery is not guaranteed.")
        painter.end()


class RecoveryActionTile(QPushButton):
    """Purpose-drawn recovery command tile with a distinct etched pictogram.

    All clicks are ordinary Qt button actions bound to the existing reversible
    recovery controls. No timer, animation or filesystem operations here.
    """
    def __init__(self, title: str, detail: str, kind: str, parent=None):
        super().__init__(title, parent)
        self.title = title
        self.detail = detail
        self.kind = kind
        self.setObjectName("undoActionTile")
        self.setMinimumHeight(80)
        self.setAccessibleName(title + ". " + detail)
        self.setToolTip(detail)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        highlighted = self.underMouse()
        accent = QColor("#E84764" if self.kind == "restore" else "#50BED7")
        p.setPen(QPen(accent if highlighted else QColor("#465768"), 1.5))
        p.setBrush(QColor("#2E1723" if highlighted else "#0D1924"))
        p.drawRoundedRect(QRectF(1, 1, w-2, h-2), 5, 5)
        p.setPen(QPen(accent, 2.4, Qt.SolidLine, Qt.RoundCap))
        midx, midy = 34, h * .5
        if self.kind == "restore":
            p.drawArc(QRectF(19,midy-15,31,31),30*16,288*16)
            p.drawLine(QPointF(19,midy-4),QPointF(19,midy+10))
            p.drawLine(QPointF(19,midy+10),QPointF(30,midy+2))
        elif self.kind == "bin":
            p.drawLine(QPointF(21,midy-14),QPointF(48,midy-14))
            p.drawLine(QPointF(26,midy-19),QPointF(44,midy-19))
            p.drawRoundedRect(QRectF(24,midy-11,21,29),2,2)
            p.drawLine(QPointF(32,midy-5),QPointF(32,midy+10))
            p.drawLine(QPointF(38,midy-5),QPointF(38,midy+10))
        elif self.kind == "history":
            p.drawEllipse(QRectF(19,midy-16,32,32))
            p.drawLine(QPointF(35,midy),QPointF(35,midy-10))
            p.drawLine(QPointF(35,midy),QPointF(43,midy+5))
        else:
            p.drawEllipse(QRectF(22,midy-14,25,25))
            p.drawEllipse(QRectF(30,midy-6,9,9))
            for dx,dy in ((0,-18), (0,16), (-17,0), (17,0)):
                p.drawLine(QPointF(35,midy),QPointF(35+dx,midy+dy))
        p.setPen(QColor("#F3EFF0"))
        p.setFont(QFont("Segoe UI",11,QFont.Bold))
        p.drawText(QRectF(66, 12, max(50,w-76),27),Qt.AlignVCenter,self.title.upper())
        p.setPen(QColor("#94ACBC"))
        p.setFont(QFont("Segoe UI",9))
        p.drawText(QRectF(66, 40, max(50,w-76),h-45),
                   Qt.AlignTop|Qt.TextWordWrap,self.detail)
        p.end()
