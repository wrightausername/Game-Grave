"""Overview's Today strip (owner, 2026-11-27: "Add a Today strip"): what needs you today, from what Game Grave already
knows. No Qt, no network; every line comes from a saved fact:
* free games: the last free game check in Deals (`deals_free_now`), if it ran in the last two days;
* wishlist price drops: the notices Deals posted in the last 7 days (`deals_recent_drops`);
* low space: drives that hold games and are in the Graveyard's low zone (under 40 GB or 10% free);
* news: official Steam posts for your games from the last 3 days (Ready Room's saved news).
Nothing is called safe and nothing changes; each line only opens its tab.
"""
from __future__ import annotations

from dataclasses import dataclass
import time

from core import human_size
from gg_desktop import deals_core as dc

FREE_FRESH = 2 * 86400
DROP_DAYS = 7
NEWS_DAYS = 3


@dataclass(frozen=True)
class Line:
    key: str
    text: str
    tip: str
    route: str          # tab it opens; "" for the all-quiet line
    tone: str           # good, warn, bad, info


def items(settings, drives=(), news=(), now=None):
    now = now if now is not None else time.time()
    out = []
    settings = settings if isinstance(settings, dict) else {}

    free = [f for f in settings.get(dc.FREE_NOW_KEY) or [] if isinstance(f, dict) and f.get("title")]
    try:
        checked = float(settings.get(dc.FREE_CHECKED_KEY) or 0)
    except (TypeError, ValueError):
        checked = 0
    if free and now - checked <= FREE_FRESH:
        text = f"Free to keep: {free[0]['title']}" if len(free) == 1 else f"{len(free)} games free to keep"
        out.append(Line("free", text, "Games their store lists at $0 right now. Open Deals to claim them in the store.",
                        "Deals", "warn"))

    drops = [d for d in settings.get(dc.DROPS_KEY) or [] if isinstance(d, dict) and d.get("title")
             and isinstance(d.get("at"), (int, float)) and now - d["at"] <= DROP_DAYS * 86400]
    if drops:
        names = list(dict.fromkeys(d["title"] for d in reversed(drops)))
        text = f"Price drop: {names[0]}" if len(names) == 1 else f"{len(names)} wishlist price drops"
        out.append(Line("drops", text, "; ".join(f"{d['title']}: {d.get('message', '')}" for d in drops[-4:]),
                        "Deals", "good"))

    for d in drives:
        if getattr(d, "low", False):
            out.append(Line("space", f"{d.root.rstrip(chr(92))} is low on space ({human_size(d.free)} free)",
                            "A drive that holds your games is under 40 GB or 10% free. The Graveyard suggests games "
                            "you haven't played in a while to put to rest.", "Graveyard", "bad"))

    recent = [n for n in news if isinstance(n, dict) and isinstance(n.get("timestamp"), int)
              and now - n["timestamp"] <= NEWS_DAYS * 86400]
    if recent:
        games = list(dict.fromkeys(n.get("game", "") for n in recent if n.get("game")))
        text = (f"News for {games[0]}" if len(games) == 1 else f"{len(recent)} news posts for {len(games)} of your games")
        out.append(Line("news", text, "Official Steam posts from the last 3 days. Open Ready Room to read them.",
                        "Ready Room", "info"))

    if not out:
        out.append(Line("quiet", "All quiet: nothing needs you today",
                        "Free games, wishlist price drops, low space and news for your games show here.", "", "info"))
    return out
