"""User-approved Graveyard cleanup worker.

Pure worker logic: never uses Tk widgets, prompts, or a permanent-delete
fallback. The UI performs its single approval before starting this function.
Core rechecks file identity and Windows Recycle Bin recovery on every file.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable

from core import OldFile, is_protected_path, is_unchanged, log_event, recycle_file
from graveyard import GraveyardEntry, looks_like_game_archive
from recordings import RECORDING_EXTENSIONS
from recovery import register_recycle


def recycle_reviewed_entries(
    entries: Iterable[GraveyardEntry],
    never_touch: Iterable[str],
    session: str,
    progress: Callable[[int, int], None] | None = None,
) -> dict:
    """Move only approved individual files to Windows Recycle Bin.

    The selected entries and protections are snapshotted by the caller before
    the worker starts. Any blocked/changed file is skipped. No permanent
    deletion fallback exists. A failed Undo Center log is surfaced separately
    from a successful Windows Recycle Bin move.
    """
    chosen = tuple(entries)
    protected = list(never_touch)
    completed = 0
    skipped: list[str] = []
    recovery_warnings = 0
    log_event("Cleanup started", f"Graveyard selected {len(chosen)} items",
              session_id=session, source="The Graveyard")
    for position, entry in enumerate(chosen, 1):
        file = entry.old_file
        try:
            if not entry.can_recycle or file is None:
                raise ValueError("This finding is protected or not an ordinary file")
            if not is_unchanged(file):
                raise ValueError("File changed since scan; scan again before deleting")
            path = Path(file.path)
            if is_protected_path(path, protected):
                raise ValueError("Protected by Game Grave or your Never Touch list")
            allowed = (looks_like_game_archive(path) or
                       (entry.category == "Old game recording" and
                        path.suffix.casefold() in RECORDING_EXTENSIONS))
            if not path.is_file() or not allowed:
                raise ValueError("No longer a recognized reviewable file")
            # Includes the mandatory disposable byte-exact recovery canary.
            # This is deliberately slower than permanent deletion.
            recycle_file(path)
            try:
                recovery_id = register_recycle(path, file.size, "Graveyard")
            except OSError:
                recovery_id = None
                recovery_warnings += 1
                log_event("Recovery warning", "Undo Center entry not saved",
                          session_id=session, path=str(path), source="The Graveyard")
            log_event("Manual recycled", "Graveyard file moved to Recycle Bin",
                      session_id=session, path=str(path), size_bytes=file.size,
                      source="The Graveyard", result="Recycled",
                      recovery_id=recovery_id)
            completed += 1
        except (OSError, ValueError, RuntimeError) as exc:
            skipped.append(f"{entry.name}: {exc}")
            log_event("Cleanup skipped", str(exc), session_id=session,
                      path=entry.path, source="The Graveyard", result="Skipped")
        if progress is not None:
            progress(position, len(chosen))
    log_event("Cleanup finished",
              f"Graveyard: {completed} recycled, {len(skipped)} skipped. "
              "Recycle Bin may still occupy space.",
              session_id=session, source="The Graveyard")
    return {"completed": completed, "skipped": skipped,
            "recovery_warnings": recovery_warnings, "requested": len(chosen)}


def recycle_old_files(
    files: Iterable[OldFile],
    never_touch: Iterable[str],
    session: str,
    progress: Callable[[int, int], None] | None = None,
) -> dict:
    """Perform a confirmed Old Files deletion using only reversible Windows Shell.

    No UI calls or approval prompts belong here. Every file is rechecked after
    selection; the Windows Shell recovery canary runs before moving real data.
    """
    chosen = tuple(files)
    protected = list(never_touch)
    completed = 0
    skipped: list[str] = []
    recovery_warnings = 0
    log_event("Cleanup started", f"Old Files: selected {len(chosen)}",
              session_id=session, source="Old Files")
    for index, file in enumerate(chosen, 1):
        path = Path(file.path)
        try:
            if not is_unchanged(file):
                raise ValueError("File changed since scan; refresh before deleting")
            if is_protected_path(path, protected):
                raise ValueError("Protected by Game Grave or Never Touch")
            # Never call unlink or a permanent-deletion fallback for user data.
            recycle_file(path)
            try:
                rid = register_recycle(path, file.size, "Old Files")
            except OSError:
                rid = None
                recovery_warnings += 1
                log_event("Recovery warning", "Undo Center entry not saved",
                          session_id=session, path=str(path), source="Old Files")
            log_event("Manual recycled", "Old File moved to Recycle Bin",
                      session_id=session, path=str(path), size_bytes=file.size,
                      source="Old Files", result="Recycled", recovery_id=rid)
            completed += 1
        except (OSError, ValueError, RuntimeError) as exc:
            skipped.append(f"{path.name}: {exc}")
            log_event("Cleanup skipped", str(exc), session_id=session,
                      path=str(path), source="Old Files", result="Skipped")
        if progress is not None:
            progress(index, len(chosen))
    log_event("Cleanup finished",
              f"Old Files: {completed} moved; {len(skipped)} skipped; "
              "Recycle Bin still uses disk space.",
              session_id=session, source="Old Files")
    return {"completed": completed, "skipped": skipped,
            "recovery_warnings": recovery_warnings, "requested": len(chosen)}
