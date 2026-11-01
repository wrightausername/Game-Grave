"""Ready Room change-detection tests use only synthetic disposable local files."""
from __future__ import annotations

from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from gg_desktop.ready_room_health import (
    _identity, capture_game_state, linked_mods_for_game,
    load_game_baseline, save_game_baseline, compare_game_state,
)


class ReadyRoomHealthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.game_dir = self.root / "steamapps" / "common" / "Test Game"
        self.mod_dir = self.game_dir / "mods"
        self.mod_dir.mkdir(parents=True)
        self.sample = self.mod_dir / "example.esp"
        self.sample.write_bytes(b"working mod")
        self.game = SimpleNamespace(
            name="Test Game", key="Steam:123", launcher="Steam",
            app_id="123", install_path=str(self.game_dir),
            status="Installed (Steam record)", size_bytes=100,
        )
        self.mod = SimpleNamespace(path=str(self.mod_dir), source="Mod Radar")
        self.detector = SimpleNamespace(active=lambda: False)
        self.patch = patch("gg_desktop.ready_room_health.config_dir", return_value=self.root / "settings")
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_only_evidenced_mod_roots_can_be_tracked(self):
        other = self.root / "unrelated" / "mods"
        other.mkdir(parents=True)
        mod2 = SimpleNamespace(path=str(other), source="Mod Radar")
        self.assertEqual(linked_mods_for_game(self.game, [self.mod, mod2]), [self.mod])

    def test_baseline_and_comparison_use_file_metadata_not_contents(self):
        first = capture_game_state(self.game, [self.mod], detector=self.detector)
        self.assertEqual(first["linked_mod_roots"], 1)
        self.assertGreater(len(first["observation"]["entries"]), 0)
        self.assertFalse(compare_game_state(None, first)["has_baseline"])
        path = save_game_baseline(self.game, first)
        self.assertTrue(path.is_file())
        loaded = load_game_baseline(self.game)
        self.assertIsNotNone(loaded)
        self.sample.write_bytes(b"changed mod content and size")
        second = capture_game_state(self.game, [self.mod], detector=self.detector)
        delta = compare_game_state(loaded, second)
        self.assertTrue(delta["has_baseline"])
        self.assertGreater(delta["total_changes"], 0)
        self.assertGreater(delta["potential_mod_review"], 0)
        self.assertTrue(self.sample.is_file())

    def test_gameplay_cancel_avoids_observation_and_file_changes(self):
        with self.assertRaises(InterruptedError):
            capture_game_state(
                self.game, [self.mod], cancel=lambda: True,
                detector=SimpleNamespace(active=lambda: True))
        self.assertTrue(self.sample.is_file())
        self.assertIsNone(load_game_baseline(self.game))

    def test_baseline_identity_does_not_use_similar_game_titles(self):
        other = SimpleNamespace(**vars(self.game))
        other.install_path = str(self.root / "other-folder")
        self.assertNotEqual(_identity(self.game), _identity(other))


if __name__ == "__main__":
    unittest.main()
