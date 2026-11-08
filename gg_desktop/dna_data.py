"""Qt-free Game DNA model: one game's storage, shown only where the data proves the link.

What counts as proof:
  * the game's install folder (a Steam manifest or launcher record Game Grave read),
  * mods inside that folder or recorded by the Steam Workshop scanner with the game's app ID,
  * Steam's shader cache folder named for the game's app ID,
  * screenshots in Steam's own per-app screenshot folder,
  * folders YOU link to the game (evidence "Yours").
Saves, configs and recordings are never matched by name. A save folder whose name resembles the game is only a
suggestion until you link it. Nothing here reads file contents or removes anything.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import time

from gg_desktop.models import _path_key

CATEGORIES = ("Game Install", "Mods / Addons", "Caches", "Saves", "Screenshots", "Recordings",
              "Configs / Settings", "Other")
COLORS = {"Game Install": "#ff2346", "Mods / Addons": "#c562e6", "Caches": "#16c9eb", "Saves": "#27dc74",
          "Screenshots": "#f7b737", "Recordings": "#ff8a3d", "Configs / Settings": "#7a8cff", "Other": "#9ca8bd"}
LINK_CATEGORIES = CATEGORIES[1:]
TABS = (("Storage DNA", "box"), ("Files & Locations", "folder"), ("Saves", "archive"), ("Mods & Addons", "mods"),
        ("Caches", "storage"), ("Config / Settings", "settings"), ("Screenshots", "camera"), ("Recordings", "play"))
TAB_CATEGORY = {"Saves": "Saves", "Mods & Addons": "Mods / Addons", "Caches": "Caches",
                "Config / Settings": "Configs / Settings", "Screenshots": "Screenshots", "Recordings": "Recordings"}
EMPTY = {
    "Saves": "No save folder is linked to this game. Saves are never matched by name. Link a folder you know is this game's saves.",
    "Mods & Addons": "No mod or addon location is proven for this game by its install folder or Steam Workshop ID.",
    "Caches": "No Steam shader cache folder named for this game's app ID was found.",
    "Config / Settings": "No config or settings folder is linked to this game. Link the folder yourself; it is never guessed.",
    "Screenshots": "No screenshots were proven for this game by Steam's per-game screenshot folders.",
    "Recordings": "No recordings are linked to this game. Recordings are only tied to a game when you link a folder.",
}
EVIDENCE_TEXT = {
    "Direct": "Backed by a record or app ID that Game Grave read.",
    "Location": "Found inside the game's recorded install folder.",
    "Yours": "You linked this folder to the game.",
    "Name hint": "Only the name resembles the game. Not linked.",
}
MAX_LINKS_PER_GAME = 20
MAX_LINKED_GAMES = 300
STEAM_CAPTURE_SOURCE = "Steam capture path / app ID"
DAY = 86400


@dataclass(eq=False)
class Location:
    key: str
    label: str
    path: str
    category: str
    size: int | None
    items: int | None
    newest: float | None
    evidence: str
    why: str
    source: str             # install | mod | cache | capture | link
    nested: bool = False    # lies inside the install folder, so its bytes are already in the install size
    partial: bool = False
    measured: bool = False

    @property
    def sort_size(self):
        return -1 if self.size is None else self.size


@dataclass(eq=False)
class Suggestion:
    key: str
    title: str
    detail: str
    size: int | None
    route: str              # the locked tab that owns removal: Other Storage, Captures, Graveyard
    search: str             # text to put in that tab's search box
    pending_key: str = ""   # exact item key when the owning tab can focus it


@dataclass(eq=False)
class Hint:
    path: str
    name: str
    why: str
    kind: str


@dataclass(eq=False)
class Profile:
    game: object
    locations: list = field(default_factory=list)
    hints: list = field(default_factory=list)
    suggestions: list = field(default_factory=list)
    analyzed: bool = False
    created: float | None = None
    unmeasured: int = 0

    @property
    def install(self):
        return next((l for l in self.locations if l.source == "install"), None)

    def of(self, category):
        return [l for l in self.locations if l.category == category]


def _within(path, root):
    path, root = _path_key(path).rstrip("\\"), _path_key(root).rstrip("\\")
    return bool(root) and (path == root or path.startswith(root + "\\"))


def _timestamp(value):
    return value if isinstance(value, (int, float)) and value > 0 else None


def steam_record(game, steam):
    """The scanner's Steam record for an inventory game, by app ID. Returns None when there is none."""
    app = str(getattr(game, "app_id", "") or "")
    if not app.isdecimal() or getattr(game, "launcher", "") != "Steam":
        return None
    return next((s for s in steam if str(getattr(s, "app_id", "")) == app), None)


def cache_candidates(game, steam):
    """(label, path, category, why) for folders whose NAME is the game's app ID. Existence is checked by the caller."""
    record = steam_record(game, steam)
    if record is None or not getattr(record, "library", ""):
        return []
    app = str(record.app_id)
    base = Path(record.library) / "steamapps"
    return [("Steam shader cache", str(base / "shadercache" / app), "Caches",
             f"Steam shader cache folder named for app ID {app}, inside the same Steam library as the game.")]


def aggregate(prefix, items):
    """One summary row for many proven files in the same group (size, count, newest, the folder they share)."""
    paths = [str(i.path) for i in items]
    folder = os.path.commonpath(paths) if len(paths) > 1 else os.path.dirname(paths[0])
    if folder in paths:
        folder = os.path.dirname(folder)
    size = sum(max(0, int(i.size)) for i in items)
    newest = max((i.modified for i in items if _timestamp(i.modified)), default=None)
    return folder, size, len(items), newest


def build_profile(game, *, assets=(), steam=(), captures=(), saves=(), links=(), graveyard=(), analysis=None,
                  exists=lambda path: os.path.isdir(path), now=None):
    """Everything provable about one game. `analysis` maps path keys to Measure (see dna_actions.analyze)."""
    analysis = analysis or {}
    now = time.time() if now is None else now
    profile = Profile(game, analyzed=bool(analysis))
    install = str(game.install_path)
    measured = analysis.get(_path_key(install)) if install else None
    profile.created = analysis.get("created:" + _path_key(install)) if install else None
    size = measured.bytes if measured else game.size_bytes
    profile.locations.append(Location(
        "install", "Game install folder", install, "Game Install", size,
        measured.files if measured else None, measured.newest if measured else None, "Direct",
        game.install_evidence or "Recorded by the launcher.", "install", partial=bool(measured and measured.partial),
        measured=bool(measured)))
    seen = {_path_key(install)}

    def add(loc):
        key = _path_key(loc.path)
        if key in seen:
            return
        seen.add(key)
        loc.nested = _within(loc.path, install)
        found = analysis.get(key)
        if found is not None:
            loc.size, loc.items, loc.newest, loc.partial, loc.measured = found.bytes, found.files, found.newest, found.partial, True
        profile.locations.append(loc)

    for asset in assets:
        within = "Within recorded" in str(asset.get("evidence", ""))
        add(Location("mod:" + asset["path"], os.path.basename(asset["path"].rstrip("\\/")) or asset["path"], asset["path"],
                     "Mods / Addons", max(0, int(asset.get("apparent_bytes", 0))), None, None,
                     "Location" if within else "Direct", str(asset.get("evidence", "")), "mod"))
    for label, path, category, why in cache_candidates(game, steam):
        if exists(path):
            add(Location("cache:" + path, label, path, category, None, None, None, "Direct", why, "cache"))
    for kind in ("Screenshots", "Recordings"):
        proven = [c for c in captures if c.game == game.name and c.kind == kind and c.source == STEAM_CAPTURE_SOURCE]
        if proven:
            folder, total, count, newest = aggregate(kind, [c.record for c in proven])
            profile.locations.append(Location(
                "capture:" + kind, f"Steam {kind.lower()}", folder, kind, total, count, newest, "Direct",
                f"{count:,} {kind.lower()} in Steam's per-game folder for app ID {game.app_id}.", "capture",
                nested=_within(folder, install), measured=True))
            seen.add(_path_key(folder))
    for link in links:
        add(Location("link:" + link["path"], os.path.basename(link["path"].rstrip("\\/")) or link["path"], link["path"],
                     link["category"], None, None, None, "Yours", "You linked this folder to the game.", "link"))
    linked = {_path_key(l.path) for l in profile.locations}
    profile.unmeasured = sum(1 for l in profile.locations if l.size is None)
    profile.hints = hints_for(game, saves, linked)
    profile.suggestions = suggestions_for(profile, graveyard, now)
    return profile


def hints_for(game, saves, linked):
    """Save locations whose recorded game name or folder name matches. A suggestion only, never counted."""
    name = str(game.name).strip().casefold()
    if len(name) < 4:
        return []
    output = []
    for item in saves:
        path = str(getattr(item, "path", "") or "")
        if not path or _path_key(path) in linked:
            continue
        hint = str(getattr(item, "game", "") or "").strip().casefold()
        parts = {p.casefold() for p in Path(path).parts}
        if hint == name or name in parts:
            output.append(Hint(path, os.path.basename(path.rstrip("\\/")) or path,
                               "The name resembles this game. Game Grave cannot prove it is this game's data.",
                               str(getattr(item, "kind", "Possible save/profile"))))
    return output[:20]


def suggestions_for(profile, graveyard, now):
    game = profile.game
    output = []
    for loc in profile.of("Caches"):
        if loc.source == "cache":
            output.append(Suggestion(
                loc.key, "Steam shader cache", "Steam rebuilds this when the game needs it. "
                "A first load afterwards can be slower. Removal is reviewed in Other Storage.", loc.size,
                "Other Storage", game.name))
    shots = next((l for l in profile.locations if l.source == "capture" and l.category == "Screenshots"), None)
    if shots:
        output.append(Suggestion(shots.key, f"{shots.items:,} Steam screenshots",
                                 "Screenshots are yours. Review them one by one in Captures.", shots.size, "Captures", game.name))
    app = str(getattr(game, "app_id", "") or "")
    entry = next((e for e in graveyard if getattr(e, "key", "") == "steam:" + app), None) if app else None
    if entry is not None:
        days = getattr(entry, "age_days", None)
        when = f"Steam's last-play record is {days:,} days old. " if days is not None else ""
        output.append(Suggestion(entry.key, "In your Graveyard", when + "Age alone does not show a game is unwanted. "
                                 "Uninstalling goes through Steam from the Graveyard.", None, "Graveyard", game.name,
                                 pending_key=entry.key))
    return output


# ------------------------------------------------------------------ totals
def footprint(profile):
    """(total, segments, unknown). Nested locations are carved out of the install so no byte is counted twice."""
    install = profile.install
    amounts = {}
    nested = {}
    for loc in profile.locations:
        if loc.source == "install" or loc.size is None:
            continue
        amounts[loc.category] = amounts.get(loc.category, 0) + loc.size
        if loc.nested:
            nested[loc.category] = nested.get(loc.category, 0) + loc.size
    total_nested = sum(nested.values())
    known_install = install.size if install is not None else None
    result = {}
    if known_install is not None:
        result["Game Install"] = max(0, known_install - total_nested)
    for category, value in amounts.items():
        result[category] = result.get(category, 0) + value
    segments = [(c, result[c], COLORS[c]) for c in CATEGORIES if result.get(c)]
    total = sum(result.values())
    unknown = profile.unmeasured + (1 if known_install is None else 0)
    return total, segments, unknown


def total_items(profile):
    """Sum of counted items. None when any location has not been counted yet."""
    values = []
    for loc in profile.locations:
        if loc.nested and loc.source != "install":
            continue
        if loc.items is None:
            return None
        values.append(loc.items)
    return sum(values)


def days_since(timestamp, now=None):
    if not _timestamp(timestamp):
        return None
    return max(0, int(((time.time() if now is None else now) - timestamp) / DAY))


def percent(part, total):
    return 0 if not total else part * 100.0 / total
