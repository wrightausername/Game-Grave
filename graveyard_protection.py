"""Per-item Never Touch controls for the Graveyard; no filesystem writes.

Built-in safe-path rules cannot be toggled. Protections inherited from parent
folders can only be changed deliberately in Settings, not from a file row.
"""
from __future__ import annotations

import os
from pathlib import Path

from core import is_protected_path


def _identity(path: str) -> str:
    # Preserve safe path matching for case-insensitive Windows filesystems.
    # This compares names only; it does not follow filesystem links.
    return os.path.abspath(os.fspath(path)).replace("/", "\\").casefold().rstrip("\\")


def protection_action(path: str, never_touch: list[str]) -> tuple[str | None, str]:
    """Return the only permitted action for this row, or a safety explanation."""
    candidate = Path(path)
    if is_protected_path(candidate, []):
        return None, "Built-in protection applies to game, save, mod, or system locations."
    if any(isinstance(x, str) and x.strip() and _identity(x) == _identity(path)
           for x in never_touch):
        return "Unprotect", "You personally protected this item."
    if is_protected_path(candidate, never_touch):
        return None, "A parent folder is protected. Change that rule under Settings > Never Touch."
    return "Protect", "Prevent Game Grave from recycling this item."


def set_item_protection(never_touch: list[str], path: str, *, protect: bool) -> list[str]:
    """Toggle only an exact user entry, never inherited or built-in rules."""
    action, reason = protection_action(path, never_touch)
    desired = "Protect" if protect else "Unprotect"
    if action != desired:
        raise ValueError(reason)
    if protect:
        return [*never_touch, os.path.abspath(path)]
    return [x for x in never_touch
            if not (isinstance(x, str) and _identity(x) == _identity(path))]
