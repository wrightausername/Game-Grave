"""Registry Cleanup against the REAL registry on the Windows CI machine, using only test entries this script creates:
a startup value for you (HKCU Run) and an App Paths key for all users (HKLM), both pointing to a folder that doesn't
exist. A real scan must find both (and the full scan must finish), a real fix must back them up and remove only them (the
all-users one through the elevated script, with a restore point asked for), and a real Undo must put both back. The
script removes its test entries at the end whatever happens."""
from __future__ import annotations

import os
import sys
import tempfile
import time
import winreg
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\GameGraveRegistryTest.exe"
NAME = "GameGraveRegistryTest"
GONE = r"C:\GameGraveRegistryTestGone\never-here.exe"
REAL = os.environ.get("SystemRoot", r"C:\Windows") + r"\notepad.exe"
KEEP = "GameGraveRegistryKeep"


def setup():
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, f'"{GONE}" --tray')
        winreg.SetValueEx(k, KEEP, 0, winreg.REG_SZ, f'"{REAL}"')          # a present program: must never be listed
    with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, APP, 0,
                            winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, GONE)


def has_run(name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN) as k:
            winreg.QueryValueEx(k, name)
            return True
    except OSError:
        return False


def has_app():
    try:
        winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, APP, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY).Close()
        return True
    except OSError:
        return False


def cleanup():
    for name in (NAME, KEEP):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, name)
        except OSError:
            pass
    try:
        winreg.DeleteKeyEx(winreg.HKEY_LOCAL_MACHINE, APP, winreg.KEY_WOW64_64KEY, 0)
    except OSError:
        pass


def main():
    from gg_desktop import registry_win as rw
    setup()
    try:
        started = time.time()
        found = rw.scan()
        took = time.time() - started
        print(f"Real scan: {len(found)} findings in {took:.1f} s")
        for f in found[:15]:
            print("  ", f.category, "|", f.name, "|", f.target)
        mine = [f for f in found if f.name in (NAME, "GameGraveRegistryTest.exe")]
        assert {f.category for f in mine} == {"startup", "app_paths"}, mine
        assert not any(f.name == KEEP for f in found), "a present program was listed"
        assert not any(f.target.casefold().startswith(os.environ.get("SystemRoot", r"C:\Windows").casefold() + "\\")
                       for f in found), "the Windows folder is never treated as missing"
        with tempfile.TemporaryDirectory(prefix="GG-regcheck-") as d:
            result = rw.fix(mine, restore_point=True, root=d)
            print("Fix result:", result)
            assert sorted(result["done"]) == sorted(f.ident for f in mine), result
            assert not has_run(NAME) and not has_app(), "the test entries were not removed"
            assert has_run(KEEP), "an entry that wasn't chosen was changed"
            folder = Path(result["folder"])
            assert len(list(folder.glob("*.reg"))) == 2 and (folder / "changes.txt").is_file()
            failed = rw.undo(folder)
            assert not failed, failed
            assert has_run(NAME) and has_app(), "Undo did not put the test entries back"
            assert rw.backups(d)[0][2], "the backup is marked as undone"
        print("PASS: real Registry Cleanup scan, backup, fix (own and all-users) and Undo on test entries. Restore "
              f"point: {result['restore'] or 'not asked'}")
    finally:
        cleanup()


if __name__ == "__main__":
    main()
