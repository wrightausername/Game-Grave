"""Crisp, local-only preview of a real scanned game screenshot.

Only a verified screenshot from the current read-only inventory can be decoded.
The decode uses the existing bounded Pillow preview, runs via the desktop's
background worker, and keeps pixels in memory (no thumbnail cache or upload).
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from core import is_unchanged
from screenshot_preview import decode_screenshot_preview


def decode_capture_for_display(record):
    """Existing safeguards check extension, metadata, file size and pixel count."""
    return decode_screenshot_preview(record)


class ScreenshotImage(QWidget):
    """Aspect-fitted source image. Never upscales tiny screenshots into pixel art."""

    def __init__(self, *, height=160, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(height)
        self.setMaximumHeight(height)
        self._pixmap = QPixmap()
        self._message = "Scan your PC to see your latest game screenshot"
        self.setAccessibleName("Actual locally detected game screenshot preview")
        self.setToolTip("Only screenshot pixels from your own PC appear here.")

    def set_status(self, message: str):
        self._pixmap = QPixmap()
        self._message = str(message)
        self.update()

    def set_image(self, image):
        """Called on the Qt UI thread with a bounded Pillow RGB preview."""
        rgb = image.convert("RGB") if image.mode != "RGB" else image
        raw = rgb.tobytes()
        qimg = QImage(
            raw, rgb.width, rgb.height, rgb.width * 3, QImage.Format_RGB888
        ).copy()
        self._pixmap = QPixmap.fromImage(qimg)
        self._message = ""
        self.update()

    def has_image(self) -> bool:
        return not self._pixmap.isNull()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        bounds = QRectF(0, 0, self.width(), self.height())
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#07111C"))
        painter.drawRoundedRect(bounds, 8, 8)
        painter.save()
        painter.setClipRect(bounds.adjusted(1, 1, -1, -1))
        if self.has_image():
            width, height = self._pixmap.width(), self._pixmap.height()
            # Small or low-resolution originals are shown at native pixel size
            # rather than magnified. Higher resolution sources are downscaled
            # using the smooth painter transform.
            factor = min(
                1.0,
                max(1, self.width() - 12) / max(1, width),
                max(1, self.height() - 12) / max(1, height),
            )
            shown_w, shown_h = width * factor, height * factor
            dest = QRectF(
                (self.width() - shown_w) / 2,
                (self.height() - shown_h) / 2,
                shown_w, shown_h,
            )
            painter.drawPixmap(
                dest, self._pixmap,
                QRectF(0, 0, self._pixmap.width(), self._pixmap.height()))
        else:
            painter.setPen(QColor("#C5D6E5"))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(
                bounds.adjusted(20, 12, -20, -12),
                Qt.AlignCenter | Qt.TextWordWrap,
                self._message,
            )
        painter.restore()
        painter.setPen(QPen(QColor("#305064"), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(bounds.adjusted(.5, .5, -.5, -.5), 8, 8)


def request_screenshot(window, record, widget: ScreenshotImage, on_ready=None):
    """Asynchronously decode one scanned screenshot and ignore destroyed UI."""
    from shiboken6 import isValid
    if record not in window.inventory.screenshots or not is_unchanged(record):
        widget.set_status("Screenshot changed. Scan PC again to refresh.")
        return
    widget.set_status("Loading your actual screenshot from this PC…")
    widget.setProperty("sourcePath", record.path)

    def ready(image):
        if not isValid(widget) or widget.property("sourcePath") != record.path:
            return
        if not is_unchanged(record):
            widget.set_status("Screenshot changed since the scan. Scan again.")
            return
        widget.set_image(image)
        if on_ready:
            on_ready(image)

    # Errors can be nonfatal for the dashboard; never launch deletion if a
    # preview fails. The existing desktop job runner handles user-visible errors.
    window.job(
        lambda _emitter: decode_capture_for_display(record),
        ready,
        error_title="Screenshot thumbnail could not be displayed",
    )
