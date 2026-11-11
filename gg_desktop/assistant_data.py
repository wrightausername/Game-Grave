"""AI Assistant facts: a read-only snapshot of what Game Grave has already scanned.

Nothing here reads the disk or the network. Every number comes from the in-memory inventory, the recovery records and
the activity log. Reported sizes stay "reported": they are what launchers and scans recorded, not measured disk use, and
a recycled file is never counted as freed space.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from gg_desktop import undo_data
from gg_desktop.insight_models import capture_items, overview_storage_segments, storage_items

# key, display name. The order is the order in the Data Used panel.
SOURCES = (("library", "Game library"), ("storage", "Storage scans"), ("history", "Cleanup history"),
           ("mods", "Mods inventory"), ("captures", "Captures index"))
SOURCE_NAMES = dict(SOURCES)
SOURCE_KEY = "assistant_sources"
DEFAULT_ENABLED = tuple(key for key, _ in SOURCES)


@dataclass(frozen=True)
class Facts:
    games: tuple = ()
    storage: tuple = ()
    segments: tuple = ()
    captures: tuple = ()
    mods: tuple = ()
    old_files: tuple = ()
    history: tuple = ()
    scanned_at: str = ""
    enabled: frozenset = frozenset(DEFAULT_ENABLED)
    now: float = 0.0
    scope: str = ""  # a game key, or "" for every game
    saves: tuple = ()      # save folders the save scanner labeled (part of the storage scan)
    hardware: object = None  # hardware_core.Specs once Windows has reported the parts, else None

    def on(self, key):
        return key in self.enabled


@dataclass(frozen=True)
class SourceState:
    key: str
    name: str
    count: int
    detail: str
    enabled: bool


def enabled_sources(settings):
    """Sources the owner turned on. A missing or damaged setting means all of them."""
    value = settings.get(SOURCE_KEY) if isinstance(settings, dict) else None
    if not isinstance(value, list):
        return frozenset(DEFAULT_ENABLED)
    return frozenset(v for v in value if v in SOURCE_NAMES)


def with_sources(settings, keys):
    ordered = [key for key, _ in SOURCES if key in set(keys)]
    return dict(settings, **{SOURCE_KEY: ordered})


def build_facts(inventory, records=(), events=(), *, enabled=None, now=None, scope="", hardware=None):
    now = float(now if now is not None else datetime.now().timestamp())
    try:
        history = tuple(undo_data.build_entries(list(records), list(events)))
    except Exception:  # a damaged history file must not stop the assistant
        history = ()
    return Facts(
        games=tuple(inventory.games), storage=tuple(storage_items(inventory)),
        segments=tuple(overview_storage_segments(inventory)), captures=tuple(capture_items(inventory)),
        mods=tuple(inventory.mods), old_files=tuple(inventory.files), history=history,
        scanned_at=str(inventory.scanned_at or ""),
        enabled=frozenset(DEFAULT_ENABLED if enabled is None else enabled), now=now, scope=scope or "",
        saves=tuple(getattr(inventory, "saves", None) or ()), hardware=hardware)


def _launchers(games):
    return len({p for g in games for p in g.claimed_by}) or (1 if games else 0)


def source_states(facts):
    """What each source holds, whether or not it is switched on."""
    games, storage = facts.games, len(facts.storage) + len(facts.old_files)
    scan = ("Full scan, " + facts.scanned_at) if facts.scanned_at else "Not scanned yet"
    rows = (
        ("library", len(games), f"{len(games):,} games, {_launchers(games)} launchers" if games else "No games found yet"),
        ("storage", storage, f"{storage:,} items, {scan}" if storage else "Nothing scanned yet"),
        ("history", len(facts.history), f"{len(facts.history):,} records" if facts.history else "Nothing recorded yet"),
        ("mods", len(facts.mods), f"{len(facts.mods):,} mod locations" if facts.mods else "Nothing scanned yet"),
        ("captures", len(facts.captures), f"{len(facts.captures):,} captures" if facts.captures else "Nothing scanned yet"),
    )
    return [SourceState(key, SOURCE_NAMES[key], count, detail, key in facts.enabled) for key, count, detail in rows]


def when_text(stamp, now):
    """'2h ago' style text for a "YYYY-MM-DD HH:MM" scan stamp."""
    try:
        seconds = max(0, now - datetime.strptime(stamp, "%Y-%m-%d %H:%M").timestamp())
    except (TypeError, ValueError):
        return "Not scanned"
    if seconds < 90:
        return "Just now"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    return f"{int(seconds // 86400)}d ago"


def metrics(facts, conversations):
    states = source_states(facts)
    items = len(facts.old_files) + len(facts.captures) + len(facts.mods) + len(facts.storage)
    return {
        "conversations": conversations,
        "games": len(facts.games),
        "items": items,
        "scan": when_text(facts.scanned_at, facts.now) if facts.scanned_at else "No scan yet",
        "sources_on": sum(1 for s in states if s.enabled),
        "sources_total": len(states),
    }


def find_game(facts, key):
    return next((g for g in facts.games if g.key == key), None)
