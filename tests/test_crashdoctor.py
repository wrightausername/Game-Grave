import json
import tempfile
import unittest
from pathlib import Path

from gg_desktop import crashdoctor_core as cd


class Judge(unittest.TestCase):
    def test_judge(self):
        self.assertEqual(cd.judge(cd.Observation(True, 30, False), 120), "crash")
        self.assertEqual(cd.judge(cd.Observation(True, 125, True), 120), "ok")
        self.assertEqual(cd.judge(cd.Observation(False, 0, False), 120), "unsure")
        self.assertEqual(cd.judge(cd.Observation(True, 200, True, crash_recorded=True), 120), "crash")
        self.assertIn("closed after 30 seconds", cd.explain("crash", cd.Observation(True, 30, False), 120))

    def test_mo2_executables_and_launch(self):
        ini = ("[General]\ngameName=Skyrim Special Edition\n[customExecutables]\nsize=2\n1\\title=Skyrim Special Edition\n"
               "1\\binary=C:/Games/Skyrim/SkyrimSE.exe\n2\\title=SKSE\n2\\binary=C:/Games/Skyrim/skse64_loader.exe\n")
        self.assertEqual(cd.mo2_executables(ini)[0], ("SKSE", "C:/Games/Skyrim/skse64_loader.exe"), "the loader comes first")
        self.assertEqual(cd.mo2_launch("C:/MO2/ModOrganizer.exe", "GG Bisect - Main", "SKSE"),
                         ["C:/MO2/ModOrganizer.exe", "-p", "GG Bisect - Main", "moshortcut://:SKSE"])

    def test_game_programs(self):
        with tempfile.TemporaryDirectory() as d:
            for name, size in (("SkyrimSE.exe", 900), ("SkyrimSELauncher.exe", 50), ("skse64_loader.exe", 10),
                               ("unins000.exe", 5)):
                (Path(d) / name).write_bytes(b"x" * size)
            games, loaders = cd.game_programs(d)
            self.assertEqual(games, ["SkyrimSE.exe"])
            self.assertEqual(loaders, ["skse64_loader.exe"])


class Folder(unittest.TestCase):
    def test_switch_and_put_back_never_overwrites(self):
        with tempfile.TemporaryDirectory() as d:
            mods = Path(d) / "Mods"
            mods.mkdir()
            for name in ("A", "B", "C"):
                (mods / name).mkdir()
                (mods / name / "f.txt").write_text(name)
            (mods / "D.dll").write_text("d")
            sw = cd.FolderSwitcher(mods)
            self.assertEqual([u.key for u in sw.units()], ["A", "B", "C", "D.dll"])
            sw.apply({"A", "D.dll"})
            self.assertEqual(sorted(p.name for p in mods.iterdir() if p.name != cd.HOLD_NAME), ["A", "D.dll"])
            self.assertEqual([u.key for u in sw.units()], ["A", "B", "C", "D.dll"], "moved mods are still known")
            self.assertEqual(cd.leftovers([d + "/Mods"]), [mods])
            sw.apply({"B"})
            self.assertEqual(sorted(p.name for p in mods.iterdir() if p.name != cd.HOLD_NAME), ["B"])
            (mods / "C").mkdir()                       # something new with the same name appears
            left = sw.restore()
            self.assertEqual(left, ["C"])
            self.assertEqual((mods / "A" / "f.txt").read_text(), "A")
            self.assertTrue((mods / cd.HOLD_NAME / "C" / "f.txt").is_file(), "never overwritten, kept aside")
            (mods / "C").rmdir()
            self.assertEqual(cd.put_back(mods), [])
            self.assertFalse((mods / cd.HOLD_NAME).exists())
            self.assertEqual((mods / "C" / "f.txt").read_text(), "C")


    def test_keep_off_and_back_on(self):
        with tempfile.TemporaryDirectory() as d:
            mods = Path(d)
            for name in ("Good", "Bad"):
                (mods / name).mkdir()
            sw = cd.FolderSwitcher(mods)
            self.assertEqual(cd.turn_off(sw, ["Bad"]), [])
            self.assertFalse((mods / "Bad").exists())
            self.assertEqual([u.key for u in cd.FolderSwitcher(mods).units()], ["Good"], "kept-off mods aren't tested")
            self.assertEqual(cd.turned_off([d]), [mods])
            self.assertEqual(cd.leftovers([d]), [], "keeping off is not an unfinished test")
            self.assertEqual(cd.turn_back_on(mods), [])
            self.assertTrue((mods / "Bad").is_dir())
            self.assertEqual(cd.turned_off([d]), [])

    def test_resume_key(self):
        self.assertEqual(cd.resume_key("Folder", "Stardew", "D:/Mods"), cd.resume_key("Folder", "Stardew", "d:/mods"))
        self.assertNotEqual(cd.resume_key("Folder", "Stardew", "D:/Mods"), cd.resume_key("Vortex", "Stardew", "D:/Mods"))


class Vortex(unittest.TestCase):
    def test_deployment_list(self):
        with tempfile.TemporaryDirectory() as d:
            game = Path(d)
            data = game / "Data"
            (data / "SKSE" / "Plugins").mkdir(parents=True)
            (data / "SkyUI.esp").write_text("1")
            (data / "SKSE" / "Plugins" / "engine.dll").write_text("2")
            (data / "Other.esp").write_text("3")
            (data / "vortex.deployment.json").write_text(json.dumps({"files": [
                {"relPath": "SkyUI.esp", "source": "SkyUI-5"}, {"relPath": "SKSE/Plugins/engine.dll", "source": "Engine Fixes"},
                {"relPath": "Other.esp", "source": "Other"}, {"relPath": "../evil.txt", "source": "Bad"}],
                "targetPath": str(data)}))
            sw = cd.VortexSwitcher(game)
            self.assertEqual([u.key for u in sw.units()], ["Engine Fixes", "Other", "SkyUI-5"])
            sw.apply({"SkyUI-5"})
            self.assertTrue((data / "SkyUI.esp").exists())
            self.assertFalse((data / "SKSE" / "Plugins" / "engine.dll").exists())
            self.assertFalse((data / "Other.esp").exists())
            self.assertEqual(sw.restore(), [])
            self.assertEqual((data / "SKSE" / "Plugins" / "engine.dll").read_text(), "2")
            self.assertEqual((data / "Other.esp").read_text(), "3")
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(cd.DoctorError):
                cd.VortexSwitcher(d)

    def test_confirmation_words(self):
        text = cd.confirmation(cd.Plan("Folder", "Stardew Valley", "Stardew Valley.exe", 120), 12, "D:/Stardew/Mods")
        self.assertIn("12 mods", text)
        self.assertIn("D:/Stardew/Mods", text)
        self.assertIn("Nothing is deleted or overwritten", text)
        self.assertNotIn("safe", text.lower())


if __name__ == "__main__":
    unittest.main()


class EasyPath(unittest.TestCase):
    def test_find_mod_folder(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(cd.find_mod_folder(d), "")
            (Path(d) / "Mods").mkdir()
            self.assertEqual(cd.find_mod_folder(d), "", "an empty Mods folder isn't a mod folder")
            (Path(d) / "BepInEx" / "plugins").mkdir(parents=True)
            (Path(d) / "BepInEx" / "plugins" / "a.dll").write_text("x")
            self.assertEqual(Path(cd.find_mod_folder(d)), Path(d) / "BepInEx" / "plugins")
            (Path(d) / "Mods" / "SMAPI-thing").mkdir()
            self.assertEqual(Path(cd.find_mod_folder(d)), Path(d) / "Mods")
        with tempfile.TemporaryDirectory() as local:
            bg3 = Path(local) / "Larian Studios" / "Baldur's Gate 3" / "Mods"
            bg3.mkdir(parents=True)
            (bg3 / "x.pak").write_text("x")
            self.assertEqual(Path(cd.find_mod_folder("", "Baldur's Gate 3", local)), bg3)

    def test_when_and_estimate(self):
        self.assertEqual(cd.when_choice("play")[2:4], (300, True))
        self.assertEqual(cd.when_choice("nonsense")[0], "menu")
        low, high, low_min, high_min = cd.estimate(40, 120)
        self.assertTrue(2 <= low < high <= cd.MAX_RUNS and low_min < high_min)
        self.assertGreater(cd.estimate(40, 120, True)[3], high_min)
        self.assertLess(cd.remaining(3, 60)[0], cd.remaining(100, 60)[0])

    def test_blockers_and_words(self):
        found = cd.blockers(["explorer.exe", "Vortex.exe", "SkyrimSE.exe", "ModOrganizer.exe"], ["SkyrimSE.exe"])
        self.assertEqual({f for _e, f in found}, {"Vortex", "the game", "Mod Organizer 2"})
        self.assertEqual(cd.headline("culprit", ["SkyUI"]), "Found it: SkyUI is crashing your game.")
        self.assertIn("A and B crash when", cd.headline("interaction", ["A", "B"]))
        self.assertTrue(cd.look_up_url("Sky UI", "Skyrim").startswith("https://www.google.com/search?q=Sky+UI"))
        for text in cd.HINTS.values():
            self.assertNotIn("safe", text.lower())
