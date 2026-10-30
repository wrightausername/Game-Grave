"""Keyboard-first navigation guide for Game Grave.

Shortcuts only open read-only pages, trigger the same explicit Scan PC action,
or cancel a running scan. No key combination recycles or deletes user files.
"""
from __future__ import annotations

PAGE_SHORTCUTS = (
    ("Ctrl+1", "Overview", "Overview"),
    ("Ctrl+2", "Game DNA", "Game DNA"),
    ("Ctrl+3", "Game Mods", "Game Mods"),
    ("Ctrl+4", "The Graveyard", "The Graveyard"),
    ("Ctrl+5", "Save Vault", "Save Vault"),
    ("Ctrl+6", "Resurrection Lab", "Resurrection Lab"),
    ("Ctrl+7", "Undo Center", "Undo Center"),
)

ACTION_SHORTCUTS = (
    ("F1", "Show this keyboard guide"),
    ("F5", "Start a read-only PC scan"),
    ("Esc", "Request cancel while a scan is running"),
)

PAGE_KEYS = {shortcut: destination for shortcut, _, destination in PAGE_SHORTCUTS}


def shortcut_help_text() -> str:
    lines = ["NAVIGATION (NO CLEANUP ACTIONS)"]
    lines.extend(f"{shortcut:9}  {label}" for shortcut, label, _ in PAGE_SHORTCUTS)
    lines.append("")
    lines.append("OTHER KEYS")
    lines.extend(f"{key:9}  {description}" for key, description in ACTION_SHORTCUTS)
    lines.append("")
    lines.append("Use Tab / Shift+Tab to move between buttons and Space to activate.")
    lines.append("No shortcut deletes or restores files without normal approval dialogs.")
    return "\n".join(lines)
