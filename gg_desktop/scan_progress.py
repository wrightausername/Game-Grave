"""Crimson Command segmented scan progress.

Painted at scan updates or at most once per second from an already running
UI timing clock. No GPU effects, browser, threaded animation or idle timer.
Indeterminate Full Scan displays honest activity, not a fabricated percentage.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QProgressBar


class CrimsonScanProgress(QProgressBar):
    """Low-overhead, segmented red scan track with an optional motion cue."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("crimsonScanProgress")
        self.setFixedHeight(27)
        self.setTextVisible(False)
        self.setAccessibleName("Crimson Command scan progress")
        self._tick = 0
        self._paused = False
        self._stage = "READY"

    def set_stage(self, text: str):
        stage = str(text or "SCANNING")
        self._stage = stage[:110]
        self.setAccessibleDescription(
            ("Paused for gameplay. " if self._paused else "") + stage)
        self.update()

    def set_paused(self, paused: bool):
        self._paused = bool(paused)
        self.update()

    def advance_pulse(self):
        """Caller may invoke once per second only when a scan is active."""
        if self.isVisible() and not self._paused:
            self._tick = (self._tick + 1) % 36
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        area = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor("#7A3545"), 1))
        p.setBrush(QColor("#0B101B"))
        p.drawRoundedRect(area, 7, 7)

        inner = area.adjusted(7, 6, -7, -6)
        # Leave room for a clearly legible stage percentage.
        right_label = 56
        track_width = max(20., inner.width() - right_label)
        number = max(14, int(track_width / 24))
        gap = 3.0
        unit = max(2.0, (track_width - gap * (number - 1)) / number)
        indeterminate = self.minimum() == 0 and self.maximum() == 0
        fraction = (0 if indeterminate else
                    min(1., max(0., (self.value() - self.minimum()) /
                          max(1, self.maximum() - self.minimum()))))
        for index in range(number):
            x = inner.x() + index * (unit + gap)
            rect = QRectF(x, inner.y(), unit, inner.height())
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#273240"))
            p.drawRoundedRect(rect, 2, 2)
            active = ((index - self._tick) % number < 5
                      if indeterminate and not self._paused
                      else index < round(fraction * number))
            if active:
                if self._paused:
                    color = QColor("#92707B")
                else:
                    mix = (index + self._tick) % 6
                    color = QColor(246, 64 + 5 * mix, 90 + 3 * mix)
                p.setBrush(color)
                p.drawRoundedRect(rect, 2, 2)

        p.setPen(QColor("#F8E7EB") if not self._paused
                 else QColor("#B9A5AE"))
        p.setFont(QFont("Segoe UI", 9, QFont.Bold))
        value = ("PAUSED" if self._paused else
                 "SCAN" if indeterminate else
                 f"{round(fraction * 100)}%")
        p.drawText(QRectF(inner.right() - right_label + 6,
                          inner.y() - 2, right_label - 8, inner.height() + 4),
                   Qt.AlignCenter, value)
        p.end()
