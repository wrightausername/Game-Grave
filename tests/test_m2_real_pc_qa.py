"""M2 real-PC QA report stays read-only, bounded and free of personal paths."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from core import SteamGame, ModFolder
from tools.m2_real_pc_qa import aggregate_results


class RealPcReportTests(unittest.TestCase):
    def test_aggregate_excludes_private_paths_titles_and_profile_names(self):
        with tempfile.TemporaryDirectory() as td:
            private = td + "/PRIVATE_USERNAME/PRIVATE_GAME_SAVE"
            game = SteamGame("42", "PRIVATE_GAME_TITLE", td, private,
                             512, None, "Unknown")
            mod = ModFolder("PRIVATE_MOD_TITLE", private + "/Mods", td,
                            "Installed mods", (), 700, 1, False, "Vortex",
                            "Read-only", 1)
            profile = {"manager": "Vortex", "profile": "PRIVATE_PROFILE",
                       "source": private, "stale": True, "incomplete": True,
                       "mods": [{"name": "PRIVATE_MOD_TITLE", "marker": "+"}]}
            report = aggregate_results([game], [], [mod], {"profiles": [profile]})
            exported = json.dumps(report)
            for item in ("PRIVATE_USERNAME", "PRIVATE_GAME_TITLE",
                         "PRIVATE_MOD_TITLE", "PRIVATE_PROFILE", private):
                self.assertNotIn(item, exported)
            self.assertEqual(report["games_by_launcher"]["Steam"], 1)
            self.assertEqual(report["mod_roots_by_source"]["Vortex"], 1)
            self.assertEqual(report["stale_manager_snapshots"], 1)
            self.assertTrue(report["scan_only"])
            self.assertFalse(report["automatic_cleanup_authorized"])
            self.assertFalse(report["m2_release_accepted"])

    def test_unrecognized_sources_are_grouped_not_output_raw(self):
        private = r"C:\Sensitive\User\Secret Mod Tool"
        mod = SimpleNamespace(path=private, source=private, truncated=True)
        other = SimpleNamespace(name="Secret", launcher=private, install_path=private)
        report = aggregate_results([], [other], [mod], {"profiles": []})
        out = json.dumps(report)
        self.assertNotIn(private, out)
        self.assertEqual(report["games_by_launcher"]["Other"], 1)
        self.assertEqual(report["mod_roots_by_source"]["Other"], 1)
        self.assertEqual(report["truncated_mod_scan_results"], 1)

    def test_empty_scan_does_not_claim_reliable_coverage(self):
        report = aggregate_results([], [], [], {"profiles": [], "warnings": []})
        self.assertEqual(report["games_by_launcher"]["Steam"], 0)
        self.assertEqual(report["confirmed_orphan_mods"], 0)
        self.assertFalse(report["manually_verified_against_launchers"])
        self.assertFalse(report["m2_release_accepted"])


if __name__ == "__main__":
    unittest.main()
