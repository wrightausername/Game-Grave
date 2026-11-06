"""Read-only data needed by Overview, independent of cleanup inventories."""
from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path
import re
import shutil
import stat
import time

from core import OldFile, _has_reparse_component, _steam_roots, is_protected_path, safe_scan_root
from screenshots import default_screenshot_roots, looks_like_screenshot, _steam_screenshot_root


def system_disk_path() -> Path:
    """The OS volume, even when a Windows home folder is on another drive."""
    if os.name == "nt":
        drive = os.environ.get("SystemDrive", "")
        if re.fullmatch(r"[A-Za-z]:", drive):
            return Path(drive + "\\")
        for name in ("SystemRoot", "WINDIR"):
            anchor = Path(os.environ.get(name, "")).anchor
            if anchor:
                return Path(anchor)
    return Path(Path.home().anchor)


def disk_reading():
    path = system_disk_path()
    usage = shutil.disk_usage(path)
    if usage.total <= 0 or not 0 <= usage.free <= usage.total:
        raise OSError("Drive usage not available")
    return path, usage


@dataclass(frozen=True)
class LauncherSummary:
    name: str
    count: int
    known_bytes: int
    unknown_sizes: int


def launcher_games(games, name):
    return [g for g in games if (len(g.claimed_by) != 1 if name == "Multiple launchers"
                                else len(g.claimed_by) == 1 and g.launcher == name)]


def launcher_summaries(games):
    groups = {}
    for game in games:
        name = game.launcher if len(game.claimed_by) == 1 else "Multiple launchers"
        groups.setdefault(name, []).append(game)
    return tuple(LauncherSummary(name, len(rows),
                                sum(g.size_bytes for g in rows if g.size_bytes is not None),
                                sum(g.size_bytes is None for g in rows))
                 for name, rows in sorted(groups.items(), key=lambda pair: (-len(pair[1]), pair[0])))


@dataclass(frozen=True)
class CaptureResult:
    latest: OldFile | None = None
    limited: bool = False
    warnings: tuple[str, ...] = ()


def latest_capture(settings, *, home=None, steam_roots=None, canceled=lambda: False,
                   max_entries=30000, max_directories=600):
    """Find a recent screenshot by metadata, without the cleanup-age restriction.

    Only known game capture directories and explicitly selected capture roots
    are inspected. Never reads image bytes, caches thumbnails or changes files.
    Limits apply to the whole discovery, not separately to every selected root.
    """
    home = Path(home or Path.home())
    steam = _steam_roots(list(settings.get("steam_extra_roots", []))) if steam_roots is None else steam_roots
    roots = default_screenshot_roots(home, steam)
    roots.extend(Path(p).expanduser() for p in settings.get("screenshot_roots", [])[:30]
                 if isinstance(p, str) and p.strip())
    latest = None
    entries = directories = 0
    seen, warnings = set(), []
    now = time.time()
    for root in roots:
        if canceled():
            raise InterruptedError("Overview screenshot check stopped")
        trusted = _steam_screenshot_root(root, steam)
        identity = os.path.normcase(os.path.abspath(root))
        if identity in seen:
            continue
        seen.add(identity)
        if _has_reparse_component(root) or not root.is_dir() or (not trusted and not safe_scan_root(root)):
            continue
        pending = [(root, 0)]
        while pending:
            if canceled():
                raise InterruptedError("Overview screenshot check stopped")
            folder, depth = pending.pop()
            if directories >= max_directories or entries >= max_entries:
                return CaptureResult(latest, True, tuple(warnings))
            directories += 1
            if _has_reparse_component(folder):
                continue
            try:
                with os.scandir(folder) as listing:
                    for item in listing:
                        if canceled():
                            raise InterruptedError("Overview screenshot check stopped")
                        if entries >= max_entries:
                            return CaptureResult(latest, True, tuple(warnings))
                        entries += 1
                        path = Path(item.path)
                        if _has_reparse_component(path):
                            continue
                        if item.is_dir(follow_symlinks=False):
                            if (not trusted and depth < 5 and len(pending) + directories < max_directories
                                    and path.name.casefold() not in {"thumbnails", "thumbs", "cache", ".git", "node_modules"}
                                    and not is_protected_path(path, [])):
                                pending.append((path, depth + 1))
                            elif not trusted and path.name.casefold() not in {"thumbnails", "thumbs", "cache", ".git", "node_modules"}:
                                warnings.append("Some capture subfolders were outside the bounded search.")
                            continue
                        if not looks_like_screenshot(path) or is_protected_path(path, []):
                            continue
                        info = path.lstat()
                        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
                                not math.isfinite(info.st_mtime) or info.st_mtime > now + 86400):
                            continue
                        record = OldFile(str(path), info.st_size, info.st_mtime, info.st_dev,
                                         info.st_ino, info.st_mtime_ns, info.st_nlink)
                        if latest is None or (record.modified, record.path) > (latest.modified, latest.path):
                            latest = record
            except OSError:
                warnings.append("A capture folder was unavailable during inspection.")
    return CaptureResult(latest, bool(warnings), tuple(dict.fromkeys(warnings))[:10])
