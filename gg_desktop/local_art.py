"""Opt-in-free, read-only discovery of game artwork already present on this PC.

No network requests, arbitrary folder crawling or images bundled from a store.
Only well-known Steam library-cache locations and explicit root cover filenames
are considered. Missing art is a normal outcome and never affects scanning.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

_IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp")
_MAX_BYTES = 16 * 1024 * 1024


def _usable(path: Path) -> bool:
    try:
        return (path.is_file() and not path.is_symlink()
                and path.suffix.lower() in _IMAGE_EXT
                and 1000 <= path.stat().st_size <= _MAX_BYTES)
    except (OSError, ValueError):
        return False


def _steam_locations(install_path: str):
    """Bounded root discovery, not a recursive disk search."""
    roots = []
    try:
        path = Path(install_path)
        for node in (path, *list(path.parents)[:5]):
            if node.name.lower() == "steamapps":
                roots.append(node.parent)
                break
    except (OSError, ValueError):
        pass
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                roots.append(Path(winreg.QueryValueEx(key, "SteamPath")[0]))
        except (OSError, ValueError, ImportError):
            pass
        for env in ("PROGRAMFILES(X86)", "PROGRAMFILES"):
            value = os.environ.get(env)
            if value:
                roots.append(Path(value) / "Steam")
    seen = set()
    for root in roots:
        name = os.path.normcase(str(root))
        if name not in seen:
            seen.add(name)
            yield root


@lru_cache(maxsize=256)
def _cover_path(launcher: str, app_id: str, install_path: str) -> str:
    # Do not inspect every image in a game folder. The user selected a game
    # install; only specifically named root poster/cover files may be opened.
    candidate = []
    # Official Steam library art takes precedence over a game's generic cover.jpg.
    if launcher.casefold() == "steam" and app_id.isascii() and app_id.isdecimal() and len(app_id) <= 12:
        for root in _steam_locations(install_path):
            cache = root / "appcache" / "librarycache"
            for name in (
                f"{app_id}_library_600x900.jpg",
                f"{app_id}_library_600x900.png",
                f"{app_id}_library_600x900.webp",
                f"{app_id}_header.jpg",
                f"{app_id}_library_hero.jpg",
            ):
                candidate.append(cache / name)
            for name in ("library_600x900.jpg", "library_600x900.png",
                         "library_600x900.webp", "header.jpg"):
                candidate.append(cache / app_id / name)
            candidate.extend((
                root / "config" / "grid" / f"{app_id}p.jpg",
                root / "config" / "grid" / f"{app_id}p.png",
                root / "config" / "grid" / f"{app_id}.jpg",
                root / "config" / "grid" / f"{app_id}.png",
            ))
        from gg_desktop.steam_artwork import cached_steam_cover
        official = cached_steam_cover(app_id)
        if official:
            candidate.append(Path(official))
    try:
        folder = Path(install_path)
        candidate.extend(folder / filename for filename in (
            "cover.jpg", "cover.png", "poster.jpg", "poster.png",
            "folder.jpg", "folder.png"))
    except (OSError, ValueError):
        pass
    for p in candidate[:80]:
        if _usable(p):
            return str(p)
    return ""


def game_cover_path(game) -> str:
    """Return an absolute local image path or an empty string (no guessing)."""
    return _cover_path(str(getattr(game, "launcher", "")),
                       str(getattr(game, "app_id", "") or ""),
                       str(getattr(game, "install_path", "") or ""))


def invalidate_cover_cache() -> None:
    """Call after an official image is successfully cached."""
    _cover_path.cache_clear()
