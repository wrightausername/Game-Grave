"""Don't slow my games: Game Grave's own CPU and memory while a stand-in game runs flat out.

The stand-in game is a small program that keeps every CPU core busy, like a game would. With it running, Game Grave
must notice it, show "Paused while you play", hold back its background work, and use almost no CPU itself.
Measured over 2 minutes with the game running, after 1 minute of the same window idle without a game to compare.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rw_common as rw  # noqa: E402

GAME = r"""
using System; using System.Threading;
class StandIn {
  static void Main() {
    for (int i = 0; i < Environment.ProcessorCount; i++) {
      new Thread(() => { double x = 0; while (true) { x = Math.Sqrt(x + 1.0001); } }) { IsBackground = false }.Start();
    }
  }
}
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("_ci_temp/realworld"))
    parser.add_argument("--seconds", type=int, default=120)
    args = parser.parse_args()
    scratch = rw.isolate("GG-rw-game-")
    rep = rw.Report("game-running", args.output)
    from unittest.mock import patch
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from core import SteamGame
    from gg_desktop import autopilot_ui, autopsy_ui, local_ai_ui
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.backend import Inventory
    from gg_desktop.games_tracking import tracker_for, PLAYING
    from gg_desktop.models import merge_games

    lib = scratch / "SteamLibrary"
    folder = lib / "steamapps" / "common" / "Stand In"
    folder.mkdir(parents=True)
    exe = folder / "StandIn.exe"
    if not rw.guarded(rep, "build the stand-in game", lambda: rw.compile_cs(GAME, exe) or True):
        return rep.finish()
    steam = [SteamGame("777", "Stand In", str(lib), str(folder), 50 * 1024 ** 2, None, "Game check")]

    with patch("core.save_settings"), patch("gg_desktop.game_artwork._request", side_effect=OSError("offline")), \
            patch.object(CrimsonWindow, "info"), patch.object(CrimsonWindow, "error"), \
            patch.object(CrimsonWindow, "confirm", return_value=False):
        window = CrimsonWindow()
        window.show()
        window.resize(1280, 760)
        window.inventory = Inventory(steam=steam, games=merge_games(steam, []), scanned_at="2026-11-17 09:00")
        window.navigate("Overview")
        tracker = tracker_for(window)
        tracker.register(window.inventory.games)
        rw.pump(2)

        def measure(seconds):
            mb0, cpu0 = rw.process_usage()
            t0 = time.time()
            peak = mb0
            while time.time() - t0 < seconds:
                rw.pump(1)
                peak = max(peak, rw.process_usage()[0])
            mb1, cpu1 = rw.process_usage()
            return round(100 * (cpu1 - cpu0) / (time.time() - t0), 2), round(mb1), round(peak)

        idle_cpu, idle_mb, _ = measure(60)
        rep.note("idle, no game", cpu_percent_of_one_core=idle_cpu, memory_mb=idle_mb)

        game = subprocess.Popen([str(exe)])
        try:
            seen = rw.wait_for(lambda: bool(tracker.last_active), timeout=60)
            rep.check("Game Grave notices the game", seen)
            rw.pump(2)
            chip = getattr(window, "paused_chip", None)
            rw.wait_for(lambda: chip is not None and "Stand In" in chip.text(), timeout=30)   # refreshed every 10 s
            shown = chip.text() if chip is not None else ""
            rep.check("the top bar says it's paused while you play", chip is not None and chip.isVisible()
                      and "Stand In" in shown, text=shown)
            holds = {"plans": autopilot_ui.game_running(window), "frame checks": autopsy_ui.game_running(window),
                     "local AI": local_ai_ui.game_running(window)}
            rep.check("background work knows a game is running", all(holds.values()), **holds)
            rep.check("game checks slow down while playing", tracker.timer.interval() >= PLAYING,
                      interval_ms=tracker.timer.interval())
            cpu, mb, peak = measure(args.seconds)
            rep.check("Game Grave uses under 2% of one CPU core while the game runs", cpu < 2.0,
                      cpu_percent_of_one_core=cpu, idle_was=idle_cpu)
            rep.check("Game Grave's memory stays flat while the game runs (under 30 MB more)", peak - idle_mb < 30,
                      memory_mb=mb, peak_mb=peak, idle_mb=idle_mb)
            game_mb, game_cpu = rw.process_usage(game.pid)
            rep.note("the stand-in game", cpu_seconds=round(game_cpu), memory_mb=round(game_mb))
        finally:
            game.kill()
        window.close()
    return rep.finish()


if __name__ == "__main__":
    raise SystemExit(main())
