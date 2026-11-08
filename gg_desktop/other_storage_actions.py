"""The only removal Other Storage offers: small launcher cache and log folders, one verified file at a time.

Every file is re-checked right before it moves: it must still be a normal file inside the folder that was
scanned (no links, no hard links), with the same size, date and identity, and not on the Never Touch list.
Game Grave's own protection rules and the Windows Recycle Bin recovery preflight then apply unchanged.
There is no permanent deletion, no bypass of those protections, and a run is limited to 200 files.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat

from core import is_protected_path, log_event, recycle_file
from recovery import register_recycle
from gg_desktop.other_storage_data import MAX_FILES

REPARSE = 0x400


@dataclass(frozen=True)
class PlanFile:
    path: Path
    size: int
    mtime_ns: int
    inode: int
    device: int


@dataclass(frozen=True)
class Plan:
    entry: object
    root: Path
    files: tuple
    skipped: int

    @property
    def size(self):
        return sum(f.size for f in self.files)


def _normal_dir(path):
    try:
        info = Path(path).lstat()
    except OSError:
        return False
    return stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & REPARSE


def _normal_file(path):
    try:
        info = Path(path).lstat()
    except OSError:
        return False
    return (stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode)
            and not getattr(info, "st_file_attributes", 0) & REPARSE and info.st_nlink == 1)


def _inspect_one(entry):
    if not entry.cleanable:
        return None, "Not a launcher cache or log folder small enough to verify file by file"
    root = Path(entry.path)
    if not _normal_dir(root):
        return None, "The folder is missing, linked or redirected"
    files, skipped = [], 0
    for current, subdirs, names in os.walk(root, topdown=True, followlinks=False):
        if not _normal_dir(current):
            return None, "The folder contains an unsafe directory"
        subdirs[:] = [d for d in subdirs if _normal_dir(Path(current) / d)]
        for name in names:
            candidate = Path(current) / name
            if not _normal_file(candidate):
                skipped += 1
                continue
            info = candidate.lstat()
            files.append(PlanFile(candidate, info.st_size, info.st_mtime_ns, info.st_ino, info.st_dev))
            if len(files) > MAX_FILES:
                return None, f"More than {MAX_FILES} files. Nothing was removed"
    if not files:
        return None, "No eligible files remain in this folder"
    return Plan(entry, root, tuple(files), skipped), ""


def inspect(entries):
    """Read-only. [(entry, Plan or None, reason)] with a combined limit of MAX_FILES files."""
    output, total = [], 0
    for entry in entries:
        plan, reason = _inspect_one(entry)
        if plan is not None:
            total += len(plan.files)
            if total > MAX_FILES:
                plan, reason = None, f"Together the checked folders hold more than {MAX_FILES} files. Check fewer"
        output.append((entry, plan, reason))
    return output


def still_matches(plan, file):
    if not _normal_dir(plan.root) or not _normal_file(file.path):
        return False
    try:
        if not file.path.resolve(strict=True).is_relative_to(plan.root.resolve(strict=True)):
            return False
        info = file.path.lstat()
        return (info.st_size, info.st_mtime_ns, info.st_ino, info.st_dev) == (file.size, file.mtime_ns, file.inode, file.device)
    except (OSError, ValueError):
        return False


def recycle(plans, never_touch, session, progress=None):
    """Move the planned files to the Recycle Bin. Returns {'completed', 'skipped', 'requested'}."""
    plans = tuple(plans)
    total = sum(len(p.files) for p in plans)
    if total > MAX_FILES:
        raise ValueError(f"A run is limited to {MAX_FILES} files. Nothing was removed")
    rules = list(never_touch)
    done = completed = warnings = 0
    skipped = []
    log_event("Cleanup started", f"Other Storage: {len(plans)} folders, {total} files", session_id=session,
              source="Other Storage")
    for plan in plans:
        label = f"Other Storage: {plan.entry.name}"
        for file in plan.files:
            done += 1
            try:
                if is_protected_path(file.path, rules):
                    raise ValueError("Protected by Game Grave or your Never Touch list")
                if not still_matches(plan, file):
                    raise ValueError("File changed or is no longer safe to recycle")
                recycle_file(file.path)
                try:
                    recovery_id = register_recycle(file.path, file.size, label)
                except OSError:
                    recovery_id = None
                    warnings += 1
                    log_event("Recovery warning", "Could not save Undo Center entry", session_id=session,
                              path=str(file.path), source=label)
                log_event("Manual recycled", "Other Storage file moved to Recycle Bin", session_id=session,
                          path=str(file.path), size_bytes=file.size, source=label, result="Recycled",
                          recovery_id=recovery_id)
                completed += 1
            except (OSError, ValueError, RuntimeError) as exc:
                skipped.append(f"{file.path.name}: {exc}")
                log_event("Cleanup skipped", str(exc), session_id=session, path=str(file.path), source=label,
                          result="Skipped")
            if progress is not None:
                progress(done, total)
    log_event("Cleanup finished", f"Other Storage: {completed} recycled, {len(skipped)} skipped. "
              "Recycle Bin may still occupy disk space.", session_id=session, source="Other Storage")
    return {"completed": completed, "skipped": skipped, "requested": total, "recovery_warnings": warnings}
