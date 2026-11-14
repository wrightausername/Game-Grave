"""The welcome tour: what Game Grave is and where everything lives. Pure (no Qt), covered by tests/test_welcome.py.

Owner instructions, 2026-11-14: a beta tester could not tell what the app was for ("the app should be able to speak for
itself"), then "the tutorial needs to be a little more extensive along with an option to turn off on startup permanently,
or skip, or look at it again in the settings". Every line states only what the code does; nothing is called safe.

When it shows:
* At startup while the "welcome_at_startup" setting is on (the default).
* Skip intro closes it for this time only; it shows again at the next start.
* "Don't show this at startup" (on every screen) or finishing the last screen turns the setting off.
* It can be watched again any time from Settings (Startup & Behavior) or the ? button in the top bar, and switched back on there.
"""
from __future__ import annotations

STARTUP_KEY = "welcome_at_startup"

STEPS = (
    {
        "kicker": "WELCOME",
        "title": "Your games, kept alive.",
        "body": ("Game Grave is a caretaker for your PC games. It finds the games you have installed, backs them up, "
                 "helps you fix them when they break, and keeps your PC running right for them. This short tour shows "
                 "where everything is."),
        "points": (
            ("Start with a scan", "Press Scan PC (or F5). It only reads; nothing on your PC is changed by a scan."),
            ("No account, no tracking", "Nothing about you is collected. Your files stay on your PC."),
            ("Nothing happens behind your back", "Every change is shown first, asks you, and is written to a log."),
        ),
    },
    {
        "kicker": "FINDING YOUR WAY",
        "title": "Five groups in the sidebar.",
        "body": "The sidebar on the left is sorted by what you want to do. Each tab has one line under it saying what it is for.",
        "points": (
            ("Home and Library", "Overview and Ready Room, then your Games, Mods and Captures."),
            ("Clean Up", "Old Files, Other Storage and Graveyard: find what is taking up space."),
            ("Fix and Protect", "Fix Kit, Game DNA and Undo Center: crashes, backups and rollbacks."),
            ("PC and Help", "Hardware, Toolbox, the AI Assistant and Settings."),
        ),
    },
    {
        "kicker": "LIBRARY",
        "title": "Everything you play, in one place.",
        "body": "Games from Steam and other launchers, your mods and your screenshots, each with its own tab.",
        "points": (
            ("Games", "Size, last played and drive for every game. Verify or uninstall goes through its launcher."),
            ("Mods", "Turn mods on and off and reorder them in Mod Organizer 2, with Undo. Steam Workshop items get real names."),
            ("Captures", "Screenshots and recordings, grouped by game when the file path proves which game."),
        ),
    },
    {
        "kicker": "CLEAN UP",
        "title": "Find what is eating your drives.",
        "body": ("These tabs show what is taking up space. You review every item yourself, and anything you choose to "
                 "remove goes to the Recycle Bin, so you can get it back."),
        "points": (
            ("Old Files", "Older files in a folder you pick. Age alone never decides for you."),
            ("Other Storage", "Caches, logs and temp files from launchers and games."),
            ("Graveyard", "Leftovers from games you removed, with the evidence for each."),
        ),
    },
    {
        "kicker": "FIX AND PROTECT",
        "title": "Bring a broken game back.",
        "body": "Fix Kit holds every tool for a crashing, stuttering or risky game. Undo Center keeps track of what changed.",
        "points": (
            ("Mod Bisect", "Finds the mod that is crashing a game, one test launch at a time."),
            ("Black Box, Autopsy, Exhume", "Crash reports, frame-time comparisons and rolling back a graphics driver."),
            ("Resurrection Kit", "Back up a whole game, with saves and load order, and restore it later."),
            ("Undo Center", "See every change Game Grave made, and undo what can be undone."),
        ),
    },
    {
        "kicker": "READY ROOM",
        "title": "Your setup, ready to play.",
        "body": "Ready Room shows official news and patches for your games, plus two tools for how you play.",
        "points": (
            ("Patch Watch", "Official Steam news for your games, refreshed while Ready Room is open."),
            ("Soulbind", "Set your controls and comfort settings once. Game Grave applies them where a game supports them, with a backup first."),
            ("Squad Sync", "Share a code so friends can match your modded co-op setup."),
        ),
    },
    {
        "kicker": "PC AND HELP",
        "title": "Your PC, and help when you need it.",
        "body": "Click any tool or strip to open it. Strips open and close with one click anywhere on their title line.",
        "points": (
            ("Hardware", "Your parts and live load, upgrade notes, outdated drivers and what starts with Windows."),
            ("Toolbox", "Windows tune-ups, backups, reports and file utilities, each listed once."),
            ("AI Assistant", "Ask about your games or PC. Optional: turn it on in Settings."),
        ),
    },
    {
        "kicker": "YOU'RE SET",
        "title": "Scan, and you're ready.",
        "body": "Press Scan my games to find your library now. You can watch this tour again any time.",
        "points": (
            ("Watch this again", "Press the ? button at the top, or open Settings, Startup & Behavior."),
            ("Shortcuts", "F5 scans your PC. Ctrl + K searches the tab you are on."),
            ("Show at startup", "Finishing the tour turns it off at startup. Switch it back on in Settings."),
        ),
    },
)

LAST = len(STEPS) - 1
MAX_POINTS = max(len(step["points"]) for step in STEPS)


def should_show(settings: dict, *, reference_preview: bool = False) -> bool:
    """At startup while the setting is on; never in the photo-reference preview or when starting minimized."""
    if reference_preview or not isinstance(settings, dict):
        return False
    if settings.get("start_minimized") is True:
        return False
    return settings.get(STARTUP_KEY, True) is not False


def clamp(index: int) -> int:
    return max(0, min(LAST, int(index)))


def next_label(index: int) -> str:
    return "Scan my games" if clamp(index) == LAST else "Next"


def close_label(index: int) -> str:
    return "Close" if clamp(index) == LAST else "Skip intro"


def step_caption(index: int) -> str:
    return f"{clamp(index) + 1} of {len(STEPS)}"


def startup_after(*, finished: bool, dont_show: bool, current: bool = True) -> bool:
    """Whether the tour shows at the next start. Skip keeps the current choice; finishing or the box turns it off."""
    if dont_show or finished:
        return False
    return current


def with_startup(settings: dict, on: bool) -> dict:
    updated = dict(settings or {})
    updated[STARTUP_KEY] = bool(on)
    return updated
