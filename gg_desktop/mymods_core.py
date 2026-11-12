"""My Mods engine: one game's mods from Mod Organizer 2, switched on and off, reordered, with snapshots and undo.

Reads an MO2 instance (ModOrganizer.ini), its profiles, each profile's modlist.txt / plugins.txt, and each mod's meta.ini
(version, the newest version MO2 recorded from Nexus, the Nexus mod ID). No Qt here.

Writes (owner approval 2026-11-11, "That's better yes"): only the chosen profile's modlist.txt, and only:
* switching a mod on (+) or off (-), and
* moving a mod to another place in the order.
Before every write the profile's modlist.txt and plugins.txt are copied into Game Grave's own snapshot folder; Undo puts
the last snapshot back, but only while the file is still exactly what Game Grave wrote (if MO2 or you changed it since,
Undo says so and leaves it). Nothing is written while Mod Organizer 2 is running, links are refused, mod folders and
plugins are never moved or deleted.

MO2's modlist.txt lists the highest-priority mod first; the screen shows MO2's own order (lowest priority at the top,
the winner of any file clash at the bottom), so the list is reversed on read and on write.
"""
from __future__ import annotations

import configparser
from dataclasses import dataclass, field, replace
import hashlib
import os
from pathlib import Path
import re
import shutil
import time

import core

MAX_MODS = 5000
MAX_SNAPSHOTS = 30
SEPARATOR = "_separator"


class ModsError(RuntimeError):
    pass


@dataclass(frozen=True)
class Mod:
    name: str                 # MO2's mod name = its folder name
    enabled: bool
    kind: str = "mod"         # "mod", "separator", "base" (managed outside MO2, the * lines)
    version: str = ""
    newest: str = ""          # newest version MO2 recorded from Nexus
    nexus_id: str = ""
    game: str = ""            # MO2's gameName in meta.ini
    url: str = ""
    installed_from: str = ""
    plugins: tuple = ()       # plugin files in the mod folder

    @property
    def label(self):
        return self.name[:-len(SEPARATOR)] if self.kind == "separator" else self.name

    @property
    def update(self):
        return bool(self.newest and self.version and _vt(self.newest) > _vt(self.version))


@dataclass(frozen=True)
class Profile:
    name: str
    folder: Path
    mods: tuple               # MO2 screen order: first = lowest priority
    plugins_enabled: tuple    # plugin names ticked in plugins.txt, in load order
    local_saves: bool = False


@dataclass(frozen=True)
class Instance:
    game: str                 # MO2's gameName
    game_path: Path | None
    ini: Path
    mods_dir: Path
    profiles_dir: Path
    selected: str
    profiles: tuple = field(default_factory=tuple)   # profile names

    @property
    def key(self):
        return "mo2:" + str(self.ini).casefold()


def _vt(version):
    return tuple(int(x) for x in re.findall(r"\d+", str(version or ""))[:6])


# ------------------------------------------------------------------ reading
def _ini(path: Path):
    cfg = configparser.RawConfigParser(interpolation=None, strict=False)
    cfg.optionxform = str
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        text = path.read_text(encoding="cp1252", errors="replace")
    cfg.read_string(text)
    return cfg


def _resolve(raw: str, base: Path, ini_dir: Path) -> Path:
    raw = re.sub(r"%BASE_DIR%", lambda _m: str(base), str(raw).strip().strip('"'), flags=re.I)
    raw = os.path.expandvars(os.path.expanduser(raw))
    if os.name != "nt":
        raw = raw.replace("\\", "/")
    p = Path(raw)
    return p if p.is_absolute() else ini_dir / p


def _qt(value: str) -> str:
    value = str(value or "")
    if value.startswith("@ByteArray(") and value.endswith(")"):
        value = value[len("@ByteArray("):-1]
    return value.replace("\\\\", "\\")


def _is_link(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        return bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)
    except OSError:
        return True


def read_instance(ini: Path) -> Instance:
    if not ini.is_file() or _is_link(ini):
        raise ModsError("Mod Organizer 2's settings file isn't readable.")
    cfg = _ini(ini)
    general = cfg["General"] if cfg.has_section("General") else {}
    settings = cfg["Settings"] if cfg.has_section("Settings") else {}
    base = _resolve(settings.get("base_directory", str(ini.parent)), ini.parent, ini.parent)
    mods_dir = _resolve(settings.get("mod_directory", "%BASE_DIR%/mods"), base, ini.parent)
    profiles_dir = _resolve(settings.get("profiles_directory", "%BASE_DIR%/profiles"), base, ini.parent)
    game_path = _qt(general.get("gamePath", ""))
    try:
        names = sorted((p.name for p in profiles_dir.iterdir() if p.is_dir() and not _is_link(p)), key=str.casefold)
    except OSError:
        names = []
    return Instance(_qt(general.get("gameName", "")) or ini.parent.name, Path(game_path) if game_path else None, ini,
                    mods_dir, profiles_dir, _qt(general.get("selected_profile", "")), tuple(names))


def parse_modlist(text: str):
    """[(name, marker)] in MO2 screen order (the file lists the highest priority first, so it is reversed)."""
    rows, seen = [], set()
    for line in text.splitlines():
        if not line or line.startswith("#") or line[0] not in "+-*":
            continue
        name = line[1:].strip()
        if not name or "/" in name or "\\" in name or name in (".", "..") or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        rows.append((name, line[0]))
        if len(rows) >= MAX_MODS:
            break
    return list(reversed(rows))


def render_modlist(rows, header="# This file was automatically generated by Mod Organizer.") -> str:
    """Back to MO2's file form: highest priority first."""
    lines = [header] + [f"{marker}{name}" for name, marker in reversed(list(rows))]
    return "\r\n".join(lines) + "\r\n"


def parse_plugins(text: str):
    """Ticked plugins in plugins.txt, in load order (lines starting with * are on)."""
    on = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("*") and len(line) > 1:
            on.append(line[1:].strip())
    return on


def read_meta(folder: Path) -> dict:
    meta = folder / "meta.ini"
    if not meta.is_file():
        return {}
    try:
        cfg = _ini(meta)
    except (OSError, configparser.Error):
        return {}
    g = cfg["General"] if cfg.has_section("General") else {}
    mod_id = str(g.get("modid", "") or "").strip()
    return {"version": str(g.get("version", "") or "").strip(), "newest": str(g.get("newestVersion", "") or "").strip(),
            "nexus_id": mod_id if mod_id.isdigit() and mod_id != "0" else "", "game": str(g.get("gameName", "") or ""),
            "url": str(g.get("url", "") or ""), "installed_from": str(g.get("installationFile", "") or "")}


PLUGIN_EXT = (".esp", ".esm", ".esl")


def plugins_in(folder: Path):
    try:
        return tuple(sorted(p.name for p in folder.iterdir() if p.is_file() and p.suffix.lower() in PLUGIN_EXT))
    except OSError:
        return ()


def _read_text(path: Path) -> str:
    if not path.is_file() or _is_link(path):
        return ""
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return path.read_text(encoding="cp1252", errors="replace")
    except OSError:
        return ""


def read_profile(instance: Instance, name: str) -> Profile:
    folder = instance.profiles_dir / name
    if not folder.is_dir() or _is_link(folder):
        raise ModsError(f"Profile {name} isn't readable.")
    rows = parse_modlist(_read_text(folder / "modlist.txt"))
    mods = []
    for mod_name, marker in rows:
        if marker == "*":
            mods.append(Mod(mod_name, True, "base"))
            continue
        if mod_name.casefold().endswith(SEPARATOR):
            mods.append(Mod(mod_name, marker == "+", "separator"))
            continue
        mod_folder = instance.mods_dir / mod_name
        meta = read_meta(mod_folder)
        mods.append(Mod(mod_name, marker == "+", "mod", plugins=plugins_in(mod_folder), **meta))
    settings = _read_text(folder / "settings.ini")
    local = bool(re.search(r"(?im)^\s*LocalSaves\s*=\s*true", settings))
    return Profile(name, folder, tuple(mods), tuple(parse_plugins(_read_text(folder / "plugins.txt"))), local)


# ------------------------------------------------------------------ snapshots, writes, undo
def snapshot_root() -> Path:
    return core.config_dir() / "mod_snapshots"


def _profile_key(folder: Path) -> str:
    return hashlib.sha256(str(folder).casefold().encode("utf-8")).hexdigest()[:16]


def snapshots(folder: Path, root: Path | None = None):
    base = (root or snapshot_root()) / _profile_key(folder)
    try:
        return sorted((p for p in base.iterdir() if p.is_dir()), key=lambda p: p.name)
    except OSError:
        return []


def take_snapshot(folder: Path, label: str, root: Path | None = None) -> Path:
    base = (root or snapshot_root()) / _profile_key(folder)
    stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{int(time.time() * 1000) % 1000:03d}"
    target = base / f"{stamp}-{re.sub(r'[^A-Za-z0-9]+', '-', label)[:40].strip('-')}"
    target.mkdir(parents=True, exist_ok=False)
    for name in ("modlist.txt", "plugins.txt", "loadorder.txt"):
        src = folder / name
        if src.is_file() and not _is_link(src):
            shutil.copy2(src, target / name)
    (target / "profile.txt").write_text(str(folder), encoding="utf-8")
    for old in snapshots(folder, root)[:-MAX_SNAPSHOTS]:
        shutil.rmtree(old, ignore_errors=True)
    return target


def _guard(profile_folder: Path, running):
    state = running() if callable(running) else running
    if state:
        raise ModsError("Close Mod Organizer 2 first. It rewrites its lists when it closes, so changes made while it's "
                        "open would be lost.")
    target = profile_folder / "modlist.txt"
    if not target.is_file() or _is_link(target):
        raise ModsError("This profile's mod list isn't an ordinary file, so Game Grave won't change it.")


def _replace(temp: Path, target: Path, tries=20, wait=0.1):
    """os.replace, retried: on Windows a file another program is reading (an antivirus scan, Game Grave's own detailed
    view loading) refuses to be replaced for a moment. If it stays locked, the text is written into the file directly."""
    for _ in range(tries):
        try:
            os.replace(temp, target)
            return
        except PermissionError:
            time.sleep(wait)
    data = temp.read_bytes()
    with target.open("r+b") as out:
        out.write(data)
        out.truncate()
    temp.unlink()


def _write(profile_folder: Path, rows, label: str, running, root=None) -> Path:
    _guard(profile_folder, running)
    snap = take_snapshot(profile_folder, label, root)
    text = render_modlist(rows)
    temp = profile_folder / "modlist.txt.gg-tmp"
    temp.write_text(text, encoding="utf-8", newline="")
    _replace(temp, profile_folder / "modlist.txt")
    (snap / "written.sha256").write_text(hashlib.sha256(text.encode("utf-8")).hexdigest(), encoding="utf-8")
    return snap


def _rows(profile_folder: Path):
    return parse_modlist(_read_text(profile_folder / "modlist.txt"))


def set_enabled(profile_folder: Path, names, on: bool, *, running=None, root=None) -> Path:
    wanted = {n.casefold() for n in names}
    rows = _rows(profile_folder)
    found = {n.casefold() for n, m in rows if m in "+-"}
    missing = wanted - found
    if missing:
        raise ModsError("Not in this profile: " + ", ".join(sorted(missing))[:200])
    new = [(n, ("+" if on else "-") if n.casefold() in wanted and m in "+-" else m) for n, m in rows]
    verb = "on" if on else "off"
    return _write(profile_folder, new, f"turn {verb} {len(wanted)}", running, root)


def move(profile_folder: Path, name: str, to_index: int, *, running=None, root=None) -> Path:
    """Move a mod to position to_index in MO2's screen order (0 = top, lowest priority)."""
    rows = _rows(profile_folder)
    at = next((i for i, (n, _m) in enumerate(rows) if n.casefold() == name.casefold()), None)
    if at is None:
        raise ModsError(f"{name} isn't in this profile.")
    item = rows.pop(at)
    rows.insert(max(0, min(len(rows), to_index)), item)
    return _write(profile_folder, rows, f"move {name}", running, root)


def reorder(profile_folder: Path, names_in_order, *, running=None, root=None) -> Path:
    """Set the whole order (screen order). Every current entry must be present exactly once."""
    rows = _rows(profile_folder)
    by = {n.casefold(): (n, m) for n, m in rows}
    order = [n.casefold() for n in names_in_order]
    if sorted(order) != sorted(by) or len(set(order)) != len(order):
        raise ModsError("The new order doesn't match this profile's mods, so nothing was changed.")
    return _write(profile_folder, [by[n] for n in order], "reorder", running, root)


def undo(profile_folder: Path, *, running=None, root=None) -> str:
    snaps = snapshots(profile_folder, root)
    if not snaps:
        raise ModsError("There is nothing to undo for this profile.")
    last = snaps[-1]
    _guard(profile_folder, running)
    written = (last / "written.sha256")
    current = hashlib.sha256(_read_text(profile_folder / "modlist.txt").replace("\r\n", "\n").replace("\n", "\r\n")
                             .encode("utf-8")).hexdigest()
    if written.is_file() and written.read_text(encoding="utf-8").strip() != current:
        raise ModsError("The mod list changed since Game Grave's last change (Mod Organizer 2 or you edited it), so "
                        "Undo left it alone.")
    for name in ("modlist.txt", "plugins.txt", "loadorder.txt"):
        src = last / name
        if src.is_file():
            temp = profile_folder / (name + ".gg-tmp")
            shutil.copy2(src, temp)
            if (profile_folder / name).exists():
                _replace(temp, profile_folder / name)
            else:
                os.replace(temp, profile_folder / name)
    label = last.name.split("-", 3)[-1].replace("-", " ")
    shutil.rmtree(last, ignore_errors=True)
    return label


# ------------------------------------------------------------------ plugin masters (Mod Doctor)
def plugin_masters(path: Path) -> list[str]:
    """Master files a Bethesda plugin (.esp/.esm/.esl) says it needs, from its TES4 header's MAST entries."""
    try:
        with path.open("rb") as f:
            head = f.read(24)
            if len(head) < 24 or head[:4] != b"TES4":
                return []
            size = int.from_bytes(head[4:8], "little")
            if size <= 0 or size > 4_000_000:
                return []
            data = f.read(size)
    except OSError:
        return []
    masters, i = [], 0
    while i + 6 <= len(data):
        kind = data[i:i + 4]
        length = int.from_bytes(data[i + 4:i + 6], "little")
        body = data[i + 6:i + 6 + length]
        if kind == b"MAST":
            masters.append(body.split(b"\0", 1)[0].decode("cp1252", "replace"))
        i += 6 + length
    return masters
