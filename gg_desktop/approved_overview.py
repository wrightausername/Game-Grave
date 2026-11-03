"""Owner-locked Overview composition. All displayed values originate from local data.

The design reference is the November 2 cinematic Overview PNG. This module
uses Qt widgets, never a static screenshot. It does not scan or delete files.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import math

from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import QColor, QImageReader, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QScrollArea, QVBoxLayout, QWidget,
)

from core import human_size, get_activity, friendly_activity
from recovery import get_records
from gg_desktop.widgets import HeroBanner, button, label


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
    col = _stack(shell, margin=(8, 6, 15, 8), gap=6)
    heading = QWidget()
    headings = _line(heading, gap=8)
    related = ("Undo Center" if "RECYCLE" in title or "ACTIVITY" in title
               else "Games" if "LIBRARY" in title else "Graveyard")
    glyph = QLabel()
    glyph.setPixmap(nav_icon(related).pixmap(26, 26))
    glyph.setFixedSize(28, 28)
    headings.addWidget(glyph)
    headings.addWidget(_txt(title.title(), size=20, color="#F6F7FB", bold=True), 1)
    col.addWidget(heading)
    if subtitle:
        caption = _txt(subtitle, size=11, color="#ADB8C8", wrap=True)
        col.addWidget(caption)
    return shell, col


def _compact_action(text, handler, *, secondary=""):
    if secondary:
        action = QPushButton(str(text) + "\n" + str(secondary))
        action.setMinimumHeight(48)
        action.setToolTip(str(secondary))
        action.setProperty("multiLine", True)
    else:
        action = QPushButton(str(text) + "   ›")
        action.setMinimumHeight(34)
    action.setObjectName("approvedAction")
    action.setAccessibleName(str(text))
    action.clicked.connect(handler)
    return action


class RecycledRing(QWidget):
    """Ring depicts logged Recycle Bin moves, NOT storage actually reclaimed."""
    def __init__(self, amount: int, parent=None):
        super().__init__(parent)
        self.amount = max(0, amount)
        self.setMinimumSize(126, 126)
        self.setMaximumSize(175, 175)
        self.setToolTip(
            "Bytes moved through Game Grave's logged Recycle Bin actions. "
            "This is not confirmed free space and may include restored items.")

    def paintEvent(self, _event):
        paint = QPainter(self)
        paint.setRenderHint(QPainter.Antialiasing)
        length = min(self.width(), self.height()) - 10
        rect = QRectF((self.width()-length)/2, (self.height()-length)/2,
                      length, length)
        stroke = max(11, length*.095)
        paint.setPen(QPen(QColor("#27313E"), stroke, Qt.SolidLine, Qt.RoundCap))
        paint.drawArc(rect.adjusted(stroke/2, stroke/2, -stroke/2, -stroke/2),
                      0, 360*16)
        # A nonzero amount produces a complete accent rather than a fake %
        # progress against an unmeasured disk-reclamation target.
        if self.amount:
            paint.setPen(QPen(QColor(STORAGE_RED), stroke, Qt.SolidLine, Qt.RoundCap))
            paint.drawArc(rect.adjusted(stroke/2, stroke/2, -stroke/2, -stroke/2),
                          90*16, -285*16)
        paint.setPen(QColor("#FFFFFF"))
        from PySide6.QtGui import QFont
        font = QFont("Segoe UI", 15)
        font.setBold(True)
        paint.setFont(font)
        paint.drawText(rect, Qt.AlignCenter, human_size(self.amount))
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
    tile.setMinimumHeight(82)
    tile.setMaximumHeight(93)
    tile.setObjectName("approvedMetric")
    tile.setAccessibleName(label_text + ": " + str(value) + ". " + description)
    tile.setToolTip(description)
    tile.setStyleSheet(
        "QPushButton#approvedMetric{background:transparent;border:0;"
        "border-bottom:2px solid " + accent + ";border-radius:0;"
        "text-align:left;padding:5px;}"
        "QPushButton#approvedMetric:hover{background:#18202B;}")
    frame = _line(tile, margin=(6, 7, 6, 7), gap=12)
    glyph = QLabel()
    glyph.setFixedSize(37, 37)
    glyph.setPixmap(nav_icon(route).pixmap(35,35))
    frame.addWidget(glyph)
    details = QWidget()
    col = _stack(details, gap=1)
    col.addWidget(_txt(label_text.upper(), size=11, color="#CAD2DB", bold=True))
    col.addWidget(_txt(value, size=23, color=accent, bold=True))
    frame.addWidget(details, 1)
    tile.clicked.connect(lambda _checked=False: handler(route))
    return tile


def _cover(game, open_game):
    """Verified local artwork or clearly identified generated placeholder."""
    holder = QPushButton()
    holder.setObjectName("approvedCover")
    holder.setMinimumWidth(132)
    holder.setMaximumWidth(165)
    holder.setFixedHeight(184)
    holder.setToolTip(game.name + "\n" + game.launcher
                      + "\nCover from local cache if available")
    holder.setAccessibleName("Inspect " + game.name)
    outer = _stack(holder, margin=(5, 5, 5, 6), gap=4)
    art = QLabel()
    art.setAlignment(Qt.AlignCenter)
    art.setFixedHeight(129)
    art.setMinimumWidth(118)
    from gg_desktop.local_art import game_cover_path
    source = game_cover_path(game)
    pixmap = None
    if source:
        reader = QImageReader(source)
        reader.setAutoTransform(True)
        geometry = reader.size()
        if (geometry.isValid() and 0 < geometry.width() <= 8192
                and 0 < geometry.height() <= 8192
                and geometry.width()*geometry.height() <= 32_000_000):
            reader.setScaledSize(QSize(240, 135))
            image = reader.read()
            if not image.isNull():
                pixmap = QPixmap.fromImage(image).scaled(
                    148, 129, Qt.KeepAspectRatioByExpanding,
                    Qt.SmoothTransformation)
    if pixmap is None:
        from gg_desktop.poster_art import generated_game_poster
        pixmap = generated_game_poster(game.name, 148, 129)
        art.setToolTip("Original Game Grave placeholder, not official box art")
    else:
        art.setToolTip("Locally verified artwork for " + game.name)
    art.setPixmap(pixmap)
    outer.addWidget(art)
    title = _txt(game.name, size=12, color="#EDF1F7", bold=True)
    title.setMaximumHeight(33)
    title.setWordWrap(True)
    outer.addWidget(title)
    holder.clicked.connect(lambda _=False: open_game(game))
    return holder


def render_approved_overview(window):
    """Construct the approved Overview without fabricated game or disk data."""
    page = window.page_for("Overview")
    page.content.setSpacing(9)
    page.content.setContentsMargins(12, 7, 12, 16)

    hero = HeroBanner(title="Overview",
                      subtitle="Your games. All their baggage. Under control.",
                      detail="")
    hero.setMinimumHeight(181)
    hero.setMaximumHeight(181)
    hero.setAccessibleName(
        "Overview. Your games. All their baggage. Under control.")
    page.content.addWidget(hero)

    found = bool(window.inventory.scanned_at)
    games = window.inventory.games
    mods = window.inventory.mods
    files = window.inventory.files
    captures = len(window.inventory.screenshots) + len(window.inventory.recordings)
    metrics = QWidget()
    metrics.setMinimumHeight(91)
    metrics.setObjectName("approvedMetrics")
    mrow = _line(metrics, gap=8)
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
    for text, val, route, description, accent in values:
        mrow.addWidget(_metric(text, val, accent, route, window.navigate,
                               description), 1)
    page.content.addWidget(metrics)

    recycled, move_count, recent = _monthly_moves()
    center = QWidget()
    c = _line(center, gap=10)

    activity_panel, activity = _panel("RECENT ACTIVITY",
        subtitle="Verified local events only. No simulated gaming history.")
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
    c.addWidget(activity_panel, 4)

    recycled_panel, rc = _panel("RECYCLE BIN ACTIVITY",
        subtitle="Logged moves, not confirmed disk space reclaimed")
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
    rc.addWidget(_compact_action("Open Undo Center",
                lambda: window.navigate("Undo Center")))
    c.addWidget(recycled_panel, 4)

    quick_panel, quick = _panel("QUICK ACTIONS",
                               subtitle="Every action opens a real workflow")
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
    c.addWidget(quick_panel, 3)
    page.content.addWidget(center)

    library, libcol = _panel("YOUR LIBRARY",
        subtitle="Verified installations across launchers. Covers use local art where available.")
    heads = QWidget()
    h = _line(heads, gap=9)
    h.addWidget(_txt("Installed games", color="#BBC9D6", size=11), 1)
    h.addWidget(_compact_action("View all games", lambda: window.navigate("Games")))
    libcol.addWidget(heads)
    if found and games:
        shelf = QScrollArea()
        shelf.setObjectName("approvedLibraryScroll")
        shelf.setFrameShape(QFrame.NoFrame)
        shelf.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        shelf.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        shelf.setWidgetResizable(True)
        shelf.setMinimumHeight(207)
        row_widget = QWidget()
        row = _line(row_widget, gap=9)
        row.setAlignment(Qt.AlignLeft)
        def inspect(game):
            window._pending_game_query = game.name
            window.navigate("Games")
        for game in games[:16]:
            row.addWidget(_cover(game, inspect))
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
