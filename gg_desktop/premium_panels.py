"""Crimson Command game and mod inspectors. UI only; all facts come from scans.

Cards show locally discovered art or an explicitly labeled generated title.
No remote requests, fake covers, fabricated mod conflicts or destructive actions.
"""
from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QPointF, QRectF
from PySide6.QtGui import QColor, QFont, QImageReader, QPainter, QPen, QPixmap, QRadialGradient, QLinearGradient
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QVBoxLayout, QWidget,
)

from core import human_size, age_text
from gg_desktop.local_art import game_cover_path
from gg_desktop.voice import EMPTY_STATES
from gg_desktop.typography import display_family, text_family


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
        if game is not None:
            label.setText("OFFICIAL COVER UNAVAILABLE")
            label.setStyleSheet(
                "background:#0A1824;color:#BDD0DE;border:1px dashed #345064;"
                "font-size:11px;font-weight:700;")
            label.setToolTip("No matching game artwork in cache.")
        else:
            from gg_desktop.poster_art import generated_game_poster
            label.setPixmap(generated_game_poster("MOD RADAR", min(w, 320), h))
            label.setToolTip("Game Grave artwork for a mod source, not a game cover.")


class GameInspector(QFrame):
    """Persistent selection detail area with only verified available actions."""

    def __init__(self, on_details, on_open, on_mods, on_captures,
                 on_choose_cover=None, on_reset_cover=None,
                 on_steam_cover=None):
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
        self.choose_cover_btn = QPushButton("Choose game cover…")
        self.choose_cover_btn.setObjectName("chooseGameCover")
        self.choose_cover_btn.setToolTip(
            "Choose a real image for this exact game when automatic official "
            "artwork is unavailable. Files are copied into Game Grave's cache only.")
        self.choose_cover_btn.clicked.connect(
            lambda: self.game is not None and on_choose_cover is not None
                    and on_choose_cover(self.game))
        self.choose_cover_btn.setVisible(on_choose_cover is not None)
        layout.addWidget(self.choose_cover_btn)
        self.steam_cover_btn = QPushButton("Find official Steam cover by AppID…")
        self.steam_cover_btn.setObjectName("steamStoreCoverLookup")
        self.steam_cover_btn.clicked.connect(
            lambda: self.game is not None and on_steam_cover is not None
                    and on_steam_cover(self.game))
        self.steam_cover_btn.setVisible(on_steam_cover is not None)
        layout.addWidget(self.steam_cover_btn)
        self.reset_cover_btn = QPushButton("Restore official artwork")
        self.reset_cover_btn.setObjectName("resetGameCover")
        self.reset_cover_btn.clicked.connect(
            lambda: self.game is not None and on_reset_cover is not None
                    and on_reset_cover(self.game))
        self.reset_cover_btn.setVisible(on_reset_cover is not None)
        layout.addWidget(self.reset_cover_btn)
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
        self.choose_cover_btn.setEnabled(active)
        self.steam_cover_btn.setEnabled(active)
        from gg_desktop.custom_game_art import override_path
        self.reset_cover_btn.setEnabled(active and bool(override_path(game)) if active else False)
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


class ModShelfEmpty(QFrame):
    """Original quiet, illustrated empty mod shelf. Not a pretend game cover.

    Readable actions on the left; a spare stack of unlabelled game binders
    on the right. No animations, no fabricated data, no scans on show.
    """
    def __init__(self, on_scan=None, on_add_library=None):
        super().__init__()
        self.setObjectName("modShelfEmpty")
        self.setMinimumHeight(282)
        self.setSizePolicy(
            self.sizePolicy().horizontalPolicy(), self.sizePolicy().verticalPolicy())
        stage = QHBoxLayout(self)
        stage.setContentsMargins(22, 24, 18, 23)
        stage.setSpacing(12)
        words = QWidget()
        words.setObjectName("modShelfCopy")
        column = QVBoxLayout(words)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(12)
        column.addWidget(_label("THE MOD SHELF  /  00", "modShelfKicker"))
        column.addWidget(_label(EMPTY_STATES["Mods"][0], "modShelfHeadline"))
        body = _label(EMPTY_STATES["Mods"][1], "modShelfDescription")
        column.addWidget(body)
        column.addSpacing(9)
        if on_scan is not None:
            rescan = QPushButton("Scan again")
            rescan.setObjectName("primary")
            rescan.setAccessibleName("Scan again for game mod locations")
            rescan.clicked.connect(on_scan)
            column.addWidget(rescan)
        if on_add_library is not None:
            add = QPushButton("Add a game folder…")
            add.setObjectName("referenceSecondary")
            add.setAccessibleName("Add a game library folder")
            add.clicked.connect(on_add_library)
            column.addWidget(add)
        column.addStretch(1)
        stage.addWidget(words, 5)
        stage.addStretch(3)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor("#090F17"))
        glow = QRadialGradient(QPointF(w*.82, h*.58), max(110,w*.44))
        glow.setColorAt(0, QColor(142, 37, 62, 108))
        glow.setColorAt(1, QColor(20, 20, 27, 0))
        p.fillRect(self.rect(), glow)
        # Game binders without fictional posters or implied installations.
        midx, floor = w*.82, h*.81
        unit = max(16.0, min(42.0, w*.065))
        for i, (tilt, height, tint) in enumerate(
                ((-10, 139, "#1E3B47"), (0, 174, "#412333"), (7, 153, "#242D3F"))):
            x = midx+(i-1)*(unit+9)
            y = floor-height
            p.save()
            p.translate(x, floor)
            p.rotate(tilt)
            spine = QLinearGradient(0,-height,unit,0)
            spine.setColorAt(0, QColor(tint))
            spine.setColorAt(1, QColor("#080E15"))
            p.setBrush(spine)
            p.setPen(QPen(QColor("#58636C"), 1.8))
            p.drawRoundedRect(QRectF(0, -height, unit, height), 2, 2)
            p.setPen(QPen(QColor("#B34157"), 2.0))
            p.drawLine(QPointF(5,-height+18), QPointF(unit-5,-height+18))
            p.setPen(QPen(QColor("#658C9A"), 1.3))
            p.drawLine(QPointF(7,-height+32), QPointF(unit-7,-height+32))
            p.drawLine(QPointF(7,-height+39), QPointF(unit-7,-height+39))
            p.drawEllipse(QPointF(unit*.5,-33), 6, 6)
            p.restore()
        p.setPen(QPen(QColor("#4B2637"), 4))
        p.drawLine(QPointF(w*.62, floor+14), QPointF(w*.99, floor+14))
        p.setPen(QPen(QColor("#B14159"), 1))
        p.drawLine(QPointF(w*.62, floor+22), QPointF(w*.99, floor+22))
        p.end()


class ModLocationCard(QFrame):
    """Visual selection without a promise of safe removal or conflict detection."""

    def __init__(self, game, locations, on_selected, source=None):
        super().__init__()
        self.setObjectName("modLocationCard")
        self.setMinimumWidth(140)
        self.setFixedHeight(294)
        self.setCursor(Qt.PointingHandCursor)
        self.setProperty("selected", False)
        self._choose = on_selected
        self.game_name = game.name if game is not None else str(source or "Other locations")
        self.source_name = (str(source) if source else "Linked game")
        self.location_count = len(locations)
        self.search_tokens = " ".join(
            [self.game_name, self.source_name, *[
                str(getattr(mod, "source", "")) + " " +
                str(getattr(mod, "path", "")) for mod in locations]]
        ).casefold()
        layout = _col(self, spacing=5, margins=(5, 5, 5, 9))
        art = QLabel()
        _image(art, game, w=162, h=200)
        art.setObjectName("modCardArtwork")
        if game is None:
            art.setText(str(source or "Unlinked folder"))
            art.setAlignment(Qt.AlignCenter)
            art.setWordWrap(True)
            art.setObjectName("modSourcePlaceholder")
            art.setMinimumHeight(200)
        layout.addWidget(art)
        title = game.name if game else str(source or "Other locations")
        name_label = _label(title[:42], "findingTitle")
        name_label.setFont(QFont(display_family(), 12, QFont.Bold))
        name_label.setToolTip(title)
        layout.addWidget(name_label)
        count_label = _label(f"{len(locations)} mod folder(s)", "premiumState")
        count_label.setFont(QFont(display_family(), 10, QFont.DemiBold))
        layout.addWidget(count_label)
        context_label = _label(
            "Game-linked" if game else "Unlinked source", "caption")
        context_label.setFont(QFont(text_family(), 9))
        layout.addWidget(context_label)
        layout.addStretch()

    def activate(self):
        """The selection border follows the live inspector, not a fake active state."""
        parent = self.parentWidget()
        if parent is not None:
            for card in parent.findChildren(ModLocationCard, options=Qt.FindDirectChildrenOnly):
                card.setProperty("selected", card is self)
                card.style().unpolish(card)
                card.style().polish(card)
        self._choose()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self.activate()
        super().mouseReleaseEvent(event)


def mod_gallery(games, mods, on_selected, *, limit=10, columns=5,
                on_scan=None, on_add_library=None):
    """Gallery of actual mod locations, grouped by known game or detected source."""
    pairs, unknown = group_mod_locations(games, mods)
    box = QFrame()
    box.setObjectName("referenceLibrary")
    column = _col(box, spacing=11)
    if not mods:
        column.addWidget(ModShelfEmpty(on_scan, on_add_library))
        return box, pairs, unknown
    column.addWidget(_label("YOUR MODDED GAMES", "modShelfSectionTitle"))
    column.addWidget(_label(
        "Select a game to see the mod folders we could link to its install. "
        "Unlinked manager folders have their own place on the shelf.",
        "modShelfSectionNote"))
    targets = [(game, found, None) for game, found in pairs]
    if unknown:
        sources = {}
        for mod in unknown:
            source = str(getattr(mod, "source", "") or "Other mod locations")
            sources.setdefault(source, []).append(mod)
        targets.extend((None, found, source) for source, found in
                       sorted(sources.items(), key=lambda row: (-len(row[1]), row[0])))
    grid_holder = QWidget()
    grid_holder.setObjectName("modCardGrid")
    grid = QGridLayout(grid_holder)
    grid.setContentsMargins(0, 3, 0, 3)
    grid.setSpacing(11)
    columns = max(1, min(5, int(columns)))
    for i, (game, found, source) in enumerate(targets[:limit]):
        grid.addWidget(ModLocationCard(
            game, found,
            lambda g=game, m=found, src=source: on_selected(g, m, src),
            source=source), i // columns, i % columns)
    for col in range(columns):
        grid.setColumnStretch(col, 1)
    if grid.count():
        first = grid.itemAt(0).widget()
        first.setProperty("selected", True)
    column.addWidget(grid_holder)
    if len(targets) > limit:
        column.addWidget(_label(
            f"{len(targets) - limit} additional game/source groups. "
            "The complete findings table is below.", "caption"))
    return box, pairs, unknown


class ModRadarScope(QWidget):
    """Native high-DPI crimson radar instrument; count is actual selected rows.

    This is navigation artwork, NOT an invented conflict/orphan health score.
    No animation, polling, file access or GPU hooks.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._count = 0
        self.setFixedHeight(156)
        self.setObjectName("modRadarScope")
        self.setAccessibleName("Illustrated mod radar: selection location count")

    def set_count(self, count):
        self._count = max(0, int(count))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#0A1019"))
        x, y = self.width() * .5, self.height() * .53
        radius = min(70.0, self.height() * .43, self.width() * .39)
        glow = QRadialGradient(QPointF(x, y), radius * 1.18)
        glow.setColorAt(0, QColor(235, 44, 78, 55))
        glow.setColorAt(1, QColor(235, 44, 78, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QPointF(x, y), radius * 1.15, radius * 1.15)
        p.setBrush(Qt.NoBrush)
        for fraction, color, weight in (
                (1, "#E73959", 2.8),
                (.73, "#7D3047", 1.4),
                (.46, "#B73350", 1.1)):
            p.setPen(QPen(QColor(color), weight))
            p.drawEllipse(QPointF(x, y), radius * fraction, radius * fraction)
        p.setPen(QPen(QColor("#C73B59"), 1))
        p.drawLine(QPointF(x-radius-9, y), QPointF(x+radius+9, y))
        p.drawLine(QPointF(x, y-radius-9), QPointF(x, y+radius+9))
        p.setPen(QPen(QColor("#EF536E"), 2.4))
        p.drawArc(int(x-radius*.95), int(y-radius*.95),
                  int(radius*1.9), int(radius*1.9), 29*16, 54*16)
        p.setFont(QFont(display_family(), 24, QFont.Bold))
        p.setPen(QColor("#FEF3F5"))
        p.drawText(int(x-60), int(y-30), 120, 48, Qt.AlignCenter, str(self._count))
        p.setFont(QFont(display_family(), 9, QFont.Bold))
        p.setPen(QColor("#DCA7B3"))
        p.drawText(int(x-95), int(y+17), 190, 22, Qt.AlignCenter, "LOCATIONS")
        p.end()


class ModInspector(QFrame):
    """Selection-driven mod evidence panel, without speculative health scores."""

    def __init__(self, on_open, on_review, on_scan):
        super().__init__()
        self.setObjectName("premiumInspector")
        self.setMinimumWidth(310)
        self.setMaximumWidth(345)
        self._on_open = on_open
        self._on_review = on_review
        self._on_scan = on_scan
        self.locations = []
        col = _col(self, spacing=9)
        col.addWidget(_label("MOD CONTROL CENTER", "sceneKicker"))
        self.scope = ModRadarScope()
        col.addWidget(self.scope)
        self.art = QLabel()
        col.addWidget(self.art)
        self.title = _label("Pick a game", "premiumTitle")
        self.title.setFont(QFont(display_family(), 19, QFont.Bold))
        col.addWidget(self.title)
        self.count = _label("0 locations", "premiumMetric")
        col.addWidget(self.count)
        self.provenance = _label("", "caption")
        col.addWidget(self.provenance)
        col.addWidget(_label("WHERE WE FOUND IT", "sceneKicker"))
        self.sources = _label("", "premiumPath")
        col.addWidget(self.sources)
        col.addWidget(_label("WHAT YOU CAN DO", "sceneKicker"))
        self.open_btn = QPushButton("Open folder")
        self.open_btn.clicked.connect(self.open_selected)
        col.addWidget(self.open_btn)
        self.review_btn = QPushButton("Review in Graveyard…")
        self.review_btn.setObjectName("primary")
        self.review_btn.clicked.connect(self.review_selected)
        col.addWidget(self.review_btn)
        self.scan_btn = QPushButton("RUN MOD SCAN")
        self.scan_btn.clicked.connect(self._on_scan)
        col.addWidget(self.scan_btn)
        col.addWidget(_label(
            "Files aren't called leftovers because they're old. "
            "Review the source and protections before moving anything.",
            "editorialFootnote"))
        col.addStretch()
        self.set_group(None, [])

    def set_group(self, game, locations, source=None):
        self.locations = list(locations)
        self.title.setText(game.name if game is not None else
                           str(source or "Pick a folder"))
        self.count.setText(f"{len(self.locations)} FOUND FOLDERS")
        self.scope.set_count(len(self.locations))
        self.provenance.setText(
            "Found inside this game's install folder" if game is not None
            else "We couldn't link this folder to a game install")
        self.sources.setText("\n".join(
            f"{name}: {count} location(s)" for name, count in
            Counter(str(getattr(m, "source", "Unknown"))
                    for m in self.locations).most_common(6))
            or "Choose a game or folder to see its source")
        self.open_btn.setEnabled(bool(self.locations))
        self.review_btn.setEnabled(bool(self.locations))
        self.review_btn.setText(
            "Review first folder in Graveyard…"
            if len(self.locations) > 1 else "Review in Graveyard…")
        _image(self.art, game, w=320, h=158)
        self.art.setVisible(game is not None)

    def open_selected(self):
        if self.locations:
            self._on_open(self.locations[0])

    def review_selected(self):
        if self.locations:
            self._on_review(self.locations[0])
