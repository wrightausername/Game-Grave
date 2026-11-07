"""Read Overview's favorite preference without changing the shared loader."""
from __future__ import annotations

import json
import core


def restore_overview_favorites(settings):
    def valid(value):
        return type(value) is list and all(type(key) is str and 0 < len(key) <= 4096 and "\0" not in key for key in value)
    if "desktop_favorites" in settings:
        value = settings["desktop_favorites"]
        return set(value) if valid(value) else set()
    path = core.config_dir()/"settings.json"
    try:
        if core._has_reparse_component(path) or not path.is_file() or path.stat().st_size > core.MAX_SETTINGS_BYTES:
            return set()
        with path.open("rb") as stream:
            raw = stream.read(core.MAX_SETTINGS_BYTES+1)
        if len(raw) > core.MAX_SETTINGS_BYTES:
            return set()
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=core._settings_no_duplicate_keys)
        value = data.get("desktop_favorites", []) if isinstance(data, dict) else []
        return set(value) if valid(value) else set()
    except (OSError, ValueError, TypeError, UnicodeError):
        return set()
