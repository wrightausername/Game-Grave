import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

from gg_desktop import bisect_units as bu
from gg_desktop.mods_data import Dependency


def entry(root, name, deps=(), files=(), kind="mod"):
    folder = Path(root) / name
    folder.mkdir(parents=True, exist_ok=True)
    for rel in files:
        target = folder / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x")
    return NS(key="k:" + name, name=name, path=str(folder), dependencies=list(deps), kind=kind)


class Units(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name

    def catalog(self, *entries, markers=None):
        profile = NS(members={e.key: (markers or {}).get(e.name, "+") for e in entries})
        return NS(entries=list(entries)), profile

    def test_only_mods_switched_on_become_units(self):
        a, b, c = (entry(self.root, n, files=["a.dds"]) for n in "ABC")
        catalog, profile = self.catalog(a, b, c, markers={"B": "-"})
        units, files, _ = bu.units_for_profile(catalog, profile)
        self.assertEqual([u.name for u in units], ["A", "C"])
        self.assertEqual(set(files), {"k:A", "k:C"})

    def test_scripts_and_plugins_make_a_code_mod_and_textures_do_not(self):
        a = entry(self.root, "Tex", files=["textures/a.dds"])
        b = entry(self.root, "Script", files=["scripts/q.pex"])
        c = entry(self.root, "Plug", files=["x.esp"])
        d = entry(self.root, "Native", files=["SKSE/Plugins/thing.dll"])
        units, _, _ = bu.units_for_profile(*self.catalog(a, b, c, d))
        self.assertEqual({u.name: u.kind for u in units}, {"Tex": "assets", "Script": "code", "Plug": "code", "Native": "code"})

    def test_declared_requirements_link_to_mods_by_exact_name_only(self):
        fw = entry(self.root, "Framework")
        a = entry(self.root, "Needs It", deps=[Dependency("framework"), Dependency("Elsewhere"),
                                              Dependency("Framework", optional=True), Dependency("Needs It")])
        units, _, _ = bu.units_for_profile(*self.catalog(fw, a))
        need = {u.name: u.requires for u in units}
        self.assertEqual(need["Needs It"], ("k:Framework",))
        self.assertEqual(need["Framework"], ())

    def test_always_on_marks_pinned(self):
        a, b = entry(self.root, "A"), entry(self.root, "B")
        units, _, _ = bu.units_for_profile(*self.catalog(a, b), always_on=["k:B"])
        self.assertEqual({u.name: u.pinned for u in units}, {"A": False, "B": True})

    def test_install_date_comes_from_the_folder_and_is_explained(self):
        a = entry(self.root, "A")
        units, _, notes = bu.units_for_profile(*self.catalog(a), installed=lambda p: 1_700_000_000.0)
        self.assertEqual(units[0].added, 1_700_000_000.0)
        self.assertTrue(any("folder was created" in n or "folder" in n for n in notes))
        units, _, notes = bu.units_for_profile(*self.catalog(a), installed=lambda p: None)
        self.assertIsNone(units[0].added)
        self.assertTrue(any("no readable install date" in n for n in notes))

    def test_a_missing_folder_does_not_break_the_list(self):
        ghost = NS(key="k:Ghost", name="Ghost", path=str(Path(self.root) / "nope"), dependencies=[], kind="mod")
        units, files, _ = bu.units_for_profile(*self.catalog(ghost))
        self.assertEqual(files["k:Ghost"], [])
        self.assertIsNone(units[0].added)

    def test_links_are_not_followed_and_the_file_cap_holds(self):
        a = entry(self.root, "Big")
        for i in range(30):
            (Path(a.path) / f"f{i}.dds").write_bytes(b"x")
        try:
            os.symlink(self.root, Path(a.path) / "loop", target_is_directory=True)
        except (OSError, NotImplementedError):
            pass
        names, _ = bu.scan_mod_files(a.path)
        self.assertEqual(len(names), 30)
        original = bu.MAX_FILES_PER_MOD
        bu.MAX_FILES_PER_MOD = 10
        try:
            self.assertLessEqual(len(bu.scan_mod_files(a.path)[0]), 10)
        finally:
            bu.MAX_FILES_PER_MOD = original

    def test_cancel_stops_early(self):
        a = entry(self.root, "A", files=["x.dds"])
        units, _, _ = bu.units_for_profile(*self.catalog(a), cancelled=lambda: True)
        self.assertEqual(units, [])


class Reports(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.now = time.time()

    def put(self, rel, text="x", age_days=1):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        stamp = self.now - age_days * 86400
        os.utime(path, (stamp, stamp))
        return path

    def test_only_recent_crash_looking_text_files_are_found_newest_first(self):
        self.put("game/crash-2026-11-01.log", age_days=9)
        self.put("game/crash-2026-11-08.log", age_days=2)
        self.put("game/readme.txt")
        self.put("game/notes.log")                      # a log, but not a crash word
        self.put("game/crash-ancient.log", age_days=400)
        self.put("game/data.bin")
        found = bu.find_reports([self.root / "game"], now=self.now)
        self.assertEqual([Path(p).name for p, _ in found], ["crash-2026-11-08.log", "crash-2026-11-01.log"])

    def test_missing_roots_and_deep_folders_are_fine(self):
        self.put("a/b/c/d/crash.log")
        self.assertEqual(bu.find_reports([self.root / "nope", self.root / "a"], now=self.now), [])
        self.assertEqual(len(bu.find_reports([self.root / "a"], now=self.now, depth=4)), 1)

    def test_text_is_read_capped_and_garbage_is_survived(self):
        big = self.put("crash-big.log", "A" * (bu.MAX_REPORT_BYTES + 5000))
        bad = self.root / "crash-bad.log"
        bad.write_bytes(b"\xff\xfe\x00\x00 bin \x80\x81")
        got = bu.read_reports_text([(str(big), 1.0), (str(bad), 2.0), (str(self.root / "gone.log"), 3.0)])
        self.assertEqual(len(got), 2)
        self.assertLessEqual(len(got[0][0]), bu.MAX_REPORT_BYTES)

    def test_default_roots_cover_game_manager_and_script_extender_logs(self):
        docs = self.root / "Documents"
        (docs / "My Games" / "Skyrim Special Edition" / "SKSE").mkdir(parents=True)
        roots = [str(r) for r in bu.default_report_roots(self.root / "Game", self.root / "MO2", docs)]
        text = " ".join(roots)
        for want in ("Game", "logs", "crashDumps", "SKSE", "Crash Reports"):
            self.assertIn(want, text)


if __name__ == "__main__":
    unittest.main()
