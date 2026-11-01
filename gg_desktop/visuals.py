"""Crimson Command visual system for approved Game Grave tabs.

High-DPI vector graphics, no remote assets, fictional game covers, fake sizes,
stock imagery or animation. Every visual component is a normal Qt Widget and
can be painted at arbitrary DPI. Colors and type match the main Crimson shell.

The page *chrome* is shared. The artwork and information structure are
distinct per feature, to make the tabs useful to visual learners.
"""
from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen,
    QPolygonF, QRadialGradient,
)
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

RED = QColor("#F84359")
CYAN = QColor("#43D6F2")
WHITE = QColor("#F2F7FA")
MUTED = QColor("#9DAEBF")
NAVY = QColor("#0D1924")
BORDER = QColor("#2A4251")


def _pen(color, width=2):
    return QPen(QColor(color), width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)


def _line(p, a, b, color=CYAN, width=2):
    p.setPen(_pen(color, width))
    p.drawLine(QPointF(*a), QPointF(*b))


def _round(p, r, fill, stroke=None, radius=8):
    p.setPen(_pen(stroke) if stroke is not None else Qt.NoPen)
    p.setBrush(QColor(fill))
    p.drawRoundedRect(QRectF(*r), radius, radius)


def _folder(p, x, y, w=112, h=70, color=CYAN):
    shade = QColor(color)
    _round(p, (x + 6, y - 12, w * .47, 21), "#153747", shade, 5)
    _round(p, (x, y, w, h), "#112C3A", shade, 8)
    _line(p, (x + 11, y + 18), (x + w - 11, y + 18), shade, 1)


def _controller(p, cx, cy, scale=1):
    p.save()
    p.translate(cx, cy)
    p.scale(scale, scale)
    path = QPainterPath()
    path.moveTo(-69, 12)
    path.cubicTo(-82, -8, -71, -36, -44, -38)
    path.cubicTo(-15, -42, 15, -42, 44, -38)
    path.cubicTo(71, -36, 82, -8, 69, 12)
    path.cubicTo(58, 36, 38, 12, 21, 5)
    path.lineTo(-21, 5)
    path.cubicTo(-38, 12, -58, 36, -69, 12)
    p.setBrush(QColor("#102633"))
    p.setPen(_pen(CYAN, 3))
    p.drawPath(path)
    _line(p, (-37, -19), (-37, 2), CYAN, 3)
    _line(p, (-48, -9), (-26, -9), CYAN, 3)
    p.setBrush(RED)
    p.setPen(Qt.NoPen)
    for x, y in ((34, -20), (46, -9), (22, -9), (34, 2)):
        p.drawEllipse(QPointF(x, y), 3.5, 3.5)
    p.restore()


def _gear(p, cx, cy, r, color=CYAN):
    p.save()
    p.translate(cx, cy)
    p.setPen(_pen(color, 3))
    p.setBrush(QColor("#102D3C"))
    points = []
    for i in range(24):
        a = -math.pi / 2 + 2 * math.pi * i / 24
        level = r * (1.09 if i % 3 == 0 else .79 if i % 3 == 1 else 1.0)
        points.append(QPointF(math.cos(a) * level, math.sin(a) * level))
    p.drawPolygon(QPolygonF(points))
    p.setBrush(QColor("#07121D"))
    p.drawEllipse(QPointF(0, 0), r * .35, r * .35)
    p.restore()


class SceneHeader(QFrame):
    """Compact cinematic header with uniquely drawn scene for each tab."""

    def __init__(self, kind: str, title: str, subtitle: str, *, note: str = ""):
        super().__init__()
        self.kind = kind
        self.setObjectName("sceneHeader")
        self.setMinimumHeight(184)
        self.setMaximumHeight(211)
        self.setAccessibleName(title + ". " + subtitle)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 19, 18, 16)
        layout.setSpacing(10)
        words = QVBoxLayout()
        words.setSpacing(5)
        kicker = QLabel(note.upper() if note else "GAME GRAVE  /  CRIMSON COMMAND")
        kicker.setObjectName("sceneKicker")
        words.addWidget(kicker)
        heading = QLabel(title)
        heading.setObjectName("sceneTitle")
        heading.setWordWrap(True)
        words.addWidget(heading)
        subtitle_label = QLabel(subtitle)
        subtitle_label.setWordWrap(True)
        subtitle_label.setObjectName("sceneDescription")
        subtitle_label.setMaximumWidth(470)
        words.addWidget(subtitle_label)
        words.addStretch(1)
        layout.addLayout(words, 1)
        spacer = QWidget()
        spacer.setFixedWidth(330)
        spacer.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(spacer)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        bg = QLinearGradient(0, 0, w, h)
        bg.setColorAt(0, QColor("#101A25"))
        bg.setColorAt(.53, QColor("#0A121B"))
        bg.setColorAt(1, QColor("#091621"))
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(QRectF(0, 0, w, h), 11, 11)
        p.save()
        p.setClipRect(QRectF(w * .52, 1, w * .48 - 1, h - 2))
        # Delicate technical outlines instead of giant bright red light floods.
        p.setPen(_pen("#203747", 1))
        for y in range(15, h + 14, 24):
            p.drawLine(QPointF(w * .54, y), QPointF(w + 15, y))
        p.translate(w - 360, h / 2 + 6)
        if self.kind == "games":
            self._game_shelf(p)
        elif self.kind == "mods":
            self._mod_network(p)
        elif self.kind == "oldfiles":
            self._archive(p)
        elif self.kind == "graveyard":
            self._headstone(p)
        elif self.kind == "dna":
            self._forensics(p)
        elif self.kind == "undo":
            self._rewind(p)
        elif self.kind == "settings":
            self._settings(p)
        elif self.kind == "captures":
            self._captures(p)
        else:
            _controller(p, 185, 15, 1.0)
        p.restore()
        p.setPen(_pen("#2D4552", 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(.5, .5, w - 1, h - 1), 11, 11)

    def _game_shelf(self, p):
        for i, color in enumerate(("#456A80", "#42D4F2", "#F84359", "#6B91AA")):
            x = 20 + i * 78
            y = -62 + (i % 2) * 15
            _round(p, (x + 7, y + 8, 62, 118), "#080F18", "#263D4B", 7)
            _round(p, (x, y, 62, 118), "#102330", color, 7)
            _line(p, (x + 8, y + 84), (x + 54, y + 84), color, 2)
            _line(p, (x + 8, y + 93), (x + 40, y + 93), "#7999AA", 1)
            _controller(p, x + 31, y + 48, .35)
        _line(p, (15, 76), (333, 76), CYAN, 2)

    def _mod_network(self, p):
        _controller(p, 165, -2, .83)
        paths = [((165, 32), (35, 60)), ((165, 32), (295, 60)),
                 ((165, 32), (165, -78)), ((165, 32), (295, -70))]
        for a, b in paths:
            _line(p, a, b, "#3B8FA4", 2)
        for x, y in ((35, 60), (295, 60), (165, -78), (295, -70)):
            _round(p, (x - 21, y - 18, 42, 36), "#0F3040", CYAN, 6)
            _gear(p, x, y, 10, CYAN)
        p.setPen(_pen("#416777", 1))
        for r in (61, 84, 108):
            p.drawEllipse(QPointF(165, 0), r * 1.35, r * .73)

    def _archive(self, p):
        for i in range(4):
            x = 33 + 73 * i
            y = -65 + (i % 2) * 17
            _folder(p, x, y, 65, 92, CYAN if i != 2 else RED)
            p.setPen(_pen("#9DD7E4", 1))
            for j in range(3):
                p.drawLine(QPointF(x + 12, y + 43 + j * 9),
                           QPointF(x + 49, y + 43 + j * 9))
        _round(p, (53, 48, 242, 21), "#112732", "#31566A", 4)

    def _headstone(self, p):
        p.setPen(_pen("#2A5060", 1))
        p.setBrush(QColor("#10232C"))
        p.drawEllipse(QRectF(5, 64, 343, 26))
        head = QPainterPath()
        head.moveTo(127, 68)
        head.lineTo(127, -17)
        head.cubicTo(129, -97, 264, -97, 266, -17)
        head.lineTo(266, 68)
        head.closeSubpath()
        p.setBrush(QColor("#172934"))
        p.setPen(_pen("#405E6D", 3))
        p.drawPath(head)
        p.setPen(_pen(RED, 4))
        p.drawLine(QPointF(196, -43), QPointF(196, 19))
        p.drawLine(QPointF(178, -7), QPointF(214, -7))
        _controller(p, 77, 50, .52)
        _line(p, (110, 71), (289, 71), "#294653", 2)

    def _forensics(self, p):
        _round(p, (105, -80, 156, 135), "#0D2635", "#315E73", 14)
        for i, color in enumerate((CYAN, QColor("#6387A1"), RED)):
            x, y = 126 + i * 12, 36 - i * 27
            p.setPen(_pen(color, 2))
            p.setBrush(QColor("#0D222C"))
            p.drawPolygon(QPolygonF([
                QPointF(x, y), QPointF(x + 90, y),
                QPointF(x + 117, y + 12), QPointF(x + 28, y + 12),
            ]))
        # Controlled helix visual within the lab viewport.
        p.setPen(_pen(CYAN, 2))
        points1, points2 = [], []
        for i in range(35):
            y = -65 + i * 3
            points1.append(QPointF(180 + 20 * math.sin(i * .38), y))
            points2.append(QPointF(180 - 20 * math.sin(i * .38), y))
        p.drawPolyline(QPolygonF(points1))
        p.setPen(_pen(RED, 2))
        p.drawPolyline(QPolygonF(points2))
        _controller(p, 287, 18, .37)

    def _rewind(self, p):
        p.setPen(_pen("#2D5162", 12))
        p.drawArc(QRectF(103, -74, 167, 167), 35 * 16, 295 * 16)
        p.setPen(_pen(CYAN, 5))
        p.drawArc(QRectF(112, -65, 149, 149), 45 * 16, 245 * 16)
        p.setBrush(RED)
        p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([
            QPointF(112, -48), QPointF(76, -56), QPointF(96, -18)]))
        _folder(p, 230, -5, 74, 46, CYAN)
        _folder(p, 31, -5, 66, 43, "#607B90")
        _line(p, (101, 33), (226, 33), "#476C7A", 1)

    def _settings(self, p):
        p.setPen(_pen("#2C4553", 2))
        p.drawEllipse(QPointF(177, 0), 110, 110)
        p.drawEllipse(QPointF(177, 0), 79, 79)
        _gear(p, 177, 0, 54, "#F84359")
        for y in (-52, -16, 20):
            _line(p, (18, y), (82, y), "#456F82", 2)
            p.setBrush(CYAN)
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(48 + (y + 52), y), 5, 5)

    def _captures(self, p):
        _round(p, (35, -63, 153, 102), "#132736", CYAN, 7)
        _round(p, (66, -36, 153, 102), "#101F2D", "#5B8BA2", 7)
        _round(p, (98, -6, 153, 97), "#0F2532", RED, 7)
        p.setBrush(CYAN)
        p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([
            QPointF(161, 17), QPointF(161, 69), QPointF(201, 43)]))


class FeatureStrip(QWidget):
    """Consistent compact guide; texts are real feature semantics, never fake counts."""

    def __init__(self, steps: list[tuple[str, str]]):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)
        for i, (heading, detail) in enumerate(steps):
            holder = QFrame()
            holder.setObjectName("featureStep")
            h = QHBoxLayout(holder)
            h.setContentsMargins(12, 10, 10, 10)
            number = QLabel(f"{i+1:02d}")
            number.setObjectName("featureNumber")
            h.addWidget(number)
            text = QVBoxLayout()
            primary = QLabel(heading)
            primary.setObjectName("findingTitle")
            secondary = QLabel(detail)
            secondary.setWordWrap(True)
            secondary.setObjectName("caption")
            text.addWidget(primary)
            text.addWidget(secondary)
            h.addLayout(text, 1)
            layout.addWidget(holder, 1)


class RelationshipMap(QWidget):
    """Visual relationship map for *actual* evidenced game DNA categories.

    Selecting a node emits a grounded name. Unknown links stay explicitly
    unknown rather than being presented as safe-to-delete.
    """
    selected = Signal(str)
    NODE_TYPES = ("Install", "Mods", "Saves", "Captures", "Configs", "Leftovers")
    NODE_COLORS = ("#43D6F2", "#82A9C5", "#5F91B4",
                   "#46BEDA", "#E6A1A9", "#F84359")

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(350)
        self.setAccessibleName("Visual relationship map connecting installed game, mods, saves, captures, configuration and unknown leftovers")
        self.game_name = "Choose a game"
        self.states = {}
        self.active = "Install"

    def set_game(self, name: str, states: dict[str, str]):
        self.game_name = str(name)[:120]
        self.states = {str(k): str(v)[:100] for k, v in states.items()}
        self.active = "Install"
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor("#0A1420"))
        center = QPointF(w * .50, h * .51)
        radius_x = max(165, min(310, w * .32))
        radius_y = max(110, h * .32)
        p.setPen(_pen("#173243", 1))
        for r in (0.72, 1.0, 1.18):
            p.drawEllipse(center, radius_x * r, radius_y * r)
        p.setPen(_pen("#4B8AA1", 2))
        p.setBrush(QColor("#0D2835"))
        p.drawEllipse(center, 80, 56)
        p.setPen(_pen(CYAN, 3))
        p.drawEllipse(center, 86, 61)
        p.setPen(WHITE)
        title_font = QFont("Segoe UI", 11, QFont.DemiBold)
        p.setFont(title_font)
        p.drawText(QRectF(center.x()-72, center.y()-28, 144, 56),
                   Qt.AlignCenter | Qt.TextWordWrap, self.game_name)
        self.positions = {}
        for i, name in enumerate(self.NODE_TYPES):
            angle = -math.pi / 2 + i * math.pi * 2 / len(self.NODE_TYPES)
            x = center.x() + math.cos(angle) * radius_x
            y = center.y() + math.sin(angle) * radius_y
            rect = QRectF(x-74, y-31, 148, 62)
            self.positions[name] = rect
            color = QColor(self.NODE_COLORS[i])
            p.setPen(_pen(color, 2 if name == self.active else 1))
            p.drawLine(center, QPointF(x, y))
            p.setPen(_pen(color if name == self.active else "#345D70", 2))
            p.setBrush(QColor("#183540" if name == self.active else "#102330"))
            p.drawRoundedRect(rect, 9, 9)
            p.setPen(WHITE)
            p.setFont(QFont("Segoe UI", 11, QFont.DemiBold))
            p.drawText(QRectF(rect.x()+5, rect.y()+4, rect.width()-10, 22),
                       Qt.AlignCenter, name)
            p.setPen(MUTED)
            p.setFont(QFont("Segoe UI", 9))
            status = self.states.get(name, "Not verified")
            p.drawText(QRectF(rect.x()+7, rect.y()+27, rect.width()-14, 30),
                       Qt.AlignCenter | Qt.TextWordWrap, status)
        p.end()

    def mousePressEvent(self, event):
        for name, rect in getattr(self, "positions", {}).items():
            if rect.contains(event.position()):
                self.active = name
                self.update()
                self.selected.emit(name)
                break
        super().mousePressEvent(event)


class RecoveryRoute(QWidget):
    """Selected original path -> Windows Recycle Bin -> restore state."""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(150)
        self.path = "Select a recovery record"
        self.state = "Not checked"
        self.setAccessibleName("Recovery route and verification status")

    def set_record(self, path: str, state: str):
        self.path = str(path)
        self.state = str(state)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor("#0A1420"))
        slots = [(20, "ORIGINAL", Path(self.path).name or "Unknown"),
                 (w/3+10, "RECYCLE BIN", "Verify with Windows"),
                 (w*2/3+5, "RESTORE", self.state)]
        slot_w = min(225, max(115, w/3-28))
        for i, (x, heading, subtitle) in enumerate(slots):
            color = CYAN if i == 0 else RED if i == 1 else QColor("#70BAA6")
            r = QRectF(x, 25, slot_w, 88)
            p.setBrush(QColor("#11232F"))
            p.setPen(_pen("#3A5360", 1))
            p.drawRoundedRect(r, 8, 8)
            p.setPen(_pen(color, 2))
            p.drawLine(QPointF(x+10, 40), QPointF(x+44, 40))
            p.setPen(WHITE)
            p.setFont(QFont("Segoe UI", 10, QFont.DemiBold))
            p.drawText(QRectF(x+10, 44, slot_w-20, 20), heading)
            p.setFont(QFont("Segoe UI", 9))
            p.setPen(MUTED)
            p.drawText(QRectF(x+10, 66, slot_w-20, 39),
                       Qt.AlignLeft | Qt.TextWordWrap,
                       subtitle[:80])
            if i < 2:
                p.setPen(_pen(CYAN if i == 1 else "#658DA3", 2))
                x2 = x + slot_w
                end = slots[i+1][0]
                y = 67
                p.drawLine(QPointF(x2+3,y), QPointF(end-4,y))
                p.drawLine(QPointF(end-11,y-6), QPointF(end-4,y))
                p.drawLine(QPointF(end-11,y+6), QPointF(end-4,y))
        p.setPen(MUTED)
        p.setFont(QFont("Segoe UI", 9))
        p.drawText(QRectF(10, 120, w-20, 27),
                   Qt.AlignCenter,
                   "Restore availability requires an exact Windows Recycle Bin match. No expiry date is assumed.")
