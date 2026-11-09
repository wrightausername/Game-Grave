"""Black Box: what Windows recorded when a game crashed, and what changed before it. No Qt in this module.

Honesty rules:
* Crashes come only from Windows' own Application log (event 1000, "Application Error"), read when the owner
  opens Black Box. Game Grave does not watch games in the background.
* A file that changed before a crash is a lead, not a cause. Black Box never says which file "caused" a crash.
* Reports are written only where the owner saves them, with the Windows user name and profile path replaced, so
  they can be posted to a mod author or a Discord without showing who you are.
* Black Box reads. It never moves, changes or deletes a file.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from gg_desktop.mod_shield import _is_link  # symlinks and Windows junctions are not followed

EVENT_QUERY = "*[System[Provider[@Name='Application Error'] and (EventID=1000)]]"
EVENT_LIMIT = 200
CHANGE_WINDOW_DAYS = 7
CHANGE_LIMIT = 40
WALK_LIMIT = 60_000
NS = "{http://schemas.microsoft.com/win/2004/08/events/event}"
# Event 1000 data, in Windows' order.
FIELDS = ("app", "app_version", "app_stamp", "module", "module_version", "module_stamp", "exception", "offset",
          "pid", "process_start", "app_path", "module_path", "report_id")
EXCEPTIONS = {
    "c0000005": "access violation (the program read or wrote memory it did not own)",
    "c0000409": "stack buffer overrun (the program stopped itself after detecting corrupted memory)",
    "c000001d": "illegal instruction (often a CPU feature the program expected is missing)",
    "c00000fd": "stack overflow",
    "80000003": "breakpoint (the program stopped on purpose, often a deliberate crash handler)",
    "e06d7363": "unhandled C++ exception",
    "c0000374": "heap corruption",
    "c0000142": "the program could not start (a DLL failed to initialise)",
}
WINDOWS_MODULES = frozenset({"ntdll.dll", "kernelbase.dll", "kernel32.dll", "ucrtbase.dll", "msvcrt.dll",
                             "vcruntime140.dll", "msvcp140.dll", "user32.dll", "win32u.dll", "combase.dll"})


@dataclass
class Crash:
    when: datetime
    app: str
    app_version: str
    module: str
    module_version: str
    exception: str
    app_path: str
    module_path: str
    report_id: str = ""
    game: str = ""
    game_path: str = ""

    def exception_text(self):
        code = self.exception.casefold().removeprefix("0x")
        meaning = EXCEPTIONS.get(code)
        return f"0x{code} ({meaning})" if meaning else f"0x{code}"

    def module_note(self):
        name = self.module.casefold()
        if not self.module or name == self.app.casefold():
            return "The crash happened inside the game's own program."
        if name in WINDOWS_MODULES:
            return (f"The crash surfaced in {self.module}, a Windows file. That usually means the real fault happened "
                    "earlier in the game or a mod, so the list of changes below matters more.")
        if self.game_path and _inside(self.module_path, self.game_path):
            return f"The crash happened in {self.module}, a file inside the game's folder. Check whether a mod added it."
        return f"The crash happened in {self.module} ({self.module_path or 'location not recorded'})."


@dataclass
class Change:
    path: str
    when: datetime
    size: int


@dataclass
class Findings:
    crash: Crash
    changes: list = field(default_factory=list)
    drivers: list = field(default_factory=list)
    truncated: bool = False


def _key(path):
    return os.path.normcase(str(path).replace("/", "\\")).rstrip("\\")


def _inside(path, folder):
    p, f = _key(path), _key(folder)
    return bool(p and f) and (p == f or p.startswith(f + "\\"))


def query_args(limit=EVENT_LIMIT):
    return ["wevtutil", "qe", "Application", "/q:" + EVENT_QUERY, "/c:" + str(int(limit)), "/rd:true", "/f:xml"]


def _parse_time(text):
    if not text:
        return None
    text = text.strip().replace("Z", "+00:00")
    match = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?(.*)", text)
    if not match:
        return None
    stamp = datetime.fromisoformat(match.group(1) + (match.group(3) or ""))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone().replace(tzinfo=None)


def parse_events(xml_text):
    """Crashes from wevtutil's XML (several <Event> elements, not one document)."""
    crashes = []
    for chunk in re.findall(r"<Event[\s>].*?</Event>", xml_text or "", flags=re.S):
        try:
            node = ET.fromstring(chunk)
        except ET.ParseError:
            continue
        created = node.find(f"{NS}System/{NS}TimeCreated")
        when = _parse_time(created.get("SystemTime") if created is not None else "")
        values = [(d.text or "").strip() for d in node.findall(f"{NS}EventData/{NS}Data")]
        if when is None or len(values) < 11:
            continue
        data = dict(zip(FIELDS, values + [""] * (len(FIELDS) - len(values))))
        crashes.append(Crash(when, data["app"], data["app_version"], data["module"], data["module_version"],
                             data["exception"], data["app_path"], data["module_path"], data["report_id"]))
    crashes.sort(key=lambda c: c.when, reverse=True)
    return crashes


def match_games(crashes, games):
    """Tie a crash to a game only when the crashed program lives inside that game's recorded install folder."""
    installs = [(g.name, g.install_path) for g in games if getattr(g, "install_path", "")]
    installs.sort(key=lambda gi: -len(gi[1]))
    for crash in crashes:
        for name, path in installs:
            if _inside(crash.app_path, path):
                crash.game, crash.game_path = name, path
                break
    return crashes


def read_crashes(runner, games, *, limit=EVENT_LIMIT):
    result = runner.run(query_args(limit), timeout=60, limit=4 * 1024 * 1024)
    if result.code != 0 and not result.output.strip().startswith("<"):
        raise OSError("Windows did not return its crash log: " + (result.output.strip()[:200] or f"code {result.code}"))
    return match_games(parse_events(result.output), games)


def recent_changes(folders, before, *, days=CHANGE_WINDOW_DAYS, limit=CHANGE_LIMIT, walk_limit=WALK_LIMIT):
    """Files in these folders that changed in the days before the crash, newest first. Reads only."""
    start = (before - timedelta(days=days)).timestamp()
    end = before.timestamp() + 60
    found, walked, truncated = [], 0, False
    for folder in folders:
        stack = [str(folder)]
        while stack and not truncated:
            current = stack.pop()
            try:
                with os.scandir(current) as entries:
                    items = list(entries)
            except OSError:
                continue
            for entry in items:
                try:
                    if _is_link(entry):
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
                        continue
                    st = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                walked += 1
                if walked >= walk_limit:
                    truncated = True
                    break
                if start <= st.st_mtime <= end:
                    found.append(Change(entry.path, datetime.fromtimestamp(st.st_mtime), int(st.st_size)))
    found.sort(key=lambda c: c.when, reverse=True)
    return found[:limit], truncated


def driver_changes(history, before, *, days=CHANGE_WINDOW_DAYS):
    """Graphics drivers Game Grave first saw in the days before the crash (from Exhume's history)."""
    start = before - timedelta(days=days)
    changed = []
    for entry in history:
        try:
            seen = datetime.strptime(entry.first_seen, "%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            continue
        if start <= seen <= before:
            changed.append(entry)
    return changed


def investigate(crash, history=(), extra_folders=()):
    folders = [crash.game_path] if crash.game_path else []
    folders += [f for f in extra_folders if f and not any(_inside(f, g) for g in folders)]
    changes, truncated = recent_changes(folders, crash.when) if folders else ([], False)
    return Findings(crash, changes, driver_changes(history, crash.when), truncated)


# ------------------------------------------------------------------ the shareable report
def scrubber(env=None):
    env = os.environ if env is None else env
    pairs = []
    profile = env.get("USERPROFILE") or str(Path.home())
    user = env.get("USERNAME") or Path(profile).name
    if profile:
        pairs.append((re.compile(re.escape(profile), re.IGNORECASE), "%USERPROFILE%"))
    if user and len(user) >= 3:
        pairs.append((re.compile(r"(?<![A-Za-z0-9])" + re.escape(user) + r"(?![A-Za-z0-9])", re.IGNORECASE), "<user>"))
    host = env.get("COMPUTERNAME")
    if host and len(host) >= 3:
        pairs.append((re.compile(r"(?<![A-Za-z0-9])" + re.escape(host) + r"(?![A-Za-z0-9])", re.IGNORECASE), "<pc>"))

    def scrub(text):
        for pattern, replacement in pairs:
            text = pattern.sub(replacement, text)
        return text
    return scrub


def report_text(findings, *, version="", scrub=None, generated=None):
    scrub = scrub or scrubber()
    crash = findings.crash
    lines = [
        "Game Grave Black Box report",
        f"Generated: {(generated or datetime.now()).strftime('%Y-%m-%d %H:%M')}" + (f" by Game Grave {version}" if version else ""),
        "",
        f"Game: {crash.game or 'Not matched to a scanned game'}",
        f"Crashed program: {crash.app} {crash.app_version}".rstrip(),
        f"When: {crash.when.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Faulting module: {crash.module} {crash.module_version}".rstrip(),
        f"Module path: {crash.module_path or 'not recorded'}",
        f"Exception: {crash.exception_text()}",
        f"Note: {crash.module_note()}",
        "",
        f"Files that changed in the {CHANGE_WINDOW_DAYS} days before the crash ({len(findings.changes)}"
        f"{'+' if findings.truncated else ''}):",
    ]
    if findings.changes:
        for change in findings.changes:
            lines.append(f"  {change.when.strftime('%Y-%m-%d %H:%M')}  {change.path}")
    else:
        lines.append("  None found in the game's folder.")
    lines.append("")
    lines.append("Graphics drivers first seen in that time:")
    if findings.drivers:
        for entry in findings.drivers:
            lines.append(f"  {entry.first_seen}  {entry.adapter} {entry.driver().friendly_version}")
    else:
        lines.append("  None recorded by Game Grave.")
    lines += ["", "A file or driver that changed before a crash is a lead, not proof of the cause.",
              "User name, PC name and profile folder are replaced in this report."]
    return scrub("\n".join(lines)) + "\n"


def report_name(crash):
    """A file name Windows accepts, for example black-box-Space-Marine-2-20261108-2015.txt."""
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", crash.game or crash.app or "crash").strip("-.")[:60] or "crash"
    return f"black-box-{base}-{crash.when:%Y%m%d-%H%M}.txt"


def summary(crashes):
    games = [c for c in crashes if c.game]
    if not crashes:
        return "Windows has no recent application crashes in its log."
    return (f"Windows recorded {len(crashes):,} application crash{'es' if len(crashes) != 1 else ''}; "
            f"{len(games):,} {'are' if len(games) != 1 else 'is'} in a scanned game's folder. Nothing was changed.")
