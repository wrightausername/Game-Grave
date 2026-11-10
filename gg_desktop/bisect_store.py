"""Mod Bisect: remembers an unfinished search between sessions, in Game Grave's own folder only.

One small JSON file in the Game Grave config folder (`bisect/runs.json`). It holds the owner's answers and clues, never
mod files. A damaged, linked or oversized file is ignored rather than trusted."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

MAX_BYTES = 512 * 1024
MAX_RUNS = 20


def _file(root: Path) -> Path:
    return Path(root) / "bisect" / "runs.json"


def _linked(path: Path) -> bool:
    try:
        return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)
    except OSError:
        return False


def load_all(root: Path) -> dict:
    path = _file(root)
    try:
        if _linked(path) or _linked(path.parent) or not path.is_file() or path.stat().st_size > MAX_BYTES:
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, dict)}


def load(root: Path, profile_key: str):
    return load_all(root).get(profile_key)


def save(root: Path, profile_key: str, snapshot: dict) -> bool:
    runs = load_all(root)
    runs.pop(profile_key, None)
    runs[profile_key] = snapshot                      # newest last, so the oldest are the ones dropped
    while len(runs) > MAX_RUNS:
        runs.pop(next(iter(runs)))
    return _write(root, runs)


def forget(root: Path, profile_key: str) -> bool:
    runs = load_all(root)
    if profile_key not in runs:
        return True
    runs.pop(profile_key)
    return _write(root, runs)


def _write(root: Path, runs: dict) -> bool:
    path = _file(root)
    try:
        content = json.dumps(runs, ensure_ascii=False).encode("utf-8")
        if len(content) > MAX_BYTES:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        if _linked(path.parent) or _linked(path):
            return False
        fd, raw = tempfile.mkstemp(prefix=".gg-bisect-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
            os.replace(raw, path)
        except OSError:
            try:
                os.unlink(raw)
            except OSError:
                pass
            return False
        return True
    except (OSError, ValueError):
        return False
