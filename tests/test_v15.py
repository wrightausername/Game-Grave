from __future__ import annotations
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

import core
import insights
import launchers
import ecosystems
import recovery
import explainer


class ExpansionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_mod_ecosystems_are_read_only_and_protected(self):
        home = self.root / 'person'
        app = home / 'AppData' / 'Roaming'
        prism = app / 'PrismLauncher' / 'instances' / 'my-world'
        prism.mkdir(parents=True)
        (prism / 'level.dat').write_bytes(b'world')
        r2 = app / 'r2modmanPlus-local' / 'Risk of Rain 2' / 'profiles'
        r2.mkdir(parents=True)
        (r2 / 'profile.json').write_text('{}')
        env={'APPDATA': str(app), 'LOCALAPPDATA': str(home / 'AppData' / 'Local')}
        result=ecosystems.find_ecosystem_storage(home=home, env=env)
        self.assertEqual({x.source for x in result}, {'Prism Launcher', 'r2modman'})
        self.assertTrue((prism / 'level.dat').exists())
        self.assertTrue(any('protected' in x.status for x in result))

    def test_steam_staging_detects_but_does_not_mark_safe(self):
        steam = self.root / 'Steam'
        cache = steam / 'steamapps' / 'shadercache' / '1234'
        cache.mkdir(parents=True)
        (cache / 'blob').write_bytes(b'1234')
        with patch('core._steam_roots', return_value=[steam]), patch('core.steam_libraries', return_value=[steam]):
            result = ecosystems.find_steam_staging()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].source, 'Steam shader cache')
        self.assertIn('regenerates', result[0].status)
        self.assertTrue((cache / 'blob').exists())

    def test_epic_manifests_and_missing_installation(self):
        prog=self.root / 'ProgramData'
        manifests=prog / 'Epic' / 'EpicGamesLauncher' / 'Data' / 'Manifests'
        manifests.mkdir(parents=True)
        install=self.root / 'Games' / 'Control'
        install.mkdir(parents=True)
        (manifests / 'control.item').write_text(json.dumps({'DisplayName':'Control','AppName':'ControlGame',
                                                            'InstallLocation':str(install),'InstallSize':10000}))
        (manifests / 'gone.item').write_text(json.dumps({'DisplayName':'Deleted Game','AppName':'Gone',
                                                         'InstallLocation':str(self.root/'missing')}))
        result=launchers.epic_games(prog)
        self.assertEqual([x.name for x in result],['Control'])
        self.assertEqual(result[0].reported_bytes,10000)

    def test_custom_folders_never_called_orphan(self):
        library=self.root / 'Custom Games'
        (library / 'Game A').mkdir(parents=True)
        result=launchers.custom_library_folders([str(library)])
        self.assertIn('not verified',result[0].status)

    def test_prevent_saved_mod_workshop_folders_from_recycling(self):
        self.assertTrue(core.is_protected_path(self.root / 'steamapps' / 'common' / 'game' / 'notes.log'))
        self.assertTrue(core.is_protected_path(self.root / 'Minecraft' / 'worlds' / 'world1' / 'level.dat'))
        self.assertTrue(core.is_protected_path(self.root / 'games' / 'mods' / 'modfile.zip'))
        self.assertTrue(core.is_protected_path(self.root / 'Downloads' / 'file.tmp', [str(self.root / 'Downloads')]))
        self.assertFalse(core.is_protected_path(self.root / 'Downloads' / 'file.tmp', [str(self.root / 'Documents')]))

    def test_explain_folder_is_non_destructive(self):
        folder = self.root / 'SomeGame'
        (folder / 'BepInEx').mkdir(parents=True)
        (folder / 'BepInEx' / 'my.dll').write_bytes(b'a'*32)
        result=explainer.explain_folder(folder)
        self.assertIn('Possible mod signatures',result)
        self.assertTrue((folder / 'BepInEx' / 'my.dll').exists())

    def test_history_and_plan_never_claim_confirmed_space(self):
        games=[SimpleNamespace(size=1024, install_path=str(self.root))]
        mods=[SimpleNamespace(source='Vortex',apparent_bytes=1024),SimpleNamespace(source='Vortex',apparent_bytes=1024)]
        old=[SimpleNamespace(size=1024)]
        with patch.object(insights, 'config_dir', return_value=self.root):
            point=insights.record_scan(games, mods, old, str(self.root), [self.root])
            self.assertEqual(point['mod_sources']['Vortex']['count'],2)
            self.assertEqual(len(insights.load_history()),1)
            self.assertEqual(len(insights.compare_scans(insights.load_history())),1)
            insights.record_scan(games, mods, old, str(self.root), [self.root])
            self.assertEqual(len(insights.load_history()),2)
        plan=insights.make_room_plan(200*1024**3,games,mods,old)
        self.assertEqual(plan['verified_reclaimable'],0)
        self.assertIsNone(plan['options'][2]['apparent_bytes'])

    def test_recovery_register_only_and_windows_checks_disabled_off_windows(self):
        with patch.object(recovery,'config_dir',return_value=self.root):
            event_id=recovery.register_recycle(self.root / 'sample.tmp',12)
            self.assertEqual(recovery.get_records()[0]['id'],event_id)
            self.assertEqual(recovery.get_records()[0]['state'],'Not checked')
            if os.name!='nt':
                with self.assertRaises(RuntimeError):
                    recovery.check_restore(event_id)
        self.assertIn('AMBIGUOUS',recovery._bin_script('C:/test.txt'))
        self.assertIn('UNVERIFIED',recovery._bin_script('C:/test.txt',True))

    def test_no_scans_or_deletion_on_import(self):
        self.assertFalse(core.default_settings()['auto_enabled'])
        self.assertFalse(core.default_settings()['scan_on_launch'])
        self.assertEqual(core.default_settings()['ui_layout'],'simple')


if __name__ == '__main__':
    unittest.main()

class SaveVaultTests(unittest.TestCase):
    def test_save_backup_verified_and_non_destructive(self):
        import save_vault
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            source=root/'Games'/'My Game'/'saves'
            source.mkdir(parents=True)
            (source/'progress.dat').write_bytes(b'my save')
            target=root/'my_backup.zip'
            result=save_vault.create_backup(source,target)
            self.assertTrue(result['verified'])
            self.assertTrue(target.is_file())
            import zipfile
            with zipfile.ZipFile(target) as z:
                self.assertEqual(z.read('progress.dat'),b'my save')
            self.assertEqual((source/'progress.dat').read_bytes(),b'my save')
            with self.assertRaises(FileExistsError):
                save_vault.create_backup(source,target)

    def test_save_backup_rejects_destination_inside_source(self):
        import save_vault
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'world'
            source.mkdir()
            (source/'level.dat').write_bytes(b'world')
            with self.assertRaises(ValueError):
                save_vault.create_backup(source,source/'bad.zip')
