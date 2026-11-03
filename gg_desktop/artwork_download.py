"""On-demand public Steam cover retrieval, never a background game monitor.

Only a deliberate user click starts HTTPS requests for verified numeric Steam
app IDs. No game names, paths, file inventories, screenshots or telemetry are
sent. Cache is private to the user's Game Grave profile. A game-aware process
guard interrupts further requests before they begin.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import time
from urllib.request import Request, urlopen

from gg_desktop.local_art import (
    artwork_cache_dir, invalidate_cover_cache, steam_art_hashes,
)

MAX_DOWNLOAD = 8 * 1024 * 1024


def _foreign_fullscreen() -> bool:
    """Do not mistake maximized Game Grave itself for a running game."""
    import os
    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = wintypes.HWND
        hwnd = user32.GetForegroundWindow()
        if hwnd:
            pid = wintypes.DWORD(0)
            user32.GetWindowThreadProcessId(
                hwnd, ctypes.byref(pid))
            if pid.value == os.getpid():
                return False
    except (OSError, ValueError, AttributeError):
        pass
    from performance_guard import _foreground_is_fullscreen
    return _foreground_is_fullscreen()


def official_steam_urls(game):
    app_id = str(getattr(game, "app_id", "") or "")
    if (str(getattr(game, "launcher", "")).casefold() != "steam"
            or not app_id.isascii() or not app_id.isdecimal()
            or not 1 <= len(app_id) <= 12):
        return ()
    base = ("https://shared.fastly.steamstatic.com/"
            "store_item_assets/steam/apps/" + app_id + "/")
    urls = []
    for hash_id in steam_art_hashes(game)[:3]:
        for suffix in ("library_600x900_2x.jpg", "library_600x900.jpg"):
            urls.append(base + hash_id + "/" + suffix)
    for suffix in ("library_600x900_2x.jpg", "library_600x900.jpg"):
        urls.append(base + suffix)
    urls.append("https://cdn.akamai.steamstatic.com/steam/apps/"
                + app_id + "/library_600x900_2x.jpg")
    return tuple(urls[:10])


def _read_public_image(url: str):
    req = Request(url, headers={
        "User-Agent": "GameGrave-Artwork/1.0",
        "Accept": "image/jpeg,image/png",
    })
    with urlopen(req, timeout=3.5) as response:
        media = str(response.headers.get("Content-Type", "")).lower()
        if not media.startswith(("image/jpeg", "image/png")):
            return b""
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_DOWNLOAD:
            return b""
        payload = response.read(MAX_DOWNLOAD + 1)
        return payload if len(payload) <= MAX_DOWNLOAD else b""


def _validated_jpeg(payload: bytes):
    """Reject HTML, SVG and huge/broken image decompression bombs."""
    if not payload or len(payload) < 1000:
        return None
    from PIL import Image, UnidentifiedImageError
    try:
        with Image.open(BytesIO(payload)) as decoded:
            if (decoded.format not in ("JPEG", "PNG")
                    or decoded.width < 130 or decoded.height < 185
                    or decoded.width * decoded.height > 24_000_000
                    or decoded.height / decoded.width < 1.15):
                return None
            decoded.load()
            rgb = decoded.convert("RGB")
            rgb.thumbnail((720, 1080))
            out = BytesIO()
            rgb.save(out, "JPEG", quality=87, optimize=True)
            return out.getvalue()
    except (ValueError, OSError, UnidentifiedImageError):
        return None


def download_official_steam_covers(
        games, *, limit=20, game_active=None, fetch=None, clock=time.monotonic):
    """Retrieve up to 20 missing official covers, only when explicitly invoked.

    Returns counts for the UI. Download occurs on the existing job thread and
    never blocks Qt painting. Avoids any new requests while a game is detected.
    """
    from performance_guard import GameActivityDetector
    detector = GameActivityDetector(refresh_seconds=2.0, fullscreen=_foreign_fullscreen)
    detector.set_game_roots([
        str(getattr(g, "install_path", "") or "") for g in games])
    active = game_active if game_active is not None else detector.active
    downloader = fetch if fetch is not None else _read_public_image
    limit = max(1, min(int(limit), 20))
    seen = set()
    total = completed = skipped = failed = 0
    paused = False
    deadline = clock() + 60.0
    target_dir = artwork_cache_dir() / "official-steam"
    for game in games:
        urls = official_steam_urls(game)
        if not urls:
            continue
        app_id = str(game.app_id)
        if app_id in seen:
            continue
        seen.add(app_id)
        target = target_dir / (app_id + ".jpg")
        if target.exists():
            skipped += 1
            continue
        if total >= limit or clock() >= deadline:
            break
        if active():
            paused = True
            break
        total += 1
        found = False
        for url in urls[:5]:
            if active() or clock() >= deadline:
                paused = True
                break
            try:
                result = _validated_jpeg(downloader(url))
            except (OSError, ValueError, TimeoutError):
                continue
            if not result:
                continue
            target_dir.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(".partial")
            try:
                tmp.write_bytes(result)
                tmp.replace(target)
                found = True
                completed += 1
            finally:
                tmp.unlink(missing_ok=True)
            break
        if not found:
            failed += 1
        if paused:
            break
    if completed:
        invalidate_cover_cache()
    return {
        "checked": total, "downloaded": completed,
        "already_cached": skipped, "unavailable": failed,
        "paused_for_game": paused,
        "remaining": sum(
            1 for g in games
            if str(getattr(g, "launcher", "")).casefold() == "steam"
            and str(getattr(g, "app_id", "") or "").isascii()
            and str(getattr(g, "app_id", "") or "").isdecimal()
            and not (target_dir / (str(g.app_id) + ".jpg")).exists()),
    }


def _strict_title(name: str) -> str:
    """Exact-title normalization only; never silently swap game editions."""
    import re
    import unicodedata
    normalized = unicodedata.normalize("NFKC", str(name)).casefold()
    return re.sub(r"[^a-z0-9]+", "", normalized)


def search_exact_steam_catalog(name: str, *, fetch_json=None) -> str:
    """Match another launcher's game to Steam's *identical* public title.

    The user must explicitly opt in before this is called: a game name is
    transmitted to Steam's Store Search endpoint. No install path or game
    inventory is shared. Ambiguous exact-title matches are refused.
    """
    import json
    from urllib.parse import urlencode
    name = str(name).strip()
    if not 2 <= len(name) <= 120:
        return ""
    term = _strict_title(name)
    if not term:
        return ""
    url = ("https://store.steampowered.com/api/storesearch/?" +
           urlencode({"term": name, "l": "english", "cc": "us"}))
    if fetch_json is None:
        req = Request(url, headers={
            "User-Agent": "GameGrave-Artwork/1.0", "Accept": "application/json"})
        with urlopen(req, timeout=3.5) as response:
            if not str(response.headers.get("Content-Type", "")).lower().startswith(
                    ("application/json", "text/javascript")):
                return ""
            raw = response.read(100_001)
            if len(raw) > 100_000:
                return ""
            entries = json.loads(raw.decode("utf-8"))
    else:
        entries = fetch_json(url)
    if not isinstance(entries, dict):
        return ""
    matches = {
        str(item.get("id")) for item in entries.get("items", [])[:20]
        if isinstance(item, dict) and item.get("type") == "app"
        and _strict_title(item.get("name", "")) == term
        and type(item.get("id")) is int
        and 0 < item["id"] < 10**12
    }
    return next(iter(matches)) if len(matches) == 1 else ""


def download_matched_catalog_covers(
        games, *, limit=8, game_active=None, search=None, fetch=None,
        clock=time.monotonic):
    """User-initiated exact-title store cover lookup for other launchers.

    A game name is sent to Steam only after the user consents in the UI.
    Reuses the same strict image validation and gameplay guard as Steam-ID
    downloads. Never changes any file in the actual game installation.
    """
    import hashlib
    from gg_desktop.local_art import game_cover_path, _game_key
    from performance_guard import GameActivityDetector
    detector = GameActivityDetector(refresh_seconds=2., fullscreen=_foreign_fullscreen)
    detector.set_game_roots([
        str(getattr(g, "install_path", "")) for g in games])
    active = game_active or detector.active
    lookup = search or search_exact_steam_catalog
    fetch_image = fetch or _read_public_image
    max_games = max(1, min(8, int(limit)))
    deadline = clock() + 60
    seen = set()
    checked = downloaded = unmatched = 0
    paused = False
    target_dir = artwork_cache_dir() / "catalog-match"
    for game in games:
        if str(getattr(game, "launcher", "")).casefold() == "steam":
            continue
        key = _game_key(game)
        if key in seen:
            continue
        seen.add(key)
        if checked >= max_games or clock() > deadline:
            break
        if active():
            paused = True
            break
        if game_cover_path(game):
            continue
        checked += 1
        try:
            app_id = lookup(str(game.name))
        except (ValueError, OSError, TimeoutError):
            app_id = ""
        if not app_id or not str(app_id).isascii() or not str(app_id).isdecimal():
            unmatched += 1
            continue
        # Only public portrait URLs from a uniquely verified exact title;
        # no similarity-score best guess or publisher-specific fake cover.
        base = ("https://shared.fastly.steamstatic.com/"
                "store_item_assets/steam/apps/" + str(app_id) + "/")
        urls = (base + "library_600x900_2x.jpg",
                base + "library_600x900.jpg",
                "https://cdn.akamai.steamstatic.com/steam/apps/" +
                str(app_id) + "/library_600x900_2x.jpg")
        found = False
        for url in urls:
            if active() or clock() > deadline:
                paused = True
                break
            try:
                payload = _validated_jpeg(fetch_image(url))
            except (ValueError, OSError, TimeoutError):
                continue
            if not payload:
                continue
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / (key + ".jpg")
            tmp = target.with_suffix(".partial")
            try:
                tmp.write_bytes(payload)
                tmp.replace(target)
                downloaded += 1
                found = True
            finally:
                tmp.unlink(missing_ok=True)
            break
        if not found:
            unmatched += 1
        if paused:
            break
    if downloaded:
        invalidate_cover_cache()
    return {
        "checked": checked, "downloaded": downloaded,
        "unmatched": unmatched, "paused_for_game": paused,
    }
