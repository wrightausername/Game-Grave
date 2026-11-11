"""Live rings, reference artwork and opt-in capture tiles for the desktop."""
from __future__ import annotations

from math import atan2, cos, degrees, hypot, radians, sin

from PySide6.QtCore import Qt, QPointF, QRect, QRectF, QSize, Signal
from functools import lru_cache

from PySide6.QtGui import QColor, QBrush, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QFrame, QLayout, QListWidget, QStyledItemDelegate, QStyle, QWidget
from core import human_size
from gg_desktop.reference_widgets import BRAND, CoverGrid, draw_crop, icon, pixel_font

# The GG mark inside gg_desktop/assets/brand/game_grave_logo.png (transparent PNG): left, top, width, height.
GG_MARK = (24, 40, 356, 320)


@lru_cache(maxsize=16)
def gg_mark(width, height, dpr):
    """The GG mark cut out of the full-resolution brand logo (no background), resampled once to real device pixels."""
    source = QPixmap(str(BRAND / "game_grave_logo.png"))
    if source.isNull() or width < 1 or height < 1:
        return QPixmap()
    left, top, w, h = GG_MARK
    out = source.copy(left, top, w, h).scaled(max(1, round(width * dpr)), max(1, round(height * dpr)),
                                              Qt.KeepAspectRatio, Qt.SmoothTransformation)
    out.setDevicePixelRatio(dpr)
    return out

CAPTURE_ROLE = int(Qt.UserRole) + 10


class ActionFlow(QLayout):
    """Keyboard-native action buttons wrap when a desktop panel gets narrower."""
    def __init__(self, parent=None, spacing=5):
        super().__init__(parent)
        self.items = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(spacing)

    def addItem(self, item):
        self.items.append(item)

    def count(self):
        return len(self.items)

    def itemAt(self, index):
        return self.items[index] if 0 <= index < len(self.items) else None

    def takeAt(self, index):
        return self.items.pop(index) if 0 <= index < len(self.items) else None

    def expandingDirections(self):
        return Qt.Orientations()

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._arrange(QRect(0, 0, width, 0), True)

    def minimumSize(self):
        size = QSize()
        for item in self.items:
            size = size.expandedTo(item.minimumSize())
        return size

    def sizeHint(self):
        return self.minimumSize()

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._arrange(rect, False)

    def _arrange(self, rect, measure):
        x, y, height = rect.x(), rect.y(), 0
        for item in self.items:
            if item.isEmpty():
                continue
            hint = item.sizeHint().expandedTo(item.minimumSize())
            width = min(hint.width(), max(1, rect.width()))
            if x > rect.x() and x + width > rect.right() + 1:
                x, y, height = rect.x(), y + height + self.spacing(), 0
            if not measure:
                item.setGeometry(QRect(x, y, width, hint.height()))
            x += width + self.spacing()
            height = max(height, hint.height())
        return y + height - rect.y()


class ReferenceArt(QWidget):
    """Decorative artwork, never a preview of a local user file."""
    def __init__(self, scene, crop, *, height=85):
        super().__init__()
        self.scene, self.crop = scene, crop
        self.setFixedHeight(height)
        self.setMinimumWidth(0)
        self.setAccessibleName("Decorative Game Grave reference artwork")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 5, 5)
        p.setClipPath(path)
        draw_crop(p, QRectF(self.rect()), self.scene, self.crop)


class FootprintRing(QWidget):
    brand_mark = True  # the real GG mark (transparent, full resolution); False falls back to the old photo crop

    def __init__(self, *, caption="REPORTED SIZE"):
        super().__init__()
        self.segments = []
        self.caption = caption
        self.title = "No data"
        self.setMinimumSize(135, 140)
        self.setMouseTracking(True)
        self._hovered = -1
        self._base_tip = ""

    def set_segments(self, segments, title=None):
        self.segments = [(name, max(0, int(value)), color) for name, value, color in segments if value is not None]
        total = sum(value for _, value, _ in self.segments)
        self.title = title if title is not None else human_size(total)
        self.setAccessibleName(self.caption + ": " + self.title + ". " + "; ".join(
            f"{name}: {human_size(value)}" for name, value, _ in self.segments))
        self._hovered = -1
        self.setToolTip(self.accessibleName())
        self._base_tip = self.toolTip()
        self.update()

    def paintEvent(self, event):
        """A machined, backlit dial; only the main colored arcs encode bytes."""
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        side = min(self.width(), self.height())
        p.translate(self.width() / 2, self.height() / 2)
        p.scale(side / 220, side / 220)

        def circle(radius):
            return QRectF(-radius, -radius, radius * 2, radius * 2)

        def arc(radius, start, span, width, color):
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QBrush(color), width, Qt.SolidLine, Qt.FlatCap))
            p.drawArc(circle(radius), round(start * 16), round(span * 16))

        def polar(radius, angle):
            theta = radians(angle)
            return radius * cos(theta), -radius * sin(theta)

        halo = QRadialGradient(0, 0, 109)
        halo.setColorAt(0, QColor(4, 8, 13, 0))
        halo.setColorAt(.59, QColor(255, 28, 69, 3))
        halo.setColorAt(.83, QColor(255, 28, 69, 15))
        halo.setColorAt(1, QColor(255, 28, 69, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(halo)
        p.drawEllipse(circle(109))

        # Outer index marks and interrupted laser rails frame the data band.
        for index in range(72):
            angle = 90 - index * 5
            major = index % 6 == 0
            p.setPen(QPen(QColor("#687d91" if major else "#263b4c"), .95 if major else .6))
            x1, y1 = polar(103 if major else 105, angle)
            x2, y2 = polar(108, angle)
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        for angle, span in ((122, 27), (212, 19), (302, 27), (32, 19)):
            glow = QColor("#ff2146")
            glow.setAlpha(30)
            arc(109, angle, span, 5, glow)
            arc(109, angle, span, 1.2, QColor("#ed2649"))

        metal = QLinearGradient(-90, -100, 85, 100)
        for stop, color in ((0, "#7490a5"), (.18, "#182532"), (.34, "#485967"),
                            (.55, "#050a10"), (.82, "#455969"), (1, "#101a23")):
            metal.setColorAt(stop, QColor(color))
        arc(100.4, 0, 360, 3.2, metal)
        arc(98, 0, 360, 1, QColor("#071017"))
        arc(89, 0, 360, 21, QColor("#0c1722"))

        total = sum(v for _, v, _ in self.segments)
        start = 90.0
        if total:
            for index, (_, value, color) in enumerate(self.segments):
                if value <= 0:
                    continue
                span = -value / total * 360
                gap = min(1.1, abs(span) * .045)
                visible_start, visible_span = start - gap / 2, span + gap
                base = QColor(color)
                active = index == self._hovered
                for width, opacity in ((34, 10), (28, 18), (23, 33)):
                    glow = QColor(base)
                    glow.setAlpha(opacity + (12 if active else 0))
                    arc(89, visible_start, visible_span, width, glow)

                bevel = QLinearGradient(-50, -100, 45, 105)
                for stop, shade in ((0, base.lighter(155)), (.22, base.lighter(118)),
                                     (.47, base), (.7, base.darker(135)), (1, base.darker(205))):
                    bevel.setColorAt(stop, shade)
                arc(89, visible_start, visible_span, 18.5, bevel)
                arc(97.5, visible_start, visible_span, 1.2, base.lighter(150))
                arc(80.6, visible_start, visible_span, 1.6, base.darker(180))

                # Fine grooves add depth, with a continuous color stripe for
                # reading the original category hue even under the bevel.
                first = int((90 - start) / 4) + 1
                last = int((90 - start - span) / 4)
                p.setPen(QPen(QColor(2, 7, 12, 65), .7))
                for mark in range(first, last + 1):
                    angle = 90 - mark * 4
                    x1, y1 = polar(82, angle)
                    x2, y2 = polar(96, angle)
                    p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
                arc(89, visible_start, visible_span, 2.2, base)
                if active:
                    arc(99.1, visible_start, visible_span, 1.3, QColor("#e9faff"))
                start += span

        # Recessed center, steel lip and glass reflection.
        arc(76, 0, 360, 2.8, metal)
        core = QRadialGradient(-24, -35, 113)
        core.setColorAt(0, QColor("#172c3e"))
        core.setColorAt(.42, QColor("#09131f"))
        core.setColorAt(.75, QColor("#02060b"))
        core.setColorAt(1, QColor("#101a26"))
        p.setPen(QPen(QColor("#070d14"), 2.2))
        p.setBrush(core)
        p.drawEllipse(circle(72.5))
        arc(71.4, 37, 133, .9, QColor("#496375"))
        arc(71.4, 213, 95, .8, QColor("#5b1b31"))
        arc(67.8, 4, 40, .65, QColor("#254454"))

        glass = QPainterPath()
        glass.addEllipse(circle(70))
        p.save()
        p.setClipPath(glass)
        highlight = QLinearGradient(-50, -75, 25, 18)
        highlight.setColorAt(0, QColor(175, 221, 255, 19))
        highlight.setColorAt(1, QColor(175, 221, 255, 0))
        p.fillRect(QRectF(-80, -80, 160, 76), highlight)
        p.restore()

        logo_glow = QRadialGradient(0, -30, 36)
        logo_glow.setColorAt(0, QColor(255, 25, 65, 31))
        logo_glow.setColorAt(1, QColor(255, 25, 65, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(logo_glow)
        p.drawEllipse(QRectF(-36, -65, 72, 72))
        if self.brand_mark:
            height = 38.0
            width = height * GG_MARK[2] / GG_MARK[3]
            device = p.deviceTransform().m11()  # logical-to-pixel scale including the dial's own scaling
            mark = gg_mark(max(1, round(width * device)), max(1, round(height * device)), 1.0)
            if not mark.isNull():
                p.save()
                p.setRenderHint(QPainter.SmoothPixmapTransform)
                p.drawPixmap(QRectF(-width / 2, -50, width, height), mark, QRectF(mark.rect()))
                p.restore()
        else:
            p.setCompositionMode(QPainter.CompositionMode_Screen)
            draw_crop(p, QRectF(-22, -49, 44, 37), "games", (26, 14, 53, 46), fill=False)
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)

        font = pixel_font(26 if len(self.title) < 10 else 21, True)
        font.setLetterSpacing(QFont.AbsoluteSpacing, -.4)
        p.setFont(font)
        p.setPen(QColor("#020408"))
        p.drawText(QRectF(-75, -5, 150, 42), Qt.AlignCenter, self.title)
        p.setPen(QColor("#f0f7ff"))
        p.drawText(QRectF(-75, -7, 150, 42), Qt.AlignCenter, self.title)
        font = pixel_font(8, True)
        font.setLetterSpacing(QFont.AbsoluteSpacing, .7)
        p.setFont(font)
        p.setPen(QColor("#8ca6bb"))
        p.drawText(QRectF(-73, 30, 146, 15), Qt.AlignCenter, self.caption)
        arc(55, 247, 46, .9, QColor("#91213c"))

    def mouseMoveEvent(self, event):
        point = event.position()
        dx, dy = point.x() - self.width() / 2, point.y() - self.height() / 2
        scale = min(self.width(), self.height()) / 220
        total = sum(value for _, value, _ in self.segments)
        hovered = -1
        if total and 78 <= hypot(dx, dy) / max(scale, .01) <= 101:
            angle = degrees(atan2(dx, -dy)) % 360
            cumulative = 0
            for index, (_, value, _) in enumerate(self.segments):
                cumulative += value / total * 360
                if value and angle < cumulative:
                    hovered = index
                    break
        if hovered != self._hovered:
            if self._hovered < 0:
                self._base_tip = self.toolTip()
            self._hovered = hovered
            if hovered >= 0:
                name, value, _ = self.segments[hovered]
                self.setToolTip(f"{name}\n{human_size(value)} · {value / total:.1%}")
            else:
                self.setToolTip(self._base_tip)
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self._hovered >= 0:
            self._hovered = -1
            self.setToolTip(self._base_tip)
            self.update()
        super().leaveEvent(event)


class CaptureDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        return self.parent().gridSize()

    def paint(self, painter, option, index):
        data = index.data(CAPTURE_ROLE) or {}
        item = data.get("item")
        if item is None:
            return
        painter.save()
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        area = QRectF(option.rect).adjusted(4, 4, -4, -4)
        path = QPainterPath()
        path.addRoundedRect(area, 5, 5)
        painter.setClipPath(path)
        painter.fillRect(area, QColor("#0b1923"))
        art = area.adjusted(0, 0, 0, -23)
        preview = data.get("preview")
        if preview is not None and not preview.isNull():
            scaled = preview.scaled(art.size().toSize(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            painter.drawPixmap(art.toRect(), scaled, QRect((scaled.width() - int(art.width())) // 2,
                (scaled.height() - int(art.height())) // 2, int(art.width()), int(art.height())))
        else:
            symbol = "camera" if item.kind == "Screenshots" else "play"
            icon(symbol, "#526c83", 28).paint(painter, QRect(int(art.center().x() - 14), int(art.center().y() - 25), 28, 28))
            painter.setFont(pixel_font(10))
            painter.setPen(QColor("#aab9c8"))
            painter.drawText(art.adjusted(5, 35, -5, -4), Qt.AlignCenter, "Preview to load" if item.kind == "Screenshots" else "Recording")
        checked = index.data(Qt.CheckStateRole) in (Qt.Checked, Qt.Checked.value)
        painter.setBrush(QColor("#d40b30" if checked else "#090f15"))
        painter.setPen(QPen(QColor("#ff5c76" if checked else "#aebbc7"), 1.3))
        check = QRectF(area.left() + 7, area.top() + 7, 13, 13)
        painter.drawRoundedRect(check, 2, 2)
        if checked:
            painter.setPen(QPen(QColor("white"), 1.5))
            painter.drawLine(int(check.left() + 3), int(check.top() + 6), int(check.left() + 6), int(check.top() + 10))
            painter.drawLine(int(check.left() + 6), int(check.top() + 10), int(check.left() + 11), int(check.top() + 3))
        painter.fillRect(QRectF(area.left(), area.bottom() - 22, area.width(), 22), QColor("#04080c"))
        painter.setPen(QColor("#d8e2e9"))
        painter.setFont(pixel_font(9))
        dims = data.get("dimensions")
        caption = f"{dims[0]} × {dims[1]}" if dims else item.game
        caption = painter.fontMetrics().elidedText(caption, Qt.ElideRight, int(area.width() - 54))
        painter.drawText(area.adjusted(7, area.height() - 24, -5, -1), Qt.AlignLeft | Qt.AlignVCenter, caption)
        painter.drawText(area.adjusted(0, area.height() - 24, -5, -1), Qt.AlignRight | Qt.AlignVCenter, human_size(item.record.size))
        painter.setClipping(False)
        selected = option.state & QStyle.State_Selected
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor("#ff1c40" if checked or selected else "#273540"), 2 if checked or selected else 1))
        painter.drawRoundedRect(area, 5, 5)
        painter.restore()


class CaptureGrid(QListWidget):
    previewRequested = Signal(int)

    def __init__(self):
        super().__init__()
        self.setObjectName("coverGrid")
        self.setFrameShape(QFrame.NoFrame)
        self.setViewMode(QListWidget.IconMode)
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Static)
        self.setUniformItemSizes(True)
        self.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setItemDelegate(CaptureDelegate(self))
        self.setMinimumSize(130, 145)
        self.tile_width = 125
        self.itemDoubleClicked.connect(lambda _: self.previewRequested.emit(self.currentRow()))

    def _fit(self):
        width = max(100, self.viewport().width() - 2)
        columns = max(1, width // self.tile_width)
        cell = width // columns
        self.setGridSize(QSize(cell, int(cell * .77)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()

    def mouseReleaseEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        if item and event.button() == Qt.LeftButton:
            rect = self.visualItemRect(item)
            if event.position().x() < rect.left() + 32 and event.position().y() < rect.top() + 32:
                item.setCheckState(Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)
                self.setCurrentItem(item)
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space and self.currentItem():
            item = self.currentItem()
            item.setCheckState(Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)
            return
        super().keyPressEvent(event)
