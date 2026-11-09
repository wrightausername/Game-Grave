"""Exhume, Black Box, Autopsy, Soulbind and Squad Sync engines (no Qt)."""
import json
import os
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from gg_desktop import autopsy, black_box, exhume, soulbind, squad_sync
from gg_desktop.winpc import RunResult

DISPLAY = exhume.DISPLAY_CLASS


class FakeRegistry:
    def __init__(self, data):
        self.data = data

    def read(self, hive, path, name):
        return self.data.get((hive, path.lower(), name))


class FakeRunner:
    def __init__(self, result):
        self.result, self.calls = result, []

    def run(self, args, **kw):
        self.calls.append(list(args))
        return self.result


def reg(index, desc, version, provider="NVIDIA"):
    path = (DISPLAY + "\\" + f"{index:04d}").lower()
    return {("HKLM", path, "DriverDesc"): (desc, 1), ("HKLM", path, "DriverVersion"): (version, 1),
            ("HKLM", path, "DriverDate"): ("10-1-2024", 1), ("HKLM", path, "ProviderName"): (provider, 1)}


# ------------------------------------------------------------------ Exhume
class Exhume(unittest.TestCase):
    def test_reads_real_adapters_and_skips_basic_display(self):
        data = reg(0, "NVIDIA GeForce RTX 4070", "32.0.15.6094") | reg(1, "Microsoft Basic Display Adapter", "10.0.1")
        drivers = exhume.read_drivers(FakeRegistry(data))
        self.assertEqual([d.adapter for d in drivers], ["NVIDIA GeForce RTX 4070"])
        self.assertEqual(drivers[0].friendly_version, "560.94")
        self.assertEqual(drivers[0].vendor, "nvidia")
        self.assertEqual(exhume.read_drivers(None), [])

    def test_other_vendors_keep_the_windows_version(self):
        amd = exhume.Driver("AMD Radeon RX 7800 XT", "31.0.24027.1012", "", "Advanced Micro Devices, Inc.")
        self.assertEqual(amd.friendly_version, "31.0.24027.1012")
        self.assertEqual(amd.vendor, "amd")
        self.assertEqual(exhume.vendor_page(amd)[0], "AMD")

    def test_history_records_marks_and_advises(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "h.json"
            old = exhume.Driver("RTX", "32.0.15.5612", "", "NVIDIA")
            new = exhume.Driver("RTX", "32.0.15.6094", "", "NVIDIA")
            entries = exhume.record([], [old], now="2026-10-01 10:00")
            self.assertTrue(exhume.mark_known_good(entries, old))
            entries = exhume.record(entries, [new], now="2026-11-01 10:00")
            exhume.save_history(path, entries)
            loaded = exhume.load_history(path)
            self.assertEqual([e.version for e in loaded], ["32.0.15.5612", "32.0.15.6094"])
            text = " ".join(exhume.advice(loaded, new))
            self.assertIn("Last known good: 556.12", text)
            self.assertIn("Roll Back Driver", text)
            self.assertNotIn("safe", text.casefold())
            fresh = " ".join(exhume.advice([], new))
            self.assertIn("nothing to go back to", fresh)
            self.assertEqual(exhume.load_history(Path(temp) / "missing.json"), [])


# ------------------------------------------------------------------ Black Box
EVENT = """<Event xmlns='http://schemas.microsoft.com/win/2004/08/events/event'><System><Provider Name='Application Error'/>
<EventID>1000</EventID><TimeCreated SystemTime='{when}'/></System><EventData>
<Data>SkyrimSE.exe</Data><Data>1.6.1170.0</Data><Data>65f3</Data><Data>{module}</Data><Data>2.0.0.0</Data><Data>0</Data>
<Data>c0000005</Data><Data>0x1</Data><Data>0x10</Data><Data>0x1</Data><Data>{app}</Data><Data>{mpath}</Data>
<Data>abc-123</Data></EventData></Event>"""


class BlackBox(unittest.TestCase):
    def xml(self, when="2026-11-08T20:15:00.000Z", module="po3_Tweaks.dll", app="D:\\Games\\Skyrim\\SkyrimSE.exe",
            mpath="D:\\Games\\Skyrim\\Data\\SKSE\\Plugins\\po3_Tweaks.dll"):
        return EVENT.format(when=when, module=module, app=app, mpath=mpath)

    def test_parses_events_and_matches_only_by_install_folder(self):
        text = self.xml() + self.xml(when="2026-11-07T10:00:00Z", app="C:\\Other\\SkyrimSE.exe")
        games = [SimpleNamespace(name="Skyrim Special Edition", install_path="D:\\Games\\Skyrim")]
        crashes = black_box.read_crashes(FakeRunner(RunResult(0, text)), games)
        self.assertEqual(len(crashes), 2)
        self.assertEqual(crashes[0].game, "Skyrim Special Edition")
        self.assertEqual(crashes[1].game, "")
        self.assertIn("access violation", crashes[0].exception_text())
        self.assertIn("inside the game's folder", crashes[0].module_note())
        self.assertIn("Nothing was changed", black_box.summary(crashes))

    def test_report_names_are_valid_windows_file_names(self):
        crash = black_box.Crash(datetime(2026, 11, 8, 20, 15), "x.exe", "", "", "", "", "", "",
                                game='Warhammer 40,000: Space Marine 2 / "GOTY"')
        name = black_box.report_name(crash)
        self.assertEqual(name, "black-box-Warhammer-40-000-Space-Marine-2-GOTY-20261108-2015.txt")
        self.assertFalse(set(name) & set('<>:"/\\|?*'))

    def test_query_uses_the_application_error_log_only(self):
        args = black_box.query_args(50)
        self.assertEqual(args[:3], ["wevtutil", "qe", "Application"])
        self.assertIn("/c:50", args)
        self.assertIn("EventID=1000", args[3])

    def test_windows_module_note_points_back_to_changes(self):
        crash = black_box.parse_events(self.xml(module="ntdll.dll", mpath="C:\\Windows\\System32\\ntdll.dll"))[0]
        self.assertIn("a Windows file", crash.module_note())

    def test_log_errors_are_raised(self):
        with self.assertRaises(OSError):
            black_box.read_crashes(FakeRunner(RunResult(5, "Access is denied.")), [])

    def test_recent_changes_window_and_report_scrubbing(self):
        with tempfile.TemporaryDirectory() as temp:
            game = Path(temp) / "Skyrim"
            (game / "Data").mkdir(parents=True)
            recent, old = game / "Data" / "new.esp", game / "Data" / "old.esp"
            recent.write_bytes(b"1")
            old.write_bytes(b"2")
            crash_time = datetime.now()
            past = (crash_time - timedelta(days=30)).timestamp()
            os.utime(old, (past, past))
            crash = black_box.Crash(crash_time, "SkyrimSE.exe", "1", "SkyrimSE.exe", "1", "c0000005",
                                    str(game / "SkyrimSE.exe"), "", game="Skyrim", game_path=str(game))
            history = [exhume.Entry("RTX", "32.0.15.6094", "", "NVIDIA",
                                    (crash_time - timedelta(days=1)).strftime("%Y-%m-%d %H:%M"), "")]
            findings = black_box.investigate(crash, history)
            self.assertEqual([Path(c.path).name for c in findings.changes], ["new.esp"])
            self.assertEqual(len(findings.drivers), 1)
            env = {"USERPROFILE": "C:\\Users\\Alexander", "USERNAME": "Alexander", "COMPUTERNAME": "ALEX-PC"}
            findings.changes[0].path = "C:\\Users\\Alexander\\Mods\\new.esp"
            text = black_box.report_text(findings, scrub=black_box.scrubber(env))
            self.assertNotIn("Alexander", text)
            self.assertIn("%USERPROFILE%\\Mods\\new.esp", text)
            self.assertIn("lead, not proof", text)
            self.assertIn("560.94", text)


# ------------------------------------------------------------------ Autopsy
class Autopsy(unittest.TestCase):
    def csv(self, ms, column="MsBetweenPresents", count=200):
        return f"Application,ProcessID,{column}\n" + "".join(f"game.exe,1,{ms}\n" for _ in range(count))

    def test_summary_and_columns(self):
        times = autopsy.frame_times(self.csv(10.0))
        cap = autopsy.summarize(times, label="Before", game="game.exe", taken="t")
        self.assertEqual((cap.avg_fps, cap.low1_fps, cap.stutters, cap.frames), (100.0, 100.0, 0, 200))
        self.assertEqual(len(autopsy.frame_times(self.csv(5.0, column="FrameTime"))), 200)
        with self.assertRaises(ValueError):
            autopsy.frame_times("a,b\n1,2\n")
        with self.assertRaises(ValueError):
            autopsy.summarize([10.0] * 5, label="x", game="g")

    def test_stutters_and_lows(self):
        times = [10.0] * 190 + [50.0] * 10
        cap = autopsy.summarize(times, label="x", game="g")
        self.assertEqual(cap.stutters, 10)
        self.assertEqual(cap.low1_fps, 20.0)

    def test_verdicts_are_plain_and_honest(self):
        base = autopsy.Capture("Before", "g", "t", 60, 6000, 72.0, 50.0, 13.0, 4)
        same = autopsy.Capture("After", "g", "t", 60, 6000, 73.0, 50.5, 13.0, 4)
        better = autopsy.Capture("After", "g", "t", 60, 6000, 81.0, 60.0, 12.0, 1)
        worse = autopsy.Capture("After", "g", "t", 60, 6000, 60.0, 40.0, 16.0, 9)
        self.assertIn("no real difference", autopsy.verdict(base, same)[0])
        self.assertTrue(autopsy.verdict(base, better)[0].startswith("Verdict: better"))
        self.assertTrue(autopsy.verdict(base, worse)[0].startswith("Verdict: worse"))
        self.assertIn("Stutters: 4 → 1.", autopsy.verdict(base, better))
        mixed = autopsy.Capture("After", "g", "t", 60, 6000, 80.0, 40.0, 12.0, 4)
        self.assertIn("mixed", autopsy.verdict(base, mixed)[0])

    def test_capture_args_and_storage(self):
        args = autopsy.capture_args("pm.exe", "game.exe", "C:/out.csv", 60)
        self.assertEqual(args[:3], ["pm.exe", "--process_name", "game.exe"])
        self.assertIn("--terminate_after_timed", args)
        with tempfile.TemporaryDirectory() as temp:
            cap = autopsy.Capture("Before", "g", "t", 60, 100, 70.0, 50.0, 14.0, 2)
            autopsy.save_capture(temp, cap)
            self.assertEqual(autopsy.load_captures(temp), [cap])
            (Path(temp) / "PresentMon-2.3.1-x64.exe").write_bytes(b"")
            self.assertTrue(autopsy.find_presentmon([temp], env={}).endswith("PresentMon-2.3.1-x64.exe"))

    def test_permission_failure_explains_what_to_do(self):
        text = autopsy.failure_text(RunResult(1, "Error: access denied"))
        self.assertIn("Performance Log Users", text)


# ------------------------------------------------------------------ Soulbind
class Soulbind(unittest.TestCase):
    def test_profile_is_cleaned_and_round_trips(self):
        with tempfile.TemporaryDirectory() as temp:
            path = soulbind.save_profile(Path(temp) / "p.json", {"motion_blur": True, "evil": "rm -rf", "subtitles": 1})
            prefs = soulbind.import_profile(path)
            self.assertTrue(prefs["motion_blur"])
            self.assertFalse(prefs["subtitles"])
            self.assertNotIn("evil", prefs)
            bad = Path(temp) / "bad.json"
            bad.write_text('{"app": "other"}')
            with self.assertRaises(ValueError):
                soulbind.import_profile(bad)

    def test_set_switches_keeps_other_lines(self):
        text = "[Core.Log]\nLogX=1\n\n[SystemSettings]\nr.MotionBlurQuality=4\nr.Other=2\n\n[Audio]\nA=1\n"
        out = soulbind.set_switches(text, {"r.MotionBlurQuality": "0", "r.LensFlareQuality": "0"})
        self.assertIn("r.MotionBlurQuality=0", out)
        self.assertNotIn("r.MotionBlurQuality=4", out)
        self.assertIn("r.Other=2", out)
        self.assertLess(out.index("r.LensFlareQuality=0"), out.index("[Audio]"))
        self.assertIn("[Core.Log]\nLogX=1", out)
        fresh = soulbind.set_switches("", {"r.FilmGrain": "0"})
        self.assertEqual(fresh, "[SystemSettings]\nr.FilmGrain=0\n")
        self.assertEqual(soulbind.set_switches(out, {"r.MotionBlurQuality": "0", "r.LensFlareQuality": "0"}), out)

    def test_finds_unreal_games_and_skips_the_launcher(self):
        with tempfile.TemporaryDirectory() as temp:
            local = Path(temp) / "Local"
            for project in ("Palworld", "EpicGamesLauncher"):
                folder = local / project / "Saved" / "Config" / "Windows"
                folder.mkdir(parents=True)
                (folder / "GameUserSettings.ini").write_text("[x]")
            docs = Path(temp) / "User" / "Documents" / "My Games" / "Hogwarts Legacy" / "Saved" / "Config" / "WindowsNoEditor"
            docs.mkdir(parents=True)
            (docs / "GameUserSettings.ini").write_text("[x]")
            targets = soulbind.find_targets({"LOCALAPPDATA": str(local), "USERPROFILE": str(Path(temp) / "User")})
            self.assertEqual([t.name for t in targets], ["Hogwarts Legacy", "Palworld"])

    def test_apply_and_restore_existing_file(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "Game" / "Saved" / "Config" / "Windows"
            folder.mkdir(parents=True)
            engine = folder / "Engine.ini"
            engine.write_text("[Core.System]\nPaths=x\n")
            target = soulbind.Target("Game", str(folder))
            prefs = soulbind.clean_profile({"motion_blur": True, "film_grain": True, "subtitles": True})
            self.assertEqual(soulbind.score(prefs), (2, 3))
            result = soulbind.apply(target, prefs, Path(temp) / "backups")
            self.assertIn("r.MotionBlurQuality=0", engine.read_text())
            self.assertIn("r.FilmGrain=0", engine.read_text())
            self.assertFalse(result.created)
            soulbind.apply(target, prefs, Path(temp) / "backups")  # a second apply keeps the first original
            self.assertTrue(soulbind.has_backup(target, Path(temp) / "backups"))
            self.assertIn("Restored", soulbind.restore(target, Path(temp) / "backups"))
            self.assertEqual(engine.read_text(), "[Core.System]\nPaths=x\n")
            with self.assertRaises(ValueError):
                soulbind.restore(target, Path(temp) / "backups")

    def test_restore_removes_only_an_unchanged_created_file(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "G"
            folder.mkdir()
            target = soulbind.Target("G", str(folder))
            prefs = soulbind.clean_profile({"lens_flare": True})
            soulbind.apply(target, prefs, Path(temp) / "b")
            engine = folder / "Engine.ini"
            engine.write_text(engine.read_text() + "r.Game=1\n")
            with self.assertRaises(ValueError):
                soulbind.restore(target, Path(temp) / "b")
            self.assertTrue(engine.exists())
            other = soulbind.Target("G2", str(Path(temp) / "G2"))
            Path(other.folder).mkdir()
            soulbind.apply(other, prefs, Path(temp) / "b")
            soulbind.restore(other, Path(temp) / "b")
            self.assertFalse(Path(other.engine_ini).exists())

    def test_utf16_and_crlf_files_keep_their_encoding_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as temp:
            for encoding, bom, newline in (("utf-16-le", b"\xff\xfe", "\r\n"), ("utf-8", b"", "\r\n"),
                                            ("utf-8", b"\xef\xbb\xbf", "\n")):
                folder = Path(temp) / (encoding + str(len(bom)) + str(len(newline)))
                folder.mkdir()
                original = bom + "[systemsettings]\nr.Old=1\n".replace("\n", newline).encode(encoding)
                (folder / "Engine.ini").write_bytes(original)
                target = soulbind.Target("G", str(folder))
                soulbind.apply(target, soulbind.clean_profile({"motion_blur": True}), Path(temp) / "b")
                data = (folder / "Engine.ini").read_bytes()
                self.assertTrue(data.startswith(bom))
                text = data[len(bom):].decode(encoding)
                self.assertIn("r.MotionBlurQuality=0" + newline, text)
                self.assertEqual(text.count("[systemsettings]"), 1)
                self.assertEqual(text.count("[SystemSettings]"), 0)
                soulbind.restore(target, Path(temp) / "b")
                self.assertEqual((folder / "Engine.ini").read_bytes(), original)

    def test_unknown_encoding_is_left_alone(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / "Engine.ini").write_bytes(b"\x81\x82\xff[x]")
            with self.assertRaises(ValueError):
                soulbind.apply(soulbind.Target("G", temp), soulbind.clean_profile({"motion_blur": True}), Path(temp) / "b")
            self.assertEqual((Path(temp) / "Engine.ini").read_bytes(), b"\x81\x82\xff[x]")

    def test_nothing_to_apply_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                soulbind.apply(soulbind.Target("G", temp), soulbind.clean_profile({"subtitles": True}), temp)


# ------------------------------------------------------------------ Squad Sync
MODS_YML = """- manifestVersion: 1
  name: BepInEx-BepInExPack
  authorName: BepInEx
  displayName: BepInExPack
  versionNumber:
    major: 5
    minor: 4
    patch: 2100
  enabled: true
  dependencies: []
- manifestVersion: 1
  name: notnotnotswipez-MoreCompany
  authorName: notnotnotswipez
  dependencies:
    - BepInEx-BepInExPack-5.4.2100
  versionNumber:
    major: 1
    minor: 9
    patch: 1
  enabled: true
- manifestVersion: 1
  name: x753-More_Suits
  versionNumber:
    major: 1
    minor: 4
    patch: 3
  enabled: false
"""


class SquadSync(unittest.TestCase):
    def test_parses_manager_mod_lists(self):
        mods = squad_sync.parse_mod_list(MODS_YML)
        self.assertEqual([(m.name, m.version, m.enabled) for m in mods],
                         [("BepInEx-BepInExPack", "5.4.2100", True), ("notnotnotswipez-MoreCompany", "1.9.1", True),
                          ("x753-More_Suits", "1.4.3", False)])
        self.assertEqual(mods[1].page, "https://thunderstore.io/package/notnotnotswipez/MoreCompany/")

    def test_code_round_trip_carries_only_turned_on_mods(self):
        mods = squad_sync.parse_mod_list(MODS_YML)
        code = squad_sync.make_code("LethalCompany", "Jake", mods)
        self.assertTrue(code.startswith("GGSQ1."))
        squad = squad_sync.read_code("  " + code[:20] + "\n" + code[20:] + " ")
        self.assertEqual(squad.game, "LethalCompany")
        self.assertEqual(squad_sync.read_code("here you go:\n" + code + "\nsee you at 8").mods, squad.mods)
        self.assertEqual(squad_sync.read_code("code " + code[:30] + "\n" + code[30:]).mods, squad.mods)
        self.assertEqual([m.name for m in squad.mods], ["BepInEx-BepInExPack", "notnotnotswipez-MoreCompany"])

    def test_bad_codes_are_rejected(self):
        for bad in ("", "hello", "GGSQ1.!!!!", "GGSQ1." + "A" * 70000):
            with self.assertRaises(ValueError):
                squad_sync.read_code(bad)

    def test_oversized_squad_configs_are_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "big.r2z"
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("export.r2x", squad_sync.export_r2x("x", [squad_sync.Mod("A-B", "1.0.0")]))
                archive.writestr("BepInEx/config/huge.cfg", b"0" * (squad_sync.CONFIG_LIMIT_BYTES + 1))
                archive.writestr("BepInEx/config/../../evil.cfg", b"x")
            with self.assertRaises(ValueError):
                squad_sync.read_squad_configs(path)

    def test_compare(self):
        host = [squad_sync.Mod("A-One", "1.0.0"), squad_sync.Mod("B-Two", "2.0.0"), squad_sync.Mod("C-Three", "1.0.0"),
                squad_sync.Mod("D-Four", "1.0.0")]
        mine = [squad_sync.Mod("A-One", "1.0.0"), squad_sync.Mod("B-Two", "1.5.0"), squad_sync.Mod("D-Four", "1.0.0", False),
                squad_sync.Mod("E-Extra", "1.0.0")]
        result = squad_sync.compare(host, mine)
        self.assertEqual([m.name for m in result.missing], ["C-Three"])
        self.assertEqual([(m.name, v) for m, v in result.wrong_version], [("B-Two", "1.5.0")])
        self.assertEqual([m.name for m in result.extra], ["E-Extra"])
        self.assertEqual([m.name for m in result.turned_off], ["D-Four"])
        self.assertEqual(result.summary(), "1 match. 1 missing, 1 wrong version, 1 turned off, 1 extra.")
        self.assertTrue(squad_sync.compare(host[:1], host[:1]).matched)

    def test_profiles_squad_file_and_configs(self):
        with tempfile.TemporaryDirectory() as temp:
            profile = Path(temp) / "r2modmanPlus-local" / "LethalCompany" / "profiles" / "Friday"
            (profile / "BepInEx" / "config").mkdir(parents=True)
            (profile / "mods.yml").write_text(MODS_YML)
            (profile / "BepInEx" / "config" / "MoreCompany.cfg").write_text("players = 8")
            (profile / "BepInEx" / "config" / "dump.dll").write_bytes(b"x")
            profiles = squad_sync.find_profiles({"APPDATA": temp})
            self.assertEqual([(p.manager, p.game, p.name) for p in profiles], [("r2modman", "LethalCompany", "Friday")])
            mods = squad_sync.read_profile(profiles[0])
            configs = squad_sync.collect_configs(profiles[0].folder)
            self.assertEqual(list(configs), ["BepInEx/config/MoreCompany.cfg"])
            out = squad_sync.write_squad_file(Path(temp) / "Squad - Jake.r2z", "Squad - Jake", mods, configs)
            with zipfile.ZipFile(out) as archive:
                text = archive.read("export.r2x").decode()
                self.assertIn("profileName: \"Squad - Jake\"", text)
                self.assertIn("BepInEx/config/MoreCompany.cfg", archive.namelist())
            squad = squad_sync.read_squad_file(out)
            self.assertEqual(squad.label, "Squad - Jake")
            # The disabled mod stays out of the squad, and turned-on state is written as it was.
            self.assertEqual([m.version for m in squad.mods], ["5.4.2100", "1.9.1"])
            self.assertTrue(all(m.enabled for m in squad.mods))
            self.assertIn("enabled: false", text)
            self.assertEqual(list(squad_sync.read_squad_configs(out)), ["BepInEx/config/MoreCompany.cfg"])
            self.assertEqual(squad_sync.safe_name('Ja/ke:"*'), "Jake")


if __name__ == "__main__":
    unittest.main()
