"""Run at QT_SCALE_FACTOR=1.25 and 1.5 on isolated Windows CI only.

Checks native Qt page geometry and legibility at common Windows DPI without
scanning or modifying any personal game files. The normal rendered screenshots
are generated separately at 100% scaling.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


def main():
    if os.name != "nt" or os.environ.get("GG_CRIMSON_QA_DISPOSABLE") != "YES":
        print("Refusing DPI smoke outside disposable Windows CI.")
        return 2
    scale = float(os.environ.get("QT_SCALE_FACTOR", "1"))
    if scale not in (1.25, 1.5):
        print("Require explicit 125% or 150% Qt scaling.")
        return 2
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from PySide6.QtWidgets import QApplication
    from gg_desktop.app import CrimsonWindow, configure_crimson_dialog_palette
    from gg_desktop.theme import STYLE
    with tempfile.TemporaryDirectory(prefix="GG-DPI-", dir=root / "_ci_temp") as temp:
        os.environ["LOCALAPPDATA"] = str(Path(temp) / "Local")
        os.environ["APPDATA"] = str(Path(temp) / "Roaming")
        Path(os.environ["LOCALAPPDATA"]).mkdir(parents=True, exist_ok=True)
        Path(os.environ["APPDATA"]).mkdir(parents=True, exist_ok=True)
        app = QApplication.instance() or QApplication(sys.argv)
        configure_crimson_dialog_palette(app)
        app.setStyleSheet(STYLE)
        win = CrimsonWindow()
        win.settings["scan_on_launch"] = False
        win.resize(1366, 768)
        win.show()
        app.processEvents()
        try:
            assert win.devicePixelRatioF() >= (scale - 0.08), (
                "Qt scaling did not take effect on the native Windows worker")
            for route in (
                "Overview", "Ready Room", "Games", "Mods", "Old Files",
                "Other Storage", "Captures", "Graveyard", "Game DNA",
                "Undo Center", "AI Assistant", "Settings", "More Tools",
            ):
                win.navigate(route)
                app.processEvents()
                assert win.current_route == route
                assert win.page is not None and win.page.isVisible()
                assert win.global_search.isVisible()
                assert win.page.body.width() <= win.page.viewport().width() + 8, (
                    "Horizontal clipping at " + str(scale) + ": " + route)
                assert not win.grab().isNull(), (
                    "DPI rendering failure: " + route)
        finally:
            win.close()
            app.processEvents()
    print("PASS: all 13 Qt routes at", scale,
          "Windows scale, with no scan or cleanup operations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
