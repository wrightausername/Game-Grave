"""Games filtering/actions and artwork are independent of cleanup authority."""
from __future__ import annotations

from dataclasses import asdict, replace
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from PIL import Image
except ImportError:
    Image = None
from core import SteamGame
from gg_desktop.models import merge_games
from gg_desktop.games_data import chosen_executable, filtered_games, launch_uri, steam_install_current
from gg_desktop.game_artwork import (Artwork, _checked_url, choose_artwork, clear_artwork,
    game_id, image_from_bytes, load_preferences, local_artwork, official_artwork, save_preferences)
from launchers import LauncherGame


def picture(color="crimson", size=(200, 300)):
    raw = BytesIO()
    Image.new("RGB", size, color).save(raw, format="PNG")
    return raw.getvalue()


@unittest.skipUnless(Image is not None, "Optional Games artwork dependency Pillow is not installed")
class GamesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        library = self.root / "Steam"
        install = library / "steamapps" / "common" / "Game"
        install.mkdir(parents=True)
        self.raw = SteamGame("1091500", "Example Game", str(library), str(install), 1024, None, "Unknown")
        self.game = merge_games([self.raw], [])[0]
        self.install = install
        self.manifest = library / "steamapps" / "appmanifest_1091500.acf"
        self.manifest.write_text('"AppState" { "appid" "1091500" "installdir" "Game" "StateFlags" "4" }')
        cache = patch("gg_desktop.game_artwork.artwork_dir", return_value=self.root / "Artwork")
        cache.start()
        self.addCleanup(cache.stop)

    def test_search_is_case_insensitive_multiword_and_does_not_mutate_records(self):
        before = asdict(self.game)
        self.assertEqual(filtered_games([self.game], "EXAMPLE Steam"), [self.game])
        self.assertEqual(filtered_games([self.game], "does not exist"), [])
        self.assertEqual(asdict(self.game), before)

    def test_unknown_sizes_and_dates_stay_after_known_values_in_both_directions(self):
        zero = replace(self.game, key="zero", size_bytes=0, last_played_at=1500000000)
        unknown = replace(self.game, key="unknown", size_bytes=None)
        known = replace(self.game, key="known", size_bytes=5, last_played_at=1600000000)
        for sort in ("Largest known size", "Smallest known size", "Recently played", "Oldest played"):
            self.assertEqual(filtered_games([unknown, zero, known], sort=sort)[-1].key, "unknown")
        self.assertEqual(filtered_games([unknown, zero, known], sort="Smallest known size")[0].key, "zero")

    def test_more_than_500_games_remain_in_the_filtered_model(self):
        records = [replace(self.game, key=str(i), name=f"Game {i:04}") for i in range(1007)]
        self.assertEqual(len(filtered_games(records)), 1007)
        self.assertEqual(filtered_games(records, "1006")[0].key, "1006")

    def test_only_supported_verified_launch_protocols_are_created(self):
        self.assertEqual(launch_uri(self.game), "steam://rungameid/1091500")
        epic = replace(self.game, launcher="Epic Games", app_id="namespace:catalog:app", claimed_by=("Epic Games",))
        self.assertTrue(launch_uri(epic).startswith("com.epicgames.launcher://apps/namespace%3Acatalog%3Aapp"))
        self.assertFalse(launch_uri(replace(epic, app_id="bad?command=evil")))
        self.assertFalse(launch_uri(replace(self.game, capabilities=("inspect",))))
        self.assertFalse(launch_uri(replace(self.game, claimed_by=("Steam", "Epic Games"))))

    def test_steam_launch_and_uninstall_require_current_matching_manifest(self):
        self.assertTrue(steam_install_current(self.game, [self.raw]))
        self.manifest.write_text('"AppState" { "appid" "999" "installdir" "Game" "StateFlags" "4" }')
        self.assertFalse(steam_install_current(self.game, [self.raw]))
        self.manifest.unlink()
        self.assertFalse(steam_install_current(self.game, [self.raw]))

    def test_user_chosen_executable_must_be_inside_the_verified_install(self):
        target = self.install / "Game.exe"
        target.write_bytes(b"MZsynthetic fixture never executed")
        self.assertEqual(chosen_executable(self.game, str(target)), str(target))
        external = self.root / "Other.exe"
        external.write_bytes(b"MZoutside")
        with self.assertRaises(ValueError):
            chosen_executable(self.game, str(external))
        with self.assertRaises(ValueError):
            chosen_executable(replace(self.game, capabilities=("inspect",)), str(target))

    def test_custom_art_survives_restart_and_never_changes_installed_files(self):
        source = self.root / "cover.png"
        raw = picture()
        source.write_bytes(raw)
        original_install = list(self.install.iterdir())
        chosen = choose_artwork(self.game, str(source))
        self.assertTrue(Path(chosen).is_file())
        self.assertEqual(local_artwork(self.game).source, "Your chosen artwork")
        self.assertEqual(list(self.install.iterdir()), original_install)
        self.assertEqual(source.read_bytes(), raw)
        self.assertIsNotNone(local_artwork(self.game).image)
        clear_artwork(self.game)
        self.assertIsNone(local_artwork(self.game).image)
        self.assertEqual(source.read_bytes(), raw)

    def test_same_title_installations_do_not_share_custom_art(self):
        second = replace(self.game, key="different install", install_path=str(self.root / "Second"))
        source = self.root / "cover.png"
        source.write_bytes(picture())
        choose_artwork(self.game, str(source))
        self.assertNotEqual(game_id(self.game), game_id(second))
        self.assertIsNone(local_artwork(second).image)

    def test_modern_local_steam_hash_cover_is_found_without_network(self):
        root = Path(self.raw.library)
        cache = root / "appcache" / "librarycache" / self.game.app_id / ("a" * 40)
        cache.mkdir(parents=True)
        (cache / "library_600x900.jpg").write_bytes(picture())
        with patch("gg_desktop.game_artwork._request", side_effect=AssertionError("No automatic network")):
            art = local_artwork(self.game, [root])
        self.assertIsNotNone(art.image)
        self.assertEqual(art.source, "Local Steam library artwork")

    def test_missing_and_corrupt_images_keep_a_fallback_available(self):
        self.assertIsNone(local_artwork(self.game).image)
        (self.install / "cover.png").write_bytes(b"not an image")
        self.assertIsNone(local_artwork(self.game).image)
        with self.assertRaises(ValueError):
            image_from_bytes(b'<svg><image href="https://outside.test"/></svg>')
        with patch("gg_desktop.game_artwork.MAX_PIXELS", 10):
            with self.assertRaises(ValueError):
                image_from_bytes(picture())

    def test_preferences_are_separate_and_atomic(self):
        state = {"schema": 1, "executables": {game_id(self.game): str(self.install / "Game.exe")}}
        save_preferences(state)
        self.assertEqual(load_preferences(), state)
        before = (self.root / "Artwork" / "games.json").read_bytes()
        with patch("os.replace", side_effect=OSError("disk error")):
            with self.assertRaises(OSError):
                save_preferences({"schema": 1, "executables": {}})
        self.assertEqual((self.root / "Artwork" / "games.json").read_bytes(), before)

    def test_redirects_and_arbitrary_hosts_are_rejected(self):
        for url in ("file:///etc/passwd", "http://api.steampowered.com/", "https://api.steampowered.com.evil.test/",
                    "https://user@api.steampowered.com/", "https://api.steampowered.com:999/"):
            with self.assertRaises(ValueError):
                _checked_url(url)

    def request(self, app_id="1091500", title="Example Game", bad_asset=False):
        def get(url, limit):
            if "storesearch" in url:
                return json.dumps({"items": [{"id": 1091500, "name": "Example Game"}]}).encode()
            if "IStoreBrowseService" in url:
                return json.dumps({"response": {"store_items": [{"appid": int(app_id), "name": title,
                    "assets": {"library_capsule": "../../other.jpg" if bad_asset else "b" * 40 + "/library_600x900.jpg"}}]}}).encode()
            self.assertNotIn("../", url)
            self.assertIn("/steam/apps/1091500/", url)
            return picture()
        return get

    def test_official_art_uses_exact_app_identity_and_is_cached_locally(self):
        before = asdict(self.game)
        art = official_artwork(self.game, request=self.request())
        self.assertIsNotNone(art.image)
        self.assertEqual(local_artwork(self.game).source, "Cached official Steam artwork")
        self.assertEqual(asdict(self.game), before)

    def test_wrong_metadata_app_id_does_not_attach_artwork(self):
        art = official_artwork(self.game, request=self.request(app_id="999"))
        self.assertIsNone(art.image)
        self.assertIsNone(local_artwork(self.game).image)

    def test_nonsteam_matching_is_exact_and_never_changes_launcher_capabilities(self):
        other = LauncherGame("Example Game", "GOG", str(self.install), "gog100", None, "Verified registry")
        game = merge_games([], [other])[0]
        before = asdict(game)
        self.assertIsNotNone(official_artwork(game, request=self.request()).image)
        self.assertEqual(asdict(game), before)
        self.assertNotIn("steam_uninstall", game.capabilities)
        self.assertIsNone(official_artwork(game, request=self.request(title="Different edition")).image)

    def test_cancellation_makes_no_requests(self):
        with patch("gg_desktop.game_artwork._request", side_effect=AssertionError("Canceled")):
            self.assertIsNone(official_artwork(self.game, canceled=lambda: True).image)

    def test_linked_artwork_source_is_refused(self):
        source = self.root / "cover.png"
        source.write_bytes(picture())
        link = self.root / "linked.png"
        try:
            link.symlink_to(source)
        except OSError:
            self.skipTest("Symlinks unavailable")
        with self.assertRaises(ValueError):
            choose_artwork(self.game, str(link))
        self.assertTrue(source.exists())


if __name__ == "__main__":
    unittest.main()
