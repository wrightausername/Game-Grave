"""The Mods Library as a gallery: a poster wall of your games, a banner for the one you picked, card rows for the mods
that need a look and the ones that changed lately.

Display only. Every card is drawn from facts the Mods tab already has (saved profile status, the manager's own recorded
update, the conflict check, the folder's own change time), supplied by `mods_gallery_data`. Pictures are each game's own
artwork when Game Grave already has it (the same local pictures the Games tab uses), else a drawn colour field. Nothing is
downloaded here, nothing is changed in any mod manager, and nothing is called safe. The table is still there as List view.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSignalBlocker, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
                           QRadialGradient)
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QScrollArea, QSizePolicy, QVBoxLayout, QWidget)
from shiboken6 import isValid

from gg_desktop import mods_gallery_data as gd
from gg_desktop import mods_insight as mi
from gg_desktop import mods_sort
from gg_desktop import mods_words as words
from gg_desktop.artwork import game_app_id
from gg_desktop.mods_visuals import hue_for, initials
from gg_desktop.reference_widgets import _cover_fit, tool

TONE_TEXT = {"green": "#69DEA7", "amber": "#FFD08E", "red": "#FF8796", "muted": "#A3B4C5"}
TONE_LINE = {"green": "#3E9E77", "amber": "#B58B4E", "red": "#FF5269", "muted": "#4A5967"}
PANEL, BORDER, TEXT, MUTED = "#111922", "#2A3541", "#F4F7FC", "#A3B4C5"
RED, CYAN, AMBER = "#FF5269", "#42D4F2", "#FFD08E"
POSTER = (132, 174)
CARD = (208, 218)
ART_HEIGHT = 117
ROW_PAD = 22  # room for a row's margins and its thin scroll bar

STYLE = f"""
QWidget#modGallery {{ background: transparent; }}
QFrame#modCard {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 12px; }}
QFrame#modCard:hover {{ border: 1px solid #5D7A94; background: #16212B; }}
QFrame#modCard[selected="true"] {{ border: 2px solid {RED}; background: #1A1F2A; }}
QFrame#modCard:focus {{ border: 2px solid {CYAN}; }}
QPushButton#cardAction {{ min-height: 16px; padding: 3px 12px; border-radius: 12px; font-size: 11px; font-weight: 700; }}
QPushButton#chip {{ min-height: 14px; padding: 4px 12px; border-radius: 14px; font-size: 11px; background: #17222D;
    border: 1px solid #384755; color: #D7E1ED; font-weight: 500; }}
QPushButton#chip:checked {{ background: #2A1220; border: 1px solid {RED}; color: white; font-weight: 700; }}
QPushButton#seg {{ min-height: 16px; padding: 5px 16px; border-radius: 7px; background: transparent; border: 1px solid transparent;
    color: #D7E1ED; font-weight: 500; }}
QPushButton#seg:checked {{ background: #A91E38; border: 1px solid {RED}; color: white; font-weight: 700; }}
QScrollArea#modRow, QScrollArea#modGalleryScroll {{ background: transparent; border: none; }}
QScrollArea#modRow > QWidget > QWidget, QScrollArea#modGalleryScroll > QWidget > QWidget {{ background: transparent; }}
QScrollBar:horizontal {{ height: 8px; background: transparent; margin: 0; }}
QScrollBar::handle:horizontal {{ background: #2A3541; border-radius: 4px; min-width: 40px; }}
QScrollBar::handle:horizontal:hover {{ background: #415569; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
"""


def _font(size, bold=False, weight=None):
    font = QFont("Segoe UI")
    font.setPixelSize(size)
    font.setBold(bold)
    if weight:
        font.setWeight(weight)
    return font


@lru_cache(maxsize=1)
def brand_art():
    path = Path(__file__).resolve().parent / "assets" / "brand" / "banner_mods.jpg"
    pix = QPixmap(str(path))
    return pix if not pix.isNull() else None


# ---------------------------------------------------------------- painting helpers
def paint_art(p, rect, pixmap, name, *, tint=0.0):
    """The game's own picture cover-fitted into `rect`, else a colour field from the name. `tint` adds the name's colour."""
    rect = QRectF(rect)
    hue = hue_for(name) / 360
    p.fillRect(rect, QColor("#0B1119"))
    if pixmap is not None and not pixmap.isNull():
        dpr = round(max(1.0, p.device().devicePixelRatioF()), 2)
        p.drawPixmap(rect.topLeft(), _cover_fit(pixmap, max(1, round(rect.width())), max(1, round(rect.height())), dpr))
    else:
        base = QLinearGradient(rect.topLeft(), rect.bottomRight())
        base.setColorAt(0, QColor.fromHslF(hue, .55, .20))
        base.setColorAt(.6, QColor("#0F141D"))
        base.setColorAt(1, QColor.fromHslF((hue + .08) % 1, .6, .16))
        p.fillRect(rect, base)
        glow = QRadialGradient(QPointF(rect.width() * .72, rect.height() * .35), rect.width() * .6)
        glow.setColorAt(0, QColor.fromHslF(hue, .8, .5, .40))
        glow.setColorAt(1, QColor.fromHslF(hue, .8, .5, 0))
        p.save()
        p.translate(rect.topLeft())
        p.fillRect(QRectF(0, 0, rect.width(), rect.height()), glow)
        p.restore()
    if tint:
        p.fillRect(rect, QColor.fromHslF(hue, .75, .45, tint))


def rounded(rect, top=12, bottom=12):
    rect = QRectF(rect)
    path = QPainterPath()
    path.moveTo(rect.left() + top, rect.top())
    path.lineTo(rect.right() - top, rect.top())
    path.quadTo(rect.right(), rect.top(), rect.right(), rect.top() + top)
    path.lineTo(rect.right(), rect.bottom() - bottom)
    path.quadTo(rect.right(), rect.bottom(), rect.right() - bottom, rect.bottom())
    path.lineTo(rect.left() + bottom, rect.bottom())
    path.quadTo(rect.left(), rect.bottom(), rect.left(), rect.bottom() - bottom)
    path.lineTo(rect.left(), rect.top() + top)
    path.quadTo(rect.left(), rect.top(), rect.left() + top, rect.top())
    path.closeSubpath()
    return path


def chip(p, x, y, text, color, *, dot=False, right=False, height=19, line=None):
    """A small dark pill with text; returns its rectangle. `right` anchors it by its right edge."""
    font = _font(11, True)
    fm = QFontMetrics(font)
    width = fm.horizontalAdvance(text) + (28 if dot else 18)
    left = x - width if right else x
    rect = QRectF(left, y, width, height)
    p.setPen(QPen(QColor(line or color), 1))
    p.setBrush(QColor(6, 9, 14, 205))
    p.drawRoundedRect(rect, height / 2, height / 2)
    p.setFont(font)
    if dot:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(color))
        p.drawEllipse(QPointF(rect.left() + 11, rect.center().y()), 3.2, 3.2)
    p.setPen(QColor(color))
    p.drawText(QRectF(rect.left() + (19 if dot else 0), rect.top(), rect.width() - (21 if dot else 0), height),
               Qt.AlignVCenter | (Qt.AlignLeft if dot else Qt.AlignHCenter), text)
    return rect


class Elided(QLabel):
    """One line of text that ends in an ellipsis instead of widening the card. The full text stays in the tooltip."""

    def __init__(self, text, size, color, bold=False):
        super().__init__()
        self._full, self._color = str(text), QColor(color)
        self.setFont(_font(size, bold))
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setMinimumWidth(0)
        self.setFixedHeight(QFontMetrics(self.font()).height() + 3)
        self.setAccessibleName(self._full)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setFont(self.font())
        p.setPen(self._color)
        p.drawText(self.rect(), Qt.AlignVCenter | Qt.AlignLeft,
                   QFontMetrics(self.font()).elidedText(self._full, Qt.ElideRight, self.width()))


# ---------------------------------------------------------------- pieces
class ArtBox(QWidget):
    """The picture on top of a card: the game's artwork, a colour of the mod's own, its initials, status pill, version."""

    def __init__(self, c, pixmap):
        super().__init__()
        self.c, self.pixmap = c, pixmap
        self.setFixedHeight(ART_HEIGHT)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
        r = QRectF(self.rect())
        name = self.c.facts.name
        p.setClipPath(rounded(r, 11, 0))
        paint_art(p, r, self.pixmap, name, tint=.30)
        veil = QLinearGradient(r.topLeft(), r.bottomLeft())
        veil.setColorAt(0, QColor(6, 9, 14, 120))
        veil.setColorAt(.45, QColor(6, 9, 14, 0))
        veil.setColorAt(1, QColor(6, 9, 14, 170))
        p.fillRect(r, veil)
        hue = hue_for(name) / 360
        x = -20.0
        while x < r.width() + 20:
            t = max(0.0, min(1.0, (x / r.width() - .15) / .75))
            if t > 0:
                p.setPen(QPen(QColor.fromHslF(hue, .9, .75, .16 * t), 3))
                p.drawLine(QPointF(x, r.height()), QPointF(x + r.height() * .36, 0))
            x += 18
        p.setPen(QColor(255, 255, 255, 120))
        p.setFont(_font(34, True))
        p.drawText(r, Qt.AlignCenter, initials(name))
        p.setClipping(False)
        chip(p, 8, 8, self.c.label, TONE_TEXT[self.c.tone], dot=True, line=TONE_LINE[self.c.tone])
        if self.c.version_text:
            chip(p, r.right() - 8, r.bottom() - 27, self.c.version_text, "#EAF4FC", right=True, line="#4A5967")


class ModCard(QFrame):
    activated = Signal(int)
    opened = Signal(int)
    reviewed = Signal(int)

    def __init__(self, c, pixmap, tip):
        super().__init__()
        self.c = c
        f = c.facts
        self.setObjectName("modCard")
        self.setFixedSize(*CARD)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setProperty("selected", False)
        self.setAccessibleName(f"{f.name}, {c.label}")
        self.setAccessibleDescription(c.note)
        if tip:
            self.setToolTip(tip)
        box = QVBoxLayout(self)
        box.setContentsMargins(1, 1, 1, 0)
        box.setSpacing(0)
        box.addWidget(ArtBox(c, pixmap))
        body = QVBoxLayout()
        body.setContentsMargins(11, 8, 11, 9)
        body.setSpacing(3)
        body.addWidget(Elided(f.name, 13, TEXT, bold=True))
        note = QLabel(c.note)
        note.setWordWrap(True)
        note.setFont(_font(11))
        note.setStyleSheet("color:#B9C5D2;background:transparent;")
        note.setFixedHeight(30)
        note.setAttribute(Qt.WA_TransparentForMouseEvents)
        body.addWidget(note)
        foot = QHBoxLayout()
        foot.setContentsMargins(0, 2, 0, 0)
        facts_line = " · ".join(t for t in (mods_sort.size_text(f.size) if f.size else "", f.manager) if t and t != "—")
        foot.addWidget(Elided(facts_line, 11, MUTED), 1)
        if c.action:
            button = QPushButton(c.action)
            button.setObjectName("cardAction")
            button.setCursor(Qt.PointingHandCursor)
            button.setAccessibleName(f"{c.action}: {f.name}")
            tone = c.tone
            button.setStyleSheet(
                f"QPushButton#cardAction {{ color:{TONE_TEXT[tone]}; border:1px solid {TONE_LINE[tone]}; "
                f"background:rgba(255,255,255,0.04); }} QPushButton#cardAction:hover {{ background:rgba(255,255,255,0.12); }}")
            button.clicked.connect(lambda: (self.activated.emit(f.index), self.reviewed.emit(f.index)))
            foot.addWidget(button, 0, Qt.AlignRight)
        body.addLayout(foot)
        box.addLayout(body)

    def set_selected(self, on):
        if bool(self.property("selected")) != on:
            self.setProperty("selected", on)
            self.style().unpolish(self)
            self.style().polish(self)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.activated.emit(self.c.facts.index)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.opened.emit(self.c.facts.index)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.activated.emit(self.c.facts.index)
            if event.key() != Qt.Key_Space:
                self.opened.emit(self.c.facts.index)
            return
        super().keyPressEvent(event)


class PosterTile(QAbstractButton):
    """A game as a poster: its artwork, name, how many mods, and an amber badge when some need a look."""

    def __init__(self, tile, pixmap, selected):
        super().__init__()
        self.tile, self.pixmap, self.picked = tile, pixmap, selected
        self.setFixedSize(*POSTER)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setText(tile.name)
        noun = "mod" if tile.count == 1 else "mods"
        extra = f", {tile.flagged} need a look" if tile.flagged else ""
        self.setAccessibleName(f"{tile.name}, {tile.count} {noun}{extra}")
        self.setToolTip(f"{tile.name}\n{tile.count} {noun}" + (f"\n{tile.flagged} with a conflict or a recorded update" if tile.flagged else ""))

    def sizeHint(self):
        return QSize(*POSTER)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
        outer = QRectF(self.rect())
        art = outer.adjusted(5, 5, -5, -5)
        if self.picked:
            for grow, alpha in ((4.5, 26), (3, 44), (1.6, 70)):
                p.setPen(QPen(QColor(255, 24, 59, alpha), 2))
                p.setBrush(Qt.NoBrush)
                p.drawPath(rounded(art.adjusted(-grow, -grow, grow, grow), 12 + grow, 12 + grow))
        path = rounded(art, 12, 12)
        p.setClipPath(path)
        paint_art(p, art, self.pixmap, self.tile.name)
        veil = QLinearGradient(art.topLeft(), art.bottomLeft())
        veil.setColorAt(0, QColor(6, 9, 14, 30))
        veil.setColorAt(.42, QColor(6, 9, 14, 0))
        veil.setColorAt(1, QColor(6, 9, 14, 240))
        p.fillRect(art, veil)
        if self.pixmap is None:
            p.setPen(QColor(255, 255, 255, 90))
            p.setFont(_font(36, True))
            p.drawText(QRectF(art.left(), art.top(), art.width(), art.height() * .62), Qt.AlignCenter,
                       "ALL" if self.tile.name == gd.ALL_GAMES else initials(self.tile.name))
        p.setFont(_font(13, True))
        fm = QFontMetrics(p.font())
        p.setPen(QColor(TEXT))
        p.drawText(QRectF(art.left() + 10, art.bottom() - 40, art.width() - 20, 18), Qt.AlignVCenter | Qt.AlignLeft,
                   fm.elidedText(self.tile.name, Qt.ElideRight, int(art.width() - 20)))
        p.setFont(_font(11))
        p.setPen(QColor("#C2CEDA"))
        noun = "mod" if self.tile.count == 1 else "mods"
        p.drawText(QRectF(art.left() + 10, art.bottom() - 22, art.width() - 20, 16), Qt.AlignVCenter | Qt.AlignLeft,
                   f"{self.tile.count} {noun}")
        p.setClipping(False)
        if self.tile.flagged:
            chip(p, art.right() - 7, art.top() + 7, str(self.tile.flagged), AMBER, dot=True, right=True, line="#B58B4E")
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(RED) if self.picked else QColor(BORDER), 2 if self.picked else 1))
        p.drawPath(path)
        if self.hasFocus():
            p.setPen(QPen(QColor(CYAN), 2))
            p.drawPath(rounded(art.adjusted(-2, -2, 2, 2), 14, 14))


class Banner(QFrame):
    """The picked game as a wide banner with the health bar along its bottom edge."""

    def __init__(self, pixmap, name, parts):
        super().__init__()
        self.pixmap, self.name, self.parts = pixmap, name, parts
        self.setMinimumHeight(150)
        self.setAccessibleName("Selected game " + name)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(.5, .5, -.5, -.5)
        path = rounded(r, 14, 14)
        p.setClipPath(path)
        paint_art(p, r, self.pixmap, self.name)
        veil = QLinearGradient(r.topLeft(), r.topRight())
        veil.setColorAt(0, QColor(6, 9, 14, 238))
        veil.setColorAt(.55, QColor(6, 9, 14, 160))
        veil.setColorAt(1, QColor(6, 9, 14, 70))
        p.fillRect(r, veil)
        if self.parts:
            colors = ("#69DEA7", "#FFD08E", "#FF4D66", "#5B6B7A", "#394450")
            x = r.left()
            for share, color in zip(self.parts, colors):
                width = r.width() * share
                if width > 0:
                    p.fillRect(QRectF(x, r.bottom() - 4, max(1.0, width - 2), 4), QColor(color))
                x += width
        p.setClipping(False)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(BORDER), 1))
        p.drawPath(path)


class ArtHero(QWidget):
    """The picture above a mod's details: its game's artwork fading into the panel, with its status and version."""

    def __init__(self, name, version, word, tone, pixmap):
        super().__init__()
        self.name, self.version, self.word, self.tone, self.pixmap = str(name), gd.known_version(version), str(word or ""), tone, pixmap
        self.setFixedHeight(132)
        self.setAccessibleName("Picture for " + self.name)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
        r = QRectF(self.rect())
        p.setClipPath(rounded(r, 8, 0))
        paint_art(p, r, self.pixmap, self.name, tint=.30)
        fade = QLinearGradient(r.topLeft(), r.bottomLeft())
        fade.setColorAt(0, QColor(6, 9, 14, 90))
        fade.setColorAt(.45, QColor(17, 25, 34, 0))
        fade.setColorAt(1, QColor("#111922"))
        p.fillRect(r, fade)
        p.setPen(QColor(255, 255, 255, 110))
        p.setFont(_font(36, True))
        p.drawText(QRectF(r.left(), r.top(), r.width(), r.height() * .8), Qt.AlignCenter, initials(self.name))
        p.setClipping(False)
        if self.word:
            chip(p, 8, 8, self.word, self.tone, dot=True, line=self.tone)
        if self.version:
            chip(p, r.right() - 8, 8, "v" + self.version.lstrip("vV"), "#EAF4FC", right=True, line="#4A5967")


def _dot(color):
    dot = QLabel()
    dot.setFixedSize(8, 8)
    dot.setStyleSheet(f"background:{color};border-radius:4px;")
    return dot


def _heading(text, count, dot=None, caption=""):
    row = QHBoxLayout()
    row.setSpacing(8)
    if dot:
        row.addWidget(_dot(dot), 0, Qt.AlignVCenter)
    title = QLabel(text)
    title.setFont(_font(15, True))
    title.setStyleSheet(f"color:{TEXT};background:transparent;")
    row.addWidget(title)
    if count is not None:
        number = QLabel(str(count))
        number.setStyleSheet(f"color:{MUTED};background:transparent;")
        row.addWidget(number)
    if caption:
        note = QLabel(caption)
        note.setStyleSheet(f"color:{MUTED};background:transparent;")
        row.addWidget(note)
    row.addStretch(1)
    return row


def _scroller(widgets, height, spacing=12, name="modRow"):
    area = QScrollArea()
    area.setObjectName(name)
    area.setFrameShape(QFrame.NoFrame)
    area.setWidgetResizable(True)
    area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    area.setFixedHeight(height)
    inner = QWidget()
    inner.setObjectName("modRowBody")
    row = QHBoxLayout(inner)
    row.setContentsMargins(2, 4, 2, 6)
    row.setSpacing(spacing)
    for widget in widgets:
        row.addWidget(widget, 0, Qt.AlignTop)
    row.addStretch(1)
    area.setWidget(inner)
    return area


# ---------------------------------------------------------------- facts from the page
def _alive(widget):
    return widget is not None and isValid(widget)


def collect(window, control):
    """(facts for every mod, facts for the rows on this page with their table positions)."""
    views = list(getattr(window, "_mod_views", []))
    shown = list(getattr(window, "_shown_mods", []))
    scanned = bool(getattr(window, "_mod_updates_scanned", False))
    updates = getattr(window, "_mod_updates", {}) if scanned else {}
    known_updates = scanned and bool(updates)
    report_known = control is not None and control.report is not None

    def build(view, index, with_time):
        entry = getattr(view.record, "catalog_entry", None)
        word, is_mod, outdated, newest, conflicts, partners, version = "Storage folder", False, None, "", None, (), ""
        if entry is not None and control is not None:
            status = mi.entry_status(entry, control.catalog)
            word = words.status_word(status.text)
            is_mod = entry.kind == "mod"
            version = entry.version if is_mod else ""
            info = updates.get(entry.key)
            if known_updates and is_mod:
                outdated = bool(info and info.outdated)
                newest = info.newest if info else ""
            if report_known and is_mod:
                found = control.findings(entry)
                conflicts = len(found)
                names = []
                for finding in found:
                    for key in finding.mods:
                        if key != entry.key:
                            name = control.entry_names.get(key, "")
                            if name and name not in names:
                                names.append(name)
                partners = tuple(names)
        key = str(getattr(view.record, "path", ""))
        modified = mods_sort.modified_time(key) if with_time else None
        return gd.Facts(index, key, view.name, view.game, view.manager, version, view.size, word, outdated, newest,
                        conflicts, partners, modified, is_mod)

    everything = [build(v, -1, False) for v in views]
    page = [build(view, i, True) for i, view in enumerate(shown)]
    return everything, page


# ---------------------------------------------------------------- the gallery
class ModsGallery(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.setObjectName("modGallery")
        self.setStyleSheet(STYLE)
        self.cards = []
        self.rebuilding = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("modGalleryScroll")
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setAccessibleName("Mods gallery")
        outer.addWidget(self.scroll)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self.refresh)
        artwork = getattr(window, "artwork", None)
        if artwork is not None:
            artwork.changed.connect(self._art_changed)

    def _art_changed(self, *_):
        if self.isVisible():
            self.timer.start()

    def pixmap_for(self, name):
        if name == gd.ALL_GAMES:
            return brand_art()
        artwork = getattr(self.window, "artwork", None)
        if artwork is None:
            return None
        for game in self.window.inventory.games:
            if game.name == name:
                return artwork.pixmap(game_app_id(game))
        return None

    # -- selection
    def pick(self, index):
        table = self.window.mod_table
        if 0 <= index < table.rowCount():
            table.selectRow(index)
            self.sync_selection()

    def open_details(self, index):
        self.pick(index)
        from gg_desktop import mods_page
        mods_page.activate(self.window)

    def review(self, index):
        self.pick(index)
        from gg_desktop import mods_page
        facts = next((c.facts for c in self.cards if c.facts.index == index), None)
        control = getattr(self.window.page, "mods", None)
        if facts is not None and facts.conflicts:
            mods_page.goto(self.window, "Conflicts")
        elif control is not None:
            mods_page.activate(self.window)

    def sync_selection(self):
        current = self.window.mod_table.currentRow()
        for card in self.findChildren(ModCard):
            card.set_selected(card.c.facts.index == current)

    def choose_game(self, name):
        filters = self.window.mod_game_filters
        for row in range(filters.count()):
            if filters.item(row).data(Qt.UserRole) == name:
                filters.setCurrentRow(row)
                return

    # -- build
    def refresh(self):
        window = self.window
        if not _alive(window.mod_table) or getattr(window, "_mod_tab", "Library") != "Library":
            return
        control = getattr(window.page, "mods", None)
        everything, page = collect(window, control)
        chosen_item = window.mod_game_filters.currentItem()
        chosen = chosen_item.data(Qt.UserRole) if chosen_item is not None else gd.ALL_GAMES
        in_game = [f for f in everything if chosen == gd.ALL_GAMES or f.game == chosen]
        h = gd.health(in_game)
        items = gd.cards(page)
        attention, recent = gd.needs_attention(items), gd.recently_changed(items)
        body = QWidget()
        body.setObjectName("modGalleryBody")
        column = QVBoxLayout(body)
        column.setContentsMargins(2, 2, 6, 8)
        column.setSpacing(14)
        tiles = gd.tiles(everything)
        column.addLayout(self._games_head(tiles))
        posters = [self._poster(t, t.name == chosen) for t in tiles]
        column.addWidget(_scroller(posters, POSTER[1] + ROW_PAD, spacing=8))
        column.addWidget(self._banner(chosen, in_game, h))
        if not everything:
            column.addWidget(self._empty("Nothing found yet", "Press Scan for Mods and the mods Game Grave finds will appear here."))
        elif not items:
            column.addWidget(self._empty("No mods match these filters", "Clear the search or pick another game or manager."))
        flagged_total = sum(bool(c.action) for c in items)
        dated_total = sum(1 for c in items if not c.action and c.facts.modified)
        if attention:
            column.addLayout(_heading("Needs attention", flagged_total, "#FF4D66",
                                      "conflicts first, then recorded updates"
                                      + (f" · showing {len(attention)} of {flagged_total}" if flagged_total > len(attention) else "")))
            column.addWidget(_scroller([self._card(c) for c in attention], CARD[1] + ROW_PAD))
        if recent:
            column.addLayout(_heading("Recently changed", dated_total, "#69DEA7",
                                      "newest folder change first"
                                      + (f" · showing {len(recent)}" if dated_total > len(recent) else "")))
            column.addWidget(_scroller([self._card(c) for c in recent], CARD[1] + ROW_PAD))
        rest = [c for c in items if not c.action and not c.facts.modified]
        if rest:
            column.addLayout(_heading("No change date", len(rest), "#5B6B7A",
                                      "the folder's change time could not be read"
                                      + (f" · showing {gd.RECENT_LIMIT}" if len(rest) > gd.RECENT_LIMIT else "")))
            column.addWidget(_scroller([self._card(c) for c in rest[:gd.RECENT_LIMIT]], CARD[1] + ROW_PAD))
        foot = QLabel("Pictures are each game's own artwork when Game Grave has it. Mods share their game's picture and "
                      "get a colour of their own. Game Grave only reads your mod folders; it never changes them.")
        foot.setWordWrap(True)
        foot.setStyleSheet(f"color:{MUTED};background:transparent;font-size:11px;")
        column.addWidget(foot)
        column.addStretch(1)
        self.cards = items
        position = self.scroll.verticalScrollBar().value()
        self.scroll.setUpdatesEnabled(False)
        old = self.scroll.takeWidget()
        self.scroll.setWidget(body)
        if old is not None:
            old.deleteLater()
        self.scroll.verticalScrollBar().setValue(position)
        self.scroll.setUpdatesEnabled(True)
        self.sync_selection()

    def _empty(self, title, text):
        box = QFrame()
        box.setStyleSheet(f"background:{PANEL};border:1px dashed #384755;border-radius:12px;")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(20, 22, 20, 22)
        head = QLabel(title)
        head.setFont(_font(15, True))
        head.setAlignment(Qt.AlignCenter)
        head.setStyleSheet("border:none;background:transparent;")
        note = QLabel(text)
        note.setAlignment(Qt.AlignCenter)
        note.setWordWrap(True)
        note.setStyleSheet(f"border:none;background:transparent;color:{MUTED};")
        lay.addWidget(head)
        lay.addWidget(note)
        return box

    def _games_head(self, tiles):
        row = QHBoxLayout()
        row.setSpacing(10)
        title = QLabel("Your games")
        title.setFont(_font(15, True))
        title.setStyleSheet(f"color:{TEXT};background:transparent;")
        row.addWidget(title)
        count = QLabel(str(max(0, len(tiles) - 1)))
        count.setStyleSheet(f"color:{MUTED};background:transparent;")
        row.addWidget(count)
        row.addStretch(1)
        window = self.window
        checks = list(getattr(window, "mod_manager_checks", []))
        if checks:
            group = QWidget()
            lay = QHBoxLayout(group)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(6)
            lay.addWidget(self._chip("All managers", not any(c.isChecked() for c in checks), self.clear_managers))
            for check in checks:
                lay.addWidget(self._chip(check.text().replace("  ", " "), check.isChecked(),
                                         lambda c=check: c.setChecked(not c.isChecked())))
            group.setAccessibleName("Filter by mod manager")
            row.addWidget(group)
        return row

    def _chip(self, text, on, action):
        button = QPushButton(text)
        button.setObjectName("chip")
        button.setCheckable(True)
        button.setChecked(on)
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(lambda: action())
        return button

    def clear_managers(self):
        for check in self.window.mod_manager_checks:
            with QSignalBlocker(check):
                check.setChecked(False)
        self.window._fill_mods()

    def _poster(self, tile, selected):
        poster = PosterTile(tile, self.pixmap_for(tile.name), selected)
        poster.clicked.connect(lambda: self.choose_game(tile.name))
        return poster

    def _card(self, c):
        control = getattr(self.window.page, "mods", None)
        view = self.window._shown_mods[c.facts.index] if 0 <= c.facts.index < len(self.window._shown_mods) else None
        entry = getattr(view.record, "catalog_entry", None) if view is not None else None
        tip = control.tooltip(entry) if control is not None and entry is not None else ""
        card = ModCard(c, self.pixmap_for(c.facts.game), tip)
        card.activated.connect(self.pick)
        card.opened.connect(self.open_details)
        card.reviewed.connect(self.review)
        return card

    def _banner(self, chosen, rows, h):
        name = chosen if chosen != gd.ALL_GAMES else "All your games"
        banner = Banner(self.pixmap_for(chosen), chosen, gd.bar_parts(h))
        lay = QHBoxLayout(banner)
        lay.setContentsMargins(22, 16, 18, 16)
        left = QVBoxLayout()
        left.setSpacing(3)
        eyebrow = QLabel("SELECTED GAME" if chosen != gd.ALL_GAMES else "EVERY GAME")
        eyebrow.setStyleSheet(f"color:{AMBER};font-size:10px;font-weight:700;letter-spacing:2px;background:transparent;")
        title = QLabel(name)
        title.setTextFormat(Qt.PlainText)
        title.setFont(_font(28, True))
        title.setStyleSheet("background:transparent;color:#F6FAFF;")
        size = sum(f.size or 0 for f in rows if f.is_mod)
        bits = [f"{h['count']} {'item' if h['count'] == 1 else 'items'}"]
        if size:
            bits.append(mods_sort.size_text(size) + " reported")
        manager = gd.managers_text(rows)
        if manager:
            bits.append("managed by " + manager)
        meta = QLabel(" · ".join(bits))
        meta.setTextFormat(Qt.PlainText)
        meta.setStyleSheet("background:transparent;color:#D7E1ED;")
        left.addWidget(eyebrow)
        left.addWidget(title)
        left.addWidget(meta)
        stats = QHBoxLayout()
        stats.setSpacing(22)
        stats.setContentsMargins(0, 8, 0, 0)
        for value, text, color in ((h["on"], "on", "#69DEA7"), (h["outdated"], "update listed", "#FFD08E"),
                                   (h["conflicts"], "sharing files", "#FF8796"), (h["off"], "off", "#F4F7FC")):
            if value is None:
                html = f"<span style='color:#A3B4C5'>{text}: not checked</span>"
            else:
                html = (f"<span style='font-size:20px;font-weight:800;color:{color}'>{value}</span> "
                        f"<span style='color:#C2CEDA'>{text}</span>")
            label = QLabel(html)
            label.setStyleSheet("background:transparent;")
            stats.addWidget(label)
        stats.addStretch(1)
        left.addLayout(stats)
        lay.addLayout(left, 1)
        buttons = QVBoxLayout()
        buttons.addStretch(1)
        row = QHBoxLayout()
        row.setSpacing(8)
        window = self.window
        row.addWidget(tool("Add Source", "download", window._add_mod_source))
        row.addWidget(tool("Scan for Mods", "refresh", window.start_scan, kind="primary"))
        buttons.addLayout(row)
        lay.addLayout(buttons)
        return banner


class ViewBar(QWidget):
    """Search plus the Gallery / List switch. The search box is the same search the list view uses."""

    def __init__(self, window, on_mode):
        super().__init__()
        self.window = window
        self.setObjectName("modViewBar")
        self.setStyleSheet(STYLE)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search mods, games or managers")
        self.search.setAccessibleName("Search mods")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(180)
        self.search.setMaximumWidth(340)
        self.search.setText(window.mod_search.text())
        self.search.textChanged.connect(self._typed)
        window.mod_search.textChanged.connect(self._mirror)
        row.addWidget(self.search, 1)
        row.addStretch(2)
        seg = QWidget()
        seg.setStyleSheet(f"background:{PANEL};border:1px solid {BORDER};border-radius:10px;")
        lay = QHBoxLayout(seg)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self.group = QButtonGroup(self)
        self.gallery_button, self.list_button = QPushButton("Gallery"), QPushButton("List")
        for button, mode in ((self.gallery_button, True), (self.list_button, False)):
            button.setObjectName("seg")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setAccessibleName(button.text() + " view")
            self.group.addButton(button)
            lay.addWidget(button)
            button.clicked.connect(lambda _=False, m=mode: on_mode(m))
        self.gallery_button.setChecked(True)
        row.addWidget(seg)

    def _typed(self, text):
        if _alive(self.window.mod_search) and self.window.mod_search.text() != text:
            self.window.mod_search.setText(text)

    def _mirror(self, text):
        if _alive(self.search) and self.search.text() != text:
            with QSignalBlocker(self.search):
                self.search.setText(text)

    def set_mode(self, gallery):
        with QSignalBlocker(self.group):
            self.gallery_button.setChecked(gallery)
            self.list_button.setChecked(not gallery)


# ---------------------------------------------------------------- hooks used by mods_page
def install(window, contents):
    """Add the gallery above the table. The table, filters and pager stay exactly as they were (List view)."""
    window._mod_gallery_on = True
    window.mod_gallery = ModsGallery(window)
    window.mod_view_bar = ViewBar(window, lambda on: set_mode(window, on))
    table_at = contents.indexOf(window.mod_table)
    contents.insertWidget(table_at, window.mod_gallery, 1)
    contents.insertWidget(0, window.mod_view_bar)
    window.mod_table.itemSelectionChanged.connect(lambda: sync(window))
    window.mod_gallery.hide()


def sync(window):
    gallery = getattr(window, "mod_gallery", None)
    if _alive(gallery) and gallery.isVisible():
        gallery.sync_selection()


def is_gallery(window):
    gallery = getattr(window, "mod_gallery", None)
    return _alive(gallery) and getattr(window, "_mod_gallery_on", False) and getattr(window, "_mod_tab", "Library") == "Library"


def set_mode(window, gallery_on):
    window._mod_gallery_on = bool(gallery_on)
    window._fill_mods(requested_page=window.mod_pager.page)


def apply_mode(window):
    """Show the gallery only on the Library tab; every other tab keeps its table and the filter column."""
    gallery, bar = getattr(window, "mod_gallery", None), getattr(window, "mod_view_bar", None)
    if not (_alive(gallery) and _alive(bar) and _alive(window.mod_table)):
        return False
    on = is_gallery(window)
    library = getattr(window, "_mod_tab", "Library") == "Library"
    bar.setVisible(library)
    bar.set_mode(getattr(window, "_mod_gallery_on", True))
    gallery.setVisible(on)
    window.mod_table.setVisible(not on)
    filters = window.mod_game_filters.parentWidget()
    if _alive(filters):
        filters.setVisible(not on)
    return on


def refresh(window):
    if apply_mode(window):
        window.mod_gallery.refresh()


def selection_text(window):
    shown = len(getattr(window, "_shown_mods", []))
    return f"{shown} shown · pick a card for its details"
