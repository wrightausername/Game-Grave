"""M2 scanner metadata limits and redirected-root regression tests.

All data is synthetic and temporary. No game/mod files are deleted or changed.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import core
import mod_sources


class ReadOnlyScannerBoundaries(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.steam = self.root / "Steam"
        (self.steam / "steamapps").mkdir(parents=True)

    def test_small_ordinary_steam_vdf_still_parses(self):
        manifest = self.steam / "steamapps" / "appmanifest_42.acf"
        manifest.write_text('"AppState" { "appid" "42" }', encoding="utf-8")
        self.assertEqual(core.read_vdf(manifest)["appstate"]["appid"], "42")

    def test_oversized_steam_vdf_is_ignored_without_reading_contents(self):
        manifest = self.steam / "steamapps" / "libraryfolders.vdf"
        manifest.write_bytes(b"x" * 120)
        with patch.object(core, "MAX_STEAM_VDF_BYTES", 100), \
                patch.object(Path, "read_text", side_effect=AssertionError("read forbidden")):
            self.assertEqual(core.read_vdf(manifest), {})
        self.assertEqual(manifest.stat().st_size, 120)

    def test_redirected_manifest_is_not_trusted(self):
        ordinary = self.root / "record.acf"
        ordinary.write_text('"AppState" { "appid" "42" }', encoding="utf-8")
        pointer = self.steam / "steamapps" / "appmanifest_42.acf"
        try:
            pointer.symlink_to(ordinary)
        except (OSError, NotImplementedError):
            self.skipTest("Symbolic links disabled")
        self.assertEqual(core.read_vdf(pointer), {})
        self.assertEqual(ordinary.read_text(), '"AppState" { "appid" "42" }')

    def test_relative_steam_extra_root_is_not_considered_installed(self):
        with patch.dict(core.os.environ, {"PROGRAMFILES": "", "PROGRAMFILES(X86)": ""}):
            self.assertEqual(core._steam_roots(["relative-steam-path"]), [])

    def test_valid_steam_library_and_custom_secondary_drive_are_detected(self):
        secondary = self.root / "Secondary Games"
        (secondary / "steamapps").mkdir(parents=True)
        vdf = self.steam / "steamapps" / "libraryfolders.vdf"
        vdf.write_text('"libraryfolders" { "1" { "path" "' + str(secondary).replace("\\", "\\\\") + '" } }')
        result = core.steam_libraries([self.steam])
        self.assertIn(self.steam.resolve(), result)
        self.assertIn(secondary.resolve(), result)

    def test_steam_and_manager_roots_through_symlink_ancestors_are_rejected(self):
        redirect = self.root / "Redirect"
        try:
            redirect.symlink_to(self.steam, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symbolic links disabled")
        self.assertFalse(mod_sources._safe_folder(redirect / "steamapps"))
        with patch.dict(core.os.environ, {"PROGRAMFILES": "", "PROGRAMFILES(X86)": ""}):
            self.assertEqual(core._steam_roots([str(redirect)]), [])
        self.assertTrue((self.steam / "steamapps").is_dir())


if __name__ == "__main__":
    unittest.main()
