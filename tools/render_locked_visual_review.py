"""Render actual Qt pages with an isolated, explicitly synthetic visual fixture.

No scans, cleanup, AI inference, network requests or user files are involved.
Original approved header crops are loaded by the normal application widgets.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
import shutil
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    if os.name != "nt":
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QCoreApplication, QEvent
    from core import SteamGame, OldFile, ModFolder, default_settings
    from graveyard import build_graveyard
    from gg_desktop.models import merge_games
    from gg_desktop.app import CrimsonWindow, configure_crimson_dialog_palette

    app = QApplication.instance() or QApplication([])
    configure_crimson_dialog_palette(app)
    with tempfile.TemporaryDirectory(prefix="GG-Visual-") as temporary:
        data = Path(temporary)
        with patch.dict(os.environ, {"LOCALAPPDATA": str(data / "Local"),
                                     "APPDATA": str(data / "Roaming")}):
            settings = default_settings()
            settings["scan_on_launch"] = False
            with patch("gg_desktop.app.load_settings", return_value=settings):
                window = CrimsonWindow()
            games = []
            for index, title in enumerate(("Demo Adventure", "Demo Open World",
                    "Demo Racing", "Demo Strategy", "Demo Survival", "Demo RPG")):
                install = data / "Steam" / "steamapps" / "common" / title
                install.mkdir(parents=True)
                games.append(SteamGame(str(900001+index), title, str(data / "Steam"),
                    str(install), (8+index*7)*1024**3, None, "Unknown"))
            files = []
            for index in range(12):
                path = data / "Downloads" / f"demo-game-mod-{index+1:02d}.zip"
                path.parent.mkdir(exist_ok=True)
                # Sparse fixture: real apparent size, negligible physical allocation.
                with path.open("wb") as stream:
                    stream.truncate((index+1)*71_000_000)
                stamp = time.time() - (390+index*38)*86400
                os.utime(path, (stamp, stamp))
                state = path.stat()
                files.append(OldFile(str(path), state.st_size, state.st_mtime,
                    state.st_dev, state.st_ino, state.st_mtime_ns, state.st_nlink))
            window.settings["never_touch"] = [item.path for item in files[1:4]]
            window.inventory.steam = games
            window.inventory.games = merge_games(games, [])
            mods = []
            for game in games[:3]:
                folder = Path(game.install_path) / "Data" / "Mods"
                folder.mkdir(parents=True)
                fixture = folder / "SYNTHETIC-REVIEW.txt"
                fixture.write_text("Disposable UI review fixture, not a real mod.")
                mods.append(ModFolder(game.name, str(folder), game.library,
                    "Installed", ("SYNTHETIC fixture",), fixture.stat().st_size,
                    1, False, source="Steam game folder"))
            external = data / "Managers" / "MO2" / "mods"
            external.mkdir(parents=True)
            mods.append(ModFolder("External fixture", str(external), "",
                "Unknown", ("SYNTHETIC fixture",), 0, 0, False,
                source="Mod Organizer 2"))
            window.inventory.mods = mods
            window.inventory.files = files
            window.inventory.scanned_at = "SYNTHETIC visual-review inventory"
            window.inventory.old_files_scan_status = "complete"
            window.inventory.old_files_scan_message = "SYNTHETIC visual-review fixture"
            window.inventory.old_files_scan_root = str(data / "Downloads")
            window.settings["scan_folder"] = str(data / "Downloads")
            window.inventory.graveyard = build_graveyard(games, mods, files, 365,
                never_touch=window.settings["never_touch"])
            screenshot_records = []
            for index, page_name in enumerate(("graveyard", "undo-center")):
                # Existing screenshots of this application, explicitly used as
                # review fixtures. No invented gameplay images or user pixels.
                source = root / "docs" / "ui-review" / "2026-11-04" / "windows" / (
                    "visual-review-" + page_name + "-1672.png")
                path = data / "Videos" / "Captures" / f"UI-screenshot-fixture-{index+1}.png"
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, path)
                state = path.stat()
                screenshot_records.append(OldFile(str(path), state.st_size, state.st_mtime,
                    state.st_dev, state.st_ino, state.st_mtime_ns, state.st_nlink))
            window.inventory.screenshots = screenshot_records
            now = datetime.now(timezone.utc)
            records = [{"id":f"demo-record-{index}",
                "path":str(data / "Downloads" / f"demo-archive-{index+1:02d}.zip"),
                "size":(index+1)*81_000_000, "action":"Manual recycle",
                "time":(now-timedelta(hours=index*3)).isoformat(),
                "state":("Available", "Restored", "Not checked", "Needs review")[index%4],
                "source":"SYNTHETIC VISUAL FIXTURE"} for index in range(12)]
            events = [{"date":(now-timedelta(hours=index*2)).isoformat(),
                "kind":kind, "details":"SYNTHETIC visual-review event",
                "path":str(data / "Downloads" / f"demo-archive-{index:02d}.zip"),
                "source":"SYNTHETIC VISUAL FIXTURE"} for index, kind in enumerate((
                    "Scan completed", "Manual recycled", "Mod inventory completed",
                    "Cleanup reviewed", "Restored from Recycle Bin"))]
            window._ai_session = {"busy":False, "status":"Synthetic conversation; no AI model was run.",
                "messages":[
                    "You: DEMO — Explain these old archives before I remove anything.",
                    f"Game Grave AI: This visual-review inventory contains {len(window.inventory.graveyard)} candidates. "
                    "Three have a personal Never Touch rule. Their age is evidence for review, "
                    "not proof that they are unused.",
                    "You: What should I check next?",
                    "Game Grave AI: Open an individual finding in Graveyard and check its path, "
                    "source and protection reason. Save files and active mod locations remain "
                    "protected. Any removal needs your separate confirmation."]}
            import gg_desktop.approved_overview
            import gg_desktop.approved_undo
            routes = ("Overview", "Ready Room", "Games", "Mods", "Old Files",
                      "Other Storage", "Captures", "Graveyard", "Game DNA",
                      "Undo Center", "AI Assistant", "Settings", "More Tools")
            captures = []
            with patch("core.get_activity", side_effect=lambda limit=1500: events[:limit]), \
                    patch("gg_desktop.approved_overview.get_activity", side_effect=lambda limit=1500: events[:limit]), \
                    patch("gg_desktop.approved_overview.get_records", return_value=records), \
                    patch("gg_desktop.approved_undo.get_records", return_value=records):
                window.show()
                try:
                    for width, height in ((1672, 941), (1366, 768)):
                        window.resize(width, height)
                        for route in routes:
                            window._settings_category_index = 0
                            window.navigate(route)
                            for _ in range(8):
                                app.processEvents()
                            if route == "Captures":
                                from gg_desktop.capture_image import ScreenshotImage
                                preview = window.page.findChild(ScreenshotImage, "captureSelectedImage")
                                deadline = time.monotonic() + 10
                                while preview is not None and not preview.has_image() and time.monotonic() < deadline:
                                    app.processEvents()
                                    time.sleep(.02)
                                if preview is None or not preview.has_image():
                                    raise RuntimeError("Actual Captures image did not render")
                            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
                            slug = route.casefold().replace(" ", "-")
                            filename = f"visual-review-{slug}-{width}.png"
                            if not window.grab().save(str(output / filename)):
                                raise RuntimeError("Could not save " + filename)
                            captures.append({"page":route,"file":filename,"size":[width,height],
                                "body_width":window.page.body.width(),
                                "viewport_width":window.page.viewport().width(),
                                "vertical_scroll_maximum":window.page.verticalScrollBar().maximum()})
                finally:
                    window.close()
                    app.processEvents()
            (output / "visual-review.json").write_text(json.dumps({
                "fixture":"Explicit synthetic visual data; no user data or AI inference",
                "covers":"Genuine local images when available; neutral missing-artwork states otherwise",
                "capture_images":"Existing actual application screenshots used as synthetic review fixtures",
                "platform":sys.platform,"commit":os.environ.get("GITHUB_SHA", "local working tree"),
                "source_reference":"Owner-supplied seven-page reference/running-UI comparison, left column",
                "pixel_fidelity":"No automated claim of 1:1 equivalence",
                "captures":captures},indent=2),encoding="utf-8")
            print(f"Rendered {len(captures)} actual Qt captures with synthetic visual-review data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
