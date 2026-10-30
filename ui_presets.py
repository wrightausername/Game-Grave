"""Portable, data-only presentation presets for Game Grave.

Import/export never restores any scanner, security, deletion, automation, path,
account or activity setting. Presets cannot execute code or request file operations.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from view_options import (FILES_SORT_OPTIONS, GAMES_SORT_OPTIONS, MOD_SORT_OPTIONS,
                          GRAVE_SORT_KEYS, SORT_DIRECTIONS, GRAVE_STATES, GRAVE_SIZES)

FORMAT = "gamegrave.ui-preset"
VERSION = 1
MAX_FILE_BYTES = 24 * 1024
MAX_PRESETS = 30
HEX_PATTERN = re.compile(r"#[0-9a-fA-F]{6}\Z")
NAME_PATTERN = re.compile(r"[^\x00-\x1f\x7f]")

# No user file paths, recent scans, library names, free-text search, never-touch
# folders, permission settings or cleanup controls may leave the user's machine.
ALLOWED = {
    "ui_theme": ("dark", "light", "system"),
    "ui_accent": ("teal", "blue", "purple", "orange", "custom"),
    "ui_scale": ("compact", "normal", "large"),
    "ui_layout": ("simple", "advanced"),
    "game_sort": GAMES_SORT_OPTIONS,
    "mod_sort": MOD_SORT_OPTIONS,
    "files_sort": FILES_SORT_OPTIONS,
    "graveyard_sort": GRAVE_SORT_KEYS,
    "graveyard_order": SORT_DIRECTIONS,
    "graveyard_status": GRAVE_STATES,
    "graveyard_min_size": tuple(GRAVE_SIZES),
    "graveyard_days": (180, 365, 730, 1095),
}


def normalize_color(value: object) -> str:
    if not isinstance(value, str) or not HEX_PATTERN.fullmatch(value):
        raise ValueError("Color must be a six-digit hexadecimal color, such as #CC44EE.")
    return value.upper()


def validate_name(name: object) -> str:
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 40:
        raise ValueError("Preset name must be 1 to 40 characters.")
    name = name.strip()
    if not all(NAME_PATTERN.fullmatch(ch) for ch in name):
        raise ValueError("Preset names cannot contain control characters.")
    return name


def capture_presentation(settings: dict) -> dict:
    """Only user-presentational choices, never private paths or deletion controls."""
    candidate = {key: settings[key] for key in ALLOWED if key in settings}
    candidate["ui_custom_accent"] = settings.get("ui_custom_accent", "#50DCC5")
    return validate_presentation(candidate)


def validate_presentation(data: object) -> dict:
    if not isinstance(data, dict):
        raise ValueError("A preset must contain a settings object.")
    expected = set(ALLOWED) | {"ui_custom_accent"}
    if set(data) != expected:
        raise ValueError("Preset settings are missing, unknown, or contain forbidden fields.")
    normalized = {}
    for key, allowed in ALLOWED.items():
        value = data[key]
        if key == "graveyard_days" and type(value) is not int:
            raise ValueError("Invalid Graveyard age filter.")
        if key != "graveyard_days" and not isinstance(value, str):
            raise ValueError("Invalid presentation value: " + key)
        if value not in allowed:
            raise ValueError("Unsupported presentation value: " + key)
        normalized[key] = value
    normalized["ui_custom_accent"] = normalize_color(data["ui_custom_accent"])
    return normalized


def preset_document(name: str, settings: dict) -> dict:
    return {"format": FORMAT, "version": VERSION, "name": validate_name(name),
            "settings": validate_presentation(settings)}


def encode_preset(name: str, settings: dict) -> str:
    return json.dumps(preset_document(name, settings), indent=2, ensure_ascii=False) + "\n"


def decode_preset(text: str) -> tuple[str, dict]:
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError("Preset file exceeds the 24 KB limit.")
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise ValueError("Not a valid Game Grave preset JSON file.") from exc
    if not isinstance(data, dict) or set(data) != {"format", "version", "name", "settings"}:
        raise ValueError("Unexpected file format or additional fields.")
    if data["format"] != FORMAT or type(data["version"]) is not int or data["version"] != VERSION:
        raise ValueError("Unsupported Game Grave preset version.")
    return validate_name(data["name"]), validate_presentation(data["settings"])


def sanitize_local_presets(data: object) -> dict:
    """Drop malformed entries; never apply imported data without validating it."""
    if not isinstance(data, dict):
        return {}
    cleaned = {}
    for name, settings in list(data.items())[:MAX_PRESETS]:
        try:
            key = validate_name(name)
            cleaned[key] = validate_presentation(settings)
        except ValueError:
            continue
    return cleaned


def read_preset_file(path: str | Path) -> tuple[str, dict]:
    path = Path(path)
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("Preset file exceeds the 24 KB limit.")
    return decode_preset(path.read_text(encoding="utf-8"))


def write_preset_file(path: str | Path, name: str, settings: dict) -> None:
    Path(path).write_text(encode_preset(name, settings), encoding="utf-8")
