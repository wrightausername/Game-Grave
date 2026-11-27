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


def stores():
    cache = folder() / "stores.json"
    try:
        saved = json.loads(cache.read_text(encoding="utf-8"))
        if time.time() - float(saved.get("at", 0)) < STORES_TTL and saved.get("stores"):
            return dict(saved["stores"])
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    found = dc.parse_stores(get_json(dc.stores_url()))
    if found:
        try:
            cache.write_text(json.dumps({"at": time.time(), "stores": found}), encoding="utf-8")
        except OSError:
            pass
    return found


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
