"""Game Grave gameplay guard: no live game or GUI required."""
from __future__ import annotations

import tempfile
import ctypes
import ntpath
import os
import importlib.util
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from ctypes import wintypes

from core import run_auto_cleanup, scan_old_files
from performance_guard import (
    CooperativeGameplayPause, GameActivityDetector, background_worker_priority,
    _Rect, _MonitorInfo, _window_is_fullscreen, _windows_user32,
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

    def test_windowed_store_games_detected_before_inventory(self):
        for path in (
            r"C:\XboxGames\Halo Infinite\Content\game.exe",
            r"E:\EA Games\Battlefield\bf.exe",
        ):
            with self.subTest(path=path):
                detector = GameActivityDetector(
                    process_paths=lambda path=path: [path], fullscreen=lambda: False,
                )
                self.assertTrue(detector.active())

    def test_arbitrary_games_folder_is_not_installation_evidence(self):
        detector = GameActivityDetector(
            process_paths=lambda: [r"D:\Games\Utilities\browser.exe"],
            fullscreen=lambda: False,
        )
        self.assertFalse(detector.active())
        self.assertEqual(detector.pause_reason, "")

    def test_game_grave_and_its_same_executable_bootloader_do_not_pause_scan(self):
        for own_path in (r"D:\Games\GameGrave\GameGrave-Crimson-Preview.exe",
                         r"D:\Steam\steamapps\common\GameGrave\GameGrave.exe"):
            with self.subTest(path=own_path), patch("performance_guard.sys.executable", own_path):
                detector = GameActivityDetector(
                    process_paths=lambda: [own_path, own_path.upper()],
                    fullscreen=lambda: False)
                detector.set_game_roots([ntpath.dirname(own_path)])
                self.assertFalse(detector.active())

    def test_wallpaper_launcher_and_crash_helpers_do_not_hold_scan_forever(self):
        for name in ("wallpaper64.exe", "wallpaper32.exe", "wallpaperui.exe",
                     "UnityCrashHandler64.exe", "crashpad_handler.exe", "steamwebhelper.exe",
                     "EOSOverlayRenderer-Win64-Shipping.exe", "EOSOverlayRenderer-Win32-Shipping.exe"):
            with self.subTest(executable=name):
                root = r"D:\Steam\steamapps\common\Some App"
                detector = GameActivityDetector(
                    process_paths=lambda: [root + "\\" + name], fullscreen=lambda: False)
                detector.set_game_roots([root])
                self.assertFalse(detector.active())

    def test_pause_names_the_game_process_and_clears_after_it_exits(self):
        paths = [r"D:\EA Games\Battlefield\bf.exe"]
        now = [0.0]
        detector = GameActivityDetector(process_paths=lambda: paths,
            fullscreen=lambda: False, clock=lambda: now[0])
        self.assertTrue(detector.active())
        self.assertEqual(detector.pause_reason, "Running game process: bf.exe")
        paths.clear()
        now[0] = 4.0
        self.assertFalse(detector.active())
        self.assertEqual(detector.pause_reason, "")

    def test_fullscreen_fallback_catches_game_without_process_path(self):
        detector = GameActivityDetector(
            process_paths=lambda: [],
            fullscreen=lambda: True,
        )
        self.assertTrue(detector.active())
        self.assertIn("Fullscreen application", detector.pause_reason)

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


class FullscreenWindowTests(unittest.TestCase):
    def window_api(self, *, owner=None, window_class="GameWindow",
                   style=0x90000000, rect=(0, 0, 1920, 1080),
                   monitor=(0, 0, 1920, 1080)):
        def process_id(_hwnd, pointer):
            ctypes.cast(pointer, ctypes.POINTER(wintypes.DWORD)).contents.value = (
                os.getpid()+100 if owner is None else owner)
            return 1
        def class_name(_hwnd, buffer, _length):
            buffer.value = window_class
            return len(window_class)
        def window_rect(_hwnd, pointer):
            bounds = ctypes.cast(pointer, ctypes.POINTER(_Rect)).contents
            bounds.left, bounds.top, bounds.right, bounds.bottom = rect
            return 1
        def monitor_info(_handle, pointer):
            info = ctypes.cast(pointer, ctypes.POINTER(_MonitorInfo)).contents
            info.rcMonitor = _Rect(*monitor)
            return 1
        return SimpleNamespace(GetDesktopWindow=lambda: 1, GetShellWindow=lambda: 2,
            GetWindowThreadProcessId=process_id, GetClassNameW=class_name,
            GetWindowLongW=lambda *_: style, GetWindowRect=window_rect,
            MonitorFromWindow=lambda *_: 3, GetMonitorInfoW=monitor_info)

    def test_shell_handles_and_desktop_taskbar_classes_are_never_games(self):
        api = self.window_api()
        for handle in (None, 0, 1, 2):
            self.assertFalse(_window_is_fullscreen(api, handle))
        for name in ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
            with self.subTest(window_class=name):
                self.assertFalse(_window_is_fullscreen(self.window_api(window_class=name), 100))

    def test_own_and_unidentified_windows_do_not_pause_scanning(self):
        for owner in (os.getpid(), 0):
            with self.subTest(owner=owner):
                self.assertFalse(_window_is_fullscreen(self.window_api(owner=owner), 100))

    def test_maximized_browser_with_hidden_taskbar_is_not_fullscreen(self):
        api = self.window_api(window_class="Chrome_WidgetWin_1", style=0x10CF0000,
                              rect=(-8, -8, 1928, 1088))
        self.assertFalse(_window_is_fullscreen(api, 100))
        self.assertFalse(_window_is_fullscreen(
            self.window_api(style=0x10CF0000), 100))

    def test_foreign_borderless_fullscreen_still_pauses_on_any_monitor(self):
        for rect in ((0, 0, 1920, 1080), (-1920, 0, 0, 1080), (1920, -1080, 3840, 0)):
            with self.subTest(monitor=rect):
                self.assertTrue(_window_is_fullscreen(
                    self.window_api(rect=rect, monitor=rect), 100))

    def test_windowed_and_monitor_spanning_apps_are_not_fullscreen(self):
        for rect in ((0, 0, 1920, 1040), (200, 100, 1500, 900), (0, 0, 3840, 1080)):
            with self.subTest(rect=rect):
                self.assertFalse(_window_is_fullscreen(self.window_api(rect=rect), 100))

    @unittest.skipUnless(os.name == "nt", "Requires native Windows shell handles")
    def test_actual_windows_desktop_and_shell_are_excluded(self):
        api = _windows_user32()
        self.assertFalse(_window_is_fullscreen(api, api.GetDesktopWindow()))
        self.assertFalse(_window_is_fullscreen(api, api.GetShellWindow()))


class ActivityIndependentScanTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        # Any attempt to inspect a game/fullscreen state fails immediately,
        # rather than hanging the regression test in the old pause loop.
        self.detector = self.stack.enter_context(patch(
            "performance_guard.GameActivityDetector",
            side_effect=AssertionError("Requested scans must not query game activity")))
        self.stack.enter_context(patch(
            "performance_guard.CooperativeGameplayPause.checkpoint",
            side_effect=AssertionError("Requested scans must never enter a gameplay wait")))
        self.stack.enter_context(patch(
            "performance_guard._foreground_is_fullscreen", return_value=True))
        self.scanners = {}
        def scan(*args, cancel, **kwargs):
            if cancel():
                raise InterruptedError("Scan canceled")
            return []
        for name in ("find_games", "find_launcher_games", "find_all_mod_storage",
                     "find_old_recordings", "find_old_screenshots"):
            self.scanners[name] = self.stack.enter_context(patch(
                "gg_desktop.backend." + name, side_effect=scan))
        self.stack.enter_context(patch("gg_desktop.backend.scan_old_files_scope",
            return_value=SimpleNamespace(files=[], status="complete", message="Done")))
        self.stack.enter_context(patch("save_discovery.discover_saves", return_value=[]))
        self.stack.enter_context(patch("gg_desktop.backend.build_graveyard", return_value=[]))

    def test_inventory_finishes_all_stages_without_game_or_fullscreen_wait(self):
        from gg_desktop.backend import scan_inventory
        messages = []
        inventory = scan_inventory({}, lambda: False,
            lambda percent, stage: messages.append((percent, stage)))
        self.assertTrue(inventory.scanned_at)
        self.assertEqual(inventory.old_files_scan_status, "complete")
        self.assertEqual([p for p, _ in messages], [0, 20, 40, 60, 80, 100])
        self.assertFalse(any("Paused" in text for _, text in messages))
        for scanner in self.scanners.values():
            scanner.assert_called_once()
        self.detector.assert_not_called()

    def test_cancel_before_scan_still_stops_before_launcher_reads(self):
        from gg_desktop.backend import scan_inventory, ScanCanceled
        with self.assertRaises(ScanCanceled):
            scan_inventory({}, lambda: True)
        self.scanners["find_games"].assert_not_called()
        self.detector.assert_not_called()

    def test_cancel_during_traversal_still_stops_scan(self):
        from gg_desktop.backend import scan_inventory
        canceled = [False]
        def cancel_inside_scan(*args, cancel, **kwargs):
            canceled[0] = True
            self.assertTrue(cancel())
            raise InterruptedError("Scan canceled during traversal")
        self.scanners["find_games"].side_effect = cancel_inside_scan
        with self.assertRaises(InterruptedError):
            scan_inventory({}, lambda: canceled[0])
        self.scanners["find_launcher_games"].assert_not_called()
        self.detector.assert_not_called()

    @unittest.skipUnless(importlib.util.find_spec("PySide6"), "Optional Qt dependency")
    def test_requested_mod_scans_are_not_blocked_by_game_detection(self):
        from gg_desktop.game_dna_tools import run_ghost_watch
        for patch_only in (False, True):
            with self.subTest(patch_only=patch_only):
                window = SimpleNamespace(scanning=False, cleaning=False,
                    inventory=SimpleNamespace(scanned_at="Fixture", mods=[]),
                    info=Mock(), job=Mock())
                with patch("game_intelligence.load_observation", return_value={"entries": {}}):
                    run_ghost_watch(window, patch_only=patch_only)
                window.job.assert_called_once()
                window.info.assert_not_called()
        self.detector.assert_not_called()


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
