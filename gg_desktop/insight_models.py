"""Read models for storage, captures, Game DNA and append-only recovery history.

These models never grant deletion or restore authority. Unknown relationships,
access dates, physical allocation and recovery availability remain unknown.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import time

from gg_desktop.models import _path_key

STORAGE_TYPES = ("Caches", "Shader Cache", "Config / Settings", "Logs / Reports", "Temporary Files", "Other")
STORAGE_COLORS = ("#16bdf5", "#ffc326", "#ef47ac", "#568aff", "#bd5bdf", "#a8b5c6")
OVERVIEW_CATEGORIES = (("Old Files", "#f0bc78"), ("Other Storage", "#40d8d3"),
                       ("Mods", "#ce8fe5"), ("Captures", "#778dff"))


@dataclass(frozen=True)
class StorageItem:
    key: str
    name: str
    path: str
    category: str
    size: int
    items: int
    source: str
    evidence: str
    old_file: object = None


def storage_items(inventory):
    candidates = []
    for m in inventory.mods:
        text = (str(m.source) + " " + str(m.status)).casefold()
        kind = ("Shader Cache" if "shader cache" in text else "Caches" if "cache" in text else
                "Config / Settings" if "configuration" in text else None)
        if kind:
            candidates.append(StorageItem(_path_key(m.path), m.name, m.path, kind,
                max(0, m.apparent_bytes), max(0, m.file_count), m.source,
                m.status + ". " + m.advice))
    for f in inventory.files:
        suffix = Path(f.path).suffix.casefold()
        kind = ("Logs / Reports" if suffix in {".log", ".dmp"} else
                "Temporary Files" if suffix == ".tmp" else
                "Config / Settings" if suffix in {".ini", ".cfg", ".json", ".yaml", ".toml"} else None)
        if kind:
            candidates.append(StorageItem(_path_key(f.path), Path(f.path).name, f.path,
                kind, max(0, f.size), 1, "Selected file folder · game unverified",
                "Extension-based file type. Age and filename do not establish disuse or safe removal.", f))
    # A parent storage record already includes its descendants. Do not charge
    # those reported bytes again; hardlink/physical allocation is still unknown.
    output = []
    for item in sorted(candidates, key=lambda r: (r.key.count("\\"), r.key)):
        if not any(item.key == p.key or item.key.startswith(p.key.rstrip("\\") + "\\") for p in output):
            output.append(item)
    return output


def overview_storage_segments(inventory):
    """Disjoint reported bytes, with the same categories in the pie and legend.

    Capture and cache records take precedence over generic file/mod records at
    the same path. A measured parent already includes its descendants; unknown
    sizes, game install totals and recycle history are not pie slices.
    """
    rows = [(r.record.path, r.record.size, "Captures", 0) for r in capture_items(inventory)]
    rows += [(r.path, r.size, "Other Storage", 1) for r in storage_items(inventory)]
    rows += [(r.path, r.apparent_bytes, "Mods", 2) for r in inventory.mods]
    rows += [(r.path, r.size, "Old Files", 3) for r in inventory.files]
    candidates = [(_path_key(path), size, category, priority) for path, size, category, priority in rows
                  if path and type(size) is int and size > 0]
    accepted, totals = set(), dict.fromkeys((name for name, _ in OVERVIEW_CATEGORIES), 0)
    for key, size, category, priority in sorted(candidates, key=lambda r: (r[0].count("\\"), r[0], r[3])):
        if key in accepted:
            continue
        parts = key.split("\\")
        if any("\\".join(parts[:i]) in accepted for i in range(1, len(parts))):
            continue
        accepted.add(key)
        totals[category] += size
    return [(name, totals[name], color) for name, color in OVERVIEW_CATEGORIES]


def capture_identity(record):
    return (str(record.path), record.size, record.modified, record.device,
            record.inode, record.modified_ns)


def capture_owner(record, steam):
    path = _path_key(record.path)
    for game in steam:
        prefix = _path_key(str(Path(game.library) / "userdata")).rstrip("\\") + "\\"
        if not path.startswith(prefix) or not str(game.app_id).isdecimal():
            continue
        parts = path[len(prefix):].split("\\")
        if (len(parts) >= 6 and parts[0].isdecimal() and parts[1:3] == ["760", "remote"]
                and parts[3] == str(game.app_id) and parts[4] == "screenshots"):
            return game.name, "Steam capture path / app ID"
    return "Unverified", "Local capture discovery"


@dataclass(frozen=True)
class CaptureItem:
    record: object
    kind: str
    game: str
    source: str

    @property
    def key(self):
        return capture_identity(self.record)


def capture_items(inventory):
    output, seen = [], set()
    for kind, files in (("Screenshots", inventory.screenshots), ("Recordings", inventory.recordings)):
        for f in files:
            key = _path_key(f.path)
            if key in seen:
                continue
            seen.add(key)
            game, source = capture_owner(f, inventory.steam)
            output.append(CaptureItem(f, kind, game, source))
    return output


def grave_bucket(entry):
    category = entry.category.casefold()
    if "installed game" in category:
        return "Games"
    if "download" in category:
        return "Downloads"
    if "screenshot" in category or "recording" in category:
        return "Captures"
    if "cache" in category:
        return "Caches"
    return "Mods / Addons"


def timestamp(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError, OverflowError):
        return None


@dataclass(frozen=True)
class HistoryItem:
    key: str
    action: str
    path: str
    size: int | None
    recorded: str
    state: str
    note: str
    recovery_id: str | None
    source: str


def history_items(records, events):
    output = []
    ids = set()
    for r in records:
        if not isinstance(r, dict) or not isinstance(r.get("id"), str) or not r["id"] or r["id"] in ids:
            continue
        ids.add(r["id"])
        size = r.get("size")
        output.append(HistoryItem("recovery:" + r["id"], "Recycled", str(r.get("path", "Unknown")),
            size if type(size) is int and size >= 0 else None, str(r.get("time", "")),
            str(r.get("state", "Not checked")), str(r.get("note", "Availability must be checked in Windows.")),
            r["id"], str(r.get("action", "Recovery record"))))
    for i, e in enumerate(events):
        if not isinstance(e, dict) or e.get("recovery_id") in ids or e.get("kind") in {"Cleanup started", "Cleanup finished"}:
            continue
        kind = str(e.get("kind", "Activity"))
        size = e.get("size_bytes")
        output.append(HistoryItem("audit:" + str(i), kind, str(e.get("path", "")),
            size if type(size) is int and size >= 0 else None, str(e.get("date", "")),
            str(e.get("result", "Recorded")), str(e.get("details", "")), None,
            str(e.get("source", "Activity log"))))
    return sorted(output, key=lambda r: -(timestamp(r.recorded) or 0))


def dna_footprint(game, assets):
    """Keep nested mod bytes inside the reported install, not an extra charge."""
    install = _path_key(game.install_path).rstrip("\\")
    external, seen = [], []
    for asset in sorted(assets, key=lambda a: _path_key(a["path"]).count("\\")):
        path = _path_key(asset["path"])
        if path == install or path.startswith(install + "\\"):
            continue
        if any(path == p or path.startswith(p + "\\") for p in seen):
            continue
        seen.append(path)
        external.append(asset)
    known = game.size_bytes
    outside = sum(a["apparent_bytes"] for a in external)
    segments = [("Game install", known, "#ff2346")] if known is not None else []
    if external:
        segments.append(("External linked storage", outside, "#c562e6"))
    total = (known or 0) + outside
    return total, segments, external
