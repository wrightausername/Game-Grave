"""Resurrection Lab behavior tests using only disposable synthetic directories.

No real game, mod manager, user library, or external network is accessed.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from resurrection_v2 import create_complete_kit, inspect_restore
from resurrection_lab import (
    missing_pieces, compare_kits, plan_living_update, create_living_update,
    rehearse_kit, list_snapshots, prepare_pc_transfer,
)


class ResurrectionLabTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)
        self.saves = self.root / "Saved Games"
        self.mods = self.root / "Manager mods"
        self.profile = self.root / "MO2 Profile"
        (self.saves / "slot").mkdir(parents=True)
        (self.mods / "SkyUI").mkdir(parents=True)
        self.profile.mkdir(parents=True)
        (self.saves / "slot" / "save.dat").write_bytes(b"progress 1")
        (self.mods / "SkyUI" / "skyui.esp").write_bytes(b"active mod")
        (self.profile / "modlist.txt").write_text("+SkyUI\n-Optional\n", encoding="utf-8")
        self.sources = {"Saves": self.saves, "Mods": self.mods, "Profiles": self.profile}
        self.old = self.root / "Skyrim-2026-01.zip"
        self.new = self.root / "Skyrim-2026-02.zip"

    def kit(self, destination=None, sources=None, name="Skyrim", manager=True):
        ctx = ({"kind": "MO2", "auto_discovered": True, "profile": "Default"}
               if manager else None)
        return create_complete_kit(
            name, sources or self.sources, destination or self.old,
            manager_context=ctx)

    def test_missing_pieces_detects_broken_enabled_mod_without_guessing_links(self):
        (self.profile / "modlist.txt").write_text("+SkyUI\n+Missing Critical Mod\n-Optional\n")
        k = self.kit()
        result = missing_pieces(Path(k["manifest"]))
        self.assertTrue(result["archive_verified"])
        self.assertEqual(result["missing_count"], 1)
        self.assertIn("Missing Critical Mod", result["missing_enabled_mods"])
        self.assertEqual(result["readiness"], "Needs attention")
        self.assertFalse(result["complete_game_recovery_verified"])
        self.assertNotIn("download_url", result)

    def test_archive_integrity_does_not_equal_compatibility(self):
        k = self.kit()
        result = missing_pieces(Path(k["manifest"]))
        self.assertEqual(result["missing_count"], 0)
        self.assertFalse(result["restore_rehearsed"])
        self.assertFalse(result["complete_game_recovery_verified"])
        self.assertTrue(any("not independently verified" in s for s in result["unknown"]))
        self.assertIn("setup recovery unverified", result["readiness"])

    def test_unmanaged_kit_has_unknown_dependency_status(self):
        k = self.kit(manager=False)
        result = missing_pieces(Path(k["manifest"]))
        self.assertEqual(result["manager"], "unknown")
        self.assertTrue(any("ownership" in line.lower() for line in result["unknown"]))

    def test_kit_snapshot_comparison_detects_add_delete_and_change(self):
        first = self.kit()
        (self.saves / "slot" / "save.dat").write_bytes(b"progress 2")
        (self.mods / "SkyUI" / "skyui.esp").unlink()
        (self.mods / "SkyUI" / "newmod.esp").write_bytes(b"new")
        second = self.kit(destination=self.new)
        delta = compare_kits(Path(first["manifest"]), Path(second["manifest"]))
        self.assertTrue(delta["full_archive_checksums_verified"])
        self.assertEqual(delta["change_count"], 3)
        self.assertEqual({c["change"] for c in delta["changes"]},
                         {"added", "missing in newer snapshot", "changed"})
        self.assertTrue(Path(first["archive"]).is_file())
        self.assertTrue(Path(second["archive"]).is_file())
        self.assertTrue(delta["no_overwrite"])

    def test_time_machine_rejects_different_game_kit(self):
        first = self.kit()
        second = self.kit(destination=self.new, name="Starfield")
        with self.assertRaisesRegex(ValueError, "different recorded games"):
            compare_kits(Path(first["manifest"]), Path(second["manifest"]))

    def test_local_history_lists_versions_but_does_not_claim_verified(self):
        first = self.kit()
        second = self.kit(destination=self.new)
        result = list_snapshots(self.root, game="Skyrim")
        self.assertEqual(len(result), 2)
        self.assertTrue(all(not r["verified"] for r in result))
        self.assertEqual({r["manifest"] for r in result},
                         {first["manifest"], second["manifest"]})
        self.assertEqual(list_snapshots(self.root, game="Wrong Game"), [])

    def test_living_kit_skips_identical_and_preserves_old_after_changes(self):
        old = self.kit()
        initial = plan_living_update(Path(old["manifest"]), self.sources)
        self.assertFalse(initial["changed"])
        self.assertEqual(initial["change_count"], 0)
        with self.assertRaisesRegex(ValueError, "no new version needed"):
            create_living_update(Path(old["manifest"]), self.sources, self.new,
                                 approved=True,
                                 expected_source_fingerprint=initial["source_fingerprint"])
        (self.saves / "slot" / "save.dat").write_bytes(b"progress 3")
        plan = plan_living_update(Path(old["manifest"]), self.sources)
        self.assertTrue(plan["changed"])
        self.assertEqual(plan["change_count"], 1)
        with self.assertRaises(PermissionError):
            create_living_update(Path(old["manifest"]), self.sources, self.new)
        revised = create_living_update(
            Path(old["manifest"]), self.sources, self.new,
            approved=True, expected_source_fingerprint=plan["source_fingerprint"])
        self.assertTrue(Path(revised["archive"]).exists())
        self.assertTrue(Path(old["archive"]).exists())
        self.assertEqual(inspect_restore(Path(old["manifest"]))["files"], 3)
        self.assertFalse(revised["manager_evidence_carried_over"])
        after = json.loads(Path(revised["manifest"]).read_text())
        self.assertNotIn("manager_context", after)

    def test_changed_during_review_requires_new_permission(self):
        old = self.kit()
        (self.saves / "slot" / "save.dat").write_bytes(b"updated")
        plan = plan_living_update(Path(old["manifest"]), self.sources)
        (self.saves / "slot" / "save.dat").write_bytes(b"updated again")
        with self.assertRaisesRegex(ValueError, "changed since"):
            create_living_update(Path(old["manifest"]), self.sources, self.new,
                                 approved=True,
                                 expected_source_fingerprint=plan["source_fingerprint"])
        self.assertFalse(self.new.exists())

    def test_revisions_refuse_missing_role_source(self):
        old = self.kit()
        with self.assertRaisesRegex(ValueError, "same backup categories"):
            plan_living_update(Path(old["manifest"]), {"Saves": self.saves})

    def test_rehearsal_extracts_and_hashes_then_cleans_own_temporary_copy(self):
        created = self.kit()
        scratch = self.root / "Scratch"
        scratch.mkdir()
        saved_before = (self.saves / "slot" / "save.dat").read_bytes()
        result = rehearse_kit(Path(created["manifest"]), scratch)
        self.assertTrue(result["isolated_extract_verified"])
        self.assertEqual(result["files_verified"], 3)
        self.assertFalse(result["game_launch_verified"])
        self.assertFalse(result["manager_reconnection_verified"])
        self.assertTrue(result["temporary_files_cleaned"])
        self.assertEqual(list(scratch.iterdir()), [])
        self.assertEqual((self.saves / "slot" / "save.dat").read_bytes(), saved_before)

    def test_rehearsal_refuses_tampering_before_creating_scratch_files(self):
        created = self.kit()
        scratch = self.root / "Scratch"
        scratch.mkdir()
        Path(created["archive"]).write_bytes(b"corrupted")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            rehearse_kit(Path(created["manifest"]), scratch)
        self.assertFalse(list(scratch.iterdir()))

    def test_rehearsal_receipt_updates_readiness_only_for_same_archive_hash(self):
        created = self.kit()
        scratch = self.root / "Scratch"
        scratch.mkdir()
        with patch("resurrection_lab.config_dir", return_value=self.root / "GGData"):
            before = missing_pieces(Path(created["manifest"]))
            self.assertFalse(before["restore_rehearsed"])
            result = rehearse_kit(Path(created["manifest"]), scratch, record=True)
            self.assertTrue(result["receipt_recorded"])
            after = missing_pieces(Path(created["manifest"]))
            self.assertTrue(after["restore_rehearsed"])
            self.assertFalse(after["complete_game_recovery_verified"])
            receipts = (self.root / "GGData" / "kit_rehearsals.json").read_text()
            self.assertNotIn(str(self.root), receipts)
            self.assertFalse(list(scratch.iterdir()))
            (self.saves / "slot" / "save.dat").write_bytes(b"new version")
            updated = self.kit(destination=self.new)
            self.assertFalse(missing_pieces(Path(updated["manifest"]))["restore_rehearsed"])

    def test_baseline_hash_change_refuses_preapproved_living_version(self):
        first = self.kit()
        (self.saves / "slot" / "save.dat").write_bytes(b"edited")
        plan = plan_living_update(Path(first["manifest"]), self.sources)
        with self.assertRaisesRegex(ValueError, "previous kit changed"):
            create_living_update(Path(first["manifest"]), self.sources, self.new,
                                 approved=True,
                                 expected_source_fingerprint=plan["source_fingerprint"],
                                 expected_previous_archive_hash="deadbeef" * 8)
        self.assertFalse(self.new.exists())

    def test_transfer_folder_contains_only_verified_portable_parts_and_guide(self):
        created = self.kit()
        usb = self.root / "USB"
        usb.mkdir()
        with self.assertRaises(PermissionError):
            prepare_pc_transfer(Path(created["manifest"]), usb)
        transfer = prepare_pc_transfer(Path(created["manifest"]), usb, approved=True)
        folder = Path(transfer["target"])
        self.assertTrue(transfer["portable_copy_verified"])
        self.assertFalse(transfer["launcher_installation_included"])
        self.assertTrue((folder / "READ_ME_FIRST.txt").is_file())
        self.assertFalse((folder / "TRANSFER_INCOMPLETE.txt").exists())
        self.assertTrue((folder / Path(created["archive"]).name).exists())
        self.assertTrue(inspect_restore(Path(transfer["manifest"]))["verified"])
        self.assertEqual((self.saves / "slot" / "save.dat").read_bytes(), b"progress 1")
        self.assertNotIn(str(self.root), (folder / "READ_ME_FIRST.txt").read_text())
        with self.assertRaises(FileExistsError):
            prepare_pc_transfer(Path(created["manifest"]), usb, approved=True)

    def test_transfer_refuses_corrupted_zip_and_does_not_create_folder(self):
        k = self.kit()
        usb = self.root / "USB"
        usb.mkdir()
        with Path(k["archive"]).open("ab") as stream:
            stream.write(b"oops")
        with self.assertRaises(ValueError):
            prepare_pc_transfer(Path(k["manifest"]), usb, approved=True)
        self.assertEqual(list(usb.iterdir()), [])

    def test_missing_piece_report_handles_kit_without_mods(self):
        kit = self.kit(sources={"Saves": self.saves}, manager=False)
        result = missing_pieces(Path(kit["manifest"]))
        self.assertEqual(result["roles"], ["Saves"])
        self.assertTrue(any("Mod binaries" in line for line in result["unknown"]))


if __name__ == "__main__":
    unittest.main()
