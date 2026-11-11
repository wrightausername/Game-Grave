"""Drivers & Startup: parsing what Windows reports, Task Manager's on/off value, and honest summaries."""
from __future__ import annotations

from datetime import date, datetime, timezone
import json
import unittest

from gg_desktop import upkeep_core as up

ID = "3f1c9b2e-1111-4a2b-9c3d-123456789abc"


class Drivers(unittest.TestCase):
    def test_updates_are_parsed_and_junk_dropped(self):
        text = json.dumps([{"Id": ID, "Title": "NVIDIA - Display - 32.0.15.6094", "Class": "Display", "Maker": "NVIDIA",
                            "Model": "RTX 4070", "Date": "2024-09-12", "Size": 700_000_000},
                           {"Id": ID, "Title": "dup"}, {"Id": "not-an-id", "Title": "x"}, "junk"])
        found = up.parse_updates(text)
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0].device_class, found[0].size, found[0].date), ("Display", 700_000_000, "2024-09-12"))
        self.assertEqual(up.parse_updates(json.dumps({"Id": ID, "Title": "one"}))[0].title, "one")
        self.assertEqual(up.parse_updates(""), [])
        self.assertEqual(up.parse_updates("not json"), [])

    def test_old_drivers_are_a_hint_from_game_relevant_classes(self):
        installed = up.parse_installed(json.dumps([
            {"DeviceName": "Old Sound Card", "DeviceClass": "MEDIA", "Date": "2017-03-01", "DriverVersion": "1.0"},
            {"DeviceName": "Volume", "DeviceClass": "VOLUME", "Date": "2010-01-01"},
            {"DeviceName": "Inbox Mouse", "DeviceClass": "MOUSE", "Date": "2006-06-21"},
            {"DeviceName": "New GPU", "DeviceClass": "DISPLAY", "Date": "2026-01-01"},
            {"DeviceName": "", "DeviceClass": "NET"}]))
        self.assertEqual(len(installed), 4)
        aged = up.old_drivers(installed, today=date(2026, 11, 11))
        self.assertEqual([d.device for _, d in aged], ["Old Sound Card"])
        self.assertIsNone(up.years_old("bad"))

    def test_maker_pages_are_official(self):
        self.assertEqual(up.maker_page(["NVIDIA GeForce RTX 4070"])[1], "https://www.nvidia.com/en-us/software/nvidia-app/")
        self.assertIn("amd.com", up.maker_page(["AMD Radeon RX 7800 XT"])[1])
        self.assertIn("intel.com", up.maker_page(["Intel(R) Arc(TM) A770"])[1])
        self.assertIsNone(up.maker_page(["Microsoft Basic Display Adapter"]))

    def test_install_summary_in_words(self):
        ok, words, reboot = up.summarize_install(json.dumps({"found": 2, "reboot": True, "results": [
            {"title": "A", "code": 2}, {"title": "B driver", "code": 4}]}), 2)
        self.assertTrue(ok and reboot)
        self.assertIn("Installed 1 of 2", words)
        self.assertIn("B driver: failed", words)
        self.assertIn("restart", words)
        self.assertFalse(up.summarize_install(json.dumps({"found": 0, "results": []}), 1)[0])
        self.assertIn("no longer offers", up.summarize_install(json.dumps({"found": 0}), 1)[1])
        self.assertIn("stopped", up.summarize_install(json.dumps({"error": "0x80240024"}), 1)[1])
        self.assertFalse(up.summarize_install("", 1)[0])

    def test_install_script_only_holds_update_ids(self):
        script = up.install_script([ID, "'; Remove-Item C:\\ -Recurse; '"], "__RESULT__")
        self.assertIn(f"'{ID}'", script)
        self.assertNotIn("Remove-Item", script)
        self.assertIn("Type='Driver'", script)


class Startup(unittest.TestCase):
    def test_task_manager_rule(self):
        self.assertTrue(up.approved_enabled(None))
        self.assertTrue(up.approved_enabled(bytes([2]) + bytes(11)))
        self.assertTrue(up.approved_enabled(bytes([6]) + bytes(11)))
        self.assertFalse(up.approved_enabled(bytes([3]) + bytes(11)))
        self.assertFalse(up.approved_enabled(bytes([7]) + bytes(11)))

    def test_values_written_match_task_manager(self):
        on = up.approved_value(True)
        self.assertEqual(on, bytes([2]) + bytes(11))
        off = up.approved_value(False, datetime(2026, 11, 11, tzinfo=timezone.utc))
        self.assertEqual(len(off), 12)
        self.assertEqual(off[:4], bytes([3, 0, 0, 0]))
        self.assertEqual(int.from_bytes(off[4:], "little"), int((datetime(2026, 11, 11, tzinfo=timezone.utc).timestamp() + 11644473600) * 10_000_000))
        self.assertFalse(up.approved_enabled(off))

    def test_program_path(self):
        env = {"ProgramFiles": r"C:\Program Files", "LOCALAPPDATA": r"C:\Users\a\AppData\Local"}
        self.assertEqual(up.program_path(r'"C:\Program Files\Steam\steam.exe" -silent', env), r"C:\Program Files\Steam\steam.exe")
        self.assertEqual(up.program_path(r"C:\Program Files\Discord\Update.exe --processStart Discord.exe", env),
                         r"C:\Program Files\Discord\Update.exe")
        self.assertEqual(up.program_path(r"%LOCALAPPDATA%\App\app.exe /min", env), r"C:\Users\a\AppData\Local\App\app.exe")
        self.assertEqual(up.program_path("", env), "")

    def test_startup_rows(self):
        text = json.dumps([
            {"Name": "Steam", "Command": "\"C:\\Steam\\steam.exe\" -silent", "Scope": "user", "Source": "Run",
             "Approved": "030000000000000000000000", "Company": "Valve", "Description": "Steam", "Exists": True},
            {"Name": "Discord", "Command": "C:\\D\\Update.exe", "Scope": "user", "Source": "Run", "Approved": "", "Exists": True},
            {"Name": "Vendor Tool", "Command": "x.exe", "Scope": "machine", "Source": "Run32", "Approved": "zz"},
            {"Name": "Bad", "Scope": "nowhere", "Source": "Run"}, {"Name": "", "Scope": "user", "Source": "Run"},
            {"Name": "steam", "Command": "dup", "Scope": "user", "Source": "Run"}])
        apps = up.parse_startup(text)
        self.assertEqual([a.title for a in apps], ["Discord", "Vendor Tool", "Steam"], "On first, then off")
        steam = apps[-1]
        self.assertFalse(steam.enabled)
        self.assertEqual(steam.target, "C:\\Steam\\steam.exe")
        self.assertTrue(apps[1].needs_admin and apps[1].enabled)
        self.assertEqual(up.approved_path(apps[1]), up.APPROVED + "\\Run32")

    def test_user_toggle_writes_only_the_approved_value(self):
        app = up.parse_startup(json.dumps([{"Name": "Steam", "Command": "s.exe", "Scope": "user", "Source": "Run"}]))[0]
        writes = []
        up.set_enabled_user(app, False, writer=lambda key, name, data: writes.append((key, name, data)))
        self.assertEqual(writes[0][0], up.APPROVED + "\\Run")
        self.assertEqual(writes[0][1], "Steam")
        self.assertFalse(up.approved_enabled(writes[0][2]))
        machine = up.parse_startup(json.dumps([{"Name": "X", "Command": "x.exe", "Scope": "machine", "Source": "Run"}]))[0]
        with self.assertRaises(up.UpkeepError):
            up.set_enabled_user(machine, False, writer=lambda *a: None)

    def test_admin_toggle_script_quotes_the_name(self):
        app = up.parse_startup(json.dumps([{"Name": "It's'; rm -r C:\\", "Command": "x.exe", "Scope": "machine",
                                            "Source": "StartupFolder"}]))[0]
        script = up.toggle_script(app, True)
        self.assertIn("HKLM:\\" + up.APPROVED + "\\StartupFolder", script)
        self.assertIn("-Name 'It''s''; rm -r C:\\'", script)
        self.assertIn("([byte[]](2,0,0,0,0,0,0,0,0,0,0,0))", script)


if __name__ == "__main__":
    unittest.main()


class StoreAppsAndTasks(unittest.TestCase):
    def rows(self):
        return up.parse_startup(json.dumps([
            {"Name": "SpotifyStartupTask", "Command": "SpotifyAB.Spotify_zpdnekdrzrea0", "Scope": "user", "Source": "StoreApp",
             "Ref": "SpotifyAB.Spotify_zpdnekdrzrea0\\SpotifyStartupTask", "State": 2, "Description": "Spotify"},
            {"Name": "PolicyTask", "Scope": "user", "Source": "StoreApp", "Ref": "Pkg\\PolicyTask", "State": 3},
            {"Name": "NoRef", "Scope": "user", "Source": "StoreApp", "State": 2},
            {"Name": "Vendor Logon", "Command": "C:\\V\\v.exe /tray", "Scope": "machine", "Source": "Task",
             "Ref": "\\Vendor\\Vendor Logon", "State": False, "Description": "Vendor Tray"},
            {"Name": "My Task", "Command": "C:\\a.exe", "Scope": "user", "Source": "Task", "Ref": "\\My Task", "State": True}]))

    def test_states(self):
        apps = {a.name: a for a in self.rows()}
        self.assertEqual(set(apps), {"SpotifyStartupTask", "PolicyTask", "Vendor Logon", "My Task"})
        self.assertTrue(apps["SpotifyStartupTask"].enabled and not apps["SpotifyStartupTask"].locked)
        self.assertTrue(apps["PolicyTask"].locked and not apps["PolicyTask"].enabled)
        self.assertFalse(apps["Vendor Logon"].enabled)
        self.assertTrue(apps["My Task"].enabled)

    def test_store_toggle_writes_only_the_state(self):
        apps = {a.name: a for a in self.rows()}
        writes = []
        up.set_enabled_user(apps["SpotifyStartupTask"], False, writer=lambda *a: writes.append(a))
        self.assertEqual(writes, [(up.STORE_TASKS + "\\SpotifyAB.Spotify_zpdnekdrzrea0\\SpotifyStartupTask", "State", 1)])
        with self.assertRaisesRegex(up.UpkeepError, "policy"):
            up.set_enabled(apps["PolicyTask"], True)

    def test_task_script(self):
        apps = {a.name: a for a in self.rows()}
        self.assertEqual(up.task_script(apps["Vendor Logon"], True),
                         "$ErrorActionPreference='Stop'\nEnable-ScheduledTask -TaskPath '\\Vendor\\' -TaskName 'Vendor Logon' | Out-Null\n")
        self.assertIn("Disable-ScheduledTask -TaskPath '\\' -TaskName 'My Task'", up.task_script(apps["My Task"], False))
        self.assertIn("Disable-ScheduledTask", up.toggle_script(apps["Vendor Logon"], False))

    def test_install_criteria_can_be_chosen(self):
        self.assertIn("Type='Software'", up.install_script([ID], "__RESULT__", criteria="IsInstalled=0 and Type='Software'"))
        self.assertIn("Type='Driver'", up.install_script([ID], "__RESULT__"))
