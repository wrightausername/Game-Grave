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
        self.setFixedHeight(90)
        self._title = "Select a finding"
        self._category = "LOCAL EVIDENCE"
        self._samples = []
        self._selected_key = None
        self.setAccessibleName("Selected Graveyard file visual context")

    def set_entry(self, entry):
        self._title = str(getattr(entry, "name", "") or "Unnamed finding")
        self._category = str(getattr(entry, "category", "") or "Unknown source")
        self._selected_key = getattr(entry, "key", None)
        self.setToolTip(self._title + "\n" + self._category)
        self.update()

    def set_candidates(self, entries):
        self._samples = [(getattr(item, "key", None), max(0, int(
            getattr(item, "apparent_bytes", 0)))) for item in entries[:24]]
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
        p.setPen(QColor("#FFFFFF"))
        p.setFont(QFont("Segoe UI", 10, QFont.Bold))
        fm = p.fontMetrics()
        title = fm.elidedText(self._title, Qt.ElideMiddle, max(50, w-22))
        p.drawText(QRectF(11, 5, max(48, w-22), 22),
                   Qt.AlignLeft | Qt.AlignVCenter, title)
        p.setPen(QColor("#DD9AAA"))
        p.setFont(QFont("Segoe UI", 8))
        category = p.fontMetrics().elidedText(
            self._category.upper(), Qt.ElideRight, max(50, w-22))
        p.drawText(QRectF(11, 27, max(48, w-22), 17),
                   Qt.AlignLeft | Qt.AlignVCenter, category)
        # Actual candidate sizes, not an invented usage/FPS/time history.
        maximum = max((size for _, size in self._samples), default=0)
        if maximum:
            pitch = max(2., (w-24)/max(1, len(self._samples)))
            for index, (key, size) in enumerate(self._samples):
                bar_h = max(2., 24 * size/maximum)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor("#F3AE64" if key == self._selected_key else "#93444E"))
                p.drawRoundedRect(QRectF(12+index*pitch, 70-bar_h,
                                         max(1., pitch-3), bar_h), 1.5, 1.5)
        p.setPen(QColor("#A6B4C4"))
        p.setFont(QFont("Segoe UI", 7))
        p.drawText(QRectF(11, 75, w-22, 13), Qt.AlignLeft,
                   "Candidate sizes • relative")
        p.end()
