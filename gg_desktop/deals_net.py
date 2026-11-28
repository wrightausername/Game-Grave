"""Deals tab: the only network calls, plus the GG.deals key. Called from background jobs, never the screen's own thread.

Hosts: www.cheapshark.com (official stores, no key) and api.gg.deals (key reseller prices, only with the user's own key).
Pictures: https only, image content, 2 MB at most. Nothing about the user or this PC is sent; a search sends the typed
title, a price check sends CheapShark's game numbers or Steam app numbers.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request

from gg_desktop import deals_core as dc

AGENT = "GameGrave-Deals/1.0 (+https://github.com/wrightausername/Game-Grave)"
TIMEOUT = 15
IMAGE_LIMIT = 2 * 1024 * 1024
STORES_TTL = 24 * 3600


class DealsError(Exception):
    """A plain sentence for the screen."""


def folder() -> Path:
    from core import config_dir
    path = Path(config_dir()) / "deals"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _open(url, accept="application/json"):
    request = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": accept})
    return urllib.request.urlopen(request, timeout=TIMEOUT)


def get_json(url):
    if not dc.api_allowed(url):
        raise DealsError("Game Grave only asks CheapShark and GG.deals for prices.")
    try:
        with _open(url) as response:
            return json.loads(response.read(4 * 1024 * 1024).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise DealsError("The price service asked Game Grave to slow down. Try again in a minute.") from None
        if exc.code in (401, 403):
            raise DealsError("The price service refused the request. If this is GG.deals, check your API key.") from None
        raise DealsError(f"The price service answered with an error ({exc.code}). Try again later.") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise DealsError("Couldn't reach the price service. Check your internet connection.") from None
    except ValueError:
        raise DealsError("The price service sent an answer Game Grave couldn't read.") from None


def _stores_raw():
    cache = folder() / "stores-raw.json"
    try:
        saved = json.loads(cache.read_text(encoding="utf-8"))
        if time.time() - float(saved.get("at", 0)) < STORES_TTL and saved.get("stores"):
            return saved["stores"]
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    raw = get_json(dc.stores_url())
    if dc.parse_stores(raw):
        try:
            cache.write_text(json.dumps({"at": time.time(), "stores": raw}), encoding="utf-8")
        except OSError:
            pass
    return raw


def stores():
    return dc.parse_stores(_stores_raw())


def store_icons():
    try:
        return dc.parse_store_icons(_stores_raw())
    except DealsError:
        return {}


def front():
    """The storefront rows: {key: [Deal]}. A row that can't be read comes back empty with the others still shown."""
    known = stores()
    out, problems = {}, []
    for n, (key, _title, _note, params) in enumerate(dc.FRONT):
        try:
            out[key] = dc.parse_deals(get_json(dc.deals_list_url(params)), known)
        except DealsError as exc:
            out[key] = []
            problems.append(str(exc))
        if n + 1 < len(dc.FRONT):
            time.sleep(0.3)
    if not any(out.values()) and problems:
        raise DealsError(problems[0])
    return out


def search(title):
    title = (title or "").strip()
    if len(title) < 2:
        raise DealsError("Type at least two letters of the game's name.")
    return dc.parse_search(get_json(dc.search_url(title)))


def game(game_id):
    found = dc.parse_game(game_id, get_json(dc.game_url(game_id)), stores())
    if found is None:
        raise DealsError("CheapShark has no price record for that game.")
    return found


def games(game_ids):
    known = stores()
    out = {}
    for n in range(0, len(game_ids), dc.BATCH):
        part = list(game_ids)[n:n + dc.BATCH]
        out.update(dc.parse_games(get_json(dc.games_url(part)), known))
        if n + dc.BATCH < len(game_ids):
            time.sleep(1.5)              # spaced out, so a long wishlist never hammers the service
    return out


def keyshops(app_id, key):
    if not app_id or not key:
        return None
    return dc.parse_ggdeals(get_json(dc.ggdeals_url([app_id], key)), app_id)


def image(url):
    if not dc.image_allowed(url):
        return b""
    try:
        with _open(url, "image/*") as response:
            if not str(response.headers.get("Content-Type", "")).startswith("image/"):
                return b""
            data = response.read(IMAGE_LIMIT + 1)
            return b"" if len(data) > IMAGE_LIMIT else data
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return b""


# ------------------------------------------------------------------ the GG.deals key (encrypted for this Windows account)
def _key_file() -> Path:
    return folder() / "ggdeals_key.json"


def save_key(key):
    key = (key or "").strip()
    if not dc.valid_ggdeals_key(key):
        raise DealsError("That doesn't look like a GG.deals API key. Copy it from your GG.deals settings.")
    import base64
    raw, how = key.encode("utf-8"), "file"
    if os.name == "nt":
        from gg_desktop.nexus_core import _dpapi
        try:
            raw, how = _dpapi(raw, True), "windows"
        except OSError as problem:
            raise DealsError(f"Windows would not encrypt the key, so it was not saved: {problem}") from None
    temp = _key_file().with_suffix(".tmp")
    temp.write_text(json.dumps({"how": how, "key": base64.b64encode(raw).decode("ascii")}), encoding="utf-8")
    os.replace(temp, _key_file())


def load_key():
    import base64
    try:
        data = json.loads(_key_file().read_text(encoding="utf-8"))
        raw = base64.b64decode(data["key"])
        if data.get("how") == "windows":
            from gg_desktop.nexus_core import _dpapi
            raw = _dpapi(raw, False)
        return raw.decode("utf-8")
    except (OSError, ValueError, KeyError, TypeError):
        return ""


def forget_key():
    try:
        _key_file().unlink()
    except OSError:
        pass


def free_now():
    """Games their store lists at $0 right now (CheapShark), for free game alerts."""
    params = next(p for key, _t, _n, p in dc.FRONT if key == "free")
    return dc.parse_deals(get_json(dc.deals_list_url(dict(params, pageSize=20))), stores())


def about(app_ids, limit=30, pause=0.35):
    """{Steam app number: short description} for these games, from a 30-day cache in the Deals folder, asking Steam's
    public store for at most `limit` missing ones, spaced out. A game Steam won't describe is cached as "" so it isn't
    asked again for a month. Network trouble stops the lookups quietly; what was found is kept."""
    path = folder() / "about.json"
    try:
        cache = json.loads(path.read_text(encoding="utf-8"))
        cache = cache if isinstance(cache, dict) else {}
    except (OSError, ValueError):
        cache = {}
    now = time.time()
    for app in dc.about_wanted(app_ids, cache, now)[:limit]:
        try:
            text = dc.parse_about(get_json(dc.about_url(app)), app)
        except DealsError:
            break
        cache[app] = {"at": now, "text": text}
        time.sleep(pause)
    try:
        path.write_text(json.dumps(cache), encoding="utf-8")
    except OSError:
        pass
    return {app: str(hit.get("text") or "") for app, hit in cache.items() if isinstance(hit, dict) and app.isdigit()}


def media(app_id):
    """Steam's screenshots, trailers and store facts for one game: (screenshots, trailers, details). Only the Steam app
    number is sent."""
    if not str(app_id or "").isdigit():
        return [], [], {}
    data = get_json(dc.media_url(app_id))
    shots, movies = dc.parse_media(data, app_id)
    return shots, movies, dc.parse_details(data, app_id)



def steam_ids(titles, limit=20, pause=0.35):
    """{title: Steam app number or ""} for games CheapShark lists without one, by an exact name match in Steam's store
    search. Cached 30 days with the descriptions; only the title is sent."""
    path = folder() / "about.json"
    try:
        cache = json.loads(path.read_text(encoding="utf-8"))
        cache = cache if isinstance(cache, dict) else {}
    except (OSError, ValueError):
        cache = {}
    now = time.time()
    out, asked = {}, 0
    for title in dict.fromkeys(t for t in titles if t):
        key = "t:" + title.casefold()
        hit = cache.get(key)
        if isinstance(hit, dict) and now - float(hit.get("at", 0)) < dc.ABOUT_DAYS * 86400:
            out[title] = str(hit.get("app") or "")
            continue
        if asked >= limit:
            continue
        try:
            app = dc.match_steam(get_json(dc.steam_search_url(title)), title)
        except DealsError:
            break
        asked += 1
        cache[key] = {"at": now, "app": app}
        out[title] = app
        time.sleep(pause)
    try:
        path.write_text(json.dumps(cache), encoding="utf-8")
    except OSError:
        pass
    return out
