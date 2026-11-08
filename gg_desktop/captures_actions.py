"""Captures actions that touch files: Recycle Bin removal in small verified runs, and copying out.

Removal re-checks every file right before it moves: it must still be a normal file inside a known capture folder
with the same size, date and identity, with no links or hard links, and not protected. Game Grave's own protection
rules and the Windows Recycle Bin recovery check then apply unchanged. There is no permanent deletion.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import stat

from core import _has_reparse_component, is_protected_path, is_unchanged, log_event, recycle_file
from gg_desktop.models import _path_key
from recovery import register_recycle

MAX_RUN = 100
MAX_COPY = 500


@dataclass(frozen=True)
class Plan:
    capture: object
    reason: str = ""

    @property
    def ok(self):
        return not self.reason


def inside(path, roots):
    key = _path_key(str(path))
    return any(key.startswith(_path_key(str(root)).rstrip("\\") + "\\") for root in roots)


def check_one(capture, roots, never_touch):
    path = Path(capture.path)
    if not inside(path, roots):
        return "Not inside a known capture folder"
    if is_protected_path(path, never_touch):
        return "Protected by Game Grave or your Never Touch list"
    try:
        state = os.lstat(path)
    except OSError:
        return "No longer exists"
    if not stat.S_ISREG(state.st_mode) or _has_reparse_component(path):
        return "Linked or redirected file"
    if state.st_nlink != 1:
        return "Has more than one hard link"
    if not is_unchanged(capture.old_file):
        return "File changed since the scan"
    return ""


def inspect(captures, roots, never_touch):
    """Read-only. One Plan per capture; the combined run is limited to MAX_RUN files."""
    plans = [Plan(c, check_one(c, roots, never_touch)) for c in captures]
    if len(plans) > MAX_RUN:
        plans = [Plan(p.capture, p.reason or f"A run is limited to {MAX_RUN} files") if i >= MAX_RUN else p
                 for i, p in enumerate(plans)]
    return plans


def recycle(captures, roots, never_touch, session, progress=None):
    """Move verified captures to the Recycle Bin. Returns {'completed', 'skipped', 'requested', 'moved'}."""
    captures = list(captures)
    if len(captures) > MAX_RUN:
        raise ValueError(f"A run is limited to {MAX_RUN} files. Nothing was removed")
    log_event("Cleanup started", f"Captures: {len(captures)} files", session_id=session, source="Captures")
    moved, skipped, warnings = [], [], 0
    for index, capture in enumerate(captures, 1):
        path = Path(capture.path)
        try:
            reason = check_one(capture, roots, never_touch)
            if reason:
                raise ValueError(reason)
            recycle_file(path)
            try:
                recovery_id = register_recycle(path, capture.size, "Captures")
            except OSError:
                recovery_id = None
                warnings += 1
                log_event("Recovery warning", "Could not save Undo Center entry", session_id=session, path=str(path),
                          source="Captures")
            log_event("Manual recycled", "Capture moved to Recycle Bin", session_id=session, path=str(path),
                      size_bytes=capture.size, source="Captures", result="Recycled", recovery_id=recovery_id)
            moved.append(capture.key)
        except (OSError, ValueError, RuntimeError) as exc:
            skipped.append(f"{path.name}: {exc}")
            log_event("Cleanup skipped", str(exc), session_id=session, path=str(path), source="Captures", result="Skipped")
        if progress is not None:
            progress(index, len(captures))
    log_event("Cleanup finished", f"Captures: {len(moved)} recycled, {len(skipped)} skipped. "
              "Recycle Bin may still occupy disk space.", session_id=session, source="Captures")
    return {"completed": len(moved), "skipped": skipped, "requested": len(captures), "moved": moved,
            "recovery_warnings": warnings}


def unique_name(folder, name):
    target = Path(folder) / name
    stem, suffix, number = target.stem, target.suffix, 1
    while target.exists():
        number += 1
        target = Path(folder) / f"{stem} ({number}){suffix}"
    return target


def copy_to(captures, destination, canceled=lambda: False, progress=None):
    """Copy files into `destination` without overwriting anything. Originals are never changed."""
    destination = Path(destination)
    if len(captures) > MAX_COPY:
        raise ValueError(f"Copy at most {MAX_COPY} files at a time.")
    if not destination.is_dir() or _has_reparse_component(destination):
        raise ValueError("Choose a normal local folder.")
    copied, skipped = [], []
    for index, capture in enumerate(captures, 1):
        if canceled():
            raise InterruptedError("Copy canceled")
        source = Path(capture.path)
        try:
            if _has_reparse_component(source) or not source.is_file():
                raise ValueError("Linked or missing file")
            target = unique_name(destination, source.name)
            shutil.copy2(source, target)
            copied.append(str(target))
        except (OSError, ValueError) as exc:
            skipped.append(f"{source.name}: {exc}")
        if progress is not None:
            progress(index, len(captures))
    return {"copied": copied, "skipped": skipped}
