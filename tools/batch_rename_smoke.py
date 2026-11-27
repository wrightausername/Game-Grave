"""Native Qt check of Toolbox > Batch Rename: the tile opens it, dropped files and folders are listed oldest first with a
live preview, typing a name numbers them, a taken name blocks Rename All, rows can be reordered, Enter renames for real,
Undo puts the names back (also after reopening), a big batch works, and nothing but names ever changes.
Only throw-away temp folders are touched."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
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
    from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
    from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QImage
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    import core
    from gg_desktop import rename_core as rc, rename_ui, tools_data as data
    from gg_desktop.app import CrimsonWindow

    app = QApplication.instance() or QApplication([])

    def settle(ms=30):
        app.processEvents()
        QTest.qWait(ms)
        app.processEvents()

    def wait_for(test, seconds=20):
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents()
            if test():
                return
            QTest.qWait(20)
        raise AssertionError("timed out")

    def snap(dialog, name):
        dialog.show()
        settle(120)
        assert dialog.grab().save(str(args.output / name)), name

    def drop(widget, paths):
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
        at = QPointF(widget.width() / 2, widget.height() / 2)
        enter = QDragEnterEvent(at.toPoint(), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        QApplication.sendEvent(widget, enter)
        event = QDropEvent(at, Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        QApplication.sendEvent(widget, event)
        settle()

    def digest(folder):
        return sorted(hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(folder).iterdir() if p.is_file())

    with tempfile.TemporaryDirectory(prefix="GG-rename-") as temp:
        root = Path(temp)
        shots = root / "Screenshots"
        shots.mkdir()
        colors = ["#c8102e", "#13bcf5", "#32d67a"]
        for n, color in enumerate(colors):          # real pictures, created one after another (oldest first)
            image = QImage(320, 200, QImage.Format_RGB32)
            image.fill(QColor(color))
            image.save(str(shots / f"Screenshot {['b', 'a', 'c'][n]}.png"))
            time.sleep(0.05)
        (shots / "notes.txt").write_text("keep these words", encoding="utf-8")
        hidden_extra = shots / "desktop.ini"
        hidden_extra.write_text("[x]", encoding="utf-8")
        contents_before = digest(shots)

        shown, asked = [], []
        stack = ExitStack()
        for target, options in (
            ("core.config_dir", dict(return_value=root / "Config")),
            ("gg_desktop.tools_page.get_activity", dict(return_value=[])),
            ("gg_desktop.recovery_screens.get_records", dict(return_value=[])),
            ("gg_desktop.recovery_screens.get_activity", dict(return_value=[])),
            ("gg_desktop.undo_page.get_records", dict(return_value=[])),
            ("gg_desktop.undo_page.get_activity", dict(return_value=[])),
            ("gg_desktop.ready_room_services.config_dir", dict(return_value=root / "Preferences")),
            ("gg_desktop.ready_room_services.fetch_one", dict(side_effect=OSError("offline QA"))),
        ):
            stack.enter_context(patch(target, **options))
        errors = stack.enter_context(patch.object(CrimsonWindow, "error"))
        stack.enter_context(patch.object(CrimsonWindow, "info"))
        stack.enter_context(patch.object(CrimsonWindow, "confirm", side_effect=lambda t, m, **kw: asked.append((t, m)) or True))
        stack.enter_context(patch.object(rename_ui.RenameDialog, "exec", lambda self: shown.append(self) or 0))
        with stack:
            core.save_settings(core.default_settings())
            window = CrimsonWindow()
            window.show()
            window.resize(1280, 760)
            window.navigate("More Tools")
            settle()

            # The tile is in Files and opens the window.
            files = next(c for c in data.CATEGORIES if c.key == "files")
            assert files.tiles[0].key == "batch_rename", [t.key for t in files.tiles]
            window.tools_tiles["batch_rename"].click()
            settle()
            dialog = shown.pop()
            assert isinstance(dialog, rename_ui.RenameDialog)
            assert dialog.windowTitle() == "Game Grave · Batch Rename"
            assert not dialog.advanced.isVisible() or not dialog.isVisible(), "advanced options start folded"
            assert not dialog.rename_button.isEnabled() and not dialog.undo_button.isEnabled()
            snap(dialog, "tools-batch-rename-empty.png")
            assert not dialog.advanced.isVisible(), "advanced options start folded"

            # Drop the folder onto the list: its files, oldest first, desktop.ini left out.
            drop(dialog.listing.viewport(), [shots])
            names = [Path(i.path).name for i in dialog.items]
            assert names == ["Screenshot b.png", "Screenshot a.png", "Screenshot c.png", "notes.txt"], names
            assert dialog.listing.count() == 4
            wait_for(lambda: all(str(shots / n) in dialog.thumbs.cache for n in names[:3]))  # pictures loaded

            # Type a name: WW_01.png ... WW_04.txt, extensions kept, live.
            dialog.name.clear()
            QTest.keyClicks(dialog.name, "WW")
            settle()
            assert [p.name for p in dialog.plans] == ["WW_01.png", "WW_02.png", "WW_03.png", "WW_04.txt"], [p.name for p in dialog.plans]
            assert dialog.rename_button.isEnabled() and dialog.rename_button.text() == "Rename All (4)"
            snap(dialog, "tools-batch-rename-preview.png")

            # A taken name blocks Rename All and says why.
            taken = shots / "WW_04.txt"
            taken.write_text("somebody else's file", encoding="utf-8")
            dialog.dir_cache.clear()
            dialog.refresh()
            assert dialog.plans[3].status == rc.EXISTS and not dialog.rename_button.isEnabled()
            assert "attention" in dialog.result_line.text(), dialog.result_line.text()
            snap(dialog, "tools-batch-rename-conflict.png")
            QTest.keyClick(dialog.name, Qt.Key_Return)      # Enter does not rename while a name is taken
            settle()
            assert (shots / "Screenshot b.png").exists() and taken.read_text(encoding="utf-8") == "somebody else's file"
            taken.unlink()
            dialog.dir_cache.clear()
            dialog.refresh()
            assert dialog.rename_button.isEnabled()

            # Reorder: move notes.txt to the top by dragging (the list's own move), numbers follow.
            moved = dialog.listing.takeItem(3)
            dialog.listing.insertItem(0, moved)
            dialog.reordered()
            assert dialog.manual_order and dialog.plans[0].name == "WW_01.txt", [p.name for p in dialog.plans]

            # Advanced: prefix and a separator, then back.
            dialog.adv_toggle.click()
            settle()
            assert dialog.advanced.isVisible()
            dialog.prefix.setText("GG-")
            settle()
            assert dialog.plans[0].name == "GG-WW_01.txt"
            snap(dialog, "tools-batch-rename-advanced.png")
            dialog.prefix.clear()
            dialog.adv_toggle.click()
            settle()

            # Enter renames for real.
            QTest.keyClick(dialog.name, Qt.Key_Return)
            wait_for(lambda: not dialog.busy)
            after = sorted(p.name for p in shots.iterdir())
            assert after == ["WW_01.txt", "WW_02.png", "WW_03.png", "WW_04.png", "desktop.ini"], after
            assert (shots / "WW_01.txt").read_text(encoding="utf-8") == "keep these words"
            assert digest(shots) == contents_before, "only names change, never contents"
            assert "Renamed 4 files" in dialog.result_line.text(), dialog.result_line.text()
            assert dialog.undo_button.isEnabled()
            assert [Path(i.path).name for i in dialog.items] == ["WW_01.txt", "WW_02.png", "WW_03.png", "WW_04.png"]
            log = (root / "Config" / "activity.log").read_text(encoding="utf-8").splitlines()
            assert json.loads(log[-1])["kind"] == "Batch Rename", log[-1]
            snap(dialog, "tools-batch-rename-done.png")

            # Undo puts the old names back.
            dialog.undo_button.click()
            wait_for(lambda: not dialog.busy)
            after = sorted(p.name for p in shots.iterdir())
            assert after == ["Screenshot a.png", "Screenshot b.png", "Screenshot c.png", "desktop.ini", "notes.txt"], after
            assert digest(shots) == contents_before
            assert not dialog.undo_button.isEnabled()
            assert json.loads((root / "Config" / "activity.log").read_text(encoding="utf-8").splitlines()[-1])["kind"] == "Batch Rename undo"

            # Rename again, close, reopen: Undo still works and preferences are remembered.
            QTest.keyClick(dialog.name, Qt.Key_Return)
            wait_for(lambda: not dialog.busy)
            dialog.done(0)
            window.tools_tiles["batch_rename"].click()
            settle()
            again = shown.pop()
            assert again.name.text() == "WW" and again.undo_button.isEnabled()
            again.undo_button.click()
            wait_for(lambda: not again.busy)
            assert sorted(p.name for p in shots.iterdir())[0] == "Screenshot a.png"
            assert digest(shots) == contents_before

            # A big batch: 1,500 files, dropped on the window itself.
            big = root / "Big"
            big.mkdir()
            for n in range(1500):
                (big / f"clip {n:04d}.mp4").write_bytes(b"x" * 16)
            again.clear_list()
            drop(again, [big])
            assert again.listing.count() == 1500
            again.name.setText("Trip")
            settle()
            assert again.plans[0].name == "Trip_0001.mp4" and again.plans[-1].name == "Trip_1500.mp4"
            started = time.time()
            again.rename_button.click()
            wait_for(lambda: not again.busy, seconds=120)
            print("1,500 files renamed in", round(time.time() - started, 2), "seconds")
            assert len(list(big.glob("Trip_*.mp4"))) == 1500 and not list(big.glob("clip *"))
            assert not list(big.glob(".ggbr-*")), "no temporary names left behind"
            again.listing.scrollToBottom()
            snap(again, "tools-batch-rename-big.png")
            again.undo_button.click()
            wait_for(lambda: not again.busy, seconds=120)
            assert len(list(big.glob("clip *.mp4"))) == 1500
            again.done(0)

            assert errors.call_count == 0, errors.call_args_list
            window.close()
            settle()
    print("PASS: Batch Rename: tile in Files, drop folder (oldest first, hidden files left out), thumbnails, live WW_01 preview, "
          "taken name blocks Enter, reorder, advanced prefix, real rename with contents unchanged and logged, Undo, Undo after "
          "reopening with remembered name, 1,500-file batch and its undo.")


if __name__ == "__main__":
    main()
