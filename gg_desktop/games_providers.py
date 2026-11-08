"""Read-only, authenticated Games libraries for Steam, Epic, EA and GOG.

Credentials come from the app's explicit sign-in window, never other apps'
credential files. Provider responses cannot change shared installation data.
"""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from html.parser import HTMLParser
import json
import re
import time
from urllib.parse import quote, urlencode

from gg_desktop.games_http import ProviderError, SignInRequired, cookie_header, json_request, request

EPIC_AUTH = "account-public-service-prod03.ol.epicgames.com"
EPIC_LIBRARY = "library-service.live.use1a.on.epicgames.com"
EPIC_ASSETS = "launcher-public-service-prod06.ol.epicgames.com"
EPIC_CATALOG = "catalog-public-service-prod06.ol.epicgames.com"
# Public desktop OAuth client identity, used by the Epic launcher protocol.
# User access/refresh tokens are separate and encrypted in the private store.
EPIC_CLIENT = "34a02cf8f4414e29b15921876da36f9a"
_EPIC_DESKTOP = "daafbccc737745039dffe53d94fc76cf"
EA_API = "service-aggregation-layer.juno.ea.com"
MAX_GAMES = 10000


def identifier(value):
    value = str(value or "")
    return value if re.fullmatch(r"[A-Za-z0-9_.:-]{1,180}", value) else ""


def number(value):
    return value if type(value) in (int, float) and 0 <= value <= 10**13 else None


def epoch(value):
    if number(value) is not None:
        return float(value)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError, OverflowError):
        return None


def _stopped(canceled):
    if canceled():
        raise InterruptedError("Library refresh canceled. The previous library is retained.")


def _snapshot(provider, account_id, name, items):
    if not account_id or len(items) > MAX_GAMES:
        raise ProviderError("The service returned an unsupported library.")
    return dict(provider=provider, account_id=str(account_id)[:100], account_name=str(name or provider)[:160],
                checked_at=time.time(), items=items)


class SteamPage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.result = {}

    def handle_starttag(self, _tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id") == "application_config":
            try:
                user = json.loads(attrs.get("data-userinfo", "{}"))
                config = json.loads(attrs.get("data-store_user_config", "{}"))
                if user.get("logged_in") and re.fullmatch(r"[0-9]{17}", str(user.get("steamid", ""))):
                    token = config.get("webapi_token")
                    if isinstance(token, str) and 0 < len(token) < 16000:
                        self.result = dict(account_id=str(user["steamid"]), access_token=token)
            except (ValueError, TypeError, AttributeError):
                pass


def steam_token_from_html(raw):
    parser = SteamPage()
    parser.feed(raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw)
    return parser.result


def fetch_steam(secret, *, get=json_request, raw_get=request, canceled=lambda: False, progress=lambda *_: None, previous=None, on_credentials=lambda _secret: None):
    account = str(secret.get("account_id", ""))
    if not re.fullmatch(r"[0-9]{17}", account):
        raise SignInRequired("Connect your Steam account first.")
    def library(token):
        return get("https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?" + urlencode(dict(
            steamid=account, access_token=token, include_appinfo=1, include_played_free_games=1)),
            hosts={"api.steampowered.com"})
    _stopped(canceled)
    try:
        data = library(secret.get("access_token", ""))
    except SignInRequired:
        cookies = cookie_header(secret.get("cookies", []), "store.steampowered.com")
        html = raw_get("https://store.steampowered.com/explore/", hosts={"store.steampowered.com"}, headers={"Cookie": cookies})
        updated = steam_token_from_html(html)
        if updated.get("account_id") != account:
            raise SignInRequired("Sign in to the same Steam account again.")
        secret = {**secret, **updated}
        on_credentials(secret)
        data = library(secret["access_token"])
    body = data.get("response") if isinstance(data, dict) else None
    if not isinstance(body, dict) or "game_count" not in body:
        raise SignInRequired("Steam did not return this account's library. Reconnect Steam.")
    rows = body.get("games", [])
    if not isinstance(rows, list) or len(rows) > MAX_GAMES or body.get("game_count") != len(rows):
        raise ProviderError("Steam returned an incomplete library; the previous library is retained.")
    items = []
    for game in rows:
        _stopped(canceled)
        ident = str(game.get("appid", ""))
        if not re.fullmatch(r"[1-9][0-9]{0,9}", ident) or not isinstance(game.get("name"), str):
            continue
        minutes = number(game.get("playtime_forever"))
        items.append(dict(id=ident, title=game["name"][:170],
            playtime_seconds=minutes * 60 if minutes is not None else None,
            last_played_at=epoch(game.get("rtime_last_played")), aliases=[ident]))
    progress(100, "Steam library and playtime refreshed")
    return _snapshot("Steam", account, secret.get("account_name", "Steam account"), items), secret


def exchange_epic_code(code, *, get=json_request, refresh=False):
    if not isinstance(code, str) or not 0 < len(code) < 16000 or any(c in code for c in "\r\n\0"):
        raise SignInRequired("Epic did not return a usable sign-in code.")
    auth = base64.b64encode((EPIC_CLIENT + ":" + _EPIC_DESKTOP).encode()).decode()
    form = {"grant_type": "refresh_token" if refresh else "authorization_code", "token_type": "eg1"}
    form["refresh_token" if refresh else "code"] = code
    result = get(f"https://{EPIC_AUTH}/account/api/oauth/token", hosts={EPIC_AUTH},
                 headers={"Authorization": "Basic " + auth}, form=form)
    if (not isinstance(result, dict) or not isinstance(result.get("access_token"), str)
            or not identifier(result.get("account_id")) or result.get("errorCode")):
        raise SignInRequired("Epic sign-in was not completed. Try connecting again.")
    return dict(access_token=result["access_token"], refresh_token=result.get("refresh_token", ""),
                account_id=result["account_id"], account_name=result.get("displayName", "Epic account"),
                expires_at=time.time() + min(number(result.get("expires_in")) or 3600, 86400))


def _epic_session(secret, get, on_credentials):
    if not secret.get("access_token"):
        raise SignInRequired("Connect Epic Games first.")
    if secret.get("expires_at", 0) < time.time() + 30:
        new = exchange_epic_code(secret.get("refresh_token", ""), get=get, refresh=True)
        if new["account_id"] != secret.get("account_id"):
            raise SignInRequired("The Epic account changed. Connect it again.")
        secret = {**secret, **new}
        on_credentials(secret)
    return secret


def fetch_epic(secret, *, get=json_request, canceled=lambda: False, progress=lambda *_: None, previous=None, on_credentials=lambda _secret: None, **_kwargs):
    secret = _epic_session(secret, get, on_credentials)
    headers = {"Authorization": "Bearer " + secret["access_token"]}
    records, cursors, cursor = [], set(), None
    for _ in range(200):
        _stopped(canceled)
        query = dict(includeMetadata="true", platform="Windows")
        if cursor:
            query["cursor"] = cursor
        page = get(f"https://{EPIC_LIBRARY}/library/api/public/items?" + urlencode(query), hosts={EPIC_LIBRARY}, headers=headers)
        batch = page.get("records") if isinstance(page, dict) else None
        if not isinstance(batch, list) or len(records) + len(batch) > MAX_GAMES:
            raise ProviderError("Epic returned an unsupported library.")
        records.extend(batch)
        cursor = page.get("responseMetadata", {}).get("nextCursor")
        if not cursor:
            break
        if not isinstance(cursor, str) or len(cursor) > 4000 or cursor in cursors:
            raise ProviderError("Epic returned a repeated library page.")
        cursors.add(cursor)
    else:
        raise ProviderError("Epic library paging exceeded its limit.")
    _stopped(canceled)
    assets = get(f"https://{EPIC_ASSETS}/launcher/api/public/assets/Windows?label=Live", hosts={EPIC_ASSETS}, headers=headers)
    if not isinstance(assets, list):
        raise ProviderError("Epic did not return its current game versions.")
    versions = {str(row.get("appName")): str(row.get("buildVersion", ""))[:300] for row in assets if isinstance(row, dict)}
    try:
        playtimes = get(f"https://{EPIC_LIBRARY}/library/api/public/playtime/account/{quote(secret['account_id'], safe='')}/all",
                        hosts={EPIC_LIBRARY}, headers=headers)
    except ProviderError:
        playtimes = []
    times = {str(row.get("artifactId")): number(row.get("totalTime")) for row in playtimes if isinstance(row, dict)} if isinstance(playtimes, list) else {}
    cached = {str(item.get("id")): item for item in (previous or {}).get("items", []) if isinstance(item, dict)}
    usable = []
    for record in records:
        if not isinstance(record, dict):
            continue
        app, namespace, catalog = (identifier(record.get(key)) for key in ("appName", "namespace", "catalogItemId"))
        if app and namespace and catalog and namespace != "ue":
            usable.append((app, namespace, catalog))
    def describe(row):
        _stopped(canceled)
        app, namespace, catalog = row
        old = cached.get(app, {})
        # Publisher catalogue fields can be reused; ownership and versions are
        # refreshed independently from this account on every sync.
        if old.get("metadata_at", 0) > time.time() - 86400 * 7:
            info = dict(old)
        else:
            reply = get(f"https://{EPIC_CATALOG}/catalog/api/shared/namespace/{quote(namespace, safe='')}/bulk/items?" +
                        urlencode(dict(id=catalog, includeDLCDetails="true", includeMainGameDetails="true", country="US", locale="en-US")),
                        hosts={EPIC_CATALOG}, headers=headers)
            meta = reply.get(catalog, {}) if isinstance(reply, dict) else {}
            if not isinstance(meta, dict) or not isinstance(meta.get("title"), str):
                raise ProviderError("Epic did not return complete game titles. The previous library is retained.")
            if meta.get("mainGameItem"):
                return None  # DLC is managed on the base game's client page.
            images = [img for img in meta.get("keyImages", []) if isinstance(img, dict) and isinstance(img.get("url"), str)]
            images.sort(key=lambda img: img.get("type") not in ("DieselGameBoxTall", "OfferImageTall"))
            info = dict(title=meta["title"][:170], artwork_url=images[0]["url"] if images else "", metadata_at=time.time())
        return dict(info, id=app, namespace=namespace, catalog_id=catalog, aliases=[app],
                    latest_version=versions.get(app, ""), playtime_seconds=times.get(app))
    items = []
    with ThreadPoolExecutor(max_workers=6, thread_name_prefix="Games-Epic-catalogue") as pool:
        futures = [pool.submit(describe, row) for row in usable]
        try:
            for count, future in enumerate(as_completed(futures), 1):
                _stopped(canceled)
                item = future.result()
                if item:
                    items.append(item)
                progress(int(count * 100 / max(1, len(futures))), f"Epic: {count} of {len(futures)} game details")
        except BaseException:
            for future in futures:
                future.cancel()
            raise
    return _snapshot("Epic Games", secret["account_id"], secret.get("account_name"), items), secret


def ea_access_token(secret, *, get=json_request):
    cookies = cookie_header(secret.get("cookies", []), "accounts.ea.com")
    reply = get("https://accounts.ea.com/connect/auth?" + urlencode(dict(client_id="ORIGIN_JS_SDK", response_type="token",
                redirect_uri="nucleus:rest", prompt="none")), hosts={"accounts.ea.com"}, headers={"Cookie": cookies})
    if not isinstance(reply, dict) or not isinstance(reply.get("access_token"), str):
        raise SignInRequired("Connect your EA account again.")
    return {**secret, "access_token": reply["access_token"],
            "expires_at": time.time() + min(number(reply.get("expires_in")) or 3600, 86400)}


def fetch_ea(secret, *, get=json_request, canceled=lambda: False, progress=lambda *_: None, **_kwargs):
    if not secret.get("access_token") or secret.get("expires_at", 0) < time.time() + 30:
        secret = ea_access_token(secret, get=get)
    def query(text, variables=None):
        _stopped(canceled)
        reply = get(f"https://{EA_API}/graphql", hosts={EA_API}, headers={"Authorization": "Bearer " + secret["access_token"]},
                    data={"query": text, "variables": variables or {}})
        if not isinstance(reply, dict) or reply.get("errors") or not isinstance(reply.get("data"), dict):
            raise SignInRequired("EA did not return the connected library. Sign in again.")
        return reply["data"]
    player = query("query{me{player{pd psd displayName}}}").get("me", {}).get("player", {})
    if not isinstance(player, dict) or not identifier(player.get("pd")):
        raise SignInRequired("EA did not identify the signed-in account.")
    if secret.get("account_id") and secret["account_id"] != str(player["pd"]):
        raise SignInRequired("The EA account changed. Reconnect it before refreshing.")
    secret = {**secret, "account_id": str(player["pd"]), "account_name": str(player.get("displayName", "EA account"))[:160]}
    offers, cursors, cursor = [], set(), None
    entitlement_query = """query getEntitlements($limit:Int,$next:String){me{ownedGameProducts(locale:"DEFAULT",
        entitlementEnabled:true,storefronts:[EA],type:[DIGITAL_FULL_GAME,PACKAGED_FULL_GAME],platforms:[PC],
        paging:{limit:$limit,next:$next}){next items{originOfferId product{baseItem{gameType}}}}}}"""
    for _ in range(200):
        page = query(entitlement_query, {"limit": 100, "next": cursor}).get("me", {}).get("ownedGameProducts", {})
        if not isinstance(page, dict) or not isinstance(page.get("items"), list):
            raise ProviderError("EA returned an unreadable ownership page.")
        for item in page["items"]:
            if isinstance(item, dict) and (item.get("product") or {}).get("baseItem", {}).get("gameType") == "BASE_GAME":
                ident = identifier(item.get("originOfferId"))
                if ident:
                    offers.append(ident)
        if len(offers) > MAX_GAMES:
            raise ProviderError("EA library exceeded its size limit.")
        cursor = page.get("next")
        if cursor is None:
            break
        if not isinstance(cursor, str) or cursor in cursors or len(cursor) > 4000:
            raise ProviderError("EA returned a repeated ownership page.")
        cursors.add(cursor)
    else:
        raise ProviderError("EA library paging exceeded its limit.")
    details_query = """query getOffers($offerIds:[String!]!){legacyOffers(offerIds:$offerIds,locale:"DEFAULT"){offerId:id contentId}
        gameProducts(offerIds:$offerIds,locale:"DEFAULT"){items{id originOfferId baseItem{title packArt{largestImage{path}} keyArt{largestImage{path}}}}}}"""
    items = []
    for offset in range(0, len(offers), 100):
        result = query(details_query, {"offerIds": offers[offset:offset + 100]})
        products = result.get("gameProducts", {}).get("items", [])
        mapping = {str(item.get("originOfferId")): item for item in products if isinstance(item, dict)}
        content = {str(item.get("offerId")): identifier(item.get("contentId")) for item in result.get("legacyOffers", []) if isinstance(item, dict)}
        for ident in offers[offset:offset + 100]:
            product = mapping.get(ident)
            if not product:
                raise ProviderError("EA did not return all game details. The previous library is retained.")
            base = product.get("baseItem") or {}
            if not isinstance(base.get("title"), str):
                raise ProviderError("EA returned an unnamed game.")
            image = ((base.get("packArt") or base.get("keyArt") or {}).get("largestImage") or {}).get("path", "")
            items.append(dict(id=ident, title=base["title"][:170], content_id=content.get(ident, ""),
                aliases=[value for value in (ident, content.get(ident)) if value], artwork_url=image))
        progress(int((offset + 100) * 100 / max(1, len(offers))), f"EA: {len(items)} game details")
    return _snapshot("EA", secret["account_id"], secret["account_name"], items), secret


def fetch_gog(secret, *, get=json_request, canceled=lambda: False, progress=lambda *_: None, **_kwargs):
    def read(url, host):
        _stopped(canceled)
        return get(url, hosts={host}, headers={"Cookie": cookie_header(secret.get("cookies", []), host)})
    account = read("https://menu.gog.com/v1/account/basic", "menu.gog.com")
    if not isinstance(account, dict) or not account.get("isLoggedIn") or not account.get("userId") or not account.get("username"):
        raise SignInRequired("Sign in to GOG again to refresh its library.")
    account_id, username = str(account["userId"]), str(account["username"])
    if secret.get("account_id") and secret["account_id"] != account_id:
        raise SignInRequired("The GOG account changed. Connect it again.")
    secret = {**secret, "account_id": account_id, "account_name": username}
    items = []
    try:
        first = read("https://www.gog.com/u/" + quote(username, safe="") + "/games/stats?sort=recent_playtime&order=desc&page=1", "www.gog.com")
        pages = first.get("pages") if isinstance(first, dict) else None
        if type(pages) is not int or not 0 <= pages <= 200 or not isinstance(first.get("_embedded", {}).get("items"), list):
            raise ProviderError("GOG profile statistics are unavailable.")
        batches = [first]
        for page in range(2, pages + 1):
            batches.append(read("https://www.gog.com/u/" + quote(username, safe="") + "/games/stats?sort=recent_playtime&order=desc&page=" + str(page), "www.gog.com"))
        for batch in batches:
            for row in batch.get("_embedded", {}).get("items", []):
                game = row.get("game", {}) if isinstance(row, dict) else {}
                ident = str(game.get("id", ""))
                if not re.fullmatch(r"[1-9][0-9]{0,19}", ident) or not isinstance(game.get("title"), str):
                    continue
                stats = row.get("stats") or {}
                stats = stats.get(account_id, stats) if isinstance(stats, dict) else {}
                minutes = number(stats.get("playtime")) if isinstance(stats, dict) else None
                items.append(dict(id=ident, aliases=[ident], title=game["title"][:170], artwork_url=game.get("image", ""),
                    playtime_seconds=minutes * 60 if minutes is not None else None,
                    last_played_at=epoch(stats.get("lastSession")) if isinstance(stats, dict) else None))
            if len(items) > MAX_GAMES:
                raise ProviderError("GOG library exceeded its size limit.")
    except ProviderError as exc:
        if isinstance(exc, SignInRequired):
            raise
        items = []
        for page in range(1, 201):
            data = read(f"https://www.gog.com/account/getFilteredProducts?hiddenFlag=0&mediaType=1&page={page}&sortBy=title", "www.gog.com")
            if not isinstance(data, dict) or not isinstance(data.get("products"), list):
                raise ProviderError("GOG did not return its library; the previous library is retained.")
            for game in data["products"]:
                if isinstance(game, dict) and game.get("isGame", True) and not game.get("isMovie"):
                    ident = str(game.get("id", ""))
                    if re.fullmatch(r"[1-9][0-9]{0,19}", ident) and isinstance(game.get("title"), str):
                        items.append(dict(id=ident, aliases=[ident], title=game["title"][:170], artwork_url=game.get("image", "")))
            if len(items) > MAX_GAMES:
                raise ProviderError("GOG library exceeded its size limit.")
            if page >= data.get("totalPages", 1):
                break
        else:
            raise ProviderError("GOG library paging exceeded its limit.")
    progress(100, "GOG ownership and available playtime refreshed")
    return _snapshot("GOG", account_id, username, items), secret


FETCHERS = {"Steam": fetch_steam, "Epic Games": fetch_epic, "EA": fetch_ea, "GOG": fetch_gog}
