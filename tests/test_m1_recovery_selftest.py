"""M1 voluntary Windows safety check. All test input is disposable."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import safety_selftest
from ui import GameGraveApp


class DisposableUndoSelfCheckTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def test_byte_identical_recycle_and_restore_removes_only_owned_probe(self):
        stored = {}
        def recycle(path):
            stored[str(path)] = path.read_bytes()
            path.unlink()
        def shell(command):
            if "InvokeVerb('undelete')" in command:
                name, value = next(iter(stored.items()))
                Path(name).write_bytes(value)
                return "RESTORED"
            return "AVAILABLE"
        unrelated = self.folder / "important-user-fixture.txt"
        unrelated.write_bytes(b"do not touch")
        with patch("safety_selftest._desktop_local_disk", return_value=True), \
             patch("safety_selftest.recycle_file", side_effect=recycle), \
             patch("safety_selftest._run_ps", side_effect=shell):
            report = safety_selftest.check_disposable_undo(self.folder)
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["undo_byte_identical"])
        self.assertFalse(report["release_gate_accepted"])
        self.assertEqual(unrelated.read_bytes(), b"do not touch")
        self.assertEqual(list(self.folder.iterdir()), [unrelated])

    def test_missing_recycle_bin_entry_fails_without_claiming_success(self):
        with patch("safety_selftest._desktop_local_disk", return_value=True), \
             patch("safety_selftest.recycle_file", side_effect=lambda path: path.unlink()), \
             patch("safety_selftest._run_ps", return_value="NOT_FOUND"):
            with self.assertRaisesRegex(safety_selftest.SafetySelfCheckError, "restored"):
                safety_selftest.check_disposable_undo(self.folder)
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_corrupt_restored_bytes_cannot_be_claimed_or_cleaned_as_owned(self):
        location = []
        def recycle(path):
            location.append(path)
            path.unlink()
        def shell(command):
            if "InvokeVerb('undelete')" in command:
                location[0].write_bytes(b"not the original marker")
                return "RESTORED"
            return "AVAILABLE"
        with patch("safety_selftest._desktop_local_disk", return_value=True), \
             patch("safety_selftest.recycle_file", side_effect=recycle), \
             patch("safety_selftest._run_ps", side_effect=shell):
            with self.assertRaisesRegex(safety_selftest.SafetySelfCheckError, "different bytes"):
                safety_selftest.check_disposable_undo(self.folder)
        self.assertTrue(location[0].exists(), "Do not erase unexpected replacement bytes")
        self.assertEqual(location[0].read_bytes(), b"not the original marker")

    def test_never_touch_root_and_missing_desktop_block_before_probe(self):
        with patch("safety_selftest._desktop_local_disk", return_value=True) as session:
            with self.assertRaises(safety_selftest.SafetySelfCheckError):
                safety_selftest.check_disposable_undo(
                    self.folder, never_touch=(str(self.folder),))
        session.assert_not_called()
        with patch("safety_selftest._desktop_local_disk", return_value=False):
            with self.assertRaisesRegex(safety_selftest.SafetySelfCheckError, "interactive Windows"):
                safety_selftest.check_disposable_undo(self.folder)
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_declined_button_does_not_create_file_or_start_worker(self):
        fake = SimpleNamespace(
            scanning=False, cleanup_running=False, _selfcheck_busy=False,
            settings={"scan_folder": str(self.folder), "never_touch": []},
        )
        with patch("ui.filedialog.askdirectory", return_value=str(self.folder)), \
             patch("ui.messagebox.askyesno", return_value=False) as approve, \
             patch("ui.threading.Thread") as worker:
            GameGraveApp._start_disposable_undo_check(fake)
        approve.assert_called_once()
        worker.assert_not_called()
        self.assertFalse(fake._selfcheck_busy)
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_confirmed_button_only_queues_worker_and_never_runs_shell_on_tk_thread(self):
        fake = SimpleNamespace(
            scanning=False, cleanup_running=False, _selfcheck_busy=False,
            settings={"scan_folder": str(self.folder), "never_touch": []},
            status_text=SimpleNamespace(set=Mock()), events=Mock(),
        )
        with patch("ui.filedialog.askdirectory", return_value=str(self.folder)), \
             patch("ui.messagebox.askyesno", return_value=True), \
             patch("ui.threading.Thread") as worker, \
             patch("ui.check_disposable_undo") as check:
            GameGraveApp._start_disposable_undo_check(fake)
        self.assertTrue(fake._selfcheck_busy)
        worker.assert_called_once()
        worker.return_value.start.assert_called_once()
        check.assert_not_called()
        self.assertEqual(list(self.folder.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
