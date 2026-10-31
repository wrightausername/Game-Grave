"""M5 legacy app preferences survive safe upgrade without modifying old files."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import core


class LegacySettingsUpgradeTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.base = Path(folder.name)
        self.current_root = self.base / "Game Grave"
        self.legacy_root = self.base / "DustOff"
        self.legacy_root.mkdir()
        self.legacy_file = self.legacy_root / "settings.json"
        self.current_file = self.current_root / "settings.json"

    def load(self):
        with patch("core.config_dir", return_value=self.current_root):
            return core.load_settings()

    def test_reads_legacy_preferences_without_moving_or_deleting_original(self):
        original = {
            "ui_theme": "light", "ui_layout": "advanced",
            "never_touch": ["C:/Important/Saves"],
            "game_stale_days": 730, "graveyard_days": 365,
        }
        self.legacy_file.write_text(json.dumps(original), encoding="utf-8")
        preserved = self.legacy_file.read_bytes()
        loaded = self.load()
        self.assertEqual(loaded["ui_theme"], "light")
        self.assertEqual(loaded["game_stale_days"], 730)
        self.assertEqual(loaded["never_touch"], ["C:/Important/Saves"])
        self.assertEqual(self.legacy_file.read_bytes(), preserved)
        self.assertFalse(self.current_file.exists())
        with patch("core.config_dir", return_value=self.current_root):
            core.save_settings(loaded)
        self.assertTrue(self.current_file.is_file())
        self.assertEqual(self.legacy_file.read_bytes(), preserved)

    def test_current_preferences_win_without_unrequested_rollback(self):
        self.legacy_file.write_text(json.dumps({"ui_theme": "light"}))
        self.current_root.mkdir()
        self.current_file.write_text(json.dumps({"ui_theme": "dark"}))
        self.assertEqual(self.load()["ui_theme"], "dark")

    def test_corrupt_current_file_is_not_replaced_by_old_legacy_values(self):
        self.legacy_file.write_text(json.dumps({"ui_theme": "light"}))
        self.current_root.mkdir()
        self.current_file.write_text("{broken")
        before = self.current_file.read_bytes()
        self.assertEqual(self.load()["ui_theme"], core.default_settings()["ui_theme"])
        self.assertEqual(self.current_file.read_bytes(), before)

    def test_malformed_duplicate_or_oversized_legacy_files_fail_closed(self):
        for data in (
            b'{"ui_theme":"light","ui_theme":"dark"}',
            b"x" * (core.MAX_SETTINGS_BYTES + 1),
            b"not json",
        ):
            with self.subTest(size=len(data)):
                self.legacy_file.write_bytes(data)
                self.assertEqual(self.load(), core.default_settings())

    def test_bool_does_not_disguise_integer_configuration_and_unknown_keys_ignored(self):
        self.legacy_file.write_text(json.dumps({
            "game_stale_days": True, "auto_enabled": 1,
            "ui_theme": "light", "not_real_feature": "secret",
        }))
        result = self.load()
        self.assertEqual(result["game_stale_days"], core.default_settings()["game_stale_days"])
        self.assertFalse(result["auto_enabled"])
        self.assertEqual(result["ui_theme"], "light")
        self.assertNotIn("not_real_feature", result)

    def test_save_uses_its_own_unique_temp_file(self):
        self.current_root.mkdir()
        previous = self.current_root / "settings.tmp"
        previous.write_bytes(b"unrelated data")
        with patch("core.config_dir", return_value=self.current_root):
            core.save_settings(core.default_settings())
        self.assertEqual(previous.read_bytes(), b"unrelated data")
        self.assertTrue(self.current_file.exists())

    def test_failed_publish_keeps_existing_preferences(self):
        self.current_root.mkdir()
        original = b'{"ui_theme":"light"}'
        self.current_file.write_bytes(original)
        with patch("core.config_dir", return_value=self.current_root), \
             patch("core.os.replace", side_effect=OSError("failed")):
            with self.assertRaises(OSError):
                core.save_settings(core.default_settings())
        self.assertEqual(self.current_file.read_bytes(), original)
        self.assertFalse(list(self.current_root.glob(".gg-settings-*.tmp")))

    def test_oversized_preferences_refused(self):
        self.current_root.mkdir()
        self.current_file.write_bytes(b"original")
        data = core.default_settings()
        data["graveyard_search"] = "X" * (core.MAX_SETTINGS_BYTES + 1)
        with patch("core.config_dir", return_value=self.current_root):
            with self.assertRaises(ValueError):
                core.save_settings(data)
        self.assertEqual(self.current_file.read_bytes(), b"original")

    def test_linked_legacy_file_is_never_followed(self):
        alternate = self.base / "external-settings.json"
        alternate.write_text(json.dumps({"ui_theme": "light"}))
        try:
            self.legacy_file.symlink_to(alternate)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks unavailable on this runner")
        self.assertEqual(self.load(), core.default_settings())
        self.assertEqual(json.loads(alternate.read_text())["ui_theme"], "light")


if __name__ == "__main__":
    unittest.main()
