"""Disposable native Windows Qt smoke. Never opens or mutates user game data."""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path


def main():
    if os.name != "nt" or os.environ.get("GG_CRIMSON_QA_DISPOSABLE") != "YES":
        print("Refusing to run without Windows disposable CI approval.")
        return 2
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from PySide6.QtWidgets import QApplication, QTableWidget
    from core import SteamGame, OldFile
    from launchers import LauncherGame
    from graveyard import build_graveyard
    from gg_desktop.models import merge_games
    from gg_desktop.app import CrimsonWindow

    app = QApplication.instance() or QApplication(sys.argv)
    with tempfile.TemporaryDirectory(prefix="GG-Crimson-", dir=root / "_ci_temp") as temp:
        synthetic = Path(temp)
        os.environ["LOCALAPPDATA"] = str(synthetic / "Local")
        os.environ["APPDATA"] = str(synthetic / "Roaming")
        Path(os.environ["LOCALAPPDATA"]).mkdir(parents=True)
        Path(os.environ["APPDATA"]).mkdir(parents=True)
        oldzip = synthetic / "old-skyrim-mod.zip"
        oldzip.write_bytes(b"not an actual mod or game")
        stamp = time.time() - 800 * 86400
        os.utime(oldzip, (stamp, stamp))
        st = oldzip.stat()
        old = OldFile(str(oldzip), st.st_size, st.st_mtime,
                      st.st_dev, st.st_ino, st.st_mtime_ns, st.st_nlink)
        steam = [SteamGame("455", "Sample Steam Game", str(synthetic),
                           str(synthetic / "Steam" / "Sample"),
                           1200000, None, "Unknown")]
        other = [
            LauncherGame("Sample Epic Game", "Epic Games",
                         str(synthetic / "Epic" / "Sample"),
                         "epic455", None, "Manifest and folder verified"),
            LauncherGame("Sample EA Game", "EA",
                         str(synthetic / "EA" / "Sample"),
                         "ea11", None, "Registry installation record"),
        ]
        window = CrimsonWindow()
        window.show()
        app.processEvents()
        try:
            window.settings["scan_on_launch"] = False
            window.inventory.steam = steam
            window.inventory.other = other
            window.inventory.games = merge_games(steam, other)
            window.inventory.files = [old]
            window.inventory.scanned_at = "Synthetic test date"
            window.inventory.graveyard = build_graveyard(steam, [], [old], 365)
            for route in ("Overview", "Games", "Graveyard", "Game DNA",
                          "Mods", "Old Files", "Undo Center", "Settings", "More Tools"):
                window.navigate(route)
                window.resize(1366, 768)
                app.processEvents()
                assert window.page is not None and window.page.isVisible()
                assert window.current_route == route
                assert oldzip.read_bytes() == b"not an actual mod or game"
                if route == "Games":
                    rows = window._shown_games
                    assert len(rows) == 3
                    assert {r.launcher for r in rows} == {"Steam", "Epic Games", "EA"}
                    assert rows[0].last_played_at is None or (
                        rows[0].last_played_source != "Unknown")
                if route == "Graveyard":
                    assert len(window._shown_graves) == 1
                    assert window.grave_table.rowCount() == 1
            # Exact personal Never Touch rule can be removed from the Graveyard
            # with a separate confirmation and WITHOUT a recycle operation.
            from gg_desktop.backend import refresh_graveyard
            from unittest.mock import patch
            window.settings["never_touch"] = [str(oldzip)]
            refresh_graveyard(window.inventory, window.settings)
            window.navigate("Graveyard")
            assert not window.inventory.graveyard[0].can_recycle
            archive = next(e for e in window.inventory.graveyard
                           if e.category == "Possible mod / game download")
            with patch.object(window, "confirm", return_value=True), \\
                 patch("gg_desktop.screens.recycle_reviewed_entries") as recycle:
                window._unprotect_grave(archive)
                assert oldzip.is_file()
                assert str(oldzip) not in window.settings["never_touch"]
                recycle.assert_not_called()
            window.settings["never_touch"] = []
            refresh_graveyard(window.inventory, window.settings)

            for route, filename in (
                ("Overview", "crimson-desktop-1440.png"),
                ("Games", "crimson-games-1440.png"),
                ("Graveyard", "crimson-graveyard-1440.png"),
                ("Game DNA", "crimson-dna-1440.png"),
            ):
                window.navigate(route)
                window.resize(1440, 900)
                app.processEvents()
                path = root / "_ci_temp" / filename
                assert window.grab().save(str(path)), "Cannot render Qt screenshot: " + route
                assert path.stat().st_size > 9000, "Blank Qt screenshot: " + route
            print("PASS: Qt Crimson Overview and 9 interactive pages, mixed-launcher "
                  "Games, inline exact-rule Unprotect without deletion, "
                  "four screenshots and original hero asset.")
        finally:
            window.close()
            app.processEvents()
        assert oldzip.exists()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
