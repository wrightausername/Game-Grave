import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import core


class CoreTests(unittest.TestCase):
    def test_vdf_nested_and_escaped_paths(self):
        vdf = r'''"libraryfolders" { "0" { "path" "C:\\Program Files (x86)\\Steam" "apps" {"100" "123"} } // comment
                   "1" { "path" "D:\\SteamLibrary" } }'''
        parsed = core.parse_vdf(vdf)
        self.assertEqual(parsed["libraryfolders"]["0"]["path"], "C:\\Program Files (x86)\\Steam")
        self.assertEqual(parsed["libraryfolders"]["0"]["apps"]["100"], "123")

    def test_game_history_and_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Steam"
            extra = Path(tmp) / "SteamLibrary"
            (root / "steamapps").mkdir(parents=True)
            (extra / "steamapps").mkdir(parents=True)
            (root / "steamapps/libraryfolders.vdf").write_text(
                '"libraryfolders" { "0" { "path" "' + str(root).replace('\\', '\\\\') +
                '" } "1" { "path" "' + str(extra).replace('\\', '\\\\') + '" } }')
            (extra / "steamapps/appmanifest_123.acf").write_text('''"AppState" {
                "appid" "123" "name" "Old Game" "installdir" "Old Game"
                "SizeOnDisk" "1073741824" "StateFlags" "4" }''')
            config = root / "userdata" / "456" / "config"
            config.mkdir(parents=True)
            past = int(time.time() - 200 * 86400)
            (config / "localconfig.vdf").write_text('''"UserLocalConfigStore" {
                "Software" { "Valve" { "Steam" { "apps" { "123" { "LastPlayed" "''' + str(past) + '''" } } } } } }''')
            with patch.object(core, "_steam_roots", return_value=[root]):
                games = core.find_games()
            self.assertEqual(len(games), 1)
            self.assertEqual(games[0].size, 1073741824)
            self.assertEqual(games[0].last_played, past)
            self.assertEqual(games[0].source, "Steam account history")

    def test_30_and_60_day_filters_and_unknown_history(self):
        self.assertEqual(core.GAME_AGE_OPTIONS, (30, 60, 90, 180, 365, 730))
        now = 10_000_000
        def game(days_ago):
            return core.SteamGame("1", "Example", "", "", 100,
                                  None if days_ago is None else now - days_ago * 86400, "")
        self.assertTrue(core.is_game_neglected(game(45), 30, now))
        self.assertFalse(core.is_game_neglected(game(45), 60, now))
        self.assertTrue(core.is_game_neglected(game(61), 60, now))
        self.assertTrue(core.is_game_neglected(game(60), 60, now))
        self.assertFalse(core.is_game_neglected(game(None), 30, now))
        self.assertFalse(core.is_game_neglected(game(4), 30, now))

    def test_mod_scanner_finds_leftovers_and_active_mod_markers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "Steam"
            apps = root / "steamapps"
            common = apps / "common"
            (common / "Active Skyrim" / "Data" / "SKSE").mkdir(parents=True)
            (common / "Active Skyrim" / "Data" / "SKSE" / "custom.pex").write_bytes(b"123")
            (common / "Active Skyrim" / "Data" / "regular.dat").write_bytes(b"a" * 250)
            (apps / "appmanifest_100.acf").write_text('"AppState" { "appid" "100" "name" "Active Skyrim" "installdir" "Active Skyrim" "StateFlags" "4" }')
            (common / "Uninstalled Game" / "BepInEx" / "plugins").mkdir(parents=True)
            (common / "Uninstalled Game" / "BepInEx" / "plugins" / "mod.dll").write_bytes(b"1" * 23)
            (common / "Unknown Copy").mkdir()
            (common / "Unknown Copy" / "user-file.txt").write_bytes(b"1234")
            (common / "active-empty").mkdir()
            # Scan only the synthetic Steam root; no actual game files are touched.
            with patch.object(core, "_steam_roots", return_value=[root]):
                found = core.find_mod_folders()
            byname = {f.name: f for f in found}
            self.assertEqual(len(found), 4)
            self.assertEqual(byname["Active Skyrim"].status, "Installed: possible mods")
            self.assertEqual(byname["Active Skyrim"].apparent_bytes, 3)  # Counts markers, not base game.
            self.assertIn("data/skse", byname["Active Skyrim"].indicators)
            self.assertEqual(byname["Uninstalled Game"].status, "Unmatched Steam folder")
            self.assertEqual(byname["Uninstalled Game"].apparent_bytes, 23)
            self.assertEqual(byname["Unknown Copy"].indicators, ())
            # An unmatched folder is never called a confirmed uninstall or safe deletion.
            self.assertEqual(byname["Unknown Copy"].status, "Unmatched Steam folder")
            self.assertTrue((common / "Uninstalled Game" / "BepInEx" / "plugins" / "mod.dll").exists())

    def test_mod_scanner_does_not_follow_outside_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "Steam"
            common = root / "steamapps" / "common"
            (common / "Game" / "mods").mkdir(parents=True)
            outside = Path(temp) / "private"
            outside.mkdir()
            (outside / "large.dat").write_bytes(b"x" * 1024)
            link = common / "Game" / "mods" / "outside"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("OS cannot create symlinks")
            (common / "Game" / "mods" / "tiny.txt").write_bytes(b"a")
            with patch.object(core, "_steam_roots", return_value=[root]):
                found = core.find_mod_folders()
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0].apparent_bytes, 1)

    def test_mod_file_scan_is_bounded(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            for i in range(5):
                (folder / f"{i}.bin").write_bytes(b"xx")
            size, count, truncated = core._measured_files([folder], max_files=2)
            self.assertEqual((size, count, truncated), (4, 2, True))

    def test_unknown_does_not_become_old(self):
        self.assertIsNone(core._valid_timestamp(86400))
        self.assertIsNone(core._valid_timestamp(0))
        self.assertEqual(core.age_text(None), "Unknown")

    def test_file_scan_and_change_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Downloads"
            folder.mkdir()
            candidate = folder / "old.zip"
            candidate.write_bytes(b"old data")
            age = time.time() - 400 * 86400
            os.utime(candidate, (age, age))
            latest = folder / "today.txt"
            latest.write_text("new")
            found = core.scan_old_files(folder, 180)
            self.assertEqual(len(found), 1)
            self.assertEqual(Path(found[0].path).name, "old.zip")
            self.assertTrue(core.is_unchanged(found[0]))
            candidate.write_text("changed")
            self.assertFalse(core.is_unchanged(found[0]))

    def test_restrict_system_scan(self):
        self.assertFalse(core.safe_scan_root(Path.home()))
        self.assertFalse(core.safe_scan_root(Path(Path.home().anchor)))

    def test_auto_cleanup_only_recycles_approved_file_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Downloads"
            folder.mkdir()
            old = time.time() - 500 * 86400
            for filename in ("old.log", "important.pdf", "installer.exe", "recent.log"):
                p = folder / filename
                p.write_text("data")
                os.utime(p, (old, old))
            newer = folder / "recent.log"
            os.utime(newer, None)
            settings = core.default_settings()
            settings["auto_enabled"] = True
            sent = []
            with patch.object(core, "load_settings", return_value=settings), \
                 patch.object(core, "downloads_dir", return_value=folder), \
                 patch.object(core, "recycle_file", side_effect=lambda path: sent.append(path)), \
                 patch.object(core, "log_event"):
                count, size, msg = core.run_auto_cleanup()
            self.assertEqual(count, 1)
            self.assertEqual([p.name for p in sent], ["old.log"])
            self.assertTrue((folder / "important.pdf").exists())

    def test_friendly_logs_never_claim_game_uninstalled(self):
        item = core.friendly_activity({"kind": "Steam uninstall opened", "details": "Skyrim",
                                      "date": "2026-10-20T12:00:00-04:00"})
        self.assertEqual(item["status"], "Needs review")
        self.assertIn("must approve", item["explanation"])
        self.assertNotIn("uninstalled", item["title"].lower())

    def test_logs_distinguish_completed_and_skipped(self):
        recycled = core.friendly_activity({"kind": "Manual recycled", "details": "/Downloads/old.iso", "date": ""})
        skipped = core.friendly_activity({"kind": "Cleanup skipped", "details": "changed since scan", "date": ""})
        self.assertEqual(recycled["status"], "Done")
        self.assertEqual(recycled["summary"], "old.iso")
        self.assertEqual(skipped["status"], "Skipped")

    def test_log_csv_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "history.csv"
            count = core.export_activity_csv(target, [{"kind": "Scan completed", "details": "2 games", "date": ""}])
            self.assertEqual(count, 1)
            content = target.read_text(encoding="utf-8-sig")
            self.assertIn("What happened", content)
            self.assertIn("Storage scan completed", content)

    def test_csv_export_neutralizes_formulas(self):
        self.assertEqual(core._csv_safe("=1+1"), "'=1+1")
        self.assertEqual(core._csv_safe("safe filename"), "safe filename")

    def test_log_reader_skips_invalid_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(core, "config_dir", return_value=Path(tmp)):
                (Path(tmp) / "activity.log").write_text('bad json\n{"date":"2026", "kind":"Scan completed", "details":"ok"}\n')
                result = core.get_activity()
                self.assertEqual(len(result), 1)
                self.assertEqual(result[0]["kind"], "Scan completed")

    def test_autoclean_disabled_does_nothing(self):
        with patch.object(core, "load_settings", return_value=core.default_settings()):
            count, size, message = core.run_auto_cleanup()
        self.assertEqual((count, size), (0, 0))
        self.assertIn("disabled", message)


if __name__ == "__main__":
    unittest.main()
