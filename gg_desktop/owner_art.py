"""Pixel-source artwork blended from the seven exact locked owner references.

Each native Qt page owns all text, status, data and controls. The isolated
photo crop is only a decorative image; no fake UI values are baked into it.
"""
from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPixmap

IMAGE_BY_ROUTE = {
    "overview": "owner_cinematic_overview.jpg",
    "graveyard": "owner_cinematic_graveyard.jpg",
    "dna": "owner_cinematic_dna.jpg",
    "undo": "owner_cinematic_undo.jpg",
    "assistant": "owner_cinematic_assistant.jpg",
    "settings": "owner_cinematic_settings.jpg",
    "tools": "owner_cinematic_tools.jpg",
    # Other sections share the definitive cinematic world until their own
    # final owner reference can supersede it. No neon/fantasy theme drift.
    "readyroom": "owner_cinematic_overview.jpg",
    "games": "owner_cinematic_overview.jpg",
    "mods": "owner_cinematic_overview.jpg",
    "oldfiles": "owner_cinematic_overview.jpg",
    "captures": "owner_cinematic_overview.jpg",
    "otherstorage": "owner_cinematic_overview.jpg",
}


def load_approved_hero(kind: str) -> QPixmap:
    name = IMAGE_BY_ROUTE.get(str(kind).casefold())
    return (QPixmap(str(Path(__file__).parent / "assets" / name))
            if name else QPixmap())


def draw_approved_hero(painter, art: QPixmap, width: int, height: int) -> bool:
    """Show the owner's original proportions without a rectangular left seam.

    Crops are approximately 835x150: stretching them across 1380x164 makes
    the stone GG grotesquely wide. Render with preserved source aspect ratio
    against the vector forest fallback and fade only the left edge. This is
    a one-frame paint, not a game-running background animation.
    """
    if art.isNull() or width < 1 or height < 1:
        return False
    w, h = max(1, int(width)), max(1, int(height))
    natural = float(art.width()) / max(1.0, float(art.height()))
    artwork_width = min(int(w*.86), max(1,int(h*natural*1.04)))
    left = w-artwork_width
    composite = QPixmap(artwork_width, h)
    composite.fill(Qt.transparent)
    layer = QPainter(composite)
    layer.setRenderHint(QPainter.SmoothPixmapTransform)
    src_width = min(float(art.width()), artwork_width*float(art.height()) / h)
    src_x = max(0., (art.width()-src_width)*.5)
    layer.drawPixmap(
        QRectF(0, 0, artwork_width, h), art,
        QRectF(src_x, 0, src_width, float(art.height())))
    layer.setCompositionMode(QPainter.CompositionMode_DestinationIn)
    opacity = QLinearGradient(0, 0, max(1, artwork_width*.30), 0)
    opacity.setColorAt(0., QColor(255, 255, 255, 0))
    opacity.setColorAt(.55, QColor(255, 255, 255, 136))
    opacity.setColorAt(1., QColor(255, 255, 255, 255))
    layer.fillRect(composite.rect(), opacity)
    layer.end()
    painter.drawPixmap(left, 0, composite)
    return True
