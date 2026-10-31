"""Conservative read-only discovery of old local gaming video captures.

No cloud browsing, video parsing, thumbnail generation, or automatic cleanup.
Names and locations are hints, not proof a video is a disposable game recording.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Callable

from core import OldFile, scan_old_files, safe_scan_root, _has_reparse_component

RECORDING_EXTENSIONS = frozenset({".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".wmv"})
CAPTURE_DIR_NAMES = frozenset({
    "captures", "game captures", "game clips", "game dvr", "shadowplay",
    "nvidia", "highlights", "replay", "instant replay", "relive", "radeon relive",
    "obs", "obs-studio", "recordings", "steam recordings",
})
CAPTURE_NAME_HINT = re.compile(
    r"(?:capture|game\s*bar|gameplay|shadowplay|instant\s*replay|"
    r"highlight|recording|replay|\bclip\b|obs|relive)", re.IGNORECASE)
# Common in GeForce, Game Bar and similar captures, but not sufficient alone
# to categorize an arbitrary personal movie as a gaming recording.
TIMESTAMP_HINT = re.compile(r"\b20\d\d[-_. ]\d\d[-_. ]\d\d\b")


def default_recording_roots(home: Path | None = None) -> list[Path]:
    """Look in conventional local Videos folders; do not search whole drives."""
    home = Path.home() if home is None else Path(home)
    candidates = [home / "Videos", home / "OneDrive" / "Videos",
                  home / "Documents" / "Captures"]
    return [p for p in candidates if p.is_dir() and safe_scan_root(p)]


def looks_like_recording(path: Path, root: Path, *, user_selected: bool = False) -> bool:
    """Use cautious metadata heuristics and explicitly selected roots only."""
    if path.suffix.casefold() not in RECORDING_EXTENSIONS:
        return False
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    if user_selected:
        return True  # The user deliberately marked this folder as recording storage.
    parts = {part.casefold() for part in relative.parts[:-1]}
    if parts & CAPTURE_DIR_NAMES:
        return True
    if CAPTURE_NAME_HINT.search(path.stem):
        return True
    # OBS and similar recorders often save date-stamped clips directly in
    # Videos rather than a Captures folder. Treat as *possible* clips only.
    if TIMESTAMP_HINT.search(path.stem):
        return True
    return False


def find_old_recordings(days: int = 180, custom_roots: list[str] | None = None,
                        *, home: Path | None = None, cancel: Callable[[], bool] | None = None,
                        max_matches: int = 2500) -> list[OldFile]:
    """Read file metadata only. Avoid junctions, duplicate roots and live game data."""
    if days < 1 or max_matches < 1:
        raise ValueError("Days and max_matches must be positive")
    ordinary = default_recording_roots(home)
    selected = [Path(p).expanduser() for p in (custom_roots or [])
                if isinstance(p, str) and p.strip()]
    roots: list[tuple[Path, bool]] = [(p, False) for p in ordinary]
    roots.extend((p, True) for p in selected)
    seen_roots: set[str] = set()
    seen_files: set[str] = set()
    output: list[OldFile] = []
    for root, user_selected in roots:
        if cancel and cancel():
            raise InterruptedError("Scan canceled")
        key = os.path.normcase(os.path.abspath(str(root))).casefold()
        if key in seen_roots or not safe_scan_root(root):
            continue
        seen_roots.add(key)
        remaining = max_matches - len(output)
        if remaining <= 0:
            break
        # Extra headroom for personal videos that do not match capture hints.
        # The scan itself never modifies files.
        candidates = scan_old_files(root, days, cancel=cancel,
                                    allowed_extensions=set(RECORDING_EXTENSIONS),
                                    max_matches=max(remaining * 4, remaining))
        for file in candidates:
            path = Path(file.path)
            identity = os.path.normcase(os.path.abspath(file.path)).casefold()
            if (identity in seen_files or _has_reparse_component(path)
                    or not looks_like_recording(path, root, user_selected=user_selected)):
                continue
            seen_files.add(identity)
            output.append(file)
            if len(output) >= max_matches:
                return sorted(output, key=lambda f: -f.size)
    return sorted(output, key=lambda f: -f.size)
