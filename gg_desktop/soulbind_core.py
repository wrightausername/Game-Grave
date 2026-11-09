"""Soulbind: set your game preferences once, then apply them to every game Game Grave can verify.

Honesty rules this module enforces:
* A preference only counts for a game when Game Grave finds that exact setting inside the game's real config
  file on this PC. No file, or no such line in the file, means "not supported for this game", never a guess.
* Applying edits only the value on the matching line, keeps a dated backup of the original file first, and is
  recorded in the activity log. Reverting restores that backup, but only if the file is still exactly what
  Soulbind wrote, so a later change by you or by the game is never overwritten.
* Nothing here talks to the network or to a game process.

Pure Python (no Qt) so every rule is unit tested.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import zlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

MAX_CODE_CHARS = 4000
MAX_CONFIG_BYTES = 2_000_000
CODE_PREFIX = "GGSB1-"


# ------------------------------------------------------------------ preferences
@dataclass(frozen=True)
class Pref:
    id: str
    label: str
    group: str
    kind: str                       # "toggle", "number" or "choice"
    default: object
    options: tuple = ()             # choice: ((value, label), ...)   number: (minimum, maximum)
    tip: str = ""


PREFS = (
    Pref("subtitles", "Show subtitles", "Accessibility", "toggle", True, tip="Turn subtitles on."),
    Pref("screen_effects", "Screen shake and distortion", "Accessibility", "choice", "reduced",
         (("full", "Full"), ("reduced", "Reduced"), ("off", "Off")), "Less motion on screen can help with motion sickness."),
    Pref("view_bob", "Camera head bob", "Comfort", "toggle", False, tip="Turn walking camera bob on or off."),
    Pref("fov", "Field of view", "Comfort", "number", 90, (60, 120), "Wider view, in degrees."),
    Pref("invert_y", "Invert vertical look", "Controls", "toggle", False, tip="Push up to look down."),
    Pref("toggle_sprint", "Toggle sprint (tap instead of hold)", "Controls", "toggle", True),
    Pref("toggle_crouch", "Toggle crouch (tap instead of hold)", "Controls", "toggle", True),
)
PREF_BY_ID = {p.id: p for p in PREFS}
GROUPS = ("Accessibility", "Comfort", "Controls")


def clean_value(pref: Pref, value):
    """Return `value` as the right type for `pref`, or raise ValueError."""
    if pref.kind == "toggle":
        if isinstance(value, bool):
            return value
        raise ValueError(pref.id + ": expected on or off")
    if pref.kind == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(pref.id + ": expected a number")
        low, high = pref.options
        if not low <= value <= high:
            raise ValueError(f"{pref.id}: must be between {low} and {high}")
        return int(round(value))
    if pref.kind == "choice":
        if value in {v for v, _ in pref.options}:
            return value
        raise ValueError(pref.id + ": unknown choice")
    raise ValueError(pref.id + ": unknown kind")


def clean_profile(raw) -> dict:
    """Keep only known preferences with valid values; silently drop everything else."""
    out = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            pref = PREF_BY_ID.get(key)
            if pref is None:
                continue
            try:
                out[key] = clean_value(pref, value)
            except ValueError:
                continue
    return out


def value_text(pref: Pref, value) -> str:
    if pref.kind == "toggle":
        return "On" if value else "Off"
    if pref.kind == "number":
        return f"{value}°"
    return dict(pref.options).get(value, str(value))


# ------------------------------------------------------------------ share code
def make_code(profile: dict) -> str:
    body = json.dumps(clean_profile(profile), sort_keys=True, separators=(",", ":")).encode()
    return CODE_PREFIX + base64.urlsafe_b64encode(zlib.compress(body, 9)).decode().rstrip("=")


def read_code(code: str) -> dict:
    """Profile from a Soulbind code. Raises ValueError for anything that is not a plain Soulbind code."""
    code = (code or "").strip()
    if not code.startswith(CODE_PREFIX) or len(code) > MAX_CODE_CHARS:
        raise ValueError("That is not a Soulbind code.")
    packed = code[len(CODE_PREFIX):]
    try:
        raw = base64.urlsafe_b64decode(packed + "=" * (-len(packed) % 4))
        decoder = zlib.decompressobj()
        body = decoder.decompress(raw, MAX_CODE_CHARS * 4)
        if decoder.unconsumed_tail:
            raise ValueError("too large")
        data = json.loads(body.decode("utf-8"))
    except (ValueError, zlib.error, UnicodeError):
        raise ValueError("That Soulbind code is damaged.") from None
    profile = clean_profile(data)
    if not profile:
        raise ValueError("That Soulbind code has no preferences in it.")
    return profile


# ------------------------------------------------------------------ games Game Grave can verify
def _bool01(value):
    return "1" if value else "0"


def _read01(text):
    return {"1": True, "0": False}.get(text.strip())


def _bool_word(value):
    return "true" if value else "false"


def _read_word(text):
    return {"true": True, "false": False}.get(text.strip().lower())


def _num_ini(value):
    return f"{float(value):.4f}"


def _read_num(text):
    try:
        return int(round(float(text.strip())))
    except ValueError:
        return None


_EFFECT = {"full": "1.0", "reduced": "0.5", "off": "0.0"}


def _effect_text(value):
    return _EFFECT[value]


def _effect_read(text):
    try:
        number = float(text.strip())
    except ValueError:
        return None
    return "full" if number >= .75 else "reduced" if number >= .25 else "off"


@dataclass(frozen=True)
class Setting:
    pref: str
    key: str
    encode: Callable
    decode: Callable
    section: str | None = None      # INI section; None for flat key:value files


@dataclass(frozen=True)
class Adapter:
    id: str
    title: str
    names: tuple                    # lower-case fragments of the game's name
    files: tuple                    # ((root, relative path), ...) root is "documents" or "appdata"
    style: str                      # "ini" (key=value under [sections]) or "colon" (key:value)
    settings: tuple = field(default_factory=tuple)


BETHESDA = (
    Setting("invert_y", "bInvertYValues", _bool01, _read01, "Controls"),
    Setting("fov", "fDefaultWorldFOV", _num_ini, _read_num, "Display"),
)

ADAPTERS = (
    Adapter("skyrim-se", "The Elder Scrolls V: Skyrim Special Edition", ("skyrim special edition", "skyrim se"),
            (("documents", "My Games/Skyrim Special Edition/SkyrimPrefs.ini"),), "ini", BETHESDA),
    Adapter("fallout4", "Fallout 4", ("fallout 4",),
            (("documents", "My Games/Fallout4/Fallout4Prefs.ini"),), "ini", BETHESDA),
    Adapter("minecraft-java", "Minecraft: Java Edition", ("minecraft",),
            (("appdata", ".minecraft/options.txt"),), "colon", (
                Setting("invert_y", "invertYMouse", _bool_word, _read_word),
                Setting("view_bob", "bobView", _bool_word, _read_word),
                Setting("subtitles", "showSubtitles", _bool_word, _read_word),
                Setting("toggle_sprint", "toggleSprint", _bool_word, _read_word),
                Setting("toggle_crouch", "toggleCrouch", _bool_word, _read_word),
                Setting("screen_effects", "screenEffectScale", _effect_text, _effect_read),
            )),
)


def adapter_for(game_name: str):
    name = (game_name or "").casefold()
    return next((a for a in ADAPTERS if any(fragment in name for fragment in a.names)), None)


def default_roots() -> dict:
    home = Path.home()
    docs = [home / "Documents", home / "OneDrive" / "Documents"]
    return {"documents": docs, "appdata": [Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming")]}


def config_file(adapter: Adapter, roots: dict | None = None):
    """The first config file of this game that exists on this PC, or None."""
    roots = roots or default_roots()
    for root, relative in adapter.files:
        for base in roots.get(root, ()):
            candidate = Path(base) / relative
            try:
                if candidate.is_file() and not candidate.is_symlink() and candidate.stat().st_size <= MAX_CONFIG_BYTES:
                    return candidate
            except OSError:
                continue
    return None


# ------------------------------------------------------------------ reading and editing a config text
_SECTION = re.compile(r"^\s*\[([^\]]+)\]\s*$")


def _locate(adapter: Adapter, lines: list, setting: Setting):
    """Index of the line holding `setting`, or None. Matching is exact on section and key (case-insensitive)."""
    section = None
    separator = "=" if adapter.style == "ini" else ":"
    for index, line in enumerate(lines):
        match = _SECTION.match(line)
        if match:
            section = match.group(1).strip().casefold()
            continue
        if adapter.style == "ini" and (setting.section or "").casefold() != section:
            continue
        head, found, _ = line.partition(separator)
        if found and head.strip().casefold() == setting.key.casefold():
            return index
    return None


def _split(text: str):
    return text.split("\n")


@dataclass(frozen=True)
class Change:
    pref: str
    label: str
    key: str
    old: str
    new: str
    status: str                     # "matches" or "differs"


@dataclass(frozen=True)
class Plan:
    adapter: str
    changes: tuple                  # verified settings, matching or not
    unsupported: tuple              # preference ids the user set that this game cannot verify

    @property
    def differing(self):
        return tuple(c for c in self.changes if c.status == "differs")

    @property
    def matching(self):
        return tuple(c for c in self.changes if c.status == "matches")


def make_plan(adapter: Adapter, text: str, profile: dict) -> Plan:
    lines = _split(text)
    changes, unsupported = [], []
    by_pref = {s.pref: s for s in adapter.settings}
    for pref_id, wanted in profile.items():
        pref = PREF_BY_ID.get(pref_id)
        setting = by_pref.get(pref_id)
        if pref is None:
            continue
        index = _locate(adapter, lines, setting) if setting else None
        if setting is None or index is None:
            unsupported.append(pref_id)
            continue
        separator = "=" if adapter.style == "ini" else ":"
        current_text = lines[index].partition(separator)[2].rstrip("\r")
        current = setting.decode(current_text)
        if current is None:
            unsupported.append(pref_id)
            continue
        status = "matches" if current == wanted else "differs"
        changes.append(Change(pref_id, pref.label, setting.key, value_text(pref, current), value_text(pref, wanted), status))
    return Plan(adapter.id, tuple(changes), tuple(unsupported))


def apply_to_text(adapter: Adapter, text: str, profile: dict) -> str:
    """Return `text` with only the differing values changed. Every other byte stays as it was."""
    lines = _split(text)
    by_pref = {s.pref: s for s in adapter.settings}
    separator = "=" if adapter.style == "ini" else ":"
    for change in make_plan(adapter, text, profile).differing:
        setting = by_pref[change.pref]
        index = _locate(adapter, lines, setting)
        head, _, old = lines[index].partition(separator)
        tail = "\r" if old.endswith("\r") else ""
        lines[index] = head + separator + setting.encode(profile[change.pref]) + tail
    return "\n".join(lines)


# ------------------------------------------------------------------ score shown on a game
@dataclass(frozen=True)
class Score:
    text: str
    tone: str                       # "green", "amber" or "muted"
    detail: str


def score_for(plan: Plan | None, chosen: int) -> Score:
    if not chosen:
        return Score("No profile", "muted", "Choose some preferences in Soulbind first.")
    if plan is None:
        return Score("Not supported", "muted", "Game Grave cannot verify this game's settings yet.")
    checked = len(plan.changes)
    if not checked:
        return Score("Not supported", "muted", "None of your preferences were found in this game's settings file.")
    skipped = len(plan.unsupported)
    note = f" {skipped} of your preferences are not supported by this game." if skipped else ""
    if plan.differing:
        return Score(f"{len(plan.differing)} to apply", "amber",
                     f"{len(plan.matching)} of {checked} supported preferences already match.{note}")
    return Score("Soulbound", "green", f"All {checked} supported preferences match.{note}")


def badge_for(game_name: str, profile: dict, roots: dict | None = None):
    """The small badge for a game card, or None when there is nothing true to show (no profile, no known
    adapter, no settings file, or none of the chosen preferences found in the file)."""
    adapter = adapter_for(game_name)
    if adapter is None or not profile:
        return None
    path = config_file(adapter, roots)
    if path is None:
        return None
    try:
        text, _bom = _decode(path.read_bytes())
    except (OSError, UnicodeError):
        return None
    plan = make_plan(adapter, text, profile)
    return score_for(plan, len(profile)) if plan.changes else None


# ------------------------------------------------------------------ storage, apply and revert
def soulbind_dir() -> Path:
    import core
    return core.config_dir() / "soulbind"


def load_profile(root: Path | None = None) -> dict:
    path = (root or soulbind_dir()) / "profile.json"
    try:
        if path.stat().st_size > 20000:
            return {}
        return clean_profile(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return {}


def save_profile(profile: dict, root: Path | None = None) -> None:
    root = root or soulbind_dir()
    root.mkdir(parents=True, exist_ok=True)
    _atomic_write(root / "profile.json", json.dumps(clean_profile(profile), indent=2).encode("utf-8"))


def _atomic_write(path: Path, data: bytes) -> None:
    temp = path.with_name(path.name + ".soulbind-tmp")
    temp.write_bytes(data)
    os.replace(temp, path)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _decode(data: bytes):
    bom = data.startswith(b"\xef\xbb\xbf")
    return data[3:].decode("utf-8") if bom else data.decode("utf-8"), bom


@dataclass(frozen=True)
class Applied:
    entry_id: str
    path: str
    changes: tuple
    backup: str


def _ledger(root: Path) -> list:
    try:
        data = json.loads((root / "ledger.json").read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def ledger(root: Path | None = None) -> list:
    return _ledger(root or soulbind_dir())


def apply_profile(adapter: Adapter, path: Path, profile: dict, *, root: Path | None = None,
                  log: Callable | None = None, now: datetime | None = None) -> Applied | None:
    """Apply the profile to one game's config file. Returns None when everything already matches."""
    root = root or soulbind_dir()
    original = Path(path).read_bytes()
    if len(original) > MAX_CONFIG_BYTES:
        raise ValueError("That settings file is too large to edit safely.")
    text, bom = _decode(original)
    plan = make_plan(adapter, text, profile)
    if not plan.differing:
        return None
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    backup_dir = root / "backups" / adapter.id
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"{stamp}-{Path(path).name}"
    shutil.copy2(path, backup)
    edited = apply_to_text(adapter, text, profile).encode("utf-8")
    if bom:
        edited = b"\xef\xbb\xbf" + edited
    _atomic_write(Path(path), edited)
    entry = {"id": f"{adapter.id}-{stamp}", "game": adapter.title, "path": str(path), "backup": str(backup),
             "after_sha": _sha(edited), "time": stamp, "reverted": False,
             "changes": [{"label": c.label, "key": c.key, "old": c.old, "new": c.new} for c in plan.differing]}
    entries = (_ledger(root) + [entry])[-50:]
    _atomic_write(root / "ledger.json", json.dumps(entries, indent=2).encode("utf-8"))
    if log is None:
        import core
        log = core.log_event
    log("soulbind_apply", f"{adapter.title}: " + ", ".join(f"{c.label} {c.old} to {c.new}" for c in plan.differing),
        path=str(path), result="applied", source="soulbind")
    return Applied(entry["id"], str(path), plan.differing, str(backup))


def revert(entry_id: str, *, root: Path | None = None, log: Callable | None = None) -> bool:
    """Restore the backup of one apply. Refuses, and changes nothing, if the file changed since Soulbind wrote it."""
    root = root or soulbind_dir()
    entries = _ledger(root)
    entry = next((e for e in entries if e.get("id") == entry_id), None)
    if entry is None or entry.get("reverted"):
        raise ValueError("That change is not available to revert.")
    path, backup = Path(entry["path"]), Path(entry["backup"])
    if not backup.is_file():
        raise ValueError("The backup of that file is missing, so nothing was changed.")
    if not path.is_file() or _sha(path.read_bytes()) != entry["after_sha"]:
        raise ValueError("That file has changed since Soulbind edited it, so nothing was reverted.")
    _atomic_write(path, backup.read_bytes())
    entry["reverted"] = True
    _atomic_write(root / "ledger.json", json.dumps(entries, indent=2).encode("utf-8"))
    if log is None:
        import core
        log = core.log_event
    log("soulbind_revert", f"{entry['game']}: restored the settings file from before Soulbind",
        path=str(path), result="restored", source="soulbind")
    return True
