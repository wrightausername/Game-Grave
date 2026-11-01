"""Reference-fidelity Crimson headers for Games and Mods.

Painted controls over original local vector artwork, never a screenshot of
fake UI. Metrics are only passed from verified scan inventory.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from gg_desktop.visuals import SceneHeader
from gg_desktop.voice import PAGE_LANGUAGE


class ReferenceHero(SceneHeader):
    """Cinematic header with scan-grounded metric tiles embedded in the art."""

    def __init__(self, kind, title, subtitle, metrics=()):
        super().__init__(kind, title, subtitle, note="CRIMSON COMMAND")
        self.setObjectName("referenceHero")
        self._has_metrics = bool(metrics)
        self.setMinimumHeight(278 if self._has_metrics else 214)
        self.setMaximumHeight(278 if self._has_metrics else 214)
        self.setAccessibleName(title + ". " + subtitle)
        for child in self.findChildren(QLabel):
            child.hide()
        scene_assets = {
            "mods": "crimson_mods_scene.svg",
            "dna": "crimson_dna_scene.svg",
            "undo": "crimson_undo_scene.svg",
            "oldfiles": "crimson_oldfiles_scene.svg",
            "storage": "crimson_storage_scene.svg",
            "captures": "crimson_captures_scene.svg",
            "graveyard": "crimson_graveyard_scene.svg",
        }
        asset = scene_assets.get(str(kind), "crimson_reference_scene.svg")
        self.background_art = QSvgRenderer(str(
            Path(__file__).parent / "assets" / asset))

        # Feature-specific palette and an editorial title set. A seven-page
        # app should not read like the same prebuilt template everywhere.
        self.kind = str(kind)
        self.theme_tone = {
            "dna": "#BC7AFF", "oldfiles": "#57D8F0",
            "storage": "#57D8F0", "captures": "#F45F7C",
            "graveyard": "#F05069", "undo": "#F28599",
        }.get(self.kind, "#F44A64")
        self.title_overlay = QLabel(title, self)
        self.title_overlay.setObjectName("referenceHeroTitle")
        self.title_overlay.setStyleSheet(
            "background:transparent; color:#FFFFFF;"
            "font-family:'Georgia','Cambria','Segoe UI'; font-size:47px;"
            "font-weight:800; letter-spacing:-.2px;")
        route_for_kind = {
            "mods": "Mods", "oldfiles": "Old Files",
            "storage": "Other Storage", "captures": "Captures",
            "graveyard": "Graveyard", "dna": "Game DNA",
            "undo": "Undo Center", "games": "Games",
        }.get(self.kind)
        editorial = PAGE_LANGUAGE.get(route_for_kind, ("GAME GRAVE", ""))[0]
        self.eyebrow_overlay = QLabel(editorial, self)
        self.eyebrow_overlay.setObjectName("featureHeroKicker")
        self.eyebrow_overlay.setStyleSheet(
            "background:transparent;color:"+self.theme_tone+
            ";font-size:11px;font-weight:800;letter-spacing:1.5px;")
        self.subtitle_overlay = QLabel(subtitle, self)
        self.subtitle_overlay.setObjectName("referenceHeroSubtitle")
        self.subtitle_overlay.setWordWrap(True)
        self.subtitle_overlay.setStyleSheet(
            "background:transparent;color:#DFDCE3;"
            "font-size:15px;line-height:1.3;")

        self.metrics = QWidget(self)
        self.metrics.setObjectName("referenceHeroMetrics")
        self.metrics.setVisible(self._has_metrics)
        row = QHBoxLayout(self.metrics)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        for i, (name, value, note) in enumerate(list(metrics)[:6]):
            tile = QFrame(self.metrics)
            tile.setObjectName("referenceHeroTile")
            tile.setStyleSheet(
                "QFrame#referenceHeroTile{"
                "background:rgba(8,10,16,226);"
                "border:0;border-left:1px solid #5D3D4B;border-radius:0;}")
            col = QVBoxLayout(tile)
            col.setContentsMargins(17, 11, 9, 8)
            col.setSpacing(3)
            top = QLabel(str(name).upper())
            top.setStyleSheet(
                "background:transparent;color:#D6BEC8;"
                "font-size:10px;font-weight:700;letter-spacing:1px;")
            count = QLabel(str(value))
            count.setStyleSheet(
                "background:transparent;color:#FFFFFF;"
                "font-family:'Georgia','Segoe UI';font-size:27px;font-weight:800;")
            foot = QLabel(str(note))
            foot.setStyleSheet(
                "background:transparent;color:#92A3B0;font-size:10px;")
            foot.setWordWrap(True)
            for widget in (top, count, foot):
                col.addWidget(widget)
            row.addWidget(tile, 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.width()
        self.eyebrow_overlay.setGeometry(37, 34, max(150, w - 76), 25)
        self.title_overlay.setGeometry(32, 64, max(150, w - 71), 62)
        self.subtitle_overlay.setGeometry(36, 131, max(150, w - 73), 52)
        self.metrics.setGeometry(17, 190, max(250, w - 34), 73)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        full = QRectF(0, 0, w, h)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#100D1B"))
        p.drawRoundedRect(full, 12, 12)
        p.save()
        p.setClipRect(full)
        if self.background_art.isValid():
            self.background_art.render(p, QRectF(0, -65, w, h + 122))
        # Preserve artwork on the right; fade only the functional text field.
        shade = QLinearGradient(0, 0, w, 0)
        shade.setColorAt(0.0, QColor(5, 7, 14, 251))
        shade.setColorAt(.29, QColor(8, 8, 16, 192))
        shade.setColorAt(.55, QColor(10, 7, 16, 33))
        shade.setColorAt(1, QColor(12, 6, 13, 0))
        p.fillRect(full, shade)
        # Darken only the bottom where translucent tiles sit.
        bottom = QLinearGradient(0, h * .49, 0, h)
        bottom.setColorAt(0, QColor(6, 7, 11, 0))
        bottom.setColorAt(1, QColor(6, 6, 11, 193))
        p.fillRect(full, bottom)
        p.restore()
        p.setPen(QPen(QColor(self.theme_tone), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(full.adjusted(.5, .5, -.5, -.5), 8, 8)
        # Carved-corner framing and a feature-specific navigation sigil.
        p.setPen(QPen(QColor(self.theme_tone), 2.4))
        p.drawLine(15, h - 2, min(w - 20, w*.42), h - 2)
        p.drawLine(w-132, 0, w-35, 0)
        p.drawLine(w-35, 0, w-10, 21)
        p.drawLine(18, 39, 18, 164)
        # A consistent crest with per-room glyph, not a font-emoji ornament.
        p.setPen(QPen(QColor(self.theme_tone), 2))
        p.setBrush(QColor(11, 17, 26, 185))
        p.drawEllipse(QRectF(24, 173, 40, 40))
        p.drawEllipse(QRectF(28, 177, 32, 32))
        # Editorial title takes precedence over unnecessary ornamentation.
        # The small crest is deliberately quiet and never covers any text.
        cx, cy = 44.0, 194.0
        if self.kind == "dna":
            p.drawArc(QRectF(39, 60, 22, 31), 85*16, 185*16)
            p.drawArc(QRectF(39, 60, 22, 31), 265*16, 185*16)
            for dy in (-7, 0, 7):
                p.drawLine(QPointF(43,cy+dy),QPointF(56,cy+dy))
        elif self.kind == "undo":
            p.drawArc(QRectF(36, 63, 27, 27), 5*16, 292*16)
            p.drawLine(QPointF(33,68),QPointF(39,81))
            p.drawLine(QPointF(33,68),QPointF(46,67))
        elif self.kind == "graveyard":
            p.drawRoundedRect(QRectF(41,63,17,27),5,5)
            p.drawLine(QPointF(cx,65),QPointF(cx,83))
            p.drawLine(QPointF(cx-7,72),QPointF(cx+7,72))
        elif self.kind == "captures":
            p.drawRoundedRect(QRectF(38,65,23,19),3,3)
            p.drawEllipse(QPointF(49,74),5,5)
            p.drawLine(QPointF(40,62),QPointF(59,62))
        elif self.kind == "mods":
            p.drawRect(QRectF(41,64,18,23))
            p.drawEllipse(QPointF(50,65),3,3)
            p.drawLine(QPointF(38,73),QPointF(42,73))
            p.drawLine(QPointF(59,78),QPointF(63,78))
        elif self.kind in ("storage","oldfiles"):
            p.drawRect(QRectF(37,65,25,20))
            for dy in (69,75,81):
                p.drawLine(QPointF(42,dy),QPointF(55,dy))
        else:
            p.drawRoundedRect(QRectF(36,68,27,16),5,5)
            p.drawEllipse(QPointF(55,75),2,2)
            p.drawLine(QPointF(42,72),QPointF(42,80))
            p.drawLine(QPointF(38,76),QPointF(46,76))
        p.end()
