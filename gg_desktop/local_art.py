"""Safe, bounded discovery of actual game cover art.

Prefers user-selected artwork, then previously fetched official Steam artwork,
then installed launcher's local poster files. No internet requests here.
Steam's legacy, appid/ and newer appid/content-hash caches are supported.
Missing art remains explicitly labelled, not a fake official cover.
"""
from __future__ import annotations

import hashlib
import os
import re
from functools import lru_cache
from itertools import islice
from pathlib import Path

_IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp")
_MAX_BYTES = 16 * 1024 * 1024
_HASH = re.compile(r"^[a-fA-F0-9]{16,64}$")


def artwork_cache_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME")
    if not base:
        base = str(Path.home() / ".cache")
    return Path(base) / "GameGrave" / "artwork"


def _game_key(game) -> str:
    return hashlib.sha256(str(getattr(game, "key", "")).encode(
        "utf-8", errors="replace")).hexdigest()[:32]


def _usable(path: Path) -> bool:
    try:
        stat = path.stat()
        return (path.is_file() and not path.is_symlink()
                and path.suffix.lower() in _IMAGE_EXT
                and 1000 <= stat.st_size <= _MAX_BYTES)
    except (OSError, ValueError):
        return False


def _steam_locations(install_path: str):
    """Bounded root discovery, never scan an entire drive recursively."""
    roots = []
    try:
        path = Path(install_path)
        for node in (path, *list(path.parents)[:6]):
            if node.name.lower() == "steamapps":
                roots.append(node.parent)
                break
    except (OSError, ValueError):
        pass
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Valve\Steam") as key:
                roots.append(Path(winreg.QueryValueEx(key, "SteamPath")[0]))
        except (OSError, ValueError, ImportError):
            pass
        for env in ("PROGRAMFILES(X86)", "PROGRAMFILES"):
            value = os.environ.get(env)
            if value:
                roots.append(Path(value) / "Steam")
    seen = set()
    for root in roots:
        norm = os.path.normcase(str(root)).casefold()
        if norm not in seen:
            seen.add(norm)
            yield root


def _steam_cache_candidates(root, app_id):
    """Portrait-first candidates across all three Steam cache layouts."""
    cache = root / "appcache" / "librarycache"
    preferred = []
    secondary = []
    for name in (
        f"{app_id}_library_600x900_2x.jpg",
        f"{app_id}_library_600x900.jpg",
        f"{app_id}_library_600x900.png",
        f"{app_id}_library_600x900.webp",
    ):
        preferred.append(cache / name)
    parent = cache / app_id
    image_names = (
        "library_600x900_2x.jpg", "library_600x900.jpg",
        "library_600x900.png", "library_600x900.webp",
        "library_capsule.jpg", "library_capsule.png",
    )
    preferred.extend(parent / name for name in image_names)
    try:
        # Steam 2026: <appid>/<contentHash>/library_600x900.jpg.
        # Strictly inspect no more than 48 immediate hash directories.
        if parent.is_dir() and not parent.is_symlink():
            for child in islice(parent.iterdir(), 48):
                if child.is_dir() and not child.is_symlink() and _HASH.fullmatch(child.name):
                    preferred.extend(child / name for name in image_names)
                    secondary.extend(child / name for name in (
                        "library_header.jpg", "header.jpg", "library_hero.jpg"))
    except (OSError, ValueError):
        pass
    preferred.extend((
        root / "config" / "grid" / f"{app_id}p.jpg",
        root / "config" / "grid" / f"{app_id}p.png",
    ))
    # User-specific Steam artwork lives in userdata/<numeric ID>/config/grid.
    # Inspect only a small bounded set of account directories, never perform
    # a recursive scan of userdata (which contains private game save data).
    accounts = root / "userdata"
    try:
        if accounts.is_dir() and not accounts.is_symlink():
            for account in islice(accounts.iterdir(), 24):
                if (not account.name.isascii() or not account.name.isdecimal()
                        or not account.is_dir() or account.is_symlink()):
                    continue
                grid = account / "config" / "grid"
                preferred.extend((
                    grid / f"{app_id}p.jpg",
                    grid / f"{app_id}p.png",
                    grid / f"{app_id}p.webp",
                ))
    except (OSError, ValueError):
        pass
    secondary.extend((
        cache / f"{app_id}_header.jpg",
        cache / f"{app_id}_library_hero.jpg",
        parent / "library_header.jpg", parent / "header.jpg",
        parent / "library_hero.jpg",
        root / "config" / "grid" / f"{app_id}.jpg",
        root / "config" / "grid" / f"{app_id}.png",
    ))
    return preferred, secondary


def steam_art_hashes(game):
    """Public asset hashes are obtained only from this PC's Steam cache."""
    app_id = str(getattr(game, "app_id", "") or "")
    if str(getattr(game, "launcher", "")).casefold() != "steam" or (
            not app_id.isascii() or not app_id.isdecimal() or len(app_id) > 12):
        return ()
    result = []
    for root in _steam_locations(str(getattr(game, "install_path", "") or "")):
        parent = root / "appcache" / "librarycache" / app_id
        try:
            if parent.is_dir() and not parent.is_symlink():
                for child in islice(parent.iterdir(), 48):
                    if child.is_dir() and not child.is_symlink() and _HASH.fullmatch(child.name):
                        result.append(child.name)
        except (OSError, ValueError):
            continue
    return tuple(dict.fromkeys(result[:6]))


@lru_cache(maxsize=512)
def _cover_path(launcher: str, app_id: str, install_path: str,
                stable_key: str) -> str:
    base = artwork_cache_dir()
    # User overrides are stable across scans and distinct same-name games.
    overrides = [
        base / "custom" / f"{stable_key}.jpg",
        base / "custom" / f"{stable_key}.png",
        base / "custom" / f"{stable_key}.webp",
        # Explicitly requested Steam Store title match for other launchers.
        base / "catalog-match" / f"{stable_key}.jpg",
    ]
    if launcher.casefold() == "steam" and app_id.isascii() and (
            app_id.isdecimal() and len(app_id) <= 12):
        overrides.append(base / "official-steam" / f"{app_id}.jpg")
    for p in overrides:
        if _usable(p):
            return str(p)

    portraits, landscapes = [], []
    try:
        folder = Path(install_path)
        portraits.extend(folder / filename for filename in (
            "cover.jpg", "cover.png", "cover.webp",
            "poster.jpg", "poster.png", "poster.webp",
            "boxart.jpg", "boxart.png", "library_600x900.jpg",
            "Artwork/cover.jpg", "Artwork/cover.png",
            "Images/cover.jpg", "Images/cover.png",
            "Assets/StoreLogo.png", "Assets/Square150x150Logo.png",
            "Assets/Square44x44Logo.png", "Assets/StoreLogo.scale-200.png",
        ))
        landscapes.extend(folder / filename for filename in (
            "folder.jpg", "folder.png", "banner.jpg", "banner.png",
            "header.jpg", "header.png",
            "Assets/Wide310x150Logo.png", "Assets/SplashScreen.png",
        ))
    except (OSError, ValueError):
        pass
    if launcher.casefold() == "steam" and app_id.isascii() and (
            app_id.isdecimal() and len(app_id) <= 12):
        # Steam's own portrait is preferred to a generic game-folder image.
        steam_portraits, steam_landscapes = [], []
        for root in _steam_locations(install_path):
            a, b = _steam_cache_candidates(root, app_id)
            steam_portraits.extend(a)
            steam_landscapes.extend(b)
        for p in steam_portraits + portraits + steam_landscapes + landscapes:
            if _usable(p):
                return str(p)
    else:
        for p in portraits + landscapes:
            if _usable(p):
                return str(p)
    return ""


def game_cover_path(game) -> str:
    """Absolute path to verified local artwork, or empty when unavailable."""
    return _cover_path(
        str(getattr(game, "launcher", "") or ""),
        str(getattr(game, "app_id", "") or ""),
        str(getattr(game, "install_path", "") or ""),
        _game_key(game))


@lru_cache(maxsize=256)
def _banner_path(launcher: str, app_id: str, install_path: str) -> str:
    """Prefer a genuine wide Steam hero/header for the selected-game panel."""
    candidates = []
    if (launcher.casefold() == "steam" and app_id.isascii()
            and app_id.isdecimal() and len(app_id) <= 12):
        for root in _steam_locations(install_path):
            _portraits, secondary = _steam_cache_candidates(root, app_id)
            # Landscape headers/heroes are intended for the wide inspector.
            candidates.extend(secondary)
    try:
        root = Path(install_path)
        candidates.extend(root / name for name in (
            "banner.jpg", "banner.png", "header.jpg", "header.png",
            "background.jpg", "background.png",
            "Images/banner.jpg", "Images/header.jpg",
            "Assets/Wide310x150Logo.png", "Assets/SplashScreen.png",
        ))
    except (OSError, ValueError):
        pass
    for candidate in candidates[:100]:
        if _usable(candidate):
            return str(candidate)
    return ""


def game_banner_path(game) -> str:
    """Wide verified header if available, otherwise the real cover poster."""
    return (_banner_path(
        str(getattr(game, "launcher", "") or ""),
        str(getattr(game, "app_id", "") or ""),
        str(getattr(game, "install_path", "") or ""))
        or game_cover_path(game))


def invalidate_cover_cache():
    """Call after a user override or official cover finishes downloading."""
    _cover_path.cache_clear()
    _banner_path.cache_clear()


def save_custom_cover(game, image_path: str) -> str:
    """Validate and thumbnail one user-selected image into private app storage.

    Does not retain the source path, open unrelated game files, or upload data.
    """
    from PIL import Image, UnidentifiedImageError
    src = Path(image_path)
    if not _usable(src):
        raise ValueError("Select a JPG, PNG or WebP picture under 16 MB.")
    try:
        with Image.open(src) as image:
            if image.format not in ("JPEG", "PNG", "WEBP"):
                raise ValueError("Only JPG, PNG and WebP cover images are supported.")
            if image.width < 100 or image.height < 100 or (
                    image.width * image.height > 32_000_000):
                raise ValueError("Cover dimensions must be 100-8000 pixels, at most 32 MP.")
            image = image.convert("RGB")
            image.thumbnail((720, 1080))
            target_dir = artwork_cache_dir() / "custom"
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / (_game_key(game) + ".jpg")
            tmp = target.with_suffix(".partial")
            try:
                image.save(tmp, format="JPEG", quality=90, optimize=True)
                tmp.replace(target)
            finally:
                tmp.unlink(missing_ok=True)
    except (OSError, UnidentifiedImageError) as exc:
        raise ValueError("Could not decode this cover image.") from exc
    invalidate_cover_cache()
    return str(target)
