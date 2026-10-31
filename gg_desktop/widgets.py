"""Crimson Command real Qt widgets. All assets local and no network calls."""
from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import Qt, QSize, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QHBoxLayout, QVBoxLayout, QPushButton,
    QScrollArea, QGridLayout, QProgressBar, QTableWidget, QHeaderView,
    QSizePolicy, QAbstractItemView,
)
from gg_desktop.theme import COLORS


def label(text: str = "", role: str = "", wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    if role:
        widget.setObjectName(role)
    widget.setWordWrap(wrap)
    widget.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return widget


def row(*, spacing: int = 10, margins=(0, 0, 0, 0)) -> QHBoxLayout:
    result = QHBoxLayout()
    result.setContentsMargins(*margins)
    result.setSpacing(spacing)
    return result


def column(*, spacing: int = 10, margins=(0, 0, 0, 0)) -> QVBoxLayout:
    result = QVBoxLayout()
    result.setContentsMargins(*margins)
    result.setSpacing(spacing)
    return result


def button(text: str, action=None, *, kind: str = "", tip: str = "") -> QPushButton:
    control = QPushButton(text)
    if kind:
        control.setObjectName(kind)
    if tip:
        control.setToolTip(tip)
    control.setAccessibleName(text.replace("…", ""))
    control.setFocusPolicy(Qt.StrongFocus)
    if action:
        control.clicked.connect(action)
    return control


def panel(*, kind="panel", padding=17, spacing=10) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName(kind)
    frame.setMinimumWidth(0)
    frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    contents = column(spacing=spacing, margins=(padding, padding, padding, padding))
    frame.setLayout(contents)
    return frame, contents


def section_title(title: str, trailing: str = "") -> QWidget:
    box = QWidget()
    layout = row()
    box.setLayout(layout)
    layout.addWidget(label(title, "sectionTitle"), 1)
    if trailing:
        layout.addWidget(label(trailing, "caption"))
    return box


class ScrollPage(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.body = QWidget()
        self.body.setObjectName("scrollBody")
        self.content = column(spacing=15, margins=(20, 18, 20, 28))
        self.body.setLayout(self.content)
        self.setWidget(self.body)

    def clear(self):
        while self.content.count():
            item = self.content.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
            elif item.layout() is not None:
                destroy_layout(item.layout())


def destroy_layout(layout):
    while layout.count():
        child = layout.takeAt(0)
        if child.widget():
            child.widget().deleteLater()
        elif child.layout():
            destroy_layout(child.layout())


def page_heading(page: ScrollPage, title: str, subtitle: str):
    page.content.addWidget(label(title, "pageTitle"))
    page.content.addWidget(label(subtitle, "subtle", wrap=True))


class HeroBanner(QFrame):
    """Original game-styled local art drawn with an opacity-safe text overlay."""
    def __init__(self, *, title="YOUR GAMES.", subtitle="A CLEANER TOMORROW.",
                 detail="A lighter PC. A safer way to manage gaming storage."):
        super().__init__()
        self.setObjectName("hero")
        self.setMinimumHeight(157)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.title = title
        self.subtitle = subtitle
        self.detail = detail
        from PySide6.QtSvg import QSvgRenderer
        self.art = QSvgRenderer(str(Path(__file__).parent / "assets" / "crimson_ruins.svg"))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        target = QRectF(0, 0, self.width(), self.height())
        painter.setBrush(QColor("#0E161E"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(target, 11, 11)
        painter.save()
        painter.setClipRect(target)
        if self.art.isValid():
            # Crop art into the banner rather than stretching its full dimensions.
            self.art.render(painter, QRectF(0, -22, self.width(), self.height() + 47))
        from PySide6.QtGui import QLinearGradient
        grad = QLinearGradient(0, 0, self.width() * .79, 0)
        grad.setColorAt(0, QColor(4, 9, 16, 250))
        grad.setColorAt(.46, QColor(5, 10, 17, 183))
        grad.setColorAt(1, QColor(10, 15, 22, 15))
        painter.fillRect(target, grad)
        painter.setPen(QColor("#F5F7FB"))
        painter.setFont(QFont("Segoe UI", 20, QFont.Black))
        painter.drawText(22, 46, self.title)
        painter.setPen(QColor(COLORS["red"]))
        painter.setFont(QFont("Segoe UI", 20, QFont.Black))
        painter.drawText(22, 79, self.subtitle)
        painter.setPen(QColor("#BBCAD7"))
        painter.setFont(QFont("Segoe UI", 10))
        painter.drawText(QRectF(23, 92, max(120, self.width() * .58), 52),
                         Qt.AlignLeft | Qt.TextWordWrap, self.detail)
        painter.restore()
        painter.setPen(QPen(QColor("#334552"), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(target.adjusted(.5, .5, -.5, -.5), 11, 11)


class LandscapeArt(QFrame):
    """Original local placeholder artwork, NOT the user's actual game screenshot."""
    def __init__(self, height=154):
        super().__init__()
        self.setMinimumHeight(height)
        self.setMaximumHeight(height)
        self.setAccessibleName("Original decorative Game Grave landscape artwork. Screenshot not loaded.")
        from PySide6.QtSvg import QSvgRenderer
        self.renderer = QSvgRenderer(
            str(Path(__file__).parent / "assets" / "crimson_ruins.svg"))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        area = QRectF(0, 0, self.width(), self.height())
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#111922"))
        painter.drawRoundedRect(area, 10, 10)
        painter.setClipRect(area)
        if self.renderer.isValid():
            self.renderer.render(painter, QRectF(
                -self.width() * .3, -42, self.width() * 1.6,
                self.height() + 125))
        painter.fillRect(QRectF(0, self.height() - 41, self.width(), 41),
                         QColor(6, 10, 17, 212))
        painter.setPen(QColor("#C4D4E1"))
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(QRectF(12, self.height() - 35, self.width() - 24, 25),
                         Qt.AlignLeft | Qt.AlignVCenter,
                         "Local illustration  •  Click Preview to inspect your actual image")


class StorageRing(QWidget):
    """Only real OS-reported used/free disk usage; no fake reclaimed segment."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.capacity = 0
        self.free = 0
        self.setMinimumSize(145, 155)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAccessibleName("Storage usage chart. Capacity unknown.")

    def update_amounts(self, capacity: int, free: int):
        self.capacity = max(0, capacity)
        self.free = max(0, min(free, capacity))
        used = self.capacity - self.free
        self.setAccessibleName(f"Disk used: {used} bytes. Free: {self.free} bytes.")
        self.update()

    def paintEvent(self, event):
        from core import human_size
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        side = max(70, min(self.width(), self.height()) - 22)
        rect = QRectF((self.width() - side) / 2 + 12,
                      (self.height() - side) / 2 + 12, side - 24, side - 24)
        pen = QPen(QColor("#283948"), 17)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, 0, 360 * 16)
        if self.capacity:
            used_ratio = (self.capacity - self.free) / self.capacity
            used = QPen(QColor(COLORS["red"]), 17)
            used.setCapStyle(Qt.RoundCap)
            painter.setPen(used)
            painter.drawArc(rect, 90 * 16, -int(used_ratio * 360 * 16))
        painter.setPen(QColor(COLORS["text"]))
        painter.setFont(QFont("Segoe UI", 13, QFont.Bold))
        painter.drawText(rect.adjusted(0, -12, 0, 0), Qt.AlignCenter,
                         human_size(self.capacity - self.free) if self.capacity else "No data")
        painter.setFont(QFont("Segoe UI", 9))
        painter.setPen(QColor(COLORS["muted"]))
        painter.drawText(rect.adjusted(0, 20, 0, 15), Qt.AlignCenter, "used")


class MetricCard(QFrame):
    def __init__(self, caption: str, value: str, hint: str = "", *, tone="text"):
        super().__init__()
        self.setObjectName("metricCard")
        contents = column(spacing=5, margins=(16, 14, 16, 14))
        self.setLayout(contents)
        self.caption = label(caption.upper(), "caption")
        self.value = label(value, "metricValue")
        self.hint = label(hint, "subtle", wrap=True)
        contents.addWidget(self.caption)
        contents.addWidget(self.value)
        contents.addWidget(self.hint)
        if tone != "text":
            self.value.setStyleSheet("color:" + COLORS[tone] + ";")

    def update_value(self, value: str, hint: str = ""):
        self.value.setText(value)
        self.hint.setText(hint)


class ActionCard(QFrame):
    def __init__(self, glyph: str, title: str, explanation: str, action):
        super().__init__()
        self.setObjectName("actionCard")
        self._action = action
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(title + ". " + explanation)
        contents = row(spacing=11, margins=(13, 12, 13, 12))
        self.setLayout(contents)
        g = label(glyph)
        g.setStyleSheet("color:#FF5269;font-size:25px;")
        contents.addWidget(g)
        inner = QWidget()
        inner.setMinimumWidth(0)
        inner.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        inner_layout = column(spacing=4)
        inner.setLayout(inner_layout)
        heading = label(title, "sectionTitle", wrap=True)
        heading.setMinimumWidth(0)
        heading.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        detail = label(explanation, "subtle", wrap=True)
        detail.setMinimumWidth(0)
        detail.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        inner_layout.addWidget(heading)
        inner_layout.addWidget(detail)
        contents.addWidget(inner, 1)
        trigger = button("›", action, kind="link", tip=title)
        trigger.setMinimumWidth(36)
        trigger.setAccessibleName(title)
        contents.addWidget(trigger)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._action()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self._action()
            event.accept()
            return
        super().keyPressEvent(event)


def data_table(headers: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setAlternatingRowColors(False)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setStretchLastSection(True)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    table.setSortingEnabled(False)
    table.setShowGrid(False)
    table.setMinimumHeight(270)
    table.setAccessibleName("Game Grave review table: " + ", ".join(headers))
    table.setFocusPolicy(Qt.StrongFocus)
    return table
