"""Screen-reader names for controls that were built without one.

A button that shows text already reads well. This fills the gaps: icon-only buttons, search boxes, drop-downs and
switches get a name from their tooltip, placeholder or text. It never replaces a name a page set itself and changes
nothing a sighted user can see.
"""
from __future__ import annotations

import re


def derive_name(text="", tooltip="", placeholder="", fallback=""):
    """The best short name available, or "" when there is nothing honest to say."""
    for candidate in (text, placeholder, tooltip, fallback):
        clean = re.sub(r"\s+", " ", str(candidate or "").replace("&", "")).strip(" .…:")
        if clean and any(ch.isalnum() for ch in clean):
            first = re.split(r"(?<=[.!?])\s", clean)[0]      # a tooltip's first sentence is its name
            return first[:80].strip(" .")
    return ""


def name_controls(root):
    """Give every unnamed button, field, drop-down and tick box under `root` a name. Returns how many it named."""
    from PySide6.QtWidgets import QAbstractButton, QComboBox, QLineEdit, QPlainTextEdit, QTextEdit
    from shiboken6 import isValid
    if root is None or not isValid(root):
        return 0
    named = 0
    for control in root.findChildren(QAbstractButton):
        if not control.accessibleName():
            name = derive_name(control.text(), control.toolTip())
            if name:
                control.setAccessibleName(name)
                named += 1
    for control in root.findChildren(QLineEdit):
        if not control.accessibleName():
            name = derive_name("", control.toolTip(), control.placeholderText(), "Text box")
            control.setAccessibleName(name)
            named += 1
    for control in root.findChildren(QComboBox):
        if not control.accessibleName():
            name = derive_name("", control.toolTip(), control.placeholderText(), "Choice list")
            control.setAccessibleName(name)
            named += 1
    for kind in (QPlainTextEdit, QTextEdit):
        for control in root.findChildren(kind):
            if not control.accessibleName():
                control.setAccessibleName(derive_name("", control.toolTip(), control.placeholderText(), "Text area"))
                named += 1
    return named
