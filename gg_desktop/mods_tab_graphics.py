"""Painted graphics for the Mods sub-tabs: Mod Radar, Load Order, Profiles, Conflicts and Cleanup.

Display only. Every picture here is drawn from a number or a word the tab already shows, so none of
them claims more than the text beside it: chips for counts, a thin on/off bar under each profile, a rail
for the load-order position, a ring for how many mods a profile turns on, cards for the coverage lines.
Cell text is never changed, mod managers and mod files are never touched, and nothing is called safe.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QSizePolicy, QStyle, QStyledItemDelegate, QStyleOptionViewItem,
                               QVBoxLayout, QWidget, QApplication)

from gg_desktop import mods_graphics as graphics
from gg_desktop.mods_graphics import BAR_ROLE, HUE_ROLE, PILL_ROLE, SHARE_COLORS, TRACK, _card, _font, _text
from gg_desktop.mods_visuals import count_tone, hue_for, mix_parts, rail_fraction, size_fraction, split_fractions

TONE_ROLE = int(Qt.UserRole) + 60
FRACTION_ROLE = TONE_ROLE + 1
SPLIT_ROLE = TONE_ROLE + 2

# text, border, fill
CHIPS = {
    "green": ("#7bf0a6", "#1d5a38", "#0b1f14"),
    "amber": ("#eab464", "#6b5120", "#1a140a"),
    "red": ("#ff8ea3", "#6b2433", "#14090d"),
    "cyan": ("#8fdcf0", "#1d5566", "#08181f"),
    "muted": ("#9aa7b3", "#2a3b4b", "#0c141b"),
}
DOTS = {"green": "#3cda63", "amber": "#eab464", "red": "#ff4d66", "cyan": "#4dd2e9", "muted": "#8794a1"}


def _base(delegate, painter, option, index):
    """Draw the row background and selection, but not the text."""
    opt = QStyleOptionViewItem(option)
    delegate.initStyleOption(opt, index)
    opt.text = ""
    widget = option.widget
    (widget.style() if widget else QApplication.style()).drawControl(QStyle.CE_ItemViewItem, opt, painter, widget)


# ---------------------------------------------------------------- table cells
class ChipDelegate(QStyledItemDelegate):
    """The cell text inside a small rounded chip, tinted by the tone the row was given."""

    def paint(self, painter, option, index):
        tone = index.data(TONE_ROLE)
        text = index.data(Qt.DisplayRole)
        if not tone or text in (None, ""):
            super().paint(painter, option, index)
            return
        _base(self, painter, option, index)
        color, border, fill = CHIPS.get(tone, CHIPS["muted"])
        font = _font(option.font, 11, bold=True)
        text = str(text)
        width = min(option.rect.width() - 8, QFontMetrics(font).horizontalAdvance(text) + 18)
        height = 20.0
        chip = QRectF(option.rect.left() + 4, option.rect.top() + (option.rect.height() - height) / 2,
                      max(22.0, width), height)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(border), 1))
        painter.setBrush(QColor(fill))
        painter.drawRoundedRect(chip, 10, 10)
        painter.setFont(font)
        painter.setPen(QColor(color))
        painter.drawText(chip, Qt.AlignCenter, QFontMetrics(font).elidedText(text, Qt.ElideRight, int(chip.width()) - 8))
        painter.restore()


class DotDelegate(QStyledItemDelegate):
    """A coloured dot in front of the text; the text keeps its own colour."""

    def paint(self, painter, option, index):
        tone = index.data(TONE_ROLE)
        if not tone:
            super().paint(painter, option, index)
            return
        _base(self, painter, option, index)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        brush = index.data(Qt.ForegroundRole)
        painter.setPen(brush.color() if brush is not None and hasattr(brush, "color") else QColor("#d7dfe7"))
        painter.setFont(option.font)
        room = max(10, option.rect.width() - 22)
        painter.drawText(QRectF(option.rect.left() + 18, option.rect.top(), room, option.rect.height()),
                         Qt.AlignVCenter | Qt.AlignLeft,
                         QFontMetrics(option.font).elidedText(str(index.data(Qt.DisplayRole) or ""), Qt.ElideRight, int(room)))
        dot = QColor(DOTS.get(tone, DOTS["muted"]))
        glow = QColor(dot)
        glow.setAlpha(60)
        center = QPointF(option.rect.left() + 9, option.rect.center().y())
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(center, 5.5, 5.5)
        painter.setBrush(dot)
        painter.drawEllipse(center, 3.2, 3.2)
        painter.restore()


class NameBarDelegate(QStyledItemDelegate):
    """A profile's name with a thin bar under it: how much of its saved list is on, off and unmarked."""

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        split = index.data(SPLIT_ROLE)
        if not split:
            return
        track = QRectF(option.rect.left() + 6, option.rect.bottom() - 9, max(10, option.rect.width() - 14), 4)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#13202b"))
        painter.drawRoundedRect(track, 2, 2)
        x = track.left()
        for share, color in zip(split, ("#3cda63", "#5b6874", "#eab464")):
            if share <= 0:
                continue
            piece = QRectF(x, track.top(), track.width() * share, track.height())
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(piece.adjusted(0, 0, -0.6, 0), 2, 2)
            x += piece.width()
        painter.restore()


class OrderDelegate(QStyledItemDelegate):
    """The load-order number inside a ring, with a small rail below showing how early or late it loads."""

    def paint(self, painter, option, index):
        fraction = index.data(FRACTION_ROLE)
        text = index.data(Qt.DisplayRole)
        if text in (None, ""):
            super().paint(painter, option, index)
            return
        _base(self, painter, option, index)
        rect = option.rect
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        center = QPointF(rect.center().x(), rect.top() + rect.height() / 2 - 2)
        painter.setPen(QPen(QColor("#8fdcf0" if fraction is not None else "#2a3b4b"), 1.2))
        painter.setBrush(QColor("#08181f" if fraction is not None else "#0c141b"))
        painter.drawEllipse(center, 10, 10)
        painter.setFont(_font(option.font, 11, bold=True))
        painter.setPen(QColor("#e8f7fb" if fraction is not None else "#9aa7b3"))
        painter.drawText(QRectF(center.x() - 12, center.y() - 10, 24, 20), Qt.AlignCenter, str(text))
        if fraction is not None:
            track = QRectF(rect.center().x() - 22, rect.bottom() - 7, 44, 2)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#1b2833"))
            painter.drawRoundedRect(track, 1, 1)
            painter.setBrush(QColor("#4dd2e9"))
            painter.drawEllipse(QPointF(track.left() + track.width() * float(fraction), track.center().y()), 2.6, 2.6)
        painter.restore()


# ---------------------------------------------------------------- which painter draws which column
def _delegates(table):
    if not hasattr(table, "_gg_tab_delegates"):
        table._gg_tab_delegates = {
            "plain": QStyledItemDelegate(table), "chip": ChipDelegate(table), "dot": DotDelegate(table),
            "name": NameBarDelegate(table), "order": OrderDelegate(table),
        }
    return table._gg_tab_delegates


COLUMNS = {
    "Mod Radar": {2: "chip", 3: "dot"},
    "Load Order": {2: "order", 3: "status", 4: "chip"},
    "Profiles": {1: "name", 3: "chip", 4: "chip", 5: "chip"},
    "Conflicts": {1: "dot", 3: "chip", 4: "chip"},
    "Cleanup": {3: "size", 4: "chip"},
}


def use_for(table, tab):
    """Point every column at its painter for this tab; Library gets back its own status and size painters."""
    painters = _delegates(table)
    chosen = {4: "size", 5: "status"} if tab == "Library" else COLUMNS.get(tab, {})
    for column in range(table.columnCount()):
        kind = chosen.get(column, "plain")
        if kind == "status":
            if not hasattr(table, "_gg_status_delegate"):
                table._gg_status_delegate = graphics.StatusDelegate(table)
            delegate = table._gg_status_delegate
        elif kind == "size":
            if not hasattr(table, "_gg_size_delegate"):
                table._gg_size_delegate = graphics.SizeDelegate(table)
            delegate = table._gg_size_delegate
        else:
            delegate = painters[kind]
        table.setItemDelegateForColumn(column, delegate)
    table.viewport().update()


def _put(table, row_index, column, role, value):
    cell = table.item(row_index, column)
    if cell is not None:
        cell.setData(role, value)


def decorate(window):
    """Hand the painters the facts for each visible row of a sub-tab. Cell text is never changed."""
    table = window.mod_table
    tab = window._mod_tab
    rows = getattr(window, "_mod_tab_rows", [])
    if tab == "Library" or not rows:
        return
    if tab == "Mod Radar":
        for i, item in enumerate(rows):
            _put(table, i, 2, TONE_ROLE, "green" if item.payload.get("custom") else "cyan")
            pending = "next scan" in str(item.payload.get("state", "")).casefold()
            _put(table, i, 3, TONE_ROLE, "amber" if pending else "cyan")
    elif tab == "Load Order":
        positions = []
        for item in rows:
            try:
                positions.append(int(item.cells[1]))
            except (TypeError, ValueError):
                pass
        count = max(positions, default=0)
        for i, item in enumerate(rows):
            _put(table, i, 2, FRACTION_ROLE, rail_fraction(item.cells[1], count))
            _put(table, i, 2, TONE_ROLE, "cyan")
            _put(table, i, 3, PILL_ROLE, item.cells[2])
            _put(table, i, 4, TONE_ROLE, "muted")
    elif tab == "Profiles":
        for i, item in enumerate(rows):
            p = item.payload
            _put(table, i, 1, SPLIT_ROLE, split_fractions(p["enabled"], p["disabled"], p.get("unknown", 0)))
            _put(table, i, 3, TONE_ROLE, count_tone(item.cells[2], "green"))
            _put(table, i, 4, TONE_ROLE, "muted")
            _put(table, i, 5, TONE_ROLE, count_tone(item.cells[4], "amber"))
    elif tab == "Conflicts":
        for i, item in enumerate(rows):
            _put(table, i, 1, TONE_ROLE, "amber")
            _put(table, i, 3, TONE_ROLE, count_tone(item.cells[2], "amber"))
            _put(table, i, 4, TONE_ROLE, count_tone(item.cells[3], "amber"))
    elif tab == "Cleanup":
        biggest = max((item.payload.get("size") or 0 for item in rows), default=0)
        for i, item in enumerate(rows):
            size = item.payload.get("size")
            _put(table, i, 3, BAR_ROLE, size_fraction(size, biggest))
            _put(table, i, 3, HUE_ROLE, hue_for(item.payload.get("name", "")))
            _put(table, i, 4, TONE_ROLE, "muted" if item.cells[3] == "Protected" else "amber")
    table.viewport().update()


# ---------------------------------------------------------------- empty table
class EmptyState(QWidget):
    """A quiet picture over a table with no rows, so the big empty area explains itself."""

    def __init__(self, table):
        super().__init__(table.viewport())
        self.table = table
        self.title = ""
        self.sub = ""
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        table.viewport().installEventFilter(self)
        self.hide()

    def eventFilter(self, source, event):
        if event.type() == QEvent.Resize:
            self.setGeometry(self.table.viewport().rect())
        return False

    def show_for(self, title, sub):
        self.title, self.sub = title, sub
        self.setGeometry(self.table.viewport().rect())
        self.show()
        self.raise_()
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2 - 24
        # three stacked slabs, the top one lit, like a tidy pile of folders
        for i, (dy, color) in enumerate(((26, "#13202b"), (13, "#1b2d3a"), (0, "#27485a"))):
            slab = QRectF(cx - 46 + i * 2, cy + dy - 8, 92 - i * 4, 22)
            path = QPainterPath()
            path.addRoundedRect(slab, 6, 6)
            gradient = QLinearGradient(slab.topLeft(), slab.bottomLeft())
            gradient.setColorAt(0, QColor(color).lighter(125))
            gradient.setColorAt(1, QColor(color))
            p.setPen(QPen(QColor("#33566a" if i == 2 else "#21313d"), 1))
            p.setBrush(gradient)
            p.drawPath(path)
        glow = QColor("#4dd2e9")
        glow.setAlpha(50)
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QPointF(cx, cy + 3), 9, 9)
        p.setPen(QPen(QColor("#8fdcf0"), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawLine(QPointF(cx - 4, cy + 3), QPointF(cx - 1, cy + 6))
        p.drawLine(QPointF(cx - 1, cy + 6), QPointF(cx + 5, cy))
        p.setPen(QColor("#d7dfe7"))
        p.setFont(_font(self.font(), 14, bold=True))
        p.drawText(QRectF(0, cy + 52, self.width(), 22), Qt.AlignCenter, self.title)
        p.setPen(QColor("#8794a1"))
        p.setFont(_font(self.font(), 11))
        p.drawText(QRectF(24, cy + 76, self.width() - 48, 40), Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, self.sub)


EMPTY_TITLES = {
    "Mod Radar": ("No mod sources listed", "Use Scan for Mods, or Add Source for a folder of your own."),
    "Load Order": ("No saved load order", "Choose a saved profile above."),
    "Profiles": ("No saved profiles listed", "Game Grave reads Mod Organizer 2 profiles after Scan for Mods."),
    "Conflicts": ("No findings listed", "Run a conflict check from Actions, or choose another profile."),
    "Cleanup": ("Nothing to review here", "Game Grave lists items to look at. It removes nothing from this tab."),
}


def refresh_empty(window):
    table = window.mod_table
    state = getattr(table, "_gg_empty_state", None)
    if state is None:
        state = table._gg_empty_state = EmptyState(table)
    tab = window._mod_tab
    if tab == "Library" or table.rowCount() > 0 or tab not in EMPTY_TITLES:
        state.hide()
        return
    if window.mod_search.text().strip():
        state.show_for("Nothing matches the search", "Clear the search box to see every row.")
    else:
        state.show_for(*EMPTY_TITLES[tab])


# ---------------------------------------------------------------- detail pictures
class SplitRing(QWidget):
    """A ring of how many mods a profile turns on, off and leaves unmarked, with the counts beside it."""

    def __init__(self, on, off, unknown=0):
        super().__init__()
        self.counts = (int(on or 0), int(off or 0), int(unknown or 0))
        self.setFixedHeight(92)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setMinimumWidth(0)
        self.setAccessibleName(f"{self.counts[0]} on, {self.counts[1]} off, {self.counts[2]} unmarked")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        box = QRectF(8, 8, 76, 76)
        p.setPen(QPen(TRACK, 9))
        p.drawEllipse(box)
        shares = split_fractions(*self.counts)
        colors = ("#3cda63", "#5b6874", "#eab464")
        if shares:
            angle = 90 * 16
            for share, color in zip(shares, colors):
                if share <= 0:
                    continue
                span = -int(360 * 16 * share)
                pen = QPen(QColor(color), 9)
                pen.setCapStyle(Qt.FlatCap)
                p.setPen(pen)
                p.drawArc(box, angle, span)
                angle += span
        total = sum(self.counts)
        p.setPen(QColor("#f1f1f5"))
        p.setFont(_font(self.font(), 18, bold=True))
        p.drawText(QRectF(8, 22, 76, 28), Qt.AlignCenter, str(self.counts[0]))
        p.setPen(QColor("#8794a1"))
        p.setFont(_font(self.font(), 10))
        p.drawText(QRectF(8, 48, 76, 18), Qt.AlignCenter, f"of {total} on" if total else "no mods")
        y = 18
        for (name, count), color in zip((("On", self.counts[0]), ("Off", self.counts[1]), ("Unmarked", self.counts[2])), colors):
            if name == "Unmarked" and not count:
                continue
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(color))
            p.drawEllipse(QPointF(106, y + 6), 4, 4)
            p.setPen(QColor("#d7dfe7"))
            p.setFont(_font(self.font(), 12, bold=True))
            p.drawText(QRectF(118, y - 3, 40, 18), Qt.AlignVCenter | Qt.AlignLeft, str(count))
            p.setPen(QColor("#9aa7b3"))
            p.setFont(_font(self.font(), 11))
            p.drawText(QRectF(134, y - 3, max(10, self.width() - 136), 18), Qt.AlignVCenter | Qt.AlignLeft, name)
            y += 22


class MixBar(QWidget):
    """One stacked bar of how many sources each manager or kind has, with a legend. Counts are real counts."""

    def __init__(self, counts):
        super().__init__()
        self.parts = mix_parts(counts)
        self.setFixedHeight(18 + 17 * max(1, len(self.parts)))
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setMinimumWidth(0)
        self.setAccessibleName("Sources by type: " + ", ".join(f"{n} {c}" for n, c, _s in self.parts))

    def paintEvent(self, event):
        if not self.parts:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        track = QRectF(1, 2, max(10, self.width() - 2), 8)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#13202b"))
        p.drawRoundedRect(track, 4, 4)
        x = track.left()
        for (name, count, share), color in zip(self.parts, SHARE_COLORS):
            piece = QRectF(x, track.top(), track.width() * share, track.height())
            p.setBrush(QColor(color))
            p.drawRoundedRect(piece.adjusted(0, 0, -1, 0), 3, 3)
            x += piece.width()
        y = 20
        for (name, count, _share), color in zip(self.parts, SHARE_COLORS):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(color))
            p.drawEllipse(QPointF(6, y + 7), 3.5, 3.5)
            p.setPen(QColor("#d7dfe7"))
            p.setFont(_font(self.font(), 11, bold=True))
            p.drawText(QRectF(16, y, 30, 15), Qt.AlignVCenter | Qt.AlignLeft, str(count))
            p.setPen(QColor("#9aa7b3"))
            p.setFont(_font(self.font(), 11))
            text = QFontMetrics(p.font()).elidedText(name, Qt.ElideRight, max(10, self.width() - 52))
            p.drawText(QRectF(44, y, max(10, self.width() - 46), 15), Qt.AlignVCenter | Qt.AlignLeft, text)
            y += 17


def coverage_card(name, text, tone):
    """One coverage fact as a card with a coloured edge: cyan for plain facts, amber where coverage is partial."""
    warn = tone == "warn"
    edge, fill, head = ("#6b5120", "#15110a", "#eab464") if warn else ("#1d5566", "#08141a", "#8fdcf0")
    frame = _card(edge, fill)
    box = QVBoxLayout(frame)
    box.setContentsMargins(9, 6, 9, 7)
    box.setSpacing(2)
    box.addWidget(_text(name, head, 11, True))
    item = _text(text, "#d7dfe7" if not warn else "#e6d3a8", 10)
    box.addWidget(item)
    return frame


class FindingBanner(QFrame):
    """The top of a conflict finding: two overlapping circles and the real counts as chips."""

    def __init__(self, mods, files):
        super().__init__()
        self.setObjectName("modCard")
        self.setStyleSheet("QFrame#modCard{border:1px solid #6b5120;border-radius:6px;background:#15110a;}")
        box = QHBoxLayout(self)
        box.setContentsMargins(8, 7, 9, 7)
        box.setSpacing(10)
        glyph = graphics.OverlapGlyph(mods)
        glyph.setToolTip(f"{mods} mod{'s' if mods != 1 else ''} involved")
        box.addWidget(glyph, 0, Qt.AlignVCenter)
        words = QVBoxLayout()
        words.setSpacing(3)
        words.addWidget(_text(f"{mods} mod{'s' if mods != 1 else ''} involved", "#eab464", 12, True))
        words.addWidget(_text(f"{files} file{'s' if files != 1 else ''} listed", "#d9c9a0", 10))
        box.addLayout(words, 1)
        self.setAccessibleName(f"{mods} mods involved, {files} files listed")


def empty_note(text):
    frame = _card("#21313d", "#0a1218")
    box = QVBoxLayout(frame)
    box.setContentsMargins(9, 8, 9, 8)
    box.addWidget(_text(text, "#9aa7b3", 10))
    return frame
