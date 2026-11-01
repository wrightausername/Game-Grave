"""Visual-first, local-only slideshow for scanned gaming screenshots.

Autoplay shows each inventory image for five seconds; the list is never sampled.
Only one bounded preview is decoded at a time, with no permanent image cache.
No deletion action exists here. Scanning, cleanup and uploads are never started
by the timer. The timer stops when Captures is hidden or the app is inactive.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from gg_desktop.capture_image import ScreenshotImage, request_screenshot


SLIDE_INTERVAL_MS = 5000


class CaptureSlideshow(QFrame):
    """Autoplay every detected game screenshot, no fake/sample images."""

    def __init__(self, host, screenshots, parent=None):
        super().__init__(parent)
        self.host = host
        self.records = list(screenshots)
        self.index = 0
        self.playing = bool(self.records)
        self.setObjectName("captureSlideshow")
        self.setAccessibleName("Automatically cycling gaming screenshot slideshow")
        self.setMinimumWidth(0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)

        heading = QHBoxLayout()
        title = QLabel("SCREENSHOT GALLERY")
        title.setObjectName("captureSlideshowHeading")
        heading.addWidget(title)
        heading.addStretch()
        self.position = QLabel("")
        self.position.setObjectName("captureSlideshowCount")
        heading.addWidget(self.position)
        layout.addLayout(heading)

        self.preview = ScreenshotImage(height=355, parent=self)
        self.preview.setAccessibleName("Currently displayed game screenshot")
        layout.addWidget(self.preview)
        self.description = QLabel("")
        self.description.setWordWrap(True)
        self.description.setObjectName("captureSlideshowDescription")
        layout.addWidget(self.description)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.previous_button = QPushButton("◀  Previous")
        self.previous_button.clicked.connect(self.previous)
        self.play_button = QPushButton("❚❚  Pause")
        self.play_button.setObjectName("captureSlideshowPlay")
        self.play_button.clicked.connect(self.toggle_play)
        self.next_button = QPushButton("Next  ▶")
        self.next_button.clicked.connect(self.next)
        for control in (self.previous_button, self.play_button, self.next_button):
            actions.addWidget(control)
        actions.addStretch(1)
        note = QLabel("5 sec / image  •  loops all detected screenshots")
        note.setObjectName("captureSlideshowNote")
        actions.addWidget(note)
        layout.addLayout(actions)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(SLIDE_INTERVAL_MS)
        self.timer.timeout.connect(self._advance)
        if not self.records:
            self.playing = False
            self.preview.set_status("No game screenshots detected. Scan PC to build your gallery.")
        self._display()

    def _display(self):
        total = len(self.records)
        for control in (self.previous_button, self.next_button, self.play_button):
            control.setEnabled(total > 0)
        self.play_button.setText("❚❚  Pause" if self.playing else "▶  Play")
        self.position.setText(f"{self.index + 1:,} / {total:,}" if total else "0 / 0")
        if not total:
            self.description.setText("Your own game captures will appear here after a scan.")
            self.timer.stop()
            return

        item = self.records[self.index]
        self.description.setText(
            f"{Path(item.path).name}  •  "
            f"{datetime.fromtimestamp(item.modified):%b %d, %Y at %I:%M %p}")
        # Reuse the existing identity-checking asynchronous image loader.
        # It rejects stale replies when a different sourcePath is selected.
        request_screenshot(self.host, item, self.preview)
        self._schedule_next()

    def _schedule_next(self):
        self.timer.stop()
        if (self.playing and self.records and self.isVisible()
                and self.host.isActiveWindow()):
            self.timer.start()

    def _advance(self):
        # Never read another image while Game Grave is in the background or
        # after switching to Videos, another tab, or a running fullscreen game.
        if not self.isVisible() or not self.host.isActiveWindow():
            return
        if self.playing and self.records:
            self.index = (self.index + 1) % len(self.records)
            self._display()

    def jump_to(self, index):
        if not self.records or not 0 <= index < len(self.records):
            return
        self.index = index
        self._display()

    def previous(self):
        if self.records:
            self.index = (self.index - 1) % len(self.records)
            self._display()

    def next(self):
        if self.records:
            self.index = (self.index + 1) % len(self.records)
            self._display()

    def toggle_play(self):
        if not self.records:
            return
        self.playing = not self.playing
        self.play_button.setText("❚❚  Pause" if self.playing else "▶  Play")
        self._schedule_next()

    def showEvent(self, event):
        super().showEvent(event)
        self._schedule_next()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def set_records(self, records):
        """Keep slideshow consistent after deliberate fullscreen review."""
        previous = self.records[self.index].path if self.records else ""
        self.records = list(records)
        self.index = next(
            (i for i, rec in enumerate(self.records) if rec.path == previous), 0)
        self.playing = bool(self.records) and self.playing
        if not self.records:
            self.preview.set_status("No screenshots remain in this review list.")
        self._display()
