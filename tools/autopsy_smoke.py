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

    def choose(window, key, path):
        with patch("gg_desktop.autopsy_ui.QFileDialog.getOpenFileName", return_value=(str(path), "")):
            getattr(live(window), f"{key}_button").click()
        settle()

    with tempfile.TemporaryDirectory(prefix="GG-autopsy-") as temp:
        root = Path(temp)
        before = capture(root / "before-run.csv", 16.7, 28.0)
        after = capture(root / "after-run.csv", 11.4, 12.0)
        short = capture(root / "short-run.csv", 11.0, 0.0, count=200)
        junk = root / "notes.csv"
        junk.write_text("name,score\nalex,3\n", encoding="utf-8")
        with patch.dict(os.environ, {"LOCALAPPDATA": str(root / "Local")}), \
             patch("gg_desktop.app.load_settings", side_effect=default_settings), \
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
            body = live(window)
            assert not body.compare_button.isEnabled() and not body.copy_button.isEnabled()
            assert "does not record frames" in body.summary.text()

            choose(window, "before", before)
            assert not live(window).compare_button.isEnabled(), "Compare needs both files"
            choose(window, "after", after)
            body = live(window)
            assert body.compare_button.isEnabled()
            assert body.names["before"].text() == "before-run.csv" and body.names["after"].text() == "after-run.csv"
            body.note.setText("Updated the graphics driver")
            body.compare_button.click()
            wait_for(lambda: live(window).result is not None, "the comparison")
            body = live(window)
            comparison = body.result.comparison
            assert comparison.comparable, comparison.summary
            rows = {r.metric: r for r in comparison.rows}
            assert rows["Average FPS"].verdict == "better" and rows["Median frame time (ms)"].verdict == "better"
            assert "One capture each" in body.summary.text()
            assert body.graph.before and body.graph.after and len(body.graph.before) <= 700
            assert body.grid.count() >= 4 * 8, body.grid.count()
            assert body.copy_button.isEnabled()
            body.copy_button.click()
            copied = QApplication.clipboard().text()
            assert "Change: Updated the graphics driver" in copied and "before-run.csv" in copied and str(root) not in copied
            window.page.ensureWidgetVisible(window.page.autopsy)
            settle(80)
            assert window.grab().save(str(args.output / "ready-room-autopsy-1280.png"))

            # A page rebuild keeps the files, the note and the newest result.
            window.navigate("Ready Room")
            settle(300)
            body = live(window)
            assert body.result is not None and body.names["after"].text() == "after-run.csv"
            assert body.note.text() == "Updated the graphics driver" and body.graph.after

            # A file that is not a capture is explained in words, with no dialog.
            choose(window, "after", junk)
            live(window).compare_button.click()
            wait_for(lambda: live(window).result is not None and live(window).result.error, "the refusal")
            assert "not a frame-time capture" in live(window).summary.text()
            assert not live(window).copy_button.isEnabled()

            # A short capture is refused honestly.
            choose(window, "after", short)
            live(window).compare_button.click()
            wait_for(lambda: live(window).result is not None and not live(window).result.error, "the short result")
            assert "will not draw a conclusion" in live(window).summary.text()
            error.assert_not_called()
    print("Autopsy smoke passed")


if __name__ == "__main__":
    main()
