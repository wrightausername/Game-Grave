"""Painted graphics for the Hardware tab: ring gauges, the smooth live chart, a core grid, memory slots, speed
bars and drive bars.

Display only. Every shape is drawn from a number the tab already shows in words (a load percentage, a core
count, how many memory slots are used, how full a drive is). Nothing here estimates, scores or promises anything.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QSizePolicy, QWidget

TRACK = QColor("#15222c")
SWEEP_START, SWEEP = 225, -270     # degrees: the gauge opens at the bottom


def _font(base, pixels, bold=False):
    font = QFont(base)
    font.setPixelSize(pixels)
    font.setBold(bold)
    return font


def clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def level_color(base: str, fraction):
    """Same hue as the gauge until it is very full, then amber and red. Fullness is shown, never judged as good or bad."""
    if fraction is None:
        return QColor("#4a5863")
    if fraction >= .95:
        return QColor("#ff4d66")
    if fraction >= .85:
        return QColor("#eab464")
    return QColor(base)


# ---------------------------------------------------------------- gauge
class RingGauge(QWidget):
    """An open ring that fills with a percentage. Shows a dash and an empty track when the value cannot be read."""

    def __init__(self, base_color, title, size=112):
        super().__init__()
        self.base = base_color
        self.title = title
        self.fraction = None
        self.big = "—"
        self.small = ""
        self.setFixedSize(size, size)
        self.setAccessibleName(f"{title} gauge")

    def set_value(self, fraction, big, small=""):
        self.fraction = None if fraction is None else clamp(float(fraction))
        self.big, self.small = big, small
        self.setAccessibleName(f"{self.title} gauge: {big} {small}".strip())
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        side = min(self.width(), self.height())
        box = QRectF((self.width() - side) / 2 + 9, (self.height() - side) / 2 + 9, side - 18, side - 18)
        color = level_color(self.base, self.fraction)
        # quiet backdrop disc
        back = QRadialGradient(box.center(), box.width() / 2)
        back.setColorAt(0, QColor(18, 30, 40, 200))
        back.setColorAt(1, QColor(8, 14, 20, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(back)
        p.drawEllipse(box.adjusted(-4, -4, 4, 4))
        # tick marks around the open ring
        p.setPen(QPen(QColor("#22323e"), 1))
        for i in range(0, 28):
            angle = 225 - i * 270 / 27
            self._tick(p, box, angle, 3 if i % 9 == 0 else 2)
        # track and fill
        ring = box.adjusted(7, 7, -7, -7)
        pen = QPen(TRACK, 8)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(ring, SWEEP_START * 16, SWEEP * 16)
        if self.fraction:
            glow = QColor(color)
            glow.setAlpha(50)
            wide = QPen(glow, 14)
            wide.setCapStyle(Qt.RoundCap)
            p.setPen(wide)
            p.drawArc(ring, SWEEP_START * 16, int(SWEEP * 16 * self.fraction))
            bright = QPen(color, 8)
            bright.setCapStyle(Qt.RoundCap)
            p.setPen(bright)
            p.drawArc(ring, SWEEP_START * 16, int(SWEEP * 16 * self.fraction))
        # numbers
        p.setPen(QColor("#f1f4f7" if self.fraction is not None else "#6c7a86"))
        p.setFont(_font(self.font(), 20 if len(self.big) <= 4 else 15, bold=True))
        p.drawText(QRectF(0, self.height() / 2 - 20, self.width(), 28), Qt.AlignCenter, self.big)
        p.setPen(QColor("#8794a1"))
        p.setFont(_font(self.font(), 10))
        p.drawText(QRectF(0, self.height() / 2 + 6, self.width(), 14), Qt.AlignCenter, self.small or self.title)
        p.setPen(QColor(self.base))
        p.setFont(_font(self.font(), 10, bold=True))
        p.drawText(QRectF(0, self.height() - 16, self.width(), 14), Qt.AlignCenter, self.title if self.small else "")

    @staticmethod
    def _tick(p, box, degrees, length):
        import math
        rad = math.radians(degrees)
        c = box.center()
        r = box.width() / 2
        p.drawLine(QPointF(c.x() + (r - length) * math.cos(rad), c.y() - (r - length) * math.sin(rad)),
                   QPointF(c.x() + r * math.cos(rad), c.y() - r * math.sin(rad)))


# ---------------------------------------------------------------- smooth live chart
class AreaChart(QWidget):
    """The last readings as a smooth glowing line over a soft fill. Unreadable readings leave a gap, never a zero."""

    def __init__(self, color, empty_text, history):
        super().__init__()
        self.color = QColor(color)
        self.empty_text = empty_text
        self.history = history
        self.values = []
        self.setMinimumHeight(92)
        self.setMaximumHeight(220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_values(self, values):
        self.values = list(values)
        self.update()

    def _points(self, w, h):
        step = w / max(1, self.history - 1)
        start = self.history - len(self.values)
        out = []
        for i, value in enumerate(self.values):
            if value is None:
                out.append(None)
            else:
                out.append(QPointF((start + i) * step, h * (1 - clamp(value / 100.0))))
        return out

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height() - 2
        # frame, grid and its labels
        frame = QPainterPath()
        frame.addRoundedRect(QRectF(0, 0, w, h), 6, 6)
        wash = QLinearGradient(0, 0, 0, h)
        wash.setColorAt(0, QColor(14, 24, 32, 160))
        wash.setColorAt(1, QColor(8, 14, 20, 60))
        p.fillPath(frame, wash)
        p.setPen(QPen(QColor("#15222c"), 1, Qt.DashLine))
        for fraction in (.25, .5, .75):
            y = round(h * (1 - fraction))
            p.drawLine(0, y, w, y)
        p.setPen(QColor("#4b5a66"))
        p.setFont(_font(self.font(), 9))
        p.drawText(QRectF(5, 2, 40, 12), Qt.AlignLeft | Qt.AlignTop, "100%")
        p.drawText(QRectF(5, h - 14, 40, 12), Qt.AlignLeft | Qt.AlignBottom, "0")
        p.setPen(QPen(QColor("#26343f"), 1))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 6, 6)
        points = self._points(w, h)
        if not any(pt is not None for pt in points):
            p.setPen(QColor("#9AA4AC"))
            p.setFont(_font(self.font(), 12))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, self.empty_text)
            return
        # runs of readable points, drawn separately so a gap stays a gap
        runs, run = [], []
        for pt in points + [None]:
            if pt is None:
                if run:
                    runs.append(run)
                run = []
            else:
                run.append(pt)
        for run in runs:
            line = QPainterPath(run[0])
            for a, b in zip(run, run[1:]):
                mid = (a.x() + b.x()) / 2
                line.cubicTo(QPointF(mid, a.y()), QPointF(mid, b.y()), b)
            area = QPainterPath(line)
            area.lineTo(QPointF(run[-1].x(), h))
            area.lineTo(QPointF(run[0].x(), h))
            area.closeSubpath()
            fill = QLinearGradient(0, 0, 0, h)
            top, bottom = QColor(self.color), QColor(self.color)
            top.setAlpha(120)
            bottom.setAlpha(6)
            fill.setColorAt(0, top)
            fill.setColorAt(1, bottom)
            p.fillPath(area, fill)
            glow = QColor(self.color)
            glow.setAlpha(55)
            p.setPen(QPen(glow, 5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPath(line)
            p.setPen(QPen(self.color.lighter(120), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPath(line)
        last = points[-1]
        if last is not None:
            halo = QColor(self.color)
            halo.setAlpha(70)
            p.setPen(Qt.NoPen)
            p.setBrush(halo)
            p.drawEllipse(last, 6, 6)
            p.setBrush(QColor("#ffffff"))
            p.drawEllipse(last, 2.6, 2.6)


# ---------------------------------------------------------------- parts
class CoreGrid(QWidget):
    """One square per processor core; two small bars inside each when the part reports two threads per core."""

    def __init__(self, cores, threads, color="#42D4F2"):
        super().__init__()
        self.cores, self.threads, self.color = max(0, int(cores)), max(0, int(threads)), QColor(color)
        self.cell = 13
        columns = min(16, max(1, self.cores))
        rows = -(-max(1, self.cores) // columns)
        self.setFixedHeight(rows * (self.cell + 3) + 2)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setMinimumWidth(0)
        self.setAccessibleName(f"{self.cores} cores, {self.threads} threads")

    def paintEvent(self, event):
        if not self.cores:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        columns = min(16, self.cores)
        pair = self.threads == self.cores * 2
        for i in range(self.cores):
            x = (i % columns) * (self.cell + 3) + 1
            y = (i // columns) * (self.cell + 3) + 1
            rect = QRectF(x, y, self.cell, self.cell)
            border = QColor(self.color)
            border.setAlpha(170)
            fill = QColor(self.color)
            fill.setAlpha(34)
            p.setPen(QPen(border, 1))
            p.setBrush(fill)
            p.drawRoundedRect(rect, 3, 3)
            if pair:
                p.setPen(Qt.NoPen)
                p.setBrush(self.color)
                p.drawRoundedRect(QRectF(x + 3, y + 3, 3, self.cell - 6), 1, 1)
                p.drawRoundedRect(QRectF(x + self.cell - 6, y + 3, 3, self.cell - 6), 1, 1)


class SlotStrip(QWidget):
    """Memory slots as little module shapes: filled for the slots in use, outlined for the rest."""

    def __init__(self, used, slots, color="#35DC7C"):
        super().__init__()
        self.used, self.slots, self.color = max(0, int(used)), max(0, int(slots)), QColor(color)
        self.setFixedHeight(22)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setMinimumWidth(0)
        self.setAccessibleName(f"{self.used} of {self.slots} memory slots used")

    def paintEvent(self, event):
        count = self.slots or self.used
        if not count:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        width = min(54, max(20, (self.width() - 6 * (count - 1)) // count))
        for i in range(min(count, 12)):
            x = i * (width + 6) + 1
            rect = QRectF(x, 3, width, 15)
            on = i < self.used
            border = QColor(self.color)
            border.setAlpha(210 if on else 90)
            fill = QColor(self.color)
            fill.setAlpha(70 if on else 0)
            p.setPen(QPen(border, 1))
            p.setBrush(fill)
            p.drawRoundedRect(rect, 3, 3)
            p.setPen(Qt.NoPen)
            p.setBrush(border)
            for notch in range(4):
                p.drawRect(QRectF(x + 5 + notch * (width - 10) / 4, 14, 2, 4))


class SpeedBars(QWidget):
    """Running speed against rated speed, both in MT/s, as two bars on one scale. Only drawn when both are known."""

    def __init__(self, running, rated, color="#35DC7C"):
        super().__init__()
        self.running, self.rated, self.color = int(running or 0), int(rated or 0), QColor(color)
        self.setFixedHeight(26)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setMinimumWidth(0)
        self.setAccessibleName(f"Running at {self.running} MT/s, rated {self.rated} MT/s")

    def paintEvent(self, event):
        top = max(self.running, self.rated)
        if not top:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        label_w = 52
        track_w = max(10, self.width() - label_w - 60)
        for i, (name, value, color) in enumerate((("Running", self.running, self.color), ("Rated", self.rated, QColor("#5b6874")))):
            y = 2 + i * 12
            p.setPen(QColor("#8794a1"))
            p.setFont(_font(self.font(), 10))
            p.drawText(QRectF(0, y - 2, label_w, 12), Qt.AlignVCenter | Qt.AlignLeft, name)
            p.setPen(Qt.NoPen)
            p.setBrush(TRACK)
            p.drawRoundedRect(QRectF(label_w, y + 1, track_w, 6), 3, 3)
            if value:
                p.setBrush(color)
                p.drawRoundedRect(QRectF(label_w, y + 1, max(6.0, track_w * value / top), 6), 3, 3)
            p.setPen(QColor("#d7dfe7"))
            p.drawText(QRectF(label_w + track_w + 6, y - 2, 54, 12), Qt.AlignVCenter | Qt.AlignLeft, f"{value or '—'}")


# ---------------------------------------------------------------- drives
class DriveBar(QWidget):
    """A thick drive bar with tick marks every tenth and how full it is written inside."""

    def __init__(self, used_fraction, color="#42D4F2"):
        super().__init__()
        self.fraction = clamp(float(used_fraction or 0))
        self.base = color
        self.setFixedHeight(16)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAccessibleName(f"{round(self.fraction * 100)} percent full")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        p.setPen(QPen(QColor("#26343f"), 1))
        p.setBrush(QColor("#0e171f"))
        p.drawRoundedRect(rect, 5, 5)
        color = level_color(self.base, self.fraction)
        if self.fraction > 0:
            fill = QRectF(1.5, 1.5, max(8.0, (rect.width() - 2) * self.fraction), rect.height() - 2)
            gradient = QLinearGradient(fill.topLeft(), fill.topRight())
            dark = QColor(color).darker(170)
            gradient.setColorAt(0, dark)
            gradient.setColorAt(1, color)
            p.setPen(Qt.NoPen)
            p.setBrush(gradient)
            p.drawRoundedRect(fill, 4, 4)
        p.setPen(QPen(QColor(0, 0, 0, 90), 1))
        for i in range(1, 10):
            x = rect.left() + rect.width() * i / 10
            p.drawLine(QPointF(x, rect.top() + 3), QPointF(x, rect.bottom() - 3))
        p.setPen(QColor("#f1f4f7"))
        p.setFont(_font(self.font(), 10, bold=True))
        p.drawText(rect.adjusted(7, 0, -7, 0), Qt.AlignVCenter | Qt.AlignLeft, f"{round(self.fraction * 100)}% full")
