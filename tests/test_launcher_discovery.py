"""Evidence-based cross-launcher detection and ownership tests.

These create only disposable directories and dummy executable names. No actual
games, Windows registry values, launcher caches, or saves are modified.
"""
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from game_signatures import identify_game_install
from launchers import (
    _rockstar_install, custom_library_folders, find_launcher_games,
    LauncherGame,
)
from gg_desktop.models import merge_games


class InstallEvidenceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def make_game(self, folder, relative):
        target = self.root / folder / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"not a real game executable")
        return target

    def test_rockstar_rdr2_from_verified_executable(self):
        self.make_game("Rockstar/Red Dead Redemption 2", "RDR2.exe")
        game = _rockstar_install(
            str(self.root / "Rockstar/Red Dead Redemption 2"),
            evidence="Rockstar product registry InstallFolder")
        self.assertIsNotNone(game)
        self.assertEqual(game.name, "Red Dead Redemption 2")
        self.assertEqual(game.launcher, "Rockstar Games")
        self.assertIn("RDR2.exe", game.status)
        self.assertIn("entitlement/playability not checked", game.status)

    def test_missing_game_exe_never_claims_installed(self):
        install = self.root / "Rockstar/Red Dead Redemption 2"
        install.mkdir(parents=True)
        self.assertIsNone(
            _rockstar_install(str(install), evidence="registry"))
        self.assertIsNone(identify_game_install(install))

    def test_rockstar_reg_path_does_not_claim_unrelated_game(self):
        self.make_game("Other", "Starfield.exe")
        self.assertIsNone(_rockstar_install(str(self.root / "Other"),
                                            evidence="registry"))

    def test_custom_root_can_be_a_game_root_or_parent(self):
        self.make_game("Red Dead Redemption 2", "PlayRDR2.exe")
        self.make_game("Cyberpunk 2077", "bin/x64/Cyberpunk2077.exe")
        unknown = self.root / "Empty Folder"
        unknown.mkdir()
        result = custom_library_folders([str(self.root)])
        names = {game.name for game in result}
        self.assertIn("Red Dead Redemption 2", names)
        self.assertIn("Cyberpunk 2077", names)
        self.assertIn("Empty Folder", names)
        rdr = next(x for x in result if x.name == "Red Dead Redemption 2")
        self.assertEqual(rdr.launcher, "Local game files")
        self.assertIn("license/launcher unknown", rdr.status)
        single = custom_library_folders([str(self.root / "Red Dead Redemption 2")])
        self.assertEqual(len(single), 1)
        self.assertEqual(single[0].name, "Red Dead Redemption 2")

    def test_does_not_recurse_deep_unknown_folders(self):
        self.make_game("Nested/Extra/Red Dead Redemption 2", "RDR2.exe")
        found = custom_library_folders([str(self.root)])
        self.assertFalse(any(x.name == "Red Dead Redemption 2" for x in found))

    def test_linked_executable_does_not_confirm_install(self):
        valid = self.make_game("Actual", "RDR2.exe")
        linked_dir = self.root / "Linked Game"
        linked_dir.mkdir()
        try:
            (linked_dir / "RDR2.exe").symlink_to(valid)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks unavailable in this environment")
        self.assertIsNone(identify_game_install(linked_dir))

    def test_custom_unknown_not_duplicated_if_registry_detected(self):
        self.make_game("Red Dead Redemption 2", "RDR2.exe")
        rockstar = LauncherGame(
            "Red Dead Redemption 2", "Rockstar Games",
            str(self.root / "Red Dead Redemption 2"), "RDR2.exe",
            None, "Rockstar registry record and game executable")
        with ExitStack() as stack:
            for func in (
                "epic_games", "gog_registry", "riot_games",
                "vendor_registry_games", "blizzard_uninstall_records",
                "rockstar_common_folders", "known_publisher_uninstall_games",
            ):
                stack.enter_context(patch("launchers." + func, return_value=[]))
            stack.enter_context(
                patch("launchers.rockstar_registry_games", return_value=[rockstar]))
            found = find_launcher_games([str(self.root)])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].launcher, "Rockstar Games")

    def test_steam_rdr2_and_rockstar_registry_count_once(self):
        path = str(self.root / "Red Dead Redemption 2")
        steam = [SimpleNamespace(
            app_id="1174180", name="Red Dead Redemption 2",
            install_path=path, size=180, last_played=None,
            source="Steam install record")]
        rockstar = [LauncherGame(
            "Red Dead Redemption 2", "Rockstar Games", path,
            "RDR2.exe", None, "Rockstar registry executable evidence")]
        games = merge_games(steam, rockstar)
        self.assertEqual(len(games), 1)
        self.assertEqual(games[0].launcher, "Steam")
        self.assertIn("Rockstar", games[0].install_evidence)
        self.assertIn("steam_uninstall", games[0].capabilities)


if __name__ == "__main__":
    unittest.main()
