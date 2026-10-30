"""MO2 manager-aware Resurrection Kit reattachment.

Rechecks the ZIP and exact installed-game/manager paths before any write.
Requires user approval and same dry-run fingerprint. Only installs missing mod
folders and ONE new, uniquely named profile. Never edits MO2's INI, existing
profiles, preexisting mods, game installation or Vortex LevelDB.

MO2 may still need the user to select the restored profile in its UI.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from manager_profiles import _identity, _ordinary, _verified_game
from mod_sources import _read_ini, _resolve_mo_path
from resurrection_v2 import (_manifest_for, _scan_archive, _valid_member,
                             _relative_name, inspect_restore, MIN_SPACE_BUFFER)


def _mo2_targets(ini_file: Path):
    if not _ordinary(ini_file):
        raise ValueError("Choose an ordinary MO2 instance INI file.")
    cfg = _read_ini(ini_file)
    if cfg is None or not cfg.has_section("Settings"):
        raise ValueError("MO2 instance configuration is missing or unsupported.")
    base = _resolve_mo_path(cfg["Settings"].get("base_directory", str(ini_file.parent)),
                            ini_file.parent, ini_file.parent)
    profiles = _resolve_mo_path(cfg["Settings"].get("profiles_directory", "%BASE_DIR%/profiles"),
                                base, ini_file.parent)
    mods = _resolve_mo_path(cfg["Settings"].get("mod_directory", "%BASE_DIR%/mods"),
                            base, ini_file.parent)
    for label, root in (("profiles", profiles), ("mods", mods)):
        if (not _ordinary(root, directory=True)
                or root.resolve() in (Path(root.anchor), Path.home().resolve())):
            raise ValueError(f"MO2 {label} folder is unavailable, linked or unsafe.")
        # Configurable MO2 roots may be on separate drives, but must be ordinary folders.
        # Reject path aliases that could make profile and mod content overlap.
    a, b = profiles.resolve(), mods.resolve()
    if a == b or a in b.parents or b in a.parents:
        raise ValueError("MO2 profile and mod destinations overlap.")
    game_path = cfg.get("General", "gamePath", fallback="") if cfg.has_section("General") else ""
    return profiles, mods, game_path


def _closed_manager_check():
    """Best effort Windows process guard; fail closed when it cannot be checked."""
    if os.name != "nt":
        return
    result = subprocess.run(["tasklist", "/FO", "CSV", "/NH"],
                            capture_output=True, text=True, timeout=8,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        raise RuntimeError("Could not verify that MO2 is closed. No files restored.")
    import csv
    rows = csv.reader(result.stdout.splitlines())
    running = {row[0].strip().casefold() for row in rows if row}
    if running.intersection({"modorganizer.exe", "modorganizer2.exe"}):
        raise RuntimeError("Close Mod Organizer 2 before reconnecting a Resurrection Kit.")


def _profile_name(value: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 130:
        raise ValueError("Missing or invalid MO2 profile name.")
    if len(_relative_name(value)) != 1:
        raise ValueError("MO2 profile must have a single portable folder name.")
    return value + "_GameGrave"


def _read_zip_modlist(archive: zipfile.ZipFile) -> set[str]:
    try:
        info = archive.getinfo("Profiles/modlist.txt")
    except KeyError as exc:
        raise ValueError("The kit does not contain the required MO2 modlist.txt.") from exc
    if info.file_size > 2_000_000:
        raise ValueError("MO2 modlist is too large to validate.")
    raw = archive.read(info)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
    enabled = set()
    for line in text.splitlines():
        if line.startswith("+"):
            name = line[1:].strip()
            if len(name) > 200 or not name or "/" in name or "\\" in name or name in (".", ".."):
                raise ValueError("MO2 modlist contains a nonportable enabled-mod name.")
            enabled.add(name.casefold())
    return enabled


def _build_mo2_plan(manifest_path: Path, ini_file: Path, games=(), other_games=()) -> dict:
    kit = inspect_restore(manifest_path)  # Full SHA256, ZIP CRC and count verification
    manifest, archive_path = _manifest_for(manifest_path)
    if manifest.get("schema") != 2:
        raise ValueError("Automatic MO2 reconnection requires a v2 Resurrection Kit.")
    context = manifest.get("manager_context")
    if (not isinstance(context, dict) or context.get("kind") != "MO2"
            or context.get("auto_discovered") is not True):
        raise ValueError("This kit has no verified MO2 discovery record. Use staged recovery instead.")
    if "Mods" not in kit["roles"] or "Profiles" not in kit["roles"]:
        raise ValueError("MO2 reconnection requires both a mod folder and a profile folder.")
    root_profiles, root_mods, game_path = _mo2_targets(Path(ini_file))
    game_name, installed_path = _verified_game(game_path, games, other_games)
    if not game_name or game_name.casefold() != kit["game"].casefold():
        raise ValueError("The current MO2 instance does not match this installed game.")
    new_name = _profile_name(context.get("profile"))
    profile_target = root_profiles / new_name
    if profile_target.exists() or profile_target.is_symlink():
        raise FileExistsError("Restored profile already exists in MO2; no files were touched.")
    mod_folders = set()
    with zipfile.ZipFile(archive_path) as archive:
        infos, _, _ = _scan_archive(archive, 2)
        enabled = _read_zip_modlist(archive)
        for info in infos:
            parts = _valid_member(info, 2)
            if parts[0] == "Mods":
                if len(parts) < 3:
                    raise ValueError("MO2 mods must be organized into named folders.")
                mod_folders.add(parts[1])
        if not mod_folders:
            raise ValueError("Kit has no compatible MO2 mod folders.")
        if enabled - {m.casefold() for m in mod_folders}:
            missing = len(enabled - {m.casefold() for m in mod_folders})
            raise ValueError(f"Kit is missing {missing} enabled mod folder(s). Use staged recovery.")
        # Reject case collisions against pre-existing MO2 folders on Windows.
        existing = {p.name.casefold() for p in root_mods.iterdir()}
        if any(name.casefold() in existing for name in mod_folders):
            raise FileExistsError("Some kit mods already exist in MO2. No overwrite or merge is attempted.")
    ignored_roles = [r for r in kit["roles"] if r not in ("Mods", "Profiles")]
    total = kit["bytes"]
    # The two roots could live on different disks. Check per-volume conservative room.
    for root in {root_profiles, root_mods}:
        if shutil.disk_usage(root).free < total + MIN_SPACE_BUFFER:
            raise OSError("Not enough free space in an MO2 destination.")
    names = sorted(mod_folders, key=str.casefold)
    payload = {
        "game": game_name,
        "manager": "Mod Organizer 2",
        "mod_root": str(root_mods), "profiles_root": str(root_profiles),
        "profile_target": str(profile_target),
        "mods_to_add": names, "mods_count": len(names),
        "not_reconnected_roles": ignored_roles,
        "files": kit["files"], "bytes": total,
        "archive": str(archive_path),
        "no_overwrite": True, "no_live_game_edit": True,
        "requires_mo2_closed": True,
        "note": "All mod folders must be absent. A new MO2 profile is added; select it in MO2 after restoration.",
    }
    signature_data = {
        "archive_sha256": manifest["archive_sha256"],
        "ini_sha256": hashlib.sha256(Path(ini_file).read_bytes()).hexdigest(),
        "mod_root": payload["mod_root"],
        "profile_target": payload["profile_target"],
        "mods_to_add": names,
        "game": game_name,
    }
    payload["fingerprint"] = hashlib.sha256(json.dumps(
        signature_data, sort_keys=True).encode("utf-8")).hexdigest()
    return payload


def preview_mo2_reconnect(manifest_path: Path, ini_file: Path, games=(),
                           other_games=()) -> dict:
    """Dry-run with precise destination information and zero writes."""
    return _build_mo2_plan(Path(manifest_path), Path(ini_file), games, other_games)


def reconnect_to_mo2(manifest_path: Path, ini_file: Path, games=(),
                     other_games=(), *, approved=False, expected_fingerprint="") -> dict:
    """User-approved, conflict-free MO2 restore into new profile/mod folders.

    Partial restoration is NEVER declared successful. If failure happens after
    publishing, only Game Grave-created files are eligible for conservative
    rollback. Preserve anything unexpectedly modified by another process.
    """
    if approved is not True or not expected_fingerprint:
        raise PermissionError("Explicit approved dry-run is required.")
    _closed_manager_check()
    plan = _build_mo2_plan(manifest_path, ini_file, games, other_games)
    if expected_fingerprint != plan["fingerprint"]:
        raise ValueError("The backup, MO2 config or restore plan changed. Preview again.")
    profile_root = Path(plan["profiles_root"])
    mod_root = Path(plan["mod_root"])
    profile_dest = Path(plan["profile_target"])
    manifest, archive_path = _manifest_for(manifest_path)
    created_dirs = []
    created_files = []
    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos, _, _ = _scan_archive(archive, 2)
            # Explicit exclusive directory reservations. No existing mod or
            # profile directory is merged or overwritten.
            for name in plan["mods_to_add"]:
                dest = mod_root / name
                if not _ordinary(mod_root, directory=True):
                    raise RuntimeError("MO2 mod root changed during restore.")
                dest.mkdir(exist_ok=False)
                created_dirs.append(dest)
            if not _ordinary(profile_root, directory=True):
                raise RuntimeError("MO2 profiles root changed during restore.")
            profile_dest.mkdir(exist_ok=False)
            created_dirs.append(profile_dest)
            for info in infos:
                parts = _valid_member(info, 2)
                if parts[0] == "Mods":
                    destination = mod_root.joinpath(*parts[1:])
                    anchor = mod_root / parts[1]
                elif parts[0] == "Profiles":
                    destination = profile_dest.joinpath(*parts[1:])
                    anchor = profile_dest
                else:
                    # Save/config roles are retained in the verified ZIP. Never
                    # guess live save destinations from directory names alone.
                    continue
                # Files must stay inside an exclusively-created destination.
                if anchor not in destination.parents or not _ordinary(anchor, directory=True):
                    raise RuntimeError("Restore destination escaped its reserved folder.")
                parents = []
                parent = destination.parent
                while parent != anchor:
                    parents.append(parent)
                    parent = parent.parent
                for directory in reversed(parents):
                    if directory.exists() or directory.is_symlink():
                        if not _ordinary(directory, directory=True):
                            raise RuntimeError("Restore encountered linked or changed folder.")
                    else:
                        directory.mkdir(exist_ok=False)
                with archive.open(info) as source, destination.open("xb") as output:
                    shutil.copyfileobj(source, output, 1024 * 1024)
                created_files.append(destination)
                if destination.stat().st_size != info.file_size:
                    raise RuntimeError("Restored file size differs from archive.")
        return {
            "restored": True, "profile": str(profile_dest),
            "not_reconnected_roles": plan["not_reconnected_roles"],
            "added_mod_folders": plan["mods_count"],
            "files": plan["files"],
            "no_overwrite": True,
            "note": "Recreated missing MO2 mod folders and a new profile. Select the restored profile in MO2.",
        }
    except BaseException as error:
        # Avoid wiping unrelated files if a concurrent process touched our directories.
        # Only roll back if *every* newly-created subtree consists solely of the
        # exact files we created. Any uncertainty leaves directories for review.
        import collections
        expected = collections.defaultdict(set)
        for item in created_files:
            for ancestor in created_dirs:
                if ancestor in item.parents:
                    expected[ancestor].add(item)
                    break
        for folder in reversed(created_dirs):
            try:
                actual = {p for p in folder.rglob("*") if p.is_file()}
                linked = any(p.is_symlink() for p in folder.rglob("*"))
                if not linked and actual == expected[folder]:
                    shutil.rmtree(folder)
            except OSError:
                pass
        raise RuntimeError(
            "MO2 restoration did not complete. Inspect the manager folders for "
            "possible partial data; existing game files were not replaced."
        ) from error
