"""Read-only, bounded *manual* Old Files scan of an entire local Windows drive.

The ordinary folder scanner continues to refuse drive roots. Only the owner
choosing a local fixed drive in the Old Files UI enables this separate mode.
No automatic cleanup, no follow-links, no scanning system/hidden app trees,
no permanent-delete fallback and no guarantee that 'old' means 'unneeded'.
"""
from __future__ import annotations

from dataclasses import dataclass
import ctypes
import os
from pathlib import Path
import stat
import time
from typing import Callable, Iterable

from core import (
    OldFile, _has_reparse_component, safe_scan_root, scan_old_files,
    is_protected_path,
)

# The default scope for a whole-drive scan must not be Windows OS,
# program installation, application data, save profiles, or recycled data.
SKIP_TOP_LEVEL = frozenset({
    "windows", "program files", "program files (x86)",
    "program files (arm)", "programdata", "$recycle.bin",
    "system volume information", "recovery", "perflogs", "efi",
    "msocache", "config.msi", "$windows.~bt", "$windows.~ws",
    "documents and settings", "applications", "appdata",
})
SKIP_ANYWHERE = frozenset({
    "$recycle.bin", "system volume information", "windows", "appdata",
    "programdata", "program files", "program files (x86)",
    "program files (arm)", "node_modules", ".git", ".venv",
    "venv", "__pycache__", "steamapps", "saves", "savegames",
    "saved games", "modorganizer", "modorganizer2",
    "mod organizer", "mod organizer 2", "vortex",
    "r2modman", "wabbajack", "thunderstore", "curseforge",
    "profiles", "mods", "worlds",
})
MAX_ENTRIES = 160_000
MAX_MATCHES = 15_000
MAX_SECONDS = 25.0
MAX_DEPTH = 14


@dataclass(frozen=True)
class OldFilesScopeResult:
    files: tuple[OldFile, ...]
    status: str  # "complete" or "partial"
    message: str
    inspected: int = 0
    skipped: int = 0


def is_fixed_drive_root(folder: str | Path) -> bool:
    """Only an existing Windows local fixed-drive root (C:\\, D:\\, etc.)."""
    if os.name != "nt":
        return False
    try:
        requested = Path(os.path.abspath(os.fspath(folder)))
        if (not requested.anchor or requested != Path(requested.anchor)
                or not requested.is_dir() or _has_reparse_component(requested)):
            return False
        return ctypes.windll.kernel32.GetDriveTypeW(str(requested)) == 3
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def accepted_old_files_scope(folder: str | Path) -> bool:
    path = Path(folder)
    return is_fixed_drive_root(path) or (
        safe_scan_root(path) and not is_protected_path(path)
    )


def _inside(parent: Path, child: Path) -> bool:
    try:
        child.absolute().relative_to(parent.absolute())
        return True
    except (OSError, ValueError, TypeError):
        return False


def drive_file_allowed(root: str | Path, file: str | Path) -> bool:
    """Constrain whole-drive discovery/recycling to non-system child files."""
    drive = Path(root)
    target = Path(file)
    if not is_fixed_drive_root(drive) or not _inside(drive, target):
        return False
    try:
        parts = target.absolute().relative_to(drive.absolute()).parts
        if len(parts) < 2 or any(
            item.casefold() in SKIP_ANYWHERE for item in parts[:-1]
        ) or parts[0].casefold() in SKIP_TOP_LEVEL:
            return False
        if _has_reparse_component(target) or is_protected_path(target):
            return False
        return True
    except (OSError, ValueError):
        return False


def _excluded_known_game(path: Path, known: tuple[Path, ...]) -> bool:
    return any(_inside(game, path) for game in known)


def scan_old_files_scope(
    folder: str | Path,
    days: int,
    *,
    cancel: Callable[[], bool] | None = None,
    known_game_roots: Iterable[str] = (),
    max_entries: int = MAX_ENTRIES,
    max_matches: int = MAX_MATCHES,
    max_seconds: float = MAX_SECONDS,
) -> OldFilesScopeResult:
    """Choose normal folder scan or separately bounded local fixed-drive scan.

    Returns completeness explicitly, to prevent the UI claiming 'nothing found'
    when a drive scan timed out or failed to inspect some directories.
    """
    root = Path(folder)
    if not is_fixed_drive_root(root):
        if not safe_scan_root(root):
            raise ValueError("Select an ordinary folder or a local fixed drive.")
        files = scan_old_files(root, days, cancel=cancel)
        return OldFilesScopeResult(
            files=tuple(files),
            status="partial" if len(files) >= 50_000 else "complete",
            message=("Ordinary folder scan reached the 50,000-file display limit."
                     if len(files) >= 50_000 else "Folder scan completed."),
            inspected=0,
        )

    if not 1 <= int(days) <= 10_000:
        raise ValueError("Old Files age filter must be at least 1 day.")
    if not 1 <= max_entries <= MAX_ENTRIES or not 1 <= max_matches <= MAX_MATCHES:
        raise ValueError("Drive scan limits are invalid.")
    if max_seconds <= 0 or max_seconds > 120:
        raise ValueError("Drive scan time limit is invalid.")
    games = tuple(
        Path(path) for path in known_game_roots
        if isinstance(path, str) and path.strip() and _inside(root, Path(path))
    )
    cutoff = time.time() - days * 86400
    result: list[OldFile] = []
    visited = 0
    skipped = 0
    status = "complete"
    reason = "Drive scan completed (protected and system areas excluded)."
    started = time.monotonic()
    inaccessible = 0

    def on_error(_exc):
        nonlocal inaccessible
        inaccessible += 1

    # os.walk calls scandir; followlinks remains disabled and every entry is
    # rechecked before following it, protecting against junctions/reparse.
    for parent, dirs, names in os.walk(root, followlinks=False,
                                       onerror=on_error):
        if cancel and cancel():
            raise InterruptedError("Old Files drive scan canceled.")
        if time.monotonic() - started >= max_seconds:
            status, reason = "partial", "Time limit reached; results are incomplete."
            break
        parent_path = Path(parent)
        if _has_reparse_component(parent_path):
            skipped += 1
            dirs[:] = []
            continue
        depth = len(parent_path.relative_to(root).parts)
        if depth >= MAX_DEPTH:
            skipped += len(dirs)
            dirs[:] = []
        else:
            safe_dirs: list[str] = []
            for name in dirs:
                key = name.casefold()
                item = parent_path / name
                if (key in SKIP_ANYWHERE or
                        (depth == 0 and key in SKIP_TOP_LEVEL) or
                        _has_reparse_component(item) or
                        _excluded_known_game(item, games)):
                    skipped += 1
                    continue
                safe_dirs.append(name)
            dirs[:] = safe_dirs

        for name in names:
            visited += 1
            if visited >= max_entries:
                status, reason = "partial", "Item limit reached; results are incomplete."
                break
            if cancel and cancel():
                raise InterruptedError("Old Files drive scan canceled.")
            if time.monotonic() - started >= max_seconds:
                status, reason = "partial", "Time limit reached; results are incomplete."
                break
            candidate = parent_path / name
            if not drive_file_allowed(root, candidate):
                skipped += 1
                continue
            if _excluded_known_game(candidate, games):
                skipped += 1
                continue
            try:
                state = candidate.lstat()
            except (OSError, ValueError):
                skipped += 1
                continue
            if not stat.S_ISREG(state.st_mode) or state.st_nlink != 1:
                skipped += 1
                continue
            if state.st_mtime <= cutoff:
                result.append(OldFile(
                    str(candidate), state.st_size, state.st_mtime,
                    state.st_dev, state.st_ino,
                    state.st_mtime_ns, state.st_nlink,
                ))
                if len(result) >= max_matches:
                    status, reason = "partial", "Result limit reached; scan is incomplete."
                    break
        if status != "complete":
            break
    if inaccessible:
        status = "partial"
        reason += f" {inaccessible} folder(s) could not be accessed."
    return OldFilesScopeResult(
        files=tuple(result), status=status, message=reason,
        inspected=visited, skipped=skipped + inaccessible,
    )
