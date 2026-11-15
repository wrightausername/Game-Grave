"""Hardware > Registry Cleanup, driven like the owner would: open the tab (nothing is read until Scan), scan a fake
registry, see grouped results with review-only items unticked and unclickable, untick one, press Fix and read the one
confirmation (restore point, backup folder, exact keys), check only ticked entries go to the fixer, then Undo. The real
registry is never touched here; tools/registry_real_check.py does that with test entries on the CI machine."""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("_ci_temp"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QCoreApplication, QEvent, Qt
    from PySide6.QtWidgets import QApplication, QPushButton
    from core import default_settings
    from gg_desktop import registry_core as rc
    from gg_desktop.app import CrimsonWindow
    from tests.test_registry import Scan, checks

    app = QApplication.instance() or QApplication([])

    def settle(seconds=0.0):
        end = time.time() + seconds
        while True:
            app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            if time.time() >= end:
                break
            time.sleep(0.02)

    def wait_for(test, words, seconds=20):
        end = time.time() + seconds
        while not test():
            settle(0.05)
            assert time.time() < end, "Timed out waiting for " + words

    with tempfile.TemporaryDirectory(prefix="GG-registry-") as temp:
        root = Path(temp)
        calls = SimpleNamespace(scans=0, fixed=None, restore=None, undone=None)
        fake_reg = Scan().reg()

        class Backend:
            @staticmethod
            def scan(progress=None):
                calls.scans += 1
                return rc.scan(fake_reg, checks())

            @staticmethod
            def backup_root():
                return root / "registry_backups"

            @staticmethod
            def fix(chosen, restore_point=True):
                calls.fixed, calls.restore = list(chosen), restore_point
                (root / "registry_backups" / "2026-11-15 12-00-00").mkdir(parents=True, exist_ok=True)
                return {"folder": str(root / "registry_backups" / "2026-11-15 12-00-00"), "restore": "made",
                        "done": [f.ident for f in chosen[1:]], "kept": [chosen[0].ident], "failed": []}

            @staticmethod
            def backups():
                if calls.fixed is None:
                    return []
                return [(root / "registry_backups" / "2026-11-15 12-00-00", len(calls.fixed), calls.undone is not None)]

            @staticmethod
            def undo(folder):
                calls.undone = folder
                return []

        asked = []
        with patch("gg_desktop.app.load_settings", side_effect=default_settings), \
             patch("gg_desktop.ready_room_services.config_dir", return_value=root / "Prefs"), \
             patch("gg_desktop.registry_ui.log_event"), \
             patch("gg_desktop.registry_ui.RegistryTab.__init__.__defaults__", (Backend,)), \
             patch.object(CrimsonWindow, "confirm", lambda self, t, text, **_: asked.append(text) or True), \
             patch.object(CrimsonWindow, "info"), patch.object(CrimsonWindow, "error"):
            window = CrimsonWindow()
            window.resize(1366, 790)
            window.show()
            window.navigate("Hardware")
            settle(0.2)
            tabs = [b for b in window.page.findChildren(QPushButton) if b.text() == "Registry Cleanup"]
            assert tabs, "Hardware has no Registry Cleanup tab"
            tabs[0].click()
            settle(0.2)
            tab = window.page.hardware.registry_tab
            assert tab is not None and tab.isVisible() and not window.page.hardware.pc_tab.isVisible()
            assert calls.scans == 0, "nothing is read before Scan"
            assert not tab.fix_button.isEnabled() and not tab.undo_button.isEnabled()
            assert tab.restore_box.isChecked(), "a restore point is ticked by default"

            tab.scan_button.click()
            wait_for(lambda: tab.findings, "the scan")
            settle(0.1)
            tops = [tab.tree.topLevelItem(i) for i in range(tab.tree.topLevelItemCount())]
            titles = [t.text(0) for t in tops]
            assert titles[0].startswith("Startup entries") and titles[-1].startswith("Review only"), titles
            review = tops[-1]
            for j in range(review.childCount()):
                assert not review.child(j).flags() & Qt.ItemIsUserCheckable, "review-only items can't be ticked"
            ticked = tab.chosen()
            assert ticked and all(f.fixable for f in ticked)
            assert "Fix 6 entries" == tab.fix_button.text(), tab.fix_button.text()
            startup = tops[0].child(0)
            startup.setCheckState(0, Qt.Unchecked)
            settle(0.05)
            assert tab.fix_button.text() == "Fix 5 entries", tab.fix_button.text()
            tab.grab().save(str(args.output / "registry-cleanup-results.png"))

            tab.fix_button.click()
            wait_for(lambda: calls.fixed is not None and not tab.busy, "the fix")
            settle(0.1)
            text = asked[-1]
            assert "Restore point" in text and str(root / "registry_backups") in text and "HKEY_LOCAL_MACHINE" in text, text
            assert "OldTool" not in text, "an unticked entry is not in the confirmation"
            assert calls.restore is True and len(calls.fixed) == 5
            assert all(f.name != "OldTool" for f in calls.fixed)
            banner = tab.banner.label.text()
            assert "Fixed 4 entries" in banner and "1 left alone because their file came back" in banner, banner
            assert "restore point was made" in banner and "Undo last fix" in banner, banner
            assert tab.undo_button.isEnabled()
            tab.grab().save(str(args.output / "registry-cleanup-fixed.png"))

            tab.undo_button.click()
            wait_for(lambda: calls.undone is not None and not tab.busy, "the undo")
            settle(0.1)
            assert "Put back" in asked[-1] and "Put back" in tab.banner.label.text()
            assert not tab.undo_button.isEnabled(), "nothing left to undo"
            window.close()
    print("PASS: Registry Cleanup reads nothing until Scan, groups results, keeps review-only items unticked, confirms "
          "the exact keys with a restore point and backup, fixes only ticked entries, and undoes.")


if __name__ == "__main__":
    main()
