"""Native Qt check of Autopsy: two fixture captures, comparison table, graph, copy, honest error and short states."""
from __future__ import annotations

import argparse
import math
import os
from pathlib import Path
import sys
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch


def capture(path, base, spike, count=2400):
    lines = ["Application,ProcessID,MsBetweenPresents,Dropped"]
    for i in range(count):
        ms = base + 0.8 * math.sin(i / 7.0) + (spike if i % 80 == 0 else 0)
        lines.append(f"game.exe,42,{ms:.3f},0")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("_ci_temp"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication
    from core import default_settings
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.ready_room_services import parse_news

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

    def live(window):
        return window.page.autopsy.autopsy

    with tempfile.TemporaryDirectory(prefix="GG-autopsy-") as temp:
        root = Path(temp)
        found = root / "PresentMon"
        found.mkdir()
        before = capture(found / "PresentMon-Hades-2024-05-01T100000.csv", 16.7, 28.0)
        after = capture(found / "PresentMon-Hades-2024-05-02T100000.csv", 11.4, 12.0)
        now = datetime.now().timestamp()
        os.utime(before, (now - 2 * 86400, now - 2 * 86400))
        os.utime(after, (now - 86400, now - 86400))
        short = capture(root / "short-run.csv", 11.0, 0.0, count=200)
        junk = root / "notes.csv"
        junk.write_text("name,score\nalex,3\n", encoding="utf-8")
        with patch.dict(os.environ, {"LOCALAPPDATA": str(root / "Local")}), \
             patch("gg_desktop.app.load_settings", side_effect=default_settings), \
             patch("core.config_dir", return_value=root / "Prefs"), \
             patch("gg_desktop.autopsy_library.default_roots", return_value=[found]), \
             patch("gg_desktop.ready_room_services.config_dir", return_value=root / "Prefs"), \
             patch("gg_desktop.ready_room_services.fetch_one",
                   side_effect=lambda sid, name: parse_news({"appnews": {"appid": int(sid), "newsitems": []}}, sid, name)), \
             patch.object(CrimsonWindow, "info"), patch.object(CrimsonWindow, "error") as error:
            window = CrimsonWindow()
            window.resize(1280, 790)
            window.show()
            window.navigate("Ready Room")
            settle(300)
            panel = window.page.autopsy
            assert panel is not None, "Autopsy panel is missing from Ready Room"
            assert not panel.strip_open and panel.maximumHeight() <= 50, "Autopsy starts as one slim line"

            # The automatic pass finds both captures on its own, with no click and no dialog.
            wait_for(lambda: len(live(window).entries) == 2, "the automatic pass")
            body = live(window)
            assert "2 of 10 kept" in panel.detail_label.text() and "better" in panel.detail_label.text(), panel.detail_label.text()
            comparison = body.result.comparison
            assert comparison.comparable, comparison.summary
            rows = {r.metric: r for r in comparison.rows}
            assert rows["Average FPS"].verdict == "better" and rows["Median frame time (ms)"].verdict == "better"
            assert rows["Spikes per minute"].verdict == "within noise", rows["Spikes per minute"]
            assert "One capture each" in body.summary.text()
            assert body.graph.before and body.graph.after and len(body.graph.before) <= 200
            assert body.grid.count() >= 4 * 8, body.grid.count()
            assert body.combos["before"].currentText().startswith("Hades") and body.count.text() == "2 of 10 captures kept"

            # Passes are spaced out, and are skipped while a game is running.
            from gg_desktop import autopsy_ui
            assert not autopsy_ui.scan_allowed(window), "a second pass right away is refused"
            window.autopsy_last_pass = None
            with patch("gg_desktop.autopsy_ui.game_running", return_value=True):
                assert not autopsy_ui.scan_allowed(window), "no pass while a game is running"
            assert autopsy_ui.scan_allowed(window)

            # Open it, describe the change, copy.
            panel.strip_toggle.click()
            settle(80)
            assert panel.strip_open
            body.note.setText("Updated the graphics driver")
            body.copy_button.click()
            copied = QApplication.clipboard().text()
            assert "Change: Updated the graphics driver" in copied and "2024-05-01" in copied and str(root) not in copied
            window.page.ensureWidgetVisible(window.page.autopsy)
            settle(80)
            assert window.grab().save(str(args.output / "ready-room-autopsy-1280.png"))

            # A page rebuild keeps the choice and the note without reading any capture again.
            window.navigate("Ready Room")
            settle(300)
            body = live(window)
            assert body.result is not None and body.note.text() == "Updated the graphics driver" and body.graph.after

            # A file that is not a capture is explained in words, with no dialog, and is not added.
            with patch("gg_desktop.autopsy_ui.QFileDialog.getOpenFileName", return_value=(str(junk), "")):
                body.add_button.click()
            wait_for(lambda: "not a frame-time capture" in live(window).summary.text(), "the refusal")
            assert len(live(window).entries) == 2

            # A short capture is added, and comparing it is refused honestly.
            with patch("gg_desktop.autopsy_ui.QFileDialog.getOpenFileName", return_value=(str(short), "")):
                live(window).add_button.click()
            wait_for(lambda: len(live(window).entries) == 3, "the short capture")
            body = live(window)
            short_at = body.combos["after"].findData(next(e.id for e in body.entries if e.name == "short-run.csv"))
            body.combos["after"].setCurrentIndex(short_at)
            settle(50)
            assert "will not draw a conclusion" in body.summary.text(), body.summary.text()
            assert not body.copy_button.isEnabled()

            # Only ten are kept: the oldest summary is replaced, and no capture file is touched.
            from gg_desktop import autopsy_library as lib
            extra = root / "extra"
            extra.mkdir()
            for i in range(9):
                path = capture(extra / f"PresentMon-Doom-2024-06-{i + 1:02d}T100000.csv", 12.0 + i, 5.0, count=900)
                os.utime(path, (now - 3600 * (9 - i),) * 2)
                lib.add_by_hand(path)
            live(window).reload()
            assert len(live(window).entries) == 10 and live(window).count.text() == "10 of 10 captures kept"
            assert before.exists() and after.exists() and short.exists(), "capture files are never removed"
            assert "Hades-2024-05-01" not in " ".join(e.name for e in live(window).entries), "the oldest was replaced"
            error.assert_not_called()
    print("Autopsy smoke passed")


if __name__ == "__main__":
    main()
