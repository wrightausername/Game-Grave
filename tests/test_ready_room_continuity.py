"""Game Grave private Ready Room features: measured, not invented, sessions."""
from __future__ import annotations
from datetime import datetime, timezone
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from gg_desktop import ready_room_sessions as session, ready_room_memory as memory


class ReadyRoomContinuityTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        root = Path(self.t.name)
        for module in (session, memory):
            patcher = patch.object(module, "config_dir", return_value=root)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.game = SimpleNamespace(
            key="Steam:222:/thegame", name="Example Game", launcher="Steam",
            status="Installed (Steam record)",
            install_path=str(root/"steamapps"/"common"/"Example Game"))

    def test_only_completed_sessions_count_in_recap(self):
        self.assertEqual(session.recap(session.read_sessions(), "This Year")["seconds"], 0)
        start = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
        tick = int(start.timestamp())
        session.start_session(self.game, at=tick)
        self.assertIsNotNone(session.active_session())
        self.assertEqual(session.recap(session.read_sessions(), "This Year",
                                       now=start)["sessions"], 0)
        result = session.finish_session(at=tick + 2700)
        self.assertEqual(result["end"] - result["start"], 2700)
        stats = session.recap(session.read_sessions(), "This Year", now=start)
        self.assertEqual(stats["seconds"], 2700)
        self.assertEqual(stats["average_seconds"], 2700)
        self.assertEqual(stats["most_played"], "Example Game")
        self.assertEqual(stats["monthly_seconds"][10], 2700)
        self.assertEqual(stats["sessions"], 1)
        self.assertIsNone(session.active_session())

    def test_daily_sessions_never_fake_entire_year(self):
        start = int(datetime(2026, 8, 5, tzinfo=timezone.utc).timestamp())
        session.start_session(self.game, at=start)
        session.finish_session(at=start+3600)
        now = datetime(2026, 11, 1, tzinfo=timezone.utc)
        self.assertEqual(session.recap(session.read_sessions(), "This Year",
                                       now=now)["sessions"], 1)
        self.assertEqual(session.recap(session.read_sessions(), "This Month",
                                       now=now)["sessions"], 0)
        self.assertEqual(session.recap(session.read_sessions(), "This Session",
                                       now=now)["sessions"], 1)

    def test_cannot_double_start_and_stale_not_saved(self):
        session.start_session(self.game, at=1000)
        with self.assertRaises(ValueError):
            session.start_session(self.game, at=1200)
        with self.assertRaises(ValueError):
            session.finish_session(at=1000 + session.MAX_SESSION_SECONDS + 1)
        self.assertFalse(session.read_sessions())
        self.assertIsNone(session.finish_session(discard=True))
        self.assertIsNone(session.active_session())

    def test_captures_associated_by_timestamp_not_assumed_game_name(self):
        begin = int(datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp())
        run = {"start": begin, "end": begin + 7200}
        named = SimpleNamespace(modified=begin+10, path="unrelated_shot.png")
        before = SimpleNamespace(modified=begin-5, path="Example_Game.png")
        video = SimpleNamespace(modified=begin+7000, path="video.mp4")
        actual = session.captured_during(run, [before, video, named])
        self.assertEqual(actual, [video, named])
        self.assertEqual(session.captured_during(None, [named]), [])

    def test_game_memory_local_and_install_files_untouched(self):
        expected = memory.save_game_memory(
            self.game, where="At the final boss",
            next_goal="Repair gear", profile="Mod Organizer profile Alpha")
        self.assertEqual(memory.read_game_memory(self.game), expected)
        another = SimpleNamespace(**{**vars(self.game),
                                      "install_path":"/completely/different/path"})
        self.assertEqual(memory.read_game_memory(another)["next"], "")
        self.assertFalse(Path(self.game.install_path).exists())
        with self.assertRaises(ValueError):
            memory.save_game_memory(self.game, where=2, next_goal="", profile="")


if __name__ == "__main__":
    unittest.main()
