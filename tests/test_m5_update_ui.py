"""M5 preview UI must never make unsolicited update network requests."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ui import GameGraveApp


class ManualUpdateUiTests(unittest.TestCase):
    def test_unconfigured_preview_refuses_before_starting_thread(self):
        dummy = SimpleNamespace()
        with patch("ui.update_ready", return_value=False), \
             patch("ui.messagebox.showinfo") as notice, \
             patch("ui.threading.Thread") as thread, \
             patch("ui.check_for_updates") as request:
            GameGraveApp._check_updates_clicked(dummy)
        notice.assert_called_once()
        self.assertIn("No internet request", notice.call_args.args[1])
        thread.assert_not_called()
        request.assert_not_called()

    def test_already_running_does_not_start_second_check(self):
        dummy = SimpleNamespace(_update_check_active=True)
        with patch("ui.update_ready", return_value=True), \
             patch("ui.threading.Thread") as thread, \
             patch("ui.check_for_updates") as request:
            GameGraveApp._check_updates_clicked(dummy)
        thread.assert_not_called()
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
