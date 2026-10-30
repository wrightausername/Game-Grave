"""M3 Time Machine SHA-256 identifies files hidden by ZIP CRC32 collisions.

Fixed 8-byte CRC collision payloads were generated once for this synthetic
regression fixture. No game data is read, modified or deleted.
"""
import hashlib
import tempfile
import unittest
import zlib
from pathlib import Path

from resurrection_v2 import create_complete_kit
from resurrection_lab import compare_kits


class StrongSnapshotCompareTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.saves = self.root / "Synthetic Saves"
        self.saves.mkdir()
        self.first = self.root / "v1.zip"
        self.second = self.root / "v2.zip"

    def kit(self, path):
        return create_complete_kit("Demo", {"Saves": self.saves}, path)

    def test_crc32_and_file_size_collision_is_still_reported_changed(self):
        left = bytes.fromhex("d8801db225d2ff8e")
        right = bytes.fromhex("040802945f150c12")
        self.assertEqual(len(left), len(right))
        self.assertEqual(zlib.crc32(left), zlib.crc32(right))
        self.assertNotEqual(hashlib.sha256(left).digest(), hashlib.sha256(right).digest())
        item = self.saves / "slot.dat"
        item.write_bytes(left)
        older = self.kit(self.first)
        item.write_bytes(right)
        newer = self.kit(self.second)
        delta = compare_kits(Path(older["manifest"]), Path(newer["manifest"]))
        self.assertEqual(delta["change_count"], 1)
        self.assertEqual(delta["changes"],
                         [{"path": "Saves/slot.dat", "change": "changed"}])
        self.assertGreaterEqual(delta["strong_file_hash_comparisons"], 1)
        self.assertIn("SHA-256", delta["file_identity_method"])
        self.assertTrue(delta["no_overwrite"])
        self.assertEqual(item.read_bytes(), right)

    def test_identical_contents_are_not_false_positive(self):
        item = self.saves / "slot.dat"
        item.write_bytes(b"same content for both versions")
        first = self.kit(self.first)
        second = self.kit(self.second)
        delta = compare_kits(Path(first["manifest"]), Path(second["manifest"]))
        self.assertEqual(delta["change_count"], 0)
        self.assertEqual(delta["strong_file_hash_comparisons"], 1)


if __name__ == "__main__":
    unittest.main()
