"""How the sidebar is organised: five headings, every tab with one plain line under it. Pure (tests/test_nav_groups.py).

Owner instruction, 2026-11-14 ("these need to be more organized ... things are all over the place"), picking the grouped
sidebar with a new Fix Kit tab. Route keys stay the same everywhere in the code; only the label shown can differ
(More Tools is shown as Toolbox).
"""
from __future__ import annotations

GROUPS = (
    ("Home", (
        ("Overview", "Your PC's gaming at a glance"),
        ("Ready Room", "News, patches and your setup"),
    )),
    ("Library", (
        ("Games", "Everything installed, in one place"),
        ("Mods", "Switch, sort and fix your mods"),
        ("Captures", "Screenshots and recordings"),
    )),
    ("Clean Up", (
        ("Old Files", "Older files you can review"),
        ("Other Storage", "Caches, logs and temp files"),
        ("Graveyard", "Leftovers from removed games"),
    )),
    ("Fix and Protect", (
        ("Fix Kit", "Crashes, backups and rollbacks"),
        ("Game DNA", "What belongs to each game"),
        ("Undo Center", "Every change Game Grave made"),
    )),
    ("PC and Help", (
        ("Hardware", "Specs, drivers, startup apps"),
        ("More Tools", "Windows and file utilities"),
        ("AI Assistant", "Ask about your games or PC"),
        ("Settings", "How Game Grave behaves"),
    )),
)

DISPLAY = {"More Tools": "Toolbox"}


def display_name(route: str) -> str:
    return DISPLAY.get(route, route)


def routes() -> tuple:
    return tuple(route for _heading, items in GROUPS for route, _sub in items)


def subtitle(route: str) -> str:
    for _heading, items in GROUPS:
        for name, sub in items:
            if name == route:
                return sub
    return ""


def group_of(route: str) -> str:
    for heading, items in GROUPS:
        if any(name == route for name, _sub in items):
            return heading
    return ""


OPEN_KEY = "nav_open_groups"


def toggled(open_groups, clicked: str) -> frozenset:
    """Each group opens and folds on its own: a click on a heading flips only that group."""
    groups = set(open_groups)
    groups.symmetric_difference_update({clicked})
    return frozenset(groups)


def open_for(route: str, open_groups) -> frozenset:
    """Going to a tab opens its group if it was folded, so the highlighted tab is on screen. Other groups stay as they are."""
    heading = group_of(route)
    return frozenset(set(open_groups) | ({heading} if heading else set()))


def saved_open(settings) -> frozenset:
    """The groups that were open last time, keeping only headings that still exist."""
    names = {heading for heading, _ in GROUPS}
    value = settings.get(OPEN_KEY)
    return frozenset(v for v in value if v in names) if isinstance(value, list) else frozenset()
