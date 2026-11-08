"""Native Qt check of the Captures page: scan, metrics, thumbnails, filters, tabs, tags, analysis, protection and the verified Recycle Bin path."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import os
from pathlib import Path
import shutil
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
    from PIL import Image
    from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget
    from core import SteamGame, default_settings, human_size
    from gg_desktop import captures_page
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.backend import Inventory
    from gg_desktop.insight_widgets import CAPTURE_ROLE

    app = QApplication.instance() or QApplication([])
    day = 86400

    def settle():
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()

    def wait_for(predicate, what="Captures did not finish its task"):
        deadline = time.monotonic() + 40
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
            time.sleep(.004)
        assert predicate(), what
        settle()

    def picture(path, size=(320, 180), color=(200, 30, 30), age=0, noise=0):
        path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", size)
        pixels = image.load()
        for x in range(size[0]):
            for y in range(size[1]):
                pixels[x, y] = (min(255, color[0] + x // 4 + noise), min(255, color[1] + y // 4), color[2])
        image.save(path)
        moment = time.time() - age * day
        os.utime(path, (moment, moment))
        return path

    def blob(path, payload, age=0):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        moment = time.time() - age * day
        os.utime(path, (moment, moment))
        return path

    def tree_bytes(folder):
        return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in folder.rglob("*") if p.is_file()}

    def shown(window):
        return [c.name for c in window._shown_captures]

    def every(window):
        return [c.name for c in window._cap_rows]

    def open_tab(window, name):
        window.capture_tabs.buttons[name].click()
        settle()
        assert state_of(window).tab == name, name

    def tick(window, name, on=True):
        index = shown(window).index(name)
        item = window.capture_grid.item(index)
        item.setCheckState(Qt.Checked if on else Qt.Unchecked)
        settle()

    def idle(window):
        wait_for(lambda: not state_of(window).busy and not window.workers and not window.cleaning)

    with tempfile.TemporaryDirectory(prefix="GG-captures-page-") as temp:
        root = Path(temp)
        home, steam = root / "Home", root / "Steam"
        extra = root / "ExtraShots"
        for folder in (home, steam, extra):
            folder.mkdir()
        shots = home / "Pictures" / "Game Screenshots"
        clips = home / "Videos" / "Captures"
        owned_dir = steam / "userdata" / "123" / "760" / "remote" / "1091500" / "screenshots"
        picture(shots / "alpha.png", (1920, 1080), (200, 30, 30), age=2)
        picture(shots / "dup_one.png", (320, 180), (30, 160, 60), age=40)
        blob(shots / "dup_two.png", (shots / "dup_one.png").read_bytes(), age=10)
        picture(shots / "similar_a.png", (320, 180), (20, 40, 200), age=5)
        picture(shots / "similar_b.png", (320, 180), (20, 40, 200), age=4, noise=2)
        picture(shots / "ancient.png", (640, 360), (180, 180, 40), age=900)
        picture(owned_dir / "steam_one.png", (800, 450), (230, 120, 20), age=60)
        blob(clips / "clip one.mp4", b"v" * 5000, age=300)
        picture(extra / "extra_shot.png", (200, 100), (10, 200, 200), age=3)
        before = tree_bytes(root)
        game = SteamGame("1091500", "Cyberpunk 2077", str(steam), str(root / "Library" / "steamapps" / "common" / "Cyberpunk 2077"),
                         120000000, None, "Scope fixture")
        settings = default_settings()
        settings["never_touch"] = []
        settings["screenshot_roots"] = []
        settings["recording_roots"] = []
        saved = []
        env = {"USERPROFILE": str(home), "HOME": str(home)}
        shell_bin = root / "DisposableShell"
        shell_bin.mkdir()
        recycled = []

        def fake_recycle(path):
            recycled.append(Path(path))
            shutil.move(str(path), str(shell_bin / (str(len(recycled)) + "-" + Path(path).name)))

        def keep_settings(updated):
            saved.append(dict(updated))

        def allow(path):
            return Path(path).is_dir()

        from PySide6.QtWidgets import QFileDialog, QInputDialog
        from gg_desktop.captures_page import state_of
        stack = ExitStack()
        stack.enter_context(patch.dict(os.environ, env))
        for target, options in (
            ("gg_desktop.app.load_settings", dict(return_value=settings)),
            ("gg_desktop.captures_data.safe_scan_root", dict(new=allow)),
            ("gg_desktop.captures_page.safe_scan_root", dict(new=allow)),
            ("screenshots.safe_scan_root", dict(new=allow)),
            ("recordings.safe_scan_root", dict(new=allow)),
            ("gg_desktop.captures_data._steam_roots", dict(return_value=[steam])),
            ("gg_desktop.captures_state.config_dir", dict(return_value=root / "Config")),
            ("core.save_settings", dict(side_effect=keep_settings)),
            ("gg_desktop.captures_page.save_settings", dict(side_effect=keep_settings)),
            ("gg_desktop.reference_library.save_settings", {}),
            ("gg_desktop.recovery_screens.save_settings", dict(side_effect=keep_settings)),
            ("gg_desktop.ready_room_services.config_dir", dict(return_value=root / "Preferences")),
            ("gg_desktop.game_artwork.artwork_dir", dict(return_value=root / "Artwork")),
            ("gg_desktop.game_artwork._request", dict(side_effect=AssertionError("No automatic network"))),
        ):
            stack.enter_context(patch(target, **options))
        info = stack.enter_context(patch.object(CrimsonWindow, "info"))
        errors = stack.enter_context(patch.object(CrimsonWindow, "error"))
        confirm = stack.enter_context(patch.object(CrimsonWindow, "confirm", return_value=False))
        chooser = stack.enter_context(patch.object(QFileDialog, "getExistingDirectory"))
        asker = stack.enter_context(patch.object(QInputDialog, "getText"))
        picker = stack.enter_context(patch.object(QInputDialog, "getItem"))
        with stack:
            window = CrimsonWindow()
            window.inventory = Inventory(steam=[game], scanned_at="2026-11-06 12:00")
            window.show()
            window.resize(1280, 720)
            window.navigate("Captures")
            settle()

            # First open scans by itself, reads only metadata, and claims only what it finds.
            state = state_of(window)
            wait_for(lambda: state.scanned and not state.busy and not window.workers)
            names = {"alpha.png", "dup_one.png", "dup_two.png", "similar_a.png", "similar_b.png", "ancient.png", "steam_one.png"}
            assert set(every(window)) == names, every(window)
            strip = window.capture_metrics.values
            assert strip[0].text() == "7" and strip[1].text() == "1", [v.text() for v in strip]
            total = sum(c.size for c in state.report.captures)
            assert strip[2].text() == human_size(total), strip[2].text()
            assert strip[3].text() == "1", "Only the proven Steam game is counted"
            assert strip[4].text() == "2+ Years", strip[4].text()
            assert window.capture_tabs.buttons["Screenshots"].text() == "Screenshots (7)"
            assert window.capture_tabs.buttons["Recordings"].text() == "Recordings (1)"
            assert window.capture_stack.currentIndex() == 0

            # Thumbnails decode in memory for the tiles on screen.
            wait_for(lambda: all(c.key in state.thumbs for c in window._shown_captures))
            for i in range(window.capture_grid.count()):
                payload = window.capture_grid.item(i).data(CAPTURE_ROLE)
                assert payload["preview"] is not None and not payload["preview"].isNull(), i
            wait_for(lambda: all(c.dimensions for c in state.report.captures if c.kind == "Screenshots"), "Resolution never loaded")
            assert window.grab().save(str(args.output / "captures-results-1280.png"))

            # Details are evidence, never a safe-to-delete claim.
            window.capture_grid.setCurrentRow(shown(window).index("steam_one.png"))
            settle()
            text = " ".join(w.text() for w in window.capture_details.findChildren(QLabel))
            assert "Cyberpunk 2077" in text and "Recommendations" in text, text
            assert "safe to delete" not in text.lower() and "safe to remove" not in text.lower(), text
            assert "1920" not in text and "800" in text, text

            # Filters: game, type, age, size, resolution, search and Clear All.
            window.capture_game.setCurrentRow(1)
            settle()
            assert window.capture_game.currentItem().data(Qt.UserRole) == "Cyberpunk 2077"
            assert every(window) == ["steam_one.png"], every(window)
            window.capture_game.setCurrentRow(0)
            settle()
            window.capture_age.setCurrentText("2+ Years")
            settle()
            assert every(window) == ["ancient.png"], every(window)
            window.capture_age.setCurrentIndex(0)
            window.capture_resolution.setCurrentText("1080p or Larger")
            settle()
            assert every(window) == ["alpha.png"], every(window)
            window.capture_resolution.setCurrentIndex(0)
            window.capture_global = window.global_search
            window.global_search.setText("similar")
            settle()
            assert set(every(window)) == {"similar_a.png", "similar_b.png"}, every(window)
            window.global_search.clear()
            window.capture_sort.setCurrentText("Name (A–Z)")
            settle()
            assert every(window) == sorted(every(window), key=str.casefold)
            window.capture_sort.setCurrentText("Size (Largest)")
            window.capture_age.setCurrentText("30+ Days")
            window.capture_types[0].setChecked(False)
            settle()
            assert not every(window), "Both types hidden would show nothing on Screenshots"
            window.capture_types[0].setChecked(True)
            window.capture_tabs.buttons["Screenshots"].click()
            window.capture_zoom.setValue(190)
            settle()
            captures_page.clear_filters(window)
            settle()
            assert set(every(window)) == names and window.capture_age.currentIndex() == 0

            # Recordings keep their own tab and open without decoding.
            open_tab(window, "Recordings")
            assert every(window) == ["clip one.mp4"], every(window)
            open_tab(window, "Screenshots")

            # By Game / Timeline / Clean Up tabs fill from the scan only.
            open_tab(window, "By Game")
            assert window.capture_notice.text().startswith("Game links come from"), window.capture_notice.text()
            open_tab(window, "Timeline")
            assert window.capture_month.isVisible() and window.capture_month.count() > 1
            open_tab(window, "Clean Up")
            assert "ancient.png" in every(window) and "alpha.png" not in every(window), every(window)
            open_tab(window, "Screenshots")

            # Tags are saved by Game Grave only.
            tick(window, "alpha.png")
            asker.return_value = ("Favorite", True)
            captures_page.add_tag(window)
            settle()
            assert "Favorite" in [window.capture_tag.itemText(i) for i in range(window.capture_tag.count())]
            assert (root / "Config" / "capture_tags.json").is_file()
            window.capture_tag.setCurrentText("Favorite")
            settle()
            assert every(window) == ["alpha.png"], every(window)
            picker.return_value = ("Favorite", True)
            captures_page.remove_tag(window)
            settle()
            assert window.capture_tag.currentText() == "All Tags" and "Favorite" not in [
                window.capture_tag.itemText(i) for i in range(window.capture_tag.count())]
            tick(window, "alpha.png", False)

            # Duplicates are found by content, only when asked.
            open_tab(window, "Duplicates")
            assert state.duplicates is None and window.capture_action.text() == "Find Duplicates"
            assert not every(window), "Nothing is claimed before the check"
            window.capture_action.click()
            wait_for(lambda: not state.busy and not window.workers)
            assert state.duplicates is not None and len(state.duplicates) == 1
            assert set(every(window)) == {"dup_one.png", "dup_two.png"}, every(window)
            assert window.grab().save(str(args.output / "captures-duplicates-1280.png"))
            captures_page.select_extra_copies(window)
            settle()
            assert [c.name for c in captures_page.selected_captures(window)] == ["dup_two.png"], "The oldest copy is kept"
            window.capture_grid.setCurrentRow(shown(window).index("dup_one.png"))
            settle()
            window._capture_subtab = "Related"
            captures_page.details(window)
            related_text = " ".join([w.text() for w in window.capture_details.findChildren(QLabel)] +
                                    [b.text() for b in window.capture_details.findChildren(QPushButton)])
            assert "dup_two.png" in related_text, related_text
            window._capture_subtab = "Details"

            # Similar images are found by fingerprint, labelled as similar and never as identical.
            open_tab(window, "Similar")
            window.capture_action.click()
            wait_for(lambda: not state.busy and not window.workers)
            assert state.similar is not None and any({"similar_a.png", "similar_b.png"} <= {c.name for c in universe_of(window, g)}
                                                      for g in state.similar), state.similar

            # Protect saves a Never Touch rule and moves nothing.
            open_tab(window, "Screenshots")
            captures_page.select_visible(window, False)
            tick(window, "alpha.png")
            window._protect_paths([c.path for c in captures_page.selected_captures(window)], lambda: captures_page.refresh(window))
            settle()
            assert any("alpha.png" in str(rule) for rule in window.settings["never_touch"]), window.settings["never_touch"]
            assert not window.capture_delete.isEnabled() and "protected" in window.capture_delete.toolTip().lower(), window.capture_delete.toolTip()
            tick(window, "alpha.png", False)
            assert (shots / "alpha.png").exists()

            # Add to Graveyard only lists the file for protected review.
            tick(window, "ancient.png")
            captures_page.add_to_graveyard(window)
            assert info.called
            assert any(str(shots / "ancient.png") == r["path"] for r in window.settings["manual_review_files"])
            assert any(e.path == str(shots / "ancient.png") for e in window.inventory.graveyard)
            tick(window, "ancient.png", False)
            assert (shots / "ancient.png").exists()

            # Copy To never changes the originals.
            destination = root / "CopyHere"
            destination.mkdir()
            chooser.return_value = str(destination)
            tick(window, "similar_a.png")
            captures_page.copy_selected(window)
            wait_for(lambda: not window.workers)
            assert (destination / "similar_a.png").is_file() and (shots / "similar_a.png").is_file()
            tick(window, "similar_a.png", False)

            # List view shares the same selection and rows.
            window.capture_view_list.click()
            settle()
            assert window.capture_stack.currentIndex() == 1
            assert window.capture_table.rowCount() == len(window._shown_captures) == 7
            assert window.grab().save(str(args.output / "captures-list-1280.png"))
            window.capture_view_grid.click()
            settle()
            assert window.capture_stack.currentIndex() == 0

            # A large preview opens without writing anything.
            captures_page.open_viewer(window, shown(window).index("steam_one.png"))
            wait_for(lambda: not window.workers)
            viewer = window._capture_viewer
            assert viewer.isVisible() and viewer.image.pixmap() is not None and not viewer.image.pixmap().isNull()
            viewer.close()
            settle()

            # Delete: the extra duplicate only; declined first, then approved into a disposable shell bin.
            open_tab(window, "Duplicates")
            captures_page.select_visible(window, False)
            captures_page.select_extra_copies(window)
            settle()
            assert window.capture_delete.isEnabled()
            captures_page.delete_selected(window)
            idle(window)
            assert confirm.called and (shots / "dup_two.png").exists(), "Declined must change nothing"
            confirm.return_value = True
            with patch("gg_desktop.captures_actions.recycle_file", side_effect=fake_recycle), \
                 patch("gg_desktop.captures_actions.register_recycle", return_value="test"), \
                 patch("gg_desktop.captures_actions.log_event"):
                captures_page.delete_selected(window)
                idle(window)
            assert [p.name for p in recycled] == ["dup_two.png"], recycled
            assert not (shots / "dup_two.png").exists() and (shots / "dup_one.png").exists()
            assert "dup_two.png" not in [c.name for c in captures_page.universe(window)]
            assert state.duplicates == [], state.duplicates
            open_tab(window, "Screenshots")
            assert "dup_two.png" not in every(window) and len(every(window)) == 6
            assert window.grab().save(str(args.output / "captures-cleared-1280.png"))

            # Settings lists the scanned folders and lets the user add one, read-only.
            open_tab(window, "Settings")
            assert window.capture_stack.currentIndex() == 2
            listed = [window.capture_roots_list.item(i).text() for i in range(window.capture_roots_list.count())]
            assert len(listed) >= 3, listed
            assert window.grab().save(str(args.output / "captures-settings-1280.png"))
            chooser.return_value = str(extra)
            captures_page.add_folder(window, "screenshot_roots")
            wait_for(lambda: not state.busy and not window.workers)
            assert str(extra) in window.settings["screenshot_roots"]
            assert "extra_shot.png" in [c.name for c in captures_page.universe(window)]
            window.capture_roots_list.setCurrentRow(next(i for i in range(window.capture_roots_list.count())
                                                         if str(extra) in window.capture_roots_list.item(i).text()))
            captures_page.remove_folder(window)
            wait_for(lambda: not state.busy and not window.workers)
            assert str(extra) not in window.settings["screenshot_roots"]
            assert "extra_shot.png" not in [c.name for c in captures_page.universe(window)]
            open_tab(window, "Screenshots")

            # The page remembers its scan, and narrower windows keep every action visible.
            window.navigate("Overview")
            settle()
            window.navigate("Captures")
            settle()
            assert state.scanned and len(captures_page.universe(window)) == 7
            for width, height in ((1280, 720), (1440, 900), (960, 650)):
                window.resize(width, height)
                settle()
                if height >= 720:
                    bottom = window.capture_more.mapTo(window, QPoint(0, window.capture_more.height())).y()
                    assert bottom <= window.height(), ("Footer actions are cut off", (width, height), bottom)
                if window.page.horizontalScrollBar().maximum() != 0:
                    wide = sorted(((w.minimumSizeHint().width(), type(w).__name__, w.objectName())
                                   for w in window.page.findChildren(QWidget)), reverse=True)[:12]
                    print("Horizontal overflow at", (width, height), "viewport", window.page.viewport().width(), "widest:", wide)
                assert window.page.horizontalScrollBar().maximum() == 0, (width, height)
                assert window.grab().save(str(args.output / f"captures-page-{width}.png"))
            errors.assert_not_called()
            window.close()
            settle()
        after = tree_bytes(root)
        gone = {k for k in before if k not in after and not k.startswith("DisposableShell")}
        assert gone == {str(Path("Home") / "Pictures" / "Game Screenshots" / "dup_two.png")}, gone
        changed = {k for k in before if k in after and before[k] != after[k]}
        assert not changed, changed
    print("PASS: Captures page: scan-only metrics, in-memory thumbnails, evidence without safe-to-delete claims, filters, tabs, tags, "
          "duplicate and similar analysis, protection, Graveyard review, copy, and a confirmed Recycle Bin move of exactly the checked extra copy.")
    return 0


def universe_of(window, keys):
    from gg_desktop import captures_page
    by_key = {c.key: c for c in captures_page.universe(window)}
    return [by_key[k] for k in keys if k in by_key]


if __name__ == "__main__":
    raise SystemExit(main())
