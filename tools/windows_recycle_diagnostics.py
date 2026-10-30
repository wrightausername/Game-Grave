"""Disposable Windows Recycle Bin diagnostics for M1.

Never accepts a user file for deletion. Creates a uniquely named temporary
probe on a disposable local volume, sends ONLY that probe to Windows Shell
and inspects whether the Recycle Bin is visible through two read-only APIs.
This is for test VMs/CI, not a normal background application feature.
"""
from __future__ import annotations

import argparse
import ctypes
import os
import sys
import tempfile
import uuid
from ctypes import wintypes
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class RecycleInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("i64Size", ctypes.c_int64),
        ("i64NumItems", ctypes.c_int64),
    ]


def _native_recycle_inventory(drive: Path) -> dict:
    """Use documented SHQueryRecycleBinW; no file access or mutation."""
    result = RecycleInfo()
    result.cbSize = ctypes.sizeof(RecycleInfo)
    shell = ctypes.windll.shell32
    query = shell.SHQueryRecycleBinW
    query.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(RecycleInfo)]
    query.restype = ctypes.c_long
    error = int(query(str(drive), ctypes.byref(result)))
    return {
        "query_hresult": error,
        "recycle_item_count": int(result.i64NumItems) if error == 0 else None,
        "recycle_size": int(result.i64Size) if error == 0 else None,
    }


def _shell_visibility(name: str, full_path: Path) -> dict:
    """Read-only PowerShell inspection. Never outputs other bin item names."""
    import recovery
    literal = recovery._powershell_literal(name)
    path = recovery._powershell_literal(str(full_path))
    script = (
        "$ErrorActionPreference = 'Stop'\n"
        "$bin = (New-Object -ComObject Shell.Application).Namespace(10)\n"
        "if ($null -eq $bin) { throw 'Cannot access Shell Recycle Bin' }\n"
        "$count = 0; $named = 0; $linked = 0; $origin = 0\n"
        "$probeName = " + literal + "\n"
        "$probePath = " + path + "\n"
        "foreach ($item in $bin.Items()) {\n"
        "  $count += 1\n"
        "  $from = [string]$item.ExtendedProperty('System.Recycle.DeletedFrom')\n"
        "  if ($from) { $origin += 1 }\n"
        "  if ([string]::Equals($item.Name, $probeName, "
        "[StringComparison]::OrdinalIgnoreCase)) {\n"
        "    $named += 1\n"
        "    if ($from -and [string]::Equals("
        "[System.IO.Path]::Combine($from, $item.Name), $probePath, "
        "[StringComparison]::OrdinalIgnoreCase)) { $linked += 1 }\n"
        "  }\n"
        "}\n"
        "'SHELL_ITEM_COUNT=' + $count\n"
        "'NAMED_PROBE_MATCHES=' + $named\n"
        "'FULL_PATH_MATCHES=' + $linked\n"
        "'ITEMS_WITH_ORIGIN_PROPERTY=' + $origin\n"
    )
    try:
        output = recovery._run_ps(script)
    except (OSError, RuntimeError) as exc:
        return {"shell_error": str(exc)[:160]}
    results = {}
    for line in output.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            if key in {"SHELL_ITEM_COUNT", "NAMED_PROBE_MATCHES",
                       "FULL_PATH_MATCHES", "ITEMS_WITH_ORIGIN_PROPERTY"}:
                results[key.lower()] = value.strip()
    return results


def _read_only_probe(drive: Path, original: Path) -> dict:
    """Query both inventory APIs for comparison; do not move any files."""
    output = _native_recycle_inventory(drive)
    output.update(_shell_visibility(original.name, original))
    return output


def run(scratch: Path) -> int:
    if os.name != "nt" or os.environ.get("GG_QA_DISPOSABLE") != "YES":
        print("Refusing to diagnose: requires Windows and explicit disposable QA opt-in.")
        return 2
    from core import _shell_recycle_operation, _is_reparse_point
    folder = scratch.resolve(strict=True)
    if folder == Path(folder.anchor) or folder == Path.home().resolve():
        raise ValueError("Drive root/home is never a disposable QA directory.")
    with tempfile.TemporaryDirectory(prefix="GG-M1-Diag-", dir=folder) as testdir:
        target = Path(testdir) / ("diagnostic-" + uuid.uuid4().hex + ".txt")
        target.write_bytes(b"Game Grave disposable Windows recycle diagnostic")
        drive = Path(target.anchor)
        print("BEFORE", _read_only_probe(drive, target), flush=True)
        try:
            _shell_recycle_operation(target)
        except (OSError, RuntimeError) as exc:
            print("DELETE_REQUEST_FAILED:", str(exc)[:160], flush=True)
            return 1
        print("AFTER", _read_only_probe(drive, target), flush=True)
        if target.exists():
            print("Source still exists after Shell request; not considered recycled.")
            return 1
        # If Shell confirms this exact item, ask it to restore the unique
        # disposable test file and check byte equality. Other bin items untouched.
        from recovery import _bin_script, _run_ps
        try:
            avail = _run_ps(_bin_script(str(target)))
            print("CHECK_STATE:", avail, flush=True)
            if avail != "AVAILABLE":
                print("FAIL: Shell cannot verify recoverability.", flush=True)
                return 1
            restore = _run_ps(_bin_script(str(target), restore=True))
            if restore != "RESTORED" or target.read_bytes() != (
                    b"Game Grave disposable Windows recycle diagnostic"):
                print("FAIL: Shell did not restore matching bytes.", flush=True)
                return 1
            target.unlink()
            print("PASS: Recycled and recovered exact disposable file.", flush=True)
            return 0
        except (OSError, RuntimeError) as exc:
            print("RESTORE_CHECK_FAILED:", str(exc)[:160], flush=True)
            return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit("Explicit --execute is required.")
    raise SystemExit(run(args.scratch))
