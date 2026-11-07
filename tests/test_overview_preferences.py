"""Real-file Overview preference restore without shared-loader changes."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import core
from gg_desktop.overview_preferences import restore_overview_favorites


class OverviewPreferencesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.patch = patch("core.config_dir", return_value=self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_restores_real_save_when_shared_loader_filters_extra_key(self):
        settings = dict(core.default_settings(), desktop_favorites=["steam:one", "epic:two"])
        core.save_settings(settings)
        accepted = core.load_settings()
        self.assertNotIn("desktop_favorites", accepted)
        before = deepcopy(accepted)
        payload = (self.root/"settings.json").read_bytes()
        self.assertEqual(restore_overview_favorites(accepted), {"steam:one", "epic:two"})
        self.assertEqual(accepted, before)
        self.assertEqual((self.root/"settings.json").read_bytes(), payload)

    def test_current_session_including_explicit_empty_takes_precedence(self):
        core.save_settings(dict(core.default_settings(), desktop_favorites=["old"]))
        self.assertEqual(restore_overview_favorites({"desktop_favorites": []}), set())
        self.assertEqual(restore_overview_favorites({"desktop_favorites": ["new"]}), {"new"})

    def test_invalid_or_duplicate_json_does_not_guess_favorites(self):
        for payload in ('{"desktop_favorites":123}', '{"desktop_favorites":[null]}',
                        '{"desktop_favorites":["x"],"desktop_favorites":["y"]}', '{bad'):
            (self.root/"settings.json").write_text(payload)
            self.assertEqual(restore_overview_favorites({}), set())

    def test_oversized_file_is_not_read(self):
        (self.root/"settings.json").write_bytes(b" "*(core.MAX_SETTINGS_BYTES+1))
        with patch.object(Path, "open", side_effect=AssertionError("Oversized preference file opened")):
            self.assertEqual(restore_overview_favorites({}), set())

    def test_redirected_preferences_are_not_opened(self):
        core.save_settings(dict(core.default_settings(), desktop_favorites=["private"]))
        with patch("core._has_reparse_component", return_value=True), \
             patch.object(Path, "open", side_effect=AssertionError("Redirected preference file opened")):
            self.assertEqual(restore_overview_favorites({}), set())


if __name__ == "__main__":
    unittest.main()
