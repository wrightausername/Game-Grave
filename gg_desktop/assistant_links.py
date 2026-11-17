"""Clickable answers and next-question buttons for the AI Assistant. Pure: text in, HTML or suggestions out.

Game names open that game in Games, tab names open the tab, Windows folder paths open the folder. Opening changes
nothing. Next questions are a few short follow-ups that fit what was just asked.
"""
from __future__ import annotations

import html
import re

from gg_desktop import nav_groups

_PATH = r"[A-Za-z]:\\[^\s\"<>|*?,;()]+(?:\\[^\s\"<>|*?,;()]+)*"
LINK_STYLE = "color:#7cc4ff;text-decoration:none;"


def tab_names():
    """{shown name: route} for every sidebar tab ("Toolbox" opens More Tools)."""
    names = {}
    for route in nav_groups.routes():
        names[nav_groups.display_name(route)] = route
    return names


def linkify(text, games=(), tabs=None):
    """The answer as safe HTML with game names, tab names and folder paths as links. Plain text stays plain."""
    tabs = tab_names() if tabs is None else tabs
    names = sorted({g for g in games if len(g) >= 3}, key=len, reverse=True)
    tab_list = sorted((t for t in tabs if len(t) >= 4), key=len, reverse=True)
    parts = [f"(?P<path>{_PATH})"]
    if names:
        parts.append("(?P<game>" + "|".join(re.escape(n) for n in names) + r")(?![\w])")
    if tab_list:
        parts.append(r"(?<![\w])(?P<tab>" + "|".join(re.escape(t) for t in tab_list) + r")(?![\w])")
    pattern = re.compile("|".join(parts))
    out, at = [], 0
    for m in pattern.finditer(text or ""):
        out.append(html.escape(text[at:m.start()]))
        word = m.group(0)
        if m.group("path"):
            word = word.rstrip(".:")
            href = "path:" + word
        elif names and m.group("game"):
            href = "game:" + word
        else:
            href = "tab:" + tabs[word]
        out.append(f'<a href="{html.escape(href, quote=True)}" style="{LINK_STYLE}">{html.escape(word)}</a>')
        out.append(html.escape(text[m.start() + len(word):m.end()]))
        at = m.end()
    out.append(html.escape((text or "")[at:]))
    return "".join(out).replace("\n", "<br>")


def has_links(text, games=(), tabs=None):
    return "<a " in linkify(text, games, tabs)


# ------------------------------------------------------------------ next questions
NEXT = {
    "games": (("Which haven't I played lately?", "Which games haven't I played lately?"),
              ("Free up space", "What can I review to free up space?")),
    "summary": (("Biggest games", "What are my largest games?"), ("Free up space", "What can I review to free up space?")),
    "candidates": (("Games I don't play", "Which games haven't I played lately?"),
                   ("What's in Other Storage?", "What's in Other Storage?")),
    "performance": (("Get my PC ready to play", "get my PC ready to play"), ("Check my drivers", "check my drivers"),
                    ("Make it run better", "how do I make a game run better")),
    "hardware": (("Can I fit a 100 GB game?", "Do I have room for a 100 GB game?"),
                 ("Check my drivers", "check my drivers")),
    "mods": (("Any mod conflicts?", "Do I have any mod conflicts?"),
             ("Find a crashing mod", "how do I find which mod is crashing my game")),
    "error": (("Check the usual fixes", "fix my game"), ("Check my drivers", "check my drivers")),
    "fixes": (("Help me fix it step by step", "help me fix my game"), ("Check my drivers", "check my drivers")),
    "captures": (("Find duplicate screenshots", "how do I find duplicate screenshots"),),
    "saves": (("Back up my saves", "how do I back up my saves"),),
}


def next_questions(intent, question="", answer_text="", game=""):
    """Up to three short follow-ups that fit the last answer: (button text, question to ask)."""
    picks = list(NEXT.get(intent, ()))
    q = (question or "").casefold()
    if game and intent in ("profile", "feature", "local_ai", "fixes", "error"):
        picks = [(f"Is {game} modded?", f"is {game} modded"), (f"Where are {game}'s saves?", f"where are my {game} saves"),
                 (f"Fix {game}", f"help me fix {game}")] + picks
    elif intent == "local_ai" and re.search(r"crash|won'?t|stutter|lag|error|fix|broken", q):
        picks = [("Help me fix it step by step", "help me fix my game"), ("Find the crashing mod",
                 "how do I find which mod is crashing my game")] + picks
    seen, out = set(), []
    for label, ask in picks:
        if label not in seen and ask.casefold() != q:
            seen.add(label)
            out.append((label, ask))
    return out[:3]


SIMPLER = "Explain that again more simply, in short plain steps."
MORE = "Give me more detail on that, including the exact steps and where to click."


# ------------------------------------------------------------------ search and pins
PINS_KEY = "assistant_pins"
MAX_PINS = 30


def search_chats(chats, words):
    """Ids of chats whose title or any message contains every word typed (case ignored). Empty search matches all."""
    terms = [w for w in (words or "").casefold().split() if w]
    found = []
    for chat in chats:
        if not terms:
            found.append(chat["id"])
            continue
        text = " ".join([chat.get("title") or ""] + [str(m.get("text") or "") + " " +
                        str((m.get("answer") or {}).get("text") or "") for m in chat.get("messages") or []]).casefold()
        if all(t in text for t in terms):
            found.append(chat["id"])
    return found


def add_pin(pins, question, answer_text, when):
    """Pins with this answer added (newest last, MAX_PINS kept); the same question and answer is not pinned twice."""
    kept = [p for p in pins or [] if not (p.get("question") == question and p.get("answer") == answer_text)]
    kept.append({"question": question[:600], "answer": answer_text[:4000], "when": when})
    return kept[-MAX_PINS:]


def remove_pin(pins, index):
    return [p for i, p in enumerate(pins or []) if i != index]


# ------------------------------------------------------------------ errors and attached logs
def error_question(title, message):
    """The question asked when the owner presses "Ask the assistant" on a warning in the app."""
    body = " ".join(str(message or "").split())[:700]
    return f'Game Grave showed "{title}": {body} What does that mean and what should I do?'


LOG_TYPES = (".log", ".txt", ".ini", ".cfg", ".json", ".xml", ".dmp.txt", ".csv")
MAX_LOG_BYTES = 4 * 1024 * 1024
_KEY = re.compile(r"(error|exception|fatal|fail|crash|access violation|unhandled|0x[0-9a-f]{8}|\.dll|missing|"
                  r"not found|cannot|can't|couldn't|denied|warning|stack|caused by|faulting|plugin|master)", re.I)


def key_lines(text, limit=25):
    """The lines of a log worth asking about: errors, exceptions, crash codes, DLLs, missing files, with the line
    before each for context. Repeats are dropped. Falls back to the last lines when nothing stands out."""
    lines = [l.rstrip() for l in str(text or "").splitlines() if l.strip()]
    picked, seen = [], set()
    for i, line in enumerate(lines):
        if _KEY.search(line):
            for l in (lines[i - 1] if i and not _KEY.search(lines[i - 1]) else None, line):
                if l is None:
                    continue
                short = l.strip()[:240]
                norm = re.sub(r"\d+", "#", short.casefold())
                if norm not in seen:
                    seen.add(norm)
                    picked.append(short)
        if len(picked) >= limit:
            break
    if not picked:
        picked = [l.strip()[:240] for l in lines[-min(limit, 12):]]
    return picked[:limit]


def log_question(name, text, ask=""):
    """The chat question for an attached file: its name, the key lines, and what the owner asked (if anything)."""
    lines = key_lines(text)
    ask = (ask or "").strip() or "What does this log say went wrong, and what should I try?"
    found = "\n".join(lines) if lines else "(the file is empty)"
    return f"{ask}\n\nFrom the file {name} (the lines that stand out):\n{found}"


def read_log(path):
    """(name, text) of a small text file, or (name, None, reason). Opens the file read only; nothing is changed."""
    from pathlib import Path
    p = Path(path)
    name = p.name
    if not any(name.casefold().endswith(t) for t in LOG_TYPES):
        return name, None, "Only text files can be attached: .log, .txt, .ini, .cfg, .json, .xml or .csv."
    try:
        size = p.stat().st_size
        if size > MAX_LOG_BYTES:
            with p.open("rb") as f:          # a big log: its end is where the crash usually is
                f.seek(size - MAX_LOG_BYTES)
                raw = f.read()
        else:
            raw = p.read_bytes()
    except OSError as exc:
        return name, None, f"That file couldn't be read ({exc.strerror or exc})."
    for enc in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            text = raw.decode(enc)
            if enc == "utf-16" and not raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
                continue
            return name, text, ""
        except UnicodeDecodeError:
            continue
    return name, raw.decode("utf-8", "replace"), ""
