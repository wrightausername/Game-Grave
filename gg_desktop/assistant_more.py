"""More AI Assistant answers: greetings, counts, where to look to free space, saves, hardware, moving a game, game
updates. Pure: no file access. Hardware facts are only what Windows already reported to the Hardware tab.

Rules kept from the engine: nothing is called safe to remove, reported sizes stay "reported", and every answer says
where its numbers come from and which tab acts on them.
"""
from __future__ import annotations

import re

GREETINGS = {"hi", "hey", "hello", "yo", "sup", "hiya", "howdy", "morning", "evening", "afternoon"}
THANKS = {"thanks", "thank", "thx", "ty", "cheers", "appreciate", "nice", "cool", "great", "awesome", "perfect", "ok",
          "okay"}
GENERIC_NAME_WORDS = {"the", "of", "and", "edition", "special", "remastered", "definitive", "game", "games", "simulator",
                      "collection", "complete", "ultimate", "deluxe", "anniversary", "enhanced", "goty", "year", "online",
                      "world", "war", "legends", "edition", "version", "director's", "directors", "cut", "part"}


def _norm(text):
    return re.sub(r"[^a-z0-9 ]+", " ", text.casefold())


def nickname_match(games, question):
    """A game named by a short form ("cyberpunk", "skyrim"): a distinctive word of 5+ letters from exactly one title."""
    words = set(_norm(question).split())
    owners = {}
    for g in games:
        for w in set(_norm(g.name).split()):
            if len(w) >= 5 and w not in GENERIC_NAME_WORDS and not w.isdigit():
                owners.setdefault(w, set()).add(g.key)
    hits = {}
    for w in words:
        keys = owners.get(w, set())
        if len(keys) == 1:
            key = next(iter(keys))
            hits[key] = hits.get(key, 0) + len(w)
    if not hits:
        return None
    best = max(hits, key=lambda k: hits[k])
    return next(g for g in games if g.key == best)


def is_small_talk(words):
    """'hi', 'thanks', 'ok cool' and the like: short messages made only of greeting or thanks words."""
    plain = [w.strip(".'!") for w in words if w.strip(".'!")]
    if not plain or len(plain) > 4:
        return ""
    if all(w in GREETINGS | {"there", "claude", "assistant", "gg"} for w in plain) and any(w in GREETINGS for w in plain):
        return "greet"
    if all(w in THANKS | {"you", "so", "much", "a", "lot", "very", "man", "bro", "dude", "that", "works", "it"}
           for w in plain) and any(w in THANKS for w in plain):
        return "thanks"
    return ""


def drive_of(path):
    path = str(path or "")
    return path[0].upper() if len(path) >= 2 and path[1] == ":" and path[0].isalpha() else ""


def gb(value):
    return f"{value / 1024 ** 3:,.0f} GB" if value >= 10 * 1024 ** 3 else f"{value / 1024 ** 3:,.1f} GB"
