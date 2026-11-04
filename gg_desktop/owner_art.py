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
    artwork_width = max(1, round(h * natural))
    # In the supplied comparison the GG stone is in the right third. The
    # narrow 700x96 crops have the stone near their left third: right-aligning
    # the entire crop incorrectly placed the stone behind the page title.
    source_focus = .35 if natural > 6 else .50
    left = round(w * .79 - artwork_width * source_focus)
    composite = QPixmap(artwork_width, h)
    composite.fill(Qt.transparent)
    layer = QPainter(composite)
    layer.setRenderHint(QPainter.SmoothPixmapTransform)
    layer.drawPixmap(
        QRectF(0, 0, artwork_width, h), art,
        QRectF(0, 0, float(art.width()), float(art.height())))
    layer.setCompositionMode(QPainter.CompositionMode_DestinationIn)
    opacity = QLinearGradient(0, 0, max(1, artwork_width*.30), 0)
    opacity.setColorAt(0., QColor(255, 255, 255, 0))
    opacity.setColorAt(.55, QColor(255, 255, 255, 136))
    opacity.setColorAt(1., QColor(255, 255, 255, 255))
    layer.fillRect(composite.rect(), opacity)
    layer.end()
    painter.drawPixmap(left, 0, composite)
    return True
