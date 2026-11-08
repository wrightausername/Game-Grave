"""Read-only discovery of game-related storage outside game installs.

Metadata only: sizes, file counts and modified dates. Nothing is opened, changed or removed here.
Linked or redirected folders are never entered. Removal lives in other_storage_actions and
applies only to what can be re-verified file by file.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import stat
import time

from gg_desktop.models import _path_key

REPARSE = 0x400
MAX_ENTRIES = 250_000
MAX_CHILDREN = 400
MAX_FILES = 200  # files one cleanup run may move to the Recycle Bin

DRIVER_NOTE = ("Shared by every game on this PC. Game Grave does not remove it. Windows Disk Cleanup or "
               "your graphics driver's own tool can clear it; games rebuild it, which can mean slower first loads.")
LAUNCHER_NOTE = ("Owned by the launcher; close the launcher before clearing it. Game Grave can move up to 200 "
                 "verified files per run to the Recycle Bin. Bigger caches are review only: use the launcher's own settings.")
LOG_NOTE = ("Diagnostic files. Keep them while you are troubleshooting. Game Grave can move up to 200 verified "
            "files per run to the Recycle Bin after you confirm. Bigger folders are review only.")
SETTINGS_NOTE = ("Settings and, in some games, saves. Game Grave never removes these. "
                 "Use Protect to record that explicitly.")
STAGING_NOTE = ("May hold an active or interrupted update. Never remove it while the launcher is downloading. "
                "Game Grave does not remove it here.")
SHADER_NOTE = ("Steam rebuilds this when the game needs it, which can mean a longer first load or brief stutter. "
               "Game Grave's protection rules keep anything inside a Steam library's steamapps folder out of reach, "
               "so clear it from Steam itself if you want it gone.")
LOOSE_NOTE = ("A single file found by the last PC scan. Age and file type do not show it is unused. "
              "Review it in Old Files, where removal is checked file by file.")


@dataclass(frozen=True)
class Spot:
    name: str
    path: Path
    category: str
    source: str
    summary: str
    evidence: str
    note: str
    kind: str = "review"      # review | clearable | settings | steam-shader
    children: bool = False    # every immediate folder becomes its own item
    match: bool = False       # the last path part is a wildcard pattern


@dataclass(frozen=True)
class Measure:
    bytes: int
    files: int
    newest: float | None
    partial: bool
    skipped: int


@dataclass(frozen=True)
class StorageEntry:
    key: str
    name: str
    path: str
    category: str
    related: str
    size: int
    items: int
    newest: float | None
    partial: bool
    summary: str
    evidence: str
    note: str
    kind: str = "review"
    app_id: str = ""
    old_file: object = None

    @property
    def cleanable(self):
        """Launcher cache or log folders small enough to verify file by file. Never settings or driver caches."""
        return self.kind == "clearable" and not self.partial and 0 < self.items <= MAX_FILES

    @property
    def protected_kind(self):
        return self.kind == "settings"

    @property
    def badge(self):
        return "Protected" if self.protected_kind else "Reviewable" if self.cleanable else "Review only"


@dataclass
class StorageReport:
    entries: list = field(default_factory=list)
    scanned_at: float = 0.0
    partial: bool = False
    problems: list = field(default_factory=list)
    checked: int = 0

    def summary(self):
        total = sum(e.size for e in self.entries)
        text = f"{len(self.entries):,} storage items found in {self.checked} known locations"
        if self.partial:
            text += "; some very large folders were only partly measured"
        return text + f" ({total:,} bytes reported)"


def path_key(path):
    return _path_key(path)


def _attrs(info):
    return getattr(info, "st_file_attributes", 0)


def normal_dir(path):
    try:
        info = os.lstat(path)
    except OSError:
        return False
    return stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode) and not _attrs(info) & REPARSE


def measure(path, canceled=lambda: False, limit=None):
    """Total reported bytes and files beneath a folder without entering links or reparse points."""
    limit = MAX_ENTRIES if limit is None else limit
    total = files = skipped = visited = 0
    newest, partial = None, False
    stack = [os.fspath(path)]
    while stack:
        if canceled():
            raise InterruptedError("Scan canceled")
        current = stack.pop()
        try:
            scan = os.scandir(current)
        except OSError:
            skipped += 1
            continue
        with scan:
            for entry in scan:
                visited += 1
                if visited > limit:
                    partial = True
                    stack.clear()
                    break
                try:
                    info = entry.stat(follow_symlinks=False)
                except OSError:
                    skipped += 1
                    continue
                if entry.is_symlink() or _attrs(info) & REPARSE:
                    skipped += 1
                    continue
                if stat.S_ISDIR(info.st_mode):
                    stack.append(entry.path)
                elif stat.S_ISREG(info.st_mode):
                    total += info.st_size
                    files += 1
                    newest = info.st_mtime if newest is None else max(newest, info.st_mtime)
                else:
                    skipped += 1
    return Measure(total, files, newest, partial, skipped)


def _home(env, home):
    if home is not None:
        return Path(home)
    for name in ("USERPROFILE", "HOME"):
        if env.get(name):
            return Path(env[name])
    return Path.home()


def known_spots(env=None, home=None, steam_roots=(), libraries=()):
    env = dict(os.environ if env is None else env)
    home = _home(env, home)
    local = Path(env.get("LOCALAPPDATA") or home / "AppData" / "Local")
    data = Path(env.get("PROGRAMDATA") or "C:/ProgramData")
    docs = home / "Documents"
    shader = [
        ("DirectX Shader Cache", local / "D3DSCache", "Windows / DirectX", "Compiled shaders for DirectX games"),
        ("NVIDIA DirectX Cache", local / "NVIDIA" / "DXCache", "NVIDIA driver", "Compiled shaders from the NVIDIA driver"),
        ("NVIDIA OpenGL Cache", local / "NVIDIA" / "GLCache", "NVIDIA driver", "OpenGL and Vulkan shader cache"),
        ("NVIDIA Shared Shader Cache", data / "NVIDIA Corporation" / "NV_Cache", "NVIDIA driver", "Shared NVIDIA shader cache"),
        ("AMD DirectX Cache", local / "AMD" / "DxCache", "AMD driver", "Compiled shaders from the AMD driver"),
        ("AMD OpenGL Cache", local / "AMD" / "GLCache", "AMD driver", "OpenGL shader cache"),
        ("AMD Vulkan Cache", local / "AMD" / "VkCache", "AMD driver", "Vulkan shader cache"),
        ("Intel Shader Cache", local / "Intel" / "ShaderCache", "Intel driver", "Compiled shaders from the Intel driver"),
    ]
    spots = [Spot(n, p, "Shader Cache", s, summary, f"Known {s} shader cache location.", DRIVER_NOTE)
             for n, p, s, summary in shader]
    caches = [
        ("Steam Web Cache", local / "Steam" / "htmlcache", "Steam", "Steam client browser cache", False),
        ("Epic Launcher Web Cache", local / "EpicGamesLauncher" / "Saved" / "webcache*", "Epic Games", "Epic launcher browser cache", True),
        ("Battle.net Cache", local / "Battle.net" / "Cache", "Battle.net", "Battle.net launcher cache", False),
        ("Ubisoft Connect Cache", local / "Ubisoft Game Launcher" / "cache", "Ubisoft Connect", "Ubisoft launcher cache", False),
        ("GOG Galaxy Web Cache", data / "GOG.com" / "Galaxy" / "webcache", "GOG Galaxy", "GOG launcher browser cache", False),
        ("EA app Cache", local / "Electronic Arts" / "EA Desktop" / "cache", "EA app", "EA launcher cache", False),
        ("FiveM Cache", local / "FiveM" / "FiveM.app" / "data" / "cache", "FiveM", "FiveM client cache", False),
    ]
    spots += [Spot(n, p, "Caches", s, summary, f"Known {s} cache location.", LAUNCHER_NOTE, kind="clearable", match=m)
              for n, p, s, summary, m in caches]
    logs = [
        ("Windows Crash Dumps", local / "CrashDumps", "Windows", "Crash dumps from all applications"),
        ("Epic Launcher Logs", local / "EpicGamesLauncher" / "Saved" / "Logs", "Epic Games", "Epic launcher log files"),
        ("Epic Crash Reports", local / "EpicGamesLauncher" / "Saved" / "Crashes", "Epic Games", "Epic launcher crash reports"),
        ("Battle.net Logs", local / "Battle.net" / "Logs", "Battle.net", "Battle.net launcher logs"),
        ("Ubisoft Connect Logs", local / "Ubisoft Game Launcher" / "logs", "Ubisoft Connect", "Ubisoft launcher logs"),
        ("GOG Galaxy Logs", data / "GOG.com" / "Galaxy" / "logs", "GOG Galaxy", "GOG launcher logs"),
    ]
    for root in steam_roots:
        logs += [("Steam Logs", Path(root) / "logs", "Steam", "Steam client logs"),
                 ("Steam Crash Dumps", Path(root) / "dumps", "Steam", "Steam client crash dumps")]
    spots += [Spot(n, p, "Logs / Reports", s, summary, f"Known {s} log location.", LOG_NOTE, kind="clearable")
              for n, p, s, summary in logs]
    spots += [
        Spot("My Games", docs / "My Games", "Config / Settings", "Documents\\My Games", "Game settings and saves",
             "Each game folder inside Documents\\My Games.", SETTINGS_NOTE, kind="settings", children=True),
        Spot("Saved Games", home / "Saved Games", "Config / Settings", "Saved Games", "Game saves and settings",
             "Each game folder inside Saved Games.", SETTINGS_NOTE, kind="settings", children=True),
    ]
    for library in libraries:
        apps = Path(library) / "steamapps"
        spots += [
            Spot("Steam Shader Cache", apps / "shadercache", "Shader Cache", "Steam", "Steam shader cache for one game",
                 "Folder named for a Steam app ID inside this library's shadercache.", SHADER_NOTE,
                 kind="steam-shader", children=True),
            Spot("Steam Downloading", apps / "downloading", "Temporary Files", "Steam", "Steam update staging",
                 "Steam's staging folder for updates in progress.", STAGING_NOTE),
            Spot("Steam Temp", apps / "temp", "Temporary Files", "Steam", "Steam temporary files",
                 "Steam's temporary folder inside this library.", STAGING_NOTE),
        ]
    return spots


def _expand(spot, canceled):
    """(folder, display name) pairs for one known location. Unsafe or missing folders yield nothing."""
    base = spot.path
    if spot.match:
        parent = base.parent
        if not normal_dir(parent):
            return []
        try:
            found = sorted(parent.glob(base.name))
        except OSError:
            return []
        return [(p, p.name) for p in found if normal_dir(p)]
    if not normal_dir(base):
        return []
    if not spot.children:
        return [(base, spot.name)]
    output = []
    try:
        with os.scandir(base) as scan:
            for entry in scan:
                if canceled():
                    raise InterruptedError("Scan canceled")
                if len(output) >= MAX_CHILDREN:
                    break
                child = Path(entry.path)
                if entry.is_dir(follow_symlinks=False) and normal_dir(child):
                    output.append((child, entry.name))
    except OSError:
        return []
    return sorted(output, key=lambda pair: pair[1].casefold())


def discover(*, env=None, home=None, steam_roots=(), libraries=(), games=(), canceled=lambda: False,
             progress=lambda text: None, now=time.time):
    """Measure every known location that exists. Missing locations are simply absent."""
    env = dict(os.environ if env is None else env)
    names = {str(g.app_id): g for g in games if str(getattr(g, "app_id", "")).isdecimal()}
    spots = known_spots(env, home, steam_roots, libraries)
    report = StorageReport(checked=len(spots))
    seen = set()
    for index, spot in enumerate(spots, 1):
        if canceled():
            raise InterruptedError("Scan canceled")
        progress(f"Checking {spot.name} ({index} of {len(spots)})")
        for folder, name in _expand(spot, canceled):
            key = path_key(folder)
            if key in seen:
                continue
            seen.add(key)
            try:
                found = measure(folder, canceled)
            except InterruptedError:
                raise
            except OSError as exc:
                report.problems.append(f"{folder}: {exc}")
                continue
            if found.files == 0 and not found.partial:
                continue
            related, evidence, app_id, title, kind = spot.source, spot.evidence, "", name, spot.kind
            if spot.kind == "steam-shader":
                game = names.get(name) if name.isdecimal() else None
                if game is not None:
                    related, title, app_id = game.name, game.name + " Shader Cache", name
                    evidence = f"Steam shader cache for {game.name} (app ID {name}), a game installed in this Steam library."
                else:
                    related, title = "No installed game", f"Steam app {name} Shader Cache"
                    evidence = (f"Steam shader cache for app ID {name}. No installed game with this ID was found "
                                "in the scanned Steam libraries.")
            report.entries.append(StorageEntry(
                key, title, str(folder), spot.category, related, found.bytes, found.files, found.newest,
                found.partial, spot.summary, evidence, spot.note, kind, app_id))
            report.partial = report.partial or found.partial
    report.entries.sort(key=lambda e: (-e.size, e.name.casefold()))
    report.scanned_at = now()
    return report


def from_inventory(items):
    """Entries from the last PC scan (mod-radar cache folders and loose log, temp and config files)."""
    output = []
    for item in items:
        loose = item.old_file is not None
        output.append(StorageEntry(
            item.key, item.name, item.path, item.category, item.source, item.size, item.items,
            getattr(item.old_file, "modified", None), False,
            "Loose file from the last PC scan" if loose else "Folder from the last PC scan",
            item.evidence, LOOSE_NOTE if loose else LAUNCHER_NOTE, "review", "", item.old_file))
    return output


def merge(scanned, inventory_entries):
    """Scan results first; inventory entries only where they do not overlap a scanned folder."""
    keys = [e.key for e in scanned]
    output = list(scanned)
    for entry in inventory_entries:
        key = entry.key
        if any(key == k or key.startswith(k.rstrip("\\") + "\\") or k.startswith(key.rstrip("\\") + "\\") for k in keys):
            continue
        output.append(entry)
    return output


def category_total(entries, category):
    return sum(e.size for e in entries if e.category == category)

