"""On-demand official Steam library covers with modern hash-aware StoreBrowse.

SteamAppID is required; matching by approximate game title is forbidden.
Network lookups run only in a low-priority worker on explicit/visible-card
requests and never when a game is detected. Cover downloads are small,
redirect-validated and cached on the device. No game files are modified.
"""
from __future__ import annotations

import json
from pathlib import Path
import os
import re
import tempfile
import time
import urllib.parse
import urllib.request

_ALLOWED_HOSTS = {
    "shared.fastly.steamstatic.com",
    "shared.cloudflare.steamstatic.com",
    "shared.steamstatic.com",
    "cdn.cloudflare.steamstatic.com",
}
_API_HOST = "api.steampowered.com"
_MAX_BYTES = 5 * 1024 * 1024
_MAX_METADATA = 256 * 1024
_TIMEOUT = 3
_FAILURE_TTL = 6 * 3600
_APP_ID = re.compile(r"[1-9][0-9]{0,9}\Z")
_ASSET = re.compile(
    r"(?:[0-9a-fA-F]{32,40}/)?library_600x900(?:_2x)?\.(?:jpg|png)\Z"
)


def verified_steam_id(game) -> str:
    if str(getattr(game, "launcher", "")).casefold() != "steam":
        return ""
    ident = str(getattr(game, "app_id", "") or "")
    return ident if _APP_ID.fullmatch(ident) else ""


def artwork_cache_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if root:
        return Path(root) / "GameGrave" / "OfficialSteamArtwork"
    return Path.home() / ".cache" / "gamegrave" / "official-steam-artwork"


def cached_steam_cover(app_id: str) -> str:
    if not _APP_ID.fullmatch(str(app_id)):
        return ""
    dest = artwork_cache_dir() / (str(app_id) + ".jpg")
    try:
        if (dest.is_file() and not dest.is_symlink()
                and 1000 <= dest.stat().st_size <= _MAX_BYTES):
            return str(dest)
    except OSError:
        pass
    return ""


def _urls(app_id: str) -> tuple[str, ...]:
    """Legacy fallback for app IDs whose fixed URL still has real portrait art.

    Never substitute a wide header cropped to 600:900 as if it were box art.
    """
    if not _APP_ID.fullmatch(app_id):
        return ()
    return (
        f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{app_id}/library_600x900_2x.jpg",
        f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{app_id}/library_600x900.jpg",
        f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/library_600x900.jpg",
    )


def _checked_host(response, allowed: set[str]) -> bool:
    try:
        uri = urllib.parse.urlsplit(response.geturl())
        return (uri.scheme == "https" and uri.hostname in allowed
                and uri.username is None and uri.password is None
                and uri.port in (None, 443))
    except (TypeError, ValueError, AttributeError):
        return False


def _read_store_assets(app_id: str, opener=None) -> tuple[str, ...]:
    """Discover hashed portrait asset names from Steam's public store metadata.

    A fixed CDN path returns 404 for newer games, even if Steam has the real
    cover in a content-hash directory. The metadata ties assets to the AppID.
    """
    if not _APP_ID.fullmatch(app_id):
        return ()
    query = json.dumps({
        "ids": [{"appid": int(app_id)}],
        "context": {"country_code": "US", "language": "english"},
        "data_request": {"include_assets": True},
    }, separators=(",", ":"))
    url = ("https://api.steampowered.com/IStoreBrowseService/GetItems/v1/"
           "?input_json=" + urllib.parse.quote(query, safe=""))
    fetcher = opener or urllib.request.urlopen
    try:
        with fetcher(urllib.request.Request(
            url, headers={"User-Agent": "GameGrave/1.0 (official Steam cover)"}),
                timeout=_TIMEOUT) as response:
            if not _checked_host(response, {_API_HOST}):
                return ()
            raw = response.read(_MAX_METADATA + 1)
        if len(raw) > _MAX_METADATA:
            return ()
        payload = json.loads(raw)
        items = payload.get("response", {}).get("store_items", [])
        item = next((row for row in items if isinstance(row, dict)
                     and str(row.get("appid")) == app_id), None)
        if not item:
            return ()
        assets = item.get("assets")
        if not isinstance(assets, dict):
            return ()
        # We do NOT follow an arbitrary asset_url_format returned by a
        # server. Build our own trusted-host URLs using validated filenames.
        names = []
        for key in ("library_capsule_2x", "library_capsule"):
            filename = assets.get(key)
            if isinstance(filename, str) and _ASSET.fullmatch(filename):
                if filename not in names:
                    names.append(filename)
        urls = []
        for name in names:
            path = f"steam/apps/{app_id}/{name}"
            urls.extend([
                "https://shared.fastly.steamstatic.com/store_item_assets/" + path,
                "https://shared.cloudflare.steamstatic.com/store_item_assets/" + path,
            ])
        return tuple(urls)
    except (OSError, ValueError, KeyError, TypeError, UnicodeError, TimeoutError):
        return ()


def _local_hash_urls(app_id: str, install_path: str) -> tuple[str, ...]:
    """Use a known Steam AppID's local hash folders to request missing portrait.

    This reads only filenames from that specific cache folder. It does not
    crawl other apps' artwork, enumerate user images, or upload local paths.
    """
    if not _APP_ID.fullmatch(app_id):
        return ()
    try:
        from gg_desktop.local_art import _steam_locations
    except ImportError:
        return ()
    urls = []
    for root in _steam_locations(install_path):
        folder = root / "appcache" / "librarycache" / app_id
        try:
            if not folder.is_dir() or folder.is_symlink():
                continue
            count = 0
            for child in folder.iterdir():
                if (not child.is_dir() or child.is_symlink() or
                        not re.fullmatch("[0-9a-fA-F]{32,40}", child.name)):
                    continue
                for filename in ("library_600x900_2x.jpg",
                                 "library_600x900.jpg"):
                    urls.append(
                        "https://shared.fastly.steamstatic.com/store_item_assets/"
                        f"steam/apps/{app_id}/{child.name}/{filename}")
                count += 1
                if count >= 6:
                    break
        except (OSError, ValueError):
            continue
    return tuple(urls)


def fetch_steam_cover(game, *, game_active=None, opener=None,
                      force=False) -> str:
    """Fetch one exact-AppID official portrait in the lowest-priority worker.

    Honors previous retry backoff; force=True is reserved for a user pressing
    Refresh Missing Artwork. No game process data, file paths, or account
    details are sent to Steam, only Steam AppIDs.
    """
    app_id = verified_steam_id(game)
    if not app_id:
        return ""
    present = cached_steam_cover(app_id)
    if present:
        return present
    if game_active is not None and game_active():
        return ""
    folder = artwork_cache_dir()
    failed = folder / (app_id + ".retry")
    try:
        if (not force and failed.is_file()
                and time.time() - failed.stat().st_mtime < _FAILURE_TTL):
            return ""
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        return ""
    fetcher = opener or urllib.request.urlopen
    # Metadata is preferred; local hashes and fixed URLs are resilient
    # fallbacks when the public metadata service is unavailable.
    urls = [*_read_store_assets(app_id, opener=opener),
            *_local_hash_urls(app_id, str(getattr(game, "install_path", "") or "")),
            *_urls(app_id)]
    seen = set()
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        if game_active is not None and game_active():
            return ""
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "GameGrave/1.0 (official Steam cover)"})
            with fetcher(request, timeout=_TIMEOUT) as response:
                if not _checked_host(response, _ALLOWED_HOSTS):
                    continue
                content_type = response.headers.get(
                    "Content-Type", "").split(";")[0].strip().lower()
                if content_type not in ("image/jpeg", "image/jpg", "image/png"):
                    continue
                data = response.read(_MAX_BYTES + 1)
            if not (1000 <= len(data) <= _MAX_BYTES and (
                    data.startswith(b"\xff\xd8\xff")
                    or data.startswith(b"\x89PNG\r\n\x1a\n"))):
                continue
            if game_active is not None and game_active():
                return ""
            handle, name = tempfile.mkstemp(dir=folder, suffix=".part")
            try:
                with os.fdopen(handle, "wb") as target:
                    target.write(data)
                os.replace(name, folder / (app_id + ".jpg"))
            finally:
                if os.path.exists(name):
                    os.unlink(name)
            if failed.exists():
                try:
                    failed.unlink()
                except OSError:
                    pass
            return cached_steam_cover(app_id)
        except (OSError, ValueError, TimeoutError):
            continue
    try:
        failed.touch()
    except OSError:
        pass
    return ""


def prime_visible_covers(games, *, limit: int = 9, active=None,
                         force=False) -> int:
    """At most 24 requested covers in a single batch, never while gaming.

    The default visible-page batch is 9. The user can explicitly request a
    larger catch-up batch with force. Every download is sequential, bounded
    and performed by a low CPU/disk priority worker. No continuous service.
    """
    from gg_desktop.local_art import game_cover_path, invalidate_cover_cache
    from performance_guard import GameActivityDetector, background_worker_priority
    detector = active or GameActivityDetector()
    downloaded = 0
    seen = set()
    with background_worker_priority():
        for game in list(games)[:max(0, min(limit, 24))]:
            if detector.active():
                break
            ident = verified_steam_id(game)
            if not ident or ident in seen or (not force and game_cover_path(game)):
                continue
            seen.add(ident)
            if fetch_steam_cover(game, game_active=detector.active, force=force):
                downloaded += 1
                invalidate_cover_cache()
    return downloaded
