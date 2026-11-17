"""Guided troubleshooting for the AI Assistant: one fix at a time, then "Did that work?". Pure: no Qt, no files.

A session lives on the assistant message that showed the step, so it is only answered while it is the newest message in
the chat. Steps come from the general known fixes in `local_ai_knowledge.PROBLEMS`; each step that Game Grave can do or
open gets a button that asks the assistant for it (a plan still waits for Run all, opening changes nothing).
"""
from __future__ import annotations

import re

from gg_desktop import local_ai_knowledge as kb

START = re.compile(r"\b(help me (fix|troubleshoot|sort out)|step by step|walk me through (fixing|it)|troubleshoot|"
                   r"guide me|one (step|fix) at a time)\b", re.I)
YES = re.compile(r"^\s*(yes|yep|yeah|ya|it worked|that worked|worked|fixed|it'?s fixed|all good|solved)\b", re.I)
NO = re.compile(r"^\s*(no|nope|nah|didn'?t|did not|still|next|not fixed|no luck|same)\b", re.I)
SKIP = re.compile(r"^\s*(skip|can'?t do that|already did|already tried)\b", re.I)
STOP = re.compile(r"^\s*(stop|cancel|quit|end|never ?mind|forget it)\b", re.I)

LABELS = {
    "crash_on_start": "It won't start", "crash_midgame": "It crashes while playing", "stutter": "It stutters or lags",
    "mods_not_loading": "Mods aren't working",
}

# Step text -> what the button asks (the assistant plans or opens it). {game} is filled in when known.
ACTIONS = (
    ("Check the usual fixes", "Check it for me", "fix {game}"),
    ("> Verify", "Verify it for me", "fix {game}"),
    ("Drivers & Startup", "Check my drivers", "check my drivers"),
    ("Make it run better", "Open Games", "open games"),
    ("Game Optimizer", "Get my PC ready", "get my PC ready to play"),
    ("Memory Optimizer", "Open Memory Optimizer", "open memory optimizer"),
    ("Black Box", "Open Black Box", "open black box"),
    ("Crash Doctor", "Open Crash Doctor", "open crash doctor"),
    ("Mod Doctor", "Open My Mods", "open my mods"),
    ("Hardware > Your PC", "Show my memory speed", "what speed is my memory running at"),
    ("Close overlays", "Which overlays are open?", "which overlays are open"),
)


def starts(text):
    """A request to be walked through a fix ("help me fix Hades", "troubleshoot my game step by step"). A walkthrough
    of a tool ("walk me through mod bisect", "explain it step by step") is not one."""
    t = text or ""
    return bool(START.search(t)) and bool(problem_of(t) or re.search(r"\b(fix|troubleshoot|broken)\b", t, re.I))


def problem_of(text):
    low = f" {(text or '').casefold()} "
    for key, (words, _steps) in kb.PROBLEMS.items():
        if any(w in low for w in words):
            return key
    return ""


def game_in(text, games):
    low = (text or "").casefold()
    return next((g for g in sorted(games, key=len, reverse=True) if len(g) >= 3 and g.casefold() in low), "")


def steps_for(problem):
    entry = kb.PROBLEMS.get(problem)
    return [s.replace("GG: ", "In Game Grave: ") for s in entry[1]] if entry else []


def begin(text, games=()):
    """A new session, or one that first asks what is wrong."""
    return {"problem": problem_of(text), "game": game_in(text, games), "at": 0, "tried": []}


def ask_problem(session):
    """(body, buttons) asking what is happening, when the first message didn't say."""
    who = session["game"] or "the game"
    body = f"Let's fix it together, one step at a time. What's happening with {who}?"
    suffix = f" with {session['game']}" if session["game"] else ""
    buttons = tuple((label, f"q:help me fix it: {label.casefold()}{suffix}") for label in LABELS.values())
    return body, buttons


def step_view(session):
    """(body, buttons) for the current step, or None when every step was tried."""
    steps = steps_for(session["problem"])
    at = session["at"]
    if at >= len(steps):
        return None
    step = steps[at]
    game = session["game"]
    head = f"Step {at + 1} of {len(steps)}" + (f" for {game}" if game else "")
    body = f"{head}:\n{step}\n\nTry it, then tell me: did that work?"
    buttons = []
    for marker, caption, ask in ACTIONS:
        if marker in step and ("{game}" not in ask or game):
            buttons.append((caption, "q:" + ask.format(game=game)))
            break
    buttons += [("Yes, it's fixed", "q:yes it worked"), ("No, next step", "q:no, next step"),
                ("Skip this one", "q:skip"), ("Stop", "q:stop")]
    return body, tuple(buttons)


def reply(session, text):
    """What an answer to a step means: "fixed", "next", "skip", "stop", or "" (not an answer; the chat goes on)."""
    if STOP.search(text or ""):
        return "stop"
    if SKIP.search(text or ""):
        return "skip"
    if YES.search(text or ""):
        return "fixed"
    if NO.search(text or ""):
        return "next"
    return ""


def advance(session, verdict):
    """The session after an answer."""
    s = dict(session, tried=list(session.get("tried") or []))
    steps = steps_for(s["problem"])
    if verdict == "next" and s["at"] < len(steps):
        s["tried"].append(steps[s["at"]])
    if verdict in ("next", "skip"):
        s["at"] += 1
    return s


def done_view(session):
    """(body, buttons) once every step was tried and it still isn't fixed."""
    game = session["game"] or "the game"
    body = (f"That's every usual fix for this. Since {game} still isn't right, the next best moves are: "
            "find the exact mod with Crash Doctor if it's modded, look the exact error up online, or ask the game's "
            "support with the details. Copy diagnostics on the bell gives them your PC's details.")
    return body, (("Open Crash Doctor", "q:open crash doctor"), ("Open Fix Kit", "Fix Kit"))
