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
from collections import Counter
from dataclasses import dataclass, field, replace

DAY = 86400.0
FILE_TOKEN = re.compile(r"[\w\-.+()~]+\.[A-Za-z0-9]{2,5}")
PATH_PART = re.compile(r"[^\\/\r\n:*?\"<>|]+(?=[\\/])")
# folder names so common that matching a mod called this would be a coin flip
GENERIC_FOLDERS = frozenset({"data", "mods", "plugins", "scripts", "textures", "meshes", "bin", "windows", "system32",
                             "program files", "program files (x86)", "users", "appdata", "local", "roaming",
                             "documents", "my games", "steam", "steamapps", "common", "logs", "saves", "config"})


# Faulting files that do not belong to a mod. Windows records where the failure SURFACED, so this says whose file it
# is, never who caused it. Kept short on purpose: only names that are well known.
KNOWN_MODULES = {
    "nvwgf2umx.dll": "the NVIDIA graphics driver", "nvlddmkm.sys": "the NVIDIA graphics driver",
    "nvoglv64.dll": "the NVIDIA graphics driver",
    "atidxx64.dll": "the AMD graphics driver", "amdxx64.dll": "the AMD graphics driver",
    "aticfx64.dll": "the AMD graphics driver", "atiumd64.dll": "the AMD graphics driver",
    "igd10iumd64.dll": "the Intel graphics driver", "igdumdim64.dll": "the Intel graphics driver",
    "igd11dxva64.dll": "the Intel graphics driver",
    "d3d11.dll": "DirectX", "d3d12.dll": "DirectX", "d3d9.dll": "DirectX", "dxgi.dll": "DirectX",
    "ntdll.dll": "Windows itself (the crash surfaced there, the cause is usually elsewhere)",
    "kernelbase.dll": "Windows itself (the crash surfaced there, the cause is usually elsewhere)",
    "kernel32.dll": "Windows itself (the crash surfaced there, the cause is usually elsewhere)",
    "ucrtbase.dll": "the Windows C runtime", "msvcp140.dll": "the Visual C++ runtime",
    "vcruntime140.dll": "the Visual C++ runtime", "msvcr120.dll": "the Visual C++ runtime",
    "steam_api64.dll": "Steam", "steam_api.dll": "Steam",
}
# What the code Windows recorded means, in words that stay true. Never a cause.
KNOWN_CODES = {
    "c0000005": "an access violation: the game touched memory it should not have",
    "c0000409": "the program shut itself down after detecting corrupted memory",
    "c00000fd": "a stack overflow",
    "c0000374": "heap corruption: memory the game owns was damaged",
    "c0000017": "running out of memory",
    "c000001d": "an illegal instruction: code that does not fit this PC or was damaged",
    "80000003": "a breakpoint compiled into some code",
    "e0434352": "a .NET error",
    "e06d7363": "a C++ error that was not handled",
}
CODE_TOKEN = re.compile(r"\b(?:0x)?([0-9a-fA-F]{8})\b")


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
    modules: tuple = ()                                # (faulting file name, crashes) most common first
    codes: tuple = ()                                  # (exception code, crashes) most common first

    @property
    def hint_keys(self) -> tuple:
        """Mods worth testing first, most reports first, faulting mods leading."""
        order = sorted(self.hits, key=lambda k: (-self.hits[k], k))
        return tuple(dict.fromkeys(list(self.fault_keys) + order))


def _code(value) -> str:
    text = str(value or "").strip().lower()
    text = text[2:] if text.startswith("0x") else text
    return text.zfill(8) if re.fullmatch(r"[0-9a-f]{1,8}", text) else ""


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
    modules: Counter = Counter()
    codes: Counter = Counter()
    seen_ambiguous: set = set()
    times: list = []
    count = 0
    for text, when in reports:
        count += 1
        if when is not None:
            times.append(float(when))
        named: set = set()
        for found in {_code(c) for c in CODE_TOKEN.findall(text or "")}:
            if found in KNOWN_CODES:
                codes[found] += 1
        for token in FILE_TOKEN.findall(text or ""):
            if token.lower() in KNOWN_MODULES:
                modules[token.lower()] += 1
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
        if module:
            modules[module] += 1
        code = _code(getattr(crash, "code", ""))
        if code:
            codes[code] += 1
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
                 len(seen_ambiguous), tuple(notes), tuple(modules.most_common()), tuple(codes.most_common()))


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


def what_reports_say(clues: Clues) -> list:
    """Plain lines about what the reports recorded, before any testing. Facts about the reports, never a cause."""
    lines = []
    total = sum(n for _, n in clues.modules)
    for name, n in clues.modules[:3]:
        owner = KNOWN_MODULES.get(name)
        if owner:
            lines.append(f"{n} of {total} recorded crashes happened inside {name}, which belongs to {owner}.")
    for code, n in clues.codes[:2]:
        meaning = KNOWN_CODES.get(code)
        if meaning:
            lines.append(f"{_times(n)} the reports recorded code {code.upper()}: {meaning}.")
    mod_modules = [(n, c) for n, c in clues.modules if n not in KNOWN_MODULES]
    if mod_modules and clues.fault_keys:
        lines.append("Windows recorded the failure inside a file that belongs to a mod. That is where it surfaced, "
                     "not proof that the mod caused it.")
    if clues.first_crash is not None and clues.crash_count > 1 and clues.last_crash != clues.first_crash:
        lines.append(f"{clues.crash_count} dated crashes between the first and the last report.")
    return lines


def _times(n: int) -> str:
    return "Once" if n == 1 else f"{n} times"


def cross_reference(units, clues: Clues, verdict) -> list:
    """Lines that compare the crash reports with what the owner's launches proved.

    Agreement is stated as agreement. Disagreement is stated too, and the launches win: a mod named in a report that
    stayed on during a clean run was named, not guilty. Nothing here changes the verdict."""
    names = {u.key: u.name for u in units}
    kind = getattr(verdict, "kind", "")
    groups = [tuple(g) for g in getattr(verdict, "groups", ()) or ()]
    found = {k for g in groups for k in g}
    lines = []
    if kind == "outside":
        lines += what_reports_say(clues)
        outside = [n for n, _ in clues.modules if n in KNOWN_MODULES]
        if outside:
            lines.append("The game crashed with every mod off, and the reports agree it is not a mod: "
                         f"the failures are recorded inside {', '.join(outside[:3])}. Updating or reinstalling that "
                         "part, and verifying the game files, is where to look.")
        elif clues.reports_read or clues.crash_count:
            lines.append("The reports do not name a mod either, which fits a crash that does not come from the mods.")
        return lines
    if kind not in ("culprit", "interaction", "multiple"):
        return what_reports_say(clues) if kind == "undetermined" else lines
    agreeing = [k for k in sorted(found) if clues.hits.get(k) or k in clues.fault_keys]
    for key in agreeing:
        n = clues.hits.get(key, 0)
        say = f"named in {_plural_reports(n)}" if n else "recorded as the crash location"
        if n and key in clues.fault_keys:
            say += " and recorded as the crash location"
        lines.append(f"The reports agree on {names.get(key, key)}: {say}.")
    if found and not agreeing:
        if clues.reports_read or clues.crash_count:
            lines.append("None of the mods your launches found are named in the crash reports. That happens "
                         "when a crash leaves no file name; the result stands on your launches.")
    off = set(found)                                       # switched off in the clean run: the found mods and what needs them
    while True:
        more = {u.key for u in units if u.key not in off and any(r in off for r in u.requires)}
        if not more:
            break
        off |= more
    elsewhere = [k for k in sorted(clues.hits, key=lambda k: (-clues.hits[k], k)) if k not in off and k in names]
    for key in elsewhere[:3]:
        lines.append(f"{names[key]} is named in {_plural_reports(clues.hits[key])} but was switched on during the run "
                     "that did not crash, so it was named, not the cause.")
    for name, n in clues.modules[:2]:
        owner = KNOWN_MODULES.get(name)
        if owner and not str(owner).startswith("Windows itself"):
            lines.append(f"{n} recorded crashes surfaced inside {name} ({owner}). A mod can still be the trigger, "
                         "for example with a texture or shader the driver chokes on.")
    return lines


def _plural_reports(n: int) -> str:
    return f"{n} crash report" + ("" if n == 1 else "s")
