"""Readiness checks never claim compatibility from file existence."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from gg_desktop.ready_room_data import launch_guard_summary, official_patch_source_for
from gg_desktop.ready_room_data import tonight_pick


class LaunchGuardTests(unittest.TestCase):
    def test_detects_missing_install(self):
        with tempfile.TemporaryDirectory() as root:
            game = SimpleNamespace(
                status="Installed (Steam record)",
                install_path=str(Path(root) / "not-installed"))
            status, summary = launch_guard_summary(game, free_bytes=100 * 1024**3)
            self.assertEqual(status, "Attention")
            self.assertIn("no longer exists", summary)

    def test_reports_low_space_without_claiming_mod_compatibility(self):
        with tempfile.TemporaryDirectory() as root:
            game = SimpleNamespace(
                status="Installed (Steam record)", install_path=root)
            status, summary = launch_guard_summary(game, free_bytes=5 * 1024**3)
            self.assertEqual(status, "Attention")
            self.assertIn("8 GB", summary)

    def test_installed_status_is_not_a_claim_that_game_runs(self):
        with tempfile.TemporaryDirectory() as root:
            game = SimpleNamespace(
                status="Installed (Steam record)", install_path=root)
            status, summary = launch_guard_summary(game, free_bytes=40 * 1024**3)
            self.assertEqual(status, "Installed")
            self.assertIn("unverified", summary)

    def test_unverified_game_never_becomes_ready(self):
        game = SimpleNamespace(status="Unverified folder",
                               install_path="/does-not-matter")
        self.assertEqual(launch_guard_summary(game)[0], "Unknown")

class PublisherSourcesTests(unittest.TestCase):
    def test_known_game_has_official_publisher_destination(self):
        known = SimpleNamespace(name="Cyberpunk 2077")
        source = official_patch_source_for(known)
        self.assertEqual(source[0], "CD PROJEKT RED")
        self.assertTrue(source[1].startswith("https://www.cyberpunk.net/"))

    def test_similar_name_is_not_attributed_to_different_game(self):
        unknown = SimpleNamespace(name="Cyberpunk 2077 Multiplayer Fan Clone")
        self.assertIsNone(official_patch_source_for(unknown))

class TonightPickTests(unittest.TestCase):
    def test_choice_is_stable_for_day_and_uses_only_installed_games(self):
        games = [
            SimpleNamespace(name="A", key="A", status="Installed (Steam record)"),
            SimpleNamespace(name="B", key="B", status="Unverified folder"),
            SimpleNamespace(name="C", key="C", status="Installed (launcher evidence)"),
        ]
        a = tonight_pick(games, day="2026-11-01")
        b = tonight_pick(games, day="2026-11-01")
        self.assertIs(a, b)
        self.assertNotEqual(a.name, "B")
        self.assertNotEqual(tonight_pick(games, day="2026-11-01", offset=1).key,
                            a.key)
