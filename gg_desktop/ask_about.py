"""Right-click "Ask the assistant about this" on games, mods, files and folders. Opens the AI Assistant pop-out and
answers there, so the tab stays where it is. For a game the built-in assistant answers as if it was asked; for every
other row the answer is built from the row itself (ask_about_core). Reading only; nothing is changed.
"""
from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu
from shiboken6 import isValid

from gg_desktop import ask_about_core as core

LABEL = "Ask the assistant about this"


def ask(window, kind, item):
    from gg_desktop import assistant_page, assistant_popout
    if not window.assistant_enabled():
        window.info("AI Assistant is off", "Turn on the AI Assistant in Settings, then right-click again.")
        return False
    pop = assistant_popout.open_popout(window)
    if pop is None:
        return False
    info = core.info_of(kind, item)
    text = core.question(info)
    if kind == "game":
        assistant_page.send(window, text, source=pop.input)
        return True
    from gg_desktop import assistant_actions as actions
    state = assistant_page.ensure_chats(window)
    chat = assistant_page.current_chat(window)
    if chat is None:
        chat = actions.new_chat(time.time())
        state.chats.insert(0, chat)
        state.current = chat["id"]
    protected = False
    if info.get("path"):
        try:
            from pathlib import Path
            from core import is_protected_path
            protected = is_protected_path(Path(info["path"]), window.settings.get("never_touch", []))
        except Exception:
            protected = False
    actions.add_exchange(chat, text, core.answer(info, protected), time.time())
    assistant_page.persist_chats(window)
    assistant_page.refresh_all(window)
    window.status.setText("Answered from scanned data. Nothing was changed.")
    return True


def add_to_menu(menu, window, kind, item):
    """One more entry, at the end, for a menu a tab already has."""
    if item is None:
        return None
    menu.addSeparator()
    action = menu.addAction(LABEL, lambda: ask(window, kind, item))
    action.setEnabled(window.assistant_enabled())
    if not window.assistant_enabled():
        action.setText(LABEL + "  (turn on the AI Assistant in Settings)")
    return action


def install_table(window, table, kind, item_at):
    """A right-click menu for a list that had none: `item_at(row)` gives the row's item or None."""
    table.setContextMenuPolicy(Qt.CustomContextMenu)

    def show(pos):
        if not isValid(table):
            return
        index = table.indexAt(pos)
        if not index.isValid():
            return
        item = item_at(index.row())
        if item is None:
            return
        menu = QMenu(table)
        add_to_menu(menu, window, kind, item)
        menu.actions()[0].setVisible(False)    # no separator at the top of a one-entry menu
        menu.exec(table.viewport().mapToGlobal(pos))
        menu.deleteLater()
    table.customContextMenuRequested.connect(show)
    table.gg_ask_menu = show
    return show


def install_list(window, view, kind, item_at):
    """The same for a picture grid (a list view): `item_at(row)` gives the item or None."""
    return install_table(window, view, kind, item_at)
