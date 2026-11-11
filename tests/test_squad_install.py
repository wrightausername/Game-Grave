"""Squad Sync's install step on disposable zips: only plain layouts, only new folders, nothing left behind on failure."""
from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from gg_desktop import squad_install as si


def make_zip(path, files):
    with zipfile.ZipFile(path, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return path


class Layouts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.mods = self.root / "mods"
        self.mods.mkdir()

    def z(self, files, name="Mod.zip"):
        return make_zip(self.root / name, files)

    def test_plain_wrapped_and_data_layouts(self):
        self.assertEqual(si.inspect(self.z({"SkyUI.esp": b"x", "interface/a.swf": b"y"})).root, ())
        self.assertEqual(si.inspect(self.z({"SkyUI 5.2/SkyUI.esp": b"x"})).root, ("SkyUI 5.2",))
        self.assertEqual(si.inspect(self.z({"Data/SkyUI.esp": b"x"})).root, ("Data",))
        self.assertEqual(si.inspect(self.z({"Wrap/Data/meshes/a.nif": b"x", "Wrap/readme.txt": b"r"})).root, ("Wrap", "Data"))

    def test_left_for_mod_organizer(self):
        self.assertIn("FOMOD", si.inspect(self.z({"fomod/ModuleConfig.xml": b"x", "A/a.esp": b"y"})).reason)
        self.assertIn("FOMOD", si.inspect(self.z({"Wrap/FOMOD/info.xml": b"x", "Wrap/a.esp": b"y"})).reason)
        self.assertIn("plain game data", si.inspect(self.z({"readme.txt": b"x", "tool.exe": b"y"})).reason)
        self.assertIn("plain game data", si.inspect(self.z({"Option A/a.esp": b"x", "Option B/a.esp": b"y"})).reason)
        self.assertIn("7z", si.inspect(self.root / "x.7z").reason)
        self.assertIn("unsafe", si.inspect(self.z({"../evil.esp": b"x"})).reason)
        self.assertIn("unsafe", si.inspect(self.z({"meshes/con.nif": b"x"})).reason)
        self.assertIn("same name", si.inspect(self.z({"a.esp": b"x", "A.ESP": b"y"})).reason)
        (self.root / "bad.zip").write_bytes(b"not a zip")
        self.assertIn("could not be read", si.inspect(self.root / "bad.zip").reason)

    def test_install_makes_one_new_switched_off_mod(self):
        archive = self.z({"Wrap/Data/SkyUI.esp": b"plugin", "Wrap/Data/interface/a.swf": b"ui", "Wrap/readme.txt": b"r"})
        result = si.install(archive, self.mods, "SkyUI", "skyrimspecialedition/12604")
        folder = self.mods / "SkyUI"
        self.assertEqual(Path(result["folder"]), folder)
        self.assertEqual((folder / "SkyUI.esp").read_bytes(), b"plugin")
        self.assertEqual((folder / "interface" / "a.swf").read_bytes(), b"ui")
        self.assertFalse((folder / "readme.txt").exists(), "Only the game data inside the Data folder is installed")
        from gg_desktop import nexus_core
        self.assertEqual(nexus_core.read_meta(folder / "meta.ini"), "skyrimspecialedition/12604")
        self.assertEqual(sorted(p.name for p in self.mods.iterdir()), ["SkyUI"], "Nothing but the one new folder")

    def test_never_overwrites_and_bad_names_are_refused(self):
        archive = self.z({"a.esp": b"new"})
        (self.mods / "Mine").mkdir()
        (self.mods / "Mine" / "a.esp").write_bytes(b"old")
        with self.assertRaisesRegex(si.InstallError, "already installed"):
            si.install(archive, self.mods, "Mine")
        self.assertEqual((self.mods / "Mine" / "a.esp").read_bytes(), b"old")
        for bad in ("", "a/b", "..", "con", "x" * 121, "trailing.", "a:b"):
            with self.assertRaises(si.InstallError):
                si.install(archive, self.mods, bad)
        with self.assertRaisesRegex(si.InstallError, "mods folder"):
            si.install(archive, self.root / "missing", "Ok")

    def test_a_failure_removes_what_it_made(self):
        archive = self.z({"a.esp": b"1", "meshes/b.nif": b"2"})
        real = si.meta_text
        try:
            si.meta_text = lambda *a: (_ for _ in ()).throw(OSError("disk"))
            with self.assertRaises(si.InstallError):
                si.install(archive, self.mods, "Broken")
        finally:
            si.meta_text = real
        self.assertEqual(list(self.mods.iterdir()), [])

    def test_meta_only_holds_a_clean_reference(self):
        self.assertIn("modid=5", si.meta_text("skyrim/5", "a.zip"))
        self.assertNotIn("modid", si.meta_text("../x/5", "a.zip"))
        self.assertNotIn("modid", si.meta_text("", "a.zip"))

    def test_custom_mods_folder(self):
        self.assertEqual(si.mods_folder(Path("C:/MO2"), ["mod_directory=%BASE_DIR%/m"]), Path("C:/MO2/m"))
        self.assertEqual(si.mods_folder(Path("C:/MO2"), []), Path("C:/MO2/mods"))


if __name__ == "__main__":
    unittest.main()
