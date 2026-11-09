"""Painted graphics for the Mods tab: status pills, size bars, tile meters, the summary ring, the detail
picture, the load-order stack and the conflict and update cards.

Display only. Every number drawn here is a number the Mods tab already shows in words, so no picture
claims more than the text beside it. Mod managers and mod files are never touched.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen,
                           QRadialGradient)
from PySide6.QtWidgets import (QApplication, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QSizePolicy,
                               QStyle, QStyledItemDelegate, QStyleOptionViewItem, QVBoxLayout, QWidget)

from gg_desktop.mods_visuals import (SEGMENTS, hue_for, initials, lit_segments, order_window, pill_colors,
                                     share_parts, size_fraction)
from gg_desktop.widgets import label

PILL_ROLE = int(Qt.UserRole) + 40
BADGE_ROLE = PILL_ROLE + 1
BAR_ROLE = PILL_ROLE + 2
HUE_ROLE = PILL_ROLE + 3

TILE_GLOW = ("#df83ec", "#27dc74", "#f7b737", "#fa2245", "#9ca8bd", "#9bcde4")
SHARE_COLORS = ("#ff3048", "#df83ec", "#27dc74", "#f7b737", "#9bcde4")
TRACK = QColor("#1b2833")


def _font(base, pixels, bold=False):
    font = QFont(base)
    font.setPixelSize(pixels)
    font.setBold(bold)
    return font


# ---------------------------------------------------------------- table cells
class StatusDelegate(QStyledItemDelegate):
    """Draws the Status word as a pill, with a small badge for a recorded update and for a conflict."""

    def paint(self, painter, option, index):
        word = index.data(PILL_ROLE)
        if not word:
            super().paint(painter, option, index)
            return
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        widget = option.widget
        (widget.style() if widget else QApplication.style()).drawControl(QStyle.CE_ItemViewItem, opt, painter, widget)
        text_color, border, fill, dot = pill_colors(word)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        font = _font(option.font, 11, bold=True)
        painter.setFont(font)
        text_width = QFontMetrics(font).horizontalAdvance(word)
        height = 20.0
        top = option.rect.top() + (option.rect.height() - height) / 2
        pill = QRectF(option.rect.left() + 6, top, 8 + 7 + text_width + 10, height)
        pill.setRight(min(pill.right(), option.rect.right() - 2))
        path = QPainterPath()
        path.addRoundedRect(pill, 10, 10)
        painter.setPen(QPen(QColor(border), 1))
        painter.setBrush(QColor(fill))
        painter.drawPath(path)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(dot))
        painter.drawEllipse(QPointF(pill.left() + 11, pill.center().y()), 3.2, 3.2)
        painter.setPen(QColor(text_color))
        painter.drawText(QRectF(pill.left() + 19, pill.top(), pill.width() - 21, height),
                         Qt.AlignVCenter | Qt.AlignLeft, word)
        x = pill.right() + 5
        for kind in index.data(BADGE_ROLE) or ():
            if x + 16 > option.rect.right():
                break
            self._badge(painter, QRectF(x, option.rect.top() + (option.rect.height() - 16) / 2, 16, 16), kind, option.font)
            x += 19
        painter.restore()

    @staticmethod
    def _badge(painter, rect, kind, base_font):
        color = QColor("#eab464" if kind == "update" else "#ff8ea3")
        fill = QColor(color)
        fill.setAlpha(34)
        painter.setPen(QPen(color, 1))
        painter.setBrush(fill)
        painter.drawEllipse(rect)
        painter.setPen(QPen(color, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        c = rect.center()
        if kind == "update":
            painter.drawLine(QPointF(c.x(), c.y() + 3.5), QPointF(c.x(), c.y() - 3.5))
            painter.drawLine(QPointF(c.x() - 3.2, c.y() - 0.4), QPointF(c.x(), c.y() - 3.6))
            painter.drawLine(QPointF(c.x() + 3.2, c.y() - 0.4), QPointF(c.x(), c.y() - 3.6))
        else:
            painter.setFont(_font(base_font, 11, bold=True))
            painter.drawText(rect, Qt.AlignCenter, "!")


class SizeDelegate(QStyledItemDelegate):
    """The size text with a thin bar under it, sized against the largest mod on screen."""

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        fraction = index.data(BAR_ROLE)
        if fraction is None:
            return
        hue = (index.data(HUE_ROLE) or 0) / 360
        rect = option.rect
        track = QRectF(rect.left() + 6, rect.bottom() - 10, max(8, rect.width() - 12), 3)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#13202b"))
        painter.drawRoundedRect(track, 1.5, 1.5)
        bar = QRectF(track.left(), track.top(), track.width() * float(fraction), track.height())
        gradient = QLinearGradient(bar.topLeft(), bar.topRight())
        gradient.setColorAt(0, QColor.fromHslF(hue, .7, .45))
        gradient.setColorAt(1, QColor.fromHslF(hue, .9, .65))
        painter.setBrush(gradient)
        painter.drawRoundedRect(bar, 1.5, 1.5)
        painter.restore()


# ---------------------------------------------------------------- top of the page
class MeterBar(QWidget):
    """A 4px strip under a stat tile: lit segments, or a stack of shares. Hidden until it has something true to show."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(4)
        self._lit, self._color, self._parts = 0, QColor("#27dc74"), []
        self._mode = None
        self.hide()

    def segments(self, lit, color="#27dc74"):
        self._mode, self._lit, self._color = "segments", int(lit), QColor(color)
        self.show()
        self.update()

    def stack(self, parts, colors=SHARE_COLORS):
        self._mode, self._parts = "stack", [(f, QColor(colors[i % len(colors)])) for i, f in enumerate(parts)]
        self.setVisible(bool(parts))
        self.update()

    def clear(self):
        self._mode = None
        self.hide()

    def paintEvent(self, event):
        if not self._mode:
            return
        p = QPainter(self)
        p.setPen(Qt.NoPen)
        width = float(self.width())
        if self._mode == "segments":
            gap = 3.0
            each = (width - gap * (SEGMENTS - 1)) / SEGMENTS
            for i in range(SEGMENTS):
                p.setBrush(self._color if i < self._lit else TRACK)
                p.drawRect(QRectF(i * (each + gap), 0, each, 4))
        else:
            p.setBrush(TRACK)
            p.drawRoundedRect(QRectF(0, 0, width, 4), 2, 2)
            x = 0.0
            for fraction, color in self._parts:
                span = fraction * width
                p.setBrush(color)
                p.drawRect(QRectF(x, 0, max(1.0, span - 1), 4))
                x += span


def decorate_strip(strip):
    """Glow behind each tile icon and a meter slot under Turned On and Space Used. Returns {tile index: MeterBar}."""
    count = len(strip.cells)
    for i, color in enumerate(TILE_GLOW[:count]):
        effect = QGraphicsDropShadowEffect(strip.glyphs[i])
        effect.setBlurRadius(18)
        effect.setOffset(0, 0)
        glow = QColor(color)
        glow.setAlpha(170)
        effect.setColor(glow)
        strip.glyphs[i].setGraphicsEffect(effect)
    meters = {}
    for i in (1, 5):
        if i < count:
            meters[i] = MeterBar()
            strip.word_columns[i].addWidget(meters[i])
    strip.setFixedHeight(68)
    return meters


def refresh_meters(window, m, views):
    """Turned On meter from the on/total counts; Space Used meter from the sizes of the mods listed."""
    meters = getattr(window, "mod_meters", None)
    if not meters:
        return
    if 1 in meters:
        known = m["enabled"] or m["mixed"] or m["disabled"]
        if known and m["total"]:
            meters[1].segments(lit_segments(m["enabled"], m["total"]))
        else:
            meters[1].clear()
    if 5 in meters:
        parts = share_parts([getattr(v, "size", None) for v in views])
        meters[5].stack(parts) if parts else meters[5].clear()


class RingLabel(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(36, 36)
        self._on = self._total = 0
        self.hide()

    def set_counts(self, on, total):
        self._on, self._total = int(on), int(total)
        self.setVisible(self._total > 0)
        self.update()

    def paintEvent(self, event):
        if not self._total:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        box = QRectF(5, 5, 26, 26)
        p.setPen(QPen(TRACK, 4))
        p.drawEllipse(box)
        fraction = min(1.0, self._on / self._total)
        if fraction:
            pen = QPen(QColor("#3cda63"), 4)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawArc(box, 90 * 16, -int(360 * 16 * fraction))
        p.setPen(QColor("#f1f1f5"))
        p.setFont(_font(self.font(), 9 if self._total < 100 else 8, bold=True))
        p.drawText(QRectF(self.rect()), Qt.AlignCenter,
                   f"{self._on}/{self._total}" if self._total < 100 else f"{round(fraction * 100)}%")


class SummaryBar(QWidget):
    """The plain-words sentence with a ring showing how many mods are turned on. Behaves like the old label."""

    def __init__(self):
        super().__init__()
        box = QHBoxLayout(self)
        box.setContentsMargins(4, 0, 4, 0)
        box.setSpacing(10)
        self.ring = RingLabel()
        box.addWidget(self.ring, 0, Qt.AlignVCenter)
        self.words = label("", "subtle", wrap=True)
        self.words.setStyleSheet("font-size:13px;color:#d7dfe7;")
        box.addWidget(self.words, 1)

    def setText(self, text):
        self.words.setText(text)

    def text(self):
        return self.words.text()

    def set_counts(self, on, total):
        self.ring.set_counts(on, total)


# ---------------------------------------------------------------- detail panel
class ModHero(QWidget):
    """The picture at the top of a mod's details: its own colour, abstract bars, initials, version and state."""

    def __init__(self, name, version, word, tone):
        super().__init__()
        self.name, self.version, self.word, self.tone = str(name), str(version or ""), str(word or ""), tone
        self.setFixedHeight(92)
        self.setAccessibleName("Picture for " + self.name)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(.5, .5, -.5, -.5)
        hue = hue_for(self.name) / 360
        path = QPainterPath()
        path.addRoundedRect(r, 6, 6)
        p.setClipPath(path)
        base = QLinearGradient(r.topLeft(), r.bottomRight())
        base.setColorAt(0, QColor.fromHslF(hue, .5, .16))
        base.setColorAt(1, QColor("#060b0f"))
        p.fillRect(r, base)
        glow = QRadialGradient(QPointF(r.width() * .7, r.height() * .4), r.width() * .55)
        glow.setColorAt(0, QColor.fromHslF(hue, .8, .5, .45))
        glow.setColorAt(1, QColor.fromHslF(hue, .8, .5, 0.0))
        p.fillRect(r, glow)
        x = -30.0
        while x < r.width() + 30:
            t = max(0.0, min(1.0, (x / r.width() - .1) / .8))
            if t > 0:
                p.setPen(QPen(QColor.fromHslF(hue, .9, .7, .22 * t), 3))
                p.drawLine(QPointF(x, r.height()), QPointF(x + r.height() * .36, 0))
            x += 20
        p.setPen(QColor("#f1f4f7"))
        p.setFont(_font(self.font(), 30, bold=True))
        p.drawText(r, Qt.AlignCenter, initials(self.name))
        p.setClipping(False)
        p.setPen(QPen(QColor.fromHslF(hue, .7, .55, .5), 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        small = _font(self.font(), 10, bold=True)
        p.setFont(small)
        fm = QFontMetrics(small)
        if self.version:
            text = "v" + self.version.lstrip("vV")
            text = fm.elidedText(text, Qt.ElideRight, 90)
            w = fm.horizontalAdvance(text) + 16
            badge = QRectF(r.right() - w - 8, 8, w, 18)
            self._chip(p, badge)
            p.setPen(QColor("#ffffff"))
            p.drawText(badge, Qt.AlignCenter, text)
        if self.word:
            text = fm.elidedText(self.word, Qt.ElideRight, 120)
            w = fm.horizontalAdvance(text) + 28
            badge = QRectF(r.left() + 8, r.bottom() - 26, w, 18)
            self._chip(p, badge)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(self.tone))
            p.drawEllipse(QPointF(badge.left() + 11, badge.center().y()), 3.2, 3.2)
            p.setPen(QColor(self.tone))
            p.drawText(QRectF(badge.left() + 19, badge.top(), badge.width() - 21, 18), Qt.AlignVCenter | Qt.AlignLeft, text)

    @staticmethod
    def _chip(p, rect):
        p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        p.setBrush(QColor(2, 6, 9, 150))
        p.drawRoundedRect(rect, 9, 9)


class OrderStack(QWidget):
    """A few neighbours around this mod in the saved load order, joined by a line. rows: (position, name, is_this_mod)."""
    ROW, GAP, CAP = 24, 3, 16

    def __init__(self, rows, first, last):
        super().__init__()
        self.rows, self.first, self.last = list(rows), bool(first), bool(last)
        self.setFixedHeight(self.CAP * 2 + len(self.rows) * (self.ROW + self.GAP))
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setMinimumWidth(0)
        self.setAccessibleName("Neighbours in the saved load order")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = float(self.width())
        small = _font(self.font(), 10)
        p.setFont(small)
        caption = QColor("#8c99a6")
        p.setPen(caption)
        p.drawText(QRectF(14, 0, w - 14, self.CAP), Qt.AlignVCenter | Qt.AlignLeft,
                   "Loads first" if self.first else "Loads earlier")
        self._arrow(p, 6, self.CAP / 2, down=True, color=caption)
        top = self.CAP
        if self.rows:
            line = QLinearGradient(0, top, 0, top + len(self.rows) * (self.ROW + self.GAP))
            line.setColorAt(0, QColor("#1a2530"))
            line.setColorAt(.5, QColor("#ff2847"))
            line.setColorAt(1, QColor("#1a2530"))
            p.setPen(QPen(QBrush(line), 2))
            p.drawLine(QPointF(16, top + self.ROW / 2), QPointF(16, top + (len(self.rows) - 1) * (self.ROW + self.GAP) + self.ROW / 2))
        for i, (position, name, mine) in enumerate(self.rows):
            y = top + i * (self.ROW + self.GAP)
            box = QRectF(.5, y + .5, w - 1, self.ROW - 1)
            p.setPen(QPen(QColor("#ff2847" if mine else "#1b2833"), 1))
            p.setBrush(QColor("#2a0f18" if mine else "#070d12"))
            p.drawRoundedRect(box, 5, 5)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#b60020" if mine else "#1a2530"))
            p.drawEllipse(QPointF(16, y + self.ROW / 2), 8, 8)
            p.setPen(QColor("#ffffff" if mine else "#cfd8e0"))
            p.setFont(_font(self.font(), 8, bold=True))
            p.drawText(QRectF(8, y, 16, self.ROW), Qt.AlignCenter, str(position))
            p.setFont(_font(self.font(), 11, bold=mine))
            p.setPen(QColor("#f1f4f7" if mine else "#d5dde5"))
            text = QFontMetrics(p.font()).elidedText(str(name), Qt.ElideRight, int(w - 40))
            p.drawText(QRectF(32, y, w - 38, self.ROW), Qt.AlignVCenter | Qt.AlignLeft, text)
        bottom = top + len(self.rows) * (self.ROW + self.GAP)
        p.setFont(small)
        p.setPen(caption)
        p.drawText(QRectF(14, bottom, w - 14, self.CAP), Qt.AlignVCenter | Qt.AlignLeft,
                   "Loads last" if self.last else "Loads later")
        self._arrow(p, 6, bottom + self.CAP / 2, down=False, color=QColor("#ff8ea3"))

    @staticmethod
    def _arrow(p, x, y, *, down, color):
        p.setPen(QPen(color, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        d = 1 if down else -1
        p.drawLine(QPointF(x, y - 3.5 * d), QPointF(x, y + 3.5 * d))
        p.drawLine(QPointF(x - 3, y + 0.5 * d), QPointF(x, y + 3.5 * d))
        p.drawLine(QPointF(x + 3, y + 0.5 * d), QPointF(x, y + 3.5 * d))


class OverlapGlyph(QWidget):
    """Two overlapping circles with the number of conflict findings in the middle."""

    def __init__(self, number):
        super().__init__()
        self.number = str(number)
        self.setFixedSize(70, 44)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        left, right = QColor("#ff2847"), QColor("#4dd2e9")
        for color, cx in ((left, 24), (right, 46)):
            fill = QColor(color)
            fill.setAlpha(55)
            p.setPen(QPen(color, 1.2))
            p.setBrush(fill)
            p.drawEllipse(QPointF(cx, 22), 17, 17)
        p.setPen(QColor("#ffffff"))
        p.setFont(_font(self.font(), 12, bold=True))
        p.drawText(QRectF(0, 0, 70, 44), Qt.AlignCenter, self.number)


class VersionArrow(QWidget):
    """Installed version, an arrow, then the version the mod manager recorded as newer."""

    def __init__(self, installed, newest):
        super().__init__()
        self.installed, self.newest = str(installed), str(newest)
        self.setFixedSize(190, 26)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        font = _font(self.font(), 11, bold=True)
        fm = QFontMetrics(font)
        p.setFont(font)
        old = fm.elidedText(self.installed, Qt.ElideRight, 70)
        new = fm.elidedText(self.newest, Qt.ElideRight, 70)
        w1, w2 = fm.horizontalAdvance(old) + 20, fm.horizontalAdvance(new) + 20
        a = QRectF(1, 2, w1, 22)
        b = QRectF(a.right() + 36, 2, w2, 22)
        p.setPen(QPen(QColor("#4a3a1a"), 1))
        p.setBrush(QColor("#0e0b06"))
        p.drawRoundedRect(a, 11, 11)
        p.setPen(QColor("#b9a77a"))
        p.drawText(a, Qt.AlignCenter, old)
        amber = QColor("#eab464")
        p.setPen(QPen(amber, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        y, x0, x1 = a.center().y(), a.right() + 7, b.left() - 7
        p.drawLine(QPointF(x0, y), QPointF(x1, y))
        p.drawLine(QPointF(x1 - 5, y - 4), QPointF(x1, y))
        p.drawLine(QPointF(x1 - 5, y + 4), QPointF(x1, y))
        glow = QColor(amber)
        glow.setAlpha(36)
        p.setPen(QPen(amber, 1))
        p.setBrush(glow)
        p.drawRoundedRect(b, 11, 11)
        p.setPen(QColor("#ffd596"))
        p.drawText(b, Qt.AlignCenter, new)


def _card(border, fill):
    frame = QFrame()
    frame.setObjectName("modCard")
    frame.setStyleSheet(f"QFrame#modCard{{border:1px solid {border};border-radius:6px;background:{fill};}}")
    return frame


def _text(text, color, size, bold=False):
    item = label(text, "", wrap=True)
    item.setMinimumWidth(0)
    item.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    item.setStyleSheet(f"color:{color};font-size:{size}px;{'font-weight:700;' if bold else ''}border:0;background:transparent;")
    return item


def conflict_card(found, others, limited):
    """found: this mod's findings (kind, detail). others: names of the other mods involved."""
    frame = _card("#6b2433", "#14090d")
    box = QHBoxLayout(frame)
    box.setContentsMargins(8, 7, 9, 7)
    box.setSpacing(8)
    box.addWidget(OverlapGlyph(len(found)), 0, Qt.AlignTop)
    words = QVBoxLayout()
    words.setSpacing(2)
    if others:
        title = "Conflict with " + ", ".join(others[:2]) + (f" and {len(others) - 2} more" if len(others) > 2 else "")
    else:
        title = "Conflict found"
    words.addWidget(_text(title, "#ff8ea3", 11, True))
    detail = (found[0].detail or found[0].kind)[:220]
    if len(found) > 1:
        detail += f" ({len(found) - 1} more finding{'s' if len(found) > 2 else ''})"
    words.addWidget(_text(detail, "#e2b9c2", 10))
    if limited:
        words.addWidget(_text("The check was partial, so there may be more.", "#c58d99", 10))
    box.addLayout(words, 1)
    frame.setToolTip("Two mods that change the same file. The one that loads later wins. Game Grave never reorders mods.")
    return frame


def update_card(installed, newest):
    frame = _card("#6b5120", "#15110a")
    box = QVBoxLayout(frame)
    box.setContentsMargins(9, 7, 9, 7)
    box.setSpacing(4)
    box.addWidget(_text("A newer version is recorded", "#eab464", 11, True))
    box.addWidget(VersionArrow(installed or "unknown", newest), 0, Qt.AlignLeft)
    box.addWidget(_text("Your mod manager recorded the newer version. Game Grave does not go online to check.", "#d9c9a0", 10))
    return frame


# ---------------------------------------------------------------- wiring helpers
def install_delegates(table):
    table._gg_status_delegate = StatusDelegate(table)
    table._gg_size_delegate = SizeDelegate(table)
    table.setItemDelegateForColumn(4, table._gg_size_delegate)
    table.setItemDelegateForColumn(5, table._gg_status_delegate)


def decorate_library(window, control):
    """Hand the painters the facts for each visible row. The cell text itself is never changed."""
    from PySide6.QtCore import QSignalBlocker
    table = window.mod_table
    views = getattr(window, "_shown_mods", [])
    biggest = max((v.size for v in views if v.size), default=0)
    scanned = getattr(window, "_mod_updates_scanned", False)
    updates = getattr(window, "_mod_updates", {}) if scanned else {}
    with QSignalBlocker(table):
        for i, view in enumerate(views):
            entry = getattr(view.record, "catalog_entry", None)
            cell = table.item(i, 5)
            if cell is not None:
                cell.setData(PILL_ROLE, cell.text())
                badges = []
                info = updates.get(entry.key) if entry else None
                if info is not None and info.outdated:
                    badges.append("update")
                if control is not None and entry is not None and control.findings(entry):
                    badges.append("conflict")
                cell.setData(BADGE_ROLE, badges)
                notes = {"update": "A newer version is recorded by your mod manager.",
                         "conflict": "Another mod changes the same files. The one that loads later wins."}
                if badges:
                    cell.setToolTip(cell.toolTip() + "\n" + "\n".join(notes[b] for b in badges))
            size_cell = table.item(i, 4)
            if size_cell is not None:
                fraction = size_fraction(view.size, biggest)
                size_cell.setData(BAR_ROLE, fraction)
                size_cell.setData(HUE_ROLE, hue_for(view.name))
    table.viewport().update()


def order_rows(rows, position):
    """The neighbours of `position` in `rows` [(pos, entry, marker)], marked, plus first and last flags."""
    count = len(rows)
    start, end = order_window(position, count)
    shown = [(pos, entry.name, pos == position) for pos, entry, _m in rows[start - 1:end]]
    return shown, start == 1, end == count
