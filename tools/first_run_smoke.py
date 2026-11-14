"""What a brand-new user sees before the first scan: every sidebar tab opens, says what to do, and nothing crashes."""
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
    faulthandler.dump_traceback_later(200, exit=True)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QAbstractButton, QApplication, QComboBox, QLineEdit
    from core import default_settings
    from gg_desktop.app import CrimsonWindow

    app = QApplication.instance() or QApplication([])

    def settle(ms=0):
        end = datetime.now() + timedelta(milliseconds=ms)
        while True:
            app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            if datetime.now() >= end:
                break

    with tempfile.TemporaryDirectory(prefix="GG-first-run-") as temp:
        root = Path(temp)
        env = {"LOCALAPPDATA": str(root / "Local"), "APPDATA": str(root / "Roaming"), "USERPROFILE": str(root / "User")}
        for value in env.values():
            Path(value).mkdir(parents=True)
        with patch.dict(os.environ, env), patch("gg_desktop.app.load_settings", side_effect=default_settings), \
             patch("core.config_dir", return_value=root / "Prefs"), \
             patch.object(CrimsonWindow, "info"), patch.object(CrimsonWindow, "error") as error:
            window = CrimsonWindow()
            window.resize(1280, 790)
            window.show()
            settle(300)
            assert window.inventory.scanned_at in (None, 0, ""), "A new install starts with nothing scanned"
            assert any(b.isVisible() and "scan" in b.text().casefold() for b in window.findChildren(QAbstractButton)), \
                "The first screen offers a scan"
            for route in ("Overview", "Ready Room", "Games", "Mods", "Old Files", "Other Storage", "Captures", "Graveyard",
                          "Fix Kit", "Game DNA", "Hardware", "Undo Center", "More Tools", "Settings"):
                window.navigate(route)
                settle(500)
                assert window.grab().save(str(args.output / f"first-run-{route.lower().replace(' ', '-')}.png")), route
                unnamed = [type(c).__name__ + ":" + (c.toolTip() or c.objectName() or "?")[:40]
                           for kind in (QLineEdit, QComboBox) for c in window.findChildren(kind) if not c.accessibleName()]
                assert not unnamed, f"{route}: fields without a screen-reader name: {unnamed[:5]}"
                silent = [b for b in window.findChildren(QAbstractButton)
                          if b.isVisible() and not b.accessibleName() and not b.text().strip() and b.toolTip()]
                assert not silent, f"{route}: icon buttons with a tooltip but no screen-reader name: {[b.toolTip()[:30] for b in silent[:5]]}"
            error.assert_not_called()
    print("First run smoke passed")


if __name__ == "__main__":
    main()
