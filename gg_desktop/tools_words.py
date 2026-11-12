"""Plain words for the More Tools windows. Pure: no Qt, no outside calls, so every sentence is tested.

The windows lead with these plain lines. The exact technical lines (registry values, commands) stay one click away in
"Show technical details" and are always repeated in the confirmation before anything changes.
"""
from __future__ import annotations

import re

# Each tool: (summary shown under the title, step names, category tone from the hub)
TOOLS = {
    "windows_cleanup": ("Clears out old temporary files Windows and your apps left behind.",
                        ("Look", "Check the list", "Delete"), "red"),
    "game_optimizer": ("Three Windows settings that can help games. Undo puts every one back.",
                       ("Pick", "Confirm", "Done"), "cyan"),
    "memory_optimizer": ("Close apps you are not using before you play, biggest first.",
                         ("Pick apps", "Confirm", "Closed"), "cyan"),
    "command_runner": ("Run one Windows command and see what it prints.",
                       ("Type or pick", "Confirm", "Result"), "yellow"),
    "file_associations": ("See which app opens a type of file.",
                          ("Pick a type", "See the app", "Change it in Windows"), "yellow"),
    "junction_manager": ("See and manage folder links, such as a game moved to another drive.",
                         ("Pick a folder", "See its links", "Add or remove"), "yellow"),
    "kit_menu": ("Save a whole game into one file, and put it back later.", (), "purple"),
    "hash": ("A file's fingerprint. Compare it with the one the publisher lists.", ("Pick a file", "Read it", "Compare"),
             "blue"),
}

OPTIMIZER_PLAIN = {
    "game_mode": ("Game Mode", "Tells Windows to put the game you are playing ahead of background work."),
    "background_recording": ("Background recording", "Stops Windows from quietly recording your games in the background."),
    "power_plan": ("High performance power", "Keeps the processor at full speed instead of saving power. Uses more electricity."),
}

GOOD, WARN, BAD, INFO, WORKING, IDLE = "good", "warn", "bad", "info", "working", "idle"


def summary(key):
    return TOOLS.get(key, ("", (), "red"))[0]


def steps(key):
    return TOOLS.get(key, ("", (), "red"))[1]


def tone(key):
    return TOOLS.get(key, ("", (), "red"))[2]


def optimizer_state(key, values, plan_name=None, applied=False):
    """Plain (state, pill tone) for one Game Optimizer setting.

    `values` are the raw registry numbers (None when not set); `plan_name` is the active power plan's name as Windows
    reports it (None when it could not be read); `applied` says the plan is already High performance.
    """
    if key == "power_plan":
        if not plan_name or plan_name == "Could not be read":
            return "Could not be read", WARN
        return plan_name, (GOOD if applied else IDLE)
    if not values or all(v is None for v in values):
        return "Not set, Windows decides", IDLE
    want_on = key == "game_mode"
    if all(v == (1 if want_on else 0) for v in values):
        return ("On" if want_on else "Off"), GOOD
    if all(v == (0 if want_on else 1) or v is None for v in values):
        return ("Off" if want_on else "On"), IDLE
    return "Partly off", IDLE


def optimizer_plain(key):
    return OPTIMIZER_PLAIN.get(key, (key, ""))


def apply_label(count, verb="Apply"):
    """'Apply', 'Apply 1 change', 'Apply 3 changes'."""
    if count <= 0:
        return verb
    return f"{verb} {count} change" + ("" if count == 1 else "s")


def close_label(count):
    if count <= 0:
        return "Close selected apps"
    return f"Close {count} app" + ("" if count == 1 else "s")


def plain_count(count, noun):
    return f"{count:,} {noun}" + ("" if count == 1 else "s")


_BAD = re.compile(r"\b(could not|couldn't|not made|not removed|not created|not saved|stopped|failed|error|refused|"
                  r"was not changed|nothing was restored|did not accept)\b", re.IGNORECASE)
_WARN_STRONG = re.compile(r"\b(cancel\w*|still running|broken)\b", re.IGNORECASE)
_WARN = re.compile(r"\b(first\b|select|tick|type a|choose|no .* found|not found)", re.IGNORECASE)
_GOOD = re.compile(r"\b(deleted|removed the link|created|applied|switched|turned (on|off)|restored|saved and checked|"
                   r"asked \d+ apps? to close|finished with exit code 0|match|added \d+|links? found|opens with)\b",
                   re.IGNORECASE)


def guess_tone(text):
    """Tone for a result line written elsewhere, so old wording still gets the right colour. Empty text hides the banner.

    Only the first sentence decides, because later sentences add detail ("0 skipped") that is not the outcome.
    """
    text = (text or "").strip()
    if not text:
        return IDLE
    if text.endswith("…") or text.endswith("...") or text.lower().startswith(("looking", "reading", "deleting", "running",
                                                                              "checking", "cancelling", "step ")):
        return WORKING
    first = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    if _BAD.search(first):
        return BAD
    if re.search(r"exit code (?!0\b)\d+", first, re.IGNORECASE) or _WARN_STRONG.search(first) or \
            first.lower().startswith("no "):
        return WARN
    if _GOOD.search(first):
        return GOOD
    if _WARN.search(first):
        return WARN
    return INFO
