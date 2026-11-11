"""Runs the REAL Windows calls of Drivers & Startup on a disposable Windows machine (CI). Nothing is faked.

It reads the installed drivers, asks Windows Update for driver updates (no install), and switches two test startup
entries it creates itself (one for this user, one for all users through the admin path), then removes them again.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import time
import winreg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gg_desktop import upkeep_core as up  # noqa: E402

NAME = "GG Real Check App"


def approved(hive, sub):
    try:
        with winreg.OpenKey(hive, up.APPROVED + "\\" + sub) as key:
            return winreg.QueryValueEx(key, NAME)[0]
    except OSError:
        return None


def cleanup():
    for hive, run, sub in ((winreg.HKEY_CURRENT_USER, up.RUN_KEY, "Run"), (winreg.HKEY_LOCAL_MACHINE, up.RUN_KEY, "Run")):
        for path in (run, up.APPROVED + "\\" + sub):
            try:
                with winreg.OpenKey(hive, path, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.DeleteValue(key, NAME)
            except OSError:
                pass


def find(apps, scope):
    return next((a for a in apps if a.name == NAME and a.scope == scope), None)


def main():
    started = time.time()
    installed = up.read_installed()
    assert len(installed) > 10, f"only {len(installed)} drivers read"
    print(f"PASS real: {len(installed)} installed drivers read; oldest hint rows: {len(up.old_drivers(installed))}")

    cleanup()
    target = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "notepad.exe")
    try:
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            with winreg.CreateKeyEx(hive, up.RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, NAME, 0, winreg.REG_SZ, f'"{target}" /test')
        apps = up.read_startup()
        mine, everyone = find(apps, "user"), find(apps, "machine")
        assert mine and everyone, [a.name for a in apps]
        assert mine.enabled and everyone.enabled and mine.exists is True and mine.target.lower() == target.lower(), mine
        assert "notepad" in (mine.description + mine.company).lower() or mine.company, mine
        print(f"PASS real: startup list has {len(apps)} entries; test entries read with publisher '{mine.company}'")

        up.set_enabled(mine, False)
        assert not up.approved_enabled(approved(winreg.HKEY_CURRENT_USER, "Run"))
        assert not find(up.read_startup(), "user").enabled
        up.set_enabled(mine, True)
        assert find(up.read_startup(), "user").enabled
        print("PASS real: switch for this user turned off and back on through Task Manager's value")

        up.set_enabled(everyone, False)          # goes through run_elevated (Start-Process -Verb RunAs)
        assert not up.approved_enabled(approved(winreg.HKEY_LOCAL_MACHINE, "Run")), approved(winreg.HKEY_LOCAL_MACHINE, "Run")
        assert not find(up.read_startup(), "machine").enabled
        up.set_enabled(everyone, True)
        assert find(up.read_startup(), "machine").enabled
        print("PASS real: all-users switch turned off and on through the elevated path")
    finally:
        cleanup()

    try:
        updates = up.search_updates()
        print(f"PASS real: Windows Update driver search answered with {len(updates)} update(s): "
              + "; ".join(u.title for u in updates[:5]))
    except up.UpkeepError as problem:
        print(f"NOTE real: Windows Update driver search did not answer on this machine: {problem}")
    print(f"Drivers & Startup real check passed in {time.time() - started:.0f}s")


if __name__ == "__main__":
    main()
