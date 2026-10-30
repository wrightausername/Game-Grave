"""v2.1: save discovery, honest progress, safe Graveyard handoff and UI sort."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import SteamGame, ModFolder, default_settings, is_protected_path
from graveyard import build_graveyard
from save_discovery import discover_saves
from scan_progress import STAGES, ScanProgress, eta_seconds, format_eta
from view_options import sort_games
from launchers import riot_games


class SaveDiscoveryTests(unittest.TestCase):
    def test_discovers_known_locations_without_walking_arbitrary_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            test = home / 'Saved Games' / 'Test Game'
            test.mkdir(parents=True)
            (test / 'slot.sav').write_text('save')
            elder = home / 'Documents' / 'Elder Scrolls Online' / 'live' / 'SavedVariables'
            elder.mkdir(parents=True)
            (home / 'Documents' / 'My Games' / 'Skyrim Special Edition').mkdir(parents=True)
            unused = home / 'Downloads' / 'not a save folder'
            unused.mkdir(parents=True)
            records = discover_saves(home, local=home/'AppData'/'Local',
                                     roaming=home/'AppData'/'Roaming')
            paths = {r.path for r in records}
            self.assertIn(str(test.resolve()), paths)
            self.assertIn(str(elder.resolve()), paths)
            self.assertNotIn(str(unused.resolve()), paths)
            self.assertTrue(is_protected_path(test/'slot.sav'))
            self.assertTrue(is_protected_path(home/'Documents'/'My Games'/'Skyrim Special Edition'/'save.ess'))

    def test_symlinks_never_followed_and_nonexistent_not_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home/'Saved Games').mkdir()
            elsewhere = home / 'Elsewhere'
            elsewhere.mkdir()
            try:
                (home / 'Saved Games' / 'Link').symlink_to(elsewhere, target_is_directory=True)
            except OSError:
                pass
            found = discover_saves(home)
            self.assertFalse(any(r.game == 'Link' for r in found))
            self.assertFalse(any(r.game == 'Invented Title' for r in found))


class ProgressTests(unittest.TestCase):
    def test_stage_progress_monotonic_and_finishes_at_100(self):
        self.assertEqual(ScanProgress('start', 0).percent, 0)
        values = [ScanProgress(name, i).percent for i, (name, _) in enumerate(STAGES)]
        self.assertEqual(values, sorted(values))
        self.assertEqual(ScanProgress('done', len(STAGES)).percent, 100)
        self.assertIsNone(eta_seconds(1, 1))
        self.assertIsNotNone(eta_seconds(30, 2))

    def test_time_estimate_is_qualified(self):
        self.assertIn('Rough ETA', format_eta(80))
        self.assertIn('Calculating', format_eta(None))
        self.assertGreaterEqual(eta_seconds(40, 3), 0)


class SortAndGraveyardTests(unittest.TestCase):
    def test_game_column_sort_numeric_and_missing_dates_last(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = [SteamGame('1', 'Beta', tmp, tmp, 300, 1000, 'Local'),
                    SteamGame('2', 'Alpha', tmp, tmp, 10, None, 'Unknown'),
                    SteamGame('3', 'Gamma', tmp, tmp, 500, 2000, 'Steam')]
            self.assertEqual([g.name for g in sort_games(data, 'Name A-Z')], ['Alpha', 'Beta', 'Gamma'])
            self.assertEqual([g.name for g in sort_games(data, 'Largest first')], ['Gamma', 'Beta', 'Alpha'])
            self.assertEqual([g.name for g in sort_games(data, 'Oldest first')], ['Beta', 'Gamma', 'Alpha'])
            self.assertEqual([g.name for g in sort_games(data, 'Date source A-Z')], ['Beta', 'Gamma', 'Alpha'])

    def test_manually_added_mod_appears_for_review_but_never_recyclable(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'some-mod'
            p.mkdir()
            record = ModFolder('Test Mod', str(p), 'Test', 'Managed by active profile', (), 100, 1, False)
            found = build_graveyard([], [record], [], min_days=9999, watched_mods=[str(p)])
            self.assertEqual(len(found), 1)
            self.assertIn('Manually sent', found[0].finding)
            self.assertFalse(found[0].can_recycle)


class OtherLauncherTests(unittest.TestCase):
    def test_riot_only_returns_existing_install_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            programdata=Path(tmp)
            folder=programdata/'Riot Games'/'Metadata'/'valorant'
            folder.mkdir(parents=True)
            target=programdata/'Valorant'
            target.mkdir()
            (folder/'product_settings.yaml').write_text('product_install_full_path: '+str(target)+'\nproduct_display_name: Valorant\n')
            games=riot_games(programdata)
            self.assertEqual(len(games), 1)
            self.assertEqual(games[0].name, 'Valorant')
            (folder/'product_settings.yaml').write_text('product_install_full_path: '+str(programdata/'missing'))
            self.assertEqual(riot_games(programdata), [])


if __name__ == '__main__':
    unittest.main()
