"""Live rings, reference artwork and opt-in capture tiles for the desktop."""
from __future__ import annotations

from PySide6.QtCore import Qt, QRect, QRectF, QSize, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QLayout, QListWidget, QStyledItemDelegate, QStyle, QWidget
from core import human_size
from gg_desktop.reference_widgets import CoverGrid, draw_crop, icon, pixel_font

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
    def __init__(self, *, caption="REPORTED SIZE"):
        super().__init__()
        self.segments = []
        self.caption = caption
        self.title = "No data"
        self.setMinimumSize(135, 140)

    def set_segments(self, segments, title=None):
        self.segments = [(name, max(0, int(value)), color) for name, value, color in segments if value is not None]
        total = sum(value for _, value, _ in self.segments)
        self.title = title if title is not None else human_size(total)
        self.setAccessibleName(self.caption + ": " + self.title + ". " + "; ".join(
            f"{name}: {human_size(value)}" for name, value, _ in self.segments))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        side = min(self.width(), self.height()) - 20
        rect = QRectF((self.width() - side) / 2 + 8, (self.height() - side) / 2 + 8, side - 16, side - 16)
        for delta, color, width in ((-7, "#4a1021", 2), (0, "#18212a", 15), (10, "#3b2029", 1)):
            p.setPen(QPen(QColor(color), width))
            p.drawEllipse(rect.adjusted(delta, delta, -delta, -delta))
        total = sum(v for _, v, _ in self.segments)
        start = 90 * 16
        if total:
            for _, value, color in self.segments:
                span = -round(value / total * 360 * 16)
                p.setPen(QPen(QColor(color), 15))
                p.drawArc(rect, start, span + (16 if span < -32 else 0))
                start += span
        p.setFont(pixel_font(22, True))
        p.setPen(QColor("#ff2446"))
        p.drawText(rect.adjusted(0, -43, 0, 0), Qt.AlignCenter, "GG")
        p.setPen(QColor("#f3f3f7"))
        p.setFont(pixel_font(21, True))
        p.drawText(rect, Qt.AlignCenter, self.title)
        p.setFont(pixel_font(8, True))
        p.setPen(QColor("#c2cbd5"))
        p.drawText(rect.adjusted(0, 36, 0, 0), Qt.AlignCenter, self.caption)


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
