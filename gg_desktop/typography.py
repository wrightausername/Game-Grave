"""Game Grave Windows typography.

Uses fonts shipped with supported Windows installations, not bundled or
redistributed commercial fonts. A consistent display/utility pairing is
deliberate: condensed geometric lettering for the gaming UI, Segoe for dense
file paths, timestamps and dialogs. Fallbacks keep Qt/Linux preview working.
"""
from __future__ import annotations

from functools import lru_cache
from PySide6.QtGui import QFontDatabase


@lru_cache(maxsize=1)
def _families() -> frozenset[str]:
    try:
        return frozenset(QFontDatabase.families())
    except Exception:
        return frozenset()


@lru_cache(maxsize=1)
def display_family() -> str:
    family_names = _families()
    for family in (
        "Bahnschrift", "Bahnschrift SemiCondensed",
        "Bahnschrift Condensed", "Segoe UI Variable Display",
        "Segoe UI Semibold", "Segoe UI", "Arial",
    ):
        if family in family_names:
            return family
    return "Sans Serif"


@lru_cache(maxsize=1)
def text_family() -> str:
    family_names = _families()
    for family in ("Segoe UI Variable", "Segoe UI", "Arial"):
        if family in family_names:
            return family
    return "Sans Serif"
