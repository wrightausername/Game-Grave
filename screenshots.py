"""Opt-in, metadata-only discovery of likely in-game screenshot images.

Never searches whole Pictures folders by default, never opens image bytes
during scanning, and never authorizes automatic or batch deletion. Real photo
content is unclassified; the user must preview each image before recycling.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from core import OldFile, _has_reparse_component, _steam_roots, safe_scan_root, scan_old_files

Cancel = Callable[[], bool] | None
SCREENSHOT_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp"})
SKIP_IMAGE_PARTS = frozenset({"thumbnails", "thumbnail", "thumbs", "cache", ".cache"})
MAX_SCREENSHOTS = 1500
MAX_ACCOUNTS = 60
MAX_GAMES_PER_ACCOUNT = 400


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
    ]
    for steam in (steam_roots or []):
        base = Path(steam) / "userdata"
        if not safe_scan_root(base):
            continue
        try:
            accounts = sorted(base.iterdir())[:MAX_ACCOUNTS]
        except OSError:
            continue
        for account in accounts:
            if not account.name.isdecimal() or _has_reparse_component(account):
                continue
            remote = account / "760" / "remote"
            if not safe_scan_root(remote):
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
        if key not in keys and safe_scan_root(p):
            found.append(p)
            keys.add(key)
    return found


def find_old_screenshots(
    days: int = 365,
    custom_roots: list[str] | None = None,
    *,
    home: Path | None = None,
    steam_roots: list[Path] | None = None,
    extra_steam_roots: list[str] | None = None,
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
    roots = default_screenshot_roots(home, steam)
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
        if key in seen_dirs or not safe_scan_root(root):
            continue
        seen_dirs.add(key)
        remaining = max_matches - len(result)
        if remaining <= 0:
            break
        for record in scan_old_files(
            root, days, cancel=cancel, allowed_extensions=set(SCREENSHOT_EXTENSIONS),
            max_matches=remaining * 2,
        ):
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
