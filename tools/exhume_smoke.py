"""Native Qt check of Exhume with fixture driver data: read-only check, good mark, refusal paths, confirmed rollback
through a fake Windows runner (no real driver is touched), and honest errors."""
from __future__ import annotations

import argparse
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
    from PySide6.QtWidgets import QApplication, QPushButton
    import core
    from core import default_settings
    from gg_desktop import exhume_core as ex
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.ready_room_services import parse_news
    from tests.test_exhume import CURRENT, STORE

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
        return window.page.exhume.exhume

    def buttons(window, text):
        return [b for b in live(window).findChildren(QPushButton) if b.text() == text]

    with tempfile.TemporaryDirectory(prefix="GG-exhume-") as temp:
        root = Path(temp)
        ran = []
        with patch.dict(os.environ, {"LOCALAPPDATA": str(root / "Local")}), \
             patch("gg_desktop.app.load_settings", side_effect=default_settings), \
             patch("gg_desktop.ready_room_services.config_dir", return_value=root / "Prefs"), \
             patch("gg_desktop.ready_room_services.fetch_one",
                   side_effect=lambda sid, name: parse_news({"appnews": {"appid": int(sid), "newsitems": []}}, sid, name)), \
             patch("gg_desktop.exhume_core.query_current", return_value=CURRENT), \
             patch("gg_desktop.exhume_core.query_store", return_value=STORE), \
             patch("gg_desktop.exhume_core._run", side_effect=lambda c, timeout=0: ran.append(c) or "ok"), \
             patch("gg_desktop.exhume_core.is_admin", return_value=False), \
             patch.object(CrimsonWindow, "info") as info, patch.object(CrimsonWindow, "error") as error:
            window = CrimsonWindow()
            window.resize(1280, 790)
            window.show()
            window.navigate("Ready Room")
            settle(300)
            assert window.page.exhume is not None, "Exhume panel is missing from Ready Room"
            strip = window.page.exhume
            assert not strip.strip_open and strip.maximumHeight() <= 50, "Exhume starts as one slim line"
            strip.strip_toggle.click()
            settle(80)
            assert strip.strip_open
            assert "Nothing is changed by checking" in live(window).summary.text()
            assert not buttons(window, "Roll back…")

            live(window).check_button.click()
            wait_for(lambda: live(window).cards, "the driver check")
            body = live(window)
            assert len(body.cards) == 1 and len(body.cards[0].older) == 2
            assert body.summary.text().startswith("1 display adapter found"), body.summary.text()
            assert "not running as administrator" in body.summary.text()
            assert len(buttons(window, "Roll back…")) == 2 and len(buttons(window, "Mark this driver as good")) == 1
            assert ran == [], "Checking must not run any change"
            assert strip.detail_label.text() == "1 display adapter; 2 older drivers still stored.", strip.detail_label.text()
            window.page.ensureWidgetVisible(window.page.exhume)
            settle(80)
            assert window.grab().save(str(args.output / "ready-room-exhume-1280.png"))

            # Marking is Game Grave's own file only.
            buttons(window, "Mark this driver as good")[0].click()
            settle(100)
            assert ex.load_marks()["NVIDIA GeForce RTX 4070"]["version"] == "32.0.15.6614"
            assert not buttons(window, "Mark this driver as good") and ran == []

            # Declining the confirmation changes nothing; the confirmation shows the exact commands.
            with patch.object(window, "confirm", return_value=False) as confirm:
                buttons(window, "Roll back…")[0].click()
                shown = confirm.call_args[0][1]
                assert confirm.call_args.kwargs.get("destructive") is True
                assert "pnputil /delete-driver oem42.inf /uninstall /force" in shown and "oem40.inf" in shown, shown
                assert "keeps no copy" in shown
            assert ran == []

            # Without administrator rights nothing runs and the owner is told why.
            with patch.object(window, "confirm", return_value=True):
                buttons(window, "Roll back…")[0].click()
                wait_for(lambda: error.call_count >= 1, "the admin message")
            assert ran == [] and "administrator" in error.call_args[0][1]

            # With administrator rights, a confirmed rollback runs both commands and is logged.
            with patch("gg_desktop.exhume_core.is_admin", return_value=True), \
                 patch.object(window, "confirm", return_value=True):
                buttons(window, "Roll back…")[0].click()
                wait_for(lambda: info.call_count >= 1, "the rollback")
            assert [c[1] for c in ran] == ["/delete-driver", "/add-driver"], ran
            assert "Restart the PC" in info.call_args[0][1]
            events = [e for e in core.get_activity() if e["kind"] == "exhume_rollback"]
            assert events and events[0]["result"] == "completed" and "6614 to 32.0.15.6094" in events[0]["details"]
            settle(300)

            # A page rebuild keeps what was found.
            window.navigate("Ready Room")
            settle(300)
            assert live(window).cards, "The driver list survives a page rebuild"

            # Windows refusing to answer is stated, not hidden.
            with patch("gg_desktop.exhume_core.query_store", side_effect=OSError("Access is denied.")):
                live(window).check_button.click()
                wait_for(lambda: "would not share" in live(window).summary.text(), "the error text")
            assert not buttons(window, "Roll back…")
    print("Exhume smoke passed")


if __name__ == "__main__":
    main()
