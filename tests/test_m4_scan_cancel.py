"""M4 cancellation must not mutate accepted inventory or report success.

Pure synthetic UI event tests. No Tk window and no real disk scan is started.
"""
import queue
import threading
import unittest
from unittest.mock import patch

from ui import GameGraveApp


class DummyVar:
    def __init__(self, value=""):
        self.value = value
    def set(self, value):
        self.value = value
    def get(self):
        return self.value


class FakeCancelApp:
    _check_scan_cancel = GameGraveApp._check_scan_cancel
    _scan_canceled_status = GameGraveApp._scan_canceled_status
    _poll = GameGraveApp._poll

    def __init__(self):
        self._cancel_scan = threading.Event()
        self.events = queue.Queue()
        self.scanning = True
        self.scan_progress_text = DummyVar("Previously scanning")
        self.status_text = DummyVar("Previously scanning")
        self.scan_button = self.cancel_button = self
        self.configure_calls = []
        self.games = ["existing game"]
        self.other_games = ["existing launcher"]
        self.mod_folders = ["existing mod"]
        self.old_files = ["existing old file"]
        self.save_findings = ["existing save"]
        self.last_scan = "previous scan"
        self.after_calls = []

    def configure(self, **kw):
        self.configure_calls.append(kw)
    def after(self, milliseconds, fn):
        self.after_calls.append(milliseconds)


class ScanCancelTests(unittest.TestCase):
    def test_cancel_checkpoint_stops_between_stages(self):
        fake = FakeCancelApp()
        fake._check_scan_cancel()
        fake._cancel_scan.set()
        with self.assertRaisesRegex(InterruptedError, "Previous inventory"):
            fake._check_scan_cancel()

    def test_cancelled_late_complete_never_overwrites_existing_inventory(self):
        fake = FakeCancelApp()
        fake._cancel_scan.set()
        fake.events.put(("scan_complete", (
            ["new game"], [], ["new mod"], ["new stale file"], [], "")))
        with patch("ui.log_event") as event_log:
            GameGraveApp._poll(fake)
        self.assertEqual(fake.games, ["existing game"])
        self.assertEqual(fake.mod_folders, ["existing mod"])
        self.assertEqual(fake.save_findings, ["existing save"])
        self.assertEqual(fake.last_scan, "previous scan")
        self.assertFalse(fake.scanning)
        self.assertIn("canceled", fake.status_text.get().lower())
        self.assertNotIn("complete", fake.scan_progress_text.get().lower())
        event_log.assert_called_once()
        self.assertEqual(event_log.call_args.args[0], "Scan canceled")
        self.assertEqual(fake.after_calls, [180])

    def test_cancelled_error_does_not_show_failure_popup(self):
        fake = FakeCancelApp()
        fake._cancel_scan.set()
        fake.events.put(("scan_error", "InterruptedError"))
        with patch("ui.log_event") as log, \
                patch("ui.messagebox.showwarning") as popup:
            GameGraveApp._poll(fake)
        self.assertFalse(fake.scanning)
        self.assertIn("Previous results preserved", fake.scan_progress_text.get())
        popup.assert_not_called()
        self.assertEqual(log.call_args.args[0], "Scan canceled")

    def test_real_scan_error_is_not_mislabeled_as_user_cancel(self):
        fake = FakeCancelApp()
        fake.events.put(("scan_error", "Example network drive unavailable"))
        with patch("ui.log_event") as log, \
                patch("ui.messagebox.showwarning") as popup:
            GameGraveApp._poll(fake)
        self.assertFalse(fake.scanning)
        self.assertIn("incomplete", fake.scan_progress_text.get())
        self.assertEqual(log.call_args.args[0], "Scan failed")
        popup.assert_called_once()


if __name__ == "__main__":
    unittest.main()
