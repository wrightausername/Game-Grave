"""M3 release-hardening tests. All files are synthetic temporary fixtures."""
import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import resurrection_v2
from kit_discovery import _root_safe
from resurrection_lab import prepare_pc_transfer, rehearse_kit, list_snapshots
from resurrection_v2 import create_complete_kit, restore_kit, inspect_restore


class KitTransactionalIntegrityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.saves = self.home / "Synthetic Saves"
        self.saves.mkdir()
        (self.saves / "slot.sav").write_bytes(b"dummy-progress-only")
        self.backup = self.home / "example.zip"
        self.parent = self.home / "Recovery"
        self.parent.mkdir()

    def _kit(self):
        return create_complete_kit(
            "Synthetic Game", {"Saves": self.saves}, self.backup)

    def test_successful_restore_records_exact_verified_archive_digest(self):
        created = self._kit()
        plan = inspect_restore(Path(created["manifest"]), self.parent)
        self.assertEqual(plan["archive_sha256"],
                         hashlib.sha256(self.backup.read_bytes()).hexdigest())
        recovered = restore_kit(Path(created["manifest"]), self.parent, approved=True)
        self.assertEqual(
            (Path(recovered["target"]) / "Saves" / "slot.sav").read_bytes(),
            b"dummy-progress-only")
        self.assertEqual((self.saves / "slot.sav").read_bytes(),
                         b"dummy-progress-only")

    def test_archive_mutation_during_restore_rolls_back_private_staging_only(self):
        created = self._kit()
        original_hash = resurrection_v2._sha256
        calls = []

        def apparent_tamper(path):
            calls.append(Path(path))
            if len(calls) == 1:
                return original_hash(path)
            return "0" * 64

        with patch.object(resurrection_v2, "_sha256", side_effect=apparent_tamper):
            with self.assertRaisesRegex(ValueError, "archive changed during restore"):
                restore_kit(Path(created["manifest"]), self.parent, approved=True)
        self.assertEqual(len(calls), 2)
        self.assertEqual(list(self.parent.iterdir()), [])
        self.assertEqual((self.saves / "slot.sav").read_bytes(),
                         b"dummy-progress-only")
        self.assertTrue(self.backup.exists())

    def test_new_partial_file_created_by_someone_else_is_not_deleted(self):
        partial = self.backup.with_name(self.backup.name + ".partial")
        original_constructor = zipfile.ZipFile

        def collide(archive, mode="r", *args, **kwargs):
            if Path(archive) == partial and mode == "x":
                partial.write_bytes(b"do not delete another process's file")
                raise FileExistsError("raced with unrelated file")
            return original_constructor(archive, mode, *args, **kwargs)

        with patch.object(resurrection_v2.zipfile, "ZipFile", side_effect=collide):
            with self.assertRaises(FileExistsError):
                self._kit()
        self.assertEqual(partial.read_bytes(), b"do not delete another process's file")
        self.assertFalse(self.backup.exists())
        self.assertFalse((self.home / "example.zip.ggkit.json").exists())
        self.assertEqual((self.saves / "slot.sav").read_bytes(),
                         b"dummy-progress-only")

    def test_rehearsal_and_pc_transfer_deny_junctioned_parent_directories(self):
        created = self._kit()
        ordinary = self.home / "Scratch"
        ordinary.mkdir()
        linked = self.home / "Redirected"
        try:
            linked.symlink_to(ordinary, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Test runner cannot create a directory symlink")
        self.assertFalse(_root_safe(linked))
        with self.assertRaisesRegex(ValueError, "linked or redirected ancestors"):
            rehearse_kit(Path(created["manifest"]), linked)
        with self.assertRaisesRegex(ValueError, "linked or redirected ancestors"):
            prepare_pc_transfer(Path(created["manifest"]), linked, approved=True)
        with self.assertRaisesRegex(ValueError, "linked or redirected ancestors"):
            list_snapshots(linked)
        self.assertEqual(list(ordinary.iterdir()), [])
        self.assertTrue((self.saves / "slot.sav").exists())


if __name__ == "__main__":
    unittest.main()
