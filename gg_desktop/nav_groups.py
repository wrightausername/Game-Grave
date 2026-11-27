"""How the sidebar is organised. Pure (tests/test_nav_groups.py).

Owner, 2026-11-27 ("it can be overwhelming to first time users looking at the tabs on the left... organize them better and
look more professional", then "I like. Implement it" to the proposal): the everyday places first (Home, Games, Mods,
Deals), then "Keep it running" (Fix a game, Free up space, My PC), then More (Captures, Game DNA, Toolbox), with Assistant,
Undo and Settings pinned at the bottom. No subtitle under each tab (it shows on hover). Two entries hold more than one
tab: Home (Overview, Ready Room) and Free up space (Old Files, Other Storage, Graveyard); their tabs show under them while
you are in one. Route keys are unchanged everywhere in the code; only what the sidebar shows differs.
"""
from __future__ import annotations

# Every tab: (route, one plain line shown on hover and in search)
LINES = {
    "Overview": "Your PC's gaming at a glance", "Ready Room": "News, patches and your setup",
    "Games": "Everything installed, in one place", "Mods": "Switch, sort and fix your mods",
    "Deals": "Cheapest prices and your wishlist", "Fix Kit": "Crashes, backups and rollbacks",
    "Old Files": "Older files you can review", "Other Storage": "Caches, logs and temp files",
    "Graveyard": "Leftovers from removed games", "Hardware": "Specs, drivers, startup apps",
    "Captures": "Screenshots and recordings", "Game DNA": "What belongs to each game",
    "More Tools": "Windows and file utilities", "AI Assistant": "Ask about your games or PC",
    "Undo Center": "Every change Game Grave made", "Settings": "How Game Grave behaves",
}

# Sidebar sections: (label or "" for none, ((entry label, (routes...)), ...))
SECTIONS = (
    ("", (("Home", ("Overview", "Ready Room")), ("Games", ("Games",)), ("Mods", ("Mods",)), ("Deals", ("Deals",)))),
    ("Keep it running", (("Fix a game", ("Fix Kit",)), ("Free up space", ("Old Files", "Other Storage", "Graveyard")),
                         ("My PC", ("Hardware",)))),
    ("More", (("Captures", ("Captures",)), ("Game DNA", ("Game DNA",)), ("Toolbox", ("More Tools",)))),
)
PINNED = (("Assistant", ("AI Assistant",)), ("Undo", ("Undo Center",)), ("Settings", ("Settings",)))
ENTRY_ICON = {"Free up space": "broom"}
HUB_LINES = {"Home": "Overview and your gaming news", "Free up space": "Old files, caches and leftovers"}

# The same tabs in the older (heading, ((route, line), ...)) shape, for search, numbering and checks.
GROUPS = tuple((label or "Start", tuple((route, LINES[route]) for _entry, routes in entries for route in routes))
               for label, entries in SECTIONS) + (("Pinned", tuple((route, LINES[route]) for _e, routes in PINNED
                                                                    for route in routes)),)

DISPLAY = {"More Tools": "Toolbox"}


def display_name(route: str) -> str:
    """The tab's own name (page titles, the assistant): More Tools is shown as Toolbox."""
    return DISPLAY.get(route, route)


def entries():
    """Every sidebar entry in order: (section label, entry label, routes, pinned)."""
    out = [(label, entry, routes, False) for label, items in SECTIONS for entry, routes in items]
    return out + [("", entry, routes, True) for entry, routes in PINNED]


def routes() -> tuple:
    return tuple(route for _s, _e, rs, _p in entries() for route in rs)


def subtitle(route: str) -> str:
    return LINES.get(route, "")


def entry_of(route: str) -> str:
    """The sidebar entry a tab lives under ("Free up space" for Graveyard)."""
    for _s, entry, rs, _p in entries():
        if route in rs:
            return entry
    return ""


def routes_of(entry: str) -> tuple:
    for _s, name, rs, _p in entries():
        if name == entry:
            return rs
    return ()


def is_hub(entry: str) -> bool:
    return len(routes_of(entry)) > 1


def tip(entry: str) -> str:
    rs = routes_of(entry)
    if len(rs) > 1:
        return f"{entry}: {', '.join(display_name(r) for r in rs)}"
    names = display_name(rs[0]) if rs else entry
    return f"{entry}: {LINES.get(rs[0], '')}" if names == entry else f"{entry} ({names}): {LINES.get(rs[0], '')}"


def group_of(route: str) -> str:
    for heading, items in GROUPS:
        if any(name == route for name, _sub in items):
            return heading
    return ""


def hub_target(entry: str, last: dict) -> str:
    """Where a click on an entry goes: the tab you were last on inside it, else its first tab."""
    rs = routes_of(entry)
    remembered = (last or {}).get(entry)
    return remembered if remembered in rs else (rs[0] if rs else "")


COLLAPSED_KEY = "nav_collapsed"
HUB_KEY = "nav_hub_last"


# Older settings: kept so a saved choice from the dropdown sidebar is read without error.
OPEN_KEY = "nav_open_groups"


def toggled(open_groups, clicked: str) -> frozenset:
    groups = set(open_groups)
    groups.symmetric_difference_update({clicked})
    return frozenset(groups)


def open_for(route: str, open_groups) -> frozenset:
    heading = group_of(route)
    return frozenset(set(open_groups) | ({heading} if heading else set()))


def saved_open(settings) -> frozenset:
    names = {heading for heading, _ in GROUPS}
    value = settings.get(OPEN_KEY)
    return frozenset(v for v in value if v in names) if isinstance(value, list) else frozenset()
