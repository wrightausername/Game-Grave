"""Native Qt check of Black Box: build a report for a game from fixture data, copy, save, and honest empty states."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch


def event(exe, path, when):
    return ('<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event"><System><EventID>1000</EventID>'
            '<TimeCreated SystemTime="' + when + '"/></System><EventData>'
            f'<Data>{exe}</Data><Data>1.0</Data><Data>0</Data><Data>d3d11.dll</Data><Data>1.0</Data><Data>0</Data>'
            f'<Data>c0000005</Data><Data>000000000012ab34</Data><Data>1234</Data><Data>0</Data><Data>{path}</Data>'
            '</EventData></Event>')


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
    import core
    from core import SteamGame, default_settings
    from gg_desktop import blackbox_core as bb
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.models import merge_games
    from gg_desktop.ready_room_services import parse_news

    app = QApplication.instance() or QApplication([])

    def settle(ms=0):
        end = datetime.now() + timedelta(milliseconds=ms)
        while True:
            app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            if datetime.now() >= end:
                break

    def wait_for(test, label, seconds=15):
        end = datetime.now() + timedelta(seconds=seconds)
        while not test():
            settle(20)
            assert datetime.now() < end, "Timed out waiting for " + label

    def live(window):
        return window.page.blackbox.blackbox

    with tempfile.TemporaryDirectory(prefix="GG-blackbox-") as temp:
        root = Path(temp)
        install = root / "Skyrim"
        (install / "bin").mkdir(parents=True)
        (install / "crash").mkdir()
        exe = install / "bin" / "SkyrimSE.exe"
        exe.write_bytes(b"x")
        dump = install / "crash" / "crash-2026-11-08.dmp"
        dump.write_bytes(b"d" * 4096)
        patch_file = install / "Data" / "patch.esp"
        patch_file.parent.mkdir()
        patch_file.write_bytes(b"p")
        # Everything is relative to now, so this check never goes stale: the crash was two days ago and the
        # files were last written the day before it.
        crash_at = datetime.now(timezone.utc) - timedelta(days=2)
        crash_text = crash_at.strftime("%Y-%m-%dT%H:%M:%S.1234567Z")
        recent = (crash_at - timedelta(days=1)).timestamp()
        os.utime(dump, (recent, recent))
        os.utime(patch_file, (recent, recent))
        game = SteamGame("489830", "The Elder Scrolls V: Skyrim Special Edition", str(root), str(install), 100, None, "Unknown")
        empty_install = root / "Cyberpunk"
        empty_install.mkdir()
        other = SteamGame("1091500", "Cyberpunk 2077", str(root), str(empty_install), 100, None, "Unknown")
        events = (event("SkyrimSE.exe", str(exe), crash_text)
                  + event("chrome.exe", "C:\\Program Files\\Chrome\\chrome.exe", crash_text))
        with patch.dict(os.environ, {"LOCALAPPDATA": str(root / "Local")}), \
             patch("gg_desktop.app.load_settings", side_effect=default_settings), \
             patch("gg_desktop.ready_room_services.config_dir", return_value=root / "Prefs"), \
             patch("gg_desktop.ready_room_services.fetch_one",
                   side_effect=lambda sid, name: parse_news({"appnews": {"appid": int(sid), "newsitems": []}}, sid, name)), \
             patch("gg_desktop.blackbox_core.query_events", return_value=events), \
             patch.object(CrimsonWindow, "info"), patch.object(CrimsonWindow, "error") as error:
            window = CrimsonWindow()
            window.resize(1280, 790)
            window.show()
            window.navigate("Ready Room")
            settle()
            panel = window.page.blackbox
            assert panel is not None, "Black Box panel is missing from Ready Room"
            assert not panel.strip_open and panel.maximumHeight() <= 50, "Black Box starts as one slim line"
            assert panel.strip_toggle.text() == "Open"
            panel.strip_toggle.click()
            settle(60)
            assert panel.strip_open and panel.strip_toggle.text() == "Hide" and panel.body.isVisible()
            panel.strip_toggle.click()
            settle(60)
            assert not panel.strip_open and not panel.body.isVisible() and panel.maximumHeight() <= 50, \
                "Black Box minimizes again like the other Ready Room panels"
            panel.strip_toggle.click()
            settle(60)
            body = panel.blackbox
            assert body.games.count() == 0 and not body.build_button.isEnabled()
            assert "Scan your PC" in body.summary.text()
            assert not body.copy_button.isEnabled() and not body.save_button.isEnabled()

            window.inventory.steam = [game, other]
            window.inventory.games = merge_games([game, other], [])
            window.inventory.scanned_at = "Disposable Black Box QA"
            window.navigate("Ready Room")
            settle()
            window.page.blackbox.set_open(True)
            settle(60)
            body = live(window)
            assert body.games.count() == 2 and body.build_button.isEnabled()
            body.games.setCurrentIndex(body.games.findText("The Elder Scrolls V: Skyrim Special Edition"))
            body.build_button.click()
            wait_for(lambda: live(window).report is not None, "the report")
            body = live(window)
            report = body.report
            assert len(report.crashes) == 1 and report.crashes[0].exe == "SkyrimSE.exe", report.crashes
            assert [f.path for f in report.logs] == [str(Path("crash") / "crash-2026-11-08.dmp")], report.logs
            assert any(f.path.endswith("patch.esp") for f in report.changed), report.changed
            shown = body.view.toPlainText()
            assert "SkyrimSE.exe" in shown and "chrome.exe" not in shown
            assert "does not say why the game crashed" in shown
            assert body.summary.text().startswith("1 crash recorded by Windows, 1 log or dump file")
            assert body.copy_button.isEnabled() and body.save_button.isEnabled()
            body.copy_button.click()
            assert QApplication.clipboard().text() == shown
            assert live(window).games.currentText() == report.game, "The dropdown follows the shown report"
            window.page.ensureWidgetVisible(window.page.blackbox)
            settle(50)
            assert window.grab().save(str(args.output / "ready-room-blackbox-1280.png"))

            with patch("gg_desktop.blackbox_core.blackbox_dir", return_value=root / "reports"):
                settle(100)
                body = live(window)
                body.save_button.click()
            assert body.saved is not None and body.saved.read_text(encoding="utf-8") == shown
            assert body.saved.parent == root / "reports"

            body.games.setCurrentIndex(body.games.findText("Cyberpunk 2077"))
            body.build_button.click()
            wait_for(lambda: live(window).report is not None and live(window).report.game == "Cyberpunk 2077", "the empty report")
            body = live(window)
            text = body.view.toPlainText()
            assert "None found in the Windows Application log for this game." in text
            assert body.summary.text().startswith("0 crashes recorded by Windows, 0 log or dump files")
            # A rebuilt page still shows the newest report.
            window.navigate("Ready Room")
            settle()
            assert live(window).report is not None and live(window).report.game == "Cyberpunk 2077"
            assert window.page.blackbox.strip_open, "A panel that was open stays open when Ready Room rebuilds itself"
            assert live(window).games.currentText() == "Cyberpunk 2077", "The dropdown follows the shown report"
            error.assert_not_called()
    print("Black Box smoke passed")


if __name__ == "__main__":
    main()
