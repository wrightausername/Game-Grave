"""Reference-fidelity Crimson headers for Games and Mods.

Painted controls over original local vector artwork, never a screenshot of
fake UI. Metrics are only passed from verified scan inventory.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from gg_desktop.visuals import SceneHeader
from gg_desktop.owner_art import load_approved_hero, draw_approved_hero


class ReferenceHero(SceneHeader):
    """Cinematic header with scan-grounded metric tiles embedded in the art."""

    def __init__(self, kind, title, subtitle, metrics=()):
        super().__init__(kind, title, subtitle, note="GAME GRAVE")
        self.setObjectName("referenceHero")
        self._has_metrics = bool(metrics)
        self.setMinimumHeight(224 if self._has_metrics else 132)
        self.setMaximumHeight(224 if self._has_metrics else 132)
        self.setAccessibleName(title + ". " + subtitle)
        for child in self.findChildren(QLabel):
            child.hide()
        # Use the owner's photo family throughout the shell. The vector art
        # is only a fallback if an archived photo cannot be loaded.
        themed = kind in (
            "readyroom", "games", "mods", "oldfiles",
            "otherstorage", "captures")
        self.background_art = QSvgRenderer(str(
            Path(__file__).parent / "assets" /
            ("crimson_ruins.svg" if themed else "gg_cinematic_hero.svg")))
        # Exact cropped photographic art from the owner's approved PNG,
        # rather than the previous approximate vector headstone.
        self.owner_art = load_approved_hero(kind)

        self.title_overlay = QLabel(title, self)
        self.title_overlay.setObjectName("referenceHeroTitle")
        self.title_overlay.setStyleSheet(
            "background:transparent; color:#FFFFFF; font-size:38px;"
            "font-weight:900; letter-spacing:.3px;")
        self.subtitle_overlay = QLabel(subtitle, self)
        self.subtitle_overlay.setObjectName("referenceHeroSubtitle")
        self.subtitle_overlay.setWordWrap(True)
        self.subtitle_overlay.setStyleSheet(
            "background:transparent;color:#C7CDD8;font-size:14px;")

        self.metrics = QWidget(self)
        self.metrics.setObjectName("referenceHeroMetrics")
        self.metrics.setVisible(self._has_metrics)
        row = QHBoxLayout(self.metrics)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        for i, (name, value, note) in enumerate(list(metrics)[:4]):
            tile = QFrame(self.metrics)
            tile.setObjectName("referenceHeroTile")
            tile.setStyleSheet(
                "QFrame#referenceHeroTile{"
                "background:rgba(7,13,22,195);"
                "border:1px solid #324150;border-radius:10px;}")
            col = QVBoxLayout(tile)
            col.setContentsMargins(14, 6, 11, 6)
            col.setSpacing(1)
            top = QLabel(str(name).upper())
            top.setStyleSheet(
                "background:transparent;color:#EBB8C1;"
                "font-size:10px;font-weight:800;")
            count = QLabel(str(value))
            count.setStyleSheet(
                "background:transparent;color:#FFFFFF;"
                "font-size:22px;font-weight:900;")
            foot = QLabel(str(note))
            foot.setStyleSheet(
                "background:transparent;color:#A9C2D1;font-size:10px;")
            foot.setWordWrap(True)
            for widget in (top, count, foot):
                col.addWidget(widget)
            row.addWidget(tile, 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.width()
        self.title_overlay.setGeometry(38, 13, max(150, w - 58), 49)
        self.subtitle_overlay.setGeometry(39, 61, max(150, round(w * .66 - 42)), 43)
        self.metrics.setGeometry(18, 143, max(250, w - 36), 71)

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
        if self.background_art.isValid() and self.owner_art.isNull():
            self.background_art.render(p, QRectF(0, -62, w, h + 128))
        draw_approved_hero(p, self.owner_art, w, h)
        if self.owner_art.isNull():
            # Unique vector artwork, 100% local and repaint-only. These are
            # atmospheric scene symbols, not screenshots of imaginary data.
            p.save()
            p.setClipRect(full)
            p.setOpacity(.86)
            p.translate(w - 380, h * .56)
            if self.kind == "games":
                self._game_shelf(p)
            elif self.kind == "mods":
                self._mod_network(p)
            elif self.kind == "oldfiles":
                self._archive(p)
            elif self.kind == "otherstorage":
                self._forensics(p)
            elif self.kind == "captures":
                self._captures(p)
            elif self.kind == "readyroom":
                self._game_shelf(p)
            p.restore()
        # Red moon atmosphere, while preserving white text contrast.
        shade = QLinearGradient(0, 0, w, 0)
        shade.setColorAt(0.0, QColor(5, 7, 14, 248))
        shade.setColorAt(.31, QColor(8, 8, 16, 160))
        shade.setColorAt(.58, QColor(14, 7, 17, 25))
        shade.setColorAt(1, QColor(22, 5, 12, 20))
        p.fillRect(full, shade)
        # Darken only the bottom where translucent tiles sit.
        bottom = QLinearGradient(0, h * .49, 0, h)
        bottom.setColorAt(0, QColor(6, 7, 11, 0))
        bottom.setColorAt(1, QColor(6, 6, 11, 193))
        p.fillRect(full, bottom)
        p.restore()
        # Owner reference uses a slim red title accent, not a neon outline.
        p.setPen(QPen(QColor("#EF334F"), 5, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(24, 27, 12, 99)
        p.end()
