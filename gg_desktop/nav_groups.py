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
        ("Mods", "Turn mods on and off, fix problems"),
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
