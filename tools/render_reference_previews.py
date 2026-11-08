"""Render the native Qt reference layouts using isolated, synthetic data.

Example on Linux:
QT_QPA_PLATFORM=offscreen python tools/render_reference_previews.py --output /tmp/gg-previews
This does not scan, launch, recycle or modify any user library or settings.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    args = parser.parse_args()
    if args.width < 960 or args.height < 650:
        parser.error("The preview minimum viewport is 960 × 650.")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from core import ModFolder, OldFile, SteamGame, default_settings
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.models import merge_games
    from gg_desktop.reference_widgets import reference
    from graveyard import build_graveyard

    app = QApplication.instance() or QApplication([])
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="GG-Design-Fixtures-") as temp:
        root = Path(temp)
        settings = default_settings()
        settings["steam_artwork_downloads"] = False
        settings["scan_folder"] = str(root / "Downloads")
        Path(settings["scan_folder"]).mkdir()
        titles = [
            ("1091500", "Cyberpunk 2077", 112.4), ("1086940", "Baldur's Gate 3", 149.7),
            ("292030", "The Witcher 3: Wild Hunt", 76.3), ("1716740", "Starfield", 125.2),
            ("489830", "Skyrim Special Edition", 48.6), ("1174180", "Red Dead Redemption 2", 119.4),
            ("2933620", "Call of Duty: Black Ops 6", 215.8), ("1245620", "Elden Ring", 54.2),
            ("553850", "Helldivers 2", 44.8), ("1845910", "Dragon Age: The Veilguard", 93.1),
        ]
        games = [SteamGame(app_id, name, str(root / "Steam"), str(root / "Games" / app_id),
                           int(gb * 1024 ** 3), time.time() - i * 86400, "Synthetic preview fixture")
                 for i, (app_id, name, gb) in enumerate(titles)]
        mod_titles = [("Cyber Engine Tweaks", 0), ("RED4ext", 0), ("ArchiveXL", 4),
                      ("SKSE64", 4), ("TweakXL", 0), ("Equipment-EX", 0),
                      ("Immersive Citizens", 4), ("SkyUI", 4), ("Skyrim Flora", 4)]
        mods = [ModFolder(name, str(Path(games[g].install_path) / "mods" / name), "",
                          "Installed: possible mods", ("Synthetic source evidence",),
                          12400000 + i * 5000, 8, False,
                          "Vortex" if i % 2 == 0 else "Mod Organizer 2", "Synthetic protected fixture")
                for i, (name, g) in enumerate(mod_titles)]
        mods += [ModFolder("Steam Shader Cache – Cyberpunk", str(root / "Steam/steamapps/shadercache/1091500"), "",
                 "Shader cache: regenerates", ("shadercache",), int(6.3 * 1024 ** 3), 4182, False,
                 "Steam shader cache", "Review through the original game and launcher."),
                 ModFolder("Steam Shader Cache – Starfield", str(root / "Steam/steamapps/shadercache/1716740"), "",
                 "Shader cache: regenerates", ("shadercache",), int(4.2 * 1024 ** 3), 2651, False,
                 "Steam shader cache", "Protected synthetic fixture."),
                 ModFolder("Steam Download Cache", str(root / "Steam/steamapps/workshop/downloads/489830"), "",
                 "Workshop: pending/download cache", ("download cache",), int(1.7 * 1024 ** 3), 210, False,
                 "Steam Workshop", "May contain active downloads."),
                 ModFolder("Cyberpunk Workshop Content", str(root / "Steam/steamapps/workshop/content/1091500"), "",
                 "Installed: managed content", ("Workshop",), int(8.5 * 1024 ** 3), 318, False,
                 "Steam Workshop", "Linked external content stays protected.")]
        for game in games:
            Path(game.install_path).mkdir(parents=True, exist_ok=True)
        for mod in mods:
            Path(mod.path).mkdir(parents=True, exist_ok=True)
            old_stamp = time.time() - 800 * 86400
            os.utime(mod.path, (old_stamp, old_stamp))
        files = []
        for i, (name, gb) in enumerate([
            ("Cyberpunk 2077 – Old Mods.zip", 68.4), ("Starfield – Old Cache.zip", 42.1),
            ("Nexus Downloads.7z", 28.7), ("Old Game Installer.exe", 24.9),
            ("RDR2 – Leftover Files.zip", 18.3), ("Mod Archives.rar", 16.7),
            ("Crash Logs & Reports.log", 6.1), ("Old Screenshot.png", 4.8),
            ("Game Config.json", .3), ("Installer Temporary.tmp", .7),
        ]):
            # These reported sizes are illustration fixtures, not allocated files.
            path = Path(settings["scan_folder"]) / name
            path.write_bytes(b"DISPOSABLE SYNTHETIC PREVIEW FIXTURE")
            modified = time.time() - (365 + i * 30) * 86400
            os.utime(path, (modified, modified))
            st = path.stat()
            files.append(OldFile(str(path), int(gb * 1024 ** 3), modified,
                                 st.st_dev, st.st_ino, st.st_mtime_ns, st.st_nlink))
        screenshots = []
        for i in range(12):
            app_id = ("1091500", "489830", "1716740", "1174180")[i % 4]
            path = root / f"Steam/userdata/76561198000000001/760/remote/{app_id}/screenshots/capture-{i}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            col, line = i % 4, i // 4
            reference("captures").copy(424 + col * 145, 326 + line * 115, 100, 55).save(str(path))
            modified = time.time() - (400 + i) * 86400
            os.utime(path, (modified, modified))
            st = path.stat()
            screenshots.append(OldFile(str(path), st.st_size, modified, st.st_dev, st.st_ino, st.st_mtime_ns, st.st_nlink))
        undo_rows = [{"id": f"synthetic-{i}", "path": str(root / "Downloads" / name), "size": int(gb * 1024 ** 3),
                      "time": datetime.fromtimestamp(time.time() - i * 86400).astimezone().isoformat(),
                      "action": source, "state": state, "note": "Synthetic recovery record. Availability is not asserted."}
                     for i, (name, gb, source, state) in enumerate([
                         ("Old Recordings.mp4", 18.4, "Captures", "Not checked"), ("Old Mods.zip", 7.3, "Graveyard", "Available"),
                         ("Shader Cache.bin", 4.2, "Shader cache", "Restored"), ("Old Screenshots.png", 6.1, "Captures", "Not found"),
                         ("Installer Leftovers.zip", 12.9, "Old Files", "Not checked"), ("Logs.log", .8, "Old Files", "Available")])]
        with patch.dict(os.environ, {"LOCALAPPDATA": str(root / "Local"), "APPDATA": str(root / "Roaming")}), \
             patch("gg_desktop.app.load_settings", return_value=settings), \
             patch("gg_desktop.recovery_screens.get_records", return_value=undo_rows), \
             patch("gg_desktop.undo_page.get_records", return_value=undo_rows), \
             patch("gg_desktop.undo_page.get_activity", return_value=[]), \
             patch("gg_desktop.assistant_page.get_records", return_value=undo_rows), \
             patch("gg_desktop.assistant_page.get_activity", return_value=[]), \
             patch("gg_desktop.settings_page.get_records", return_value=[]), \
             patch("gg_desktop.reference_overview.get_records", return_value=undo_rows), \
             patch("gg_desktop.reference_overview.get_activity", return_value=[
                 {"kind": name, "details": "Synthetic design fixture", "date": datetime.now().astimezone().isoformat()}
                 for name in ("Scan completed", "Manual recycled", "Mod inventory completed", "Cleanup reviewed")]), \
             patch("gg_desktop.recovery_screens.get_activity", return_value=[]):
            window = CrimsonWindow()
            try:
                window.inventory.steam = games
                window.inventory.games = merge_games(games, [])
                window.inventory.mods = mods
                window.inventory.files = files
                window.inventory.screenshots = screenshots
                window.inventory.graveyard = build_graveyard(games, mods, files, 365, screenshots=screenshots)
                window.inventory.scanned_at = "Synthetic design preview"
                window.inventory.file_scan_root = settings["scan_folder"]
                window.inventory.file_scan_days = 180
                window.status.setText("DESIGN PREVIEW · Synthetic sample data")
                window.resize(args.width, args.height)
                window.show()
                for route in ("Overview", "Games", "Mods", "Old Files", "Other Storage", "Captures", "Graveyard", "Game DNA", "Undo Center"):
                    if route == "Game DNA":
                        window._pending_dna_game_key = next(g.key for g in window.inventory.games if g.name == "Cyberpunk 2077")
                    window.navigate(route)
                    for _ in range(4):
                        app.processEvents()
                        time.sleep(.01)
                    if route == "Mods":
                        index = next(i for i, m in enumerate(window._shown_mods) if m.name == "Cyber Engine Tweaks")
                        window.mod_table.selectRow(index)
                    if route == "Old Files":
                        for i in (0, 1, 3):
                            window.old_table.item(i, 0).setCheckState(Qt.Checked)
                    if route == "Captures":
                        # Explicit preview requests for these disposable fixtures,
                        # never automatic decoding of a real capture inventory.
                        with patch.object(window, "job", side_effect=lambda fn, done, **_: done(fn(None))):
                            for i in range(len(window._shown_captures)):
                                window._request_capture_preview(i)
                        for i in (0, 3, 5):
                            window.capture_grid.item(i).setCheckState(Qt.Checked)
                    if route == "Graveyard":
                        window._select_eligible()
                    if route == "Other Storage":
                        window.storage_table.item(0, 0).setCheckState(Qt.Checked)
                    if route == "Undo Center":
                        if window.undo_table.item(0, 0):
                            window.undo_table.item(0, 0).setCheckState(Qt.Checked)
                    app.processEvents()
                    path = args.output / f"{route.lower().replace(' ', '-')}-{args.width}.png"
                    if not window.grab().save(str(path)):
                        raise RuntimeError("Failed to render " + route)
                    print(path)
            finally:
                window.close()
                app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
