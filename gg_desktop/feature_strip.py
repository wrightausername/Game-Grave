"""Slim, collapsible panels: Soulbind and Squad Sync in Ready Room; Black Box, Autopsy and Exhume in Fix Kit.

Each one used to be a tall panel that pushed Ready Room's own content down. Now it is one quiet line (title, one
status sentence and an Open button) until the owner opens it. Display only; the features' own rules live elsewhere.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QSizePolicy

from gg_desktop.widgets import button

STRIP_HEIGHT = 50
BIG = 16777215
# Ready Room rebuilds itself when live news arrives. Without this a panel you had open would snap shut mid-use.
# Kept for this run of the app only; every panel starts closed the next time Game Grave starts.
_REMEMBERED = {}


class _HeaderClick(QObject):
    """A click anywhere on a strip's header line opens or hides it (owner, 2026-11-14: "if i click on a tool tab it should
    just open not me having to find the open button"). The Open / Hide button keeps working for the keyboard."""

    def __init__(self, panel):
        super().__init__(panel)
        self.panel = panel

    def eventFilter(self, target, event):
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            if target.rect().contains(event.position().toPoint()):
                self.panel.set_open(not self.panel.strip_open)
                return True
        return False


def collapsible(panel_cls, title, subtitle, glyph, *, open_height, open_text="Open", close_text="Hide",
                expanded=False):
    """A ReadyPanel that shows only its header line until opened. Returns the panel; `panel.set_open(True)` opens it."""
    toggle = button(open_text, None, kind="readyLink")
    toggle.setAccessibleName(f"{open_text} {title}")
    panel = panel_cls(title, subtitle, glyph, trailing=toggle)
    panel.strip_toggle = toggle
    panel.strip_open = False

    def set_open(opened: bool):
        panel.strip_open = bool(opened)
        _REMEMBERED[title] = panel.strip_open
        panel.body.setVisible(panel.strip_open)
        toggle.setText(close_text if panel.strip_open else open_text)
        toggle.setAccessibleName(f"{toggle.text()} {title}")
        if panel.strip_open:
            panel.setMinimumHeight(open_height)
            panel.setMaximumHeight(BIG)
            panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        else:
            panel.setMinimumHeight(STRIP_HEIGHT)
            panel.setMaximumHeight(STRIP_HEIGHT)
            panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    toggle.clicked.connect(lambda _=False: set_open(not panel.strip_open))
    panel.set_open = set_open
    header = getattr(panel, "header", None)
    if header is not None:
        header.setCursor(Qt.PointingHandCursor)
        header.setToolTip("Click to open or hide " + title)
        panel._header_click = _HeaderClick(panel)
        header.installEventFilter(panel._header_click)
    set_open(_REMEMBERED.get(title, expanded))
    return panel
