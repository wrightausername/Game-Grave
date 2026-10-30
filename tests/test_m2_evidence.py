"""M2 game/mod evidence regression tests. Disposable local fixtures only."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from core import ModFolder, SteamGame
from launchers import LauncherGame, _ordinary_install, epic_games
from game_intelligence import build_game_dna, capture_mod_observation, compare_observations
from mod_radar_audit import audit_mod_radar


def mod(path: Path, source="Mod Organizer 2"):
    return ModFolder(path.name, str(path), str(path.parent), "Installed mods", (),
                     3, 1, False, source, "Review in manager")


class M2EvidenceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def _game(self, install: Path, appid="42"):
        return SteamGame(appid, "Example", str(self.root), str(install),
                         42, None, "Unknown")

    def test_epic_manifest_missing_location_does_not_become_cwd_game(self):
        program = self.root / "ProgramData"
        manifests = program / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
        manifests.mkdir(parents=True)
        for idx, location in enumerate(("", " ", ".", "/", None)):
            info = {"DisplayName": f"Phantom Game {idx}", "AppName": f"phantom{idx}"}
            if location is not None:
                info["InstallLocation"] = location
            (manifests / f"phantom{idx}.item").write_text(json.dumps(info))
        actual = self.root / "Real Game"
        actual.mkdir()
        (manifests / "real.item").write_text(json.dumps({
            "DisplayName": "Real Game", "AppName": "realgame",
            "InstallLocation": str(actual), "InstallSize": 1024,
        }))
        report = epic_games(program)
        self.assertEqual([x.name for x in report], ["Real Game"])
        self.assertEqual(report[0].reported_bytes, 1024)
        self.assertEqual(report[0].install_path, str(actual))

    def test_launcher_install_path_must_be_real_absolute_ordinary_directory(self):
        directory = self.root / "Valid"
        directory.mkdir()
        self.assertEqual(_ordinary_install(str(directory)), directory)
        for raw in ("", "   ", ".", "../somegame", "/", None, 123, str(self.root / "absent")):
            self.assertIsNone(_ordinary_install(raw))

    def test_symlink_parent_is_not_verifiable_launcher_install(self):
        original = self.root / "Real"
        original.mkdir()
        (original / "Game").mkdir()
        redirected = self.root / "Redirected"
        try:
            redirected.symlink_to(original, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symbolic links unavailable on this Windows runner")
        self.assertIsNone(_ordinary_install(str(redirected / "Game")))

    def test_conflicting_game_install_roots_never_assign_mod_owner(self):
        games = self.root / "Games"
        child = games / "Nested Game"
        (child / "Mods").mkdir(parents=True)
        parent_game = self._game(games, "10")
        nested_game = self._game(child, "11")
        finding = mod(child / "Mods")
        data = build_game_dna([parent_game, nested_game], mods=[finding])
        self.assertEqual(sum(len(g["assets"]) for g in data["games"]), 0)
        self.assertEqual(len(data["unresolved"]), 1)
        self.assertTrue(data["unresolved"][0]["ambiguous"])
        self.assertIn("Multiple launcher/game records", data["unresolved"][0]["reason"])
        audit = audit_mod_radar([parent_game, nested_game], mods=[finding])
        self.assertEqual(audit["ambiguous_claims"], 1)
        self.assertEqual(audit["associated_mod_locations"], 0)
        self.assertEqual(audit["removal_authorizations"], 0)

    def test_custom_library_folder_is_not_proof_of_installed_game(self):
        base = self.root / "User Library"
        (base / "Example" / "Mods").mkdir(parents=True)
        user_game = LauncherGame("Example", "Custom library",
                                 str(base / "Example"), "", None, "Folder present")
        data = build_game_dna(other_games=[user_game], mods=[mod(base / "Example" / "Mods")])
        self.assertEqual(data["games"][0]["assets"], [])
        self.assertTrue(data["unresolved"][0]["ambiguous"])
        self.assertIn("User-added library", data["unresolved"][0]["reason"])

    def test_linked_ancestor_does_not_link_mod_to_game(self):
        base = self.root / "Real Game"
        (base / "Mods").mkdir(parents=True)
        redirect = self.root / "Shortcuts"
        try:
            redirect.symlink_to(base, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symbolic links unavailable on this Windows runner")
        data = build_game_dna([self._game(base)], mods=[mod(redirect / "Mods")])
        self.assertFalse(data["games"][0]["assets"])
        self.assertIn("linked or redirected", data["unresolved"][0]["reason"])
        report = audit_mod_radar([self._game(base)], mods=[mod(redirect / "Mods")])
        self.assertEqual(report["redirected_locations"], 1)
        self.assertFalse(report["safe_to_recycle"])

    def test_unique_exact_association_still_works_without_deletion_rights(self):
        root = self.root / "Game"
        (root / "Mods").mkdir(parents=True)
        data = build_game_dna([self._game(root)], mods=[mod(root / "Mods")])
        self.assertEqual(len(data["games"][0]["assets"]), 1)
        self.assertFalse(data["games"][0]["assets"][0]["can_recycle"])
        self.assertTrue(data["games"][0]["assets"][0]["protected"])
        audit = audit_mod_radar([self._game(root)], mods=[mod(root / "Mods")])
        self.assertEqual(audit["associated_mod_locations"], 1)
        self.assertEqual(audit["confirmed_orphans"], 0)

    def test_truncated_observation_does_not_claim_absent_mod_was_deleted(self):
        first = {"schema": 1, "roots": ["A"], "entries": {"A/keep.dll": [1, 1]},
                 "truncated": False}
        newer = {"schema": 1, "roots": ["A"], "entries": {}, "truncated": True}
        report = compare_observations(first, newer)
        self.assertEqual(report["count"], 1)
        self.assertTrue(report["incomplete"])
        self.assertTrue(report["unreliable_missing_inference"])
        self.assertEqual(report["changes"][0]["change"], "not observed (incomplete comparison)")
        newer["truncated"] = False
        newer["roots"] = ["B"]
        report = compare_observations(first, newer)
        self.assertTrue(report["scope_changed"])
        self.assertTrue(report["incomplete"])
        self.assertIn("incomplete comparison", report["changes"][0]["change"])

    def test_linked_or_skipped_scan_root_marks_ghost_watch_incomplete(self):
        root = self.root / "Mods"
        root.mkdir()
        (root / "mod.dll").write_bytes(b"1")
        alias = self.root / "Alias"
        try:
            alias.symlink_to(root, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symbolic links unavailable")
        data = capture_mod_observation([mod(root), mod(alias)])
        self.assertEqual(data["skipped_roots"], 1)
        self.assertTrue(data["truncated"])
        self.assertEqual(len(data["entries"]), 1)
        self.assertIn("mod.dll", "".join(data["entries"]))
        self.assertTrue((root / "mod.dll").exists())

    def test_audit_shows_recorded_state_but_never_calls_disabled_safe(self):
        root = self.root / "Game"
        (root / "Mods").mkdir(parents=True)
        p = {
            "manager": "Mod Organizer 2", "profile": "Default",
            "verified_install_path": str(root), "source": "local fixture",
            "stale": True, "incomplete": True,
            "mods": [{"name": "A", "marker": "+"}, {"name": "B", "marker": "-"}],
        }
        audit = audit_mod_radar([self._game(root)], mods=[mod(root / "Mods")],
                               manager_profiles=[p])
        self.assertEqual(audit["enabled_profile_references"], 1)
        self.assertEqual(audit["disabled_profile_references"], 1)
        self.assertEqual(audit["stale_manager_snapshots"], 1)
        self.assertEqual(audit["incomplete_manager_snapshots"], 1)
        self.assertEqual(audit["removal_authorizations"], 0)
        self.assertFalse(audit["safe_to_recycle"])


if __name__ == "__main__":
    unittest.main()
