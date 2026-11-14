"""Welcome tour window (Qt). Wording and the startup rules live in welcome_data.py.

A window over the app. Shown at startup from main() while the setting is on, and on demand from Settings or the ? button.
Skip closes it for now; "Don't show this at startup" or finishing turns the startup tour off. "Scan my games" on the last
screen starts the same read-only scan as Scan PC.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout)

from gg_desktop import welcome_data

STYLE = """
QDialog#welcome { background: #080C13; }
QFrame#welcomeCard { background: #111922; border: 1px solid #2A3541; border-radius: 16px; }
QLabel#welcomeBrand { font-size: 17px; font-weight: 900; letter-spacing: 1px; color: #F6FAFF; }
QLabel#welcomeCount { color: #8C9AA9; font-size: 12px; }
QLabel#welcomeKicker { color: #42D4F2; font-size: 11px; font-weight: 700; letter-spacing: 2px; }
QLabel#welcomeTitle { font-size: 28px; font-weight: 900; color: #F6FAFF; }
QLabel#welcomeBody { font-size: 13.5px; color: #D7E1ED; }
QFrame#welcomePoint { background: #0C151C; border: 1px solid #2A3541; border-radius: 10px; }
QLabel#welcomePointName { font-size: 13.5px; font-weight: 700; color: #F4F7FC; }
QLabel#welcomePointText { font-size: 12.5px; color: #A3B4C5; }
QLabel#welcomeTick { color: #69DEA7; font-size: 15px; font-weight: 900; }
QFrame#welcomeBar { background: #25303C; border-radius: 2px; }
QFrame#welcomeBar[on="true"] { background: #FF4357; }
QPushButton#welcomeSkip { background: transparent; border: none; color: #A3B4C5; padding: 8px 4px; }
QPushButton#welcomeSkip:hover { color: #FFFFFF; }
QCheckBox#welcomeNever { color: #A3B4C5; font-size: 12px; spacing: 8px; }
"""


def _label(text, role, wrap=False):
    widget = QLabel(text)
    widget.setObjectName(role)
    widget.setTextFormat(Qt.PlainText)
    widget.setWordWrap(wrap)
    return widget


class WelcomeDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window_ref = window
        self.index = 0
        self.scan_requested = False
        self._saved = False
        self.setObjectName("welcome")
        self.setWindowTitle("Welcome to Game Grave")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setModal(True)
        self.setStyleSheet(STYLE)
        self.setFixedSize(700, 660)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        card = QFrame()
        card.setObjectName("welcomeCard")
        outer.addWidget(card)
        box = QVBoxLayout(card)
        box.setContentsMargins(34, 26, 34, 22)
        box.setSpacing(14)

        top = QHBoxLayout()
        top.addWidget(_label("GAME GRAVE", "welcomeBrand"))
        top.addSpacing(12)
        self.count = _label("", "welcomeCount")
        top.addWidget(self.count)
        top.addStretch(1)
        self.skip_button = QPushButton("Skip intro")
        self.skip_button.setObjectName("welcomeSkip")
        self.skip_button.clicked.connect(self.reject)
        top.addWidget(self.skip_button)
        box.addLayout(top)

        bars = QHBoxLayout()
        bars.setSpacing(6)
        self.bars = []
        for _ in welcome_data.STEPS:
            bar = QFrame()
            bar.setObjectName("welcomeBar")
            bar.setFixedHeight(4)
            bars.addWidget(bar, 1)
            self.bars.append(bar)
        box.addLayout(bars)

        self.kicker = _label("", "welcomeKicker")
        self.title = _label("", "welcomeTitle", wrap=True)
        self.body = _label("", "welcomeBody", wrap=True)
        for widget in (self.kicker, self.title, self.body):
            box.addWidget(widget)

        self.point_rows = []
        for _ in range(welcome_data.MAX_POINTS):
            frame = QFrame()
            frame.setObjectName("welcomePoint")
            line = QHBoxLayout(frame)
            line.setContentsMargins(14, 9, 14, 9)
            line.setSpacing(12)
            line.addWidget(_label("✓", "welcomeTick"), 0, Qt.AlignTop)
            texts = QVBoxLayout()
            texts.setSpacing(2)
            name = _label("", "welcomePointName")
            text = _label("", "welcomePointText", wrap=True)
            texts.addWidget(name)
            texts.addWidget(text)
            line.addLayout(texts, 1)
            box.addWidget(frame)
            self.point_rows.append((frame, name, text))

        box.addStretch(1)
        self.never = QCheckBox("Don't show this at startup")
        self.never.setObjectName("welcomeNever")
        self.never.setAccessibleName("Don't show the welcome tour at startup")
        box.addWidget(self.never)
        actions = QHBoxLayout()
        self.back_button = QPushButton("Back")
        self.back_button.setAccessibleName("Previous screen")
        self.back_button.clicked.connect(self.back)
        self.next_button = QPushButton("Next")
        self.next_button.setObjectName("primary")
        self.next_button.setDefault(True)
        self.next_button.clicked.connect(self.advance)
        for control in (self.back_button, self.next_button):
            control.setMinimumHeight(40)
            control.setMinimumWidth(130)
        actions.addWidget(self.back_button)
        actions.addStretch(1)
        actions.addWidget(self.next_button)
        box.addLayout(actions)

        self.finished.connect(self._on_finished)
        self.render()

    def render(self):
        step = welcome_data.STEPS[self.index]
        self.count.setText(welcome_data.step_caption(self.index))
        self.kicker.setText(step["kicker"])
        self.title.setText(step["title"])
        self.body.setText(step["body"])
        points = step["points"]
        for position, (frame, name, text) in enumerate(self.point_rows):
            shown = position < len(points)
            frame.setVisible(shown)
            if shown:
                name.setText(points[position][0])
                text.setText(points[position][1])
        for position, bar in enumerate(self.bars):
            on = position <= self.index
            if bar.property("on") != on:
                bar.setProperty("on", on)
                bar.style().unpolish(bar)
                bar.style().polish(bar)
        self.back_button.setVisible(self.index > 0)
        caption = welcome_data.next_label(self.index)
        self.next_button.setText(caption)
        self.next_button.setAccessibleName(caption)
        close = welcome_data.close_label(self.index)
        self.skip_button.setText(close)
        self.skip_button.setAccessibleName(close + " the welcome tour")

    def advance(self):
        if self.index >= welcome_data.LAST:
            self.scan_requested = True
            self.accept()
            return
        self.index = welcome_data.clamp(self.index + 1)
        self.render()

    def back(self):
        self.index = welcome_data.clamp(self.index - 1)
        self.render()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Right:
            self.advance() if self.index < welcome_data.LAST else None
            return
        if event.key() == Qt.Key_Left:
            self.back()
            return
        super().keyPressEvent(event)

    def _on_finished(self, _result):
        self._save_choice()
        if self.scan_requested:
            start = getattr(self.window_ref, "start_scan", None)
            if callable(start):
                start()

    def _save_choice(self):
        if self._saved:
            return
        self._saved = True
        current = getattr(self.window_ref, "settings", None)
        before = (current or {}).get(welcome_data.STARTUP_KEY, True) is not False
        on = welcome_data.startup_after(finished=self.index == welcome_data.LAST, dont_show=self.never.isChecked(), current=before)
        if on == before:
            return
        try:
            from gg_desktop.settings_store import load_settings
            from core import save_settings
            save_settings(welcome_data.with_startup(load_settings(), on))
            if isinstance(current, dict):
                current[welcome_data.STARTUP_KEY] = on
        except Exception:
            pass  # a settings write that fails only means the tour shows once more next time
        refresh = getattr(self.window_ref, "_welcome_setting_changed", None)
        if callable(refresh):
            refresh()


def open_tour(window, *, blocking: bool = True) -> WelcomeDialog:
    """Show the tour now. From Settings or the ? button it is a normal modal window like Help used to be; at startup it
    opens without blocking. The startup choice is kept unless the owner ticks the box or finishes the tour."""
    old = getattr(window, "_welcome_dialog", None)
    try:
        if old is not None and old.isVisible():
            old.raise_()
            return old
    except RuntimeError:
        pass
    dialog = WelcomeDialog(window)
    window._welcome_dialog = dialog
    if blocking:
        dialog.exec()
    else:
        dialog.open()
    return dialog


def show_if_needed(window) -> WelcomeDialog | None:
    if not welcome_data.should_show(getattr(window, "settings", {}),
                                    reference_preview=bool(getattr(window, "reference_preview", False))):
        return None
    return open_tour(window, blocking=False)
