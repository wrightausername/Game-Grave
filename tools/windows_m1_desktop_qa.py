"""Native Windows desktop M1 checklist using *only* disposable data.

This is not a release certificate. It is an interactive QA exercise for human
Windows 10/11 testers. No real games, saves, libraries, or account data used.
It requires explicit --execute and GG_QA_DISPOSABLE=YES and uses an exclusive
new temporary folder under an ordinary, local, fixed-disk scratch directory.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _operating_system() -> dict:
    """Only public OS metadata. Do not capture user/device or filesystem paths."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as key:
            product = str(winreg.QueryValueEx(key, "ProductName")[0])[:120]
    except (ImportError, OSError):
        product = "Unknown Windows edition"
    return {
        "product": product,
        "windows_release": platform.win32_ver()[0],
        "windows_version": platform.win32_ver()[1],
        "python_version": platform.python_version(),
    }


def run_checks(scratch: Path) -> dict:
    import core
    import recovery
    from resurrection_v2 import create_complete_kit, inspect_restore, restore_kit

    result = {
        "schema": 1,
        "test_family": "Game Grave M1 disposable Windows desktop QA",
        "system": _operating_system(),
        "manual_ui_tested": False,
        "real_game_files_used": False,
        "results": [],
        "release_accepted": False,
    }

    def add(label: str, state: str, detail: str = "") -> None:
        result["results"].append({"test": label, "state": state, "detail": detail[:160]})

    with tempfile.TemporaryDirectory(prefix="GG-M1-LocalQA-", dir=scratch) as temp:
        folder = Path(temp)
        qa_settings = folder / "qa-settings"
        saves = folder / "Saved Games"
        saves.mkdir()
        sample = saves / "Game Grave - 保存.txt"
        bytes_saved = b"Game Grave disposable Unicode save test"
        sample.write_bytes(bytes_saved)

        try:
            if not core.is_protected_path(sample):
                raise AssertionError("Built-in saves protection missing")
            try:
                core.recycle_file(sample)
            except (ValueError, RuntimeError):
                pass
            else:
                raise AssertionError("A built-in protected file was recycled")
            if sample.read_bytes() != bytes_saved:
                raise AssertionError("Protected test file changed")
            add("Built-in save protection", "PASS")
        except (AssertionError, OSError, ValueError) as exc:
            add("Built-in save protection", "FAIL", type(exc).__name__)

        try:
            regular = folder / "linked-copy.txt"
            regular.write_bytes(b"hardlinked harmless QA bytes")
            sibling = folder / "second-hardlink.txt"
            os.link(regular, sibling)
            if regular.stat().st_nlink < 2:
                raise AssertionError("Hard links were not created on this volume")
            try:
                core.recycle_file(regular)
            except (ValueError, RuntimeError):
                pass
            else:
                raise AssertionError("Hardlinked test source was recycled")
            if regular.read_bytes() != sibling.read_bytes():
                raise AssertionError("Hardlinked source was changed")
            add("Hardlink cleanup refusal", "PASS")
        except PermissionError:
            add("Hardlink cleanup refusal", "SKIP", "No permission for hardlink fixture")
        except (OSError, ValueError, AssertionError) as exc:
            add("Hardlink cleanup refusal", "FAIL", type(exc).__name__)

        try:
            shortcut = folder / "QA redirected parent"
            shortcut.symlink_to(saves, target_is_directory=True)
            linked_save = shortcut / sample.name
            if not core._has_reparse_component(linked_save):
                raise AssertionError("Linked ancestor was not detected")
            try:
                core.recycle_file(linked_save)
            except (ValueError, RuntimeError):
                pass
            else:
                raise AssertionError("Cleanup followed a redirected parent folder")
            if sample.read_bytes() != bytes_saved:
                raise AssertionError("Saved file changed via redirected path")
            add("Linked-directory ancestor refusal", "PASS")
        except (PermissionError, NotImplementedError):
            add("Linked-directory ancestor refusal", "SKIP", "Symlink requires local policy support")
        except (OSError, AssertionError, ValueError) as exc:
            add("Linked-directory ancestor refusal", "FAIL", type(exc).__name__)

        try:
            zip_path = folder / "GG_M1_Kit.zip"
            kit = create_complete_kit("Game Grave M1 QA", {"Saves": saves}, zip_path)
            manifest = Path(kit["manifest"])
            if not inspect_restore(manifest)["verified"]:
                raise AssertionError("Kit verification failed")
            target_parent = folder / "Recovery"
            target_parent.mkdir()
            staged = restore_kit(manifest, target_parent, approved=True)
            received = Path(staged["target"]) / "Saves" / sample.name
            if received.read_bytes() != bytes_saved:
                raise AssertionError("Staged Unicode save differs")
            try:
                restore_kit(manifest, target_parent, approved=True)
            except FileExistsError:
                pass
            else:
                raise AssertionError("Kit restore overwrote preexisting target")
            if received.read_bytes() != bytes_saved or sample.read_bytes() != bytes_saved:
                raise AssertionError("Kit recovery changed a retained save")
            add("Kit backup, Unicode recovery and collision refusal", "PASS")
        except (OSError, ValueError, AssertionError, RuntimeError) as exc:
            add("Kit backup, Unicode recovery and collision refusal",
                "FAIL", type(exc).__name__)

        with patch.object(core, "config_dir", return_value=qa_settings), \
                patch.object(recovery, "config_dir", return_value=qa_settings):
            try:
                missing = folder / ("never-existed-" + uuid.uuid4().hex + ".txt")
                recovery_id = recovery.register_recycle(missing, 0, "M1 QA")
                status = recovery.check_restore(recovery_id)
                if status != "NOT_FOUND":
                    raise AssertionError("Missing item did not yield NOT_FOUND")
                add("Missing Recycle Bin item reports honest status", "PASS")
            except (OSError, ValueError, AssertionError, RuntimeError) as exc:
                add("Missing Recycle Bin item reports honest status",
                    "FAIL", type(exc).__name__)

            original = folder / ("GG-Undo-" + uuid.uuid4().hex + ".txt")
            text = b"Game Grave disposable Undo QA file"
            original.write_bytes(text)
            try:
                core.recycle_file(original)
                if original.exists():
                    raise AssertionError("Shell reported recycling, but original remained")
                event = recovery.register_recycle(original, len(text), "M1 QA")
                if recovery.check_restore(event) != "AVAILABLE":
                    raise AssertionError("Recycle Bin item not available")
                original.write_bytes(b"newer collision content")
                try:
                    recovery.restore(event)
                except ValueError:
                    pass
                else:
                    raise AssertionError("Undo replaced a conflicting file")
                if original.read_bytes() != b"newer collision content":
                    raise AssertionError("Undo altered conflicting file")
                # This deletes only the exact test collision created by this
                # script; the original test file remains in Windows Recycle Bin.
                original.unlink()
                if recovery.restore(event) != "RESTORED":
                    raise AssertionError("Undo did not restore exact test item")
                if original.read_bytes() != text:
                    raise AssertionError("Restored bytes do not match")
                add("Recycle Bin, Undo, and no-overwrite conflict", "PASS")
            except (OSError, ValueError, AssertionError, RuntimeError) as exc:
                add("Recycle Bin, Undo, and no-overwrite conflict",
                    "FAIL", type(exc).__name__)
                # Do not tamper with anything in Windows Recycle Bin.
                # The single test file can be restored manually if needed.

    result["automated_disposable_checks_passed"] = bool(result["results"]) and all(
        row["state"] == "PASS" for row in result["results"])
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Run disposable Windows M1 safety/Undo tests and print a privacy-limited report.")
    parser.add_argument("--scratch", type=Path, required=True,
                        help="Existing ordinary folder on a local fixed Windows drive.")
    parser.add_argument("--execute", action="store_true",
                        help="Explicitly consent to recycling and recovering tiny script-created files.")
    parser.add_argument("--report", type=Path, help="Optional JSON report output path.")
    args = parser.parse_args(argv)
    if not args.execute or os.environ.get("GG_QA_DISPOSABLE") != "YES" or os.name != "nt":
        print("REFUSED: Windows, --execute and GG_QA_DISPOSABLE=YES are required.",
              file=sys.stderr)
        return 2
    import core
    try:
        scratch = args.scratch.resolve(strict=True)
        if (not scratch.is_dir() or core._has_reparse_component(scratch)
                or scratch in (Path(scratch.anchor), Path.home().resolve())
                or core.is_protected_path(scratch)
                or core._is_reparse_point(scratch)):
            raise ValueError("Scratch folder is not an ordinary unprotected Windows subfolder.")
        if core.ctypes.windll.kernel32.GetDriveTypeW(str(Path(scratch.anchor))) != 3:
            raise ValueError("Scratch must be on a local fixed drive.")
        report = run_checks(scratch)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        if args.report:
            path = args.report.resolve(strict=False)
            if path.exists() or path.is_symlink():
                raise FileExistsError("Report target already exists; choose a new filename.")
            with path.open("x", encoding="utf-8") as out:
                json.dump(report, out, indent=2, ensure_ascii=False)
            print("A JSON QA report was written to the explicitly selected path.")
        if report["automated_disposable_checks_passed"]:
            print("PASS: Disposable M1 recovery checks passed on this Windows instance.")
            print("NOT RELEASE SIGN-OFF: manual UI, language, installed-app, and another OS remain.")
            return 0
        print("FAIL / SKIP: Check the individual test results before M1 sign-off.", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print("QA REFUSED / ERROR:", str(exc)[:180], file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
