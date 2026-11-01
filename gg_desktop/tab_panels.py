"""Functional visual panels composed from real inventory records only.

Nothing in this module scans or deletes files. Content is labelled as reported
or estimated when appropriate. Each tab reuses the global shell but receives
distinct graphic information to aid visual learners.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QFont, QImageReader, QPixmap, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton, QSizePolicy, QScrollArea,
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
    """Local-art game card using verified game records, never invented covers.

    Steam cache posters (when present) are decoded locally and bounded. Other
    launchers may provide an explicit cover in the game's installed root.
    No remote API, no download and no placeholder pretending to be real art.
    """
    def __init__(self, game, on_selected):
        super().__init__()
        self.game = game
        self._select = on_selected
        self.setObjectName("gameCover")
        self.setFixedHeight(211)
        self.setMinimumWidth(195)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"{game.name}\n{game.launcher}\n{game.install_path}")
        self.setAccessibleName("Select game: " + game.name)
        layout = _layout(self, pad=(7, 7, 7, 8), gap=4)
        art = QLabel()
        art.setObjectName("gameCoverArt")
        art.setAlignment(Qt.AlignCenter)
        art.setFixedHeight(134)
        art.setMinimumWidth(185)
        from gg_desktop.local_art import game_cover_path
        source = game_cover_path(game)
        if source:
            reader = QImageReader(source)
            reader.setAutoTransform(True)
            size = reader.size()
            if (size.isValid() and 0 < size.width() <= 8192
                    and 0 < size.height() <= 8192
                    and size.width() * size.height() <= 32_000_000):
                scale = min(1.0, 420 / max(size.width(), size.height()))
                if scale < 1:
                    reader.setScaledSize(QSize(
                        max(1, round(size.width() * scale)),
                        max(1, round(size.height() * scale))))
                image = reader.read()
                if not image.isNull():
                    pixmap = QPixmap.fromImage(image).scaled(
                        290, 134, Qt.KeepAspectRatioByExpanding,
                        Qt.SmoothTransformation)
                    art.setPixmap(pixmap)
                    art.setToolTip("Local artwork: " + source)
        if art.pixmap() is None or art.pixmap().isNull():
            # Original game-styled art, clearly marked as a generated fallback.
            from gg_desktop.poster_art import generated_game_poster
            art.setPixmap(generated_game_poster(game.name, 265, 134))
            art.setToolTip("Original Game Grave artwork, not an official game cover")
        layout.addWidget(art)
        name = QLabel(game.name)
        name.setObjectName("findingTitle")
        name.setWordWrap(True)
        name.setMaximumHeight(39)
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


def game_gallery(games, selected_callback, *, limit=9, empty_message=None):
    """Artwork-led game library grid, backed only by actual installations.

    The full searchable record table remains below. This is visual navigation,
    not an alternative data source or storage-deletion authority.
    """
    section = QFrame()
    section.setObjectName("referenceLibrary")
    section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
    layout = _layout(section, gap=10)
    layout.addWidget(_small("YOUR GAME LIBRARY  •  VERIFIED INSTALLATIONS",
                            "sectionTitle"))
    layout.addWidget(_small(
        "Select a cover to inspect its verified install and actions. "
        "Artwork is loaded from local caches when available."))
    if not games:
        layout.addWidget(_small(
            empty_message or "No verified games yet. Run Scan PC to populate the library."))
        return section
    shelf = QWidget()
    row_count = (min(len(games), limit) + 2) // 3
    shelf.setFixedHeight(row_count * 211 + max(0, row_count - 1) * 11 + 8)
    grid = QGridLayout(shelf)
    grid.setContentsMargins(0, 5, 0, 3)
    grid.setHorizontalSpacing(10)
    grid.setVerticalSpacing(11)
    for index, game in enumerate(games[:limit]):
        grid.addWidget(GameCover(game,
                       lambda g=game: selected_callback(g)),
                       index // 3, index % 3)
    for col in range(3):
        grid.setColumnStretch(col, 1)
    layout.addWidget(shelf, 0, Qt.AlignTop)
    if len(games) > limit:
        layout.addWidget(_small(
            f"Showing {limit} of {len(games)} verified games. "
            "Use search and the full list below for the rest."))
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


def _evidence_bar(parent, name, value, maximum, *, color="#F84359",
                  detail=""):
    """Truthful relative count visualization, with an explicit denominator."""
    row = QWidget()
    line = _layout(row, vertical=False, pad=(0, 0, 0, 0), gap=11)
    title = _small(name, "findingTitle")
    title.setMinimumWidth(135)
    line.addWidget(title, 2)
    bar = QProgressBar()
    bar.setMinimum(0)
    bar.setMaximum(max(1, int(maximum)))
    bar.setValue(max(0, min(int(value), max(1, int(maximum)))))
    bar.setTextVisible(False)
    bar.setFixedHeight(12)
    bar.setStyleSheet(
        "QProgressBar{background:#0B1721;border:1px solid #334757;"
        "border-radius:5px;}"
        f"QProgressBar::chunk{{background:{color};border-radius:4px;}}")
    bar.setAccessibleName(f"{name}: {value} of {maximum} inspected findings")
    line.addWidget(bar, 4)
    line.addWidget(_small(f"{value:,} / {maximum:,}" + detail, "caption"), 2)
    parent.addWidget(row)


def graveyard_mix_panel(entries):
    """What kinds of findings were discovered, not a deletion forecast."""
    total = len(entries)
    counts = Counter(str(getattr(e, "category", "Other")) for e in entries)
    panel = QFrame()
    panel.setObjectName("dashboardPanel")
    col = _layout(panel, gap=11)
    col.addWidget(_small("GRAVEYARD DISCOVERY MIX", "sectionTitle"))
    col.addWidget(_small(
        "Counts of currently scanned findings. Protection and apparent size "
        "are separate from what can actually be reclaimed.", "caption"))
    if not entries:
        col.addWidget(_small("No findings to chart after this scan.", "caption"))
        return panel
    colors = ("#F84359", "#41C7E8", "#A482EE", "#F8AF67", "#77D7AA")
    for idx, (category, count) in enumerate(counts.most_common(5)):
        _evidence_bar(col, category, count, total,
                      color=colors[idx % len(colors)])
    if len(counts) > 5:
        extra = sum(n for _, n in counts.most_common()[5:])
        _evidence_bar(col, "Other categories", extra, total, color="#91A7B9")
    return panel


def old_file_age_chart(files, *, now=None):
    """Age histogram from metadata, never proof that removal is safe."""
    import time
    clock = time.time() if now is None else now
    groups = [
        ("0–90 days", 0), ("91–180 days", 0), ("181–365 days", 0),
        ("1–2 years", 0), ("2+ years", 0),
    ]
    counts = [0] * len(groups)
    for file in files:
        try:
            age = max(0, (clock - float(file.modified)) / 86400)
        except (TypeError, ValueError, OverflowError):
            continue
        idx = (0 if age <= 90 else 1 if age <= 180 else
               2 if age <= 365 else 3 if age <= 730 else 4)
        counts[idx] += 1
    panel = QFrame()
    panel.setObjectName("dashboardPanel")
    col = _layout(panel, gap=9)
    col.addWidget(_small("DISCOVERED FILE AGE", "sectionTitle"))
    col.addWidget(_small(
        "Last-modified date is not last-used date. These relative counts "
        "do not establish that any file can be safely recycled.", "caption"))
    measured = sum(counts)
    if measured == 0:
        col.addWidget(_small("No timestamped findings to chart.", "caption"))
        return panel
    for i, ((name, _), amount) in enumerate(zip(groups, counts)):
        _evidence_bar(col, name, amount, measured,
                      color="#43D6F2" if i <= 2 else "#F84359")
    return panel
