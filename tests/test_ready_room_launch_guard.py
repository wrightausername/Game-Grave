"""Readiness checks never claim compatibility from file existence."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from gg_desktop.ready_room_data import launch_guard_summary


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
