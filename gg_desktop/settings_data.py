"""Settings tab data: the preferences it owns, validation, export, import and reset.

Nothing here touches a file except what the caller passes to core.save_settings. Reset and import never remove a
Never Touch rule, so protection can only grow through them.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import core

APP_FORMAT = 1
MAX_FOLDERS = 30
MAX_NEVER_TOUCH = 200
MAX_PATH = 4096
FILE_DAYS = (30, 90, 180, 365, 730)
GRAVE_DAYS = (90, 180, 365, 730)
SCALES = (100, 110, 125, 150)        # interface size in percent; 100 is the approved native layout

# Preferences the Settings tab owns, with their defaults. Reset puts exactly these back.
OWNED = {
    "start_minimized": False,
    "scan_on_launch": False,
    "files_stale_days": 180,
    "graveyard_days": 365,
    "excluded_folders": [],
    "steam_artwork_downloads": True,
    "assistant_enabled": False,   # the AI Assistant tab is optional and starts switched off
    "check_updates_on_launch": False,   # one question to GitHub when the app starts; off until the owner turns it on
    "soulbind_new_games": False,        # apply the Soulbind profile to newly installed games; off until switched on
    "interface_scale": 100,             # whole-window size in percent; used the next time the app starts
    "welcome_at_startup": True,         # the welcome tour opens when Game Grave starts until the owner turns it off
}
LIBRARY_KEYS = ("steam_extra_roots", "other_library_roots", "mod_extra_roots", "screenshot_roots", "recording_roots")
LIBRARY_NAMES = {"steam_extra_roots": "Steam libraries", "other_library_roots": "Other / Xbox libraries",
                 "mod_extra_roots": "Mod locations", "screenshot_roots": "Screenshot folders",
                 "recording_roots": "Recording folders"}
EXPORT_KEYS = tuple(OWNED) + LIBRARY_KEYS + ("scan_folder", "never_touch")


def _path_ok(value):
    return type(value) is str and 0 < len(value) <= MAX_PATH and "\0" not in value and Path(value).is_absolute()


def clean_folders(values, limit=MAX_FOLDERS):
    seen, out = set(), []
    for value in values if isinstance(values, list) else []:
        if not _path_ok(value):
            continue
        key = os.path.normcase(os.path.normpath(value))
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
        if len(out) >= limit:
            break
    return out


def pick_days(value, choices, default):
    return value if type(value) is int and value in choices else default


def current(settings):
    """The owned preferences as the saved settings hold them, repaired to valid values."""
    return {
        "start_minimized": settings.get("start_minimized") is True,
        "scan_on_launch": settings.get("scan_on_launch") is True,
        "files_stale_days": pick_days(settings.get("files_stale_days"), FILE_DAYS, 180),
        "graveyard_days": pick_days(settings.get("graveyard_days"), GRAVE_DAYS, 365),
        "excluded_folders": clean_folders(settings.get("excluded_folders", [])),
        "steam_artwork_downloads": settings.get("steam_artwork_downloads", True) is not False,
        "assistant_enabled": settings.get("assistant_enabled") is True,
        "check_updates_on_launch": settings.get("check_updates_on_launch") is True,
        "soulbind_new_games": settings.get("soulbind_new_games") is True,
        "interface_scale": pick_days(settings.get("interface_scale"), SCALES, 100),
        "welcome_at_startup": settings.get("welcome_at_startup", True) is not False,
    }


def scale_factor(settings):
    """The Qt scale factor for a saved interface size, as text, or None for the native 100%."""
    percent = pick_days(settings.get("interface_scale") if isinstance(settings, dict) else None, SCALES, 100)
    return None if percent == 100 else f"{percent / 100:.2f}"


def defaults():
    return {key: (list(value) if isinstance(value, list) else value) for key, value in OWNED.items()}


def changed(saved, pending):
    return [key for key in OWNED if saved.get(key) != pending.get(key)]


def apply(settings, pending):
    """Settings with the pending preferences written in. Everything else is carried over unchanged."""
    values = current(pending)
    return dict(settings, **values)


def exclusion_problem(path, existing):
    """Why this folder cannot be excluded, or an empty string when it can."""
    target = Path(path)
    if not target.is_absolute() or not target.is_dir():
        return "Choose an existing folder on this PC."
    if target == Path(target.anchor):
        return "A whole drive cannot be excluded. Choose a folder."
    if core._has_reparse_component(target):
        return "That folder is a link or redirect. Choose the real folder."
    if len(existing) >= MAX_FOLDERS:
        return f"At most {MAX_FOLDERS} folders can be excluded."
    key = os.path.normcase(os.path.normpath(str(target)))
    if any(os.path.normcase(os.path.normpath(e)) == key for e in existing):
        return "That folder is already excluded."
    return ""


# ---------------------------------------------------------------- export and import
def export_text(settings):
    payload = {"app": "Game Grave", "format": APP_FORMAT,
               "settings": {key: settings[key] for key in EXPORT_KEYS if key in settings}}
    return json.dumps(payload, indent=2, ensure_ascii=False)


class ImportReport:
    def __init__(self, settings, notes, counts):
        self.settings, self.notes, self.counts = settings, notes, counts


def import_settings(raw: bytes, settings) -> ImportReport:
    """Validate a settings export. Raises ValueError when the file is not a Game Grave export."""
    if len(raw) > core.MAX_SETTINGS_BYTES:
        raise ValueError("That file is too large to be a Game Grave settings export.")
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=core._settings_no_duplicate_keys)
    except (ValueError, UnicodeError):
        raise ValueError("That file is not valid Game Grave settings.") from None
    if (not isinstance(data, dict) or data.get("app") != "Game Grave" or data.get("format") != APP_FORMAT
            or not isinstance(data.get("settings"), dict)):
        raise ValueError("That file is not a Game Grave settings export.")
    incoming = data["settings"]
    updated = dict(settings)
    notes, counts = [], {}
    prefs = current(dict(settings, **{k: incoming[k] for k in OWNED if k in incoming}))
    for key, value in prefs.items():
        if key in incoming and key != "excluded_folders" and updated.get(key) != value:
            counts[key] = value
        updated[key] = value
    folders = clean_folders(incoming.get("excluded_folders", []))
    updated["excluded_folders"] = [f for f in folders if os.path.isdir(f)]
    skipped = len(folders) - len(updated["excluded_folders"])
    for key in LIBRARY_KEYS:
        found = clean_folders(incoming.get(key, []))
        usable = [f for f in found if os.path.isdir(f) and not core._has_reparse_component(Path(f))
                  and (key != "steam_extra_roots" or os.path.isdir(os.path.join(f, "steamapps")))]
        skipped += len(found) - len(usable)
        merged = clean_folders([*updated.get(key, []), *usable])
        if len(merged) != len(updated.get(key, [])):
            counts[key] = len(merged) - len(updated.get(key, []))
        updated[key] = merged
    folder = incoming.get("scan_folder")
    if _path_ok(folder):
        target = Path(folder)
        if target.is_dir() and core.safe_scan_root(target) and not core.is_protected_path(target, []):
            updated["scan_folder"] = folder
        else:
            skipped += 1
    rules = [r for r in incoming.get("never_touch", []) if _path_ok(r)] if isinstance(incoming.get("never_touch"), list) else []
    existing = list(settings.get("never_touch", []))
    have = {os.path.normcase(os.path.normpath(r)) for r in existing}
    added = [r for r in rules if os.path.normcase(os.path.normpath(r)) not in have][:MAX_NEVER_TOUCH]
    if added:
        updated["never_touch"] = [*existing, *dict.fromkeys(added)]
        counts["never_touch"] = len(added)
    if skipped:
        notes.append(f"{skipped} folder(s) in the file were skipped because they are missing or not allowed on this PC.")
    notes.append("Personal Never Touch rules were only added, never removed.")
    return ImportReport(updated, notes, counts)
