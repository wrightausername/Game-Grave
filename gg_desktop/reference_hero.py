"""Reference-fidelity Crimson headers for Games and Mods.

Painted controls over original local vector artwork, never a screenshot of
fake UI. Metrics are only passed from verified scan inventory.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen, QFont, QFontDatabase
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from gg_desktop.visuals import SceneHeader
from gg_desktop.voice import PAGE_LANGUAGE
from gg_desktop.typography import display_family, text_family


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
        self.title_overlay = QLabel(
            "THE MOD SHELF" if self.kind == "mods" else title, self)
        self.title_overlay.setObjectName("referenceHeroTitle")
        self.title_overlay.setFont(QFont(display_family(), 42, QFont.Bold))
        self.title_overlay.setStyleSheet(
            "background:transparent;color:#FFFFFF;letter-spacing:1px;")
        route_for_kind = {
            "mods": "Mods", "oldfiles": "Old Files",
            "storage": "Other Storage", "captures": "Captures",
            "graveyard": "Graveyard", "dna": "Game DNA",
            "undo": "Undo Center", "games": "Games",
        }.get(self.kind)
        editorial = PAGE_LANGUAGE.get(route_for_kind, ("GAME GRAVE", ""))[0]
        self.eyebrow_overlay = QLabel(
            "MODS / YOUR LIBRARY" if self.kind == "mods" else editorial, self)
        self.eyebrow_overlay.setObjectName("featureHeroKicker")
        self.eyebrow_overlay.setFont(QFont(display_family(), 11, QFont.DemiBold))
        self.eyebrow_overlay.setStyleSheet(
            "background:transparent;color:"+self.theme_tone+
            ";letter-spacing:1.6px;")
        self.subtitle_overlay = QLabel(subtitle, self)
        self.subtitle_overlay.setObjectName("referenceHeroSubtitle")
        self.subtitle_overlay.setWordWrap(True)
        self.subtitle_overlay.setFont(QFont(text_family(), 11))
        self.subtitle_overlay.setStyleSheet(
            "background:transparent;color:#DFDCE3;")

        self.metrics = QWidget(self)
        self.metrics.setObjectName("referenceHeroMetrics")
        self.metrics.setVisible(self._has_metrics)
        row = QHBoxLayout(self.metrics)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(7)
        for i, (name, value, note) in enumerate(list(metrics)[:6]):
            tile = QFrame(self.metrics)
            tile.setObjectName("referenceHeroTile")
            tile.setStyleSheet(
                "QFrame#referenceHeroTile{"
                "background:rgba(12,8,18,219);"
                "border:1px solid #933049;border-radius:4px;}")
            col = QVBoxLayout(tile)
            col.setContentsMargins(13, 7, 9, 6)
            col.setSpacing(1)
            top = QLabel(str(name).upper())
            top.setFont(QFont(display_family(), 9, QFont.DemiBold))
            top.setStyleSheet(
                "background:transparent;color:#E8C1CB;letter-spacing:.5px;")
            count = QLabel(str(value))
            count.setFont(QFont(display_family(), 23, QFont.Bold))
            count.setStyleSheet(
                "background:transparent;color:#FFFFFF;")
            foot = QLabel(str(note))
            foot.setFont(QFont(text_family(), 8))
            foot.setStyleSheet(
                "background:transparent;color:#A7AFB9;")
            foot.setWordWrap(True)
            for widget in (top, count, foot):
                col.addWidget(widget)
            row.addWidget(tile, 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.width()
        self.eyebrow_overlay.setGeometry(36, 28, max(150, w - 80), 21)
        self.title_overlay.setGeometry(32, 55, max(150, w - 64), 64)
        self.subtitle_overlay.setGeometry(36, 122, max(150, w - 73), 42)
        self.metrics.setGeometry(17, 186, max(250, w - 34), 81)

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
        # The title and the artwork are the focal points. No repeated badge
        # ornaments that make the panels look like a generic game dashboard.
        p.end()
