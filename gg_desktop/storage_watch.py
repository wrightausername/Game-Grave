"""Privacy-first, no-service storage trend on Ready Room visits.

Samples only fixed local game drives when the user opens Ready Room and no
game is detected. No filesystem crawl, file names, user activity logs,
network requests or always-on background process.
"""
from __future__ import annotations

from collections import namedtuple
import ctypes
import json
import os
from pathlib import Path
import shutil
import time

from core import config_dir
from performance_guard import GameActivityDetector

MAX_HISTORY = 60
SAMPLE_INTERVAL = 6 * 3600
MAX_DATA = 75_000


def _path() -> Path:
    return config_dir() / "ready_room_drive_history.json"


def load_history() -> dict[str, list[dict]]:
    try:
        target = _path()
        if (not target.is_file() or target.is_symlink() or
                target.stat().st_size > MAX_DATA):
            return {}
        obj = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(obj, dict):
            return {}
        return {str(drive): [row for row in entries[:MAX_HISTORY]
                             if isinstance(row, dict) and
                             type(row.get("free")) is int and
                             type(row.get("at")) is int]
                for drive, entries in list(obj.items())[:8]
                if isinstance(entries, list)}
    except (OSError, UnicodeError, ValueError, TypeError):
        return {}


def _local_drive_roots(games) -> list[str]:
    output = []
    for game in games:
        root = str(getattr(game, "install_path", ""))
        anchor = Path(root).anchor
        if not anchor or anchor in output:
            continue
        if os.name == "nt":
            try:
                if ctypes.windll.kernel32.GetDriveTypeW(str(anchor)) != 3:
                    continue
            except (OSError, ValueError, AttributeError):
                continue
        output.append(anchor)
        if len(output) >= 8:
            break
    return output


def sample_on_ready_room_open(games, *, active=None, clock=time.time,
                              disk_usage=shutil.disk_usage) -> dict:
    """Read only bounded OS disk counters; never scan file/folder trees."""
    old = load_history()
    detector = active or GameActivityDetector()
    if detector.active():
        return old
    now = int(clock())
    changed = False
    for drive in _local_drive_roots(games):
        if detector.active():
            break
        previous = old.get(drive, [])
        if previous and now - previous[0]["at"] < SAMPLE_INTERVAL:
            continue
        try:
            usage = disk_usage(drive)
        except (OSError, ValueError):
            continue
        if usage.total <= 0 or not 0 <= usage.free <= usage.total:
            continue
        old[drive] = [
            {"at": now, "free": int(usage.free), "total": int(usage.total)},
            *previous,
        ][:MAX_HISTORY]
        changed = True
    if changed:
        dest = _path()
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".new")
        try:
            tmp.write_text(json.dumps(old), encoding="utf-8")
            os.replace(tmp, dest)
        finally:
            tmp.unlink(missing_ok=True)
    return old


def describe_storage_history(history: dict) -> list[str]:
    from core import human_size
    lines = []
    for drive, rows in list(sorted(history.items()))[:8]:
        if not rows:
            continue
        latest = rows[0]
        current = human_size(latest["free"])
        if len(rows) < 2:
            message = "First sample; no trend available yet."
        else:
            delta = latest["free"] - rows[1]["free"]
            direction = "more" if delta >= 0 else "less"
            message = (human_size(abs(delta)) + " " + direction +
                       " free than the previous sampled visit.")
        lines.append(str(drive) + "  •  " + current + " free  •  " + message)
    return lines
