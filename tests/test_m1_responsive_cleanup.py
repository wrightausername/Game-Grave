"""M1: responsive Graveyard cleanup with no unapproved or irreversible fallback.

Uses only temporary, disposable files. Native Windows Shell compatibility is
checked separately on the Windows CI runner.
"""
from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core import OldFile
from graveyard import build_graveyard
from cleanup_actions import recycle_reviewed_entries
from ui import GameGraveApp


def fixture(root: Path, *, protected: bool = False):
    file = root / "skyrim-mod.zip"
    file.write_bytes(b"disposable archive")
    stamp = time.time() - 900 * 86400
    os.utime(file, (stamp, stamp))
    record = OldFile(str(file), file.stat().st_size, file.stat().st_mtime)
    results = build_graveyard([], [], [record], 365,
                              never_touch=[str(file)] if protected else [])
    return file, results[0]


class WorkerSafetyTests(unittest.TestCase):
    def test_unavailable_windows_recovery_cannot_move_the_real_candidate(self):
        with tempfile.TemporaryDirectory() as root:
            file, entry = fixture(Path(root))
            progress = []
            with patch("cleanup_actions.log_event"), \
                 patch("cleanup_actions.recycle_file",
                       side_effect=RuntimeError("Windows Recycle Bin unavailable")) as mover, \
                 patch("cleanup_actions.register_recycle") as register:
                result = recycle_reviewed_entries([entry], [], "test-session",
                                                   progress=lambda a, b: progress.append((a, b)))
            self.assertEqual(result["completed"], 0)
            self.assertEqual(len(result["skipped"]), 1)
            self.assertEqual(result["recovery_warnings"], 0)
            self.assertEqual(progress, [(1, 1)])
            mover.assert_called_once_with(file)
            register.assert_not_called()
            self.assertTrue(file.is_file())

    def test_personal_protection_is_rechecked_even_after_approval(self):
        with tempfile.TemporaryDirectory() as root:
            file, entry = fixture(Path(root))
            with patch("cleanup_actions.log_event"), \
                 patch("cleanup_actions.recycle_file") as mover:
                result = recycle_reviewed_entries([entry], [str(file)], "test-session")
            self.assertEqual(result["completed"], 0)
            self.assertEqual(len(result["skipped"]), 1)
            mover.assert_not_called()
            self.assertTrue(file.exists())

    def test_modified_file_is_skipped_in_worker(self):
        with tempfile.TemporaryDirectory() as root:
            file, entry = fixture(Path(root))
            file.write_bytes(b"new and different data")
            with patch("cleanup_actions.log_event"), \
                 patch("cleanup_actions.recycle_file") as mover:
                result = recycle_reviewed_entries([entry], [], "test-session")
            self.assertEqual(result["completed"], 0)
            self.assertIn("changed", result["skipped"][0])
            mover.assert_not_called()
            self.assertTrue(file.is_file())

    def test_move_success_is_recorded_and_undo_failure_is_explicit(self):
        with tempfile.TemporaryDirectory() as root:
            file, entry = fixture(Path(root))
            with patch("cleanup_actions.log_event") as log, \
                 patch("cleanup_actions.recycle_file", side_effect=lambda p: p.unlink()), \
                 patch("cleanup_actions.register_recycle", side_effect=OSError("blocked")):
                result = recycle_reviewed_entries([entry], [], "test-session")
            self.assertEqual(result["completed"], 1)
            self.assertEqual(result["recovery_warnings"], 1)
            self.assertFalse(file.exists())
            self.assertTrue(any(call.args[0] == "Recovery warning" for call in log.call_args_list))

    def test_protected_row_never_accepted(self):
        with tempfile.TemporaryDirectory() as root:
            file, entry = fixture(Path(root), protected=True)
            with patch("cleanup_actions.log_event"), \
                 patch("cleanup_actions.recycle_file") as mover:
                result = recycle_reviewed_entries([entry], [], "test-session")
            self.assertEqual(result["completed"], 0)
            mover.assert_not_called()
            self.assertTrue(file.exists())


class UiThreadBoundaryTests(unittest.TestCase):
    def test_approval_starts_worker_without_blocking_tk_with_recycle(self):
        with tempfile.TemporaryDirectory() as root:
            file, entry = fixture(Path(root))
            app = SimpleNamespace(
                graveyard_lookup={entry.key: entry},
                settings={"never_touch": []},
                scanning=False,
                cleanup_running=False,
                status_text=SimpleNamespace(set=Mock()),
                scan_button=Mock(),
                _grave_sync_actions=Mock(),
                events=Mock(),
            )
            with patch("ui.messagebox.askyesno", return_value=True), \
                 patch("ui.threading.Thread") as worker, \
                 patch("ui.recycle_reviewed_entries") as mover:
                GameGraveApp._grave_recycle_ids(app, [entry.key])
            self.assertTrue(app.cleanup_running)
            worker.assert_called_once()
            worker.return_value.start.assert_called_once()
            mover.assert_not_called()
            self.assertTrue(file.exists())

    def test_second_cleanup_is_refused_while_first_is_running(self):
        app = SimpleNamespace(cleanup_running=True)
        with patch("ui.messagebox.showinfo") as notice, \
             patch("ui.messagebox.askyesno") as approval, \
             patch("ui.threading.Thread") as worker:
            GameGraveApp._grave_recycle_ids(app, ["fake"])
        notice.assert_called_once()
        approval.assert_not_called()
        worker.assert_not_called()


class OldFilesWorkerTests(unittest.TestCase):
    def make_file(self, root: Path):
        p = root / "old-download.txt"
        p.write_bytes(b"disposable old download")
        stamp = time.time() - 500 * 86400
        os.utime(p, (stamp, stamp))
        return p, OldFile(str(p), p.stat().st_size, p.stat().st_mtime)

    def test_refuses_protected_old_file_without_shell_call(self):
        from cleanup_actions import recycle_old_files
        with tempfile.TemporaryDirectory() as folder:
            file, record = self.make_file(Path(folder))
            with patch("cleanup_actions.log_event"), \
                 patch("cleanup_actions.recycle_file") as mover:
                result = recycle_old_files([record], [str(file)], "disposable-qa")
            self.assertEqual(result["completed"], 0)
            self.assertEqual(len(result["skipped"]), 1)
            mover.assert_not_called()
            self.assertTrue(file.exists())

    def test_failed_windows_undo_probe_never_counts_as_deleted(self):
        from cleanup_actions import recycle_old_files
        with tempfile.TemporaryDirectory() as folder:
            file, record = self.make_file(Path(folder))
            with patch("cleanup_actions.log_event"), \
                 patch("cleanup_actions.recycle_file", side_effect=RuntimeError("no recovery")) as mover, \
                 patch("cleanup_actions.register_recycle") as register:
                result = recycle_old_files([record], [], "disposable-qa")
            self.assertEqual(result["completed"], 0)
            self.assertTrue(result["skipped"])
            mover.assert_called_once()
            register.assert_not_called()
            self.assertTrue(file.is_file())

    def test_success_records_undo_and_progress(self):
        from cleanup_actions import recycle_old_files
        with tempfile.TemporaryDirectory() as folder:
            file, record = self.make_file(Path(folder))
            updates = []
            with patch("cleanup_actions.log_event"), \
                 patch("cleanup_actions.recycle_file", side_effect=lambda p: p.unlink()), \
                 patch("cleanup_actions.register_recycle", return_value="test-undo") as register:
                result = recycle_old_files(
                    [record], [], "disposable-qa",
                    progress=lambda a, b: updates.append((a, b)))
            self.assertEqual(result["completed"], 1)
            self.assertEqual(result["skipped"], [])
            self.assertEqual(updates, [(1, 1)])
            register.assert_called_once()
            self.assertFalse(file.exists())

    def test_old_files_button_queues_work_not_shell_call(self):
        with tempfile.TemporaryDirectory() as folder:
            file, record = self.make_file(Path(folder))
            tree = SimpleNamespace(winfo_exists=lambda: True, selection=lambda: ("row",))
            fake = SimpleNamespace(file_tree=tree, file_lookup={"row": record},
                                   settings={"never_touch": []}, cleanup_running=False,
                                   scanning=False, status_text=SimpleNamespace(set=Mock()),
                                   scan_button=Mock(), events=Mock())
            with patch("ui.messagebox.askyesno", return_value=True), \
                 patch("ui.threading.Thread") as worker, \
                 patch("ui.recycle_old_files") as mover:
                GameGraveApp._recycle_selected(fake)
            self.assertTrue(fake.cleanup_running)
            worker.assert_called_once()
            worker.return_value.start.assert_called_once()
            mover.assert_not_called()
            self.assertTrue(file.exists())


if __name__ == "__main__":
    unittest.main()
