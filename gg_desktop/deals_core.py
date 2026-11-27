"""Deals tab: the cheapest price for a game, and a wishlist that watches prices. No Qt and no network in this module.

Sources (owner choice, 2026-11-27: "Official plus key resellers", in a new Deals tab in Library):
* Official and authorized stores come from CheapShark's free public API (www.cheapshark.com, no key): Steam, GOG, Epic,
  Humble, Fanatical, GreenManGaming and the other stores it lists. Prices are in US dollars, as CheapShark reports them.
* Key resellers (G2A, Kinguin, Eneba and the like) have no free public price feed. With the user's own free GG.deals API
  key (api.gg.deals), GG.deals' current and lowest keyshop prices are shown, always labelled as key resellers with a
  warning. Without a key, Deals offers searches on the resellers' own sites in the browser and shows no number.

Honesty rules: every price says where it came from; nothing is called the cheapest anywhere, only the cheapest Game Grave
found in these sources; key reseller prices always carry the warning; Game Grave never buys anything, it only opens the
store page in the browser.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import time
from urllib.parse import quote, quote_plus, urlparse

CHEAPSHARK = "https://www.cheapshark.com/api/1.0"
GGDEALS = "https://api.gg.deals/v1/prices/by-steam-app-id/"
API_HOSTS = {"www.cheapshark.com", "api.gg.deals"}
MAX_WISHLIST = 100
BATCH = 25                 # CheapShark answers up to 25 games per request
WATCH_HOURS = 6            # the wishlist is checked at most this often while Game Grave runs
WISHLIST_KEY, CHECKED_KEY = "deals_wishlist", "deals_checked_at"
FREE_ALERTS_KEY, FREE_CHECKED_KEY, FREE_SEEN_KEY, FREE_NOW_KEY = ("deals_free_alerts", "deals_free_checked_at",
                                                                  "deals_free_seen", "deals_free_now")
DROPS_KEY = "deals_recent_drops"
RESELLER_WARNING = ("Key reseller: keys come from third-party sellers, not the publisher. They can be region-locked, "
                    "resold or revoked later. Buy at your own risk.")


@dataclass(frozen=True)
class Hit:
    game_id: str
    title: str
    steam_app_id: str
    cheapest: float | None
    thumb: str


@dataclass(frozen=True)
class Offer:
    store: str
    store_id: str
    price: float
    retail: float | None
    savings: int
    url: str


@dataclass
class GameDeals:
    game_id: str
    title: str
    steam_app_id: str
    thumb: str
    offers: list = field(default_factory=list)       # cheapest first
    lowest_ever: float | None = None
    lowest_ever_date: str = ""

    @property
    def best(self):
        return self.offers[0] if self.offers else None


@dataclass(frozen=True)
class Keyshops:
    current: float | None
    lowest: float | None
    retail_lowest: float | None
    url: str
    currency: str


def money(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def price_text(value, currency="USD") -> str:
    if value is None:
        return "—"
    if value == 0:
        return "Free"
    sign = {"USD": "$", "EUR": "€", "GBP": "£"}.get(currency, "")
    return f"{sign}{value:,.2f}" if sign else f"{value:,.2f} {currency}"


def deal_url(deal_id: str) -> str:
    """CheapShark asks apps to send buyers through its redirect link, which opens the store's own page."""
    return "https://www.cheapshark.com/redirect?dealID=" + quote(str(deal_id), safe="")


def search_url(title: str, limit: int = 40) -> str:
    return f"{CHEAPSHARK}/games?title={quote_plus(title.strip())}&limit={int(limit)}&exact=0"


def game_url(game_id: str) -> str:
    return f"{CHEAPSHARK}/games?id={quote(str(game_id), safe='')}"


def games_url(game_ids) -> str:
    return f"{CHEAPSHARK}/games?ids={','.join(quote(str(g), safe='') for g in game_ids)}"


def stores_url() -> str:
    return f"{CHEAPSHARK}/stores"


def ggdeals_url(app_ids, key: str, region: str = "us") -> str:
    return f"{GGDEALS}?ids={','.join(str(a) for a in app_ids)}&key={quote(key, safe='')}&region={quote(region, safe='')}"


def api_allowed(url: str) -> bool:
    parts = urlparse(url)
    return parts.scheme == "https" and parts.hostname in API_HOSTS


def image_allowed(url: str) -> bool:
    return urlparse(str(url or "")).scheme == "https"


def reseller_links(title: str):
    """Searches on the resellers' own sites, opened in the browser. Game Grave reads nothing from them."""
    q = quote_plus(title.strip())
    return (("G2A", f"https://www.g2a.com/search?query={q}"),
            ("Kinguin", f"https://www.kinguin.net/listing?phrase={q}"),
            ("Eneba", f"https://www.eneba.com/store/all?text={q}"),
            ("GG.deals (all shops)", f"https://gg.deals/search/?title={q}"))


@dataclass(frozen=True)
class Deal:
    """One card on the storefront: a game on sale at one store."""
    game_id: str
    title: str
    steam_app_id: str
    price: float
    retail: float | None
    savings: int
    store: str
    store_id: str
    url: str
    rating: str          # Steam's own review summary as CheapShark reports it ("Very Positive"), or ""
    rating_pct: int
    metacritic: int
    thumb: str


# The storefront's rows (owner, 2026-11-27: the tab "just feels heartless"). Each is one CheapShark /deals request.
FRONT = (
    ("best", "Best deals right now", "Ranked by CheapShark's deal rating (price, discount and reviews together).",
     {"sortBy": "Deal Rating", "pageSize": 12, "onSale": 1}),
    ("free", "Free to keep right now", "Full games their store lists at $0 for a limited time. Claim them in the store.",
     {"upperPrice": 0, "pageSize": 8, "sortBy": "Recent"}),
    ("big", "Big games, big discounts", "Games that usually cost $30 or more, biggest discount first.",
     {"AAA": 1, "sortBy": "Savings", "pageSize": 12, "onSale": 1}),
)


def deals_list_url(params) -> str:
    query = "&".join(f"{quote(str(k), safe='')}={quote(str(v), safe='')}" for k, v in params.items())
    return f"{CHEAPSHARK}/deals?{query}"


def art_url(steam_app_id, thumb="") -> str:
    """A big picture for a card: Steam's own header image when the game is on Steam, else the store thumbnail."""
    app = str(steam_app_id or "")
    if app.isdigit():
        return f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app}/header.jpg"
    return str(thumb or "")


def parse_store_icons(data) -> dict:
    out = {}
    for s in data if isinstance(data, list) else []:
        images = s.get("images") if isinstance(s, dict) and isinstance(s.get("images"), dict) else {}
        icon = str(images.get("icon") or "")
        if icon.startswith("/"):
            out[str(s.get("storeID"))] = "https://www.cheapshark.com" + icon
    return out


def _int(value):
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return 0


def parse_deals(data, stores) -> list:
    out, seen = [], set()
    for d in data if isinstance(data, list) else []:
        if not isinstance(d, dict) or not d.get("dealID") or not d.get("gameID"):
            continue
        store_id = str(d.get("storeID", ""))
        if stores and store_id not in stores:
            continue
        price = money(d.get("salePrice"))
        if price is None or str(d["gameID"]) in seen:
            continue
        seen.add(str(d["gameID"]))
        out.append(Deal(str(d["gameID"]), str(d.get("title") or "Unknown game"), str(d.get("steamAppID") or ""),
                        price, money(d.get("normalPrice")), max(0, min(100, _int(d.get("savings")))),
                        stores.get(store_id, f"Store {store_id}"), store_id, deal_url(d["dealID"]),
                        str(d.get("steamRatingText") or ""), _int(d.get("steamRatingPercent")),
                        _int(d.get("metacriticScore")), str(d.get("thumb") or "")))
    return out


def meter(game: GameDeals):
    """Where today's best price sits between the lowest ever and the usual price: (now, usual, lowest), all known, else
    None. Drawn as the deal meter; nothing is guessed."""
    best = game.best
    usual = max((o.retail for o in game.offers if o.retail), default=None)
    if best is None or usual is None or game.lowest_ever is None or usual <= 0:
        return None
    return best.price, usual, min(game.lowest_ever, best.price)


# ------------------------------------------------------------------ parsing CheapShark
def parse_stores(data) -> dict:
    out = {}
    for s in data if isinstance(data, list) else []:
        if isinstance(s, dict) and s.get("storeID") is not None and str(s.get("isActive", 1)) != "0":
            out[str(s["storeID"])] = str(s.get("storeName") or f"Store {s['storeID']}")
    return out


def parse_search(data):
    hits = []
    for g in data if isinstance(data, list) else []:
        if not isinstance(g, dict) or not g.get("gameID"):
            continue
        hits.append(Hit(str(g["gameID"]), str(g.get("external") or g.get("internalName") or "Unknown game"),
                        str(g.get("steamAppID") or ""), money(g.get("cheapest")), str(g.get("thumb") or "")))
    return hits


def _date(value) -> str:
    try:
        return datetime.fromtimestamp(int(value)).strftime("%b %Y")
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


def parse_game(game_id, data, stores) -> GameDeals | None:
    if not isinstance(data, dict) or not isinstance(data.get("info"), dict):
        return None
    info = data["info"]
    offers = []
    for d in data.get("deals") or []:
        if not isinstance(d, dict) or not d.get("dealID"):
            continue
        price = money(d.get("price"))
        if price is None:
            continue
        store_id = str(d.get("storeID", ""))
        if stores and store_id not in stores:
            continue                     # stores CheapShark marks inactive are left out
        retail = money(d.get("retailPrice"))
        try:
            savings = int(round(float(d.get("savings") or 0)))
        except (TypeError, ValueError):
            savings = 0
        offers.append(Offer(stores.get(store_id, f"Store {store_id}"), store_id, price, retail, max(0, min(100, savings)),
                            deal_url(d["dealID"])))
    offers.sort(key=lambda o: (o.price, o.store.casefold()))
    ever = data.get("cheapestPriceEver") if isinstance(data.get("cheapestPriceEver"), dict) else {}
    return GameDeals(str(game_id), str(info.get("title") or "Unknown game"), str(info.get("steamAppID") or ""),
                     str(info.get("thumb") or ""), offers, money(ever.get("price")), _date(ever.get("date")))


def parse_games(data, stores) -> dict:
    out = {}
    for game_id, value in (data.items() if isinstance(data, dict) else ()):
        parsed = parse_game(game_id, value, stores)
        if parsed is not None:
            out[str(game_id)] = parsed
    return out


def parse_ggdeals(data, app_id) -> Keyshops | None:
    if not isinstance(data, dict) or not data.get("success"):
        return None
    entry = (data.get("data") or {}).get(str(app_id))
    if not isinstance(entry, dict):
        return None
    prices = entry.get("prices") if isinstance(entry.get("prices"), dict) else {}
    return Keyshops(money(prices.get("currentKeyshops")), money(prices.get("historicalKeyshops")),
                    money(prices.get("historicalRetail")), str(entry.get("url") or ""), str(prices.get("currency") or "USD"))


def valid_ggdeals_key(key: str) -> bool:
    key = (key or "").strip()
    return 16 <= len(key) <= 200 and all(c.isalnum() or c in "-_" for c in key)


# ------------------------------------------------------------------ wishlist
def wishlist(settings) -> list:
    raw = settings.get(WISHLIST_KEY) if isinstance(settings, dict) else None
    out = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict) and item.get("game_id") and item.get("title"):
            out.append({"game_id": str(item["game_id"]), "title": str(item["title"])[:200],
                        "steam_app_id": str(item.get("steam_app_id") or ""), "thumb": str(item.get("thumb") or ""),
                        "target": money(item.get("target")), "best": money(item.get("best")),
                        "store": str(item.get("store") or ""), "url": str(item.get("url") or ""),
                        "notified": money(item.get("notified")), "added": item.get("added") or 0})
    return out[:MAX_WISHLIST]


def with_wishlist(settings, items):
    out = dict(settings)
    out[WISHLIST_KEY] = list(items)[:MAX_WISHLIST]
    return out


def on_wishlist(items, game_id) -> bool:
    return any(i["game_id"] == str(game_id) for i in items)


def add_item(items, game: GameDeals, target=None, now=None):
    if on_wishlist(items, game.game_id):
        return [dict(i, target=money(target)) if i["game_id"] == game.game_id else i for i in items]
    if len(items) >= MAX_WISHLIST:
        raise ValueError(f"The wishlist holds {MAX_WISHLIST} games. Remove one first.")
    best = game.best
    return items + [{"game_id": game.game_id, "title": game.title, "steam_app_id": game.steam_app_id, "thumb": game.thumb,
                     "target": money(target), "best": best.price if best else None, "store": best.store if best else "",
                     "url": best.url if best else "", "notified": best.price if best else None,
                     "added": int(now if now is not None else time.time())}]


def remove_item(items, game_id):
    return [i for i in items if i["game_id"] != str(game_id)]


def due(settings, now=None) -> bool:
    try:
        last = float(settings.get(CHECKED_KEY) or 0)
    except (TypeError, ValueError):
        last = 0
    return (now if now is not None else time.time()) - last >= WATCH_HOURS * 3600


def batches(items):
    ids = [i["game_id"] for i in items]
    return [ids[n:n + BATCH] for n in range(0, len(ids), BATCH)]


def drop_message(item, game: GameDeals):
    """A notice for a real price drop, else None. A drop counts when the best price reaches the target, or is at least 5%
    and 50 cents below the last price the user was told about. The same price never notifies twice."""
    best = game.best
    if best is None:
        return None
    told = item.get("notified")
    target = item.get("target")
    if told is not None and best.price >= told:
        return None
    hit_target = target is not None and best.price <= target and (told is None or told > target)
    big = told is not None and (told - best.price) >= max(0.5, told * 0.05)
    if not (hit_target or big or (told is None and target is None and best.savings >= 50)):
        return None
    was = f" (was {price_text(told)})" if told is not None else ""
    why = " That's at or under your target." if hit_target else ""
    low = " Lowest price CheapShark has seen." if game.lowest_ever is not None and best.price <= game.lowest_ever else ""
    return f"{price_text(best.price)} at {best.store}{was}.{why}{low}"


def refreshed(items, games: dict, now=None):
    """(new wishlist, [(title, message)]) after a price check. Items CheapShark didn't answer for keep their old price."""
    out, news = [], []
    for item in items:
        game = games.get(item["game_id"])
        if game is None:
            out.append(item)
            continue
        message = drop_message(item, game)
        best = game.best
        new = dict(item, best=best.price if best else None, store=best.store if best else "", url=best.url if best else "",
                   thumb=game.thumb or item["thumb"])
        if message:
            new["notified"] = best.price
            news.append((item["title"], message))
        elif best is not None and item.get("notified") is not None and best.price > item["notified"]:
            new["notified"] = best.price       # price went back up: the next real drop from here is news again
        out.append(new)
    return out, news


def summary(game: GameDeals) -> str:
    best = game.best
    if best is None:
        return "No store CheapShark tracks is selling this right now."
    text = f"Cheapest found: {price_text(best.price)} at {best.store}"
    if best.retail and best.retail > best.price:
        text += f" ({best.savings}% off {price_text(best.retail)})"
    if game.lowest_ever is not None:
        text += f". Lowest ever: {price_text(game.lowest_ever)}" + (f" ({game.lowest_ever_date})" if game.lowest_ever_date else "")
    return text + "."


# ------------------------------------------------------------------ free game alerts (owner, 2026-11-27)
def free_alerts_on(settings) -> bool:
    return bool(settings.get(FREE_ALERTS_KEY, True)) if isinstance(settings, dict) else True


def free_due(settings, now=None) -> bool:
    try:
        last = float(settings.get(FREE_CHECKED_KEY) or 0)
    except (TypeError, ValueError):
        last = 0
    return (now if now is not None else time.time()) - last >= WATCH_HOURS * 3600


def free_update(settings, deals, now=None):
    """(new settings, [Deal]) after a free-games check: the list shown on Overview's Today strip, and the giveaways that
    are new since the last check. Only games their store lists at $0 count. The seen list keeps the newest 300 ids."""
    free = [d for d in deals if d.price == 0]
    seen = [str(x) for x in (settings.get(FREE_SEEN_KEY) or []) if isinstance(x, (str, int))]
    known = set(seen)
    fresh = [d for d in free if d.game_id not in known]
    out = dict(settings)
    out[FREE_SEEN_KEY] = (seen + [d.game_id for d in fresh])[-300:]
    out[FREE_NOW_KEY] = [{"game_id": d.game_id, "title": d.title, "store": d.store, "url": d.url} for d in free[:12]]
    out[FREE_CHECKED_KEY] = now if now is not None else time.time()
    return out, fresh


def free_message(fresh):
    """(title, detail) for one quiet notice, or None."""
    if not fresh:
        return None
    if len(fresh) == 1:
        d = fresh[0]
        return (f"Free to keep: {d.title}",
                f"On {d.store} for a limited time. Claim it in the store; Game Grave doesn't claim anything for you.")
    names = ", ".join(d.title for d in fresh[:3]) + (f" and {len(fresh) - 3} more" if len(fresh) > 3 else "")
    return (f"{len(fresh)} games are free to keep right now", names + ". Open Deals to claim them in their stores.")


def remember_drops(settings, news, now=None, keep=20):
    """Keep the newest price-drop notices for Overview's Today strip."""
    stamp = now if now is not None else time.time()
    old = [d for d in (settings.get(DROPS_KEY) or []) if isinstance(d, dict) and d.get("title")]
    out = dict(settings)
    out[DROPS_KEY] = (old + [{"title": t, "message": m, "at": stamp} for t, m in news])[-keep:]
    return out
