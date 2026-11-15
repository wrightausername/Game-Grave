"""Crash Doctor, driven like the owner would: open it from Fix Kit, see Vortex offered when a deployment list exists,
pick a plain mod folder, Start, Stop part-way and Start again (it carries on from the answers), and let it run every test with a fake game that crashes only while the mod "Bad Mod" is
in the folder. It must name Bad Mod, put every mod back, keep Bad Mod off and turn it back on when asked, and offer mods back after Game Grave closed mid-test. Only
temporary folders are touched; no game is started."""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path
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
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication
    from core import SteamGame, default_settings
    from gg_desktop import crashdoctor_core as cd, crashdoctor_ui, fix_kit_page
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.backend import Inventory
    from gg_desktop.models import merge_games

    app = QApplication.instance() or QApplication([])

    def settle():
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()

    with tempfile.TemporaryDirectory(prefix="GG-doctor-") as temp:
        root = Path(temp)
        game_dir = root / "Steam" / "common" / "Pixel Farm"
        (game_dir / "Data").mkdir(parents=True)
        (game_dir / "PixelFarm.exe").write_bytes(b"x" * 4000)
        (game_dir / "Data" / "vortex.deployment.json").write_text(json.dumps(
            {"files": [{"relPath": "a.esp", "source": "A"}], "targetPath": str(game_dir / "Data")}))
        mods = game_dir / "Mods"
        names = ["Better Crops", "Bad Mod", "Fishing Plus", "Map HD", "UI Tweaks", "Weather"]
        for name in names:
            (mods / name).mkdir(parents=True)
            (mods / name / "manifest.json").write_text(name)
        settings = dict(default_settings(), welcome_at_startup=False)
        stack = ExitStack()
        for target, options in (
            ("gg_desktop.app.load_settings", dict(return_value=settings)),
            ("core.save_settings", {}),
            ("core.config_dir", dict(return_value=root / "Preferences")),
            ("gg_desktop.backend.save_settings", {}),
            ("gg_desktop.backend.log_event", {}),
            ("gg_desktop.crashdoctor_ui.log_event", {}),
            ("gg_desktop.ready_room_services.config_dir", dict(return_value=root / "Preferences")),
            ("gg_desktop.game_artwork.artwork_dir", dict(return_value=root / "Artwork")),
            ("gg_desktop.game_artwork._request", dict(side_effect=AssertionError("No automatic network"))),
        ):
            stack.enter_context(patch(target, **options))
        stack.enter_context(patch.object(CrimsonWindow, "error"))
        stack.enter_context(patch.object(CrimsonWindow, "info"))
        stack.enter_context(patch.object(CrimsonWindow, "confirm", lambda self, t, text, **_: True))

        # The fake game: "starts" when launched, crashes after a moment while Bad Mod is in the folder, else keeps running.
        state = SimpleNamespace(launches=0, at=0.0)

        def fake_launch(self):
            state.launches += 1
            state.at = time.time()

        def fake_running(self):
            if not state.at:
                return []
            if (mods / "Bad Mod").exists() and time.time() - state.at > 0.3:
                state.at = 0.0
                return []
            return [SimpleNamespace(name="PixelFarm.exe", pid=4242, kb=1)]

        def fake_close(self):
            state.at = 0.0
        stack.enter_context(patch.object(crashdoctor_ui.DoctorDialog, "_launch", fake_launch))
        stack.enter_context(patch.object(crashdoctor_ui.DoctorDialog, "_running", fake_running))
        stack.enter_context(patch.object(crashdoctor_ui.DoctorDialog, "_close_game", fake_close))
        stack.enter_context(patch.object(crashdoctor_ui.DoctorDialog, "_crash_recorded", lambda self: False))
        with stack:
            window = CrimsonWindow()
            window.show()
            window.resize(1280, 820)
            steam = [SteamGame("9", "Pixel Farm", str(root / "Steam"), str(game_dir), 2 * 1024 ** 3, None, "Steam")]
            window.inventory = Inventory(steam=steam, games=merge_games(steam, []), scanned_at="2026-11-15 10:00")
            settle()

            fix_kit_page.run(window, "doctor")
            settle()
            dialog = window.crash_doctor
            assert dialog.isVisible()
            methods = [dialog.method_box.itemData(i) for i in range(dialog.method_box.count())]
            assert methods == ["Vortex", "Folder"], methods
            assert dialog.launch_box.count() >= 1, "no way to start the game"
            dialog.method_box.setCurrentIndex(methods.index("Folder"))
            dialog.folder = str(mods)
            dialog.fill_launch()
            settle()
            assert "Mod folder:" in dialog.note.text()
            dialog.grab().save(str(args.output / "crash-doctor-setup.png"))

            dialog.timer.setInterval(40)
            original = crashdoctor_ui.QTimer.singleShot
            with patch.object(crashdoctor_ui, "QTimer", SimpleNamespace(singleShot=lambda ms, fn: original(30, fn))):
                dialog.start()
                assert dialog.phase != "idle", dialog.result_line.label.text()
                dialog.plan = dataclasses.replace(dialog.plan, fine_after=1)
                assert str(mods) in window.settings.get(crashdoctor_ui.ACTIVE_KEY, []), "the folder is remembered while busy"

                # Stop part-way: everything goes back, the answers are kept, Start carries on from them.
                deadline = time.time() + 60
                while len(dialog.flow.answers) < 2 and time.time() < deadline:
                    settle()
                    time.sleep(0.02)
                answered = len(dialog.flow.answers)
                assert answered >= 2, answered
                dialog.stop()
                settle()
                assert sorted(p.name for p in mods.iterdir()) == sorted(names), "Stop put everything back"
                assert "carry on" in dialog.result_line.label.text(), dialog.result_line.label.text()
                dialog.start()
                assert len(dialog.flow.answers) >= answered, "the earlier answers were not carried on"
                assert dialog.phase != "idle"
                dialog.plan = dataclasses.replace(dialog.plan, fine_after=1)
                deadline = time.time() + 120
                while dialog.phase != "idle" and time.time() < deadline:
                    settle()
                    time.sleep(0.02)
            assert dialog.phase == "idle", "Crash Doctor did not finish"
            report = dialog.result_line.label.text()
            print("Report:", report[:300], "| launches:", state.launches)
            assert "Bad Mod" in report, report
            assert 2 <= state.launches <= 12, state.launches
            assert sorted(p.name for p in mods.iterdir()) == sorted(names), list(mods.iterdir())
            assert not window.settings.get(crashdoctor_ui.ACTIVE_KEY), "the folder is forgotten when done"
            dialog.grab().save(str(args.output / "crash-doctor-found.png"))

            # Then what: keep the cause off (moved aside, nothing deleted), and turn it back on.
            assert dialog.off_button.isVisible() and "Bad Mod" in dialog.off_button.text(), dialog.off_button.text()
            dialog.off_button.click()
            settle()
            assert not (mods / "Bad Mod").exists() and (mods / cd.OFF_NAME / "Bad Mod" / "manifest.json").is_file()
            assert dialog.on_button.isVisible() and not dialog.off_button.isVisible()
            dialog.on_button.click()
            settle()
            assert sorted(p.name for p in mods.iterdir()) == sorted(names), list(mods.iterdir())

            # Game Grave closed during a test: mods wait aside, the next start offers them back.
            switcher = cd.FolderSwitcher(mods)
            switcher.apply({"Weather"})
            assert not (mods / "Bad Mod").exists()
            window.settings = dict(window.settings, **{crashdoctor_ui.ACTIVE_KEY: [str(mods)]})
            offered = []
            with patch("gg_desktop.comfort.notify", lambda w, title, text, tone, target, action=None, **_:
                       offered.append(action)):
                crashdoctor_ui.check_leftovers(window)
            assert offered and offered[0][0] == "Put back", offered
            offered[0][1]()
            assert sorted(p.name for p in mods.iterdir()) == sorted(names), list(mods.iterdir())
            dialog.reject()
            settle()
            window.close()
    print("Crash Doctor smoke passed.")


if __name__ == "__main__":
    main()
