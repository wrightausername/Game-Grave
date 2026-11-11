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
from gg_desktop import assistant_more as more
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
HELP_TEXT = ("I answer from what Game Grave has already scanned on this PC. Try: how many games do I have, my largest "
             "games, where to look to free up space, how big is a game or when did I last play it, what drive it is on, "
             "what's in Other Storage, screenshots and recordings by game, my mods, games I haven't played lately, what "
             "Game Grave removed, or my graphics card, memory and free space on each drive. You can also ask how a "
             "feature works, for example: what is the Resurrection Kit, how do I share my mods with a friend, which mod "
             "is crashing my game, how do I stop apps starting with Windows.")
UNKNOWN_TEXT = ("I don't have an answer for that one yet. " + HELP_TEXT)


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
    if named:
        return max(named, key=lambda g: len(g.name))
    return more.nickname_match(facts.games, question)


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
        if key == "history":
            return Answer("empty", "Game Grave hasn't removed or restored anything yet, so there is nothing to explain "
                          "or undo. Every cleanup you confirm is listed in Undo Center.",
                          handoffs=(("Open Undo Center", "Undo Center"),))
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
    small = more.is_small_talk(text.split())
    if small:
        return small, None
    if "game grave" in text and _has(words, text, "safe", "trust", "delete", "deletes", "change", "changes",
                                     "touch", "harm", "virus", "dangerous"):
        return "trust", None
    if _has(words, text, "install mod", "install mods", "install a mod", "installs mods", "download mods",
            "download mod", "get mods", "add mods", "add a mod"):
        return "mod_install", None
    if _has(words, text, "slow", "stutter", "stuttering", "lag", "laggy", "lagging", "fps", "frame rate", "framerate",
            "performance", "faster", "speed up", "boost", "optimize", "optimise", "low fps", "freezing", "freezes"):
        if not _has(words, text, "boot", "startup", "start up", "starting with windows"):
            return "performance", find_entity(facts, question)
    if _has(words, text, "verify", "corrupt", "corrupted", "broken files", "missing files", "repair", "validate",
            "integrity"):
        return "verify", find_entity(facts, question)
    if _has(words, text, "backup", "back up", "backups", "archive") and not _has(words, text, "save", "saves"):
        return "backup", None
    named = find_entity(facts, question)
    game = named
    # Questions about this PC's parts and drives, answered from what Windows reported to the Hardware tab.
    if _has(words, text, "graphics card", "video card", "gpu", "cpu", "processor", "ram", "memory", "motherboard",
            "free space", "space left", "space free", "drive space", "disk space", "how full", "my drives", "my specs",
            "pc specs", "good enough", "can my pc", "can i run", "will it run", "run it", "windows version",
            "enough space", "enough room", "room for", "space for", "fit a", "will it fit", "what windows"):
        if not _has(words, text, "mod", "mods", "screenshot", "screenshots", "recording", "recordings"):
            return "hardware", game
    feature = features.find_feature(question, named.name if named else "")
    conflict_words = _has(words, text, "conflict", "conflicts", "conflicting", "overwrite each other", "clash")
    if feature and not (feature.key == "mods_library" and (_has(words, text, "how many") or conflict_words)):
        return "feature", None
    if _has(words, text, "help", "what can you", "what can i ask", "how do you work", "what do you do"):
        return "help", None
    if _has(words, text, "share my mod", "share mods", "share my mods", "mod list with", "modlist with", "same mods",
            "my friend", "with a friend", "with friends", "co op", "coop"):
        return "squad", None
    if conflict_words:
        return "conflicts", game
    if _has(words, text, "start with windows", "starting with windows", "starts with windows", "startup",
            "start up", "boot", "on startup", "at startup", "launch at login", "open when windows"):
        return "startup", None
    if _has(words, text, "save", "saves", "savegame", "save game", "save games", "save file", "save files", "savefile"):
        return "saves", game
    if _has(words, text, "move", "moving", "transfer", "relocate", "another drive", "other drive", "different drive"):
        return "move", game
    if _has(words, text, "update", "updates", "updated", "patch", "patches", "patch notes", "news") \
            and not _has(words, text, "driver", "drivers", "game grave"):
        return "game_updates", game
    if _has(words, text, "how many", "number of", "count", "total number"):
        return "count", game
    if _has(words, text, "free up", "free space up", "make room", "make space", "running out", "out of space",
            "low on space", "clear space", "almost full", "is full", "nearly full", "full drive", "drive full", "get space", "save space", "reclaim", "uninstall", "should i delete",
            "what can i delete", "what should i delete", "what should i remove", "what can i remove",
            "what to delete", "what to remove", "delete to", "remove to", "get rid of", "clean my", "clean up space"):
        return "candidates", game
    if _has(words, text, "safe", "safely", "can i delete", "ok to delete", "okay to delete", "protected", "protect"):
        return "safety", None
    if _has(words, text, "cleanup", "cleaned", "undo", "restore", "restored", "recycle", "recycled", "history",
            "clean up", "removed", "deleted", "did game grave", "what did you", "last cleanup"):
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
    size_words = _has(words, text, "largest", "biggest", "heaviest", "big", "large", "size", "most space", "top",
                      "most room", "room", "list", "all my games", "show my games", "my games")
    place_words = _has(words, text, "folder", "folders", "drive", "disk", "storage", "space", "where", "breakdown",
                       "summary", "overview", "using", "taking")
    if (size_words or "space" in words) and "game" in text and not _has(words, text, "folder", "folders", "drive", "disk"):
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
    handler = {"help": _help, "safety": _safety, "unknown": _unknown, "greet": _greet, "thanks": _thanks,
               "squad": _squad, "startup": _startup, "trust": _trust, "mod_install": _mod_install,
               "backup": _backup}.get(intent)
    if handler:
        return handler()
    if intent == "hardware":
        return _hardware(facts, game, question)
    extra = {"conflicts": _conflicts, "saves": _saves, "move": _move, "game_updates": _game_updates,
             "count": _count, "candidates": _candidates, "performance": _performance,
             "verify": _verify}.get(intent)
    if extra:
        return extra(facts, game, question)
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


GLOSSARY = (
    (("shader cache", "shadercache", "shaders", "shader"), "A shader cache holds graphics code your driver or game "
     "compiled for your card so it doesn't have to compile it again. If it is cleared it is rebuilt, which can mean "
     "stutter or a longer first load for a while."),
    (("crash dump", "crash dumps", "dump", "dumps"), "Crash dumps are snapshots Windows or a game writes when something "
     "crashes. They only matter if you are sending a crash to a developer."),
    (("log", "logs", "log file", "log files"), "Logs are text records a game or launcher writes as it runs. They help "
     "when something goes wrong and otherwise just pile up."),
    (("temp", "temporary", "temp files"), "Temporary files are working files a program meant to clean up after itself. "
     "One in use can still be needed until the program closes."),
    (("cache", "caches"), "A cache is a copy of something kept to save time later, such as downloaded artwork or web "
     "pages in a launcher. It is rebuilt when needed."),
)


def _explain_term(question):
    text = " " + " ".join(_words(question)) + " "
    if not any(w in text for w in (" what is ", " what are ", " whats ", " what's ", " explain ", " mean ")):
        return ""
    for terms, meaning in GLOSSARY:
        if any(f" {t} " in text for t in terms):
            return meaning + "\n\n"
    return ""


def _other(facts, game, question):
    meaning = _explain_term(question)
    if meaning and not facts.on("storage"):
        return Answer("other", meaning.strip(), handoffs=(("Open Other Storage", "Other Storage"),))
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
    return Answer("other", meaning + f"Other Storage found {len(facts.storage):,} items reporting {_size(total)}. By type:", rows,
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
    total = sum(max(0, getattr(c.record, "size", 0) or 0) for c in items)
    return Answer("captures", f"Your captures report {_size(total)}: {shots:,} screenshot{'s' if shots != 1 else ''} and "
                  f"{len(items) - shots:,} recording{'s' if len(items) - shots != 1 else ''}. By game:", rows,
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
                  f"{len(stale):,} {'wasn' if len(stale) == 1 else 'weren'}'t played in {IDLE_DAYS}+ days:", rows, note, _source_names("library"),
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


def _profile_lead(facts, game, question):
    """One direct sentence that answers what was asked about the game, before the full record."""
    text = question.casefold()
    words = set(_words(question))
    if _has(words, text, "last play", "last played", "when did i", "played", "play time", "playtime"):
        if game.last_played_at:
            days = _days(game.last_played_at, facts.now)
            when = "today" if days == 0 else "yesterday" if days == 1 else f"{days:,} days ago"
            return f"You last played {game.name} {when} ({game.last_played_source or 'launcher record'})."
        return f"Game Grave has no last-played date for {game.name}; {game.launcher} didn't record one."
    if _has(words, text, "where", "drive", "folder", "installed", "location", "path"):
        drive = more.drive_of(game.install_path)
        return f"{game.name} is installed in {game.install_path}" + (f", on drive {drive}:." if drive else ".")
    if _has(words, text, "big", "size", "large", "space", "gb", "much"):
        if game.size_bytes is None:
            return f"{game.launcher} hasn't reported a size for {game.name}."
        known = sum(g.size_bytes for g in facts.games if g.size_bytes is not None)
        share = f", {game.size_bytes / known * 100:.0f}% of your reported library" if known else ""
        return f"{game.name} reports {_size(game.size_bytes)}{share}."
    return f"{game.name} is installed through {game.launcher}."


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
    return Answer("profile", _profile_lead(facts, game, question) + " This is what Game Grave has recorded:",
                  tuple(rows), "I only see the reported total, not a per-file breakdown. Game DNA lists the locations "
                  "that are proven to belong to this game.", _source_names(*used),
                  (("Open Game DNA", "Game DNA"), ("Open Games", "Games")))


# ------------------------------------------------------------------ everyday questions
def _greet():
    return Answer("greet", "Hi. Ask me anything about your games, storage, mods or this PC. For example: how many games "
                  "do I have, what's taking the most space, when did I last play a game, what's my graphics card, or "
                  "how do I share my mods with a friend.")


def _thanks():
    return Answer("thanks", "Any time. Ask me something else whenever you like.")


def _feature_key(key, note=""):
    feature = features.BY_KEY[key]
    return Answer("feature", features.explain(feature), note=note,
                  handoffs=((f"Open {feature.tab}", feature.tab),) if feature.tab else ())


def _squad():
    return _feature_key("squad_sync")


def _startup():
    return _feature_key("drivers_startup")


def _conflicts(facts, game, question):
    where = f" for {game.name}" if game else ""
    return Answer("conflicts", f"Game Grave checks mod conflicts{where} in Mods > Conflicts. Press Check there and it "
                  "compares the files of the mods switched on in each saved Mod Organizer 2 or Vortex profile, then "
                  "lists every pair or group that ships the same file. I can't see that check's results from here.",
                  note="Two mods sharing a file is often intended (one is meant to override the other), so a conflict "
                       "is a list to read, not a verdict on which mod to keep. If a game crashes, Mod Bisect finds the "
                       "mod by testing.",
                  handoffs=(("Open Mods", "Mods"),))


def _saves(facts, game, question):
    if not facts.on("storage"):
        return Answer("off", "Storage scans is turned off, so I can't use the save folders it found. Turn it on in "
                      "Data Used, then ask again.")
    saves = list(facts.saves)
    if game:
        name = game.name.casefold()
        mine = [s for s in saves if s.game and (s.game.casefold() == name or s.game.casefold() in name
                                                 or name in s.game.casefold())]
        if not mine:
            return Answer("saves", f"The save scan didn't label a save folder for {game.name}. Game Grave only names a "
                          "save folder when the folder itself proves which game it belongs to, so it doesn't guess. "
                          "If you know where it is, link it to the game in Game DNA and Save Vault can back it up.",
                          sources=_source_names("storage"),
                          handoffs=(("Open Game DNA", "Game DNA"), ("Open More Tools", "More Tools")))
        rows = tuple(Row(s.path, s.kind, None, "Game DNA", s.reason) for s in mine[:TOP])
        return Answer("saves", f"{game.name}'s saves are here:", rows,
                      "Saves are never removable in Game Grave. Save Vault (More Tools) copies a save folder into a "
                      "verified ZIP.", _source_names("storage"),
                      (("Open Game DNA", "Game DNA"), ("Open More Tools", "More Tools")))
    if not saves:
        return Answer("saves", "The last scan didn't find any save folders it could tie to a game. Run Scan PC, or "
                      "link a save folder to its game in Game DNA.", sources=_source_names("storage"),
                      handoffs=(("Open Game DNA", "Game DNA"),))
    counts = defaultdict(int)
    for s in saves:
        counts[s.game or "Game not named"] += 1
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].casefold()))
    rows = tuple(Row(name, f"{count:,} folder{'s' if count != 1 else ''}", None, "Game DNA") for name, count in ordered[:TOP])
    return Answer("saves", f"The save scan found {len(saves):,} save folders for {len(counts):,} games. Ask about one game "
                  "by name to see its folders. The most found:", rows,
                  "Saves are never removable in Game Grave. Save Vault (More Tools) backs a save folder up into a "
                  "verified ZIP.", _source_names("storage"),
                  (("Open Game DNA", "Game DNA"), ("Open More Tools", "More Tools")))


def _drive_rows(specs, need=None, skip=""):
    rows = []
    for d in sorted(specs.drives, key=lambda d: d.letter):
        if skip and d.letter.upper() == skip:
            continue
        used = 1 - d.free / d.total if d.total else None
        fits = ""
        if need is not None:
            fits = "room for it" if d.free > need * 1.1 else "not enough room"
        kind = d.kind if d.kind != "unknown" else "drive"
        rows.append(Row(f"{d.letter}: {d.model or kind}", f"{_size(d.free)} free of {_size(d.total)}", used, "Hardware",
                        ", ".join(x for x in (kind, fits) if x)))
    return tuple(rows)


def _move(facts, game, question):
    text = ("Game Grave doesn't move game installs; the launcher does it so it keeps track of the new place. In Steam: "
            "Settings > Storage, pick the game, then Move. In the EA app, Ubisoft Connect, Battle.net and the Xbox app "
            "use the game's own Move or Change location option. For other launchers, move the folder only if the "
            "launcher offers to locate an existing install afterwards.")
    rows, note, used = (), "", []
    specs = facts.hardware
    if game:
        drive = more.drive_of(game.install_path)
        text = (f"{game.name} is installed in {game.install_path}" + (f" (drive {drive}:)" if drive else "") +
                (f" and reports {_size(game.size_bytes)}." if game.size_bytes is not None else ".") + "\n\n" + text)
        used.append("library")
        if specs and specs.drives:
            rows = _drive_rows(specs, game.size_bytes, drive)
            note = "Free space is what Windows reported to the Hardware tab. Leave some room spare after the move."
    elif specs and specs.drives:
        rows = _drive_rows(specs)
        note = "Free space is what Windows reported to the Hardware tab."
    sources = _source_names(*used) + (("Hardware (Windows)",) if rows else ())
    return Answer("move", text, rows, note, sources, (("Open Games", "Games"), ("Open Hardware", "Hardware")))


def _game_updates(facts, game, question):
    who = f" for {game.name}" if game else " for your games"
    return Answer("game_updates", f"Ready Room's Patch Watch shows the official Steam news and patch notes{who}. It "
                  "refreshes when you open Ready Room and every 30 minutes while it is open. Installing a game update "
                  "is done by the launcher (Steam, Epic and the rest update games themselves); Game Grave doesn't "
                  "download game updates. Mod updates your mod manager recorded show in Mods under Needs attention.",
                  note="Checking for a newer Game Grave is a different thing: Settings > Check for Updates.",
                  handoffs=(("Open Ready Room", "Ready Room"), ("Open Mods", "Mods")))


def _count(facts, game, question):
    text = question.casefold()
    words = set(_words(question))
    asks = [k for k, needles in (("mods", ("mod", "mods")), ("captures", ("screenshot", "screenshots", "recording",
            "recordings", "capture", "captures", "clips", "videos")), ("saves", ("save", "saves")),
            ("history", ("cleanup", "cleanups", "deleted", "removed", "recycled"))) if any(n in words for n in needles)]
    if not asks or "game" in text:
        asks = ["games"] + asks
    parts, rows, used = [], [], []
    for kind in asks:
        if kind == "games":
            blocked = _needs(facts, "library", "games")
            if blocked:
                return blocked
            installed = sum(1 for g in facts.games if str(g.status).casefold().startswith("install"))
            launchers = defaultdict(int)
            for g in facts.games:
                launchers[g.launcher if len(g.claimed_by) <= 1 else "Multiple launchers"] += 1
            parts.append(f"You have {len(facts.games):,} games" +
                         (f" ({installed:,} installed)" if installed and installed != len(facts.games) else "") +
                         f" across {len(launchers):,} launcher{'s' if len(launchers) != 1 else ''}.")
            top = max(launchers.values()) or 1
            rows += [Row(name, f"{count:,}", count / top, "Games")
                     for name, count in sorted(launchers.items(), key=lambda kv: (-kv[1], kv[0].casefold()))]
            used.append("library")
        elif kind == "mods":
            blocked = _needs(facts, "mods", "mod locations")
            if blocked:
                return blocked
            parts.append(f"{len(facts.mods):,} mod locations are recorded. A location can be one mod or a whole mod "
                         "folder, so count the mods themselves in Mods.")
            used.append("mods")
        elif kind == "captures":
            blocked = _needs(facts, "captures", "screenshots or recordings")
            if blocked:
                return blocked
            shots = sum(1 for c in facts.captures if c.kind == "Screenshots")
            parts.append(f"You have {shots:,} screenshot{'s' if shots != 1 else ''} and {len(facts.captures) - shots:,} "
                         f"recording{'s' if len(facts.captures) - shots != 1 else ''} on record.")
            used.append("captures")
        elif kind == "saves":
            if facts.on("storage"):
                parts.append(f"The save scan found {len(facts.saves):,} save folders.")
                used.append("storage")
        elif kind == "history":
            blocked = _needs(facts, "history", "cleanup history")
            if blocked:
                return blocked
            parts.append(f"Game Grave has logged {len(facts.history):,} actions in its cleanup history.")
            used.append("history")
    if not parts:
        return _unknown()
    tab = {"games": "Games", "mods": "Mods", "captures": "Captures", "saves": "Game DNA", "history": "Undo Center"}[asks[0]]
    return Answer("count", " ".join(parts), tuple(rows[:TOP + 2]), "", _source_names(*dict.fromkeys(used)),
                  ((f"Open {tab}", tab),))


def _candidates(facts, game, question):
    """Where the most reported space sits, biggest first, so the owner knows where to look. Never a verdict."""
    if game:
        played = (f"last played {_days(game.last_played_at, facts.now):,} days ago" if game.last_played_at
                  else "no last-played date on record")
        size = f"reports {_size(game.size_bytes)}" if game.size_bytes is not None else "has no reported size"
        return Answer("candidates", f"{game.name} {size} and has {played} ({game.last_played_source or 'no source'}). "
                      "Whether to uninstall it is your call: Game Grave can't know if you'll play it again. If you "
                      "might, a Resurrection Kit keeps the whole install and saves in one ZIP so you can put it back "
                      "without downloading.", note=SAFETY_TEXT, sources=_source_names("library"),
                      handoffs=(("Open Games", "Games"), ("Open More Tools", "More Tools")))
    rows, used = [], []
    if facts.on("library") and facts.games:
        idle = sorted((g for g in facts.games if g.last_played_at and g.size_bytes
                       and _days(g.last_played_at, facts.now) >= IDLE_DAYS), key=lambda g: -g.size_bytes)
        for g in idle[:4]:
            rows.append((g.size_bytes, Row(f"{g.name} (not played in {_days(g.last_played_at, facts.now):,} days)",
                                           _size(g.size_bytes), None, "Games", "Uninstall through its launcher")))
        if idle:
            used.append("library")
        undated = sorted((g for g in facts.games if not g.last_played_at and g.size_bytes), key=lambda g: -g.size_bytes)
        for g in undated[:2]:
            rows.append((g.size_bytes, Row(f"{g.name} (no last-played date)", _size(g.size_bytes), None, "Games",
                                           "Check when you last played it")))
            used.append("library")
    segments = {name: size for name, size, _ in facts.segments}
    for key, name, label, hint in (("storage", "Other Storage", "Caches, logs and temp files", "Review one by one"),
                                   ("storage", "Old Files", "Old files in your scanned folders", "Review and recycle"),
                                   ("captures", "Captures", "Screenshots and recordings", "Preview, then recycle")):
        if facts.on(key) and segments.get(name):
            rows.append((segments[name], Row(label, _size(segments[name]), None, name, hint)))
            used.append(key)
    if not rows:
        if not facts.scanned_at:
            return Answer("empty", "Game Grave has nothing on record yet. Run Scan PC, then ask again.",
                          handoffs=(("Open Ready Room", "Ready Room"),))
        return Answer("candidates", "Nothing big stands out in your last scan: no large games you haven't played in "
                      f"{IDLE_DAYS} days, and no sizeable caches, old files or captures.", note=SAFETY_TEXT,
                      sources=_source_names(*dict.fromkeys(used)))
    rows.sort(key=lambda r: -r[0])
    top = rows[0][0] or 1
    shown = tuple(Row(r.label, r.value, size / top, r.tab, r.detail) for size, r in rows[:TOP + 2])
    handoffs, seen = [], set()
    for r in shown:
        if r.tab not in seen and len(handoffs) < 3:
            seen.add(r.tab)
            handoffs.append((f"Open {r.tab}", r.tab))
    return Answer("candidates", "These are where the most space sits that you might not need, biggest first. Each one "
                  "opens in the tab that can act on it, after you review it:", shown,
                  "Sizes are reported, not measured, and nothing is removed from here. Games go through their launcher; "
                  "files go to the Recycle Bin only after you confirm. Not played lately doesn't mean you're done with "
                  "a game.", _source_names(*dict.fromkeys(used)), tuple(handoffs))


def _hardware(facts, game, question):
    specs = facts.hardware
    if specs is None:
        return Answer("hardware_unread", "Windows hasn't reported your parts to Game Grave yet. Open Hardware (or ask "
                      "again in a moment) and I'll answer from what it reads.", handoffs=(("Open Hardware", "Hardware"),))
    text = question.casefold()
    words = set(_words(question))
    rows, lead = [], []
    want_gpu = _has(words, text, "graphics", "gpu", "video card", "graphics card")
    want_cpu = _has(words, text, "cpu", "processor")
    want_ram = _has(words, text, "ram", "memory")
    want_disk = _has(words, text, "free space", "space left", "space free", "drive space", "disk space", "how full",
                     "my drives", "drive", "drives", "disk", "storage")
    want_os = _has(words, text, "windows version", "windows")
    can_run = _has(words, text, "good enough", "can my pc", "can i run", "will it run", "run it")
    everything = can_run or not (want_gpu or want_cpu or want_ram or want_disk or want_os)
    if (want_gpu or everything) and specs.gpus:
        for g in specs.gpus:
            rows.append(Row("Graphics", g.name, None, "Hardware", f"driver {g.driver}" if g.driver else ""))
        if want_gpu:
            lead.append("Your graphics card" + (" is " if len(specs.gpus) == 1 else "s are ") +
                        " and ".join(g.name for g in specs.gpus) + ".")
    if (want_cpu or everything) and specs.cpu:
        c = specs.cpu
        rows.append(Row("Processor", c.name, None, "Hardware", f"{c.cores} cores, {c.threads} threads"))
        if want_cpu:
            lead.append(f"Your processor is {c.name} ({c.cores} cores, {c.threads} threads).")
    if (want_ram or everything) and specs.memory:
        m = specs.memory
        amount = f"{m.total_gb:,.0f} GB" + (f" {m.kind}" if m.kind else "")
        rows.append(Row("Memory", amount, None, "Hardware",
                        f"running at {m.running_mts} MT/s" if m.running_mts else ""))
        if want_ram:
            lead.append(f"You have {amount} of memory" + (f" running at {m.running_mts} MT/s." if m.running_mts else "."))
    if (want_os or everything) and specs.os_name:
        rows.append(Row("Windows", specs.os_name, None, "Hardware", specs.os_version))
        if want_os and not want_disk:
            lead.append(f"You're on {specs.os_name}" + (f" ({specs.os_version})." if specs.os_version else "."))
    need = None
    sized = re.search(r"(\d+(?:\.\d+)?)\s*(gb|gig|gigs|tb)\b", text)
    if sized:
        need = float(sized.group(1)) * (1024 ** 4 if sized.group(2) == "tb" else 1024 ** 3)
        want_disk, everything = True, False
    if (want_disk or everything) and specs.drives:
        drive_rows = _drive_rows(specs, need)
        if need is not None:
            fits = [d.letter + ":" for d in specs.drives if d.free > need * 1.1]
            lead.append((f"Yes: {', '.join(fits)} {'has' if len(fits) == 1 else 'have'} room for {_size(int(need))} with "
                         "some to spare." if fits else f"No drive has {_size(int(need))} free with room to spare right "
                         "now. Asking where to free up space shows the biggest places to look."))
            want_disk = False
        rows += list(drive_rows)
        if want_disk:
            free = sum(d.free for d in specs.drives)
            lead.append(f"You have {_size(free)} free across {len(specs.drives):,} drive"
                        f"{'s' if len(specs.drives) != 1 else ''}:")
    note = "Read from Windows by the Hardware tab. Nothing was changed."
    if can_run:
        name = game.name if game else "a game"
        lead.insert(0, f"I can't tell you whether this PC runs {name} well: Game Grave doesn't have games' system "
                    "requirements. Compare these parts with the System requirements on the game's store page. After "
                    "you record a few play sessions, Hardware's Upgrade Advisor says what held the game back.")
    if not lead:
        lead.append("This is what Windows reported about your PC:")
    return Answer("hardware", " ".join(lead), tuple(rows[:12]), note, ("Hardware (Windows)",),
                  (("Open Hardware", "Hardware"),))


def _trust():
    return Answer("trust", "Here is exactly what Game Grave can change on your PC, and nothing else:\n"
                  "• Files you pick in Old Files, Other Storage, Captures or Graveyard go to the Recycle Bin, never "
                  "straight to deletion, after you confirm and a fresh re-check. Undo Center lists every one.\n"
                  "• Kits, Save Vault backups and Black Box reports are new files it writes where you choose.\n"
                  "• Soulbind changes one setting in a game's settings file, after saving a dated backup.\n"
                  "• Drivers & Startup installs driver updates Windows Update offers, and switches startup apps the "
                  "same way Task Manager does. Both ask first; the driver install goes through the Windows prompt.\n"
                  "• Squad Sync and Mod Bisect only add new mod folders or new Mod Organizer 2 profiles, never "
                  "overwrite one.\n"
                  "Saves and settings folders are never removable, and every change is written to the activity log.",
                  note="I can't promise that a particular file isn't needed; that's why everything goes through your review.",
                  handoffs=(("Open Undo Center", "Undo Center"), ("Open Settings", "Settings")))


def _mod_install():
    return Answer("mod_install", "Your mod manager (Mod Organizer 2, Vortex) installs mods; Game Grave doesn't, with "
                  "one exception. Squad Sync can take a friend's squad code, download the Nexus files you're missing "
                  "(Nexus Premium) and add the plain zip ones to Mod Organizer 2 as new, switched-off mods. FOMOD "
                  "installers, 7z and rar archives wait in Mod Organizer 2's Downloads tab for you to install there.",
                  note="Game Grave never overwrites a mod or edits your profile's load order.",
                  handoffs=(("Open Ready Room", "Ready Room"), ("Open Mods", "Mods")))


def _backup():
    return _feature_key("resurrection_kit", note="For just one folder, such as a save or a settings folder, Save Vault "
                        "in More Tools makes a verified ZIP of that folder alone.")


def _performance(facts, game, question):
    who = game.name if game else "a game"
    return Answer("performance", f"Game Grave can't make {who} faster by itself, but it can show you what's slowing it:\n"
                  "• Autopsy (Ready Room) reads frame-time captures from PresentMon or CapFrameX and shows stutters and "
                  "your 1% lows.\n"
                  "• Hardware's live monitor shows whether the processor, graphics card or memory is maxed out while "
                  "you play, and Upgrade Advisor turns recorded sessions into notes on what held you back.\n"
                  "• Drivers & Startup (Hardware) checks Windows Update for driver updates and lets you switch off apps "
                  "that start with Windows and run in the background.\n"
                  "• If it started after a driver update, Exhume (Ready Room) helps roll the graphics driver back.\n"
                  "• If it started after adding mods, Mod Bisect finds which mod does it.",
                  note="Nothing here changes a setting by itself; each tool asks first.",
                  handoffs=(("Open Hardware", "Hardware"), ("Open Ready Room", "Ready Room")))


def _verify(facts, game, question):
    who = game.name if game else "the game"
    launcher = game.launcher if game else "its launcher"
    return Answer("verify", f"The launcher is the one that knows which files {who} should have, so ask {launcher} to "
                  "check them: in Games, select the game and press Verify (for Steam it starts Steam's own verify; for "
                  "other launchers it opens the launcher). Steam: Properties > Installed Files > Verify integrity. Other launchers have a Repair or "
                  "Verify option on the game.",
                  note="To check one file you downloaded against a published checksum, use Hash Checker in More Tools.",
                  handoffs=(("Open Games", "Games"), ("Open More Tools", "More Tools")))
