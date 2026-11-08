"""Exercise live Ready Room with disposable saves and deterministic Steam news.

No personal folders are scanned. Native Qt on Windows; offscreen Qt on Linux.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("_ci_temp"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QCoreApplication, QEvent, Qt, QTimer
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QDialogButtonBox, QLineEdit, QListWidget, QPushButton
    from core import SteamGame, default_settings
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.models import merge_games
    from gg_desktop.ready_room_services import load_state, parse_news

    app = QApplication.instance() or QApplication([])
    def settle():
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()

    def wait_for(predicate):
        deadline = time.monotonic() + 10
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(20)
        assert predicate(), "Ready Room task did not finish"
        settle()

    def drive_dialog(open_dialog, action):
        errors = []
        def execute():
            dialog = app.activeModalWidget()
            try:
                assert dialog is not None, "Missing Ready Room dialog"
                action(dialog)
            except Exception as exc:
                errors.append(exc)
                if dialog:
                    dialog.reject()
        QTimer.singleShot(0, execute)
        open_dialog()
        if errors:
            raise errors[0]
        settle()

    def fake_news(steam_id, name):
        return parse_news({"appnews": {"appid": int(steam_id), "newsitems": [
            dict(gid=str(index + 1), title=title, date=int(time.time()) - index * 86400,
                 contents="Synthetic official-news fixture for disposable UI QA.",
                 feedname="steam_community_announcements", url="https://store.steampowered.com/news/app/" + steam_id)
            for index, title in enumerate(("Patch 2.3", "Hotfix #42", "Scheduled maintenance", "Full release out now"))
        ]}}, steam_id, name)

    with tempfile.TemporaryDirectory(prefix="GG-ready-live-") as temp:
        root = Path(temp)
        store = root / "Preferences"
        source = root / "SelectedSaves"
        source.mkdir()
        save = source / "slot.sav"
        save.write_bytes(b"DISPOSABLE SAVE: MUST REMAIN INTACT")
        destination = root / "VerifiedBackup.zip"
        install = root / "GameInstall"
        install.mkdir()
        steam = SteamGame("1091500", "Cyberpunk 2077", str(root), str(install), 100, None, "Unknown")
        with patch("gg_desktop.app.load_settings", side_effect=default_settings), \
             patch("gg_desktop.ready_room_services.config_dir", return_value=store), \
             patch("gg_desktop.ready_room_services.fetch_one", side_effect=fake_news) as fetch, \
             patch.object(CrimsonWindow, "info"), patch.object(CrimsonWindow, "error") as error:
            window = CrimsonWindow()
            window.resize(1280, 790)
            window.show()
            window.inventory.steam = [steam]
            window.inventory.games = merge_games([steam], [])
            window.inventory.scanned_at = "Disposable live UI QA"
            window.navigate("Ready Room")
            settle()
            wait_for(lambda: bool(window._ready_evidence))
            # Opening Ready Room fetches official Steam news once on its own (owner-approved live feed).
            wait_for(lambda: fetch.call_count == 1 and not window._ready_news_busy)
            settle()
            status = window.page.news_status.text()
            assert "last checked just now" in status and "30 minutes" in status, status
            assert window._ready_news_timer.isActive() and window._ready_news_timer.interval() == 30 * 60 * 1000
            window._ready_news_tick()  # fresh news: another tick inside the interval must not fetch again
            settle()
            assert fetch.call_count == 1 and not window._ready_news_busy
            assert window.page.data.counts[0] == "2" and window.page.data.counts[2] == "1" and window.page.data.counts[3] == "1"
            assert window.page.data.health_caption == "Local checks"
            assert window.page.data.games[0].hours == "— hrs"

            def choose_follow(dialog):
                choices = dialog.findChild(QListWidget)
                assert choices.count() == 1
                choices.item(0).setCheckState(Qt.Checked)
                dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Save).click()
            drive_dialog(window.ready_followed_games, choose_follow)
            assert window.page.data.counts[4] == "1"
            assert len(load_state(store)["followed"]) == 1

            def refresh(dialog):
                next(b for b in dialog.findChildren(QPushButton) if b.text() == "Refresh official news").click()
                wait_for(lambda: not window._ready_news_busy)
                posts = dialog.findChild(QListWidget)
                assert posts.count() == 4
                query = dialog.findChild(QLineEdit)
                query.setText("Hotfix")
                assert posts.count() == 1
                posts.setCurrentRow(0)
                with patch("gg_desktop.ready_room_actions.QDesktopServices.openUrl", return_value=True) as browser:
                    next(b for b in dialog.findChildren(QPushButton) if b.text() == "Open official post").click()
                    assert browser.call_args[0][0].toString().startswith("https://store.steampowered.com/news/")
                dialog.accept()
            drive_dialog(window.ready_updates, refresh)
            assert fetch.call_count == 2  # the manual button still works on top of the automatic fetch
            window._ready_state["news_checked"] = {k: 1000 for k in window._ready_state["news_checked"]}
            window._ready_news_attempt = 0  # thirty minutes later: the timer tick fetches again
            window._ready_news_tick()
            wait_for(lambda: fetch.call_count == 3 and not window._ready_news_busy)
            settle()
            assert window.page.data.counts == ("2", "0", "1", "1", "1")
            assert len(window.page.visible_patches) == 4
            assert window.page.visible_games[0].status == "Patch news"
            assert len(load_state(store)["news"]) == 4
            window.page.search.setText("maintenance")
            assert len(window.page.visible_patches) == 1
            window.page.search.clear()

            with patch("gg_desktop.ready_room_actions.QFileDialog.getExistingDirectory", return_value=str(source)), \
                 patch("gg_desktop.ready_room_actions.QFileDialog.getSaveFileName", return_value=(str(destination), "ZIP")), \
                 patch.object(window, "confirm", return_value=True):
                next(b for b in window.page.findChildren(QPushButton) if b.text() == "Backup Now").click()
                wait_for(lambda: not window.cleaning)
            assert destination.is_file()
            assert window.page.data.backup_title == "1 Saved Backup"
            assert len(load_state(store)["backups"]) == 1
            assert save.read_bytes() == b"DISPOSABLE SAVE: MUST REMAIN INTACT"

            def check_vault(dialog):
                assert "VerifiedBackup.zip" in dialog.findChild(QListWidget).item(0).text()
                dialog.accept()
            drive_dialog(window.ready_manage_saves, check_vault)
            def check_health(dialog):
                assert dialog.findChild(QListWidget).count() == 4, "Missing local checks"
                dialog.accept()
            drive_dialog(window.ready_health_details, check_health)
            drive_dialog(window.ready_mod_alerts, lambda d: d.accept())

            pulse = window.page.visible_games[0]
            window.ready_game_details(pulse)
            settle()
            assert window.current_route == "Games"
            assert window._shown_games[window.game_table.currentRow()].key == pulse.key
            window.navigate("Ready Room")
            settle()
            assert window.page.data.counts[4] == "1"
            assert window.page.data.backup_title == "1 Saved Backup"
            assert window.grab().save(str(args.output / "ready-room-live-functional.png"))
            error.assert_not_called()
            assert not window.workers
            window.close()
            settle()
    print("PASS: live news auto-refresh/refresh/filter/browser action, follow persistence, real ZIP backup and history, "
          "local health/mod dialogs and exact game selection. No automatic network requests or source-save changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
