"""Qt-free Game Night for Squad Sync: "what can we all play tonight?".

Each friend shares one code with the name they chose and their installed games (title, launcher, Steam app id, size).
Codes go person to person, like squad codes; nothing goes to a server. Matching uses the Steam app id when both sides
have one, else the exact title once cleaned (never a similar title). Co-op / multiplayer comes from Steam's public store
tags, asked only for matched Steam games and cached.
"""
from __future__ import annotations

import base64
import json
import re
import zlib
from dataclasses import dataclass, field

CODE_PREFIX = "GGGN1-"
MAX_GAMES = 600
MAX_FRIENDS = 8
CHAT_LIMIT = 1900          # a Discord message holds 2,000 characters
FRIENDS_KEY = "game_night_friends"
NAME_KEY = "game_night_name"
# Steam store category ids
MULTI = {1: "Multiplayer", 36: "Online multiplayer", 47: "LAN multiplayer"}
COOP = {9: "Co-op", 38: "Online co-op", 48: "LAN co-op", 39: "Shared/split screen co-op", 24: "Shared/split screen"}
SINGLE = 2


class GameNightError(ValueError):
    pass


@dataclass
class Friend:
    name: str
    games: list = field(default_factory=list)     # [{"n": title, "l": launcher, "a": app id, "s": bytes}]
    added: float = 0.0


@dataclass
class Row:
    title: str
    app_id: str
    have: list
    missing: list
    size: int | None = None
    modes: tuple = ()          # ("Online co-op", ...) from Steam, empty when unknown

    @property
    def everyone(self):
        return not self.missing


def clean_title(title):
    t = re.sub(r"[®™©]", "", str(title or "")).casefold()
    t = re.sub(r"\b(game of the year|goty|definitive|deluxe|ultimate|complete|anniversary|remastered) edition\b", "", t)
    return re.sub(r"[^a-z0-9]+", "", t)


def game_entries(games):
    out = []
    for g in games:
        name = str(getattr(g, "name", "") or "").strip()
        if not name:
            continue
        size = getattr(g, "size_bytes", None)
        out.append({"n": name[:120], "l": str(getattr(g, "launcher", "") or "")[:20],
                    "a": str(getattr(g, "app_id", "") or "")[:12] if getattr(g, "launcher", "") == "Steam" else "",
                    "s": int(size) if isinstance(size, int) and size >= 0 else None})
        if len(out) >= MAX_GAMES:
            break
    return out


def make_code(name, games):
    name = " ".join(str(name or "").split())[:24]
    if not name:
        raise GameNightError("Pick the name your friends will see first.")
    body = json.dumps({"v": 1, "who": name, "g": game_entries(games)}, separators=(",", ":")).encode("utf-8")
    return CODE_PREFIX + base64.urlsafe_b64encode(zlib.compress(body, 9)).decode("ascii").rstrip("=")


def find_code(text):
    """The code inside a whole chat message, even when a chat app broke it over lines."""
    flat = re.sub(r"\s+", "", str(text or ""))
    match = re.search(re.escape(CODE_PREFIX) + r"[A-Za-z0-9_\-]+", flat)
    return match.group(0) if match else ""


def read_code(text):
    code = find_code(text)
    if not code:
        raise GameNightError("That isn't a Game Night code. It starts with " + CODE_PREFIX)
    raw = code[len(CODE_PREFIX):]
    try:
        data = json.loads(zlib.decompress(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)), bufsize=4_000_000))
    except Exception:
        raise GameNightError("The code is damaged or cut off. Ask for it again (a file works if chat cuts it).")
    if not isinstance(data, dict) or data.get("v") != 1 or not isinstance(data.get("g"), list):
        raise GameNightError("This code is from a different version of Game Grave.")
    games = []
    for item in data["g"][:MAX_GAMES]:
        if isinstance(item, dict) and isinstance(item.get("n"), str) and item["n"].strip():
            size = item.get("s")
            games.append({"n": item["n"][:120], "l": str(item.get("l") or "")[:20],
                          "a": str(item.get("a") or "") if str(item.get("a") or "").isdigit() else "",
                          "s": size if isinstance(size, int) and size >= 0 else None})
    who = " ".join(str(data.get("who") or "Friend").split())[:24] or "Friend"
    return Friend(who, games)


def _key(entry):
    return ("a", entry["a"]) if entry.get("a") else ("t", clean_title(entry["n"]))


def with_friend(friends, friend, now=0.0):
    """Add or replace (same name) a friend. Newest first, at most MAX_FRIENDS."""
    kept = [f for f in friends if f.name.casefold() != friend.name.casefold()]
    friend.added = now
    return ([friend] + kept)[:MAX_FRIENDS]


def friends_from(settings):
    out = []
    for item in settings.get(FRIENDS_KEY, []) or []:
        if isinstance(item, dict) and isinstance(item.get("name"), str) and isinstance(item.get("games"), list):
            out.append(Friend(item["name"][:24], [g for g in item["games"] if isinstance(g, dict)][:MAX_GAMES],
                              float(item.get("added") or 0)))
    return out[:MAX_FRIENDS]


def friends_to(settings, friends):
    return dict(settings, **{FRIENDS_KEY: [{"name": f.name, "games": f.games, "added": f.added} for f in friends]})


def overlap(me, my_games, friends):
    """Rows for games at least two people have, everyone-has first, then the ones one person is missing."""
    people = [(me, my_games)] + [(f.name, f.games) for f in friends]
    owners, info = {}, {}
    for who, games in people:
        for entry in games:
            key = _key(entry)
            if key == ("t", ""):
                continue
            owners.setdefault(key, [])
            if who not in owners[key]:
                owners[key].append(who)
            info.setdefault(key, entry)
            if info[key].get("s") is None and entry.get("s") is not None:
                info[key] = dict(info[key], s=entry["s"])
    names = [who for who, _ in people]
    rows = []
    for key, have in owners.items():
        if len(have) < 2 and len(names) > 1:
            continue
        entry = info[key]
        rows.append(Row(entry["n"], entry.get("a", ""), have, [n for n in names if n not in have], entry.get("s")))
    rows.sort(key=lambda r: (len(r.missing), -len(r.have), r.title.casefold()))
    return rows


def parse_modes(categories):
    """Steam store categories ([{"id": 9, "description": ...}]) to plain modes, co-op first."""
    ids = {c.get("id") for c in categories or [] if isinstance(c, dict)}
    modes = [COOP[i] for i in COOP if i in ids] + [MULTI[i] for i in MULTI if i in ids]
    if not modes and SINGLE in ids:
        return ("Single-player",)
    return tuple(dict.fromkeys(modes))


def together(row):
    """True when Steam says the game can be played with others (or we don't know: never hide a game on a guess)."""
    return not row.modes or row.modes != ("Single-player",)


def summary(rows, friends):
    if not friends:
        return "Add a friend's code to see what you can all play."
    everyone = [r for r in rows if r.everyone and together(r)]
    almost = [r for r in rows if len(r.missing) == 1 and together(r)]
    who = ", ".join(f.name for f in friends)
    if everyone:
        return f"You and {who} can all play {len(everyone)} game{'s' if len(everyone) != 1 else ''} right now."
    if almost:
        return f"Nothing everyone has installed yet. {len(almost)} game{'s need' if len(almost) != 1 else ' needs'} just one download."
    return "No game in common yet. Compare again after someone installs one."


# ------------------------------------------------------------------ co-op tags from Steam's public store (cached)
STORE_URL = "https://store.steampowered.com/api/appdetails?appids={}&filters=categories"
MAX_LOOKUPS = 25          # per comparison, spaced out


def modes_cache_path():
    from pathlib import Path
    from core import config_dir
    return Path(config_dir()) / "steam_modes.json"


def load_modes(path=None):
    try:
        data = json.loads((path or modes_cache_path()).read_text(encoding="utf-8"))
        return {k: tuple(v) for k, v in data.items() if isinstance(k, str) and isinstance(v, list)}
    except (OSError, ValueError):
        return {}


def save_modes(cache, path=None):
    target = path or modes_cache_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps({k: list(v) for k, v in cache.items()}), encoding="utf-8")
    temp.replace(target)


def fetch_modes(app_ids, cache, opener=None, sleep=None, game_running=lambda: False):
    """Ask Steam for the store tags of app ids not cached yet. Returns the updated cache. Stops while a game runs."""
    import time
    import urllib.request
    opener = opener or (lambda url: urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": "GameGrave/1"}), timeout=15).read(512 * 1024))
    sleep = sleep or time.sleep
    asked = 0
    for app_id in app_ids:
        if not str(app_id).isdigit() or app_id in cache:
            continue
        if asked >= MAX_LOOKUPS or game_running():
            break
        if asked:
            sleep(0.4)
        asked += 1
        try:
            data = json.loads(opener(STORE_URL.format(app_id)))
            entry = data.get(str(app_id), {})
            cats = entry.get("data", {}).get("categories", []) if entry.get("success") else []
            cache[app_id] = parse_modes(cats) if cats else ()
        except Exception:
            continue     # not cached: asked again next time
    return cache


def with_modes(rows, cache):
    for row in rows:
        if row.app_id and row.app_id in cache:
            row.modes = tuple(cache[row.app_id])
    return rows
