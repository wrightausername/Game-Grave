"""First-launch welcome window (Qt). Facts and wording live in welcome_data.py.

A new window over the app, shown once from main(); it changes no tab, the shell or navigation. Closing it in any way
(Skip, Esc, the last button) saves `welcome_seen`. "Scan my games" starts the same read-only scan as Scan PC.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from gg_desktop import welcome_data

STYLE = """
QDialog#welcome { background: #080C13; }
QFrame#welcomeCard { background: #111922; border: 1px solid #2A3541; border-radius: 16px; }
QLabel#welcomeBrand { font-size: 17px; font-weight: 900; letter-spacing: 1px; color: #F6FAFF; }
QLabel#welcomeKicker { color: #42D4F2; font-size: 11px; font-weight: 700; letter-spacing: 2px; }
QLabel#welcomeTitle { font-size: 30px; font-weight: 900; color: #F6FAFF; }
QLabel#welcomeBody { font-size: 14px; color: #D7E1ED; }
QFrame#welcomePoint { background: #0C151C; border: 1px solid #2A3541; border-radius: 10px; }
QLabel#welcomePointName { font-size: 14px; font-weight: 700; color: #F4F7FC; }
QLabel#welcomePointText { font-size: 13px; color: #A3B4C5; }
QLabel#welcomeTick { color: #69DEA7; font-size: 16px; font-weight: 900; }
QFrame#welcomeBar { background: #25303C; border-radius: 2px; }
QFrame#welcomeBar[on="true"] { background: #FF4357; }
QPushButton#welcomeSkip { background: transparent; border: none; color: #A3B4C5; padding: 8px 4px; }
QPushButton#welcomeSkip:hover { color: #FFFFFF; }
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
        self.setFixedSize(680, 600)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        card = QFrame()
        card.setObjectName("welcomeCard")
        outer.addWidget(card)
        box = QVBoxLayout(card)
        box.setContentsMargins(36, 30, 36, 30)
        box.setSpacing(18)

        top = QHBoxLayout()
        top.addWidget(_label("GAME GRAVE", "welcomeBrand"))
        top.addStretch(1)
        self.skip_button = QPushButton("Skip intro")
        self.skip_button.setObjectName("welcomeSkip")
        self.skip_button.setAccessibleName("Skip the welcome intro")
        self.skip_button.clicked.connect(self.reject)
        top.addWidget(self.skip_button)
        box.addLayout(top)

        bars = QHBoxLayout()
        bars.setSpacing(8)
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
        for _ in range(3):
            frame = QFrame()
            frame.setObjectName("welcomePoint")
            line = QHBoxLayout(frame)
            line.setContentsMargins(16, 12, 16, 12)
            line.setSpacing(14)
            line.addWidget(_label("✓", "welcomeTick"), 0, Qt.AlignTop)
            texts = QVBoxLayout()
            texts.setSpacing(3)
            name = _label("", "welcomePointName")
            text = _label("", "welcomePointText", wrap=True)
            texts.addWidget(name)
            texts.addWidget(text)
            line.addLayout(texts, 1)
            box.addWidget(frame)
            self.point_rows.append((name, text))

        box.addStretch(1)
        actions = QHBoxLayout()
        self.back_button = QPushButton("Back")
        self.back_button.setAccessibleName("Previous welcome screen")
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
        self.kicker.setText(step["kicker"])
        self.title.setText(step["title"])
        self.body.setText(step["body"])
        for (name, text), (point_name, point_text) in zip(self.point_rows, step["points"]):
            name.setText(point_name)
            text.setText(point_text)
        for position, bar in enumerate(self.bars):
            on = position <= self.index
            if bar.property("on") != on:
                bar.setProperty("on", on)
                bar.style().unpolish(bar)
                bar.style().polish(bar)
        self.back_button.setVisible(self.index > 0)
        self.next_button.setText(welcome_data.next_label(self.index))
        self.next_button.setAccessibleName(welcome_data.next_label(self.index))

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

    def _on_finished(self, _result):
        self._save_seen()
        if self.scan_requested:
            start = getattr(self.window_ref, "start_scan", None)
            if callable(start):
                start()

    def _save_seen(self):
        if self._saved:
            return
        self._saved = True
        try:
            from gg_desktop.settings_store import load_settings
            from core import save_settings
            save_settings(welcome_data.mark_seen(load_settings()))
            current = getattr(self.window_ref, "settings", None)
            if isinstance(current, dict):
                current[welcome_data.SEEN_KEY] = True
        except Exception:
            pass  # a settings write that fails only means the welcome shows once more next time


def show_if_needed(window) -> WelcomeDialog | None:
    if not welcome_data.should_show(getattr(window, "settings", {}),
                                    reference_preview=bool(getattr(window, "reference_preview", False))):
        return None
    dialog = WelcomeDialog(window)
    window._welcome_dialog = dialog
    dialog.open()
    return dialog
