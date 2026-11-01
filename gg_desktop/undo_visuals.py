"""Visual-only recovery status dial for actual Game Grave audit records.

A logged record is not proof that a file is currently in the Recycle Bin.
Only records explicitly verified as 'Available' by Windows count as verified.
No fictitious retention time, cumulative recoverable bytes, or rate display.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget


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
        x = 185
        painter.setPen(QColor("#F4F7FB"))
        painter.setFont(QFont("Segoe UI", 15, QFont.DemiBold))
        painter.drawText(QRectF(x, 30, self.width() - x - 10, 31),
                         Qt.AlignLeft, str(self._total) + " logged")
        painter.setPen(QColor("#65CDDE"))
        painter.setFont(QFont("Segoe UI", 11, QFont.DemiBold))
        painter.drawText(QRectF(x, 70, self.width() - x - 12, 28),
                         Qt.AlignLeft, str(self._verified) + " Windows checks: available")
        painter.setPen(QColor("#E0A9B2"))
        painter.drawText(QRectF(x, 102, self.width() - x - 12, 28),
                         Qt.AlignLeft, str(self._unknown) + " unverified / review")
        painter.setPen(QColor("#9CB0C1"))
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(QRectF(x, 138, self.width() - x - 14, 42),
                         Qt.AlignLeft | Qt.TextWordWrap,
                         "Availability is rechecked when restoring. "
                         "Windows can empty the bin at any time.")
        painter.end()
