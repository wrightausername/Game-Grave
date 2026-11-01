"""On-demand Ready Room change diagnostics, local-only and gameplay aware.

Nothing runs continuously. A baseline is saved only after an explicit user
action. A comparison reads bounded mod metadata without hashing game binaries,
opening save files, editing mod managers, or contacting a server.

This is NOT a full backup or an automatic rollback engine.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path

from core import config_dir
from game_intelligence import (
    MAX_ENTRIES, build_game_dna, capture_mod_observation,
    compare_observations, patch_fallout, what_broke_my_game,
)
from performance_guard import GameActivityDetector, CooperativeGameplayPause

SNAPSHOT_SCHEMA = 1
MAX_BASELINE_BYTES = 3_000_000


def _identity(game) -> str:
    launcher = str(getattr(game, "launcher", "")).casefold()
    game_root = str(getattr(game, "install_path", "")).strip()
    if not launcher or not game_root:
        raise ValueError("A verified game record is required.")
    normalized = os.path.normcase(os.path.normpath(os.path.abspath(game_root)))
    return sha256((launcher + "\n" + normalized).encode("utf-8")).hexdigest()


def _baseline_path(game) -> Path:
    return config_dir() / "ready_room" / (_identity(game) + ".json")


def linked_mods_for_game(game, mods) -> list:
    """Use the same evidence rules as Game DNA. No fuzzy title matching."""
    if "Installed" not in str(getattr(game, "status", "")):
        return []
    known_mods = list(mods)
    # build_game_dna considers only verified install paths and Steam Workshop
    # ownership. Ambiguous or unidentified mod roots are never assigned.
    result = build_game_dna([game], [], known_mods)
    game_rows = result.get("games", [])
    if len(game_rows) != 1:
        return []
    paths = {str(entry.get("path", "")).casefold()
             for entry in game_rows[0].get("assets", [])}
    return [m for m in known_mods
            if str(getattr(m, "path", "")).casefold() in paths]


def capture_game_state(game, mods, *, cancel=lambda: False,
                       detector=None) -> dict:
    """Snapshot metadata in an explicit low-priority worker, yielding to games."""
    _identity(game)
    guard = CooperativeGameplayPause(cancel, detector=detector or GameActivityDetector())
    guard.raise_if_canceled()
    linked = linked_mods_for_game(game, mods)
    observation = capture_mod_observation(
        linked, max_entries=MAX_ENTRIES, cancel=guard.checkpoint)
    guard.raise_if_canceled()
    return {
        "schema": SNAPSHOT_SCHEMA,
        "game": str(getattr(game, "name", "Unknown game"))[:170],
        "record_key": str(getattr(game, "key", ""))[:500],
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "launcher": str(getattr(game, "launcher", "Unknown")),
        "reported_install_bytes": getattr(game, "size_bytes", None),
        "linked_mod_roots": len(linked),
        "observation": observation,
        "note": "Read-only, bounded mod-file metadata. This is not a restorable game backup.",
    }


def load_game_baseline(game) -> dict | None:
    path = _baseline_path(game)
    try:
        if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_BASELINE_BYTES:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(data, dict)
                or data.get("schema") != SNAPSHOT_SCHEMA
                or not isinstance(data.get("observation"), dict)
                or len(data.get("observation", {}).get("entries", {})) > MAX_ENTRIES):
            return None
        return data
    except (OSError, UnicodeError, ValueError, TypeError):
        return None


def save_game_baseline(game, state: dict) -> Path:
    if state.get("schema") != SNAPSHOT_SCHEMA or not isinstance(state.get("observation"), dict):
        raise ValueError("Unrecognized Ready Room snapshot.")
    data = json.dumps(state, ensure_ascii=False, sort_keys=True)
    if len(data.encode("utf-8")) > MAX_BASELINE_BYTES:
        raise ValueError("Baseline metadata too large; no data saved.")
    target = _baseline_path(game)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".new")
    try:
        tmp.write_text(data, encoding="utf-8")
        os.replace(tmp, target)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
    return target


def compare_game_state(previous: dict | None, current: dict) -> dict:
    if previous is None:
        return {
            "has_baseline": False,
            "lines": ["No local baseline exists. Use Record baseline after verifying the game works."],
            "changes": [],
            "potential_mod_review": 0,
            "complete": False,
        }
    report = compare_observations(previous["observation"], current["observation"])
    lines = what_broke_my_game(report)
    old_bytes = previous.get("reported_install_bytes")
    new_bytes = current.get("reported_install_bytes")
    if type(old_bytes) is int and type(new_bytes) is int and old_bytes != new_bytes:
        lines.insert(0, "Launcher-reported installation size changed; this alone does not identify why.")
    lines.append(
        "Known-good means only that you chose this baseline. It does not verify that the game ran.")
    return {
        "has_baseline": True,
        "recorded_at": previous.get("captured_at", "Unknown"),
        "changes": report["changes"][:60],
        "total_changes": report["count"],
        "potential_mod_review": patch_fallout(report)["total_review"],
        "complete": not report["incomplete"],
        "lines": lines,
    }
