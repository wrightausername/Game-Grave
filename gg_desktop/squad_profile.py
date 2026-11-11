"""Squad Sync's last step: a NEW Mod Organizer 2 profile with your friend's mods switched on in your friend's order.

Owner instruction (2026-11-11, "continue the checklist ... refine the squad sync"). Same model the owner approved for Mod
Bisect: a copy, never the profile you use.

What it writes: one new folder `<profiles>/GG Squad - <your profile>` holding copies of your profile's own top-level
files, a rewritten modlist.txt, and a small marker file. In that modlist the mods your friend has switched on, and that
are installed here, are switched on in your friend's order (top of the file wins, as in Mod Organizer 2); every other
mod is listed switched off; entries Mod Organizer 2 does not manage (DLC) are kept as they were.

What it never does: change your own profile, any mod folder, plugins.txt in your profile, or Mod Organizer 2's
settings; overwrite anything (an existing name gets a number); delete anything (you remove the profile in Mod
Organizer 2). Plugin order is not part of a squad code, so the profile keeps your plugins.txt and says so.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from gg_desktop.bisect_apply import _is_link, _plain_dir, _plain_file, _read_text, keeps_own_saves

PREFIX = "GG Squad - "
MARKER = "gg-squad.json"
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_FILES = 80
BAD_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


class ProfileError(Exception):
    """A plain sentence for the person."""


def build_modlist(original_text: str, host_names, installed_names):
    """(new modlist text, names switched on, host names not installed here).

    `host_names` are your friend's switched-on mods, highest priority first. `installed_names` are the mod folders
    that exist on this PC."""
    newline = "\r\n" if "\r\n" in original_text else "\n"
    installed = {}
    for name in installed_names:
        installed.setdefault(str(name).casefold(), str(name))
    comments, entries = [], []
    for line in original_text.splitlines():
        if not line.strip():
            continue
        if line.startswith("#") or line[0] not in "+-*":
            comments.append(line)
            continue
        entries.append((line[0], line[1:].strip()))
    for _sign, name in entries:
        installed.setdefault(name.casefold(), name)
    on, seen, absent = [], set(), []
    for name in host_names:
        key = str(name).casefold()
        if key in seen:
            continue
        seen.add(key)
        if key in installed and not key.endswith("_separator"):
            on.append(installed[key])
        else:
            absent.append(str(name))
    on_keys = {n.casefold() for n in on}
    lines = list(comments) + ["+" + name for name in on]
    for sign, name in entries:
        key = name.casefold()
        if key in on_keys:
            continue
        if sign == "*" or key.endswith("_separator"):
            lines.append(sign + name)            # not a mod Mod Organizer 2 switches: keep it as it was
        else:
            lines.append("-" + name)
    return newline.join(lines) + newline, on, absent


def profile_name(original_name: str, exists) -> str:
    cleaned = BAD_NAME.sub("_", original_name).strip(" .")[:60] or "profile"
    name, number = PREFIX + cleaned, 1
    while exists(name):
        number += 1
        name = f"GG Squad {number} - {cleaned}"
    return name


def preview(original: Path, host_names, mods_folder: Path) -> dict:
    """Read-only: what a squad profile would switch on. Raises ProfileError with the reason when it cannot be made."""
    original, mods_folder = Path(original), Path(mods_folder)
    root = original.parent
    if not _plain_dir(original) or _is_link(root):
        raise ProfileError("Your Mod Organizer 2 profile folder is missing or is a link.")
    if not _plain_file(original / "modlist.txt"):
        raise ProfileError("Your Mod Organizer 2 profile has no readable modlist.txt.")
    if not _plain_dir(mods_folder):
        raise ProfileError("Mod Organizer 2's mods folder is missing or is a link.")
    host = [str(n) for n in host_names if str(n).strip()]
    if not host:
        raise ProfileError("Your friend's code lists no Mod Organizer 2 mods, so there is no order to match.")
    try:
        text = _read_text(original / "modlist.txt")
        folders = [p.name for p in mods_folder.iterdir() if p.is_dir()]
    except OSError as problem:
        raise ProfileError(f"Your mod list could not be read ({type(problem).__name__}).") from None
    new_text, on, absent = build_modlist(text, host, folders)
    if not on:
        raise ProfileError("None of your friend's mods are installed here yet. Get the missing mods first.")
    name = profile_name(original.name, lambda candidate: (root / candidate).exists() or (root / candidate).is_symlink())
    return {"name": name, "folder": str(root / name), "on": on, "not_installed": absent, "text": new_text,
            "own_saves": keeps_own_saves(original), "source": original.name}


def make(original: Path, host_names, mods_folder: Path) -> dict:
    """Create the squad profile. Only reads your own profile. A failure removes exactly what this call created."""
    plan = preview(original, host_names, mods_folder)
    original, target = Path(original), Path(plan["folder"])
    files = [p for p in sorted(original.iterdir(), key=lambda p: p.name.lower()) if _plain_file(p)]
    if len(files) > MAX_FILES:
        raise ProfileError("Your profile folder holds too many files to copy.")
    created = []
    try:
        target.mkdir()
    except OSError as problem:
        raise ProfileError(f"The new profile folder could not be created ({type(problem).__name__}).") from None
    try:
        for source in files:
            if source.name.lower() in ("modlist.txt", MARKER) or source.stat().st_size > MAX_FILE_BYTES:
                continue
            destination = target / source.name
            with open(destination, "xb") as out:
                created.append(destination)
                out.write(source.read_bytes())
        modlist = target / "modlist.txt"
        with open(modlist, "x", encoding="utf-8", newline="") as out:
            created.append(modlist)
            out.write(plan["text"])
        marker = target / MARKER
        with open(marker, "x", encoding="utf-8") as out:
            created.append(marker)
            json.dump({"version": 1, "source": original.name, "created": time.time(),
                       "note": "Made by Game Grave Squad Sync. Remove it in Mod Organizer 2 when you no longer need it."},
                      out, indent=2)
    except OSError as problem:
        for path in reversed(created):
            try:
                path.unlink()
            except OSError:
                pass
        try:
            target.rmdir()
        except OSError:
            pass
        raise ProfileError(f"The squad profile could not be written ({type(problem).__name__}). Nothing was kept.") from None
    return {k: v for k, v in plan.items() if k != "text"}


def result_text(result: dict) -> str:
    on, absent = len(result["on"]), len(result["not_installed"])
    parts = [f"Made the profile \"{result['name']}\" with {on} of your friend's mod{'s' if on != 1 else ''} switched on "
             "in their order."]
    if absent:
        parts.append(f"{absent} {'are' if absent != 1 else 'is'} not installed here yet and {'were' if absent != 1 else 'was'} left out.")
    parts.append("Open Mod Organizer 2, pick that profile, and check the Plugins tab (plugin order is not part of a "
                 "squad code). Your own profile was not changed.")
    if result.get("own_saves"):
        parts.append("Your profile keeps its own saves, so the squad profile starts without them.")
    return " ".join(parts)
