"""Makes the built-in assistant understand loose questions. Pure: no Qt, no files, no network.

The keyword answers in `assistant_engine` stay the single source of every number. This layer only changes the question
they see and what happens when they miss:

* Slang and typos are turned into the words the answers know ("pics" -> screenshots, "skyrm" -> Skyrim, "storge" ->
  storage). Game names are matched loosely too ("cyber punk", "eldin ring").
* Follow-ups use the chat: "what about Starfield?", "and the second one?", "why?" refer back to the last answer.
* Two questions in one message get two answers.
* A miss is never a dead end: it says it isn't sure and offers its best guesses as buttons that ask them.
"""
from __future__ import annotations

import difflib
import re

from gg_desktop import assistant_engine as engine
from gg_desktop import assistant_features as features

# Everyday words and slang -> the words the built-in answers listen for. Whole words or phrases only.
SLANG = (
    (r"wat|wut|whut|wht", "what"),
    (r"r", "are"),
    (r"u", "you"),
    (r"ur|yur", "your"),
    (r"pls|plz", "please"),
    (r"hw", "how"),
    (r"im", "i'm"),
    (r"screenies|screencaps?|pics|pictures|photos|snaps", "screenshots"),
    (r"vids|clips|replays|highlights|shadowplay|gameplay videos?", "recordings"),
    (r"hogg?(?:ing|s)?|eating(?: up)?|chewing(?: up)?|taking up|using up|sucking up", "taking space"),
    (r"lagging|laggy|choppy|stuttery|frame drops?|low frames?|bad frames?", "lag"),
    (r"ctds?|crash(?:es|ing|ed)?|keeps? closing|closes itself|won'?t (?:start|launch|open|load)|black screens?",
     "crashing"),
    (r"(?:hdd|ssd|nvme|hard ?drive|hard ?disk|c drive|d drive|e drive|disk drive)s?", "drive"),
    (r"gigs?|gigabytes?", "gb"),
    (r"rig|computer|machine|setup|build", "pc"),
    (r"vram|graphics memory", "gpu memory"),
    (r"gfx card|graphics|video ?card", "graphics card"),
    (r"junk|crap|clutter|bloat|trash files|garbage", "old files"),
    (r"biggest|largest|fattest|heaviest|chunkiest|hugest", "largest"),
    (r"wipe|nuke|yeet|purge|trash|bin|get rid of|toss|dump", "delete"),
    (r"savegames?|save data|progress files?|my progress", "saves"),
    (r"modlist|mod list|load ?order", "mods load order"),
)
_SLANG = [(re.compile(r"\b(?:" + pattern + r")\b"), word) for pattern, word in SLANG]

# Words worth correcting a typo towards: every keyword the answers know, plus the feature names.
COMMON = {"what", "where", "when", "which", "with", "would", "could", "should", "there", "their", "these", "those",
          "about", "have", "this", "that", "your", "mine", "much", "many", "some", "more", "most", "less", "than",
          "then", "them", "they", "from", "into", "onto", "just", "like", "also", "make", "made", "does", "doing",
          "done", "want", "need", "know", "tell", "show", "give", "help", "please", "thanks", "still", "very", "only",
          "really", "maybe", "every", "each", "other", "else", "again", "after", "before", "first", "second", "third",
          "last", "next", "good", "best", "worst", "better", "worse", "think", "going", "being", "were", "will",
          "game", "games", "play", "played", "playing", "thing", "things", "stuff", "here", "time", "long", "since"}


def _vocabulary():
    words = set(COMMON)
    # The keyword phrases live as constants in the engine's compiled code, which the installed app always has (its
    # .py source is not shipped), so read them from there.
    def constants(code):
        for value in code.co_consts:
            if isinstance(value, str):
                yield value
            elif isinstance(value, tuple):
                yield from (v for v in value if isinstance(v, str))
            elif hasattr(value, "co_consts"):
                yield from constants(value)
    for name in dir(engine):
        code = getattr(getattr(engine, name), "__code__", None)
        if code is None:
            continue
        for phrase in constants(code):
            if 2 < len(phrase) <= 40 and re.fullmatch(r"[a-z][a-z0-9 .']*", phrase):
                words.update(w for w in phrase.split() if len(w) >= 3)
    for feature in features.FEATURES:
        words.update(w for w in re.findall(r"[a-z0-9]+", feature.title.casefold()) if len(w) >= 3)
        for phrase in getattr(feature, "keywords", ()) or ():
            words.update(w for w in re.findall(r"[a-z0-9]+", str(phrase).casefold()) if len(w) >= 3)
    for _pattern, word in SLANG:
        words.update(word.split())
    return frozenset(words)


VOCAB = _vocabulary()
_VOCAB_LIST = sorted(VOCAB)


def _clean(text):
    return " ".join(str(text or "").replace("’", "'").casefold().split())


# ------------------------------------------------------------------ game names
def _plain(text):
    return re.sub(r"[^a-z0-9 ]+", " ", text.casefold())


def fuzzy_game(facts, text):
    """The game a loosely typed name points at ("cyber punk", "skyrm", "eldin ring"), with the words it matched, or
    (None, ""). Exact names are already handled by the engine; this only catches near misses."""
    words = _plain(text).split()
    best, best_score, best_span = None, 0.0, ""
    for g in getattr(facts, "games", ()):
        name = _plain(g.name)
        name_words = [w for w in name.split() if w not in {"the", "of", "and"}]
        if len(name.replace(" ", "")) < 4:
            continue
        joined = name.replace(" ", "")
        spans = set()
        for size in {len(name_words), len(name_words) + 1, 1, 2}:
            for i in range(0, max(0, len(words) - size + 1)):
                spans.add(" ".join(words[i:i + size]))
        for span in spans:
            squashed = span.replace(" ", "")
            if len(squashed) < 4:
                continue
            score = difflib.SequenceMatcher(None, squashed, joined).ratio()
            # A distinctive first word on its own ("skyrm" for "the elder scrolls v skyrim" is too far; "skyrm" for
            # "skyrim special edition" uses the word "skyrim").
            for w in name_words:
                if len(w) >= 5 and w not in ("edition", "special", "remastered", "definitive"):
                    score = max(score, difflib.SequenceMatcher(None, squashed, w).ratio() - 0.02)
            if score > best_score:
                best, best_score, best_span = g, score, span
    if best is not None and best_score >= 0.84:
        return best, best_span
    return None, ""


# ------------------------------------------------------------------ normalising the question
def normalize(question, facts=None):
    """The question in words the built-in answers know. Game names are put back exactly as the library spells them."""
    text = _clean(question)
    if facts is not None and getattr(facts, "games", None) and engine.find_entity(facts, text) is None:
        game, span = fuzzy_game(facts, text)
        if game is not None and span:
            text = re.sub(r"\b" + r"\s*".join(map(re.escape, span.split())) + r"\b", game.name.casefold(),
                          _plain(text).strip(), count=1)
    for pattern, word in _SLANG:
        text = pattern.sub(word, text)
    names = set()
    for g in getattr(facts, "games", ()) if facts is not None else ():
        names.update(_plain(g.name).split())
    fixed = []
    for word in text.split():
        bare = word.strip(".,!?'\"")
        if len(bare) >= 4 and bare.isalpha() and bare not in VOCAB and bare not in names:
            close = difflib.get_close_matches(bare, _VOCAB_LIST, n=1, cutoff=0.84)
            if close:
                word = word.replace(bare, close[0])
        fixed.append(word)
    return " ".join(fixed)


# ------------------------------------------------------------------ follow-ups
_WHAT_ABOUT = re.compile(r"^(?:what|how) about\s+(.+)|^(?:and|also|same for|same with|now|ok and|okay and|what of)\s+(.+)")
_WHY = re.compile(r"^(?:why|how come|how do you know|where(?:'s| is| does) that (?:from|come from)|says who|source\??)\W*$")
_MORE = re.compile(r"^(?:tell me more|more|more info|more details|go on|explain|explain that|details|elaborate)\W*$")
_ORDINALS = {"first": 1, "1st": 1, "top": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4,
             "fifth": 5, "5th": 5, "last": -1}
_ORDINAL = re.compile(r"\b(first|1st|top|second|2nd|third|3rd|fourth|4th|fifth|5th|last)\b(?: one| game| item)?|#\s*(\d)")


def _strip_games(text, facts):
    out = text
    for g in sorted(getattr(facts, "games", ()), key=lambda g: -len(g.name)):
        out = re.sub(re.escape(g.name.casefold()), " ", out)
    return " ".join(out.split())


def follow_up(text, facts, previous_question="", previous_answer=None):
    """A rewritten question, or an Answer, when the message only makes sense next to the last one; else None."""
    if not previous_question:
        return None
    short = len(text.split()) <= 8
    rows = list((previous_answer or {}).get("rows") or [])
    if short and _WHY.match(text):
        prev = previous_answer or {}
        sources = ", ".join(prev.get("sources") or []) or "Game Grave's last scan"
        note = prev.get("note") or ""
        return engine.Answer("why", f"That answer comes from {sources}. Game Grave reads what launchers and its scans "
                             "recorded; it doesn't guess. " + note, (), "",
                             tuple(prev.get("sources") or ()), tuple(tuple(h) for h in prev.get("handoffs") or ()))
    if short and _MORE.match(text):
        return previous_question + " details"
    found = _ORDINAL.search(text)
    if short and found and rows:
        n = int(found.group(2)) if found.group(2) else _ORDINALS[found.group(1)]
        index = len(rows) - 1 if n == -1 else n - 1
        if 0 <= index < len(rows):
            label = str(rows[index][0])
            rest = _ORDINAL.sub(" ", text)
            rest = re.sub(r"^(?:and|what about|how about|tell me about|the|one)\b", " ", rest).strip(" ?.!")
            return (rest + " " + label).strip() if rest and rest not in ("one", "the one") else "tell me about " + label
    match = _WHAT_ABOUT.match(text)
    if short and match:
        subject = (match.group(1) or match.group(2) or "").strip(" ?.!")
        named = engine.find_entity(facts, subject) or fuzzy_game(facts, subject)[0]
        if named is not None:
            base = _strip_games(previous_question, facts)
            return (base + " " + named.name.casefold()).strip() if base else "tell me about " + named.name.casefold()
        return None
    # A bare game name right after another question: ask the same thing about that game.
    if short and len(text.split()) <= 4:
        named = engine.find_entity(facts, text)
        name_words = set(_plain(named.name).split()) if named is not None else set()
        leftover = [w for w in _plain(text).split() if w not in name_words and w not in ("and", "now", "then", "so")]
        if named is not None and not leftover:
            base = _strip_games(previous_question, facts)
            if base and base != previous_question:
                return base + " " + named.name.casefold()
    return None


# ------------------------------------------------------------------ two questions in one
_SPLIT = re.compile(r"\?\s+(?=\w)|\s+(?:and also|also|plus|and then)\s+|"
                    r"\s+and\s+(?=(?:what|when|where|how|which|who|why|is|are|do|does|did|can|could|should|will)\b)")


def split_two(text):
    """At most two separate questions; ("whole question",) when it is really one."""
    parts = [p.strip(" ?.!") for p in _SPLIT.split(text, maxsplit=1) if p and p.strip(" ?.!")]
    if len(parts) == 2 and all(len(p.split()) >= 2 for p in parts):
        return tuple(parts)
    return (text,)


def _combine(first, second):
    handoffs = list(first.handoffs)
    for h in second.handoffs:
        if h not in handoffs:
            handoffs.append(h)
    sources = tuple(dict.fromkeys(tuple(first.sources) + tuple(second.sources)))
    note = " ".join(n for n in (first.note, second.note) if n)
    if first.intent == second.intent:
        # Two of the same kind (two games): the lead sentences answer both; two copies of the same rows would only confuse.
        lead = lambda a: a.text.replace(" This is what Game Grave has recorded:", "").strip()
        return engine.Answer(first.intent, lead(first) + "\n\n" + lead(second), (), note, sources, tuple(handoffs[:5]))
    return engine.Answer(first.intent, first.text + "\n\n" + second.text, tuple(first.rows) + tuple(second.rows), note,
                         sources, tuple(handoffs[:5]))


# ------------------------------------------------------------------ best guesses instead of "I don't know"
TOPICS = (
    ("Largest games", "What are my largest games?", {"largest", "big", "size", "space", "games", "gb", "taking"}),
    ("What's using space", "What's taking up space on my drives?", {"space", "drive", "storage", "full", "taking",
                                                                    "room", "using"}),
    ("Free up space", "What can I review to free up space?", {"free", "delete", "clean", "remove", "space", "room",
                                                              "old", "files", "full"}),
    ("Games I don't play", "Which games haven't I played lately?", {"played", "play", "unused", "old", "forgot",
                                                                     "haven't", "never"}),
    ("A game keeps crashing", "How do I find the mod that's crashing my game?", {"crashing", "crash", "mod", "mods",
                                                                                  "broken", "fix", "error"}),
    ("Game runs badly", "Why is my game running slow?", {"lag", "slow", "fps", "performance", "stutter", "run",
                                                         "faster"}),
    ("My mods", "Show my mods", {"mods", "mod", "load", "order", "nexus", "vortex", "organizer"}),
    ("My saves", "Where are my saves?", {"saves", "save", "progress", "backup", "back"}),
    ("Screenshots and clips", "How much space do my screenshots and recordings use?", {"screenshots", "recordings",
                                                                                         "captures", "videos"}),
    ("My PC's parts", "What are my PC specs?", {"pc", "specs", "graphics", "card", "cpu", "ram", "memory", "gpu",
                                                "run"}),
    ("What Game Grave did", "Explain my last cleanup", {"undo", "restore", "deleted", "cleanup", "did", "history",
                                                        "recycle"}),
    ("What can you do?", "What can you do?", {"help", "can", "do", "how", "use", "work"}),
)
NOT_SURE = "I'm not sure what you mean yet. Is it one of these?"


def suggestions(text, facts=None, limit=3):
    words = set(re.findall(r"[a-z0-9']+", text))
    scored = []
    for index, (label, question, keys) in enumerate(TOPICS):
        score = len(words & keys)
        if score:
            scored.append((-score, index, label, question))
    scored.sort()
    picks = [(label, question) for _s, _i, label, question in scored[:limit]]
    named = engine.find_entity(facts, text) if facts is not None else None
    if named is not None:
        picks.insert(0, (f"About {named.name}", f"tell me about {named.name.casefold()}"))
    for label, question, _keys in TOPICS:
        if len(picks) >= limit:
            break
        if (label, question) not in picks and label in ("Largest games", "Free up space", "What can you do?"):
            picks.append((label, question))
    return picks[:limit]


def not_sure(text, facts=None, local_ai_on=False):
    picks = suggestions(text, facts)
    tail = ("" if local_ai_on else " You can also ask in other words, or switch on the local AI in the settings panel "
            "for open questions.")
    return engine.Answer("suggest", NOT_SURE + tail, (), "", (), tuple((label, "q:" + q) for label, q in picks))


# ------------------------------------------------------------------ the one entry point
def answer(question, facts, previous_question="", previous_answer=None, local_ai_on=False):
    """The built-in answer to a loosely worded question. Never "I don't know": a miss offers best guesses."""
    text = normalize(question, facts)
    if not text:
        return engine.answer(question, facts)
    rewritten = follow_up(text, facts, normalize(previous_question, facts) if previous_question else "", previous_answer)
    if isinstance(rewritten, engine.Answer):
        return rewritten
    if rewritten:
        text = rewritten
    parts = split_two(text)
    if len(parts) == 2:
        first, second = engine.answer(parts[0], facts), engine.answer(parts[1], facts)
        known = [a for a in (first, second) if a.intent not in ("unknown", "help")]
        if len(known) == 2 and first.text != second.text:
            return _combine(first, second)
        if len(known) == 1 and engine.answer(text, facts).intent in ("unknown", "help"):
            return known[0]
    result = engine.answer(text, facts)
    if result.intent == "unknown":
        return not_sure(text, facts, local_ai_on)
    return result
