"""Painted graphics for the Hardware tab: ring gauges, the smooth live chart, a core grid, memory slots, speed
bars and drive bars.

Display only. Every shape is drawn from a number the tab already shows in words (a load percentage, a core
count, how many memory slots are used, how full a drive is). Nothing here estimates, scores or promises anything.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QSizePolicy, QWidget

from core import human_size

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
    """Drive bars keep their hue until the drive is very full, then amber and red. Used for drive fullness only."""
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
        color = QColor(self.base) if self.fraction is not None else QColor("#4a5863")   # load is shown, never judged
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
        rad = math.radians(degrees)
        c = box.center()
        r = box.width() / 2
        p.drawLine(QPointF(c.x() + (r - length) * math.cos(rad), c.y() - (r - length) * math.sin(rad)),
                   QPointF(c.x() + r * math.cos(rad), c.y() - r * math.sin(rad)))


# ---------------------------------------------------------------- smooth live chart
class AreaChart(QWidget):
    """The last readings as a smooth glowing line over a soft fill. Unreadable readings leave a gap, never a zero."""

    def __init__(self, color, empty_text, history, top_label="100%"):
        super().__init__()
        self.top_label = top_label
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
        p.drawText(QRectF(5, 2, 40, 12), Qt.AlignLeft | Qt.AlignTop, self.top_label)
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


# ---------------------------------------------------------------- the rig map
def _elide(p, text, width):
    return QFontMetrics(p.font()).elidedText(str(text), Qt.ElideRight, max(8, int(width)))


class RigMap(QWidget):
    """A drawn map of this PC: the processor, memory slots, graphics card and drives, joined by a bus.

    Every box is a part Windows reported, with its real name and numbers. The live readings light the parts up
    (processor glow, memory fill, graphics bars, drive fullness). A part that cannot be read is drawn dim and says so.
    """

    HEIGHT = 312

    def __init__(self):
        super().__init__()
        self.specs = None
        self.live = None
        self.message = "Reading your hardware…"
        self.setFixedHeight(self.HEIGHT)
        self.setMinimumWidth(520)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAccessibleName("Map of your PC")

    def set_specs(self, specs, message=""):
        self.specs = specs
        if message:
            self.message = message
        self.update()

    def set_live(self, live):
        self.live = live
        self.update()

    # ------------------------------------------------------------ drawing helpers
    def _label(self, p, text, rect, color="#d7dfe7", size=12, bold=False, align=Qt.AlignLeft | Qt.AlignVCenter):
        p.setPen(QColor(color))
        p.setFont(_font(self.font(), size, bold))
        p.drawText(rect, align, _elide(p, text, rect.width()))

    @staticmethod
    def _bar(p, rect, fraction, color, track="#15222c"):
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(track))
        p.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        if fraction is not None and fraction > 0:
            fill = QRectF(rect.left(), rect.top(), max(rect.height(), rect.width() * clamp(fraction)), rect.height())
            gradient = QLinearGradient(fill.topLeft(), fill.topRight())
            gradient.setColorAt(0, QColor(color).darker(160))
            gradient.setColorAt(1, QColor(color))
            p.setBrush(gradient)
            p.drawRoundedRect(fill, rect.height() / 2, rect.height() / 2)

    @staticmethod
    def _tag(p, rect, text, color, font):
        p.setPen(QPen(QColor(color), 1))
        p.setBrush(QColor(0, 0, 0, 90))
        p.drawRoundedRect(rect, 5, 5)
        p.setFont(font)
        p.setPen(QColor(color))
        p.drawText(rect, Qt.AlignCenter, text)

    # ------------------------------------------------------------ the painting
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        shape = QPainterPath()
        shape.addRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 10, 10)
        p.setClipPath(shape)
        wash = QLinearGradient(0, 0, 0, h)
        wash.setColorAt(0, QColor("#0c1720"))
        wash.setColorAt(1, QColor("#070d12"))
        p.fillPath(shape, wash)
        p.setPen(QPen(QColor(66, 212, 242, 13), 1))
        for x in range(24, w, 24):
            p.drawLine(x, 1, x, h - 1)
        for y in range(24, h, 24):
            p.drawLine(1, y, w - 1, y)
        self._label(p, "YOUR RIG", QRectF(16, 9, 120, 16), "#8794a1", 11, True)
        specs = self.specs
        if specs is None:
            self._label(p, self.message, QRectF(20, 0, w - 40, h), "#6c7a86", 14, False, Qt.AlignCenter)
            p.setClipping(False)
            p.setPen(QPen(QColor("#26343f"), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 10, 10)
            return
        live = self.live
        cpu_load = None if live is None or live.cpu is None else clamp(live.cpu / 100.0)
        mem_fraction = (None if live is None or live.mem_used_gb is None or not live.mem_total_gb
                        else clamp(live.mem_used_gb / live.mem_total_gb))
        gpu_live = None if live is None else live.gpu
        top, bottom = 36, h - 38
        mid = top + (bottom - top) * .46
        bus_color = QColor(66, 212, 242, 70)
        colc_x = w * .60
        colc_w = w - colc_x - 18
        # ---- bus: runs from the processor across, then down beside the graphics card and drives
        spine_x = colc_x - 14
        p.setPen(QPen(bus_color, 2, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(w * .20, mid), QPointF(spine_x, mid))
        p.drawLine(QPointF(spine_x, top + 40), QPointF(spine_x, bottom - 6))
        # ---- processor
        cx = w * .20
        size = min(100.0, (bottom - top) * .46)
        chip = QRectF(cx - size / 2, mid - size / 2, size, size)
        if cpu_load is not None:
            glow = QRadialGradient(chip.center(), size * .95)
            glow.setColorAt(0, QColor(66, 212, 242, int(40 + 150 * cpu_load)))
            glow.setColorAt(1, QColor(66, 212, 242, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            p.drawEllipse(chip.center(), size * .95, size * .95)
        socket = chip.adjusted(-9, -9, 9, 9)
        p.setPen(QPen(QColor("#26404d"), 1))
        p.setBrush(QColor("#0b171f"))
        p.drawRoundedRect(socket, 7, 7)
        pin = QColor(66, 212, 242, 150)
        p.setPen(QPen(pin, 1.4))
        for i in range(1, 11):
            t = i / 11
            x = chip.left() + chip.width() * t
            y = chip.top() + chip.height() * t
            p.drawLine(QPointF(x, socket.top() - 1), QPointF(x, socket.top() + 4))
            p.drawLine(QPointF(x, socket.bottom() + 1), QPointF(x, socket.bottom() - 4))
            p.drawLine(QPointF(socket.left() - 1, y), QPointF(socket.left() + 4, y))
            p.drawLine(QPointF(socket.right() + 1, y), QPointF(socket.right() - 4, y))
        body = QLinearGradient(chip.topLeft(), chip.bottomRight())
        body.setColorAt(0, QColor("#17303c"))
        body.setColorAt(1, QColor("#0d1b24"))
        p.setPen(QPen(QColor(66, 212, 242, 190), 1.4))
        p.setBrush(body)
        p.drawRoundedRect(chip, 8, 8)
        die = chip.adjusted(size * .22, size * .22, -size * .22, -size * .22)
        p.setPen(QPen(QColor(66, 212, 242, 160), 1))
        p.setBrush(QColor(66, 212, 242, int(26 + 110 * (cpu_load or 0))))
        p.drawRoundedRect(die, 4, 4)
        self._label(p, "CPU", die, "#e8f7fb", 14, True, Qt.AlignCenter)
        if specs.cpu:
            c = specs.cpu
            self._label(p, c.name, QRectF(cx - w * .17, socket.bottom() + 8, w * .34, 16), "#e6edf2", 12, True, Qt.AlignHCenter | Qt.AlignVCenter)
            self._label(p, f"{c.cores} cores · {c.threads} threads · {c.base_ghz} GHz", QRectF(cx - w * .17, socket.bottom() + 25, w * .34, 15),
                        "#8794a1", 11, False, Qt.AlignHCenter | Qt.AlignVCenter)
        bar = QRectF(cx - 48, socket.bottom() + 46, 96, 6)
        self._bar(p, bar, cpu_load, "#42D4F2")
        self._label(p, "not readable" if cpu_load is None else f"{round(cpu_load * 100)}% in use",
                    QRectF(cx - 70, bar.bottom() + 3, 140, 14), "#8fdcf0", 11, True, Qt.AlignHCenter | Qt.AlignVCenter)
        # ---- memory slots
        memory = specs.memory
        colb_x = w * .37
        colb_w = w * .17
        count = min(8, (memory.slots or memory.sticks) if memory else 0)
        slot_top = mid - 62
        slot_h = 124.0
        if count:
            gap = 7
            slot_w = max(8.0, min(20.0, (colb_w - gap * (count - 1)) / count))
            total_w = slot_w * count + gap * (count - 1)
            x0 = colb_x + (colb_w - total_w) / 2
            green = QColor("#35DC7C")
            p.setPen(QPen(bus_color, 2, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(socket.right(), mid), QPointF(x0, mid))
            for i in range(count):
                x = x0 + i * (slot_w + gap)
                rect = QRectF(x, slot_top, slot_w, slot_h)
                used = i < memory.sticks
                border = QColor(green)
                border.setAlpha(220 if used else 80)
                p.setPen(QPen(border, 1.2))
                p.setBrush(QColor(8, 16, 22, 230))
                p.drawRoundedRect(rect, 3, 3)
                if used:
                    fraction = mem_fraction if mem_fraction is not None else 0.0
                    fill_h = max(0.0, (slot_h - 6) * fraction)
                    if fill_h > 0:
                        fill = QRectF(x + 2, slot_top + slot_h - 3 - fill_h, slot_w - 4, fill_h)
                        gradient = QLinearGradient(fill.topLeft(), fill.bottomLeft())
                        gradient.setColorAt(0, green)
                        gradient.setColorAt(1, green.darker(210))
                        p.setPen(Qt.NoPen)
                        p.setBrush(gradient)
                        p.drawRoundedRect(fill, 2, 2)
                p.setPen(Qt.NoPen)
                p.setBrush(border)
                p.drawRect(QRectF(x + slot_w / 2 - 1.5, slot_top - 4, 3, 4))
            base = slot_top + slot_h + 8
            self._label(p, f"{memory.total_gb:g} GB {memory.kind}".strip(), QRectF(colb_x - 10, base, colb_w + 20, 16), "#e6edf2", 12, True, Qt.AlignHCenter | Qt.AlignVCenter)
            if live is not None and live.mem_used_gb is not None:
                self._label(p, f"{live.mem_used_gb:.1f} GB in use", QRectF(colb_x - 10, base + 16, colb_w + 20, 15), "#7bf0a6", 11, True, Qt.AlignHCenter | Qt.AlignVCenter)
            if memory.running_mts:
                speed = f"{memory.running_mts} of {memory.rated_mts} MT/s" if memory.rated_mts else f"{memory.running_mts} MT/s"
                self._label(p, speed, QRectF(colb_x - 14, base + 31, colb_w + 28, 15), "#8794a1", 11, False, Qt.AlignHCenter | Qt.AlignVCenter)
        else:
            self._label(p, "Memory not reported", QRectF(colb_x, mid - 10, colb_w, 20), "#6c7a86", 11, False, Qt.AlignCenter)
        # ---- graphics card
        card = QRectF(colc_x, top, colc_w, 100)
        red = QColor("#FF3B57")
        load = None if gpu_live is None or gpu_live.load is None else clamp(gpu_live.load / 100.0)
        p.setPen(QPen(bus_color, 2, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(spine_x, card.center().y()), QPointF(card.left(), card.center().y()))
        if load is not None:
            halo = QRadialGradient(card.center(), card.width() * .5)
            halo.setColorAt(0, QColor(255, 59, 87, int(30 + 70 * load)))
            halo.setColorAt(1, QColor(255, 59, 87, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(halo)
            p.drawEllipse(card.center(), card.width() * .5, card.height() * .8)
        shell = QLinearGradient(card.topLeft(), card.bottomLeft())
        shell.setColorAt(0, QColor("#1b0f15"))
        shell.setColorAt(1, QColor("#0e0a0e"))
        edge = QColor(red)
        edge.setAlpha(200)
        p.setPen(QPen(edge, 1.4))
        p.setBrush(shell)
        p.drawRoundedRect(card, 9, 9)
        fans = 2 if card.width() >= 280 else 1
        for k in range(fans):
            fc = QPointF(card.left() + 38 + k * 66, card.center().y())
            p.setPen(QPen(QColor(255, 59, 87, 120), 1))
            p.setBrush(QColor(10, 6, 9))
            p.drawEllipse(fc, 28, 28)
            p.setPen(QPen(QColor(255, 59, 87, 200), 3, Qt.SolidLine, Qt.RoundCap))
            for blade in range(7):
                a0 = math.radians(blade * 360 / 7)
                a1 = a0 + .55
                p.drawLine(QPointF(fc.x() + 6 * math.cos(a0), fc.y() + 6 * math.sin(a0)),
                           QPointF(fc.x() + 23 * math.cos(a1), fc.y() + 23 * math.sin(a1)))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#2a1a20"))
            p.drawEllipse(fc, 6, 6)
        tx = card.left() + 12 + fans * 66
        tw = card.right() - tx - 10
        gpu = specs.gpus[0] if specs.gpus else None
        self._tag(p, QRectF(tx, card.top() + 9, 34, 17), "GPU", "#FF3B57", _font(self.font(), 10, True))
        self._label(p, gpu.name if gpu else "Not reported", QRectF(tx + 40, card.top() + 8, tw - 40, 19), "#f1f4f7", 12, True)
        bar1 = QRectF(tx, card.top() + 38, tw - 56, 6)
        self._bar(p, bar1, load, "#FF3B57")
        self._label(p, "needs NVIDIA" if load is None else f"{round(load * 100)}% load", QRectF(bar1.right() + 6, card.top() + 32, 60, 17), "#ff9aa9", 11, True)
        vram = None
        if gpu_live is not None and gpu_live.mem_used_mb is not None and gpu_live.mem_total_mb:
            vram = clamp(gpu_live.mem_used_mb / gpu_live.mem_total_mb)
        bar2 = QRectF(tx, card.top() + 58, tw - 56, 6)
        self._bar(p, bar2, vram, "#df83ec")
        self._label(p, "" if vram is None else f"{gpu_live.mem_used_mb / 1024:.1f} GB", QRectF(bar2.right() + 6, card.top() + 52, 60, 17), "#e4aef0", 11, True)
        temp = "" if gpu_live is None or gpu_live.temp_c is None else f"  ·  {round(gpu_live.temp_c)} °C"
        driver = f"Driver {gpu.driver}" if gpu and gpu.driver else ""
        self._label(p, driver + temp, QRectF(tx, card.top() + 72, tw, 17), "#8794a1", 11)
        # ---- drives
        drives = list(specs.drives)[:4]
        y = card.bottom() + 12
        row_h, row_gap = 38.0, 7.0
        for drive in drives:
            rect = QRectF(colc_x, y, colc_w, row_h)
            p.setPen(QPen(bus_color, 2, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(spine_x, rect.center().y()), QPointF(rect.left(), rect.center().y()))
            hard = drive.kind == "hard drive"
            tone = QColor("#DFAC46" if hard else "#42D4F2")
            p.setPen(QPen(QColor(tone.red(), tone.green(), tone.blue(), 150), 1.2))
            p.setBrush(QColor(9, 16, 22, 230))
            p.drawRoundedRect(rect, 7, 7)
            self._tag(p, QRectF(rect.left() + 8, rect.top() + 9, 38, 17), "HDD" if hard else ("SSD" if drive.fast else "DRV"),
                      tone.name(), _font(self.font(), 10, True))
            used = 1 - drive.free / drive.total if drive.total else 0
            self._label(p, f"{drive.letter}: {drive.model or 'Drive'}", QRectF(rect.left() + 54, rect.top() + 3, rect.width() - 112, 17), "#e6edf2", 11, True)
            self._bar(p, QRectF(rect.left() + 54, rect.top() + 24, rect.width() - 112, 6), used, tone.name())
            self._label(p, f"{round(used * 100)}% full", QRectF(rect.right() - 54, rect.top() + 3, 48, 17), tone.name(), 11, True, Qt.AlignRight | Qt.AlignVCenter)
            self._label(p, f"{human_size(drive.free)} free", QRectF(rect.right() - 62, rect.top() + 20, 56, 15), "#8794a1", 10, False, Qt.AlignRight | Qt.AlignVCenter)
            y += row_h + row_gap
        if len(specs.drives) > len(drives):
            self._label(p, f"+ {len(specs.drives) - len(drives)} more drives", QRectF(colc_x, y - 4, colc_w, 16), "#8794a1", 11)
        # ---- footer: board, display, system
        p.setPen(QPen(QColor("#1b2a35"), 1))
        p.drawLine(QPointF(14, h - 31), QPointF(w - 14, h - 31))
        pieces = [("BOARD", specs.board), ("DISPLAY", specs.display), ("SYSTEM", specs.os_name)]
        slot = (w - 28) / 3
        for i, (name, value) in enumerate(pieces):
            rect = QRectF(14 + i * slot, h - 28, slot - 8, 24)
            self._label(p, name, QRectF(rect.left(), rect.top(), 52, 24), "#5b6e7c", 10, True)
            self._label(p, value or "not reported", QRectF(rect.left() + 52, rect.top(), rect.width() - 52, 24), "#c3ced6" if value else "#6c7a86", 11)
        p.setClipping(False)
        p.setPen(QPen(QColor("#26343f"), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 10, 10)


# ---------------------------------------------------------------- recorded sessions
class SessionPeaks(QWidget):
    """The peaks of each recorded play session as grouped bars: processor, graphics, memory and video memory.

    These are the same numbers the upgrade notes are built from, so the chart is the evidence behind the notes.
    A reading the session could not take is left out, never drawn as zero.
    """

    SERIES = (("Processor", "#42D4F2"), ("Graphics", "#FF3B57"), ("Memory", "#35DC7C"), ("Video memory", "#df83ec"))

    def __init__(self, sessions=()):
        super().__init__()
        self.sessions = list(sessions)[-8:]
        self.setFixedHeight(196)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAccessibleName(f"Peaks of {len(self.sessions)} recorded sessions")

    def set_sessions(self, sessions):
        self.sessions = list(sessions)[-8:]
        self.setAccessibleName(f"Peaks of {len(self.sessions)} recorded sessions")
        self.update()

    @staticmethod
    def values(session):
        def share(part, whole):
            return None if part is None or not whole else clamp(part / whole) * 100.0
        return (session.cpu_peak, session.gpu_peak, share(session.ram_peak_gb, session.ram_total_gb),
                share(session.vram_peak_mb, session.vram_total_mb))

    def paintEvent(self, event):
        import datetime
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        left, right, top, bottom = 34, 8, 8, 52
        plot = QRectF(left, top, max(40, w - left - right), h - top - bottom)
        p.setFont(_font(self.font(), 10))
        for fraction in (0, .25, .5, .75, 1):
            y = plot.bottom() - plot.height() * fraction
            p.setPen(QPen(QColor("#15222c" if fraction not in (0, 1) else "#26343f"), 1, Qt.DashLine if fraction not in (0, 1) else Qt.SolidLine))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(QColor("#5b6e7c"))
            p.drawText(QRectF(0, y - 7, left - 6, 14), Qt.AlignRight | Qt.AlignVCenter, f"{round(fraction * 100)}%")
        if not self.sessions:
            p.setPen(QColor("#6c7a86"))
            p.setFont(_font(self.font(), 12))
            p.drawText(plot, Qt.AlignCenter, "Record a play session to see its peaks here")
            return
        count = len(self.sessions)
        group_w = plot.width() / max(count, 4)
        bar_w = max(4.0, min(16.0, (group_w - 14) / 4))
        for index, session in enumerate(self.sessions):
            gx = plot.left() + group_w * index + (group_w - bar_w * 4 - 3 * 2) / 2
            for k, ((_name, color), value) in enumerate(zip(self.SERIES, self.values(session))):
                if value is None:
                    continue
                x = gx + k * (bar_w + 2)
                height = max(2.0, plot.height() * value / 100.0)
                rect = QRectF(x, plot.bottom() - height, bar_w, height)
                gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
                gradient.setColorAt(0, QColor(color))
                gradient.setColorAt(1, QColor(color).darker(220))
                p.setPen(Qt.NoPen)
                p.setBrush(gradient)
                p.drawRoundedRect(rect, 2, 2)
            centre = plot.left() + group_w * index + group_w / 2
            when = datetime.datetime.fromtimestamp(session.started).strftime("%b %d")
            p.setPen(QColor("#9aa7b3"))
            p.setFont(_font(self.font(), 10, True))
            p.drawText(QRectF(centre - group_w / 2, plot.bottom() + 4, group_w, 14), Qt.AlignHCenter | Qt.AlignVCenter, when)
            p.setPen(QColor("#5b6e7c"))
            p.setFont(_font(self.font(), 10))
            minutes = session.seconds // 60
            p.drawText(QRectF(centre - group_w / 2, plot.bottom() + 18, group_w, 14), Qt.AlignHCenter | Qt.AlignVCenter,
                       f"{minutes // 60} h {minutes % 60:02d}" if minutes >= 60 else f"{minutes} min")
        x = plot.left()
        for name, color in self.SERIES:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(color))
            p.drawRoundedRect(QRectF(x, h - 12, 9, 9), 2, 2)
            p.setPen(QColor("#9aa7b3"))
            p.setFont(_font(self.font(), 10))
            width = 14 + len(name) * 6 + 14
            p.drawText(QRectF(x + 14, h - 15, width, 14), Qt.AlignLeft | Qt.AlignVCenter, name)
            x += width


# ---------------------------------------------------------------- storage overview
class StorageDonut(QWidget):
    """All drives in one ring: each drive's used space is a coloured arc, free space is the empty track."""

    COLORS = ("#42D4F2", "#DFAC46", "#df83ec", "#35DC7C", "#ff7a59", "#8fa8ff")

    def __init__(self, drives=()):
        super().__init__()
        self.drives = list(drives)
        self.setFixedHeight(112)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setAccessibleName("All drives together")

    def set_drives(self, drives):
        self.drives = list(drives)
        self.update()

    def paintEvent(self, event):
        total = sum(d.total for d in self.drives if d.total)
        if not total:
            return
        used = sum(max(0, d.total - d.free) for d in self.drives if d.total)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        box = QRectF(8, 8, 96, 96)
        p.setPen(QPen(TRACK, 11))
        p.drawEllipse(box)
        angle = 90 * 16
        for index, d in enumerate(self.drives):
            if not d.total:
                continue
            span = -int(360 * 16 * max(0, d.total - d.free) / total)
            if span == 0:
                continue
            pen = QPen(QColor(self.COLORS[index % len(self.COLORS)]), 11)
            pen.setCapStyle(Qt.FlatCap)
            p.setPen(pen)
            p.drawArc(box, angle, span)
            angle += span
        p.setPen(QColor("#f1f4f7"))
        p.setFont(_font(self.font(), 18, bold=True))
        p.drawText(QRectF(8, 34, 96, 26), Qt.AlignCenter, f"{round(100 * used / total)}%")
        p.setPen(QColor("#8794a1"))
        p.setFont(_font(self.font(), 10))
        p.drawText(QRectF(8, 58, 96, 16), Qt.AlignCenter, "of all drives")
        y = 18
        for index, d in enumerate(self.drives[:5]):
            color = QColor(self.COLORS[index % len(self.COLORS)])
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(QRectF(120, y + 3, 10, 10), 3, 3)
            p.setPen(QColor("#d7dfe7"))
            p.setFont(_font(self.font(), 11, True))
            p.drawText(QRectF(136, y, 30, 16), Qt.AlignVCenter | Qt.AlignLeft, f"{d.letter}:")
            p.setPen(QColor("#9aa7b3"))
            p.setFont(_font(self.font(), 11))
            text = f"{human_size(max(0, d.total - d.free))} used of {human_size(d.total)}"
            p.drawText(QRectF(160, y, max(10, self.width() - 164), 16), Qt.AlignVCenter | Qt.AlignLeft,
                       QFontMetrics(p.font()).elidedText(text, Qt.ElideRight, max(10, self.width() - 164)))
            y += 20
