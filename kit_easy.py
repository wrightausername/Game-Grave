"""Easy Resurrection Kit setup for ONE game. Pure logic: no Qt, nothing is written, no network.

It turns what Game Grave already knows (the install folder, save-scanner matches, folders the owner linked in Game DNA,
verified Mod Organizer 2 profiles, the game's Windows load-order file, the Steam manifest) into a short list of parts the
owner can tick, with sizes. The kit itself is made by `resurrection_v2.create_complete_kit`.

Honest rules kept from Game DNA: a save or settings folder is never matched by a name that merely looks right. It is
offered only when the save scanner labeled it with this exact game, or the owner linked it, and the screen says which.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import shutil
import stat

from resurrection_v2 import ORIGIN_TOKENS, _ordinary_ancestry, documents_dir

# Load-order files that live outside the game folder. Only files that exist are offered.
# game name (casefolded, no trademark signs) -> (Local AppData sub-folder, file names)
LOAD_ORDER_FILES = {
    "the elder scrolls v: skyrim special edition": ("Skyrim Special Edition", ("plugins.txt", "loadorder.txt")),
    "the elder scrolls v: skyrim": ("Skyrim", ("plugins.txt", "loadorder.txt")),
    "the elder scrolls v: skyrim vr": ("Skyrim VR", ("plugins.txt", "loadorder.txt")),
    "the elder scrolls iv: oblivion": ("Oblivion", ("plugins.txt",)),
    "the elder scrolls iv: oblivion game of the year edition": ("Oblivion", ("plugins.txt",)),
    "fallout 4 vr": ("Fallout4VR", ("plugins.txt", "loadorder.txt")),
    "fallout 3 - game of the year edition": ("Fallout3", ("plugins.txt",)),
    "fallout 4": ("Fallout4", ("plugins.txt", "loadorder.txt")),
    "fallout 3": ("Fallout3", ("plugins.txt",)),
    "fallout: new vegas": ("FalloutNV", ("plugins.txt",)),
    "starfield": ("Starfield", ("plugins.txt",)),
    "baldur's gate 3": ("Larian Studios\\Baldur's Gate 3\\PlayerProfiles\\Public", ("modsettings.lsx",)),
}


@dataclass
class Part:
    role: str                      # Game, Saves, Configs, Profiles, Mods, LoadOrder, Launcher
    title: str
    why: str                       # one honest sentence: where it came from
    source: object                 # a folder Path, or a list of file Paths for LoadOrder / Launcher
    files: int = 0
    bytes: int = 0
    origin: str | None = None      # templated original place, e.g. %LOCALAPPDATA%\Skyrim Special Edition
    on: bool = True
    problem: str = ""              # why it cannot be included right now
    manager: str = ""              # "MO2" / "Vortex" / ""
    profile: str = ""


@dataclass
class Plan:
    game: str
    parts: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def chosen(self):
        return [p for p in self.parts if p.on and not p.problem]

    @property
    def total_bytes(self):
        return sum(p.bytes for p in self.chosen())

    @property
    def total_files(self):
        return sum(p.files for p in self.chosen())


# ------------------------------------------------------------------ small helpers
def _norm(path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path))).replace("/", "\\").rstrip("\\").casefold()


def _inside(child, parent) -> bool:
    c, p = _norm(child), _norm(parent)
    return c == p or c.startswith(p + "\\")


def _overlaps(a, b) -> bool:
    return _inside(a, b) or _inside(b, a)


def clean_name(name: str) -> str:
    return re.sub(r"[™®©]", "", str(name or "")).strip().casefold()


def safe_file_label(name: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9 _.-]+", "_", str(name)).strip(" ._")[:60]
    return clean or "Game"


def templatize(path, environ=None) -> str | None:
    """A path under Documents, Local AppData, Roaming AppData or the user profile, written with a token so a kit never
    stores a user name. None when the path is somewhere else (a custom drive, say)."""
    env = os.environ if environ is None else environ
    profile = env.get("USERPROFILE")
    roots = []
    documents = documents_dir(environ)   # the real Documents folder, which OneDrive may have moved
    if documents:
        roots.append(("%DOCUMENTS%", documents))
    if env.get("LOCALAPPDATA"):
        roots.append(("%LOCALAPPDATA%", Path(env["LOCALAPPDATA"])))
    if env.get("APPDATA"):
        roots.append(("%APPDATA%", Path(env["APPDATA"])))
    if profile:
        roots.append(("%USERPROFILE%", Path(profile)))
    for token, root in roots:
        if token in ORIGIN_TOKENS and _inside(path, root):
            rest = os.path.relpath(os.fspath(path), os.fspath(root)).replace("/", "\\")
            return token if rest in (".", "") else token + "\\" + rest
    return None


def measure_folder(path):
    """(files, bytes, links) for a folder. Links and junctions are counted but never followed."""
    files = size = links = 0
    for here, folders, names in os.walk(path, followlinks=False):
        for name in list(folders):
            try:
                info = (Path(here) / name).lstat()
            except OSError:
                links += 1
                continue
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                links += 1
        for name in names:
            try:
                info = (Path(here) / name).lstat()
            except OSError:
                continue
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                links += 1
            elif stat.S_ISREG(info.st_mode):
                files += 1
                size += info.st_size
    return files, size, links


def measure_files(paths):
    files = size = 0
    for path in paths:
        try:
            files += 1
            size += Path(path).stat().st_size
        except OSError:
            files -= 1
    return files, size


# ------------------------------------------------------------------ the plan
def build_plan(game, *, saves=(), links=(), discovery=None, environ=None, measure=measure_folder) -> Plan:
    """Parts for one game. `saves` are save-scanner items (game, path). `links` are the owner's Game DNA links
    ({"category", "path"}). `discovery` is the result of `kit_discovery.discover_setup` (verified MO2 / Vortex)."""
    title = str(getattr(game, "name", "") or "").strip()
    install = str(getattr(game, "install_path", "") or "")
    if not title or not install:
        raise ValueError("Choose a game with a recorded install folder.")
    env = os.environ if environ is None else environ
    plan = Plan(title)
    root = Path(install)

    # 1. The whole installation.
    if root.is_dir():
        files, size, link_count = measure(root)
        part = Part("Game", "Game install", f"The whole install folder, read by {getattr(game, 'launcher', 'your launcher')}: "
                    + str(getattr(game, "install_evidence", "") or "recorded install"), root, files, size)
        if link_count:
            part.problem = (f"The install folder holds {link_count} link or junction item"
                            f"{'s' if link_count != 1 else ''}. A kit does not follow links, so it can't be made with this part.")
        if not _ordinary_ancestry(root, directory=True):
            part.problem = "The install folder sits behind a link or redirected folder."
        plan.parts.append(part)
    else:
        plan.notes.append("The install folder was not found on disk, so only the other parts can be saved.")

    # 2. Steam's own manifest, so Steam recognises the restored folder.
    app_id = str(getattr(game, "app_id", "") or "")
    if str(getattr(game, "launcher", "")).casefold() == "steam" and app_id.isdigit() and root.parent.name.casefold() == "common" \
            and root.parent.parent.name.casefold() == "steamapps":
        manifest = root.parent.parent / f"appmanifest_{app_id}.acf"
        if manifest.is_file() and _ordinary_ancestry(manifest):
            f, b = measure_files([manifest])
            plan.parts.append(Part("Launcher", "Steam install record", "Lets Steam see the restored folder as installed.", [manifest], f, b))

    # 3. Saves: exact-label scanner match or an owner link; never a name guess.
    owner_saves = [str(x["path"]) for x in links if x.get("category") == "Saves"]
    scanner = [str(getattr(s, "path", "")) for s in saves if str(getattr(s, "game", "")).strip().casefold() == title.casefold()]
    picked, why = None, ""
    for candidate, reason in [(p, "You linked this folder as this game's saves in Game DNA.") for p in owner_saves] + \
                             [(p, f"The save scanner labeled this folder {title}. Individual files are not verified.") for p in scanner]:
        if candidate and Path(candidate).is_dir() and not _overlaps(candidate, install):
            picked, why = candidate, reason
            break
    if picked:
        f, b, n = measure(Path(picked))
        part = Part("Saves", "Saves", why, Path(picked), f, b, origin=templatize(picked, env))
        if n:
            part.problem = "This folder holds links or junctions, which a kit does not follow."
        plan.parts.append(part)
        extra = len({_norm(p) for p in owner_saves + scanner if p}) - 1
        if extra > 0:
            plan.notes.append(f"{extra} other possible save folder{'s were' if extra != 1 else ' was'} found. Use Choose folders yourself to pick a different one.")
    else:
        plan.notes.append("No save folder is linked to this game yet, so saves are not included. Link one in Game DNA to add it. Saves are never matched by name.")

    # 4. Settings the owner linked.
    for item in links:
        if item.get("category") == "Configs / Settings" and Path(item["path"]).is_dir() and not _overlaps(item["path"], install):
            f, b, n = measure(Path(item["path"]))
            part = Part("Configs", "Settings", "You linked this folder as this game's settings in Game DNA.", Path(item["path"]),
                        f, b, origin=templatize(item["path"], env))
            if n:
                part.problem = "This folder holds links or junctions, which a kit does not follow."
            plan.parts.append(part)
            break

    # 5. Mod manager load order and mods (verified Mod Organizer 2 / Vortex), then folders the owner linked.
    candidates = (discovery or {}).get("candidates", [])
    have = {p.role for p in plan.parts}
    for role, label in (("Profiles", "Load order and profile"), ("Mods", "Mod manager mods")):
        found = next((c for c in candidates if c["role"] == role and c.get("default")), None)
        if found and not _overlaps(found["path"], install):
            f, b, n = measure(Path(found["path"]))
            part = Part(role, label, found["evidence"], Path(found["path"]), f, b, manager=found.get("manager", ""),
                        profile=found.get("profile", ""))
            if n:
                part.problem = "This folder holds links or junctions, which a kit does not follow."
            plan.parts.append(part)
            have.add(role)
    if "Mods" not in have:
        for item in links:
            if item.get("category") == "Mods / Addons" and Path(item["path"]).is_dir() and not _overlaps(item["path"], install):
                f, b, n = measure(Path(item["path"]))
                part = Part("Mods", "Mods outside the install", "You linked this folder as this game's mods in Game DNA.",
                            Path(item["path"]), f, b)
                if n:
                    part.problem = "This folder holds links or junctions, which a kit does not follow."
                plan.parts.append(part)
                break

    # 6. The game's own load-order file in Local AppData.
    entry = LOAD_ORDER_FILES.get(clean_name(title))
    local = env.get("LOCALAPPDATA")
    if entry and local:
        folder = Path(local).joinpath(*entry[0].split("\\"))
        found_files = [folder / name for name in entry[1] if (folder / name).is_file() and _ordinary_ancestry(folder / name)]
        if found_files:
            f, b = measure_files(found_files)
            plan.parts.append(Part("LoadOrder", "Plugin load order", f"{', '.join(x.name for x in found_files)} from the game's Windows folder.",
                                   found_files, f, b, origin=templatize(folder, env)))
    # Two parts can never hold the same folder (a settings folder that contains the saves folder, say). The engine
    # refuses that, so say it here and keep the first one.
    kept = []
    for part in plan.parts:
        if not part.files and not part.problem:
            part.problem = "This folder has no files in it, so there is nothing to save."
        folder = None if isinstance(part.source, (list, tuple)) else part.source
        if folder is not None and not part.problem:
            clash = next((other for other in kept if _overlaps(folder, other.source)), None)
            if clash is not None:
                part.problem = f"This folder overlaps the {clash.title} folder, so it can't be a separate part of the same kit."
                continue
            kept.append(part)
    if not any(p.role in ("Profiles", "LoadOrder") for p in plan.parts):
        plan.notes.append("No load-order file was found for this game. If you use a mod manager Game Grave can't read yet, the mods inside the install are still saved.")
    return plan


def to_sources(plan: Plan):
    """(sources, origins, manager_context) for `create_complete_kit`, from the ticked parts."""
    sources, origins, manager = {}, {}, None
    for part in plan.chosen():
        sources[part.role] = part.source
        if part.origin:
            origins[part.role] = part.origin
        if part.manager == "MO2" and part.role == "Profiles":
            manager = {"kind": "MO2", "profile": part.profile, "auto_discovered": True}
        elif part.manager == "Vortex" and manager is None:
            manager = {"kind": "Vortex", "auto_discovered": True}
    return sources, origins, manager


def default_destination(game_name, folder, *, exists=lambda p: Path(p).exists()):
    """A new ZIP name inside `folder`: `<Game> Kit.zip`, then `<Game> Kit 2.zip` and so on."""
    base = safe_file_label(game_name) + " Kit"
    candidate = Path(folder) / (base + ".zip")
    number = 2
    while exists(candidate) or exists(str(candidate) + ".ggkit.json"):
        candidate = Path(folder) / f"{base} {number}.zip"
        number += 1
    return candidate


def free_bytes(folder) -> int | None:
    """Free space for the nearest existing folder at or above `folder`."""
    probe = Path(folder)
    while not probe.exists():
        if probe.parent == probe:
            return None
        probe = probe.parent
    try:
        return shutil.disk_usage(probe).free
    except OSError:
        return None


def readiness(plan: Plan, destination_folder) -> dict:
    """What the Create button needs: something ticked, and enough free space. Never a promise about the game itself."""
    chosen = plan.chosen()
    free = free_bytes(destination_folder)
    need = plan.total_bytes
    if not chosen:
        return {"ok": False, "why": "Tick at least one part.", "need": 0, "free": free}
    if free is not None and free < need + 64 * 1024 ** 2:
        return {"ok": False, "why": "Not enough free space in that folder. Choose another drive.", "need": need, "free": free}
    return {"ok": True, "why": "", "need": need, "free": free}
