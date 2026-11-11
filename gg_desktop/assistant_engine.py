"""Local question answering over Game Grave's own scan data. No online service, no file access, nothing changes.

The assistant explains what was recorded. It never says anything is safe to remove, never turns a reported size into
disk space freed, and sends the owner to the tab that owns the files. If a question needs data that is switched off or
was never scanned, it says so instead of guessing.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import re

from core import human_size
from gg_desktop import assistant_data as data
from gg_desktop import assistant_features as features
from gg_desktop import undo_insight
from gg_desktop.models import _path_key

IDLE_DAYS = 180
TOP = 6

QUICK_PROMPTS = (
    ("list", "Largest games by size", "What are my largest games by size?"),
    ("storage", "Summarize my storage", "Where does my storage space go?"),
    ("undo", "Explain my last cleanup", "Explain my last cleanup"),
    ("camera", "Recordings by game", "Show my recordings and screenshots by game"),
    ("clock", "Games not played lately", "Which games haven't I played lately?"),
)

SAFETY_TEXT = ("I can't tell you that something is safe to remove, and I never remove anything. Game Grave only moves "
               "files to the Recycle Bin after you review them and confirm in the tab that owns them, and it checks "
               "again right before it acts. Age, size and a name never prove a file is unused.")
HELP_TEXT = ("I answer from what Game Grave has already scanned on this PC. Try: largest games, where storage space "
             "goes, what is in Other Storage, recordings and screenshots by game, mods, games you haven't played "
             "lately, games per launcher, your cleanup history, or a game by name. You can also ask how a feature works, for "
             "example: what is the Resurrection Kit, how does Save Vault work, what does Black Box do.")
UNKNOWN_TEXT = ("I can't answer that from your scan data. " + HELP_TEXT)


@dataclass(frozen=True)
class Row:
    label: str
    value: str = ""
    share: float | None = None
    tab: str | None = None
    detail: str = ""


@dataclass(frozen=True)
class Answer:
    intent: str
    text: str
    rows: tuple = ()
    note: str = ""
    sources: tuple = ()
    handoffs: tuple = ()  # (button label, tab name)

    def to_dict(self):
        return {"intent": self.intent, "text": self.text, "note": self.note, "sources": list(self.sources),
                "rows": [[r.label, r.value, r.share, r.tab, r.detail] for r in self.rows],
                "handoffs": [list(h) for h in self.handoffs]}


def answer_from_dict(value):
    """Rebuild a saved answer; anything malformed becomes None so a damaged settings file cannot break the page."""
    try:
        rows = tuple(Row(str(r[0])[:200], str(r[1])[:80], None if r[2] is None else float(r[2]),
                         None if r[3] is None else str(r[3]), str(r[4])[:300]) for r in value.get("rows", [])[:12])
        return Answer(str(value["intent"])[:30], str(value["text"])[:2000], rows, str(value.get("note", ""))[:600],
                      tuple(str(s)[:40] for s in value.get("sources", [])[:6]),
                      tuple((str(h[0])[:40], str(h[1])[:30]) for h in value.get("handoffs", [])[:5]))
    except (AttributeError, IndexError, KeyError, TypeError, ValueError):
        return None


# ------------------------------------------------------------------ helpers
def _words(question):
    return re.sub(r"[^a-z0-9:.' ]+", " ", question.casefold()).split()


def _has(words, text, *needles):
    return any((n in text) if " " in n else (n in words) for n in needles)


def _within(path, root):
    path, root = _path_key(path), _path_key(root).rstrip("\\")
    return path == root or path.startswith(root + "\\")


def find_entity(facts, question):
    """The game named in the question (longest name wins), or the game the chat is scoped to."""
    if facts.scope:
        return data.find_game(facts, facts.scope)
    text = question.casefold()
    named = [g for g in facts.games if len(g.name) >= 4 and g.name.casefold() in text]
    return max(named, key=lambda g: len(g.name)) if named else None


def _days(timestamp, now):
    return max(0, int((now - timestamp) // 86400))


def _size(value):
    return human_size(value) if value is not None else "Unknown"


def _needs(facts, key, noun, tab="Ready Room"):
    """None when the source is on and holds data, otherwise the Answer that says why not."""
    name = data.SOURCE_NAMES[key]
    state = next(s for s in data.source_states(facts) if s.key == key)
    if not state.enabled:
        return Answer("off", f"{name} is turned off, so I can't use it. Turn it on in Data Used, then ask again.")
    if not state.count:
        return Answer("empty", f"Game Grave has no {noun} on record yet. Run Scan PC, then ask again.",
                      handoffs=(("Open Ready Room", tab),))
    return None


def _source_names(*keys):
    return tuple(data.SOURCE_NAMES[k] for k in keys)


# ------------------------------------------------------------------ classification
def classify(question, facts):
    text = " ".join(_words(question))
    words = set(text.split())
    if not words:
        return "help", None
    named = find_entity(facts, question)
    if features.find_feature(question, named.name if named else ""):
        return "feature", None
    if _has(words, text, "help", "what can you", "what can i ask", "how do you work"):
        return "help", None
    if _has(words, text, "safe", "safely", "should i delete", "can i delete", "ok to delete", "okay to delete",
            "protected", "protect"):
        return "safety", None
    game = find_entity(facts, question)
    if _has(words, text, "cleanup", "cleaned", "undo", "restore", "restored", "recycle", "recycled", "history",
            "clean up", "removed"):
        return "history", game
    if any(w.startswith("mod") for w in words):
        return "mods", game
    if _has(words, text, "capture", "captures", "recording", "recordings", "screenshot", "screenshots", "clip",
            "clips", "video", "videos", "footage"):
        return "captures", game
    if _has(words, text, "cache", "caches", "log", "logs", "temp", "temporary", "shader", "other storage", "config"):
        return "other", None
    if _has(words, text, "played", "unused", "idle", "stale", "neglected", "abandoned", "untouched", "not used",
            "haven't", "havent"):
        return ("profile", game) if game else ("idle", None)
    if _has(words, text, "launcher", "launchers", "steam", "epic", "gog", "xbox", "ubisoft", "ea app", "battle.net") \
            and _has(words, text, "by", "per", "each", "many", "break", "count", "launcher", "launchers"):
        return "launchers", None
    if game:
        return "profile", game
    size_words = _has(words, text, "largest", "biggest", "heaviest", "big", "large", "size", "most space", "top")
    place_words = _has(words, text, "folder", "folders", "drive", "disk", "storage", "space", "where", "breakdown",
                       "summary", "overview", "using", "taking")
    if size_words and "game" in text and not _has(words, text, "folder", "folders", "drive", "disk"):
        return "games", None
    if place_words:
        return "summary", None
    if size_words:
        return "games", None
    return "unknown", None


# ------------------------------------------------------------------ answers
def answer(question, facts):
    intent, game = classify(question, facts)
    if intent == "feature":
        named = find_entity(facts, question)
        return _feature(question, named.name if named else "")
    handler = {"help": _help, "safety": _safety, "unknown": _unknown}.get(intent)
    if handler:
        return handler()
    return {"history": _history, "mods": _mods, "captures": _captures, "other": _other, "idle": _idle,
            "launchers": _launchers, "profile": _profile, "games": _games, "summary": _summary}[intent](
                facts, game, question)


def _help():
    return Answer("help", HELP_TEXT)


def _unknown():
    return Answer("unknown", UNKNOWN_TEXT)


def _feature(question, game_name=""):
    """How one of Game Grave's own features works. Described from the code, not from scan data, so no source is used."""
    feature = features.find_feature(question, game_name)
    text = features.explain(feature)
    asked_safe = any(w in question.casefold() for w in ("safe", "safely", "delete", "remove"))
    note = SAFETY_TEXT if asked_safe else ""
    handoffs = ((f"Open {feature.tab}", feature.tab),) if feature.tab else ()
    return Answer("feature", text, note=note, handoffs=handoffs)


def _safety():
    return Answer("safety", SAFETY_TEXT, handoffs=(("Open Graveyard", "Graveyard"), ("Open Old Files", "Old Files"),
                                                   ("Open Other Storage", "Other Storage"),
                                                   ("Open Undo Center", "Undo Center")))


def _games(facts, game, question):
    blocked = _needs(facts, "library", "games")
    if blocked:
        return blocked
    known = sorted((g for g in facts.games if g.size_bytes is not None), key=lambda g: (-g.size_bytes, g.name.casefold()))
    unknown = len(facts.games) - len(known)
    if not known:
        return Answer("games", f"You have {len(facts.games):,} games, but your launchers haven't reported a size "
                      "for any of them.", sources=_source_names("library"), handoffs=(("Open Games", "Games"),))
    total = sum(g.size_bytes for g in known)
    rows = tuple(Row(g.name, _size(g.size_bytes), g.size_bytes / total if total else None, "Games", g.launcher)
                 for g in known[:TOP])
    extra = f" ({unknown:,} have no reported size)" if unknown else ""
    return Answer("games", f"You have {len(facts.games):,} games. Their launchers report {_size(total)} in all{extra}. "
                  "The largest are:", rows,
                  "These are launcher-reported sizes, not measured disk use. Open Games to review a game yourself.",
                  _source_names("library"), (("Open Games", "Games"), ("Open Game DNA", "Game DNA")))


def _summary(facts, game, question):
    segments = {name: size for name, size, _ in facts.segments}
    groups, used = [], []
    if facts.on("library"):
        known = [g.size_bytes for g in facts.games if g.size_bytes is not None]
        if known:
            groups.append((f"Game installs ({len(facts.games):,} games)", sum(known), "Games"))
            used.append("library")
    for key, name, label, tab in (("storage", "Other Storage", "Other Storage (caches, logs)", "Other Storage"),
                                  ("storage", "Old Files", "Old files in scanned folders", "Old Files"),
                                  ("mods", "Mods", "Mod locations", "Mods"),
                                  ("captures", "Captures", "Captures and recordings", "Captures")):
        if facts.on(key) and segments.get(name):
            groups.append((label, segments[name], tab))
            if key not in used:
                used.append(key)
    off = [data.SOURCE_NAMES[k] for k in ("library", "storage", "mods", "captures") if not facts.on(k)]
    if not groups:
        if off:
            return Answer("summary", "The data sources I would need are turned off: " + ", ".join(off) +
                          ". Turn one on in Data Used and ask again.")
        return Answer("empty", "Game Grave has no sizes on record yet. Run Scan PC, then ask again.",
                      handoffs=(("Open Ready Room", "Ready Room"),))
    groups.sort(key=lambda g: -g[1])
    top = groups[0][1] or 1
    rows = tuple(Row(label, _size(size), size / top, tab) for label, size, tab in groups)
    text = (f"From your last scan ({facts.scanned_at}), these groups hold the most reported data:"
            if facts.scanned_at else "These groups hold the most reported data:")
    note = ("Game installs can include mod and cache folders inside them, so don't add these rows into one total. "
            "I only have reported sizes grouped by type, not per-drive totals.")
    if off:
        note += " Turned off: " + ", ".join(off) + "."
    handoffs, seen = [], set()
    for row in rows:
        if row.tab not in seen and len(handoffs) < 3:
            seen.add(row.tab)
            handoffs.append((f"Open {row.tab}", row.tab))
    return Answer("summary", text, rows, note, _source_names(*used), tuple(handoffs))


def _other(facts, game, question):
    blocked = _needs(facts, "storage", "storage scan results")
    if blocked:
        return blocked
    groups = defaultdict(lambda: [0, 0])
    for item in facts.storage:
        groups[item.category][0] += 1
        groups[item.category][1] += max(0, item.size)
    if not groups:
        return Answer("other", "The last scan found no caches, logs, temporary files or settings folders.",
                      sources=_source_names("storage"), handoffs=(("Open Other Storage", "Other Storage"),))
    ordered = sorted(groups.items(), key=lambda kv: -kv[1][1])
    top = ordered[0][1][1] or 1
    rows = tuple(Row(f"{name} ({count:,})", _size(size), size / top, "Other Storage") for name, (count, size) in ordered[:TOP])
    total = sum(v[1] for v in groups.values())
    return Answer("other", f"Other Storage found {len(facts.storage):,} items reporting {_size(total)}. By type:", rows,
                  "I can't tell you what is safe to clear. Settings and saves are never removable, and caches are "
                  "reviewed one by one in Other Storage.", _source_names("storage"),
                  (("Open Other Storage", "Other Storage"),))


def _captures(facts, game, question):
    blocked = _needs(facts, "captures", "screenshots or recordings")
    if blocked:
        return blocked
    items = [c for c in facts.captures if not game or c.game == game.name]
    if not items:
        return Answer("captures", f"No captures are recorded for {game.name}." if game else "No captures were found.",
                      sources=_source_names("captures"), handoffs=(("Open Captures", "Captures"),))
    groups = defaultdict(lambda: [0, 0])
    for c in items:
        owner = "Owner not proven" if c.game == "Unverified" else c.game
        groups[owner][0] += 1
        groups[owner][1] += max(0, getattr(c.record, "size", 0) or 0)
    ordered = sorted(groups.items(), key=lambda kv: (-kv[1][1], kv[0].casefold()))
    top = ordered[0][1][1] or 1
    rows = tuple(Row(f"{name} ({count:,})", _size(size), size / top, "Captures") for name, (count, size) in ordered[:TOP])
    shots = sum(1 for c in items if c.kind == "Screenshots")
    return Answer("captures", f"I found {len(items):,} captures ({shots:,} screenshots, {len(items) - shots:,} "
                  "recordings), grouped by owner:", rows,
                  "A game is only named when the capture's own path proves it. Everything else stays 'Owner not proven'.",
                  _source_names("captures"), (("Open Captures", "Captures"),))


def _mods(facts, game, question):
    text = question.casefold()
    if any(w in text for w in ("recent use", "unused", "last used", "not used", "haven't used", "havent used")):
        return Answer("mods", "Game Grave doesn't track when a mod was last used, so I can't tell you which mods are "
                      "unused. Mods lists each mod location with the evidence for where it came from.",
                      handoffs=(("Open Mods", "Mods"),))
    blocked = _needs(facts, "mods", "mod locations")
    if blocked:
        return blocked
    mods = [m for m in facts.mods if not game or _within(m.path, game.install_path)]
    if not mods:
        return Answer("mods", "No mod locations are recorded" + (f" inside {game.name}." if game else "."),
                      sources=_source_names("mods"), handoffs=(("Open Mods", "Mods"),))
    mods = sorted(mods, key=lambda m: (-max(0, m.apparent_bytes), m.name.casefold()))
    top = max(0, mods[0].apparent_bytes) or 1
    rows = tuple(Row(m.name, _size(max(0, m.apparent_bytes)), max(0, m.apparent_bytes) / top, "Mods", m.source)
                 for m in mods[:TOP])
    total = sum(max(0, m.apparent_bytes) for m in mods)
    return Answer("mods", f"{len(mods):,} mod locations are recorded, reporting {_size(total)}. The largest:", rows,
                  "Sizes are what the scan reported. Open Mods for the source evidence behind each one.",
                  _source_names("mods"), (("Open Mods", "Mods"),))


def _history(facts, game, question):
    blocked = _needs(facts, "history", "cleanup history")
    if blocked:
        return blocked
    entries = [e for e in facts.history if not game or (e.path and _within(e.path, game.install_path))]
    if not entries:
        return Answer("history", "Nothing in the cleanup history belongs to that game.",
                      sources=_source_names("history"), handoffs=(("Open Undo Center", "Undo Center"),))
    counts = undo_insight.metrics(entries, set())
    newest = sorted(entries, key=lambda e: e.when or 0, reverse=True)[:5]
    rows = tuple(Row(f"{e.action}: {e.name}"[:60], e.status, None, "Undo Center", e.recorded) for e in newest)
    return Answer("history", f"Game Grave has logged {counts['total']:,} actions: {counts['recycled']:,} recycled, "
                  f"{counts['restored']:,} restored, {counts['failed']:,} failed. The newest are:", rows,
                  "Recycled files still take disk space until Windows empties the Recycle Bin, and a recorded recycle "
                  "isn't a promise that Windows can restore it. Undo Center checks again before any restore.",
                  _source_names("history"), (("Open Undo Center", "Undo Center"),))


def _idle(facts, game, question):
    blocked = _needs(facts, "library", "games")
    if blocked:
        return blocked
    known = [g for g in facts.games if g.last_played_at]
    stale = sorted((g for g in known if _days(g.last_played_at, facts.now) >= IDLE_DAYS),
                   key=lambda g: (-(g.size_bytes or 0), g.name.casefold()))
    note = ("Not played lately doesn't mean you're done with a game. Decide in Games. I never remove anything.")
    if not stale:
        return Answer("idle", f"Last-played dates are known for {len(known):,} of {len(facts.games):,} games, and none "
                      f"of those were last played {IDLE_DAYS}+ days ago.", note=note,
                      sources=_source_names("library"), handoffs=(("Open Games", "Games"),))
    top = max(stale[0].size_bytes or 0, 1)
    rows = tuple(Row(f"{g.name} ({_days(g.last_played_at, facts.now):,} days)", _size(g.size_bytes),
                     (g.size_bytes or 0) / top, "Games", g.last_played_source) for g in stale[:TOP])
    return Answer("idle", f"Last-played dates are known for {len(known):,} of {len(facts.games):,} games. "
                  f"{len(stale):,} weren't played in {IDLE_DAYS}+ days:", rows, note, _source_names("library"),
                  (("Open Games", "Games"),))


def _launchers(facts, game, question):
    blocked = _needs(facts, "library", "games")
    if blocked:
        return blocked
    groups = defaultdict(lambda: [0, 0])
    for g in facts.games:
        name = g.launcher if len(g.claimed_by) <= 1 else "Multiple launchers"
        groups[name][0] += 1
        groups[name][1] += g.size_bytes or 0
    ordered = sorted(groups.items(), key=lambda kv: (-kv[1][0], kv[0].casefold()))
    top = max((v[1] for _, v in ordered), default=0) or 1
    rows = tuple(Row(f"{name} ({count:,})", _size(size), size / top, "Games") for name, (count, size) in ordered)
    return Answer("launchers", f"Your {len(facts.games):,} games come from {len(ordered):,} launcher groups:", rows,
                  "A game claimed by more than one launcher is counted once, under 'Multiple launchers'.",
                  _source_names("library"), (("Open Games", "Games"),))


def _profile(facts, game, question):
    blocked = _needs(facts, "library", "games")
    if blocked:
        return blocked
    known = [g.size_bytes for g in facts.games if g.size_bytes is not None]
    rows = [Row("Launcher", game.launcher), Row("Install folder", game.install_path)]
    if game.size_bytes is not None:
        share = game.size_bytes / sum(known) if sum(known) else None
        rows.insert(1, Row("Reported size", _size(game.size_bytes), share, None,
                           f"{share * 100:.0f}% of reported library size" if share is not None else ""))
    else:
        rows.insert(1, Row("Reported size", "Unknown"))
    rows.append(Row("Last played", (f"{_days(game.last_played_at, facts.now):,} days ago" if game.last_played_at
                                    else "Unknown"), None, None, game.last_played_source))
    used = ["library"]
    if facts.on("mods"):
        rows.append(Row("Mod locations inside it", f"{sum(1 for m in facts.mods if _within(m.path, game.install_path)):,}"))
        used.append("mods")
    if facts.on("captures"):
        rows.append(Row("Captures proven to be its", f"{sum(1 for c in facts.captures if c.game == game.name):,}"))
        used.append("captures")
    if facts.on("history"):
        rows.append(Row("Cleanup history records", f"{sum(1 for e in facts.history if e.path and _within(e.path, game.install_path)):,}"))
        used.append("history")
    return Answer("profile", f"{game.name} is installed through {game.launcher}. This is what Game Grave has recorded:",
                  tuple(rows), "I only see the reported total, not a per-file breakdown. Game DNA lists the locations "
                  "that are proven to belong to this game.", _source_names(*used),
                  (("Open Game DNA", "Game DNA"), ("Open Games", "Games")))
