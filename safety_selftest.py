"""Explicit M1 Windows Recycle Bin + Undo self-check using only app-created bytes.

Never touches a user game, save, mod or recording. No periodic checks, no
telemetry, no user-file deletion and no change to real Undo Center history.
A passing self-check is not M1 Windows 10/11 release sign-off.
"""
from __future__ import annotations

import ctypes
import os
import secrets
import tempfile
from pathlib import Path

from core import (
    _has_reparse_component, _is_reparse_point, _recycle_shell_session_ready,
    is_protected_path, recycle_file, safe_scan_root,
)
from recovery import _bin_script, _run_ps


class SafetySelfCheckError(RuntimeError):
    """Windows test-file recovery could not be proved."""


def _desktop_local_disk(folder: Path) -> bool:
    if os.name != "nt" or not _recycle_shell_session_ready():
        return False
    try:
        return ctypes.windll.kernel32.GetDriveTypeW(str(Path(folder.anchor))) == 3
    except (OSError, AttributeError, ValueError):
        return False


def _is_exact_owned_marker(path: Path, marker: bytes) -> bool:
    """Only remove the precise disposable bytes this check itself created."""
    try:
        return (not _has_reparse_component(path)
                and not _is_reparse_point(path)
                and path.is_file() and path.stat().st_nlink == 1
                and path.stat().st_size == len(marker)
                and path.read_bytes() == marker)
    except (OSError, ValueError):
        return False


def check_disposable_undo(folder: Path, never_touch: tuple[str, ...] = ()) -> dict:
    """Create one unique tiny file on the selected fixed disk; recycle and restore.

    The user's explicit UI confirmation is required BEFORE calling this method.
    Core's ordinary safety preflight is still mandatory for this disposable
    file. A failure never falls back to unverified permanent deletion.
    """
    root = Path(folder).expanduser()
    if (not safe_scan_root(root) or _has_reparse_component(root)
            or is_protected_path(root, list(never_touch))):
        raise SafetySelfCheckError(
            "Choose an ordinary unprotected local folder, not a system, game, "
            "redirected or Never Touch folder.")
    if not _desktop_local_disk(root):
        raise SafetySelfCheckError(
            "This safety check requires an interactive Windows desktop and a local fixed disk.")
    marker = b"Game Grave disposable Win Undo check: " + secrets.token_bytes(16)
    probe = None
    try:
        descriptor, raw = tempfile.mkstemp(
            dir=root, prefix="GG-owned-UndoCheck-", suffix=".txt")
        probe = Path(raw)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(marker)
            stream.flush()
            os.fsync(stream.fileno())
        if not _is_exact_owned_marker(probe, marker):
            raise SafetySelfCheckError("The test file changed before the Recycle Bin check.")
        # This operation runs core's mandatory verified canary and only
        # submits the single random file just created by this check.
        recycle_file(probe)
        if probe.exists():
            raise SafetySelfCheckError("Windows did not move the disposable test file.")
        if _run_ps(_bin_script(str(probe))) != "AVAILABLE":
            raise SafetySelfCheckError("Windows did not confirm that the test file can be restored.")
        if _run_ps(_bin_script(str(probe), restore=True)) != "RESTORED":
            raise SafetySelfCheckError("Windows did not confirm that Undo restored the test file.")
        if not _is_exact_owned_marker(probe, marker):
            raise SafetySelfCheckError("Undo restored different bytes or an unsafe file type.")
        return {
            "schema": 1,
            "status": "PASS",
            "recycle_bin_round_trip_verified": True,
            "undo_byte_identical": True,
            "used_disposable_test_data_only": True,
            "user_data_touched": False,
            "release_gate_accepted": False,
        }
    except SafetySelfCheckError:
        raise
    except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
        raise SafetySelfCheckError(
            "Windows could not complete the disposable Recycle Bin and Undo check. "
            "Do not rely on Game Grave deletion until the cause is reviewed.") from exc
    finally:
        # Clean up ONLY the exact random marker belonging to this operation,
        # regardless of whether it is the initial file or restored copy.
        # If it stayed in the Recycle Bin after a failed restore, leave it:
        # never delete or manipulate other bin entries.
        if probe is not None and _is_exact_owned_marker(probe, marker):
            try:
                probe.unlink()
            except OSError:
                pass
