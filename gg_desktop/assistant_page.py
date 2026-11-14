"""AI Assistant page: the approved mockup, answering only from data Game Grave has already scanned.

There is no online service. Questions are answered locally by gg_desktop.assistant_engine from the in-memory inventory,
the recovery records and the activity log. The assistant is read only: it never deletes, moves, restores or scans, and
every row that names files hands the owner to the tab that owns them. Conversations are saved in the owner's settings.
"""
from __future__ import annotations

from gg_desktop.nav_groups import display_name

from types import SimpleNamespace
import time

from PySide6.QtCore import QRectF, QSize, Qt, QTimer
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
WELCOME = ("Ask me about your games, storage, mods, captures or cleanup history. I answer only from what Game Grave "
           "has already scanned on this PC, I show where each answer came from, and I never change any file.")
ACCENTS = {"red": "255,37,74", "yellow": "246,190,36", "cyan": "19,188,245", "green": "50,214,122"}


def accent(frame, name, tone):
    rgb = ACCENTS[tone]
    frame.setObjectName(name)
    frame.setStyleSheet(
        f"QFrame#{name}{{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba({rgb},38),stop:.4 #08101a,stop:1 #060b12);"
        f"border:1.5px solid rgba({rgb},215);border-radius:10px;}}")
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
        if item.tab:
            go = tool("Open", "chevron", lambda _=False, tab=item.tab: window.navigate(tab), tip="Open " + display_name(item.tab))
            go.setText("Open " + display_name(item.tab))
            go.setIcon(icon("chevron", "#e8eef5", 12))
            go.setFixedHeight(26)
            go.setStyleSheet("font-size:11px;padding:0 9px;")
            line.addWidget(go)


class Avatar(QLabel):
    def __init__(self):
        super().__init__()
        self.setFixedSize(30, 30)
        self.setAlignment(Qt.AlignCenter)
        self.setPixmap(icon("sparkles", "#ff254a", 17).pixmap(17, 17))
        self.setStyleSheet("background:#14060b;border:1px solid #ff254a;border-radius:15px;")


def bubble(text):
    wrap = QWidget()
    line = row(spacing=0, margins=(40, 0, 0, 0))
    wrap.setLayout(line)
    line.addStretch()
    frame = QFrame()
    frame.setObjectName("assistantAsk")
    frame.setStyleSheet("QFrame#assistantAsk{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(255,37,74,80),"
                        "stop:1 rgba(255,37,74,30));border:1px solid #8c1b2f;border-radius:10px;}")
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

    prompts, box = panel(kind="fileFilterPanel", padding=9, spacing=5)
    accent(prompts, "assistantPrompts", "yellow")
    prompts.setMinimumWidth(190)
    prompts.setMaximumWidth(235)
    head2 = row(spacing=6)
    bolt = QLabel()
    bolt.setPixmap(icon("sparkles", "#f6be24", 18).pixmap(18, 18))
    head2.addWidget(bolt)
    head2.addWidget(label("Quick Prompts", "sectionTitle"), 1)
    box.addLayout(head2)
    for symbol, text, question in engine.QUICK_PROMPTS:
        control = tool(text, symbol, lambda _=False, q=question: send(self, q), tip=question)
        control.setStyleSheet("text-align:left;font-size:12px;")
        box.addWidget(control)
    left = QWidget()
    left_lay = column(spacing=8)
    left.setLayout(left_lay)
    left_lay.addWidget(convo, 5)
    left_lay.addWidget(prompts, 4)
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
    self.assistant_scope = tool("All Games", "game", lambda: choose_scope(self),
                                tip="Limit answers to one game, or all games")
    self.assistant_scope.setFixedHeight(28)
    top.addWidget(self.assistant_scope)
    top.addWidget(tool("Clear Chat", "refresh", lambda: clear(self), tip="Remove this conversation's saved messages"))
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

    using_box = QWidget()
    using_box.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    using_box.setMinimumWidth(0)
    using = row(spacing=6, margins=(12, 4, 12, 0))
    using_box.setLayout(using)
    using.addWidget(label("Using", "caption"))
    self.assistant_using = row(spacing=5)
    using.addLayout(self.assistant_using)
    using.addStretch()
    body.addWidget(using_box)
    compose = row(spacing=8, margins=(12, 6, 12, 10))
    self.assistant_input = QLineEdit()
    self.assistant_input.setPlaceholderText("Ask about your games, mods, storage, or cleanup history…")
    self.assistant_input.setAccessibleName("Message the assistant")
    self.assistant_input.setMaxLength(engine_limit())
    self.assistant_input.setFixedHeight(36)
    self.assistant_input.setMinimumWidth(60)
    self.assistant_input.returnPressed.connect(lambda: send(self))
    compose.addWidget(self.assistant_input, 1)
    self.assistant_send = tool("Send", "chevron", lambda: send(self), kind="primary", tip="Ask (Enter)")
    self.assistant_send.setFixedHeight(36)
    compose.addWidget(self.assistant_send)
    body.addLayout(compose)

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
    right = QWidget()
    right_lay = column(spacing=8)
    right.setLayout(right_lay)
    right_lay.addWidget(can, 4)
    right_lay.addWidget(used, 4)

    page.content.addWidget(_split(_split(left, chat, [222, 580]), _detail_scroll(right), [802, 232]), 1)
    page.assistant_ready = True
    refresh(self)
    self.assistant_input.setFocus()


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
    ordered = sorted(state.chats, key=lambda c: (-(c["updated"] or 0)))
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


def clear_messages(window):
    layout = window.assistant_messages
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()


def render_chat(window):
    clear_messages(window)
    chat = current_chat(window)
    window.assistant_title.setText(chat["title"] if chat and chat["messages"] else "New chat")
    if not chat or not chat["messages"]:
        add_assistant_text(window, WELCOME)
        if local_ai_ui.show_card(window):
            window.assistant_messages.addSpacing(6)
            window.assistant_messages.addWidget(local_ai_ui.setup_card(window))
    else:
        question = ""
        for message in chat["messages"]:
            if message["role"] == "user":
                question = message["text"]
                window.assistant_messages.addWidget(bubble(message["text"]))
            else:
                add_answer(window, question, engine.answer_from_dict(message.get("answer") or {}))
    window.assistant_messages.addStretch()
    scroll_down(window)


def add_assistant_text(window, text):
    line = row(spacing=10, margins=(0, 0, 0, 0))
    holder = QWidget()
    holder.setLayout(line)
    avatar = Avatar()
    line.addWidget(avatar, 0, Qt.AlignTop)
    words = label(text, "subtle", wrap=True)
    words.setTextFormat(Qt.PlainText)
    words.setStyleSheet("color:#e8eef5;font-size:13px;")
    line.addWidget(words, 1)
    window.assistant_messages.addWidget(holder)


def add_answer(window, question, answer):
    if answer is None:
        return
    line = row(spacing=10)
    holder = QWidget()
    holder.setLayout(line)
    line.addWidget(Avatar(), 0, Qt.AlignTop)
    stack = column(spacing=7)
    text = label(answer.text, "subtle", wrap=True)
    text.setTextFormat(Qt.PlainText)
    text.setTextInteractionFlags(Qt.TextSelectableByMouse)
    text.setStyleSheet("color:#e8eef5;font-size:13px;")
    stack.addWidget(text)
    for index, item in enumerate(answer.rows):
        stack.addWidget(AnswerRow(window, item, ROW_COLORS[index % len(ROW_COLORS)]))
    if answer.note:
        note = label(answer.note, "caption", wrap=True)
        note.setTextFormat(Qt.PlainText)
        note.setTextInteractionFlags(Qt.TextSelectableByMouse)
        stack.addWidget(note)
    actions_row = ActionFlow(spacing=6)
    for caption, tab in answer.handoffs:
        actions_row.addWidget(tool(caption, "chevron", lambda _=False, t=tab: window.navigate(t), tip=f"Open the {tab} tab"))
    actions_row.addWidget(tool("Copy", "file", lambda _=False, q=question, a=answer: copy_answer(window, q, a),
                               tip="Copy this question and answer"))
    stack.addWidget(_widget(actions_row))
    if answer.sources:
        sources = row(spacing=5)
        sources.addWidget(label("Sources", "caption"))
        for name in answer.sources:
            sources.addWidget(chip(name, "blue"))
        sources.addStretch()
        stack.addLayout(sources)
    line.addLayout(stack, 1)
    window.assistant_messages.addWidget(holder)


def scroll_down(window):
    def go():
        if live(window):
            bar = window.assistant_scroll.verticalScrollBar()
            bar.setValue(bar.maximum())
    QTimer.singleShot(0, go)
    QTimer.singleShot(60, go)


# ------------------------------------------------------------------ actions
def send(window, question=None):
    if not live(window):
        return
    state = state_of(window)
    text = " ".join((question if question is not None else window.assistant_input.text()).split())[:actions.MAX_QUESTION]
    if not text:
        return
    facts = make_facts(window)
    result = engine.answer(text, facts)
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
            if live(window):
                window.assistant_input.setText(text)
                send(window)
        window.job(work, arrived, error_title="Could not read the hardware")
        return
    chat = current_chat(window)
    if chat is None:
        chat = actions.new_chat(time.time())
        state.chats.insert(0, chat)
        state.current = chat["id"]
    window.assistant_input.clear()
    if local_ai_ui.enabled(window) and result.intent not in ("greet", "thanks", "off", "hardware_unread"):
        msgs = chat["messages"]
        history = [(msgs[i]["text"], msgs[i + 1]["text"]) for i in range(0, len(msgs) - 1, 2)
                   if msgs[i]["role"] == "user" and msgs[i + 1]["role"] == "assistant"]
        window.assistant_input.setEnabled(False)
        window.assistant_send.setEnabled(False)
        starting = local_ai_ui.state_of(window).server is None
        window.status.setText("Local AI is starting on this PC (the first answer can take up to a minute)…" if starting
                              else "Local AI is writing the answer on this PC…")
        # Show the question and a thinking line right away; the real answer replaces them.
        layout = window.assistant_messages
        if layout.count() and layout.itemAt(layout.count() - 1).spacerItem() is not None:
            layout.takeAt(layout.count() - 1)
        layout.addWidget(bubble(text))
        add_assistant_text(window, "Starting the local AI model, this first answer can take up to a minute…" if starting
                           else "Thinking…")
        layout.addStretch()
        scroll_down(window)
        chat_id = chat["id"]

        def deliver(answer):
            target = next((c for c in state.chats if c["id"] == chat_id), None)
            if target is not None:
                actions.add_exchange(target, text, answer, time.time())
                persist_chats(window)
            if live(window):
                window.assistant_input.setEnabled(True)
                window.assistant_send.setEnabled(True)
                window.assistant_input.setFocus()
                window.status.setText("Answered on this PC from scanned data. Nothing was changed.")
                refresh(window)
        local_ai_ui.answer_async(window, text, result, facts, history, deliver)
        return
    actions.add_exchange(chat, text, result, time.time())
    persist_chats(window)
    window.status.setText("Answered from scanned data. Nothing was changed.")
    refresh(window)


def new_chat(window):
    state = state_of(window)
    chat = current_chat(window)
    if chat is None or chat["messages"]:
        chat = actions.new_chat(time.time())
        state.chats.insert(0, chat)
        state.current = chat["id"]
    refresh(window)
    window.assistant_input.setFocus()


def pick_chat(window):
    items = window.assistant_list.selectedItems()
    if not items:
        return
    state = state_of(window)
    chat_id = items[0].data(Qt.UserRole)
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


def copy_answer(window, question, answer):
    QGuiApplication.clipboard().setText(actions.answer_text(question, answer))
    window.status.setText("Answer copied.")
