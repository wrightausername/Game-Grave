"""Scan results stay after Game Grave closes and opens again, with the scan time in the top bar, until the owner scans
again. Runs with a stand-in scan and a temporary settings folder, so nothing on this PC is read or changed."""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("_ci_temp"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    os.environ["GAME_GRAVE_SCAN_CACHE"] = "1"   # this check is about the cache, so it is on here
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from core import OldFile, SteamGame, default_settings
    from gg_desktop import scan_cache
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.backend import Inventory
    from gg_desktop.models import merge_games

    app = QApplication.instance() or QApplication([])

    def settle():
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()

    def wait_for(test, what, seconds=15):
        for _ in range(seconds * 50):
            settle()
            if test():
                return
            QTest.qWait(20)
        raise AssertionError("Timed out waiting for " + what)

    with tempfile.TemporaryDirectory(prefix="GG-scan-cache-") as temp:
        root = Path(temp)
        prefs = root / "Preferences"
        kept = root / "Downloads" / "old-setup.exe"
        kept.parent.mkdir(parents=True)
        kept.write_bytes(b"x" * 10)
        stamp = {"n": 0}

        def fake_scan(settings, canceled, progress=None):
            stamp["n"] += 1
            steam = [SteamGame(str(stamp["n"]), f"Game {stamp['n']}", "C:\\Steam", f"C:\\Steam\\common\\Game{stamp['n']}",
                               10 * 1024 ** 3, None, "Steam")]
            return Inventory(steam=steam, games=merge_games(steam, []), files=[OldFile(str(kept), 10, 1.0),
                                                                               OldFile(str(root / "gone.zip"), 10, 1.0)],
                             scanned_at=datetime.now().strftime("%Y-%m-%d %H:%M"))

        settings = dict(default_settings(), welcome_at_startup=False)
        stack = ExitStack()
        for target, options in (
            ("gg_desktop.app.load_settings", dict(return_value=settings)),
            ("core.config_dir", dict(return_value=prefs)),
            ("core.save_settings", {}),
            ("gg_desktop.backend.save_settings", {}),
            ("gg_desktop.backend.log_event", {}),
            ("gg_desktop.app.scan_inventory", dict(side_effect=fake_scan)),
            ("gg_desktop.ready_room_services.config_dir", dict(return_value=prefs)),
            ("gg_desktop.game_artwork.artwork_dir", dict(return_value=root / "Artwork")),
            ("gg_desktop.game_artwork._request", dict(side_effect=AssertionError("No automatic network"))),
        ):
            stack.enter_context(patch(target, **options))
        errors = stack.enter_context(patch.object(CrimsonWindow, "error"))
        stack.enter_context(patch.object(CrimsonWindow, "info"))
        with stack:
            window = CrimsonWindow()
            window.show()
            window.resize(1440, 900)
            settle()
            assert window.scan_time.text() == "Not scanned yet", window.scan_time.text()
            window.start_scan()
            wait_for(lambda: not window.scanning, "the scan")
            wait_for(lambda: scan_cache.cache_path().exists(), "the results file")
            assert window.scan_time.text().startswith("Last scan Today "), window.scan_time.text()
            assert window.grab().save(str(args.output / "scan-bar-time-overview.png"))
            window.close()
            settle()

            # Open Game Grave again: the results and their time are back without scanning.
            again = CrimsonWindow()
            again.show()
            again.resize(1440, 900)
            settle()
            assert [g.name for g in again.inventory.games] == ["Game 1"], again.inventory.games
            assert [Path(f.path).name for f in again.inventory.files] == ["old-setup.exe"], "A file gone since is dropped"
            assert again.scan_time.text().startswith("Last scan Today "), again.scan_time.text()
            again.navigate("Games")
            settle()
            assert again.scan_time.text().startswith("Last scan Today ")
            assert again.grab().save(str(args.output / "scan-bar-time-games.png"))
            again.navigate("Other Storage")
            settle()
            assert again.scan_time.text() == "Not scanned yet", "Other Storage has its own scan"
            # Only a new scan replaces them.
            again.start_scan()
            wait_for(lambda: not again.scanning, "the second scan")
            assert [g.name for g in again.inventory.games] == ["Game 2"]
            wait_for(lambda: [g.name for g in scan_cache.read_all()["inventory"][0].games] == ["Game 2"],
                     "the new results to be written")
            errors.assert_not_called()
            again.close()
            settle()
    print("PASS: scan results stay after a restart with their scan time, files gone since are dropped, and only a new "
          "scan replaces them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
