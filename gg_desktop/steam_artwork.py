"""On-demand official Steam artwork cache. Never guess images from game names.

No automatic service, accounts, telemetry, game paths, or library uploads.
Only validated Steam AppIDs are requested, only while the app is open and
the user's Games/Ready Room view needs artwork. Failed requests back off.
"""
from __future__ import annotations

from pathlib import Path
import os
import re
import tempfile
import time
import urllib.parse
import urllib.request

_ALLOWED_HOSTS = {"shared.fastly.steamstatic.com", "cdn.cloudflare.steamstatic.com"}
_MAX_BYTES = 5 * 1024 * 1024
_TIMEOUT = 3
_FAILURE_TTL = 24 * 3600


def verified_steam_id(game) -> str:
    if str(getattr(game, "launcher", "")).casefold() != "steam":
        return ""
    app_id = str(getattr(game, "app_id", "") or "")
    if not re.fullmatch(r"[1-9][0-9]{0,9}", app_id):
        return ""
    return app_id


def artwork_cache_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if root:
        return Path(root) / "GameGrave" / "OfficialSteamArtwork"
    return Path.home() / ".cache" / "gamegrave" / "official-steam-artwork"


def cached_steam_cover(app_id: str) -> str:
    if not re.fullmatch(r"[1-9][0-9]{0,9}", str(app_id)):
        return ""
    dest = artwork_cache_dir() / (app_id + ".jpg")
    try:
        if dest.is_file() and not dest.is_symlink() and 1000 <= dest.stat().st_size <= _MAX_BYTES:
            return str(dest)
    except OSError:
        pass
    return ""


def _urls(app_id: str) -> tuple[str, ...]:
    if not re.fullmatch(r"[1-9][0-9]{0,9}", app_id):
        return ()
    # Official Steam CDN. Newer content-hashed assets are normally found in
    # Steam's local hashed library cache before this legacy URL fallback.
    return (
        f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{app_id}/library_600x900.jpg",
        f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/library_600x900.jpg",
        f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/header.jpg",
    )


def fetch_steam_cover(game, *, game_active=None, opener=None) -> str:
    """Fetch one authentic Steam image, only if not cached and no game is active.

    Call in a background-priority worker. This function never accesses local
    game installation paths, never follows an off-domain redirect, and caps
    the response before writing an atomically replaced cache file.
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
        if failed.is_file() and time.time() - failed.stat().st_mtime < _FAILURE_TTL:
            return ""
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        return ""
    fetcher = opener or urllib.request.urlopen
    for url in _urls(app_id):
        if game_active is not None and game_active():
            return ""
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "GameGrave/1.0 (official Steam artwork)"})
            with fetcher(request, timeout=_TIMEOUT) as response:
                final_url = urllib.parse.urlsplit(response.geturl())
                if final_url.scheme != "https" or final_url.hostname not in _ALLOWED_HOSTS:
                    continue
                content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
                if content_type not in ("image/jpeg", "image/jpg", "image/png"):
                    continue
                data = response.read(_MAX_BYTES + 1)
            if not (1000 <= len(data) <= _MAX_BYTES and
                    (data.startswith(b"\xff\xd8\xff") or data.startswith(b"\x89PNG\r\n\x1a\n"))):
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


def prime_visible_covers(games, *, limit: int = 9, active=None) -> int:
    """At most nine requested covers, sequential and strictly on demand."""
    from gg_desktop.local_art import game_cover_path, invalidate_cover_cache
    from performance_guard import GameActivityDetector, background_worker_priority
    detector = active or GameActivityDetector()
    downloaded = 0
    seen = set()
    with background_worker_priority():
        for game in list(games)[:max(0, min(limit, 9))]:
            if detector.active():
                break
            ident = verified_steam_id(game)
            if not ident or ident in seen or game_cover_path(game):
                continue
            seen.add(ident)
            if fetch_steam_cover(game, game_active=detector.active):
                downloaded += 1
                invalidate_cover_cache()
    return downloaded
