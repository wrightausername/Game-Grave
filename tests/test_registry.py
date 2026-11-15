import unittest

from gg_desktop import registry_core as rc


class FakeReg:
    def __init__(self, data):
        self.data = data          # {(hive, key): {"values": {...}, "subkeys": [...]}}

    def subkeys(self, hive, key):
        return list(self.data.get((hive, key), {}).get("subkeys", []))

    def values(self, hive, key):
        return dict(self.data.get((hive, key), {}).get("values", {}))


PRESENT = {r"c:\program files\steam\steam.exe", r"c:\games\real\game.exe", r"c:\program files\real",
           r"c:\program files\real\unins000.exe"}


def checks(present=PRESENT, fixed=("C",)):
    return rc.Checks(exists=lambda p: p.casefold() in present, drive_ok=lambda d: d in fixed,
                     expand=lambda t: t.replace("%ProgramFiles%", r"C:\Program Files"))


class Parse(unittest.TestCase):
    def test_target_from(self):
        t = rc.target_from
        self.assertEqual(t('"C:\\Program Files\\X\\x.exe" -silent'), r"C:\Program Files\X\x.exe")
        self.assertEqual(t(r"C:\Program Files\X\x.exe -silent"), r"C:\Program Files\X\x.exe")
        self.assertEqual(t(r"C:\Tools\a.exe,0"), r"C:\Tools\a.exe")
        self.assertEqual(t(r'rundll32.exe "C:\Old\thing.dll",Start'), r"C:\Old\thing.dll")
        self.assertEqual(t("MsiExec.exe /X{1234}"), "")
        self.assertEqual(t("notepad.exe"), "", "relative names can't be checked")
        self.assertEqual(t("@%SystemRoot%\\x.dll,-101"), "")
        self.assertEqual(t(r"%ProgramFiles%\Gone\g.exe", lambda s: s.replace("%ProgramFiles%", r"C:\Program Files")),
                         r"C:\Program Files\Gone\g.exe")

    def test_gone_is_careful(self):
        c = checks()
        self.assertTrue(c.gone(r"C:\Program Files\Gone\g.exe"))
        self.assertFalse(c.gone(r"C:\Program Files\Steam\steam.exe"), "present")
        self.assertFalse(c.gone(r"E:\Games\g.exe"), "an unplugged or removable drive is never 'missing'")
        self.assertFalse(c.gone(r"C:\Windows\System32\gone.dll"), "the Windows folder is never 'missing'")
        self.assertFalse(c.gone(r"\\server\share\x.exe"))
        self.assertFalse(c.gone("C:\\"))
        self.assertFalse(c.gone(""))


class Scan(unittest.TestCase):
    def reg(self):
        U = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
        return FakeReg({
            ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Run"): {"values": {
                "Steam": r'"C:\Program Files\Steam\steam.exe" -silent', "OldTool": r"C:\Old Tool\tool.exe /tray",
                "USBThing": r"E:\Portable\p.exe", "Sys": r"C:\Windows\System32\gone.exe"}},
            ("HKLM", U): {"subkeys": ["GoneApp", "RealApp", "MsiGone", "MsGone", "Sys", "NoUninstaller"]},
            ("HKLM", U + r"\GoneApp"): {"values": {"DisplayName": "Gone App", "UninstallString": r'"C:\Program Files\GoneApp\unins000.exe"',
                                                    "InstallLocation": r"C:\Program Files\GoneApp"}},
            ("HKLM", U + r"\RealApp"): {"values": {"DisplayName": "Real", "UninstallString": r"C:\Program Files\Real\unins000.exe",
                                                    "InstallLocation": r"C:\Program Files\Real"}},
            ("HKLM", U + r"\MsiGone"): {"values": {"DisplayName": "Msi Thing", "UninstallString": r"C:\Program Files\M\u.exe",
                                                    "WindowsInstaller": "1"}},
            ("HKLM", U + r"\MsGone"): {"values": {"DisplayName": "MS Thing", "Publisher": "Microsoft Corporation",
                                                   "UninstallString": r"C:\Program Files\MS\u.exe"}},
            ("HKLM", U + r"\Sys"): {"values": {"DisplayName": "Hidden", "SystemComponent": "1",
                                                "UninstallString": r"C:\Program Files\H\u.exe"}},
            ("HKLM", U + r"\NoUninstaller"): {"values": {"DisplayName": "Odd", "UninstallString": "MsiExec.exe /X{1}"}},
            ("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\SharedDLLs"): {"values": {
                r"C:\Program Files\Gone\shared.dll": "1", r"C:\Program Files\Real\unins000.exe": "1"}},
            ("HKCU", r"Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\MuiCache"): {"values": {
                r"C:\Gone\app.exe.FriendlyAppName": "App", r"C:\Games\Real\game.exe.FriendlyAppName": "Game"}},
            ("HKCU", r"AppEvents\Schemes\Apps"): {"subkeys": [".Default"]},
            ("HKCU", r"AppEvents\Schemes\Apps\.Default"): {"subkeys": ["Notify"]},
            ("HKCU", r"AppEvents\Schemes\Apps\.Default\Notify\.Current"): {"values": {"": r"C:\Sounds\gone.wav"}},
            ("HKLM", r"SYSTEM\CurrentControlSet\Services"): {"subkeys": ["OldSvc"]},
            ("HKLM", r"SYSTEM\CurrentControlSet\Services\OldSvc"): {"values": {"ImagePath": r'"C:\Old\svc.exe"'}},
            ("HKCU", r"Software\Classes\Applications"): {"subkeys": ["gone.exe"]},
            ("HKCU", r"Software\Classes\Applications\gone.exe\shell\open\command"): {"values": {
                "": r'"C:\Gone\gone.exe" "%1"'}},
        })

    def test_finds_only_proven_leftovers(self):
        found = rc.scan(self.reg(), checks())
        by = {(f.category, f.name) for f in found}
        self.assertIn(("startup", "OldTool"), by)
        self.assertNotIn(("startup", "Steam"), by)
        self.assertNotIn(("startup", "USBThing"), by)
        self.assertNotIn(("startup", "Sys"), by)
        self.assertIn(("uninstall", "Gone App"), by)
        self.assertFalse(any(f.name in ("Real", "Hidden", "Odd") for f in found))
        self.assertIn(("review", "Msi Thing"), by)
        self.assertIn(("review", "MS Thing"), by)
        self.assertIn(("review", "OldSvc"), by)
        self.assertIn(("shared_dlls", "shared.dll"), by)
        self.assertNotIn(("shared_dlls", "unins000.exe"), by)
        self.assertIn(("mui_cache", "app.exe"), by)
        self.assertNotIn(("mui_cache", "game.exe"), by)
        self.assertIn(("sounds", "Notify"), by)
        self.assertIn(("open_with", "gone.exe"), by)
        sound = next(f for f in found if f.category == "sounds")
        self.assertEqual(sound.action, "clear_value", "a sound is set to none, never deleted")
        for f in found:
            if f.category == "review":
                self.assertFalse(f.fixable)
                self.assertNotIn(f.ident, rc.default_ticked(found))

    def test_words(self):
        found = rc.scan(self.reg(), checks())
        text = rc.confirmation([f for f in found if f.fixable], True, r"C:\Backups")
        self.assertIn("Restore point", text)
        self.assertIn(r"C:\Backups", text)
        self.assertIn("Windows will ask", text)
        self.assertIn("HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run value \"OldTool\"", text)
        for words in [rc.HONEST_NOTE, text, rc.summary(found)] + [c[1] for c in rc.CATEGORIES.values()]:
            self.assertNotIn("safe", words.lower())
            self.assertNotIn("faster", words.lower().replace("doesn't make games faster", ""))
        groups = [g[0] for g in rc.grouped(found)]
        self.assertEqual(groups[-1], "review")
        self.assertFalse(rc.CATEGORIES["installer_folders"][2], "installer folders start unticked")

    def test_one_bad_area_never_stops_the_scan(self):
        class Broken(FakeReg):
            def values(self, hive, key):
                if "SharedDLLs" in key:
                    raise RuntimeError("boom")
                return super().values(hive, key)
        found = rc.scan(Broken(self.reg().data), checks())
        self.assertTrue(any(f.category == "startup" for f in found))


class Scripts(unittest.TestCase):
    def test_elevated_script_rechecks_each_target(self):
        from gg_desktop import registry_win as rw
        f = rc.Finding("startup", "HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run", "Old'Tool", r"C:\Old\t.exe")
        script = rw.elevated_script([f], True)
        self.assertIn("Checkpoint-Computer", script)
        self.assertIn("Test-Path -LiteralPath 'C:\\Old\\t.exe'", script)
        self.assertIn("-Name 'Old''Tool'", script, "quotes are escaped")
        self.assertIn("Registry::HKEY_LOCAL_MACHINE\\SOFTWARE", script)

    def test_backup_refuses_when_an_export_fails(self):
        import tempfile
        from types import SimpleNamespace
        from gg_desktop import registry_win as rw
        f = rc.Finding("startup", "HKCU", r"Software\X", "a", r"C:\gone.exe")
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(rw.RegistryError):
                rw.backup([f], d, runner=lambda *a, **k: SimpleNamespace(returncode=1))

            def ok(args, **_):
                open(args[3], "w").write("Windows Registry Editor Version 5.00\n")
                return SimpleNamespace(returncode=0)
            folder = rw.backup([f], d, runner=ok)
            self.assertTrue((folder / "001.reg").is_file() and (folder / "changes.json").is_file())
            self.assertEqual(rw.backups(d)[0][1], 1)


if __name__ == "__main__":
    unittest.main()
