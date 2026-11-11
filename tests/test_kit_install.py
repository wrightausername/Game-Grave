"""Whole-installation Resurrection Kits: create with no size cap, restore the install, saves and load order in place.

Every fixture is a disposable temporary folder. Nothing here touches a real game."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

import resurrection_v2 as kit


class KitInstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        # The "old PC": a Steam library, saves in Documents, a plugins.txt in Local AppData.
        old = self.root / "oldpc"
        self.old_env = {"USERPROFILE": str(old / "User"), "LOCALAPPDATA": str(old / "User" / "AppData" / "Local"),
                        "APPDATA": str(old / "User" / "AppData" / "Roaming")}
        library = old / "SteamLibrary" / "steamapps"
        self.game = library / "common" / "Skyrim Special Edition"
        (self.game / "Data").mkdir(parents=True)
        (self.game / "SkyrimSE.exe").write_bytes(b"MZ" + b"e" * 5000)
        (self.game / "Data" / "Skyrim.esm").write_bytes(b"esm" * 3000)
        (self.game / "Data" / "Textures.bsa").write_bytes(b"bsa" * 3000)
        (self.game / "Data" / "SkyUI.esp").write_bytes(b"skyui")
        self.manifest_file = library / "appmanifest_489830.acf"
        self.manifest_file.write_text('"AppState" { "appid" "489830" }')
        self.saves = Path(self.old_env["USERPROFILE"]) / "Documents" / "My Games" / "Skyrim Special Edition" / "Saves"
        self.saves.mkdir(parents=True)
        (self.saves / "Save1.ess").write_bytes(b"progress")
        self.plugins_dir = Path(self.old_env["LOCALAPPDATA"]) / "Skyrim Special Edition"
        self.plugins_dir.mkdir(parents=True)
        self.plugins = self.plugins_dir / "plugins.txt"
        self.plugins.write_text("*SkyUI.esp\n")
        self.out = self.root / "kits"
        self.out.mkdir()
        self.zip = self.out / "Skyrim.zip"

    def make(self, **extra):
        sources = {"Game": self.game, "Saves": self.saves, "LoadOrder": [self.plugins], "Launcher": [self.manifest_file]}
        origins = {"Saves": "%DOCUMENTS%\\My Games\\Skyrim Special Edition\\Saves",
                   "LoadOrder": "%LOCALAPPDATA%\\Skyrim Special Edition"}
        return kit.create_complete_kit("Skyrim Special Edition", sources, self.zip, origins=origins, **extra)

    def new_pc(self):
        new = self.root / "newpc"
        env = {"USERPROFILE": str(new / "User"), "LOCALAPPDATA": str(new / "User" / "AppData" / "Local"),
               "APPDATA": str(new / "User" / "AppData" / "Roaming")}
        library = new / "Games" / "steamapps" / "common"
        library.mkdir(parents=True)
        Path(env["USERPROFILE"]).mkdir(parents=True)
        return env, library

    def test_no_size_cap_and_limits_are_structural(self):
        self.assertGreater(kit.MAX_BYTES, 1024 ** 5)
        self.assertGreaterEqual(kit.MAX_FILES, 1_000_000)

    def test_create_holds_the_whole_install_and_stays_private(self):
        created = self.make()
        self.assertEqual(set(created["roles"]), {"Game", "Saves", "LoadOrder", "Launcher"})
        manifest = json.loads(Path(created["manifest"]).read_text())
        self.assertTrue(manifest["includes_game_install"])
        self.assertNotIn(str(self.root), json.dumps(manifest), "No local path or user name in the manifest")
        origins = {r["name"]: r.get("origin") for r in manifest["roles"]}
        self.assertEqual(origins["LoadOrder"], "%LOCALAPPDATA%\\Skyrim Special Edition")
        with zipfile.ZipFile(self.zip) as z:
            names = set(z.namelist())
            self.assertIn("Game/SkyrimSE.exe", names)
            self.assertIn("Game/Data/SkyUI.esp", names)
            self.assertIn("LoadOrder/plugins.txt", names)
            self.assertIn("Launcher/appmanifest_489830.acf", names)
            self.assertEqual(z.getinfo("Game/Data/Textures.bsa").compress_type, zipfile.ZIP_STORED)
            self.assertEqual(z.getinfo("Game/SkyrimSE.exe").compress_type, zipfile.ZIP_DEFLATED)
        self.assertEqual((self.game / "SkyrimSE.exe").read_bytes()[:2], b"MZ", "Sources are untouched")

    def test_origin_rules(self):
        with self.assertRaises(ValueError):
            kit._clean_origin("C:\\Users\\alex\\Documents")
        with self.assertRaises(ValueError):
            kit._clean_origin("%DOCUMENTS%\\..\\Windows")
        self.assertIsNone(kit.expand_origin("C:\\Users\\alex", {}))
        self.assertEqual(kit.expand_origin("%DOCUMENTS%\\My Games", {"USERPROFILE": str(self.root)}),
                         self.root / "Documents" / "My Games")

    def test_role_shape_is_enforced(self):
        with self.assertRaises(ValueError):
            kit.create_complete_kit("G", {"LoadOrder": self.plugins_dir}, self.zip)
        with self.assertRaises(ValueError):
            kit.create_complete_kit("G", {"Saves": [self.plugins]}, self.zip)

    def test_game_install_and_its_own_mods_folder_cannot_both_be_chosen(self):
        with self.assertRaisesRegex(ValueError, "overlap"):
            kit.create_complete_kit("G", {"Game": self.game, "Mods": self.game / "Data"}, self.zip)

    def test_links_are_refused_and_named(self):
        try:
            os.symlink(self.root, self.game / "Data" / "Shortcut", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are not available here")
        with self.assertRaisesRegex(ValueError, "Shortcut"):
            self.make()
        self.assertFalse(self.zip.exists() or (self.out / "Skyrim.zip.partial").exists())

    def test_create_reports_progress_and_can_be_cancelled(self):
        seen = []
        self.make(progress=lambda phase, done, total, note: seen.append(phase))
        self.assertIn("Copying", seen)
        self.assertEqual(seen[-1], "Done")
        other = self.out / "Second.zip"
        with self.assertRaises(InterruptedError):
            kit.create_complete_kit("G", {"Game": self.game}, other, cancel=lambda: True)
        self.assertEqual([p.name for p in self.out.iterdir() if p.name.startswith("Second")], [])

    def test_plan_then_restore_everything_in_place(self):
        created = self.make()
        env, library = self.new_pc()
        manifest = Path(created["manifest"])
        plan = kit.plan_installation(manifest, library, environ=env)
        modes = {p["role"]: p["mode"] for p in plan["parts"]}
        self.assertEqual(modes, {"Game": "new_folder", "Launcher": "place_files", "Saves": "place", "LoadOrder": "place_files"})
        self.assertEqual(plan["blocked"], [])
        with self.assertRaises(PermissionError):
            kit.restore_installation(manifest, library, environ=env)
        seen = []
        result = kit.restore_installation(manifest, library, approved=True, environ=env,
                                          progress=lambda *a: seen.append(a[0]))
        self.assertTrue(result["restored"])
        restored = library / "Skyrim Special Edition"
        self.assertEqual((restored / "SkyrimSE.exe").read_bytes(), (self.game / "SkyrimSE.exe").read_bytes())
        self.assertEqual((restored / "Data" / "SkyUI.esp").read_bytes(), b"skyui")
        self.assertEqual((library.parent / "appmanifest_489830.acf").read_text(), self.manifest_file.read_text())
        self.assertEqual((Path(env["USERPROFILE"]) / "Documents" / "My Games" / "Skyrim Special Edition" / "Saves" / "Save1.ess").read_bytes(), b"progress")
        self.assertEqual((Path(env["LOCALAPPDATA"]) / "Skyrim Special Edition" / "plugins.txt").read_text(), "*SkyUI.esp\n")
        self.assertEqual(result["review_folder"], "")
        self.assertIn("Restoring", seen)

    def test_existing_saves_and_load_order_are_never_overwritten(self):
        created = self.make()
        env, library = self.new_pc()
        saves = Path(env["USERPROFILE"]) / "Documents" / "My Games" / "Skyrim Special Edition" / "Saves"
        saves.mkdir(parents=True)
        (saves / "Newer.ess").write_bytes(b"newer progress")
        plugins = Path(env["LOCALAPPDATA"]) / "Skyrim Special Edition"
        plugins.mkdir(parents=True)
        (plugins / "plugins.txt").write_text("*Mine.esp\n")
        result = kit.restore_installation(Path(created["manifest"]), library, approved=True, environ=env)
        self.assertEqual((saves / "Newer.ess").read_bytes(), b"newer progress")
        self.assertFalse((saves / "Save1.ess").exists(), "Old saves never go into a folder that already has files")
        self.assertEqual((plugins / "plugins.txt").read_text(), "*Mine.esp\n")
        self.assertEqual(result["skipped_existing"], ["plugins.txt"])
        review = Path(result["review_folder"])
        self.assertEqual((review / "Saves" / "Save1.ess").read_bytes(), b"progress")

    def test_existing_game_folder_blocks_everything(self):
        created = self.make()
        env, library = self.new_pc()
        (library / "Skyrim Special Edition").mkdir()
        before = sorted(p for p in self.root.rglob("*") if "newpc" in str(p))
        with self.assertRaises(FileExistsError):
            kit.restore_installation(Path(created["manifest"]), library, approved=True, environ=env)
        self.assertEqual(sorted(p for p in self.root.rglob("*") if "newpc" in str(p)), before)

    def test_cancel_removes_everything_the_restore_wrote(self):
        created = self.make()
        env, library = self.new_pc()
        before = sorted(str(p) for p in (self.root / "newpc").rglob("*"))
        calls = {"n": 0}

        def cancel():
            calls["n"] += 1
            return calls["n"] > 3
        with self.assertRaises(InterruptedError):
            kit.restore_installation(Path(created["manifest"]), library, approved=True, environ=env, cancel=cancel)
        self.assertEqual(sorted(str(p) for p in (self.root / "newpc").rglob("*")), before)

    def test_tampered_kit_restores_nothing(self):
        created = self.make()
        env, library = self.new_pc()
        with open(self.zip, "r+b") as handle:
            handle.seek(40)
            handle.write(b"\x00\x01\x02")
        with self.assertRaises((ValueError, zipfile.BadZipFile)):
            kit.restore_installation(Path(created["manifest"]), library, approved=True, environ=env)
        self.assertEqual(list(library.iterdir()), [])

    def test_non_steam_library_sends_the_launcher_file_to_review(self):
        created = self.make()
        env, _ = self.new_pc()
        other = self.root / "newpc" / "Epic"
        other.mkdir()
        plan = kit.plan_installation(Path(created["manifest"]), other, environ=env)
        launcher = next(p for p in plan["parts"] if p["role"] == "Launcher")
        self.assertEqual(launcher["mode"], "review")

    def test_old_kits_still_restore_the_old_way(self):
        saves = self.root / "S"
        saves.mkdir()
        (saves / "a.sav").write_bytes(b"x")
        created = kit.create_complete_kit("Old", {"Saves": saves}, self.out / "Old.zip")
        parent = self.root / "Recovery"
        parent.mkdir()
        result = kit.restore_kit(Path(created["manifest"]), parent, approved=True)
        self.assertTrue((Path(result["target"]) / "Saves" / "a.sav").exists())


if __name__ == "__main__":
    unittest.main()


class Polish(KitInstallTests):
    def test_every_phase_reports_progress_and_checks_can_be_cancelled(self):
        phases = []
        created = self.make(progress=lambda phase, done, total, note: phases.append(phase))
        for wanted in ("Copying", "Checking the ZIP", "Fingerprinting", "Done"):
            self.assertIn(wanted, phases)
        env, library = self.new_pc()
        seen = []
        kit.restore_installation(Path(created["manifest"]), library, approved=True, environ=env,
                                 progress=lambda phase, *rest: seen.append(phase))
        self.assertIn("Final check", seen)
        big = self.root / "big"
        big.mkdir()
        (big / "blob.bin").write_bytes(os.urandom(3 * 2 ** 20))
        made = kit.create_complete_kit("Big", {"Saves": big}, self.out / "big.zip")
        import time
        def slow_cancel():
            time.sleep(.25)
            return True
        with self.assertRaises(InterruptedError):
            kit.inspect_restore(Path(made["manifest"]), cancel=slow_cancel)

    def test_kits_without_role_details_restore_to_the_review_folder(self):
        created = self.make()
        manifest_path = Path(created["manifest"])
        data = json.loads(manifest_path.read_text())
        data["roles"] = ["Game", "Saves"]          # an old shape: names only
        manifest_path.write_text(json.dumps(data))
        env, library = self.new_pc()
        plan = kit.plan_installation(manifest_path, library, environ=env)
        modes = {p["role"]: p["mode"] for p in plan["parts"]}
        self.assertEqual(modes["Game"], "new_folder")
        self.assertEqual(modes["Saves"], "review")

    def test_note_is_honest_when_the_kit_has_no_install(self):
        made = kit.create_complete_kit("S", {"Saves": self.saves}, self.out / "s.zip",
                                       origins={"Saves": "%DOCUMENTS%" + chr(92) + "My Games" + chr(92) + "X"})
        env, library = self.new_pc()
        result = kit.restore_installation(Path(made["manifest"]), library, approved=True, environ=env)
        self.assertIn("did not hold the game install", result["note"])

    def test_documents_folder(self):
        self.assertEqual(kit.documents_dir({"USERPROFILE": str(self.root)}), self.root / "Documents")
        self.assertIsNone(kit.documents_dir({}))
        if os.name == "nt":
            real = kit.documents_dir()
            self.assertTrue(real is not None and real.is_absolute())

    def test_restored_files_keep_their_recorded_time(self):
        old = 1_600_000_000
        os.utime(self.game / "Data" / "SkyUI.esp", (old, old))
        os.utime(self.game / "Data" / "Skyrim.esm", (old - 86400, old - 86400))
        created = self.make()
        env, library = self.new_pc()
        kit.restore_installation(Path(created["manifest"]), library, approved=True, environ=env)
        data = library / "Skyrim Special Edition" / "Data"
        self.assertLess(abs((data / "SkyUI.esp").stat().st_mtime - old), 3)
        self.assertLess((data / "Skyrim.esm").stat().st_mtime, (data / "SkyUI.esp").stat().st_mtime)

    def test_empty_folders_come_back(self):
        (self.game / "Data" / "Logs").mkdir()
        (self.game / "Mods" / "Later").mkdir(parents=True)
        created = self.make()
        manifest = json.loads(Path(created["manifest"]).read_text())
        game = next(r for r in manifest["roles"] if r["name"] == "Game")
        self.assertEqual(game["empty_folders"], ["Data/Logs", "Mods/Later"])
        with zipfile.ZipFile(self.zip) as z:
            self.assertFalse(any(i.is_dir() for i in z.infolist()), "The ZIP still holds files only")
        env, library = self.new_pc()
        kit.restore_installation(Path(created["manifest"]), library, approved=True, environ=env)
        restored = library / "Skyrim Special Edition"
        self.assertTrue((restored / "Data" / "Logs").is_dir())
        self.assertTrue((restored / "Mods" / "Later").is_dir())

    def test_empty_folder_names_from_a_manifest_are_checked(self):
        self.assertEqual(kit._clean_empty(["Data/Logs", "../Windows", "C:/x", 5, "", "a/../../b"]), ["Data/Logs"])

    def test_paths_too_long_for_this_pc_stop_before_anything_is_written(self):
        created = self.make()
        env, library = self.new_pc()
        before = sorted(str(p) for p in (self.root / "newpc").rglob("*"))
        real = kit.path_limit
        try:
            kit.path_limit = lambda: len(str(library)) + 30      # pretend Windows allows very little here
            with self.assertRaisesRegex(ValueError, "longer than"):
                kit.restore_installation(Path(created["manifest"]), library, approved=True, environ=env)
        finally:
            kit.path_limit = real
        self.assertEqual(sorted(str(p) for p in (self.root / "newpc").rglob("*")), before)
        self.assertEqual(kit.too_long(["a" * 300, "b" * 10], 259), 1)
        self.assertEqual(kit.too_long(["a" * 300], None), 0)
