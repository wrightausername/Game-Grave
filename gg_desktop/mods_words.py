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


# ---------------------------------------------------------------- readable names
import re as _re

_NEXUS_ARCHIVE = _re.compile(r"^(?P<title>.+?)-(?P<modid>\d{1,7})(?:-[0-9A-Za-z]{1,12}){1,6}-(?P<stamp>\d{9,11})$")
_TRAILING_STAMP = _re.compile(r"[-_ ]+\d{9,}$")
_HEXISH = _re.compile(r"^(?:[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}|[0-9a-fA-F]{20,})$")


def readable_name(name: str, path: str = "", source: str = "", games=()) -> str:
    """A name a person can read for a mod storage folder, using only what the folder name or the scan proves.

    * A folder named only by digits inside Steam's Workshop folder is a Steam app number. It gets the installed game's
      name only when that exact app number is one of the scanned games.
    * A download name such as "SkyUI-12604-5-2SE-1564405049" loses its trailing mod id, version and time stamp.
    * Long hexadecimal or GUID names are shortened so they do not read as a wall of characters.
    Anything else is returned unchanged. The caller keeps the original folder name for the tooltip and inspector.
    """
    raw = (name or "").strip()
    if not raw:
        return "Mod storage"
    in_workshop = "workshop" in (source + " " + path).casefold()
    if raw.isdigit():
        game = next((g for g in games if str(getattr(g, "app_id", "")) == raw), None)
        if game is not None and in_workshop:
            return f"{game.name} Workshop items"
        if in_workshop:
            return f"Steam Workshop items (app {raw})"
        return f"Folder {raw}"
    nexus = _NEXUS_ARCHIVE.match(raw)
    if nexus:
        title = _re.sub(r"[_]+", " ", nexus.group("title")).strip()
        if len(title) >= 2:
            return title
    if _HEXISH.match(raw):
        return f"Folder {raw[:8]}…"
    stripped = _TRAILING_STAMP.sub("", raw)
    if stripped and stripped != raw and len(stripped) >= 3:
        return stripped
    return raw
