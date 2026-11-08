"""Ready Room's on-demand public news and private local records. No Qt required.

Nothing runs at import. News requests send only Steam application IDs, never
local paths or account details. Existing game/mod/save files are never modified.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from html import unescape
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from core import _has_reparse_component, config_dir, read_vdf

MAX_STATE_BYTES = 1024 * 1024
MAX_NEWS_BYTES = 512 * 1024
MAX_NEWS_GAMES = 40


def plain(value, limit=300):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>|\[[^\]]*\]", " ", unescape(str(value)))).strip()[:limit]


def app_id(value):
    text = str(value)
    return text if re.fullmatch(r"[1-9][0-9]{0,9}", text) else ""


def news_url(value, steam_id):
    """Only public Steam news pages can become clickable links."""
    try:
        url = urlsplit(str(value))
        if (url.scheme == "https" and not url.username and not url.password
                and url.port in (None, 443) and
                ((url.hostname == "store.steampowered.com" and url.path.startswith("/news/"))
                 or (url.hostname in ("steamcommunity.com", "www.steamcommunity.com")
                     and url.path.startswith(("/games/", "/app/", "/ogg/"))))):
            return url.geturl()
    except ValueError:
        pass
    return "https://store.steampowered.com/news/app/" + app_id(steam_id) if app_id(steam_id) else ""


def news_kind(title):
    title = title.casefold()
    if re.search(r"\b(hotfix|hot fix)\b", title):
        return "hotfix"
    if re.search(r"\b(maintenance|downtime|server outage|scheduled outage)\b", title):
        return "maintenance"
    if re.search(r"\b(mods?|modding|creation kit|workshop)\b", title):
        return "mod"
    if re.search(r"\b(patch|update|fixes)\b", title):
        return "update"
    if re.search(r"\b(launch|launched|out now|release date|full release)\b", title):
        return "release"
    return "news"


def parse_news(payload, steam_id, name, *, now=None):
    now = time.time() if now is None else now
    container = payload.get("appnews", {}) if isinstance(payload, dict) else {}
    if not isinstance(container, dict) or app_id(container.get("appid")) != app_id(steam_id):
        raise ValueError("Steam returned news for a different game.")
    items = container.get("newsitems", [])
    if not isinstance(items, list):
        raise ValueError("Steam returned an invalid news list.")
    result, seen = [], set()
    for item in items[:20]:
        if not isinstance(item, dict) or item.get("feedname") != "steam_community_announcements":
            continue  # Third-party press articles are not official game updates.
        gid = str(item.get("gid", ""))
        stamp = item.get("date")
        title = plain(item.get("title", ""), 180)
        if (not gid.isdecimal() or gid in seen or not title or type(stamp) not in (int, float)
                or not math.isfinite(stamp) or not 946684800 <= stamp <= now + 86400):
            continue
        seen.add(gid)
        result.append(dict(id=str(steam_id) + ":" + gid, app_id=str(steam_id), game=plain(name, 170),
                           title=title, detail=plain(item.get("contents", "")), timestamp=int(stamp),
                           kind=news_kind(title), url=news_url(item.get("url"), steam_id)))
    return result


class _SteamRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urlsplit(newurl)
        if target.scheme != "https" or target.hostname != "api.steampowered.com" or target.port not in (None, 443):
            raise ValueError("Steam redirected outside its news service.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_one(steam_id, name):
    if not app_id(steam_id):
        raise ValueError("Invalid Steam application ID.")
    query = urlencode(dict(appid=steam_id, count=10, maxlength=400, format="json",
                           feeds="steam_community_announcements"))
    request = Request("https://api.steampowered.com/ISteamNews/GetNewsForApp/v0002/?" + query,
                      headers={"User-Agent": "GameGrave-ReadyRoom/0.2", "Accept": "application/json"})
    with build_opener(_SteamRedirects()).open(request, timeout=8) as response:
        raw = response.read(MAX_NEWS_BYTES + 1)
    if len(raw) > MAX_NEWS_BYTES:
        raise ValueError("Steam news exceeded the response size limit.")
    return parse_news(json.loads(raw), steam_id, name)


def news_targets(games, followed):
    result = {}
    for game in [*followed, *games]:
        field = game.get if isinstance(game, dict) else lambda k, default="": getattr(game, k, default)
        steam_id = app_id(field("app_id")) if field("launcher") == "Steam" else ""
        if steam_id:
            result.setdefault(steam_id, plain(field("name"), 170))
    return list(result.items())


def refresh_news(games, state, *, fetcher=None):
    """Failures keep each affected game's cached news. No polling or auto-fetch."""
    targets = news_targets(games, state.get("followed", []))
    fetcher = fetcher or fetch_one
    checked = dict(state.get("news_checked", {}))
    succeeded, warnings, fresh = set(), [], []

    def get(target):
        steam_id, name = target
        try:
            return steam_id, fetcher(steam_id, name), ""
        except Exception:
            return steam_id, [], name + ": news unavailable; cached posts retained."

    with ThreadPoolExecutor(max_workers=4) as pool:
        for steam_id, items, error in pool.map(get, targets[:MAX_NEWS_GAMES]):
            if error:
                warnings.append(error)
            else:
                succeeded.add(steam_id)
                checked[steam_id] = int(time.time())
                fresh.extend(items)
    if len(targets) > MAX_NEWS_GAMES:
        warnings.append("News covers the first 40 games; followed games take priority.")
    active = {steam_id for steam_id, _ in targets}
    retained = [n for n in state.get("news", []) if n.get("app_id") not in succeeded and n.get("app_id") in active]
    merged = {n["id"]: n for n in retained + fresh}
    return {"news": sorted(merged.values(), key=lambda n: n["timestamp"], reverse=True)[:400],
            "news_checked": checked, "news_warnings": warnings[:45], "succeeded": len(succeeded)}


NEWS_INTERVAL = 30 * 60


def last_checked(state):
    """Newest time Steam answered for any game, or 0 when it has never answered."""
    return max((v for v in state.get("news_checked", {}).values() if type(v) is int), default=0)


def news_is_stale(state, last_attempt=0, *, now=None, interval=NEWS_INTERVAL):
    """True when it is time to ask Steam again. A failed attempt also counts, so an offline PC is not hammered."""
    now = time.time() if now is None else now
    return now - max(last_checked(state), last_attempt or 0) >= interval


def news_status_text(state, games, *, busy=False, failed=False, now=None):
    """The one honest line shown above Patch Watch: what was checked, when, and what has no feed."""
    now = time.time() if now is None else now
    targets = news_targets(games, state.get("followed", []))
    if busy:
        return "Checking Steam for official news…"
    if not targets:
        others = any(getattr(g, "launcher", "Steam") != "Steam" for g in games)
        return ("No official news feed is available for these games. Only Steam publishes one."
                if others else "Scan your games to follow official Steam news.")
    stamp = last_checked(state)
    when = "not checked yet" if not stamp else (
        "just now" if now - stamp < 60 else f"{int((now - stamp) // 60)} min ago" if now - stamp < 3600
        else datetime.fromtimestamp(stamp).strftime("today %H:%M" if now - stamp < 86400 else "%d %b %H:%M"))
    text = f"Official Steam news · last checked {when} · updates every 30 minutes while this page is open"
    if failed:
        text = f"Steam could not be reached · showing saved posts · last checked {when}"
    non_steam = sum(1 for g in games if getattr(g, "launcher", "Steam") != "Steam")
    if non_steam and not failed:
        text += f" · {non_steam} non-Steam game{'s have' if non_steam != 1 else ' has'} no official feed"
    return text


def _empty_state():
    return {"schema": 1, "followed": [], "news": [], "news_checked": {}, "news_warnings": [], "backups": []}


def load_state(directory=None):
    target = Path(directory or config_dir()) / "ready-room.json"
    state = _empty_state()
    try:
        if _has_reparse_component(target) or not target.is_file() or target.stat().st_size > MAX_STATE_BYTES:
            return state
        raw = json.loads(target.read_bytes())
        if not isinstance(raw, dict) or raw.get("schema") != 1:
            return state
        for key in ("followed", "news", "news_warnings", "backups"):
            if isinstance(raw.get(key), list):
                state[key] = raw[key][:400]
        state["followed"] = [g for g in state["followed"] if isinstance(g, dict)
                             and all(isinstance(g.get(k), str) for k in ("key", "name", "launcher", "app_id"))][:200]
        state["news"] = [n for n in state["news"] if isinstance(n, dict)
                         and all(isinstance(n.get(k), str) for k in ("id", "app_id", "game", "title", "detail", "kind", "url"))
                         and type(n.get("timestamp")) is int and 946684800 <= n["timestamp"] <= time.time() + 86400
                         and app_id(n["app_id"])]
        for item in state["news"]:
            item["url"] = news_url(item["url"], item["app_id"])
            for key in ("game", "title", "detail"):
                item[key] = plain(item[key])
        state["backups"] = [b for b in state["backups"] if isinstance(b, dict)
                            and all(isinstance(b.get(k), str) for k in ("source", "destination"))
                            and all(type(b.get(k)) is int and b[k] >= 0 for k in ("created_at", "size", "mtime_ns", "files"))
                            and b["created_at"] <= time.time() + 86400][:200]
        state["news_warnings"] = [plain(w) for w in state["news_warnings"] if isinstance(w, str)][:45]
        if isinstance(raw.get("news_checked"), dict):
            state["news_checked"] = {k: v for k, v in raw["news_checked"].items()
                                     if app_id(k) and type(v) is int and v > 0}
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        return _empty_state()
    return state


def save_state(state, directory=None):
    directory = Path(directory or config_dir())
    raw = json.dumps(state, ensure_ascii=False, indent=2).encode("utf-8")
    if len(raw) > MAX_STATE_BYTES:
        raise ValueError("Ready Room's local history is full.")
    existing = directory
    while not existing.exists() and not existing.is_symlink() and existing.parent != existing:
        existing = existing.parent
    if _has_reparse_component(existing):
        raise ValueError("Ready Room's storage directory is redirected.")
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "ready-room.json"
    if _has_reparse_component(directory) or ((target.exists() or target.is_symlink()) and _has_reparse_component(target)):
        raise ValueError("Ready Room's storage file is redirected.")
    fd, name = tempfile.mkstemp(prefix=".ready-room-", suffix=".tmp", dir=directory)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        if _has_reparse_component(directory) or ((target.exists() or target.is_symlink()) and _has_reparse_component(target)):
            raise ValueError("Ready Room's storage path changed.")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def backup_receipt(report, *, now=None):
    if report.get("verified") is not True:
        raise ValueError("Only a completed, verified backup can enter Save Vault history.")
    path = Path(report["destination"])
    if _has_reparse_component(path) or not path.is_file():
        raise ValueError("The backup file is unavailable.")
    info = path.stat()
    return dict(source=str(report["source"]), destination=str(path), files=int(report["files"]),
                created_at=int(time.time() if now is None else now), size=info.st_size, mtime_ns=info.st_mtime_ns)


def backup_status(receipt):
    path = Path(receipt["destination"])
    try:
        if _has_reparse_component(path) or not path.is_file():
            return "Unavailable"
        info = path.stat()
        return "Verified when created" if (info.st_size, info.st_mtime_ns) == (receipt["size"], receipt["mtime_ns"]) else "Changed: recheck needed"
    except (OSError, ValueError):
        return "Unavailable"


def inspect_local(inventory, extra_roots=()):
    """Read existing bounded manager/history readers, never game contents."""
    from core import _steam_roots
    from manager_profiles import inspect_manager_profiles
    from mod_radar_audit import audit_mod_radar
    profiles = inspect_manager_profiles(inventory.mods, inventory.steam, inventory.other)
    audit = audit_mod_radar(inventory.steam, inventory.other, inventory.mods, inventory.saves,
                            profiles.get("profiles", []))
    playtimes = {}
    for root in _steam_roots(list(extra_roots))[:10]:
        try:
            from itertools import islice
            configs = list(islice((root / "userdata").glob("*/config/localconfig.vdf"), 20))
        except OSError:
            continue
        for path in configs:
            try:
                if _has_reparse_component(path) or not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
                    continue
            except OSError:
                continue
            data = read_vdf(path)
            apps = data
            for key in ("userlocalconfigstore", "software", "valve", "steam", "apps"):
                apps = apps.get(key, {}) if isinstance(apps, dict) else {}
            if not isinstance(apps, dict):
                continue
            for steam_id, details in apps.items():
                if not app_id(steam_id) or not isinstance(details, dict):
                    continue
                try:
                    minutes = int(details["playtime"])
                    if 0 <= minutes <= 100_000_000:
                        playtimes[steam_id] = max(minutes, playtimes.get(steam_id, 0))
                except (KeyError, TypeError, ValueError):
                    continue
    accessible = sum(bool(g.install_path) and Path(g.install_path).is_dir()
                     and not _has_reparse_component(Path(g.install_path)) for g in inventory.games)
    managers = [m for m in inventory.mods if getattr(m, "source", "") in ("Mod Organizer 2", "Vortex")]
    manager_accessible = sum(Path(m.path).is_dir() and not _has_reparse_component(Path(m.path)) for m in managers)
    return dict(audit=audit, profiles=profiles, playtimes=playtimes, accessible_games=accessible,
                manager_count=len(managers), accessible_managers=manager_accessible,
                checked_at=int(time.time()))


def date_label(stamp):
    days = max(0, int((time.time() - stamp) / 86400))
    return "Today" if days == 0 else "Yesterday" if days == 1 else f"{days} days ago" if days < 30 else datetime.fromtimestamp(stamp).strftime("%d %b %Y")
