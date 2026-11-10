"""Pure facts for the Mods gallery: which card says what, which rows need attention, the numbers on the banner.

Nothing here touches Qt, a file, the network or a mod manager. The screen layer reads what the Mods tab already knows
(saved profile status, the manager's own recorded update, the conflict check) and hands it over as `Facts`. A value the
tab does not know stays None and is shown as not checked, never guessed. Nothing is called safe.
"""
from __future__ import annotations

from dataclasses import dataclass

TONES = ("green", "amber", "red", "muted")
STATUS_WORDS = {"On": "green", "Off": "muted", "On in some": "amber", "Not recorded": "muted", "Storage folder": "muted"}
ALL_GAMES = "All Games"
ATTENTION_LIMIT = 30
RECENT_LIMIT = 20


@dataclass(frozen=True)
class Facts:
    """What the Mods tab knows about one row. `outdated` and `conflicts` are None when that check has not run."""
    index: int                      # row position on the current page of the Library table
    key: str                        # stable id (the folder path)
    name: str
    game: str
    manager: str
    version: str = ""
    size: int | None = None
    word: str = "Not recorded"      # On, Off, On in some, Not recorded, Storage folder
    outdated: bool | None = None
    newest: str = ""
    conflicts: int | None = None
    partners: tuple[str, ...] = ()  # names of the other mods that share files with this one
    modified: int | None = None
    is_mod: bool = False            # an individual mod, not a whole storage folder


@dataclass(frozen=True)
class Card:
    facts: Facts
    label: str
    tone: str
    note: str
    action: str                     # "" | "Review" | "Details"
    version_text: str


def known_version(version: str) -> str:
    text = str(version or "").strip()
    return "" if text.casefold() in {"", "unknown", "none", "n/a", "-", "—"} else text


def status_of(f: Facts) -> tuple[str, str]:
    """The pill: a conflict outranks an update, an update outranks the saved on/off state."""
    if f.conflicts:
        return "Conflict", "red"
    if f.outdated:
        return "Update ready", "amber"
    return f.word, STATUS_WORDS.get(f.word, "muted")


def partner_text(partners: tuple[str, ...]) -> str:
    names = [p for p in partners if p]
    if not names:
        return "Shares files with another mod"
    if len(names) == 1:
        return f"Shares files with {names[0]}"
    if len(names) == 2:
        return f"Shares files with {names[0]} and {names[1]}"
    return f"Shares files with {names[0]}, {names[1]} and {len(names) - 2} more"


def note_for(f: Facts) -> str:
    if f.conflicts:
        return partner_text(f.partners)
    if f.outdated:
        newest = known_version(f.newest)
        return f"Your mod manager lists {newest} as newer" if newest else "Your mod manager lists a newer version"
    return {
        "On": "Turned on in your mod manager",
        "Off": "Turned off in your mod manager",
        "On in some": "On in some saved profiles, off in others",
        "Storage folder": "A folder where a mod manager keeps its mods",
    }.get(f.word, "Your mod manager has not saved whether it is on")


def action_for(f: Facts) -> str:
    """Game Grave never installs or changes a mod, so a flagged card offers a look, not a fix."""
    if f.conflicts:
        return "Review"
    if f.outdated:
        return "Details"
    return ""


def version_text(f: Facts) -> str:
    installed, newest = known_version(f.version), known_version(f.newest)
    if f.outdated and installed and newest:
        return f"{installed} → {newest}"
    return installed


def card(f: Facts) -> Card:
    label, tone = status_of(f)
    return Card(f, label, tone, note_for(f), action_for(f), version_text(f))


def cards(facts) -> list[Card]:
    return [card(f) for f in facts]


def needs_attention(items) -> list[Card]:
    """Conflicts first, then updates, each in the order the table already shows them."""
    flagged = [c for c in items if c.action]
    flagged.sort(key=lambda c: 0 if c.tone == "red" else 1)
    return flagged[:ATTENTION_LIMIT]


def recently_changed(items) -> list[Card]:
    """Newest folder change first. Rows that need attention are in their own row, so they are left out here."""
    dated = [c for c in items if not c.action and c.facts.modified]
    dated.sort(key=lambda c: -int(c.facts.modified))
    return dated[:RECENT_LIMIT]


def health(facts) -> dict:
    """Counts for one game. `outdated` and `conflicts` are None until those checks have produced an answer."""
    rows = list(facts)
    mods = [f for f in rows if f.is_mod]
    out = {
        "count": len(rows),
        "on": sum(f.word == "On" for f in mods),
        "off": sum(f.word == "Off" for f in mods),
        "unrecorded": sum(f.word not in ("On", "Off") for f in mods),
        "folders": len(rows) - len(mods),
        "outdated": None,
        "conflicts": None,
    }
    if any(f.outdated is not None for f in mods):
        out["outdated"] = sum(bool(f.outdated) for f in mods)
    if any(f.conflicts is not None for f in mods):
        out["conflicts"] = sum(bool(f.conflicts) for f in mods)
    return out


def bar_parts(h: dict):
    """Shares for the thin bar under the banner: (on, outdated, conflict, off, not recorded) as fractions of the mods."""
    on, off, rest = h["on"], h["off"], h["unrecorded"]
    total = on + off + rest
    if not total:
        return None
    outdated = min(on, h["outdated"] or 0)
    conflict = min(on - outdated, h["conflicts"] or 0)
    parts = (on - outdated - conflict, outdated, conflict, off, rest)
    return tuple(p / total for p in parts)


@dataclass(frozen=True)
class Tile:
    name: str
    count: int          # individual mods
    flagged: int        # mods with a conflict or a recorded update
    folders: int = 0    # mod storage folders (a folder can hold many mods, so it is never counted as one)


def count_noun(count: int, folders: int) -> str:
    """The words under a poster: mods when there are any, else the folders, never the two added together."""
    if count:
        return f"{count} mod" + ("" if count == 1 else "s")
    if folders:
        return f"{folders} folder" + ("" if folders == 1 else "s")
    return "No mods"


def tiles(all_facts) -> list[Tile]:
    """One poster per game plus All Games, the game with the most mods first."""
    by_game: dict[str, list[Facts]] = {}
    for f in all_facts:
        by_game.setdefault(f.game, []).append(f)

    def make(name, rows):
        mods = [f for f in rows if f.is_mod]
        return Tile(name, len(mods), sum(bool(f.conflicts) or bool(f.outdated) for f in mods), len(rows) - len(mods))

    ordered = sorted(((n, make(n, r)) for n, r in by_game.items()),
                     key=lambda kv: (-kv[1].count, -kv[1].folders, kv[0].casefold()))
    return [make(ALL_GAMES, list(all_facts))] + [t for _n, t in ordered]


def managers_text(facts) -> str:
    names = sorted({f.manager for f in facts if f.manager})
    if not names:
        return ""
    return names[0] if len(names) == 1 else ", ".join(names[:2]) + (f" and {len(names) - 2} more" if len(names) > 2 else "")


def count_text(value, none_text="Not checked") -> str:
    return none_text if value is None else str(value)
