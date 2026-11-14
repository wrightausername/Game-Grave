"""First-launch welcome: what Game Grave is, in three short screens. Pure (no Qt), covered by tests/test_welcome.py.

Owner instruction, 2026-11-14: a beta tester opened the app cold and could not tell what it was for, so the app has to
say it on its own. Every line below states only what the code does; nothing is called safe and nothing is promised
that a feature cannot keep.
"""
from __future__ import annotations

SEEN_KEY = "welcome_seen"

STEPS = (
    {
        "kicker": "WELCOME",
        "title": "Your games, kept alive.",
        "body": ("Game Grave is a caretaker for your PC games. It finds the games you have installed, backs them up, "
                 "helps you fix them when they break, and keeps them running right."),
        "points": (
            ("Finds your games", "Steam and other launchers, in one library. Press Scan PC to start."),
            ("Backs up whole games", "Resurrection Kit saves the install, your saves and your load order."),
            ("No account, no tracking", "Nothing about you is collected. Your files stay on your PC."),
        ),
    },
    {
        "kicker": "WHEN SOMETHING BREAKS",
        "title": "Bring it back from the dead.",
        "body": ("Crashes, a bad mod, a driver update that tanked your frames. Game Grave keeps track of what changed "
                 "so you can get back to when it worked."),
        "points": (
            ("Mod Bisect", "Finds the mod that is crashing your game, one test launch at a time."),
            ("Undo Center", "See every change Game Grave made, and undo what can be undone."),
            ("Black Box", "Keeps crash records and what changed since the last good launch."),
        ),
    },
    {
        "kicker": "SET IT ONCE",
        "title": "Every game plays your way.",
        "body": ("Pick your controls, accessibility and comfort settings one time. Soulbind applies them to every game "
                 "that has them, with a backup first."),
        "points": (
            ("Soulbind", "Your preferences, set once in the Ready Room."),
            ("Hardware", "Your PC's parts live, outdated drivers, and what starts with Windows."),
            ("AI Assistant", "Ask anything about your games or PC. Optional, runs on your PC."),
        ),
    },
)

LAST = len(STEPS) - 1


def should_show(settings: dict, *, reference_preview: bool = False) -> bool:
    """Shown once: not in the photo-reference preview, not when starting minimized, not after it was seen."""
    if reference_preview or not isinstance(settings, dict):
        return False
    if settings.get("start_minimized") is True:
        return False
    return settings.get(SEEN_KEY) is not True


def clamp(index: int) -> int:
    return max(0, min(LAST, int(index)))


def next_label(index: int) -> str:
    return "Scan my games" if clamp(index) == LAST else "Next"


def mark_seen(settings: dict) -> dict:
    updated = dict(settings or {})
    updated[SEEN_KEY] = True
    return updated
