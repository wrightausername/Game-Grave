"""Native Qt check of the Hardware tab with fixture readings: parts, live tiles and charts, recording a play session
(too short is thrown away, long enough is saved), advisor notes that follow the saved sessions, filters, spec sheet
copy, clearing, and that nothing outside Game Grave's own sessions file is written."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("_ci_temp"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    root_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root_dir))
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication, QPushButton
    import core
    from core import default_settings
    from gg_desktop import hardware_core as hw
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.models import GameRecord
    from gg_desktop.ready_room_services import parse_news
    from tests.test_hardware import SAMPLE

    app = QApplication.instance() or QApplication([])

    def settle(ms=0):
        end = datetime.now() + timedelta(milliseconds=ms)
        while True:
            app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            if datetime.now() >= end:
                break

    def wait_for(test, label, seconds=20):
        end = datetime.now() + timedelta(seconds=seconds)
        while not test():
            settle(20)
            assert datetime.now() < end, "Timed out waiting for " + label

    def body(window):
        return window.page.hardware

    def texts(window):
        from PySide6.QtWidgets import QLabel
        return [w.text() for w in window.page.findChildren(QLabel)]

    def pressed(window, text):
        found = [b for b in window.page.findChildren(QPushButton) if b.text() == text]
        assert found, "No button named " + text
        return found[0]

    class FakeClock:
        now = 5000.0

        def __call__(self):
            return self.now

    clock = FakeClock()
    ticks = {"n": 0}

    def cpu_times():
        ticks["n"] += 1
        return ticks["n"] * 10, ticks["n"] * 20  # half idle, every reading

    def gpu():
        return hw.GpuLive("NVIDIA GeForce RTX 3060 Ti", 88.0, 7900.0, 8192.0, 71.0)

    def game(name, letter, gb):
        return GameRecord(name, name, "Steam", None, f"{letter}:\\Games\\{name}", "fixture", gb * 1024 ** 3, "fixture",
                          None, "", "installed", ())

    with tempfile.TemporaryDirectory(prefix="GG-hardware-") as temp:
        root = Path(temp)
        sampler = hw.Sampler(cpu_times=cpu_times, memory=lambda: (18.4, 32.0), gpu=gpu, clock=clock)
        reads = []
        with patch.dict(os.environ, {"LOCALAPPDATA": str(root / "Local")}), \
             patch("gg_desktop.app.load_settings", side_effect=default_settings), \
             patch("gg_desktop.ready_room_services.config_dir", return_value=root / "Prefs"), \
             patch("gg_desktop.ready_room_services.fetch_one",
                   side_effect=lambda sid, name: parse_news({"appnews": {"appid": int(sid), "newsitems": []}}, sid, name)), \
             patch("gg_desktop.hardware_core.query_specs", side_effect=lambda: reads.append(1) or json.dumps(SAMPLE)), \
             patch("gg_desktop.hardware_page.Monitor.__init__.__defaults__", (sampler, clock)), \
             patch("gg_desktop.hardware_page.TICK_MS", 200), \
             patch.object(CrimsonWindow, "info") as info, patch.object(CrimsonWindow, "error") as error:
            window = CrimsonWindow()
            window.resize(1366, 790)
            window.show()
            window.inventory.games = [game("Big Game", "D", 112), game("Other Game", "D", 100), game("Small Game", "C", 50)]
            settle(100)
            assert "Hardware" in window.nav_buttons, "Hardware is missing from the sidebar"
            names = list(window.nav_buttons)
            assert names.index("Game DNA") + 1 == names.index("Hardware") and names.index("Hardware") + 1 == names.index("Undo Center")

            window.navigate("Hardware")
            wait_for(lambda: window.page.isVisible(), "the Hardware page")
            assert window.current_route == "Hardware" and window.page.banner_artwork.art == "banner_hardware.jpg"
            wait_for(lambda: getattr(window, "hardware_specs", None) is not None, "the parts list")
            wait_for(lambda: body(window).monitor.history, "the first live reading")
            settle(200)
            shown = texts(window)
            assert any("AMD Ryzen 5 5600X" in t for t in shown) and any("RTX 3060 Ti" in t for t in shown)
            assert any("B550 TOMAHAWK" in t for t in shown) and any("2560 x 1440 at 144 Hz" in t for t in shown)
            assert any("D: WDC WD20EZAZ" in t for t in shown)
            assert not any(t.startswith("Notes appear") for t in shown)
            # Live tiles come from the (fake) sampler: memory, video memory and temperature.
            values = [v.text() for v in body(window).metrics.values]
            assert values[2] == "18.4 of 32 GB" and values[3] == "7.7 of 8 GB" and values[4] == "71 °C", values
            assert values[5] == "2", values
            # No recorded sessions yet: every reading-based note asks for sessions instead of claiming anything.
            assert body(window).sessions == []
            assert sum(1 for t in shown if t == "NEEDS SESSIONS") == 3, [t for t in shown if t.isupper()]
            assert any("Moving games is done in Steam" in t for t in shown), "storage note comes from install folders"
            assert any("NO PURCHASE NEEDED" == t for t in shown)
            assert body(window).pc_tab.isVisible() and not body(window).adv_tab.isVisible(), "Your PC is the first tab"
            assert window.grab().save(str(args.output / "hardware-no-sessions-1366.png"))

            # The advisor is its own tab inside Hardware.
            pressed(window, "Upgrade Advisor").click()
            settle(100)
            assert body(window).adv_tab.isVisible() and not body(window).pc_tab.isVisible()
            assert window.hardware_tab == "Upgrade Advisor"
            assert window.grab().save(str(args.output / "hardware-advisor-empty-1366.png"))

            # A too-short recording is thrown away.
            pressed(window, "Record Play Session").click()
            assert body(window).monitor.recording
            clock.now += 30
            wait_for(lambda: body(window).monitor.readings, "a recorded reading")
            pressed(window, "Stop and Save Session").click()
            settle(100)
            assert hw.load_sessions() == [] and body(window).sessions == []
            assert "shorter than 2 minutes" in body(window).record_status.text()

            # Long enough sessions are saved and the notes follow them.
            for i in range(3):
                pressed(window, "Record Play Session").click()
                start = body(window).monitor.started
                wait_for(lambda: len(body(window).monitor.readings) >= 2, "readings")
                clock.now = start + 1800
                pressed(window, "Stop and Save Session").click()
                settle(80)
                clock.now += 10
            assert len(hw.load_sessions()) == 3 and len(body(window).sessions) == 3
            shown = texts(window)
            assert "STRONGEST SIGNAL" in shown and "NOT NEEDED YET" in shown and "NO SIGN OF A LIMIT" in shown, [t for t in shown if t.isupper()]
            assert any("Video memory peaked at 7.7 GB of 8 GB in 3 of 3 sessions" in t for t in shown), [t for t in shown if "Video" in t]
            assert any(e["kind"] == "Hardware session recorded" for e in core.get_activity())
            assert sum(1 for t in shown if t.endswith(" readings")) == 3, [t for t in shown if "readings" in t]
            assert any(t.startswith("GPU ") and t.endswith("%") for t in shown), [t for t in shown if t.startswith("GPU")]
            window.page.ensureWidgetVisible(body(window).advice_panel)
            settle(100)
            assert window.grab().save(str(args.output / "hardware-with-sessions-1366.png"))

            # The whole advisor tab, then the whole Your PC tab, so every panel is reviewed.
            window.resize(1366, 1100)
            settle(300)
            assert window.grab().save(str(args.output / "hardware-advisor-full-1366.png"))
            pressed(window, "Your PC").click()
            window.resize(1366, 1500)
            settle(300)
            assert body(window).pc_tab.isVisible() and not body(window).adv_tab.isVisible()
            window.page.ensureWidgetVisible(body(window).monitor_panel)
            settle(100)
            page_body = body(window)
            # The Live Monitor is the centre of the tab: full width, above Your Parts and Drives, with big gauges.
            assert page_body.monitor_panel.width() >= page_body.rig.width() * 0.9, (page_body.monitor_panel.width(), page_body.rig.width())
            assert page_body.monitor_panel.y() < page_body.parts_panel.y() and page_body.monitor_panel.y() < page_body.drives_panel.y()
            assert all(g.width() >= 140 for g in page_body.gauges.values()), [g.width() for g in page_body.gauges.values()]
            assert all(c.height() >= 120 for c, _ in page_body.charts.values())
            assert window.grab().save(str(args.output / "hardware-full-1366.png"))
            pressed(window, "Upgrade Advisor").click()
            window.resize(1366, 790)
            settle(200)

            # Filters only change what is listed.
            pressed(window, "Memory").click()
            settle(60)
            shown = texts(window)
            assert "NOT NEEDED YET" in shown and "STRONGEST SIGNAL" not in shown
            pressed(window, "All").click()
            settle(60)
            assert "STRONGEST SIGNAL" in texts(window)

            # The page survives a rebuild and keeps its readings and sessions.
            window.navigate("Overview")
            settle(150)
            window.navigate("Hardware")
            wait_for(lambda: window.page.isVisible(), "the rebuilt page")
            settle(300)
            assert len(body(window).sessions) == 3 and any("AMD Ryzen" in t for t in texts(window))
            assert body(window).adv_tab.isVisible(), "the chosen tab is remembered after a rebuild"
            assert len(reads) == 1, "the parts are read once, not on every visit"

            # Spec sheet goes to the clipboard and nowhere else.
            pressed(window, "Copy Specs").click()
            copied = QGuiApplication.clipboard().text()
            assert "CPU: AMD Ryzen 5 5600X" in copied and "Drive D:" in copied

            # Re-read asks Windows again.
            pressed(window, "Re-read Hardware").click()
            wait_for(lambda: len(reads) == 2, "the second read")
            settle(150)

            # Clearing needs confirmation and removes only the sessions file.
            with patch.object(window, "confirm", return_value=False):
                pressed(window, "Clear Sessions").click()
            assert len(hw.load_sessions()) == 3
            with patch.object(window, "confirm", return_value=True):
                pressed(window, "Clear Sessions").click()
            settle(100)
            assert hw.load_sessions() == [] and body(window).sessions == []
            assert sum(1 for t in texts(window) if t == "NEEDS SESSIONS") == 3

            assert error.call_count == 0 and info.call_count == 0, (error.call_args_list, info.call_args_list)
            window.navigate("Overview")
            settle(200)
            assert not body_alive(window), "the sampler must stop when no Hardware tab is open"
            window.close()
            settle(100)
    print("PASS: Hardware tab shows parts and live load, records and saves sessions, and notes follow only those sessions.")
    return 0


def body_alive(window):
    monitor = getattr(window, "hardware_monitor", None)
    return bool(monitor and (monitor.viewers or monitor.timer.isActive()))


if __name__ == "__main__":
    raise SystemExit(main())
