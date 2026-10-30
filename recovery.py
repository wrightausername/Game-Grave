"""Local Recycle Bin history + cautious in-app restore for Windows.

Never creates a deletion path. Records are append-only state transitions and
recovery is refused on ambiguous matches rather than restoring the wrong item.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import uuid
from datetime import datetime
from pathlib import Path

from core import config_dir, log_event


def _log_path():
    return config_dir() / "undo.json"


def get_records() -> list[dict]:
    try:
        data = json.loads(_log_path().read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError, TypeError):
        return []


def _write(records):
    target = _log_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps(records[-2000:], indent=2), encoding="utf-8")
    temp.replace(target)


def register_recycle(original: Path, size: int, action: str = "Manual") -> str:
    """Call only after recycle_file succeeds, not before."""
    event_id = str(uuid.uuid4())
    records = get_records()
    records.append({"id": event_id, "path": str(original), "size": max(0, size),
                    "time": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "action": action, "state": "Not checked",
                    "note": "In Recycle Bin if Windows has not emptied it."})
    _write(records)
    return event_id


def _run_ps(source: str) -> str:
    if os.name != "nt":
        raise RuntimeError("Recycle Bin restoration is available on Windows only.")
    cmd = base64.b64encode(source.encode("utf-16le")).decode("ascii")
    process = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive",
                              "-EncodedCommand", cmd], text=True, capture_output=True,
                             timeout=24, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if process.returncode:
        raise RuntimeError((process.stderr or process.stdout or "Windows Shell failed")[:380])
    return process.stdout.strip()


def _powershell_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _bin_script(path: str, restore=False) -> str:
    """Use original location and name; restore only if exactly one match.

    Windows Shell COM is localized; ExtendedProperty is preferred, with the
    localized details string fallback. An unavailable/mismatched property
    means we refuse to restore (never guess).
    """
    action = r'''
if ($matches.Count -eq 1) {
    # Recheck at the last possible moment. Otherwise Windows Shell may
    # rename/reposition an item over a newly recreated game save.
    if (Test-Path -LiteralPath $original) {
        'ORIGINAL_EXISTS'
    } else {
        $matches[0].InvokeVerb('RESTORE')
        Start-Sleep -Milliseconds 500
        if (Test-Path -LiteralPath $original) { 'RESTORED' } else { 'UNVERIFIED' }
    }
} elseif ($matches.Count -eq 0) { 'NOT_FOUND' } else { 'AMBIGUOUS' }
''' if restore else r'''
if ($matches.Count -eq 1) { 'AVAILABLE' }
elseif ($matches.Count -eq 0) { 'NOT_FOUND' }
else { 'AMBIGUOUS' }
'''
    return r'''$ErrorActionPreference = 'Stop'
$original = ''' + _powershell_literal(path) + r'''
$bin = (New-Object -ComObject Shell.Application).Namespace(10)
if ($null -eq $bin) { throw 'Recycle Bin cannot be accessed' }
$matches = @()
foreach ($item in $bin.Items()) {
    # .Name is an Explorer DISPLAY NAME, often without a hidden extension
    # (e.g., GG-canary instead of GG-canary.txt). Windows confirms the exact
    # filename including extension lives in the System.FileName property.
    # Never guess the extension or use a localized GetDetailsOf column.
    $from = [string]$item.ExtendedProperty('System.Recycle.DeletedFrom')
    $fileName = [string]$item.ExtendedProperty('System.FileName')
    if (-not $from -or -not $fileName) { continue }
    $candidate = [System.IO.Path]::Combine($from, $fileName)
    if ([string]::Equals($candidate, $original, [StringComparison]::OrdinalIgnoreCase)) {
        $matches += $item
    }
}
''' + action


def check_restore(event_id: str) -> str:
    records = get_records()
    row = next((r for r in records if r.get("id") == event_id), None)
    if row is None:
        raise ValueError("Recovery entry missing")
    if row.get("state") == "Restored":
        return "RESTORED"
    path = str(row.get("path", ""))
    if Path(path).exists():
        result = "ORIGINAL_EXISTS"
    else:
        result = _run_ps(_bin_script(path))
    if result == "AVAILABLE":
        row["state"] = "Available"
        row["note"] = "Windows reports a matching Recycle Bin item."
    elif result == "NOT_FOUND":
        row["state"] = "Not found"
        row["note"] = "Not found. Windows may have emptied the bin."
    elif result == "AMBIGUOUS":
        row["state"] = "Needs review"
        row["note"] = "More than one matching file; restore manually through Windows."
    else:
        row["state"] = "Needs review"
        row["note"] = "A file already exists at the original path."
    _write(records)
    return result


def restore(event_id: str) -> str:
    records = get_records()
    row = next((r for r in records if r.get("id") == event_id), None)
    if row is None:
        raise ValueError("Recovery entry missing")
    if row.get("state") == "Restored":
        return "RESTORED"
    path = str(row.get("path", ""))
    if Path(path).exists():
        raise ValueError("The original file path already exists. Restore manually to avoid overwriting it.")
    result = _run_ps(_bin_script(path, restore=True))
    if result == "RESTORED":
        row["state"] = "Restored"
        row["note"] = "Restored to the original path through Windows Shell."
        _write(records)
        log_event("Restored from Recycle Bin", path)
    elif result == "NOT_FOUND":
        row["state"] = "Not found"
        row["note"] = "Not in Recycle Bin, possibly emptied or removed elsewhere."
        _write(records)
    else:
        row["state"] = "Needs review"
        row["note"] = f"Windows reported {result}; no successful restore was verified."
        _write(records)
    return result
