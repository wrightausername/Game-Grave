"""AI Assistant automation: turn a request into a plan of Game Grave's own tools, and keep saved routines. Pure: no Qt,
no file or network access, so every rule is tested.

Owner decisions (2026-11-14): off until the owner switches it on; only tools from the fixed ACTIONS list, never a typed
command; checks (read only) run straight away; every change is listed in the plan and the whole plan runs on one press of
Run all; routines run their checks on time, but their changes wait as a notice until the owner presses OK; nothing runs
while a game is open.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import timedelta

SETTING = "autopilot_on"
ROUTINES_KEY = "autopilot_routines"
MAX_ROUTINES = 12
MAX_STEPS = 16
CATCH_UP = timedelta(hours=24)  # a routine missed while the PC was off runs once at the next start, if within a day

CHECK, CHANGE = "check", "change"
UI_CHECKS = frozenset({"scan_library", "scan_leftovers", "scan_storage", "scan_captures"})  # run by the screen itself


@dataclass(frozen=True)
class Action:
    key: str
    title: str
    kind: str              # CHECK reads only; CHANGE changes something on the PC
    plain: str             # what it does, in plain words
    technical: str         # the exact change, shown folded and in the plan's confirmation
    routine: bool = True   # can be part of a scheduled routine
    undo: str = ""         # how to put it back, when it can be


ACTIONS = {a.key: a for a in (
    Action("scan_library", "Scan my games", CHECK, "Looks through your drives for games, mods, saves and leftovers.",
           "Reads folders only. Nothing is changed."),
    Action("check_temp", "Look for old temporary files", CHECK, "Counts temporary files that have not changed for 2 days.",
           "Reads Windows' temp folders only."),
    Action("check_memory", "See which apps use the most memory", CHECK, "Lists the apps open right now, biggest first.",
           "tasklist (your own session). Reads only.", routine=False),
    Action("check_drivers", "Check for driver updates", CHECK, "Asks Windows Update which driver updates it offers this PC.",
           "Windows Update Agent search, Type='Driver', IsInstalled=0. Reads only."),
    Action("check_startup", "See what starts with Windows", CHECK, "Lists the apps that start when Windows does.",
           "Reads the Run keys, Startup folders, Store app startup tasks and sign-in tasks."),
    Action("check_app_update", "Check for a newer Game Grave", CHECK, "Asks GitHub for the newest Game Grave build.",
           "One request to the GitHub releases list. Nothing is downloaded."),
    Action("scan_leftovers", "Scan for leftovers", CHECK, "Looks in known game-related places for leftovers of removed "
           "games (Graveyard).", "Reads folders only. Nothing is changed."),
    Action("scan_storage", "Scan Other Storage", CHECK, "Finds shader caches, launcher caches, logs and other game data.",
           "Reads known locations only. Nothing is changed."),
    Action("scan_captures", "Scan captures", CHECK, "Finds your screenshots and recordings and groups them by game.",
           "Reads your capture folders only. Nothing is changed."),
    Action("check_mods", "Find the mods you named", CHECK, "Looks up the mods in your Mod Organizer 2 profiles.",
           "Reads modlist.txt in each Mod Organizer 2 profile. Nothing is changed.", routine=False),
    Action("check_game_fix", "Check why the game won't run", CHECK, "Looks for the usual causes that are not mods: crashes "
           "Windows recorded, overlays that hook into games, and missing Microsoft runtimes.",
           "Reads Black Box's crash records (Windows Application log), the open apps (tasklist), the Visual C++ runtime "
           "registry keys and System32 / SysWOW64 for d3dx9_43.dll. Nothing is changed.", routine=False),
    Action("verify_game", "Ask the launcher to check the game's files", CHANGE,
           "Steam compares every game file with the real one and downloads any that are missing or damaged. Your saves "
           "and settings are not part of it.", "Opens steam://validate/<app id>; Steam does the check.", routine=False,
           undo="Nothing to undo: Steam only replaces damaged or missing game files."),
    Action("install_vcredist", "Install Microsoft's Visual C++ runtime", CHANGE,
           "Downloads Microsoft's Visual C++ 2015-2022 runtime from Microsoft and installs it. Windows asks you to allow it.",
           "https://aka.ms/vs/17/release/vc_redist.x64.exe (Microsoft hosts only, signature checked as Microsoft), "
           "then vc_redist.x64.exe /install /passive /norestart.", routine=False,
           undo="Remove it in Windows Settings > Apps if you ever need to."),
    Action("clear_temp", "Delete old temporary files", CHANGE,
           "Deletes temporary files that have not changed for 2 days. Files in use are skipped.",
           "Permanently deletes (no Recycle Bin) files 2+ days old in Windows' temp folders, each checked again first.",
           undo="Cannot be undone."),
    Action("game_mode_on", "Turn on Game Mode", CHANGE, "Tells Windows to put the game you are playing first.",
           r"HKCU\Software\Microsoft\GameBar AutoGameModeEnabled = 1", undo="Undo in Toolbox > Game Optimizer."),
    Action("recording_off", "Turn off background recording", CHANGE, "Stops Windows recording your games in the background.",
           r"HKCU\System\GameConfigStore GameDVR_Enabled = 0; HKCU\Software\Microsoft\Windows\CurrentVersion\GameDVR "
           "AppCaptureEnabled = 0", undo="Undo in Toolbox > Game Optimizer."),
    Action("power_high", "Switch to High performance power", CHANGE,
           "Keeps the processor at full speed. Uses more electricity.",
           "powercfg /setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c", undo="Undo in Toolbox > Game Optimizer."),
    Action("undo_optimizer", "Put my Windows settings back", CHANGE,
           "Puts Game Mode, background recording and the power plan back to how they were before Game Grave changed them.",
           "Restores the values saved in game-optimizer-backup.json.", routine=False),
    Action("close_app", "Close an app", CHANGE, "Asks the app to close normally, like pressing its X.",
           "taskkill /PID <id> (no /F, nothing is forced).", routine=False),
    Action("startup_off", "Stop an app starting with Windows", CHANGE,
           "Turns the app's startup switch off, the same switch as Task Manager. The app is not removed.",
           "StartupApproved value set to off (or the Store task or scheduled task disabled).", routine=False,
           undo="Turn it back on in Hardware > Drivers & Startup."),
    Action("startup_on", "Let an app start with Windows again", CHANGE,
           "Turns the app's startup switch back on, the same switch as Task Manager.",
           "StartupApproved value set to on (or the Store task or scheduled task enabled).", routine=False,
           undo="Turn it off again in Hardware > Drivers & Startup."),
    Action("mod_off", "Turn off a mod", CHANGE, "Switches the mod off in its Mod Organizer 2 profile. The mod folder "
           "stays where it is.", "modlist.txt: the mod's line changes from + to -, after a snapshot of the profile's files.",
           routine=False, undo="Undo in Mods > My Mods."),
    Action("mod_on", "Turn on a mod", CHANGE, "Switches the mod on in its Mod Organizer 2 profile.",
           "modlist.txt: the mod's line changes from - to +, after a snapshot of the profile's files.", routine=False,
           undo="Undo in Mods > My Mods."),
    Action("install_drivers", "Install the driver updates Windows offers", CHANGE,
           "Installs the driver updates Windows Update found. Windows asks you to allow it.",
           "Windows Update Agent download and install of the listed update IDs, in a PowerShell that Windows asks to allow.",
           undo="Roll back a driver in Device Manager."),
)}

# Launchers and voice apps are never suggested for closing; the owner can still close them in Toolbox > Memory Optimizer.
NEVER_SUGGEST = frozenset(n.casefold() for n in (
    "steam.exe", "steamwebhelper.exe", "epicgameslauncher.exe", "galaxyclient.exe", "eadesktop.exe", "battle.net.exe",
    "ubisoftconnect.exe", "upc.exe", "xboxapp.exe", "gamingservices.exe", "explorer.exe", "gamegrave.exe",
    "nvcontainer.exe", "radeonsoftware.exe", "msiafterburner.exe", "rtss.exe",
))
BIG_APP_KB = 300 * 1024


@dataclass
class Step:
    key: str
    args: dict = field(default_factory=dict)
    detail: str = ""        # filled in when the plan is prepared ("About 340 files, 1.2 GB")
    ticked: bool = True
    status: str = "waiting"  # waiting, running, done, problem, skipped
    result: str = ""

    @property
    def action(self):
        return ACTIONS[self.key]

    @property
    def title(self):
        name = self.args.get("name")
        if self.key == "close_app" and name:
            return "Close " + name
        if self.key == "startup_off" and name:
            return f"Stop {name} starting with Windows"
        if self.key == "startup_on" and name:
            return f"Let {name} start with Windows again"
        if self.key == "verify_game" and name:
            return f"Ask Steam to check {name}'s files"
        if self.key == "check_game_fix" and name:
            return f"Check why {name} won't run"
        if self.key in ("mod_off", "mod_on") and name:
            return ("Turn off " if self.key == "mod_off" else "Turn on ") + name
        return self.action.title

    @property
    def kind(self):
        return self.action.kind


@dataclass
class Schedule:
    days: tuple       # 0 = Monday ... 6 = Sunday
    time: str         # "21:00"


@dataclass
class Plan:
    request: str
    steps: list
    schedule: Schedule | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    routine_id: str = ""


# ------------------------------------------------------------------ reading a request
_QUESTION = re.compile(r"^(what|where|which|why|how much|how many|how do|how does|how is|is|are|does|do i|did|when|who|"
                       r"should|explain|tell me|show me|describe|summari[sz]e|list|give me|help me understand)\b")
_VERB = re.compile(r"\b(clean|clear|delete|remove|close|kill|quit|exit|end|turn|switch|stop|disable|block|prevent|scan|"
                   r"re-?scan|check|update|install|download|get|make|run|boost|optimi[sz]e|speed|prep|prepare|undo|revert|"
                   r"put|restore|free|tidy|do|find|look|automate|schedule|enable|activate|deactivate|toggle|open|launch|start|"
                   r"show|take|go|set|use|bring|pull|help|back|fix|repair|crash|crashes|crashing)\b")
_POLITE = re.compile(r"\b(can you|could you|would you|please|for me|go ahead|do it|run|automate|every|each|daily|nightly|"
                     r"weekly)\b")


def is_request(text):
    """A request to do something, not a question about the data. "What can I delete?" stays a question."""
    t = " ".join(text.casefold().split())
    if not t or not _VERB.search(t):
        return False  # a name on its own ("Cleanup history", "Drivers & Startup") is a question about that thing
    return not _QUESTION.search(t) or bool(_POLITE.search(t))


_READY = re.compile(r"ready to play|before i (play|game)|game ?time|gaming mode|\bboost\b|speed up|optimi[sz]e|"
                    r"get (my )?(pc|computer) ready|run (better|faster|smoother)|less lag|more fps|prep(are)? (my )?(pc|computer)")
_CLEAN = re.compile(r"clean ?up|clear (out )?(the |my )?(temp|junk|temporary)|temp(orary)? files|\bjunk\b|tidy")
_DRIVERS = re.compile(r"\bdrivers?\b")
_INSTALL_DRIVERS = re.compile(r"(install|update|get|download)\s+(all\s+|the\s+|my\s+|any\s+|new\s+)*(driver|updates)|"
                              r"drivers?\s+(updated|installed)")
_STARTUP = re.compile(r"start(s|ing)? (up )?with windows|startup|start-up|start up|on boot|at boot|when windows starts")
_OFF = re.compile(r"\b(turn off|switch off|stop|disable|don'?t|prevent|remove|block|no longer)\b")
_CLOSE = re.compile(r"\b(close|kill|quit|exit|shut down|end)\b(?! game grave)")
_SCAN = re.compile(r"\b(re-?scan|scan)\b|look for (my )?games|find (my )?games")
_LEFTOVERS = re.compile(r"\bleftovers?\b|\bgraveyard\b|left ?behind by (old|removed|uninstalled) games")
_STORAGE_SCAN = re.compile(r"other storage|\bcaches?\b|shader cache")
_CAPTURES_SCAN = re.compile(r"\bcaptures?\b|\bscreenshots?\b|\brecordings?\b|\bclips\b")
_MOD_SWITCH = re.compile(r"\b(turn|switch|toggle) (it |them |that |those )?(off|on)\b|\b(disable|enable|deactivate|activate)\b|"
                         r"\b(turn|switch) .{1,60}? (off|on)\b")
_GAME_MODE = re.compile(r"game ?mode")
_RECORDING = re.compile(r"recording|game ?bar|game ?dvr|captures? in the background")
_POWER = re.compile(r"power plan|high performance|full power|max(imum)? performance|full speed")
_UNDO = re.compile(r"\b(undo|revert|put (it|them|those|my settings|my windows settings|windows settings|everything) back|"
                   r"restore my (windows )?settings|change (it|them) back)\b")
_APP_UPDATE = re.compile(r"update game grave|new(er)? (version|build) of game grave|game grave update|check for updates|"
                         r"is there an update|latest version")


def wants(text):
    """The actions a request asks for, in a sensible order. Empty when it asks for none of Game Grave's tools."""
    t = " ".join(text.casefold().replace("’", "'").split())
    if not is_request(t):
        return []
    found = []

    def add(key, **args):
        if not any(s.key == key and s.args == args for s in found) and len(found) < MAX_STEPS:
            found.append(Step(key, dict(args)))
    if _UNDO.search(t) and (_GAME_MODE.search(t) or _RECORDING.search(t) or _POWER.search(t) or
                            re.search(r"optimi[sz]|windows settings|my settings", t)):
        add("undo_optimizer")
        return found
    from gg_desktop import fixgame_core
    if fixgame_core.wants_fix(t):        # "my game won't start", "Elden Ring keeps crashing": the non-mod causes first
        add("check_game_fix", mentioned=t)
        add("check_drivers")
        return found
    looks = bool(_SCAN.search(t) or re.search(r"\b(find|look for|check)\b", t))
    specific = False
    if looks and _LEFTOVERS.search(t):
        add("scan_leftovers")
        specific = True
    caches_only = bool(_STORAGE_SCAN.search(t)) and not re.search(r"\btemp|temporary|junk", t)
    if (looks or (_CLEAN.search(t) and caches_only)) and _STORAGE_SCAN.search(t):
        add("scan_storage")
        specific = True
    if looks and _CAPTURES_SCAN.search(t):
        add("scan_captures")
        specific = True
    if _SCAN.search(t) and not specific:
        add("scan_library")
    if re.search(r"\bmods?\b", t) and _MOD_SWITCH.search(t) and not _STARTUP.search(t):
        on = bool(re.search(r"\b(turn|switch|toggle)\b.*\bon\b|\b(enable|activate)\b", t)) and not \
            re.search(r"\b(off|disable|deactivate)\b", t)
        add("check_mods", mentioned=t, on=on)
    if _APP_UPDATE.search(t):
        add("check_app_update")
    if _READY.search(t):
        add("check_memory", mentioned=t)
        add("game_mode_on")
        add("recording_off")
        add("power_high", ticked=False)
    if _CLOSE.search(t) and not _STARTUP.search(t) and not re.search(r"\bmods?\b", t):
        add("check_memory", mentioned=t)
    if _GAME_MODE.search(t) and not _OFF.search(t):
        add("game_mode_on")
    if _RECORDING.search(t) and (_OFF.search(t) or "background" in t):
        add("recording_off")
    if _POWER.search(t):
        add("power_high")
    if _CLEAN.search(t) and not caches_only:
        add("check_temp")
        add("clear_temp")
    if _DRIVERS.search(t):
        add("check_drivers")
        if _INSTALL_DRIVERS.search(t):
            add("install_drivers")
    if _STARTUP.search(t):
        add("check_startup", mentioned=t, off=bool(_OFF.search(t)))
    if not found and _MOD_SWITCH.search(t) and not _STARTUP.search(t):
        # "turn off skyui": not one of Windows' settings above, so it names mods
        on = bool(re.search(r"\bon\b|\b(enable|activate)\b", t)) and not re.search(r"\b(off|disable|deactivate)\b", t)
        add("check_mods", mentioned=t, on=on)
    for step in found:  # the "ticked" hint above is a plan default, not an argument
        if "ticked" in step.args:
            step.ticked = bool(step.args.pop("ticked"))
    return found


def plan_for(text):
    steps = wants(text)
    if not steps:
        return None
    return Plan(" ".join(text.split())[:300], steps, parse_schedule(text))


# ------------------------------------------------------------------ preparing a plan (pure parts; the reads are elsewhere)
def mentioned(name, text):
    """True when the request names this app ("close discord" names Discord.exe)."""
    stem = re.sub(r"\.exe$", "", name.casefold())
    stem = re.sub(r"[^a-z0-9]+", " ", stem).strip()
    words = set(re.sub(r"[^a-z0-9]+", " ", (text or "").casefold()).split())
    parts = [p for p in stem.split() if len(p) >= 3]
    return bool(parts) and (stem.replace(" ", "") in words or any(p in words for p in parts))


_MOD_STOP = frozenset("the and for with mod mods turn switch off on my in of a an to please disable enable it them".split())


def mod_named(name, request):
    """True when the request names this mod: its whole name, or every real word of it ("turn off skyui" names SkyUI, but
    "skyrim" alone does not name "Unofficial Skyrim Special Edition Patch")."""
    squash = lambda text: re.sub(r"[^a-z0-9]+", "", text.casefold())
    full = squash(name)
    if len(full) >= 3 and full in squash(request):
        return True
    words = set(re.sub(r"[^a-z0-9]+", " ", (request or "").casefold()).split())
    parts = [p for p in re.sub(r"[^a-z0-9]+", " ", name.casefold()).split() if p not in _MOD_STOP and len(p) >= 2]
    return bool(parts) and all(p in words for p in parts)


def mod_steps(profiles, request, on):
    """One step per named mod in each Mod Organizer 2 profile. Mods already in the asked state are reported, not listed."""
    steps, already = [], []
    key = "mod_on" if on else "mod_off"
    for game, profile, folder, mods in profiles:
        for name, enabled, label in mods:
            if not mod_named(label, request):
                continue
            if enabled == on:
                already.append(label)
                continue
            steps.append(Step(key, {"name": label, "key": name, "folder": str(folder), "profile": profile, "game": game},
                              detail=f"{game}, profile {profile}"))
    return steps[:12], already


def close_steps(procs, request):
    """One "Close <app>" step per big app. Ticked only when the request names it; launchers are never suggested."""
    steps = []
    for proc in procs:
        name = proc.name
        if name.casefold() in NEVER_SUGGEST:
            continue
        named = mentioned(name, request)
        if proc.kb < BIG_APP_KB and not named:
            continue
        steps.append(Step("close_app", {"name": name, "pid": int(proc.pid)}, detail=f"{proc.kb / 1024:,.0f} MB in use",
                          ticked=named))
        if len(steps) >= 6:
            break
    return steps


def startup_steps(apps, request, off_wanted):
    """Startup apps that are on. Named ones are ticked; with no name, all are listed unticked so the owner picks."""
    steps = []
    for app in apps:
        if not app.enabled or app.locked:
            continue
        named = mentioned(app.title, request) or mentioned(app.name, request)
        if off_wanted and not named and any(mentioned(a.title, request) or mentioned(a.name, request)
                                            for a in apps if a.enabled):
            continue
        steps.append(Step("startup_off", {"name": app.title, "key": app.key},
                          detail=(app.company or app.source) + (", asks Windows to allow it" if app.needs_admin else ""),
                          ticked=named and off_wanted))
    return steps[:12]


def counts(plan):
    ticked = [s for s in plan.steps if s.ticked and s.status != "skipped"]
    return (sum(1 for s in ticked if s.kind == CHANGE), sum(1 for s in ticked if s.kind == CHECK))


def summary(plan):
    changes, checks = counts(plan)
    parts = []
    if changes:
        parts.append(f"{changes} change" + ("" if changes == 1 else "s"))
    if checks:
        parts.append(f"{checks} check" + ("" if checks == 1 else "s"))
    return ", ".join(parts) or "nothing to do"


def confirmation(plan):
    """The text of the one OK: every change, with its exact technical line."""
    lines = []
    for n, step in enumerate([s for s in plan.steps if s.ticked and s.kind == CHANGE and s.status == "waiting"], 1):
        lines.append(f"{n}. {step.title}" + (f" ({step.detail})" if step.detail else ""))
        technical = step.action.technical
        if step.key == "verify_game" and step.args.get("url"):
            technical = "Opens " + str(step.args["url"]) + "; Steam does the check."
        lines.append("   " + technical)
        if step.action.undo:
            lines.append("   " + step.action.undo)
    return "\n".join(lines)


def run_order(plan):
    """Ticked steps still waiting, checks first so a change never acts on an old reading."""
    waiting = [s for s in plan.steps if s.ticked and s.status == "waiting"]
    return [s for s in waiting if s.kind == CHECK] + [s for s in waiting if s.kind == CHANGE]


# ------------------------------------------------------------------ schedules
DAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_EVERY = re.compile(r"\b(every|each|daily|nightly|weekly|weekdays?|weekends?|(on )?(mon|tues|wednes|thurs|fri|satur|sun)days)\b")


def parse_schedule(text):
    t = " ".join(text.casefold().split())
    if not _EVERY.search(t):
        return None
    days = set()
    if re.search(r"every ?day|daily|each day|every night|nightly|every morning|every evening", t):
        days = set(range(7))
    if re.search(r"weekdays?|work ?days?", t):
        days |= {0, 1, 2, 3, 4}
    if re.search(r"weekends?", t):
        days |= {5, 6}
    for n, name in enumerate(DAY_NAMES):
        if re.search(r"\b" + name[:3] + r"(" + name[3:] + r")?s?\b", t):
            days.add(n)
    if not days and re.search(r"every week|weekly|each week", t):
        days = {6}
    if not days:
        return None
    hour, minute = (21, 0) if re.search(r"night|evening", t) else (9, 0) if "morning" in t else (20, 0)
    match = re.search(r"\b(?:at|@)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?", t) or \
        re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", t)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2) or 0)
        half = (match.group(3) or "").replace(".", "")
        if half == "pm" and hour < 12:
            hour += 12
        if half == "am" and hour == 12:
            hour = 0
        if not half and hour < 7 and re.search(r"night|evening|pm", t):
            hour += 12
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            hour, minute = 20, 0
    return Schedule(tuple(sorted(days)), f"{hour:02d}:{minute:02d}")


def clock(time_text):
    hour, minute = (int(x) for x in time_text.split(":"))
    suffix = "AM" if hour < 12 else "PM"
    return f"{hour % 12 or 12}:{minute:02d} {suffix}"


def describe_schedule(schedule):
    days = tuple(schedule.days)
    if days == tuple(range(7)):
        when = "Every day"
    elif days == (0, 1, 2, 3, 4):
        when = "Weekdays"
    elif days == (5, 6):
        when = "Weekends"
    else:
        names = [DAY_NAMES[d].capitalize() for d in days]
        when = "Every " + (names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1])
    return f"{when} at {clock(schedule.time)}"


def last_slot(schedule, now):
    """The most recent scheduled time at or before now (looking back up to 8 days), or None."""
    hour, minute = (int(x) for x in schedule.time.split(":"))
    for back in range(0, 8):
        day = now - timedelta(days=back)
        slot = day.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if slot <= now and day.weekday() in schedule.days:
            return slot
    return None


def next_slot(schedule, now):
    hour, minute = (int(x) for x in schedule.time.split(":"))
    for ahead in range(0, 8):
        day = now + timedelta(days=ahead)
        slot = day.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if slot > now and day.weekday() in schedule.days:
            return slot
    return None


def is_due(routine, now):
    """Due when a scheduled time has passed since it last ran (or was made), and not more than a day ago."""
    if not routine.get("on", True):
        return False
    slot = last_slot(Schedule(tuple(routine["days"]), routine["time"]), now)
    if slot is None:
        return False
    since = max(float(routine.get("last_run") or 0), float(routine.get("created") or 0))
    return slot.timestamp() > since and now - slot <= CATCH_UP


# ------------------------------------------------------------------ saved routines
def routine_from_plan(plan, name, now):
    keys = []
    for step in plan.steps:
        if step.ticked and step.action.routine and step.key not in keys:
            keys.append(step.key)
    if "clear_temp" in keys and "check_temp" not in keys:
        keys.insert(keys.index("clear_temp"), "check_temp")
    if "install_drivers" in keys and "check_drivers" not in keys:
        keys.insert(keys.index("install_drivers"), "check_drivers")
    left_out = sorted({s.title for s in plan.steps if s.ticked and not s.action.routine})
    return {"id": uuid.uuid4().hex[:10], "name": (name or "My routine")[:40], "steps": keys,
            "days": list(plan.schedule.days), "time": plan.schedule.time, "on": True,
            "created": float(now.timestamp()), "last_run": 0.0}, left_out


def load_routines(settings):
    raw = settings.get(ROUTINES_KEY) if isinstance(settings, dict) else None
    routines = []
    for item in raw if isinstance(raw, list) else []:
        try:
            steps = [k for k in item["steps"] if k in ACTIONS and ACTIONS[k].routine][:MAX_STEPS]
            days = sorted({int(d) for d in item["days"] if 0 <= int(d) <= 6})
            hour, minute = (int(x) for x in str(item["time"]).split(":"))
            if not steps or not days or not (0 <= hour <= 23 and 0 <= minute <= 59):
                continue
            routines.append({"id": str(item["id"])[:12], "name": str(item.get("name") or "My routine")[:40],
                             "steps": steps, "days": days, "time": f"{hour:02d}:{minute:02d}",
                             "on": bool(item.get("on", True)), "created": float(item.get("created") or 0),
                             "last_run": float(item.get("last_run") or 0),
                             "last_note": str(item.get("last_note") or "")[:300]})
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    return routines[:MAX_ROUTINES]


def with_routines(settings, routines):
    return dict(settings, **{ROUTINES_KEY: list(routines)[:MAX_ROUTINES]})


def routine_plan(routine):
    """A fresh plan for a routine run: checks run straight away, changes wait for the owner's OK."""
    plan = Plan("Routine: " + routine["name"], [Step(k) for k in routine["steps"]],
                Schedule(tuple(routine["days"]), routine["time"]), routine_id=routine["id"])
    return plan


def routine_line(routine, now):
    schedule = Schedule(tuple(routine["days"]), routine["time"])
    titles = ", ".join(ACTIONS[k].title.lower() for k in routine["steps"])
    nxt = next_slot(schedule, now)
    when = describe_schedule(schedule)
    return f"{when}: {titles}." + (f" Next: {nxt.strftime('%a')} {clock(nxt.strftime('%H:%M'))}." if nxt and
                                   routine.get("on", True) else " Paused.")


# ------------------------------------------------------------------ keeping a plan with the chat
def plan_to_dict(plan):
    data = asdict(plan)
    data["schedule"] = asdict(plan.schedule) if plan.schedule else None
    for step in data["steps"]:
        step["args"] = {k: v for k, v in step["args"].items() if k in ("name", "pid", "key", "mentioned", "off", "ids",
                                                                         "titles", "on", "folder", "profile", "game")}
    return data


def plan_from_dict(raw):
    try:
        steps = [Step(str(s["key"]), dict(s.get("args") or {}), str(s.get("detail", ""))[:200], bool(s.get("ticked", True)),
                      str(s.get("status", "waiting")), str(s.get("result", ""))[:400])
                 for s in raw["steps"][:MAX_STEPS] if s.get("key") in ACTIONS]
        sched = raw.get("schedule")
        schedule = Schedule(tuple(int(d) for d in sched["days"]), str(sched["time"])) if sched else None
        return Plan(str(raw.get("request", ""))[:300], steps, schedule, str(raw.get("id", ""))[:12] or uuid.uuid4().hex[:10],
                    str(raw.get("routine_id", ""))[:12])
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def intro(plan, on):
    if not on:
        return ("I can do this for you with Game Grave's own tools, but running tools is switched off. Turn on "
                "\"Let the assistant run tools\" and ask again, or use the buttons to open the tools yourself.")
    if plan.schedule:
        return ("Here is the plan. Run it now, or save it as a routine: " + describe_schedule(plan.schedule) +
                ". Checks run on time; changes wait for your OK.")
    return "Here is the plan. Checks run straight away. Nothing changes until you press Run all."
