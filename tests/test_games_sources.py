"""Mixed-launcher identity, artwork and registered-install checks."""
from dataclasses import replace
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from gg_desktop.game_artwork import local_artwork, official_artwork
from gg_desktop.models import merge_games
from gg_desktop.games_sources import combine_games, launcher_bucket, registered_games
from launchers import LauncherGame


class Registry:
    HKEY_LOCAL_MACHINE = 1
    HKEY_CURRENT_USER = 2
    KEY_READ = 4
    KEY_WOW64_32KEY = 8
    KEY_WOW64_64KEY = 16

    class Key:
        def __init__(self, value):
            self.value = value
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass

    def __init__(self, games):
        self.games = games
        self.reads = 0

    def OpenKey(self, parent, path, *_):
        self.reads += 1
        if isinstance(parent, self.Key):
            return self.Key(self.games[path])
        if path != r"SOFTWARE\Rockstar Games":
            raise OSError("Key absent")
        return self.Key(self.games)

    def EnumKey(self, parent, index):
        try:
            return list(parent.value)[index]
        except IndexError:
            raise OSError("End")

    def QueryValueEx(self, key, field):
        if field not in key.value:
            raise OSError("Value absent")
        return key.value[field], 1


class GamesSourcesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.install = self.root/"Red Dead Redemption 2"
        self.install.mkdir()
        self.raw = LauncherGame("Red Dead Redemption 2", "Rockstar Games", str(self.install), "rdr2", None, "Registered install")

    def test_supported_brand_counts_and_ambiguous_install(self):
        for value, expected in (("Steam", "Steam"), ("EA app", "EA"), ("Origin", "EA"),
                                ("Epic Games", "Epic"), ("Rockstar Games Launcher", "Rockstar"),
                                ("Ubisoft Connect", "Ubisoft"), ("Blizzard", "Battle.net"),
                                ("Xbox", "Xbox (PC)"), ("GOG", "GOG"), ("Riot", "Other"),
                                ("Steam / Rockstar Games", "Other")):
            with self.subTest(value=value):
                self.assertEqual(launcher_bucket(value), expected)

    def test_registry_both_views_deduplicate_game_and_exclude_launcher(self):
        registry = Registry({"Red Dead Redemption 2": {"InstallFolder": str(self.install)},
                             "Launcher": {"InstallFolder": str(self.install)},
                             "Social Club": {"InstallFolder": str(self.install)},
                             "Missing game": {"InstallFolder": str(self.root/"missing")},
                             "Bad path": {"InstallFolder": ""}})
        found = registered_games(registry=registry)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].name, self.raw.name)
        self.assertEqual(found[0].launcher, "Rockstar Games")
        self.assertEqual(found[0].reported_bytes, None)

    def test_registry_cancellation_retains_no_partial_results(self):
        registry = Registry({"Game": {"InstallFolder": str(self.install)}})
        self.assertEqual(registered_games(registry=registry, canceled=lambda: True), [])
        self.assertEqual(registry.reads, 0)

    def test_registry_does_not_follow_redirected_install(self):
        link = self.root/"redirect"
        try:
            link.symlink_to(self.install, target_is_directory=True)
        except OSError:
            self.skipTest("Symlinks unavailable")
        self.assertEqual(registered_games(registry=Registry({"Game": {"InstallFolder": str(link)}})), [])

    def test_added_sources_preserve_inventory_identity_and_capabilities(self):
        original = merge_games([], [replace(self.raw, launcher="Epic Games", app_id="epic-id")])
        before = list(original)
        combined = combine_games(original, [self.raw, self.raw])
        self.assertEqual(original, before)
        self.assertEqual(combined, original)
        self.assertEqual(combined[0].app_id, "epic-id")

    def test_same_title_different_installations_remain_separate(self):
        other = self.root/"Second"
        other.mkdir()
        combined = combine_games(merge_games([], [self.raw]), [replace(self.raw, install_path=str(other))])
        self.assertEqual(len(combined), 2)

    def test_exact_artwork_works_across_launchers_without_granting_steam_actions(self):
        picture = BytesIO()
        Image.new("RGB", (60, 90), "red").save(picture, "PNG")
        def request(url, _limit):
            if "storesearch" in url:
                return json.dumps({"items": [{"id": 1174180, "name": self.raw.name}]}).encode()
            if "GetItems" in url:
                return json.dumps({"response": {"store_items": [{"appid": 1174180, "name": self.raw.name, "assets": {}}]}}).encode()
            return picture.getvalue()
        with patch("gg_desktop.game_artwork.artwork_dir", return_value=self.root/"Art"):
            for launcher in ("EA", "Rockstar Games", "Epic Games", "Ubisoft Connect", "GOG", "Battle.net", "Xbox", "Riot", "Custom library"):
                with self.subTest(launcher=launcher):
                    game = merge_games([], [replace(self.raw, launcher=launcher)])[0]
                    before = replace(game)
                    self.assertIsNotNone(official_artwork(game, request=request,
                        steam_id="1174180" if launcher == "Custom library" else None).image)
                    self.assertIsNotNone(local_artwork(game).image)
                    self.assertEqual(game, before)
                    self.assertNotIn("steam_uninstall", game.capabilities)

    def test_ambiguous_artwork_matches_are_not_applied(self):
        game = merge_games([], [self.raw])[0]
        payload = json.dumps({"items": [{"id": 1, "name": game.name}, {"id": 2, "name": game.name}]}).encode()
        self.assertIsNone(official_artwork(game, request=lambda *_: payload).image)


if __name__ == "__main__":
    unittest.main()
