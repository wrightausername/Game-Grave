"""Non-modal, persistent, user-controlled local AI companion for Crimson Command.

Dock to the right of any tab, float as a separate window, resize, minimize or
close it. Chat does not navigate away from the user's current workspace.
Existing optional local AI engine remains opt-in and has no deletion authority.
Only aggregate inventory counts are supplied automatically.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDockWidget, QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QPushButton, QVBoxLayout, QWidget,
)
from shiboken6 import isValid

from local_ai import ask_local_assistant


class AiCompanion(QDockWidget):
    def __init__(self, window):
        super().__init__("Game Grave AI  •  Local companion", window)
        self.owner = window
        self.setObjectName("aiCompanionDock")
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.setFeatures(
            QDockWidget.DockWidgetClosable |
            QDockWidget.DockWidgetMovable |
            QDockWidget.DockWidgetFloatable
        )
        self.setMinimumWidth(330)
        self.resize(405, 630)
        self.setAccessibleName(
            "Optional AI companion. Dock or detach and continue navigating Game Grave.")
        self.setToolTip(
            "Float this assistant to continue working in other tabs while getting help.")
        root = QWidget()
        root.setObjectName("aiCompanionBody")
        self.setWidget(root)
        col = QVBoxLayout(root)
        col.setContentsMargins(13, 12, 13, 12)
        col.setSpacing(10)

        title = QLabel("GAME GRAVE  /  AI ASSISTANT")
        title.setObjectName("eyebrow")
        col.addWidget(title)
        caption = QLabel(
            "A companion, not a separate tab. Keep browsing your files while "
            "asking questions. The model runs locally and cannot delete anything.")
        caption.setObjectName("subtle")
        caption.setWordWrap(True)
        col.addWidget(caption)
        toolbar = QHBoxLayout()
        self.detach_btn = QPushButton("Pop out ↗")
        self.detach_btn.clicked.connect(self.toggle_floating)
        toolbar.addWidget(self.detach_btn)
        dock_btn = QPushButton("Dock right")
        dock_btn.clicked.connect(self.dock_right)
        toolbar.addWidget(dock_btn)
        toolbar.addStretch()
        col.addLayout(toolbar)

        self.transcript = QPlainTextEdit()
        self.transcript.setObjectName("aiTranscript")
        self.transcript.setReadOnly(True)
        self.transcript.setPlaceholderText(
            "Ask how to use Graveyard, Mod Radar, Game DNA, screenshots, "
            "Resurrection Kits, or anything else about Game Grave.")
        col.addWidget(self.transcript, 1)

        quick = QHBoxLayout()
        for label, query in (
            ("Graveyard help", "How do I review and recycle a protected Graveyard item?"),
            ("Mod Radar", "How does Mod Radar identify leftover mods safely?"),
        ):
            control = QPushButton(label)
            control.setObjectName("link")
            control.setToolTip(query)
            control.clicked.connect(lambda _=False, q=query: self.ask(q))
            quick.addWidget(control)
        col.addLayout(quick)

        entry = QHBoxLayout()
        self.question = QLineEdit()
        self.question.setMaxLength(800)
        self.question.setPlaceholderText("Ask Game Grave AI…")
        self.question.setAccessibleName("Question for local AI assistant")
        self.send = QPushButton("Send")
        self.send.setObjectName("primary")
        self.send.clicked.connect(self.submit)
        self.question.returnPressed.connect(self.submit)
        entry.addWidget(self.question, 1)
        entry.addWidget(self.send)
        col.addLayout(entry)

        self.status_label = QLabel(
            "Local-only AI. No automatic cleanup, file-content upload, or stored transcript.")
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("caption")
        col.addWidget(self.status_label)
        self.topLevelChanged.connect(self._floating_changed)
        self._busy = False

    def toggle_floating(self):
        self.setFloating(not self.isFloating())
        self.show()
        self.raise_()

    def dock_right(self):
        if self.isFloating():
            self.setFloating(False)
        self.owner.addDockWidget(Qt.RightDockWidgetArea, self)
        self.show()

    def _floating_changed(self, floating):
        self.detach_btn.setText("Docked ✓" if floating else "Pop out ↗")
        self.status_label.setText(
            "Pop-out is independent: switch tabs in Game Grave while chatting."
            if floating else
            "Docked on the right. Work in any Game Grave tab while chatting.")

    def submit(self):
        self.ask(self.question.text().strip())

    def ask(self, query: str):
        query = str(query).strip()[:800]
        if not query or self._busy:
            return
        if self.owner.settings.get("ai_assistant_enabled") is not True:
            self.status_label.setText("AI has been disabled in Settings.")
            return
        self._busy = True
        self.transcript.appendPlainText("YOU\n" + query + "\n")
        self.question.clear()
        self.question.setEnabled(False)
        self.send.setEnabled(False)
        self.status_label.setText("Running the local model…")
        settings = dict(self.owner.settings)
        inventory = self.owner.inventory

        def background(_emitter):
            from local_ai import AssistantUnavailable
            try:
                return True, ask_local_assistant(query, settings, inventory)
            except AssistantUnavailable as error:
                return False, str(error)
            except Exception:
                return False, "Local AI could not complete the request."

        def finished(result):
            if not isValid(self):
                return
            ok, response = result
            self.transcript.appendPlainText(
                ("GAME GRAVE AI\n" if ok else "AI UNAVAILABLE\n")
                + str(response) + "\n")
            self._busy = False
            self.question.setEnabled(True)
            self.send.setEnabled(True)
            self.question.setFocus()
            self.status_label.setText(
                "Local answer complete. No files were changed."
                if ok else "Local assistant unavailable. Normal features still work.")

        self.owner.job(
            background, finished,
            error_title="Local AI companion request could not finish")


def open_companion(window):
    if window.settings.get("ai_assistant_enabled") is not True:
        window._settings_category_index = 4
        window.navigate("Settings")
        window.info(
            "AI is optional and disabled",
            "Enable the AI Assistant in Settings. Game Grave will install "
            "the local engine after your approval. You can then open the "
            "companion next to any other tab.")
        return
    instance = getattr(window, "_ai_companion", None)
    if instance is None or not isValid(instance):
        instance = AiCompanion(window)
        window.addDockWidget(Qt.RightDockWidgetArea, instance)
        window._ai_companion = instance
    instance.show()
    instance.raise_()
    instance.question.setFocus()
