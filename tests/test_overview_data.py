"""Overview's data fixes never change cleanup scope or infer reclaimed space."""
from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from core import SteamGame
from gg_desktop.models import merge_games
from gg_desktop.overview_data import disk_reading, latest_capture, launcher_games, launcher_summaries
from launchers import LauncherGame
from screenshots import find_old_screenshots


class OverviewDataTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name) / "SyntheticHome"
        self.home.mkdir()

    def image_metadata(self, name, age):
        target = self.home / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"Metadata fixture: never decode during discovery")
        stamp = time.time() - age
        os.utime(target, (stamp, stamp))
        return target

    def test_latest_includes_todays_capture_without_changing_cleanup_inventory(self):
        old = self.image_metadata("Videos/Captures/old.png", 900 * 86400)
        recent = self.image_metadata("Videos/Captures/today.png", 30)
        before = find_old_screenshots(365, home=self.home, steam_roots=[])
        result = latest_capture({}, home=self.home, steam_roots=[])
        self.assertEqual(Path(result.latest.path), recent)
        self.assertEqual([Path(r.path) for r in before], [old])
        self.assertEqual(find_old_screenshots(365, home=self.home, steam_roots=[]), before)
        self.assertFalse(result.limited)

    def test_does_not_discover_personal_photos_desktop_captures_or_thumbnails(self):
        self.image_metadata("Pictures/Family/photo.png", 1)
        self.image_metadata("Pictures/Screenshots/desktop.png", 1)
        self.image_metadata("Videos/Captures/thumbnails/thumb.png", 1)
        result = latest_capture({}, home=self.home, steam_roots=[])
        self.assertIsNone(result.latest)

    def test_steam_captures_are_metadata_only_and_do_not_crawl_games(self):
        steam = self.home / "Steam"
        image = self.image_metadata("Steam/userdata/100/760/remote/1091500/screenshots/f12.jpg", 1)
        self.image_metadata("Steam/steamapps/common/Game/Data/texture.jpg", 0)
        self.image_metadata("Steam/userdata/100/760/remote/1091500/screenshots/thumbnails/thumb.jpg", 0)
        with patch("builtins.open", side_effect=AssertionError("Discovery opened file content")):
            result = latest_capture({}, home=self.home, steam_roots=[steam])
        self.assertEqual(Path(result.latest.path), image)

    def test_explicit_folder_is_read_only_and_preferences_do_not_change(self):
        image = self.image_metadata("SelectedCaptures/custom.png", 1)
        settings = {"screenshot_roots": [str(image.parent)], "never_touch": ["KEEP"]}
        before = deepcopy(settings)
        result = latest_capture(settings, home=self.home, steam_roots=[])
        self.assertEqual(Path(result.latest.path), image)
        self.assertEqual(settings, before)
        self.assertTrue(image.exists())

    def test_linked_files_and_directories_are_not_followed(self):
        captures = self.home / "Videos" / "Captures"
        captures.mkdir(parents=True)
        photo = self.image_metadata("Private/photo.png", 1)
        try:
            (captures / "linked.png").symlink_to(photo)
            (captures / "linked-dir").symlink_to(photo.parent, target_is_directory=True)
        except OSError:
            self.skipTest("Symlinks unavailable")
        self.assertIsNone(latest_capture({}, home=self.home, steam_roots=[]).latest)
        self.assertTrue(photo.exists())

    def test_cancel_and_global_limits_are_explicit(self):
        for i in range(5):
            self.image_metadata(f"Videos/Captures/{i}.png", 10 + i)
        with self.assertRaises(InterruptedError):
            latest_capture({}, home=self.home, steam_roots=[], canceled=lambda: True)
        result = latest_capture({}, home=self.home, steam_roots=[], max_entries=2)
        self.assertTrue(result.limited)

    def test_shared_install_group_and_unknown_sizes_are_counted_correctly(self):
        path = str(self.home / "SharedInstall")
        steam = SteamGame("10", "Shared", str(self.home), path, 100, None, "Unknown")
        other = LauncherGame("Shared", "Epic Games", path, "epic10", 200, "Verified manifest")
        zero = SteamGame("11", "Empty game", str(self.home), str(self.home / "Empty"), 0, None, "Unknown")
        rows = merge_games([steam, zero], [other])
        groups = {s.name: s for s in launcher_summaries(rows)}
        self.assertEqual(groups["Multiple launchers"].count, 1)
        self.assertEqual(groups["Multiple launchers"].unknown_sizes, 1)
        self.assertEqual(groups["Steam"].known_bytes, 0)
        self.assertEqual(groups["Steam"].unknown_sizes, 0)
        self.assertEqual([g.name for g in launcher_games(rows, "Multiple launchers")], ["Shared"])
        self.assertEqual([g.name for g in launcher_games(rows, "Steam")], ["Empty game"])

    def test_drive_reading_queries_system_volume_and_rejects_invalid_capacity(self):
        expected = self.home.anchor
        with patch("gg_desktop.overview_data.system_disk_path", return_value=Path(expected)), \
             patch("gg_desktop.overview_data.shutil.disk_usage", return_value=SimpleNamespace(total=100, free=40, used=60)) as read:
            path, usage = disk_reading()
        read.assert_called_once_with(Path(expected))
        self.assertEqual(usage.free, 40)
        with patch("gg_desktop.overview_data.shutil.disk_usage", return_value=SimpleNamespace(total=0, free=0)):
            with self.assertRaises(OSError):
                disk_reading()


if __name__ == "__main__":
    unittest.main()
