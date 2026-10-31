"""M3 disposable Windows recovery pipeline acceptance exercises.

CI only. Uses uniquely owned temporary fixtures, never user games, saves,
libraries, accounts or manager data. Not a substitute for Windows 10/11
desktop acceptance or external real-MO2 clean-install reconnection.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def run_disposable_suite(workspace: Path) -> dict:
    from resurrection_v2 import create_complete_kit, inspect_restore, restore_kit
    from resurrection_lab import (
        compare_kits, create_living_update, missing_pieces, plan_living_update,
        prepare_pc_transfer, rehearse_kit,
    )
    checks: list[dict] = []

    def verify(name: str, fn) -> None:
        try:
            fn()
            checks.append({"test": name, "status": "PASS"})
        except Exception as exc:
            checks.append({"test": name, "status": "FAIL",
                           "reason": type(exc).__name__})

    with tempfile.TemporaryDirectory(prefix="GG-M3-QA-", dir=workspace) as temp:
        root = Path(temp)
        saves = root / "Disposable Saves"
        mods = root / "Disposable Mods"
        profiles = root / "Disposable MO2 Profile"
        (saves / "Slot 1").mkdir(parents=True)
        (mods / "SkyUI").mkdir(parents=True)
        profiles.mkdir()
        save = saves / "Slot 1" / "保存.sav"
        mod = mods / "SkyUI" / "plugin.esp"
        modlist = profiles / "modlist.txt"
        payload = b"GG disposable savedata\x00\x01"
        save.write_bytes(payload)
        mod.write_bytes(b"Game Grave fixture plugin v1")
        modlist.write_text("+SkyUI\n", encoding="utf-8")
        sources = {"Saves": saves, "Mods": mods, "Profiles": profiles}
        kit = root / "test-kit.zip"
        restore_root = root / "Recovery"
        restore_root.mkdir()
        rehearsal_root = root / "Rehearsal"
        rehearsal_root.mkdir()
        transfer_root = root / "Portable"
        transfer_root.mkdir()
        old_manifest = None

        def build():
            nonlocal old_manifest
            created = create_complete_kit(
                "Disposable MO2 Game", sources, kit,
                manager_context={"kind": "MO2", "profile": "QA Profile"})
            old_manifest = Path(created["manifest"])
            assert created["files"] == 3
            assert kit.is_file() and old_manifest.is_file()
            assert hashlib.sha256(kit.read_bytes()).hexdigest() == json.loads(
                old_manifest.read_text(encoding="utf-8"))["archive_sha256"]
            assert save.read_bytes() == payload

        verify("Create multi-role kit with SHA and unchanged source", build)
        if old_manifest is None:
            return {"schema": 1, "suite": "M3 disposable Windows QA", "checks": checks,
                    "all_passed": False, "manual_windows_desktop_accepted": False}

        def preview():
            result = inspect_restore(old_manifest, restore_root)
            assert result["verified"] is True
            assert set(result["roles"]) == {"Saves", "Mods", "Profiles"}
            assert result["files"] == 3
            readiness = missing_pieces(old_manifest)
            assert readiness["missing_count"] == 0
            assert readiness["complete_game_recovery_verified"] is False

        verify("Preview multi-root MO2 evidence and disclose unknowns", preview)

        def stage_and_collide():
            restored = restore_kit(old_manifest, restore_root, approved=True)
            dest = Path(restored["target"])
            assert (dest / "Saves" / "Slot 1" / "保存.sav").read_bytes() == payload
            assert (dest / "Mods" / "SkyUI" / "plugin.esp").read_bytes() == mod.read_bytes()
            assert (dest / "Profiles" / "modlist.txt").read_text(encoding="utf-8") == "+SkyUI\n"
            try:
                restore_kit(old_manifest, restore_root, approved=True)
            except FileExistsError:
                pass
            else:
                raise AssertionError("A second staged restore could overwrite a previous one")
            assert (dest / "Saves" / "Slot 1" / "保存.sav").read_bytes() == payload
            assert save.read_bytes() == payload

        verify("Byte-identical staged restore and no-overwrite collision refusal", stage_and_collide)

        def rehearse():
            result = rehearse_kit(old_manifest, rehearsal_root, record=False)
            assert result["isolated_extract_verified"] is True
            assert result["temporary_files_cleaned"] is True
            assert result["game_launch_verified"] is False
            assert not list(rehearsal_root.iterdir())
            assert save.read_bytes() == payload

        verify("Isolated complete-recovery rehearsal cleans scratch", rehearse)

        newer_manifest = None
        new_kit = root / "test-kit-v2.zip"

        def version():
            nonlocal newer_manifest
            unchanged = plan_living_update(old_manifest, sources)
            assert unchanged["changed"] is False
            mod.write_bytes(b"Game Grave fixture plugin v2 - changed")
            plan = plan_living_update(old_manifest, sources)
            assert plan["changed"] is True
            created = create_living_update(
                old_manifest, sources, new_kit,
                approved=True,
                expected_source_fingerprint=plan["source_fingerprint"],
                expected_previous_archive_hash=plan["previous_archive_hash"])
            newer_manifest = Path(created["manifest"])
            comparison = compare_kits(old_manifest, newer_manifest)
            assert comparison["change_count"] >= 1
            assert comparison["full_archive_checksums_verified"] is True
            assert kit.exists() and new_kit.exists() and kit != new_kit

        verify("Living Kit immutable version, content change and SHA comparison", version)

        def transfer():
            manifest = newer_manifest or old_manifest
            result = prepare_pc_transfer(manifest, transfer_root, approved=True)
            dest = Path(result["target"])
            assert result["portable_copy_verified"] is True
            assert (dest / "READ_ME_FIRST.txt").is_file()
            assert not (dest / "TRANSFER_INCOMPLETE.txt").exists()
            assert inspect_restore(Path(result["manifest"]))["verified"] is True
            assert save.read_bytes() == payload

        verify("Portable copy keeps verified ZIP, manifest and recovery guide", transfer)

        def tamper_refused():
            damaged = root / "Damaged"
            damaged.mkdir()
            from shutil import copy2
            copy2(kit, damaged / kit.name)
            copy2(old_manifest, damaged / old_manifest.name)
            with (damaged / kit.name).open("ab") as stream:
                stream.write(b"tampered-on-purpose")
            before = set(restore_root.iterdir())
            try:
                restore_kit(damaged / old_manifest.name, restore_root, approved=True)
            except ValueError:
                pass
            else:
                raise AssertionError("Tampered ZIP was accepted")
            assert set(restore_root.iterdir()) == before
            assert save.read_bytes() == payload

        verify("Corrupt archive never changes prior restores or source", tamper_refused)

    return {
        "schema": 1,
        "suite": "M3 disposable Windows QA",
        "checks": checks,
        "all_passed": bool(checks) and all(x["status"] == "PASS" for x in checks),
        "manual_windows_desktop_accepted": False,
        "real_manager_used": False,
        "real_game_files_used": False,
        "limitations": "No installed-app UI, real MO2/Vortex, game launch, or Win10/11 desktop sign-off.",
    }


def main() -> int:
    if os.name != "nt" or os.environ.get("GITHUB_ACTIONS") != "true" or (
            os.environ.get("GG_M3_QA_DISPOSABLE") != "YES"):
        print("REFUSED: only an explicitly opted-in ephemeral Windows GitHub runner is supported.")
        return 2
    workspace = Path(os.environ["GITHUB_WORKSPACE"]).resolve(strict=True)
    scratch = workspace / "_ci_temp"
    scratch.mkdir(mode=0o700, exist_ok=True)
    if scratch.is_symlink() or not scratch.is_dir():
        print("REFUSED: linked or missing disposable scratch directory.")
        return 2
    result = run_disposable_suite(scratch)
    target = scratch / "m3-disposable-report.json"
    with target.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result["all_passed"]:
        print("PASS: M3 disposable CI only. Real Windows 10/11 manual release gate remains OPEN.")
        return 0
    print("FAIL: M3 disposable Windows recovery suite detected a failure.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
