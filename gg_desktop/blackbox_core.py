"""Black Box: after a game crashes, collect what Windows and the game folder actually recorded, plus what changed
nearby, into one report the owner can read, copy or send to a friend or the game's support.

Honesty rules: this only reports what is on disk or in the Windows Application event log. It cannot say why a game
crashed, and it cannot know when the last good launch was, so "what changed" uses a fixed look-back window and says
so. Nothing here goes online, runs the game or changes a game file. The report hides the Windows user name.
"""
from __future__ import annotations

import re
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOOKBACK_DAYS = 7           # "what changed" window before the newest crash
LOG_DAYS = 30               # how far back crash logs and dumps are listed
MAX_SCAN_FILES = 4000
MAX_EVENTS = 60
MAX_SHOWN = 12
LOG_SUFFIXES = (".dmp", ".mdmp", ".log", ".txt", ".crash", ".rpt")
CRASH_WORDS = ("crash", "dump", "error", "exception", "minidump", "report")
QUIET_SUFFIXES = (".dmp", ".mdmp", ".log", ".txt", ".crash", ".rpt")


@dataclass
class Crash:
    when: datetime
    exe: str
    module: str
    code: str
    offset: str
    path: str = ""


@dataclass
class FileFact:
    path: str          # relative to the game folder
    when: datetime
    size: int


@dataclass
class Report:
    game: str
    folder: str
    made: datetime
    crashes: list = field(default_factory=list)
    logs: list = field(default_factory=list)
    changed: list = field(default_factory=list)
    changed_total: int = 0
    grave: list = field(default_factory=list)       # (when text, plain sentence) from Game Grave's own log
    scan_limited: bool = False
    event_log_ok: bool = True
    event_log_note: str = ""


# ------------------------------------------------------------------ Windows event log
def query_events(limit: int = MAX_EVENTS) -> str:
    """Raw XML of recent Application Error events. Returns '' when the log cannot be read (not Windows, no access)."""
    command = ["wevtutil", "qe", "Application", "/q:*[System[(EventID=1000)]]", f"/c:{limit}", "/rd:true", "/f:xml"]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=25, creationflags=flags)
    except (OSError, subprocess.SubprocessError):
        raise OSError("The Windows event log could not be read on this PC.")
    if done.returncode != 0:
        raise OSError("The Windows event log could not be read on this PC.")
    return done.stdout[:4_000_000]


def parse_events(xml_text: str) -> list[Crash]:
    """Application Error (event 1000) records. Anything malformed is skipped, never guessed at."""
    cleaned = re.sub(r'\sxmlns="[^"]+"', "", xml_text or "")
    try:
        root = ET.fromstring("<Events>" + cleaned + "</Events>")
    except ET.ParseError:
        return []
    crashes = []
    for event in root.findall("Event"):
        stamp = event.find("./System/TimeCreated")
        data = [(d.text or "").strip() for d in event.findall("./EventData/Data")]
        if stamp is None or len(data) < 8:
            continue
        when = _parse_loose(stamp.get("SystemTime", ""))
        if when is None:
            continue
        crashes.append(Crash(when.astimezone().replace(tzinfo=None), data[0], data[3], data[6], data[7],
                             data[10] if len(data) > 10 else ""))
    return crashes


def _parse_loose(text: str):
    match = re.match(r"(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)", text or "")
    if not match:
        return None
    return datetime(*(int(g) for g in match.groups()), tzinfo=timezone.utc)


def exe_names(folder: Path) -> set[str]:
    """Names of programs inside the game folder (top two levels)."""
    names = set()
    try:
        for entry in folder.iterdir():
            if entry.suffix.lower() == ".exe":
                names.add(entry.name.casefold())
            elif entry.is_dir():
                try:
                    for inner in entry.iterdir():
                        if inner.suffix.lower() == ".exe":
                            names.add(inner.name.casefold())
                except OSError:
                    continue
            if len(names) > 300:
                break
    except OSError:
        pass
    return names


def crashes_for(crashes: list[Crash], folder: Path) -> list[Crash]:
    """Only crashes whose program lives in the game folder, or that has the same name as a program in it."""
    root = str(folder).casefold().rstrip("\\/")
    names = exe_names(folder)
    kept = []
    for crash in crashes:
        inside = bool(crash.path) and crash.path.casefold().startswith(root)
        if inside or (crash.exe.casefold() in names):
            kept.append(crash)
    return kept


# ------------------------------------------------------------------ game folder
def _walk(folder: Path, depth: int = 3):
    """Yield files up to a depth, bounded, so a huge game folder cannot freeze the app."""
    count = 0
    stack = [(folder, 0)]
    while stack:
        current, level = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            count += 1
            if count > MAX_SCAN_FILES:
                yield None
                return
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir():
                    if level < depth:
                        stack.append((entry, level + 1))
                elif entry.is_file():
                    yield entry
            except OSError:
                continue


def scan_folder(folder: Path, newest_crash: datetime | None, now: datetime):
    """Crash logs and dumps from the last 30 days, and other files changed in the week before the newest crash."""
    logs, changed, limited = [], [], False
    log_cutoff = now - timedelta(days=LOG_DAYS)
    window_end = newest_crash or now
    window_start = window_end - timedelta(days=LOOKBACK_DAYS)
    for entry in _walk(folder):
        if entry is None:
            limited = True
            break
        try:
            info = entry.stat()
        except OSError:
            continue
        when = datetime.fromtimestamp(info.st_mtime)
        rel = str(entry.relative_to(folder))
        lowered = entry.name.casefold()
        looks_like_crash = lowered.endswith((".dmp", ".mdmp", ".crash", ".rpt")) or (
            lowered.endswith(LOG_SUFFIXES) and any(w in lowered or w in rel.casefold() for w in CRASH_WORDS))
        if looks_like_crash and when >= log_cutoff:
            logs.append(FileFact(rel, when, info.st_size))
        elif not lowered.endswith(QUIET_SUFFIXES) and window_start <= when <= window_end:
            changed.append(FileFact(rel, when, info.st_size))
    logs.sort(key=lambda f: f.when, reverse=True)
    changed.sort(key=lambda f: f.when, reverse=True)
    return logs, changed, limited


def grave_changes(events: list[dict], game: str, folder: Path, newest_crash: datetime | None, now: datetime):
    """Game Grave's own log lines about this game in the same window. Only what Game Grave itself did."""
    end = newest_crash or now
    start = end - timedelta(days=LOOKBACK_DAYS)
    name, root = game.casefold(), str(folder).casefold()
    lines = []
    for event in events:
        text = f"{event.get('details', '')} {event.get('path', '')}".casefold()
        if name not in text and root not in text:
            continue
        try:
            when = datetime.fromisoformat(str(event.get("date", ""))).replace(tzinfo=None)
        except ValueError:
            continue
        if start <= when <= end:
            lines.append((when, f"{event.get('kind', 'event').replace('_', ' ')}: {str(event.get('details', ''))[:140]}"))
    lines.sort(key=lambda item: item[0], reverse=True)
    return lines


# ------------------------------------------------------------------ build and write
def build_report(game: str, folder, *, events_xml: str | None = None, activity: list | None = None,
                 now: datetime | None = None) -> Report:
    now = now or datetime.now()
    folder = Path(folder)
    report = Report(game, str(folder), now)
    try:
        xml_text = query_events() if events_xml is None else events_xml
    except OSError as problem:
        xml_text, report.event_log_ok, report.event_log_note = "", False, str(problem)
    report.crashes = sorted(crashes_for(parse_events(xml_text), folder), key=lambda c: c.when, reverse=True)
    newest = report.crashes[0].when if report.crashes else None
    if folder.is_dir():
        report.logs, changed, report.scan_limited = scan_folder(folder, newest, now)
        report.changed_total = len(changed)
        report.changed = changed[:MAX_SHOWN]
    report.grave = grave_changes(activity or [], game, folder, newest, now)
    return report


def hide_user(text: str) -> str:
    """Replace the Windows user's folder name so a shared report does not carry it."""
    return re.sub(r"(?i)([A-Z]:\\Users\\)[^\\/\r\n]+", r"\1<user>", text)


def render(report: Report) -> str:
    stamp = lambda d: d.strftime("%Y-%m-%d %H:%M")
    out = [f"Game Grave Black Box report: {report.game}", f"Made {stamp(report.made)} on this PC.",
           f"Game folder: {report.folder}", "",
           "This report lists only what Windows and the game folder recorded. It does not say why the game crashed.", ""]
    out.append("Crashes Windows recorded for this game")
    if not report.event_log_ok:
        out.append(f"  {report.event_log_note}")
    elif not report.crashes:
        out.append("  None found in the Windows Application log for this game.")
    for crash in report.crashes[:MAX_SHOWN]:
        out.append(f"  {stamp(crash.when)}  {crash.exe}  in {crash.module or 'unknown module'}  "
                   f"code {crash.code}  offset {crash.offset}")
    if len(report.crashes) > MAX_SHOWN:
        out.append(f"  and {len(report.crashes) - MAX_SHOWN} older")
    out += ["", f"Crash logs and dumps in the game folder (last {LOG_DAYS} days)"]
    if not report.logs:
        out.append("  None found.")
    for item in report.logs[:MAX_SHOWN]:
        out.append(f"  {stamp(item.when)}  {item.path}  ({_size(item.size)})")
    if len(report.logs) > MAX_SHOWN:
        out.append(f"  and {len(report.logs) - MAX_SHOWN} more")
    anchor = "the newest crash" if report.crashes else "today"
    out += ["", f"Files changed in the game folder in the {LOOKBACK_DAYS} days before {anchor}",
            "  Game Grave cannot tell when the last good launch was, so it uses a fixed window. An update, a mod or the",
            "  game itself can all change files."]
    if not report.changed:
        out.append("  None found.")
    for item in report.changed:
        out.append(f"  {stamp(item.when)}  {item.path}")
    if report.changed_total > len(report.changed):
        out.append(f"  and {report.changed_total - len(report.changed)} more")
    out += ["", f"Changes Game Grave itself made in the same {LOOKBACK_DAYS} days"]
    if not report.grave:
        out.append("  None recorded.")
    for when, line in report.grave[:MAX_SHOWN]:
        out.append(f"  {stamp(when)}  {line}")
    if report.scan_limited:
        out += ["", f"The game folder is large, so only the first {MAX_SCAN_FILES:,} items were checked."]
    return hide_user("\n".join(out)) + "\n"


def _size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} B"


def blackbox_dir() -> Path:
    import core
    return core.config_dir() / "blackbox"


def save_report(report: Report, text: str | None = None, root: Path | None = None) -> Path:
    root = Path(root) if root else blackbox_dir()
    root.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^A-Za-z0-9]+", "-", report.game).strip("-")[:40] or "game"
    path = root / f"{slug}-{report.made.strftime('%Y%m%d-%H%M%S')}.txt"
    path.write_text(text if text is not None else render(report), encoding="utf-8")
    return path
