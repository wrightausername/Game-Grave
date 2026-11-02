"""A restrained, actual-data-only playtime timeline for Crimson Ready Room.

The playtime chart draws only explicitly completed local session records. It
does not infer Steam hours or imply we know activity before tracking began.
Static QPainter at resize/data changes: no GPU effects or animation loops.
"""
from __future__ import annotations
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget


class PlaytimeTimeline(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("readyRoomPlaytimeTimeline")
        self.setMinimumHeight(178)
        self.setMaximumHeight(178)
        self.setAccessibleName("Tracked gaming session time by month")
        self._months = [0] * 12

    def set_seconds(self, values):
        if len(values) != 12:
            raise ValueError("Expected January through December.")
        self._months = [max(0, int(v)) for v in values]
        summary = ", ".join(
            f"{name}: {round(value/3600, 1)} hours"
            for name, value in zip(
                ("Jan","Feb","Mar","Apr","May","Jun",
                 "Jul","Aug","Sep","Oct","Nov","Dec"), self._months))
        self.setAccessibleDescription(
            "Only manually tracked, finished local Game Grave sessions. " + summary)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#101219"))
        frame = QRectF(self.rect()).adjusted(14, 12, -14, -25)
        for mark in (.25, .5, .75, 1.):
            line_y = frame.bottom() - mark * frame.height()
            painter.setPen(QPen(QColor("#293039"), 1))
            painter.drawLine(int(frame.left()), int(line_y),
                             int(frame.right()), int(line_y))
        highest = max(self._months)
        labels = ("J","F","M","A","M","J","J","A","S","O","N","D")
        available = max(0., frame.width())
        step = available / 12
        width = max(3.0, min(26., step - 8))
        for index, (seconds, tag) in enumerate(zip(self._months, labels)):
            x = frame.x() + (index + .5) * step - width / 2
            if highest and seconds:
                h = max(2., (seconds / highest) * (frame.height() - 15))
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor("#D73B53" if seconds < highest
                                        else "#FF6475"))
                painter.drawRoundedRect(
                    QRectF(x, frame.bottom() - h, width, h), 2, 2)
            painter.setPen(QColor("#9FAEBB"))
            painter.setFont(QFont("Segoe UI", 9))
            painter.drawText(QRectF(x - 5, frame.bottom() + 5,
                                    width + 10, 18), Qt.AlignCenter, tag)
        if not highest:
            painter.setPen(QColor("#AEBCC9"))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(
                frame, Qt.AlignCenter | Qt.TextWordWrap,
                "No tracked sessions yet. Your timeline starts "
                "when you choose to record a session.")
        painter.end()
