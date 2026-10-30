"""Opt-in local Living Kit watches only operate on disposable fixture folders."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from resurrection_v2 import create_complete_kit
from kit_watch import (register_kit_watch, list_kit_watches,
                       check_kit_watches, stop_kit_watch)


class LivingWatchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = self.root / "Local Settings"
        hook = patch("kit_watch.config_dir", return_value=self.config)
        hook.start()
        self.addCleanup(hook.stop)
        self.saves = self.root / "Game Saves"
        self.saves.mkdir()
        (self.saves / "first.sav").write_bytes(b"original")
        kit = create_complete_kit("Example", {"Saves": self.saves},
                                  self.root / "Kit_1.zip")
        self.manifest = Path(kit["manifest"])

    def test_opt_in_required_and_user_paths_remain_only_local(self):
        with self.assertRaises(PermissionError):
            register_kit_watch(self.manifest, {"Saves": self.saves})
        self.assertFalse(list_kit_watches())
        saved = register_kit_watch(self.manifest, {"Saves": self.saves}, approved=True)
        self.assertTrue(saved["local_only"])
        self.assertEqual(saved["folders"], 1)
        data = json.loads((self.config / "living_kit_watches.json").read_text())
        self.assertEqual(data["schema"], 1)
        self.assertIn(str(self.saves), data["watches"][0]["sources"]["Saves"])
        self.assertEqual(len(list_kit_watches()), 1)
        self.assertFalse((self.saves / "first.sav").is_symlink())

    def test_tracked_file_changes_report_possible_only(self):
        register_kit_watch(self.manifest, {"Saves": self.saves}, approved=True)
        before = check_kit_watches()
        self.assertEqual(before[0]["status"], "unchanged metadata")
        self.assertTrue(before[0]["no_automatic_backup"])
        self.assertTrue(self.manifest.exists())
        (self.saves / "first.sav").write_bytes(b"substantially different bytes")
        after = check_kit_watches()
        self.assertEqual(after[0]["status"], "possible changes")
        self.assertIn("full content review", after[0]["reason"])
        self.assertEqual(list(self.root.glob("Kit_*.zip")), [self.root / "Kit_1.zip"])

    def test_missing_source_reported_unknown_not_unchanged(self):
        register_kit_watch(self.manifest, {"Saves": self.saves}, approved=True)
        (self.saves / "first.sav").unlink()
        state = check_kit_watches()
        self.assertEqual(state[0]["status"], "unknown")
        self.assertIn("do not assume unchanged", state[0]["reason"])

    def test_watch_remove_requires_approval_preserves_source_files(self):
        watch = register_kit_watch(self.manifest, {"Saves": self.saves}, approved=True)
        with self.assertRaises(PermissionError):
            stop_kit_watch(watch["id"])
        self.assertTrue(stop_kit_watch(watch["id"], approved=True))
        self.assertEqual(check_kit_watches(), [])
        self.assertFalse(stop_kit_watch(watch["id"], approved=True))
        self.assertEqual((self.saves / "first.sav").read_bytes(), b"original")
        self.assertTrue(self.manifest.exists())

    def test_watch_list_limits_and_bad_json_fail_safe(self):
        f = self.config / "living_kit_watches.json"
        self.config.mkdir(parents=True)
        f.write_text("corrupt-json")
        self.assertEqual(list_kit_watches(), [])
        f.write_text("x" * 100000)
        self.assertEqual(list_kit_watches(), [])


if __name__ == "__main__":
    unittest.main()
