"""The local AI's lookups, plans and answer check. Pure: every outside read is a stand-in."""
import json
import unittest
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace

from gg_desktop import local_ai_tools as t
from tests.test_assistant import facts
from tests.test_assistant_answers import SPECS


def ctx(**over):
    f = replace(facts(), hardware=SPECS)
    crash = SimpleNamespace(when=datetime(2026, 11, 10, 21, 5), exe="Cyberpunk2077.exe", module="nvwgf2umx.dll",
                            code="c0000005", offset="0x1")
    base = dict(facts=f, settings={"autopilot_on": True, "never_touch": ["C:\\Keep"]},
                mo2_profiles=lambda: [("Cyberpunk 2077", "Default", "C:\\MO2\\profiles\\Default",
                                       [("SkyUI", True, "SkyUI"), ("Old Patch", False, "Old Patch")])],
                game_crashes=lambda game: [crash, crash],
                list_processes=lambda: [SimpleNamespace(name="Discord.exe", pid=4, kb=400_000),
                                        SimpleNamespace(name="chrome.exe", pid=5, kb=900_000)],
                read_startup=lambda: [SimpleNamespace(name="Spotify", enabled=True, company="Spotify AB", scope="user",
                                                      exists=True)],
                read_runtimes=lambda: (True, False, True), screen={"tab": "Games", "selected": "Starfield"})
    base.update(over)
    return SimpleNamespace(**base)


class Lookups(unittest.TestCase):
    def test_game_names_are_found_loosely_but_never_guessed(self):
        f = facts()
        self.assertEqual(t.find_game(f, "cyber punk").name, "Cyberpunk 2077")
        self.assertEqual(t.find_game(f, "stafield").name, "Starfield")
        self.assertIsNone(t.find_game(f, "zelda"))
        missing = json.loads(t.run(ctx(), "look_up_game", {"name": "zelda"}))
        self.assertFalse(missing["found"])
        self.assertIn("Starfield", missing["installed_games"])

    def test_each_lookup_reads_what_it_says(self):
        c = ctx()
        game = json.loads(t.run(c, "look_up_game", '{"name": "cyberpunk"}'))
        self.assertEqual(game["reported_size"], "70.0 GB")
        mods = json.loads(t.run(c, "game_mods", {"name": "cyberpunk"}))
        self.assertEqual(mods["mod_organizer_2"][0]["on"], ["SkyUI"])
        crashes = json.loads(t.run(c, "game_crashes", {"name": "cyberpunk"}))
        self.assertEqual(crashes["crashes_recorded"], 2)
        self.assertIn("NVIDIA graphics driver", crashes["crash_location_files"][0]["what_it_is"])
        apps = json.loads(t.run(c, "open_apps", {}))
        self.assertIn("Discord", " ".join(apps["overlays_open"]))
        self.assertFalse(json.loads(t.run(c, "runtimes", {}))["visual_cpp_2015_2022_x86"])
        state = json.loads(t.run(c, "game_grave_state", {}))
        self.assertEqual((state["tab_open_now"], state["selected_now"], state["never_touch_rules"]), ("Games", "Starfield", 1))
        self.assertTrue(json.loads(t.run(c, "pc_status", {}))["drives"])
        self.assertTrue(json.loads(t.run(c, "app_help", {"topic": "find which mod crashes my game"}))["features"])

    def test_a_failing_read_is_a_note_not_a_crash(self):
        def boom(*_a):
            raise OSError("access denied")
        c = ctx(game_crashes=boom, list_processes=boom, read_startup=boom)
        for name, args in (("game_crashes", {"name": "hades"}), ("open_apps", {}), ("startup_apps", {})):
            self.assertIn("access denied", t.run(c, name, args))
        self.assertIn("no lookup called", t.run(c, "format_c", {}))
        self.assertLessEqual(len(t.run(c, "app_help", {"topic": "a " * 500})), t.MAX_RESULT + 20)


class Plans(unittest.TestCase):
    def test_only_known_jobs_become_steps(self):
        steps, dropped = t.plan_steps([{"job": "clean_temp_files"}, {"job": "mod_off", "target": "SkyUI"},
                                       {"job": "close_app"}, {"job": "format_drive"}, "game_mode_on"])
        keys = [s.key for s in steps]
        self.assertEqual(keys, ["check_temp", "clear_temp", "check_mods", "game_mode_on"])
        self.assertEqual(steps[2].args["mentioned"], "turn off SkyUI")
        self.assertEqual(dropped, ["close_app (no target)", "format_drive"])

    def test_every_job_maps_to_real_actions(self):
        from gg_desktop import autopilot_core as core
        for job in t.JOBS:
            steps, dropped = t.plan_steps([{"job": job, "target": "Discord"}])
            self.assertTrue(steps and not dropped, job)
            self.assertTrue(all(s.key in core.ACTIONS for s in steps), job)


class Loop(unittest.TestCase):
    def test_looks_up_then_answers(self):
        replies = iter([{"content": "", "tool_calls": [{"id": "1", "function": {"name": "look_up_game",
                                                                                "arguments": '{"name": "hades"}'}}]},
                        {"content": "Hades reports 15.0 GB."}])
        seen = []

        def chat(messages, tools):
            seen.append((list(messages), tools))
            return next(replies)
        out = t.converse(chat, [{"role": "user", "content": "hades?"}], ctx())
        self.assertEqual(out["text"], "Hades reports 15.0 GB.")
        self.assertEqual(out["checked"], ["Games"])
        self.assertEqual(seen[1][0][-1]["role"], "tool")

    def test_text_written_calls_work_and_plans_end_the_loop(self):
        replies = iter([{"content": '<tool_call>{"name": "make_plan", "arguments": {"jobs": [{"job": "scan_games"}],'
                                    ' "summary": "Scan."}}</tool_call>'}])
        out = t.converse(lambda m, tl: next(replies), [], ctx())
        self.assertEqual(out["jobs"], [{"job": "scan_games"}])
        self.assertEqual(out["summary"], "Scan.")

    def test_the_last_round_must_answer(self):
        call = {"content": "", "tool_calls": [{"id": "1", "function": {"name": "pc_status", "arguments": "{}"}}]}
        offers = []

        def chat(messages, tools):
            offers.append(tools)
            return call if tools else {"content": "Done looking."}
        out = t.converse(chat, [], ctx(), max_rounds=2)
        self.assertEqual(out["text"], "Done looking.")
        self.assertIsNone(offers[-1])


class Checking(unittest.TestCase):
    def test_sizes_and_games_must_match_the_data(self):
        f = facts()
        self.assertEqual(t.problems("Starfield reports 120 GB and Cyberpunk 2077 70 GB, 190 GB together.", f), [])
        self.assertTrue(t.problems("Cyberpunk 2077 takes 999 GB.", f))
        self.assertTrue(t.problems("You have Elden Ring installed.", f))
        self.assertEqual(t.problems("A shader cache is usually a few hundred MB.", f), [])
        self.assertEqual(t.problems("The lookup said 33.3 GB.", f, ['{"size": "33.3 GB"}']), [])


if __name__ == "__main__":
    unittest.main()


class Knowledge(unittest.TestCase):
    def test_known_fixes_and_errors(self):
        from gg_desktop import local_ai_knowledge as kb
        fixes = kb.known_fixes("my game won't start", "Skyrim Special Edition")
        kinds = {next(iter(k)) for k in fixes["known_fixes"]}
        self.assertEqual(kinds, {"problem", "game"})
        self.assertIn("Visual C++", kb.explain_error("MSVCP140.dll was not found")["matches"][0]["usually_means"])
        self.assertIn("32-bit", kb.explain_error("error 0xc000007b")["matches"][0]["usually_means"])
        self.assertFalse(kb.explain_error("hello there").get("matches"))
        self.assertEqual(kb.tab_help("toolbox")["tab"], "Toolbox")
        for _key, (_words, steps) in kb.PROBLEMS.items():
            for step in steps:
                self.assertNotIn("safe to", step.casefold())
        for _p, means, nxt in kb.ERRORS:
            self.assertNotIn("safe to", (means + nxt).casefold())

    def test_built_in_assistant_explains_pasted_errors(self):
        from gg_desktop import assistant_understand as u
        self.assertEqual(u.answer("The program can't start because MSVCP140.dll is missing", facts()).intent, "error")
        self.assertEqual(u.answer("my controller isnt detected", facts()).intent, "fixes")
