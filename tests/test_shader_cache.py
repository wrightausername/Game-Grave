"""Regression checks for per-game shader cleanup boundaries."""
import tempfile
import unittest
from pathlib import Path
from core import SteamGame
from shader_cache import inspect_steam_shader_cache, file_still_matches


class ShaderCacheTests(unittest.TestCase):
    def sample(self, base, app_id='123'):
        lib=Path(base) / 'SteamLibrary'
        apps=lib/'steamapps'
        (apps/'common'/'My Game').mkdir(parents=True)
        target=apps/'shadercache'/app_id
        target.mkdir(parents=True)
        (apps/f'appmanifest_{app_id}.acf').write_text(
            f'"AppState" {{ "appid" "{app_id}" "name" "My Game" "installdir" "My Game" "StateFlags" "4" }}')
        game=SteamGame(app_id, 'My Game', str(lib), str(apps/'common'/'My Game'),100,None,'Unknown')
        return game,target

    def test_installed_game_cache_only_and_unmodified(self):
        with tempfile.TemporaryDirectory() as d:
            game,cache=self.sample(d)
            file=cache/'abc.cache'
            file.write_bytes(b'123')
            (cache/'x').mkdir()
            (cache/'x'/'more.bin').write_bytes(b'5678')
            discovered=inspect_steam_shader_cache(game)
            self.assertEqual(discovered.bytes_total, 7)
            self.assertEqual(len(discovered.files), 2)
            self.assertTrue(all(file_still_matches(discovered, f) for f in discovered.files))
            self.assertTrue(file.exists())

    def test_missing_manifest_or_uninstalled_game_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            game,cache=self.sample(d)
            (cache/'a.bin').write_bytes(b'1')
            (Path(game.library)/'steamapps'/'appmanifest_123.acf').unlink()
            self.assertIsNone(inspect_steam_shader_cache(game))

    def test_changed_file_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            game,cache=self.sample(d)
            p=cache/'abc.cache'
            p.write_bytes(b'abc')
            result=inspect_steam_shader_cache(game)
            p.write_bytes(b'different')
            self.assertFalse(file_still_matches(result,result.files[0]))

    def test_untrusted_folder_and_symlink_not_followed(self):
        with tempfile.TemporaryDirectory() as d:
            game,cache=self.sample(d)
            elsewhere=Path(d)/'outside';elsewhere.mkdir()
            (elsewhere/'personal.txt').write_text('do not touch')
            try:
                (cache/'linked').symlink_to(elsewhere,target_is_directory=True)
            except (OSError, NotImplementedError):
                pass
            result=inspect_steam_shader_cache(game)
            self.assertEqual(result.bytes_total,0)
            self.assertTrue((elsewhere/'personal.txt').exists())
            self.assertGreaterEqual(result.skipped,0)

    def test_path_cannot_escape_its_installed_game_or_match_different_id(self):
        with tempfile.TemporaryDirectory() as d:
            game,cache=self.sample(d)
            bad=SteamGame('124', 'Other', game.library, game.install_path,0,None,'Unknown')
            self.assertIsNone(inspect_steam_shader_cache(bad))
            wrong=SteamGame('123', 'Other', game.library, str(Path(d)/'wrong'),0,None,'Unknown')
            self.assertIsNone(inspect_steam_shader_cache(wrong))

if __name__ == '__main__': unittest.main()
