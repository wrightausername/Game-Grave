"""Game Grave core scanners. Read-only except explicit recycle_file()."""
from __future__ import annotations

import ctypes
import csv
import uuid
import json
import os
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

APP_NAME = "Game Grave"
TASK_NAME = "DustOff Weekly Cleanup"  # Legacy task ID retained so old scheduled rule is manageable
SCAN_EXCLUDED = {".git", "node_modules", "$recycle.bin", "system volume information", "windows", "appdata"}
AUTO_BASE_EXTENSIONS = {".tmp", ".log"}
AUTO_EXTRA_EXTENSIONS = {".zip", ".7z", ".rar", ".iso", ".msi", ".exe"}
GAME_AGE_OPTIONS = (30, 60, 90, 180, 365, 730)


def config_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_NAME


def downloads_dir() -> Path:
    return Path.home() / "Downloads"


def default_settings() -> dict:
    return {
        "game_stale_days": 180,
        "files_stale_days": 180,
        "graveyard_days": 365,
        "graveyard_sort": "Size",
        "graveyard_order": "Descending",
        "graveyard_category": "All types",
        "graveyard_status": "All findings",
        "graveyard_min_size": "Any size",
        "graveyard_search": "",
        "graveyard_saved_views": {},
        "game_sort": "Oldest first",
        "mod_sort": "Largest first",
        "files_sort": "Largest first",
        "scan_folder": str(downloads_dir()),
        "steam_extra_roots": [],
        "other_library_roots": [],
        "mod_extra_roots": [],  # optional Vortex/MO2/custom mod storage locations
        "auto_enabled": False,
        "auto_days": 365,
        "auto_include_archives": False,
        "ui_theme": "dark",
        "ui_accent": "teal",
        "ui_custom_accent": "#50DCC5",
        "ui_presets": {},
        "ui_scale": "normal",
        "ui_layout": "simple",
        "never_touch": [],
        "scan_on_launch": False,
        "save_review_paths": [],
        "graveyard_watchlist": [],
    }


def load_settings() -> dict:
    result = default_settings()
    try:
        config = config_dir() / "settings.json"
        if not config.exists():
            config = config_dir().parent / "Game Grave" / "settings.json"
        data = json.loads(config.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for key in result:
                if key in data and isinstance(data[key], type(result[key])):
                    result[key] = data[key]
    except (OSError, ValueError, TypeError):
        pass
    return result


def save_settings(settings: dict) -> None:
    directory = config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "settings.json"
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    tmp.replace(target)


def log_event(kind: str, details: str, *, session_id: str | None = None,
              path: str | None = None, size_bytes: int | None = None,
              result: str | None = None, source: str | None = None,
              recovery_id: str | None = None) -> None:
    """Append local audit facts. Every confirmed removal is recorded individually.

    No log operation represents the Recycle Bin as genuinely freed disk space.
    """
    try:
        config_dir().mkdir(parents=True, exist_ok=True)
        record = {"date": datetime.now().astimezone().isoformat(timespec="seconds"),
                  "kind": kind, "details": str(details)}
        for key, value in (("session_id", session_id), ("path", path),
                           ("size_bytes", size_bytes), ("result", result),
                           ("source", source), ("recovery_id", recovery_id)):
            if value is not None:
                record[key] = value
        with (config_dir() / "activity.log").open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def get_activity(limit: int = 1500) -> list[dict]:
    """Read local audit entries in newest-first order; skip incomplete/corrupt records."""
    try:
        lines = (config_dir() / "activity.log").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    events = []
    for line in reversed(lines):
        try:
            event = json.loads(line)
            if isinstance(event, dict) and isinstance(event.get("kind"), str):
                events.append(event)
                if len(events) >= limit:
                    break
        except (ValueError, TypeError):
            continue
    return events


def friendly_activity(event: dict) -> dict:
    """Present the local audit trail as plain English without claiming unverified outcomes."""
    kind = str(event.get("kind", ""))
    details = str(event.get("details", ""))
    timestamp = str(event.get("date", ""))
    try:
        display_time = datetime.fromisoformat(timestamp).strftime("%b %d, %Y  %I:%M %p")
    except ValueError:
        display_time = timestamp.replace("T", " ")[:19]
    title, status, explanation = {
        "Scan completed": ("Storage scan completed", "Done", "Game Grave checked your selected game libraries and file folder. Nothing was deleted."),
        "Steam uninstall opened": ("Steam uninstall requested", "Needs review", "Steam was opened to request an uninstall. Game Grave cannot confirm removal; you must approve it in Steam."),
        "Manual recycled": ("File moved to Recycle Bin", "Done", "You selected this file for removal. It may be restorable from Windows Recycle Bin until emptied."),
        "Auto recycled": ("Automatic cleanup recycled file", "Done", "A file matching your approved Downloads cleanup rules was sent to Recycle Bin."),
        "Cleanup skipped": ("File skipped during cleanup", "Skipped", "Game Grave did not recycle this file. Review the recorded reason below."),
        "Automatic cleanup": ("Automatic cleanup finished", "Done", "Game Grave checked files against your approved automatic cleanup rules."),
        "Automation enabled": ("Weekly cleanup enabled", "Settings", "The Windows scheduled task was created to use your approved automatic cleanup rules."),
        "Automation disabled": ("Weekly cleanup disabled", "Settings", "Game Grave automatic cleanup was switched off."),
        "Scan failed": ("Storage scan could not finish", "Needs review", "The scan ended with an error. No file was removed by this scan."),
        "Cleanup preview": ("Automatic cleanup previewed", "Preview", "This was only a preview. No file was removed."),
        "Mod folder scan": ("Game folder scan completed", "Done", "Read-only inspection of mod indicators and unmatched Steam folders. Nothing was deleted."),
        "Mod inventory completed": ("Game and mod inventory completed", "Done", "Game Grave checked installed gaming content. Nothing was deleted."),
        "Cleanup started": ("Cleanup review started", "Preview", "Selected items were reviewed before any removal."),
        "Cleanup finished": ("Cleanup finished", "Done", "All recorded results below describe what was recycled or skipped. Files sent to Recycle Bin may still occupy disk space."),
        "Cleanup reviewed": ("Item reviewed", "Preview", "This item was examined, not removed."),
        "Restored from Recycle Bin": ("File restored", "Done", "Windows reported a successful restore to the original path."),
    }.get(kind, (kind or "Activity", "Info", "This is a recorded Game Grave event."))
    if kind == "Automatic cleanup" and ("skipped" in details.lower() or "failed" in details.lower()):
        title, status = "Automatic cleanup could not finish", "Needs review"
    name = Path(event.get("path") or details).name if kind in {"Manual recycled", "Auto recycled", "Restored from Recycle Bin"} else ""
    if event.get("path"):
        details = (f"File: {event['path']}" +
                   (f"\nApparent size: {human_size(event['size_bytes'])}" if isinstance(event.get("size_bytes"), int) else "") +
                   (f"\nSource: {event['source']}" if event.get("source") else "") +
                   (f"\nRecovery ID: {event['recovery_id']}" if event.get("recovery_id") else "") +
                   f"\nResult: {event.get('result') or kind}")
    return {"date": display_time, "status": status, "title": title,
            "summary": name or details, "explanation": explanation,
            "details": details, "kind": kind, "timestamp": timestamp}


def _csv_safe(value: str) -> str:
    # Excel and other spreadsheet programs may interpret untrusted filenames as formulas.
    value = str(value)
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def export_activity_csv(path: Path, events: list[dict]) -> int:
    """Export a readable local report. Never send it over a network."""
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(["Date", "Result", "What happened", "Details", "Explanation"])
        for event in events:
            item = friendly_activity(event)
            writer.writerow([_csv_safe(item[k]) for k in ("date", "status", "title", "details", "explanation")])
    return len(events)


def _tokens(source: str) -> list[str]:
    """Tokenize Valve KeyValues text, honoring quoted strings, comments and braces."""
    pattern = re.compile(r'\s+|//[^\r\n]*|"(?:\\.|[^"\\])*"|[{}]|[^\s{}"]+')
    out = []
    for m in pattern.finditer(source.lstrip("\ufeff")):
        item = m.group()
        if not item or item.isspace() or item.startswith("//"):
            continue
        if item.startswith('"') and item.endswith('"'):
            item = re.sub(r'\\(["\\])', lambda match: match.group(1), item[1:-1])
        out.append(item)
    return out


def parse_vdf(source: str) -> dict:
    """Parse text VDF into nested dict. Key casing is normalized to lowercase."""
    tokens = _tokens(source)
    result: dict = {}
    stack = [result]
    i = 0
    while i < len(tokens):
        token = tokens[i]
        i += 1
        if token == "}":
            if len(stack) > 1:
                stack.pop()
            continue
        if token == "{":
            continue
        if i >= len(tokens):
            break
        value = tokens[i]
        i += 1
        if value == "{":
            child: dict = {}
            stack[-1][token.lower()] = child
            stack.append(child)
        elif value != "}":
            stack[-1][token.lower()] = value
        else:
            if len(stack) > 1:
                stack.pop()
    return result


def read_vdf(path: Path) -> dict:
    try:
        return parse_vdf(path.read_text(encoding="utf-8-sig", errors="replace"))
    except OSError:
        return {}


def _steam_roots(extra: list[str] | None = None) -> list[Path]:
    roots = []
    if os.name == "nt":
        try:
            import winreg
            for hive, reg_path, name in [
                (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
            ]:
                try:
                    with winreg.OpenKey(hive, reg_path) as key:
                        roots.append(Path(winreg.QueryValueEx(key, name)[0]))
                except OSError:
                    continue
        except ImportError:
            pass
    for key in ("PROGRAMFILES(X86)", "PROGRAMFILES"):
        if os.environ.get(key):
            roots.append(Path(os.environ[key]) / "Steam")
    if extra:
        roots.extend(Path(p) for p in extra)
    unique = {}
    for p in roots:
        try:
            resolved = p.expanduser().resolve()
            if (resolved / "steamapps").is_dir():
                unique[str(resolved).lower()] = resolved
        except OSError:
            pass
    return list(unique.values())


def steam_libraries(steam_roots: list[Path]) -> list[Path]:
    libraries = {}
    for steam_root in steam_roots:
        candidates = [steam_root]
        vdf = read_vdf(steam_root / "steamapps" / "libraryfolders.vdf")
        folders = vdf.get("libraryfolders", {})
        for key, entry in folders.items():
            if key.isdecimal():
                path = entry.get("path") if isinstance(entry, dict) else entry
                if isinstance(path, str) and path:
                    candidates.append(Path(path))
        for candidate in candidates:
            try:
                candidate = candidate.expanduser().resolve()
                if (candidate / "steamapps").is_dir():
                    libraries[str(candidate).lower()] = candidate
            except OSError:
                continue
    return list(libraries.values())


def _valid_timestamp(raw: object) -> float | None:
    try:
        timestamp = float(raw)
        if datetime(2000, 1, 1).timestamp() <= timestamp <= time.time() + 86400:
            return timestamp
    except (TypeError, ValueError, OverflowError):
        pass
    return None


def local_play_history(steam_roots: list[Path]) -> dict[str, float]:
    """Newest known LastPlayed across accounts on this machine; unknown is unknown."""
    result: dict[str, float] = {}
    for root in steam_roots:
        try:
            configs = list((root / "userdata").glob("*/config/localconfig.vdf"))
        except OSError:
            continue
        for config in configs:
            data = read_vdf(config)
            try:
                apps = data["userlocalconfigstore"]["software"]["valve"]["steam"]["apps"]
                if not isinstance(apps, dict):
                    continue
                for app_id, details in apps.items():
                    if not isinstance(details, dict):
                        continue
                    ts = _valid_timestamp(details.get("lastplayed"))
                    if ts and ts > result.get(app_id, 0):
                        result[app_id] = ts
            except (KeyError, TypeError):
                continue
    return result


@dataclass
class SteamGame:
    app_id: str
    name: str
    library: str
    install_path: str
    size: int
    last_played: float | None
    source: str


def is_game_neglected(game: SteamGame, days: int, now: float | None = None) -> bool:
    """True only when a real last-played timestamp is known and old enough."""
    if game.last_played is None or days < 1:
        return False
    at = time.time() if now is None else now
    return game.last_played <= at - days * 86400


def find_games(extra_roots: list[str] | None = None) -> list[SteamGame]:
    roots = _steam_roots(extra_roots)
    histories = local_play_history(roots)
    result: dict[str, SteamGame] = {}
    for lib in steam_libraries(roots):
        for manifest in (lib / "steamapps").glob("appmanifest_*.acf"):
            info = read_vdf(manifest).get("appstate", {})
            if not isinstance(info, dict):
                continue
            app_id = str(info.get("appid", ""))
            if not app_id.isdecimal():
                continue
            try:
                state = int(info.get("stateflags", 4))
                if not state & 4:
                    continue
                size = max(0, int(info.get("sizeondisk", 0)))
            except (TypeError, ValueError):
                continue
            name = str(info.get("name", f"Steam app {app_id}"))
            install_dir = str(info.get("installdir", ""))
            if not install_dir or Path(install_dir).name != install_dir or install_dir in (".", ".."):
                continue
            directory = lib / "steamapps" / "common" / install_dir
            # Preserve games moved or staged under another location; a manifest is required.
            last = histories.get(app_id)
            source = "Steam account history" if last else "Unknown"
            from_manifest = _valid_timestamp(info.get("lastplayed"))
            if from_manifest and (not last or from_manifest > last):
                last, source = from_manifest, "Steam installation record"
            result[app_id] = SteamGame(app_id, name, str(lib), str(directory), size, last, source)
    return sorted(result.values(), key=lambda item: item.name.lower())


# Narrow signatures only. A filename or directory name is evidence worth reviewing,
# not proof that a mod can safely be removed.
MOD_INDICATOR_DIRS = (
    ("mods",), ("~mods",), ("bepinex",), ("melonloader",),
    ("plugins",), ("modloader",), ("ue4ss",),
    ("r6", "mods"), ("red4ext", "plugins"),
    ("shooterGame", "content", "mods"),  # ARK installs
    ("data", "f4se", "plugins"), ("data", "skse", "plugins"),
    ("reshade-shaders",), ("scripts", "plugins"),
    ("data", "skse"), ("data", "f4se"),
    ("data", "nvse"), ("data", "obse"), ("data", "sfse"),
    ("content", "paks", "~mods"),
    ("archive", "pc", "mod"),  # Cyberpunk 2077
    ("red4ext", "plugins"), ("r6", "scripts"),
)
MOD_INDICATOR_FILES = {
    "dinput8.dll", "reshade.ini", "skse64_loader.exe",
    "f4se_loader.exe", "nvse_loader.exe", "obse_loader.exe", "sfse_loader.exe",
    "scripthookv.dll", "scripthookvdotnet.asi", "winhttp.dll",
    "version.dll", "winmm.dll", "dxgi.dll", "d3d11.dll",
}


@dataclass
class ModFolder:
    name: str
    path: str
    library: str
    status: str
    indicators: tuple[str, ...]
    apparent_bytes: int
    file_count: int
    truncated: bool
    source: str = "Steam game folder"
    advice: str = "Review manually; no cleanup is performed."
    item_count: int = 0
    # Includes the entire unmatched folder; installed games only include identified
    # marker paths. No size is an estimate of guaranteed freed disk space.


def _mod_markers(folder: Path) -> list[tuple[str, Path]]:
    """Collect potential mod signatures without reading unknown file content."""
    try:
        entries = {p.name.casefold(): p for p in folder.iterdir()}
    except OSError:
        return []
    results = []
    for path_parts in MOD_INDICATOR_DIRS:
        current = entries.get(path_parts[0])
        if current is None:
            continue
        for part in path_parts[1:]:
            if _is_reparse_point(current) or not current.is_dir():
                current = None
                break
            try:
                current = next((p for p in current.iterdir() if p.name.casefold() == part), None)
            except (OSError, NotADirectoryError):
                current = None
            if current is None:
                break
        if current is not None and not _is_reparse_point(current) and current.is_dir():
            results.append(("/".join(path_parts), current))
    for name in sorted(MOD_INDICATOR_FILES):
        current = entries.get(name)
        if current is not None and not _is_reparse_point(current) and current.is_file():
            results.append((name, current))
    # Exclude nested marker paths (like mods under broader recognized directories)
    # from apparent byte accounting via file inode deduplication below.
    return results


def _measured_files(paths: list[Path], max_files: int = 100_000,
                    cancel: Callable[[], bool] | None = None) -> tuple[int, int, bool]:
    """Read-only bounded size estimate, skipping Windows junctions and symlinks.

    Counts file identities only once even if marker paths overlap. For files on
    separate paths with a shared NTFS hardlink, actual reclaimable space can differ.
    """
    bytes_total = count = 0
    seen_files = set()
    pending = list(paths)
    while pending:
        if cancel and cancel():
            raise InterruptedError("Mod scan canceled")
        path = pending.pop()
        if _is_reparse_point(path):
            continue
        try:
            if path.is_dir():
                with os.scandir(path) as entries:
                    pending.extend(Path(entry.path) for entry in entries)
            elif path.is_file():
                st = path.stat()
                key = (st.st_dev, st.st_ino) if st.st_ino else str(path.resolve()).casefold()
                if key in seen_files:
                    continue
                seen_files.add(key)
                bytes_total += max(0, st.st_size)
                count += 1
                if count >= max_files:
                    return bytes_total, count, True
        except (PermissionError, OSError):
            continue
    return bytes_total, count, False


def find_mod_folders(extra_roots: list[str] | None = None,
                     games: list[SteamGame] | None = None,
                     cancel: Callable[[], bool] | None = None,
                     max_folders: int = 1000) -> list[ModFolder]:
    """Find mod-like installed-game files and folders with no matching Steam install.

    An unmatched directory is *not* proof of an uninstalled game or safe deletion.
    The scanner intentionally never deletes, moves, or edits mod files.
    """
    roots = _steam_roots(extra_roots)
    libraries = steam_libraries(roots)
    if games is None:
        games = find_games(extra_roots)
    installed = {str(Path(g.install_path).resolve()).casefold() for g in games}
    results = []
    for lib in libraries:
        common = lib / "steamapps" / "common"
        if not common.is_dir() or _is_reparse_point(common):
            continue
        try:
            folders = sorted(common.iterdir(), key=lambda p: p.name.casefold())
        except OSError:
            continue
        for folder in folders:
            if cancel and cancel():
                raise InterruptedError("Mod scan canceled")
            if len(results) >= max_folders:
                return results
            if not folder.is_dir() or _is_reparse_point(folder):
                continue
            is_installed = str(folder.resolve()).casefold() in installed
            markers = _mod_markers(folder)
            if is_installed and not markers:
                continue
            if is_installed:
                measured = [p for _, p in markers]
                status = "Installed: possible mods"
            else:
                measured = [folder]
                status = "Unmatched Steam folder"
            size, files, truncated = _measured_files(measured, cancel=cancel)
            results.append(ModFolder(folder.name, str(folder), str(lib), status,
                                     tuple(label for label, _ in markers), size, files, truncated))
    return sorted(results, key=lambda f: (f.status != "Unmatched Steam folder", -f.apparent_bytes,
                                          f.name.casefold()))


def find_all_mod_storage(extra_roots: list[str] | None = None,
                         mod_extra_roots: list[str] | None = None,
                         games: list[SteamGame] | None = None,
                         cancel: Callable[[], bool] | None = None) -> list[ModFolder]:
    """Read-only combined Steam install, Workshop, Vortex and MO2 inventory."""
    from mod_sources import find_external_mod_storage
    if games is None:
        games = find_games(extra_roots)
    results = find_mod_folders(extra_roots, games=games, cancel=cancel)
    results += find_external_mod_storage(extra_roots, mod_extra_roots or [], games, cancel)
    from ecosystems import find_ecosystem_storage, find_steam_staging
    results += find_ecosystem_storage(extra_roots, mod_extra_roots, cancel)
    results += find_steam_staging(extra_roots, games, cancel)
    from ecosystems import find_installed_game_content
    results += find_installed_game_content(games, cancel)
    # Avoid duplicate reports for the same folder and source. Do not sum these
    # as reclaimable space: hardlinks can share actual disk blocks.
    unique: dict[tuple[str, str], ModFolder] = {}
    for row in results:
        unique[(str(Path(row.path)).casefold(), row.source.casefold())] = row
    return sorted(unique.values(), key=lambda r: (r.source.casefold(), -r.apparent_bytes, r.name.casefold()))


@dataclass
class OldFile:
    path: str
    size: int
    modified: float


def _is_reparse_point(path: Path) -> bool:
    """Block Windows directory junctions and links from escaping the scanned folder."""
    try:
        if path.is_symlink():
            return True
        state = path.lstat()
        return bool(getattr(state, "st_file_attributes", 0) & 0x400)  # REPARSE_POINT
    except OSError:
        return True


def safe_scan_root(path: Path) -> bool:
    """Refuse drive root/home and core operating-system directories."""
    try:
        if _is_reparse_point(path):
            return False
        p = path.expanduser().resolve(strict=True)
        home = Path.home().resolve()
        if not p.is_dir() or p == home or p == Path(p.anchor):
            return False
        parts = {segment.lower() for segment in p.parts}
        if any(part in parts for part in ("windows", "program files", "program files (x86)", "programdata", "appdata", ".git", "steamapps")):
            return False
        # Avoid scanning system folders the user selected by mistake.
        return True
    except OSError:
        return False


def scan_old_files(folder: Path, min_days: int = 180, cancel: Callable[[], bool] | None = None,
                   allowed_extensions: set[str] | None = None, max_matches: int = 50000) -> list[OldFile]:
    if not safe_scan_root(folder):
        raise ValueError("Choose an existing folder that is not a system directory or drive root.")
    cutoff = time.time() - max(1, min_days) * 86400
    found: list[OldFile] = []
    for parent, dirs, names in os.walk(folder, followlinks=False):
        if cancel and cancel():
            raise InterruptedError("Scan canceled")
        dirs[:] = [d for d in dirs if d.lower() not in SCAN_EXCLUDED and not
                   _is_reparse_point(Path(parent) / d)]
        for name in names:
            path = Path(parent) / name
            if allowed_extensions is not None and path.suffix.lower() not in allowed_extensions:
                continue
            try:
                if _is_reparse_point(path) or not path.is_file():
                    continue
                stat = path.stat()
                if stat.st_mtime <= cutoff:
                    found.append(OldFile(str(path), stat.st_size, stat.st_mtime))
                    if len(found) >= max_matches:
                        return found
            except (OSError, ValueError):
                continue
    return found


def human_size(n: int) -> str:
    size = float(max(0, n))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return "0 B"


def age_text(timestamp: float | None) -> str:
    if not timestamp:
        return "Unknown"
    days = max(0, int((time.time() - timestamp) / 86400))
    if days < 1:
        return "Today"
    if days < 30:
        return f"{days} days ago"
    if days < 365:
        return f"{days // 30} months ago"
    return f"{days // 365} years ago"


def is_unchanged(candidate: OldFile) -> bool:
    try:
        path = Path(candidate.path)
        if _is_reparse_point(path) or not path.is_file():
            return False
        state = path.stat()
        return state.st_size == candidate.size and abs(state.st_mtime - candidate.modified) < 1
    except OSError:
        return False


def is_protected_path(path: Path, extra: list[str] | None = None) -> bool:
    """Reject known save/profile roots and user-defined Never Touch directories/files.

    Used at the point of removal as well as while assembling suggestions.
    """
    p = Path(os.path.abspath(str(path)))
    # Fail closed for likely personal saves, managed game folders and mod profiles.
    # The generic Old Files cleaner is not a game/mod manager.
    pieces = [part.casefold() for part in p.parts]
    if any(part in {"saves", "savegames", "saved games", "worlds", "playerprofiles",
                     "modorganizer", "mod organizer 2", "steamapps",
                     "addons", "savedvariables", "my games", "saves", "userprofiles", "userskins", "usersights", "usermissions",
                     "userhangar", "interface", "profiles"} for part in pieces):
        return True
    if "mods" in pieces and "downloads" not in pieces:
        return True
    guarded = [Path(os.path.abspath(str(x))) for x in (extra or []) if isinstance(x, str) and x.strip()]
    # Do not permit deletions through this utility in crucial Windows roots.
    for var in ("WINDIR", "SYSTEMROOT"):
        if os.environ.get(var):
            guarded.append(Path(os.path.abspath(os.environ[var])))
    for target in guarded:
        try:
            if os.path.normcase(os.path.commonpath([str(p), str(target)])) == os.path.normcase(str(target)):
                return True
        except ValueError:
            continue  # Windows paths on different drives cannot share an ancestor.
        except OSError:
            return True
    return False


def recycle_file(path: Path) -> None:
    """Send local fixed-disk file to Windows Recycle Bin. Never fall back to permanent delete."""
    if os.name != "nt":
        raise RuntimeError("Recycling requires Windows.")
    from ctypes import wintypes

    if _is_reparse_point(path):
        raise ValueError("Reparse points and symbolic links are not eligible.")
    path = path.resolve(strict=True)
    if not path.is_file() or len(str(path)) > 240:
        raise ValueError("Not an ordinary, local Windows file (or path is too long).")
    root = Path(path.anchor)
    drive_type = ctypes.windll.kernel32.GetDriveTypeW(str(root))
    if drive_type != 3:  # DRIVE_FIXED. Reject network/removable drives.
        raise ValueError("Only local fixed disks can use automatic Recycle Bin cleanup.")

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT),
                    ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR),
                    ("fFlags", wintypes.WORD), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", wintypes.LPVOID), ("lpszProgressTitle", wintypes.LPCWSTR)]

    op = SHFILEOPSTRUCTW()
    op.wFunc = 3  # FO_DELETE
    op.pFrom = str(path) + "\0\0"
    op.fFlags = 0x0040 | 0x0010 | 0x0004 | 0x0400  # ALLOWUNDO, NOCONFIRMATION, SILENT, NOERRORUI
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if result or op.fAnyOperationsAborted or path.exists():
        raise OSError(f"Windows could not recycle this file (code {result}).")


def run_auto_cleanup() -> tuple[int, int, str]:
    cfg = load_settings()
    if not cfg["auto_enabled"]:
        return 0, 0, "Automatic cleanup is disabled."
    # Hard-coded scope: only Downloads, independent of the manually browsed folder.
    folder = downloads_dir()
    extensions = AUTO_BASE_EXTENSIONS | (AUTO_EXTRA_EXTENSIONS if cfg["auto_include_archives"] else set())
    try:
        items = scan_old_files(folder, int(cfg["auto_days"]), allowed_extensions=extensions)
    except (OSError, ValueError) as exc:
        log_event("Automatic cleanup", f"Scan skipped: {exc}")
        return 0, 0, str(exc)
    session_id = str(uuid.uuid4())
    log_event("Cleanup started", f"Automatic cleanup: {len(items)} candidates reviewed", session_id=session_id)
    done, total_bytes, failed = 0, 0, 0
    for item in items:
        try:
            if is_protected_path(Path(item.path), cfg.get("never_touch", [])):
                raise ValueError("Protected by Never Touch list")
            if not is_unchanged(item):
                failed += 1
                log_event("Cleanup skipped", f"{item.path}: Changed since scan", session_id=session_id,
                          path=item.path, result="Changed since scan", source="Automatic")
                continue
            # Recheck age in case the source file changed after scanning.
            if item.modified > time.time() - int(cfg["auto_days"]) * 86400:
                log_event("Cleanup skipped", f"{item.path}: No longer old enough", session_id=session_id,
                          path=item.path, result="Age threshold not met", source="Automatic")
                continue
            recycle_file(Path(item.path))
            recovery_id = None
            try:
                from recovery import register_recycle
                recovery_id = register_recycle(Path(item.path), item.size, "Automatic")
            except OSError:
                log_event("Recovery warning", "Could not register: " + item.path)
            done += 1
            total_bytes += item.size
            log_event("Auto recycled", item.path, session_id=session_id, path=item.path,
                      size_bytes=item.size, result="Sent to Recycle Bin", source="Automatic",
                      recovery_id=recovery_id)
        except (OSError, ValueError, RuntimeError) as exc:
            failed += 1
            log_event("Cleanup skipped", f"{item.path}: {exc}", session_id=session_id,
                      path=item.path, result=str(exc), source="Automatic")
    summary = f"Sent {done} files ({human_size(total_bytes)}) to Recycle Bin; skipped {failed}."
    log_event("Cleanup finished", summary, session_id=session_id, source="Automatic")
    return done, total_bytes, summary
