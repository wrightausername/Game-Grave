"""Synthetic MO2/Vortex profile fixtures. All inspection is read-only."""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import mod_sources
from core import SteamGame
from game_intelligence import build_game_dna
from manager_profiles import (inspect_manager_profiles, summarize_manager_profile,
                              _identity, _read_modlist)


class GameDNAManagerProfiles(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def make_mo2(self, matched=True, profile_text="+Core Mod\n-Optional Mod\n"):
        install = self.root / "Steam" / "steamapps" / "common" / "Skyrim"
        install.mkdir(parents=True)
        ini_dir = self.root / "ModOrganizer" / "SkyrimSE"
        ini_dir.mkdir(parents=True)
        data = self.root / "Portable Mods"
        (data / "mods" / "Core Mod").mkdir(parents=True)
        (data / "profiles" / "Playthrough").mkdir(parents=True)
        (data / "profiles" / "Playthrough" / "modlist.txt").write_text(
            profile_text, encoding="utf-8")
        (ini_dir / "ModOrganizer.ini").write_text(
            "[General]\n"
            "gameName=Skyrim Special Edition\n"
            "selected_profile=@ByteArray(Playthrough)\n"
            "gamePath=" + (str(install) if matched else str(self.root / "Elsewhere")) + "\n"
            "[Settings]\n"
            "base_directory=" + str(data) + "\n"
            "mod_directory=%BASE_DIR%/mods\n"
            "profiles_directory=%BASE_DIR%/profiles\n",
            encoding="utf-8",
        )
        scanned = mod_sources._mo2(ini_dir.parent, None)
        game = SteamGame("489830", "Skyrim Special Edition", str(self.root),
                         str(install), 200, None, "Unknown")
        return game, scanned, ini_dir, data

    def test_mo2_active_disabled_and_missing_mods_preserved(self):
        game, scanned, _ini, data = self.make_mo2(
            profile_text="+Core Mod\n-Optional Mod\n*DLC\n+No Folder\n# ignore\n"
                         "+Core Mod\n+../escape\n+Divider_separator\n")
        self.assertTrue(any("MO2 INI:" in str(row.indicators) for row in scanned))
        with patch.dict(os.environ, {"APPDATA": str(self.root / "missing"),
                                     "PROGRAMDATA": str(self.root / "missing")}):
            report = inspect_manager_profiles(scanned, [game])
        self.assertEqual(report["count"], 1)
        profile = report["profiles"][0]
        self.assertEqual(profile["manager"], "Mod Organizer 2")
        self.assertEqual(profile["verified_game"], "Skyrim Special Edition")
        self.assertTrue(profile["active_at_snapshot"])
        self.assertTrue(profile["protected"])
        names = [x["name"] for x in profile["mods"]]
        self.assertEqual(names, ["Core Mod", "Optional Mod", "DLC", "No Folder"])
        self.assertEqual(profile["mods"][0]["storage"], "folder present")
        self.assertIn("not confirmed", profile["mods"][1]["storage"])
        self.assertEqual(summarize_manager_profile(profile)["enabled"], 2)
        self.assertEqual(summarize_manager_profile(profile)["disabled"], 1)
        dna = build_game_dna([game], mods=scanned,
                             manager_profiles=report["profiles"])
        self.assertEqual(len(dna["games"][0]["manager_profiles"]), 1)
        self.assertFalse(any(x.get("kind") == "Unverified manager profile"
                             for x in dna["unresolved"]))
        self.assertTrue((data / "profiles" / "Playthrough" / "modlist.txt").exists())

    def test_mo2_game_name_alone_never_establishes_ownership(self):
        game, scanned, _ini, _data = self.make_mo2(matched=False)
        with patch.dict(os.environ, {"APPDATA": str(self.root / "missing"),
                                     "PROGRAMDATA": str(self.root / "missing")}):
            report = inspect_manager_profiles(scanned, [game])
        self.assertEqual(report["profiles"][0]["verified_game"], "")
        dna = build_game_dna([game], mods=scanned,
                             manager_profiles=report["profiles"])
        self.assertEqual(dna["games"][0]["manager_profiles"], [])
        self.assertTrue(any(x.get("kind") == "Unverified manager profile"
                            for x in dna["unresolved"]))

    def test_mo2_truncation_and_dangerous_entries(self):
        file = self.root / "modlist.txt"
        file.write_text("+Good\n+../../secret\n+other\\folder\n+Good\n+Entry_separator\n")
        rows, issue = _read_modlist(file)
        self.assertEqual([r["name"] for r in rows], ["Good"])
        self.assertEqual(issue, "")
        with patch("manager_profiles.MAX_MO2_LIST_BYTES", 8):
            rows, issue = _read_modlist(file)
        self.assertFalse(rows)
        self.assertIn("cap", issue)

    def make_vortex(self, *, with_backup=True, stale=False):
        root = self.root / "Vortex"
        staged = root / "skyrimse" / "mods"
        staged.mkdir(parents=True)
        (staged / "KeepMe").mkdir()
        game_dir = self.root / "Games" / "Skyrim"
        game_dir.mkdir(parents=True)
        game = SteamGame("489830", "Skyrim", str(self.root), str(game_dir),
                         500, None, "Unknown")
        if with_backup:
            backup_dir = root / "temp" / "state_backups_full"
            backup_dir.mkdir(parents=True)
            data = {
                "persistent": {
                    "profiles": {"p1": {"gameId": "skyrimse", "name": "Modded",
                                        "modState": {"m1": {"enabled": True},
                                                     "m2": {"enabled": False}}}},
                    "mods": {"skyrimse": {
                        "m1": {"attributes": {"modName": "KeepMe", "version": "1"}},
                        "m2": {"attributes": {"modName": "Disabled"}},
                        "m3": {"attributes": {"modName": "Uncertain"}}}}},
                "settings": {
                    "gameMode": {"discovered": {"skyrimse": {"path": str(game_dir)}}},
                    "profiles": {"activeProfileId": "p1"}},
            }
            backup = backup_dir / "manual.json"
            backup.write_text(json.dumps(data), encoding="utf-8")
            if stale:
                date = time.time() - 14 * 86400
                os.utime(backup, (date, date))
        rows = mod_sources._vortex(root, None)
        return root, game, rows

    def test_vortex_json_snapshot_profile_and_staleness(self):
        root, game, rows = self.make_vortex(stale=True)
        with patch.dict(os.environ, {"APPDATA": str(self.root),
                                     "PROGRAMDATA": str(self.root / "missing")}):
            report = inspect_manager_profiles(rows, [game])
        self.assertEqual(report["count"], 1)
        p = report["profiles"][0]
        self.assertEqual(p["verified_game"], "Skyrim")
        self.assertEqual(p["game_hint"], "skyrimse")
        self.assertTrue(p["active_at_snapshot"])
        self.assertTrue(p["stale"])
        self.assertEqual([m["marker"] for m in p["mods"]], ["+", "-", "?"])
        self.assertTrue(summarize_manager_profile(p)["incomplete"])
        self.assertTrue(any("older than seven days" in x for x in report["warnings"]))
        self.assertTrue((root / "temp" / "state_backups_full" / "manual.json").exists())

    def test_live_vortex_database_is_not_opened_or_modified(self):
        root, game, rows = self.make_vortex(with_backup=False)
        database = root / "state.v2"
        database.mkdir()
        marker = database / "LOCK"
        marker.write_bytes(b"do not touch")
        with patch.dict(os.environ, {"APPDATA": str(self.root),
                                     "PROGRAMDATA": str(self.root / "missing")}):
            report = inspect_manager_profiles(rows, [game])
        self.assertEqual(report["profiles"], [])
        self.assertTrue(any("State.v2 was not opened" in x for x in report["warnings"]))
        self.assertEqual(marker.read_bytes(), b"do not touch")

    def test_vortex_invalid_json_does_not_guess_state(self):
        root, game, rows = self.make_vortex()
        backup = root / "temp" / "state_backups_full" / "manual.json"
        backup.write_text("{oops", encoding="utf-8")
        with patch.dict(os.environ, {"APPDATA": str(self.root),
                                     "PROGRAMDATA": str(self.root / "missing")}):
            report = inspect_manager_profiles(rows, [game])
        self.assertFalse(report["profiles"])
        self.assertTrue(any("invalid JSON" in x for x in report["warnings"]))

    def test_moved_path_and_identifier_are_exact(self):
        self.assertNotEqual(_identity(str(self.root / "Game")),
                            _identity(str(self.root / "GameOld")))
        self.assertEqual(_identity(r"C:\Steam\Game"),
                         _identity(r"c:\steam\game"))
        self.assertEqual(_identity(r"@ByteArray(C:\\Steam\\Game)"),
                         _identity(r"c:\steam\game"))


if __name__ == "__main__":
    unittest.main()
