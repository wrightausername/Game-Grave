"""Mod Bisect, the only part that writes: a COPY of a Mod Organizer 2 profile, never the original.

Owner decision (2026-11-10, "Yes to all"): Bisect works on a copy of the profile and keeps backups of the
profile's modlist.txt and plugins.txt next to it. The profile the owner uses is only ever read.

What this module will do:
  * create one new profile folder named "GG Bisect - <profile>" beside the original, holding copies of the
    original's top-level profile files (modlist.txt, plugins.txt, loadorder.txt, settings.ini, game INI files);
  * rewrite modlist.txt inside that copy so exactly the mods of one Bisect test are switched on;
  * leave the original profile, the mods folder, saves and every other file alone.

What it refuses: any folder that is not a "GG Bisect" copy carrying this module's marker file, any path that is a
link or leaves the profiles folder, a profile that keeps its own saves (a copy would not see them), and writing
while Mod Organizer 2 is running (it can overwrite the file when it closes).

Removing the copy is left to the owner (Mod Organizer 2, Profiles, Remove): nothing here deletes.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

COPY_PREFIX = "GG Bisect - "
MARKER = "gg-bisect.json"
MARKER_VERSION = 1
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_FILES = 80
BACKUP_NAMES = {"modlist.txt": "GG-original-modlist.txt", "plugins.txt": "GG-original-plugins.txt"}
MO2_PROCESSES = ("modorganizer.exe", "mo2.exe")
BAD_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


class ApplyError(Exception):
    """Something that makes writing unsafe or impossible. The message is written for the owner."""


@dataclass(frozen=True)
class CopyInfo:
    folder: Path
    source_name: str
    created: float


def _is_link(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
        return bool(attributes & 0x400)                      # FILE_ATTRIBUTE_REPARSE_POINT
    except OSError:
        return True


def _plain_dir(path: Path) -> bool:
    return path.is_dir() and not _is_link(path)


def _plain_file(path: Path) -> bool:
    return path.is_file() and not _is_link(path)


def copy_name(profile_name: str) -> str:
    cleaned = BAD_NAME.sub("_", profile_name).strip(" .")[:60] or "profile"
    return COPY_PREFIX + cleaned


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def keeps_own_saves(profile: Path) -> bool:
    """MO2's per-profile saves setting. A copy of such a profile would start with no saves, so Bisect refuses it."""
    settings = profile / "settings.ini"
    if not _plain_file(settings):
        return False
    try:
        text = _read_text(settings)
    except OSError:
        return True                                          # unreadable: do not guess, refuse
    match = re.search(r"^\s*LocalSaves\s*=\s*(\S+)", text, re.I | re.M)
    return bool(match and match.group(1).strip().lower() in ("true", "1", "yes"))


def mo2_running() -> bool | None:
    """True or False when Windows can tell us, None when it cannot (not Windows, no tasklist)."""
    if os.name != "nt":
        return None
    try:
        done = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True, timeout=15,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    names = {line.split('","')[0].strip('"').lower() for line in done.stdout.splitlines() if line}
    return any(name in names for name in MO2_PROCESSES)


# ------------------------------------------------------------------ the copy
def read_marker(folder: Path) -> CopyInfo | None:
    marker = folder / MARKER
    if not _plain_file(marker):
        return None
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
        if data.get("version") != MARKER_VERSION or not isinstance(data.get("source"), str):
            return None
        return CopyInfo(folder, data["source"], float(data.get("created", 0)))
    except (OSError, ValueError, TypeError):
        return None


def _check_copy(folder: Path, profiles_root: Path) -> CopyInfo:
    """Every write goes through this: ours by marker, directly inside the profiles folder, not a link."""
    if folder.parent != profiles_root or not folder.name.startswith(COPY_PREFIX):
        raise ApplyError("Bisect only writes to its own test profile, and this is not one.")
    if not _plain_dir(folder) or _is_link(profiles_root):
        raise ApplyError("The test profile folder is missing or is a link, so nothing was written.")
    info = read_marker(folder)
    if info is None:
        raise ApplyError("This folder was not made by Game Grave Bisect, so nothing was written to it.")
    return info


def make_copy(original: Path, profiles_root: Path | None = None) -> CopyInfo:
    """Create (or reuse) the test profile for `original`. Only reads the original."""
    original = Path(original)
    root = Path(profiles_root) if profiles_root else original.parent
    if original.parent != root or not _plain_dir(original) or _is_link(root):
        raise ApplyError("The profile folder is missing, is a link, or is not inside the profiles folder.")
    if not _plain_file(original / "modlist.txt"):
        raise ApplyError("The profile has no readable modlist.txt.")
    if keeps_own_saves(original):
        raise ApplyError("This profile keeps its own saves. A copy would not see them, so Bisect will not use it. "
                         "Turn off \"Use profile-specific Save Games\" in a copy you make yourself, or test with "
                         "another profile.")
    target = root / copy_name(original.name)
    if target.exists():
        info = _check_copy(target, root)
        if info.source_name != original.name:
            raise ApplyError("A Bisect test profile with this name already exists for another profile.")
        return info
    files = [p for p in sorted(original.iterdir(), key=lambda p: p.name.lower()) if _plain_file(p)]
    if len(files) > MAX_FILES:
        raise ApplyError("The profile folder holds too many files to copy safely.")
    target.mkdir()
    try:
        for source in files:
            if source.stat().st_size > MAX_FILE_BYTES:
                continue
            data = source.read_bytes()
            (target / source.name).write_bytes(data)
            backup = BACKUP_NAMES.get(source.name.lower())
            if backup:
                (target / backup).write_bytes(data)
        marker = {"version": MARKER_VERSION, "source": original.name, "created": time.time(),
                  "note": "Made by Game Grave Mod Bisect. Safe to remove in Mod Organizer 2 when you are done."}
        (target / MARKER).write_text(json.dumps(marker, indent=2), encoding="utf-8")
    except OSError as exc:
        raise ApplyError(f"The test profile could not be created: {exc}") from exc
    return _check_copy(target, root)


# ------------------------------------------------------------------ one test
def plan(original_modlist: str, enabled_names) -> tuple[str, list]:
    """The new modlist.txt text and the names it switched on, from the ORIGINAL file's text.

    Order, comments, separators and entries managed outside MO2 are kept as they were. Names that are not in
    the file are returned separately by `missing`."""
    on = {n.casefold() for n in enabled_names}
    newline = "\r\n" if "\r\n" in original_modlist else "\n"
    out, switched = [], []
    for line in original_modlist.splitlines():
        if not line or line.startswith("#") or line[0] not in "+-":
            out.append(line)
            continue
        name = line[1:].strip()
        if name.casefold().endswith("_separator"):
            out.append(line)
            continue
        if name.casefold() in on:
            out.append("+" + name)
            switched.append(name)
        else:
            out.append("-" + name)
    return newline.join(out) + newline, switched


def missing(original_modlist: str, enabled_names) -> list:
    present = {line[1:].strip().casefold() for line in original_modlist.splitlines()
               if line and line[0] in "+-"}
    return sorted(n for n in enabled_names if n.casefold() not in present)


def write_test(folder: Path, enabled_names, *, running=mo2_running) -> list:
    """Make the test profile hold exactly `enabled_names` switched on. Returns the names switched on."""
    folder = Path(folder)
    root = folder.parent
    _check_copy(folder, root)
    if running() is True:
        raise ApplyError("Mod Organizer 2 is running. Close it completely first, then try again: it can write its "
                         "own copy of the list over this one when it closes.")
    backup = folder / BACKUP_NAMES["modlist.txt"]
    if not _plain_file(backup):
        raise ApplyError("The backup of the original modlist.txt is missing, so nothing was written.")
    original = _read_text(backup)
    lost = missing(original, enabled_names)
    if lost:
        raise ApplyError("These mods are not in the profile's mod list, so the test cannot be made: "
                         + ", ".join(lost[:5]) + (" and more" if len(lost) > 5 else ""))
    text, switched = plan(original, enabled_names)
    target = folder / "modlist.txt"
    if target.exists() and not _plain_file(target):
        raise ApplyError("modlist.txt in the test profile is not an ordinary file, so nothing was written.")
    temp = folder / "modlist.txt.gg-tmp"
    try:
        temp.write_bytes(text.encode("utf-8"))
        os.replace(temp, target)
    except OSError as exc:
        try:
            temp.unlink()
        except OSError:
            pass
        raise ApplyError(f"The test could not be written: {exc}") from exc
    return switched


def enabled_in(folder: Path) -> set:
    """Names currently switched on in the test profile's modlist.txt (to show what is set up)."""
    path = Path(folder) / "modlist.txt"
    if not _plain_file(path):
        return set()
    return {line[1:].strip() for line in _read_text(path).splitlines()
            if line.startswith("+") and not line[1:].strip().casefold().endswith("_separator")}
