"""Crimson Command read-only Other Storage category visualization.

Draws ONLY the bytes actually examined by the user's chosen metadata scan.
Neither the chart nor percentages imply coverage of all drive space or
that measured categories are safe to delete. Nothing is fetched or sampled.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QWidget

from core import human_size

_PALETTE = (
    "#FA4A66", "#4DD9E8", "#A98CFF", "#F4B768",
    "#54CFA3", "#E58BC3", "#8297B5",
)


def chart_segments(report, *, limit: int = 6) -> list[tuple[str, int]]:
    """Group measured bytes by source category, with bounded visual complexity.

    The final wedge accounts for remaining measured categories only. No
    unscanned, skipped, excluded game or estimated disk bytes enter the chart.
    """
    categories = list(getattr(report, "category_totals", ()) or ())
    merged = {}
    for name, raw in categories:
        if type(raw) is int and raw > 0:
            key = str(name).strip() or "Uncategorized"
            merged[key] = merged.get(key, 0) + raw
    if not merged and not categories:
        for row in getattr(report, "folders", ()):
            amount = getattr(row, "apparent_bytes", 0)
            if type(amount) is int and amount > 0:
                key = str(getattr(row, "category", "")).strip() or "Uncategorized"
                merged[key] = merged.get(key, 0) + amount
    ordered = sorted(merged.items(), key=lambda item: (-item[1], item[0]))
    if len(ordered) > limit:
        return [*ordered[:limit - 1],
                ("Other measured categories", sum(b for _, b in ordered[limit - 1:]))]
    return ordered


class OtherStorageBreakdown(QWidget):
    """Single static-paint donut and matching ranked category bars.

    Repaints only when a new report is displayed or the page resizes. There
    is no animation, sampling, polling, network access or disk traversal.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("otherStorageBreakdownChart")
        self.setAccessibleName("Other Storage scan results visual breakdown")
        self.setMinimumHeight(260)
        self.setMaximumHeight(260)
        self._report = None
        self._segments: list[tuple[str, int]] = []
        self._total = 0

    def set_report(self, report):
        self._report = report
        self._segments = chart_segments(report)
        self._total = sum(amount for _, amount in self._segments)
        coverage = ("complete within allowed scope" if report.complete
                    else "partial or excluded scope")
        spoken = "; ".join(f"{name} {human_size(value)}"
                           for name, value in self._segments)
        self.setAccessibleDescription(
            f"Measured {human_size(self._total)} in {report.entries_seen:,} "
            f"file and folder entries. Coverage: {coverage}. "
            "Percentages are ONLY of measured and categorized bytes, not "
            "of all disk storage or the estimated Other allocation. " + spoken)
        self.update()

    @property
    def measured_total(self) -> int:
        return self._total

    @property
    def segments(self) -> tuple[tuple[str, int], ...]:
        return tuple(self._segments)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        bounds = self.rect()
        p.fillRect(bounds, QColor("#0C1420"))

        left = 15
        diameter = min(190.0, max(104.0, self.height() - 44.0))
        dial = QRectF(left, (self.height() - diameter) / 2, diameter, diameter)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor("#2A3847"), 19, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(dial, 0, 360 * 16)

        if not self._segments or not self._total:
            p.setPen(QColor("#A4B5C6"))
            p.setFont(QFont("Segoe UI", 12, QFont.DemiBold))
            p.drawText(dial, Qt.AlignCenter | Qt.TextWordWrap,
                       "NO MEASURED\nCATEGORY DATA")
        else:
            start = 90 * 16
            for index, (_, count) in enumerate(self._segments):
                span = max(1, round(360 * 16 * count / self._total))
                pen = QPen(QColor(_PALETTE[index % len(_PALETTE)]),
                           19, Qt.SolidLine, Qt.FlatCap)
                p.setPen(pen)
                p.drawArc(dial, start, -span)
                start -= span
            p.setPen(QColor("#F7F7FA"))
            p.setFont(QFont("Segoe UI", 19, QFont.Bold))
            p.drawText(
                QRectF(dial.left() + 10, dial.center().y() - 20,
                       dial.width() - 20, 37),
                Qt.AlignCenter, human_size(self._total))
            p.setPen(QColor("#B5C8D7"))
            p.setFont(QFont("Segoe UI", 9, QFont.DemiBold))
            p.drawText(
                QRectF(dial.left() + 10, dial.center().y() + 13,
                       dial.width() - 20, 24),
                Qt.AlignCenter, "MEASURED")

        x = int(dial.right()) + 29
        usable_width = max(0, self.width() - x - 15)
        if usable_width < 105:
            p.end()
            return
        p.setPen(QColor("#F2F4F8"))
        p.setFont(QFont("Segoe UI", 13, QFont.DemiBold))
        p.drawText(QRectF(x, 8, usable_width, 23), Qt.AlignLeft,
                   "CATEGORY BREAKDOWN")
        p.setPen(QColor("#94ADBF"))
        p.setFont(QFont("Segoe UI", 9))
        p.drawText(QRectF(x, 29, usable_width, 21), Qt.AlignLeft,
                   "% of examined bytes only")

        bar_start = 64
        line_height = 31
        for idx, (name, amount) in enumerate(self._segments[:6]):
            y = bar_start + idx * line_height
            color = QColor(_PALETTE[idx % len(_PALETTE)])
            p.setBrush(color)
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(x, y + 3, 9, 9), 2, 2)
            p.setPen(QColor("#E9F0F7"))
            p.setFont(QFont("Segoe UI", 9, QFont.DemiBold))
            # Reserve right-hand space for an exact measured size and percent.
            label_width = max(65, usable_width - 154)
            metrics_width = min(148, max(75, usable_width - label_width))
            short = p.fontMetrics().elidedText(name, Qt.ElideRight,
                                                max(30, label_width - 16))
            p.drawText(QRectF(x + 17, y - 2, label_width, 20),
                       Qt.AlignVCenter | Qt.AlignLeft, short)
            p.setPen(QColor("#B5C9D8"))
            percent = 100 * amount / self._total if self._total else 0
            size_label = f"{percent:.1f}%  ·  {human_size(amount)}"
            p.drawText(QRectF(x + 17 + label_width, y - 2, metrics_width, 20),
                       Qt.AlignVCenter | Qt.AlignRight, size_label)
            track_width = max(40, usable_width - 20)
            track = QRectF(x + 16, y + 21, track_width, 4)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#253341"))
            p.drawRoundedRect(track, 2, 2)
            p.setBrush(color)
            p.drawRoundedRect(QRectF(track.x(), track.y(),
                                      max(1.5, track.width() * percent / 100),
                                      track.height()), 2, 2)
        p.end()
