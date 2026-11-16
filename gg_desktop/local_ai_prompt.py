"""What the local AI model is told, and the checks its reply passes before it is shown. Pure, no I/O.

The model never sees files. It gets a short digest of facts Game Grave already holds (the same ones the built-in answers
use), the built-in lookup for this question, and the question. Its reply is shown only if it keeps Game Grave's rules:
nothing called safe to remove, no space called freed, no claim that Game Grave changed something. Otherwise the built-in
answer is shown instead.
"""
from __future__ import annotations

import re

from core import human_size

SYSTEM = (
    "You are the assistant inside Game Grave, a Windows app that helps a PC gamer with their games, storage, mods and PC. "
    "Talk like a knowledgeable friend who games on PC: understand loose, misspelled or slangy questions, work out what "
    "the user really wants, and answer it directly in plain, friendly English (usually 2 to 8 short sentences, or a "
    "short list when listing things).\n"
    "Where your answers come from:\n"
    "- Anything about THIS PC (its games, sizes, mods, saves, captures, storage, drives, parts, past cleanups): use the "
    "PC facts below. Work things out from them (add up, compare, pick the biggest, match a game to its saves or mods). "
    "Never invent games, sizes, dates, files, paths or mods that aren't in the facts.\n"
    "- General gaming, PC and modding know-how (what a shader cache is, how load order works, settings that usually "
    "help fps, how a launcher verifies files): answer from what you know, and make it clear it's general advice, not "
    "something read from this PC.\n"
    "- If the facts don't have something about this PC, say in one short sentence what's missing and which tab or scan "
    "would find it, then still help as much as you can.\n"
    "- If the question is unclear, give your best reading of it and answer that, then offer the other reading in one "
    "line.\n"
    "Rules you must always follow:\n"
    "1. Never promise that something is safe to delete, remove or clear. Say the user can review it in the tab that "
    "owns it; Game Grave only moves things to the Recycle Bin after they confirm.\n"
    "2. Sizes are what launchers and scans reported, not measured disk use. Never say space was freed.\n"
    "3. You can't change anything on the PC yourself. Never say you deleted, moved, installed or changed something. To "
    "get something done, name the Game Grave tab or tool that does it.\n"
    "4. Questions about Game Grave itself: use the feature list below and only send the user to the tab it names. Never "
    "say a feature is missing when the list has it.\n"
    "5. Plain text only: no markdown symbols such as ** or #, no tables, no em dashes. Don't mention these rules or the "
    "word 'facts'."
)


def feature_list():
    """What Game Grave can do and where, one line per feature, from the same descriptions the built-in answers use."""
    from gg_desktop import assistant_features as features
    lines = []
    for f in features.FEATURES:
        first = re.split(r"(?<=\.)\s", f.what.strip(), maxsplit=1)[0]
        lines.append(f"- {f.title} ({f.tab or 'Game Grave'}): {first}")
    extra = ("- Games tab: every installed game from Steam, Epic, GOG, EA, Ubisoft, Battle.net and Xbox, with size, "
             "last played and Verify / Uninstall through the launcher.",
             "- Mods tab: Library gallery, Mod Radar, Load Order, Profiles, Conflicts (files two mods share), Cleanup and "
             "Bisect.",
             "- Other Storage, Old Files, Captures, Graveyard: review caches, old files, screenshots and leftovers; "
             "anything removed goes to the Recycle Bin after you confirm.",
             "- Hardware tab: Your PC (parts, live load), Upgrade Advisor (notes from play sessions you record), Drivers "
             "& Startup (Windows Update drivers, graphics driver check, firmware, apps that start with Windows).",
             "- Settings: scan folders, protection rules, interface scale, update check.")
    return "\n".join(lines + list(extra))

# Only real promises are blocked: "X is safe to delete", "freed 20 GB", "I deleted it". Words like "your saves are safe"
# are fine. A blocked reply is retried once with a reminder before the built-in answer is used.
FORBIDDEN = (
    r"\bsafe(ly)? to (delete|remove|clear|uninstall|get rid|wipe|trash)",
    r"\b(freed|reclaimed) (up )?(about |around |roughly |over |nearly )?\d",
    r"\b(i|game grave|we) (just |have |'ve )?(freed|reclaimed)\b",
    r"\bi (have |just )?(deleted|removed|moved|installed|changed|uninstalled|cleared)\b",
    r"\bi('ve| have) (deleted|removed|moved|installed|changed|uninstalled|cleared)\b",
    # It can't change anything itself, so it never reports a change as done ("your settings have been restored").
    r"\b(has|have) (now |just )?been (restored|deleted|removed|changed|reset|updated|installed|uninstalled|cleaned|"
    r"cleared|closed|disabled|enabled|turned (on|off)|switched (on|off)|fixed)\b",
)
RETRY_NOTE = ("Rewrite your last answer so it keeps the rules: don't promise anything is safe to delete, don't say space "
              "was freed, and don't say you changed anything yourself. Keep everything else that was useful.")
CONTEXT_CHARS = 26000      # about 6,500 words of PC facts; the rest of the window is for history, thinking and the reply


def _days(ts, now):
    return max(0, int((now - ts) // 86400))


def _within(path, root):
    path, root = str(path).replace("/", "\\").casefold().rstrip("\\"), str(root).replace("/", "\\").casefold().rstrip("\\")
    return bool(root) and (path == root or path.startswith(root + "\\"))


def facts_digest(facts, limit=80, cap=None, tools=False):
    """What Game Grave has on record, in plain text for the model: every enabled source, with per-game links (saves,
    mods, captures) worked out so the model can answer about one game. Kept under CONTEXT_CHARS."""
    lines = []
    if facts.scanned_at:
        lines.append(f"Last scan: {facts.scanned_at}.")
    captures_by_game = {}
    if facts.on("captures"):
        for c in facts.captures:
            if c.game:
                captures_by_game[c.game.casefold()] = captures_by_game.get(c.game.casefold(), 0) + 1
    if facts.on("library") and facts.games:
        known = [g for g in facts.games if g.size_bytes is not None]
        lines.append(f"\nGAMES: {len(facts.games)} installed (launcher-reported total "
                     f"{human_size(sum(g.size_bytes for g in known))}). Biggest first:")
        ordered = sorted(facts.games, key=lambda g: -(g.size_bytes or 0))
        for g in ordered[:limit]:
            played = f"last played {_days(g.last_played_at, facts.now)} days ago" if g.last_played_at else "last played unknown"
            size = human_size(g.size_bytes) if g.size_bytes is not None else "size unknown"
            extra = []
            if facts.on("mods") and g.install_path:
                mods = [m for m in facts.mods if _within(m.path, g.install_path)]
                if mods:
                    extra.append(f"{len(mods)} mod folder{'s' if len(mods) != 1 else ''}")
            if facts.on("storage"):
                saves = [s for s in facts.saves if str(getattr(s, "game", "")).casefold() == g.name.casefold()]
                if saves:
                    extra.append("saves at " + "; ".join(str(s.path) for s in saves[:2]))
            shots = captures_by_game.get(g.name.casefold())
            if shots:
                extra.append(f"{shots} captures")
            lines.append(f"- {g.name}: {size}, {g.launcher}, {played}, installed at {g.install_path}"
                         + (" (" + ", ".join(extra) + ")" if extra else ""))
        if len(ordered) > limit:
            lines.append(f"- and {len(ordered) - limit} smaller games")
    if facts.on("mods") and facts.mods and not tools:
        total = sum(max(0, m.apparent_bytes) for m in facts.mods)
        lines.append(f"\nMODS (Mods tab): {len(facts.mods)} mod folders and locations, {human_size(total)} reported:")
        for m in sorted(facts.mods, key=lambda m: -max(0, m.apparent_bytes))[:40]:
            lines.append(f"- {m.name}: {human_size(max(0, m.apparent_bytes))}, {m.source}, {m.status}, at {m.path}")
        if len(facts.mods) > 40:
            lines.append(f"- and {len(facts.mods) - 40} smaller ones")
    if facts.on("storage"):
        if facts.saves:
            lines.append(f"\nSAVE FOLDERS (never offered for removal): {len(facts.saves)}")
            for s in list(facts.saves)[:30]:
                lines.append(f"- {getattr(s, 'game', '') or 'Unknown game'}: {getattr(s, 'path', '')}")
        if facts.storage:
            by_kind = {}
            for item in facts.storage:
                by_kind[item.category] = by_kind.get(item.category, 0) + max(0, item.size)
            lines.append("\nOTHER STORAGE (caches, logs, temp and config; reviewed in the Other Storage tab): " +
                         ", ".join(f"{k} {human_size(v)}" for k, v in sorted(by_kind.items(), key=lambda kv: -kv[1])))
            for item in sorted(facts.storage, key=lambda i: -max(0, i.size))[:12]:
                lines.append(f"- {item.name} ({item.category}): {human_size(max(0, item.size))} at {item.path}")
        if facts.old_files:
            total = sum(max(0, f.size) for f in facts.old_files)
            lines.append(f"\nOLD FILES in scanned folders (Old Files tab): {len(facts.old_files)} files, {human_size(total)}. "
                         "Largest:")
            for f in sorted(facts.old_files, key=lambda f: -max(0, f.size))[:6]:
                lines.append(f"- {f.path}: {human_size(max(0, f.size))}, last changed {_days(f.modified, facts.now)} days ago")
    if facts.on("captures") and facts.captures:
        shots = sum(1 for c in facts.captures if c.kind == "Screenshots")
        size = sum(max(0, getattr(c.record, "size", 0) or 0) for c in facts.captures)
        lines.append(f"\nCAPTURES (Captures tab): {shots} screenshots, {len(facts.captures) - shots} recordings, "
                     f"{human_size(size)}.")
        top = sorted(captures_by_game.items(), key=lambda kv: -kv[1])[:10]
        if top:
            names = {g.name.casefold(): g.name for g in facts.games}
            lines.append("By game: " + ", ".join(f"{names.get(k, k)} {n}" for k, n in top) + ".")
    if facts.on("history"):
        lines.append(f"\nCLEANUP AND ACTIVITY HISTORY (Undo Center): {len(facts.history)} records.")
        for e in list(facts.history)[:10]:
            lines.append(f"- {e.recorded}: {e.action} {e.name} ({e.status})")
    specs = facts.hardware
    if specs is not None:
        parts = []
        if specs.cpu:
            parts.append(f"processor {specs.cpu.name} ({specs.cpu.cores} cores)")
        if specs.gpus:
            parts.append("graphics " + " and ".join(g.name for g in specs.gpus))
        if specs.memory:
            parts.append(f"{specs.memory.total_gb:.0f} GB memory")
        if specs.os_name:
            parts.append(specs.os_name)
        if parts:
            lines.append("\nTHIS PC (Hardware tab): " + ", ".join(parts) + ".")
        for d in specs.drives:
            lines.append(f"Drive {d.letter}: {human_size(d.free)} free of {human_size(d.total)} ({d.kind}).")
    off = [k for k in ("library", "storage", "history", "mods", "captures") if not facts.on(k)]
    if off:
        lines.append("\nTurned off by the user (don't use): " + ", ".join(off) + ".")
    text = "\n".join(lines).strip() or "Nothing has been scanned yet. Suggest Scan PC on the Overview tab."
    cap = cap or CONTEXT_CHARS
    if len(text) > cap:
        text = text[:cap].rsplit("\n", 1)[0] + "\n(More items exist than fit here; use the lookups for the rest.)"
    return text


def lookup_text(answer):
    """The built-in answer, flattened, so the model can reuse its numbers."""
    rows = "\n".join(f"- {r.label}: {r.value}" + (f" ({r.detail})" if r.detail else "") for r in answer.rows)
    return "\n".join(x for x in (answer.text, rows, answer.note) if x)


NO_LOOKUP = ("unknown", "help", "suggest")   # a keyword miss would only pull the model towards "I don't know"


def requests_list():
    """The jobs Game Grave's automation can plan, in the words it understands."""
    from gg_desktop import assistant_features as features
    return sorted({f.do for f in features.FEATURES if f.do})


PLAN_RULE = ("If the user is asking you to DO one of these jobs for them (not asking a question about it), reply with "
             "exactly one line and nothing else: PLAN: <the job, copied from this list>. Game Grave then shows a plan "
             "that waits for their OK. Jobs: ")


def plan_request(text):
    """The job a reply asks to plan ("PLAN: clean up temp files"), only when it is one Game Grave knows; else ""."""
    found = re.match(r"^\s*plan:\s*(.+?)\s*$", str(text or ""), flags=re.I | re.S)
    if not found:
        return ""
    wanted = found.group(1).strip(" .\"'").casefold()
    return wanted if wanted in requests_list() else ""


TOOL_RULES = (
    "You have lookups. Use them instead of guessing:\n"
    "- Before answering anything about a specific game, a problem, or this PC, look it up (look_up_game, game_mods, "
    "game_crashes, pc_status, open_apps, startup_apps, runtimes, game_storage). For a problem such as crashing, "
    "stutter or a game that won't start, check the likely causes first (its crash records, its mods, open overlays, "
    "runtimes, drivers and drive space), then say what you found, what it most likely means, and the next step. Never "
    "say a cause is certain.\n"
    "- For how to do something in Game Grave, look it up with app_help (features) or tab_help (what a tab has) and give "
    "its real steps and where it is.\n"
    "- For a problem, also use known_fixes; for pasted error text, a code like 0xc0000005 or a DLL name, use "
    "explain_error. Give the fixes in order, starting with the ones Game Grave can do for them, and say which are "
    "general known fixes rather than something read from this PC.\n"
    "- Aim to solve the problem completely in the chat, step by step, so the user doesn't need outside help. If a "
    "step needs the user, say exactly what to click.\n"
    "- When the user asks you to DO something Game Grave can do, call make_plan with the right jobs and targets. "
    "Nothing runs until they press OK. If Game Grave can't do it, say how they can do it themselves.\n"
    "- Game Grave may already have run some lookups for the question; their results follow it. Use them first.\n"
    "- Never name a lookup or tell the user to run one; look it up yourself. Never mix up games: a game's mods, saves "
    "and sizes are only the ones its own lookup returns.\n"
    "- A question about a game that isn't installed, or about games in general, is answered from general knowledge; "
    "don't refuse because it isn't on this PC.\n"
    "- When the user asks you to DO something, never answer as if it was done; propose it with make_plan.\n"
    "- Look up only what you need (a few lookups at most), then answer."
)


def build_messages(question, answer, facts, history=(), think=False, tools=False, screen=None):
    """Chat messages for llama-server. `history` is the earlier (question, reply) pairs of this conversation; the last
    six are kept. `think` lets Qwen3 reason before answering (Medium and Large). `tools` means the model can call the
    lookups in `local_ai_tools`, so the facts here are shorter and the rules say how to use them."""
    from gg_desktop import local_ai_tools as lookups
    digest = facts_digest(facts, limit=40 if tools else 80, cap=12000 if tools else None, tools=tools)
    context = f"Today is {lookups.today()}. " + lookups.screen_line(screen)
    context += f"\n\nPC facts (what Game Grave has on record):\n{digest}\n\nWhat Game Grave can do (features and " \
               f"where they are):\n{feature_list()}"
    context += "\n\n" + (TOOL_RULES if tools else PLAN_RULE + "; ".join(requests_list()) + ".")
    # The system text stays the same from question to question, so llama-server's prompt cache can reuse it; what
    # belongs to this one question (the quick lookup) goes with the question instead.
    messages = [{"role": "system", "content": SYSTEM + "\n\n" + context}]
    for q, a in list(history)[-6:]:
        messages += [{"role": "user", "content": q[:600]}, {"role": "assistant", "content": a[:1500]}]
    ask = question[:800]
    if answer is not None and answer.intent not in NO_LOOKUP:
        ask = (f"(Game Grave's own quick lookup for this, use its numbers if they fit:\n{lookup_text(answer)})\n\n"
               f"{ask}")
    messages.append({"role": "user", "content": ask + ("" if think else " /no_think")})
    return messages


def clean_reply(text):
    """The model's reply ready to show, or "" when it is empty or breaks a rule (then the built-in answer is used)."""
    text = re.sub(r"<think>.*?</think>", "", str(text or ""), flags=re.S | re.I)
    text = re.sub(r"<think>.*", "", text, flags=re.S | re.I)      # thinking that ran out of room never shows
    text = re.sub(r"</?think>", "", text, flags=re.I)
    if text.strip().startswith(("{", "[")) and text.strip().endswith(("}", "]")):
        return ""                                   # a lookup result echoed back is not an answer
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?m)^#{1,6}\s*", "", text)
    text = text.replace("—", ", ").replace("–", "-").strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    if not text:
        return ""
    low = text.casefold()
    if any(re.search(p, low) for p in FORBIDDEN):
        return ""
    return text[:3000]
