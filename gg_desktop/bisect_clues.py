"""Crash-report clues for Mod Bisect.

Pure Python: it is handed text and records that something else already read (Black Box collects them) and never
opens a file itself. It answers three questions from what the reports actually say:

  * Which mods have files named in crash reports? (`hits`, how many reports named each mod)
  * Which mod owns the file Windows recorded as the crash location? (`fault_keys`)
  * When did the crashes start? (`first_crash`, `last_crash`, `crash_count`)

None of this is proof. A file named in a report was loaded or on the stack, not necessarily guilty, and a crash
report can name nothing at all. These clues only decide which tests Bisect runs first; the verdict still comes from
the owner's own launches. A file name that belongs to more than one mod is left out and counted as ambiguous
rather than blamed on one of them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

DAY = 86400.0
FILE_TOKEN = re.compile(r"[\w\-.+()~]+\.[A-Za-z0-9]{2,5}")
PATH_PART = re.compile(r"[^\\/\r\n:*?\"<>|]+(?=[\\/])")
# folder names so common that matching a mod called this would be a coin flip
GENERIC_FOLDERS = frozenset({"data", "mods", "plugins", "scripts", "textures", "meshes", "bin", "windows", "system32",
                             "program files", "program files (x86)", "users", "appdata", "local", "roaming",
                             "documents", "my games", "steam", "steamapps", "common", "logs", "saves", "config"})


@dataclass(frozen=True)
class Clues:
    hits: dict = field(default_factory=dict)           # mod key -> number of reports that named one of its files
    fault_keys: tuple = ()                             # mods owning the file Windows recorded as the crash location
    first_crash: float | None = None                   # epoch seconds
    last_crash: float | None = None
    crash_count: int = 0                               # dated crashes
    reports_read: int = 0
    ambiguous: int = 0                                 # file names that belong to several mods and were ignored
    notes: tuple = ()

    @property
    def hint_keys(self) -> tuple:
        """Mods worth testing first, most reports first, faulting mods leading."""
        order = sorted(self.hits, key=lambda k: (-self.hits[k], k))
        return tuple(dict.fromkeys(list(self.fault_keys) + order))


def _norm(name: str) -> str:
    return name.replace("\\", "/").strip("/").lower()


def _file_index(files: dict):
    """base name -> mod key when exactly one mod has it; the ambiguous ones are returned separately."""
    owners: dict = {}
    for key, paths in files.items():
        for path in paths:
            base = _norm(path).rsplit("/", 1)[-1]
            if base:
                owners.setdefault(base, set()).add(key)
    unique = {b: next(iter(k)) for b, k in owners.items() if len(k) == 1}
    return unique, {b for b, k in owners.items() if len(k) > 1}


def _folder_index(units) -> dict:
    out: dict = {}
    for u in units:
        for label in {u.key, u.name}:
            low = label.strip().lower()
            if low and low not in GENERIC_FOLDERS:
                out.setdefault(low, set()).add(u.key)
    return {name: next(iter(keys)) for name, keys in out.items() if len(keys) == 1}


def read_reports(units, files: dict, reports=(), crashes=()) -> Clues:
    """units: Bisect units. files: {mod key: iterable of file paths inside that mod}.
    reports: iterable of (text, when) where `when` is epoch seconds or None. crashes: Black Box `Crash` records
    (anything with .when as a datetime, .module as the faulting module name)."""
    unique, ambiguous = _file_index(files)
    folders = _folder_index(units)
    hits: dict = {}
    seen_ambiguous: set = set()
    times: list = []
    count = 0
    for text, when in reports:
        count += 1
        if when is not None:
            times.append(float(when))
        named: set = set()
        for token in FILE_TOKEN.findall(text or ""):
            low = token.lower()
            if low in unique:
                named.add(unique[low])
            elif low in ambiguous:
                seen_ambiguous.add(low)
        for part in PATH_PART.findall(text or ""):
            key = folders.get(part.strip().lower())
            if key:
                named.add(key)
        for key in named:
            hits[key] = hits.get(key, 0) + 1
    fault: list = []
    for crash in crashes:
        stamp = getattr(crash, "when", None)
        if stamp is not None:
            try:
                times.append(stamp.timestamp())
            except (OverflowError, OSError, ValueError):
                pass
        module = _norm(getattr(crash, "module", "") or "").rsplit("/", 1)[-1]
        if module in unique and unique[module] not in fault:
            fault.append(unique[module])
        elif module in ambiguous:
            seen_ambiguous.add(module)
    notes = []
    if not count and not crashes:
        notes.append("No crash reports were given, so there are no clues from them.")
    elif not hits and not fault:
        notes.append("The crash reports did not name a file that belongs to any mod. That is common and says nothing "
                     "about whether a mod is involved.")
    if fault:
        notes.append("Windows recorded the crash inside a mod's file. That points at where it failed, which is not "
                     "always the mod that caused it.")
    return Clues(hits, tuple(fault), min(times) if times else None, max(times) if times else None, len(times), count,
                 len(seen_ambiguous), tuple(notes))


def apply_hits(units, clues: Clues) -> list:
    """The same units with `crash_hits` filled in from the reports."""
    return [replace(u, crash_hits=clues.hits.get(u.key, u.crash_hits)) for u in units]


def started_after(units, clues: Clues, days: float = 7.0) -> tuple:
    """Mods added in the `days` before the first dated crash. A clue for "it started after I added these"; it is
    not the owner's statement, so Bisect treats it only as search order."""
    if clues.first_crash is None:
        return ()
    low, high = clues.first_crash - days * DAY, clues.first_crash
    return tuple(u.key for u in units if u.added is not None and low <= u.added <= high)
