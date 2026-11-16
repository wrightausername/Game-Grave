"""Question bench for the local AI: real questions with known right answers, run through the REAL model the same way the
app runs it (lookups, plans, the answer check). Used by `local_ai_real_check.py` on the Windows CI machine.

Each case passes when the model did what a good answer needs: looked up the right thing, proposed the right job, said
the right fact, and never broke a rule. The score is printed with every miss so the prompt and lookups can be tuned.
"""
from __future__ import annotations

import time
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace

from gg_desktop import assistant_engine as engine
from gg_desktop import local_ai_prompt as prompt
from gg_desktop import local_ai_tools as lookups
from tests.test_assistant import facts
from tests.test_assistant_answers import SPECS

# (question, expectations). tool: one of these lookups was used. job: the plan holds this job. says: the answer
# contains one of these words. never: the answer contains none of these.
CASES = (
    ("how many games do i have", {"says": ("4", "four")}),
    ("what's my biggest game", {"says": ("Starfield",)}),
    ("biggets game on my pc?", {"says": ("Starfield",)}),
    ("how big is cyberpunk", {"says": ("70",)}),
    ("when did i last play cyber punk", {"says": ("400", "over a year", "more than a year")}),
    ("which games haven't i played in ages", {"says": ("Cyberpunk",)}),
    ("which game should i uninstall to make room", {"says": ("Cyberpunk", "Starfield"), "never": ("safe to delete",)}),
    ("is hades modded", {"tool": ("look_up_game", "game_mods")}),
    ("what mods do i have for cyberpunk", {"tool": ("game_mods",), "says": ("SkyUI",)}),
    ("cyberpunk keeps crashing, why", {"tool": ("game_crashes",), "says": ("NVIDIA", "graphics driver", "driver")}),
    ("my game crashes on startup what do i do", {"tool": ("known_fixes", "game_crashes", "app_help")}),
    ("Cyberpunk won't launch", {"tool": ("game_crashes", "known_fixes", "runtimes", "look_up_game")}),
    ("what graphics card do i have", {"tool": ("pc_status",), "says": ("RTX", "NVIDIA", "GeForce")}),
    ("how much ram do i have", {"tool": ("pc_status",), "says": ("32", "16")}),
    ("is my ram running at full speed", {"tool": ("pc_status",)}),
    ("how much space is left on my c drive", {"tool": ("pc_status",), "says": ("GB",)}),
    ("can i fit a 100 gb game", {"tool": ("pc_status",)}),
    ("what's eating my storage", {"says": ("Starfield", "GB")}),
    ("what starts with windows on my pc", {"tool": ("startup_apps",), "says": ("Spotify",)}),
    ("is discord open right now", {"tool": ("open_apps",), "says": ("Discord", "yes", "Yes")}),
    ("do i have the visual c++ runtime", {"tool": ("runtimes",)}),
    ("what does 0xc0000005 mean", {"tool": ("explain_error",), "says": ("access violation", "memory")}),
    ("the program can't start because MSVCP140.dll is missing", {"tool": ("explain_error",), "says": ("Visual C++",)}),
    ("i got DXGI_ERROR_DEVICE_HUNG in starfield", {"tool": ("explain_error",), "says": ("driver", "graphics")}),
    ("my screen goes black when i launch a game", {"tool": ("known_fixes",)}),
    ("game stutters a lot", {"tool": ("known_fixes", "app_help", "pc_status")}),
    ("my controller isn't detected", {"tool": ("known_fixes",)}),
    ("i lost my save in hades", {"tool": ("known_fixes", "look_up_game", "app_help")}),
    ("mods aren't loading in skyrim", {"tool": ("known_fixes", "app_help")}),
    ("how do i back up a game", {"tool": ("app_help",), "says": ("Resurrection Kit",)}),
    ("how do i find which mod is crashing my game", {"tool": ("app_help", "known_fixes"), "says": ("Crash Doctor",)}),
    ("how do i restore something game grave deleted", {"tool": ("app_help", "tab_help"), "says": ("Undo Center",)}),
    ("where do i turn off startup apps", {"says": ("Drivers & Startup", "Hardware")}),
    ("what does the graveyard tab do", {"tool": ("tab_help", "app_help"), "says": ("leftover", "Leftover")}),
    ("what's in the toolbox", {"tool": ("tab_help", "app_help")}),
    ("how do i share my mod list with a friend", {"says": ("Squad Sync",)}),
    ("what tab am i on", {"tool": ("game_grave_state",), "says": ("Games",)}),
    ("is automation on", {"tool": ("game_grave_state",)}),
    ("what did game grave do recently", {"tool": ("recent_activity",)}),
    ("clean up my temp files", {"job": ("clean_temp_files",)}),
    ("can you tidy up the junk on my pc", {"job": ("clean_temp_files",)}),
    ("get my pc ready to play", {"job": ("get_ready_to_play", "game_mode_on")}),
    ("turn on game mode", {"job": ("game_mode_on",)}),
    ("turn off skyui", {"job": ("mod_off",)}),
    ("close discord", {"job": ("close_app",)}),
    ("stop spotify starting with windows", {"job": ("stop_startup_app",)}),
    ("check my drivers", {"job": ("check_drivers", "install_driver_updates")}),
    ("update all my drivers", {"job": ("install_driver_updates",)}),
    ("fix cyberpunk", {"job": ("fix_game",)}),
    ("scan for leftovers", {"job": ("scan_leftovers",)}),
    ("rescan my games", {"job": ("scan_games",)}),
    ("put my windows settings back", {"job": ("undo_windows_settings",)}),
    ("is there a newer game grave", {"job": ("check_game_grave_update",)}),
    ("can i delete my old screenshots", {"never": ("safe to delete", "safe to remove")}),
    ("is it safe to delete shader cache", {"never": ("safe to delete", "safe to remove")}),
    ("delete starfield for me", {"never": ("I deleted", "I've deleted", "I have deleted", "I uninstalled")}),
    ("what is a shader cache", {"says": ("shader",)}),
    ("how does load order work", {"says": ("order",)}),
    ("why does skyrim need skse", {"says": ("script extender", "SKSE")}),
    ("hi", {"never": ("safe to delete",)}),
)


def context():
    f = replace(facts(), hardware=SPECS)
    crash = SimpleNamespace(when=datetime(2026, 11, 10, 21, 5), exe="Cyberpunk2077.exe", module="nvwgf2umx.dll",
                            code="c0000005", offset="0x1")
    return SimpleNamespace(
        facts=f, settings={"autopilot_on": True, "never_touch": []},
        mo2_profiles=lambda: [("Cyberpunk 2077", "Default", "C:\\MO2\\profiles\\Default",
                               [("SkyUI", True, "SkyUI"), ("Old Patch", False, "Old Patch")])],
        game_crashes=lambda game: [crash, crash, crash] if "Cyberpunk" in game.name else [],
        list_processes=lambda: [SimpleNamespace(name="Discord.exe", pid=4, kb=400_000),
                                SimpleNamespace(name="chrome.exe", pid=5, kb=900_000)],
        read_startup=lambda: [SimpleNamespace(name="Spotify", enabled=True, company="Spotify AB", scope="user",
                                              exists=True)],
        read_runtimes=lambda: (True, True, False), screen={"tab": "Games", "selected": ""})


def judge(expect, result, text):
    called = {c for c in getattr(result, "called", ())}
    jobs = {str(j.get("job", "")) if isinstance(j, dict) else str(j) for j in (result.get("jobs") or [])}
    misses = []
    if "tool" in expect and not called & set(expect["tool"]):
        misses.append(f"expected a lookup {expect['tool']}, used {sorted(called) or 'none'}")
    if "job" in expect and not jobs & set(expect["job"]):
        misses.append(f"expected a plan with {expect['job']}, got {sorted(jobs) or 'no plan'}")
    if "says" in expect and result.get("jobs") is None and not any(w.casefold() in text.casefold() for w in expect["says"]):
        misses.append(f"expected one of {expect['says']} in the answer")
    for word in expect.get("never", ()):
        if word.casefold() in text.casefold():
            misses.append(f"said '{word}'")
    return misses


def run(server, think=False, budget_s=35 * 60, cases=CASES, log=print):
    """Ask every case (until the time budget runs out). Returns (passed, asked, misses)."""
    ctx = context()
    passed, asked, misses = 0, 0, []
    started = time.monotonic()
    for question, expect in cases:
        if time.monotonic() - started > budget_s:
            log(f"(time budget reached after {asked} questions)")
            break
        asked += 1
        base = engine.answer(question, ctx.facts)
        messages = prompt.build_messages(question, base, ctx.facts, think=think, tools=True, screen=ctx.screen)
        called = []

        def chat(msgs, tools):
            reply = server.chat_message(msgs, tools, max_tokens=1600 if think else 500, timeout=600)
            called.extend(name for _cid, name, _a in lookups.calls_in(reply))
            return reply
        t = time.monotonic()
        try:
            result = lookups.converse(chat, messages, ctx, question=question)
            called.extend(result.get("looked") or [])
        except Exception as exc:          # one slow or broken answer must not end the bench
            misses.append((question, [f"error: {exc}"]))
            log(f"  ERROR {question}: {exc}")
            continue
        text = prompt.clean_reply(result["text"]) if result["text"] else ""
        if result["text"] and not text:
            text = "[blocked by the rules]"
        result = dict(result)
        holder = SimpleNamespace(called=called)
        holder.get = result.get
        wrong = judge(expect, holder, text)
        if result.get("jobs") is None and text and lookups.problems(text, ctx.facts, result["results"]):
            wrong.append("said something the data doesn't back up: " +
                         "; ".join(lookups.problems(text, ctx.facts, result["results"])))
        shown = text[:160].replace("\n", " ") if result.get("jobs") is None else f"PLAN {result['jobs']}"
        log(f"  {'ok ' if not wrong else 'MISS'} ({time.monotonic() - t:.0f}s) {question} -> {shown}"
            + (f"  [{'; '.join(wrong)}]" if wrong else ""))
        if wrong:
            misses.append((question, wrong))
        else:
            passed += 1
    return passed, asked, misses
