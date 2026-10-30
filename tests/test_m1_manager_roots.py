"""M1 manager-root protection and Windows restore collision regression tests."""
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import core
import recovery
from core import OldFile, is_protected_path
from graveyard import build_graveyard


class ManagedRootSafetyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.downloads = self.root / "Downloads"
        self.downloads.mkdir()

    def test_managed_storage_is_protected_even_below_downloads(self):
        for folder in ("Mods", "Vortex", "MO2", "Mod Organizer",
                       "CurseForge", "Wabbajack", "Thunderstore",
                       "r2modman", "Modrinth", "Prism Launcher"):
            with self.subTest(folder=folder):
                item = self.downloads / folder / "skyrim-mod.zip"
                self.assertTrue(is_protected_path(item),
                                f"{folder} is protected even if under Downloads")
        self.assertFalse(is_protected_path(self.downloads / "ordinary-old.log"))

    def test_graveyard_prohibits_recycling_managed_archives(self):
        location = self.downloads / "Vortex"
        location.mkdir()
        archive = location / "skyrim-mod.zip"
        archive.write_bytes(b"do not touch manager archives")
        entries = build_graveyard([], [], [OldFile(str(archive), archive.stat().st_size, 1)],
                                  min_days=30, now=60 * 86400)
        self.assertEqual(len(entries), 1)
        self.assertFalse(entries[0].can_recycle)
        self.assertTrue(archive.exists())

    def test_auto_cleanup_refuses_manager_path_even_if_scanner_suggested(self):
        manager = self.downloads / "Mods"
        manager.mkdir()
        protected = manager / "old.log"
        allowed = self.downloads / "other.log"
        for path in (protected, allowed):
            path.write_text("test")
            old = time.time() - 400 * 86400
            os.utime(path, (old, old))
        found = [OldFile(str(path), path.stat().st_size, path.stat().st_mtime)
                 for path in (protected, allowed)]
        cfg = core.default_settings()
        cfg["auto_enabled"] = True
        sent = []
        with patch.object(core, "load_settings", return_value=cfg), \
                patch.object(core, "downloads_dir", return_value=self.downloads), \
                patch.object(core, "scan_old_files", return_value=found), \
                patch.object(core, "recycle_file", side_effect=lambda path: sent.append(path)), \
                patch.object(core, "log_event"):
            done, _bytes, _msg = core.run_auto_cleanup()
        self.assertEqual(done, 1)
        self.assertEqual(sent, [allowed])
        self.assertTrue(protected.exists())

    def test_windows_restore_checks_collision_inside_shell_script(self):
        script = recovery._bin_script(r"C:\Users\Test\Saves\save1.ess", restore=True)
        self.assertIn("'ORIGINAL_EXISTS'", script)
        self.assertLess(script.index("if (Test-Path -LiteralPath $original)"),
                        script.index("$matches[0].InvokeVerb('undelete')"))
        self.assertIn("OrdinalIgnoreCase", script)


if __name__ == "__main__":
    unittest.main()
