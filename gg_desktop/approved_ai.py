"""Approved optional AI Assistant page: local-only, working conversation and context.

The in-page chat is enabled only after the user explicitly opts in from Settings.
No game hooks, background prompts, file contents, deletion, path changes or
unreviewed repair actions are provided to the assistant.
"""
from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QTextBrowser,
    QPushButton, QVBoxLayout, QWidget,
)

from ai_bundle import is_ai_installed
from gg_desktop.reference_hero import ReferenceHero
from gg_desktop.widgets import button, label, panel, row
from gg_desktop.cinematic_art import CinematicToolArtwork
from gg_desktop.responsive import ResponsiveGrid
from gg_desktop.inspector_widgets import InspectorFacts, detail_section


def _label(text, *, color="#B6C6D7", font=11, strong=False, wrap=True):
    w = label(str(text), "caption", wrap=wrap)
    w.setTextInteractionFlags(Qt.TextSelectableByMouse)
    w.setStyleSheet("background:transparent;color:" + color +
                    f";font-size:{font}px;" +
                    ("font-weight:800;" if strong else ""))
    return w


def _small_status(title, data, color):
    section = QFrame()
    section.setObjectName("ggStatusChip")
    col = QVBoxLayout(section)
    col.setContentsMargins(12, 6, 12, 6)
    col.setSpacing(3)
    col.addWidget(_label(title.upper(), color="#AEBECC", font=10, strong=True))
    col.addWidget(_label(data, color=color, font=19, strong=True))
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
    # Session state belongs to the window, not to widgets destroyed on navigation.
    if not hasattr(window, "_ai_session"):
        window._ai_session = {"messages": [], "busy": False, "status": ""}
    session = window._ai_session

    statuses = ResponsiveGrid(columns=((0, 1), (500, 2), (1000, 5)))
    ss = statuses
    for title, value, color in (
        ("AI Engine", "Enabled" if enabled else "Off", "#85DCAE" if enabled else "#F1B27F"),
        ("Local Model", "Installed" if installed else "Not installed",
         "#68D0E8" if installed else "#F1B27F"),
        ("Privacy", "Local-only", "#9CB8EE"),
        ("Permissions", "Read-only", "#D6A9ED"),
    ):
        ss.addWidget(_small_status(title, value, color))
    def configure_ai():
        window._settings_category_index = 4
        window.navigate("Settings")
    ss.addWidget(button("Configure local AI", configure_ai))
    page.content.addWidget(statuses)

    workspace = ResponsiveGrid(
        columns=((0, 1), (620, 2), (1000, 14)), spacing=9,
        positions={
            1: ((1, 0, 1, 1), (0, 0, 1, 1), (2, 0, 1, 1)),
            2: ((1, 0, 1, 1), (0, 0, 1, 2), (1, 1, 1, 1)),
            14: ((0, 0, 1, 3), (0, 3, 1, 7), (0, 10, 1, 4)),
        })
    workspace.setObjectName("approvedAIWorkspace")
    wrow = workspace

    modes, ml = panel(padding=9, spacing=6)
    modes.setObjectName("contextPanel")
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
        ("Custom Tools", "More Tools",
         "Open available advanced Game Grave utilities"),
    )
    for name, route, tooltip in destinations:
        action = button(name + "   ›",
                        lambda _=False, route=route: (
                            entry.setFocus() if route == "AI Assistant"
                            else window.navigate(route)))
        action.setObjectName(
            "approvedAIModeActive" if route == "AI Assistant"
            else "approvedAIWorkflow")
        action.setMinimumHeight(27)
        action.setToolTip(tooltip)
        ml.addWidget(action)
    ml.addStretch()
    wrow.addWidget(modes)

    hub, chat = panel(padding=10, spacing=9)
    heading = QWidget()
    heading_row = row(spacing=9)
    heading.setLayout(heading_row)
    welcome = QLabel("GG")
    welcome.setObjectName("ggAssistantWelcomeArt")
    welcome.setAlignment(Qt.AlignCenter)
    welcome.setFixedSize(40, 40)
    welcome.setStyleSheet("color:#FF697C;background:#351524;border:1px solid #B33A55;"
                         "border-radius:20px;font-size:15px;font-weight:850;")
    heading_row.addWidget(welcome)
    titles = QWidget()
    title_col = QVBoxLayout(titles)
    title_col.setContentsMargins(0,0,0,0)
    title_col.setSpacing(2)
    title_col.addWidget(_label("GAME GRAVE AI", color="#FFFFFF", font=14, strong=True))
    title_col.addWidget(_label("Private • Local • Read-only guidance", font=10))
    heading_row.addWidget(titles, 1)
    chat.addWidget(heading)
    if not (enabled and installed):
        offline = _label(
            "ENGINE OFFLINE  •  Enable local AI in Settings to ask questions. "
            "All other Game Grave tools remain fully usable.",
            color="#F0C188", font=10, strong=True)
        chat.addWidget(offline)
    transcript = QTextBrowser()
    transcript.setReadOnly(True)
    transcript.setOpenExternalLinks(False)
    transcript.setMinimumHeight(230)
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

    rendered = {"text": None}
    def refresh_session():
        from shiboken6 import isValid
        if not isValid(transcript):
            return
        text = "\n\n".join(session["messages"])
        if rendered["text"] != text:
            rendered["text"] = text
            blocks = []
            for message in session["messages"]:
                speaker, separator, content = message.partition(":")
                accent = "#F27488" if speaker == "You" else "#70DCB4"
                content = content if separator else message
                background = "#241823" if speaker == "You" else "#14211F"
                blocks.append(
                    '<table width="100%" cellspacing="0" cellpadding="8"><tr><td bgcolor="' +
                    background + '" style="border-left:2px solid ' + accent + ';">'
                    '<span style="font-weight:700;color:' + accent + ';">' +
                    escape(speaker if separator else "Game Grave AI") + '</span><br>' +
                    '<span style="color:#D6DFE9;line-height:1.5;">' +
                    escape(content.strip()).replace("\n", "<br>") +
                    '</span></td></tr></table><p style="margin:0;font-size:4px;">&nbsp;</p>')
            if not blocks:
                blocks.append('<h3 style="color:#EBE5F0;">Your gaming workspace, explained.</h3>'
                    '<p style="color:#AEBCCB;">Ask about a detected game, mod location, '
                    'cleanup candidate or recovery action.</p>'
                    '<p style="color:#D7AD86;">Local AI is optional. Enable it in Settings '
                    'when you want to start a conversation.</p>')
            transcript.setHtml(''.join(blocks))
            transcript.verticalScrollBar().setValue(
                transcript.verticalScrollBar().maximum())
        ready = (window.settings.get("ai_assistant_enabled") is True
                 and installed and not session["busy"])
        entry.setEnabled(ready)
        send.setEnabled(ready)
        if session["busy"]:
            status_line.setText("Asking your local AI. No cleanup is permitted.")
        elif session["status"]:
            status_line.setText(session["status"])

    window._refresh_ai_session = refresh_session
    refresh_session()

    def update_current_view():
        if window.current_route == "AI Assistant":
            window._refresh_ai_session()

    def submit():
        query = entry.text().strip()
        if (session["busy"] or not query or not installed
                or window.settings.get("ai_assistant_enabled") is not True):
            return
        session["messages"].append("You: " + query)
        entry.clear()
        session["busy"] = True
        refresh_session()
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
            session["messages"].append(
                ("Game Grave AI: " if ok else "AI unavailable: ") +
                str(message))
            session["status"] = "No files changed. Conversation stays in this session."
            session["busy"] = False
            update_current_view()

        def job_failure():
            session["busy"] = False
            session["status"] = "Local AI could not answer. You can try again."
            update_current_view()
        window.job(ask, finish, error_title="Local AI could not answer",
                   on_failure=job_failure)
    send.clicked.connect(submit)
    entry.returnPressed.connect(submit)
    wrow.addWidget(hub)

    side, scol = panel(padding=11, spacing=7)
    side.setObjectName("contextPanel")
    side.setAccessibleName("Local AI inventory context and investigation links")
    scol.addWidget(_label("ACTIVE CONTEXT", color="#FFFFFF", font=14, strong=True))
    if window.inventory.scanned_at:
        scol.addWidget(InspectorFacts((
            ("Installed games", len(window.inventory.games)),
            ("Mod locations", len(window.inventory.mods)),
            ("Graveyard candidates", len(window.inventory.graveyard)),
            ("Protected save locations", len(window.inventory.saves)),
            ("Capture files", len(window.inventory.screenshots) +
             len(window.inventory.recordings)),
        )))
    else:
        scol.addWidget(_label(
            "No inventory scan yet. The assistant does not invent results."))
    scol.addWidget(detail_section("Source & privacy"))
    scol.addWidget(_label(
        "Questions and aggregate context stay local. No automatic sharing "
        "of filenames, screenshots or save contents.", font=10))
    scol.addWidget(detail_section("Investigate"))
    for title, route, detail in (
        ("Game DNA", "Game DNA", "Inspect the selected game's storage relationships"),
        ("Mod Radar", "Mods", "Review detected manager and mod locations"),
        ("Save Vault", "More Tools", "Create a backup before making changes"),
    ):
        link = button(title + "   ›", lambda _=False, route=route: window.navigate(route))
        link.setObjectName("contextAction")
        link.setToolTip(detail)
        scol.addWidget(link)
    scol.addStretch()
    wrow.addWidget(side)
    page.content.addWidget(workspace)

    quick, qcol = panel(padding=9, spacing=6)
    qcol.addWidget(_label("QUICK WORKFLOWS", color="#FFFFFF",
                          font=13, strong=True))
    cards = ResponsiveGrid(columns=((0, 1), (490, 2), (700, 3), (1200, 6)), spacing=7)
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
        control.setObjectName("approvedAIQuickTile")
        control.setMinimumHeight(40)
        control.setAccessibleName("Open " + title + " workflow")
        cards.addWidget(control)
    qcol.addWidget(cards)
    page.content.addWidget(quick)
    return page
