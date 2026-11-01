"""Functional visual panels composed from real inventory records only.

Nothing in this module scans or deletes files. Content is labelled as reported
or estimated when appropriate. Each tab reuses the global shell but receives
distinct graphic information to aid visual learners.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from core import human_size


def _layout(widget, *, vertical=True, pad=(13, 12, 13, 12), gap=7):
    layout = QVBoxLayout(widget) if vertical else QHBoxLayout(widget)
    layout.setContentsMargins(*pad)
    layout.setSpacing(gap)
    return layout


def _small(text, role="caption"):
    label = QLabel(str(text))
    label.setObjectName(role)
    label.setWordWrap(True)
    return label


class GraphicCard(QFrame):
    """Native high-DPI graphic with bounded, genuine user inventory metadata."""

    def __init__(self, label: str, value: str, description: str, *,
                 pictogram="▣", color="#43D6F2"):
        super().__init__()
        self.setObjectName("graphicCard")
        self.setMinimumWidth(145)
        self.color = QColor(color)
        layout = _layout(self, gap=4)
        mark = QLabel(pictogram)
        mark.setObjectName("graphicMark")
        mark.setStyleSheet(f"color:{color};font-size:27px;")
        layout.addWidget(mark)
        heading = _small(label, "findingTitle")
        layout.addWidget(heading)
        metric = _small(value, "graphicValue")
        layout.addWidget(metric)
        layout.addWidget(_small(description))
        layout.addStretch(1)


class GameCover(QPushButton):
    """Local vector cover treatment, NOT an external fictional cover image.

    The launcher, title and size are bound to scan data. Clicking selects the
    game record in the real Games list.
    """
    def __init__(self, game, on_selected):
        super().__init__()
        self.game = game
        self.setMinimumWidth(170)
        self.setMaximumWidth(185)
        self.setMinimumHeight(188)
        self.setObjectName("gameCover")
        self.setToolTip(f"{game.name}\n{game.launcher}\n{game.install_path}")
        self.setAccessibleName("Select game: " + game.name)
        self.clicked.connect(on_selected)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        shades = [
            ("#122D3B", "#1B576A"), ("#1C2B3E", "#3A6880"),
            ("#263044", "#80525A"), ("#142D38", "#2D6B6D"),
        ]
        idx = sum(ord(c) for c in self.game.name) % len(shades)
        gradient = QLinearGradient(0, 0, w, h)
        gradient.setColorAt(0, QColor(shades[idx][0]))
        gradient.setColorAt(1, QColor("#0B121C"))
        p.setPen(QPen(QColor("#365363"), 1))
        p.setBrush(gradient)
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 9, 9)
        p.setPen(QPen(QColor(shades[idx][1]), 2))
        for k in range(4):
            p.drawArc(23+k*6, 14+k*4, 128-k*12, 118-k*9, 10*16, 128*16)
        p.setPen(QPen(QColor("#55D2E9"), 3))
        p.drawLine(23, 100, w-23, 100)
        first_letters = "".join(x[0] for x in self.game.name.split()[:2]).upper()[:2]
        p.setPen(QColor("#EAF6FD"))
        p.setFont(QFont("Segoe UI", 29, QFont.Bold))
        p.drawText(20, 19, w-40, 79, Qt.AlignCenter, first_letters)
        p.setPen(QColor("#DDEBF6"))
        p.setFont(QFont("Segoe UI", 10, QFont.DemiBold))
        title = self.game.name
        fm = p.fontMetrics()
        title = fm.elidedText(title, Qt.ElideRight, w-24)
        p.drawText(12, 123, w-24, 21, Qt.AlignLeft, title)
        p.setPen(QColor("#9DCDDF"))
        p.setFont(QFont("Segoe UI", 9))
        p.drawText(12, 143, w-24, 18,
                   Qt.AlignLeft, fm.elidedText(self.game.launcher, Qt.ElideRight, w-24))
        size = human_size(self.game.size_bytes) if self.game.size_bytes is not None else "Size unknown"
        p.drawText(12, 164, w-24, 18, Qt.AlignLeft, size)
        if self.underMouse():
            p.setPen(QPen(QColor("#43D6F2"), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(self.rect().adjusted(2, 2, -3, -3), 9, 9)
        p.end()


def game_gallery(games, selected_callback, *, limit=7):
    """Horizontal browse row that maps directly to existing game records."""
    section = QFrame()
    section.setObjectName("dashboardPanel")
    layout = _layout(section)
    layout.addWidget(_small("YOUR GAME LIBRARY  •  VERIFIED INSTALLATIONS", "sectionTitle"))
    layout.addWidget(_small(
        "Select a game card to inspect its installation evidence and actions below. "
        "Cards use local vector artwork, not unverified cover images."))
    if not games:
        layout.addWidget(_small("No verified games yet. Run Scan PC to populate the shelf."))
        return section
    scroller = QScrollArea()
    scroller.setWidgetResizable(True)
    scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    scroller.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroller.setMinimumHeight(218)
    scroller.setMaximumHeight(228)
    area = QWidget()
    row = _layout(area, vertical=False, pad=(1, 3, 1, 3), gap=11)
    for game in games[:limit]:
        row.addWidget(GameCover(game, lambda _=False, g=game: selected_callback(g)))
    row.addStretch(1)
    scroller.setWidget(area)
    layout.addWidget(scroller)
    return section


def mod_radar_panel(mods):
    """Mod-specific, source-linked graphic. Does not infer unused mods."""
    by_source = Counter(str(getattr(m, "source", "Unknown")) for m in mods)
    panel = QFrame()
    panel.setObjectName("dashboardPanel")
    row = _layout(panel, vertical=False, gap=13)
    summary = QFrame()
    summary.setObjectName("radarFocus")
    col = _layout(summary)
    col.addWidget(_small("MOD RADAR", "sceneKicker"))
    number = _small(str(len(mods)), "metricValue")
    col.addWidget(number)
    col.addWidget(_small("Known storage locations"))
    col.addWidget(_small("Protected by default. A match is not proof a mod is unused."))
    col.addStretch()
    row.addWidget(summary, 1)
    sources = QWidget()
    source_col = _layout(sources, gap=7)
    source_col.addWidget(_small("DISCOVERED SOURCES", "sectionTitle"))
    if not by_source:
        source_col.addWidget(_small("No mod sources found. Nothing will be cleaned automatically."))
    for title, amount in by_source.most_common(5):
        box = QWidget()
        line = _layout(box, vertical=False, pad=(0, 0, 0, 0), gap=8)
        text = _small(title)
        text.setMaximumWidth(265)
        line.addWidget(text, 1)
        bar = QProgressBar()
        bar.setRange(0, len(mods) if mods else 1)
        bar.setValue(amount)
        bar.setTextVisible(False)
        bar.setFixedHeight(7)
        bar.setAccessibleName(f"{title}: {amount} of {len(mods)} detected mod locations")
        line.addWidget(bar, 1)
        line.addWidget(_small(str(amount), "findingTitle"))
        source_col.addWidget(box)
    source_col.addStretch(1)
    row.addWidget(sources, 3)
    return panel


def old_files_categories(files):
    """Read-only, honest classification of files from the selected scan root."""
    buckets = {
        "Game caches": [0, 0], "Logs": [0, 0],
        "Temporary": [0, 0], "Install remnants": [0, 0],
        "Other old files": [0, 0],
    }
    for item in files:
        path = Path(item.path)
        name = path.name.casefold()
        parts = {s.casefold() for s in path.parts}
        if "cache" in name or "cache" in parts or "shadercache" in name:
            group = "Game caches"
        elif path.suffix.casefold() in (".log", ".trace") or "log" in parts:
            group = "Logs"
        elif path.suffix.casefold() in (".tmp", ".temp", ".bak", ".old"):
            group = "Temporary"
        elif path.suffix.casefold() in (".msi", ".msp", ".iso") or "installer" in name:
            group = "Install remnants"
        else:
            group = "Other old files"
        buckets[group][0] += 1
        buckets[group][1] += max(0, int(item.size))
    wrapper = QWidget()
    row = _layout(wrapper, vertical=False, pad=(0,0,0,0), gap=9)
    marks = (("Game caches", "▥"), ("Logs", "▤"), ("Temporary", "▧"),
             ("Install remnants", "▣"), ("Other old files", "▦"))
    for index, (name, mark) in enumerate(marks):
        count, bytes_size = buckets[name]
        row.addWidget(GraphicCard(
            name, human_size(bytes_size),
            f"{count:,} discovered file(s)",
            pictogram=mark, color="#43D6F2" if index != 3 else "#F84359"), 1)
    return wrapper


def graveyard_overview(entries):
    counts = Counter(str(e.category) for e in entries)
    total = sum(max(0, int(e.apparent_bytes)) for e in entries)
    safe = sum(1 for e in entries if e.can_recycle)
    protected = len(entries) - safe
    wrapper = QWidget()
    row = _layout(wrapper, vertical=False, pad=(0, 0, 0, 0), gap=9)
    for title, value, desc, icon, color in (
        ("Needs review", str(len(entries)), "Nothing recycled yet", "▤", "#F84359"),
        ("Apparent size", human_size(total), "Not confirmed reclaimable", "▣", "#43D6F2"),
        ("Reviewable", str(safe), "File-specific review", "✓", "#43D6F2"),
        ("Protected", str(protected), "Override requires consent", "⬡", "#92AEC1"),
    ):
        row.addWidget(GraphicCard(title, value, desc, pictogram=icon, color=color), 1)
    return wrapper


def clear_empty_panel(title: str, message: str):
    panel = QFrame()
    panel.setObjectName("dashboardPanel")
    col = _layout(panel, pad=(20, 20, 20, 20), gap=12)
    icon = _small("✓", "graphicMark")
    icon.setStyleSheet("color:#43D6F2;font-size:40px;")
    col.addWidget(icon)
    col.addWidget(_small(title, "sceneTitle"))
    col.addWidget(_small(message))
    return panel
