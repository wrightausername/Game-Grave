"""AI Assistant automation: requests become plans of Game Grave's own tools; checks run, changes wait for Run all."""
import unittest
from datetime import datetime
from types import SimpleNamespace

from gg_desktop import autopilot_core as core, autopilot_run as run


def keys(text):
    return [s.key for s in core.wants(text)]


class AutopilotTest(unittest.TestCase):
    def test_requests_become_plans_and_questions_do_not(self):
        assert keys("get my pc ready to play") == ["check_memory", "game_mode_on", "recording_off", "power_high"]
        assert [s.ticked for s in core.wants("get my pc ready to play")] == [True, True, True, False]
        assert keys("clean up my temp files") == ["check_temp", "clear_temp"]
        assert keys("check my drivers") == ["check_drivers"]
        assert keys("update all my drivers") == ["check_drivers", "install_drivers"]
        assert keys("stop discord starting with windows") == ["check_startup"]
        assert core.wants("stop discord starting with windows")[0].args["off"] is True
        assert keys("close chrome") == ["check_memory"]
        assert keys("scan my games") == ["scan_library"]
        assert keys("turn on game mode") == ["game_mode_on"]
        assert keys("turn off background recording") == ["recording_off"]
        assert keys("undo the optimizer changes") == ["undo_optimizer"]
        assert keys("check for updates to game grave") == ["check_app_update"]
        assert keys("is there an update for game grave?") == []  # a question: the built-in answer covers it
        # Questions about data stay questions; the built-in answers handle them.
        assert keys("what can I delete to free up space?") == []
        assert keys("how much space do my temp files use?") == []
        assert keys("which drivers are old") == []
        assert keys("hello there") == []
        assert keys("Explain my last cleanup") == [] and keys("Cleanup history") == []
        assert keys("Drivers & Startup") == [] and keys("tell me about my drivers") == []
        # A polite question that asks Game Grave to do it is a request.
        assert keys("can you clean up my temp files?") == ["check_temp", "clear_temp"]


    def test_only_listed_tools_and_every_change_names_its_exact_line(self):
        for action in core.ACTIONS.values():
            assert action.kind in (core.CHECK, core.CHANGE) and action.plain and action.technical
            for words in (action.title, action.plain, action.undo):
                assert "safe" not in words.lower() and "—" not in words and "–" not in words
        plan = core.plan_for("clean up temp files and turn on game mode")
        text = core.confirmation(plan)
        assert "Delete old temporary files" in text and "no Recycle Bin" in text
        assert "AutoGameModeEnabled = 1" in text and "Undo in Toolbox" in text
        assert core.summary(plan) == "2 changes, 1 check"


    def test_close_and_startup_suggestions(self):
        procs = [SimpleNamespace(name="chrome.exe", pid=10, kb=900_000), SimpleNamespace(name="steam.exe", pid=11, kb=800_000),
                 SimpleNamespace(name="Discord.exe", pid=12, kb=400_000), SimpleNamespace(name="notepad.exe", pid=13, kb=9_000)]
        steps = core.close_steps(procs, "close discord")
        assert [(s.args["name"], s.ticked) for s in steps] == [("chrome.exe", False), ("Discord.exe", True)]
        assert all(s.args["name"] != "steam.exe" for s in core.close_steps(procs, "close steam"))  # launchers never suggested
        assert [s.args["name"] for s in core.close_steps(procs, "close notepad")] == ["chrome.exe", "Discord.exe", "notepad.exe"]
        apps = [SimpleNamespace(name="Discord", title="Discord", key="user|Run|Discord", enabled=True, locked=False,
                                company="Discord Inc.", source="Run", needs_admin=False),
                SimpleNamespace(name="Spotify", title="Spotify", key="user|Run|Spotify", enabled=True, locked=False,
                                company="Spotify AB", source="Run", needs_admin=False),
                SimpleNamespace(name="Off", title="Off", key="k", enabled=False, locked=False, company="", source="Run",
                                needs_admin=False)]
        named = core.startup_steps(apps, "stop discord starting with windows", True)
        assert [(s.args["name"], s.ticked) for s in named] == [("Discord", True)]
        unnamed = core.startup_steps(apps, "turn off startup apps", True)
        assert [(s.args["name"], s.ticked) for s in unnamed] == [("Discord", False), ("Spotify", False)]


    def test_schedules(self):
        s = core.parse_schedule("every sunday at 9pm clean temp files")
        assert s.days == (6,) and s.time == "21:00" and core.describe_schedule(s) == "Every Sunday at 9:00 PM"
        assert core.parse_schedule("every night check drivers").time == "21:00"
        assert core.parse_schedule("daily at 7:30 am").days == tuple(range(7))
        assert core.describe_schedule(core.parse_schedule("weekdays at 6 pm scan")) == "Weekdays at 6:00 PM"
        assert core.parse_schedule("on saturdays and sundays at 10am").days == (5, 6)
        assert core.parse_schedule("clean temp files") is None
        sunday_9pm = core.Schedule((6,), "21:00")
        now = datetime(2026, 11, 16, 8, 0)  # Monday morning
        assert core.last_slot(sunday_9pm, now) == datetime(2026, 11, 15, 21, 0)
        assert core.next_slot(sunday_9pm, now) == datetime(2026, 11, 22, 21, 0)
        routine = {"days": [6], "time": "21:00", "on": True, "created": datetime(2026, 11, 10).timestamp(), "last_run": 0}
        assert core.is_due(routine, now)  # missed last night while the PC was off: runs once, within a day
        assert not core.is_due(dict(routine, last_run=datetime(2026, 11, 15, 21, 5).timestamp()), now)
        assert not core.is_due(routine, datetime(2026, 11, 17, 8, 0))  # more than a day late: wait for next Sunday
        assert not core.is_due(dict(routine, on=False), now)
        assert not core.is_due(dict(routine, created=datetime(2026, 11, 16, 7).timestamp()), now)  # made after the slot


    def test_routines_keep_only_routine_steps_and_survive_bad_settings(self):
        plan = core.plan_for("every sunday at 9pm clean temp files, close chrome and check drivers")
        routine, left_out = core.routine_from_plan(plan, "Sunday tidy", datetime(2026, 11, 14, 12))
        assert routine["steps"] == ["check_temp", "clear_temp", "check_drivers"]
        assert routine["days"] == [6] and routine["time"] == "21:00"
        assert left_out == ["See which apps use the most memory"]
        settings = core.with_routines({}, [routine, {"id": "x", "steps": ["rm -rf"], "days": [1], "time": "9:00"},
                                           {"id": "y", "steps": ["close_app"], "days": [1], "time": "09:00"}, "junk"])
        loaded = core.load_routines(settings)
        assert [r["name"] for r in loaded] == ["Sunday tidy"]
        fresh = core.routine_plan(loaded[0])
        assert [s.key for s in fresh.steps] == ["check_temp", "clear_temp", "check_drivers"]
        assert "Every Sunday at 9:00 PM" in core.routine_line(loaded[0], datetime(2026, 11, 14, 12))


    def test_plan_round_trip(self):
        plan = core.plan_for("every day at 8pm clean temp files")
        plan.steps[0].status, plan.steps[0].result = "done", "12 old temporary files, 3 MB."
        again = core.plan_from_dict(core.plan_to_dict(plan))
        assert [s.key for s in again.steps] == ["check_temp", "clear_temp"] and again.steps[0].result.startswith("12")
        assert again.schedule.time == "20:00"
        assert core.plan_from_dict({"steps": [{"key": "format_c"}]}).steps == []
        assert core.plan_from_dict("junk") is None


# ------------------------------------------------------------------ executors with stand-ins
def fake_env(**over):
    log = []
    procs = [SimpleNamespace(name="chrome.exe", pid=10, kb=900_000), SimpleNamespace(name="Discord.exe", pid=12, kb=400_000)]
    closed = set()
    env = SimpleNamespace(
        reg=object(), runner=object(), backup="b.json", never_touch=[], size=lambda n: f"{n} B", sleep=lambda s: None,
        roots=lambda: ["T"],
        plan_cleanup=lambda roots, never_touch=(): SimpleNamespace(items=[1, 2, 3], total=300, truncated=False),
        run_cleanup=lambda items, roots: SimpleNamespace(removed=len(items), reported_bytes=300, skipped=0),
        list_processes=lambda runner: [p for p in procs if p.pid not in closed],
        close_processes=lambda runner, pids: closed.update(pids),
        read_optimizer=lambda reg, runner: [SimpleNamespace(key="game_mode", applied=True, current="On"),
                                            SimpleNamespace(key="background_recording", applied=False, current="On"),
                                            SimpleNamespace(key="power_plan", applied=False, current="Balanced")],
        apply_optimizer=lambda reg, runner, keys, backup: [f"{k}: done." for k in keys],
        undo_optimizer=lambda reg, runner, backup: ["Restored X."], has_backup=lambda path: False,
        search_updates=lambda: [SimpleNamespace(update_id="u1", title="NVIDIA Display")],
        install_updates=lambda updates, on_step=None: (True, "1 of 1 installed.", False),
        read_startup=lambda: [], set_startup=lambda app, on: None, check_update=lambda: ("current", "You have the newest build."),
        log=lambda details, result: log.append((details, result)), cache={})
    for k, v in over.items():
        setattr(env, k, v)
    return env, log


class AutopilotRunTest(unittest.TestCase):
    def test_prepare_runs_checks_and_fills_in_changes(self):
        env, log = fake_env()
        plan = run.prepare(core.plan_for("get my pc ready to play and clean up temp files and update my drivers"), env)
        by = {s.key: s for s in plan.steps}
        assert by["check_memory"].status == "done" and "chrome.exe" in by["check_memory"].result
        assert [s.args["name"] for s in plan.steps if s.key == "close_app"] == ["chrome.exe", "Discord.exe"]
        assert by["game_mode_on"].status == "skipped" and by["recording_off"].status == "waiting"
        assert by["power_high"].detail == "Balanced" and not by["power_high"].ticked
        assert by["check_temp"].result.startswith("3 old temporary files") and "About 3 files" in by["clear_temp"].detail
        assert by["install_drivers"].args["ids"] == ["u1"]
        assert not log, "Preparing only reads"


    def test_prepare_skips_while_a_game_runs_and_undo_without_backup(self):
        env, _ = fake_env()
        plan = run.prepare(core.plan_for("clean up temp files"), env, game_running=lambda: True)
        assert plan.steps[0].status == "skipped"
        plan = run.prepare(core.plan_for("undo the optimizer changes"), env)
        assert plan.steps[0].status == "skipped" and "nothing to put back" in plan.steps[0].result


    def test_run_changes_log_each_one(self):
        env, log = fake_env()
        step = run.run_change(core.Step("clear_temp"), env)
        assert step.status == "done" and step.result.startswith("Deleted 3 files")
        step = run.run_change(core.Step("recording_off"), env)
        assert step.status == "done" and "Undo in Toolbox" in step.result
        step = run.run_change(core.Step("close_app", {"pid": 10, "name": "chrome.exe"}), env)
        assert step.status == "done" and step.result == "Closed chrome.exe."
        step = run.run_change(core.Step("close_app", {"pid": 10, "name": "chrome.exe"}), env)
        assert step.status == "skipped"  # already closed: never touches another app that took the number
        step = run.run_change(core.Step("install_drivers", {"ids": ["u1"]}), env)
        assert step.status == "done"
        assert len(log) == 4
        broken, _ = fake_env(run_cleanup=lambda items, roots: (_ for _ in ()).throw(OSError("disk busy")))
        assert run.run_change(core.Step("clear_temp"), broken).result == "Stopped: disk busy"


    def test_outcome(self):
        plan = core.plan_for("clean up temp files")
        plan.steps[0].status = plan.steps[1].status = "done"
        assert run.outcome(plan) == ("All done: 2 steps finished.", "good")
        plan.steps[1].status = "problem"
        assert run.outcome(plan)[1] == "warn"


if __name__ == "__main__":
    unittest.main()
