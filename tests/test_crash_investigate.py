"""Crash investigation: every kind of cause is found from the clues Windows and games really leave."""
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from gg_desktop import crash_investigate as ci

NOW = datetime(2026, 11, 18, 12, 0)
T = NOW - timedelta(days=2)
FOLDER = r"C:\Games\Night City"
EXE = FOLDER + r"\bin\x64\NightCity.exe"
GAME = SimpleNamespace(name="Night City", install_path=FOLDER, app_id="1091500")


def crash(module, code="c0000005", when=T, path=EXE):
    return ("Application Error", 1000, when,
            ["NightCity.exe", "1.0", "0", module, "1.0", "0", code, "0x123", "1", "2", path])


def base(**extra):
    values = dict(exes={"nightcity.exe"}, free={"C:\\": (300 * 1024 ** 3, 1000 * 1024 ** 3)}, page_file="?:\\pagefile.sys",
                  memory=(32 * 1024 ** 3, 40 * 1024 ** 3), disks=[{"FriendlyName": "SSD", "HealthStatus": "Healthy"}],
                  runtimes=(True, True, True), gpus=[{"Name": "GPU", "DriverDate": "2026-10-01"}])
    values.update(extra)
    return ci.Sources(**values)


def top(src, game=GAME):
    inv = ci.investigate(game, src, NOW)
    return inv, (inv.causes[0].id if inv.causes else "")


class Causes(unittest.TestCase):
    def test_graphics_driver(self):
        inv, cause = top(base(app_events=[crash("nvwgf2umx.dll")] * 3))
        self.assertEqual(cause, "gpu_driver")
        self.assertTrue(inv.settled)
        self.assertIn("driver_back", inv.tests)

    def test_driver_update_just_before_counts(self):
        inv, cause = top(base(app_events=[crash("d3d12.dll")],
                              driver_events=[(T - timedelta(days=1), "NVIDIA GeForce RTX 4070 32.0.15.6094")]))
        self.assertEqual(cause, "gpu_driver")
        self.assertTrue(any("started after" in c.text for c in inv.causes[0].clues))

    def test_overlay(self):
        inv, cause = top(base(app_events=[crash("RTSSHooks64.dll")] * 2))
        self.assertEqual(cause, "overlay")
        self.assertIn("overlays_off", inv.tests)

    def test_audio_enhancer(self):
        _inv, cause = top(base(app_events=[crash("NahimicOSD.dll")]))
        self.assertEqual(cause, "audio")

    def test_missing_runtime_from_the_code(self):
        _inv, cause = top(base(app_events=[crash("unknown", "c0000135")]))
        self.assertEqual(cause, "missing_runtime")

    def test_graphics_card_reset_near_the_crash(self):
        inv, cause = top(base(app_events=[crash("NightCity.exe")],
                              system_events=[("Display", 4101, T + timedelta(seconds=30), ["nvlddmkm"])]))
        self.assertEqual(cause, "gpu_unstable")
        self.assertIn("temps", inv.tests)

    def test_hardware_errors(self):
        events = [("Microsoft-Windows-WHEA-Logger", 18, T - timedelta(hours=5), []),
                  ("Microsoft-Windows-WER-SystemErrorReporting", 1001, T + timedelta(minutes=1), ["0x124"])]
        inv, cause = top(base(app_events=[crash("ntdll.dll", "c0000374")], system_events=events))
        self.assertEqual(cause, "hardware")
        self.assertIn("memory_test", inv.tests)

    def test_power_loss_while_playing(self):
        _inv, cause = top(base(app_events=[crash("NightCity.exe")],
                               system_events=[("Microsoft-Windows-Kernel-Power", 41, T + timedelta(minutes=2), [])]))
        self.assertEqual(cause, "power")

    def test_page_file_off(self):
        _inv, cause = top(base(app_events=[crash("NightCity.exe", "c0000017")], page_file=""))
        self.assertEqual(cause, "memory")

    def test_antivirus_blocked_a_game_file(self):
        defender = [("Microsoft-Windows-Windows Defender", 1117, T - timedelta(hours=1),
                     ["Trojan:Win32/Wacatac", FOLDER + r"\bin\x64\steam_api64.dll"])]
        _inv, cause = top(base(app_events=[crash("unknown", "c0000135")], defender_events=defender))
        self.assertEqual(cause, "antivirus")

    def test_failing_drive(self):
        _inv, cause = top(base(app_events=[crash("NightCity.exe", "c0000006")],
                               disks=[{"FriendlyName": "Old HDD", "HealthStatus": "Warning"}]))
        self.assertEqual(cause, "storage")

    def test_anti_cheat(self):
        _inv, cause = top(base(app_events=[crash("EasyAntiCheat_x64.dll")] * 2))
        self.assertEqual(cause, "anti_cheat")

    def test_dotnet_out_of_memory(self):
        event = (".NET Runtime", 1026, T, ["Application: NightCity.exe\nException Info: System.OutOfMemoryException"])
        _inv, cause = top(base(app_events=[event]))
        self.assertEqual(cause, "memory")

    def test_mod_crash_logger_names_plugins(self):
        log = Path(tempfile.mkdtemp()) / "crash-2026-11-16.log"
        log.write_text("Crash Logger SSE\nPOSSIBLE RELEVANT OBJECTS\n  File: \"BadArmor.esp\"\n  File: \"Skyrim.esm\"\n")
        inv, cause = top(base(app_events=[crash("SkyrimSE.exe")], logs=[(T, log)]))
        self.assertEqual(cause, "mod")
        texts = " ".join(c.text for c in inv.causes[0].clues)
        self.assertIn("BadArmor.esp", texts)
        self.assertNotIn("Skyrim.esm", texts, "the game's own files are never blamed as mods")

    def test_unreal_device_removed_log(self):
        log = Path(tempfile.mkdtemp()) / "NightCity.log"
        log.write_text("LogD3D12RHI: Error: GPU crashed\nDXGI_ERROR_DEVICE_REMOVED\n")
        _inv, cause = top(base(logs=[(T, log)]))
        self.assertEqual(cause, "gpu_unstable")

    def test_game_update_just_before(self):
        inv, cause = top(base(app_events=[crash("NightCity.exe")] * 2, game_updated=T - timedelta(hours=10)))
        self.assertEqual(cause, "game_patch")
        self.assertIn("online", inv.tests)

    def test_settings_changed_just_before(self):
        _inv, cause = top(base(app_events=[crash("NightCity.exe")], settings=[(T - timedelta(hours=3), "UserSettings.ini")]))
        self.assertEqual(cause, "settings")


class NeverJustUnknown(unittest.TestCase):
    def test_no_clues_gives_the_full_ladder(self):
        inv = ci.investigate(GAME, base(), NOW)
        self.assertFalse(inv.settled)
        self.assertEqual(inv.causes, [])
        for test in ("verify", "overlays_off", "crash_doctor", "driver_back", "memory_test", "online"):
            self.assertIn(test, inv.tests)
        self.assertIn("tests below", ci.headline(inv))
        self.assertNotIn("unknown", ci.headline(inv).casefold())

    def test_close_leads_are_not_settled(self):
        inv = ci.investigate(GAME, base(app_events=[crash("RTSSHooks64.dll"), crash("nvwgf2umx.dll")]), NOW)
        self.assertFalse(inv.settled)
        self.assertIn("Not settled", ci.headline(inv))

    def test_checked_and_fine_is_listed(self):
        inv = ci.investigate(GAME, base(), NOW)
        self.assertTrue(any("page file" in line for line in inv.fine))
        self.assertTrue(any("healthy" in line for line in inv.fine))

    def test_other_games_crashes_are_ignored(self):
        other = crash("nvwgf2umx.dll", path=r"C:\Games\Other\Other.exe")
        other[3][0] = "Other.exe"
        inv = ci.investigate(GAME, base(app_events=[other]), NOW)
        self.assertEqual(inv.crashes, [])


class Reading(unittest.TestCase):
    def test_windows_error_report(self):
        text = ("Version=1\nEventType=APPCRASH\nEventTime=134080000000000000\nSig[0].Name=Application Name\n"
                "Sig[0].Value=NightCity.exe\nSig[3].Name=Fault Module Name\nSig[3].Value=discordhook64.dll\n"
                "Sig[6].Name=Exception Code\nSig[6].Value=c0000005\nAppPath=" + EXE + "\n")
        report = ci.parse_wer(text)
        self.assertEqual(report["sigs"]["Fault Module Name"], "discordhook64.dll")
        report["when"] = T
        _inv, cause = top(base(wer=[report]))
        self.assertEqual(cause, "overlay")

    def test_wer_files_on_disk(self):
        root = Path(tempfile.mkdtemp())
        folder = root / "AppCrash_NightCity.exe_abc"
        folder.mkdir()
        (folder / "Report.wer").write_bytes("EventType=APPCRASH\nAppPath=C:\\x.exe\n".encode("utf-16"))
        reports = ci.wer_reports([root])
        self.assertEqual(reports[0]["EventType"], "APPCRASH")

    def test_event_xml(self):
        xml = ('<Event xmlns="x"><System><Provider Name="Application Error"/><EventID>1000</EventID>'
               '<TimeCreated SystemTime="2026-11-16T12:00:00.000Z"/></System><EventData><Data>NightCity.exe</Data>'
               '<Data>1</Data></EventData></Event>')
        events = ci.parse_log(xml)
        self.assertEqual(events[0][1], 1000)
        self.assertEqual(events[0][3][0], "NightCity.exe")

    def test_log_places_unreal_and_unity(self):
        home = Path(tempfile.mkdtemp())
        local, locallow = home / "AppData" / "Local", home / "AppData" / "LocalLow"
        (local / "NightCity" / "Saved" / "Crashes").mkdir(parents=True)
        (locallow / "Studio" / "Night City").mkdir(parents=True)
        game_folder = home / "Games" / "Night City"
        game_folder.mkdir(parents=True)
        places = ci.log_places("Night City", game_folder, home=home, local=local, locallow=locallow, temp=home / "t")
        names = [str(p) for p in places]
        self.assertTrue(any("Saved" in n for n in names))
        self.assertTrue(any(n.endswith("Night City") and "LocalLow" in n for n in names))

    def test_steam_news_and_patch_clue(self):
        stamp = int((T - timedelta(days=1)).timestamp())
        raw = json.dumps({"appnews": {"newsitems": [{"date": stamp, "title": "Patch 2.3 hotfix", "url": "https://x"}]}})
        news = ci.steam_news("1091500", fetch=lambda url: raw)
        clue = ci.news_clue(news, [(T, "NightCity.exe", "x", "")])
        self.assertEqual(clue.cause, "game_patch")
        inv = ci.investigate(GAME, base(app_events=[crash("NightCity.exe")]), NOW)
        ci.add_clue(inv, clue, GAME)
        self.assertEqual(inv.causes[0].id, "game_patch")

    def test_search_links_send_only_game_and_error(self):
        links = ci.search_links(GAME, [(T, "NightCity.exe", "nvwgf2umx.dll", "c0000005")])
        self.assertIn("nvwgf2umx.dll", links["Search the web"])
        self.assertIn("1091500", links["Steam discussions"])
        self.assertNotIn("Users", " ".join(links.values()))

    def test_report_hides_the_user_name(self):
        inv = ci.investigate(SimpleNamespace(name="X", install_path=r"C:\Users\Alex\Games\X", app_id=""), base(), NOW)
        self.assertNotIn("Alex", ci.render(inv))


if __name__ == "__main__":
    unittest.main()
