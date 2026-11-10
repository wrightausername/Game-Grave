"""Slim, collapsible panels for the optional Ready Room features (Soulbind, Autopsy, Exhume, Squad Sync).

Each one used to be a tall panel that pushed Ready Room's own content down. Now it is one quiet line (title, one
status sentence and an Open button) until the owner opens it. Display only; the features' own rules live elsewhere.
"""
from __future__ import annotations

from PySide6.QtWidgets import QSizePolicy

from gg_desktop.widgets import button

STRIP_HEIGHT = 50
BIG = 16777215


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
    set_open(expanded)
    return panel
