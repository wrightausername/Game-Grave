"""Read-only, on-demand MO2/Vortex profile evidence for Game Grave.

Sources:
* MO2 instance INI paths supplied by Game Grave's mod storage scanner.
* MO2 per-profile modlist.txt, with + / - / * status markers.
* Vortex's optional JSON *backup* snapshots, never its live LevelDB State.v2.

Never writes into a manager, repairs mod lists or infers deletion eligibility.
"""
from __future__ import annotations

import json
import ntpath
import os
import stat
import time
from pathlib import Path

from mod_sources import _read_ini, _resolve_mo_path

MAX_PROFILES = 50
MAX_MODS_PER_PROFILE = 3500
MAX_MO2_LIST_BYTES = 2 * 1024 * 1024
MAX_VORTEX_JSON_BYTES = 64 * 1024 * 1024
VORTEX_BACKUPS = ("manual.json", "startup.json", "hourly.json")


def _ordinary(path: Path, *, directory: bool = False) -> bool:
    """Prevent symlink / Windows junction / reparse-point traversal."""
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            return False
        return stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    except (OSError, ValueError):
        return False


def _identity(raw: str) -> str:
    """Stable comparison, including drive/casing semantics on synthetic Linux CI."""
    if not isinstance(raw, str) or not raw.strip():
        return ""
    value = raw.strip().strip('"')
    if value.startswith("@ByteArray(") and value.endswith(")"):
        value = value[len("@ByteArray("):-1]
    # Qt writes escaped backslashes in some INI versions.
    value = value.replace("\\\\", "\\")
    if not value or value in (".", ".."):
        return ""
    if len(value) > 4096:
        return ""
    if ":" in value[:3] or value.startswith("\\\\"):
        return ntpath.normcase(ntpath.normpath(value))
    try:
        return os.path.normcase(str(Path(value).resolve(strict=False)))
    except (OSError, RuntimeError, ValueError):
        return ""


def _verified_game(path: str, games=(), other_games=()) -> tuple[str, str]:
    """Exact installation root match only. Name matching is never adequate."""
    target = _identity(path)
    if not target:
        return "", ""
    matches = [
        (str(getattr(g, "name", "")), str(getattr(g, "install_path", "")))
        for g in list(games) + list(other_games)
        if _identity(str(getattr(g, "install_path", ""))) == target
    ]
    if len(matches) == 1:
        return matches[0]
    return "", ""


def _valid_mod_name(raw: str) -> bool:
    return bool(raw and len(raw) <= 200 and raw not in (".", "..")
                and "/" not in raw and "\\" not in raw
                and not any(ord(x) < 32 for x in raw))


def _read_modlist(path: Path) -> tuple[list[dict], str]:
    if not _ordinary(path):
        return [], "modlist.txt unavailable or not an ordinary file"
    if path.stat().st_size > MAX_MO2_LIST_BYTES:
        return [], "modlist.txt exceeded inspection size cap"
    try:
        contents = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        # A legacy MO2 configuration may use a system encoding.
        try:
            contents = path.read_text(encoding="cp1252")
        except (OSError, UnicodeError):
            return [], "modlist.txt could not be read"
    except OSError:
        return [], "modlist.txt could not be read"
    rows, seen = [], set()
    for line in contents.splitlines():
        if not line or line.startswith("#"):
            continue
        marker = line[0]
        if marker in "+-*":
            name = line[1:].strip()
            status = {"+": "enabled in profile", "-": "disabled in profile",
                      "*": "managed outside MO2 / base content"}[marker]
        else:
            name = line.strip()
            status = "status not explicitly marked"
        if not _valid_mod_name(name) or name.casefold() in seen:
            continue
        if name.casefold().endswith("_separator"):
            continue
        seen.add(name.casefold())
        rows.append({"name": name, "status": status, "marker": marker if marker in "+-*" else "?"})
        if len(rows) >= MAX_MODS_PER_PROFILE:
            return rows, "modlist.txt item cap reached; report incomplete"
    return rows, ""


def _mo2_roots(mods) -> list[Path]:
    roots = {}
    for mod in mods:
        if str(getattr(mod, "source", "")) != "Mod Organizer 2":
            continue
        for indicator in (getattr(mod, "indicators", ()) or ()):
            if isinstance(indicator, str) and indicator.startswith("MO2 INI: "):
                target = Path(indicator[len("MO2 INI: "):])
                roots[str(target).casefold()] = target
    return list(roots.values())[:30]


def _read_mo2_instance(ini_path: Path, games, other_games) -> tuple[list[dict], list[str]]:
    warnings = []
    if not _ordinary(ini_path):
        return [], ["MO2 instance configuration is not an ordinary readable file."]
    cfg = _read_ini(ini_path)
    if cfg is None or not cfg.has_section("Settings"):
        return [], ["MO2 configuration format could not be inspected."]
    settings = cfg["Settings"]
    ini_dir = ini_path.parent
    base = _resolve_mo_path(settings.get("base_directory", str(ini_dir)),
                            ini_dir, ini_dir)
    profiles = _resolve_mo_path(settings.get("profiles_directory", "%BASE_DIR%/profiles"),
                                base, ini_dir)
    storage = _resolve_mo_path(settings.get("mod_directory", "%BASE_DIR%/mods"),
                               base, ini_dir)
    if not _ordinary(profiles, directory=True):
        return [], ["MO2 profiles root is unavailable, moved or protected."]
    if not _ordinary(storage, directory=True):
        warnings.append("MO2 installed-mod storage is unavailable; mod existence not confirmed.")
    game_path = cfg.get("General", "gamePath", fallback="") if cfg.has_section("General") else ""
    game_title = cfg.get("General", "gameName", fallback="") if cfg.has_section("General") else ""
    selected = cfg.get("General", "selected_profile", fallback="") if cfg.has_section("General") else ""
    selected = selected.removeprefix("@ByteArray(").removesuffix(")")
    matched_name, matched_path = _verified_game(game_path, games, other_games)
    try:
        directories = sorted((p for p in profiles.iterdir() if _ordinary(p, directory=True)),
                             key=lambda p: p.name.casefold())[:MAX_PROFILES]
    except OSError:
        return [], ["Unable to list MO2 profiles."]
    rows = []
    for folder in directories:
        mod_rows, issue = _read_modlist(folder / "modlist.txt")
        if issue:
            warnings.append(f"MO2 profile {folder.name}: {issue}")
        # Existence in storage is evidence, not proof of deployment.
        if _ordinary(storage, directory=True):
            for item in mod_rows:
                if item["marker"] not in ("+", "-"):
                    item["storage"] = "not verified"
                    continue
                candidate = storage / item["name"]
                item["storage"] = ("folder present" if _ordinary(candidate, directory=True)
                                   else "not confirmed in configured mod storage")
        else:
            for item in mod_rows:
                item["storage"] = "not checked"
        rows.append({
            "manager": "Mod Organizer 2", "profile": folder.name,
            "game_hint": game_title or ini_dir.name,
            "verified_game": matched_name, "verified_install_path": matched_path,
            "manager_game_path": _identity(game_path),
            "match_evidence": ("Exact MO2 gamePath matches recorded installed game"
                               if matched_name else "Managed game location not verified against installed games"),
            "active_at_snapshot": folder.name == selected if selected else None,
            "source": str(folder / "modlist.txt"),
            "snapshot_epoch": None, "stale": False,
            "mods": mod_rows,
            "incomplete": bool(issue),
            "protected": True,
            "note": "MO2 profile records describe saved configuration, not proof that a mod is loaded in-game.",
        })
    return rows, warnings


def _vortex_roots(mods) -> list[Path]:
    roots = {}
    for mod in mods:
        if str(getattr(mod, "source", "")) != "Vortex":
            continue
        p = Path(str(getattr(mod, "path", "")))
        if p.name and len(p.parents) >= 2:
            # Standard staging <Vortex>/<game-id>/mods or downloads/<game-id>
            parent = p.parent.parent
            if parent.name.casefold() == "vortex" and _ordinary(parent, directory=True):
                roots[str(parent).casefold()] = parent
    for variable in ("APPDATA", "PROGRAMDATA"):
        raw = os.environ.get(variable)
        if raw:
            p = Path(raw) / "Vortex"
            if _ordinary(p, directory=True):
                roots[str(p).casefold()] = p
    return list(roots.values())[:8]


def _latest_backup(root: Path) -> Path | None:
    directory = root / "temp" / "state_backups_full"
    if not _ordinary(directory, directory=True):
        return None
    choices = []
    for name in VORTEX_BACKUPS:
        path = directory / name
        if _ordinary(path):
            try:
                size = path.stat().st_size
                if 0 < size <= MAX_VORTEX_JSON_BYTES:
                    choices.append(path)
            except OSError:
                pass
    return max(choices, key=lambda p: p.stat().st_mtime) if choices else None


def _read_vortex_backup(path: Path, games, other_games) -> tuple[list[dict], list[str]]:
    warnings = []
    if not _ordinary(path):
        return [], ["Vortex backup is not an ordinary file."]
    try:
        if path.stat().st_size > MAX_VORTEX_JSON_BYTES:
            return [], ["Vortex snapshot exceeded inspection size cap."]
        state = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, ValueError, TypeError):
        return [], ["Vortex backup is missing or invalid JSON."]
    if not isinstance(state, dict):
        return [], ["Vortex backup has an unsupported structure."]
    persistent = state.get("persistent", state)
    if not isinstance(persistent, dict):
        return [], ["Vortex persistent state is unavailable in this snapshot."]
    profiles = persistent.get("profiles", {})
    mods = persistent.get("mods", {})
    settings = state.get("settings", {})
    if not isinstance(profiles, dict) or not isinstance(mods, dict):
        return [], ["Vortex backup does not include recognized profile/mod objects."]
    if not isinstance(settings, dict):
        settings = {}
    discovered = settings.get("gameMode", {})
    discovered = discovered.get("discovered", {}) if isinstance(discovered, dict) else {}
    discovered = discovered if isinstance(discovered, dict) else {}
    profile_settings = settings.get("profiles", {})
    active_id = (profile_settings.get("activeProfileId")
                 if isinstance(profile_settings, dict) else None)
    timestamp = path.stat().st_mtime
    stale = timestamp < time.time() - 7 * 86400
    if stale:
        warnings.append("Vortex backup is older than seven days; profile states may have changed.")
    out = []
    for profile_id, obj in list(profiles.items())[:MAX_PROFILES]:
        if not isinstance(obj, dict):
            continue
        game_id = obj.get("gameId")
        if not isinstance(game_id, str) or not game_id:
            continue
        data = mods.get(game_id, {})
        if not isinstance(data, dict):
            data = {}
        mod_state = obj.get("modState", {})
        if not isinstance(mod_state, dict):
            mod_state = {}
        game_entry = discovered.get(game_id, {})
        game_path = (game_entry.get("path", "") if isinstance(game_entry, dict) else "")
        matched_name, matched_path = _verified_game(game_path, games, other_games)
        entries = []
        for mod_id, mod_data in list(data.items())[:MAX_MODS_PER_PROFILE]:
            if not isinstance(mod_data, dict):
                continue
            attrs = mod_data.get("attributes", {})
            attrs = attrs if isinstance(attrs, dict) else {}
            label = attrs.get("modName") or attrs.get("name") or mod_data.get("id") or str(mod_id)
            if not isinstance(label, str):
                label = str(mod_id)
            mod_profile_state = mod_state.get(mod_id, {})
            enabled = (mod_profile_state.get("enabled") if isinstance(mod_profile_state, dict) else None)
            status = ("enabled in saved profile" if enabled is True else
                      "disabled in saved profile" if enabled is False else
                      "profile status not recorded")
            entries.append({
                "name": label[:200], "status": status, "marker": "+" if enabled is True else
                "-" if enabled is False else "?", "storage": "not verified",
            })
        out.append({
            "manager": "Vortex", "profile": str(obj.get("name") or profile_id)[:140],
            "game_hint": game_id, "verified_game": matched_name,
            "verified_install_path": matched_path,
            "manager_game_path": _identity(game_path) if isinstance(game_path, str) else "",
            "match_evidence": ("Exact Vortex discovered game path matches recorded installed game"
                               if matched_name else "Vortex game ID/path has no verified installed-game match"),
            "active_at_snapshot": str(profile_id) == str(active_id) if active_id is not None else None,
            "source": str(path), "snapshot_epoch": int(timestamp),
            "stale": stale, "mods": entries,
            "incomplete": len(data) > MAX_MODS_PER_PROFILE,
            "protected": True,
            "note": "Vortex JSON is a periodic backup, not live LevelDB state; profile status may be stale.",
        })
    if len(profiles) > MAX_PROFILES:
        warnings.append("Vortex profile count capped; report incomplete.")
    return out, warnings


def inspect_manager_profiles(mods, games=(), other_games=()) -> dict:
    """On-demand inventory from already detected managers; never visits arbitrary drives."""
    sources = list(mods)
    rows, warnings = [], []
    for ini in _mo2_roots(sources):
        found, notes = _read_mo2_instance(ini, games, other_games)
        rows.extend(found)
        warnings.extend(notes)
    for root in _vortex_roots(sources):
        backup = _latest_backup(root)
        if backup:
            found, notes = _read_vortex_backup(backup, games, other_games)
            rows.extend(found)
            warnings.extend(notes)
        else:
            warnings.append("No readable Vortex JSON backup was found. Live State.v2 was not opened.")
    return {
        "profiles": rows[:100], "warnings": warnings[:30],
        "count": len(rows), "truncated": len(rows) > 100,
        "no_deletion": True, "network_upload": False,
        "note": "Profile configuration evidence only. Enabled here does not prove active use, and disabled never means safe to delete.",
    }


def summarize_manager_profile(profile: dict) -> dict:
    records = profile.get("mods", ())
    return {
        "enabled": sum(x.get("marker") == "+" for x in records),
        "disabled": sum(x.get("marker") == "-" for x in records),
        "other": sum(x.get("marker") not in ("+", "-") for x in records),
        "incomplete": bool(profile.get("incomplete") or profile.get("stale")),
        "owner_verified": bool(profile.get("verified_game")),
    }
