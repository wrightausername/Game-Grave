"""Mod Bisect, reading side: turns what Mods already knows into Bisect units and finds crash reports.

Read-only. It opens mod folders and report files to read their names or text, with hard limits so a huge library
cannot freeze the app, and it never changes anything.

  * `units_for_profile` : the mods switched on in one Mod Organizer 2 profile, with install date (folder creation
    time), whether they hold scripts or plugins, and the requirements their own metadata declares.
  * `scan_mod_files`    : bounded file lists per mod, used to match file names in crash reports to mods.
  * `find_reports` / `read_reports_text` : crash log files near the game, newest first, size capped.

The install date is the date the mod's folder was created. If mods were moved or restored from a backup that can be
later than the real install, so the screen says where the date came from.
"""
from __future__ import annotations

import os
from pathlib import Path

from gg_desktop.bisect_core import Unit
from gg_desktop.blackbox_core import CRASH_WORDS, LOG_SUFFIXES

STRONG_CODE = frozenset({".dll", ".asi", ".pex", ".lua", ".jar", ".py", ".exe", ".esp", ".esm", ".esl"})
MAX_FILES_PER_MOD = 4000
MAX_FILES_TOTAL = 400_000
MAX_DEPTH = 8
MAX_REPORTS = 30
MAX_REPORT_BYTES = 256 * 1024
REPORT_DAYS = 120
SCRIPT_EXTENDER_FOLDERS = ("skse", "f4se", "sfse", "obse", "nvse", "fose", "mwse")


def install_time(path) -> float | None:
    """When the mod's folder was created (Windows creation time), or None when it cannot be read."""
    try:
        info = os.stat(path)
    except OSError:
        return None
    stamp = getattr(info, "st_birthtime", None)
    if stamp is None and os.name == "nt":
        stamp = info.st_ctime
    return float(stamp) if stamp else None


def scan_mod_files(path, *, cancelled=lambda: False, budget=None):
    """(relative file paths, holds scripts or plugins) for one mod folder. Never follows links; bounded."""
    files: list = []
    strong = False
    root = Path(path)
    stack = [(root, 0)]
    while stack and len(files) < MAX_FILES_PER_MOD:
        if cancelled():
            break
        current, depth = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            if depth < MAX_DEPTH:
                                stack.append((Path(entry.path), depth + 1))
                        elif entry.is_file(follow_symlinks=False):
                            files.append(str(Path(entry.path).relative_to(root)))
                            if Path(entry.name).suffix.lower() in STRONG_CODE:
                                strong = True
                            if budget is not None:
                                budget[0] += 1
                            if len(files) >= MAX_FILES_PER_MOD:
                                break
                    except OSError:
                        continue
        except OSError:
            continue
        if budget is not None and budget[0] >= MAX_FILES_TOTAL:
            break
    return files, strong


def declared_requirements(entry, by_name: dict) -> tuple:
    """Keys of the mods this entry's own metadata says it needs, matched by exact name."""
    keys = []
    for dep in getattr(entry, "dependencies", ()) or ():
        if getattr(dep, "optional", False) or getattr(dep, "incompatible", False):
            continue
        target = by_name.get(str(dep.name).casefold())
        if target and target != entry.key and target not in keys:
            keys.append(target)
    return tuple(keys)


def units_for_profile(catalog, profile, *, always_on=(), cancelled=lambda: False, scan_files=True,
                      installed=install_time):
    """(units, files, notes). Candidates are the mods switched ON in `profile`; mods switched off stay off.

    files maps each mod key to its (bounded) relative file list for crash-report matching."""
    entries = {e.key: e for e in catalog.entries if e.kind == "mod"}
    on = [entries[k] for k, marker in profile.members.items() if marker == "+" and k in entries]
    by_name = {}
    for e in on:
        by_name.setdefault(e.name.casefold(), e.key)
    pinned = set(always_on)
    units, files, notes = [], {}, []
    budget = [0]
    limited = False
    for e in on:
        if cancelled():
            break
        names = []
        strong = False
        if scan_files and budget[0] < MAX_FILES_TOTAL:
            names, strong = scan_mod_files(e.path, cancelled=cancelled, budget=budget)
            files[e.key] = names
        else:
            limited = limited or scan_files
        added = installed(e.path)
        units.append(Unit(e.key, e.name, added=added, kind="code" if strong else "assets",
                          requires=declared_requirements(e, by_name), pinned=e.key in pinned))
    if limited:
        notes.append("The file limit was reached, so crash reports can only be matched to some of the mods.")
    missing_dates = sum(1 for u in units if u.added is None)
    if missing_dates:
        notes.append(f"{missing_dates} mod folders have no readable install date; they are tested last.")
    notes.append("Install dates are when each mod's folder was created. Mods that were moved or restored from a "
                 "backup can show a later date than their real install.")
    return units, files, notes


# ------------------------------------------------------------------ crash reports
def _looks_like_report(name: str) -> bool:
    low = name.casefold()
    return low.endswith(LOG_SUFFIXES) and any(word in low for word in CRASH_WORDS)


def default_report_roots(game_folder, mo2_base=None, documents=None) -> list:
    """Places crash logs are normally written, as folders to look in (the caller decides which exist)."""
    roots = []
    if game_folder:
        roots.append(Path(game_folder))
        for folder in SCRIPT_EXTENDER_FOLDERS:
            roots.append(Path(game_folder) / "Data" / folder / "Plugins")
    if mo2_base:
        roots += [Path(mo2_base) / "logs", Path(mo2_base) / "crashDumps"]
    if documents:
        games = Path(documents) / "My Games"
        try:
            with os.scandir(games) as it:
                for entry in list(it)[:40]:
                    if entry.is_dir(follow_symlinks=False):
                        base = Path(entry.path)
                        roots.append(base)
                        roots += [base / name.upper() for name in SCRIPT_EXTENDER_FOLDERS]
                        roots.append(base / "Crash Reports")
        except OSError:
            pass
    return roots


def find_reports(roots, *, now: float, days: int = REPORT_DAYS, depth: int = 2) -> list:
    """Newest crash-looking text files under `roots`: [(path, mtime)]. Bounded and never follows links."""
    cutoff = now - days * 86400.0
    found = {}
    scanned = 0
    for root in roots:
        stack = [(Path(root), 0)]
        while stack:
            current, level = stack.pop()
            try:
                with os.scandir(current) as it:
                    for entry in it:
                        scanned += 1
                        if scanned > 20_000:
                            stack.clear()
                            break
                        try:
                            if entry.is_symlink():
                                continue
                            if entry.is_dir(follow_symlinks=False):
                                if level < depth:
                                    stack.append((Path(entry.path), level + 1))
                            elif entry.is_file(follow_symlinks=False) and _looks_like_report(entry.name):
                                mtime = entry.stat().st_mtime
                                if mtime >= cutoff:
                                    found[os.path.normcase(entry.path)] = (entry.path, mtime)
                        except OSError:
                            continue
            except OSError:
                continue
    return sorted(found.values(), key=lambda item: -item[1])[:MAX_REPORTS]


def read_reports_text(paths) -> list:
    """[(text, mtime)] for report files, each capped. Unreadable files are skipped."""
    out = []
    for path, mtime in paths:
        try:
            with open(path, "rb") as handle:
                raw = handle.read(MAX_REPORT_BYTES)
        except OSError:
            continue
        if b"\x00" in raw[:2000] and raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
            text = raw.decode("utf-16", "replace")
        else:
            text = raw.decode("utf-8", "replace")
        out.append((text, mtime))
    return out
