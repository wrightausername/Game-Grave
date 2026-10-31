"""M5 UI update download requires a separate approval and never runs on Tk thread."""
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ui import GameGraveApp
from updates import VerifiedRelease


class VerifiedDownloadUiTests(unittest.TestCase):
    def setUp(self):
        self.release = VerifiedRelease(
            "1.0.1", "https://updates.example.com/stable/installer.exe",
            "a"*64, 1024, "stable")
        self.app = SimpleNamespace(
            _update_download_active=False, _update_check_active=False,
            _update_download_cancel=threading.Event(),
            status_text=SimpleNamespace(set=Mock()), events=Mock())

    def test_no_consent_starts_no_download_thread_or_dialog(self):
        with patch("ui.messagebox.askyesno", return_value=False) as approval, \
             patch("ui.filedialog.asksaveasfilename") as dialog, \
             patch("ui.threading.Thread") as worker:
            GameGraveApp._begin_verified_download(self.app, self.release)
        approval.assert_called_once()
        dialog.assert_not_called()
        worker.assert_not_called()
        self.assertFalse(self.app._update_download_active)

    def test_explicit_consent_only_queues_off_tk_thread(self):
        with patch("ui.messagebox.askyesno", return_value=True), \
             patch("ui.filedialog.asksaveasfilename", return_value="C:/safe/new.exe"), \
             patch("ui.threading.Thread") as worker, \
             patch("ui.download_verified_installer") as download:
            GameGraveApp._begin_verified_download(self.app, self.release)
        self.assertTrue(self.app._update_download_active)
        worker.assert_called_once()
        worker.return_value.start.assert_called_once()
        download.assert_not_called()

    def test_cancel_sets_event_without_touching_files(self):
        self.app._update_download_active = True
        with patch("ui.messagebox.showinfo") as notice:
            GameGraveApp._cancel_verified_download(self.app)
        self.assertTrue(self.app._update_download_cancel.is_set())
        notice.assert_not_called()


if __name__ == "__main__":
    unittest.main()
