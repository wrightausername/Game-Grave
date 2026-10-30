"""Local-only, conservative scan history and storage-goal planning.

This module NEVER deletes, moves, or marks a file as safe to remove.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path

from core import config_dir, human_size

MAX_HISTORY = 40


def _history_file() -> Path:
    return config_dir() / "scan_history.json"


def load_history() -> list[dict]:
    try:
        records = json.loads(_history_file().read_text(encoding="utf-8"))
        return records[-MAX_HISTORY:] if isinstance(records, list) else []
    except (OSError, ValueError, TypeError):
        return []


def record_scan(games, mods, old_files, scanned_folder: str, drive_paths=()) -> dict:
    """Record observed inventory, not confirmed reclaimable space.

    File totals may overlap between game/mod paths and hardlinked directories.
    Therefore game bytes and mod bytes must never be added as an actual disk total.
    """
    sources: dict[str, dict] = {}
    for mod in mods:
        entry = sources.setdefault(mod.source, {"count": 0, "apparent_bytes": 0})
        entry["count"] += 1
        entry["apparent_bytes"] += max(0, mod.apparent_bytes)
    drives = {}
    for raw in drive_paths:
        try:
            path = Path(raw)
            usage = shutil.disk_usage(path)
            root = str(Path(path.anchor or path))
            drives[root] = {"total": usage.total, "used": usage.used, "free": usage.free}
        except (OSError, ValueError):
            continue
    point = {
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "epoch": int(time.time()),
        "games": len(games),
        "game_apparent_bytes": sum(max(0, g.size) for g in games),
        "mod_findings": len(mods),
        "mod_sources": sources,
        "old_files": len(old_files),
        "old_files_apparent_bytes": sum(max(0, f.size) for f in old_files),
        "old_files_root": str(scanned_folder),
        "drives": drives,
        "limitations": "Overlapping folders and hardlinks; sizes are not reclaimable-space estimates.",
    }
    history = load_history()
    history.append(point)
    history = history[-MAX_HISTORY:]
    destination = _history_file()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(".tmp")
    temp.write_text(json.dumps(history, indent=2), encoding="utf-8")
    temp.replace(destination)
    return point


def compare_scans(history: list[dict]) -> list[str]:
    if len(history) < 2:
        return ["Scan again later to see what changed. No background monitoring is required."]
    before, after = history[-2:]
    changes = []
    for field, label in (("games", "Steam game count"), ("mod_findings", "Mod/storage findings"),
                         ("old_files_apparent_bytes", "Old-file apparent size")):
        delta = after.get(field, 0) - before.get(field, 0)
        if not delta:
            continue
        wording = (human_size(abs(delta)) if field.endswith("bytes") else str(abs(delta)))
        changes.append(f"{label}: {'increased' if delta > 0 else 'decreased'} by {wording}.")
    for root, drive in after.get("drives", {}).items():
        previous = before.get("drives", {}).get(root)
        if previous and drive.get("free") != previous.get("free"):
            delta = drive["free"] - previous["free"]
            changes.append(f"{root} free space {'increased' if delta > 0 else 'decreased'} by {human_size(abs(delta))}.")
    if before.get("old_files_root") != after.get("old_files_root"):
        changes.append("Old-file scan location changed; its apparent size is not directly comparable.")
    return changes or ["No tracked changes between these scans. Untracked directories may still have changed."]


def make_room_plan(target_bytes: int, games, mods, old_files) -> dict:
    """Conservative suggestions, with zero *verified* savings until independently confirmed.

    Does not sum mod folders because mod storage often overlaps and can be hardlinked.
    """
    target_bytes = max(0, int(target_bytes))
    old_bytes = sum(max(0, x.size) for x in old_files)
    game_bytes = sum(max(0, x.size) for x in games)
    return {
        "target": target_bytes,
        "verified_reclaimable": 0,
        "options": [
            {"name": "Review old files", "apparent_bytes": old_bytes, "count": len(old_files),
             "note": "Review individual files. Moving to Recycle Bin does not free disk space immediately."},
            {"name": "Review Steam games", "apparent_bytes": game_bytes, "count": len(games),
             "note": "Use Steam's uninstall flow. This is all installed-game size, not a deletion recommendation."},
            {"name": "Inspect mods and hidden storage", "apparent_bytes": None, "count": len(mods),
             "note": "Overlapping, active and hardlinked mod files are excluded from space-savings estimates."},
        ],
        "warning": "Nothing has been confirmed safe to remove. Every action requires your review.",
    }
