"""Qt-free Graveyard model: one list of reviewable leftovers from evidence Game Grave already has.

Sources are the engine's own Graveyard entries (neglected installed games, old archives, recordings,
screenshots, mod folders, files you sent for review) and, when you ask for it, the read-only Other Storage
scan (configs, caches, logs, temporary files and orphaned Steam shader caches). Nothing here reads file
contents, changes anything or claims that an item is unused or safe to remove. Age is a signal only.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import time

from core import is_protected_path
from gg_desktop.other_storage_data import StorageEntry

TABS = ("All Items", "Games", "Mods", "Downloads", "Configs", "Leftovers", "Orphans")
TYPES = ("Game Files / Installs", "Mods / Addons", "Possible Downloads", "Cache / Shader Cache",
         "Configs / Settings", "Screenshots / Recordings", "Other Leftovers")
EVIDENCE = ("Direct", "Location", "Name hint", "Age only", "Yours")
EVIDENCE_TEXT = {
    "Direct": "Backed by a Steam record Game Grave read.",
    "Location": "Found in a known game-related location. Location does not show it is unused.",
    "Name hint": "Only the file name resembles gaming content.",
    "Age only": "Only its age points here. Age does not show it is unused.",
    "Yours": "You sent this here for review.",
}
STEAM_KIND = "Neglected installed game"


@dataclass(eq=False)
class GraveItem:
    key: str
    name: str
    path: str
    tab: str
    kind: str          # one of TYPES
    category: str
    related: str
    game: str          # a game name only when Steam proves the link, otherwise ""
    size: int
    items: int | None
    modified: float | None
    age_days: int | None
    evidence: str
    why: str
    note: str = ""
    app_id: str = ""
    entry: object = None      # GraveyardEntry from the protected engine
    storage: object = None    # StorageEntry from the Other Storage scan
    partial: bool = False

    @property
    def folder(self):
        return str(Path(self.path).parent)

    @property
    def is_folder_item(self):
        return self.entry is None or self.entry.old_file is None

    @property
    def subtitle(self):
        return self.category


def classify_entry(entry):
    category = entry.category
    if category == STEAM_KIND:
        return "Games", TYPES[0], "Direct"
    if category == "Possible mod / game download":
        return "Downloads", TYPES[2], "Name hint"
    if category in ("Old game recording", "Old game screenshot"):
        return "Leftovers", TYPES[5], "Location"
    if category == "Manual review":
        return "Leftovers", TYPES[6], "Yours"
    return "Mods", TYPES[1], "Age only"


def classify_storage(entry):
    if entry.kind == "steam-shader" and entry.related == "No installed game":
        return "Orphans", TYPES[3], "Direct"
    if entry.category == "Config / Settings":
        return "Configs", TYPES[4], "Location"
    if entry.category in ("Shader Cache", "Caches"):
        return "Leftovers", TYPES[3], "Direct" if entry.app_id else "Location"
    return "Leftovers", TYPES[6], "Location"


def _age(modified, now):
    return None if modified is None else max(0, int((now - modified) / 86400))


def from_graveyard(entries, now=None):
    now = time.time() if now is None else now
    output = []
    for e in entries:
        tab, kind, evidence = classify_entry(e)
        modified = e.old_file.modified if e.old_file is not None else (
            None if e.age_days is None else now - e.age_days * 86400)
        game = e.name if e.category == STEAM_KIND else ""
        app_id = e.key.split(":", 1)[1] if e.key.startswith("steam:") else ""
        output.append(GraveItem(
            key=e.key, name=e.name, path=e.path, tab=tab, kind=kind, category=e.category,
            related=e.relationship, game=game, size=max(0, e.apparent_bytes),
            items=1 if e.old_file is not None else None, modified=modified, age_days=e.age_days,
            evidence=evidence, why=e.finding, app_id=app_id if app_id.isdecimal() else "", entry=e))
    return output


def from_storage(entries, now=None):
    now = time.time() if now is None else now
    output = []
    for e in entries:
        tab, kind, evidence = classify_storage(e)
        game = e.related if e.app_id else ""
        why = e.evidence
        if e.newest is not None:
            why += f" Newest file changed {_age(e.newest, now):,} days ago."
        output.append(GraveItem(
            key="storage:" + e.key, name=e.name, path=e.path, tab=tab, kind=kind, category=e.category,
            related=e.related, game=game, size=max(0, e.size), items=e.items, modified=e.newest,
            age_days=_age(e.newest, now), evidence=evidence, why=why, note=e.note, app_id=e.app_id,
            storage=e, partial=e.partial))
    return output


def merge(graveyard_items, storage_items):
    """Engine entries first; a scanned folder is dropped when an engine entry already has the same path."""
    seen = {os.path.normcase(os.path.abspath(i.path)) for i in graveyard_items}
    output = list(graveyard_items)
    for item in storage_items:
        if os.path.normcase(os.path.abspath(item.path)) not in seen:
            output.append(item)
    return output


def discover_leftovers(settings, games, canceled, progress):
    """Read-only Other Storage scan. Returns a StorageReport."""
    from core import _steam_roots, steam_libraries
    from gg_desktop import other_storage_data as storage
    try:
        roots = _steam_roots(list(settings.get("steam_extra_roots", [])))
        libraries = steam_libraries(roots)
    except (OSError, ValueError):
        roots, libraries = [], []
    return storage.discover(steam_roots=roots, libraries=libraries, games=games, canceled=canceled,
                            progress=progress)


def is_protected(item, never_touch):
    if item.storage is not None and item.storage.protected_kind:
        return True
    return is_protected_path(Path(item.path), never_touch)
