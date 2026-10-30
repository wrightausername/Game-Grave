"""M1 Recycle Bin canary uses only disposable files and fails closed."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import core
import recovery


class RecycleCanaryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_missing_recycle_bin_entry_blocks_real_file_operation(self):
        original = self.root / "important-user-file.txt"
        original.write_bytes(b"please keep")
        seen = []

        def fake_shell(path):
            self.assertTrue(path.name.startswith("gg-safe-recycle-"))
            self.assertEqual(path.parent, self.root)
            seen.append(path)
            path.unlink()  # Only the temporary file created inside the probe.

        with patch.object(core, "_shell_recycle_operation", side_effect=fake_shell), \
                patch.object(recovery, "_run_ps", return_value="NOT_FOUND"):
            self.assertFalse(core._recycle_canary_passes(self.root))
        self.assertEqual(len(seen), 1)
        self.assertEqual(original.read_bytes(), b"please keep")
        self.assertEqual([p for p in self.root.iterdir()], [original])

    def test_recovery_available_and_verifiably_restored_passes_probe(self):
        saved = []
        marker = b"Game Grave safe Recycle Bin canary"

        def fake_shell(path):
            saved.append(path)
            self.assertEqual(path.read_bytes(), marker)
            path.unlink()

        def fake_ps(script):
            if "InvokeVerb('RESTORE')" in script:
                saved[0].write_bytes(marker)
                return "RESTORED"
            return "AVAILABLE"

        with patch.object(core, "_shell_recycle_operation", side_effect=fake_shell), \
                patch.object(recovery, "_run_ps", side_effect=fake_ps):
            self.assertTrue(core._recycle_canary_passes(self.root))
        self.assertEqual(len(saved), 1)
        self.assertFalse(saved[0].exists())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_failed_shell_operation_cleans_its_own_canary_and_stops(self):
        def fail(_path):
            raise OSError("Shell refused to recycle this canary")

        with patch.object(core, "_shell_recycle_operation", side_effect=fail):
            self.assertFalse(core._recycle_canary_passes(self.root))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_bad_or_modified_recovery_bytes_do_not_unlock_recycle(self):
        location = []
        def shell(path):
            location.append(path)
            path.unlink()
        def ps(script):
            if "InvokeVerb('RESTORE')" in script:
                location[0].write_bytes(b"not the canary bytes")
                return "RESTORED"
            return "AVAILABLE"
        with patch.object(core, "_shell_recycle_operation", side_effect=shell), \
                patch.object(recovery, "_run_ps", side_effect=ps):
            self.assertFalse(core._recycle_canary_passes(self.root))
        self.assertEqual(location[0].read_bytes(), b"not the canary bytes")


if __name__ == "__main__":
    unittest.main()
