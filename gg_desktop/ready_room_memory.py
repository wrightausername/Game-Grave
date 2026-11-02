"""Private per-game memory for resuming a game, never a social feed.

Stores only notes the user intentionally enters. Data stays in local config;
nothing is read from game memory, OCR'd, captured automatically or uploaded.
"""
from __future__ import annotations
import json
import os
from pathlib import Path

from core import config_dir
from gg_desktop.ready_room_health import _identity

MAX_BYTES = 18_000
MAX_TEXT = 2400


def _path(game) -> Path:
    return config_dir() / "ready_room" / "game_memory" / (_identity(game) + ".json")


def read_game_memory(game) -> dict:
    target = _path(game)
    try:
        if not target.is_file() or target.is_symlink() or target.stat().st_size > MAX_BYTES:
            return {"where": "", "next": "", "profile": ""}
        data = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema") != 1:
            return {"where": "", "next": "", "profile": ""}
        return {key: str(data.get(key, ""))[:MAX_TEXT] for key in ("where", "next", "profile")}
    except (OSError, ValueError, UnicodeError, TypeError):
        return {"where": "", "next": "", "profile": ""}


def save_game_memory(game, *, where: str, next_goal: str, profile: str) -> dict:
    if not all(isinstance(item, str) for item in (where, next_goal, profile)):
        raise ValueError("Memory fields must be text.")
    fields = {"where": where.strip()[:MAX_TEXT],
              "next": next_goal.strip()[:MAX_TEXT],
              "profile": profile.strip()[:MAX_TEXT]}
    output = {"schema": 1, **fields}
    payload = json.dumps(output, ensure_ascii=False)
    if len(payload.encode("utf-8")) > MAX_BYTES:
        raise ValueError("Game Memory text exceeds the local record limit.")
    target = _path(game)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".new")
    try:
        temp.write_text(payload, encoding="utf-8")
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    return fields
