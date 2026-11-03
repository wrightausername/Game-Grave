"""Approved optional AI Assistant page: local-only, working conversation and context.

The in-page chat is enabled only after the user explicitly opts in from Settings.
No game hooks, background prompts, file contents, deletion, path changes or
unreviewed repair actions are provided to the assistant.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from ai_bundle import is_ai_installed
from gg_desktop.reference_hero import ReferenceHero
from gg_desktop.widgets import button, label, panel, row


def _label(text, *, color="#B6C6D7", font=11, strong=False, wrap=True):
    w = label(str(text), "caption", wrap=wrap)
    w.setTextInteractionFlags(Qt.TextSelectableByMouse)
    w.setStyleSheet("background:transparent;color:" + color +
                    f";font-size:{font}px;" +
                    ("font-weight:800;" if strong else ""))
    return w


def _small_status(title, data, color):
    section = QFrame()
    section.setObjectName("approvedAIStatus")
    col = QVBoxLayout(section)
    col.setContentsMargins(9, 5, 9, 5)
    col.setSpacing(3)
    col.addWidget(_label(title.upper(), color="#AEBECC", font=10, strong=True))
    col.addWidget(_label(data, color=color, font=16, strong=True))
    return section


def render_approved_ai(window):
    page = window.page_for("AI Assistant")
    page.content.setContentsMargins(11, 7, 11, 17)
    page.content.setSpacing(9)
    page.content.addWidget(ReferenceHero(
        "assistant", "AI Assistant",
        "Your private, opt-in gaming expert for help, analysis and cleanup guidance."))
    enabled = window.settings.get("ai_assistant_enabled") is True
    installed = is_ai_installed()

    statuses = QWidget()
    ss = row(spacing=8)
    statuses.setLayout(ss)
    for title, value, color in (
        ("AI Engine", "Enabled" if enabled else "Off", "#85DCAE" if enabled else "#F1B27F"),
        ("Local Model", "Installed" if installed else "Not installed",
         "#68D0E8" if installed else "#F1B27F"),
        ("Privacy", "Local-only", "#9CB8EE"),
        ("Permissions", "Read-only", "#D6A9ED"),
    ):
        ss.addWidget(_small_status(title, value, color), 1)
    ss.addWidget(button("Settings", lambda: window.navigate("Settings")))
    page.content.addWidget(statuses)

    workspace = QWidget()
    wrow = row(spacing=9)
    workspace.setLayout(wrow)

    modes, ml = panel(padding=9, spacing=6)
    ml.addWidget(_label("WORKFLOWS", color="#FFFFFF", font=14, strong=True))
    destinations = (
        ("Chat & Explain", "AI Assistant",
         "Ask about real Game Grave findings"),
        ("Analyze Games", "Game DNA",
         "Review evidence-backed game relationships"),
        ("Mod Help", "Mods",
         "Check detected mod manager locations"),
        ("Storage Cleanup", "Graveyard",
         "Review candidate files manually"),
        ("Resurrection Kits", "More Tools",
         "Preserve and recover configurations"),
        ("Capture Studio", "Captures",
         "Review captured game media"),
        ("Recovery", "Undo Center",
         "Verify actual Recycle Bin history"),
    )
    for name, route, tooltip in destinations:
        action = button(name + "   ›",
                        lambda _=False, route=route: (
                            entry.setFocus() if route == "AI Assistant"
                            else window.navigate(route)))
        action.setObjectName("approvedAIWorkflow")
        action.setToolTip(tooltip)
        ml.addWidget(action)
    ml.addStretch()
    wrow.addWidget(modes, 3)

    hub, chat = panel(padding=10, spacing=9)
    chat.addWidget(_label("GAME GRAVE AI", color="#FFFFFF", font=15, strong=True))
    chat.addWidget(_label(
        "A local assistant for understanding scans. It cannot delete, "
        "unprotect or repair files.", color="#ADBCC9", font=11))
    transcript = QPlainTextEdit()
    transcript.setReadOnly(True)
    transcript.setMinimumHeight(260)
    transcript.setAccessibleName("Local AI conversation history for this session")
    transcript.setPlaceholderText(
        "Ask Game Grave AI about your gaming storage, detected mods, "
        "Resurrection Kit, or recovering files.")
    chat.addWidget(transcript, 1)

    request = QWidget()
    entry_row = row(spacing=7)
    request.setLayout(entry_row)
    entry = QLineEdit()
    entry.setMaxLength(800)
    entry.setPlaceholderText("Ask Game Grave AI…")
    entry.setAccessibleName("Optional local AI question")
    entry_row.addWidget(entry, 1)
    send = button("Send", kind="primary")
    entry_row.addWidget(send)
    chat.addWidget(request)
    status_line = _label(
        "Local AI is off. Enable it in Settings; core tools work without it."
        if not enabled else
        "Install the local model through Settings first."
        if not installed else
        "Local-only: questions run on your PC, not through a cloud service.",
        color="#9CC1BB" if enabled and installed else "#E4B17C")
    chat.addWidget(status_line)
    send.setEnabled(enabled and installed)
    entry.setEnabled(enabled and installed)

    busy = {"value": False}
    def submit():
        query = entry.text().strip()
        if busy["value"] or not query or not enabled or not installed:
            return
        transcript.appendPlainText("You: " + query + "\n")
        entry.clear()
        busy["value"] = True
        send.setEnabled(False)
        entry.setEnabled(False)
        status_line.setText("Asking your local AI. No cleanup is permitted.")
        settings = dict(window.settings)
        inventory = window.inventory

        def ask(_progress):
            from local_ai import AssistantUnavailable, ask_local_assistant
            try:
                return True, ask_local_assistant(query, settings, inventory)
            except AssistantUnavailable as exc:
                return False, str(exc)

        def finish(result):
            ok, message = result
            transcript.appendPlainText(
                ("Game Grave AI: " if ok else "AI unavailable: ") +
                str(message) + "\n")
            status_line.setText("No files changed. Conversation stays in this session.")
            busy["value"] = False
            entry.setEnabled(True)
            send.setEnabled(True)
            entry.setFocus()

        def job_failure():
            busy["value"] = False
            entry.setEnabled(True)
            send.setEnabled(True)
        window.job(ask, finish, error_title="Local AI could not answer")
    send.clicked.connect(submit)
    entry.returnPressed.connect(submit)
    wrow.addWidget(hub, 6)

    side, scol = panel(padding=10, spacing=8)
    scol.addWidget(_label("ACTIVE CONTEXT", color="#FFFFFF", font=14, strong=True))
    if window.inventory.scanned_at:
        scol.addWidget(_label(
            f"{len(window.inventory.games)} games • "
            f"{len(window.inventory.mods)} mod locations",
            color="#DDE7F2", font=13, strong=True))
        scol.addWidget(_label(
            f"{len(window.inventory.graveyard)} Graveyard candidates • "
            f"{len(window.inventory.saves)} protected save locations"))
    else:
        scol.addWidget(_label(
            "No inventory scan yet. The assistant does not invent results."))
    scol.addWidget(_label("SOURCE & PRIVACY", color="#EDB9C5",
                          font=11, strong=True))
    scol.addWidget(_label(
        "Only the local AI engine receives your question and aggregate "
        "inventory context. No filenames, game lists, screenshots or save "
        "contents are automatically shared."))
    scol.addWidget(button(
        "Open Game DNA", lambda: window.navigate("Game DNA")))
    scol.addWidget(button(
        "Review Mod Radar", lambda: window.navigate("Mods")))
    scol.addWidget(button(
        "Open Save Vault", lambda: window.navigate("More Tools")))
    scol.addStretch()
    wrow.addWidget(side, 3)
    page.content.addWidget(workspace)

    quick, qcol = panel(padding=9, spacing=6)
    qcol.addWidget(_label("QUICK WORKFLOWS", color="#FFFFFF",
                          font=13, strong=True))
    cards = QWidget()
    grid = QGridLayout(cards)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setSpacing(7)
    for idx, (title, route) in enumerate((
        ("Clean My Games", "Graveyard"),
        ("Improve Storage", "Other Storage"),
        ("Check Mods", "Mods"),
        ("After a Patch", "Game DNA"),
        ("Backup Setup", "More Tools"),
        ("Recover Files", "Undo Center"),
    )):
        control = button(title + "   ›",
                         lambda _=False, route=route: window.navigate(route))
        control.setObjectName("approvedAIWorkflow")
        grid.addWidget(control, idx // 3, idx % 3)
    qcol.addWidget(cards)
    page.content.addWidget(quick)
    return page
