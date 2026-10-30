"""Safety and correctness tests for Game Grave intelligence foundations."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import game_intelligence as gg
from core import ModFolder, SteamGame
from resurrection_kit import create_resurrection_kit, verify_resurrection_kit


def mod(path, source="Vortex"):
    return ModFolder(path.name, str(path), str(path.parent), "Managed", (),
                     1, 1, False, source, "Review")


class GameDNATests(unittest.TestCase):
    def test_existing_game_subfolder_links_but_sibling_does_not(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "Game"
            child = root / "Mods"
            sibling = Path(d) / "GameOld"
            child.mkdir(parents=True)
            sibling.mkdir()
            game = SteamGame("42", "Example", d, str(root), 100, None, "Unknown")
            dna = gg.build_game_dna([game], mods=[mod(child), mod(sibling)])
            self.assertEqual(len(dna["games"][0]["assets"]), 1)
            self.assertEqual(dna["games"][0]["assets"][0]["path"], str(child))
            self.assertTrue(dna["games"][0]["assets"][0]["protected"])
            self.assertEqual(len(dna["unresolved"]), 1)

    def test_steam_workshop_id_is_evidence_not_delete_authority(self):
        with tempfile.TemporaryDirectory() as d:
            game = SteamGame("42", "Example", d, str(Path(d) / "installed"), 0, None, "Unknown")
            folder = Path(d) / "steamapps" / "workshop" / "content" / "42" / "item"
            folder.mkdir(parents=True)
            dna = gg.build_game_dna([game], mods=[mod(folder, "Steam Workshop")])
            self.assertEqual(len(dna["games"][0]["assets"]), 1)
            self.assertIn("app ID", dna["games"][0]["assets"][0]["evidence"])
            self.assertNotIn("can_delete", dna["games"][0]["assets"][0])

    def test_saves_remain_unresolved_even_with_matching_title(self):
        with tempfile.TemporaryDirectory() as d:
            game = SteamGame("1", "Example", d, str(Path(d) / "installed"), 0, None, "Unknown")
            saved = SimpleNamespace(path=str(Path(d) / "saves"), game="Example", kind="Game saves")
            dna = gg.build_game_dna([game], saves=[saved])
            self.assertFalse(dna["games"][0]["assets"])
            self.assertTrue(dna["unresolved"][0]["protected"])

    def test_no_name_guessing_for_vortex_and_mo2(self):
        with tempfile.TemporaryDirectory() as d:
            game = SteamGame("20", "Example", d, str(Path(d) / "Game"), 0, None, "Unknown")
            path = Path(d) / "Vortex" / "Example" / "mods"
            path.mkdir(parents=True)
            dna = gg.build_game_dna([game], mods=[mod(path)])
            self.assertEqual(len(dna["unresolved"]), 1)


class ChangeObservationTests(unittest.TestCase):
    def test_changed_added_and_missing_mod_files(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "staging"
            folder.mkdir()
            original = folder / "before.dll"
            original.write_text("a")
            first = gg.capture_mod_observation([mod(folder)])
            self.assertIn(str(original.resolve()), first["entries"])
            original.unlink()
            new = folder / "new.ini"
            new.write_text("abc")
            second = gg.capture_mod_observation([mod(folder)])
            diff = gg.compare_observations(first, second)
            self.assertEqual(diff["count"], 2)
            self.assertEqual(diff["patch_review"], 2)
            self.assertEqual(diff["changes"][0]["change"], "missing from observation")
            self.assertTrue((folder / "new.ini").exists())
            self.assertTrue(gg.patch_fallout(diff)["review_files"])
            self.assertFalse(gg.patch_fallout(diff)["compatibility_verified"])

    def test_symlinks_not_followed_and_caps_are_reported(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "managed"
            folder.mkdir()
            for i in range(4):
                (folder / f"file{i}.ini").write_text("stuff")
            symlink = folder / "link.ini"
            try:
                symlink.symlink_to(folder / "file0.ini")
            except (OSError, NotImplementedError):
                pass
            observation = gg.capture_mod_observation([mod(folder)], max_entries=2)
            self.assertTrue(observation["truncated"])
            self.assertEqual(len(observation["entries"]), 2)
            self.assertNotIn(str(symlink.resolve(strict=False)), observation["entries"])

    def test_change_scope_and_first_baseline_do_not_promise_repair(self):
        first = {"schema": 1, "roots": ["A"], "entries": {"a.dll": [1, 1]}, "truncated": False}
        second = {"schema": 1, "roots": ["B"], "entries": {}, "truncated": False}
        self.assertTrue(gg.compare_observations(first, second)["scope_changed"])
        self.assertTrue(gg.ghost_watch(None, first)["first_observation"])
        self.assertIn("Comparison is incomplete", gg.what_broke_my_game(gg.compare_observations(first, second))[0])

    def test_local_history_only_written_explicitly(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(gg, "config_dir", return_value=Path(d)):
                self.assertIsNone(gg.load_observation())
                state = {"schema": 1, "roots": [], "entries": {}, "truncated": False}
                gg.save_observation(state)
                self.assertEqual(gg.load_observation()["schema"], 1)

    def test_reject_inappropriate_limit(self):
        with self.assertRaises(ValueError):
            gg.capture_mod_observation([], max_entries=1000000)


class PlanningTests(unittest.TestCase):
    def test_regret_ranking_never_claims_safe_or_freed_bytes(self):
        item = SimpleNamespace(path="/example/modpack.zip", apparent_bytes=123)
        result = gg.regret_calculator([item])
        self.assertEqual(result[0]["verified_reclaimable_bytes"], 0)
        self.assertFalse(result[0]["approved"])

    def test_exodus_is_a_checklist_only(self):
        dna = {"games": [{"game": "Test", "launcher": "Steam", "install_path": "C:/Games/Test",
                         "assets": [{"path": "C:/Mods/Test"}]}], "unresolved": [{}]}
        plan = gg.exodus_plan(dna)
        self.assertFalse(plan["copy_executed"])
        self.assertEqual(plan["unresolved_count"], 1)

    def test_community_drafts_have_no_paths_uploads_or_approval(self):
        draft = gg.community_rule_draft("MO2", "manager_staging", ".zip")
        self.assertFalse(draft["uploaded"])
        self.assertFalse(draft["approved"])
        with self.assertRaises(ValueError):
            gg.community_rule_draft("C:/Users/personal", "manager_staging", ".zip")


class ResurrectionKitTests(unittest.TestCase):
    def test_create_verified_non_overwriting_kit_and_detect_tampering(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "Saves"
            source.mkdir()
            (source / "game.sav").write_bytes(b"player progress")
            archive = Path(d) / "resurrection.zip"
            kit = create_resurrection_kit("Example", source, archive, ["Mod Reference"])
            self.assertTrue(kit["verified"])
            self.assertTrue(verify_resurrection_kit(Path(kit["manifest"]))["verified"])
            self.assertTrue((source / "game.sav").exists())
            manifest = json.loads(Path(kit["manifest"]).read_text())
            self.assertNotIn(str(source.parent), json.dumps(manifest))
            self.assertFalse(manifest["actual_mod_files_preserved"])
            with self.assertRaises(FileExistsError):
                create_resurrection_kit("Example", source, archive)
            archive.write_bytes(b"tampered")
            self.assertFalse(verify_resurrection_kit(Path(kit["manifest"]))["verified"])

    def test_manifest_path_escape_is_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            manifest = Path(d) / "bad.ggkit.json"
            manifest.write_text(json.dumps({"schema": 1, "archive": "../private.zip"}))
            with self.assertRaises(ValueError):
                verify_resurrection_kit(manifest)


if __name__ == "__main__":
    unittest.main()
