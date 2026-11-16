"""What the assistant remembers between questions. Pure: settings in, settings out; no Qt, no files.

- Undo by asking: "undo that" plans the reverse of the newest plan's finished changes, through the existing undo paths
  (Game Optimizer's backup, the Mod Organizer 2 switch, the startup switch). What can't be undone is said plainly.
- Fix history: what was tried for each game and whether it helped, so the same fix isn't suggested twice.
- Notes: things the user asked it to remember ("I mod Skyrim with Vortex"); listed and removed only when asked.
- Scan news: one line after a scan when something important changed. It never runs anything.
Everything stays in this PC's settings file.
"""
from __future__ import annotations

import re
import time

FIX_KEY = "fix_history"            # {game name: [{"when", "tried", "result"}]}, newest last
NOTES_KEY = "assistant_notes"      # [{"when", "text"}]
MAX_FIXES_PER_GAME = 20
MAX_NOTES = 40


def _clean(text):
    return re.sub(r"[.!?]+$", "", " ".join(str(text or "").casefold().replace("’", "'").split()))


# ------------------------------------------------------------------ undo by asking
_UNDO = re.compile(r"^(please )?(undo|undo (that|it|this|those|the last (one|thing|change|plan|changes))|revert( that| it| "
                   r"those)?|put (it|that|them|those|everything) back|change (it|that|them) back|take (that|it) back|"
                   r"reverse (that|it)|undo what you (just )?did)$")


def is_undo(text):
    return bool(_UNDO.match(_clean(text)))


CANT_UNDO = {
    "clear_temp": "Deleted temp files can't be brought back (they were deleted, not recycled).",
    "close_app": "Closed apps aren't reopened for you; start them again yourself.",
    "verify_game": "A launcher's file check has nothing to undo; it only replaced damaged or missing game files.",
    "install_vcredist": "The Visual C++ runtime can be removed in Windows Settings > Apps if you really need to.",
    "install_drivers": "A driver can be rolled back in Device Manager: the device, Properties, Driver, Roll Back Driver.",
}
OPTIMIZER = ("game_mode_on", "recording_off", "power_high")


def undo_steps(chat):
    """For the newest plan in this chat with finished changes: (steps that put them back, lines for what can't be undone,
    the plan's request). (None, [], "") when nothing in this chat was changed by a plan."""
    from gg_desktop import autopilot_core as core
    for message in reversed((chat or {}).get("messages") or []):
        plan = message.get("plan") or {}
        done = [s for s in plan.get("steps", []) if s.get("status") == "done" and
                core.ACTIONS.get(s.get("key")) is not None and core.ACTIONS[s["key"]].kind == core.CHANGE]
        if not done:
            continue
        steps, notes = [], []
        for s in done:
            key, args = s["key"], dict(s.get("args") or {})
            if key in OPTIMIZER:
                if not any(x.key == "undo_optimizer" for x in steps):
                    steps.append(core.Step("undo_optimizer"))
            elif key in ("mod_off", "mod_on"):
                steps.append(core.Step("mod_on" if key == "mod_off" else "mod_off", args))
            elif key == "startup_off":
                steps.append(core.Step("startup_on", args))
            elif key == "startup_on":
                steps.append(core.Step("startup_off", args))
            elif key == "undo_optimizer":
                notes.append("Putting the Windows settings back can be done again in Toolbox > Game Optimizer.")
            elif key in CANT_UNDO:
                if CANT_UNDO[key] not in notes:
                    notes.append(CANT_UNDO[key])
        return steps, notes, str(plan.get("request", ""))
    return None, [], ""


NOTHING_TO_UNDO = ("Nothing in this chat was changed by a plan, so there's nothing to undo here. Files Game Grave moved to "
                   "the Recycle Bin can be restored in Undo Center; mod switches have Undo in Mods > My Mods.")


# ------------------------------------------------------------------ fix history
def record_fix(settings, game, tried, result="tried"):
    history = dict(settings.get(FIX_KEY) or {})
    rows = list(history.get(game) or [])[-(MAX_FIXES_PER_GAME - 1):]
    rows.append({"when": time.strftime("%Y-%m-%d"), "tried": str(tried)[:160], "result": result})
    history[game] = rows
    return dict(settings, **{FIX_KEY: history})


def mark_last(settings, game, result):
    history = dict(settings.get(FIX_KEY) or {})
    rows = [dict(r) for r in history.get(game) or []]
    when = rows[-1]["when"] if rows else ""
    for r in rows:
        if r.get("when") == when and r.get("result") == "tried":
            r["result"] = result          # every fix from that last session gets the answer
    history[game] = rows
    return dict(settings, **{FIX_KEY: history})


def tried_for(settings, game):
    return list((settings.get(FIX_KEY) or {}).get(game) or [])


def tried_line(settings, game):
    rows = tried_for(settings, game)
    if not rows:
        return ""
    words = {"fixed": "fixed it", "not_fixed": "didn't help", "tried": "no answer yet"}
    seen = []
    for r in rows[-6:]:
        bit = f"{r['tried']} ({words.get(r.get('result'), r.get('result'))}, {r['when']})"
        if bit not in seen:
            seen.append(bit)
    return f"Already tried for {game}: " + "; ".join(seen) + "."


_FIXED = re.compile(r"^(yes,? )?(it'?s|that|it) (fixed|worked|works now|is fixed)( it)?|^(fixed|it worked|works now|"
                    r"that fixed it|all good now|yes it'?s fixed)$")
_NOT_FIXED = re.compile(r"^(no,? )?(still (broken|crashing|crashes|not working|happening)|it didn'?t (help|work|fix it)|"
                        r"didn'?t (help|work|fix it)|not fixed|same problem|nope still)")


def fix_reply(text):
    """'fixed', 'not_fixed' or '' for an answer to "Did that fix it?"."""
    t = _clean(text)
    if _NOT_FIXED.match(t):
        return "not_fixed"
    if _FIXED.match(t):
        return "fixed"
    return ""


ASK_FIXED = "Did that fix {game}? Tell me and I'll remember, so I don't suggest the same thing again."


# ------------------------------------------------------------------ notes
_REMEMBER = re.compile(r"^(please )?(remember|note|keep in mind|don'?t forget)( that)?[:,]?\s+(.{3,300})$")
_RECALL = re.compile(r"^(what do you (remember|know) about me|what have you remembered|what are your notes|show (me )?"
                     r"(your|my) notes|what did i (tell|ask) you to remember)")
_FORGET = re.compile(r"^(please )?(forget|delete|remove) (that )?(note )?(.+)$")


def note_command(text):
    """('remember', note) / ('recall', '') / ('forget', what) / ('', '')."""
    t = _clean(text)
    raw = " ".join(str(text or "").split()).rstrip(".!")
    if _RECALL.match(t):
        return "recall", ""
    found = _REMEMBER.match(t)
    if found:
        start = len(raw) - len(found.group(4))
        return "remember", raw[start:].strip()
    found = _FORGET.match(t)
    if found and (found.group(4) or re.search(r"\b(that|everything|all|notes?)\b", found.group(5))):
        return "forget", found.group(5).strip()
    return "", ""


def notes(settings):
    return list(settings.get(NOTES_KEY) or [])


def add_note(settings, text):
    kept = [n for n in notes(settings) if n.get("text", "").casefold() != text.casefold()][-(MAX_NOTES - 1):]
    kept.append({"when": time.strftime("%Y-%m-%d"), "text": text[:300]})
    return dict(settings, **{NOTES_KEY: kept})


def forget(settings, what):
    """Removes the notes that match; "everything" / "all notes" removes all. Returns (settings, removed texts)."""
    current = notes(settings)
    w = _clean(what)
    if re.fullmatch(r"(everything|all|all (of )?(your |my |the )?notes|my notes|notes)", w):
        return dict(settings, **{NOTES_KEY: []}), [n["text"] for n in current]
    number = re.fullmatch(r"(?:note )?#?(\d+)", w)
    if number:
        i = int(number.group(1)) - 1
        if 0 <= i < len(current):
            return dict(settings, **{NOTES_KEY: current[:i] + current[i + 1:]}), [current[i]["text"]]
        return settings, []
    words = [x for x in re.findall(r"[a-z0-9']+", w) if x not in ("that", "the", "a", "about", "my", "i", "note")]
    gone = [n for n in current if words and all(x in n["text"].casefold() for x in words)]
    return dict(settings, **{NOTES_KEY: [n for n in current if n not in gone]}), [n["text"] for n in gone]


def notes_text(settings):
    items = notes(settings)
    if not items:
        return ""
    return "\n".join(f"- {n['text']} (noted {n['when']})" for n in items)


# ------------------------------------------------------------------ scan news
def scan_news(previous_games, games, low_drives=(), previous_mods=0, mods=0):
    """At most three short lines about what changed since the last scan that the user would want to know."""
    lines = []
    for drive in list(low_drives)[:1]:
        lines.append(f"Drive {drive} is almost full.")
    before = {g.casefold() for g in previous_games or ()}
    if before:
        new = [g for g in games if g.casefold() not in before]
        gone = [g for g in before if g not in {x.casefold() for x in games}]
        if new:
            lines.append(f"New since the last scan: {', '.join(new[:3])}" + (f" and {len(new) - 3} more" if len(new) > 3 else "")
                         + ".")
        if gone:
            lines.append(f"{len(gone)} game{'s' if len(gone) != 1 else ''} no longer installed (leftovers may be in Graveyard).")
        if previous_mods and mods > previous_mods:
            lines.append(f"{mods - previous_mods} new mod location{'s' if mods - previous_mods != 1 else ''} found.")
    return lines[:3]
