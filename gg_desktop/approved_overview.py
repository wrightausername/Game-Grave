"""Owner-locked Overview composition. All displayed values originate from local data.

The design reference is the November 2 cinematic Overview PNG. This module
uses Qt widgets, never a static screenshot. It does not scan or delete files.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import math

from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import QColor, QImageReader, QPainter, QPen, QPixmap, QFont, QLinearGradient, QPainterPath
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QScrollArea, QVBoxLayout, QGridLayout, QWidget,
)

from core import human_size, get_activity, friendly_activity
from recovery import get_records
from gg_desktop.widgets import HeroBanner, button, label
from gg_desktop.responsive import ResponsiveGrid, ResponsiveRow
from gg_desktop.reference_icons import metric_icon


COLORS = ("#49CBED", "#BB97EF", "#F6AD63", "#73DCC7", "#A995F0")
STORAGE_RED = "#F04C62"


def _line(parent, *, margin=(0, 0, 0, 0), gap=10):
    layout = QHBoxLayout(parent)
    layout.setContentsMargins(*margin)
    layout.setSpacing(gap)
    return layout


def _stack(parent, *, margin=(0, 0, 0, 0), gap=8):
    layout = QVBoxLayout(parent)
    layout.setContentsMargins(*margin)
    layout.setSpacing(gap)
    return layout


def _txt(text, role=None, *, size=None, color=None, bold=False, wrap=False):
    widget = QLabel(str(text))
    if role:
        widget.setObjectName(role)
    if size or color or bold:
        widget.setStyleSheet(
            "background:transparent;"
            + (f"font-size:{size}px;" if size else "")
            + (f"color:{color};" if color else "")
            + ("font-weight:800;" if bold else ""))
    widget.setWordWrap(wrap)
    widget.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return widget


def _panel(title, *, subtitle=None):
    from gg_desktop.visuals import nav_icon
    shell = QFrame()
    shell.setObjectName("approvedOverviewPanel")
    col = _stack(shell, margin=(10, 8, 13, 8), gap=6)
    heading = QWidget()
    headings = _line(heading, gap=8)
    related = ("Undo Center" if "RECYCLE" in title or "ACTIVITY" in title
               else "Games" if "LIBRARY" in title else "Graveyard")
    glyph = QLabel()
    glyph.setPixmap(nav_icon(related).pixmap(26, 26))
    glyph.setFixedSize(28, 28)
    headings.addWidget(glyph)
    headings.addWidget(_txt(title.title(), size=17, color="#F6F7FB", bold=True), 1)
    col.addWidget(heading)
    if subtitle:
        caption = _txt(subtitle, size=11, color="#ADB8C8", wrap=True)
        col.addWidget(caption)
    return shell, col


def _compact_action(text, handler, *, secondary=""):
    from gg_desktop.visuals import nav_icon
    if secondary:
        action = QPushButton()
        action.setObjectName("approvedActivity")
        action.setStyleSheet("QPushButton#approvedActivity{min-height:28px;max-height:28px;"
            "padding:4px;border:0;border-bottom:1px solid #29333D;"
            "border-radius:0;background:transparent;text-align:left;}"
            "QPushButton#approvedActivity:hover{background:#201B28;}")
        line = _line(action, margin=(5, 2, 5, 2), gap=8)
        glyph = QLabel()
        glyph.setFixedSize(25,25)
        glyph.setPixmap(nav_icon("Mods" if "mod" in text.casefold() else
            "Undo Center" if "recycl" in text.casefold() or "restor" in text.casefold()
            else "Games").pixmap(23,23))
        line.addWidget(glyph)
        copy = QWidget()
        words = _stack(copy, gap=0)
        words.addWidget(_txt(text, size=11, color="#E7EDF5", bold=True))
        stamp, _, state = str(secondary).partition("|")
        words.addWidget(_txt(stamp.strip(), size=9, color="#8F9CAA"))
        line.addWidget(copy,1)
        if state:
            chip = _txt(state.strip(), size=9, color="#7BD5AD")
            chip.setStyleSheet("color:#7BD5AD;background:#152C27;"
                              "border:1px solid #295242;border-radius:3px;padding:2px 5px;font-size:9px;")
            line.addWidget(chip)
        for child in action.findChildren(QWidget):
            child.setAttribute(Qt.WA_TransparentForMouseEvents)
        action.setToolTip(str(secondary))
        action.setAccessibleName(str(text))
        action.clicked.connect(handler)
        return action
    else:
        action = QPushButton(str(text) + "   ›")
        action.setMinimumHeight(29)
    action.setObjectName("approvedAction")
    route = {"Scan Library": "Games", "Find Unused Mods": "Mods",
             "Review Old Files": "Old Files", "Open Graveyard": "Graveyard",
             "Manage Captures": "Captures", "Undo Center": "Undo Center",
             "Review Cleanup": "Graveyard", "Review history": "Undo Center"}.get(text)
    if route:
        action.setIcon(nav_icon(route))
        action.setIconSize(QSize(18, 18))
    action.setAccessibleName(str(text))
    action.clicked.connect(handler)
    return action


class RecycledRing(QWidget):
    """Ring depicts logged Recycle Bin moves, NOT storage actually reclaimed."""
    def __init__(self, amount: int, parent=None):
        super().__init__(parent)
        self.amount = max(0, amount)
        self.setMinimumSize(164, 164)
        self.setMaximumSize(188, 188)
        self.setToolTip(
            "Bytes moved through Game Grave's logged Recycle Bin actions. "
            "This is not confirmed free space and may include restored items.")

    def paintEvent(self, _event):
        paint = QPainter(self)
        paint.setRenderHint(QPainter.Antialiasing)
        length = min(self.width(), self.height()) - 10
        rect = QRectF((self.width()-length)/2, (self.height()-length)/2,
                      length, length)
        stroke = max(15, length*.13)
        paint.setPen(QPen(QColor("#321D29"), stroke + 9, Qt.SolidLine, Qt.RoundCap))
        paint.drawArc(rect.adjusted(stroke/2, stroke/2, -stroke/2, -stroke/2),
                      0, 360*16)
        # Full decorative halo, not an invented progress percentage.
        paint.setPen(QPen(QColor(STORAGE_RED), stroke, Qt.SolidLine, Qt.RoundCap))
        paint.drawArc(rect.adjusted(stroke/2, stroke/2, -stroke/2, -stroke/2),
                      0, 360*16)
        paint.setPen(QPen(QColor("#FE8394"), 1.2))
        paint.drawEllipse(rect.adjusted(stroke, stroke, -stroke, -stroke))
        paint.setPen(QColor("#FFFFFF"))
        from PySide6.QtGui import QFont
        font = QFont("Segoe UI", 15)
        font.setBold(True)
        paint.setFont(font)
        paint.drawText(rect.adjusted(0, -10, 0, 0), Qt.AlignCenter, human_size(self.amount))
        font.setPixelSize(10)
        font.setBold(False)
        paint.setFont(font)
        paint.setPen(QColor("#BAA6B5"))
        paint.drawText(rect.adjusted(0, 34, 0, 0), Qt.AlignCenter, "LOGGED MOVES")
        paint.end()


def _monthly_moves():
    now = datetime.now().astimezone()
    amount, count = 0, 0
    recent = []
    for record in reversed(get_records()):
        if not isinstance(record, dict):
            continue
        try:
            when = datetime.fromisoformat(str(record["time"]))
            size = record["size"]
            if type(size) is not int or size < 0:
                continue
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if when.year == now.year and when.month == now.month:
            amount += size
            count += 1
        if len(recent) < 6:
            recent.append(record)
    return amount, count, recent


def _metric(label_text, value, accent, route, handler, description):
    from gg_desktop.visuals import nav_icon
    tile = QPushButton()
    tile.setMinimumHeight(70)
    tile.setMaximumHeight(76)
    tile.setObjectName("approvedMetric")
    tile.setAccessibleName(label_text + ": " + str(value) + ". " + description)
    tile.setToolTip(description)
    tile.setStyleSheet(
        "QPushButton#approvedMetric{background:transparent;border:0;"
        "border-bottom:1px solid " + accent + ";border-radius:0;"
        "text-align:left;padding:4px;min-height:62px;max-height:62px;}"
        "QPushButton#approvedMetric:hover{background:#18202B;}")
    frame = _line(tile, margin=(6, 7, 6, 7), gap=12)
    glyph = QLabel()
    glyph.setFixedSize(37, 37)
    glyph.setPixmap(metric_icon(route, accent, 35))
    frame.addWidget(glyph)
    details = QWidget()
    col = _stack(details, gap=1)
    col.addWidget(_txt(label_text.upper(), size=11, color="#CAD2DB", bold=True))
    col.addWidget(_txt(value, size=25, color=accent, bold=True))
    frame.addWidget(details, 1)
    for child in tile.findChildren(QWidget):
        child.setAttribute(Qt.WA_TransparentForMouseEvents)
    tile.clicked.connect(lambda _checked=False: handler(route))
    return tile


class LibraryCover(QPushButton):
    """Edge-to-edge local poster; native focus/selection, no screenshot controls."""
    def __init__(self, game, pixmap, open_game, official):
        super().__init__()
        self.game = game
        self.art = pixmap
        self.has_cover = official
        self.setObjectName("approvedCover")
        self.setMinimumWidth(150)
        self.setMaximumWidth(228)
        self.setFixedHeight(206)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAccessibleName("Inspect " + game.name)
        self.setToolTip(game.name + " • " + game.launcher +
                        ("\nLocally verified game artwork" if official else
                         "\nCover not loaded. Use Get Steam Covers or set your own cover in Games."))
        self.clicked.connect(lambda: open_game(game))

    def sizeHint(self):
        return QSize(190, 206)

    def minimumSizeHint(self):
        return QSize(150, 206)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        bounds = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        clip = QPainterPath()
        clip.addRoundedRect(bounds, 5, 5)
        painter.setClipPath(clip)
        painter.fillRect(bounds, QColor("#0A1119"))
        if not self.has_cover:
            painter.setPen(QColor("#D4DAE2"))
            font = QFont("Segoe UI")
            font.setPixelSize(14)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(bounds.adjusted(12, 25, -12, -45),
                             Qt.AlignCenter | Qt.TextWordWrap, self.game.name)
            font.setPixelSize(10)
            font.setBold(False)
            painter.setFont(font)
            painter.setPen(QColor("#82909F"))
            painter.drawText(QRectF(bounds.left()+8, bounds.bottom()-33, bounds.width()-16, 22),
                             Qt.AlignCenter, "Cover not loaded")
        elif not self.art.isNull():
            scale = max(bounds.width()/self.art.width(), bounds.height()/self.art.height())
            sw, sh = bounds.width()/scale, bounds.height()/scale
            painter.drawPixmap(bounds, self.art, QRectF(
                (self.art.width()-sw)/2, (self.art.height()-sh)/2, sw, sh))
        painter.setClipping(False)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor("#ED3F59" if self.underMouse() or self.hasFocus()
                                  else "#36414E"), 2 if self.hasFocus() else 1))
        painter.drawRoundedRect(bounds, 5, 5)


def _cover(game, open_game):
    """Verified local artwork or an honest missing-cover state."""
    from gg_desktop.local_art import game_cover_path, game_banner_path
    source = game_cover_path(game) or game_banner_path(game)
    pixmap = None
    if source:
        reader = QImageReader(source)
        reader.setAutoTransform(True)
        geometry = reader.size()
        if (geometry.isValid() and 0 < geometry.width() <= 8192
                and 0 < geometry.height() <= 8192
                and geometry.width()*geometry.height() <= 32_000_000):
            # Preserve portrait aspect ratio before cropping to the
            # wide cinematic tile. Decoding directly to a landscape size
            # previously stretched publisher artwork out of proportion.
            scale = max(456 / geometry.width(), 412 / geometry.height())
            if scale < 1.0:
                reader.setScaledSize(QSize(
                    max(1, round(geometry.width() * scale)),
                    max(1, round(geometry.height() * scale))))
            image = reader.read()
            if not image.isNull():
                pixmap = QPixmap.fromImage(image)
    official = pixmap is not None
    if pixmap is None:
        from gg_desktop.poster_art import missing_artwork
        pixmap = missing_artwork(game.name, 200, 240)
    return LibraryCover(game, pixmap, open_game, official)


def render_approved_overview(window):
    """Construct the approved Overview without fabricated game or disk data."""
    page = window.page_for("Overview")
    page.content.setSpacing(9)
    page.content.setContentsMargins(12, 7, 12, 16)

    hero = HeroBanner(title="Overview",
                      subtitle="Your games. All their baggage. Under control.",
                      detail="")
    hero.setMinimumHeight(148)
    hero.setMaximumHeight(148)
    hero.setAccessibleName(
        "Overview. Your games. All their baggage. Under control.")
    page.content.addWidget(hero)

    found = bool(window.inventory.scanned_at)
    games = window.inventory.games
    mods = window.inventory.mods
    files = window.inventory.files
    captures = len(window.inventory.screenshots) + len(window.inventory.recordings)
    metrics = ResponsiveGrid(columns=((0, 1), (430, 2), (970, 5)))
    metrics.setObjectName("approvedMetrics")
    values = (
        ("Games", str(len(games)) if found else "Not scanned", "Games",
         "Verified installed game records", COLORS[0]),
        ("Mods", str(len(mods)) if found else "Not scanned", "Mods",
         "Detected mod locations, not an individual mod count", COLORS[1]),
        ("Old Files", human_size(sum(max(0, f.size) for f in files)) if found
         else "Not scanned", "Old Files",
         "Apparent bytes from scoped Old Files scan", COLORS[2]),
        ("Other Storage", "Explore", "Other Storage",
         "Analyze other storage explicitly; not inferred from free space", COLORS[3]),
        ("Captures", str(captures) if found else "Not scanned", "Captures",
         "Screenshots and video records from latest scan", COLORS[4]),
    )
    for index, (text, val, route, description, accent) in enumerate(values):
        tile = _metric(text, val, accent, route, window.navigate, description)
        metrics.addWidget(tile)
    page.content.addWidget(metrics)

    recycled, move_count, recent = _monthly_moves()
    center = ResponsiveRow(breakpoint=1000, horizontal_height=302)
    c = center

    activity_panel, activity = _panel("RECENT ACTIVITY")
    # Scans count as real activity even when no files were removed. Existing
    # audit entries are presented before the separate Recycle Bin ledger.
    events = get_activity(limit=6)
    if events:
        for event in events[:5]:
            item = friendly_activity(event)
            kind = str(item.get("kind", "")).casefold()
            route = ("Undo Center" if "recycl" in kind or "restor" in kind
                     else "Mods" if "mod" in kind
                     else "Graveyard" if "cleanup" in kind
                     else "Games")
            action = _compact_action(
                str(item["title"]), lambda _checked=False, r=route: window.navigate(r),
                secondary=str(item["date"]) + " | " + str(item["status"]))
            action.setToolTip(str(item["explanation"]))
            activity.addWidget(action)
    elif recent:
        for record in recent[:5]:
            name = Path(str(record.get("path", ""))).name or "Recorded operation"
            value = human_size(record.get("size", 0))
            when = str(record.get("time", "Unknown"))[:16]
            activity.addWidget(_compact_action(
                name, lambda: window.navigate("Undo Center"),
                secondary=when + " | " + value))
    else:
        activity.addWidget(_txt(
            "No recorded Game Grave activity yet. Scanning does not delete "
            "or recycle anything.", color="#AEB8C6", size=11, wrap=True))
    activity.addStretch()
    activity.addWidget(_compact_action("Review history",
                        lambda: window.navigate("Undo Center")))
    c.addWidget(activity_panel, 5)

    recycled_panel, rc = _panel("SPACE RECLAIMED")
    ring_row = QWidget()
    rr = _line(ring_row, gap=10)
    ring = RecycledRing(recycled)
    rr.addWidget(ring)
    details = QWidget()
    dc = _stack(details, gap=5)
    dc.addWidget(_txt(human_size(recycled), size=18, color="#FFFFFF", bold=True))
    dc.addWidget(_txt("Moved this month", size=11, color="#B7C2CF"))
    dc.addWidget(_txt(str(move_count) + " recorded operations",
                      size=11, color="#D5A3AE"))
    dc.addStretch()
    rr.addWidget(details, 1)
    rc.addWidget(ring_row, 1)
    if found:
        rc.addWidget(_txt(
            str(len(window.inventory.graveyard)) +
            " Graveyard candidate(s) await separate manual review. "
            "No unconfirmed freed space is counted.",
            color="#A7D2D1", size=11, wrap=True))
    action = _compact_action("Review Cleanup",
                             lambda: window.navigate("Graveyard"))
    action.setObjectName("approvedCleanupCTA")
    rc.addWidget(action)
    c.addWidget(recycled_panel, 4)

    quick_panel, quick = _panel("QUICK ACTIONS")
    for name, callback in (
        ("Scan Library", window.start_scan),
        ("Find Unused Mods", lambda: window.navigate("Mods")),
        ("Review Old Files", lambda: window.navigate("Old Files")),
        ("Open Graveyard", lambda: window.navigate("Graveyard")),
        ("Manage Captures", lambda: window.navigate("Captures")),
        ("Undo Center", lambda: window.navigate("Undo Center")),
    ):
        quick.addWidget(_compact_action(name, callback))
    quick.addStretch()
    c.addWidget(quick_panel, 5)
    page.content.addWidget(center)

    library, libcol = _panel("YOUR LIBRARY")
    # Keep the section title and shelf controls on one aligned header row.
    # A separate full-width action row left a large blank band above covers.
    heads = libcol.itemAt(0).widget()
    h = heads.layout()
    h.addStretch(1)
    def add_library():
        window._settings_category_index = 1
        window.navigate("Settings")
    if any(str(game.launcher).casefold() == "steam" for game in games):
        h.addWidget(_compact_action("Get Steam Covers", window._download_game_covers))
    h.addWidget(_compact_action("Add library", add_library))
    h.addWidget(_compact_action("View all games", lambda: window.navigate("Games")))
    if found and games:
        shelf = QScrollArea()
        shelf.setObjectName("approvedLibraryScroll")
        shelf.setFrameShape(QFrame.NoFrame)
        shelf.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        shelf.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        shelf.setWidgetResizable(True)
        shelf.setMinimumHeight(222)
        row_widget = QWidget()
        row = _line(row_widget, gap=9)
        row.setAlignment(Qt.AlignLeft)
        def inspect(game):
            window._pending_game_query = game.name
            window.navigate("Games")
        for game in games[:16]:
            row.addWidget(_cover(game, inspect), 1)
        row.addStretch()
        shelf.setWidget(row_widget)
        libcol.addWidget(shelf)
    else:
        libcol.addWidget(_txt(
            "Your verified game library will appear here after a scan."
            if not found else "No verified games found in the last scan.",
            color="#AEB8C6", wrap=True))
        libcol.addWidget(button("Scan PC now", window.start_scan, kind="primary"))
    page.content.addWidget(library)
    if window.inventory.warnings:
        page.content.addWidget(_txt(
            "Scan coverage incomplete: " + " ".join(
                str(w) for w in window.inventory.warnings[:3]),
            color="#E7B57B", size=11, wrap=True))
    return page
