"""File Detective: an association is NOT permission to delete anything."""
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core import ModFolder, OldFile, SteamGame
from file_detective import investigate, friendly_report
from space_planner import plan_for_drive, same_volume


class DetectiveTests(unittest.TestCase):
    def test_installed_game_association_and_path_prefix_not_confused(self):
        with tempfile.TemporaryDirectory() as d:
            game_dir = Path(d)/'Game'
            game_dir.mkdir()
            game = SteamGame('33', 'Game', str(Path(d)), str(game_dir), 100, None, 'Steam')
            inside = investigate(game_dir/'Data'/'mods', [game])
            self.assertEqual(inside.headline, 'Part of an installed game')
            self.assertTrue(inside.protected)
            self.assertIn('Keep it', inside.next_step)
            outside = investigate(Path(d)/'GameTwo'/'Data'/'mods', [game])
            self.assertNotEqual(outside.headline, 'Part of an installed game')

    def test_manager_profile_protected_even_when_game_not_installed(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)/'MO2'/'profiles'
            folder.mkdir(parents=True)
            mod = ModFolder('profiles', str(folder), d, 'Profiles', ('profile.ini',), 100, 5,
                            False, 'Mod Organizer 2', 'Use MO2 first')
            found = investigate(folder/'MyProfile', mods=[mod])
            self.assertEqual(found.headline, 'Mod or addon storage found')
            self.assertTrue(found.protected)
            self.assertIn('Mod Organizer 2', found.evidence[0])

    def test_name_match_is_never_confirmed_ownership(self):
        with tempfile.TemporaryDirectory() as d:
            game = SteamGame('44', 'Skyrim', 'X', str(Path(d)/'installed'), 100, None, 'Unknown')
            verdict = investigate(Path(d)/'Skyrim-backup-2022.zip', games=[game])
            self.assertEqual(verdict.confidence, 'Name match only')
            self.assertTrue(verdict.protected)

    def test_unknown_folder_stays_unknown(self):
        with tempfile.TemporaryDirectory() as d:
            verdict = investigate(Path(d)/'mystery.zip')
            self.assertIn('not confirmed', verdict.headline.lower())
            self.assertIn('No files were changed', friendly_report(verdict, 'mystery.zip'))

    def test_workshop_app_id_not_random_filename(self):
        with tempfile.TemporaryDirectory() as d:
            game = SteamGame('1234', 'Castle Game', d, str(Path(d)/'installed'), 500, None, 'Steam')
            folder = Path(d)/'steamapps'/'workshop'/'content'/'1234'/'item'
            verdict = investigate(folder, games=[game])
            self.assertEqual(verdict.headline, 'Steam Workshop content')
            self.assertTrue(verdict.protected)

    def test_never_touch_always_protected(self):
        with tempfile.TemporaryDirectory() as d:
            verdict = investigate(Path(d)/'test'/'notes.txt', never_touch=[d])
            self.assertEqual(verdict.headline, 'Protected file or folder')


class SpacePlanTests(unittest.TestCase):
    def test_only_explicit_older_game_archive_is_candidate_and_no_delete(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            archive = root/'skyrim-mod-backup.7z'
            archive.write_bytes(b'not a real archive')
            irrelevant = root/'bank-photos.zip'
            irrelevant.write_bytes(b'secrets')
            files = [OldFile(str(archive), archive.stat().st_size, archive.stat().st_mtime),
                     OldFile(str(irrelevant), irrelevant.stat().st_size, irrelevant.stat().st_mtime)]
            result = plan_for_drive(5, root, files, [])
            self.assertEqual([row.name for row in result['candidates']], [archive.name])
            self.assertEqual(result['verified_reclaimable_bytes'], 0)
            self.assertTrue(archive.exists())
            self.assertTrue(irrelevant.exists())

    def test_protected_archive_not_suggested(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d)/'modpack.zip'
            f.write_bytes(b'x')
            result = plan_for_drive(2, d, [OldFile(str(f), 1, f.stat().st_mtime)], [], [d])
            self.assertFalse(result['candidates'])

    def test_changed_archive_ignored_until_rescan(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d)/'modpack.zip'
            f.write_bytes(b'x')
            old = OldFile(str(f), 1, f.stat().st_mtime)
            f.write_bytes(b'new content')
            result = plan_for_drive(3, d, [old], [])
            self.assertEqual(result['candidates'], [])

    def test_hardlinked_archive_counted_once_and_not_guaranteed_saving(self):
        with tempfile.TemporaryDirectory() as d:
            first = Path(d)/'skyrim-mod-1.zip'
            second = Path(d)/'skyrim-mod-2.zip'
            first.write_bytes(b'shared')
            try:
                os.link(first, second)
            except OSError:
                self.skipTest('Hardlinks unsupported on this filesystem')
            files = [OldFile(str(f), f.stat().st_size, f.stat().st_mtime) for f in (first, second)]
            result = plan_for_drive(3, d, files, [])
            self.assertEqual(len(result['candidates']), 1)
            self.assertIn('hardlink', result['candidates'][0].reason)
            self.assertEqual(result['verified_reclaimable_bytes'], 0)

    def test_invalid_goal_raises(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                plan_for_drive(0, d, [], [])

    def test_target_volume_check(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d)/'file.zip'
            f.touch()
            self.assertTrue(same_volume(f, d))


if __name__ == '__main__':
    unittest.main()
