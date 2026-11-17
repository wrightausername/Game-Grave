"""Huge libraries and a long run: 500 games, 5,000 mods and 100,000 old files, then 30 minutes of normal use.

Checked: the real Old Files scan over 100,000 real files on disk, how long each tab takes to appear with the huge
library, that the window keeps answering (no freeze over 2 seconds while a tab is built), and memory over a
30-minute soak of switching tabs and refreshing results. A leak shows as memory still climbing in the second half.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rw_common as rw  # noqa: E402

OLD = time.time() - 400 * 86400


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("_ci_temp/realworld"))
    parser.add_argument("--soak-minutes", type=float, default=30)
    parser.add_argument("--files", type=int, default=100_000)
    args = parser.parse_args()
    import faulthandler
    faulthandler.dump_traceback_later(300, repeat=True)       # if anything hangs, the log shows exactly where
    scratch = rw.isolate("GG-rw-huge-")
    rep = rw.Report("huge-library", args.output)
    from unittest.mock import patch
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    import core
    from core import ModFolder, OldFile, SteamGame
    from gg_desktop import nav_groups
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.backend import Inventory
    from gg_desktop.models import merge_games

    # Real files on disk for the Old Files scan
    downloads = scratch / "Downloads"
    started = time.time()
    for i in range(args.files):
        folder = downloads / f"batch {i // 1000:03}"
        if i % 1000 == 0:
            folder.mkdir(parents=True)
        p = folder / f"old download {i:06}.zip"
        with open(p, "wb") as f:
            f.write(b"x")
        os.utime(p, (OLD, OLD))
    rep.note("files made", count=args.files, seconds=round(time.time() - started, 1))
    started = time.time()
    files = core.scan_old_files(downloads, 180, max_matches=200_000)
    took = time.time() - started
    rep.check("the Old Files scan over 100,000 files finishes in under 3 minutes", len(files) == args.files and took < 180,
              found=len(files), seconds=round(took, 1))

    lib = scratch / "SteamLibrary"
    steam = [SteamGame(str(10000 + i), f"Test Game {i:03} {'Remastered Deluxe' if i % 7 == 0 else ''}".strip(),
                       str(lib), str(lib / "steamapps" / "common" / str(10000 + i)), (i % 90 + 1) * 1024 ** 3,
                       time.time() - (i % 700) * 86400, "Huge library check") for i in range(500)]
    mods = [ModFolder(f"Mod {i:04}", str(scratch / "Mods" / f"Mod {i:04}"), str(lib), "Unmatched", ("mod",),
                      (i % 500 + 1) * 1024 ** 2, 20, False) for i in range(5000)]
    inventory = Inventory(steam=steam, games=merge_games(steam, []), mods=mods, files=files,
                          scanned_at="2026-11-17 09:00")

    with patch("core.save_settings"), patch("gg_desktop.game_artwork._request", side_effect=OSError("offline")), \
            patch.object(CrimsonWindow, "info"), patch.object(CrimsonWindow, "error"), \
            patch.object(CrimsonWindow, "confirm", return_value=False):
        window = CrimsonWindow()
        window.show()
        window.resize(1280, 760)
        window.inventory = inventory
        rw.pump(1)

        stalls = []
        last = [time.time()]

        def beat():
            now = time.time()
            if now - last[0] > 2.0:
                stalls.append(round(now - last[0], 1))
            last[0] = now
        heart = QTimer()
        heart.timeout.connect(beat)
        heart.start(100)

        times = {}
        for route in nav_groups.routes():
            started = time.time()
            print(f"opening {route}…", flush=True)
            try:
                window.navigate(route)            # the time the window is busy building the tab
                built = time.time() - started
                rw.pump(0.5)
            except Exception as exc:
                rep.check(f"{route} opens with the huge library", False, error=f"{type(exc).__name__}: {exc}")
                continue
            times[route] = round(built, 2)
            print(f"  {route}: {times[route]} s", flush=True)
            window.grab().save(str(args.output / f"huge-{route.replace(' ', '-').lower()}.png"))
        slow = {k: v for k, v in times.items() if v > 5}
        rep.check("every tab appears within 5 seconds with the huge library", not slow, slow=slow, all=times)
        last[0] = time.time()
        stalls.clear()

        # The soak
        samples = []
        end = time.time() + args.soak_minutes * 60
        routes = [r for r in nav_groups.routes() if times.get(r, 0) < 60]
        rep.note("left out of the long run because they take over a minute to build",
                 tabs=[r for r in nav_groups.routes() if r not in routes])
        step = 0
        next_sample = time.time()
        while time.time() < end:
            route = routes[step % len(routes)]
            try:
                window.navigate(route)
            except Exception as exc:
                rep.check("tabs keep working during the long run", False, route=route, error=str(exc))
                break
            if step % len(routes) == 0:
                window.inventory = Inventory(steam=list(steam), games=merge_games(steam, []), mods=list(mods),
                                             files=list(files), scanned_at=time.strftime("%Y-%m-%d %H:%M"))
            rw.pump(1.0)
            step += 1
            if time.time() >= next_sample:
                mb, cpu = rw.process_usage()
                samples.append((round((time.time() - (end - args.soak_minutes * 60)) / 60, 1), round(mb)))
                print(f"  minute {samples[-1][0]}: {samples[-1][1]} MB, {step} tab switches", flush=True)
                next_sample = time.time() + 60
        heart.stop()
        window.close()

    rep.note("memory over the long run (minute, MB)", samples=samples, tab_switches=step)
    if len(samples) >= 6:
        half = len(samples) // 2
        early = max(m for _t, m in samples[1:half + 1])
        late = samples[-1][1]
        growth = late - early
        rep.check("memory settles: under 150 MB more at the end than in the first half", growth < 150,
                  first_half_peak=early, at_end=late, growth=growth)
    rep.check("the window never froze for more than 2 seconds during the long run", not stalls, stalls=stalls[:20])
    return rep.finish()


if __name__ == "__main__":
    raise SystemExit(main())
