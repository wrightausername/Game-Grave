"""Crimson Command game and mod inspectors. UI only; all facts come from scans.

Cards show locally discovered art or an explicitly labeled generated title.
No remote requests, fake covers, fabricated mod conflicts or destructive actions.
"""
from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QImageReader, QPixmap
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QVBoxLayout, QWidget,
)

from core import human_size, age_text
from gg_desktop.local_art import game_cover_path


def _label(text, role="", wrap=True):
    label = QLabel(str(text))
    if role:
        label.setObjectName(role)
    label.setWordWrap(wrap)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return label


def _col(parent=None, spacing=8, margins=(13, 13, 13, 13)):
    layout = QVBoxLayout(parent)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    return layout


def _load_local_art(game, width=330, height=205):
    """Limit decoding before painting, including format/pixel limits."""
    if game is None:
        return QPixmap()
    path = game_cover_path(game)
    if not path:
        return QPixmap()
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    size = reader.size()
    if (not size.isValid() or size.width() < 1 or size.height() < 1
            or size.width() > 8192 or size.height() > 8192
            or size.width() * size.height() > 32_000_000):
        return QPixmap()
    scale = min(1.0, 720 / max(size.width(), size.height()))
    if scale < 1:
        reader.setScaledSize(QSize(max(1, round(size.width() * scale)),
                                   max(1, round(size.height() * scale))))
    image = reader.read()
    if image.isNull():
        return QPixmap()
    return QPixmap.fromImage(image).scaled(
        width, height, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)


def _image(label, game, *, w=320, h=186):
    label.setFixedHeight(h)
    label.setMinimumWidth(140)
    label.setAlignment(Qt.AlignCenter)
    pixmap = _load_local_art(game, w, h)
    label.clear()
    if not pixmap.isNull():
        label.setStyleSheet("background:#091522;border:1px solid #5E3045;border-radius:9px;")
        label.setPixmap(pixmap)
        label.setToolTip("Local game art found on this PC")
    else:
        from gg_desktop.poster_art import generated_game_poster
        title = str(getattr(game, "name", "") or "MOD RADAR")
        label.setPixmap(generated_game_poster(title, min(w, 320), h))
        label.setToolTip("Original Game Grave artwork, not official game cover art")


class GameInspector(QFrame):
    """Persistent selection detail area with only verified available actions."""

    def __init__(self, on_details, on_open, on_mods, on_captures):
        super().__init__()
        self.setObjectName("premiumInspector")
        self.setMinimumWidth(335)
        self.setMaximumWidth(390)
        self.game = None
        self._details = on_details
        self._open = on_open
        self._mods = on_mods
        self._captures = on_captures
        layout = _col(self, spacing=10, margins=(13, 15, 13, 15))
        layout.addWidget(_label("SELECTED GAME", "sceneKicker"))
        self.art = QLabel()
        layout.addWidget(self.art)
        self.name = _label("Select a game", "premiumTitle")
        layout.addWidget(self.name)
        self.status = _label("", "premiumState")
        layout.addWidget(self.status)
        self.size = _label("", "premiumMetric")
        layout.addWidget(self.size)
        self.platform = _label("", "caption")
        layout.addWidget(self.platform)
        self.last = _label("", "caption")
        layout.addWidget(self.last)
        layout.addWidget(_label("INSTALL LOCATION", "sceneKicker"))
        self.path = _label("", "premiumPath")
        layout.addWidget(self.path)
        layout.addWidget(_label("WHAT CAN I DO?", "sceneKicker"))
        self.details_btn = QPushButton("Inspect game details")
        self.details_btn.setObjectName("primary")
        self.details_btn.clicked.connect(lambda: self.game is not None and self._details(self.game))
        layout.addWidget(self.details_btn)
        self.open_btn = QPushButton("Open install folder")
        self.open_btn.clicked.connect(lambda: self.game is not None and self._open(self.game))
        layout.addWidget(self.open_btn)
        self.mods_btn = QPushButton("View Mod Radar")
        self.mods_btn.clicked.connect(self._mods)
        layout.addWidget(self.mods_btn)
        self.captures_btn = QPushButton("Browse game captures")
        self.captures_btn.clicked.connect(self._captures)
        layout.addWidget(self.captures_btn)
        self.hint = _label(
            "Local artwork is optional. Installations, sizes, and activity are never invented.",
            "caption")
        layout.addWidget(self.hint)
        layout.addStretch(1)
        self.set_game(None)

    def set_game(self, game):
        self.game = game
        active = game is not None
        self.details_btn.setEnabled(active)
        self.open_btn.setEnabled(active and "open_folder" in game.capabilities)
        self.mods_btn.setEnabled(active)
        self.captures_btn.setEnabled(active)
        self.name.setText(game.name if active else "Choose a game from the library")
        self.status.setText(game.status if active else "Scan PC to populate verified games.")
        self.size.setText(
            human_size(game.size_bytes) if active and game.size_bytes is not None
            else "Size unavailable")
        self.platform.setText(
            f"Launcher: {game.launcher}" if active else "")
        self.last.setText(
            "Last played: " + (age_text(game.last_played_at)
                               if game.last_played_at is not None else "Unknown")
            if active else "")
        self.path.setText(game.install_path if active else "No installation selected")
        self.path.setToolTip(game.install_path if active else "")
        _image(self.art, game)


def _within(child: str, parent: str) -> bool:
    """Metadata-only containment for definite installed-root relationships."""
    try:
        a = os.path.normcase(os.path.abspath(str(child)))
        b = os.path.normcase(os.path.abspath(str(parent)))
        return bool(a and b and os.path.commonpath((a, b)) == b)
    except (OSError, ValueError, TypeError):
        return False


def group_mod_locations(games, mods):
    """Only attribute mod paths physically inside a verified install root.

    External manager staging paths remain unattributed rather than guessed.
    This counts discovered *locations*, never claims file counts/conflicts.
    """
    pairs = []
    unattributed = []
    for mod in mods:
        path = str(getattr(mod, "path", "") or "")
        matched = next((g for g in games if path
                        and _within(path, g.install_path)), None)
        if matched is None:
            unattributed.append(mod)
        else:
            found = next((row for row in pairs if row[0].key == matched.key), None)
            if found is None:
                pairs.append((matched, [mod]))
            else:
                found[1].append(mod)
    pairs.sort(key=lambda row: (-len(row[1]), row[0].name.casefold()))
    return pairs, unattributed


class ModLocationCard(QFrame):
    """Visual selection without a promise of safe removal or conflict detection."""

    def __init__(self, game, locations, on_selected, source=None):
        super().__init__()
        self.setObjectName("modLocationCard")
        self.setMinimumWidth(200)
        self.setFixedHeight(208)
        self.setCursor(Qt.PointingHandCursor)
        self._choose = on_selected
        layout = _col(self, spacing=4, margins=(7, 7, 7, 8))
        art = QLabel()
        _image(art, game, w=248, h=135)
        if game is None:
            from gg_desktop.poster_art import generated_game_poster
            art.setPixmap(generated_game_poster(str(source or "MOD SOURCE"), 248, 135))
        layout.addWidget(art)
        title = game.name if game else str(source or "Other locations")
        layout.addWidget(_label(title[:45], "findingTitle"))
        layout.addWidget(_label(f"{len(locations)} discovered location(s)", "premiumState"))
        layout.addWidget(_label("Verified install root" if game
                                else "External / unattributed", "caption"))
        layout.addStretch()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self._choose()
        super().mouseReleaseEvent(event)


def mod_gallery(games, mods, on_selected, *, limit=9):
    """Gallery of actual mod locations, grouped by known game or detected source."""
    pairs, unknown = group_mod_locations(games, mods)
    box = QFrame()
    box.setObjectName("referenceLibrary")
    column = _col(box, spacing=11)
    column.addWidget(_label("MOD LIBRARY  /  REAL SCAN EVIDENCE", "sectionTitle"))
    column.addWidget(_label(
        "Game-linked cards require a verified install-path match. "
        "External mod-manager folders remain separate and protected.", "caption"))
    if not mods:
        from gg_desktop.poster_art import generated_game_poster
        illustration = QLabel()
        illustration.setObjectName("noModsArtwork")
        illustration.setAlignment(Qt.AlignCenter)
        illustration.setPixmap(
            generated_game_poster("MOD RADAR • SCAN READY", 630, 208))
        illustration.setMinimumHeight(225)
        column.addWidget(illustration)
        empty = _label("NO MOD LOCATIONS FOUND", "premiumTitle")
        empty.setAlignment(Qt.AlignCenter)
        column.addWidget(empty)
        message = _label(
            "This scan found no verified mod or manager storage. "
            "Nothing is marked safe to delete. The cards appear here "
            "when sources are discovered.", "caption")
        message.setAlignment(Qt.AlignCenter)
        column.addWidget(message)
        return box, pairs, unknown
    targets = [(game, found, None) for game, found in pairs]
    if unknown:
        sources = {}
        for mod in unknown:
            source = str(getattr(mod, "source", "") or "Other mod locations")
            sources.setdefault(source, []).append(mod)
        targets.extend((None, found, source) for source, found in
                       sorted(sources.items(), key=lambda row: (-len(row[1]), row[0])))
    grid_holder = QWidget()
    grid = QGridLayout(grid_holder)
    grid.setContentsMargins(0, 3, 0, 3)
    grid.setSpacing(10)
    for i, (game, found, source) in enumerate(targets[:limit]):
        grid.addWidget(ModLocationCard(
            game, found,
            lambda g=game, m=found, src=source: on_selected(g, m, src),
            source=source), i // 3, i % 3)
    for col in range(3):
        grid.setColumnStretch(col, 1)
    column.addWidget(grid_holder)
    if len(targets) > limit:
        column.addWidget(_label(
            f"{len(targets) - limit} additional game/source groups. "
            "The complete findings table is below.", "caption"))
    return box, pairs, unknown


class ModInspector(QFrame):
    """Selection-driven mod evidence panel, without speculative health scores."""

    def __init__(self, on_open, on_review, on_scan):
        super().__init__()
        self.setObjectName("premiumInspector")
        self.setMinimumWidth(335)
        self.setMaximumWidth(390)
        self._on_open = on_open
        self._on_review = on_review
        self._on_scan = on_scan
        self.locations = []
        col = _col(self, spacing=11)
        col.addWidget(_label("MOD RADAR", "sceneKicker"))
        self.art = QLabel()
        col.addWidget(self.art)
        self.title = _label("Select a mod source", "premiumTitle")
        col.addWidget(self.title)
        self.count = _label("0 locations", "premiumMetric")
        col.addWidget(self.count)
        self.provenance = _label("", "caption")
        col.addWidget(self.provenance)
        col.addWidget(_label("DETECTED SOURCE BREAKDOWN", "sceneKicker"))
        self.sources = _label("", "premiumPath")
        col.addWidget(self.sources)
        col.addWidget(_label("SAFE ACTIONS", "sceneKicker"))
        self.open_btn = QPushButton("Open selected mod folder")
        self.open_btn.clicked.connect(self.open_selected)
        col.addWidget(self.open_btn)
        self.review_btn = QPushButton("Send location to Graveyard review…")
        self.review_btn.setObjectName("primary")
        self.review_btn.clicked.connect(self.review_selected)
        col.addWidget(self.review_btn)
        self.scan_btn = QPushButton("Scan PC again")
        self.scan_btn.clicked.connect(self._on_scan)
        col.addWidget(self.scan_btn)
        col.addWidget(_label(
            "Source and storage evidence are not proof of an orphan, conflict, "
            "safe deletion or available update. Protections remain active.",
            "caption"))
        col.addStretch()
        self.set_group(None, [])

    def set_group(self, game, locations, source=None):
        self.locations = list(locations)
        self.title.setText(game.name if game is not None else
                           str(source or "Select a mod source"))
        self.count.setText(f"{len(self.locations)} location(s)")
        self.provenance.setText(
            "Inside a verified installed game folder" if game is not None
            else "Source group / no proven installed-game association")
        self.sources.setText("\n".join(
            f"{name}: {count} location(s)" for name, count in
            Counter(str(getattr(m, "source", "Unknown"))
                    for m in self.locations).most_common(6))
            or "No mod locations selected")
        self.open_btn.setEnabled(bool(self.locations))
        self.review_btn.setEnabled(bool(self.locations))
        self.review_btn.setText(
            "Review first location in Graveyard…"
            if len(self.locations) > 1 else "Send location to Graveyard review…")
        _image(self.art, game, w=320, h=158)
        if game is None:
            from gg_desktop.poster_art import generated_game_poster
            self.art.setPixmap(generated_game_poster("MOD RADAR", 300, 158))

    def open_selected(self):
        if self.locations:
            self._on_open(self.locations[0])

    def review_selected(self):
        if self.locations:
            self._on_review(self.locations[0])
