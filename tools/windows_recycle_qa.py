"""Opt-in native Windows disposable Recycle Bin / Undo smoke test.

This intentionally moves ONE newly created, uniquely named harmless text file
into the Windows Recycle Bin, then tries to recover it. It never acts on any
user-supplied file. Use an isolated throwaway runner/VM, not a real game folder.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch


def run(scratch: Path) -> int:
    if os.name != "nt":
        print("FAIL: This integration test requires native Windows.", file=sys.stderr)
        return 2
    if os.environ.get("GG_QA_DISPOSABLE") != "YES":
        print("FAIL: GG_QA_DISPOSABLE=YES must be explicitly set.", file=sys.stderr)
        return 2
    try:
        base = scratch.resolve(strict=True)
        if not base.is_dir() or base == Path(base.anchor) or base == Path.home().resolve():
            raise ValueError("Choose a normal disposable test directory, not a drive or home root.")
    except (OSError, ValueError) as exc:
        print(f"FAIL: Unsafe QA scratch location: {exc}", file=sys.stderr)
        return 2

    # Running "python tools/windows_recycle_qa.py" sets sys.path[0] to
    # tools/, not the repository root. Import app code from this checked-out
    # repository explicitly, never from another installed Game Grave version.
    repo = Path(__file__).resolve().parents[1]
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    import core
    import recovery

    marker = b"Game Grave disposable Windows Recycle Bin / Undo test"
    with tempfile.TemporaryDirectory(prefix="GameGrave-M1-QA-", dir=base) as work:
        folder = Path(work)
        qa_settings = folder / "qa-settings"
        filename = f"throwaway-{uuid.uuid4().hex}.txt"
        item = folder / filename
        item.write_bytes(marker)
        if core._has_reparse_component(item) or core.is_protected_path(item):
            print("FAIL: QA file unexpectedly linked or protected.", file=sys.stderr)
            return 2
        with patch.object(core, "config_dir", return_value=qa_settings), \
                patch.object(recovery, "config_dir", return_value=qa_settings):
            try:
                print("STEP: recycle exactly one disposable plain text file")
                core.recycle_file(item)
                if item.exists():
                    raise RuntimeError("Recycler reported success but original still exists.")
                history_id = recovery.register_recycle(item, len(marker), "Windows QA")
                print("STEP: check unique Windows Shell Recycle Bin record")
                available = recovery.check_restore(history_id)
                if available != "AVAILABLE":
                    raise RuntimeError(f"Windows Shell lookup was {available}; restore was not safe.")
                print("STEP: restore uniquely matched file through Undo Center")
                returned = recovery.restore(history_id)
                if returned != "RESTORED" or not item.is_file() or item.read_bytes() != marker:
                    raise RuntimeError(
                        f"Unexpected restore result {returned}; returned bytes were not verified.")
                records = recovery.get_records()
                if not any(r.get("id") == history_id and r.get("state") == "Restored"
                           for r in records):
                    raise RuntimeError("Undo Center did not record verified restoration.")
            except (OSError, ValueError, RuntimeError) as exc:
                print(f"FAIL: Windows integration requires investigation: {exc}",
                      file=sys.stderr)
                return 1
    print("PASS: Disposable Windows Recycle Bin and Undo Center round-trip verified.")
    print("NOTE: This is NOT proof of localized Windows 10/11 support or release readiness.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--execute", action="store_true",
                        help="Explicitly allow ONE temporary file to be recycled and restored.")
    args = parser.parse_args(argv)
    if not args.execute:
        print("FAIL: --execute required; no file operations performed.", file=sys.stderr)
        return 2
    return run(args.scratch)


if __name__ == "__main__":
    raise SystemExit(main())
