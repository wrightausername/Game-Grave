"""Local-only, explicitly user-started Ready Room gaming session journal.

These are *user-timed* sessions, not verified game-process time. A launch URL
being accepted is not proof the game started. We never inject into processes,
poll foreground windows, detect keystrokes or upload game history. All
statistics are computed only from completed local records. Incomplete sessions
are not counted; very old timers are rejected rather than inventing playtime.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
import uuid

from core import config_dir

SCHEMA = 1
MAX_HISTORY = 2000
MAX_FILE_BYTES = 1_000_000
MAX_SESSION_SECONDS = 18 * 3600


def _journal_path() -> Path:
    return config_dir() / "ready_room_sessions.json"


def _active_path() -> Path:
    return config_dir() / "ready_room_session_active.json"


def _read_json(path: Path, max_bytes=MAX_FILE_BYTES):
    try:
        if not path.is_file() or path.is_symlink() or path.stat().st_size > max_bytes:
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, TypeError):
        return None


def _atomic(path: Path, value) -> None:
    target = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if len(target.encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError("Session history reached its bounded storage limit.")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".new")
    try:
        tmp.write_text(target, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _valid_session(value: object) -> bool:
    return (isinstance(value, dict)
            and isinstance(value.get("id"), str)
            and isinstance(value.get("key"), str)
            and isinstance(value.get("name"), str)
            and type(value.get("start")) is int
            and type(value.get("end")) is int
            and 0 < value["end"] - value["start"] <= MAX_SESSION_SECONDS
            and len(value["key"]) <= 900
            and len(value["name"]) <= 180)


def read_sessions() -> list[dict]:
    data = _read_json(_journal_path())
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return []
    entries = data.get("entries", [])
    if not isinstance(entries, list):
        return []
    seen = set()
    valid = []
    for row in entries[:MAX_HISTORY]:
        if _valid_session(row) and row["id"] not in seen:
            seen.add(row["id"])
            valid.append(row)
    return sorted(valid, key=lambda row: row["start"], reverse=True)


def active_session() -> dict | None:
    row = _read_json(_active_path(), 12_000)
    if not isinstance(row, dict) or row.get("schema") != SCHEMA:
        return None
    if (not isinstance(row.get("id"), str) or
            not isinstance(row.get("key"), str) or
            not isinstance(row.get("name"), str) or
            type(row.get("start")) is not int):
        return None
    return row


def start_session(game, *, at: int | None = None, mode="manual") -> dict:
    if active_session() is not None:
        raise ValueError("Finish or discard the current tracked session first.")
    if "Installed" not in str(getattr(game, "status", "")):
        raise ValueError("Choose an installed game verified by the scan first.")
    key = str(getattr(game, "key", ""))
    name = str(getattr(game, "name", ""))
    if not key or not name:
        raise ValueError("Game identity is missing.")
    timestamp = int(time.time()) if at is None else int(at)
    row = {
        "schema": SCHEMA, "id": str(uuid.uuid4()),
        "key": key[:900], "name": name[:180],
        "launcher": str(getattr(game, "launcher", ""))[:80],
        "start": timestamp, "mode": str(mode)[:35],
        "source": "manual session timer; game execution not verified",
    }
    _atomic(_active_path(), row)
    return row


def finish_session(*, at: int | None = None, discard=False) -> dict | None:
    entry = active_session()
    if entry is None:
        raise ValueError("No active Ready Room session timer.")
    now = int(time.time()) if at is None else int(at)
    elapsed = now - entry["start"]
    if not discard and not 0 < elapsed <= MAX_SESSION_SECONDS:
        raise ValueError(
            "The timer is stale or the system clock changed. Discard the "
            "unverified timer instead of recording invented playtime.")
    if discard:
        _active_path().unlink(missing_ok=True)
        return None
    row = {key: value for key, value in entry.items() if key != "schema"}
    row["end"] = now
    previous = read_sessions()
    if any(saved["id"] == row["id"] for saved in previous):
        raise ValueError("Session already recorded.")
    _atomic(_journal_path(), {
        "schema": SCHEMA,
        "entries": [row, *previous][:MAX_HISTORY],
    })
    _active_path().unlink(missing_ok=True)
    return row


def time_window(records: list[dict], kind: str,
                *, now: datetime | None = None) -> list[dict]:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("An aware date is required.")
    current = current.astimezone(timezone.utc)
    if kind == "This Session":
        return records[:1]
    year = current.year
    if kind == "This Month":
        return [s for s in records
                if (t := datetime.fromtimestamp(s["start"], timezone.utc)).year == year
                and t.month == current.month]
    if kind == "This Year":
        return [s for s in records
                if datetime.fromtimestamp(s["start"], timezone.utc).year == year]
    raise ValueError("Unsupported recap period.")


def recap(records: list[dict], kind: str, *, now=None) -> dict:
    scoped = time_window(records, kind, now=now)
    seconds = sum(s["end"] - s["start"] for s in scoped)
    play_by_game: dict[str, list] = {}
    for item in scoped:
        key = str(item.get("key", ""))
        if key not in play_by_game:
            play_by_game[key] = [str(item.get("name", "Game")), 0]
        play_by_game[key][1] += item["end"] - item["start"]
    most = max(play_by_game.values(), key=lambda item: item[1], default=None)
    monthly = [0] * 12
    for item in scoped:
        month = datetime.fromtimestamp(item["start"], timezone.utc).month
        monthly[month - 1] += item["end"] - item["start"]
    return {
        "kind": kind,
        "sessions": len(scoped),
        "seconds": seconds,
        "average_seconds": seconds // len(scoped) if scoped else 0,
        "most_played": most[0] if most else "No tracked sessions",
        "most_played_seconds": most[1] if most else 0,
        "monthly_seconds": tuple(monthly),
        "latest": scoped[0] if scoped else None,
        "tracked_since": min((s["start"] for s in records), default=None),
        "scope": scoped,
    }


def captured_during(session: dict | None, records) -> list:
    """Timestamp overlap only; not evidence the capture belongs to this game.

    The scanner provides known gaming screenshot/video paths, not all personal
    media. Files can be moved/edited; the recorded mtime may not be capture time.
    """
    if session is None:
        return []
    start, end = session["start"], session["end"]
    return sorted([
        rec for rec in list(records) if
        isinstance(getattr(rec, "modified", None), (float, int))
        and start <= rec.modified <= end
    ], key=lambda rec: -rec.modified)
