"""Presentation-only game-library ordering. Unknown measurements sort last.

No UI dependency, network requests, invented game sizes or guessed play times.
The same keys drive Ready Room dropdown and click-to-sort column headings.
"""
from __future__ import annotations

SORT_OPTIONS = (
    "Recently played",
    "Oldest played",
    "Game A to Z",
    "Game Z to A",
    "Launcher A to Z",
    "Launcher Z to A",
    "Size largest",
    "Size smallest",
)
DEFAULT_SORT = SORT_OPTIONS[0]
HEADER_OPTIONS = {
    0: ("Game A to Z", "Game Z to A"),
    1: ("Launcher A to Z", "Launcher Z to A"),
    2: ("Recently played", "Oldest played"),
    3: ("Size largest", "Size smallest"),
}


def sort_game_records(records, mode=DEFAULT_SORT):
    """Stable, case-insensitive sorting; missing size and play time last."""
    if mode not in SORT_OPTIONS:
        mode = DEFAULT_SORT
    rows = list(records)
    tie = lambda g: (str(getattr(g, "name", "")).casefold(),
                     str(getattr(g, "launcher", "")).casefold(),
                     str(getattr(g, "key", "")))
    if mode == "Game A to Z":
        return sorted(rows, key=tie)
    if mode == "Game Z to A":
        return sorted(rows, key=tie, reverse=True)
    if mode == "Launcher A to Z":
        return sorted(rows, key=lambda g: (
            str(getattr(g, "launcher", "")).casefold(), tie(g)))
    if mode == "Launcher Z to A":
        return sorted(rows, key=lambda g: (
            str(getattr(g, "launcher", "")).casefold(), tie(g)), reverse=True)
    attr = "size_bytes" if mode.startswith("Size") else "last_played_at"
    descending = mode in ("Recently played", "Size largest")

    def measured(g):
        value = getattr(g, attr, None)
        valid = type(value) in (int, float) and value >= 0
        return (not valid, -value if valid and descending else
                value if valid else 0, tie(g))
    return sorted(rows, key=measured)


def filter_game_records(records, query="", launcher="All launchers"):
    needle = str(query).strip().casefold()
    return [g for g in records
            if (launcher == "All launchers" or
                str(getattr(g, "launcher", "")) == launcher)
            and (not needle or needle in (
                str(getattr(g, "name", "")) + " " +
                str(getattr(g, "launcher", "")) + " " +
                str(getattr(g, "install_path", ""))).casefold())]


def next_header_sort(column, previous):
    ascending, descending = HEADER_OPTIONS[column]
    return descending if previous == ascending else ascending
