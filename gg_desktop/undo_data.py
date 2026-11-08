"""Qt-free Undo Center model: what Game Grave recorded, and what each record can honestly offer.

Two sources, both written by the protected engines and only read here:
  * recovery records (one per file sent to the Windows Recycle Bin, with the last state Windows reported),
  * the activity log (scans, skipped cleanups, restores, settings changes).
A recycled file is not "reclaimed space" and a record is not a promise: restore needs Windows to hold exactly
one matching item and the original path to be free. Nothing in this module restores, deletes or edits a record.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import PureWindowsPath as Path
import time

CATEGORIES = ("Recycled", "Restored", "Skipped", "Steam", "Scans", "Settings", "Other")
CATEGORY_ICONS = {"Recycled": "trash", "Restored": "undo", "Skipped": "warning", "Steam": "game", "Scans": "search",
                  "Settings": "settings", "Other": "box"}
CATEGORY_COLORS = {"Recycled": "#ff3b57", "Restored": "#2ec4ff", "Skipped": "#f7b737", "Steam": "#9ca8bd",
                   "Scans": "#27dc74", "Settings": "#c26cff", "Other": "#9ca8bd"}
RANGES = ("All Time", "Last 24 Hours", "Last 7 Days", "Last 30 Days", "Custom Range")
RANGE_DAYS = {"All Time": 0, "Last 24 Hours": 1, "Last 7 Days": 7, "Last 30 Days": 30}
TONES = {"green": "#27dc74", "blue": "#2ec4ff", "amber": "#f7b737", "red": "#ff3b57", "grey": "#9ca8bd"}
DAY = 86400
MAX_HIDDEN = 5000

KIND_BY_EVENT = {
    "Manual recycled": "Recycled", "Auto recycled": "Recycled", "Restored from Recycle Bin": "Restored",
    "Cleanup skipped": "Skipped", "Steam uninstall opened": "Steam",
    "Scan completed": "Scans", "Mod inventory completed": "Scans", "Mod folder scan": "Scans", "Scan failed": "Scans",
    "Scan canceled": "Scans", "Automation enabled": "Settings", "Automation disabled": "Settings",
    "Mod folder added": "Settings", "Mod folder removed": "Settings",
}
STATE_STATUS = {
    "Restored": ("Restored", "blue"), "Available": ("Available", "green"), "Not checked": ("Not checked", "grey"),
    "Not found": ("Not found", "amber"), "Needs review": ("Needs review", "amber"),
}
TYPES = {
    "Video": {".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv", ".flv"},
    "Image": {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tga", ".dds"},
    "Archive": {".zip", ".7z", ".rar", ".tar", ".gz", ".iso"},
    "Log": {".log", ".txt", ".dmp"},
    "Config": {".ini", ".cfg", ".json", ".xml", ".toml", ".yaml", ".yml"},
    "Installer": {".exe", ".msi"},
}


@dataclass(eq=False)
class Entry:
    key: str
    category: str
    action: str
    name: str
    path: str
    size: int | None
    recorded: str
    when: float | None
    state: str
    status: str
    tone: str
    note: str
    recovery_id: str | None
    source: str
    session: str = ""

    @property
    def restorable(self):
        """A recovery record exists and it has not already been restored. Windows still has the last word."""
        return bool(self.recovery_id) and self.state != "Restored"

    @property
    def folder(self):
        return str(Path(self.path).parent) if self.path else ""

    @property
    def file_type(self):
        suffix = Path(self.path).suffix.casefold() if self.path else ""
        return next((name for name, values in TYPES.items() if suffix in values), "File" if suffix else "Event")


def timestamp(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError, OverflowError):
        return None


def _size(value):
    return value if type(value) is int and value >= 0 else None


def status_for_event(kind, result):
    text = str(result or "").strip()
    low = text.casefold()
    if any(word in low for word in ("fail", "error", "refused")):
        return "Failed", "red"
    if kind == "Cleanup skipped" or "skip" in low:
        return "Skipped", "amber"
    if kind == "Restored from Recycle Bin":
        return "Restored", "blue"
    if kind in {"Steam uninstall opened"}:
        return "Needs review", "amber"
    return (text[:16] or "Logged"), "grey"


def build_entries(records, events):
    """One Entry per recovery record and per activity event not already covered by a record."""
    sessions = {}
    for e in events:
        if isinstance(e, dict) and e.get("recovery_id") and e.get("session_id"):
            sessions.setdefault(str(e["recovery_id"]), str(e["session_id"]))
    entries, ids = [], set()
    restored_paths = set()
    for r in records:
        if not isinstance(r, dict) or not isinstance(r.get("id"), str) or not r["id"] or r["id"] in ids:
            continue
        ids.add(r["id"])
        state = str(r.get("state", "Not checked"))
        path = str(r.get("path", ""))
        status, tone = STATE_STATUS.get(state, (state[:16] or "Not checked", "grey"))
        when = timestamp(r.get("time"))
        if state == "Restored":
            restored_paths.add(path.casefold())
        entries.append(Entry("recovery:" + r["id"], "Restored" if state == "Restored" else "Recycled",
                             "Restored" if state == "Restored" else "Recycled", Path(path).name or path or "Unknown",
                             path, _size(r.get("size")), str(r.get("time", "")), when, state, status, tone,
                             str(r.get("note", "Availability must be checked in Windows.")), r["id"],
                             str(r.get("action", "Recovery record")), sessions.get(r["id"], "")))
    for index, e in enumerate(events):
        if not isinstance(e, dict) or e.get("recovery_id") in ids:
            continue
        kind = str(e.get("kind", "Activity"))
        if kind in {"Cleanup started", "Cleanup finished"}:
            continue
        path = str(e.get("path", "") or "")
        if kind == "Restored from Recycle Bin" and (path or str(e.get("details", ""))).casefold() in restored_paths:
            continue  # the record row already shows this restore
        status, tone = status_for_event(kind, e.get("result"))
        shown = path or str(e.get("details", ""))
        entries.append(Entry("audit:" + str(index), KIND_BY_EVENT.get(kind, "Other"), kind,
                             Path(path).name if path else shown[:100], path, _size(e.get("size_bytes")),
                             str(e.get("date", "")), timestamp(e.get("date")), str(e.get("result", "Recorded")), status,
                             tone, str(e.get("details", "")), None, str(e.get("source", "Activity log")),
                             str(e.get("session_id", ""))))
    entries.sort(key=lambda x: -(x.when or 0))
    return entries


def when_text(entry):
    if entry.when is None:
        return entry.recorded.replace("T", " ")[:16] or "Unknown"
    return time.strftime("%b %d, %Y %H:%M", time.localtime(entry.when))


def reversible_text(entry):
    """What Windows last reported, never a blanket promise."""
    if entry.state == "Restored":
        return "Already restored"
    if not entry.recovery_id:
        return "No recovery record"
    return {"Available": "Yes, Windows reported a matching item", "Not checked": "Not checked yet. Press Check Availability",
            "Not found": "No. Windows may have emptied the Recycle Bin",
            "Needs review": "Needs review before any restore"}.get(entry.state, "Not verified")


def run_members(entries, entry):
    """Entries from the same cleanup run (same session id), the entry itself included."""
    if not entry.session:
        return [entry]
    return [e for e in entries if e.session == entry.session]
