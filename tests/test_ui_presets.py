"""Data-only portable UI profile validation and privacy tests."""
import json
import tempfile
import unittest
from pathlib import Path

from core import default_settings
from ui_presets import (MAX_FILE_BYTES, capture_presentation, encode_preset, decode_preset,
                        normalize_color, sanitize_local_presets, read_preset_file, write_preset_file)


class UIPresetTests(unittest.TestCase):
    def setUp(self):
        self.settings = default_settings()
        self.settings.update({
            "ui_theme": "light", "ui_accent": "custom", "ui_custom_accent": "#ff00cc",
            "ui_layout": "advanced", "ui_scale": "large", "graveyard_sort": "Age",
            "graveyard_days": 1095, "never_touch": ["C:/private/saves"],
            "graveyard_search": "C:/Users/secret-person/PrivateMods",
            "scan_folder": "C:/Users/secret-person/Downloads", "auto_enabled": True,
        })

    def test_arbitrary_hex_color_and_strict_validation(self):
        self.assertEqual(normalize_color("#Ff00cC"), "#FF00CC")
        for value in ["red", "#fff", "#GGFFAA", "#123456;system('cmd')", None, "#12345678"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_color(value)

    def test_export_contains_no_private_content_or_cleanup_controls(self):
        settings = capture_presentation(self.settings)
        text = encode_preset("Arcade Sunset", settings)
        self.assertNotIn("private", text.lower())
        self.assertNotIn("never_touch", text)
        self.assertNotIn("auto_enabled", text)
        self.assertNotIn("scan_folder", text)
        self.assertNotIn("graveyard_search", text)
        name, decoded = decode_preset(text)
        self.assertEqual(name, "Arcade Sunset")
        self.assertEqual(decoded["ui_custom_accent"], "#FF00CC")
        self.assertEqual(decoded["graveyard_days"], 1095)

    def test_file_round_trip(self):
        with tempfile.TemporaryDirectory() as temp:
            filename = Path(temp) / "my-gg-theme.json"
            write_preset_file(filename, "Shiny purple", capture_presentation(self.settings))
            name, settings = read_preset_file(filename)
            self.assertEqual(name, "Shiny purple")
            self.assertEqual(settings["ui_layout"], "advanced")

    def test_rejects_extra_fields_in_outer_or_settings(self):
        doc = json.loads(encode_preset("Clean", capture_presentation(self.settings)))
        doc["command"] = "rm -rf"
        with self.assertRaises(ValueError):
            decode_preset(json.dumps(doc))
        doc.pop("command")
        doc["settings"]["never_touch"] = []
        with self.assertRaises(ValueError):
            decode_preset(json.dumps(doc))
        doc["settings"].pop("never_touch")
        doc["settings"]["ui_theme"] = "__import__('os').system('calc')"
        with self.assertRaises(ValueError):
            decode_preset(json.dumps(doc))

    def test_rejects_wrong_version_oversize_invalid_age(self):
        doc = json.loads(encode_preset("Clean", capture_presentation(self.settings)))
        doc["version"] = 999
        with self.assertRaises(ValueError):
            decode_preset(json.dumps(doc))
        doc["version"] = 1
        doc["settings"]["graveyard_days"] = True
        with self.assertRaises(ValueError):
            decode_preset(json.dumps(doc))
        with self.assertRaises(ValueError):
            decode_preset(" " * (MAX_FILE_BYTES + 1))

    def test_sanitize_saved_presets_drops_unknown_data(self):
        present = capture_presentation(self.settings)
        cleaned = sanitize_local_presets({"Usable": present, "Suspicious": {**present, "auto_enabled": True},
                                         "Bad JSON": "not an object"})
        self.assertEqual(list(cleaned), ["Usable"])

    def test_presets_apply_only_user_presentation_fields(self):
        preset = capture_presentation(self.settings)
        target = default_settings()
        target["never_touch"] = ["C:/ActiveMods"]
        target["auto_enabled"] = False
        target.update(preset)
        self.assertEqual(target["never_touch"], ["C:/ActiveMods"])
        self.assertFalse(target["auto_enabled"])


if __name__ == "__main__":
    unittest.main()
