"""AI Assistant automation, driven like the owner would: off until switched on; a request becomes a plan; checks run
straight away; changes run only after Run all and one confirmation; routines run their checks on time and wait for an OK;
nothing runs while a game is open. Every tool is a stand-in here, so nothing on this PC changes."""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from contextlib import ExitStack
from datetime import datetime, timedelta
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
    from PySide6.QtCore import QCoreApplication, QEvent, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QCheckBox, QInputDialog, QLabel, QPushButton
    from core import default_settings
    from gg_desktop import autopilot_core as core, autopilot_ui as ui
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.backend import Inventory

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

    def transcript(window):
        return " ".join(label.text() for label in window.assistant_scroll.widget().findChildren(QLabel))

    def press(window, caption):
        found = [b for b in window.assistant_scroll.widget().findChildren(QPushButton) if b.text().startswith(caption)
                 and b.isVisible()]
        assert found, (caption, [b.text() for b in window.assistant_scroll.widget().findChildren(QPushButton)])
        found[-1].click()
        settle()

    def ask(window, text):
        window.assistant_input.setText(text)
        QTest.keyClick(window.assistant_input, Qt.Key_Return)
        settle()

    log, closed, cleaned, applied = [], set(), [], []
    procs = [SimpleNamespace(name="chrome.exe", pid=10, kb=900_000), SimpleNamespace(name="Discord.exe", pid=12, kb=400_000),
             SimpleNamespace(name="steam.exe", pid=14, kb=700_000)]

    def make_env(never_touch=()):
        return SimpleNamespace(
            reg=object(), runner=object(), backup="backup.json", never_touch=list(never_touch), size=lambda n: f"{n} B",
            sleep=lambda s: None, roots=lambda: ["C:\\Temp"],
            plan_cleanup=lambda roots, never_touch=(): SimpleNamespace(items=[1, 2, 3], total=3_000, truncated=False),
            run_cleanup=lambda items, roots: (cleaned.append(len(items)),
                                              SimpleNamespace(removed=len(items), reported_bytes=3_000, skipped=0))[1],
            list_processes=lambda runner: [p for p in procs if p.pid not in closed],
            close_processes=lambda runner, pids: closed.update(pids),
            read_optimizer=lambda reg, runner: [SimpleNamespace(key="game_mode", applied=False, current="Not set"),
                                                SimpleNamespace(key="background_recording", applied=True, current="Off"),
                                                SimpleNamespace(key="power_plan", applied=False, current="Balanced")],
            apply_optimizer=lambda reg, runner, keys, backup: (applied.extend(keys), [f"{k}: done." for k in keys])[1],
            undo_optimizer=lambda reg, runner, backup: ["Restored X."], has_backup=lambda path: True,
            search_updates=lambda: [SimpleNamespace(update_id="u1", title="NVIDIA Display driver")],
            install_updates=lambda updates, on_step=None: (True, "1 of 1 installed.", False),
            read_startup=lambda: [], set_startup=lambda app, on: None,
            check_update=lambda: ("current", "You have the newest build."),
            log=lambda details, result: log.append((details, result)), cache={})

    with tempfile.TemporaryDirectory(prefix="GG-autopilot-") as temp:
        root = Path(temp)
        settings = dict(default_settings(), assistant_enabled=True, welcome_at_startup=False)
        saved = []

        def keep(updated):
            saved.append(dict(updated))

        stack = ExitStack()
        for target, options in (
            ("gg_desktop.app.load_settings", dict(return_value=settings)),
            ("core.save_settings", dict(side_effect=keep)),
            ("gg_desktop.backend.save_settings", dict(side_effect=keep)),
            ("gg_desktop.backend.log_event", {}),
            ("gg_desktop.assistant_page.save_settings", dict(side_effect=keep)),
            ("gg_desktop.assistant_page.get_records", dict(return_value=[])),
            ("gg_desktop.assistant_page.get_activity", dict(return_value=[])),
            ("gg_desktop.reference_library.save_settings", {}),
            ("gg_desktop.ready_room_services.config_dir", dict(return_value=root / "Preferences")),
            ("gg_desktop.game_artwork.artwork_dir", dict(return_value=root / "Artwork")),
            ("gg_desktop.game_artwork._request", dict(side_effect=AssertionError("No automatic network"))),
            ("gg_desktop.local_ai_core.ai_dir", dict(side_effect=lambda base=None: Path(base) if base else root / "AI")),
            ("gg_desktop.autopilot_run.default_env", dict(side_effect=make_env)),
        ):
            stack.enter_context(patch(target, **options))
        errors = stack.enter_context(patch.object(CrimsonWindow, "error"))
        stack.enter_context(patch.object(CrimsonWindow, "info"))
        confirm = stack.enter_context(patch.object(CrimsonWindow, "confirm", return_value=True))
        stack.enter_context(patch.object(QInputDialog, "getText", return_value=("Sunday tidy", True)))
        playing = stack.enter_context(patch("gg_desktop.autopsy_ui.game_running", return_value=False))
        with stack:
            window = CrimsonWindow()
            window._sync_assistant_nav()
            window.show()
            window.resize(1440, 900)
            window.inventory = Inventory()
            assert ui.state_of(window).timer is not None and ui.state_of(window).timer.interval() == ui.TICK_MS
            window.navigate("AI Assistant")
            settle()

            # Off by default: a request shows what it would do and a button to switch on. Nothing runs.
            assert not ui.enabled(window) and not window.autopilot_switch.isChecked()
            assert "Off." in window.autopilot_status.text()
            ask(window, "clean up my temp files")
            assert "running tools is switched off" in transcript(window), transcript(window)
            assert not cleaned and not log
            press(window, "Turn on and plan it")
            assert ui.enabled(window) and window.autopilot_switch.isChecked() and saved[-1][core.SETTING] is True
            plan = list(ui.state_of(window).plans.values())[-1]
            wait_for(lambda: plan.steps[0].status == "done", "the temp-file check")
            assert plan.steps[0].result.startswith("3 old temporary files") and plan.steps[1].status == "waiting"
            assert "About 3 files" in plan.steps[1].detail and not cleaned, "A check only reads"
            settle()
            assert "Run all (1 change)" in [b.text() for b in window.assistant_scroll.widget().findChildren(QPushButton)]
            assert window.grab().save(str(args.output / "assistant-autopilot-plan.png"))

            # Run all: one confirmation naming the exact change, then the change, logged.
            confirm.reset_mock()
            press(window, "Run all")
            assert confirm.called and "no Recycle Bin" in confirm.call_args[0][1], confirm.call_args
            wait_for(lambda: plan.steps[1].status == "done", "the clean-up")
            assert cleaned == [3] and log[0][0].startswith("Delete old temporary files: Deleted 3 files")
            wait_for(lambda: "All done" in transcript(window), "the plan result")
            assert any(m.get("plan", {}).get("steps", [{}])[-1].get("status") == "done"
                       for m in saved[-1]["assistant_chats"][0]["messages"]), "The result is kept with the chat"

            # Ready to play: apps are suggested but only the one named is ticked; launchers are never listed.
            ask(window, "get my pc ready to play and close discord")
            plan = list(ui.state_of(window).plans.values())[-1]
            wait_for(lambda: plan.steps[0].status == "done", "the memory check")
            settle()
            names = {s.args.get("name"): s.ticked for s in plan.steps if s.key == "close_app"}
            assert names == {"chrome.exe": False, "Discord.exe": True}, names
            recording = next(s for s in plan.steps if s.key == "recording_off")
            assert recording.status == "skipped" and recording.result == "Already set."
            assert not next(s for s in plan.steps if s.key == "power_high").ticked
            assert window.grab().save(str(args.output / "assistant-autopilot-ready-to-play.png"))
            # The owner ticks Chrome too, then runs it.
            box = next(c for c in window.assistant_scroll.widget().findChildren(QCheckBox) if c.text() == "Close chrome.exe")
            box.setChecked(True)
            settle()
            press(window, "Run all")
            wait_for(lambda: all(s.status != "waiting" for s in plan.steps if s.ticked), "the ready-to-play plan")
            assert closed == {10, 12} and 14 not in closed and applied == ["game_mode"], (closed, applied)
            assert next(s for s in plan.steps if s.key == "power_high").status == "waiting", "Unticked steps never run"

            # A game starting stops the rest of a plan; nothing runs while it is open.
            ask(window, "clean up temp files")
            plan = list(ui.state_of(window).plans.values())[-1]
            wait_for(lambda: plan.steps[0].status == "done", "the check")
            playing.return_value = True
            before = len(cleaned)
            press(window, "Run all")
            assert len(cleaned) == before and plan.steps[1].status == "waiting"
            playing.return_value = False
            press(window, "Cancel")
            assert plan.steps[1].status == "skipped" and plan.steps[1].result == "Cancelled by you."
            assert "Cancelled. Nothing was changed." in transcript(window)

            # A schedule becomes a routine. Its checks run on time; its change waits for an OK.
            ask(window, "every sunday at 9pm clean temp files and check drivers")
            plan = list(ui.state_of(window).plans.values())[-1]
            wait_for(lambda: all(s.status != "running" for s in plan.steps), "the checks")
            assert "Every Sunday at 9:00 PM" in transcript(window)
            press(window, "Save as routine")
            routines = core.load_routines(saved[-1])
            assert [r["name"] for r in routines] == ["Sunday tidy"] and routines[0]["steps"] == [
                "check_temp", "clear_temp", "check_drivers"], routines
            assert "Sunday tidy" in [l.text() for l in window.findChildren(QLabel)]
            slot = core.next_slot(core.Schedule((6,), "21:00"), datetime.now())
            playing.return_value = True
            assert ui.tick(window, now=slot + timedelta(minutes=10)) is None, "Never while a game runs"
            playing.return_value = False
            before = len(cleaned)
            assert ui.tick(window, now=slot + timedelta(minutes=10))["name"] == "Sunday tidy"
            wait_for(lambda: ui.state_of(window).notice is not None and ui.state_of(window).notice.isVisible(), "the notice")
            notice = ui.state_of(window).notice
            words = " ".join(l.text() for l in notice.findChildren(QLabel))
            assert "1 change waiting for your OK" in words and len(cleaned) == before, words
            assert ui.tick(window, now=slot + timedelta(minutes=20)) is None, "Runs once per scheduled time"
            assert window.grab().save(str(args.output / "assistant-autopilot-routine-notice.png"))
            notice.review()
            settle()
            assert window.current_route == "AI Assistant" and window.assistant_title.text() == "Routines"
            routine_plan = list(ui.state_of(window).plans.values())[-1]
            press(window, "Run all")
            wait_for(lambda: routine_plan.steps[1].status == "done", "the routine's change")
            assert len(cleaned) == before + 1
            assert "change waiting" in core.load_routines(saved[-1])[0]["last_note"] or \
                "Deleted" in routine_plan.steps[1].result
            # Pause and delete only change the saved routine.
            ui.pause_routine(window, routines[0]["id"])
            assert core.load_routines(saved[-1])[0]["on"] is False
            ui.delete_routine(window, routines[0]["id"])
            assert core.load_routines(saved[-1]) == []
            assert window.grab().save(str(args.output / "assistant-autopilot-panel.png"))
            errors.assert_not_called()
            window.close()
            settle()
    print("PASS: AI Assistant automation: off until switched on, plans of Game Grave's own tools, checks straight away, "
          "changes only after Run all and one confirmation, routines wait for an OK, nothing while a game runs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
