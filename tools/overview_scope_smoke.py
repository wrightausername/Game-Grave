"""Prove Overview's approved UI and all other pages remain unchanged."""
from __future__ import annotations

import argparse
import ast
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

BASELINE = "77eaa28b0b78cc35a0e06857ca09fb6ec5782069"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("_ci_temp"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if subprocess.run(["git", "cat-file", "-e", BASELINE], cwd=root, capture_output=True).returncode:
        subprocess.run(["git", "fetch", "--no-tags", "--depth=1", "origin", BASELINE], cwd=root, check=True)
    def original(path):
        return subprocess.check_output(["git", "show", BASELINE + ":" + path], cwd=root).decode("utf-8").replace("\r\n", "\n")

    asset_changes = subprocess.check_output(["git", "diff", "--name-only", BASELINE, "--", "gg_desktop/assets"], cwd=root)
    assert not asset_changes.strip(), "Approved artwork or fonts changed"
    for name in ("app.py", "theme.py", "widgets.py", "backend.py", "models.py",
                 "ready_room.py", "ready_room_data.py", "ready_room_actions.py", "ready_room_services.py"):
        path = "gg_desktop/" + name
        assert (root / path).read_text(encoding="utf-8") == original(path), "Changed outside Overview: " + path
    for path in ("core.py", "screenshots.py", "screenshot_preview.py", "cleanup_actions.py", "graveyard.py", "recovery.py"):
        assert (root / path).read_text(encoding="utf-8") == original(path), "Shared backend changed: " + path
    def without_overview(source):
        tree = ast.parse(source)
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == "ScreenMethods":
                node.body = [method for method in node.body if getattr(method, "name", "") != "overview_page"]
        return ast.dump(tree, include_attributes=False)
    source = original("gg_desktop/screens.py")
    assert without_overview(source) == without_overview((root / "gg_desktop/screens.py").read_text(encoding="utf-8")), "A screen other than Overview changed"

    from PySide6.QtCore import QCoreApplication, QEvent, Qt
    from PySide6.QtGui import QCursor
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from core import OldFile, SteamGame, ModFolder, default_settings
    from gg_desktop.app import CrimsonWindow, ROUTES
    from gg_desktop.backend import Inventory
    from gg_desktop.models import merge_games
    from gg_desktop.overview_data import CaptureResult
    from graveyard import build_graveyard
    from launchers import LauncherGame

    namespace = {"__name__": "gg_desktop.overview_scope_baseline", "__file__": str(root / "gg_desktop/screens.py")}
    exec(compile(source, "baseline_screens.py", "exec"), namespace)
    class BaselineWindow(CrimsonWindow):
        overview_page = namespace["ScreenMethods"].overview_page

    app = QApplication.instance() or QApplication([])
    def settle(window):
        window.activateWindow()
        window.centralWidget().setFocusPolicy(Qt.StrongFocus)
        window.centralWidget().setFocus()
        for _ in range(3):
            app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            QTest.qWait(10)
    def compare(before, after, label):
        settle(before)
        settle(after)
        expected, actual = before.page.grab().toImage(), after.page.grab().toImage()
        if expected != actual:
            expected.save(str(args.output / (label + "-baseline.png")))
            actual.save(str(args.output / (label + "-current.png")))
            raise AssertionError("Approved UI pixels changed: " + label)

    with tempfile.TemporaryDirectory(prefix="GG-overview-scope-") as temp:
        folder = Path(temp)
        archive = folder / "old-skyrim-mod.zip"
        archive.write_bytes(b"DISPOSABLE ARCHIVE")
        old_time = __import__("time").time() - 900 * 86400
        os.utime(archive, (old_time, old_time))
        info = archive.stat()
        old = OldFile(str(archive), info.st_size, info.st_mtime, info.st_dev, info.st_ino, info.st_mtime_ns, info.st_nlink)
        image = folder / "synthetic-game-capture.png"
        image.write_bytes(b"Metadata-only scope fixture; never decoded")
        image_stat = image.stat()
        screenshot = OldFile(str(image), image_stat.st_size, image_stat.st_mtime,
                             image_stat.st_dev, image_stat.st_ino, image_stat.st_mtime_ns, image_stat.st_nlink)
        steam = [SteamGame("1091500", "Synthetic Steam Game", str(folder), str(folder / "Game"), 1024, None, "Unknown")]
        others = [LauncherGame("Synthetic Epic Game", "Epic Games", str(folder / "Epic"), "epic1", None, "Manifest verified")]
        populated = Inventory(steam=steam, other=others, games=merge_games(steam, others), files=[old], scanned_at="Synthetic scope QA")
        populated.screenshots = [screenshot]
        populated.mods = [ModFolder("Synthetic mods", str(folder / "Mods"), str(folder), "Protected", (), 200, 1, False, "Test manager")]
        populated.graveyard = build_graveyard(steam, populated.mods, [old], 365)
        disk = SimpleNamespace(total=1024**4, used=256 * 1024**3, free=768 * 1024**3)
        QCursor.setPos(0, 0)
        with patch("gg_desktop.app.load_settings", side_effect=default_settings), \
             patch("gg_desktop.screens.shutil.disk_usage", return_value=disk), \
             patch("gg_desktop.ready_room_services.config_dir", return_value=folder / "Preferences"), \
             patch("gg_desktop.overview.latest_capture", return_value=CaptureResult()) as capture_read, \
             patch.object(CrimsonWindow, "ready_refresh_checks"):
            baseline, window = BaselineWindow(), CrimsonWindow()
            baseline.show()
            window.show()
            assert window.current_route == baseline.current_route == "Overview"
            assert window.styleSheet() == baseline.styleSheet()
            assert window.windowFlags() == baseline.windowFlags()
            for state, inventory in (("empty", Inventory()), ("populated", populated)):
                baseline.inventory = window.inventory = inventory
                capture_read.return_value = CaptureResult(screenshot if inventory.scanned_at else None)
                for width, height in ((1450, 900), (1280, 790), (960, 650)):
                    baseline.resize(width, height)
                    window.resize(width, height)
                    baseline.navigate("Overview")
                    window.navigate("Overview")
                    compare(baseline, window, f"overview-{state}-{width}")
                baseline.resize(1450, 900)
                window.resize(1450, 900)
                for route, _ in ROUTES:
                    baseline.navigate(route)
                    window.navigate(route)
                    compare(baseline, window, f"scope-{state}-{route.lower().replace(' ', '-')}")
            window.inventory = baseline.inventory = Inventory()
            window.navigate("Overview")
            settle(window)
            assert window.grab().save(str(args.output / "restored-overview.png"))
            window.close()
            baseline.close()
            app.processEvents()
    print("PASS: Overview pixels match the approved baseline at 1450, 1280 and 960 pixels, empty and populated; "
          "every other page including Ready Room matches; shared shell, styles, assets and backend sources are unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
