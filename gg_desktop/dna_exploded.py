"""Game DNA's native, interactive 'exploded game' workstation.

Unlike the old radial RelationshipMap, this renders a stacked 2.5D object with
six independently selectable layers. The picture and data are not prerecorded:
art is the locally verified game cover, sizes come from launcher / linked mod
records, and uncertain relationships are *visibly* uncertain.

Zero timers, zero file I/O in paintEvent, no shader or GPU injection. The app
does not scan while drawing and the widget is safe to keep open while playing.
"""
from __future__ import annotations

import math

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter,
                          QPainterPath, QPen, QPolygonF, QRadialGradient)
from gg_desktop.visuals import RelationshipMap
from gg_desktop.typography import display_family, text_family


LAYERS = (
    ("Install", "GAME FILES", "#EF4662"),
    ("Mods", "MODS & ADDONS", "#C16CF8"),
    ("Captures", "CAPTURES", "#35C5ED"),
    ("Saves", "SAVES", "#3EE49D"),
    ("Configs", "CONFIG & CACHE", "#F1C156"),
    ("Leftovers", "OTHER / UNVERIFIED", "#9BA5B4"),
)


class ExplodedGameMap(RelationshipMap):
    """A real Qt widget. Click a stack layer or its label to inspect evidence."""

    def __init__(self):
        super().__init__()
        self.setObjectName("dnaExplodedGameMap")
        self.setMinimumHeight(510)
        self.setMaximumHeight(510)
        self.setMouseTracking(True)
        self.setAccessibleName(
            "Exploded game storage map. Select one of six layers to inspect "
            "its source evidence, including unknown or protected files.")
        self._sizes = {}
        self._counts = {}
        self._hover = None
        self.positions = {}

    def set_evidence(self, sizes=None, counts=None):
        """Caller must supply only source-backed size values, never guesses."""
        self._sizes = {str(k): str(v) for k, v in (sizes or {}).items()
                       if v is not None}
        self._counts = {str(k): str(v) for k, v in (counts or {}).items()
                        if v is not None}
        self.update()

    @staticmethod
    def _shade(color, alpha=255):
        c = QColor(color)
        c.setAlpha(alpha)
        return c

    @staticmethod
    def _polygon(points):
        return QPolygonF([QPointF(*pt) for pt in points])

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        width, height = self.width(), self.height()
        p.fillRect(self.rect(), QColor("#080C14"))

        # Restrained black-red set dressing: no perpetual animation, no fake
        # system numbers, no expensive images loaded on repaint.
        radial = QRadialGradient(QPointF(width*.39, height*.60),
                                 max(220, width*.62))
        radial.setColorAt(0, QColor(125, 15, 46, 95))
        radial.setColorAt(.45, QColor(39, 14, 31, 47))
        radial.setColorAt(1, QColor(8, 12, 20, 0))
        p.fillRect(self.rect(), radial)
        p.setPen(QPen(QColor("#1F2430"), 1))
        for y in range(30, height, 44):
            p.drawLine(0, y, width, y)
        for x in range(0, width, 60):
            p.drawLine(x, 0, x, height)

        wide = width >= 560
        # Dynamic geometry does not assume a huge gaming monitor.
        scale = min(1.0, max(.65, width / 780))
        cx = width * (.35 if wide else .40)
        ex, ey = 153*scale, 47*scale
        top = height*.185
        gap = 53*scale
        depth = 18*scale

        # Platform. The shadow, base and rings are authored vectors.
        base_y = top + 5*gap + 48*scale
        p.setPen(Qt.NoPen)
        p.setBrush(self._shade("#D3244B", 35))
        p.drawEllipse(QRectF(cx-ex*1.32, base_y-22,
                             ex*2.64, 67*scale))
        for inset, color, weight in (
            (1.23, "#451A2F", 14), (1.11, "#8E2746", 5),
            (1.04, "#F74665", 3)):
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(color), weight*scale))
            p.drawEllipse(QRectF(cx-ex*inset, base_y-21,
                                 2*ex*inset, 57*scale))
        p.setPen(QPen(QColor("#AA284B"), 1))
        p.drawLine(QPointF(max(4,cx-ex*1.5), base_y+37),
                   QPointF(min(width-4,cx+ex*1.5), base_y+37))

        # Show genuine per-layer data, with 'unknown' specifically distinct
        # from absence. Do not draw a colored link as proof of ownership.
        self.positions = {}
        for index, (name, caption, color) in enumerate(LAYERS):
            y = top + index * gap
            active = name == self.active
            resolved = (name == "Install" and
                        self.states.get(name) == "Recorded") or (
                        name == "Mods" and bool(self._counts.get("Mods")))
            stroke = QColor(color if resolved else "#586473")
            if active:
                stroke = QColor("#FFFFFF" if resolved else "#D4A1AA")
            alpha = 155 if resolved else 52

            top_pts = [
                (cx-ex, y),
                (cx, y-ey*.82),
                (cx+ex, y),
                (cx, y+ey*.82),
            ]
            front_pts = [
                (cx-ex, y), (cx, y+ey*.82),
                (cx, y+ey*.82+depth), (cx-ex, y+depth),
            ]
            right_pts = [
                (cx, y+ey*.82), (cx+ex, y),
                (cx+ex, y+depth), (cx, y+ey*.82+depth),
            ]
            p.setPen(Qt.NoPen)
            p.setBrush(self._shade(color, 13 if not resolved else 42))
            p.drawPolygon(self._polygon(front_pts))
            p.setBrush(self._shade(color, 18 if not resolved else 65))
            p.drawPolygon(self._polygon(right_pts))
            glow = QLinearGradient(cx-ex, y-ey, cx+ex, y+ey)
            glow.setColorAt(0, self._shade(color, 155 if resolved else 62))
            glow.setColorAt(.50, QColor("#101321"))
            glow.setColorAt(1, self._shade(color, 95 if resolved else 35))
            p.setBrush(glow)
            p.setPen(QPen(stroke, (3.4 if active else 2.2)*scale))
            p.drawPolygon(self._polygon(top_pts))
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(self._shade(color,alpha), 1.8*scale))
            p.drawPolyline(self._polygon(
                [(cx-ex,y+depth),(cx,y+ey*.82+depth),
                 (cx+ex,y+depth)]))

            # A single official local game cover is placed on the top surface.
            # All other layers use grounded categories, not generated posters.
            if index == 0:
                if not self._cover.isNull():
                    cover_rect = QRectF(cx-91*scale, y-26*scale,
                                        182*scale, 63*scale)
                    p.save()
                    clip = QPainterPath()
                    clip.addRoundedRect(cover_rect, 7, 7)
                    p.setClipPath(clip)
                    p.setOpacity(.93)
                    p.drawPixmap(cover_rect, self._cover,
                                 QRectF(0,0,self._cover.width(),
                                        self._cover.height()))
                    p.restore()
                else:
                    p.setPen(QColor("#F3E5EC"))
                    title_font=QFont(display_family(), max(9,int(13*scale)),
                                     QFont.Bold)
                    p.setFont(title_font)
                    p.drawText(QRectF(cx-120*scale,y-23*scale,
                                     240*scale,54*scale),
                               Qt.AlignCenter|Qt.TextWordWrap,
                               self.game_name[:36])
            else:
                # Layer symbols are abstract, original and consistent.
                p.setPen(QPen(self._shade(color,180 if resolved else 95),2))
                center=QPointF(cx,y)
                if index == 1:  # mod puzzle
                    p.drawRect(QRectF(cx-12,y-12,24,24))
                    p.drawEllipse(QPointF(cx-12,y),4,4)
                    p.drawEllipse(QPointF(cx+12,y),4,4)
                elif index == 2:  # film/photo
                    p.drawRoundedRect(QRectF(cx-14,y-10,28,20),3,3)
                    p.drawEllipse(QPointF(cx+7,y-4),3,3)
                    p.drawLine(QPointF(cx-11,y+6),QPointF(cx-2,y-3))
                    p.drawLine(QPointF(cx-2,y-3),QPointF(cx+9,y+7))
                elif index == 3:  # save
                    p.drawRoundedRect(QRectF(cx-11,y-13,22,26),2,2)
                    p.drawRect(QRectF(cx-5,y-8,10,7))
                    p.drawEllipse(QPointF(cx,y+6),3,3)
                elif index == 4:  # cache
                    p.drawEllipse(QPointF(cx,y),12,12)
                    p.drawArc(QRectF(cx-7,y-7,14,14),20*16,260*16)
                else:
                    p.drawRoundedRect(QRectF(cx-13,y-8,26,17),3,3)
                    p.drawLine(QPointF(cx-8,y),QPointF(cx+8,y))

            # Callouts reflect the *source*, never a fictitious safe clean total.
            if wide:
                x0=cx+ex+10*scale
                tx=min(width-197,x0+32*scale)
                line_y=y+depth*.45
                p.setPen(QPen(self._shade(color,210 if resolved else 75),
                              (2 if active else 1.2)*scale))
                p.drawLine(QPointF(x0,line_y),QPointF(tx-10,line_y))
                p.setPen(Qt.NoPen)
                p.setBrush(stroke)
                p.drawEllipse(QPointF(tx-10,line_y),3.2,3.2)
                text_rect=QRectF(tx, line_y-15, width-tx-9, 48)
                line2=self._sizes.get(name) or self._counts.get(name) or (
                    "Protected / unverified" if name in
                    ("Saves", "Configs", "Leftovers", "Captures")
                    else "No linked evidence")
                if name == "Install" and not self._sizes.get(name):
                    line2="Size not reported"
                p.setPen(QColor("#F5F2F7" if active else "#D5D5DC"))
                p.setFont(QFont(display_family(), 10, QFont.Bold))
                p.drawText(QRectF(text_rect.x(), text_rect.y(),
                                  text_rect.width(),18),caption)
                p.setPen(QColor("#BAA9B9" if resolved else "#8494A3"))
                p.setFont(QFont(text_family(), 9))
                p.drawText(QRectF(tx, line_y+5, width-tx-8,23),
                           Qt.AlignLeft|Qt.TextWordWrap,line2[:55])
                self.positions[name]=QRectF(tx-11,line_y-20,
                                             width-tx+8,49)
            else:
                self.positions[name]=QRectF(cx-ex, y-ey,
                                             2*ex,2*ey+depth)

        p.setFont(QFont(text_family(),9))
        p.setPen(QColor("#9AA5B3"))
        p.drawText(QRectF(14,height-32,width-28,23),
                   Qt.AlignLeft|Qt.AlignVCenter,
                   "SELECT A LAYER TO INSPECT  •  FADED LAYERS ARE NOT ATTRIBUTED")
        p.end()

    def mousePressEvent(self, event):
        # Existing RelationshipMap.selected(QString) drives the inspector.
        for name, rect in self.positions.items():
            if rect.contains(event.position()):
                self.active=name
                self.update()
                self.selected.emit(name)
                event.accept()
                return
        # Clicking directly on an isometric slab selects its nearest layer.
        scale=min(1.0,max(.65,self.width()/780))
        cx=self.width()*(.35 if self.width()>=560 else .40)
        top=self.height()*.185
        if abs(event.position().x()-cx)<160*scale:
            index=round((event.position().y()-top)/(53*scale))
            if 0<=index<len(LAYERS):
                self.active=LAYERS[index][0]
                self.update()
                self.selected.emit(self.active)
                event.accept()
                return
        event.ignore()
