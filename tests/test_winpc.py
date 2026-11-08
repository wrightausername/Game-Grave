"""The seven Windows tools, tested against fake registry and runner backends and real temp folders."""
import json
import os
from pathlib import Path
import tempfile
import time
import unittest

from gg_desktop import winpc as w


class FakeRegistry:
    def __init__(self, data=None):
        self.data = dict(data or {})

    def read(self, hive, path, name):
        return self.data.get((hive, path.lower(), name))

    def write(self, hive, path, name, value, kind):
        self.data[(hive, path.lower(), name)] = (value, kind)

    def delete(self, hive, path, name):
        self.data.pop((hive, path.lower(), name), None)

    def values(self, hive, path):
        return [(n, v[0], v[1]) for (h, p, n), v in self.data.items() if h == hive and p == path.lower()]


class FakeRunner:
    def __init__(self, outputs=None):
        self.calls, self.outputs = [], outputs or {}

    def run(self, args, **kw):
        self.calls.append(list(args))
        for key, result in self.outputs.items():
            if key in " ".join(args):
                return result
        return w.RunResult(0, "")


def reg_key(hive, path, name):
    return (hive, path.lower(), name)


class CleanupTests(unittest.TestCase):
    def test_only_old_files_inside_roots_and_empty_folders_tidied(self):
        with tempfile.TemporaryDirectory() as temp:
            root, outside = Path(temp, "Temp"), Path(temp, "Docs")
            (root / "sub").mkdir(parents=True)
            outside.mkdir()
            old, new, keep = root / "sub" / "old.tmp", root / "new.tmp", outside / "keep.txt"
            for f in (old, new, keep):
                f.write_bytes(b"x" * 10)
            ancient = time.time() - 10 * 86400
            os.utime(old, (ancient, ancient))
            os.utime(keep, (ancient, ancient))
            plan = w.plan_cleanup([root])
            self.assertEqual([i.path for i in plan.items], [str(old)])
            self.assertEqual(plan.total, 10)
            result = w.run_cleanup(plan.items, [root])
            self.assertEqual((result.removed, result.reported_bytes, result.skipped), (1, 10, 0))
            self.assertFalse(old.exists())
            self.assertFalse((root / "sub").exists(), "emptied sub-folder is tidied")
            self.assertTrue(root.exists() and new.exists() and keep.exists())

    def test_item_changed_after_planning_or_outside_roots_is_skipped(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp, "Temp")
            root.mkdir()
            f = root / "a.tmp"
            f.write_bytes(b"1")
            ancient = time.time() - 9 * 86400
            os.utime(f, (ancient, ancient))
            plan = w.plan_cleanup([root])
            os.utime(f, None)  # touched since the plan
            stray = Path(temp, "stray.tmp")
            stray.write_bytes(b"1")
            os.utime(stray, (ancient, ancient))
            result = w.run_cleanup(plan.items + [w.CleanupItem(str(stray), 1)], [root])
            self.assertEqual((result.removed, result.skipped), (0, 2))
            self.assertTrue(f.exists() and stray.exists())

    def test_symlinks_are_never_followed_or_deleted(self):
        with tempfile.TemporaryDirectory() as temp:
            root, target = Path(temp, "Temp"), Path(temp, "Real")
            root.mkdir()
            target.mkdir()
            (target / "save.dat").write_bytes(b"precious")
            os.symlink(target, root / "link", target_is_directory=True)
            ancient = time.time() - 9 * 86400
            os.utime(target / "save.dat", (ancient, ancient))
            plan = w.plan_cleanup([root])
            self.assertEqual(plan.items, [])
            self.assertTrue((target / "save.dat").exists())

    def test_never_touch_rule_is_respected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp, "Temp")
            (root / "mine").mkdir(parents=True)
            f = root / "mine" / "a.tmp"
            f.write_bytes(b"1")
            ancient = time.time() - 9 * 86400
            os.utime(f, (ancient, ancient))
            self.assertEqual(w.plan_cleanup([root], never_touch=[str(root / "mine")]).items, [])

    def test_roots_are_deduplicated(self):
        roots = w.cleanup_roots({"TEMP": "/a/Local/Temp", "TMP": "/a/Local/Temp", "LOCALAPPDATA": "/a/Local"})
        self.assertEqual(len(roots), 2)


class OptimizerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.backup = Path(self.tmp.name, "backup.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_apply_remembers_then_undo_restores_exact_previous_state(self):
        gm = reg_key(*w.GAME_MODE)
        dvr = reg_key(*w.DVR_STORE)
        reg = FakeRegistry({gm: (0, w.REG_DWORD)})  # game mode was explicitly off; recording value did not exist
        runner = FakeRunner({"getactivescheme": w.RunResult(0, "Power Scheme GUID: 381b4222-f694-41f0-9685-ff5bb260df2e  (Balanced)")})
        notes = w.apply_optimizer(reg, runner, {"game_mode", "background_recording", "power_plan"}, self.backup)
        self.assertEqual(reg.read(*w.GAME_MODE)[0], 1)
        self.assertEqual(reg.read(*w.DVR_STORE)[0], 0)
        self.assertEqual(reg.read(*w.DVR_CAPTURE)[0], 0)
        self.assertIn(["powercfg", "/setactive", w.HIGH_PERFORMANCE], runner.calls)
        self.assertTrue(w.has_backup(self.backup) and len(notes) == 3)
        undo = w.undo_optimizer(reg, runner, self.backup)
        self.assertEqual(reg.read(*w.GAME_MODE)[0], 0)
        self.assertIsNone(reg.read(*w.DVR_STORE))
        self.assertIsNone(reg.read(*w.DVR_CAPTURE))
        self.assertIn(["powercfg", "/setactive", "381b4222-f694-41f0-9685-ff5bb260df2e"], runner.calls)
        self.assertFalse(self.backup.exists())
        self.assertTrue(undo)

    def test_second_apply_keeps_the_original_backup(self):
        reg = FakeRegistry({reg_key(*w.GAME_MODE): (0, w.REG_DWORD)})
        runner = FakeRunner()
        w.apply_optimizer(reg, runner, {"game_mode"}, self.backup)
        w.apply_optimizer(reg, runner, {"game_mode"}, self.backup)
        saved = json.loads(self.backup.read_text())["registry"]
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["value"], 0)

    def test_read_state_reports_current_values_honestly(self):
        reg = FakeRegistry({reg_key(*w.GAME_MODE): (1, w.REG_DWORD)})
        runner = FakeRunner({"getactivescheme": w.RunResult(1, "")})
        states = {s.key: s for s in w.read_optimizer(reg, runner)}
        self.assertTrue(states["game_mode"].applied)
        self.assertFalse(states["background_recording"].applied)
        self.assertIn("Windows default", states["background_recording"].current)
        self.assertEqual(states["power_plan"].current, "Could not be read")

    def test_unreadable_power_plan_changes_nothing(self):
        runner = FakeRunner({"getactivescheme": w.RunResult(1, "")})
        notes = w.apply_optimizer(FakeRegistry(), runner, {"power_plan"}, self.backup)
        self.assertIn("nothing was changed", notes[0])
        self.assertEqual([c for c in runner.calls if "/setactive" in c], [])

    def test_undo_without_backup_is_a_no_op(self):
        self.assertEqual(w.undo_optimizer(FakeRegistry(), FakeRunner(), self.backup), ["Nothing to undo."])


TASKLIST = '''"System","4","Services","0","148 K"
"chrome.exe","1200","Console","1","1,204,500 K"
"explorer.exe","900","Console","1","80,000 K"
"Discord.exe","2200","Console","1","402,100 K"
"svchost.exe","800","Services","0","20,000 K"
"python.exe","77","Console","1","50,000 K"
"Game.exe","3300","Console","1","not a number"
'''


class MemoryTests(unittest.TestCase):
    def test_lists_only_user_apps_largest_first_without_core_or_self(self):
        runner = FakeRunner({"tasklist": w.RunResult(0, TASKLIST)})
        procs = w.list_processes(runner, own_pid=4242)
        self.assertEqual([(p.name, p.pid) for p in procs], [("chrome.exe", 1200), ("Discord.exe", 2200)])
        self.assertEqual(procs[0].kb, 1204500)

    def test_own_pid_is_excluded(self):
        runner = FakeRunner({"tasklist": w.RunResult(0, TASKLIST)})
        self.assertNotIn(2200, [p.pid for p in w.list_processes(runner, own_pid=2200)])

    def test_close_asks_politely_without_force(self):
        runner = FakeRunner({"taskkill": w.RunResult(0, "SUCCESS")})
        notes = w.close_processes(runner, [1200, "2200"])
        self.assertEqual(runner.calls, [["taskkill", "/PID", "1200"], ["taskkill", "/PID", "2200"]])
        self.assertTrue(all("/F" not in c for c in runner.calls))
        self.assertEqual(notes[0], (1200, "Asked to close."))

    def test_failure_message_is_passed_through(self):
        runner = FakeRunner({"taskkill": w.RunResult(1, "ERROR: Access is denied.\nmore")})
        self.assertEqual(w.close_processes(runner, [5])[0][1], "ERROR: Access is denied.")


class StartupTests(unittest.TestCase):
    def test_lists_run_keys_and_folder_and_toggles_only_user_entries(self):
        reg = FakeRegistry({
            reg_key(w.HKCU, w.RUN_KEY, "Discord"): ("C:\\d.exe", w.REG_SZ),
            reg_key(w.HKLM, w.RUN_KEY, "Driver"): ("C:\\drv.exe", w.REG_SZ),
            reg_key(w.HKCU, w.APPROVED + "\\Run", "Discord"): (bytes([3]) + bytes(11), w.REG_BINARY),
        })
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
            folder.mkdir(parents=True)
            (folder / "tool.lnk").write_bytes(b"x")
            (folder / "desktop.ini").write_bytes(b"x")
            entries = w.list_startup(reg, {"APPDATA": temp})
        by = {e.name: e for e in entries}
        self.assertEqual(set(by), {"Discord", "Driver", "tool.lnk"})
        self.assertFalse(by["Discord"].enabled)
        self.assertTrue(by["tool.lnk"].enabled and by["tool.lnk"].can_toggle)
        self.assertFalse(by["Driver"].can_toggle)
        w.set_startup_enabled(reg, by["Discord"], True)
        self.assertTrue(w.list_startup(reg, {})[0].enabled)
        value = reg.read(w.HKCU, w.APPROVED + "\\Run", "Discord")[0]
        self.assertEqual((len(value), value[0]), (12, 2))
        w.set_startup_enabled(reg, by["tool.lnk"], False)
        off = reg.read(w.HKCU, w.APPROVED + "\\StartupFolder", "tool.lnk")[0]
        self.assertEqual((len(off), off[0]), (12, 3))
        with self.assertRaises(ValueError):
            w.set_startup_enabled(reg, by["Driver"], False)
        # the entry itself is never deleted
        self.assertIsNotNone(reg.read(w.HKCU, w.RUN_KEY, "Discord"))


class CommandTests(unittest.TestCase):
    def test_validation(self):
        for bad in ("", "   ", "a\nb", "x" * 3000):
            self.assertTrue(w.validate_command(bad))
        self.assertEqual(w.validate_command("ipconfig /all"), "")

    def test_runs_exactly_the_typed_line_through_cmd(self):
        runner = FakeRunner({"cmd.exe": w.RunResult(0, "hello")})
        result = w.run_command(runner, "  echo hello  ")
        self.assertEqual(runner.calls, [["cmd.exe", "/d", "/s", "/c", "echo hello"]])
        self.assertEqual(result.output, "hello")
        with self.assertRaises(ValueError):
            w.run_command(runner, "")
        self.assertEqual(len(runner.calls), 1)

    def test_presets_are_valid(self):
        self.assertTrue(all(w.validate_command(cmd) == "" for _t, cmd in w.PRESETS))


class AssociationTests(unittest.TestCase):
    def test_user_choice_beats_default_and_extension_is_normalised(self):
        reg = FakeRegistry({
            reg_key(w.HKCU, r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.zip\UserChoice", "ProgId"): ("7-Zip.zip", w.REG_SZ),
            reg_key(w.HKCR, ".zip", ""): ("CompressedFolder", w.REG_SZ),
            reg_key(w.HKCR, "7-Zip.zip", ""): ("7z Archive", w.REG_SZ),
            reg_key(w.HKCR, r"7-Zip.zip\shell\open\command", ""): ('"C:\\7z.exe" "%1"', w.REG_SZ),
        })
        a = w.read_association(reg, "ZIP")
        self.assertEqual((a.ext, a.prog_id, a.app, a.source), (".zip", "7-Zip.zip", "7z Archive", "You chose this in Windows"))
        self.assertIn("7z.exe", a.command)

    def test_default_none_and_bad_input(self):
        reg = FakeRegistry({reg_key(w.HKCR, ".json", ""): ("jsonfile", w.REG_SZ)})
        self.assertEqual(w.read_association(reg, ".json").source, "Windows default")
        self.assertEqual(w.read_association(reg, ".nothing").app, "No app is set")
        for bad in ("", "..", "a b", "x" * 40):
            with self.assertRaises(ValueError):
                w.read_association(reg, bad)
        self.assertEqual(w.normalize_extension("*.ESP"), ".esp")


class JunctionTests(unittest.TestCase):
    def test_scan_remove_keeps_target_and_refuses_real_folders(self):
        with tempfile.TemporaryDirectory() as temp:
            games, real = Path(temp, "Games"), Path(temp, "Elsewhere")
            games.mkdir()
            real.mkdir()
            (real / "data.bin").write_bytes(b"d")
            os.symlink(real, games / "Skyrim", target_is_directory=True)
            os.symlink(Path(temp, "gone"), games / "Broken", target_is_directory=True)
            (games / "RealFolder").mkdir()
            found = {Path(l.path).name: l for l in w.scan_links(games)}
            self.assertEqual(set(found), {"Skyrim", "Broken"})
            self.assertTrue(found["Skyrim"].exists and not found["Broken"].exists)
            with self.assertRaises(ValueError):
                w.remove_link(games / "RealFolder")
            self.assertTrue((games / "RealFolder").exists())
            target, still = w.remove_link(games / "Skyrim")
            self.assertTrue(still and (real / "data.bin").exists())
            self.assertFalse(os.path.lexists(games / "Skyrim"))

    def test_create_validation_and_runner_use(self):
        with tempfile.TemporaryDirectory() as temp:
            target, parent = Path(temp, "Big"), Path(temp, "Lib")
            target.mkdir()
            parent.mkdir()
            link = parent / "Game"

            class MakeLink:
                def run(self, args, **kw):
                    self.args = args
                    os.symlink(args[-1], args[-2], target_is_directory=True)
                    return w.RunResult(0, "")
            maker = MakeLink()
            self.assertEqual(w.create_junction(maker, link, target), str(link))
            self.assertEqual(maker.args[:4], ["cmd.exe", "/d", "/c", "mklink"])
            self.assertIn("exists", w.check_new_link(link, target))
            self.assertIn("does not exist", w.check_new_link(parent / "x", Path(temp, "nope")))
            with self.assertRaises(ValueError):
                w.create_junction(FakeRunner(), parent / "Two", Path(temp, "nope"))
            self.assertIn("Never Touch", w.check_new_link(parent / "Prot", target, never_touch=[str(parent)]))


if __name__ == "__main__":
    unittest.main()
