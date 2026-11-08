"""Keep every saved setting across restarts.

The shared loader (core.load_settings) keeps only the keys listed in core.default_settings. Preferences that
newer tabs save (AI Assistant chats, Undo Center hidden rows, Game DNA linked folders, Settings preferences)
are therefore forgotten on the next launch, and the next save then erases them from the file. This loader
returns exactly what core.load_settings returns and additionally keeps the other keys found in the file.
core.py itself is untouched.
"""
from __future__ import annotations

import json

import core

MAX_EXTRA_KEYS = 200
MAX_KEY_LENGTH = 64


def load_settings() -> dict:
    result = core.load_settings()
    path = core.config_dir() / "settings.json"
    try:
        if core._has_reparse_component(path) or not path.is_file() or path.stat().st_size > core.MAX_SETTINGS_BYTES:
            return result
        with path.open("rb") as stream:
            raw = stream.read(core.MAX_SETTINGS_BYTES + 1)
        if len(raw) > core.MAX_SETTINGS_BYTES:
            return result
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=core._settings_no_duplicate_keys)
    except (OSError, ValueError, TypeError, UnicodeError):
        return result
    if not isinstance(data, dict):
        return result
    known = core.default_settings()
    kept = 0
    for key, value in data.items():
        if key in known or type(key) is not str or not key or len(key) > MAX_KEY_LENGTH:
            continue
        if kept >= MAX_EXTRA_KEYS:
            break
        result[key] = value
        kept += 1
    return result
