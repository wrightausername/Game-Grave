"""Optional, local-only explanation of 'Other used' storage.

This is a *separate* read-only metadata inventory. No file content, uploads,
deletion recommendations, AI requests, or automatic startup/scan side effects.
The overview Other value is disk.used - reported_game_sizes; it cannot be
exactly partitioned from directory metadata because launcher sizes may be
wrong/unknown, hard links and filesystem accounting may differ.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import os
from pathlib import Path
import stat
import sys
import time
from typing import Callable, Iterable

from core import _has_reparse_component


MAX_ENTRIES = 220_000
MAX_SECONDS = 25
MAX_FOLDER_ROWS = 150


@dataclass(frozen=True)
class FolderUsage:
    name: str
    path: str
    category: str
    apparent_bytes: int
    files_seen: int


@dataclass(frozen=True)
class OtherStorageReport:
    root: str
    folders: tuple[FolderUsage, ...]
    analyzed_bytes: int
    entries_seen: int
    skipped_entries: int
    excluded_games: int
    complete: bool
    limitation: str
    elapsed_seconds: float


def category_for_folder(name: str) -> str:
    """Honest label based on directory location, not hidden file inspection."""
    key = name.casefold().strip()
    if key in ("windows", "system32", "recovery", "perflogs"):
        return "Windows / system"
    if key in ("program files", "program files (x86)", "programdata", "program files (arm)"):
        return "Apps and shared app data"
    if key in ("users", "documents and settings"):
        return "User profiles / media / AppData"
    if key in ("games", "steamlibrary", "epic games", "gog games", "battlenet"):
        return "Game library directories (not verified)"
    return "Other folders / root files"


def _path_id(path: Path | str) -> str:
    return os.path.normcase(os.path.abspath(str(path))).replace("/", "\\").casefold().rstrip("\\")


def _same_volume(path: Path | str, root: Path) -> bool:
    try:
        result = os.path.commonpath((str(Path(path).absolute()), str(root.absolute())))
        return _path_id(result) == _path_id(root)
    except (OSError, ValueError):
        return False


def _check_requested_root(folder: Path) -> Path:
    """The production UI authorizes exactly an existing fixed-drive root."""
    path = Path(os.path.abspath(str(folder)))
    if not path.is_dir() or _has_reparse_component(path):
        raise ValueError("The selected storage volume is unavailable or redirected.")
    if os.name == "nt":
        # Never allow a user-provided network UNC location, junction or child folder.
        if not path.drive or _path_id(path) != _path_id(Path(path.anchor)):
            raise ValueError("Select a local drive root, such as C:\\, for storage analysis.")
        import ctypes
        if ctypes.windll.kernel32.GetDriveTypeW(str(path)) != 3:
            raise ValueError("Only local fixed drives are supported.")
    return path


def analyze_other_storage(
    drive: str | Path,
    installed_games: Iterable[str] = (),
    *,
    scope: str | Path | None = None,
    max_entries: int = MAX_ENTRIES,
    max_seconds: float = MAX_SECONDS,
    cancel: Callable[[], bool] | None = None,
    notify: Callable[[int, str], None] | None = None,
) -> OtherStorageReport:
    """Explicit-click, bounded metadata walk; no file contents are opened.

    Installed-game directories are excluded from the breakdown where they are
    known, but folder sizes remain apparent estimates, NOT the source of the
    overview 'Other used' number. Unknown/inaccessible items remain unknown.
    """
    drive_root = _check_requested_root(Path(drive))
    root = Path(os.path.abspath(str(scope))) if scope is not None else drive_root
    if (not root.is_dir() or not _same_volume(root, drive_root)
            or _has_reparse_component(root)):
        raise ValueError("This folder is outside the selected drive or redirected.")
    if not 1 <= max_entries <= MAX_ENTRIES:
        raise ValueError("Invalid maximum directory-entry limit.")
    if not 0 < max_seconds <= 120:
        raise ValueError("Invalid analysis time limit.")
    known_game_dirs = {
        _path_id(path) for path in installed_games
        if path and _same_volume(path, root)
        and _path_id(path) != _path_id(root)
    }
    start = time.monotonic()
    folder_bytes = defaultdict(int)
    file_counts = defaultdict(int)
    top_folder_paths: dict[str, str] = {}
    skip_count = 0
    game_count = 0
    examined = 0
    incomplete = ""
    seen_files: set[tuple[int, int]] = set()

    # Only the first directory level is used for classification; display
    # subfolders via Windows File Explorer, never guess their purpose.
    stack: list[tuple[Path, str]] = [(root, "")]
    while stack:
        if cancel and cancel():
            incomplete = "Scan canceled. Only a partial sample is shown."
            break
        if time.monotonic() - start > max_seconds:
            incomplete = "Time limit reached. Some folders remain unmeasured."
            break
        folder, group = stack.pop()
        if _has_reparse_component(folder):
            skip_count += 1
            continue
        if _path_id(folder) in known_game_dirs:
            game_count += 1
            continue
        try:
            iterator = os.scandir(folder)
        except (OSError, PermissionError):
            skip_count += 1
            continue
        try:
            with iterator:
                for entry in iterator:
                    examined += 1
                    if examined > max_entries:
                        incomplete = "Item limit reached. Some folders remain unmeasured."
                        break
                    if cancel and cancel():
                        incomplete = "Scan canceled. Only a partial sample is shown."
                        break
                    if time.monotonic() - start > max_seconds:
                        incomplete = "Time limit reached. Some folders remain unmeasured."
                        break
                    location = Path(entry.path)
                    current_group = group or entry.name
                    if not group:
                        top_folder_paths.setdefault(current_group, str(location))
                    # No symlink / junction / redirected subtree traversal.
                    try:
                        if entry.is_symlink() or _has_reparse_component(location):
                            skip_count += 1
                            continue
                        if _path_id(location) in known_game_dirs:
                            game_count += 1
                            continue
                        metadata = entry.stat(follow_symlinks=False)
                    except (OSError, PermissionError):
                        skip_count += 1
                        continue
                    if stat.S_ISDIR(metadata.st_mode):
                        stack.append((location, current_group))
                    elif stat.S_ISREG(metadata.st_mode):
                        # A hard-linked file is counted once, not at every
                        # directory reference; sparse/compressed files still
                        # have different disk and apparent sizes.
                        identity = (metadata.st_dev, metadata.st_ino)
                        if metadata.st_nlink > 1 and identity in seen_files:
                            continue
                        if metadata.st_nlink > 1:
                            seen_files.add(identity)
                        folder_bytes[current_group] += max(0, metadata.st_size)
                        file_counts[current_group] += 1
                    else:
                        skip_count += 1
            if incomplete:
                break
        except (OSError, PermissionError):
            skip_count += 1
        if notify and examined % 8000 < 250:
            notify(min(99, int(100 * examined / max_entries)),
                   f"Examined {examined:,} file/folder entries")

    grouped = []
    for name, path in top_folder_paths.items():
        if len(grouped) >= MAX_FOLDER_ROWS and name not in folder_bytes:
            continue
        grouped.append(FolderUsage(
            name=name,
            path=path,
            category=category_for_folder(name),
            apparent_bytes=folder_bytes.get(name, 0),
            files_seen=file_counts.get(name, 0),
        ))
    grouped.sort(key=lambda row: (-row.apparent_bytes, row.name.casefold()))
    if len(grouped) > MAX_FOLDER_ROWS:
        grouped = grouped[:MAX_FOLDER_ROWS]
        incomplete = incomplete or "Only the 150 largest root entries are listed."
    if skip_count and not incomplete:
        incomplete = "Some protected/inaccessible files or junctions were excluded."
    if game_count and not incomplete:
        incomplete = "Known installed-game folders were excluded where identified."
    if notify:
        notify(100, "Read-only storage analysis completed")
    return OtherStorageReport(
        root=str(root),
        folders=tuple(grouped),
        analyzed_bytes=sum(folder_bytes.values()),
        entries_seen=examined,
        skipped_entries=skip_count,
        excluded_games=game_count,
        complete=not bool(incomplete),
        limitation=incomplete or "Completed allowed metadata walk. Disk accounting can still differ.",
        elapsed_seconds=max(0, time.monotonic() - start),
    )
