"""Temporary diagnosis: which action leaves the Qt event loop stuck? Runs one probe per process."""
from __future__ import annotations

import faulthandler
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch


def run(probe):
    faulthandler.dump_traceback_later(50, exit=True)
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QCoreApplication, QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from core import default_settings
    from gg_desktop.app import CrimsonWindow
    from gg_desktop import mods_gallery as mg
    from tests.test_mods_functionality import mo2_fixture

    app = QApplication.instance() or QApplication([])

    def settle():
        app.processEvents()
        print("  processEvents ok", flush=True)
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        print("  deferred delete ok", flush=True)
        app.processEvents()

    def wait_for(predicate):
        deadline = time.monotonic() + 20
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
        assert predicate()
        settle()

    with tempfile.TemporaryDirectory(prefix="GG-probe-") as temp:
        root = Path(temp)
        inventory, storage, profiles, ini = mo2_fixture(root)
        (storage / "MountainTextures" / "meta.ini").write_text("[General]\nversion=2.0\nnewestVersion=2.5\n", encoding="utf-8")
        settings = default_settings()
        with patch("gg_desktop.app.load_settings", side_effect=lambda: dict(settings)), \
             patch("gg_desktop.ready_room_services.config_dir", return_value=root / "Preferences"), \
             patch("gg_desktop.mods_page.save_settings"), \
             patch.object(CrimsonWindow, "info"), patch.object(CrimsonWindow, "error"), \
             patch.object(CrimsonWindow, "confirm", return_value=True), patch.object(CrimsonWindow, "start_scan"):
            window = CrimsonWindow()
            window.resize(1280, 790)
            window.show()
            window.inventory = inventory
            window.settings = dict(settings)
            window.navigate("Mods")
            wait_for(lambda: not window.workers and window.page.mods.report is not None)
            wait_for(lambda: window._mod_updates_scanned and not window.workers)
            settle()
            card = next(c for c in window.mod_gallery.findChildren(mg.ModCard) if c.c.facts.name == "Mountain Textures")
            print("probe", probe, "start", flush=True)
            if probe == "A":
                settle()
            elif probe == "B":
                window.mod_table.selectRow(card.c.facts.index)
                settle()
            elif probe == "C":
                card.set_selected(True)
                settle()
            elif probe == "D":
                point = QPointF(card.width() / 2, card.height() / 2)
                QApplication.sendEvent(card, QMouseEvent(QEvent.MouseButtonPress, point, card.mapToGlobal(point),
                                                         Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
                settle()
            elif probe == "E":
                window.mod_gallery.refresh()
                settle()
                settle()
            elif probe == "F":
                window.mod_gallery.sync_selection()
                settle()
            elif probe == "G":
                window.mod_table.selectRow(card.c.facts.index)
                print("  selected", flush=True)
                window.mod_gallery.sync_selection()
                print("  synced", flush=True)
                settle()
            window.close()
            settle()
    print("probe", probe, "OK", flush=True)


def main():
    if len(sys.argv) > 1:
        run(sys.argv[1])
        return 0
    results = {}
    for probe in "ABCDEFG":
        print("=== probe", probe, flush=True)
        try:
            done = subprocess.run([sys.executable, __file__, probe], timeout=90)
            results[probe] = "ok" if done.returncode == 0 else f"exit {done.returncode}"
        except subprocess.TimeoutExpired:
            results[probe] = "HUNG"
    print("RESULTS", results, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
