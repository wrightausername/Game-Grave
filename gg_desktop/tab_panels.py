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


class GameCover(QFrame):
    """Clickable, fully laid-out visual game card backed by one real record.

    Native labels avoid painter clipping on nested Windows scroll areas.
    No fictional cover art or network image lookups.
    """
    def __init__(self, game, on_selected):
        super().__init__()
        self.game = game
        self._select = on_selected
        self.setObjectName("gameCover")
        self.setFixedHeight(187)
        self.setMinimumWidth(156)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"{game.name}\n{game.launcher}\n{game.install_path}")
        self.setAccessibleName("Select game: " + game.name)
        layout = _layout(self, pad=(9, 8, 9, 8), gap=3)
        symbol = QLabel("🎮")
        symbol.setObjectName("coverSymbol")
        symbol.setAlignment(Qt.AlignCenter)
        symbol.setFixedHeight(77)
        symbol.setStyleSheet(
            "background: #153340; color:#46D0E9; border:1px solid #315B6B;"
            "border-radius:6px; font-size:30px;")
        # A title monogram is more honest than fake, potentially copyrighted
        # game cover art. Use the game name in the accessibility description.
        initials = "".join(w[0] for w in game.name.split()[:2]).upper()[:2]
        symbol.setText(initials)
        layout.addWidget(symbol)
        name = QLabel(game.name)
        name.setObjectName("findingTitle")
        name.setWordWrap(True)
        name.setMaximumHeight(36)
        layout.addWidget(name)
        launcher = _small(game.launcher)
        launcher.setStyleSheet("color:#64D2EC;")
        layout.addWidget(launcher)
        value = (human_size(game.size_bytes)
                 if game.size_bytes is not None else "Size unknown")
        layout.addWidget(_small(value))
        layout.addStretch()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self._select()
        super().mouseReleaseEvent(event)


def game_gallery(games, selected_callback, *, limit=4):
    """Four full visual cards; the complete inventory remains in the table.

    No nested QScrollArea means no Windows render clipping or hidden row.
    """
    section = QFrame()
    section.setObjectName("dashboardPanel")
    layout = _layout(section)
    layout.addWidget(_small("YOUR GAME LIBRARY  •  VERIFIED INSTALLATIONS", "sectionTitle"))
    layout.addWidget(_small(
        "Select a game card to inspect the source and actions below. "
        "Local vector visuals, no fake game covers."))
    if not games:
        layout.addWidget(_small("No verified games yet. Run Scan PC to populate the shelf."))
        return section
    shelf = QWidget()
    shelf.setFixedHeight(202)
    shelf_row = _layout(shelf, vertical=False, pad=(1, 5, 1, 1), gap=11)
    for game in games[:limit]:
        shelf_row.addWidget(
            GameCover(game, lambda g=game: selected_callback(g)), 1)
    shelf_row.addStretch(1)
    layout.addWidget(shelf)
    if len(games) > limit:
        layout.addWidget(_small(
            f"Showing {limit} of {len(games)} verified games. "
            "Use the search and full list underneath for the rest."))
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
