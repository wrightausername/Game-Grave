"""Native controls for the owner-supplied Games / Mods / Old Files designs.

Only decorative artwork comes from the local references. Every label, number,
selection, filter and action is painted or laid out from the current inventory.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import Qt, QPointF, QRect, QRectF, QSize, Signal, Slot
from PySide6.QtGui import (
    QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QAbstractButton, QAbstractItemView, QButtonGroup, QFrame, QHBoxLayout, QLabel, QListWidget,
    QGraphicsDropShadowEffect, QPushButton, QSizePolicy, QStyledItemDelegate, QStyle, QToolButton, QVBoxLayout, QWidget,
)
from gg_desktop.widgets import button, column, label, row

ASSETS = Path(__file__).parent / "assets" / "references"
BRAND = Path(__file__).parent / "assets" / "brand"
RED = "#ff183b"

# Consistent 24px outline icons; no platform-dependent chess/emoji glyphs.
PATHS = {
    "home": '<path d="m3 10 9-7 9 7v11h-6v-7H9v7H3z"/>',
    "game": '<path d="M7 7h10c3 0 4 3 5 10 .5 3-2 4-4 2l-3-3H9l-3 3c-2 2-4.5 1-4-2C3 10 4 7 7 7Z"/><path d="M7 10v6m-3-3h6m6-1h.1m3 2h.1"/>',
    "mods": '<path d="M8 3h5v4c4-3 7 3 2 4v4h-4c3 5-4 7-4 2H3v-6h4V7H3V3h5Z"/>',
    "archive": '<rect x="3" y="4" width="18" height="5" rx="1"/><path d="M5 9v12h14V9m-10 4h6"/>',
    "storage": '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 4 18 4 18 0V5M3 10c0 4 18 4 18 0M3 15c0 4 18 4 18 0"/>',
    "camera": '<path d="M3 7h4l2-3h6l2 3h4v14H3Z"/><circle cx="12" cy="14" r="4"/>',
    "grave": '<path d="M5 21V10a7 7 0 0 1 14 0v11M2 21h20M12 6v8m-3-5h6"/>',
    "dna": '<path d="M7 2c0 10 10 10 10 20M17 2C17 12 7 12 7 22M7 5h10M8 9h8M8 15h8M7 19h10"/>',
    "undo": '<path d="M3 4v6h6M3 10a9 9 0 1 1 0 6m9-10v6l4 2"/>',
    "sparkles": '<path d="m12 3 3 6 6 3-6 3-3 6-3-6-6-3 6-3ZM3 2v4M1 4h4m15 13v5m-2.5-2.5h5"/>',
    "settings": '<path d="m9 3 1-2h4l1 2 3 2 3 1v4l-2 2 2 3-2 4-4-1-1 4h-4l-1-3-4-1-3-3 2-3-2-3 2-4 3 1Z"/><circle cx="12" cy="11" r="3"/>',
    "grid": '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    "list": '<path d="M8 5h13M8 12h13M8 19h13M3 5h.1M3 12h.1M3 19h.1"/>',
    "search": '<circle cx="10" cy="10" r="7"/><path d="m15 15 6 6"/>',
    "folder": '<path d="M2 6h8l2 3h10l-3 12H2V6Zm0 3V4h8l2 2h8v3"/>',
    "download": '<path d="M12 2v13m-6-6 6 6 6-6M3 17v5h18v-5"/>',
    "refresh": '<path d="M21 3v6h-6M3 21v-6h6M4 9a8 8 0 0 1 14-5l3 5M3 15l3 5a8 8 0 0 0 14-5"/>',
    "star": '<path d="m12 2 3 6.5 7 1-5 5 1 7-6-3.5L6 21l1-7-5-5 7-1Z"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 5v7l4 3"/>',
    "check": '<circle cx="12" cy="12" r="9"/><path d="m7 12 3 3 7-7"/>',
    "shield": '<path d="m12 2 9 4v6c0 5-9 10-9 10S3 17 3 12V6z"/><path d="m7 12 3 3 7-7"/>',
    "warning": '<path d="M12 2 1 21h22ZM12 8v6m0 3h.1"/>',
    "filter": '<path d="M2 3h20l-8 9v9l-4-2v-7Z"/>',
    "trash": '<path d="M3 6h18M9 6V3h6v3M5 6l1 16h12l1-16M10 10v8m4-8v8"/>',
    "file": '<path d="M4 2h10l6 6v14H4Zm10 0v7h6M8 13h8m-8 4h8"/>',
    "box": '<path d="m12 2 10 5v10l-10 5-10-5V7Zm0 10L2 7m10 5 10-5m-10 5v10M7 4l10 5"/>',
    "bell": '<path d="M5 17V9a7 7 0 0 1 14 0v8l2 2H3Zm5 5h4"/>',
    "help": '<circle cx="12" cy="12" r="10"/><path d="M9 8a3 3 0 1 1 5 2c-2 1-2 2-2 4m0 3h.1"/>',
    "radio": '<circle cx="12" cy="10" r="2"/><path d="m12 12-3 10h6Zm-6 2a7 7 0 0 1 0-9m12 0a7 7 0 0 1 0 9M3 17a12 12 0 0 1 0-16m18 0a12 12 0 0 1 0 16"/>',
    "play": '<path d="m8 3 13 9-13 9Z"/>',
    "close": '<path d="m5 5 14 14M5 19 19 5"/>',
    "minus": '<path d="M4 12h16"/>',
    "maximize": '<rect x="5" y="5" width="14" height="14" rx="1"/>',
    "more": '<circle cx="4" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="20" cy="12" r="1"/>',
    "chevron": '<path d="m6 9 6 6 6-6"/>',
    "plus": '<path d="M12 3v18M3 12h18"/>',
    "steam": '<circle cx="15" cy="8" r="4"/><path d="m12 11-4 6-6-3m6 3 7-5"/><circle cx="7" cy="17" r="3"/>',
}


LAUNCHER_ASSETS = Path(__file__).parent / "assets" / "launchers"
# Original monogram badges. Official launcher artwork dropped into assets/launchers/<name>.png or .svg is used instead.
LAUNCHER_MARKS = {"epic": ("E", "#e2e4e7"), "ea": ("EA", "#fa284a"), "battlenet": ("B", "#3ba9ed"),
                  "ubisoft": ("U", "#d9e2f0"), "xbox": ("X", "#33d34d"), "gog": ("G", "#bc64ee"),
                  "rockstar": ("R", "#ffc329")}


@lru_cache(maxsize=64)
def launcher_pixmap(name: str, size: int = 22, dpr: int = 4) -> QPixmap:
    """A launcher mark rendered once at real pixel size (vector or supplied HD art), never a photo crop."""
    pixels = max(1, size * dpr)
    pix = QPixmap(pixels, pixels)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
    supplied = next((f for f in (LAUNCHER_ASSETS / (name + ".svg"), LAUNCHER_ASSETS / (name + ".png")) if f.is_file()), None)
    if supplied is not None and supplied.suffix == ".svg":
        QSvgRenderer(str(supplied)).render(painter, QRectF(0, 0, pixels, pixels))
    elif supplied is not None:
        source = QPixmap(str(supplied))
        if not source.isNull():
            fitted = source.scaled(pixels, pixels, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            painter.drawPixmap((pixels - fitted.width()) // 2, (pixels - fitted.height()) // 2, fitted)
    else:
        text, tone = LAUNCHER_MARKS[name]
        accent = QColor(tone)
        box = QRectF(pixels * .04, pixels * .04, pixels * .92, pixels * .92)
        fill = QLinearGradient(box.topLeft(), box.bottomRight())
        fill.setColorAt(0, QColor("#1b2733"))
        fill.setColorAt(1, QColor("#0a1017"))
        painter.setBrush(fill)
        painter.setPen(QPen(accent, max(1.0, pixels * .055)))
        painter.drawRoundedRect(box, pixels * .24, pixels * .24)
        font = QFont("Segoe UI")
        font.setBold(True)
        font.setPixelSize(round(pixels * (.42 if len(text) > 1 else .56)))
        painter.setFont(font)
        painter.setPen(accent)
        painter.drawText(box, Qt.AlignCenter, text)
    painter.end()
    pix.setDevicePixelRatio(dpr)
    return pix


@lru_cache(maxsize=192)
def icon(name: str, color="#e1e3e7", size=22) -> QIcon:
    if name in LAUNCHER_MARKS:
        return QIcon(launcher_pixmap(name, max(size, 22), 4))
    paths = PATHS.get(name, PATHS["game"])
    data = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            f'fill="none" stroke="{color}" stroke-width="1.6" '
            f'stroke-linecap="round" stroke-linejoin="round">{paths}</svg>').encode()
    pix = QPixmap(size * 2, size * 2)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    QSvgRenderer(data).render(painter)
    painter.end()
    pix.setDevicePixelRatio(2)
    return QIcon(pix)


def tool(text, symbol, action=None, *, active=False, kind="", tip=""):
    control = button(text, action, kind=kind or "toolButton", tip=tip)
    control.setIcon(icon(symbol))
    control.setIconSize(QSize(19, 19))
    control.setProperty("active", active)
    if kind in {"primary", "danger"}:
        glow = QGraphicsDropShadowEffect(control)
        glow.setBlurRadius(12)
        glow.setOffset(0, 0)
        glow.setColor(QColor(255, 24, 59, 110))
        control.setGraphicsEffect(glow)
    return control


def tile_action(text, symbol, action, tip=""):
    control = QToolButton()
    control.setText(text)
    control.setIcon(icon(symbol, size=24))
    control.setIconSize(QSize(24, 24))
    control.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
    control.setAccessibleName(text)
    control.setToolTip(tip or text)
    control.setStyleSheet("font-size:10px;")
    control.setMinimumWidth(0)
    control.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
    control.setFixedHeight(47)
    control.clicked.connect(action)
    return control


@lru_cache(maxsize=16)
def reference(name: str) -> QPixmap:
    return QPixmap(str(ASSETS / (name + ".jpg")))


def draw_crop(painter, target, source, crop, *, fill=True):
    """Render an artwork region, preserving aspect ratio without editing assets."""
    pix = reference(source)
    if pix.isNull():
        return
    src = QRectF(*crop)
    target = QRectF(target)
    ratio = target.width() / max(1, target.height())
    if fill:
        if src.width() / src.height() > ratio:
            width = src.height() * ratio
            src.setLeft(src.left() + (src.width() - width) / 2)
            src.setWidth(width)
        else:
            height = src.width() / ratio
            src.setTop(src.top() + (src.height() - height) / 2)
            src.setHeight(height)
    painter.drawPixmap(target, pix, src)


@lru_cache(maxsize=None)
def brand_source(name):
    """A full-resolution brand PNG (transparent logo or backdrop), loaded once."""
    return QPixmap(str(BRAND / name))


@lru_cache(maxsize=32)
def brand_scaled(name, width, height, dpr, cover):
    """The brand art resampled once to this widget's real pixel size so it stays sharp on any screen.

    `cover` fills the box and crops from the bottom-left; otherwise the whole picture fits inside it.
    """
    source = brand_source(name)
    if source.isNull() or width < 1 or height < 1:
        return QPixmap()
    pixel_w, pixel_h = max(1, round(width * dpr)), max(1, round(height * dpr))
    if cover:
        scale = max(pixel_w / source.width(), pixel_h / source.height())
        sized = source.scaled(max(pixel_w, round(source.width() * scale)), max(pixel_h, round(source.height() * scale)),
                              Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        out = sized.copy(0, sized.height() - pixel_h, pixel_w, pixel_h)
    else:
        out = source.scaled(pixel_w, pixel_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    out.setDevicePixelRatio(dpr)
    return out


@lru_cache(maxsize=48)
def brand_cover(name, width, height, dpr, anchor_x=1.0, anchor_y=.5):
    """Fill width x height with the picture (no stretching, no gaps), cropping the overflow.

    The picture is resampled once to real device pixels, so a banner that is cropped to a small window and
    one that fills a 4K screen both stay sharp. `anchor_x` 1.0 keeps the right edge of the picture.
    """
    source = brand_source(name)
    if source.isNull() or width < 1 or height < 1:
        return QPixmap()
    pixel_w, pixel_h = max(1, round(width * dpr)), max(1, round(height * dpr))
    scale = max(pixel_w / source.width(), pixel_h / source.height())
    sized = source.scaled(max(pixel_w, round(source.width() * scale)), max(pixel_h, round(source.height() * scale)),
                          Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    out = sized.copy(round((sized.width() - pixel_w) * anchor_x), round((sized.height() - pixel_h) * anchor_y),
                     pixel_w, pixel_h)
    out.setDevicePixelRatio(dpr)
    return out


class Brand(QWidget):
    """The Game Grave logo: a transparent HD PNG, resampled to the screen so it never looks soft."""

    CANVAS = (1600, 384)       # the PNG's size
    CONTENT = (31, 49, 1515, 351)  # where the artwork sits inside it

    def __init__(self):
        super().__init__()
        self.setFixedHeight(65)
        self.setAccessibleName("Game Grave")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        canvas_w, canvas_h = self.CANVAS
        left, top, right, bottom = self.CONTENT
        content_w = min(self.width() - 34, 248)
        scale = content_w / (right - left)
        width, height = canvas_w * scale, canvas_h * scale
        x = 27 - left * scale
        y = (self.height() - (bottom - top) * scale) / 2 - top * scale
        dpr = self.devicePixelRatioF()
        pix = brand_scaled("game_grave_logo.png", round(width), round(height), dpr, False)
        if not pix.isNull():
            painter.drawPixmap(QPointF(x, y), pix)


class NavRail(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("navRail")
        self.setFixedWidth(219)

    def paintEvent(self, event):
        super().paintEvent(event)
        # Subtle abstract backdrop in the free space under the menu. It only uses room the menu is not using,
        # so it can never run over a button, and the picture itself fades to transparent at the top.
        menu_bottom = max((child.geometry().bottom() for child in self.findChildren(QAbstractButton)
                           if child.isVisibleTo(self)), default=0)
        free = self.height() - menu_bottom - 14
        source = brand_source("nav_backdrop.png")
        if source.isNull() or free < 90:
            return
        full = self.width() * source.height() / source.width()
        shown = min(full, free)
        width = shown * source.width() / source.height()
        pix = brand_scaled("nav_backdrop.png", round(width), round(shown), self.devicePixelRatioF(), False)
        if pix.isNull():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setOpacity(.9)
        p.drawPixmap(0, round(self.height() - pix.height() / pix.devicePixelRatio()), pix)


class TitleBar(QWidget):
    """Native system drag/maximize, with live window controls in the app chrome."""
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        if getattr(self.window(), "current_route", "") == "Ready Room":
            from gg_desktop.header_banner import paint_slice
            from gg_desktop.ready_room import ReadyRoomBackground
            paint_slice(p, ReadyRoomBackground.ART, QRectF(self.rect()), top_height=self.height(),
                        total_height=self.height() + ReadyRoomBackground.ART_HEIGHT,
                        dpr=self.devicePixelRatioF(), is_top=True)
            return
        source = "old_files" if self.window().current_route == "Old Files" else "games"
        # Decorative ceiling/forest only; original controls start at x=1080.
        draw_crop(p, QRectF(481, 0, 370, 46), source, (700, 0, 370, 46), fill=False)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.window().windowHandle():
            self.window().windowHandle().startSystemMove()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        win = self.window()
        win.showNormal() if win.isMaximized() else win.showMaximized()


# The sidebar icon of each tab. The same symbol marks the tab's page heading, so the menu and the page match.
ROUTE_SYMBOLS = {
    "Overview": "home", "Ready Room": "radio", "Games": "game", "Mods": "mods", "Old Files": "archive",
    "Other Storage": "storage", "Captures": "camera", "Graveyard": "grave", "Game DNA": "dna",
    "Undo Center": "undo", "AI Assistant": "sparkles", "More Tools": "grid", "Settings": "settings",
}


class PageBanner(QWidget):
    def __init__(self, title, subtitle, *, scene="games", symbol=None):
        super().__init__()
        symbol = ROUTE_SYMBOLS.get(title, symbol)
        self.scene = scene
        self.setFixedHeight(96 if scene == "games" else 82)
        layout = row(spacing=12, margins=(8, 5, 8, 3))
        self.setLayout(layout)
        compact = scene in {"graveyard", "dna", "undo"}
        if compact:
            layout.setContentsMargins(8, 0, 8, 0)
        if symbol:
            marker = QLabel()
            marker.setPixmap(icon(symbol, RED, 38).pixmap(38, 38))
            marker.setFixedWidth(38)
            layout.addWidget(marker)
        else:
            slash = label("╱")
            slash.setStyleSheet("font-size:44px;font-weight:900;color:#ff1038;")
            slash.setFixedWidth(25)
            layout.addWidget(slash)
        text = column(spacing=0)
        heading = label(title, "referenceTitle")
        if scene in {"other_storage", "captures", "graveyard", "dna", "undo"}:
            heading.setStyleSheet("font-size:32px;font-weight:750;")
        text.addWidget(heading)
        sub = label(subtitle, "bannerSubtitle", wrap=not compact)
        sub.setMaximumWidth(750 if compact else 445)
        if compact:
            sub.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        text.addWidget(sub)
        layout.addLayout(text, 1)
        layout.addStretch(0 if compact else 1)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        area = QRectF(self.rect())
        # Header artwork only: excludes the reference's search bar and controls.
        scenes = {
            "old_files": ("old_files", (696, 46, 584, 78)),
            "other_storage": ("other_storage", (800, 35, 480, 97)),
            "captures": ("captures", (810, 34, 470, 94)),
            "graveyard": ("graveyard", (900, 31, 380, 85)),
            "dna": ("dna", (930, 29, 350, 83)),
            "undo": ("undo", (915, 28, 365, 83)),
        }
        source, crop = scenes.get(self.scene, ("games", (655, 38, 625, 106)))
        width = crop[2] if self.scene in {"other_storage", "captures", "graveyard", "dna", "undo"} else 660
        draw_crop(p, QRectF(max(0, self.width() - width), 0, width, self.height()), source, crop)
        if self.scene in {"other_storage", "captures", "graveyard", "dna", "undo"}:
            left = max(0, self.width() - width)
            edge = QLinearGradient(left, 0, left + 110, 0)
            edge.setColorAt(0, QColor("#020609"))
            edge.setColorAt(1, QColor(2, 6, 9, 0))
            p.fillRect(QRectF(left, 0, 110, self.height()), edge)
        fade = QLinearGradient(0, 0, self.width(), 0)
        fade.setColorAt(0, QColor("#02070a"))
        fade.setColorAt(.3, QColor(2, 7, 10, 245))
        fade.setColorAt(.58, QColor(2, 7, 10, 80))
        fade.setColorAt(1, QColor(2, 7, 10, 0))
        p.fillRect(area, fade)
        bottom = QLinearGradient(0, 0, 0, self.height())
        bottom.setColorAt(0, QColor(2, 7, 10, 0))
        bottom.setColorAt(.8, QColor(2, 7, 10, 0))
        bottom.setColorAt(1, QColor("#02070a"))
        p.fillRect(area, bottom)


class MetricStrip(QFrame):
    def __init__(self, metrics, *, compact=False):
        super().__init__()
        self.setObjectName("metricStrip")
        self.setFixedHeight(54 if compact else 61)
        layout = row(spacing=0, margins=(4, 5, 4, 5))
        self.setLayout(layout)
        self.values = []
        self.captions = []
        self.cells = []
        for i, metric in enumerate(metrics):
            symbol, value, caption, color, *extra = metric
            cell = QFrame()
            cell.setObjectName("stripCell")
            cell.setMinimumWidth(0)
            cell.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            box = row(spacing=8, margins=(10, 0, 8, 0))
            cell.setLayout(box)
            glyph = QLabel()
            glyph.setPixmap(icon(symbol, color, 29).pixmap(29, 29))
            box.addWidget(glyph)
            words = column(spacing=0)
            val_label = label(str(value), "stripValue")
            caption_label = label(caption, "stripCaption")
            self.values.append(val_label)
            self.captions.append(caption_label)
            words.addWidget(val_label)
            words.addWidget(caption_label)
            box.addLayout(words)
            box.addStretch()
            cell.setToolTip(extra[0] if extra else caption)
            self.cells.append(cell)
            layout.addWidget(cell, 1)
            if i < len(metrics) - 1:
                separator = QFrame()
                separator.setObjectName("metricDivider")
                separator.setFixedSize(1, 32)
                layout.addWidget(separator)

    def set_value(self, index, value, caption=None, tip=None):
        self.values[index].setText(str(value))
        if caption is not None:
            self.captions[index].setText(caption)
        if tip is not None:
            self.cells[index].setToolTip(tip)


class TabStrip(QFrame):
    changed = Signal(str)

    def __init__(self, tabs, *, selected=None, framed=True):
        super().__init__()
        self.setObjectName("tabStrip" if framed else "chipStrip")
        self.buttons = {}
        self.group = QButtonGroup(self)
        layout = row(spacing=6, margins=(4, 4, 4, 4) if framed else (0, 0, 0, 0))
        self.setLayout(layout)
        for text, symbol in tabs:
            control = tool(text, symbol, kind="tabButton" if framed else "filterChip")
            control.setMinimumWidth(0)
            control.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            control.setCheckable(True)
            control.setChecked(text == (selected or tabs[0][0]))
            control.clicked.connect(lambda _=False, text=text: self.changed.emit(text))
            self.group.addButton(control)
            layout.addWidget(control, 1)
            self.buttons[text] = control
        self.setFixedHeight(43 if framed else 32)

    def select(self, name):
        self.buttons[name].setChecked(True)


class DetailPanel(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("detailPanel")
        self.setMinimumWidth(248)
        self.setMaximumWidth(330)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.content = column(spacing=7, margins=(10, 10, 10, 10))
        self.setLayout(self.content)


class InventoryPager(QWidget):
    """Only visible for large tables; selection stays on the displayed page."""
    changed = Signal(int)

    def __init__(self):
        super().__init__()
        self.page = 0
        box = row(spacing=5)
        self.setLayout(box)
        self.previous = button("‹", lambda: self.changed.emit(self.page - 1), tip="Previous findings")
        self.previous.setAccessibleName("Previous findings")
        self.next = button("›", lambda: self.changed.emit(self.page + 1), tip="Next findings")
        self.next.setAccessibleName("Next findings")
        self.caption = label("", "caption")
        self.caption.setMinimumWidth(0)
        self.caption.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        box.addWidget(self.previous)
        box.addWidget(self.caption, 1)
        box.addWidget(self.next)
        self.hide()

    def update_window(self, window):
        self.page = window.page
        self.caption.setText(window.label)
        self.caption.setToolTip(window.label)
        self.previous.setEnabled(window.page > 0)
        self.next.setEnabled(window.page < window.pages - 1)
        self.setVisible(window.pages > 1)


def detail_line(layout, symbol, title, value, *, tone=""):
    item = QWidget()
    box = row(spacing=7)
    item.setLayout(box)
    image = QLabel()
    image.setPixmap(icon(symbol, "#bac3cb", 14).pixmap(14, 14))
    box.addWidget(image)
    key = label(title, "detailKey")
    key.setFixedWidth(82)
    box.addWidget(key)
    text = label(str(value), "detailValue", wrap=True)
    text.setMinimumWidth(0)
    text.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    if tone:
        text.setStyleSheet("color:" + tone + ";")
    text.setToolTip(str(value))
    box.addWidget(text, 1)
    layout.addWidget(item)


def detail_section(layout, text):
    heading = label("⌃  " + text, "detailSection")
    layout.addWidget(heading)


COVERS = (
    (("cyberpunk",), (240, 350, 135, 132)),
    (("baldur",), (390, 350, 132, 132)),
    (("witcher",), (538, 350, 132, 132)),
    (("starfield",), (685, 350, 132, 132)),
    (("skyrim",), (833, 350, 131, 132)),
    (("red dead", "rdr2"), (240, 520, 135, 134)),
    (("call of duty", "black ops"), (390, 520, 132, 134)),
    (("elden ring",), (538, 520, 132, 134)),
    (("helldivers",), (685, 520, 132, 134)),
    (("dragon age",), (833, 520, 131, 134)),
)


def cover_crop(name):
    return next((crop for names, crop in COVERS
                 if any(part in name.casefold() for part in names)), None)


PHOTO_COVERS = {"on": False}  # True only in the design-reference preview, which may borrow crops from the owner's photo
_COVER_CACHE: dict = {}


def _cover_fit(pixmap, width, height, dpr):
    """The picture cover-fitted to this box at real device pixels, so it is never stretched or blurred by Qt."""
    key = (pixmap.cacheKey(), width, height, dpr)
    hit = _COVER_CACHE.get(key)
    if hit is None:
        pw, ph = max(1, round(width * dpr)), max(1, round(height * dpr))
        scaled = pixmap.scaled(pw, ph, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        hit = scaled.copy((scaled.width() - pw) // 2, (scaled.height() - ph) // 2, pw, ph)
        hit.setDevicePixelRatio(dpr)
        if len(_COVER_CACHE) > 400:
            _COVER_CACHE.clear()
        _COVER_CACHE[key] = hit
    return hit


def _monogram(name):
    words = [w for w in "".join(c if c.isalnum() else " " for c in name).split() if w]
    return ("".join(w[0] for w in words[:2]) or "GG").upper()


def draw_cover(painter, area, name, *, wide=False, pixmap=None):
    painter.fillRect(area, QColor("#101b25"))
    dpr = max(1.0, painter.device().devicePixelRatioF())
    if pixmap is not None and not pixmap.isNull():
        fitted = _cover_fit(pixmap, max(1, round(area.width())), max(1, round(area.height())), round(dpr, 2))
        painter.drawPixmap(area.topLeft(), fitted)
        return
    crop = cover_crop(name) if PHOTO_COVERS["on"] else None
    if crop:
        if wide and "cyberpunk" in name.casefold():
            draw_crop(painter, area, "games", (997, 217, 273, 104))
        else:
            draw_crop(painter, area, "games", crop)
    else:
        gradient = QLinearGradient(area.topLeft(), area.bottomRight())
        gradient.setColorAt(0, QColor("#173344"))
        gradient.setColorAt(.6, QColor("#11131d"))
        gradient.setColorAt(1, QColor("#590e23"))
        painter.fillRect(area, gradient)
        painter.save()
        painter.setRenderHint(QPainter.TextAntialiasing)
        font = QFont("Segoe UI")
        font.setBold(True)
        font.setPixelSize(max(10, int(min(area.width(), area.height()) * .34)))
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255, 215))
        painter.drawText(area, Qt.AlignCenter, _monogram(name))
        painter.restore()


@lru_cache(maxsize=128)
def cover_icon(name):
    pix = QPixmap(112 * 3, 64 * 3)
    pix.fill(Qt.transparent)
    pix.setDevicePixelRatio(3)
    p = QPainter(pix)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    draw_cover(p, QRectF(0, 0, 112, 64), name, wide=True)
    p.end()
    return QIcon(pix)


class CoverArt(QWidget):
    def __init__(self, name, *, height=96, artwork=None, app_id=None):
        super().__init__()
        self.name = name
        self.artwork, self.app_id = artwork, app_id
        if artwork is not None:
            artwork.changed.connect(self._artwork_changed)
        self.setFixedHeight(height)
        self.setMinimumWidth(0)
        self.setAccessibleName("Artwork for " + name if app_id or cover_crop(name) else "Game Grave artwork")

    @Slot(str, str)
    def _artwork_changed(self, app_id, kind):
        if app_id in ("", self.app_id):
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 5, 5)
        p.setClipPath(path)
        pixmap = self.artwork.pixmap(self.app_id, "header") if self.artwork and self.app_id else None
        if pixmap is None and self.artwork and self.app_id:
            pixmap = self.artwork.images.get((self.app_id, "cover"))
        draw_cover(p, QRectF(self.rect()), self.name, wide=True, pixmap=pixmap)


CARD_ROLE = int(Qt.UserRole) + 1


class CoverDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.list_mode = False

    def sizeHint(self, option, index):
        return self.parent().gridSize()

    def paint(self, painter, option, index):
        data = index.data(CARD_ROLE) or {}
        name = data.get("name", "Unknown")
        area = QRectF(option.rect).adjusted(3, 3, -3, -3)
        selected = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver)
        painter.save()
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        path = QPainterPath()
        path.addRoundedRect(area, 7, 7)
        painter.setClipPath(path)
        painter.fillRect(area, QColor("#091016"))
        if self.list_mode:
            art = QRectF(area.left(), area.top(), 66, area.height())
        else:
            art = area.adjusted(1, 1, -1, -22)
        service = getattr(self.parent(), "artwork", None)
        pixmap = service.pixmap(data.get("steam_app_id")) if service and data.get("steam_app_id") else None
        draw_cover(painter, art, data.get("art_name", name), pixmap=pixmap)
        if self.list_mode:
            painter.setPen(QColor("#f1f3f6"))
            painter.setFont(pixel_font(13, True))
            painter.drawText(area.adjusted(79, 3, -100, -24), Qt.AlignVCenter,
                             painter.fontMetrics().elidedText(name, Qt.ElideRight, int(area.width() - 180)))
            painter.setPen(QColor("#9baab9"))
            painter.setFont(pixel_font(11))
            painter.drawText(area.adjusted(79, 26, -85, -4), Qt.AlignVCenter, data.get("source", ""))
            painter.drawText(area.adjusted(0, 0, -12, 0), Qt.AlignRight | Qt.AlignVCenter, data.get("size", "Unknown"))
        else:
            fade = QLinearGradient(0, art.top(), 0, area.bottom())
            fade.setColorAt(0, QColor(0, 0, 0, 50))
            fade.setColorAt(.3, QColor(0, 0, 0, 0))
            fade.setColorAt(.65, QColor(0, 0, 0, 0))
            fade.setColorAt(1, QColor(0, 0, 0, 250))
            painter.fillRect(area, fade)
            # Live controls cover the sample reference's baked corner marks.
            painter.fillRect(QRectF(area.left() + 2, area.top() + 2, 28, 24), QColor("#080d13"))
            painter.fillRect(QRectF(area.right() - 25, area.top() + 2, 23, 24), QColor("#080d13"))
            icon("steam" if data.get("source") == "Steam" else "game", "#e2e8ec", 16).paint(
                painter, QRect(int(area.left() + 7), int(area.top() + 5), 17, 17))
            icon("star", "#ffcc1f" if data.get("favorite") else "#d1b757", 17).paint(
                painter, QRect(int(area.right() - 23), int(area.top() + 5), 17, 17))
            if pixmap is not None or not cover_crop(data.get("art_name", name)) or data.get("art_name", name) != name:
                painter.setFont(pixel_font(14, True))
                painter.setPen(QColor("#f5f5f8"))
                painter.drawText(area.adjusted(9, 32, -8, -29), Qt.AlignBottom | Qt.TextWordWrap, name)
            icon(data.get("status_icon", "check"), "#36cc58", 15).paint(
                painter, QRect(int(area.left() + 7), int(area.bottom() - 21), 15, 15))
            painter.setFont(pixel_font(11))
            painter.setPen(QColor("#e0e5eb"))
            painter.drawText(area.adjusted(26, area.height() - 26, -8, -3), Qt.AlignRight | Qt.AlignVCenter, data.get("size", "Unknown"))
        painter.setClipping(False)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(RED if selected else "#52606a" if hovered else "#343d46"), 2 if selected else 1))
        painter.drawRoundedRect(area, 7, 7)
        if option.state & QStyle.State_HasFocus:
            painter.setPen(QPen(QColor("#d4e4ef"), 1, Qt.DotLine))
            painter.drawRoundedRect(area.adjusted(3, 3, -3, -3), 5, 5)
        painter.restore()


def pixel_font(size, bold=False):
    font = QFont("Segoe UI")
    font.setPixelSize(size)
    font.setBold(bold)
    return font


class CoverGrid(QListWidget):
    def selectRow(self, index):
        self.setCurrentRow(index)

    """Virtualized adaptive cover list; the complete filtered inventory is reachable."""
    favoriteRequested = Signal(int)

    def __init__(self):
        super().__init__()
        self.setObjectName("coverGrid")
        self.setFrameShape(QFrame.NoFrame)
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Static)
        self.setWrapping(True)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setMouseTracking(True)
        self.delegate = CoverDelegate(self)
        self.setItemDelegate(self.delegate)
        self.set_mode("grid")
        self.setMinimumSize(180, 180)

    def set_artwork(self, artwork):
        self.artwork = artwork
        artwork.changed.connect(self._artwork_changed)

    @Slot(str, str)
    def _artwork_changed(self, app_id, kind):
        self.viewport().update()

    def set_mode(self, mode):
        self.delegate.list_mode = mode == "list"
        self.setViewMode(QListWidget.ListMode if mode == "list" else QListWidget.IconMode)
        self.setWrapping(mode != "list")
        self._fit()
        self.viewport().update()

    def _fit(self):
        width = max(120, self.viewport().width() - 2)
        if self.delegate.list_mode:
            self.setGridSize(QSize(width, 64))
        else:
            columns = max(1, width // 140)
            cell = width // columns
            self.setGridSize(QSize(cell, min(205, int(cell * 1.16))))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()

    def mouseReleaseEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        if item and event.button() == Qt.LeftButton and not self.delegate.list_mode:
            rect = self.visualItemRect(item)
            if event.position().x() > rect.right() - 31 and event.position().y() < rect.top() + 31:
                self.setCurrentItem(item)
                self.favoriteRequested.emit(self.row(item))
                event.accept()
                return
        super().mouseReleaseEvent(event)
