"""All tests operate on synthetic game files; never touch users' libraries."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import core
import mod_sources


class IntegratedModSourcesTests(unittest.TestCase):
    def test_steam_workshop_and_unindexed_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'Steam'
            apps = root / 'steamapps'
            apps.mkdir(parents=True)
            (apps / 'common' / 'Game').mkdir(parents=True)
            (apps / 'appmanifest_123.acf').write_text(
                '"AppState" { "appid" "123" "installdir" "Game" "name" "Game" "StateFlags" "4" }')
            content = apps / 'workshop' / 'content'
            (content / '123' / '456').mkdir(parents=True)
            (content / '123' / '456' / 'workshop.mod').write_bytes(b'x' * 17)
            (content / '123' / '789').mkdir()
            (content / '123' / '789' / 'orphan.dat').write_bytes(b'y' * 20)
            (content / '999' / '222').mkdir(parents=True)
            (content / '999' / '222' / 'addon.bin').write_bytes(b'a' * 5)
            (apps / 'workshop' / 'appworkshop_123.acf').write_text(
                '"AppWorkshop" { "appid" "123" "WorkshopItemsInstalled" { "456" { "size" "17" } } }')
            with patch.object(core, '_steam_roots', return_value=[root]):
                # mod_sources keeps a reference to the same _steam_roots function;
                # patch the imported symbol as well, to control discovery.
                with patch.object(mod_sources, '_steam_roots', return_value=[root]):
                    games = core.find_games()
                    findings = core.find_all_mod_storage(games=games)
            workshop = {f.name: f for f in findings if f.source == 'Steam Workshop'}
            self.assertEqual(workshop['Game'].apparent_bytes, 37)
            self.assertEqual(workshop['Game'].item_count, 2)
            self.assertIn('1 not in local manifest', workshop['Game'].indicators)
            self.assertIn('does not prove', workshop['Game'].advice)
            self.assertEqual(workshop['Steam app 999'].status, 'Workshop: no installed-game record')
            self.assertTrue((content / '123' / '789' / 'orphan.dat').exists())

    def test_vortex_default_staging_archives_are_reported_but_not_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'Vortex'
            (root / 'skyrimse' / 'mods' / 'USSEP').mkdir(parents=True)
            (root / 'skyrimse' / 'mods' / 'USSEP' / 'mod.esp').write_bytes(b'x' * 128)
            (root / 'downloads' / 'skyrimse').mkdir(parents=True)
            (root / 'downloads' / 'skyrimse' / 'archive.7z').write_bytes(b'y' * 512)
            with patch.dict(os.environ, {'APPDATA': tmp, 'LOCALAPPDATA': str(Path(tmp) / 'empty'),
                                         'PROGRAMDATA': str(Path(tmp) / 'nope')}):
                rows = mod_sources.find_external_mod_storage(None, [str(root)], [], None)
            stages = [f for f in rows if f.status == 'Vortex: mod staging']
            downloads = [f for f in rows if f.status == 'Vortex: downloaded archives']
            self.assertEqual(stages[0].apparent_bytes, 128)
            self.assertEqual(stages[0].item_count, 1)
            self.assertIn('hardlinks', stages[0].advice)
            self.assertEqual(downloads[0].apparent_bytes, 512)
            self.assertTrue((root / 'downloads' / 'skyrimse' / 'archive.7z').exists())

    def test_mo2_custom_paths_and_protected_profiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'ModOrganizer' / 'Starfield'
            root.mkdir(parents=True)
            separated = Path(tmp) / 'second-drive' / 'MO2_Data'
            (separated / 'mods' / 'SFSE').mkdir(parents=True)
            (separated / 'mods' / 'SFSE' / 'sfse_plugin.dll').write_bytes(b'm' * 97)
            (separated / 'archives').mkdir()
            (separated / 'archives' / 'mod.zip').write_bytes(b'j' * 99)
            (separated / 'profiles' / 'Default').mkdir(parents=True)
            (separated / 'profiles' / 'Default' / 'saves.dat').write_bytes(b'keep')
            (separated / 'overwrite').mkdir()
            (root / 'ModOrganizer.ini').write_text(
                '[Settings]\nbase_directory=' + str(separated) + '\n' +
                'mod_directory=%BASE_DIR%/mods\n' +
                'download_directory=%BASE_DIR%/archives\n' +
                'profiles_directory=%BASE_DIR%/profiles\n' +
                'overwrite_directory=%BASE_DIR%/overwrite\n', encoding='utf-8')
            rows = mod_sources._mo2(root.parent, None)
            categories = {f.status: f for f in rows}
            self.assertEqual(categories['MO2: installed mods'].item_count, 1)
            self.assertEqual(categories['MO2: downloads'].apparent_bytes, 99)
            self.assertEqual(categories['MO2: profiles / saves protected'].apparent_bytes, 4)
            self.assertIn('saves', categories['MO2: profiles / saves protected'].advice)
            self.assertTrue((separated / 'profiles' / 'Default' / 'saves.dat').exists())

    def test_custom_paths_not_any_drive_root_and_junctions_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            here = Path(tmp)
            self.assertFalse(mod_sources._safe_folder(Path(here.anchor)))
            self.assertFalse(mod_sources._safe_folder(Path.home()))
            target = here / 'other'
            target.mkdir()
            (target / 'large.bin').write_bytes(b'x' * 1000)
            custom = here / 'custom-mods'
            custom.mkdir()
            (custom / 'a.bin').write_bytes(b'a' * 4)
            try:
                (custom / 'linked').symlink_to(target, target_is_directory=True)
            except (NotImplementedError, OSError):
                pass
            rows = mod_sources._classify_extra(custom, None)
            self.assertEqual(rows[0].apparent_bytes, 4)
            self.assertEqual(rows[0].source, 'Custom mod storage')

    def test_workshop_partials_are_not_called_unused(self):
        with tempfile.TemporaryDirectory() as tmp:
            steam = Path(tmp) / 'Steam'
            (steam / 'steamapps' / 'workshop' / 'downloads' / '1000').mkdir(parents=True)
            (steam / 'steamapps' / 'workshop' / 'downloads' / '1000' / 'pending.dat').write_bytes(b'xxx')
            with patch.object(mod_sources, '_steam_roots', return_value=[steam]):
                rows = mod_sources._workshop(None, [], None)
            self.assertEqual(rows[0].status, 'Workshop: pending/download cache')
            self.assertIn('Do not remove', rows[0].advice)

    def test_cancel_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            vortex = Path(tmp) / 'Vortex'
            (vortex / 'somegame' / 'mods').mkdir(parents=True)
            with self.assertRaises(InterruptedError):
                mod_sources._vortex(vortex, lambda: True)

if __name__ == '__main__':
    unittest.main()
