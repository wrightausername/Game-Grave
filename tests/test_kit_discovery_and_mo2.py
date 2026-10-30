"""Regression fixtures for automatic Resurrection Kit discovery and MO2 reconnection.

Only synthetic folders under TemporaryDirectory are modified by these tests.
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core import SteamGame
from kit_discovery import discover_setup, select_sources
from manager_profiles import inspect_manager_profiles
from mod_sources import _mo2
from mo2_reconnect import preview_mo2_reconnect, reconnect_to_mo2
from resurrection_v2 import create_complete_kit


class AutoResurrectionTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)
        self.game_dir = self.root / "Steam" / "steamapps" / "common" / "Skyrim"
        self.game_dir.mkdir(parents=True)
        self.game = SteamGame("489830", "Skyrim", str(self.root),
                              str(self.game_dir), 1234, None, "Unknown")
        self.mod_base = self.root / "MO2Instance"
        self.mod_base.mkdir()
        self.profile_root = self.mod_base / "profiles"
        self.mod_root = self.mod_base / "mods"
        (self.profile_root / "Default").mkdir(parents=True)
        (self.mod_root / "SkyUI").mkdir(parents=True)
        (self.mod_root / "Some Texture").mkdir()
        (self.mod_root / "SkyUI" / "skyui.esp").write_bytes(b"fake test mod")
        (self.mod_root / "Some Texture" / "tex.dds").write_bytes(b"fake texture")
        (self.profile_root / "Default" / "modlist.txt").write_text(
            "+SkyUI\n+Some Texture\n# recorded\n", encoding="utf-8")
        self.ini = self.mod_base / "ModOrganizer.ini"
        self.ini.write_text(
            "[General]\n"
            "gamePath=" + str(self.game_dir) + "\n"
            "gameName=Skyrim\n"
            "selected_profile=@ByteArray(Default)\n"
            "[Settings]\n"
            "base_directory=" + str(self.mod_base) + "\n"
            "mod_directory=%BASE_DIR%/mods\n"
            "profiles_directory=%BASE_DIR%/profiles\n")
        self.mods = _mo2(self.mod_base, None)
        self.manager_report = inspect_manager_profiles(self.mods, [self.game])
        self.save_root = self.root / "Game Saves"
        self.save_root.mkdir()
        (self.save_root / "slot1.sav").write_bytes(b"only in disposable fixture")
        self.saves = [SimpleNamespace(game="Skyrim", path=str(self.save_root),
                                      kind="Possible saves")]
        self.zip = self.root / "Skyrim_KIT.zip"

    def discovered(self):
        return discover_setup(self.game, mods=self.mods, saves=self.saves,
                              manager_report=self.manager_report)

    def create_kit(self, include_saves=False):
        evidence = self.discovered()
        chosen = [row for row in evidence["candidates"]
                  if row["role"] in (("Profiles", "Mods", "Saves")
                                     if include_saves else ("Profiles", "Mods"))]
        sources, hints = select_sources(evidence, chosen)
        self.assertEqual(hints["kind"], "MO2")
        self.assertEqual(hints["profile"], "Default")
        return create_complete_kit("Skyrim", sources, self.zip,
                                   manager_context=hints)

    def prepare_fresh_mo2(self):
        # Removing only disposable fixture folders after a verified kit simulates
        # reinstalling MO2 with a clean manager library.
        shutil.rmtree(self.mod_root)
        shutil.rmtree(self.profile_root)
        self.mod_root.mkdir()
        self.profile_root.mkdir()

    def test_discovery_uses_exact_mo2_instance_and_save_label(self):
        results = self.discovered()
        self.assertEqual(results["count"], 3)
        roles = {row["role"] for row in results["candidates"]}
        self.assertEqual(roles, {"Saves", "Mods", "Profiles"})
        self.assertFalse(results["safe_to_delete"])
        self.assertTrue(all(row["requires_review"] for row in results["candidates"]))
        self.assertTrue(any(row["manager"] == "MO2" for row in results["candidates"]))

    def test_full_kit_mo2_additive_restore_preserves_existing_game(self):
        original_game = self.game_dir / "game.exe"
        original_game.write_bytes(b"unmodified game file")
        created = self.create_kit()
        manifest = json.loads(Path(created["manifest"]).read_text())
        self.assertNotIn(str(self.root), json.dumps(manifest))
        self.assertEqual(manifest["manager_context"]["profile"], "Default")
        self.prepare_fresh_mo2()
        plan = preview_mo2_reconnect(Path(created["manifest"]), self.ini,
                                     [self.game])
        self.assertEqual(plan["mods_count"], 2)
        self.assertIn("Default_GameGrave", plan["profile_target"])
        self.assertTrue(plan["no_overwrite"])
        with self.assertRaises(PermissionError):
            reconnect_to_mo2(Path(created["manifest"]), self.ini,
                             [self.game])
        with patch("mo2_reconnect._closed_manager_check", return_value=None):
            result = reconnect_to_mo2(Path(created["manifest"]), self.ini,
                                      [self.game], approved=True,
                                      expected_fingerprint=plan["fingerprint"])
        self.assertTrue(result["restored"])
        self.assertEqual((self.mod_root / "SkyUI" / "skyui.esp").read_bytes(),
                         b"fake test mod")
        self.assertEqual((self.profile_root / "Default_GameGrave" /
                          "modlist.txt").read_text(),
                         "+SkyUI\n+Some Texture\n# recorded\n")
        self.assertEqual(original_game.read_bytes(), b"unmodified game file")
        self.assertTrue(self.ini.exists())
        self.assertEqual(list(self.profile_root.iterdir())[0].name, "Default_GameGrave")

    def test_existing_mod_conflict_refuses_entire_reconnect(self):
        created = self.create_kit()
        # The original MO2 mods still exist. Absolutely no merge/overwrite.
        file = self.mod_root / "SkyUI" / "skyui.esp"
        with self.assertRaises(FileExistsError):
            preview_mo2_reconnect(Path(created["manifest"]), self.ini, [self.game])
        self.assertEqual(file.read_bytes(), b"fake test mod")
        self.assertFalse((self.profile_root / "Default_GameGrave").exists())

    def test_wrong_game_path_fails_closed(self):
        created = self.create_kit()
        self.prepare_fresh_mo2()
        self.ini.write_text(self.ini.read_text().replace(str(self.game_dir),
                             str(self.root / "not-the-same-game")))
        with self.assertRaisesRegex(ValueError, "does not match"):
            preview_mo2_reconnect(Path(created["manifest"]), self.ini,
                                  [self.game])
        self.assertEqual(list(self.mod_root.iterdir()), [])

    def test_kit_without_manager_evidence_cannot_reconnect(self):
        legacy = create_complete_kit("Skyrim", {
            "Mods": self.mod_root, "Profiles": self.profile_root / "Default"}, self.zip)
        self.prepare_fresh_mo2()
        with self.assertRaisesRegex(ValueError, "no verified MO2"):
            preview_mo2_reconnect(Path(legacy["manifest"]), self.ini, [self.game])

    def test_restore_plan_changes_require_fresh_approval(self):
        created = self.create_kit()
        self.prepare_fresh_mo2()
        preview = preview_mo2_reconnect(Path(created["manifest"]), self.ini,
                                        [self.game])
        # A different game config invalidates existing approval.
        self.ini.write_text(self.ini.read_text() + "\n# modified after preview\n")
        with patch("mo2_reconnect._closed_manager_check", return_value=None):
            with self.assertRaisesRegex(ValueError, "Preview again"):
                reconnect_to_mo2(Path(created["manifest"]), self.ini,
                                 [self.game], approved=True,
                                 expected_fingerprint=preview["fingerprint"])
        self.assertFalse((self.mod_root / "SkyUI").exists())

    def test_saves_remain_in_kit_but_are_not_guess_deployed(self):
        created = self.create_kit(include_saves=True)
        self.prepare_fresh_mo2()
        plan = preview_mo2_reconnect(Path(created["manifest"]), self.ini,
                                     [self.game])
        self.assertIn("Saves", plan["not_reconnected_roles"])
        with patch("mo2_reconnect._closed_manager_check", return_value=None):
            result = reconnect_to_mo2(Path(created["manifest"]), self.ini,
                                      [self.game], approved=True,
                                      expected_fingerprint=plan["fingerprint"])
        self.assertEqual(result["not_reconnected_roles"], ["Saves"])
        self.assertFalse((self.mod_root / "Saves").exists())
        self.assertTrue(self.save_root.exists())

    def test_no_false_owner_based_on_matching_manager_name(self):
        wrong = SteamGame("1", "Skyrim", str(self.root),
                          str(self.root / "Other Game"), 1, None, "Unknown")
        discovered = discover_setup(wrong, mods=self.mods, saves=[],
                                    manager_report=self.manager_report)
        self.assertEqual(discovered["candidates"], [])

    def test_vortex_does_not_claim_relink_to_leveldb(self):
        target = self.root / "Vortex" / "skyrimse" / "mods"
        target.mkdir(parents=True)
        observed = SimpleNamespace(source="Vortex", status="Vortex: mod staging",
                                   path=str(target))
        profile = {"manager":"Vortex", "verified_install_path":str(self.game_dir),
                   "verified_game":"Skyrim","game_hint":"skyrimse",
                   "stale":False,"incomplete":False}
        data = discover_setup(self.game, mods=[observed], saves=[],
                              manager_report={"profiles":[profile]})
        self.assertEqual(data["groups"]["Mods"][0]["manager"], "Vortex")
        self.assertFalse(data["groups"]["Mods"][0]["default"])
        sources, meta = select_sources(data, data["candidates"])
        self.assertEqual(meta["kind"], "Vortex")
        self.assertNotIn("active_profile", meta)


if __name__ == "__main__":
    unittest.main()
