"""M2 Steam stale/manipulated manifest and workshop provenance regression cases."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import core
from core import SteamGame, ModFolder
from file_detective import investigate
from game_intelligence import build_game_dna


def mod(folder, source):
    return ModFolder("Example mod", str(folder), str(folder.parent), "Review only",
                     (), 10, 1, False, source, "Never infer removal eligibility")


class SteamProvenanceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.steam = self.root / "Steam"
        self.apps = self.steam / "steamapps"
        self.common = self.apps / "common"
        self.common.mkdir(parents=True)

    def _manifest(self, filename_id, appid, install, *, state=4):
        file = self.apps / ("appmanifest_" + str(filename_id) + ".acf")
        file.write_text(
            '"AppState" { "appid" "' + str(appid) +
            '" "name" "Example" "installdir" "' + str(install) +
            '" "StateFlags" "' + str(state) + '" }')
        return file

    def _find(self):
        with patch.object(core, "_steam_roots", return_value=[self.steam]):
            return core.find_games()

    def test_manifest_and_present_ordinary_game_folder_count_as_installed(self):
        (self.common / "Example").mkdir()
        self._manifest(42, 42, "Example")
        result = self._find()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].app_id, "42")
        self.assertEqual(result[0].install_path, str(self.common / "Example"))

    def test_removed_game_with_stale_manifest_not_called_installed(self):
        self._manifest(42, 42, "Deleted Example")
        self.assertEqual(self._find(), [])
        self.assertTrue((self.apps / "appmanifest_42.acf").exists())

    def test_manifest_filename_must_match_appid(self):
        (self.common / "Example").mkdir()
        self._manifest(123, 42, "Example")
        self.assertEqual(self._find(), [])

    def test_manifest_must_not_claim_path_traversal_or_another_drive(self):
        (self.common / "Example").mkdir()
        for bad in ("..", "../Example", r"..\Example", r"C:\Games\Example",
                    r"\\fileserver\example", " Example", "Example ",
                    "Example/Mods"):
            with self.subTest(path=bad):
                current = self._manifest(42, 42, bad)
                self.assertEqual(self._find(), [])
                current.unlink()

    def test_linked_game_root_not_reported_verified_installed(self):
        actual = self.root / "Elsewhere"
        actual.mkdir()
        try:
            (self.common / "Example").symlink_to(actual, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks not available in this test environment")
        self._manifest(42, 42, "Example")
        self.assertEqual(self._find(), [])

    def test_workshop_app_id_without_workshop_scanner_source_is_unverified(self):
        install = self.common / "Example"
        install.mkdir()
        game = SteamGame("42", "Example", str(self.steam), str(install),
                         5, None, "Unknown")
        path = self.apps / "workshop" / "content" / "42"
        path.mkdir(parents=True)
        data = build_game_dna([game], mods=[mod(path, "Vortex")])
        self.assertFalse(data["games"][0]["assets"])
        self.assertEqual(len(data["unresolved"]), 1)
        self.assertTrue(data["unresolved"][0]["protected"])
        workshop = build_game_dna([game], mods=[mod(path, "Steam Workshop")])
        self.assertEqual(len(workshop["games"][0]["assets"]), 1)
        self.assertFalse(workshop["games"][0]["assets"][0]["can_recycle"])

    def test_detective_does_not_associate_a_linked_parent_with_game(self):
        game_root = self.common / "Example"
        (game_root / "Mods").mkdir(parents=True)
        redirect = self.root / "Junction"
        try:
            redirect.symlink_to(game_root, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks not available in this test environment")
        game = SteamGame("42", "Example", str(self.steam), str(game_root),
                         5, None, "Unknown")
        result = investigate(redirect / "Mods" / "some.dll", [game])
        self.assertNotEqual(result.headline, "Part of an installed game")
        self.assertTrue(result.protected)


if __name__ == "__main__":
    unittest.main()
