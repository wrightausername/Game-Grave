"""First-launch welcome: shows once, steps through three screens, Scan my games starts the scan, then never again."""
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
    faulthandler.dump_traceback_later(120, exit=True)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication
    from core import default_settings
    from gg_desktop.app import CrimsonWindow
    from gg_desktop import welcome_ui, welcome_data
    from gg_desktop.settings_store import load_settings

    app = QApplication.instance() or QApplication([])

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
            dialog = welcome_ui.show_if_needed(window)
            assert dialog is not None and dialog.isVisible(), "A first launch shows the welcome"
            settle(200)
            for step in range(len(welcome_data.STEPS)):
                assert dialog.title.text() == welcome_data.STEPS[step]["title"], step
                assert dialog.back_button.isVisible() == (step > 0), step
                assert dialog.next_button.text() == welcome_data.next_label(step), step
                assert dialog.grab().save(str(args.output / f"welcome-{step + 1}.png")), step
                assert window.grab().save(str(args.output / f"welcome-window-{step + 1}.png")), step
                if step < welcome_data.LAST:
                    dialog.next_button.click()
                    settle(100)
            dialog.back_button.click()
            settle(50)
            assert dialog.index == welcome_data.LAST - 1, "Back goes one screen back"
            dialog.next_button.click()
            dialog.next_button.click()
            settle(200)
            assert not dialog.isVisible(), "Scan my games closes the welcome"
            scan.assert_called_once()
            assert load_settings().get("welcome_seen") is True, "Seen is saved"
            assert window.settings.get("welcome_seen") is True
            assert welcome_ui.show_if_needed(window) is None, "The welcome never shows twice"

            fresh = dict(window.settings)
            fresh.pop("welcome_seen", None)
            window.settings = fresh
            skipped = welcome_ui.show_if_needed(window)
            assert skipped is not None
            settle(100)
            skipped.skip_button.click()
            settle(100)
            assert not skipped.isVisible(), "Skip intro closes it"
            assert scan.call_count == 1, "Skip does not scan"
            assert window.settings.get("welcome_seen") is True, "Skip also counts as seen"
            error.assert_not_called()
    print("Welcome smoke passed")


if __name__ == "__main__":
    main()
