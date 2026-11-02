"""Deliberate, one-time Graveyard override for *user-selected* known items.

The default cleaner and its hard protection rules are unchanged. This module
handles only a selected, currently scanned Graveyard row after a separate,
typed user acknowledgement. No global disable-safety switch, no permanent
delete API, no traversing links/junctions, and no attempt to override Windows
file permissions. Directory Recycle Bin moves are only attempted after the
Windows recovery canary passes and the entire tree is rechecked.
"""
from __future__ import annotations

import ctypes
import hashlib
import os
from pathlib import Path
import stat
import sys
import time
from typing import Any

import core
from core import (
    _has_reparse_component, _is_reparse_point, is_unchanged,
    log_event,
)
from recovery import register_recycle, _bin_script, _run_ps


ACKNOWLEDGEMENT = "RECYCLE"
MAX_TREE_ENTRIES = 100_000
MAX_PATH_LENGTH = 240


class OverrideRefused(ValueError):
    """A deliberately selected Graveyard entry cannot be safely recycled."""


def _identity(path: str | Path) -> str:
    return os.path.normcase(os.path.abspath(str(path))).replace("/", "\\").casefold().rstrip("\\")


def _same_path(a: str | Path, b: str | Path) -> bool:
    return _identity(a) == _identity(b)


def _contains(parent: str | Path, child: str | Path) -> bool:
    try:
        p = _identity(parent)
        c = _identity(child)
        return c == p or c.startswith(p + "\\")
    except (OSError, TypeError, ValueError):
        return False


def _critical_path(target: Path) -> bool:
    """Never override drive roots, OS trees, app roots or broad personal roots."""
    absolute = Path(os.path.abspath(str(target)))
    if _same_path(absolute, Path(absolute.anchor)):
        return True
    home = Path.home()
    roots = [home]
    roots += [home / x for x in (
        "Desktop", "Documents", "Downloads", "Pictures", "Videos",
        "Saved Games", "AppData", "OneDrive")]
    for var in ("WINDIR", "SYSTEMROOT", "ProgramFiles", "ProgramFiles(x86)",
                "ProgramData", "ALLUSERSPROFILE", "LOCALAPPDATA", "APPDATA"):
        value = os.environ.get(var)
        if value:
            roots.append(Path(value))
    # Built-in fallback on Windows when environment is unusual.
    if os.name == "nt" and absolute.anchor:
        roots.extend([Path(absolute.anchor) / x for x in ("Windows", "ProgramData")])
    # Never recycle anything INSIDE the Windows directory, not just Windows itself.
    for var in ("WINDIR", "SYSTEMROOT"):
        root = os.environ.get(var)
        if root and _contains(root, absolute):
            return True
    if os.name == "nt" and absolute.anchor and _contains(
            Path(absolute.anchor) / "Windows", absolute):
        return True
    try:
        own_runtime = Path(sys.executable).resolve(strict=True).parent
        # Prevent self-deletion, but not other games installed in Program Files.
        if _contains(absolute, own_runtime) or _same_path(absolute, own_runtime):
            return True
    except (OSError, ValueError):
        return True
    return any(_same_path(absolute, protected) or _contains(absolute, protected)
               for protected in roots)


def manual_game_entry(game: Any):
    """Produce a protected review row from an existing, verified Games record."""
    from graveyard import GraveyardEntry
    return GraveyardEntry(
        key="manual-game:" + str(game.key),
        name=str(game.name),
        path=str(game.install_path),
        category="Installed game (manual override)",
        apparent_bytes=max(0, game.size_bytes or 0),
        age_days=None, relationship=str(game.status),
        finding="Manually selected installed game. " + str(game.install_evidence),
        protection="Installed game: protected by default; launcher uninstall recommended",
        can_recycle=False,
    )


def override_eligibility(entry: Any, inventory: Any) -> tuple[bool, str]:
    """Authorize ONLY an exact current scan row, never arbitrary typed paths."""
    if entry is None or inventory is None:
        return False, "Run Scan PC and select an actual Graveyard finding first."
    known = getattr(inventory, "graveyard", ())
    in_graveyard = any(
        e == entry and getattr(e, "key", None) == getattr(entry, "key", None)
        and _same_path(getattr(e, "path", ""), getattr(entry, "path", ""))
        for e in known
    )
    # Games view can deliberately select a CURRENT verified installation for
    # advanced review even if the game has not reached the "neglected" age.
    from_game_row = (
        getattr(entry, "category", "") == "Installed game (manual override)"
        and any(
            manual_game_entry(g) == entry
            and "open_folder" in getattr(g, "capabilities", ())
            and str(getattr(g, "status", "")).startswith("Installed")
            and len(getattr(g, "claimed_by", ())) == 1
            for g in getattr(inventory, "games", ())
        )
    )
    if not in_graveyard and not from_game_row:
        return False, "This exact item is not in the current verified scan. Scan again."
    raw_path = str(getattr(entry, "path", ""))
    path = Path(raw_path)
    if not raw_path or len(raw_path) > MAX_PATH_LENGTH:
        return False, "The item has an invalid or overly long Windows path."
    if _critical_path(path):
        return False, "Drive, Windows, application or broad personal folders cannot be recycled here."
    if _has_reparse_component(path):
        return False, "Linked, redirected or missing paths cannot be overridden."
    if not path.is_file() and not path.is_dir():
        return False, "The item is no longer a normal file or folder."
    if getattr(entry, "category", "") == "Old game screenshot":
        return False, "Screenshots still require individual image preview."
    # Installed games and managed mod folders require an exact match to live
    # inventory evidence: a folder merely containing 'mods' is not enough.
    if path.is_dir():
        if getattr(entry, "category", "") == "Installed game (manual override)":
            present = from_game_row
        elif getattr(entry, "category", "") == "Neglected installed game":
            present = any(_same_path(g.install_path, path)
                          for g in getattr(inventory, "steam", ())
                          if getattr(g, "install_path", None))
        elif str(getattr(entry, "key", "")).startswith("mod:"):
            present = any(_same_path(m.path, path)
                          for m in getattr(inventory, "mods", ())
                          if getattr(m, "path", None))
        else:
            present = False
        if not present:
            return False, "This is not an exact known game or mod directory from the current scan."
    elif path.is_file():
        source = getattr(entry, "old_file", None)
        if source is None or not _same_path(source.path, path) or not is_unchanged(source):
            return False, "The selected file is unverified or changed since the scan."
        all_files = (
            *getattr(inventory, "files", ()),
            *getattr(inventory, "recordings", ()),
            *getattr(inventory, "screenshots", ()),
        )
        if not any(source == candidate for candidate in all_files):
            return False, "This file is not part of the current scanned inventory."
    return True, (
        "One-time manual Recycle Bin override. Removing a game, mod or save may "
        "break your installation or destroy progress. Recycle Bin recovery is "
        "not guaranteed if Windows empties it or another program changes it."
    )


def _metadata_fingerprint(path: Path) -> tuple[str, int, int]:
    """Bounded identity fingerprint, rejecting reparse points and hard links.

    No file contents are opened. Includes names, sizes, device IDs, inode and
    modification timestamps to detect changes during the preflight.
    """
    digest = hashlib.sha256()
    total_bytes = 0
    entries = 0

    def add(target: Path, rel: str) -> None:
        nonlocal entries, total_bytes
        entries += 1
        if entries > MAX_TREE_ENTRIES:
            raise OverrideRefused(
                "More than 100,000 entries. Use your game's launcher or Windows Explorer.")
        if _is_reparse_point(target):
            raise OverrideRefused("A link or Windows junction exists within the selected item.")
        state = target.lstat()
        if stat.S_ISREG(state.st_mode):
            if state.st_nlink != 1:
                raise OverrideRefused("Hard-linked files cannot be moved by override.")
            total_bytes += state.st_size
        elif not stat.S_ISDIR(state.st_mode):
            raise OverrideRefused("Special filesystem objects cannot be moved by override.")
        parts = (rel, str(state.st_mode), str(state.st_size), str(state.st_dev),
                 str(state.st_ino), str(state.st_mtime_ns), str(state.st_nlink))
        digest.update(("\0".join(parts) + "\n").encode("utf-8", "surrogatepass"))

    if _has_reparse_component(path):
        raise OverrideRefused("The selected folder is redirected or missing.")
    add(path, ".")
    if path.is_dir():
        for parent, dirs, names in os.walk(path, followlinks=False):
            dirs.sort()
            names.sort()
            folder = Path(parent)
            if _has_reparse_component(folder):
                raise OverrideRefused("The folder changed or contains a redirected parent.")
            for name in dirs:
                child = folder / name
                add(child, str(child.relative_to(path)))
            for name in names:
                child = folder / name
                add(child, str(child.relative_to(path)))
    return digest.hexdigest(), total_bytes, entries


def _recycle_canary_on_local_volume(target: Path) -> bool:
    """Try parent first; otherwise an ordinary writable folder on the SAME disk.

    Protected game installations under Program Files may not permit temporary
    canary creation in steamapps/common. A fallback canary validates the
    actual Windows Recycle Bin volume without modifying a protected directory.
    Windows still makes the final permission decision for the selected item.
    """
    candidates = [target.parent, Path.home() / "Downloads",
                  Path.home() / "Documents", Path.home()]
    seen = set()
    for candidate in candidates:
        if (_identity(candidate) in seen or not candidate.is_dir()
                or _has_reparse_component(candidate)
                or _identity(Path(candidate.anchor)) != _identity(Path(target.anchor))):
            continue
        seen.add(_identity(candidate))
        if core._recycle_canary_passes(candidate):
            return True
    return False


def recycle_selected_override(entry: Any, inventory: Any, never_touch: tuple[str, ...],
                              session: str, *, acknowledged: bool = False) -> dict:
    """A single, deliberate Recycle Bin move; never a permanent-delete fallback."""
    if acknowledged is not True:
        raise OverrideRefused("Explicit one-time user confirmation is required.")
    ok, reason = override_eligibility(entry, inventory)
    if not ok:
        raise OverrideRefused(reason)
    if os.name != "nt" or not core._recycle_shell_session_ready():
        raise OverrideRefused("Override recycling requires an active Windows desktop session.")
    target = Path(entry.path)
    before, size, entries = _metadata_fingerprint(target)
    if len(str(target)) > MAX_PATH_LENGTH or _critical_path(target):
        raise OverrideRefused("Selected path is too long or protected by Windows.")
    drive = Path(target.anchor)
    if ctypes.windll.kernel32.GetDriveTypeW(str(drive)) != 3:
        raise OverrideRefused("Only a local fixed disk is supported.")
    # No bypass of the existing Windows Recycle Bin / Undo canary.
    if not _recycle_canary_on_local_volume(target):
        raise OverrideRefused(
            "Windows cannot verify a recoverable Recycle Bin move here. "
            "No file was moved. Use Windows File Explorer for manual management.")
    ok, reason = override_eligibility(entry, inventory)
    if not ok or _metadata_fingerprint(target)[0] != before:
        raise OverrideRefused(
            "The item changed while Windows was being checked. Scan again.")
    # Recycle Bin move only. Windows permissions and UAC still apply.
    core._shell_recycle_operation(target)
    recovery_warning = ""
    try:
        register_recycle(target, size, "Explicit protected-item override")
    except (OSError, ValueError) as exc:
        recovery_warning = "Undo Center could not save its history entry."
        log_event("Override recovery log warning", str(exc),
                  session_id=session, path=str(target), source="The Graveyard")
    # Windows may have moved an item but no longer report it as recoverable:
    # don't falsely claim verification when that happens.
    try:
        available = _run_ps(_bin_script(str(target))) == "AVAILABLE"
    except (OSError, RuntimeError, TimeoutError, ValueError):
        available = False
    log_event("User override recycled", f"Explicitly approved {entries} entries, {size} bytes",
              session_id=session, path=str(target), size_bytes=size,
              source="The Graveyard",
              result="Recycle Bin verified" if available else "Recovery not verified")
    return {
        "completed": 1, "size_bytes": size, "entries": entries,
        "recovery_verified": available, "recovery_warning": recovery_warning,
    }
