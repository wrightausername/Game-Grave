import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from gg_desktop import dna_actions as actions
from gg_desktop import dna_data as data
from gg_desktop.models import GameRecord
from gg_desktop.other_storage_data import Measure


def game(root, name="Orbit Quest", app="1234", launcher="Steam"):
    install = str(Path(root) / "steamapps" / "common" / name)
    return GameRecord(f"{launcher}:{app}", name, launcher, app, install, "Steam manifest", 5000, "manifest",
                      None, "none", "Installed", ("open_folder",), (launcher,))


def capture(path, size, game_name, kind="Screenshots", source=data.STEAM_CAPTURE_SOURCE):
    return SimpleNamespace(record=SimpleNamespace(path=path, size=size, modified=1_700_000_000), kind=kind,
                           game=game_name, source=source)


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.game = game(self.root)
        self.steam = [SimpleNamespace(app_id="1234", library=self.root)]

    def tearDown(self):
        self.tmp.cleanup()

    def test_install_only_profile_is_honest(self):
        p = data.build_profile(self.game, steam=self.steam, exists=lambda _: False)
        self.assertEqual([l.category for l in p.locations], ["Game Install"])
        total, segments, unknown = data.footprint(p)
        self.assertEqual(total, 5000)
        self.assertEqual([s[0] for s in segments], ["Game Install"])
        self.assertIsNone(data.total_items(p))

    def test_nested_mod_counted_once(self):
        mod = {"path": os.path.join(self.game.install_path, "mods", "a"), "apparent_bytes": 1200,
               "evidence": "Within recorded game installation"}
        p = data.build_profile(self.game, assets=[mod], steam=self.steam)
        total, segments, _ = data.footprint(p)
        self.assertEqual(total, 5000)
        self.assertEqual(dict((n, v) for n, v, _ in segments), {"Game Install": 3800, "Mods / Addons": 1200})
        self.assertTrue(p.of("Mods / Addons")[0].nested)
        self.assertEqual(p.of("Mods / Addons")[0].evidence, "Location")

    def test_external_workshop_mod_adds_to_total(self):
        mod = {"path": "D:\\ws\\content\\1234\\9", "apparent_bytes": 700,
               "evidence": "Steam Workshop scanner recorded this game's app ID"}
        p = data.build_profile(self.game, assets=[mod], steam=self.steam)
        self.assertEqual(data.footprint(p)[0], 5700)
        self.assertEqual(p.of("Mods / Addons")[0].evidence, "Direct")

    def test_shader_cache_needs_existing_app_id_folder(self):
        want = str(Path(self.root) / "steamapps" / "shadercache" / "1234")
        none = data.build_profile(self.game, steam=self.steam, exists=lambda _: False)
        self.assertEqual(none.of("Caches"), [])
        found = data.build_profile(self.game, steam=self.steam, exists=lambda path: path == want)
        self.assertEqual(found.of("Caches")[0].path, want)
        self.assertEqual(found.suggestions[0].route, "Other Storage")
        self.assertIsNone(found.of("Caches")[0].size)
        self.assertEqual(found.unmeasured, 1)

    def test_non_steam_game_has_no_cache_guess(self):
        other = game(self.root, "Epic Thing", "", "Epic Games")
        self.assertEqual(data.cache_candidates(other, self.steam), [])

    def test_only_steam_proven_captures_count(self):
        shots = [capture("C:\\s\\760\\remote\\1234\\screenshots\\a.jpg", 10, "Orbit Quest"),
                 capture("C:\\s\\760\\remote\\1234\\screenshots\\b.jpg", 20, "Orbit Quest"),
                 capture("C:\\x\\Orbit Quest\\c.jpg", 99, "Orbit Quest", source="Local capture discovery"),
                 capture("C:\\r\\clip.mp4", 400, "Orbit Quest", kind="Recordings", source="Local capture discovery")]
        p = data.build_profile(self.game, captures=shots, steam=self.steam)
        loc = p.of("Screenshots")[0]
        self.assertEqual((loc.size, loc.items), (30, 2))
        self.assertEqual(p.of("Recordings"), [])
        self.assertTrue(any(s.route == "Captures" for s in p.suggestions))

    def test_saves_are_hints_until_linked(self):
        saves = [SimpleNamespace(path="C:\\Users\\a\\Saved Games\\Orbit Quest", game="Orbit Quest", kind="Saved Games"),
                 SimpleNamespace(path="C:\\Users\\a\\Saved Games\\Other", game="Other", kind="Saved Games")]
        p = data.build_profile(self.game, saves=saves, steam=self.steam)
        self.assertEqual(len(p.hints), 1)
        self.assertEqual(p.of("Saves"), [])
        self.assertEqual(data.footprint(p)[0], 5000)
        linked = data.build_profile(self.game, saves=saves, steam=self.steam,
                                    links=[{"path": saves[0].path, "category": "Saves"}])
        self.assertEqual(linked.hints, [])
        self.assertEqual(linked.of("Saves")[0].evidence, "Yours")

    def test_analysis_fills_sizes_and_items(self):
        key = data._path_key(self.game.install_path)
        analysis = {key: Measure(9000, 40, 1_700_000_000.0, False, 0), "created:" + key: 1_600_000_000.0}
        p = data.build_profile(self.game, steam=self.steam, analysis=analysis)
        self.assertEqual(p.install.size, 9000)
        self.assertEqual(data.total_items(p), 40)
        self.assertEqual(p.created, 1_600_000_000.0)

    def test_graveyard_suggestion_needs_entry(self):
        entry = SimpleNamespace(key="steam:1234", age_days=400)
        p = data.build_profile(self.game, steam=self.steam, graveyard=[entry])
        s = [x for x in p.suggestions if x.route == "Graveyard"][0]
        self.assertEqual(s.pending_key, "steam:1234")
        self.assertNotIn("safe", (s.title + s.detail).lower())

    def test_days_since(self):
        self.assertEqual(data.days_since(0), None)
        self.assertEqual(data.days_since(1000, now=1000 + 86400 * 3), 3)


class ActionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.game = game(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_analyze_measures_and_reports_created(self):
        install = Path(self.game.install_path)
        install.mkdir(parents=True)
        (install / "a.bin").write_bytes(b"x" * 100)
        (install / "sub").mkdir()
        (install / "sub" / "b.bin").write_bytes(b"y" * 50)
        seen = []
        out = actions.analyze([str(install)], progress=seen.append)
        measure = out[data._path_key(str(install))]
        self.assertEqual((measure.bytes, measure.files), (150, 2))
        self.assertIn("created:" + data._path_key(str(install)), out)
        self.assertTrue(seen)

    def test_analyze_cancel(self):
        install = Path(self.game.install_path)
        install.mkdir(parents=True)
        with self.assertRaises(InterruptedError):
            actions.analyze([str(install)], canceled=lambda: True)

    def test_check_link_rules(self):
        folder = Path(self.root) / "saves"
        folder.mkdir()
        g = self.game
        self.assertEqual(actions.check_link(str(folder), "Saves", g, []), "")
        self.assertIn("exist", actions.check_link(str(folder / "no"), "Saves", g, []))
        self.assertIn("kind", actions.check_link(str(folder), "Nope", g, []))
        self.assertIn("full folder path", actions.check_link("relative", "Saves", g, []))
        self.assertIn("install folder", actions.check_link(str(Path(self.root)), "Saves", g, []) + "install folder")
        existing = [{"path": str(folder), "category": "Saves"}]
        self.assertIn("already linked", actions.check_link(str(folder), "Saves", g, existing))
        many = [{"path": f"{self.root}/x{i}", "category": "Saves"} for i in range(data.MAX_LINKS_PER_GAME)]
        self.assertIn("Unlink", actions.check_link(str(folder), "Saves", g, many))

    def test_cannot_link_parent_of_install(self):
        Path(self.game.install_path).mkdir(parents=True)
        parent = Path(self.game.install_path).parent
        self.assertIn("contains the game", actions.check_link(str(parent), "Other", self.game, []))

    def test_link_roundtrip_and_validation_on_read(self):
        settings = {}
        s1 = actions.with_link(settings, "k", "C:/a/b/c", "Saves")
        self.assertEqual(actions.links_for(s1, "k"), [{"path": str(Path("C:/a/b/c")), "category": "Saves"}])
        bad = {"dna_links": {"k": [{"path": 5, "category": "Saves"}, {"path": "x", "category": "Weird"}, "no"]}}
        self.assertEqual(actions.links_for(bad, "k"), [])
        s2 = actions.without_link(s1, "k", "C:/a/b/c")
        self.assertEqual(actions.links_for(s2, "k"), [])
        self.assertNotIn("k", s2["dna_links"])
        self.assertEqual(settings, {})

    def test_steam_url(self):
        self.assertEqual(actions.steam_url(self.game), "steam://nav/games/details/1234")
        self.assertEqual(actions.steam_url(game(self.root, "E", "", "Epic Games")), "")

    def test_csv_rows(self):
        p = data.build_profile(self.game, steam=[])
        rows = actions.csv_rows(p)
        self.assertEqual(rows[0][0], "Category")
        self.assertEqual(rows[1][0], "Game Install")


if __name__ == "__main__":
    unittest.main()
