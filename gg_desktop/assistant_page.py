"""AI Assistant page: the approved mockup, answering only from data Game Grave has already scanned.

There is no online service. Questions are answered locally by gg_desktop.assistant_engine from the in-memory inventory,
the recovery records and the activity log. The assistant is read only: it never deletes, moves, restores or scans, and
every row that names files hands the owner to the tab that owns them. Conversations are saved in the owner's settings.
"""
from __future__ import annotations

from gg_desktop.nav_groups import display_name

from types import SimpleNamespace
import re
import time

from PySide6.QtCore import QEvent, QObject, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QPainter
from PySide6.QtWidgets import (QFrame, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
                               QScrollArea, QSizePolicy, QWidget)
from shiboken6 import isValid

from core import get_activity, save_settings
from recovery import get_records
from gg_desktop import assistant_actions as actions
from gg_desktop import local_ai_ui
from gg_desktop import assistant_data as data
from gg_desktop import assistant_engine as engine
from gg_desktop.grave_page import CheckRow
from gg_desktop.header_banner import HeaderBannerArtwork
from gg_desktop.insight_widgets import ActionFlow
from gg_desktop.reference_library import _detail_scroll, _split, _widget
from gg_desktop.reference_widgets import MetricStrip, icon, tool
from gg_desktop.widgets import button, column, label, panel, row

SUBTITLE = "Ask about your games, mods and storage. Answers come from data scanned on this PC."
ROW_COLORS = ("#30d76b", "#13bcf5", "#f2a5b2", "#f6be24", "#b455ff", "#ff254a")
WELCOME = ("Ask about your games, storage, mods or captures. I answer from what Game Grave scanned on this PC, and I "
           "never change any file.")
GRAVEKEEPER_WELCOME = ("Ask me anything about your games, mods or this PC, or just tell me what's wrong. I check before I "
                       "answer, and nothing changes without your OK.")
KEEPER_SUGGESTIONS = (
    ("warning", "Something's broken", "My game keeps crashing, can you help?"),
    ("game", "What should I play?", "What should I play tonight?"),
    ("list", "Where did my space go?", "Where did all my space go?"),
    ("sparkles", "Make it run better", "My game stutters, what can I do?"),
    ("star", "Play with friends", "Which of my games are good for co-op?"),
    ("check", "Check my PC", "Give my PC a quick health check"),
)
WELCOME_TOOLS = ("Ask a question, or tell me what to do. I show a plan first, and nothing changes until you press Run all.")
PROMPT_CHIP = ("QPushButton{background:#0f161e;border:1px solid #243243;border-radius:13px;color:#c9d4df;font-size:11px;"
               "padding:0 10px;text-align:left;} QPushButton:hover{border-color:#e5243b;color:#ffffff;}")
PILL = ("QLabel{{color:{0};background:{1};border:1px solid {0};border-radius:10px;padding:2px 9px;font-size:11px;"
        "font-weight:700;}}")
SUGGESTIONS = (   # the empty chat's cards: (icon, title, example asked when clicked)
    ("list", "Largest games", "What are my largest games by size?"),
    ("storage", "Free up space", "Where can I free up space?"),
    ("warning", "Fix a game", "My game won't start, fix it"),
    ("game", "Play with friends", "What can my friends and I play together?"),
    ("sparkles", "Make a game run better", "How do I make a game run better?"),
    ("trash", "Clean temp files", "Clean up my temp files"),
)
ACCENTS = {"red": "255,37,74", "yellow": "246,190,36", "cyan": "19,188,245", "green": "50,214,122"}


def accent(frame, name, tone):
    rgb = ACCENTS[tone]
    frame.setObjectName(name)
    frame.setStyleSheet(   # calm: one quiet border, a thin coloured line on top, a faint tint
        f"QFrame#{name}{{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba({rgb},14),stop:.25 #0a1017,stop:1 #080d13);"
        f"border:1px solid #1b2633;border-top:2px solid rgba({rgb},170);border-radius:12px;}}")
    return frame


class Bar(QWidget):
    """A thin share bar in the row's own colour."""

    def __init__(self, share, color):
        super().__init__()
        self.share, self.color = share, QColor(color)
        self.setFixedHeight(5)

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#1a2430"))
        painter.drawRoundedRect(QRectF(0, 0, self.width(), 4), 2, 2)
        painter.setBrush(self.color)
        painter.drawRoundedRect(QRectF(0, 0, max(3.0, self.width() * max(0.0, min(1.0, self.share))), 4), 2, 2)


def row_game(window, item):
    """The installed game a Games row is about, so its button can show that game instead of the whole tab."""
    if item.tab != "Games":
        return ""
    inventory = getattr(window, "inventory", None)
    names = {g.name for g in getattr(inventory, "games", ()) or ()}
    for candidate in (item.label, item.label.split(" (")[0]):
        if candidate in names:
            return candidate
    return ""


def open_link(window, href):
    """A link in an answer: a game opens in Games, a tab opens, a folder opens in File Explorer. Nothing is changed."""
    kind, _, value = str(href).partition(":")
    if kind == "game":
        show_in_games(window, value)
    elif kind == "tab":
        window.navigate(value)
    elif kind == "path":
        import os
        target = value if os.path.isdir(value) else os.path.dirname(value)
        if target and os.path.isdir(target):
            try:
                os.startfile(target)
            except (OSError, AttributeError):
                window.status.setText("That folder couldn't be opened.")
        else:
            window.status.setText("That folder isn't there any more.")


def _icon_names():
    from gg_desktop import reference_widgets
    return reference_widgets.PATHS


WEB_HOSTS = ("pcgamingwiki.com", "store.steampowered.com", "nexusmods.com", "steamcommunity.com")


def open_web(window, url):
    """Opens a page the Gravekeeper linked, only on the hosts it may link to, in the user's browser."""
    import urllib.parse
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtCore import QUrl
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    if urllib.parse.urlsplit(url).scheme != "https" or not any(host == h or host.endswith("." + h) for h in WEB_HOSTS):
        window.status.setText("That link isn't one Game Grave opens.")
        return
    QDesktopServices.openUrl(QUrl(url))
    window.status.setText("Opened in your browser.")


def open_tool(window, key):
    from gg_desktop import assistant_features as features, autopilot_ui
    feature = features.BY_KEY.get(key)
    if feature is not None and feature.opens:
        autopilot_ui.open_target(window, feature.opens)


def row_game_name(window, question):
    """The installed game a question names, for follow-up buttons ("Is Hades modded?")."""
    games = sorted((g.name for g in getattr(getattr(window, "inventory", None), "games", []) or []), key=len, reverse=True)
    q = (question or "").casefold()
    return next((g for g in games if len(g) >= 3 and g.casefold() in q), "")


def show_in_games(window, name):
    """Open Games filtered to one game by its search box. Nothing is launched or changed."""
    window.navigate("Games")
    search = getattr(window, "game_search", None)
    if search is not None and isValid(search):
        search.setText(name)


class AnswerRow(QFrame):
    def __init__(self, window, item, color):
        super().__init__()
        self.setObjectName("assistantRow")
        self.setStyleSheet("QFrame#assistantRow{background:#0a1118;border:1px solid #1d2a38;border-radius:6px;}")
        line = row(spacing=8, margins=(9, 5, 7, 5))
        self.setLayout(line)
        words = column(spacing=3)
        top = row(spacing=6)
        name = label(item.label, "detailValue")
        name.setTextFormat(Qt.PlainText)
        name.setMinimumWidth(0)
        name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        name.setToolTip(item.detail or item.label)
        top.addWidget(name, 1)
        value = label(item.value, "detailValue")
        value.setTextFormat(Qt.PlainText)
        value.setStyleSheet("font-weight:700;color:#ffffff;")
        top.addWidget(value)
        words.addLayout(top)
        if item.share is not None:
            words.addWidget(Bar(item.share, color))
        line.addLayout(words, 1)
        game = row_game(window, item)
        if game:
            go = tool("Show", "next", lambda _=False, g=game: show_in_games(window, g), tip=f"Show {game} in Games")
        elif item.tab:
            go = tool("Open", "next", lambda _=False, tab=item.tab: window.navigate(tab), tip="Open " + display_name(item.tab))
            go.setText("Open " + display_name(item.tab))
        if game or item.tab:
            go.setIcon(icon("next", "#e8eef5", 12))
            go.setFixedHeight(26)
            go.setStyleSheet("font-size:11px;padding:0 9px;")
            line.addWidget(go)


class Avatar(QLabel):
    def __init__(self):
        super().__init__()
        self.setFixedSize(30, 30)
        self.setAlignment(Qt.AlignCenter)
        self.setPixmap(icon("sparkles", "#ff5a73", 16).pixmap(16, 16))
        self.setStyleSheet("background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #3a0d18,stop:1 #170910);"
                           "border:1px solid #5c1726;border-radius:15px;")


def bubble(text):
    wrap = QWidget()
    line = row(spacing=0, margins=(40, 0, 0, 0))
    wrap.setLayout(line)
    line.addStretch()
    frame = QFrame()
    frame.setObjectName("assistantAsk")
    frame.setStyleSheet("QFrame#assistantAsk{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #4a1220,stop:1 #2a0c15);"
                        "border:1px solid #6a1a2b;border-radius:14px;border-bottom-right-radius:4px;}")
    inner = column(spacing=0, margins=(12, 8, 12, 8))
    frame.setLayout(inner)
    text_label = label(text, "subtle", wrap=True)
    text_label.setTextFormat(Qt.PlainText)
    text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    text_label.setStyleSheet("color:#f2f5f8;font-size:13px;")
    inner.addWidget(text_label)
    frame.setMaximumWidth(430)
    line.addWidget(frame)
    return wrap


def chip(text, tone):
    rgb = {"blue": ("#13bcf5", "#1b5f78", "#07151c"), "green": ("#30d76b", "#1c6a3a", "#07160d")}[tone]
    chip_label = QLabel(text)
    chip_label.setStyleSheet(f"color:{rgb[0]};border:1px solid {rgb[1]};background:{rgb[2]};border-radius:4px;"
                             "padding:1px 6px;font-size:10px;font-weight:700;")
    return chip_label


# ------------------------------------------------------------------ state
def state_of(window):
    if not hasattr(window, "_assistant_state"):
        window._assistant_state = SimpleNamespace(chats=[], current="", scope="", enabled=frozenset(data.DEFAULT_ENABLED),
                                                  facts=None, last_question="")
    return window._assistant_state


def live(window):
    return (window.current_route == "AI Assistant" and hasattr(window, "assistant_input")
            and isValid(window.assistant_input) and hasattr(window.page, "assistant_ready"))


def current_chat(window):
    state = state_of(window)
    return next((c for c in state.chats if c["id"] == state.current), None)


def make_facts(window):
    state = state_of(window)
    try:
        records, events = get_records(), get_activity()
    except Exception:  # unreadable history must not stop the assistant; the history source simply stays empty
        records, events = [], []
    state.facts = data.build_facts(window.inventory, records, events, enabled=state.enabled, scope=state.scope,
                                   hardware=getattr(window, "hardware_specs", None))
    return state.facts


def save(window, settings):
    try:
        save_settings(settings)
    except (OSError, ValueError) as exc:
        window.error("Not saved", str(exc))
        return False
    window.settings = settings
    return True


def persist_chats(window):
    state = state_of(window)
    saved = [c for c in state.chats if c["messages"]]
    return save(window, actions.with_chats(window.settings, saved))


# ------------------------------------------------------------------ page
def build(window):
    self = window
    state = state_of(self)
    state.chats = actions.load_chats(self.settings)
    state.enabled = data.enabled_sources(self.settings)
    state.scope = actions.scope_of(self.settings)
    make_facts(self)
    if state.scope and not data.find_game(state.facts, state.scope):
        state.scope = ""
        make_facts(self)
    fresh = actions.new_chat(time.time())
    if state.chats and state.current in {c["id"] for c in state.chats}:
        pass
    elif state.chats:
        state.current = state.chats[0]["id"]
    else:
        state.chats = [fresh]
        state.current = fresh["id"]

    page = self._insight_page("AI Assistant", SUBTITLE, "assistant", "sparkles", 66)
    page.banner_artwork = HeaderBannerArtwork(self, page, page.content.itemAt(0).widget(), route="AI Assistant",
                                              scene="assistant", source=(910, 0, 370, 110), excluded=((1090, 0, 190, 40),))
    self.assistant_metrics = MetricStrip([
        ("list", "0", "Conversations", "#e175eb"), ("game", "0", "Games Indexed", "#30d76b"),
        ("folder", "0", "Items Indexed", "#13bcf5"), ("clock", "—", "Last Full Scan", "#f6be24"),
        ("shield", "Read Only", "Assistant Mode", "#32d67a"), ("storage", "0 of 5", "Data Sources On", "#f2a5b2")],
        compact=True)
    page.content.addWidget(self.assistant_metrics)
    self.assistant_metrics.hide()     # calmer page: the mode is a pill in the chat header, counts live in Data Used

    # --- left: conversations and quick prompts
    convo, side = panel(kind="fileFilterPanel", padding=9, spacing=6)
    accent(convo, "assistantConvos", "red")
    convo.setMinimumWidth(190)
    convo.setMaximumWidth(235)
    head = row(spacing=6)
    mark = QLabel()
    mark.setPixmap(icon("list", "#ff3b57", 18).pixmap(18, 18))
    head.addWidget(mark)
    head.addWidget(label("Conversations", "sectionTitle"), 1)
    self.assistant_delete = tool("", "trash", lambda: delete_chat(self), tip="Delete the selected conversation")
    self.assistant_delete.setFixedSize(26, 26)
    head.addWidget(self.assistant_delete)
    side.addLayout(head)
    side.addWidget(tool("New Chat", "plus", lambda: new_chat(self), kind="primary", tip="Start a new conversation"))
    self.assistant_find = QLineEdit()
    self.assistant_find.setPlaceholderText("Search chats")
    self.assistant_find.setAccessibleName("Search chats")
    self.assistant_find.setClearButtonEnabled(True)
    self.assistant_find.textChanged.connect(lambda _t: fill_list(self))
    side.addWidget(self.assistant_find)
    self.assistant_list = QListWidget()
    self.assistant_list.setObjectName("assistantList")
    self.assistant_list.setAccessibleName("Conversations")
    self.assistant_list.setFrameShape(QFrame.NoFrame)
    self.assistant_list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
    self.assistant_list.setStyleSheet(
        "QListWidget#assistantList{background:transparent;border:0;outline:0;}"
        "QListWidget#assistantList::item{padding:5px 7px;border:1px solid transparent;border-radius:6px;color:#e8eef5;}"
        "QListWidget#assistantList::item:selected{background:rgba(255,37,74,70);border:1px solid #8c1b2f;}"
        "QListWidget#assistantList::item:hover{background:rgba(255,255,255,12);}")
    self.assistant_list.itemSelectionChanged.connect(lambda: pick_chat(self))
    side.addWidget(self.assistant_list, 1)

    left = QWidget()
    left_lay = column(spacing=8)
    left.setLayout(left_lay)
    left_lay.addWidget(convo, 1)
    left.setMinimumWidth(190)
    left.setMaximumWidth(235)

    # --- center: the chat
    chat, body = panel(kind="fileResults", padding=0, spacing=0)
    accent(chat, "assistantChat", "red")
    top = row(spacing=8, margins=(12, 8, 10, 8))
    glyph = QLabel()
    glyph.setPixmap(icon("sparkles", "#ff3b57", 18).pixmap(18, 18))
    top.addWidget(glyph)
    self.assistant_title = label("New chat", "sectionTitle")
    self.assistant_title.setMinimumWidth(0)
    self.assistant_title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    top.addWidget(self.assistant_title, 1)
    self.assistant_mode = QPushButton("Tools: Off")
    self.assistant_mode.setAccessibleName("Assistant mode")
    self.assistant_mode.setCursor(Qt.PointingHandCursor)
    self.assistant_mode.clicked.connect(lambda: show_tools_setting(self))
    top.addWidget(self.assistant_mode)
    self.assistant_scope = tool("All Games", "game", lambda: choose_scope(self),
                                tip="Limit answers to one game, or all games")
    self.assistant_scope.setFixedHeight(28)
    top.addWidget(self.assistant_scope)
    clear_button = tool("", "eraser", lambda: clear(self), tip="Clear this chat (asks first, removes its saved messages)")
    clear_button.setAccessibleName("Clear Chat")
    clear_button.setFixedSize(30, 28)
    top.addWidget(clear_button)
    self.assistant_side_button = tool("Settings", "settings", lambda: toggle_side(self),
                                      tip="Show or hide Local AI, Automation and the data the answers use")
    self.assistant_side_button.setCheckable(True)
    top.addWidget(self.assistant_side_button)
    body.addLayout(top)
    self.assistant_scroll = QScrollArea()
    self.assistant_scroll.setWidgetResizable(True)
    self.assistant_scroll.setFrameShape(QFrame.NoFrame)
    self.assistant_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    self.assistant_scroll.setStyleSheet("QScrollArea{background:transparent;} QScrollArea > QWidget > QWidget{background:transparent;}")
    holder = QWidget()
    self.assistant_messages = column(spacing=10, margins=(12, 6, 12, 8))
    holder.setLayout(self.assistant_messages)
    self.assistant_scroll.setWidget(holder)
    body.addWidget(self.assistant_scroll, 1)

    prompt_box = QWidget()
    prompt_box.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    prompt_box.setMinimumWidth(0)
    prompt_row = ActionFlow(spacing=6)
    prompt_row.setContentsMargins(14, 6, 14, 0)
    prompt_box.setLayout(prompt_row)
    for symbol, text, question in engine.QUICK_PROMPTS:
        chip_button = tool(text, symbol, lambda _=False, q=question: send(self, q), tip=question)
        chip_button.setFixedHeight(26)
        chip_button.setStyleSheet(PROMPT_CHIP)
        prompt_row.addWidget(chip_button)
    body.addWidget(prompt_box)
    self.assistant_prompts = prompt_box
    compose_box = QFrame()
    compose_box.setObjectName("assistantCompose")
    compose_box.setStyleSheet("QFrame#assistantCompose{background:#0d141c;border:1px solid #263445;border-radius:22px;}"
                              "QFrame#assistantCompose QLineEdit{background:transparent;border:0;color:#f2f5f8;"
                              "font-size:13px;padding:0 4px;}")
    compose = row(spacing=6, margins=(14, 4, 5, 4))
    compose_box.setLayout(compose)
    self.assistant_input = QLineEdit()
    self.assistant_input.setPlaceholderText("Ask anything, or tell me what to do… (Enter to send)")
    self.assistant_input.setAccessibleName("Message the assistant")
    self.assistant_input.setMaxLength(engine_limit())
    self.assistant_input.setFixedHeight(36)
    self.assistant_input.setMinimumWidth(60)
    self.assistant_input.returnPressed.connect(lambda: send(self))
    compose.addWidget(self.assistant_input, 1)
    attach = tool("", "file", lambda: pick_attachment(self, self.assistant_input),
                  tip="Attach a crash log or text file (.log, .txt, .ini...). You can also drop one here. "
                      "Only the lines that stand out are asked about; the file is not changed.")
    attach.setAccessibleName("Attach a log file")
    attach.setFixedSize(34, 34)
    compose.addWidget(attach)
    from gg_desktop import assistant_voice
    mic = tool("", "mic", lambda: assistant_voice.listen(self, self.assistant_input),
               tip="Say your question instead of typing it (Windows' own speech recognition; nothing is sent anywhere)")
    mic.setAccessibleName("Speak a question")
    mic.setFixedSize(34, 34)
    compose.addWidget(mic)
    accept_drops(self, self.assistant_input)
    self.assistant_send = tool("Send", "next", lambda: send(self), kind="primary", tip="Ask (Enter)")
    self.assistant_send.setFixedHeight(34)
    self.assistant_send.setStyleSheet("border-radius:17px;padding:0 16px;")
    compose.addWidget(self.assistant_send)
    outer = row(spacing=0, margins=(12, 8, 12, 4))
    outer.addWidget(compose_box, 1)
    body.addLayout(outer)
    using_box = QWidget()
    using_box.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    using_box.setMinimumWidth(0)
    using = row(spacing=5, margins=(18, 0, 12, 8))
    using_box.setLayout(using)
    using.addWidget(label("Answers use", "caption"))
    self.assistant_using = row(spacing=4)
    using.addLayout(self.assistant_using)
    using.addStretch()
    body.addWidget(using_box)
    using_box.hide()      # the sources are listed in Settings > Data Used; one less line under the box

    # --- right: data used and what it can do
    used, used_lay = panel(kind="fileFilterPanel", padding=9, spacing=4)
    accent(used, "assistantData", "cyan")
    head3 = row(spacing=6)
    disk = QLabel()
    disk.setPixmap(icon("storage", "#13bcf5", 18).pixmap(18, 18))
    head3.addWidget(disk)
    head3.addWidget(label("Data Used", "sectionTitle"), 1)
    used_lay.addLayout(head3)
    self.assistant_source_rows = {}
    for key, name in data.SOURCES:
        check = CheckRow(name, key in state.enabled)
        check.box.setAccessibleName("Use " + name)
        check.box.toggled.connect(lambda on, k=key: toggle_source(self, k, on))
        check.count.setText("")
        detail = label("", "caption")
        detail.setStyleSheet("padding-left:24px;")
        detail.setMinimumWidth(0)
        detail.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        used_lay.addWidget(check)
        used_lay.addWidget(detail)
        self.assistant_source_rows[key] = (check, detail)
    used_lay.addWidget(label("Answers only use what Game Grave has already scanned on this PC.", "caption", wrap=True))
    used_lay.addStretch()

    can = local_ai_ui.build_panel(self, accent)
    from gg_desktop import autopilot_ui
    auto = autopilot_ui.build_panel(self, accent)
    self.assistant_auto = auto
    right = QWidget()
    right_lay = column(spacing=8)
    right.setLayout(right_lay)
    right_lay.addWidget(level_panel(self, accent))
    right_lay.addWidget(can, 4)
    right_lay.addWidget(auto, 3)
    right_lay.addWidget(used, 4)

    side = _detail_scroll(right)
    self.assistant_side = side
    page.content.addWidget(_split(_split(left, chat, [222, 580]), side, [802, 232]), 1)
    show_side(self, bool(self.settings.get(SIDE_KEY, False)))
    page.assistant_ready = True
    refresh(self)
    self.assistant_input.setFocus()


SIDE_KEY = "assistant_side_open"


def show_side(window, on):
    window.assistant_side.setVisible(on)
    window.assistant_side_button.setChecked(on)
    window.assistant_side_button.setText("Hide settings" if on else "Settings")


def show_tools_setting(window):
    """The Tools badge opens the settings panel at "Let the assistant run tools"; the switch itself still decides."""
    if not window.assistant_side.isVisible():
        show_side(window, True)
        save(window, dict(window.settings, **{SIDE_KEY: True}))
    auto = getattr(window, "assistant_auto", None)
    if auto is not None and hasattr(window.assistant_side, "ensureWidgetVisible"):
        window.assistant_side.ensureWidgetVisible(auto)


def toggle_side(window):
    on = not window.assistant_side.isVisible()
    show_side(window, on)
    save(window, dict(window.settings, **{SIDE_KEY: on}))


def engine_limit():
    return actions.MAX_QUESTION


# ------------------------------------------------------------------ rendering
def refresh(window):
    """Everything that depends on the saved chats, the facts or the source switches."""
    if not live(window):
        return
    state = state_of(window)
    facts = state.facts
    metrics = data.metrics(facts, sum(1 for c in state.chats if c["messages"]))
    strip = window.assistant_metrics
    strip.set_value(0, f"{metrics['conversations']:,}")
    strip.set_value(1, f"{metrics['games']:,}")
    strip.set_value(2, f"{metrics['items']:,}")
    strip.set_value(3, metrics["scan"])
    from gg_desktop import autopilot_ui
    strip.set_value(4, "Runs Tools" if autopilot_ui.enabled(window) else "Read Only")
    runs = autopilot_ui.enabled(window)
    window.assistant_mode.setText(("Gravekeeper · " if gravekeeper_on(window) else "Basic · ") +
                                  ("Tools: Ask first" if runs else "Tools: Off"))
    window.assistant_mode.setToolTip("The assistant can run Game Grave's own tools; nothing changes until you press Run all. "
                                     "Click to change." if runs else
                                     "The assistant only answers. Click to switch on running tools.")
    window.assistant_mode.setStyleSheet(PILL.replace("QLabel", "QPushButton").format("#32d67a" if runs else "#9fb0c2", "#0b1a12" if runs else "#0f161e"))
    strip.set_value(5, f"{metrics['sources_on']} of {metrics['sources_total']}")
    for source in data.source_states(facts):
        check, detail = window.assistant_source_rows[source.key]
        check.box.blockSignals(True)
        check.box.setChecked(source.enabled)
        check.box.blockSignals(False)
        detail.setText(source.detail)
        detail.setToolTip(source.detail)
    while window.assistant_using.count():
        item = window.assistant_using.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
    on = [s for s in data.source_states(facts) if s.enabled]
    for source in on:
        window.assistant_using.addWidget(chip(source.name, "green"))
    if not on:
        window.assistant_using.addWidget(label("No data sources are on", "caption"))
    game = data.find_game(facts, state.scope) if state.scope else None
    window.assistant_scope.setText(game.name if game else "All Games")
    window.assistant_scope.setToolTip("Answers are limited to " + game.name if game else "Answers use all games")
    fill_list(window)
    render_chat(window)


def fill_list(window):
    state = state_of(window)
    widget = window.assistant_list
    widget.blockSignals(True)
    widget.clear()
    from gg_desktop import assistant_links as links
    words = window.assistant_find.text() if hasattr(window, "assistant_find") else ""
    pins = window.settings.get(links.PINS_KEY) or []
    if pins and not words:
        item = QListWidgetItem(f"Pinned answers ({len(pins)})\nOpen to read or unpin")
        item.setData(Qt.UserRole, PINNED)
        item.setToolTip("Answers you pinned")
        item.setSizeHint(QSize(10, 42))
        widget.addItem(item)
    keep = set(links.search_chats(state.chats, words))
    ordered = sorted((c for c in state.chats if c["id"] in keep and (c["messages"] or not words)),
                     key=lambda c: (-(c["updated"] or 0)))
    if words and not ordered:
        item = QListWidgetItem("No chats match")
        item.setFlags(Qt.NoItemFlags)
        widget.addItem(item)
    for chat in ordered:
        stamp = time.strftime("%b %d, %H:%M", time.localtime(chat["updated"])) if chat["messages"] else "Not started"
        item = QListWidgetItem(f"{chat['title']}\n{stamp}")
        item.setData(Qt.UserRole, chat["id"])
        item.setToolTip(chat["title"])
        item.setSizeHint(QSize(10, 42))
        widget.addItem(item)
        if chat["id"] == state.current:
            widget.setCurrentItem(item)
    widget.blockSignals(False)
    window.assistant_delete.setEnabled(any(c["messages"] for c in state.chats))


def clear_messages(window, layout=None):
    layout = layout if layout is not None else window.assistant_messages
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()


def render_chat(window, layout=None, title=None, scroll=None, compact=False):
    """Draw the current chat into the tab (default) or into another view, such as the pop-out window."""
    layout = layout if layout is not None else window.assistant_messages
    title = title if title is not None else window.assistant_title
    clear_messages(window, layout)
    chat = current_chat(window)
    title.setText(chat["title"] if chat and chat["messages"] else "New chat")
    prompts = getattr(window, "assistant_prompts", None)
    if layout is window.__dict__.get("assistant_messages") and prompts is not None and isValid(prompts):
        prompts.setVisible(bool(chat and chat["messages"]))    # an empty chat already shows the suggestion cards
    if not chat or not chat["messages"]:
        from gg_desktop import autopilot_ui
        layout.addWidget(welcome_hero(window, WELCOME_TOOLS if autopilot_ui.enabled(window) else WELCOME, compact))
        if local_ai_ui.show_card(window) and not compact:
            layout.addSpacing(6)
            layout.addWidget(local_ai_ui.setup_card(window))
    else:
        question = ""
        last = max((i for i, m in enumerate(chat["messages"]) if m["role"] == "assistant"), default=-1)
        for index, message in enumerate(chat["messages"]):
            if message["role"] == "user":
                question = message["text"]
                layout.addWidget(bubble(message["text"]))
            else:
                add_answer(window, question, engine.answer_from_dict(message.get("answer") or {}), message.get("plan"),
                           layout, latest=index == last, visuals=message.get("visuals") or ())
    layout.addStretch()
    scroll_down(window, scroll)


def welcome_hero(window, text, compact=False):
    """The empty chat: a friendly heading, what the assistant does in one paragraph, and cards to start from."""
    from PySide6.QtWidgets import QGridLayout
    hero = QWidget()
    box = column(spacing=10, margins=(4 if compact else 24, 10 if compact else 26, 4 if compact else 24, 6))
    hero.setLayout(box)
    mark = QLabel()
    mark.setFixedSize(52, 52)
    mark.setAlignment(Qt.AlignCenter)
    mark.setPixmap(icon("sparkles", "#ff5a73", 26).pixmap(26, 26))
    mark.setStyleSheet("background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #4a1220,stop:1 #170910);"
                       "border:1px solid #6a1a2b;border-radius:26px;")
    box.addWidget(mark, 0, Qt.AlignHCenter)
    keeper = gravekeeper_on(window)
    if keeper:
        text = GRAVEKEEPER_WELCOME
    title = label("Hey, I'm the Gravekeeper." if keeper else "What can I help with?", "sectionTitle")
    title.setStyleSheet("font-size:%dpx;font-weight:800;color:#ffffff;" % (17 if compact else 22))
    title.setAlignment(Qt.AlignCenter)
    box.addWidget(title)
    words = label(text, "subtle", wrap=True)
    words.setTextFormat(Qt.PlainText)
    words.setAlignment(Qt.AlignCenter)
    words.setStyleSheet("color:#aab6c3;font-size:12px;")
    words.setMinimumWidth(0)
    box.addWidget(words)
    if not keeper:
        basic = label("These are basic answers. For a real conversation that checks your PC, download the free Local AI "
                      "(Settings in the chat header).", "caption", wrap=True)
        basic.setAlignment(Qt.AlignCenter)
        basic.setStyleSheet("color:#f6be24;font-size:11px;")
        basic.setAccessibleName("Basic answers")
        box.addWidget(basic)
    grid = QGridLayout()
    grid.setHorizontalSpacing(8)
    grid.setVerticalSpacing(8)
    columns = 1 if compact else 2
    for n, (symbol, name, question) in enumerate(KEEPER_SUGGESTIONS if keeper else SUGGESTIONS):
        card = QPushButton()
        card.setObjectName("assistantSuggestion")
        card.setCursor(Qt.PointingHandCursor)
        card.setAccessibleName(name)
        card.setToolTip(question)
        card.setMinimumHeight(64)
        card.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)
        card.setStyleSheet("QPushButton#assistantSuggestion{background:#0d141c;border:1px solid #213040;border-radius:12px;"
                           "text-align:left;padding:8px 12px;} QPushButton#assistantSuggestion:hover{border-color:#e5243b;"
                           "background:#13101a;}")
        inner = row(spacing=10, margins=(0, 0, 0, 0))
        card.setLayout(inner)
        glyph = QLabel()
        glyph.setPixmap(icon(symbol, ROW_COLORS[n % len(ROW_COLORS)], 18).pixmap(18, 18))
        glyph.setAttribute(Qt.WA_TransparentForMouseEvents)
        inner.addWidget(glyph, 0, Qt.AlignTop)
        texts = column(spacing=1)
        head = label(name, "detailValue", wrap=True)
        head.setStyleSheet("font-weight:700;color:#f2f5f8;font-size:12px;")
        example = label("\u201c" + question + "\u201d", "caption", wrap=True)
        example.setStyleSheet("color:#8d9aa8;font-size:11px;")
        for part in (head, example):
            part.setAttribute(Qt.WA_TransparentForMouseEvents)
            texts.addWidget(part)
        inner.addLayout(texts, 1)
        card.clicked.connect(lambda _=False, q=question: send(window, q))
        grid.addWidget(card, n // columns, n % columns)
    box.addLayout(grid)
    return hero


def add_assistant_text(window, text, layout=None):
    line = row(spacing=10, margins=(0, 0, 0, 0))
    holder = QWidget()
    holder.setLayout(line)
    avatar = Avatar()
    line.addWidget(avatar, 0, Qt.AlignTop)
    words = label(text, "subtle", wrap=True)
    words.setTextFormat(Qt.PlainText)
    words.setStyleSheet("color:#e8eef5;font-size:13px;")
    line.addWidget(words, 1)
    (layout if layout is not None else window.assistant_messages).addWidget(holder)
    return words


def add_answer(window, question, answer, plan=None, layout=None, latest=False, visuals=()):
    if answer is None:
        return
    talking = answer.intent == "local_ai" or "Gravekeeper" in answer.sources   # the Gravekeeper's own words
    line = row(spacing=10)
    holder = QWidget()
    holder.setLayout(line)
    line.addWidget(Avatar(), 0, Qt.AlignTop)
    stack = column(spacing=7)
    body = answer.text
    if answer.intent == "feature" and "\n" in body:
        heading, body = body.split("\n", 1)
        title = label(heading, "subtle")
        title.setTextFormat(Qt.PlainText)
        title.setStyleSheet("color:#ffffff;font-size:14px;font-weight:700;")
        stack.addWidget(title)
    from gg_desktop import assistant_links as links
    games = [g.name for g in getattr(getattr(window, "inventory", None), "games", []) or []]
    text = label("", "subtle", wrap=True)
    text.setTextFormat(Qt.RichText)                 # game, tab and folder names are links; everything else is escaped
    text.setText(links.linkify(body, games))
    text.setProperty("plain", body)                 # the words without links, for checks and screen readers
    text.setAccessibleDescription(body[:400])
    text.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
    text.setOpenExternalLinks(False)
    text.linkActivated.connect(lambda href: open_link(window, href))
    text.setStyleSheet("color:#e8eef5;font-size:13px;" + ("line-height:140%;" if talking else ""))
    stack.addWidget(text)
    from gg_desktop import assistant_visuals
    for visual in visuals or ():
        widget = assistant_visuals.widget_for(window, visual)
        if widget is not None:
            stack.addWidget(widget)
    for index, item in enumerate(answer.rows):
        stack.addWidget(AnswerRow(window, item, ROW_COLORS[index % len(ROW_COLORS)]))
    if answer.note:
        note = label(answer.note, "caption", wrap=True)
        note.setTextFormat(Qt.PlainText)
        note.setTextInteractionFlags(Qt.TextSelectableByMouse)
        stack.addWidget(note)
    actions_row = ActionFlow(spacing=6)
    from gg_desktop import autopilot_ui
    for caption, tab in answer.handoffs:
        if tab.startswith("url:"):         # a page on the web (PCGamingWiki, the Steam store): opened in the browser
            actions_row.addWidget(tool(caption, "next", lambda _=False, u=tab[4:]: open_web(window, u),
                                       tip="Opens this page in your web browser"))
            continue
        if tab.startswith("tool:"):        # a Game Grave tool the Gravekeeper offered
            actions_row.addWidget(tool(caption, "next", lambda _=False, k=tab[5:]: open_tool(window, k),
                                       tip="Open it now. It asks before it changes anything."))
            continue
        if tab.startswith("q:"):           # a best guess: asks that question as if it were typed
            guess = tool(caption, "next", lambda _=False, q=tab[2:]: send(window, q), kind="primary",
                         tip=f"Ask: {tab[2:]}")
            actions_row.addWidget(guess)
            continue
        if ":" in tab or tab in ("bisect", "tour") or "/" in tab:
            asks = tab.startswith("ask:")
            special = tool(caption, "play" if asks else "next", lambda _=False, t=tab: autopilot_ui.open_target(window, t),
                           kind="primary" if asks else "",
                           tip=("Plan it with Game Grave's own tools; nothing changes until you press Run all" if asks
                                else "Open it now. It asks before it changes anything."))
            actions_row.addWidget(special)
            continue
        actions_row.addWidget(tool(caption, "next", lambda _=False, t=tab: window.navigate(t), tip=f"Open the {tab} tab"))
    small = []
    small.append(tool("" if talking else "Copy", "file", lambda _=False, q=question, a=answer: copy_answer(window, q, a),
                      tip="Copy this question and answer"))
    small[-1].setAccessibleName("Copy")
    from gg_desktop import assistant_voice
    if talking and assistant_voice.can_speak():
        small.append(tool("", "volume" if "volume" in _icon_names() else "play",
                          lambda _=False, a=answer: assistant_voice.say(window, a.text), tip="Read this answer aloud"))
        small[-1].setAccessibleName("Read aloud")
    if question:
        small.append(tool("" if talking else "Pin", "pin",
                          lambda _=False, q=question, a=answer: pin_answer(window, q, a),
                          tip="Keep this answer in Pinned answers so you can find it again"))
        small[-1].setAccessibleName("Pin")
        small.append(tool("" if talking else "Not helpful", "warning",
                          lambda _=False, q=question, a=answer: not_helpful(window, q, a),
                          tip="Keeps this question and answer on this PC so the assistant learns from it, and copies a "
                              "report you can send if you want. Nothing is sent by itself."))
        small[-1].setAccessibleName("Not helpful")
    for b in small:
        if talking:
            b.setFixedSize(28, 26)
        actions_row.addWidget(b)
    stack.addWidget(_widget(actions_row))
    if latest and question and not talking and answer.intent not in ("followup", "note", "ask_fixed", "news",
                                                                     "troubleshoot"):
        follow = ActionFlow(spacing=6)
        game = row_game_name(window, question)
        for caption, ask in links.next_questions(answer.intent, question, answer.text, game):
            follow.addWidget(tool(caption, "next", lambda _=False, q=ask: send(window, q), tip="Ask: " + ask))
        if any(str(s).startswith("Local AI") for s in answer.sources):
            follow.addWidget(tool("Simpler", "next", lambda _=False: send(window, links.SIMPLER),
                                  tip="Ask for the same answer in plainer words"))
            follow.addWidget(tool("More detail", "next", lambda _=False: send(window, links.MORE),
                                  tip="Ask for more detail and the exact steps"))
        if follow.count():
            stack.addWidget(_widget(follow))
    if answer.sources and not talking:
        sources = row(spacing=5)
        sources.addWidget(label("Sources", "caption"))
        for name in answer.sources:
            sources.addWidget(chip(name, "blue"))
        sources.addStretch()
        stack.addLayout(sources)
    if plan:
        from gg_desktop import autopilot_ui
        off = answer.intent == "autopilot_off"
        widget = autopilot_ui.card(window, plan, off=off)
        if widget is not None:
            stack.insertWidget(1, widget)
            if off and not autopilot_ui.enabled(window):
                stack.insertWidget(2, _widget(_turn_on_row(window, question)))
    line.addLayout(stack, 1)
    (layout if layout is not None else window.assistant_messages).addWidget(holder)


def _turn_on_row(window, question):
    flow = ActionFlow(spacing=6)

    def turn_on():
        from gg_desktop import autopilot_core, autopilot_ui
        if not save(window, dict(window.settings, **{autopilot_core.SETTING: True})):
            return
        if _alive_switch(window):
            window.autopilot_switch.blockSignals(True)
            window.autopilot_switch.setChecked(True)
            window.autopilot_switch.blockSignals(False)
        autopilot_ui.sync_panel(window)
        send(window, question)
    control = tool("Turn on and plan it", "play", turn_on, kind="primary",
                   tip="Let the assistant run Game Grave's own tools, then plan this request. Checks run straight away; "
                       "changes wait for Run all.")
    control.setAccessibleName("Let the assistant run tools")
    flow.addWidget(control)
    return flow


def _alive_switch(window):
    switch = getattr(window, "autopilot_switch", None)
    return switch is not None and isValid(switch)


def scroll_down(window, scroll=None):
    def go():
        area = scroll if scroll is not None else (window.assistant_scroll if live(window) else None)
        if area is not None and isValid(area):
            bar = area.verticalScrollBar()
            bar.setValue(bar.maximum())
    QTimer.singleShot(0, go)
    QTimer.singleShot(60, go)


# ------------------------------------------------------------------ actions
def popout_of(window):
    from gg_desktop import assistant_popout
    return assistant_popout.current(window)


def views(window):
    """Every place the chat is on screen: the AI Assistant tab and the pop-out window."""
    out = []
    if live(window):
        out.append(SimpleNamespace(messages=window.assistant_messages, input=window.assistant_input,
                                   send=window.assistant_send, scroll=window.assistant_scroll))
    pop = popout_of(window)
    if pop is not None:
        out.append(SimpleNamespace(messages=pop.messages, input=pop.input, send=pop.send_button, scroll=pop.scroll))
    return out


def refresh_all(window):
    """Redraw the tab (when it is open) and the pop-out window (when it is open)."""
    refresh(window)
    pop = popout_of(window)
    if pop is not None:
        pop.refresh()


def ensure_chats(window):
    state = state_of(window)
    if not state.chats:
        state.chats = actions.load_chats(window.settings)
        state.enabled = data.enabled_sources(window.settings)
        state.scope = actions.scope_of(window.settings)
    if not state.current or not any(c["id"] == state.current for c in state.chats):
        chat = state.chats[0] if state.chats else actions.new_chat(time.time())
        if not state.chats:
            state.chats.append(chat)
        state.current = chat["id"]
    return state


def last_exchange(chat):
    """The newest question and answer in this chat, so "what about Starfield?" or "why?" can refer back to them."""
    messages = (chat or {}).get("messages") or []
    for i in range(len(messages) - 1, 0, -1):
        if messages[i].get("role") == "assistant" and messages[i - 1].get("role") == "user":
            return str(messages[i - 1].get("text", "")), dict(messages[i].get("answer") or {})
    return "", None


def send(window, question=None, source=None, attached="", image=""):
    """Answer one message from the tab or the pop-out window (`source` is the input box it came from).
    `attached` is the key lines of a file the owner attached; it is added after the typed text, line breaks kept."""
    shown = views(window)
    if not shown:
        return
    state = ensure_chats(window)
    box = source if source is not None else shown[0].input
    text = " ".join((question if question is not None else box.text()).split())[:actions.MAX_QUESTION]
    if not text:
        return
    from gg_desktop import autopilot_ui
    if question is None:
        box.clear()
    if attached:
        text = text + "\n\n" + attached[:3500]
    text = here_question(window, text)
    if gravekeeper_on(window):           # the local AI holds the conversation; Game Grave's tools are its tools
        model_send(window, text, box, image=image)
        return
    if guide_reply(window, text):        # guided troubleshooting: one fix at a time, "Did that work?"
        return
    if memory_reply(window, text):       # notes, "undo that", "it's fixed" / "still broken"
        return
    if follow_up(window, text):          # "proceed", "yes", "do it": act on what the assistant just offered
        return
    from gg_desktop import assistant_understand as understand
    loose = understand.normalize(text, make_facts(window))      # "nuke my temp files" is "delete my temp files"
    if autopilot_ui.handle(window, text) or (loose != text.casefold() and autopilot_ui.handle(window, loose, shown=text)):
        window.status.setText("Planned with Game Grave's own tools. Nothing changes until you press Run all.")
        return
    facts = make_facts(window)
    previous_question, previous_answer = last_exchange(current_chat(window))
    result = understand.answer(text, facts, previous_question, previous_answer,
                               local_ai_on=local_ai_ui.enabled(window))
    if result.intent == "hardware_unread" and not getattr(window, "_assistant_parts_tried", False):
        # Ask Windows for the parts once (read only, the same call as Hardware's Re-read), then answer again.
        window._assistant_parts_tried = True  # once per run; Hardware's Re-read still works after a failure
        window.status.setText("Asking Windows for your parts…")

        def work(_progress):
            from gg_desktop import hardware_core as hw
            try:
                return hw.read_specs()
            except OSError:
                return None

        def arrived(specs):
            if specs is not None:
                window.hardware_specs = specs
            if views(window):
                send(window, text)
        window.job(work, arrived, error_title="Could not read the hardware")
        return
    chat = current_chat(window)
    if chat is None:
        chat = actions.new_chat(time.time())
        state.chats.insert(0, chat)
        state.current = chat["id"]
    if local_ai_ui.enabled(window) and result.intent not in ("greet", "thanks", "off", "hardware_unread"):
        msgs = chat["messages"]
        history = [(msgs[i]["text"], msgs[i + 1]["text"]) for i in range(max(0, len(msgs) - 13), len(msgs) - 1)
                   if msgs[i]["role"] == "user" and msgs[i + 1]["role"] == "assistant"]
        starting = local_ai_ui.state_of(window).server is None
        window.status.setText("Local AI is starting on this PC (the first answer can take up to a minute)…" if starting
                              else "Local AI is writing the answer on this PC…")
        # Show the question and a thinking line right away in every view; the real answer replaces them.
        live_labels = []
        for view in views(window):
            view.input.setEnabled(False)
            view.send.setEnabled(False)
            layout = view.messages
            if layout.count() and layout.itemAt(layout.count() - 1).spacerItem() is not None:
                layout.takeAt(layout.count() - 1)
            layout.addWidget(bubble(text))
            waiting = add_assistant_text(window, "Starting the local AI model, this first answer can take up to a minute…"
                                         if starting else ("Thinking it through on this PC…" if local_ai_ui.thinks(window)
                                                           else "Thinking…"), layout)
            live_labels.append((waiting, view.scroll))
            layout.addStretch()
            scroll_down(window, view.scroll)
        chat_id = chat["id"]

        def live(words):
            """The waiting bubble shows what is being checked, then the answer as it is written."""
            for waiting, scroll in live_labels:
                if isValid(waiting):
                    waiting.setText(words)
                    scroll_down(window, scroll)

        def deliver(answer):
            target = next((c for c in state.chats if c["id"] == chat_id), None)
            if target is not None:
                actions.add_exchange(target, text, answer, time.time())
                persist_chats(window)
            for view in views(window):
                view.input.setEnabled(True)
                view.send.setEnabled(True)
            if box is not None and isValid(box):
                box.setFocus()
            window.status.setText("Answered on this PC from scanned data. Nothing was changed.")
            refresh_all(window)
        local_ai_ui.answer_async(window, text, result, facts, history, deliver, live=live)
        return
    actions.add_exchange(chat, text, result, time.time())
    persist_chats(window)
    window.status.setText("Answered from scanned data. Nothing was changed.")
    refresh_all(window)


# ------------------------------------------------------------------ the Gravekeeper (local AI first)
def gravekeeper_on(window):
    """The model answers everything when it is switched on and downloaded, and no game is running (then it pauses and
    the built-in answers take over, as before)."""
    return local_ai_ui.enabled(window) and not local_ai_ui.game_running(window)


def model_history(chat):
    """The conversation as (user, assistant) pairs, with plans written out so "go ahead" and "undo that" make sense."""
    pairs, pending = [], None
    for m in (chat or {}).get("messages") or []:
        if m.get("role") == "user":
            pending = str(m.get("text") or "")
        elif m.get("role") == "assistant":
            if pending is None:
                pending = "(Game Grave told you something had happened.)"   # a message the Gravekeeper started
            said = str(m.get("text") or "")
            plan = m.get("plan") or m.get("off_plan")
            if isinstance(plan, dict) and plan.get("steps"):
                steps = "; ".join(f"{s.get('title', s.get('key', ''))} ({s.get('status', 'waiting')})"
                                  for s in plan["steps"][:10])
                said += f"\n[Plan shown: {plan.get('request', '')}. Steps: {steps}]"
            pairs.append((pending, said))
            pending = None
    return pairs


def _extras(window, chat):
    """What the Gravekeeper should know beyond the question: memory, the waiting plan, the undo it could offer."""
    from gg_desktop import assistant_followup as fu
    from gg_desktop import assistant_memory as memory
    from gg_desktop import autopilot_core, autopilot_ui
    from gg_desktop import gravekeeper
    state = state_of(window)
    offer = fu.last_offer(chat)
    waiting = off = ""
    if offer is not None and offer.kind == "plan" and offer.plan_id in autopilot_ui.state_of(window).plans:
        waiting = autopilot_ui.state_of(window).plans[offer.plan_id].request
    elif offer is not None and offer.kind == "turn_on":
        off = offer.request
    steps, _notes, request = memory.undo_steps(chat)
    return {"memory": gravekeeper.memory_text(state.chats, chat.get("id") if chat else None,
                                              window.settings.get(memory.FIX_KEY)),
            "waiting_plan": waiting, "tools_off_request": off, "tools_on": bool(window.settings.get(autopilot_core.SETTING)),
            "undo_preview": ("Undo: " + request) if steps else "", "all_chats": list(state.chats),
            "chat_id": chat.get("id") if chat else None, "allow_plans": False}


def model_send(window, text, box=None, image="", event=False):
    """One Gravekeeper turn: the question shows at once with a live line (what it is checking, then its words as they
    are written), and the reply replaces it. `event` is Game Grave telling it something (a plan finished, a crash):
    then no user bubble is drawn and the reply speaks first."""
    from gg_desktop import gravekeeper
    state = ensure_chats(window)
    chat = current_chat(window)
    if chat is None:
        chat = actions.new_chat(time.time())
        state.chats.insert(0, chat)
        state.current = chat["id"]
    previous_q, previous_a = last_exchange(chat)
    if not event and previous_a and previous_a.get("intent") == "local_ai" and gravekeeper.CORRECTION.search(text):
        save(window, gravekeeper.add_lesson(window.settings, previous_q, previous_a.get("text", ""), text))
    history = model_history(chat)
    extras = _extras(window, chat)
    extras["allow_plans"] = bool(event)
    starting = local_ai_ui.state_of(window).server is None
    window.status.setText("Starting the Gravekeeper (the first answer can take up to a minute)…" if starting
                          else "The Gravekeeper is thinking…")
    live_labels = []
    for view in views(window):
        view.input.setEnabled(False)
        view.send.setEnabled(False)
        layout = view.messages
        if layout.count() and layout.itemAt(layout.count() - 1).spacerItem() is not None:
            layout.takeAt(layout.count() - 1)
        if not event:
            layout.addWidget(bubble(text.split("\n\nFrom the file")[0] + ("\n[screenshot attached]" if image else "")))
        waiting = add_assistant_text(window, "Waking up, the first answer can take up to a minute…" if starting
                                     else "Thinking…", layout)
        live_labels.append((waiting, view.scroll))
        layout.addStretch()
        scroll_down(window, view.scroll)
    chat_id = chat["id"]

    def live(words):
        for waiting, scroll in live_labels:
            if isValid(waiting):
                waiting.setText(words)
                scroll_down(window, scroll)

    def unlock():
        for view in views(window):
            view.input.setEnabled(True)
            view.send.setEnabled(True)
        if box is not None and isValid(box):
            box.setFocus()

    def deliver(result, key):
        unlock()
        target = next((c for c in state.chats if c["id"] == chat_id), None)
        if target is None:
            return
        state.current = chat_id
        model_reply(window, target, text, result, event=event)

    def fallback(reason):
        unlock()
        if event:
            refresh_all(window)
            return
        facts = make_facts(window)
        from gg_desktop import assistant_understand as understand
        q, a = last_exchange(chat)
        answer = understand.answer(text, facts, q, a, local_ai_on=False)
        answer = engine.Answer(answer.intent, answer.text, answer.rows, (answer.note + " " if answer.note else "") +
                               reason + ", so this is the basic answer.", answer.sources, answer.handoffs)
        actions.add_exchange(chat, text, answer, time.time())
        persist_chats(window)
        refresh_all(window)
    if not local_ai_ui.agent_async(window, text, history, deliver, live=live, image=image or None, extras=extras,
                                   failed_to=fallback):
        return


def model_reply(window, chat, text, result, event=False):
    """Put the Gravekeeper's reply in the chat and do what it asked for (plans, notes, buttons, pictures)."""
    from gg_desktop import assistant_memory as memory
    from gg_desktop import autopilot_core as core, autopilot_ui
    from gg_desktop import local_ai_tools as lookups
    from gg_desktop import assistant_followup as fu
    before = fu.last_offer(chat)                      # what was waiting before this reply joins the chat
    pending_request = before.request if before is not None and before.kind == "turn_on" else ""
    preview = None
    if pending_request:                               # the previewed plan itself, so turning on runs exactly that
        for m in reversed(chat.get("messages") or []):
            if m.get("role") == "assistant":
                preview = core.plan_from_dict(m.get("plan") or {}) if m.get("plan") else None
                break
    pending_plan = before.plan_id if before is not None and before.kind == "plan" else None
    reply = (result.get("text") or "").strip()
    if result.get("unchecked") and reply:
        reply += "\n\n(Double-check: " + "; ".join(result["unchecked"]) + ".)"
    effects = list(result.get("effects") or [])
    buttons, extra = [], {}
    for item in effects:
        kind = item[0]
        if kind == "button":
            buttons.append((item[1], item[2]))
        elif kind == "link":
            buttons.append((item[1], "url:" + item[2]))
        elif kind == "chart":
            extra.setdefault("visuals", []).append({"chart": item[1]})
        elif kind == "game_card":
            extra.setdefault("visuals", []).append({"game": item[1]})
        elif kind == "note_add":
            save(window, memory.add_note(window.settings, item[1]))
        elif kind == "note_forget":
            updated, _gone = memory.forget(window.settings, item[1])
            save(window, updated)
        elif kind == "fix_result":
            game, ok, what = item[1], item[2], item[3]
            history = memory.tried_for(window.settings, game)
            if history:
                save(window, memory.mark_last(window.settings, game, "fixed" if ok else "not_fixed"))
            else:
                save(window, memory.record_fix(window.settings, game, what or "a fix from the chat",
                                               "fixed" if ok else "not_fixed"))
    plan = None
    if result.get("jobs"):
        steps, dropped = lookups.plan_steps(result["jobs"])
        if steps:
            plan = core.Plan(" ".join(str(result.get("summary") or text).split())[:300], steps)
            if dropped:
                reply = (reply + " (left out: " + ", ".join(dropped) + ")").strip()
    if not reply and plan is None:
        reply = ("I started to say something Game Grave won't let me promise, so I stopped. Could you ask that another "
                 "way?" if result.get("broke_rules") else "Sorry, I lost my train of thought there. Could you ask that "
                 "again?")
    answer = engine.Answer("local_ai", reply, (), "", ("Gravekeeper",), tuple(buttons))
    shown_q = "" if event else text
    if plan is not None:
        autopilot_ui.post_plan(window, plan, shown_q or "(Game Grave)", text=reply, sources=("Gravekeeper",))
        if event:   # a plan Game Grave asked about has no question of its own: keep the reply without a user bubble
            msgs = chat.get("messages") or []
            if len(msgs) >= 2 and msgs[-2].get("role") == "user" and msgs[-2].get("text") == "(Game Grave)":
                del msgs[-2]
    elif event:
        chat.setdefault("messages", []).append(dict({"role": "assistant", "text": answer.text, "at": time.time(),
                                                     "answer": answer.to_dict()}, **extra))
        chat["updated"] = time.time()
    else:
        actions.add_exchange(chat, text, answer, time.time())
        if extra and chat.get("messages"):
            chat["messages"][-1].update(extra)
    for item in effects:
        if item[0] == "undo":
            steps, notes, request = memory.undo_steps(chat)
            if steps:
                autopilot_ui.post_plan(window, core.Plan(("Undo: " + request)[:300], steps), "(undo)",
                                       text="Here's what I can put back.", sources=("Gravekeeper",))
                _drop_marker(chat, "(undo)")
        elif item[0] == "run_plan":
            if pending_plan and pending_plan in autopilot_ui.state_of(window).plans:
                QTimer.singleShot(0, lambda pid=pending_plan: autopilot_ui.run_all(window, pid))
        elif item[0] == "tools_on":
            if save(window, dict(window.settings, **{core.SETTING: True})):
                if _alive_switch(window):
                    window.autopilot_switch.blockSignals(True)
                    window.autopilot_switch.setChecked(True)
                    window.autopilot_switch.blockSignals(False)
                autopilot_ui.sync_panel(window)
                if preview is not None and plan is None:
                    import uuid
                    fresh = core.Plan(preview.request, [core.Step(s.key, dict(s.args), s.detail, s.ticked)
                                                         for s in preview.steps], preview.schedule, uuid.uuid4().hex[:10])
                    autopilot_ui.post_plan(window, fresh, "(go ahead)", text="Switched on. Here's the plan again; "
                                           "press Run all when you're ready.", sources=("Gravekeeper",))
                    _drop_marker(chat, "(go ahead)")
                elif pending_request and plan is None:
                    autopilot_ui.handle(window, pending_request, shown="(go ahead)")
                    _drop_marker(chat, "(go ahead)")
    persist_chats(window)
    window.status.setText("Answered on this PC. Nothing changes without your OK.")
    refresh_all(window)
    from gg_desktop import assistant_voice
    assistant_voice.after_answer(window, reply)


def _drop_marker(chat, marker):
    """Plans posted on the Gravekeeper's behalf come without a typed question; remove the placeholder bubble."""
    msgs = (chat or {}).get("messages") or []
    for i in range(len(msgs) - 1, -1, -1):
        if msgs[i].get("role") == "user" and msgs[i].get("text") == marker:
            del msgs[i]
            break


def _reply(window, text, answer, plan=None):
    state = ensure_chats(window)
    chat = current_chat(window)
    if chat is None:
        chat = actions.new_chat(time.time())
        state.chats.insert(0, chat)
        state.current = chat["id"]
    actions.add_exchange(chat, text, answer, time.time())
    persist_chats(window)
    refresh_all(window)


def _fix_game_of(window, plan):
    """The installed game a finished fix plan was for, or ''."""
    check = next((s for s in plan.steps if s.key == "check_game_fix"), None)
    if check is None:
        return ""
    if check.args.get("name"):              # the check found the game and wrote its name
        return str(check.args["name"])
    from gg_desktop import fixgame_core as fx
    from gg_desktop.local_ai_tools import find_game
    games = list(getattr(getattr(window, "inventory", None), "games", []) or [])
    game = fx.game_named(games, plan.request)
    if game is None:
        words = re.sub(r"^.*?\b(fix|repair)\b( my game| the game| my)?", "", plan.request.casefold()).strip()
        game = find_game(make_facts(window), words) if words else None
    return getattr(game, "name", "") or ""


def plan_report(plan):
    """A finished plan in words for the Gravekeeper: each step, its outcome and what it found."""
    lines = [f"- {s.title}: {s.status}" + (f" ({s.result[:160]})" if s.result else "") for s in plan.steps]
    return "Game Grave finished the plan \"" + plan.request[:200] + "\":\n" + "\n".join(lines)


def after_plan(window, plan):
    """After a plan: the Gravekeeper says what happened and what's next (when it's on). For a fix plan for a game,
    what was tried is remembered and, without the Gravekeeper, the chat asks whether it fixed it (two buttons)."""
    from gg_desktop import assistant_memory as memory, autopilot_core as core
    game = _fix_game_of(window, plan)
    if gravekeeper_on(window):
        if game:
            done = [s.title for s in plan.steps if s.status == "done" and s.kind == core.CHANGE]
            save(window, memory.record_fix(window.settings, game, ", ".join(done) or "checked the usual causes"))
        model_send(window, plan_report(plan) + "\nTell the user what happened in plain words and what to do next" +
                   (f" (ask whether {game} works now)." if game else "."), event=True)
        return
    if not game:
        return
    done = [s.title for s in plan.steps if s.status == "done" and s.kind == core.CHANGE]
    tried = ", ".join(done) if done else "checked the usual causes (crash records, overlays, runtimes, drivers)"
    save(window, memory.record_fix(window.settings, game, tried))
    answer = engine.Answer("ask_fixed", memory.ASK_FIXED.format(game=game), sources=("Fix history",),
                           handoffs=(("Yes, it's fixed", "q:it's fixed"), ("No, still broken", "q:still broken")))
    _append_assistant(window, answer, fix_game=game)


NEWS_KEY = "assistant_scan_news"


def after_scan(window, previous, inventory):
    """After a scan: when something important changed, the assistant opens with one line about it. Reads only."""
    try:
        from gg_desktop import assistant_memory as memory, space_ui
        before = [g.name for g in getattr(previous, "games", []) or []]
        games = [g.name for g in getattr(inventory, "games", []) or []]
        low = []
        try:
            drive, _drives, _picks = space_ui.low_drive(window)
            if drive is not None:
                low = [drive.root.rstrip("\\/")]
        except Exception:
            pass
        lines = memory.scan_news(before, games, low, len(getattr(previous, "mods", []) or []),
                                 len(getattr(inventory, "mods", []) or []))
    except Exception:
        return
    if not lines or window.settings.get(NEWS_KEY, True) is False:
        return
    if gravekeeper_on(window):
        speak_first(window, "Game Grave just finished a scan. What changed: " + " ".join(lines) + " Tell the user in "
                    "a sentence or two what matters most and offer the next step.", "", "")
        return
    answer = engine.Answer("news", "Since the last scan: " + " ".join(lines),
                           sources=("Last scan",), handoffs=(("Open Graveyard", "Graveyard"),) if low else ())
    chat = current_chat(window)
    if chat is None or not chat.get("messages"):
        return                                        # an empty chat keeps its welcome; the scan notice covers it
    _append_assistant(window, answer)


def speak_first(window, event, title, text):
    """Something happened that the user should hear about. With the model already running or the chat on screen, the
    Gravekeeper writes the message now; otherwise a notice offers it (so a 5 GB model never loads by itself). Skipped
    while a game runs, like all background work."""
    if not gravekeeper_on(window):
        return False
    from gg_desktop import comfort
    warm = local_ai_ui.state_of(window).server is not None or bool(views(window))

    def go():
        model_send(window, event, event=True)
    if warm:
        go()
        if title:
            comfort.notify(window, title, text, "warn", "AI Assistant",
                           action=("Open chat", lambda: _open_chat(window)))
    elif title:
        comfort.notify(window, title, text, "warn", "AI Assistant",
                       action=("Ask the Gravekeeper", lambda: (_open_chat(window), go())))
    return True


def _open_chat(window):
    from gg_desktop import assistant_popout
    assistant_popout.open_popout(window)


def _append_assistant(window, answer, **extra):
    """An assistant message on its own (no question before it), in the current chat."""
    chat = current_chat(window)
    if chat is None:
        return
    chat.setdefault("messages", []).append(dict({"role": "assistant", "text": answer.text, "at": time.time(),
                                                 "answer": answer.to_dict()}, **extra))
    del chat["messages"][:-actions.MAX_MESSAGES]
    persist_chats(window)
    refresh_all(window)


def _asked_fixed(chat):
    """The game the newest "Did that fix it?" in this chat was about, if it is the last assistant message."""
    for message in reversed((chat or {}).get("messages") or []):
        if message.get("role") == "assistant":
            return message.get("fix_game", "")
    return ""


def _guide_of(chat):
    """The guided-troubleshooting session still waiting for an answer: on one of the last three assistant messages (a
    step's button, such as Check it for me, adds a plan or answer after it), unless the session ended since."""
    seen = 0
    for message in reversed((chat or {}).get("messages") or []):
        if message.get("role") != "assistant":
            continue
        if message.get("guide"):
            return message["guide"]
        if (message.get("answer") or {}).get("intent") == "troubleshoot":
            return None                      # stopped, fixed or out of steps
        seen += 1
        if seen >= 3:
            break
    return None


def guide_reply(window, text):
    """Starts or carries on a guided troubleshooting session in this chat. Each step is one message with its buttons."""
    from gg_desktop import assistant_guide as guide
    from gg_desktop import assistant_memory as memory
    chat = current_chat(window)
    session = _guide_of(chat)
    games = [g.name for g in getattr(getattr(window, "inventory", None), "games", []) or []]
    if session is None and not guide.starts(text):
        return False
    if session is not None:
        verdict = guide.reply(session, text)
        if not verdict:
            if not guide.starts(text):
                return False                 # an ordinary question in the middle: answered normally, session ends
            session = None
        elif verdict == "stop":
            _reply(window, text, engine.Answer("troubleshoot", "Okay, stopped. Ask again any time.",
                                               sources=("Known fixes",)))
            return True
        elif verdict == "fixed":
            game = session.get("game")
            steps = guide.steps_for(session["problem"])
            worked = steps[session["at"]] if session["at"] < len(steps) else ""
            if game:
                save(window, memory.record_fix(window.settings, game, worked[:120], "fixed"))
            _reply(window, text, engine.Answer("troubleshoot", "Great, glad that sorted it." +
                                               (f" I'll remember what fixed {game}." if game else ""),
                                               sources=("Known fixes",)))
            return True
        else:
            session = guide.advance(session, verdict)
            if verdict == "next" and session.get("game") and session["tried"]:
                save(window, memory.record_fix(window.settings, session["game"], session["tried"][-1][:120],
                                               "not_fixed"))
    if session is None:
        session = guide.begin(text, games)
    if not session["problem"]:
        body, buttons = guide.ask_problem(session)
    else:
        view = guide.step_view(session)
        if view is None:
            body, buttons = guide.done_view(session)
            _reply(window, text, engine.Answer("troubleshoot", body, sources=("Known fixes",), handoffs=buttons))
            return True
        body, buttons = view
    _reply(window, text, engine.Answer("troubleshoot", body, sources=("Known fixes",), handoffs=buttons))
    if session["problem"]:
        current_chat(window)["messages"][-1]["guide"] = session
        persist_chats(window)
    return True


def memory_reply(window, text):
    """Notes ("remember that…", "what do you remember", "forget…"), "undo that", and answers to "Did that fix it?"."""
    from gg_desktop import assistant_memory as memory
    chat = current_chat(window)
    game = _asked_fixed(chat)
    verdict = memory.fix_reply(text) if game else ""
    if verdict:
        save(window, memory.mark_last(window.settings, game, verdict))
        if verdict == "fixed":
            _reply(window, text, engine.Answer("fix_noted", f"Great, glad {game} works. I'll remember what fixed it.",
                                               sources=("Fix history",)))
            return True
        from gg_desktop import local_ai_knowledge as kb
        fixes = kb.known_fixes("crash on start won't start crash while playing", game).get("known_fixes", [])
        tried = memory.tried_line(window.settings, game)
        steps = [s for f in fixes for s in f.get("usual_fixes", f.get("known_notes", []))]
        steps = [s for s in steps if not any(w in s for w in ("Check the usual fixes", "Verify"))][:4]
        body = (f"Okay, noted that it didn't help. {tried}\n\nNext things to try:\n" +
                "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1)))
        _reply(window, text, engine.Answer("fix_noted", body, sources=("Fix history", "Known fixes"),
                                           handoffs=(("Find the crashing mod", "bisect"), ("Open Fix Kit", "Fix Kit"))))
        return True
    kind, value = memory.note_command(text)
    if kind == "remember":
        save(window, memory.add_note(window.settings, value))
        _reply(window, text, engine.Answer("note", f"Noted: \"{value}\". I'll keep it in mind on this PC. Ask \"what do you "
                                                   "remember\" to see your notes, or \"forget\" one to remove it.",
                                           sources=("Your notes",)))
        return True
    if kind == "recall":
        items = memory.notes(window.settings)
        if not items:
            body = "I haven't been asked to remember anything yet. Say \"remember that …\" and I'll keep it on this PC."
            buttons = ()
        else:
            body = "What you've asked me to remember:\n" + "\n".join(f"{i}. {n['text']}" for i, n in enumerate(items, 1))
            buttons = tuple((f"Forget {i}", f"q:forget note {i}") for i in range(1, min(len(items), 4) + 1))
            buttons += (("Forget all", "q:forget all notes"),)
        _reply(window, text, engine.Answer("note", body, sources=("Your notes",), handoffs=buttons))
        return True
    if kind == "forget":
        updated, gone = memory.forget(window.settings, value)
        if gone:
            save(window, updated)
            body = "Forgotten: " + "; ".join(gone) + "."
        else:
            body = "I couldn't find a note like that. Ask \"what do you remember\" to see them."
        _reply(window, text, engine.Answer("note", body, sources=("Your notes",)))
        return True
    if memory.is_undo(text):
        steps, notes, request = memory.undo_steps(chat)
        if steps is None:
            _reply(window, text, engine.Answer("undo", memory.NOTHING_TO_UNDO,
                                               handoffs=(("Open Undo Center", "Undo Center"),)))
            return True
        if not steps:
            _reply(window, text, engine.Answer("undo", "Nothing from that plan can be put back by Game Grave. " +
                                               " ".join(notes), handoffs=(("Open Undo Center", "Undo Center"),)))
            return True
        from gg_desktop import autopilot_core as core, autopilot_ui
        plan = core.Plan(("Undo: " + request)[:300], steps)
        autopilot_ui.post_plan(window, plan, text)
        if notes:
            _append_assistant(window, engine.Answer("undo", " ".join(notes)))
        return True
    return False


def _say(window, text, reply):
    state = ensure_chats(window)
    chat = current_chat(window)
    if chat is None:
        chat = actions.new_chat(time.time())
        state.chats.insert(0, chat)
        state.current = chat["id"]
    actions.add_exchange(chat, text, engine.Answer("followup", reply), time.time())
    persist_chats(window)
    refresh_all(window)


def follow_up(window, text):
    """True when `text` was a reply to the assistant's last offer and has been acted on."""
    from gg_desktop import assistant_followup as fu
    go, no = fu.is_go_ahead(text), fu.is_no(text)
    if not (go or no):
        return False
    offer = fu.last_offer(current_chat(window))
    if offer is None:
        if go:
            _say(window, text, fu.NOTHING)
            return True
        return False
    if no:
        _say(window, text, fu.DECLINED)
        return True
    from gg_desktop import autopilot_core, autopilot_ui
    if offer.kind == "turn_on":
        if not save(window, dict(window.settings, **{autopilot_core.SETTING: True})):
            return True
        if _alive_switch(window):
            window.autopilot_switch.blockSignals(True)
            window.autopilot_switch.setChecked(True)
            window.autopilot_switch.blockSignals(False)
        autopilot_ui.sync_panel(window)
        autopilot_ui.handle(window, offer.request, shown=text)     # the plan; nothing changes until Run all
        window.status.setText("Running tools is on. Here is the plan; nothing changes until you press Run all.")
        return True
    if offer.kind == "plan":
        if offer.plan_id not in autopilot_ui.state_of(window).plans:
            _say(window, text, fu.STALE)
            return True
        _say(window, text, fu.RUNNING)
        autopilot_ui.run_all(window, offer.plan_id)                  # its one confirmation still comes first
        return True
    if offer.kind == "do":
        send(window, offer.request)
        return True
    return False


# "How do I use this?" asked from the pop-out means the tab you are looking at.
_HERE = re.compile(r"\b(this (tab|page|screen|tool|one)|here|on this|in this)\b")
ROUTE_FEATURE = {"Overview": "scan_pc", "Games": "games_tab", "Mods": "my_mods", "Captures": "captures",
                 "Old Files": "old_files", "Other Storage": "other_storage", "Graveyard": "graveyard",
                 "Game DNA": "game_dna", "Undo Center": "undo_center", "Hardware": "hardware", "Settings": "never_touch",
                 "More Tools": "windows_cleanup", "Fix Kit": "resurrection_kit", "Ready Room": "soulbind"}


def here_question(window, text):
    """Name the current tab in a question that says "this tab" or "here", so the answer is about what is on screen."""
    from gg_desktop import assistant_features as features
    route = getattr(window, "current_route", "")
    if route == "AI Assistant" or not _HERE.search(text.casefold()) or features.find_feature(text) is not None:
        return text
    if route == "Hardware" and getattr(window, "hardware_tab", "") == "Drivers & Startup":
        key = "drivers_startup"
    elif route == "More Tools":
        return text + " (in the Toolbox)"
    else:
        key = ROUTE_FEATURE.get(route)
    feature = features.BY_KEY.get(key) if key else None
    return f"{text} ({feature.keywords[0]})" if feature else text


def new_chat(window):
    state = ensure_chats(window)
    chat = current_chat(window)
    if chat is None or chat["messages"]:
        chat = actions.new_chat(time.time())
        state.chats.insert(0, chat)
        state.current = chat["id"]
    refresh_all(window)
    if live(window):
        window.assistant_input.setFocus()


def pick_chat(window):
    items = window.assistant_list.selectedItems()
    if not items:
        return
    state = state_of(window)
    chat_id = items[0].data(Qt.UserRole)
    if chat_id == PINNED:
        show_pins(window)
        fill_list(window)
        return
    if chat_id and chat_id != state.current:
        state.current = chat_id
        render_chat(window)
        window.assistant_title.setText(current_chat(window)["title"] if current_chat(window)["messages"] else "New chat")


def delete_chat(window):
    state = state_of(window)
    chat = current_chat(window)
    if not chat or not chat["messages"]:
        window.info("Nothing to delete", "Start a conversation first.")
        return
    if not window.confirm("Delete this conversation?", f"Delete \"{chat['title']}\"?\n\nOnly the saved chat text is "
                          "removed. No files, scans or cleanup records are touched.", destructive=True):
        return
    state.chats = actions.delete_chat(state.chats, chat["id"])
    if not state.chats:
        state.chats = [actions.new_chat(time.time())]
    state.current = state.chats[0]["id"]
    persist_chats(window)
    refresh(window)


def clear(window):
    chat = current_chat(window)
    if not chat or not chat["messages"]:
        return
    if not window.confirm("Clear this chat?", "Remove this conversation's saved messages?\n\nNo files, scans or "
                          "cleanup records are touched.", destructive=True):
        return
    actions.clear_chat(chat)
    persist_chats(window)
    refresh(window)


def toggle_source(window, key, on):
    state = state_of(window)
    keys = set(state.enabled)
    keys.add(key) if on else keys.discard(key)
    updated = data.with_sources(window.settings, keys)
    if not save(window, updated):
        refresh(window)
        return
    state.enabled = data.enabled_sources(updated)
    make_facts(window)
    refresh(window)


def choose_scope(window):
    state = state_of(window)
    games = sorted(state.facts.games, key=lambda g: g.name.casefold())
    if not games:
        window.info("No games yet", "Run Scan PC first. Then you can limit answers to one game.")
        return
    names = ["All games"] + [f"{g.name} ({g.launcher})" for g in games]
    start = 0
    for i, g in enumerate(games, 1):
        if g.key == state.scope:
            start = i
    choice, accepted = QInputDialog.getItem(window, "Limit answers to", "Game:", names, start, False)
    if not accepted:
        return
    index = names.index(choice)
    state.scope = games[index - 1].key if index else ""
    if not save(window, actions.with_scope(window.settings, state.scope)):
        return
    make_facts(window)
    refresh(window)


FEEDBACK_KEY = "assistant_feedback"
MAX_FEEDBACK = 50


def review_text(window, question, answer):
    """A report of one exchange for whoever helps the user: the question, the answer, where it came from, the version."""
    from gg_desktop import local_ai_ui
    from gg_desktop import __version__ as version
    model = local_ai_ui.chosen(window) if local_ai_ui.enabled(window) else "built-in"
    return (f"Game Grave {version} · assistant: {model}\n\nQuestion: {question}\n\n"
            f"{actions.answer_text(question, answer)}\n\nSources: {', '.join(answer.sources) or 'none'}")


class _Drops(QObject):
    """Lets a text file be dropped on the chat box; it is attached like the Attach button does."""
    def __init__(self, window, box):
        super().__init__(box)
        self.window_, self.box = window, box

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind in (QEvent.DragEnter, QEvent.DragMove) and event.mimeData().hasUrls():
            event.acceptProposedAction()
            return True
        if kind == QEvent.Drop and event.mimeData().hasUrls():
            urls = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
            if urls:
                attach_file(self.window_, self.box, urls[0])
            event.acceptProposedAction()
            return True
        return False


def accept_drops(window, box):
    box.setAcceptDrops(True)
    box.installEventFilter(_Drops(window, box))


IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".bmp", ".webp")


def attach_image(window, box, path):
    """A screenshot of an error: the Gravekeeper reads it when its model can see images (Qwen 3.5 with its image file)."""
    from gg_desktop import local_ai_core as ai
    if not gravekeeper_on(window) or not ai.sees_images(local_ai_ui.chosen(window)):
        window.info("Can't read screenshots yet", "Reading screenshots needs the Local AI switched on with a Qwen 3.5 "
                    "model (Settings in the chat header, then Local AI). You can also type or paste the error text.")
        return
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PySide6.QtGui import QImage
    picture = QImage(str(path))
    if picture.isNull():
        window.info("Can't read that picture", "That file couldn't be opened as a picture.")
        return
    if max(picture.width(), picture.height()) > 1600:      # enough to read an error box, small enough to be quick
        picture = picture.scaled(1600, 1600, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    picture.save(buffer, "PNG")
    import base64
    uri = "data:image/png;base64," + base64.b64encode(bytes(data)).decode("ascii")
    typed = box.text().strip()
    box.clear()
    send(window, typed or "What does this screenshot show, and what should I do about it?", source=box, image=uri)


def pick_attachment(window, box):
    from PySide6.QtWidgets import QFileDialog
    path, _ = QFileDialog.getOpenFileName(window, "Attach a log, text file or screenshot", "",
                                          "Logs, text and screenshots (*.log *.txt *.ini *.cfg *.json *.xml *.csv *.png "
                                          "*.jpg *.jpeg *.bmp *.webp);;All files (*)")
    if path:
        attach_file(window, box, path)


def attach_file(window, box, path):
    """Reads the file (read only), keeps the lines that stand out, and asks about them with whatever was typed."""
    from gg_desktop import assistant_links as links
    if str(path).lower().endswith(IMAGE_TYPES):
        attach_image(window, box, path)
        return
    name, text, *why = links.read_log(path)
    if text is None:
        window.info("Can't attach that file", why[0] if why else "That file couldn't be read.")
        return
    typed = box.text().strip()
    box.clear()
    block = "From the file " + name + " (the lines that stand out):\n" + ("\n".join(links.key_lines(text))
                                                                            or "(the file is empty)")
    send(window, typed or "What does this log say went wrong, and what should I try?", source=box, attached=block)


def level_panel(window, accent_fn):
    """"Explain things for": how much the assistant explains (used by the Local AI's answers)."""
    from PySide6.QtWidgets import QComboBox
    from gg_desktop import assistant_memory as memory
    box, lay = panel(kind="fileResults", padding=10, spacing=6)
    accent_fn(box, "assistantLevel", "cyan")
    lay.addWidget(label("Explain things for", "sectionTitle"))
    combo = QComboBox()
    combo.setAccessibleName("Explain things for")
    for key, name in memory.LEVELS.items():
        combo.addItem(name, key)
    combo.setCurrentIndex(max(0, combo.findData(memory.level_of(window.settings))))
    combo.setToolTip("New: everyday words and one step at a time. Know my way around: short answers with the technical "
                     "details. Used by the Local AI's answers; the built-in answers stay the same.")
    combo.currentIndexChanged.connect(
        lambda _i: save(window, dict(window.settings, **{memory.LEVEL_KEY: combo.currentData() or ""})))
    lay.addWidget(combo)
    window.assistant_level = combo
    from gg_desktop import assistant_voice
    from gg_desktop.settings_page import Switch
    talk = row(spacing=6)
    talk.addWidget(label("Read answers aloud", "caption"), 1)
    reader = Switch(bool(window.settings.get(assistant_voice.READ_KEY)), name="Read answers aloud")
    reader.setToolTip("The Gravekeeper's answers are read out with Windows' own voice.")
    reader.setEnabled(assistant_voice.can_speak())

    def flipped(on):
        save(window, dict(window.settings, **{assistant_voice.READ_KEY: bool(on)}))
        if not on:
            assistant_voice.stop(window)
    reader.toggled.connect(flipped)
    talk.addWidget(reader)
    lay.addLayout(talk)
    window.assistant_reader = reader
    return box


PINNED = "__pinned__"


def pin_answer(window, question, answer):
    """Keeps the answer in this PC's settings under Pinned answers. Nothing else changes."""
    from datetime import datetime
    from gg_desktop import assistant_links as links
    pins = links.add_pin(window.settings.get(links.PINS_KEY), question, answer.text,
                         datetime.now().isoformat(timespec="minutes"))
    save(window, dict(window.settings, **{links.PINS_KEY: pins}))
    window.status.setText("Pinned. Find it at the top of Conversations.")
    if hasattr(window, "assistant_list"):
        fill_list(window)


def show_pins(window):
    """A small window with every pinned answer: read, copy or unpin."""
    from PySide6.QtWidgets import QDialog, QTextBrowser, QVBoxLayout, QHBoxLayout, QListWidget as _List
    from gg_desktop import assistant_links as links
    pins = list(window.settings.get(links.PINS_KEY) or [])
    if not pins:
        return
    dialog = QDialog(window)
    dialog.setWindowTitle("Pinned answers")
    dialog.resize(640, 460)
    lay = QVBoxLayout(dialog)
    names = _List()
    names.setAccessibleName("Pinned answers")
    view = QTextBrowser()
    view.setOpenLinks(False)
    view.anchorClicked.connect(lambda url: open_link(window, url.toString()))

    def refill():
        names.clear()
        for pin in reversed(pins):
            names.addItem(pin["question"][:80])
        if names.count():
            names.setCurrentRow(0)
        else:
            view.clear()

    def shown(row):
        if 0 <= row < len(pins):
            pin = pins[len(pins) - 1 - row]
            games = [g.name for g in getattr(getattr(window, "inventory", None), "games", []) or []]
            view.setHtml(f"<p><b>{links.html.escape(pin['question'])}</b></p><p>{links.linkify(pin['answer'], games)}</p>"
                         f"<p style='color:#8a96a8'>Pinned {links.html.escape(pin.get('when') or '')}</p>")

    def unpin():
        row = names.currentRow()
        if 0 <= row < len(pins):
            pins[:] = links.remove_pin(pins, len(pins) - 1 - row)
            save(window, dict(window.settings, **{links.PINS_KEY: list(pins)}))
            refill()

    def copy():
        row = names.currentRow()
        if 0 <= row < len(pins):
            pin = pins[len(pins) - 1 - row]
            QGuiApplication.clipboard().setText(pin["question"] + "\n\n" + pin["answer"])

    names.currentRowChanged.connect(shown)
    lay.addWidget(names, 1)
    lay.addWidget(view, 2)
    buttons = QHBoxLayout()
    buttons.addWidget(tool("Close", "", dialog.accept))
    buttons.addStretch(1)
    buttons.addWidget(tool("Copy", "file", copy))
    buttons.addWidget(tool("Unpin", "trash", unpin))
    lay.addLayout(buttons)
    window._assistant_pins_dialog = dialog
    refill()
    dialog.show()


def not_helpful(window, question, answer):
    """Saves the exchange in this PC's settings (newest 50) and copies a report; nothing leaves the PC by itself."""
    from datetime import datetime
    kept = list(window.settings.get(FEEDBACK_KEY) or [])[-(MAX_FEEDBACK - 1):]
    kept.append({"when": datetime.now().isoformat(timespec="seconds"), "question": question[:600],
                 "answer": answer.text[:2000], "intent": answer.intent, "sources": list(answer.sources)})
    updated = dict(window.settings, **{FEEDBACK_KEY: kept})
    if answer.intent == "local_ai" or "Gravekeeper" in answer.sources:
        from gg_desktop import gravekeeper
        updated = gravekeeper.add_lesson(updated, question, answer.text)     # it is told about this mistake next time
    save(window, updated)
    QGuiApplication.clipboard().setText(review_text(window, question, answer))
    window.status.setText("Thanks. Kept on this PC, and a report is copied if you want to send it. Try asking it another "
                          "way, or with more detail.")


def copy_answer(window, question, answer):
    QGuiApplication.clipboard().setText(actions.answer_text(question, answer))
    window.status.setText("Answer copied.")
