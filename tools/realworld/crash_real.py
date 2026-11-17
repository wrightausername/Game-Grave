"""Real crashes: a small test program that really crashes, so Windows records a real crash.

The program ("Pixel Farm") stays running unless its Mods folder holds "Bad Mod"; then it crashes with an access violation
after a moment. Checked: Black Box reads Windows' real crash record, the Games tracker notices the game closing and the
"just crashed" notice appears, and Crash Doctor, with nothing faked except how long a fine test lasts, launches the real
program, watches it, finds Bad Mod and puts every mod back. Only this check's own folder is touched.
"""
from __future__ import annotations

import argparse
import dataclasses
import os
import subprocess
import sys
import time
import winreg
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rw_common as rw  # noqa: E402

PROGRAM = r"""
using System; using System.IO; using System.Threading; using System.Runtime.InteropServices;
class PixelFarm {
  [StructLayout(LayoutKind.Sequential)]
  struct ExceptionRecord { public uint Code; public uint Flags; public IntPtr Record; public IntPtr Address;
                           public uint Count; [MarshalAs(UnmanagedType.ByValArray, SizeConst = 15)] public IntPtr[] Info; }
  [DllImport("kernel32.dll")] static extern void RaiseFailFastException(ref ExceptionRecord record, IntPtr context, uint flags);
  static void Main(string[] args) {
    string dir = AppDomain.CurrentDomain.BaseDirectory;
    int wait = 1500;
    string waitFile = Path.Combine(dir, "crash-after-ms.txt");
    if (File.Exists(waitFile)) { int.TryParse(File.ReadAllText(waitFile).Trim(), out wait); }
    if (Directory.Exists(Path.Combine(dir, "Mods", "Bad Mod"))) {
      Thread.Sleep(wait);
      // A crash Windows records the way it records a game's: straight to Windows Error Reporting, code 0xc0000005.
      var record = new ExceptionRecord { Code = 0xC0000005, Info = new IntPtr[15] };
      RaiseFailFastException(ref record, IntPtr.Zero, 0);
    }
    Thread.Sleep(Timeout.Infinite);
  }
}
"""


def compile_program(target: Path):
    rw.compile_cs(PROGRAM, target)


def quiet_crash_dialogs():
    """No "has stopped working" window on the build machine (it would keep the crashed program open)."""
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\Windows Error Reporting", 0,
                            winreg.KEY_WRITE) as k:
        winreg.SetValueEx(k, "DontShowUI", 0, winreg.REG_DWORD, 1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("_ci_temp/realworld"))
    args = parser.parse_args()
    scratch = rw.isolate("GG-rw-crash-")
    rep = rw.Report("crash-real", args.output)
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from core import SteamGame
    from gg_desktop import blackbox_core as bb, comfort, crashdoctor_ui, fix_kit_page
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.backend import Inventory
    from gg_desktop.models import merge_games
    from unittest.mock import patch

    game_dir = scratch / "SteamLibrary" / "steamapps" / "common" / "Pixel Farm"
    mods = game_dir / "Mods"
    names = ["Better Crops", "Bad Mod", "Fishing Plus", "Map HD", "UI Tweaks", "Weather"]
    for name in names:
        (mods / name).mkdir(parents=True)
        (mods / name / "manifest.json").write_text(name)
    exe = game_dir / "PixelFarm.exe"
    if not rw.guarded(rep, "build the test program", lambda: compile_program(exe) or True):
        return rep.finish()
    quiet_crash_dialogs()

    records = [True]

    # Black Box reads the real crash record
    def black_box():
        started = time.time()
        proc = subprocess.Popen([str(exe)])
        try:
            proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            proc.kill()
            rep.check("the test program crashes with Bad Mod in place", False)
            return
        rep.check("the test program crashes with Bad Mod in place", proc.returncode != 0, exit_code=hex(proc.returncode & 0xFFFFFFFF))
        found = []
        for _ in range(20):                              # Windows writes the record a moment after the crash
            crashes = bb.parse_events(bb.query_events(20))
            found = [c for c in crashes if str(c.path or "").casefold().startswith(str(game_dir).casefold())
                     and c.when.timestamp() >= started - 5]
            if found:
                break
            time.sleep(1)
        if not found:
            for query in ("*[System[(EventID=1000)]]", "*[System[(EventID=1026)]]", "*[System[(EventID=1001)]]"):
                raw = subprocess.run(["wevtutil", "qe", "Application", f"/q:{query}", "/c:3", "/rd:true", "/f:text"],
                                     capture_output=True, text=True).stdout
                rep.note("Windows' Application log, " + query, newest=raw[:1500])
        any_crash = subprocess.run(["wevtutil", "qe", "Application", "/q:*[System[Provider[@Name='Application Error']]]",
                                    "/c:1", "/f:text"], capture_output=True, text=True).stdout.strip()
        if not found and not any_crash:
            rep.note("this build machine records no application crashes at all (not even with Windows Error Reporting "
                     "switched on), so Black Box and the crash notice can't be tried for real here")
            records[0] = False
            return
        rep.check("Black Box reads Windows' real crash record for the game", bool(found),
                  record=[dataclasses.asdict(c) if dataclasses.is_dataclass(c) else str(c) for c in found[:1]])
        report = bb.build_report("Pixel Farm", game_dir)
        rep.check("the Black Box report lists the crash", len(report.crashes) >= 1, crashes=len(report.crashes),
                  event_log_ok=report.event_log_ok)
    rw.guarded(rep, "Black Box", black_box)

    with patch.object(CrimsonWindow, "confirm", lambda self, t, text, **_: True), \
            patch.object(CrimsonWindow, "error", lambda self, t, m: rep.note("error shown", title=t, message=m)), \
            patch.object(CrimsonWindow, "info", lambda self, t, m: None), \
            patch.object(crashdoctor_ui.DoctorDialog, "_clear_the_way", lambda self, game: True):
        window = CrimsonWindow()
        window.show()
        window.resize(1280, 820)
        steam = [SteamGame("4242", "Pixel Farm", str(scratch / "SteamLibrary"), str(game_dir), 3 * 1024 ** 2, None,
                           "Steam")]
        window.inventory = Inventory(steam=steam, games=merge_games(steam, []), scanned_at="2026-11-17 10:00")
        window.navigate("Overview")
        rw.pump(0.5)

        # The tracker sees the game run and close, and the "just crashed" notice is offered
        def notice():
            from gg_desktop import assistant_page
            from gg_desktop.games_tracking import tracker_for
            tracker = tracker_for(window)
            tracker.register(window.inventory.games)
            told = []
            real_notify, real_speak = comfort.notify, assistant_page.speak_first

            def notify(win, title, *a, **k):
                told.append(("notice", title))
                return real_notify(win, title, *a, **k)

            def speak(win, prompt, title, *a, **k):
                told.append(("Gravekeeper", title))
                return real_speak(win, prompt, title, *a, **k)
            with patch.object(comfort, "notify", notify), patch.object(assistant_page, "speak_first", speak):
                (game_dir / "crash-after-ms.txt").write_text("20000")       # a game that runs a while, then crashes
                proc = subprocess.Popen([str(exe)])
                seen = rw.wait_for(lambda: bool(tracker.last_active), timeout=60)
                rep.check("the Games tracker sees the game running", seen)
                proc.wait(timeout=90)
                (game_dir / "crash-after-ms.txt").unlink()
                offered = rw.wait_for(lambda: any("just crashed" in t for _how, t in told), timeout=90)
            rep.check("the 'just crashed' notice appears", offered, told=told)
        if records[0]:
            rw.guarded(rep, "crash notice", notice)

        # Crash Doctor runs the real program; only the length of a fine test is shortened
        def doctor():
            fix_kit_page.run(window, "doctor")
            rw.pump(0.5)
            dialog = window.crash_doctor
            dialog.method_box.setCurrentIndex(dialog.method_box.findData("Folder"))
            rw.pump(0.3)
            rep.check("Crash Doctor finds the mod folder by itself", Path(dialog.folder) == mods, folder=str(dialog.folder))
            choices = [(dialog.launch_box.itemText(i), dialog.launch_box.itemData(i)) for i in range(dialog.launch_box.count())]
            rep.note("ways to start the game", choices=[c[0] for c in choices])
            steam = next((i for i, (_t, d) in enumerate(choices) if isinstance(d[1], str)), None)
            if steam is not None and not Path(r"C:\Program Files (x86)\Steam\steam.exe").exists():
                # Steam isn't on this machine: starting through Steam must stop cleanly with every mod back
                dialog.launch_box.setCurrentIndex(steam)
                dialog.start()
                stopped = rw.wait_for(lambda: dialog.phase == "idle", timeout=120)
                text = dialog.result_line.label.text()
                rep.check("when the game can't be started that way, Crash Doctor stops and puts every mod back",
                          stopped and sorted(p.name for p in mods.iterdir()) == sorted(names), result=text[:300],
                          now=sorted(p.name for p in mods.iterdir()))
            direct = next((i for i, (_t, d) in enumerate(choices) if isinstance(d[1], (list, tuple))), None)
            if direct is not None:
                dialog.launch_box.setCurrentIndex(direct)
            started = time.time()
            dialog.start()
            rw.wait_for(lambda: dialog.phase != "idle", timeout=60)
            dialog.plan = dataclasses.replace(dialog.plan, fine_after=12)
            done = rw.wait_for(lambda: dialog.phase == "idle", timeout=900)
            text = dialog.result_line.label.text()
            dialog.grab().save(str(args.output / "crash-doctor-real.png"))
            rep.check("Crash Doctor finishes on the real program", done, minutes=round((time.time() - started) / 60, 1))
            rep.check("it names Bad Mod", "Bad Mod" in text, result=text[:300])
            rep.check("every mod is back where it was", sorted(p.name for p in mods.iterdir()) == sorted(names),
                      now=sorted(p.name for p in mods.iterdir()))
        rw.guarded(rep, "Crash Doctor", doctor)
        subprocess.run(["taskkill", "/IM", "PixelFarm.exe", "/F"], capture_output=True)    # nothing left running
        window.close()
    return rep.finish()


if __name__ == "__main__":
    raise SystemExit(main())
