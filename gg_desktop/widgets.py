"""Crimson Command real Qt widgets. All assets local and no network calls."""
from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import Qt, QSize, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
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
        self.setMinimumHeight(187)
        self.setMaximumHeight(220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.title = title
        self.subtitle = subtitle
        self.detail = detail
        from PySide6.QtSvg import QSvgRenderer
        self.art = QSvgRenderer(str(Path(__file__).parent / "assets" / "crimson_hero.svg"))
        self.atlas = QPixmap(str(Path(__file__).parent / "assets" / "crimson_atlas.jpg"))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        target = QRectF(0, 0, self.width(), self.height())
        painter.setBrush(QColor("#0E161E"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(target, 11, 11)
        painter.save()
        painter.setClipRect(target)
        if not self.atlas.isNull():
            # Art from the approved mockup. ONLY the scenery region is sampled,
            # never its fictional UI figures or controls.
            painter.drawPixmap(target, self.atlas, QRectF(0, 0, 788, 190))
        elif self.art.isValid():
            self.art.render(painter, QRectF(0, -6, self.width(), self.height() + 16))
        from PySide6.QtGui import QLinearGradient
        grad = QLinearGradient(0, 0, self.width() * .79, 0)
        grad.setColorAt(0, QColor(4, 9, 16, 247))
        grad.setColorAt(.46, QColor(5, 10, 17, 122))
        grad.setColorAt(1, QColor(10, 15, 22, 15))
        painter.fillRect(target, grad)
        painter.setPen(QColor("#F5F7FB"))
        painter.setFont(QFont("Segoe UI", 23, QFont.Black))
        painter.drawText(24, 55, self.title)
        painter.setPen(QColor(COLORS["red"]))
        painter.setFont(QFont("Segoe UI", 23, QFont.Black))
        painter.drawText(24, 91, self.subtitle)
        painter.setPen(QColor("#BBCAD7"))
        painter.setFont(QFont("Segoe UI", 10))
        painter.drawText(QRectF(25, 108, max(140, self.width() * .64), 65),
                         Qt.AlignLeft | Qt.TextWordWrap, self.detail)
        painter.restore()
        painter.setPen(QPen(QColor("#334552"), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(target.adjusted(.5, .5, -.5, -.5), 11, 11)


class LandscapeArt(QFrame):
    """Original themed art, not a game screenshot. Paints only local SVG files."""
    SCENES = {
        "sunset": "crimson_sunset.svg",
        "fog": "crimson_fog.svg",
        "footer": "crimson_footer.svg",
        "hero": "crimson_hero.svg",
    }

    def __init__(self, height=154, *, scene="sunset", note=""):
        super().__init__()
        self.setMinimumHeight(height)
        self.setMaximumHeight(height)
        self.setObjectName("landscapeArt")
        self.scene = scene if scene in self.SCENES else "sunset"
        self.note = note
        self.setAccessibleName("Original decorative Game Grave " + self.scene +
                               " illustration, not a personal screenshot.")
        from PySide6.QtSvg import QSvgRenderer
        self.renderer = QSvgRenderer(str(
            Path(__file__).parent / "assets" / self.SCENES[self.scene]))
        self.atlas = QPixmap(str(Path(__file__).parent / "assets" / "crimson_atlas.jpg"))
        self.crop_regions = {
            "sunset": QRectF(2, 211, 352, 181),
            "fog": QRectF(393, 235, 325, 119),
            "footer": QRectF(790, 24, 219, 232),
            "hero": QRectF(0, 0, 788, 190),
        }

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        area = QRectF(0, 0, self.width(), self.height())
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#0A1521"))
        painter.drawRoundedRect(area, 9, 9)
        painter.save()
        painter.setClipRect(area)
        if not self.atlas.isNull():
            painter.drawPixmap(area, self.atlas,
                               self.crop_regions.get(self.scene,
                                                     self.crop_regions["sunset"]))
        elif self.renderer.isValid():
            size = self.renderer.defaultSize()
            if size.width() and size.height():
                scale = max(self.width() / size.width(),
                            self.height() / size.height())
                w, h = size.width() * scale, size.height() * scale
                self.renderer.render(painter, QRectF(
                    (self.width() - w) / 2, (self.height() - h) / 2, w, h))
        if self.note:
            painter.fillRect(QRectF(0, self.height() - 38, self.width(), 38),
                             QColor(4, 9, 15, 221))
            painter.setPen(QColor("#ECF3FA"))
            painter.setFont(QFont("Segoe UI", 9))
            painter.drawText(QRectF(10, self.height() - 34, self.width() - 20, 30),
                             Qt.AlignLeft | Qt.TextWordWrap, self.note)
        painter.restore()
        painter.setPen(QPen(QColor("#29465A"), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(area.adjusted(.5, .5, -.5, -.5), 9, 9)


class StorageRing(QWidget):
    """Crimson/cyan/gray segmented disk chart using actual observed capacity.

    Game reported sizes can overlap. Their capped display is never an exact
    independent measurement of physical disk usage.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.capacity = 0
        self.free = 0
        self.known_games = 0
        self.setMinimumSize(146, 158)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAccessibleName("Storage usage chart. Scan the PC to load details.")

    def update_amounts(self, capacity: int, free: int, known_games: int = 0):
        self.capacity = max(0, int(capacity))
        self.free = max(0, min(int(free), self.capacity))
        self.known_games = max(0, min(int(known_games), self.capacity - self.free))
        used = self.capacity - self.free
        self.setAccessibleName(
            f"Disk capacity {self.capacity} bytes; used {used}; free {self.free}. "
            f"Up to {self.known_games} bytes reported by games, not independently verified.")
        self.update()

    def paintEvent(self, event):
        from core import human_size
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        side = max(100, min(self.width(), self.height()) - 16)
        size = side - 28
        rect = QRectF((self.width() - size) / 2,
                      (self.height() - size) / 2, size, size)
        painter.setPen(QPen(QColor("#3A4552"), 19, Qt.SolidLine, Qt.FlatCap))
        painter.drawArc(rect, 0, 360 * 16)
        if self.capacity:
            fractions = (
                (self.known_games / self.capacity, QColor(COLORS["red"])),
                ((self.capacity - self.free - self.known_games) / self.capacity,
                 QColor(COLORS["cyan"])),
            )
            start = 90 * 16
            for fraction, color in fractions:
                extent = -int(fraction * 360 * 16)
                if extent:
                    painter.setPen(QPen(color, 19, Qt.SolidLine, Qt.FlatCap))
                    painter.drawArc(rect, start, extent)
                    start += extent
        painter.setPen(QColor(COLORS["text"]))
        painter.setFont(QFont("Segoe UI", 17, QFont.Bold))
        painter.drawText(rect.adjusted(0, -12, 0, 0), Qt.AlignCenter,
                         human_size(self.capacity) if self.capacity else "No data")
        painter.setFont(QFont("Segoe UI", 10))
        painter.setPen(QColor(COLORS["muted"]))
        painter.drawText(rect.adjusted(0, 26, 0, 12), Qt.AlignCenter, "Total")


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
