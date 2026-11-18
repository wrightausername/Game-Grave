"""Why did it crash?, driven like a person would: open it from Fix Kit, press Find out why on a game whose crash records
point at the graphics driver, see the cause, its evidence and the tests, reset the game's settings and put them back,
copy the report, and see the online lookup ask first and only send the Steam number. The PC reading is replaced by a
sample (real reading is covered by tools/realworld/crash_real.py); only temporary folders are touched."""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from contextlib import ExitStack
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("_ci_temp"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication, QPushButton
    from core import SteamGame, default_settings
    from gg_desktop import crash_investigate as ci, crash_investigate_ui as ui, fix_kit_page
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.backend import Inventory
    from gg_desktop.models import merge_games

    app = QApplication.instance() or QApplication([])

    def settle(seconds=0.2):
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            time.sleep(0.01)

    with tempfile.TemporaryDirectory(prefix="GG-investigate-") as temp:
        root = Path(temp)
        game_dir = root / "Steam" / "steamapps" / "common" / "Night City"
        game_dir.mkdir(parents=True)
        (game_dir / "NightCity.exe").write_bytes(b"MZ")
        docs = root / "Docs" / "My Games" / "Night City"
        docs.mkdir(parents=True)
        (docs / "Settings.ini").write_text("[Display]\nRayTracing=1\n")
        (docs / "Saves").mkdir()
        (docs / "Saves" / "save1.sav").write_text("save")
        settings = dict(default_settings(), welcome_at_startup=False)
        stored = dict(settings)
        now = datetime.now()
        t = now - timedelta(days=1)
        sample = ci.Sources(
            exes={"nightcity.exe"},
            app_events=[("Application Error", 1000, t, ["NightCity.exe", "1", "0", "nvwgf2umx.dll", "1", "0",
                                                         "c0000005", "0x1", "1", "2", str(game_dir / "NightCity.exe")])] * 3,
            driver_events=[(t - timedelta(days=1), "NVIDIA GeForce RTX 4070 32.0.15.6094")],
            free={"C:\\": (300 * 1024 ** 3, 1000 * 1024 ** 3)}, page_file="?:\\pagefile.sys",
            memory=(32 * 1024 ** 3, 40 * 1024 ** 3), disks=[{"FriendlyName": "SSD", "HealthStatus": "Healthy"}],
            runtimes=(True, True, True), looked=["sample"])
        sent = []
        stack = ExitStack()
        for target, options in (
            ("gg_desktop.app.load_settings", dict(return_value=settings)),
            ("core.save_settings", {}),
            ("core.config_dir", dict(return_value=root / "Preferences")),
            ("gg_desktop.crash_investigate_ui.load_settings", dict(side_effect=lambda: dict(stored))),
            ("gg_desktop.crash_investigate_ui.save_settings", dict(side_effect=lambda s: (stored.clear(), stored.update(s)))),
            ("gg_desktop.crash_investigate_ui.log_event", {}),
            ("gg_desktop.crash_investigate.read_sources", dict(side_effect=lambda game, progress=None: sample)),
            ("gg_desktop.crash_investigate.steam_news", dict(side_effect=lambda app_id: sent.append(app_id) or [
                (t - timedelta(hours=6), "Hotfix 2.31", "https://store.steampowered.com/news/app/1091500")])),
            ("gg_desktop.crash_investigate_ui.settings_files", dict(side_effect=lambda game: [docs / "Settings.ini"])),
            ("gg_desktop.game_artwork.artwork_dir", dict(return_value=root / "Artwork")),
            ("gg_desktop.game_artwork._request", dict(side_effect=AssertionError("No automatic network"))),
            ("gg_desktop.crash_investigate_ui.QDesktopServices.openUrl", {}),
        ):
            stack.enter_context(patch(target, **options))
        stack.enter_context(patch.object(CrimsonWindow, "error"))
        stack.enter_context(patch.object(CrimsonWindow, "info"))
        asked = []
        stack.enter_context(patch.object(CrimsonWindow, "confirm",
                                         lambda self, title, text, **_: asked.append((title, text)) or True))
        with stack:
            window = CrimsonWindow()
            window.show()
            window.resize(1280, 820)
            steam = [SteamGame("1091500", "Night City", str(root / "Steam"), str(game_dir), 70 * 1024 ** 3, None, "Steam")]
            window.inventory = Inventory(steam=steam, games=merge_games(steam, []), scanned_at="2026-11-18 10:00")
            settle()
            window.navigate("Fix Kit")
            settle()
            words = [b.text() for b in window.page.findChildren(QPushButton)]
            assert "Find out why" in words, words
            fix_kit_page.run(window, "investigate")
            settle()
            dialog = window.crash_investigation
            assert dialog.isVisible() and dialog.games.currentText() == "Night City"
            dialog.go.click()
            for _ in range(100):
                settle(0.05)
                if dialog.inv is not None:
                    break
            inv = dialog.inv
            assert inv is not None, dialog.result_line.text()
            assert inv.causes[0].id == "gpu_driver" and inv.settled, [c.id for c in inv.causes]
            banner = dialog.result_line.text()
            assert "graphics driver" in banner.casefold(), banner
            shown = " ".join(w.text() for w in dialog.results.findChildren(type(dialog.result_line.label)))
            assert "nvwgf2umx.dll" in shown and "started after" in shown, shown[:600]
            assert "Checked and fine" in shown
            buttons = {b.text(): b for b in dialog.results.findChildren(QPushButton)}
            assert "Open Exhume" in buttons and "Check drivers" in buttons, list(buttons)
            dialog.grab().save(str(args.output / "crash-investigate.png"))

            # Reset the game's settings: asked first, saves untouched, then put back
            dialog.run_test("reset_settings")
            assert asked and "Saves are not touched" in asked[-1][1]
            assert not (docs / "Settings.ini").exists() and (docs / "Saves" / "save1.sav").exists()
            dialog.run_test("reset_settings")
            assert (docs / "Settings.ini").exists(), "put back"

            # Online: asks first, sends only the Steam number, adds the patch as a clue
            before = len(asked)
            dialog.run_test("online")
            for _ in range(60):
                settle(0.05)
                if sent and "Latest Steam news" in dialog.result_line.text():
                    break
            assert len(asked) == before + 1 and "Only the game's Steam number" in asked[-1][1]
            assert sent == ["1091500"], sent
            assert any(c.id == "game_patch" for c in dialog.inv.causes), [c.id for c in dialog.inv.causes]
            assert stored.get(ui.ONLINE_KEY) == "yes"

            dialog.copy()
            text = QApplication.clipboard().text()
            assert "Game Grave crash investigation: Night City" in text
            dialog.close()
            window.close()
    print("PASS: Why did it crash? opens from Fix Kit, names the graphics driver with its evidence, offers the tests, "
          "resets and puts back settings without touching saves, and asks before the online lookup.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
