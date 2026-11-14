"""Welcome tour: shows at startup, steps through every screen, Skip keeps it for next time, "Don't show this at startup"
and finishing turn it off, Scan my games starts the scan, and Settings and the ? button open it again."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import faulthandler
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("_ci_temp"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    faulthandler.dump_traceback_later(160, exit=True)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QCoreApplication, QEvent, QTimer
    from PySide6.QtWidgets import QApplication, QPushButton
    from core import default_settings
    from gg_desktop.app import CrimsonWindow
    from gg_desktop import welcome_ui, welcome_data
    from gg_desktop.settings_store import load_settings

    app = QApplication.instance() or QApplication([])
    key = welcome_data.STARTUP_KEY

    def settle(ms=0):
        end = datetime.now() + timedelta(milliseconds=ms)
        while True:
            app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            if datetime.now() >= end:
                break

    with tempfile.TemporaryDirectory(prefix="GG-welcome-") as temp:
        root = Path(temp)
        env = {"LOCALAPPDATA": str(root / "Local"), "APPDATA": str(root / "Roaming"), "USERPROFILE": str(root / "User")}
        for value in env.values():
            Path(value).mkdir(parents=True)
        (root / "Prefs").mkdir()
        with patch.dict(os.environ, env), patch("gg_desktop.app.load_settings", side_effect=default_settings), \
             patch("core.config_dir", return_value=root / "Prefs"), \
             patch.object(CrimsonWindow, "info"), patch.object(CrimsonWindow, "error") as error, \
             patch.object(CrimsonWindow, "start_scan") as scan:
            window = CrimsonWindow()
            window.resize(1280, 790)
            window.show()
            settle(300)

            # 1. Startup: it shows. Walk every screen, then back, then Skip: it shows again next time.
            dialog = welcome_ui.show_if_needed(window)
            assert dialog is not None and dialog.isVisible(), "The tour shows at startup by default"
            settle(200)
            for step in range(len(welcome_data.STEPS)):
                assert dialog.title.text() == welcome_data.STEPS[step]["title"], step
                assert dialog.back_button.isVisible() == (step > 0), step
                assert dialog.next_button.text() == welcome_data.next_label(step), step
                assert dialog.skip_button.text() == welcome_data.close_label(step), step
                shown = sum(1 for frame, _n, _t in dialog.point_rows if frame.isVisible())
                assert shown == len(welcome_data.STEPS[step]["points"]), (step, shown)
                assert dialog.grab().save(str(args.output / f"welcome-{step + 1}.png")), step
                if step < welcome_data.LAST:
                    dialog.next_button.click()
                    settle(80)
            assert window.grab().save(str(args.output / "welcome-window.png"))
            for _ in range(welcome_data.LAST):
                dialog.back_button.click()
                settle(30)
            assert dialog.index == 0
            dialog.skip_button.click()
            settle(150)
            assert not dialog.isVisible() and scan.call_count == 0, "Skip closes without scanning"
            assert window.settings.get(key, True) is not False, "Skip keeps the tour for the next start"
            assert welcome_data.should_show(window.settings)

            # 2. "Don't show this at startup" turns it off for good; it is saved.
            dialog = welcome_ui.show_if_needed(window)
            assert dialog is not None
            settle(100)
            dialog.never.setChecked(True)
            dialog.skip_button.click()
            settle(150)
            assert window.settings.get(key) is False and load_settings().get(key) is False, "The choice is saved"
            assert welcome_ui.show_if_needed(window) is None, "Off means it no longer opens at startup"

            # 3. The ? button opens it again any time (a normal modal window), and Settings has the switch and a Watch button.
            seen = {}

            def look_and_close():
                tour = window._welcome_dialog
                seen.update(visible=tour.isVisible(), index=tour.index)
                tour.reject()

            help_button = next(b for b in window.top_bar.findChildren(QPushButton)
                               if b.accessibleName() == "Help: watch the welcome tour")
            QTimer.singleShot(250, look_and_close)
            help_button.click()
            settle(100)
            assert seen == {"visible": True, "index": 0}, seen
            assert window.settings.get(key) is False, "Watching it again does not switch startup back on"
            window.navigate("Settings")
            settle(300)
            assert key in window.settings_controls, "Settings has the startup switch"
            watch = next(b for b in window.page.findChildren(QPushButton) if b.accessibleName() == "Watch the welcome tour")
            assert window.grab().save(str(args.output / "welcome-settings.png"))
            seen.clear()
            QTimer.singleShot(250, look_and_close)
            watch.click()
            settle(100)
            assert seen.get("visible") is True, "Settings opens the tour"

            # 4. Finishing with Scan my games starts the scan and turns the startup tour off.
            window.navigate("Overview")
            settle(200)
            window.settings[key] = True

            def finish():
                tour = window._welcome_dialog
                for _ in range(welcome_data.LAST):
                    tour.next_button.click()
                tour.next_button.click()

            QTimer.singleShot(250, finish)
            help_button.click()
            settle(200)
            assert not window._welcome_dialog.isVisible()
            scan.assert_called_once()
            assert window.settings.get(key) is False, "Finishing the tour turns it off at startup"
            error.assert_not_called()
    print("Welcome tour smoke passed")


if __name__ == "__main__":
    main()
