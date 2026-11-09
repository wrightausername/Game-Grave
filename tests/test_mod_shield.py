import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from gg_desktop import mod_shield as ms
from gg_desktop.winpc import RunResult


class FakeRunner:
    def __init__(self, result):
        self.result, self.calls = result, []

    def run(self, args, **kw):
        self.calls.append((list(args), kw))
        return self.result


def write(path, data=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


class Classify(unittest.TestCase):
    def level(self, path, hidden=False):
        verdict = ms.classify(path, "C:/Mods", hidden=hidden)
        return verdict[0] if verdict else None

    def test_ordinary_mod_files_are_not_listed(self):
        for name in ("Mod.esp", "textures/rock.dds", "readme.txt", "meshes/a.nif", "mod.jar", "config.ini", "a.pak"):
            self.assertIsNone(ms.classify("C:/Mods/" + name, "C:/Mods"), name)

    def test_programs_and_scripts_are_check_first(self):
        for name in ("tool.exe", "setup.msi", "run.bat", "go.cmd", "x.ps1", "y.vbs", "link.lnk", "patch.reg", "a.scr"):
            self.assertEqual(self.level("C:/Mods/" + name), ms.CHECK_FIRST, name)

    def test_disguised_names_are_named_as_such(self):
        for name in ("readme.txt.exe", "preview.png.scr", "Mod.esp.bat", "photo\u202egpj.exe"):
            level, kind, _reason = ms.classify("C:/Mods/" + name, "C:/Mods")
            self.assertEqual((level, kind), (ms.CHECK_FIRST, "Disguised name"), name)

    def test_hidden_program_is_called_out(self):
        self.assertEqual(ms.classify("C:/Mods/a.exe", "C:/Mods", hidden=True)[1], "Hidden program")
        self.assertIsNone(ms.classify("C:/Mods/a.esp", "C:/Mods", hidden=True))

    def test_libraries_depend_on_where_they_are(self):
        self.assertEqual(self.level("C:/Skyrim/Data/SKSE/Plugins/po3.dll"), ms.EXPECTED)
        self.assertEqual(self.level("C:\\Game\\BepInEx\\plugins\\More.dll"), ms.EXPECTED)
        self.assertEqual(self.level("C:/Game/dxgi.dll"), ms.NOTE)
        self.assertEqual(ms.classify("C:/Game/dxgi.dll", "C:/Game")[1], "Proxy loader")
        self.assertEqual(ms.classify("C:/Mods/random/helper.dll", "C:/Mods")[1], "Code library")

    def test_no_reason_calls_anything_safe_or_malware(self):
        names = ("a.exe", "a.txt.exe", "a.bat", "x/skse/plugins/a.dll", "dxgi.dll", "b.dll", "a\u202eexe.txt")
        for name in names:
            _level, kind, reason = ms.classify("C:/Mods/" + name, "C:/Mods", hidden=True)
            text = (kind + " " + reason).casefold()
            self.assertNotIn("safe", text)
            self.assertNotIn("malware", text)
            self.assertNotIn("virus", text)


class Scan(unittest.TestCase):
    def test_lists_only_what_stands_out_and_changes_nothing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "Mods"
            esp = write(root / "Cool" / "Cool.esp", b"plugin")
            exe = write(root / "Cool" / "update.exe", b"MZ fake")
            write(root / "Cool" / "readme.txt.exe", b"MZ")
            write(root / "SKSE" / "Plugins" / "a.dll", b"dll")
            before = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in root.rglob("*") if p.is_file()}
            report = ms.scan([root])
            after = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in root.rglob("*") if p.is_file()}
            self.assertEqual(before, after)
            self.assertEqual(report.files_checked, 4)
            self.assertEqual(report.count(ms.CHECK_FIRST), 2)
            self.assertEqual(report.count(ms.EXPECTED), 1)
            self.assertEqual(report.findings[0].level, ms.CHECK_FIRST)
            program = next(f for f in report.findings if f.name == "update.exe")
            self.assertEqual(program.sha256, hashlib.sha256(b"MZ fake").hexdigest())
            self.assertEqual(program.size, 7)
            loader = next(f for f in report.findings if f.level == ms.EXPECTED)
            self.assertEqual(loader.sha256, "")
            self.assertTrue(esp.exists() and exe.exists())
            self.assertIn("Nothing was changed", report.summary())
            self.assertIn("2 to check first", report.summary())

    def test_nested_and_missing_roots_are_folded(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "A" / "B").mkdir(parents=True)
            roots = ms.unique_roots([root / "A" / "B", root / "A", root / "missing", "", None])
            self.assertEqual(roots, [Path(os.path.abspath(root / "A"))])

    def test_mod_roots_come_from_the_scan_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            a = Path(temp) / "A"
            a.mkdir()
            inventory = SimpleNamespace(mods=[SimpleNamespace(path=str(a)), SimpleNamespace(path=str(a / "gone"))])
            self.assertEqual(ms.mod_roots(inventory), [Path(os.path.abspath(a))])
            self.assertEqual(ms.mod_roots(SimpleNamespace(mods=None)), [])

    def test_limit_and_cancel(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for i in range(10):
                write(root / f"f{i}.txt")
            report = ms.scan([root], limit=5)
            self.assertTrue(report.truncated)
            self.assertIn("stopped at", report.summary())
            stopped = ms.scan([root], canceled=lambda: True)
            self.assertTrue(stopped.canceled)
            self.assertIn("Stopped", stopped.summary())

    @unittest.skipIf(not hasattr(os, "symlink"), "no symlinks")
    def test_links_are_not_followed(self):
        with tempfile.TemporaryDirectory() as temp:
            root, outside = Path(temp) / "Mods", Path(temp) / "Outside"
            root.mkdir()
            write(outside / "evil.exe")
            try:
                os.symlink(outside, root / "link", target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks not permitted")
            report = ms.scan([root])
            self.assertEqual(report.findings, [])
            self.assertEqual(report.links_skipped, 1)

    def test_big_files_are_not_hashed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = write(Path(temp) / "a.exe", b"12345")
            self.assertEqual(ms.sha256_file(path, limit=4), "")
            self.assertEqual(ms.sha256_file(path), hashlib.sha256(b"12345").hexdigest())
            self.assertEqual(ms.sha256_file(Path(temp) / "missing.exe"), "")


class Lookup(unittest.TestCase):
    def test_virustotal_url_holds_only_the_fingerprint(self):
        digest = "a" * 64
        self.assertEqual(ms.virustotal_url(digest), "https://www.virustotal.com/gui/file/" + digest)
        for bad in ("", "abc", "A" * 64, "a" * 63 + "/", "../" + "a" * 61):
            with self.assertRaises(ValueError):
                ms.virustotal_url(bad)


class Defender(unittest.TestCase):
    def test_finds_the_newest_platform_copy_then_the_classic_one(self):
        with tempfile.TemporaryDirectory() as temp:
            data, programs = Path(temp) / "ProgramData", Path(temp) / "Program Files"
            write(programs / "Windows Defender" / "MpCmdRun.exe")
            env = {"PROGRAMDATA": str(data), "PROGRAMFILES": str(programs)}
            self.assertEqual(ms.find_defender(env), str(programs / "Windows Defender" / "MpCmdRun.exe"))
            platform = data / "Microsoft" / "Windows Defender" / "Platform"
            write(platform / "4.18.2111.5-0" / "MpCmdRun.exe")
            newest = write(platform / "4.18.24090.11-0" / "MpCmdRun.exe")
            self.assertEqual(ms.find_defender(env), str(newest))
            self.assertEqual(ms.find_defender({}), "")

    def test_scan_never_lets_defender_act(self):
        runner = FakeRunner(RunResult(0, "Scan starting...\nScan finished.\nScanning C:\\Mods found no threats.\n"))
        result = ms.defender_scan(runner, "C:/MpCmdRun.exe", "C:/Mods")
        args = runner.calls[0][0]
        self.assertEqual(args, ["C:/MpCmdRun.exe", "-Scan", "-ScanType", "3", "-File", "C:/Mods", "-DisableRemediation"])
        self.assertEqual(result.status, "clean")
        self.assertIn("no threats in this scan", result.line())

    def test_threats_are_listed_by_name(self):
        out = ("Scan starting...\nScan finished.\nScanning C:\\Mods found 1 threats.\n"
               "Threat                  : Trojan:Win32/Fake!ml\nResources               : 1 total\n"
               "    file                : C:\\Mods\\Cool\\update.exe\n")
        result = ms.defender_scan(FakeRunner(RunResult(2, out)), "x.exe", "C:/Mods")
        self.assertEqual(result.status, "threats")
        self.assertEqual(result.threats, ["Trojan:Win32/Fake!ml"])
        self.assertEqual(result.files, ["C:\\Mods\\Cool\\update.exe"])
        self.assertIn("1 threat:", result.line())

    def test_errors_and_missing_tool_are_said_plainly(self):
        self.assertEqual(ms.defender_scan(FakeRunner(RunResult(2, "Failed")), "x.exe", "C:/Mods").status, "error")
        timed = ms.defender_scan(FakeRunner(RunResult(-1, "", timed_out=True)), "x.exe", "C:/Mods")
        self.assertEqual(timed.status, "error")
        self.assertIn("could not finish", timed.line())
        missing = ms.defender_scan(FakeRunner(RunResult(0, "")), "", "C:/Mods")
        self.assertEqual(missing.status, "unavailable")

    def test_activity_text_combines_both(self):
        report = ms.ShieldReport(roots=["C:/Mods"], files_checked=3)
        text = ms.activity_text(report, [ms.DefenderResult("clean", "C:/Mods")])
        self.assertIn("Checked 3 files in 1 folder.", text)
        self.assertIn("no threats", text)


if __name__ == "__main__":
    unittest.main()
