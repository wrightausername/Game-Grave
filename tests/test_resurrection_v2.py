"""Resurrection Kit v2 preservation and restore guardrails.

Every fixture uses disposable temporary files. No test writes to game installs.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from resurrection_kit import create_resurrection_kit
from resurrection_v2 import (create_complete_kit, inspect_restore, restore_kit,
                             _relative_name)


class KitV2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.saves = self.root / "Actual Saves"
        self.mods = self.root / "MO2 Profile"
        (self.saves / "Slot 1").mkdir(parents=True)
        self.mods.mkdir()
        (self.saves / "Slot 1" / "Save.sav").write_bytes(b"important progress")
        (self.mods / "modlist.txt").write_text("+SkyUI\n-ModNotUsedByThisProfile\n")
        self.zip = self.root / "Skyrim-kit.zip"
        self.restore_parent = self.root / "Recovery"
        self.restore_parent.mkdir()

    def _make(self):
        return create_complete_kit("Skyrim", {"Saves": self.saves, "Profiles": self.mods}, self.zip)

    def test_round_trip_preserves_two_roots_without_modifying_sources(self):
        original_save = (self.saves / "Slot 1" / "Save.sav").read_bytes()
        original_modlist = (self.mods / "modlist.txt").read_bytes()
        created = self._make()
        self.assertEqual(created["files"], 2)
        self.assertEqual(set(created["roles"]), {"Saves", "Profiles"})
        manifest = json.loads(Path(created["manifest"]).read_text())
        self.assertEqual(manifest["schema"], 2)
        self.assertNotIn(str(self.root), json.dumps(manifest))
        preview = inspect_restore(Path(created["manifest"]), self.restore_parent)
        self.assertTrue(preview["verified"])
        self.assertTrue(preview["no_overwrite"])
        self.assertEqual(preview["files"], 2)
        with self.assertRaises(PermissionError):
            restore_kit(Path(created["manifest"]), self.restore_parent)
        restored = restore_kit(Path(created["manifest"]), self.restore_parent, approved=True)
        self.assertTrue(restored["restored"])
        self.assertTrue(restored["no_overwrite"])
        self.assertEqual((Path(restored["target"]) / "Saves" / "Slot 1" / "Save.sav").read_bytes(),
                         original_save)
        self.assertEqual((Path(restored["target"]) / "Profiles" / "modlist.txt").read_bytes(),
                         original_modlist)
        self.assertEqual((self.saves / "Slot 1" / "Save.sav").read_bytes(), original_save)
        self.assertEqual((self.mods / "modlist.txt").read_bytes(), original_modlist)
        with self.assertRaises(FileExistsError):
            restore_kit(Path(created["manifest"]), self.restore_parent, approved=True)

    def test_legacy_save_folder_kit_is_restorable_as_new_copy(self):
        legacy = create_resurrection_kit("Old Game", self.saves, self.zip)
        preview = inspect_restore(Path(legacy["manifest"]), self.restore_parent)
        self.assertEqual(preview["schema"], 1)
        restored = restore_kit(Path(legacy["manifest"]), self.restore_parent, approved=True)
        self.assertEqual((Path(restored["target"]) / "Saves" / "Slot 1" / "Save.sav").read_bytes(),
                         b"important progress")

    def test_tampering_rejected_before_restore_creates_folder(self):
        created = self._make()
        with self.zip.open("ab") as stream:
            stream.write(b"corruption")
        with self.assertRaisesRegex(ValueError, "checksum"):
            restore_kit(Path(created["manifest"]), self.restore_parent, approved=True)
        self.assertEqual(list(self.restore_parent.iterdir()), [])

    def test_duplicate_restore_destination_is_refused_without_deleting_it(self):
        created = self._make()
        existing = self.restore_parent / "Skyrim_Restored"
        existing.mkdir()
        (existing / "Keep.sav").write_bytes(b"untouchable")
        with self.assertRaises(FileExistsError):
            inspect_restore(Path(created["manifest"]), self.restore_parent)
        self.assertEqual((existing / "Keep.sav").read_bytes(), b"untouchable")

    def test_nested_input_folders_refused(self):
        with self.assertRaisesRegex(ValueError, "overlap"):
            create_complete_kit("Game",
                                {"Saves": self.saves, "Mods": self.saves / "Slot 1"},
                                self.zip)
        self.assertFalse(self.zip.exists())

    def test_relative_components_block_windows_and_zip_slip(self):
        for name in ("../escape.sav", "/absolute.sav", "Saves/../escape.sav",
                     "Saves/C:\\Windows", "Saves/CON.txt", "Saves/Foo.", 
                     "Saves//file.sav", "C:/game.sav", "Saves/d:abc.sav"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    _relative_name(name)

    def test_malicious_archive_path_rejected_even_with_matching_checksum(self):
        manifest = self.root / "evil.zip.ggkit.json"
        payload = self.root / "evil.zip"
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("Saves/../../ESCAPE.sav", b"bad")
        digest = hashlib.sha256(payload.read_bytes()).hexdigest()
        manifest.write_text(json.dumps({"schema": 2, "game": "Bad",
                                        "archive": payload.name,
                                        "archive_sha256": digest, "files": 1}))
        with self.assertRaises(ValueError):
            inspect_restore(manifest, self.restore_parent)
        self.assertFalse((self.root / "ESCAPE.sav").exists())

    def test_case_collision_in_zip_rejected(self):
        payload = self.root / "collision.zip"
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("Saves/Save.sav", b"one")
            archive.writestr("Saves/save.sav", b"two")
        manifest = self.root / "collision.zip.ggkit.json"
        manifest.write_text(json.dumps({"schema": 2, "game": "Bad",
                       "archive": payload.name,
                       "archive_sha256": hashlib.sha256(payload.read_bytes()).hexdigest(),
                       "files": 2}))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            inspect_restore(manifest, self.restore_parent)

    def test_file_directory_conflict_in_zip_rejected(self):
        payload = self.root / "prefix.zip"
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("Saves/a", b"one")
            archive.writestr("Saves/a/b.sav", b"two")
        manifest = self.root / "prefix.zip.ggkit.json"
        manifest.write_text(json.dumps({"schema": 2, "game": "Bad",
                       "archive": payload.name,
                       "archive_sha256": hashlib.sha256(payload.read_bytes()).hexdigest(),
                       "files": 2}))
        with self.assertRaisesRegex(ValueError, "collision"):
            inspect_restore(manifest, self.restore_parent)

    def test_symlink_files_and_junction_like_sources_not_backed_up(self):
        outside = self.root / "private.secret"
        outside.write_bytes(b"private")
        link = self.saves / "LinkedSecret.sav"
        try:
            link.symlink_to(outside)
        except (NotImplementedError, OSError):
            self.skipTest("Symlinks unavailable on this test filesystem")
        created = self._make()
        with zipfile.ZipFile(self.zip) as archive:
            self.assertNotIn("Saves/LinkedSecret.sav", archive.namelist())
        with self.assertRaises(ValueError):
            create_complete_kit("Game", {"Saves": link}, self.root / "other.zip")
        self.assertTrue(Path(created["manifest"]).exists())

    def test_corrupt_sidecar_and_missing_archive_fail_closed(self):
        manifest = self.root / "untrusted.ggkit.json"
        manifest.write_text('{"schema":2,"archive":"../stolen.zip","archive_sha256":"abc"}')
        with self.assertRaises(ValueError):
            inspect_restore(manifest, self.restore_parent)
        self.assertEqual(list(self.restore_parent.iterdir()), [])

    def test_insufficient_space_stops_before_restore(self):
        created = self._make()
        import resurrection_v2 as module
        with patch.object(module.shutil, "disk_usage", return_value=(100, 100, 0)):
            with self.assertRaisesRegex(OSError, "free space"):
                inspect_restore(Path(created["manifest"]), self.restore_parent)
        self.assertEqual(list(self.restore_parent.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
