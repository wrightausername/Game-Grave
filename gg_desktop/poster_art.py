"""Quiet missing-artwork states; game covers come from genuine local images."""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap


def missing_artwork(title: str, width: int, height: int) -> QPixmap:
    """Show an honest empty cover, without inventing a poster for the game."""
    w, h = max(1, int(width)), max(1, int(height))
    image = QPixmap(w, h)
    image.fill(QColor("#0D141C"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.TextAntialiasing)
    painter.setPen(QPen(QColor("#2E3742"), 1))
    painter.drawRect(0, 0, w-1, h-1)
    painter.setPen(QPen(QColor("#8F3447"), 2))
    painter.drawLine(14, 16, max(14, w-14), 16)
    title_font = QFont("Segoe UI")
    title_font.setPixelSize(max(12, min(18, round(w*.08))))
    title_font.setBold(True)
    painter.setFont(title_font)
    painter.setPen(QColor("#D4DAE2"))
    painter.drawText(QRectF(12, h*.20, max(1,w-24), h*.52),
                     Qt.AlignCenter | Qt.TextWordWrap, str(title))
    caption = QFont("Segoe UI")
    caption.setPixelSize(10)
    painter.setFont(caption)
    painter.setPen(QColor("#82909F"))
    painter.drawText(QRectF(8, max(20,h-32), max(1,w-16), 22),
                     Qt.AlignCenter, "Artwork not loaded")
    painter.end()
    return image
