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

    log, closed, cleaned, applied, switched, opened = [], set(), [], [], [], []
    procs = [SimpleNamespace(name="chrome.exe", pid=10, kb=900_000), SimpleNamespace(name="Discord.exe", pid=12, kb=400_000),
             SimpleNamespace(name="steam.exe", pid=14, kb=700_000)]

    opened_urls, vc_runs = [], []

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
            log=lambda details, result: log.append((details, result)), mo2_profiles=lambda: [],
            set_mod=lambda folder, name, on: switched.append((folder, name, on)), cache={},
            games=lambda: [SimpleNamespace(name="Elden Ring", launcher="Steam", app_id="1245620",
                                           install_path="C:\\Steam\\common\\ELDEN RING")],
            game_crashes=lambda game: [], read_runtimes=lambda: (True, False, True),
            open_url=lambda url: opened_urls.append(url), install_vcredist=lambda: vc_runs.append(1) or 0)

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
            ("gg_desktop.autopilot_run.mo2_profiles", dict(return_value=[
                ("Skyrim Special Edition", "Default", "C:\\MO2\\profiles\\Default",
                 [("SkyUI_5_2", True, "SkyUI"), ("USSEP", True, "Unofficial Skyrim Special Edition Patch")])])),
            ("gg_desktop.tools_actions.run_action", dict(side_effect=lambda window, key: opened.append(key))),
            ("gg_desktop.autopilot_ui._screen_scan", dict(side_effect=lambda window, key: (
                lambda: opened.append(key), lambda: False, lambda: "12 leftover items found. See Graveyard."))),
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
            assert "Turn on and plan it" in [b.text() for b in window.assistant_scroll.widget().findChildren(QPushButton)]
            ask(window, "proceed")       # a typed follow-up does what the button does: turn on, then plan the request
            assert "proceed" in transcript(window)
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
            ask(window, "yes go ahead")  # "yes" presses Run all; its one confirmation still comes first
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
            # "Undo that" plans the way back through the existing undo paths; nothing changes until Run all.
            ask(window, "undo that")
            undo = list(ui.state_of(window).plans.values())[-1]
            assert [s.key for s in undo.steps] == ["undo_optimizer"], [s.key for s in undo.steps]
            assert "Closed apps aren't reopened" in transcript(window), transcript(window)[-400:]
            if any(b.text() == "Cancel" and b.isVisible() for b in window.assistant_scroll.widget().findChildren(QPushButton)):
                press(window, "Cancel")
            # Notes: kept on this PC, listed and forgotten only when asked.
            ask(window, "remember that I mod Skyrim with Vortex")
            assert "Noted" in transcript(window) and window.settings["assistant_notes"][-1]["text"] == "I mod Skyrim with Vortex"
            ask(window, "what do you remember about me")
            assert "1. I mod Skyrim with Vortex" in transcript(window)
            ask(window, "forget note 1")
            assert window.settings["assistant_notes"] == [] and "Forgotten" in transcript(window)

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
            # Ask how to use a tool: a walkthrough with Do it for me and Open buttons.
            window.navigate("AI Assistant")
            settle()
            ask(window, "how do I clean temp files")
            assert "Windows Cleanup" in transcript(window) and "Check the list, then press Delete" in transcript(window)
            labels = [b.text() for b in window.assistant_scroll.widget().findChildren(QPushButton) if b.isVisible()]
            assert "Do it for me" in labels and "Open Windows Cleanup" in labels, labels
            press(window, "Open Windows Cleanup")
            wait_for(lambda: opened and opened[-1] == "windows_cleanup", "the tool to open")
            before = len(ui.state_of(window).plans)
            press(window, "Do it for me")
            wait_for(lambda: len(ui.state_of(window).plans) > before, "the plan from Do it for me")
            plan = list(ui.state_of(window).plans.values())[-1]
            assert [s.key for s in plan.steps] == ["check_temp", "clear_temp"]
            assert window.grab().save(str(args.output / "assistant-autopilot-howto.png"))

            # "Open the hash checker" opens the tool itself.
            ask(window, "open the hash checker")
            wait_for(lambda: opened[-1] == "hash", "the hash checker to open")
            assert "Hash Checker" in transcript(window) and "opened it for you" in transcript(window)

            # Turn a mod off by name: found in the Mod Organizer 2 profile, switched after Run all, never the wrong mod.
            ask(window, "turn off skyui")
            plan = list(ui.state_of(window).plans.values())[-1]
            wait_for(lambda: plan.steps[0].status == "done", "the mod lookup")
            assert [s.title for s in plan.steps] == ["Find the mods you named", "Turn off SkyUI"], [s.title for s in plan.steps]
            confirm.reset_mock()
            press(window, "Run all")
            assert "modlist.txt" in confirm.call_args[0][1]
            wait_for(lambda: plan.steps[1].status == "done", "the mod switch")
            assert switched == [("C:\\MO2\\profiles\\Default", "SkyUI_5_2", False)], switched
            assert window.grab().save(str(args.output / "assistant-autopilot-mod.png"))

            # Fix my game: the usual non-mod causes, then Steam's verify and Microsoft's runtime after Run all.
            ask(window, "Elden Ring keeps crashing, fix it")
            plan = list(ui.state_of(window).plans.values())[-1]
            wait_for(lambda: plan.steps[0].status == "done", "the game checks")
            keys = [s.key for s in plan.steps]
            assert keys[0] == "check_game_fix" and "verify_game" in keys and "install_vcredist" in keys, keys
            assert "32-bit" in plan.steps[0].result, plan.steps[0].result
            assert window.grab().save(str(args.output / "assistant-autopilot-fixgame.png"))
            confirm.reset_mock()
            press(window, "Run all")
            assert "steam://validate/1245620" in confirm.call_args[0][1]
            wait_for(lambda: all(s.status in ("done", "skipped", "problem") for s in plan.steps if s.ticked), "the fixes")
            assert opened_urls == ["steam://validate/1245620"] and vc_runs == [1], (opened_urls, vc_runs)
            # It remembers what was tried and asks whether it helped; "still broken" is remembered too.
            wait_for(lambda: "Did that fix Elden Ring?" in transcript(window), "the did-it-help question")
            assert window.settings["fix_history"]["Elden Ring"][-1]["result"] == "tried"
            press(window, "No, still broken")
            assert window.settings["fix_history"]["Elden Ring"][-1]["result"] == "not_fixed"
            assert "didn't help" in transcript(window) and "Next things to try" in transcript(window)

            # The tabs' own scans run from a plan too.
            ask(window, "scan for leftovers")
            plan = list(ui.state_of(window).plans.values())[-1]
            wait_for(lambda: plan.steps[0].status == "done", "the leftover scan")
            assert "scan_leftovers" in opened and plan.steps[0].result.startswith("12 leftover items")

            # Pop the chat out: it stays beside any tab, shares the chat, and knows which tab you're on.
            from gg_desktop import assistant_popout
            window.navigate("Games")
            settle()
            assert window.assistant_popout_button.isVisible()
            window.assistant_popout_button.click()
            settle()
            pop = assistant_popout.current(window)
            assert pop is not None and pop.isVisible() and pop.pin.isChecked(), "Opens, kept on top by default"
            assert "You're on: Games" in pop.where.text(), pop.where.text()
            pop_text = lambda: " ".join(l.text() for l in pop.scroll.widget().findChildren(QLabel))
            pop.input.setText("how do I use this tab")
            QTest.keyClick(pop.input, Qt.Key_Return)
            settle()
            assert "Games shows every installed game" in pop_text(), pop_text()[-300:]
            assert window.current_route == "Games", "Asking from the pop-out never switches the tab"
            pop.input.setText("clean up temp files")
            QTest.keyClick(pop.input, Qt.Key_Return)
            plan = list(ui.state_of(window).plans.values())[-1]
            wait_for(lambda: plan.steps[0].status == "done", "the check from the pop-out")
            settle()
            runs = [b for b in pop.scroll.widget().findChildren(QPushButton) if b.text().startswith("Run all") and b.isVisible()]
            assert runs, "The plan card is in the pop-out"
            before = len(cleaned)
            runs[-1].click()
            wait_for(lambda: plan.steps[1].status == "done", "the change from the pop-out")
            assert len(cleaned) == before + 1
            wait_for(lambda: "All done" in pop_text(), "the result in the pop-out")
            window.navigate("Hardware")
            settle()
            assert "You're on: Hardware" in pop.where.text()
            pop.resize(480, 700)
            assert pop.grab().save(str(args.output / "assistant-popout.png"))
            assert window.grab().save(str(args.output / "assistant-popout-beside-hardware.png"))
            pop.pin.click()
            settle()
            assert saved[-1]["assistant_popout_on_top"] is False
            pop.close()
            settle()
            assert saved[-1].get("assistant_popout_geometry"), "Where it was is remembered"
            assert assistant_popout.current(window) is None
            assistant_popout.toggle(window)
            settle()
            assert assistant_popout.current(window) is not None and not assistant_popout.current(window).pin.isChecked()
            assistant_popout.toggle(window)
            settle()
            window.navigate("AI Assistant")
            settle()

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
