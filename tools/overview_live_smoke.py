"""Exercise Overview's existing controls with disposable data and real Qt events."""
from __future__ import annotations

import argparse
from dataclasses import replace
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
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
    from PIL import Image
    from PySide6.QtCore import QCoreApplication, QEvent, Qt, QTimer
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QDialog, QLabel, QListWidget, QPushButton, QTableWidget
    from core import OldFile, SteamGame, ModFolder, default_settings
    from graveyard import build_graveyard
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.backend import Inventory, ScanCanceled
    from gg_desktop.models import merge_games
    from gg_desktop.overview_data import latest_capture
    from gg_desktop.widgets import ActionCard
    from launchers import LauncherGame
    from screenshot_preview import decode_screenshot_preview

    app = QApplication.instance() or QApplication([])
    def settle():
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
    def wait_for(predicate):
        deadline = time.monotonic() + 10
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(20)
        assert predicate(), "Overview did not finish its task"
        settle()
    def drive_dialog(open_dialog, action):
        errors = []
        def execute():
            dialog = app.activeModalWidget()
            try:
                assert isinstance(dialog, QDialog), "Missing Overview dialog"
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

    with tempfile.TemporaryDirectory(prefix="GG-overview-live-") as temp:
        root = Path(temp)
        home = root / "SyntheticHome"
        captures = home / "Videos" / "Captures"
        captures.mkdir(parents=True)
        fresh = captures / "today-game.png"
        Image.new("RGB", (320, 180), "#A42042").save(fresh)
        recent_bytes = fresh.read_bytes()
        old_image = captures / "old-game.png"
        Image.new("RGB", (160, 90), "#20425F").save(old_image)
        archive = root / "old-skyrim-mod.zip"
        archive.write_bytes(b"DISPOSABLE ARCHIVE: KEEP")
        old_stamp = time.time() - 900 * 86400
        for path in (old_image, archive):
            os.utime(path, (old_stamp, old_stamp))
        def record(path):
            st = path.stat()
            return OldFile(str(path), st.st_size, st.st_mtime, st.st_dev, st.st_ino, st.st_mtime_ns, st.st_nlink)
        steam = [SteamGame("10", "Regular Steam", str(root), str(root / "SteamGame"), 100, None, "Unknown"),
                 SteamGame("11", "Shared installation", str(root), str(root / "Shared"), 100, None, "Unknown")]
        other = [LauncherGame("Shared installation", "Epic Games", str(root / "Shared"), "epic11", 200, "Manifest verified")]
        mod = ModFolder("Protected mods", str(root / "ProtectedMods"), str(root), "Protected", (), 500, 1, False, "Synthetic manager")
        inventory = Inventory(steam=steam, other=other, games=merge_games(steam, other), mods=[mod],
                              files=[record(archive)], screenshots=[record(old_image)], scanned_at="Disposable Overview QA")
        inventory.graveyard = build_graveyard(steam, [mod], inventory.files, 365, screenshots=inventory.screenshots)
        target = next(e for e in inventory.graveyard if e.old_file == inventory.files[0])
        inventory.graveyard += [replace(target, key="decoy" + str(i), name="Decoy " + str(i),
                                       path=str(root / ("decoy" + str(i) + ".zip")), apparent_bytes=10000 + i)
                                for i in range(501)]
        preferences = default_settings()
        preferences["screenshot_roots"] = [str(captures)]
        blocked, entered = threading.Event(), threading.Event()
        mode = ["cancel"]
        def scan(settings, canceled, progress):
            entered.set()
            progress(20, "Disposable Overview scan")
            while not blocked.is_set() and not canceled():
                time.sleep(.005)
            if canceled():
                raise ScanCanceled("Scan canceled")
            if mode[0] == "failure":
                raise OSError("Synthetic scan failure")
            return inventory
        disk = [SimpleNamespace(total=1024**4, used=256 * 1024**3, free=768 * 1024**3)]
        def current_usage(path):
            if isinstance(disk[0], Exception):
                raise disk[0]
            return disk[0]
        def discover(settings, **kwargs):
            return latest_capture(settings, home=home, steam_roots=[], **kwargs)

        with patch("gg_desktop.app.load_settings", return_value=preferences), \
             patch("gg_desktop.app.scan_inventory", side_effect=scan) as scanner, \
             patch("gg_desktop.overview_data.shutil.disk_usage", side_effect=current_usage), \
             patch("gg_desktop.overview.latest_capture", side_effect=discover), \
             patch("gg_desktop.overview.decode_screenshot_preview", wraps=decode_screenshot_preview) as decode, \
             patch.object(CrimsonWindow, "info"), patch.object(CrimsonWindow, "error") as error, \
             patch("gg_desktop.app.QMessageBox.warning") as warning, \
             patch.object(CrimsonWindow, "_approve_recycle") as recycle:
            window = CrimsonWindow()
            window.show()
            window.resize(1450, 900)
            settle()
            original = window.inventory
            def click_card(title):
                card = next(c for c in window.page.findChildren(ActionCard) if c.accessibleName().startswith(title + "."))
                text = next(l for l in card.findChildren(QLabel) if l.text() == title)
                QTest.mouseClick(text, Qt.LeftButton)
                settle()
            def overview():
                window.navigate("Overview")
                settle()
                wait_for(lambda: not window.workers)

            click_card("Scan PC")
            wait_for(entered.is_set)
            click_card("Scan PC")
            assert scanner.call_count == 1, "Overview started a duplicate scan"
            window.cancel_button.click()
            wait_for(lambda: not window.scanning)
            assert window.inventory is original, "Canceled scan replaced accepted inventory"
            mode[0] = "success"
            blocked.set()
            window.activateWindow()
            window.page.setFocus()
            QTest.keyClick(window, Qt.Key_F5)
            wait_for(lambda: window.inventory is inventory and not window.workers)
            assert scanner.call_count == 2
            assert window.page.overview.latest.path == str(fresh), "Latest Screenshot still uses the old-cleanup cutoff"
            decode.assert_not_called()
            assert inventory.screenshots == [record(old_image)], "Overview changed cleanup screenshot inventory"

            for title, route in (("Review Graveyard", "Graveyard"), ("Open Undo Center", "Undo Center"), ("Quick Settings", "Settings")):
                click_card(title)
                assert window.current_route == route
                overview()
            next(b for b in window.page.findChildren(QPushButton) if b.text() == "Steam").click()
            settle()
            assert window.current_route == "Games" and window.game_filter.currentText() == "Steam"
            assert len(window._shown_games) == 1
            scans_before = scanner.call_count
            QTest.keyClick(window, Qt.Key_F5)
            QTest.qWait(30)
            assert scanner.call_count == scans_before, "Overview's shortcut escaped to another page"
            overview()
            def choose_shared(dialog):
                entries = dialog.findChild(QListWidget)
                assert entries.count() == 1
                entries.setCurrentRow(0)
                next(b for b in dialog.findChildren(QPushButton) if b.text() == "Inspect selected installation").click()
            drive_dialog(lambda: next(b for b in window.page.findChildren(QPushButton) if b.text() == "Multiple launchers").click(), choose_shared)
            assert window.current_route == "Games" and len(window._shown_games) == 1
            assert window._shown_games[0].key.startswith("shared:")
            overview()
            window.page.overview.show_finding(target.key)
            settle()
            assert window.current_route == "Graveyard"
            assert len(window._shown_graves) == 1 and window._shown_graves[0].key == target.key
            assert window.grave_table.currentRow() == 0
            overview()
            next(b for b in window.page.findChildren(QPushButton) if b.text() == "Inspect protected mods").click()
            settle()
            table = window.page.findChild(QTableWidget)
            assert window.current_route == "Mods" and table.item(table.currentRow(), 0).text() == mod.path
            overview()

            def refresh_drive(dialog):
                disk[0] = SimpleNamespace(total=1000, free=400, used=600)
                next(b for b in dialog.findChildren(QPushButton) if b.text() == "Refresh reading").click()
                wait_for(lambda: not window.page.overview.storage_busy)
                assert window.page.overview.disk.capacity == 1000 and window.page.overview.disk.free == 400
                dialog.accept()
            drive_dialog(window.page.overview.storage_details, refresh_drive)
            disk[0] = OSError("Drive unavailable")
            window.page.overview.refresh_storage()
            wait_for(lambda: not window.workers)
            assert window.page.overview.disk.capacity == 0
            assert window.page.overview.summary.text() == "Drive usage not available"
            disk[0] = SimpleNamespace(total=1024**4, used=256 * 1024**3, free=768 * 1024**3)
            window.page.overview.refresh_storage()
            wait_for(lambda: not window.workers)

            closed, errors = [], []
            deadline = time.monotonic() + 10
            def close_preview():
                dialog = app.activeModalWidget()
                if dialog is None and time.monotonic() < deadline:
                    QTimer.singleShot(10, close_preview)
                    return
                try:
                    assert dialog and dialog.windowTitle() == "Game Grave · Latest Screenshot"
                    assert any(l.pixmap() and not l.pixmap().isNull() for l in dialog.findChildren(QLabel))
                    assert not any("Recycle" in b.text() or "Delete" in b.text() for b in dialog.findChildren(QPushButton))
                except Exception as exc:
                    errors.append(exc)
                if dialog:
                    dialog.accept()
                closed.append(True)
            QTimer.singleShot(10, close_preview)
            next(b for b in window.page.findChildren(QPushButton) if b.text() == "Preview this image").click()
            wait_for(lambda: bool(closed))
            if errors:
                raise errors[0]
            assert decode.call_count == 1
            assert fresh.read_bytes() == recent_bytes
            recycle.assert_not_called()
            with fresh.open("ab") as changed:
                changed.write(b"CHANGED")
            window.page.overview.preview_capture()
            assert error.call_count == 1
            assert decode.call_count == 1

            mode[0] = "failure"
            window.page.overview.scan()
            wait_for(lambda: not window.scanning)
            assert window.inventory is inventory
            warning.assert_called_once()
            assert archive.read_bytes() == b"DISPOSABLE ARCHIVE: KEEP"
            assert window.grab().save(str(args.output / "overview-functional-1450.png"))
            window.close()
            settle()
    print("PASS: Overview card text/click/keyboard actions, scan success/cancel/failure, storage refresh/errors, "
          "exact launcher/finding/mod selection, fresh screenshot metadata and explicit read-only preview; no cleanup inventory changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
