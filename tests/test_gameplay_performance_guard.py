"""Game Grave gameplay guard: no live game or GUI required."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core import run_auto_cleanup, scan_old_files
from performance_guard import (
    CooperativeGameplayPause, GameActivityDetector, background_worker_priority,
)


class GameActivityDetectorTests(unittest.TestCase):
    def test_known_steam_game_is_detected_without_fullscreen(self):
        detector = GameActivityDetector(
            process_paths=lambda: [r"C:\Steam\steamapps\common\Skyrim\SkyrimSE.exe"],
            fullscreen=lambda: False,
        )
        self.assertTrue(detector.active())

    def test_known_custom_game_install_is_detected(self):
        detector = GameActivityDetector(
            process_paths=lambda: [r"D:\My Library\Installed\Game\bin\game.exe"],
            fullscreen=lambda: False,
        )
        detector.set_game_roots([r"D:\My Library\Installed\Game"])
        self.assertTrue(detector.active())

    def test_game_launcher_outside_install_is_not_false_positive(self):
        detector = GameActivityDetector(
            process_paths=lambda: [r"C:\Program Files (x86)\Steam\steam.exe"],
            fullscreen=lambda: False,
        )
        self.assertFalse(detector.active())

    def test_epic_launcher_does_not_pause_forever(self):
        detector = GameActivityDetector(
            process_paths=lambda: [
                r"C:\Program Files\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe",
            ],
            fullscreen=lambda: False,
        )
        self.assertFalse(detector.active())

    def test_windowed_xbox_and_custom_games_detected_before_inventory(self):
        for path in (
            r"C:\XboxGames\Halo Infinite\Content\game.exe",
            r"D:\Games\MyGame\bin\game.exe",
            r"E:\EA Games\Battlefield\bf.exe",
        ):
            with self.subTest(path=path):
                detector = GameActivityDetector(
                    process_paths=lambda path=path: [path], fullscreen=lambda: False,
                )
                self.assertTrue(detector.active())

    def test_fullscreen_fallback_catches_game_without_process_path(self):
        detector = GameActivityDetector(
            process_paths=lambda: [],
            fullscreen=lambda: True,
        )
        self.assertTrue(detector.active())

    def test_process_check_is_cached_without_repeated_enumeration(self):
        calls = []
        now = [50.0]
        def processes():
            calls.append(1)
            return []
        detector = GameActivityDetector(
            process_paths=processes, fullscreen=lambda: False,
            clock=lambda: now[0], refresh_seconds=3,
        )
        self.assertFalse(detector.active())
        self.assertFalse(detector.active())
        now[0] += 2
        self.assertFalse(detector.active())
        self.assertEqual(len(calls), 1)
        now[0] += 2
        self.assertFalse(detector.active())
        self.assertEqual(len(calls), 2)


class CooperativePauseTests(unittest.TestCase):
    def test_scan_stops_waiting_after_game_closes(self):
        active = [True]
        transitions = []
        gate = CooperativeGameplayPause(
            lambda: False, detector=SimpleNamespace(active=lambda: active[0]),
            on_pause=transitions.append,
            sleep=lambda _: active.__setitem__(0, False),
        )
        self.assertFalse(gate.checkpoint())
        self.assertEqual(transitions, [True, False])

    def test_cancel_works_while_game_remains_open(self):
        canceled = [False]
        notifications = []
        gate = CooperativeGameplayPause(
            lambda: canceled[0], detector=SimpleNamespace(active=lambda: True),
            on_pause=notifications.append,
            sleep=lambda _: canceled.__setitem__(0, True),
        )
        self.assertTrue(gate.checkpoint())
        self.assertEqual(notifications, [True])

    def test_background_context_is_safe_on_non_windows_hosts(self):
        with background_worker_priority():
            self.assertTrue(True)


class AutoCleanupProtectionTests(unittest.TestCase):
    def test_scheduled_cleanup_does_not_even_read_settings_while_gaming(self):
        with patch("performance_guard.GameActivityDetector.active", return_value=True):
            with patch("core.load_settings") as load:
                done, byte_count, status = run_auto_cleanup()
        load.assert_not_called()
        self.assertEqual((done, byte_count), (0, 0))
        self.assertIn("deferred", status)

    def test_old_file_scan_has_file_level_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "MyDownloads"
            root.mkdir()
            (root / "a.tmp").write_bytes(b"1")
            (root / "b.tmp").write_bytes(b"2")
            calls = []
            def cancel():
                calls.append(1)
                return len(calls) >= 3
            with self.assertRaises(InterruptedError):
                scan_old_files(root, min_days=1, cancel=cancel)
            self.assertGreaterEqual(len(calls), 3)


if __name__ == "__main__":
    unittest.main()
