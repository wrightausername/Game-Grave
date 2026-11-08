"""Qt-free Game DNA actions: the read-only analysis walk, linking folders to a game, and Steam links.

Linking a folder only records your statement in settings. It never moves, renames or removes anything, and a
linked folder gets no deletion path here. Removal stays in the tab that owns it (Other Storage, Captures,
Graveyard), behind that tab's own confirmation and re-checks.
"""
from __future__ import annotations

import os
from pathlib import Path

from core import is_protected_path
from gg_desktop import dna_data as data
from gg_desktop.models import _path_key
from gg_desktop.other_storage_data import measure, normal_dir

SETTINGS_KEY = "dna_links"


def analysis_paths(profile):
    """Folders worth walking: the install, linked folders, and proven cache folders. Capture rows are already counted."""
    return [l.path for l in profile.locations
            if l.source in {"install", "link", "cache"} or (l.source == "mod" and not l.nested)]


def analyze(paths, *, canceled=lambda: False, progress=lambda text: None, created=os.stat):
    """Measure each folder (never entering links) and read the install folder's creation time. Read-only.

    Returns {path key: Measure, "created:<install key>": float}. Raises InterruptedError when canceled."""
    result = {}
    folders = [p for p in paths if p]
    for number, path in enumerate(folders, 1):
        if canceled():
            raise InterruptedError("Analysis canceled")
        progress(f"Measuring {Path(path).name or path} ({number} of {len(folders)})")
        if not normal_dir(path):
            continue
        result[_path_key(path)] = measure(path, canceled)
    if folders and normal_dir(folders[0]):
        try:
            info = created(folders[0])
            stamp = getattr(info, "st_birthtime", None) or info.st_ctime
            result["created:" + _path_key(folders[0])] = stamp
        except OSError:
            pass
    return result


def links_for(settings, game_key):
    rows = settings.get(SETTINGS_KEY, {})
    if not isinstance(rows, dict):
        return []
    output = []
    for row in rows.get(game_key, [])[:data.MAX_LINKS_PER_GAME]:
        if isinstance(row, dict) and isinstance(row.get("path"), str) and row.get("category") in data.LINK_CATEGORIES:
            output.append({"path": row["path"], "category": row["category"]})
    return output


def check_link(path, category, game, existing, never_touch=()):
    """Return an error sentence, or '' when the folder may be linked."""
    if category not in data.LINK_CATEGORIES:
        return "Choose what kind of data this folder holds."
    text = str(path).strip()
    if not text:
        return "Choose a folder."
    folder = Path(text).expanduser()
    if not folder.is_absolute():
        return "Choose a full folder path."
    if len(folder.parts) < 3:
        return "Choose a specific folder, not a drive or top-level folder."
    if not normal_dir(folder):
        return "That folder does not exist, or it is a link or redirected folder."
    key = _path_key(str(folder))
    install = _path_key(game.install_path) if game.install_path else ""
    if key == install:
        return "That is already the game's install folder."
    if install and install.startswith(key.rstrip("\\") + "\\"):
        return "That folder contains the game's install folder, so it would take in other data."
    if any(_path_key(r["path"]) == key for r in existing):
        return "That folder is already linked to this game."
    if len(existing) >= data.MAX_LINKS_PER_GAME:
        return f"A game can have {data.MAX_LINKS_PER_GAME} linked folders. Unlink one first."
    return ""


def with_link(settings, game_key, path, category):
    rows = {k: list(v) for k, v in settings.get(SETTINGS_KEY, {}).items() if isinstance(v, list)} \
        if isinstance(settings.get(SETTINGS_KEY), dict) else {}
    if game_key not in rows and len(rows) >= data.MAX_LINKED_GAMES:
        return None
    rows.setdefault(game_key, []).append({"path": str(Path(path).expanduser()), "category": category})
    return dict(settings, **{SETTINGS_KEY: rows})


def without_link(settings, game_key, path):
    rows = settings.get(SETTINGS_KEY, {})
    if not isinstance(rows, dict):
        return settings
    key = _path_key(path)
    kept = [r for r in rows.get(game_key, []) if isinstance(r, dict) and _path_key(str(r.get("path", ""))) != key]
    updated = {k: v for k, v in rows.items() if k != game_key}
    if kept:
        updated[game_key] = kept
    return dict(settings, **{SETTINGS_KEY: updated})


def protected_note(path, never_touch=()):
    """Plain-language protection state for a location, from the same rules every cleanup uses."""
    try:
        return "Protected from cleanup" if is_protected_path(Path(path), never_touch) else "Not covered by a protection rule"
    except (OSError, ValueError):
        return "Protection could not be checked"


def steam_url(game):
    app = str(getattr(game, "app_id", "") or "")
    if getattr(game, "launcher", "") == "Steam" and app.isdecimal():
        return f"steam://nav/games/details/{app}"
    return ""


def csv_rows(profile):
    header = ["Category", "Location", "Path", "Size (bytes)", "Items", "Evidence", "Source"]
    rows = [header]
    for loc in profile.locations:
        rows.append([loc.category, loc.label, loc.path, "" if loc.size is None else loc.size,
                     "" if loc.items is None else loc.items, loc.evidence, loc.why])
    return rows
