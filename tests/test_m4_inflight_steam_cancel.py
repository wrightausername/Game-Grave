"""M4: real scan cancellation between Steam manifests and account records."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import find_games, local_play_history


class InflightSteamCancelTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "Steam"
        (self.root / "steamapps" / "common").mkdir(parents=True)
        for appid in (101, 102, 103):
            (self.root / "steamapps" / f"appmanifest_{appid}.acf").write_text("ignored")

    def test_cancel_before_any_source_read(self):
        with patch("core._steam_roots", return_value=[self.root]), \
             patch("core.read_vdf") as reader:
            with self.assertRaises(InterruptedError):
                find_games(cancel=lambda: True)
        reader.assert_not_called()

    def test_cancel_while_enumerating_manifests_aborts_partial_results(self):
        stop = {"now": False}
        def read(meta):
            stop["now"] = True
            return {"appstate": {"appid": "101", "name": "Example",
                                 "installdir": "Example", "stateflags": "4"}}
        with patch("core._steam_roots", return_value=[self.root]), \
             patch("core.steam_libraries", return_value=[self.root]), \
             patch("core.local_play_history", return_value={}), \
             patch("core.read_vdf", side_effect=read) as reader:
            with self.assertRaisesRegex(InterruptedError, "canceled"):
                find_games(cancel=lambda: stop["now"])
        self.assertEqual(reader.call_count, 1)

    def test_cancel_during_user_play_history_does_not_report_completion(self):
        store = self.root / "userdata" / "1234" / "config"
        store.mkdir(parents=True)
        (store / "localconfig.vdf").write_text("fixture")
        data = {"userlocalconfigstore": {"software": {"valve": {"steam": {
            "apps": {"101": {"lastplayed": "1700000000"},
                     "102": {"lastplayed": "1700000001"},
                     "103": {"lastplayed": "1700000002"}}
        }}}}}
        state = {"calls": 0}
        def cancel():
            state["calls"] += 1
            return state["calls"] >= 3
        with patch("core.read_vdf", return_value=data):
            with self.assertRaises(InterruptedError):
                local_play_history([self.root], cancel=cancel)
        self.assertGreaterEqual(state["calls"], 3)

    def test_no_cancel_preserves_known_game_manifest_scan(self):
        directory = self.root / "steamapps" / "common" / "Test Game"
        directory.mkdir()
        expected = {"appstate": {"appid": "101", "name": "Test Game",
                                 "installdir": "Test Game", "stateflags": "4",
                                 "sizeondisk": "1024"}}
        def metadata(path):
            return expected if path.stem == "appmanifest_101" else {}
        with patch("core._steam_roots", return_value=[self.root]), \
             patch("core.steam_libraries", return_value=[self.root]), \
             patch("core.local_play_history", return_value={}), \
             patch("core.read_vdf", side_effect=metadata):
            games = find_games(cancel=lambda: False)
        self.assertEqual(len(games), 1)
        self.assertEqual(games[0].name, "Test Game")


if __name__ == "__main__":
    unittest.main()
