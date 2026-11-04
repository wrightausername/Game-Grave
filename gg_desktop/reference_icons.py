"""Native category-coloured glyphs used by the owner's locked metric bands."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter

from gg_desktop.visuals import nav_icon


def metric_icon(route, accent, size=26):
    pixmap = nav_icon(route).pixmap(size, size)
    painter = QPainter(pixmap)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), QColor(accent))
    painter.end()
    return pixmap
