"""Soulbind: set your comfort preferences once and apply them to every game that supports them. No Qt in this module.

What works today, honestly:
* Unreal Engine games read player overrides from `Engine.ini` under a `[SystemSettings]` section. Soulbind writes the
  engine's own switches there for motion blur, depth of field, chromatic aberration, film grain and lens flares.
* Subtitles, field of view, invert Y, camera shake and colorblind modes are stored per game in each game's own format.
  Soulbind keeps them in your profile and shows them as "not supported yet" instead of pretending.

Safety:
* The original `Engine.ini` is copied to Game Grave's own folder before the first change, and Restore puts it back.
  If there was no file, Restore removes only the file Soulbind wrote, and only if nobody changed it since.
* Nothing is changed until the owner presses Apply. Online games with anti-cheat may ignore or reject edited
  settings files, so the dialog says to use Soulbind on single-player games.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re

PROFILE_NAME = "soulbind.json"
BACKUP_FOLDER = "soulbind-backups"
SECTION = "SystemSettings"

# key, title, Unreal Engine switches written when the preference is on
ENGINE_PREFS = (
    ("motion_blur", "Motion blur off", {"r.MotionBlurQuality": "0"}),
    ("depth_of_field", "Depth of field off", {"r.DepthOfFieldQuality": "0"}),
    ("chromatic_aberration", "Chromatic aberration off", {"r.SceneColorFringeQuality": "0"}),
    ("film_grain", "Film grain off", {"r.FilmGrain": "0", "r.Tonemapper.GrainQuantization": "0"}),
    ("lens_flare", "Lens flares off", {"r.LensFlareQuality": "0"}),
)
GAME_PREFS = (
    ("subtitles", "Subtitles on"),
    ("wide_fov", "Wider field of view"),
    ("invert_y", "Invert Y axis"),
    ("less_shake", "Less camera shake"),
    ("colorblind", "Colorblind mode"),
)
ALL_KEYS = tuple(k for k, *_ in ENGINE_PREFS) + tuple(k for k, _ in GAME_PREFS)
TITLES = {k: t for k, t, *_ in ENGINE_PREFS} | dict(GAME_PREFS)
NOT_GAMES = frozenset({"epicgameslauncher", "unrealengine", "unreal engine", "unrealeditor", "crashreportclient",
                       "epiconlineservices", "unrealengine-launcher"})


def default_profile():
    return {k: (k in ("motion_blur", "chromatic_aberration", "film_grain", "subtitles")) for k in ALL_KEYS}


def clean_profile(data):
    """Only known keys, only true/false. Anything else is dropped."""
    base = {k: False for k in ALL_KEYS}
    if isinstance(data, dict):
        prefs = data.get("prefs", data)
        if isinstance(prefs, dict):
            for key in ALL_KEYS:
                if isinstance(prefs.get(key), bool):
                    base[key] = prefs[key]
    return base


def load_profile(path):
    try:
        return clean_profile(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return default_profile()


def save_profile(path, prefs):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"app": "Game Grave Soulbind", "schema": 1, "prefs": clean_profile(prefs)}
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return path


def import_profile(path):
    raw = Path(path).read_text(encoding="utf-8")
    if len(raw) > 64 * 1024:
        raise ValueError("That file is too large to be a Soulbind profile.")
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get("app") != "Game Grave Soulbind":
        raise ValueError("That file is not a Soulbind profile.")
    return clean_profile(data)


@dataclass
class Target:
    name: str
    folder: str      # the Saved/Config/<platform> folder

    @property
    def engine_ini(self):
        return os.path.join(self.folder, "Engine.ini")

    @property
    def key(self):
        return hashlib.sha256(os.path.normcase(self.folder).encode("utf-8")).hexdigest()[:16]


def _config_folders(base, depth):
    """Yield Saved/Config/<platform> folders holding GameUserSettings.ini, up to `depth` folders below base."""
    base = Path(base)
    if not base.is_dir():
        return
    stack = [(base, 0)]
    while stack:
        folder, level = stack.pop()
        saved = folder / "Saved" / "Config"
        if saved.is_dir():
            try:
                for platform in saved.iterdir():
                    if platform.is_dir() and (platform / "GameUserSettings.ini").is_file():
                        yield folder, platform
            except OSError:
                pass
            continue
        if level >= depth:
            continue
        try:
            for child in folder.iterdir():
                if child.is_dir() and not child.is_symlink() and not child.name.startswith("."):
                    stack.append((child, level + 1))
        except OSError:
            continue


def find_targets(env=None):
    """Unreal Engine games that have saved settings on this PC (from LOCALAPPDATA and Documents\\My Games)."""
    env = os.environ if env is None else env
    roots = []
    if env.get("LOCALAPPDATA"):
        roots.append((env["LOCALAPPDATA"], 1))
    profile = env.get("USERPROFILE")
    if profile:
        roots.append((os.path.join(profile, "Documents", "My Games"), 3))
    found, seen = [], set()
    for base, depth in roots:
        for project, platform in _config_folders(base, depth):
            if project.name.casefold() in NOT_GAMES:
                continue
            key = os.path.normcase(str(platform))
            if key in seen:
                continue
            seen.add(key)
            found.append(Target(project.name, str(platform)))
    found.sort(key=lambda t: t.name.casefold())
    return found


def wanted_switches(prefs):
    switches = {}
    for key, _title, values in ENGINE_PREFS:
        if prefs.get(key):
            switches.update(values)
    return switches


def score(prefs):
    """How many of the owner's chosen preferences Soulbind can apply to an Unreal Engine game today."""
    chosen = [k for k in ALL_KEYS if prefs.get(k)]
    applicable = [k for k, *_ in ENGINE_PREFS if prefs.get(k)]
    return len(applicable), len(chosen)


def set_switches(text, switches):
    """Return Engine.ini text with each switch set once inside [SystemSettings]. Other lines are kept as they were."""
    lines = (text or "").replace("\r\n", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    header = re.compile(r"^\s*\[(.+?)\]\s*$")
    start = next((i for i, line in enumerate(lines)
                  if (m := header.match(line)) and m.group(1).strip().casefold() == SECTION.casefold()), None)
    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"[{SECTION}]")
        start = len(lines) - 1
    end = next((i for i in range(start + 1, len(lines)) if header.match(lines[i])), len(lines))
    remaining = dict(switches)
    lowered = {k.casefold(): k for k in switches}
    for i in range(start + 1, end):
        name = lines[i].split("=", 1)[0].strip()
        original = lowered.get(name.casefold())
        if original is not None and "=" in lines[i]:
            lines[i] = f"{original}={switches[original]}"
            remaining.pop(original, None)
    insert = end
    while insert > start + 1 and not lines[insert - 1].strip():
        insert -= 1
    lines[insert:insert] = [f"{k}={v}" for k, v in remaining.items()]
    return "\n".join(lines) + "\n"


@dataclass
class ApplyResult:
    target: Target
    switches: dict = field(default_factory=dict)
    backup: str = ""
    created: bool = False


def _sha(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode("utf-8")).hexdigest()


BOMS = ((b"\xef\xbb\xbf", "utf-8"), (b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be"))


def decode_ini(data):
    """(text, encoding, bom). Some Unreal games save their ini files as UTF-16, so the encoding is kept as found."""
    for bom, encoding in BOMS:
        if data.startswith(bom):
            return data[len(bom):].decode(encoding), encoding, bom
    try:
        return data.decode("utf-8"), "utf-8", b""
    except UnicodeDecodeError:
        raise ValueError("Engine.ini uses a text encoding Soulbind does not recognise, so it was left alone.") from None


def _write_atomic(path, data):
    temp = path.with_name(path.name + ".gg-tmp")
    try:
        temp.write_bytes(data)
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()


def apply(target, prefs, backup_root, *, now=None):
    switches = wanted_switches(prefs)
    if not switches:
        raise ValueError("None of your preferences can be applied to this game yet. Turn on at least one engine setting.")
    path = Path(target.engine_ini)
    existed = path.is_file()
    raw = path.read_bytes() if existed else b""
    text, encoding, bom = decode_ini(raw) if existed else ("", "utf-8", b"")
    crlf = b"\r\n" in raw if not encoding.startswith("utf-16") else "\r\n" in text
    folder = Path(backup_root) / target.key
    folder.mkdir(parents=True, exist_ok=True)
    record_path = folder / "record.json"
    if not record_path.exists():
        # Keep the very first original, byte for byte, so Restore always returns to the settings from before Soulbind.
        if existed:
            (folder / "Engine.ini.original").write_bytes(raw)
        record = {"name": target.name, "folder": target.folder, "existed": existed,
                  "saved": now or datetime.now().strftime("%Y-%m-%d %H:%M")}
    else:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    updated = set_switches(text, switches)
    data = bom + (updated.replace("\n", "\r\n") if crlf else updated).encode(encoding)
    _write_atomic(path, data)
    record["written_sha"] = _sha(data)
    record_path.write_text(json.dumps(record, indent=1), encoding="utf-8")
    return ApplyResult(target, switches, str(folder), not existed)


def has_backup(target, backup_root):
    return (Path(backup_root) / target.key / "record.json").is_file()


def restore(target, backup_root):
    folder = Path(backup_root) / target.key
    record_path = folder / "record.json"
    if not record_path.is_file():
        raise ValueError("Soulbind has not changed this game, so there is nothing to restore.")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    path = Path(target.engine_ini)
    if record.get("existed"):
        _write_atomic(path, (folder / "Engine.ini.original").read_bytes())
        message = "Restored the Engine.ini you had before Soulbind."
    else:
        if path.is_file():
            if _sha(path.read_bytes()) != record.get("written_sha"):
                raise ValueError("Engine.ini changed after Soulbind wrote it (the game or you edited it), so it was "
                                 "left as it is. Remove it yourself if you want the game's defaults back.")
            path.unlink()
        message = "Removed the Engine.ini that Soulbind created. The game uses its defaults again."
    for child in folder.iterdir():
        child.unlink()
    folder.rmdir()
    return message
