"""Squad Sync: make everyone in a co-op group run the same mods, using only what can really be read.

Game Grave's scanner knows where mod folders are, not which mods are on. So Squad Sync reads three real sources and
says which it could read: the Steam Workshop manifest for the game, the enabled list of a Mod Organizer 2 profile, and
the Bethesda active plugin list. It compares your list with a friend's squad code or with a snapshot of your own.

It cannot download or install mods and never touches a mod file. A Steam Workshop item can be opened in Steam, where
you press Subscribe. Anything else you get from where your friend did. A snapshot records the list, not the files.
The squad code holds item names and Workshop numbers only: no paths, no user name.
"""
from __future__ import annotations

import base64
import json
import os
import re
import zlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

CODE_PREFIX = "GGSQ1-"
MAX_CODE_CHARS = 20000
MAX_ITEMS = 400
MAX_UNPACKED = 300_000
KINDS = {"workshop": "Steam Workshop", "mo2": "Mod Organizer 2", "plugin": "Plugin list"}
PLUGIN_FOLDERS = {"skyrim special edition": "Skyrim Special Edition", "fallout 4": "Fallout4"}
SAFE_NAME = re.compile(r"[^\x00-\x1f]{1,120}")


@dataclass(frozen=True)
class Item:
    kind: str
    key: str
    label: str
    stamp: str = ""          # Workshop "time updated", digits, when known


@dataclass
class Setup:
    game: str
    items: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    read_any: bool = False
    made: str = ""


# ------------------------------------------------------------------ reading real sources
def default_roots() -> dict:
    local = os.environ.get("LOCALAPPDATA")
    appdata = os.environ.get("APPDATA")
    return {"local": [Path(local)] if local else [], "roaming": [Path(appdata)] if appdata else []}


def _lines(path: Path, limit: int = 20000):
    try:
        if path.stat().st_size > 5_000_000:
            return []
        return path.read_text(encoding="utf-8-sig", errors="replace").splitlines()[:limit]
    except OSError:
        return []


def read_workshop(library: str, app_id: str) -> list[Item] | None:
    """None when the game has no Workshop manifest in that library."""
    import core
    if not (app_id or "").isdigit() or not library:
        return None
    path = Path(library) / "steamapps" / "workshop" / f"appworkshop_{app_id}.acf"
    if not path.is_file():
        return None
    data = core.read_vdf(path)
    installed = (data.get("appworkshop") or {}).get("workshopitemsinstalled")
    if not isinstance(installed, dict):
        return []
    items = []
    for item_id, fields in installed.items():
        if not str(item_id).isdigit() or len(str(item_id)) > 20:
            continue
        stamp = str(fields.get("timeupdated", "")) if isinstance(fields, dict) else ""
        items.append(Item("workshop", str(item_id), f"Workshop item {item_id}", stamp if stamp.isdigit() else ""))
        if len(items) >= MAX_ITEMS:
            break
    return sorted(items, key=lambda i: int(i.key))


def read_mo2(game: str, roots: dict) -> list[Item] | None:
    """Enabled mods of the selected profile of a Mod Organizer 2 instance made for this game."""
    for local in roots.get("local", []):
        base = local / "ModOrganizer"
        try:
            instances = [p for p in base.iterdir() if p.is_dir()]
        except OSError:
            continue
        for instance in instances:
            ini = _lines(instance / "ModOrganizer.ini", 400)
            name = next((l.split("=", 1)[1].strip() for l in ini if l.casefold().startswith("gamename=")), "")
            if not name or name.casefold() != game.casefold():
                continue
            chosen = next((l.split("=", 1)[1].strip() for l in ini if l.casefold().startswith("selected_profile=")), "")
            chosen = re.sub(r"^@ByteArray\((.*)\)$", r"\1", chosen) or "Default"
            if re.search(r"[\\/]", chosen):
                continue
            lines = _lines(instance / "profiles" / chosen / "modlist.txt")
            if not lines:
                continue
            items = [Item("mo2", l[1:].strip().casefold(), l[1:].strip()) for l in lines
                     if l.startswith("+") and SAFE_NAME.fullmatch(l[1:].strip() or "\x00")]
            return items[:MAX_ITEMS]
    return None


def read_plugins(game: str, roots: dict) -> list[Item] | None:
    folder = PLUGIN_FOLDERS.get(game.casefold())
    if folder is None:
        return None
    for local in roots.get("local", []):
        path = local / folder / "plugins.txt"
        if path.is_file():
            items = []
            for line in _lines(path):
                line = line.strip()
                if line.startswith("*") and SAFE_NAME.fullmatch(line[1:].strip() or "\x00"):
                    items.append(Item("plugin", line[1:].strip().casefold(), line[1:].strip()))
            return items[:MAX_ITEMS]
    return None


def read_setup(game: str, app_id: str | None, library: str | None, roots: dict | None = None,
               now: datetime | None = None) -> Setup:
    roots = roots if roots is not None else default_roots()
    setup = Setup(game, made=(now or datetime.now()).strftime("%Y-%m-%d %H:%M"))
    for label, items in (("Steam Workshop", read_workshop(library or "", app_id or "")),
                         ("Mod Organizer 2", read_mo2(game, roots)),
                         ("Plugin list", read_plugins(game, roots))):
        if items is None:
            setup.notes.append(f"{label}: nothing found for this game")
        else:
            setup.read_any = True
            setup.items.extend(items)
            setup.notes.append(f"{label}: {len(items)} item{'s' if len(items) != 1 else ''}")
    for base in roots.get("roaming", []):
        if (base / "Vortex").is_dir():
            setup.notes.append("Vortex: its mod lists cannot be read yet")
            break
    return setup


# ------------------------------------------------------------------ the squad code
def make_code(setup: Setup) -> str:
    payload = {"v": 1, "g": setup.game[:120],
               "i": [[i.kind, i.key, i.label, i.stamp] for i in setup.items[:MAX_ITEMS]]}
    packed = zlib.compress(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"), 9)
    return CODE_PREFIX + base64.urlsafe_b64encode(packed).decode("ascii").rstrip("=")


def read_code(text: str) -> Setup:
    text = (text or "").strip()
    if not text.startswith(CODE_PREFIX) or len(text) > MAX_CODE_CHARS:
        raise ValueError("That is not a Squad Sync code. It should start with " + CODE_PREFIX)
    body = text[len(CODE_PREFIX):]
    try:
        raw = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        unpacker = zlib.decompressobj()
        data = unpacker.decompress(raw, MAX_UNPACKED)
        if unpacker.unconsumed_tail:
            raise ValueError("too large")
        payload = json.loads(data.decode("utf-8"))
    except (ValueError, zlib.error, UnicodeError):
        raise ValueError("That code is damaged or cut off. Ask your friend to copy it again.")
    if not isinstance(payload, dict) or payload.get("v") != 1 or not isinstance(payload.get("g"), str) \
            or not isinstance(payload.get("i"), list) or len(payload["i"]) > MAX_ITEMS:
        raise ValueError("That code is not one this version of Game Grave understands.")
    items = []
    for row in payload["i"]:
        if not (isinstance(row, list) and len(row) == 4 and all(isinstance(x, str) for x in row)):
            raise ValueError("That code has an entry Game Grave cannot read.")
        kind, key, label, stamp = row
        if kind not in KINDS or len(key) > 120 or len(label) > 120 or len(stamp) > 20 \
                or (kind == "workshop" and not key.isdigit()) or (stamp and not stamp.isdigit()):
            raise ValueError("That code has an entry Game Grave cannot read.")
        if kind == "workshop":
            label = f"Workshop item {key}"      # never show text from a code beside a Steam link
        items.append(Item(kind, key, label, stamp))
    return Setup(payload["g"][:120], items, ["From a squad code"], True, "")


# ------------------------------------------------------------------ compare
@dataclass
class Comparison:
    game: str
    same: list = field(default_factory=list)
    missing: list = field(default_factory=list)       # theirs, not yours
    different: list = field(default_factory=list)     # (theirs, yours)
    extra: list = field(default_factory=list)         # yours, not theirs
    comparable: bool = True
    summary: str = ""


def workshop_url(item: Item) -> str | None:
    return f"steam://url/CommunityFilePage/{item.key}" if item.kind == "workshop" and item.key.isdigit() else None


def compare(theirs: Setup, mine: Setup) -> Comparison:
    if theirs.game.casefold() != mine.game.casefold():
        raise ValueError(f"This code is for {theirs.game}, not {mine.game}.")
    result = Comparison(mine.game)
    if not theirs.items:
        result.comparable = False
        result.summary = "The setup you are comparing with has no readable mods, so there is nothing to match."
        return result
    if not mine.read_any:
        result.comparable = False
        result.summary = ("Game Grave could not read your mods for this game, so it will not guess. "
                          "It reads the Steam Workshop manifest, a Mod Organizer 2 profile and the Bethesda plugin list.")
        return result
    mine_by = {(i.kind, i.key.casefold()): i for i in mine.items}
    theirs_keys = set()
    for item in theirs.items:
        key = (item.kind, item.key.casefold())
        theirs_keys.add(key)
        have = mine_by.get(key)
        if have is None:
            result.missing.append(item)
        elif item.stamp and have.stamp and item.stamp != have.stamp:
            result.different.append((item, have))
        else:
            result.same.append(item)
    result.extra = [i for k, i in mine_by.items() if k not in theirs_keys]
    total = len(theirs.items)
    parts = [f"You match {len(result.same)} of {total}"]
    if result.missing:
        parts.append(f"{len(result.missing)} missing")
    if result.different:
        parts.append(f"{len(result.different)} updated at a different time")
    if result.extra:
        parts.append(f"{len(result.extra)} extra on your side")
    result.summary = ", ".join(parts) + "."
    if result.extra:
        result.summary += " Extras may be harmless or may break co-op; Game Grave cannot tell."
    if not (result.missing or result.different):
        result.summary = ("Nothing is missing or out of step. " + result.summary)
    return result


# ------------------------------------------------------------------ snapshots (the list, never the files)
def squad_dir() -> Path:
    import core
    return core.config_dir() / "squadsync"


def _slug(game: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", game).strip("-")[:40] or "game"


def save_snapshot(setup: Setup, root: Path | None = None, now: datetime | None = None) -> Path:
    root = Path(root) if root else squad_dir()
    (root / "snapshots").mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    path = root / "snapshots" / f"{_slug(setup.game)}-{stamp}.json"
    payload = {"v": 1, "game": setup.game, "made": setup.made or stamp,
               "items": [[i.kind, i.key, i.label, i.stamp] for i in setup.items[:MAX_ITEMS]]}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, path)
    return path


def list_snapshots(game: str, root: Path | None = None) -> list[tuple[Path, str, int]]:
    folder = (Path(root) if root else squad_dir()) / "snapshots"
    found = []
    try:
        files = sorted(folder.glob(f"{_slug(game)}-*.json"), reverse=True)[:20]
    except OSError:
        return []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("game", "").casefold() == game.casefold():
                found.append((path, str(data.get("made", "")), len(data.get("items", []))))
        except (OSError, ValueError, AttributeError):
            continue
    return found


def load_snapshot(path: Path) -> Setup:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        items = [Item(*row) for row in data["items"] if len(row) == 4 and row[0] in KINDS]
        return Setup(str(data["game"])[:120], items[:MAX_ITEMS], ["From a snapshot"], True, str(data.get("made", "")))
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError("That snapshot could not be read.")
