"""Squad Sync: one code that tells your friends exactly which mods to run, and one press to match it. No Qt here.

Supported today: games modded through r2modman or the Thunderstore Mod Manager (Lethal Company, Valheim, Risk of Rain
2, Content Warning and every other Thunderstore game). Other mod sites are planned.

How it works:
* Share: Game Grave reads your manager profile and makes a Squad Code (the mod list with exact versions, compressed
  into text). No server, no account, no personal data, no file paths. Optionally it also saves a squad file that
  carries the profile's BepInEx config files.
* Join: paste the code. Game Grave compares it with your own profile: missing mods, wrong versions, extras.
* Match Squad: one press writes a ready-to-import profile file. Your mod manager downloads every mod from Thunderstore
  in one import and puts it in a NEW profile, so your own setup is never touched. Restoring your setup is simply
  picking your old profile again.

Mods always come from Thunderstore itself. Game Grave never copies mod files between people.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import zipfile
import zlib

CODE_PREFIX = "GGSQ1."
NAME_RE = re.compile(r"^[A-Za-z0-9_]+-[A-Za-z0-9_]+$")
VERSION_RE = re.compile(r"^\d{1,6}\.\d{1,6}\.\d{1,6}$")
MAX_MODS = 600
MAX_CODE = 60_000
CONFIG_LIMIT_FILES = 300
CONFIG_LIMIT_BYTES = 5 * 1024 * 1024
MANAGERS = (
    ("r2modman", ("r2modmanPlus-local",)),
    ("Thunderstore Mod Manager", ("Thunderstore Mod Manager", "DataFolder")),
)


@dataclass(frozen=True)
class Mod:
    name: str
    version: str
    enabled: bool = True

    @property
    def author(self):
        return self.name.split("-", 1)[0]

    @property
    def page(self):
        author, _sep, package = self.name.partition("-")
        return f"https://thunderstore.io/package/{author}/{package}/"


@dataclass(frozen=True)
class Profile:
    manager: str
    game: str
    name: str
    folder: str

    @property
    def label(self):
        return f"{self.game} · {self.name} ({self.manager})"


def find_profiles(env=None):
    """Manager profiles that have a mods.yml, from %APPDATA%."""
    env = os.environ if env is None else env
    appdata = env.get("APPDATA")
    found = []
    if not appdata:
        return found
    for manager, parts in MANAGERS:
        base = Path(appdata, *parts)
        if not base.is_dir():
            continue
        try:
            games = [g for g in base.iterdir() if g.is_dir()]
        except OSError:
            continue
        for game in games:
            profiles = game / "profiles"
            try:
                names = [p for p in profiles.iterdir() if p.is_dir()] if profiles.is_dir() else []
            except OSError:
                continue
            for profile in names:
                if (profile / "mods.yml").is_file():
                    found.append(Profile(manager, game.name, profile.name, str(profile)))
    found.sort(key=lambda p: (p.game.casefold(), p.name.casefold()))
    return found


_ITEM = re.compile(r"^(\s*)-\s+[A-Za-z_]+\s*:")
_NAME = re.compile(r"^\s*-?\s*name\s*:\s*['\"]?([^'\"\n#]+?)['\"]?\s*$", re.M)
_ENABLED = re.compile(r"^\s*-?\s*enabled\s*:\s*(true|false)\s*$", re.M | re.I)


def _number(block, key):
    match = re.search(r"^\s*" + key + r"\s*:\s*(\d+)\s*$", block, re.M)
    return int(match.group(1)) if match else None


def parse_mod_list(text):
    """Mods from an r2modman mods.yml or export.r2x (a YAML list of items with name, version numbers, enabled)."""
    lines = (text or "").replace("\r\n", "\n").split("\n")
    starts = [(i, len(m.group(1))) for i, line in enumerate(lines) if (m := _ITEM.match(line))]
    if not starts:
        return []
    indent = min(level for _i, level in starts)
    starts = [i for i, level in starts if level == indent]
    mods, seen = [], set()
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        block = "\n".join(lines[start:end])
        name = _NAME.search(block)
        major, minor, patch = (_number(block, k) for k in ("major", "minor", "patch"))
        if not name or None in (major, minor, patch):
            continue
        value = name.group(1).strip()
        if not NAME_RE.match(value) or value in seen:
            continue
        seen.add(value)
        enabled = _ENABLED.search(block)
        mods.append(Mod(value, f"{major}.{minor}.{patch}", not enabled or enabled.group(1).lower() == "true"))
    return mods


def read_profile(profile):
    text = Path(profile.folder, "mods.yml").read_text(encoding="utf-8", errors="replace")
    return parse_mod_list(text)


def make_code(game, label, mods):
    enabled = [m for m in mods if m.enabled]
    if not enabled:
        raise ValueError("This profile has no turned-on mods to share.")
    payload = {"g": str(game)[:64], "p": str(label)[:64], "m": [[m.name, m.version] for m in enabled[:MAX_MODS]]}
    raw = zlib.compress(json.dumps(payload, separators=(",", ":")).encode("utf-8"), 9)
    return CODE_PREFIX + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


@dataclass
class Squad:
    game: str
    label: str
    mods: list
    configs: dict = None


def _decode(text):
    body = text[len(CODE_PREFIX):]
    inflater = zlib.decompressobj()
    raw = inflater.decompress(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)), 2 * 1024 * 1024)
    if inflater.unconsumed_tail:
        raise ValueError
    return json.loads(raw.decode("utf-8"))


def read_code(code):
    raw = code or ""
    pattern = re.escape(CODE_PREFIX) + r"[A-Za-z0-9_-]+"
    # People paste codes with words around them ("here you go: GGSQ1..."), and chat apps sometimes break long codes
    # across lines. Try the code as written first, then with the line breaks removed.
    candidates = [m.group(0) for m in re.finditer(pattern, raw)]
    candidates += [m.group(0) for m in re.finditer(pattern, "".join(raw.split()))]
    if not candidates:
        raise ValueError("That is not a Squad Code. Squad Codes start with " + CODE_PREFIX)
    data = None
    for text in candidates:
        if len(text) > MAX_CODE:
            raise ValueError("That Squad Code is too long.")
        try:
            data = _decode(text)
            break
        except (ValueError, zlib.error, UnicodeDecodeError):
            continue
    if data is None:
        raise ValueError("That Squad Code is damaged. Ask for it again and paste all of it.")
    mods = []
    for item in data.get("m", []) if isinstance(data, dict) else []:
        if (isinstance(item, list) and len(item) == 2 and isinstance(item[0], str) and isinstance(item[1], str)
                and NAME_RE.match(item[0]) and VERSION_RE.match(item[1])):
            mods.append(Mod(item[0], item[1]))
    if not mods:
        raise ValueError("That Squad Code has no mods in it.")
    return Squad(str(data.get("g", ""))[:64], str(data.get("p", ""))[:64], mods[:MAX_MODS])


@dataclass
class Comparison:
    matching: list
    missing: list
    wrong_version: list      # (host mod, your version)
    extra: list
    turned_off: list         # in your profile but turned off

    @property
    def matched(self):
        return not (self.missing or self.wrong_version or self.extra or self.turned_off)

    def summary(self):
        if self.matched:
            return f"You match: all {len(self.matching)} mods, same versions."
        parts = []
        if self.missing:
            parts.append(f"{len(self.missing)} missing")
        if self.wrong_version:
            parts.append(f"{len(self.wrong_version)} wrong version")
        if self.turned_off:
            parts.append(f"{len(self.turned_off)} turned off")
        if self.extra:
            parts.append(f"{len(self.extra)} extra")
        return f"{len(self.matching)} match. " + ", ".join(parts) + "."


def compare(squad_mods, mine):
    yours = {m.name: m for m in mine}
    host = {m.name for m in squad_mods}
    matching, missing, wrong, off = [], [], [], []
    for mod in squad_mods:
        have = yours.get(mod.name)
        if have is None:
            missing.append(mod)
        elif have.version != mod.version:
            wrong.append((mod, have.version))
        elif not have.enabled:
            off.append(mod)
        else:
            matching.append(mod)
    extra = [m for m in mine if m.enabled and m.name not in host]
    return Comparison(matching, missing, wrong, extra, off)


def _yaml_text(text):
    return json.dumps(str(text), ensure_ascii=False)


def export_r2x(profile_name, mods):
    """r2modman's import format: a profile name and a list of mods with exact versions."""
    lines = [f"profileName: {_yaml_text(profile_name)}", "mods:"]
    for mod in mods:
        major, minor, patch = mod.version.split(".")
        lines += [f"  - name: {mod.name}", "    version:", f"      major: {int(major)}", f"      minor: {int(minor)}",
                  f"      patch: {int(patch)}", f"    enabled: {'true' if mod.enabled else 'false'}"]
    return "\n".join(lines) + "\n"


def collect_configs(profile_folder):
    """BepInEx config files from a profile, by their path inside the profile. Bounded."""
    root = Path(profile_folder)
    config = root / "BepInEx" / "config"
    files, total = {}, 0
    if not config.is_dir():
        return files
    for path in sorted(config.rglob("*")):
        if not path.is_file() or path.is_symlink() or path.suffix.casefold() not in (".cfg", ".json", ".yml", ".yaml", ".txt"):
            continue
        size = path.stat().st_size
        if len(files) >= CONFIG_LIMIT_FILES or total + size > CONFIG_LIMIT_BYTES:
            break
        files[path.relative_to(root).as_posix()] = path.read_bytes()
        total += size
    return files


def safe_name(text):
    cleaned = re.sub(r"[^A-Za-z0-9 _.()-]", "", str(text)).strip(" .") or "Squad"
    return cleaned[:60]


def write_squad_file(path, profile_name, mods, configs=None):
    """A .r2z file r2modman and the Thunderstore Mod Manager import with Profiles > Import / Update > From file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".gg-tmp")
    with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("export.r2x", export_r2x(profile_name, list(mods)))
        for name, data in (configs or {}).items():
            if name.startswith("BepInEx/config/") and ".." not in name.split("/"):
                archive.writestr(name, data)
    temp.replace(path)
    return path


def read_squad_file(path):
    """A squad file someone sent you: the mod list (and how many config files it carries)."""
    path = Path(path)
    if path.stat().st_size > 50 * 1024 * 1024:
        raise ValueError("That file is too large to be a squad file.")
    with zipfile.ZipFile(path) as archive:
        try:
            text = archive.read("export.r2x").decode("utf-8", "replace")
        except KeyError:
            raise ValueError("That file is not a mod manager profile export.") from None
        configs = [n for n in archive.namelist() if n.startswith("BepInEx/config/")]
    match = re.search(r"^profileName\s*:\s*(.+)$", text, re.M)
    label = match.group(1).strip().strip('"') if match else path.stem
    # Only mods the sender had turned on are part of the squad.
    mods = [m for m in parse_mod_list(text) if VERSION_RE.match(m.version) and m.enabled]
    if not mods:
        raise ValueError("That profile export has no turned-on mods in it.")
    return Squad("", label, mods, {n: None for n in configs})


def read_squad_configs(path):
    """BepInEx config files from a squad file, refusing oversized or oddly named entries."""
    configs, total = {}, 0
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            name = info.filename
            if info.is_dir() or not name.startswith("BepInEx/config/") or ".." in name.split("/") or "\\" in name:
                continue
            total += info.file_size
            if len(configs) >= CONFIG_LIMIT_FILES or total > CONFIG_LIMIT_BYTES:
                raise ValueError("That squad file carries more config data than Game Grave accepts.")
            configs[name] = archive.read(info)
    return configs


def import_steps(manager="r2modman"):
    return [f"Open {manager} and pick the game.",
            "Profiles > Import / Update > From file, then choose the squad file Game Grave just saved.",
            "Give the new profile a name and let it download. Your own profiles are not changed.",
            "Press Start modded. To go back to your own setup, select your old profile."]
