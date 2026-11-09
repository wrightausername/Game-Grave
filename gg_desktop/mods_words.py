"""Plain-language wording for the Mods tab. Everything here is display text only: the facts behind it are unchanged,
and nothing is called safe. Partial coverage is still said out loud."""
from __future__ import annotations

# Metric tiles, left to right: (caption, hover explanation).
TILE_TIPS = (
    ("Mods Found", "How many separate mods Game Grave found on this PC."),
    ("Turned On", "Mods your mod manager has switched on in a saved profile."),
    ("Updates Available", "Mods where your mod manager has recorded a newer version. Game Grave does not go online to check."),
    ("Conflicts Found", "Places where two mods change the same file, so one overrides the other."),
    ("Not In Use", "Installed, but not part of any saved profile, so no profile would load them."),
    ("Space Used", "Disk space reported for these mods. Files shared between mods can be counted twice."),
)
FOLDERS_CAPTION = "Mod Folders"
FOLDERS_TIP = "How many mod storage folders Game Grave found. A folder can hold many mods."

STATUS = {
    "Enabled": "On", "Disabled": "Off", "Mixed": "On in some",
    "Unknown": "Not recorded", "Protected": "Storage folder",
}
STATUS_TIPS = {
    "On": "Turned on in your mod manager's saved profile.",
    "Off": "Installed but turned off in your mod manager's saved profile.",
    "On in some": "Turned on in some saved profiles and off in others.",
    "Not recorded": "Your mod manager has not saved whether this mod is on or off.",
    "Storage folder": "A folder where a mod manager keeps its mods. Game Grave only reads it and never changes it.",
}


def status_word(text: str) -> str:
    return STATUS.get(text, text)


def manager_name(name: str) -> str:
    return "Mod Organizer 2" if name in ("MO2", "Mod Organizer 2") else name


def plural(count: int, one: str, many: str | None = None) -> str:
    return f"{count} {one if count == 1 else (many or one + 's')}"


def summary(m: dict, *, games: int = 0) -> str:
    """One sentence a non-technical person can read. Says what is unknown instead of guessing."""
    total = m.get("total") or 0
    if not total:
        return "No mods found yet. Scan your PC and Game Grave will list what it finds."
    noun = "mod" if m.get("total_label") == "Total Mods" else "mod folder"
    parts = [f"{plural(total, noun)}" + (f" for {plural(games, 'game')}" if games else "")]
    known_state = m.get("enabled") or m.get("mixed") or m.get("disabled")
    if known_state:
        parts.append(f"{m.get('enabled', 0)} turned on")
    outdated = m.get("outdated")
    if outdated is not None:
        parts.append("no updates recorded" if outdated == 0 else plural(outdated, "update") + " available")
    conflicts = m.get("conflicts")
    if conflicts is not None:
        text = "no conflicts found" if conflicts == 0 else plural(conflicts, "conflict") + " found"
        if m.get("conflicts_limited"):
            text += " (some may be missed)"
        parts.append(text)
    return "You have " + ", ".join(parts) + "."


def order_text(position: int, count: int, profile: str) -> str:
    return f"#{position} of {count} · {profile}"


def requires_text(names: list[str], more: bool) -> str:
    if not names:
        return "Doesn't list any other mods it needs"
    return f"Needs {plural(len(names) + (1 if more else 0), 'other mod')}: " + ", ".join(names) + (" …" if more else "")


def conflicts_text(count: int, limited: bool, checked: bool) -> str:
    if not checked:
        return "Not checked yet"
    if not count:
        return "None found" + (" (the check was partial)" if limited else "")
    return f"{plural(count, 'conflict')} found" + (" (check was partial)" if limited else "")


def profiles_text(names: list[str]) -> str:
    if not names:
        return "Not in any saved profile"
    return f"In {plural(len(names), 'profile')}: " + ", ".join(names[:4]) + (" …" if len(names) > 4 else "")


def update_text(newest: str, installed: str, outdated: bool, note: str) -> str:
    if outdated:
        return f"Version {newest} is available (you have {installed or 'an unknown version'})"
    return note
