"""Sorting for the Mods library: by name, game, manager, size or date, either direction. No Qt required.

Unknown values (a missing size, an unreadable folder date) always sort last in both directions, so they
never pretend to be the largest, smallest, newest or oldest.
"""
from __future__ import annotations

from datetime import datetime
from functools import lru_cache
import os

OPTIONS = ("Name (A–Z)", "Name (Z–A)", "Size (Largest)", "Size (Smallest)", "Date (Newest)", "Date (Oldest)",
           "Game (A–Z)", "Game (Z–A)", "Manager (A–Z)", "Manager (Z–A)")
DEFAULT = OPTIONS[0]

# Library table column -> (first click, second click). Clicking a header toggles between the two.
HEADERS = {1: ("Name (A–Z)", "Name (Z–A)"), 2: ("Game (A–Z)", "Game (Z–A)"), 3: ("Manager (A–Z)", "Manager (Z–A)"),
           4: ("Size (Largest)", "Size (Smallest)"), 6: ("Date (Newest)", "Date (Oldest)")}


@lru_cache(maxsize=8192)
def modified_time(path):
    """When the mod location last changed on disk, or None if it cannot be read."""
    try:
        return int(os.stat(path).st_mtime)
    except (OSError, ValueError):
        return None


def date_text(stamp):
    return datetime.fromtimestamp(stamp).strftime("%d %b %Y") if stamp else "—"


def size_text(size):
    if size is None:
        return "—"
    from core import human_size
    return human_size(size)


def _value(option, view):
    kind = option.split(" ")[0]
    if kind == "Size":
        return view.size
    if kind == "Date":
        return modified_time(str(view.record.path))
    if kind == "Game":
        return view.game.casefold() or None
    if kind == "Manager":
        return view.manager.casefold() or None
    return view.name.casefold()


def sort_views(views, option):
    """Return the views ordered by `option`; ties and unknowns fall back to name A-Z."""
    if option not in OPTIONS:
        option = DEFAULT
    ordered = sorted(views, key=lambda v: v.name.casefold())
    reverse = option in ("Name (Z–A)", "Size (Largest)", "Date (Newest)", "Game (Z–A)", "Manager (Z–A)")
    known = [v for v in ordered if _value(option, v) is not None]
    unknown = [v for v in ordered if _value(option, v) is None]
    known.sort(key=lambda v: _value(option, v), reverse=reverse)
    return known + unknown


def header_option(column, current):
    """The sort a header click selects: first the default direction, then the opposite one."""
    pair = HEADERS.get(column)
    if not pair:
        return None
    return pair[1] if current == pair[0] else pair[0]
