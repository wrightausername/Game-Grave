"""Local-first Ready Room helpers and bounded official Steam news integration.

No background timers. Only requested visible games can cause network requests,
always by numeric Steam AppID, never paths, installed game lists or file names.
Steam announcements are not independently verified as patch notes: source and
limitations must remain visible in the user interface.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
import re
import time
from typing import Iterable
import urllib.parse
import urllib.request

NEWS_API_HOST = "api.steampowered.com"
NEWS_DOMAINS = {"store.steampowered.com", "steamcommunity.com"}
MAX_RESPONSE = 1_000_000
CACHE_TTL = 30 * 60
_NEWS_CACHE: dict[str, tuple[float, tuple["SteamNews", ...]]] = {}


@dataclass(frozen=True)
class SteamNews:
    app_id: str
    title: str
    url: str
    published: int
    summary: str
    feed: str
    kind: str


def verified_appid(game) -> str:
    if str(getattr(game, "launcher", "")).casefold() != "steam":
        return ""
    value = str(getattr(game, "app_id", "") or "")
    return value if re.fullmatch(r"[1-9][0-9]{0,9}", value) else ""


def prioritize_games(games: Iterable, favorite_keys=(), limit=12) -> list:
    pinned = set(str(x) for x in favorite_keys)
    records = list(games)
    records.sort(key=lambda g: (
        str(getattr(g, "key", "")) not in pinned,
        getattr(g, "last_played_at", None) is None,
        -(getattr(g, "last_played_at", None) or 0),
        str(getattr(g, "name", "")).casefold()))
    return records[:max(0, limit)]


def launch_guard_summary(game) -> tuple[str, str]:
    """Do not infer mod compatibility, backup integrity, or game bootability."""
    if not game:
        return "Unknown", "Run a read-only inventory to detect installed games."
    if "Ambiguous" in str(getattr(game, "status", "")):
        return "Attention", "Multiple launchers claim this folder. Ownership is ambiguous."
    if "Unverified" in str(getattr(game, "status", "")):
        return "Unknown", "This folder is unverified; avoid assuming it is a working game."
    if "Installed" in str(getattr(game, "status", "")):
        return ("Installed", "Installation record found. Game launch, saves, mods "
                "and patch compatibility have not been verified.")
    return "Unknown", "Read-only inventory does not establish this game's launch health."


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.words = []

    def handle_data(self, data):
        self.words.append(data)


def _plain(value, max_length=330) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(str(value)[:4500])
        text = " ".join(" ".join(parser.words).split())
    except (ValueError, TypeError):
        text = ""
    return text[:max_length]


class _StrictSteamRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        candidate = urllib.parse.urlsplit(newurl)
        if candidate.scheme != "https" or candidate.hostname != NEWS_API_HOST:
            raise ValueError("Untrusted news API redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _valid_steam_news_url(value: str) -> bool:
    if not isinstance(value, str) or len(value) > 2000:
        return False
    parsed = urllib.parse.urlsplit(value)
    return (parsed.scheme == "https" and
            parsed.hostname in NEWS_DOMAINS and not parsed.username and
            not parsed.password)


def steam_news(game, *, force=False, fetch=None, clock=time.time) -> tuple[SteamNews, ...]:
    """Get recent Steam announcements for a single validated game.

    Call only from a low-priority worker after game-activity guard. The API may
    include general news: do not label every returned item an official patch.
    """
    app_id = verified_appid(game)
    if not app_id:
        return ()
    now = clock()
    cached = _NEWS_CACHE.get(app_id)
    if cached and not force and now - cached[0] < CACHE_TTL:
        return cached[1]
    query = urllib.parse.urlencode({
        "appid": app_id, "count": 4, "maxlength": 320, "format": "json"})
    url = f"https://{NEWS_API_HOST}/ISteamNews/GetNewsForApp/v0002/?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": "GameGrave/1.0"})
    fetcher = fetch or urllib.request.build_opener(_StrictSteamRedirects()).open
    response = fetcher(request, timeout=4)
    with response:
        target = urllib.parse.urlsplit(response.geturl())
        if target.scheme != "https" or target.hostname != NEWS_API_HOST:
            raise ValueError("Steam news response came from unexpected source")
        payload = response.read(MAX_RESPONSE + 1)
    if len(payload) > MAX_RESPONSE:
        raise ValueError("Steam news response too large")
    decoded = json.loads(payload)
    records = decoded.get("appnews", {}).get("newsitems", [])
    items = []
    for entry in records[:8]:
        if not isinstance(entry, dict) or not _valid_steam_news_url(entry.get("url", "")):
            continue
        title = _plain(entry.get("title", ""), 180)
        if not title:
            continue
        summary = _plain(entry.get("contents", ""), 360)
        ts = entry.get("date", 0)
        ts = ts if type(ts) is int and 0 < ts <= now + 86400 else 0
        is_patch = bool(re.search(r"\b(patch|update|hotfix|maintenance|fixes)\b",
                                  title, re.I))
        items.append(SteamNews(
            app_id=app_id,
            title=title,
            url=entry["url"],
            published=ts,
            summary=summary,
            feed=_plain(entry.get("feedlabel", "Steam"), 70) or "Steam",
            kind="Patch / update" if is_patch else "Announcement"))
    result = tuple(items[:4])
    if len(_NEWS_CACHE) > 48:
        _NEWS_CACHE.clear()
    _NEWS_CACHE[app_id] = (now, result)
    return result


def game_news_batch(games, *, limit=3, active=None, force=False):
    """At most 3 installed Steam titles, while no game is running."""
    from performance_guard import GameActivityDetector, background_worker_priority
    detector = active or GameActivityDetector()
    results = []
    seen = set()
    with background_worker_priority():
        for game in list(games)[:24]:
            if len(seen) >= max(0, min(limit, 3)) or detector.active():
                break
            ident = verified_appid(game)
            if not ident or ident in seen:
                continue
            seen.add(ident)
            try:
                for news in steam_news(game, force=force):
                    results.append((str(getattr(game, "name", "Game")), news))
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
                continue
    results.sort(key=lambda item: -item[1].published)
    return results[:10]
