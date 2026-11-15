"""Qt-free search across everything Game Grave knows: tabs, tools, games, mods, saves, old files and captures.
It reads only what the last scan already found; it never looks at the disk. Each hit says where it opens.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

GROUPS = ("Tabs", "Tools", "Games", "Mods", "Saves", "Old Files", "Captures")
PER_GROUP = 6
MAX_HITS = 30
MAX_SCAN = 60000          # items looked at per kind, so typing stays quick on a huge scan


@dataclass(frozen=True)
class Hit:
    group: str
    title: str
    detail: str
    target: str            # tab:<Tab>, or an assistant target such as tool:<key>, kit:easy, bisect, tour
    search: str = ""       # text put in that tab's own search box, so the item is shown there
    score: int = 0


def _leaf(path):
    return re.split(r"[\\/]", str(path).rstrip("\\/"))[-1]


def score(query, text):
    """0 = no match. Whole text first, then the start of the text, the start of a word, anywhere."""
    q, t = query.casefold().strip(), str(text).casefold()
    if not q or not t:
        return 0
    if t == q:
        return 100
    if t.startswith(q):
        return 80
    if re.search(r"(^|[\s\-_.\\/(])" + re.escape(q), t):
        return 60
    if q in t:
        return 40
    words = q.split()
    if len(words) > 1 and all(w in t for w in words):
        return 30
    return 0


def _best(query, items, limit=PER_GROUP):
    found = []
    for i, (text, hit) in enumerate(items):
        if i >= MAX_SCAN:
            break
        s = score(query, text)
        if s:
            found.append((s, -len(str(text)), i, hit))
    found.sort(key=lambda x: (-x[0], -x[1], x[2]))
    seen, out = set(), []
    for s, _, _, hit in found:
        key = (hit.title.casefold(), hit.target)
        if key in seen:
            continue
        seen.add(key)
        out.append(Hit(hit.group, hit.title, hit.detail, hit.target, hit.search, s))
        if len(out) >= limit:
            break
    return out


def find(query, tabs=(), features=(), inventory=None):
    """`tabs`: [(route, shown name, line)]; `features`: assistant features; `inventory`: the last scan."""
    query = " ".join(str(query or "").split())
    if len(query) < 2:
        return []
    groups = []
    groups.append(_best(query, [(f"{name} {line}", Hit("Tabs", name, line, "tab:" + route)) for route, name, line in tabs]))
    groups.append(_best(query, [(f"{f.title} {' '.join(f.keywords[:6])}",
                                 Hit("Tools", f.title, (f.what.split(". ")[0] or "")[:90], f.opens or ("tab:" + f.tab if f.tab else "")))
                                for f in features if (f.opens or f.tab)]))
    if inventory is not None:
        games = getattr(inventory, "games", []) or []
        groups.append(_best(query, [(g.name, Hit("Games", g.name, getattr(g, "launcher", "") or "Game", "tab:Games", g.name))
                                    for g in games if getattr(g, "name", "")]))
        mods = getattr(inventory, "mods", []) or []
        groups.append(_best(query, [(getattr(m, "name", "") or _leaf(getattr(m, "path", "")),
                                     Hit("Mods", getattr(m, "name", "") or _leaf(getattr(m, "path", "")),
                                         str(getattr(m, "game", "") or getattr(m, "source", "") or "Mod"), "tab:Mods",
                                         getattr(m, "name", "") or _leaf(getattr(m, "path", ""))))
                                    for m in mods if getattr(m, "name", "") or getattr(m, "path", "")]))
        saves = getattr(inventory, "saves", []) or []
        groups.append(_best(query, [(f"{getattr(s, 'game', '')} {_leaf(getattr(s, 'path', ''))}",
                                     Hit("Saves", str(getattr(s, "game", "") or _leaf(getattr(s, "path", ""))),
                                         str(getattr(s, "path", "")), "tab:Games", str(getattr(s, "game", "") or "")))
                                    for s in saves]))
        files = getattr(inventory, "files", []) or []
        groups.append(_best(query, [(_leaf(f.path), Hit("Old Files", _leaf(f.path), str(f.path), "tab:Old Files", _leaf(f.path)))
                                    for f in files if getattr(f, "path", "")]))
        captures = list(getattr(inventory, "screenshots", []) or []) + list(getattr(inventory, "recordings", []) or [])
        groups.append(_best(query, [(_leaf(c.path), Hit("Captures", _leaf(c.path), str(c.path), "tab:Captures", _leaf(c.path)))
                                    for c in captures if getattr(c, "path", "")]))
    hits = [h for g in groups for h in g]
    return hits[:MAX_HITS]
