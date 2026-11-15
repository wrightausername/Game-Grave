"""The AI Assistant in its own small window (owner, 2026-11-14: "an easy way to pop the ai assistant chat menu out ... so you can
follow along without swapping back and forth losing track").

The same chat as the AI Assistant tab, so a plan started in one shows its progress in both. It stays on top of Game Grave
by default (Keep on top can be switched off), remembers where it was and how big, and can be opened from the top bar's
chat button, from the tab's Pop out button, or with Ctrl+Shift+A. Asking "how do I use this tab" from here answers about
the tab you are looking at in the main window.
"""
from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QFrame, QLabel, QLineEdit, QScrollArea, QWidget
from shiboken6 import isValid

from gg_desktop.widgets import column, label, row

GEOMETRY_KEY = "assistant_popout_geometry"
ON_TOP_KEY = "assistant_popout_on_top"


def current(window):
    pop = getattr(window, "_assistant_popout", None)
    return pop if pop is not None and isValid(pop) and pop.isVisible() else None


class AssistantPopout(QWidget):
    def __init__(self, window):
        super().__init__(window, Qt.Window)
        from gg_desktop.reference_widgets import icon, tool
        from gg_desktop.theme import STYLE
        self.window_ = window
        self.setObjectName("assistantPopout")
        self.setWindowTitle("Game Grave Assistant")
        self.setStyleSheet(STYLE + "QWidget#assistantPopout{background:#06090d;}")
        self.setMinimumSize(360, 420)
        self.resize(460, 720)
        lay = column(spacing=0, margins=(0, 0, 0, 0))
        self.setLayout(lay)
        head = QFrame()
        head.setObjectName("popoutHead")
        head.setStyleSheet("QFrame#popoutHead{background:#0b1118;border-bottom:1px solid #3a1420;}")
        top = row(spacing=6, margins=(12, 8, 8, 8))
        head.setLayout(top)
        mark = QLabel()
        mark.setPixmap(icon("sparkles", "#ff3b57", 18).pixmap(18, 18))
        top.addWidget(mark)
        self.title = label("New chat", "sectionTitle")
        self.title.setMinimumWidth(0)
        top.addWidget(self.title, 1)
        self.new_button = tool("", "plus", self.new_chat, tip="New chat")
        self.new_button.setAccessibleName("New chat")
        self.pin = tool("", "pin", self.toggle_on_top, tip="Keep on top of other windows")
        self.pin.setCheckable(True)
        self.pin.setAccessibleName("Keep on top")
        self.full = tool("", "maximize", self.open_full, tip="Open the full AI Assistant tab")
        self.full.setAccessibleName("Open the full AI Assistant tab")
        for control in (self.new_button, self.pin, self.full):
            control.setFixedSize(30, 28)
            top.addWidget(control)
        lay.addWidget(head)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea{background:transparent;} QScrollArea > QWidget > QWidget{background:transparent;}")
        holder = QWidget()
        self.messages = column(spacing=10, margins=(10, 8, 10, 8))
        holder.setLayout(self.messages)
        self.scroll.setWidget(holder)
        lay.addWidget(self.scroll, 1)
        self.where = label("", "caption")
        self.where.setStyleSheet("padding:2px 12px;color:#8fa0b3;")
        lay.addWidget(self.where)
        compose = row(spacing=6, margins=(10, 6, 10, 10))
        self.input = QLineEdit()
        self.input.setPlaceholderText("Ask, or say what to do…")
        self.input.setAccessibleName("Message the assistant")
        self.input.setFixedHeight(34)
        self.input.returnPressed.connect(self.send)
        compose.addWidget(self.input, 1)
        self.send_button = tool("Send", "next", self.send, kind="primary", tip="Ask (Enter)")
        self.send_button.setFixedHeight(34)
        compose.addWidget(self.send_button)
        lay.addLayout(compose)
        QShortcut(QKeySequence("Escape"), self, activated=self.close)
        on_top = window.settings.get(ON_TOP_KEY, True) is not False
        self.pin.setChecked(on_top)
        self._apply_on_top(on_top, show=False)
        saved = window.settings.get(GEOMETRY_KEY)
        if isinstance(saved, str) and saved:
            try:
                self.restoreGeometry(QByteArray.fromBase64(saved.encode("ascii")))
            except Exception:
                pass

    # -------------------------------------------------------------- actions
    def send(self):
        from gg_desktop import assistant_page
        assistant_page.send(self.window_, None, source=self.input)

    def new_chat(self):
        from gg_desktop import assistant_page
        assistant_page.new_chat(self.window_)
        self.input.setFocus()

    def open_full(self):
        self.window_.navigate("AI Assistant")
        self.window_.raise_()
        self.window_.activateWindow()

    def toggle_on_top(self):
        on = self.pin.isChecked()
        self._apply_on_top(on)
        from gg_desktop import assistant_page
        assistant_page.save(self.window_, dict(self.window_.settings, **{ON_TOP_KEY: on}))

    def _apply_on_top(self, on, show=True):
        self.setWindowFlag(Qt.WindowStaysOnTopHint, bool(on))
        self.pin.setToolTip("Kept on top. Press to let other windows cover it." if on else
                            "Press to keep it on top of other windows.")
        if show:
            self.show()

    def refresh(self):
        from gg_desktop import assistant_page
        assistant_page.ensure_chats(self.window_)
        assistant_page.render_chat(self.window_, self.messages, self.title, self.scroll, compact=True)
        self.follow()

    def follow(self, route=None):
        """Say which tab the main window shows, so "how do I use this tab" is clear."""
        from gg_desktop.nav_groups import display_name
        route = route or getattr(self.window_, "current_route", "")
        if route and route != "AI Assistant":
            self.where.setText("You're on: " + display_name(route) + ". Ask \"how do I use this tab?\"")
        else:
            self.where.setText("")

    def closeEvent(self, event):
        from gg_desktop import assistant_page
        try:
            geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
            assistant_page.save(self.window_, dict(self.window_.settings, **{GEOMETRY_KEY: geometry}))
        except Exception:
            pass
        super().closeEvent(event)


def open_popout(window):
    """Show the pop-out chat (or bring it forward). Returns it."""
    if not window.assistant_enabled():
        window.info("AI Assistant is off", "Turn on the AI Assistant in Settings first.")
        return None
    pop = getattr(window, "_assistant_popout", None)
    if pop is None or not isValid(pop):
        pop = window._assistant_popout = AssistantPopout(window)
    pop.refresh()
    pop.show()
    pop.raise_()
    pop.activateWindow()
    pop.input.setFocus()
    return pop


def toggle(window):
    pop = current(window)
    if pop is not None:
        pop.close()
        return None
    return open_popout(window)
