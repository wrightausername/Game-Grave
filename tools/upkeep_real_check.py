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

    # A real scheduled task that runs at sign-in: listed, switched off and on, then removed.
    task = "GG Real Check Task"
    up._powershell(f"Register-ScheduledTask -TaskName {up.ps_quote(task)} -Action (New-ScheduledTaskAction -Execute "
                   f"{up.ps_quote(target)}) -Trigger (New-ScheduledTaskTrigger -AtLogOn) -Force | Out-Null", 60)
    try:
        listed = next((a for a in up.read_startup() if a.source == "Task" and a.name == task), None)
        assert listed and listed.enabled and listed.ref == "\\" + task, listed
        up.set_enabled(listed, False)
        assert not next(a for a in up.read_startup() if a.source == "Task" and a.name == task).enabled
        up.set_enabled(listed, True)
        assert next(a for a in up.read_startup() if a.source == "Task" and a.name == task).enabled
        print("PASS real: scheduled task at sign-in listed, switched off and back on")
    finally:
        up._powershell(f"Unregister-ScheduledTask -TaskName {up.ps_quote(task)} -Confirm:$false", 60)
    store = [a for a in up.read_startup() if a.source == "StoreApp"]
    print(f"PASS real: Store app startup tasks read: {len(store)} ({', '.join(a.title for a in store[:4]) or 'none on this machine'})")

    from gg_desktop import upkeep_vendor as vendor
    fw = up.read_firmware()
    print(f"PASS real: firmware read: BIOS {fw.bios_version} ({fw.bios_date}) on {fw.model}; drives: "
          + "; ".join(f"{m} fw {r}" for m, r, _t in fw.drives))
    nv = vendor.check_graphics("NVIDIA GeForce RTX 3060 Ti", "32.0.15.6094", "2024-09-12")
    print(f"NVIDIA live lookup: latest={nv.latest!r} date={nv.latest_date!r} name={nv.latest_name!r} note={nv.note!r}")
    assert nv.latest, "NVIDIA's own lookup should give the newest Game Ready driver"
    nvl = vendor.check_graphics("NVIDIA GeForce RTX 4060 Laptop GPU", "32.0.15.6094", "")
    print(f"NVIDIA live lookup (laptop): latest={nvl.latest!r} note={nvl.note!r}")
    try:
        raw = vendor._get(vendor.AMD_VERSION)
        print("AMD version file (first 700 chars):", raw[:700].replace("\n", " "))
    except vendor.VendorError as problem:
        print("AMD version file not reachable:", problem)
    amd = vendor.check_graphics("AMD Radeon RX 7800 XT", "32.0.12033.1030", "")
    print(f"AMD live check: latest={amd.latest!r} name={amd.latest_name!r} note={amd.note!r}")
    from gg_desktop import workshop_core as ws
    live = ws.fetch_details(["2016612051", "1"])
    print(f"Steam Workshop live lookup: {live.get('2016612051', {}).get('title')!r}; unknown item removed="
          f"{live.get('1', {}).get('removed')}")
    assert live.get("2016612051", {}).get("title"), "Steam's public Workshop lookup should name a real item"
    problems = up.read_problems()
    print(f"PASS real: Device Manager problems read: {len(problems)} ({'; '.join(p.name + ': ' + p.meaning for p in problems[:3]) or 'none'})")
    updates = up.search_updates()
    print(f"PASS real: Windows Update driver search answered with {len(updates)} update(s): "
          + "; ".join(u.title for u in updates[:5]))

    # Prove the download-and-install path for real. This machine rarely has a driver waiting, so if none is offered
    # the same installer code installs a small Windows Update item instead (Defender definitions, or any small one).
    if updates:
        ok, words, reboot = up.install_updates(updates[:1])
        assert ok, words
        print(f"PASS real: installed a real driver update through Windows Update: {words}")
    else:
        criteria = ("IsInstalled=0 and IsHidden=0 and Type='Software' and "
                    "CategoryIDs contains 'E0789628-CE08-4437-BE74-2495B842F43B'")          # Definition Updates
        found = up.search_any(criteria)
        small = [u for u in found if u.size < 400 * 1024 ** 2]
        if not small:
            criteria = "IsInstalled=0 and IsHidden=0 and Type='Software'"
            small = sorted([u for u in up.search_any(criteria) if 0 < u.size < 200 * 1024 ** 2], key=lambda u: u.size)
        assert small, "Windows Update offered nothing small enough to prove the install path"
        steps = []
        text = up.run_elevated(up.install_script([small[0].update_id], "__RESULT__", criteria=criteria,
                                                 progress_path="__PROGRESS__"), on_step=steps.append)
        ok, words, reboot = up.summarize_install(text, 1)
        assert ok, words
        print("PASS real: live install steps seen: " + " | ".join(up.step_text(s) for s in steps))
        assert any(s[0] in ("download", "install", "done") for s in steps), "the installer's steps were read live"
        print(f"PASS real: download and install through the same installer code worked ({small[0].title}): {words}")
    print(f"Drivers & Startup real check passed in {time.time() - started:.0f}s")


if __name__ == "__main__":
    main()
