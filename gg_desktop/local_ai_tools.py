"""Lookups the local AI can ask for before it answers, and the plans it may propose. No Qt.

Every lookup reads only. The outside reads (crash records, open apps, startup list, runtimes, Mod Organizer 2 profiles)
come through `ctx`, so tests use stand-ins and nothing here touches the PC by itself. The one thing the model can ask for
that is not a read is `make_plan`, and that only builds a plan from Game Grave's own automation jobs: it still waits for
the owner's one OK (Run all), exactly like a plan typed in the chat.
"""
from __future__ import annotations

import difflib
import json
import re
from datetime import datetime

MAX_RESULT = 2400          # characters of one lookup result handed back to the model
MAX_CALLS = 6              # lookups per question before the model must answer


def _size(n):
    from core import human_size
    return human_size(max(0, int(n or 0)))


def _days(when, now):
    """Whole days between two times; Game Grave keeps them as Unix seconds, but datetimes work too."""
    if not when:
        return None
    try:
        gap = now - when
        seconds = gap.total_seconds() if hasattr(gap, "total_seconds") else float(gap)
        return max(0, int(seconds // 86400))
    except Exception:
        return None


def _within(path, root):
    path, root = str(path).replace("/", "\\").casefold().rstrip("\\"), str(root).replace("/", "\\").casefold().rstrip("\\")
    return bool(root) and (path == root or path.startswith(root + "\\"))


def find_game(facts, name):
    """The installed game a name means: exact, then contained, then a close spelling. None rather than a wrong guess."""
    games = list(getattr(facts, "games", ()) or ())
    want = re.sub(r"[^a-z0-9]+", " ", str(name or "").casefold()).strip()
    if not want or not games:
        return None
    flat = want.replace(" ", "")
    for g in games:
        if re.sub(r"[^a-z0-9]+", "", g.name.casefold()) == flat:
            return g
    contained = [g for g in games if flat and (flat in re.sub(r"[^a-z0-9]+", "", g.name.casefold()) or
                                               re.sub(r"[^a-z0-9]+", "", g.name.casefold()) in flat)]
    if len(contained) == 1:
        return contained[0]
    scored = sorted(((difflib.SequenceMatcher(None, flat, re.sub(r"[^a-z0-9]+", "", g.name.casefold())).ratio(), g)
                     for g in games), key=lambda t: -t[0])
    if scored and scored[0][0] >= 0.8:
        return scored[0][1]
    return None


def _no_game(facts, name):
    names = [g.name for g in getattr(facts, "games", ())][:40]
    return {"found": False, "note": f"No installed game matches '{name}'.", "installed_games": names}


# ------------------------------------------------------------------ the lookups
def look_up_game(ctx, name=""):
    f = ctx.facts
    g = find_game(f, name)
    if g is None:
        return _no_game(f, name)
    out = {"found": True, "name": g.name, "launcher": g.launcher, "install_folder": str(g.install_path),
           "drive": str(g.install_path)[:2].upper() if len(str(g.install_path)) > 1 and str(g.install_path)[1] == ":" else "",
           "reported_size": _size(g.size_bytes) if g.size_bytes is not None else "unknown",
           "last_played_days_ago": _days(g.last_played_at, f.now)}
    if getattr(g, "app_id", ""):
        out["steam_app_id"] = str(g.app_id)
    if f.on("mods"):
        mods = [m for m in f.mods if _within(m.path, g.install_path)]
        out["mod_folders_inside_install"] = [m.name for m in mods][:25]
    if f.on("storage"):
        out["save_folders"] = [str(s.path) for s in f.saves if str(getattr(s, "game", "")).casefold() == g.name.casefold()][:5]
    if f.on("captures"):
        out["captures"] = sum(1 for c in f.captures if (c.game or "").casefold() == g.name.casefold())
    return out


def game_mods(ctx, name=""):
    """The game's mods: Mod Organizer 2's selected profile (on/off, in priority order) and mod folders in the install."""
    f = ctx.facts
    g = find_game(f, name)
    if g is None:
        return _no_game(f, name)
    out = {"game": g.name, "mod_organizer_2": [], "mod_folders_inside_install": [],
           "where": "Mods > My Mods (switch mods on or off, Undo, Mod Doctor, Find the crashing mod)"}
    try:
        profiles = ctx.mo2_profiles() or []
    except Exception as exc:
        profiles, out["note"] = [], f"Mod Organizer 2 profiles couldn't be read: {exc}"
    for game, profile, _folder, mods in profiles:
        if find_game(f, game) is g or str(game).casefold() in g.name.casefold() or g.name.casefold() in str(game).casefold():
            out["mod_organizer_2"].append({"profile": profile, "on": [label for _n, on, label in mods if on][:60],
                                           "off": [label for _n, on, label in mods if not on][:40],
                                           "count": len(mods)})
    if f.on("mods"):
        out["mod_folders_inside_install"] = [m.name for m in f.mods if _within(m.path, g.install_path)][:40]
    if not out["mod_organizer_2"] and not out["mod_folders_inside_install"]:
        out["note"] = (out.get("note", "") + " No Mod Organizer 2 profile or mod folder was found for this game. Vortex "
                       "and other mod folders show in Mods > My Mods.").strip()
    return out


def game_crashes(ctx, name=""):
    f = ctx.facts
    g = find_game(f, name)
    if g is None:
        return _no_game(f, name)
    from gg_desktop import fixgame_core as fx
    try:
        crashes = list(ctx.game_crashes(g) or [])
    except Exception as exc:
        return {"game": g.name, "note": f"Windows' crash records couldn't be read: {exc}"}
    modules = {}
    for c in crashes:
        modules[c.module] = modules.get(c.module, 0) + 1
    return {"game": g.name, "crashes_recorded": len(crashes), "summary": fx.crash_summary(crashes),
            "newest": max(crashes, key=lambda c: c.when).when.strftime("%Y-%m-%d %H:%M") if crashes else None,
            "crash_location_files": [{"file": m, "times": n, "what_it_is": fx.KNOWN_MODULES.get(m.casefold(), "")}
                                     for m, n in sorted(modules.items(), key=lambda kv: -kv[1])[:6]],
            "where": "Fix Kit > Black Box (full crash report) and Check the usual fixes",
            "note": "Windows only records crashes that close the game with an error; freezes and silent exits may not be "
                    "here."}


def pc_status(ctx):
    f = ctx.facts
    specs = f.hardware
    out = {}
    if specs is None:
        return {"note": "Windows hasn't been asked for the PC's parts yet; Hardware > Your PC reads them."}
    if specs.cpu:
        out["processor"] = f"{specs.cpu.name}, {specs.cpu.cores} cores / {specs.cpu.threads} threads"
    out["graphics"] = [{"name": g.name, "driver_version": g.driver} for g in specs.gpus]
    if specs.memory:
        m = specs.memory
        out["memory"] = {"total_gb": round(m.total_gb), "type": m.kind, "sticks": f"{m.sticks} of {m.slots} slots",
                         "rated_mts": m.rated_mts, "running_mts": m.running_mts,
                         "running_slower_than_rated": bool(m.rated_mts and m.running_mts and
                                                           m.running_mts < 0.95 * m.rated_mts)}
    out["windows"] = f"{specs.os_name} {specs.os_version}".strip()
    out["drives"] = [{"drive": d.letter, "type": d.kind, "free": _size(d.free), "total": _size(d.total),
                      "free_percent": round(100 * d.free / d.total) if d.total else None} for d in specs.drives]
    out["board"], out["bios"] = specs.board, specs.bios
    return out


def space_use(ctx):
    """What takes the space: biggest games, Other Storage, old files, captures, and each drive's free space."""
    f = ctx.facts
    out = {}
    if f.on("library"):
        games = sorted((g for g in f.games if g.size_bytes), key=lambda g: -g.size_bytes)
        out["biggest_games"] = [{"name": g.name, "size": _size(g.size_bytes),
                                 "last_played_days_ago": _days(g.last_played_at, f.now)} for g in games[:8]]
        out["all_games_total"] = _size(sum(g.size_bytes for g in games))
    if f.on("storage"):
        out["other_storage_total"] = _size(sum(max(0, i.size) for i in f.storage))
        out["old_files_total"] = _size(sum(max(0, o.size) for o in f.old_files))
    if f.on("captures"):
        out["captures_total"] = _size(sum(getattr(c.record, "size", 0) or 0 for c in f.captures))
    if f.hardware is not None:
        out["drives"] = [{"drive": d.letter, "free": _size(d.free), "total": _size(d.total)} for d in f.hardware.drives]
    out["where"] = ("Graveyard (games not played lately), Other Storage > Can clear here, Old Files, Captures; everything "
                    "goes to the Recycle Bin only after you confirm")
    return out


def startup_apps(ctx):
    try:
        apps = list(ctx.read_startup() or [])
    except Exception as exc:
        return {"note": f"The startup list couldn't be read: {exc}"}
    return {"apps": [{"name": a.name, "on": a.enabled, "maker": a.company, "for": "everyone" if a.scope == "machine"
                      else "you", "program_missing": a.exists is False} for a in apps][:40],
            "where": "Hardware > Drivers & Startup (the Starts with Windows list)",
            "note": "Switching one off uses the same switch as Task Manager; the app is not removed."}


def open_apps(ctx):
    from gg_desktop import fixgame_core as fx
    try:
        procs = list(ctx.list_processes() or [])
    except Exception as exc:
        return {"note": f"The open apps couldn't be read: {exc}"}
    return {"apps": [{"name": p.name, "memory": _size(p.kb * 1024)} for p in procs[:15]],
            "overlays_open": fx.overlay_findings(p.name for p in procs)}


def runtimes(ctx):
    try:
        x64, x86, d3dx = ctx.read_runtimes()
    except Exception as exc:
        return {"note": f"Couldn't read the runtimes: {exc}"}
    return {"visual_cpp_2015_2022_x64": x64, "visual_cpp_2015_2022_x86": x86, "directx_9_extra_files": d3dx}


def game_storage(ctx, name=""):
    f = ctx.facts
    g = find_game(f, name)
    if g is None:
        return _no_game(f, name)
    key = g.name.casefold()
    app = str(getattr(g, "app_id", "") or "")
    out = {"game": g.name}
    if f.on("storage"):
        related = [i for i in f.storage if key in str(i.name).casefold() or key in str(i.path).casefold() or
                   (app and re.search(r"(^|[\\/_ ])" + re.escape(app) + r"($|[\\/_ ])", str(i.path)))]
        out["other_storage"] = [{"what": i.name, "type": i.category, "size": _size(i.size), "where": str(i.path)}
                                for i in related][:10]
        old = [o for o in f.old_files if key in str(o.path).casefold()]
        out["old_files"] = [{"file": str(o.path), "size": _size(o.size)} for o in old][:8]
    if f.on("captures"):
        shots = [c for c in f.captures if (c.game or "").casefold() == key]
        out["captures"] = {"count": len(shots), "size": _size(sum(getattr(c.record, "size", 0) or 0 for c in shots))}
    out["note"] = "Each list is reviewed in its own tab; anything removed goes to the Recycle Bin after you confirm."
    return out


def app_help(ctx, topic=""):
    """The manual: Game Grave's features that match the topic, with their full steps and where they are."""
    from gg_desktop import assistant_features as features
    words = set(re.findall(r"[a-z0-9]+", str(topic).casefold()))
    scored = []
    best = None
    try:                                          # the built-in walkthrough routing, tuned on real how-to questions
        from gg_desktop import assistant_engine as engine
        guide = engine.answer(str(topic), ctx.facts)
        if guide.intent == "feature":
            title = guide.text.split("\n", 1)[0].strip()
            best = next((f for f in features.FEATURES if f.title == title), None)
    except Exception:
        best = None
    best = best or features.find_feature(str(topic))
    if best is not None:
        scored.append((-1000, best.title, best))
    for f in features.FEATURES:
        text = " ".join((f.title, f.what, " ".join(f.keywords), " ".join(f.steps), f.tab)).casefold()
        hits = sum(1 for w in words if len(w) > 2 and re.search(r"\b" + re.escape(w), text))
        title_hits = sum(2 for w in words if len(w) > 2 and w in f.title.casefold())
        if hits or title_hits:
            scored.append((-(hits + title_hits), f.title, f))
    scored.sort(key=lambda t: (t[0], t[1]))
    picks = []
    for _s, _t, f in scored:
        if f not in picks:
            picks.append(f)
    picks = picks[:3]
    if not picks:
        return {"note": "No feature matches that. Main tabs: Overview, Ready Room, Games, Mods, Old Files, Other Storage, "
                        "Captures, Graveyard, Fix Kit, Game DNA, Hardware, Undo Center, Toolbox, AI Assistant, Settings."}
    return {"best_match": picks[0].title,
            "features": [{"name": f.title, "tab": f.tab, "what": f.what, "steps": list(f.steps), "never": f.never,
                          "where": f.where, "can_plan": f.do} for f in picks]}


def tried_before(ctx, name=""):
    """What was already tried for this game's problems and whether it helped (from earlier fix plans)."""
    from gg_desktop import assistant_memory as memory
    g = find_game(ctx.facts, name)
    game = g.name if g is not None else str(name)
    rows = memory.tried_for(ctx.settings or {}, game)
    return {"game": game, "tried": rows[-10:], "note": "Don't suggest a fix that already didn't help; say so and move on."
            if rows else "Nothing has been tried for this game through Game Grave yet."}


def known_fixes(ctx, problem="", game=""):
    from gg_desktop import local_ai_knowledge as kb
    return kb.known_fixes(problem, game)


def explain_error(ctx, text=""):
    from gg_desktop import local_ai_knowledge as kb
    return kb.explain_error(text)


def tab_help(ctx, tab=""):
    from gg_desktop import local_ai_knowledge as kb
    return kb.tab_help(tab)


def game_grave_state(ctx):
    s = ctx.settings or {}
    from gg_desktop import autopilot_core as core
    routines = s.get(core.ROUTINES_KEY) or []
    return {"tab_open_now": ctx.screen.get("tab", ""), "selected_now": ctx.screen.get("selected", ""),
            "automation_on": bool(s.get(core.SETTING)), "routines": [r.get("request", "") for r in routines][:12],
            "never_touch_rules": len(s.get("never_touch") or []), "last_scan": str(getattr(ctx.facts, "scanned_at", "")),
            "popup_notices": s.get("popup_notices", True) is not False,
            "crash_notice": s.get("crash_notice", True) is not False}


def recent_activity(ctx):
    f = ctx.facts
    if not f.on("history"):
        return {"note": "Cleanup history is turned off as a source."}
    return {"records": [{"when": str(e.recorded), "what": e.action, "item": e.name, "result": e.status}
                        for e in list(f.history)[:15]]}


# ------------------------------------------------------------------ plans the model may propose
# Each job maps onto steps of the existing automation (`autopilot_core.ACTIONS`). A job that needs a target finds it the
# same way a typed request does: its check step reads the PC and only then fills in the change.
JOBS = {
    "scan_games": "Scan the PC for games, mods, saves and leftovers",
    "scan_leftovers": "Scan for leftovers of removed games",
    "scan_other_storage": "Scan caches, logs and other game data",
    "scan_captures": "Scan screenshots and recordings",
    "clean_temp_files": "Delete Windows temp files older than 2 days (permanent)",
    "check_drivers": "Ask Windows Update for driver updates",
    "install_driver_updates": "Check, then install the driver updates Windows offers",
    "game_mode_on": "Turn on Windows Game Mode",
    "background_recording_off": "Turn off Windows background recording",
    "high_performance_power": "Switch to the High performance power plan",
    "undo_windows_settings": "Put Game Mode, recording and power plan back",
    "get_ready_to_play": "Close big apps, Game Mode on, background recording off",
    "close_app": "Close one open app (target: its name)",
    "see_memory_use": "List open apps by memory",
    "stop_startup_app": "Stop one app starting with Windows (target: its name)",
    "see_startup_apps": "List the apps that start with Windows",
    "mod_off": "Turn off one Mod Organizer 2 mod (target: the mod's name)",
    "mod_on": "Turn on one Mod Organizer 2 mod (target: the mod's name)",
    "fix_game": "Check why a game won't run, then offer the launcher's verify and runtime fixes (target: the game)",
    "check_game_grave_update": "Ask GitHub for a newer Game Grave",
}
NEEDS_TARGET = {"close_app", "stop_startup_app", "mod_off", "mod_on", "fix_game"}
VAGUE = {"mod", "mods", "organizer", "2", "the", "a", "an", "my", "all", "any", "every", "game", "games", "app", "apps",
         "it", "them", "this", "that", "one", "program", "crashing", "broken", "bad", "some"}


def plan_steps(jobs):
    """Validated automation steps for the jobs the model asked for. Unknown jobs and jobs missing a target are dropped,
    never guessed. Returns (steps, dropped words)."""
    from gg_desktop import autopilot_core as core
    steps, dropped = [], []

    def add(key, ticked=True, **args):
        if key in core.ACTIONS and not any(s.key == key and s.args == args for s in steps) and len(steps) < core.MAX_STEPS:
            step = core.Step(key, dict(args))
            step.ticked = ticked
            steps.append(step)
    for job in list(jobs or [])[:8]:
        if isinstance(job, str):
            job = {"job": job}
        if not isinstance(job, dict):
            continue
        name = str(job.get("job", "")).strip().casefold()
        target = " ".join(str(job.get("target", "") or "").split())[:80]
        if name not in JOBS:
            dropped.append(name or "?")
            continue
        if name in NEEDS_TARGET and (not target or set(re.findall(r"[a-z0-9]+", target.casefold())) <= VAGUE):
            dropped.append(name + " (no target)")      # "turn off Mod Organizer 2 mod" names nothing real
            continue
        if name == "scan_games":
            add("scan_library")
        elif name == "scan_leftovers":
            add("scan_leftovers")
        elif name == "scan_other_storage":
            add("scan_storage")
        elif name == "scan_captures":
            add("scan_captures")
        elif name == "clean_temp_files":
            add("check_temp"), add("clear_temp")
        elif name == "check_drivers":
            add("check_drivers")
        elif name == "install_driver_updates":
            add("check_drivers"), add("install_drivers")
        elif name == "game_mode_on":
            add("game_mode_on")
        elif name == "background_recording_off":
            add("recording_off")
        elif name == "high_performance_power":
            add("power_high")
        elif name == "undo_windows_settings":
            add("undo_optimizer")
        elif name == "get_ready_to_play":
            add("check_memory", mentioned="")
            add("game_mode_on"), add("recording_off"), add("power_high", ticked=False)
        elif name == "close_app":
            add("check_memory", mentioned="close " + target)
        elif name == "see_memory_use":
            add("check_memory", mentioned="")
        elif name == "stop_startup_app":
            add("check_startup", mentioned="stop " + target + " starting with windows", off=True)
        elif name == "see_startup_apps":
            add("check_startup", mentioned="", off=False)
        elif name in ("mod_off", "mod_on"):
            add("check_mods", mentioned=("turn off " if name == "mod_off" else "turn on ") + target, on=name == "mod_on")
        elif name == "fix_game":
            add("check_game_fix", mentioned="fix " + target)
            add("check_drivers")
        elif name == "check_game_grave_update":
            add("check_app_update")
    return steps, dropped


def make_plan(ctx, jobs=(), summary=""):
    """Handled by the caller (it ends the lookups); this only validates so the model hears what was kept."""
    steps, dropped = plan_steps(jobs)
    return {"planned": [s.title for s in steps], "dropped": dropped}


# ------------------------------------------------------------------ the tool list the model sees
def _fn(fname, description, **params):
    required = [k for k, v in params.items() if not v.pop("optional", False)]
    return {"type": "function", "function": {"name": fname, "description": description,
                                             "parameters": {"type": "object", "properties": params, "required": required}}}


def _s(description, optional=False):
    return {"type": "string", "description": description, "optional": optional}


def tool_specs():
    return [
        _fn("look_up_game", "One installed game: size, drive, folder, last played, its mod folders, save folders and "
            "captures.", name=_s("The game's name as the user wrote it")),
        _fn("game_mods", "A game's mods: the Mod Organizer 2 profile's mods that are on and off, and mod folders in its "
            "install folder.", name=_s("The game's name")),
        _fn("game_crashes", "Crashes Windows recorded for a game and which file each crash was in (graphics driver, "
            "DirectX, a mod's file, an overlay).", name=_s("The game's name")),
        _fn("pc_status", "This PC's parts: processor, graphics card and driver version, memory and whether it runs "
            "slower than rated, Windows version, every drive's free space."),
        _fn("space_use", "What is using the space: biggest games, caches, old files, captures and every drive's free "
            "space."),
        _fn("open_apps", "Apps open right now by memory use, and overlays that hook into games (Discord, Overwolf, "
            "RivaTuner and others)."),
        _fn("startup_apps", "Apps that start with Windows, on or off."),
        _fn("runtimes", "Whether Microsoft's Visual C++ 2015-2022 runtimes and the older DirectX 9 files are installed."),
        _fn("game_storage", "Caches, logs, old files and captures that belong to one game.", name=_s("The game's name")),
        _fn("app_help", "Game Grave's own manual: which feature does something, its steps and where it is.",
            topic=_s("What the user wants to do or the feature's name")),
        _fn("known_fixes", "Well-known fixes for a PC gaming problem (crashing, won't start, stutter, mods not loading, "
            "out of space, black screen, controller, lost saves, broken after an update), and notes for popular modded "
            "games.", problem=_s("The problem in the user's words"), game=_s("The game, if any", optional=True)),
        _fn("tried_before", "What was already tried for a game's problem through Game Grave, and whether it helped.",
            name=_s("The game's name")),
        _fn("explain_error", "What an error message, error code or DLL name usually means and the usual next step.",
            text=_s("The error text exactly as the user pasted it")),
        _fn("tab_help", "What a Game Grave tab has and which buttons are on it.", tab=_s("The tab's name")),
        _fn("game_grave_state", "Game Grave's own state: the tab open now and what is selected, automation on or off, "
            "routines, protection rules, last scan."),
        _fn("recent_activity", "Game Grave's recent cleanup and activity records."),
        {"type": "function", "function": {
            "name": "make_plan",
            "description": "When the user asks you to DO something Game Grave can do, propose a plan of these jobs. "
                           "Nothing runs until the user presses OK. Jobs: " +
                           "; ".join(f"{k}: {v}" for k, v in JOBS.items()),
            "parameters": {"type": "object", "properties": {
                "summary": {"type": "string", "description": "One plain sentence saying what the plan does"},
                "jobs": {"type": "array", "items": {"type": "object", "properties": {
                    "job": {"type": "string", "enum": list(JOBS)},
                    "target": {"type": "string", "description": "The app, mod or game, for jobs that need one"}},
                    "required": ["job"]}}},
                "required": ["jobs"]}}},
    ]


LOOKUPS = {"look_up_game": look_up_game, "game_mods": game_mods, "game_crashes": game_crashes, "pc_status": pc_status,
           "open_apps": open_apps, "startup_apps": startup_apps, "space_use": space_use, "runtimes": runtimes, "game_storage": game_storage,
           "app_help": app_help, "game_grave_state": game_grave_state, "known_fixes": known_fixes,
           "explain_error": explain_error, "tab_help": tab_help, "tried_before": tried_before, "recent_activity": recent_activity,
           "make_plan": make_plan}

CHECKED_NAMES = {"look_up_game": "Games", "game_mods": "Mods", "game_crashes": "Black Box", "pc_status": "Hardware",
                 "open_apps": "Open apps", "startup_apps": "Startup", "space_use": "Storage", "runtimes": "Runtimes", "game_storage": "Storage",
                 "app_help": "Manual", "game_grave_state": "Settings", "recent_activity": "Activity",
                 "known_fixes": "Known fixes", "explain_error": "Error guide", "tab_help": "Manual",
                 "tried_before": "Fix history"}


def run(ctx, name, arguments):
    """One lookup, as text for the model. Never raises: a failure is reported to the model as a note."""
    func = LOOKUPS.get(name)
    if func is None:
        return json.dumps({"error": f"There is no lookup called {name}."})
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments or "{}")
        except ValueError:
            arguments = {}
    if not isinstance(arguments, dict):
        arguments = {}
    allowed = func.__code__.co_varnames[1:func.__code__.co_argcount]
    kwargs = {k: v for k, v in arguments.items() if k in allowed}
    try:
        result = func(ctx, **kwargs)
    except Exception as exc:        # a lookup that fails must not end the answer
        result = {"error": f"That lookup failed: {exc}"}
    return fit(result)


def _trim(value, items, chars):
    if isinstance(value, dict):
        return {k: _trim(v, items, chars) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        kept = [_trim(v, items, chars) for v in list(value)[:items]]
        return kept + ([f"...and {len(value) - items} more"] if len(value) > items else [])
    if isinstance(value, str) and len(value) > chars:
        return value[:chars] + "…"
    return value


def fit(result, limit=None):
    """A lookup result as JSON under the size limit, shortened by keeping fewer items and shorter text, so it stays
    valid JSON the model can read."""
    limit = limit or MAX_RESULT
    text = json.dumps(result, default=str, ensure_ascii=False)
    for items, chars in ((20, 400), (10, 250), (6, 160), (3, 100)):
        if len(text) <= limit:
            return text
        text = json.dumps(_trim(result, items, chars), default=str, ensure_ascii=False)
    return text if len(text) <= limit else json.dumps({"note": "Too much to show; ask about something narrower."})


# ------------------------------------------------------------------ calls written as text
_TEXT_CALL = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)


def calls_in(message):
    """Tool calls from a chat reply: the structured ones, or Qwen's <tool_call>{...}</tool_call> written in the text."""
    calls = []
    for i, call in enumerate((message or {}).get("tool_calls") or []):
        fn = call.get("function") or {}
        calls.append((call.get("id") or f"call{i}", fn.get("name", ""), fn.get("arguments") or "{}"))
    if not calls:
        for i, raw in enumerate(_TEXT_CALL.findall(str((message or {}).get("content") or ""))):
            try:
                data = json.loads(raw)
            except ValueError:
                continue
            calls.append((f"text{i}", str(data.get("name", "")), data.get("arguments") or {}))
    return calls


def screen_line(screen):
    tab = (screen or {}).get("tab") or ""
    selected = (screen or {}).get("selected") or ""
    if not tab:
        return ""
    return f"Right now the user has the {tab} tab open" + (f" with {selected} selected." if selected else ".")


def today():
    return datetime.now().strftime("%A %d %B %Y")


# ------------------------------------------------------------------ the conversation loop (pure: chat_fn is injected)
def converse(chat_fn, messages, ctx, max_rounds=MAX_CALLS, question=None):
    """Let the model look things up, then answer. chat_fn(messages, tools) returns the reply message dict.
    Returns dict(text, jobs, summary, checked, results, looked): `jobs` is set when the model proposed a plan.
    With `question`, the lookups it obviously needs are run first (`prefetch`)."""
    first = prefetch(question, ctx) if question else []
    messages, results, checked = with_prefetch(messages, ctx, first)
    looked = [fn for fn, _args in first]
    tools = tool_specs()
    if question is not None and not _STATE.search(" ".join(str(question).casefold().split())):
        tools = [s for s in tools if s["function"]["name"] != "game_grave_state"]   # only when asked about Game Grave itself
    if question is not None:
        from gg_desktop import autopilot_core as core
        if not core.is_request(question):          # a question ("how do I...") is answered, never turned into a plan
            tools = [s for s in tools if s["function"]["name"] != "make_plan"]
    for round_no in range(max_rounds + 1):
        offer = tools if round_no < max_rounds else None       # the last round must answer in words
        reply = chat_fn(messages, offer) or {}
        calls = calls_in(reply)
        said = str(reply.get("content") or "")
        if not calls and offer is not None and round_no == 0 and _PROMISE.search(said):
            # "Let me look that up" without looking: tell it to go ahead, once.
            messages += [{"role": "assistant", "content": said},
                         {"role": "user", "content": "Go ahead: use the lookups now, then answer."}]
            continue
        if not calls or offer is None:
            text = _TEXT_CALL.sub("", str(reply.get("content") or "")).strip()
            return {"text": text, "jobs": None, "summary": "", "checked": checked, "results": results, "looked": looked}
        messages.append({"role": "assistant", "content": reply.get("content") or "",
                         "tool_calls": [{"id": cid, "type": "function",
                                         "function": {"name": name, "arguments": args if isinstance(args, str)
                                                      else json.dumps(args)}} for cid, name, args in calls]})
        for cid, name, args in calls:
            if name == "make_plan":
                data = args if isinstance(args, dict) else _json(args)
                return {"text": "", "jobs": data.get("jobs") or [], "summary": str(data.get("summary") or "")[:300],
                        "checked": checked, "results": results, "looked": looked}
            looked.append(name)
            result = run(ctx, name, args)
            results.append(result)
            label = CHECKED_NAMES.get(name)
            if label and label not in checked:
                checked.append(label)
            messages.append({"role": "tool", "tool_call_id": cid, "name": name, "content": result})
    return {"text": "", "jobs": None, "summary": "", "checked": checked, "results": results, "looked": looked}


_PROMISE = re.compile(r"\b(let me|i'?ll|i will|i'?m going to) (check|look|find|see|pull|get)\b", re.I)


def _json(text):
    try:
        data = json.loads(text or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


# ------------------------------------------------------------------ checking the answer against the data
_SIZE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(TB|GB|MB)\b", re.I)
_UNIT = {"tb": 1024 ** 4, "gb": 1024 ** 3, "mb": 1024 ** 2}
_HAS_INSTALLED = re.compile(r"\b(?i:you (?:have|'ve got|also have)) ([A-Z][A-Za-z0-9:'&\- ]{2,40}?) installed\b")


def known_sizes(facts, results=()):
    sizes = []
    for g in getattr(facts, "games", ()):
        if g.size_bytes:
            sizes.append(float(g.size_bytes))
    for group in ("mods", "storage", "old_files", "captures"):
        for item in getattr(facts, group, ()) or ():
            for attr in ("apparent_bytes", "size"):
                value = getattr(item, attr, None) or getattr(getattr(item, "record", None), attr, None)
                if isinstance(value, (int, float)) and value > 0:
                    sizes.append(float(value))
                    break
    specs = getattr(facts, "hardware", None)
    for d in getattr(specs, "drives", ()) or ():
        sizes += [float(d.free), float(d.total), float(d.total - d.free)]
    if specs is not None and getattr(specs, "memory", None):
        sizes.append(specs.memory.total_gb * 1024 ** 3)
    for text in results:
        for number, unit in _SIZE.findall(str(text)):
            sizes.append(float(number.replace(",", ".")) * _UNIT[unit.casefold()])
    return sizes


def problems(text, facts, results=()):
    """Sizes and installed games in a reply that Game Grave's data doesn't back up. Empty when it all checks out."""
    found = []
    sizes = known_sizes(facts, results)
    biggest = sorted(sizes, reverse=True)[:40]
    sums = {a + b for i, a in enumerate(biggest) for b in biggest[i + 1:]}
    total_games = sum(float(g.size_bytes) for g in getattr(facts, "games", ()) if g.size_bytes)
    pool = sizes + list(sums) + ([total_games] if total_games else [])
    for number, unit in _SIZE.findall(text or ""):
        value = float(number.replace(",", ".")) * _UNIT[unit.casefold()]
        if value < 1024 ** 3 * 0.5:          # small figures are often general advice ("a few hundred MB")
            continue
        if not any(abs(value - k) <= max(0.06 * k, 0.11 * 1024 ** 3) for k in pool):
            found.append(f"{number} {unit.upper()} doesn't match any size Game Grave has on record")
    names = [g.name.casefold() for g in getattr(facts, "games", ())]
    for title in _HAS_INSTALLED.findall(text or ""):
        t = title.strip().casefold()
        if names and not any(t in n or n in t for n in names):
            found.append(f"'{title.strip()}' isn't one of the installed games")
    return found[:5]


FIX_NOTE = ("Some of that doesn't match Game Grave's data: {problems}. Check with the lookups and answer again using only "
            "figures and games from the data. Keep the rest of your answer.")


# ------------------------------------------------------------------ lookups Game Grave runs first (small models skip them)
_PROBLEM = re.compile(r"crash|ctd|won'?t (start|launch|open|load|run|work)|doesn'?t (start|launch|open|load|run|work)|"
                      r"(not|aren'?t|isn'?t) (starting|launching|loading|working|detected|showing|saving)|not detected|"
                      r"black screen|screen (goes|went|turns) black|goes black|freez|stutter|lag|fps|choppy|error|broke|"
                      r"broken|keeps closing|closes (itself|immediately)|\bfix\b|lost (my )?saves?|save (is )?(gone|missing)|"
                      r"slow download|download(ing)? slow")
_SPACE = re.compile(r"\b(space|storage|room|full|eating|hogging|taking up|biggest|largest|free up|disk usage)\b")
_HARDWARE = re.compile(r"\b(ram|memory|graphics|gpu|video card|cpu|processor|drive|disk|space|storage|free|specs?|"
                       r"windows version|bios|xmp|expo|ssd|hdd|nvme)\b")
_MODS = re.compile(r"\bmods?\b|modded|load order|plugins?|skse|f4se|nexus|vortex|organizer")
_STARTUP = re.compile(r"start(s|ing)? (up )?with windows|startup|start-up|on boot")
_OPEN_APPS = re.compile(r"\b(open|running|background) (apps?|programs?)\b|is \w+ (open|running)|overlay|discord|overwolf|"
                        r"rivatuner|afterburner|what'?s running")
_ERROR = re.compile(r"0x[0-9a-f]{8}|\.dll\b|error code|exception|dxgi_|msvcp|vcruntime|is missing|not found|"
                    r"can'?t start because")
_HOWTO = re.compile(r"^(how (do|can|would|should) i|how to|where (do|can|is)|what does|what'?s the|what is the) |"
                    r"\bhow do i\b|\bwalk me through\b|\bwhere do i\b")
_RECENT = re.compile(r"\b(recent(ly)?|last (cleanup|change)|what did (game grave|you) (do|delete|change)|history)\b")
_STATE = re.compile(r"\b(what tab|which tab|this tab|this game|selected|automation|routines?|never touch|settings)\b")


def prefetch(question, ctx):
    """The lookups a good answer to this question needs, run before the model sees it: [(name, arguments)]. The model
    can still ask for more. Small models often answer without looking, so Game Grave looks for them."""
    q = " ".join(str(question or "").casefold().replace("’", "'").split())
    f = ctx.facts
    game = None
    for g in sorted(getattr(f, "games", ()), key=lambda g: -len(g.name)):
        if g.name.casefold() in q:
            game = g
            break
    if game is None:
        from gg_desktop import assistant_understand as understand
        game = understand.fuzzy_game(f, q)[0] or find_game(f, q) if len(q.split()) <= 3 else understand.fuzzy_game(f, q)[0]
    if game is None and ctx.screen.get("selected") and re.search(r"\b(this|it|the game|selected)\b", q):
        game = find_game(f, ctx.screen["selected"])
    name = game.name if game is not None else ""
    calls = []
    from gg_desktop import local_ai_knowledge as kb
    known_game = next((k for k in kb.KNOWN_GAMES if k in q), "")

    def add(fn, **args):
        if (fn, args) not in calls and len(calls) < 5:
            calls.append((fn, args))
    howto = bool(_HOWTO.search(q))
    if "game grave" in q and re.search(r"\b(update|newer|latest|new version|new build)\b", q):
        add("app_help", topic="Check for Updates")
    if howto:                       # "how do I ..." wants the manual first, not a diagnosis of this PC
        add("app_help", topic=str(question)[:200])
    if _ERROR.search(q):
        add("explain_error", text=str(question)[:600])
    if _PROBLEM.search(q):
        if name:
            add("game_crashes", name=name)
            from gg_desktop import assistant_memory as memory
            if memory.tried_for(ctx.settings or {}, name):
                add("tried_before", name=name)
        add("known_fixes", problem=str(question)[:200], game=name)
        if not howto and re.search(r"crash|won'?t|doesn'?t|not (start|launch|load)|closes|error|fix", q):
            add("runtimes")
            add("open_apps")
    if known_game and not name:     # a well-known game that isn't installed: general notes, not "it isn't on your PC"
        add("known_fixes", problem=str(question)[:200], game=known_game)
    if name and _MODS.search(q):
        add("game_mods", name=name)
    elif name and not calls:
        add("look_up_game", name=name)
    if re.search(r"\b(ram|memory|xmp|expo|gpu|graphics|cpu|processor)\b", q):
        add("pc_status")
    elif _SPACE.search(q):
        add("space_use")
    elif _HARDWARE.search(q) and not _MODS.search(q):
        add("pc_status")
    if _STARTUP.search(q):
        add("startup_apps")
    if _OPEN_APPS.search(q):
        add("open_apps")
    from gg_desktop import local_ai_knowledge as kb_tabs
    for tab in kb_tabs.TABS:
        if re.search(r"\b" + re.escape(tab.casefold()) + r"\b", q) and tab.casefold() not in ("games", "mods", "settings"):
            add("tab_help", tab=tab)
            break
    if _RECENT.search(q):
        add("recent_activity")
    if _STATE.search(q):
        add("game_grave_state")
    return calls


def with_prefetch(messages, ctx, calls):
    """The messages with Game Grave's own lookups already asked and answered, in the chat's tool-call form."""
    if not calls:
        return list(messages), [], []
    ids = [f"gg{i}" for i in range(len(calls))]
    out = list(messages) + [{"role": "assistant", "content": "", "tool_calls": [
        {"id": cid, "type": "function", "function": {"name": fn, "arguments": json.dumps(args)}}
        for cid, (fn, args) in zip(ids, calls)]}]
    results, checked = [], []
    for cid, (fn, args) in zip(ids, calls):
        result = run(ctx, fn, args)
        results.append(result)
        label = CHECKED_NAMES.get(fn)
        if label and label not in checked:
            checked.append(label)
        out.append({"role": "tool", "tool_call_id": cid, "name": fn, "content": result})
    return out, results, checked


# ------------------------------------------------------------------ one whole answer, as the app and the bench run it
def _shrink(messages, limit=1200):
    """The same messages with every lookup result cut short, for when the model's context ran out."""
    out = []
    for m in messages:
        if m.get("role") == "tool" and len(str(m.get("content", ""))) > limit:
            m = dict(m, content=fit(_json(m["content"]) or {"note": "cut short"}, limit))
        out.append(m)
    return out


def answer(server, question, base_answer, facts, history, ctx, think=False):
    """Ask the model with lookups, then check what it said. `server` has chat_message() and chat(). Returns the result
    dict from `converse`, with the final text (empty when it broke a rule twice) and `unchecked` problems."""
    from gg_desktop import local_ai_prompt as prompt
    from gg_desktop import assistant_memory as memory
    messages = prompt.build_messages(question, base_answer, facts, history, think=think, tools=True, screen=ctx.screen,
                                     notes=memory.notes_text(ctx.settings or {}))
    budget = dict(max_tokens=2600, timeout=420) if think else dict(max_tokens=900, timeout=240)
    shrunk = {"on": False}

    def chat_fn(msgs, tools):
        if shrunk["on"]:
            msgs = _shrink(msgs)
        try:
            return server.chat_message(msgs, tools, **budget)
        except Exception as exc:
            if "400" not in str(exc) or shrunk["on"]:
                raise
            shrunk["on"] = True                       # too long for the model's window: cut lookup results and retry
            return server.chat_message(_shrink(msgs), tools, **budget)
    result = converse(chat_fn, messages, ctx, question=question)
    if result["jobs"] is not None:
        return result
    raw = result["text"]
    if not raw.strip():
        # No words at all (the Small model sometimes stops after its lookups): ask once more for the answer itself.
        nudge = messages + [{"role": "user", "content": "Answer the question now in plain words, using what you looked "
                                                         "up. /no_think"}]
        raw = server.chat(nudge, max_tokens=700, timeout=240) or ""
        result["blank"] = not raw.strip()
    planned = prompt.plan_request(prompt.clean_reply(raw))
    if planned:
        return dict(result, jobs=[], request=planned)
    text = prompt.clean_reply(raw)
    if not text and raw.strip():
        # Broke a rule or ran out of room while thinking: ask once more, shorter, before giving up.
        retry = messages + [{"role": "assistant", "content": prompt.clean_reply(raw.replace("<think>", "")) or "…"},
                            {"role": "user", "content": prompt.RETRY_NOTE + " /no_think"}]
        text = prompt.clean_reply(server.chat(retry, max_tokens=900, timeout=240))
    wrong = problems(text, facts, result["results"]) if text else []
    if wrong:
        # Says something the data doesn't back up: show the model what and let it correct itself once.
        fix = messages + [{"role": "assistant", "content": text},
                          {"role": "user", "content": FIX_NOTE.format(problems="; ".join(wrong)) + " /no_think"}]
        again = prompt.clean_reply(server.chat(fix, max_tokens=900, timeout=240))
        still = problems(again, facts, result["results"]) if again else wrong
        text = again if again and len(still) < len(wrong) else text
        result["unchecked"] = still if again else wrong
    result["text"] = text
    return result
