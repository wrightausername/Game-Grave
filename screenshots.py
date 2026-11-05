"""Opt-in, metadata-only discovery of likely in-game screenshot images.

Never searches whole Pictures folders by default, never opens image bytes
during scanning, and never authorizes automatic or batch deletion. Real photo
content is unclassified; the user must preview each image before recycling.
"""
from __future__ import annotations

import os
import stat
import time
from pathlib import Path
from typing import Callable

from core import OldFile, _has_reparse_component, _steam_roots, safe_scan_root, scan_old_files

Cancel = Callable[[], bool] | None
SCREENSHOT_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp"})
SKIP_IMAGE_PARTS = frozenset({"thumbnails", "thumbnail", "thumbs", "cache", ".cache"})
MAX_SCREENSHOTS = 1500
MAX_ACCOUNTS = 60
MAX_GAMES_PER_ACCOUNT = 400
MAX_GAME_SCREENSHOT_ROOTS = 140


def looks_like_screenshot(path: Path) -> bool:
    """Only image formats supported by the bounded screenshot preview."""
    if path.suffix.casefold() not in SCREENSHOT_EXTENSIONS:
        return False
    if any(part.casefold() in SKIP_IMAGE_PARTS for part in path.parts):
        return False
    return True


def default_screenshot_roots(
    home: Path | None = None,
    steam_roots: list[Path] | None = None,
    games: list | None = None,
) -> list[Path]:
    """Known local capture dirs, not broad personal Photos/Pictures/Videos roots.

    Steam screenshot ownership needs a numeric local Steam ID and game app ID.
    The app never concludes a picture is actually of a game from its filename.
    """
    home = Path.home() if home is None else Path(home)
    candidates = [
        home / "Videos" / "Captures",
        home / "OneDrive" / "Videos" / "Captures",
        home / "Pictures" / "Game Screenshots",
        home / "Pictures" / "Steam Screenshots",
        # Ubisoft officially stores its own in-game captures here by default.
        home / "Pictures" / "UbisoftConnect",
        home / "OneDrive" / "Pictures" / "UbisoftConnect",
        home / "Videos" / "NVIDIA",
        home / "Videos" / "Radeon ReLive",
    ]
    # Games may save photo-mode images to a dedicated per-game Screenshots
    # folder. Examine only these explicit candidate directories for games
    # already discovered by Game Grave. Never sweep Documents or Pictures.
    for game in (games or [])[:MAX_GAME_SCREENSHOT_ROOTS]:
        name = str(getattr(game, "name", "")).strip()
        if (not name or len(name) > 90 or name in {".", ".."}
                or any(char in name for char in '/\\:*?"<>|')):
            continue
        for base in (home / "Pictures", home / "Documents",
                     home / "OneDrive" / "Pictures",
                     home / "OneDrive" / "Documents"):
            candidates.append(base / name / "Screenshots")
            candidates.append(base / name / "ScreenShots")
        candidates.append(home / "Documents" / "My Games" / name / "Screenshots")
    for steam in (steam_roots or []):
        base = Path(steam) / "userdata"
        if _has_reparse_component(base) or not base.is_dir():
            continue
        try:
            accounts = sorted(base.iterdir())[:MAX_ACCOUNTS]
        except OSError:
            continue
        for account in accounts:
            if not account.name.isdecimal() or _has_reparse_component(account):
                continue
            remote = account / "760" / "remote"
            if _has_reparse_component(remote) or not remote.is_dir():
                continue
            try:
                app_dirs = sorted(remote.iterdir())[:MAX_GAMES_PER_ACCOUNT]
            except OSError:
                continue
            for game in app_dirs:
                if game.name.isdecimal() and not _has_reparse_component(game):
                    candidates.append(game / "screenshots")
    found = []
    keys = set()
    for p in candidates:
        key = os.path.normcase(os.path.abspath(os.fspath(p))).casefold()
        if key not in keys and p.is_dir() and not _has_reparse_component(p):
            found.append(p)
            keys.add(key)
    return found


def _steam_screenshot_root(root: Path, steam_roots: list[Path]) -> bool:
    for steam in steam_roots:
        try:
            parts = root.absolute().relative_to((Path(steam) / "userdata").absolute()).parts
        except ValueError:
            continue
        if (len(parts) == 5 and parts[0].isdecimal() and
                parts[1:3] == ("760", "remote") and
                parts[3].isdecimal() and parts[4].casefold() == "screenshots"):
            return True
    return False


def _read_direct_steam_images(root: Path, days: int, cancel: Cancel,
                              max_matches: int) -> list[OldFile]:
    """Known Steam screenshots can be under Program Files; no generic OS scan.

    Only direct ordinary image files within a validated account/game directory,
    never thumbnails or other game/Steam data.
    """
    cutoff = time.time() - days * 86400
    found = []
    inspected = 0
    with os.scandir(root) as listing:
        for item in listing:
            if cancel and cancel():
                raise InterruptedError("Screenshot scan canceled")
            inspected += 1
            if inspected > 10000 or len(found) >= max_matches:
                break
            path = Path(item.path)
            if not looks_like_screenshot(path) or path.is_symlink():
                continue
            try:
                # On Windows, os.DirEntry.stat(follow_symlinks=False) can
                # report different nlink / metadata semantics than Path.stat
                # for NTFS. Use one explicit non-following path identity check.
                state = path.lstat()
            except OSError:
                continue
            if (not stat.S_ISREG(state.st_mode) or state.st_nlink != 1
                    or state.st_mtime > cutoff or _has_reparse_component(path)):
                continue
            found.append(OldFile(str(path), state.st_size, state.st_mtime,
                                 state.st_dev, state.st_ino, state.st_mtime_ns,
                                 state.st_nlink))
    return found


def _read_scoped_capture_images(root: Path, cancel: Cancel,
                                max_matches: int) -> list[OldFile]:
    """Discover recent *and* older captures without loading image contents.

    Called only for a known-game-specific screenshot root, recognized launcher
    capture folder, or explicitly approved custom root. No generic home crawl.
    """
    output: list[OldFile] = []
    inspected = 0
    for parent, dirs, names in os.walk(root, followlinks=False):
        if cancel and cancel():
            raise InterruptedError("Screenshot scan canceled")
        current = Path(parent)
        if _has_reparse_component(current):
            dirs[:] = []
            continue
        depth = len(current.relative_to(root).parts)
        if depth >= 3:
            dirs[:] = []
        else:
            dirs[:] = [d for d in dirs if d.casefold() not in SKIP_IMAGE_PARTS
                       and not _has_reparse_component(current / d)][:40]
        for name in names:
            inspected += 1
            if inspected > 16000 or len(output) >= max_matches:
                return output
            file = current / name
            if not looks_like_screenshot(file) or _has_reparse_component(file):
                continue
            try:
                info = file.lstat()
            except OSError:
                continue
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                continue
            output.append(OldFile(
                str(file), info.st_size, info.st_mtime,
                info.st_dev, info.st_ino, info.st_mtime_ns, info.st_nlink,
            ))
    return output


def find_old_screenshots(
    days: int = 365,
    custom_roots: list[str] | None = None,
    *,
    home: Path | None = None,
    steam_roots: list[Path] | None = None,
    extra_steam_roots: list[str] | None = None,
    games: list | None = None,
    include_recent: bool = False,
    cancel: Cancel = None,
    max_matches: int = MAX_SCREENSHOTS,
) -> list[OldFile]:
    """Read image file metadata from known or explicitly user-added locations.

    Never reads content, creates thumbnails, mutates files or records images
    from generic Photos, Documents or Pictures by default. Missing/redirected
    roots fail closed, including linked parents and network mount redirection.
    """
    if not isinstance(days, int) or days < 1 or not 1 <= max_matches <= MAX_SCREENSHOTS:
        raise ValueError("Choose a valid screenshot age and scan limit.")
    steam = _steam_roots(extra_steam_roots) if steam_roots is None else steam_roots
    roots = default_screenshot_roots(home, steam, games)
    scan_days = 0 if include_recent else days
    roots.extend(
        Path(p).expanduser()
        for p in (custom_roots or [])[:30]
        if isinstance(p, str) and p.strip()
    )
    seen_dirs, seen_files = set(), set()
    result = []
    for root in roots:
        if cancel and cancel():
            raise InterruptedError("Screenshot scan canceled")
        key = os.path.normcase(os.path.abspath(os.fspath(root))).casefold()
        steam_trusted = _steam_screenshot_root(root, steam)
        if (key in seen_dirs or _has_reparse_component(root)
                or not root.is_dir()
                or (not steam_trusted and not safe_scan_root(root))):
            continue
        seen_dirs.add(key)
        remaining = max_matches - len(result)
        if remaining <= 0:
            break
        candidates = (_read_direct_steam_images(root, scan_days, cancel, remaining * 2)
                      if steam_trusted else
                      _read_scoped_capture_images(root, cancel, remaining * 2)
                      if include_recent else
                      scan_old_files(
                          root, scan_days, cancel=cancel,
                          allowed_extensions=set(SCREENSHOT_EXTENSIONS),
                          max_matches=remaining * 2,
                      ))
        for record in candidates:
            if cancel and cancel():
                raise InterruptedError("Screenshot scan canceled")
            candidate = Path(record.path)
            identity = os.path.normcase(os.path.abspath(record.path)).casefold()
            if (identity in seen_files or not looks_like_screenshot(candidate) or
                    _has_reparse_component(candidate) or record.hardlinks not in (None, 1)):
                continue
            seen_files.add(identity)
            result.append(record)
            if len(result) >= max_matches:
                return sorted(result, key=lambda f: (-f.size, f.path.casefold()))
    return sorted(result, key=lambda f: (-f.size, f.path.casefold()))
