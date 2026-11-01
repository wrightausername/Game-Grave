"""Fullscreen, keyboard/touch-friendly screenshot review.

Only scanned gaming captures are reviewed. Images are decoded on demand in
low-priority workers; no bulk image deletion is possible. Each Recycle Bin
move is a separate, explicitly requested action verified by the existing
file-identity, protected-path, restore-canary and Undo systems.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from dataclasses import replace
import time
import uuid

from PySide6.QtCore import Qt, QEvent, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
from shiboken6 import isValid

from core import is_protected_path, is_unchanged
from graveyard import GraveyardEntry
from gg_desktop.backend import refresh_graveyard
from screenshot_preview import decode_screenshot_preview


class CaptureReviewDialog(QDialog):
    """One full-screen review session, one acknowledgement, many decisions."""

    def __init__(self, window, records, start=0):
        super().__init__(window)
        self.host = window
        self.records = [r for r in records if r in window.inventory.screenshots]
        self.index = min(max(0, start), max(0, len(self.records) - 1))
        self.acknowledged = False  # reset whenever this window is reopened
        self.busy = False
        self._shown_image = False
        self._image = QPixmap()
        self._request = 0
        self._mouse_start = None
        self.setWindowTitle("Game Grave | Screenshot Review")
        self.setObjectName("captureReviewDialog")
        self.setMinimumSize(640, 460)
        self.setStyleSheet(
            "QDialog#captureReviewDialog {background:#060D16;color:#EAF5FC;}"
            "QLabel {background:transparent;color:#EAF5FC;}"
            "QPushButton {min-height:32px;padding:7px 12px;}"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 17, 24, 20)
        outer.setSpacing(12)
        self.heading = QLabel("Screenshot review")
        self.heading.setStyleSheet("font-size:19px;font-weight:800;color:#F0F6FA;")
        outer.addWidget(self.heading)
        self.picture = QLabel()
        self.picture.setObjectName("captureReviewPicture")
        self.picture.setAlignment(Qt.AlignCenter)
        self.picture.setMinimumHeight(250)
        self.picture.setStyleSheet("background:#07121D;border:1px solid #294757;")
        self.picture.installEventFilter(self)
        self.picture.setMouseTracking(True)
        outer.addWidget(self.picture, 1)
        self.state = QLabel("")
        self.state.setWordWrap(True)
        outer.addWidget(self.state)
        guide = QLabel(
            "← Recycle  ·  → Keep  ·  ↑ Previous  ·  ↓ Next  ·  "
            "Swipe left to Recycle, right to Keep  ·  Esc Close")
        guide.setAlignment(Qt.AlignCenter)
        guide.setStyleSheet("color:#91B4C7;")
        outer.addWidget(guide)
        controls = QHBoxLayout()
        self.prev_btn = self._button("◀ Previous", self.previous)
        self.next_btn = self._button("Next ▶", self.next)
        self.keep_btn = self._button("Keep →", self.keep)
        self.recycle_btn = self._button("Recycle ←", self.recycle)
        self.recycle_btn.setStyleSheet("background:#8A233D;color:white;font-weight:800;")
        self.close_btn = self._button("Close", self.reject)
        for widget in (
            self.prev_btn, self.next_btn, self.keep_btn, self.recycle_btn, self.close_btn,
        ):
            controls.addWidget(widget)
        outer.addLayout(controls)
        self.state.setText("Use arrow keys or swipe to review images.")
        self.picture.setText("Preparing fullscreen review…")

    @staticmethod
    def _button(text, action):
        control = QPushButton(text)
        control.clicked.connect(action)
        control.setFocusPolicy(Qt.NoFocus)  # arrow keys always remain review actions
        return control

    def start_fullscreen(self):
        self.setWindowState(self.windowState() | Qt.WindowFullScreen)
        # Decode only after a visible dialog can receive the worker callback.
        QTimer.singleShot(0, self._display)
        return self.exec()

    def _set_busy(self, state):
        self.busy = bool(state)
        for btn in (self.prev_btn, self.next_btn, self.keep_btn, self.recycle_btn):
            btn.setEnabled(not self.busy)

    def _current(self):
        return self.records[self.index] if 0 <= self.index < len(self.records) else None

    def _scale_image(self):
        if self._image.isNull():
            return
        size = self.picture.size()
        if size.width() < 2 or size.height() < 2:
            return
        self.picture.setPixmap(
            self._image.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._scale_image()

    def _display(self):
        record = self._current()
        self._image = QPixmap()
        self._shown_image = False
        if record is None:
            self.picture.setText("No more screenshots in this session.")
            self.heading.setText("Screenshot review complete")
            self.state.setText("No files were deleted permanently.")
            self._set_busy(False)
            self.keep_btn.setEnabled(False)
            self.recycle_btn.setEnabled(False)
            return
        self.heading.setText(
            f"{self.index + 1:,} of {len(self.records):,}  •  {Path(record.path).name}")
        self.picture.setText("Loading verified screenshot…")
        self.state.setText("Only this image is being decoded locally.")
        if record not in self.host.inventory.screenshots or not is_unchanged(record):
            self.picture.setText("This screenshot changed since the last scan.")
            self.state.setText("Scan again before reviewing or recycling this file.")
            self._set_busy(False)
            self.recycle_btn.setEnabled(False)
            return
        self._set_busy(True)
        self._request += 1
        request_number = self._request

        def decode(_):
            try:
                return True, decode_screenshot_preview(record)
            except (OSError, ValueError, RuntimeError) as exc:
                return False, str(exc)[:200]

        def shown(result):
            if not isValid(self) or not self.isVisible() or request_number != self._request:
                return
            valid, payload = result
            self._set_busy(False)
            if not valid or not is_unchanged(record):
                self.picture.setText("Preview unavailable. Rescan before deleting.")
                self.state.setText("Could not safely decode this image.")
                self.recycle_btn.setEnabled(False)
                return
            rgb = payload.convert("RGB") if payload.mode != "RGB" else payload
            qimg = QImage(rgb.tobytes(), rgb.width, rgb.height,
                          rgb.width * 3, QImage.Format_RGB888).copy()
            self._image = QPixmap.fromImage(qimg)
            self.picture.clear()
            self._scale_image()
            self._shown_image = True
            self.state.setText(
                "Choose Keep or Recycle. Nothing happens to other screenshots.")
            self.recycle_btn.setEnabled(
                not is_protected_path(Path(record.path),
                                      self.host.settings.get("never_touch", [])))
        self.host.job(decode, shown, error_title="Screenshot could not be displayed")

    def previous(self):
        if not self.busy and self.records:
            self.index = max(0, self.index - 1)
            self._display()

    def next(self):
        if not self.busy and self.records:
            self.index = min(len(self.records) - 1, self.index + 1)
            self._display()

    def keep(self):
        if self.busy:
            return
        if self.index + 1 < len(self.records):
            self.index += 1
            self._display()
        else:
            self.state.setText("Kept this screenshot. End of review session.")

    def recycle(self):
        record = self._current()
        if (record is None or self.busy or not self._shown_image or
                record not in self.host.inventory.screenshots or
                not is_unchanged(record)):
            return
        if is_protected_path(Path(record.path), self.host.settings.get("never_touch", [])):
            self.state.setText("This image is protected and cannot be recycled.")
            return
        if not self.acknowledged:
            accepted = self.host.confirm(
                "Enable fast screenshot review for this session?",
                "Each LEFT ARROW or LEFT SWIPE will request a move of the CURRENT "
                "displayed screenshot to Windows Recycle Bin without another popup. "
                "RIGHT ARROW / RIGHT SWIPE keeps the image. "
                "This approval ends when you close this fullscreen review. "
                "There is no permanent-delete fallback. All file identity, "
                "protection and Windows recovery checks still run per file. "
                "Recycle Bin contents can still be lost or emptied.",
                destructive=True)
            if not accepted:
                self.state.setText("No changes made. Screenshot kept.")
                return
            self.acknowledged = True
        from cleanup_actions import recycle_reviewed_entries
        age_days = max(0, int((time.time() - record.modified) / 86400))
        item = GraveyardEntry(
            key="screenshot:review:" + record.path.casefold(),
            name=Path(record.path).name, path=record.path,
            category="Old game screenshot", apparent_bytes=record.size,
            age_days=age_days,
            relationship="User previewed exact scanned screenshot",
            finding="Reviewed image in fullscreen Captures session",
            protection="Individual review required", can_recycle=True,
            old_file=record, screenshot_reviewed=True)
        rules = tuple(self.host.settings.get("never_touch", []))
        session = "capture-review-" + uuid.uuid4().hex[:10]
        self._set_busy(True)
        self.state.setText("Windows is verifying this file and Recycle Bin recovery…")

        def work(_):
            return recycle_reviewed_entries([item], rules, session,
                                            managed_roots=tuple(
                                                g.install_path for g in
                                                self.host.inventory.games))

        def finished(outcome):
            if outcome["completed"] == 1:
                self.host.inventory.screenshots = [
                    x for x in self.host.inventory.screenshots if x.path != record.path]
                refresh_graveyard(self.host.inventory, self.host.settings)
                self.host.status.setText(
                    "1 reviewed screenshot moved to Windows Recycle Bin. "
                    "No automatic file deletion.")
                if isValid(self) and self.isVisible():
                    self.records = [x for x in self.records if x.path != record.path]
                    self.index = min(self.index, max(0, len(self.records) - 1))
                    self._set_busy(False)
                    self._display()
                    if outcome.get("recovery_warnings"):
                        self.state.setText(
                            "Moved to Recycle Bin, but Undo logging was incomplete. "
                            "Check Windows Recycle Bin.")
            elif isValid(self) and self.isVisible():
                self._set_busy(False)
                self.state.setText(
                    "Not recycled. " + "; ".join(outcome.get("skipped", [])[:2]))
        self.host.job(work, finished, error_title="Screenshot was not recycled")

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Left, Qt.Key_D):
            self.recycle()
            event.accept()
        elif event.key() in (Qt.Key_Right, Qt.Key_K):
            self.keep()
            event.accept()
        elif event.key() in (Qt.Key_Up, Qt.Key_PageUp):
            self.previous()
            event.accept()
        elif event.key() in (Qt.Key_Down, Qt.Key_PageDown):
            self.next()
            event.accept()
        else:
            super().keyPressEvent(event)

    def eventFilter(self, widget, event):
        if widget is self.picture:
            if event.type() == QEvent.MouseButtonPress:
                self._mouse_start = event.position().x()
            elif event.type() == QEvent.MouseButtonRelease and self._mouse_start is not None:
                distance = event.position().x() - self._mouse_start
                self._mouse_start = None
                if distance < -110:
                    self.recycle()
                    return True
                if distance > 110:
                    self.keep()
                    return True
        return super().eventFilter(widget, event)
