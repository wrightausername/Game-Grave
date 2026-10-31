"""Optional local AI chat window for the Crimson Qt preview."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
    QVBoxLayout,
)
from local_ai import ask_local_assistant


def open_local_ai_dialog(window) -> None:
    if window.settings.get("ai_assistant_enabled") is not True:
        window.info("AI Assistant disabled", "Enable the optional AI Assistant in Settings.")
        return
    dialog = getattr(window, "_ai_dialog", None)
    if dialog is not None:
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        return

    dialog = QDialog(window)
    dialog.setWindowTitle("Game Grave | Local AI Assistant")
    dialog.setMinimumSize(620, 460)
    layout = QVBoxLayout(dialog)

    notice = QLabel(
        "Built-in private AI. Game Grave installs the model automatically "
        "after your permission in Settings. Only anonymous scan counts are "
        "included automatically. No cloud AI or automatic deletion. "
        "Chat is not saved."
    )
    notice.setWordWrap(True)
    layout.addWidget(notice)

    transcript = QPlainTextEdit()
    transcript.setReadOnly(True)
    transcript.setPlaceholderText("Ask about gaming storage, Mod Radar, or recovery.")
    layout.addWidget(transcript, 1)

    entry_row = QHBoxLayout()
    question = QLineEdit()
    question.setPlaceholderText("Ask a question (800 characters max)")
    question.setMaxLength(800)
    send = QPushButton("Ask local AI")
    entry_row.addWidget(question, 1)
    entry_row.addWidget(send)
    layout.addLayout(entry_row)

    status = QLabel("AI never gains file deletion authority.")
    status.setWordWrap(True)
    layout.addWidget(status)

    def submit():
        query = question.text().strip()
        if not query or not send.isEnabled():
            return
        transcript.appendPlainText("You: " + query + "\n")
        question.clear()
        question.setEnabled(False)
        send.setEnabled(False)
        status.setText("Waiting for the local model. No cloud request is made.")
        settings = dict(window.settings)
        inventory = window.inventory

        def finish(answer):
            transcript.appendPlainText("Assistant: " + answer + "\n")
            status.setText("Local response complete. No files were changed.")
            question.setEnabled(True)
            send.setEnabled(True)
            question.setFocus()

        def failed_answer(message):
            transcript.appendPlainText("Assistant unavailable: " + message + "\n")
            status.setText("Local AI not ready. No files were changed.")
            question.setEnabled(True)
            send.setEnabled(True)

        # Our existing background job runner prevents the model blocking the UI.
        # Catch expected service errors locally so the generic job runner does
        # not generate an additional scary error popup.
        def worker(_emitter):
            from local_ai import AssistantUnavailable
            try:
                return (True, ask_local_assistant(query, settings, inventory))
            except AssistantUnavailable as exc:
                return (False, str(exc))

        def complete(result):
            ok, message = result
            if ok:
                finish(message)
            else:
                failed_answer(message)

        window.job(worker, complete, error_title="Local AI request failed")

    send.clicked.connect(submit)
    question.returnPressed.connect(submit)
    window._ai_dialog = dialog
    dialog.show()
    dialog.raise_()
