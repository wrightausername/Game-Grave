"""Pixel-source artwork for owner-locked Game Grave cinematic heroes.

These small JPGs are cropped strictly from the owner's exact approved PNG
screenshots, with all illustrative UI figures/text excluded. The functional
Qt widgets, text, stats and actions remain native and scan-backed.
"""
from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import QRectF
from PySide6.QtGui import QPixmap

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
    """Original approved header art is optional; vector fallback still works."""
    name = IMAGE_BY_ROUTE.get(str(kind).casefold())
    return QPixmap(str(Path(__file__).parent / "assets" / name)) if name else QPixmap()


def draw_approved_hero(painter, art: QPixmap, width: int, height: int) -> bool:
    """Blend the owner-approved artwork across the header without stretching GG.

    Host pages darken the left edge for legible copy. Starting the owner art
    at 21% rather than 41% keeps the cinematic scene behind the title.
    """
    if art.isNull() or width < 1 or height < 1:
        return False
    dest = QRectF(width*.21, 0, width*.79, height)
    # Use the correct source aspect ratio and crop only the atmosphere at the
    # right edge. Stretching a gravestone/controller produces ugly proportions.
    crop_width = min(float(art.width()),
                     dest.width() * art.height() / max(1.0, dest.height()))
    available = max(0.0, art.width() - crop_width)
    source = QRectF(available*.19, 0, crop_width, float(art.height()))
    painter.drawPixmap(dest, art, source)
    return True
