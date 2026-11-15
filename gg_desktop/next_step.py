"""Empty screens say what to do next with one button beside the message (Scan Other Storage, Scan PC, Clear filters).
The button only starts what the tab's own controls already do; it never changes anything by itself.
"""
from __future__ import annotations

from PySide6.QtWidgets import QLayout, QPushButton
from shiboken6 import isValid


def _layout_of(widget):
    parent = widget.parentWidget()
    if parent is None or parent.layout() is None:
        return None, -1

    def search(layout):
        index = layout.indexOf(widget)
        if index >= 0:
            return layout, index
        for i in range(layout.count()):
            child = layout.itemAt(i).layout()
            if isinstance(child, QLayout):
                found = search(child)
                if found[0] is not None:
                    return found
        return None, -1
    return search(parent.layout())


def show(anchor, caption, action, tip=""):
    """Show (or update) the next-step button right under `anchor`; caption "" hides it."""
    if anchor is None or not isValid(anchor):
        return None
    button = anchor.property("gg_next_step")
    if button is not None and not isValid(button):
        button = None
    if not caption:
        if button is not None:
            button.hide()
        return None
    if button is None:
        layout, index = _layout_of(anchor)
        if layout is None:
            return None
        button = QPushButton()
        button.setObjectName("primaryButton")
        button.setProperty("kind", "primary")
        button.setFixedHeight(30)
        button.setMaximumWidth(260)
        layout.insertWidget(index + 1, button)
        anchor.setProperty("gg_next_step", button)
        button.clicked.connect(lambda: getattr(button, "gg_action", lambda: None)())
    button.setText(caption)
    button.setAccessibleName(caption)
    button.setToolTip(tip or caption)
    button.gg_action = action
    button.show()
    return button


def hide(anchor):
    return show(anchor, "", None)
