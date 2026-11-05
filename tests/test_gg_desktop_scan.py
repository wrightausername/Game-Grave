"""Read-only scan regression fixtures, including real asynchronous Qt delivery."""
from __future__ import annotations

from contextlib import ExitStack
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import core
import launchers
from gg_desktop.backend import scan_inventory


def steam_install(root, app_id, title):
    apps = root / "steamapps"
    (apps / "common" / title).mkdir(parents=True, exist_ok=True)
    (apps / f"appmanifest_{app_id}.acf").write_text(
        '"AppState" { "appid" "' + app_id + '" "name" "' + title +
        '" "installdir" "' + title + '" "StateFlags" "4" "SizeOnDisk" "123" }')


def xbox_install(root, executable="game.exe"):
    content = root / "XboxGames" / "Xbox Fixture" / "Content"
    content.mkdir(parents=True, exist_ok=True)
    (content / "MicrosoftGame.config").write_text(
        '<Game><Identity Name="Fixture.Xbox"/><ShellVisuals DefaultDisplayName="Xbox Fixture"/>'
        '<ExecutableList><Executable Name="' + executable + '"/></ExecutableList></Game>')
    (content / "game.exe").write_bytes(b"DISPOSABLE FIXTURE - NOT AN EXECUTABLE")
    return content


class ScanFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="GG-Scan-Fixture-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, {
            "LOCALAPPDATA": str(self.root / "Local"), "APPDATA": str(self.root / "Roaming"),
            "PROGRAMDATA": str(self.root / "ProgramData"),
            "PROGRAMFILES": str(self.root / "Programs"), "PROGRAMFILES(X86)": str(self.root / "Programs32")}))
        self.stack.enter_context(patch("core.windows_fixed_drives", return_value=[self.root / "DriveC", self.root / "DriveD"]))
        # Registry fixture tests below cover these providers separately. Never read a host's registry here.
        for provider in ("gog_registry", "vendor_registry_games", "blizzard_uninstall_records"):
            self.stack.enter_context(patch("launchers." + provider, return_value=[]))
        self.settings = core.default_settings()
        self.settings.update(scan_on_launch=False, scan_folder=str(self.root / "Downloads"),
                             screenshot_roots=[str(self.root / "Captures")], recording_roots=[str(self.root / "Captures")])
        Path(self.settings["scan_folder"]).mkdir()
        self.steam = self.root / "DriveC" / "Steam"
        self.second = self.root / "DriveD" / "SteamLibrary"
        steam_install(self.steam, "123", "Steam First")
        steam_install(self.second, "456", "Steam Second")
        epic = self.root / "Epic" / "Epic Fixture"
        epic.mkdir(parents=True)
        manifest = self.root / "ProgramData/Epic/EpicGamesLauncher/Data/Manifests/fixture.item"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({"DisplayName": "Epic Fixture", "AppName": "fixture", "InstallLocation": str(epic)}))
        self.xbox = xbox_install(self.root / "DriveD")
        captures = self.root / "Captures"
        captures.mkdir()
        (captures / "today.png").write_bytes(b"METADATA ONLY - not decoded during scan")
        (captures / "today.mp4").write_bytes(b"METADATA ONLY - not decoded during scan")
        self.stack.enter_context(patch("recordings.default_recording_roots", return_value=[]))
        self.stack.enter_context(patch("screenshots.default_screenshot_roots", return_value=[]))
        self.stack.enter_context(patch("save_discovery.discover_saves", return_value=[]))


class ScanTests(ScanFixture, unittest.TestCase):
    def test_scan_discovers_second_drive_epic_xbox_and_recent_captures(self):
        stages = []
        result = scan_inventory(self.settings, lambda: False, lambda p, s: stages.append((p, s)))
        self.assertEqual({g.name for g in result.games}, {"Steam First", "Steam Second", "Epic Fixture", "Xbox Fixture"})
        self.assertEqual(len(result.screenshots), 1)
        self.assertEqual(len(result.recordings), 1)
        self.assertFalse(any(Path(x.path).name == "today.png" for x in result.graveyard))
        self.assertEqual(result.files, [])
        steam_report = next(r for r in result.source_reports if r["source"] == "Steam")
        self.assertEqual(set(steam_report["paths"]), {str(self.steam), str(self.second)})
        self.assertEqual(stages[-1][0], 100)
        self.assertTrue(self.xbox.joinpath("game.exe").is_file())

    def test_mod_source_failure_preserves_games_and_reports_partial_coverage(self):
        with patch("gg_desktop.backend.find_all_mod_storage", side_effect=PermissionError("Fixture unavailable")):
            result = scan_inventory(self.settings, lambda: False)
        self.assertEqual(len(result.games), 4)
        self.assertTrue(any("Mod Radar" in warning for warning in result.warnings))
        self.assertEqual(next(r["status"] for r in result.source_reports if r["source"] == "Mod Radar"), "Unavailable")
        self.assertTrue(result.scanned_at)

    def test_one_launcher_failure_keeps_other_launcher_games(self):
        with patch("launchers.gog_registry", side_effect=PermissionError("Fixture registry unavailable")):
            result = scan_inventory(self.settings, lambda: False)
        self.assertEqual(len(result.games), 4)
        self.assertTrue(any("GOG" in warning for warning in result.warnings))

    def test_two_installs_of_same_steam_id_are_both_kept(self):
        steam_install(self.second, "123", "Steam Other Copy")
        games = core.find_games()
        self.assertEqual(sum(g.app_id == "123" for g in games), 2)
        self.assertEqual(len(games), 3)

    def test_explicit_steamapps_folder_normalizes_to_library(self):
        self.assertIn(self.second, core._steam_roots([str(self.second / "steamapps")]))

    def test_recent_capture_inventory_does_not_change_old_only_defaults(self):
        from screenshots import find_old_screenshots
        from recordings import find_old_recordings
        roots = [str(self.root / "Captures")]
        self.assertEqual(find_old_screenshots(180, roots, steam_roots=[]), [])
        self.assertEqual(find_old_recordings(180, roots), [])
        self.assertEqual(len(find_old_screenshots(180, roots, steam_roots=[], include_recent=True)), 1)
        self.assertEqual(len(find_old_recordings(180, roots, include_recent=True)), 1)

    def test_xbox_requires_existing_registered_executable(self):
        self.xbox.joinpath("game.exe").unlink()
        self.assertEqual(launchers.xbox_games(), [])
        xbox_install(self.root / "DriveD", "../outside.exe")
        self.assertEqual(launchers.xbox_games(), [])

    def test_xbox_library_is_not_counted_twice_as_custom_folder(self):
        games = launchers.find_launcher_games([str(self.xbox.parent.parent)])
        self.assertEqual([g.name for g in games if "Xbox" in g.name], ["Xbox Fixture"])


class RegistryTests(unittest.TestCase):
    def test_modern_ea_and_rockstar_all_registry_views_skip_unreadable_entry(self):
        class Key:
            def __init__(self, path, view): self.path, self.view = path, view
            def __enter__(self): return self
            def __exit__(self, *args): pass
        with tempfile.TemporaryDirectory(prefix="GG-Registry-Fixture-") as temp:
            root = Path(temp)
            ea, rockstar = root / "EA Game", root / "Rockstar Game"
            ea.mkdir(); rockstar.mkdir()
            def open_key(hive, path, reserved=0, access=0):
                if isinstance(hive, Key):
                    if path == "Unreadable": raise PermissionError("Fixture inaccessible")
                    return Key(hive.path + "\\" + path, hive.view)
                if path not in (r"SOFTWARE\EA Games", r"SOFTWARE\Rockstar Games"):
                    raise FileNotFoundError(path)
                return Key(path, access)
            def enum_key(parent, i):
                if i == 0: return "Unreadable"
                if i == 1: return "Modern Game"
                raise OSError("end")
            def query(key, name):
                if key.path.startswith(r"SOFTWARE\EA Games") and name == "Install Dir": return str(ea), 1
                if key.path.startswith(r"SOFTWARE\Rockstar Games") and name == "InstallFolder": return str(rockstar), 1
                if name == "DisplayName": return key.path.split("\\")[1] + " Fixture", 1
                raise FileNotFoundError(name)
            registry = SimpleNamespace(HKEY_LOCAL_MACHINE=1, HKEY_CURRENT_USER=2, KEY_READ=1,
                KEY_WOW64_64KEY=256, KEY_WOW64_32KEY=512, OpenKey=open_key, EnumKey=enum_key, QueryValueEx=query)
            with patch.dict("sys.modules", winreg=registry), patch.object(launchers, "os", SimpleNamespace(name="nt")):
                games = launchers.vendor_registry_games()
            self.assertEqual({g.launcher for g in games}, {"EA", "Rockstar Games"})
            self.assertEqual({g.install_path for g in games}, {str(ea), str(rockstar)})


HAS_QT = importlib.util.find_spec("PySide6") is not None


@unittest.skipUnless(HAS_QT, "Optional Qt preview dependencies not installed")
class OverviewScanTests(ScanFixture, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != "nt": os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        from gg_desktop.app import CrimsonWindow
        with patch("gg_desktop.app.load_settings", return_value=self.settings):
            self.window = CrimsonWindow()
        self.window.show()
        self.app.processEvents()
        self.addCleanup(self.close_window)

    def close_window(self):
        self.window.cancel.set()
        self.window.pool.waitForDone(10000)
        for _ in range(5): self.app.processEvents()
        self.window.scanning = self.window.cleaning = False
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def wait_until(self, predicate):
        deadline = time.monotonic() + 10
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            # QTest.qWait can retain the Python GIL on native Windows and
            # starve QRunnable's Python scanner. Release it as app.exec does.
            time.sleep(.01)
        self.assertTrue(predicate(), "Timed out waiting for native Qt worker: " + self.window.status.text())

    def test_overview_scan_button_and_metrics_are_visible_without_scrolling(self):
        from PySide6.QtCore import QPoint, QRect
        from PySide6.QtWidgets import QLabel
        for width, height in ((1280, 720), (1366, 768), (1672, 941), (960, 650)):
            self.window.resize(width, height)
            self.window.navigate("Overview")
            for _ in range(5): self.app.processEvents()
            with self.subTest(width=width):
                hero = self.window.overview_hero.scan
                bounds = QRect(hero.mapTo(self.window, QPoint()), hero.size())
                self.assertTrue(self.window.rect().contains(bounds))
                self.assertTrue(hero.isVisible() and hero.isEnabled())
                self.assertEqual(hero.text(), "Scan PC")
                self.assertEqual(self.window.scan_button.text(), "Scan PC")
                self.assertLessEqual(self.window.page.body.width(), self.window.page.viewport().width())
                for metric in self.window.findChildren(QLabel, "overviewMetricValue"):
                    self.assertGreaterEqual(metric.height(), 24)

    def test_click_scan_uses_real_libraries_and_delivers_results_on_ui_thread(self):
        from PySide6.QtCore import QThread
        wrong_threads = []
        set_text = self.window.status.setText
        def observed(text):
            wrong_threads.append(QThread.currentThread() != self.app.thread())
            set_text(text)
        self.stack.enter_context(patch.object(self.window.status, "setText", side_effect=observed))
        self.window.overview_hero.scan.click()
        self.assertTrue(self.window.scanning)
        self.assertFalse(self.window.overview_hero.scan.isEnabled())
        self.wait_until(lambda: not self.window.scanning)
        self.assertEqual(len(self.window.inventory.games), 4)
        self.assertEqual(self.window.overview_library.count(), 4)
        self.assertIn("4 game installs", self.window.overview_scan_status.text())
        self.assertTrue(self.window.overview_hero.scan.isEnabled())
        self.assertFalse(any(wrong_threads))
        self.assertEqual(self.window.workers, {})

    def test_cancel_keeps_previous_inventory_and_recovers_buttons_after_navigation(self):
        entered, release = threading.Event(), threading.Event()
        def pause(*args, **kwargs):
            entered.set()
            release.wait(10)
            return []
        previous = self.window.inventory
        with patch("gg_desktop.backend.find_all_mod_storage", side_effect=pause):
            self.window.start_scan()
            self.wait_until(entered.is_set)
            self.window.navigate("Games")
            self.window.navigate("Overview")
            self.assertFalse(self.window.overview_hero.scan.isEnabled())
            self.window.overview_cancel.click()
            release.set()
            self.wait_until(lambda: not self.window.scanning)
        self.assertIs(self.window.inventory, previous)
        self.assertIn("canceled", self.window.overview_scan_status.text())
        self.assertTrue(self.window.scan_button.isEnabled())

    def test_scan_locations_can_add_previously_unknown_steam_library(self):
        root = self.root / "UnusualGamesFolder"
        steam_install(root, "789", "Previously Missing")
        pending = {"steam_extra_roots": []}
        self.window._add_scan_location("steam_extra_roots", str(root / "steamapps"), pending, lambda: None)
        self.window.settings.update(pending)
        self.window.start_scan()
        self.wait_until(lambda: not self.window.scanning)
        self.assertIn("Previously Missing", [g.name for g in self.window.inventory.games])


if __name__ == "__main__":
    unittest.main()
