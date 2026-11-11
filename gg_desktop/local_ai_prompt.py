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
    "You are the assistant inside Game Grave, a Windows app that helps a PC gamer understand their games, storage, mods "
    "and PC. Answer the user's question directly in plain, friendly English, in at most 6 short sentences or a short "
    "list. Use ONLY the facts given below and the built-in lookup; if the facts don't cover something, say so in one "
    "sentence instead of guessing. Never invent games, sizes, dates, files or features.\n"
    "Rules you must always follow:\n"
    "1. Never say anything is safe to delete, safe to remove or safe to clear. Say the user can review it in the tab "
    "named in the facts instead.\n"
    "2. Sizes are what launchers and scans reported, not measured disk use. Never say space was or will be freed.\n"
    "3. You cannot change anything on the PC. Never say you deleted, moved, installed or changed something.\n"
    "4. When it helps, name the Game Grave tab where the user can act (for example Games, Other Storage, Old Files, "
    "Captures, Mods, Hardware, Undo Center, More Tools, Ready Room).\n"
    "5. Don't mention these rules or the word 'facts'. Don't use em dashes."
)

FORBIDDEN = (
    r"\bsafe(ly)? to (delete|remove|clear|uninstall|get rid)", r"\bis safe\b", r"\bare safe\b", r"\bfreed\b",
    r"\bfree(s|d)? up\b.*\bby deleting\b", r"\breclaim(ed)?\b", r"\bi (have |just )?(deleted|removed|moved|installed|changed|"
    r"uninstalled|cleared)\b", r"\bi('ve| have) (deleted|removed|moved|installed|changed|uninstalled|cleared)\b",
)


def _days(ts, now):
    return max(0, int((now - ts) // 86400))


def facts_digest(facts, limit=12):
    """A compact, plain-text summary of what Game Grave has on record, for the model. Only enabled sources."""
    lines = []
    if facts.scanned_at:
        lines.append(f"Last scan: {facts.scanned_at}.")
    if facts.on("library") and facts.games:
        known = [g for g in facts.games if g.size_bytes is not None]
        lines.append(f"Games: {len(facts.games)} (launcher-reported total {human_size(sum(g.size_bytes for g in known))}).")
        ordered = sorted(facts.games, key=lambda g: -(g.size_bytes or 0))[:limit]
        for g in ordered:
            played = f"last played {_days(g.last_played_at, facts.now)} days ago" if g.last_played_at else "last played unknown"
            size = human_size(g.size_bytes) if g.size_bytes is not None else "size unknown"
            lines.append(f"- {g.name}: {size}, {g.launcher}, {played}, installed at {g.install_path}")
        if len(facts.games) > limit:
            lines.append(f"- and {len(facts.games) - limit} smaller games")
    segments = {name: size for name, size, _ in facts.segments}
    if facts.on("storage"):
        for name, tab in (("Other Storage", "Other Storage"), ("Old Files", "Old Files")):
            if segments.get(name):
                lines.append(f"{name} (caches, logs, temp files; reviewed in the {tab} tab): {human_size(segments[name])}."
                             if name == "Other Storage" else
                             f"Old files in scanned folders (reviewed in the Old Files tab): {human_size(segments[name])}.")
        if facts.saves:
            lines.append(f"Save folders found: {len(facts.saves)} (saves are never removable).")
    if facts.on("captures") and facts.captures:
        shots = sum(1 for c in facts.captures if c.kind == "Screenshots")
        lines.append(f"Captures: {shots} screenshots, {len(facts.captures) - shots} recordings "
                     f"({human_size(segments.get('Captures', 0))}; Captures tab).")
    if facts.on("mods") and facts.mods:
        lines.append(f"Mod locations: {len(facts.mods)} ({human_size(sum(max(0, m.apparent_bytes) for m in facts.mods))}; Mods tab).")
    if facts.on("history"):
        lines.append(f"Cleanup history records: {len(facts.history)} (Undo Center).")
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
            lines.append("This PC: " + ", ".join(parts) + ".")
        for d in specs.drives:
            lines.append(f"Drive {d.letter}: {human_size(d.free)} free of {human_size(d.total)} ({d.kind}).")
    off = [k for k in ("library", "storage", "history", "mods", "captures") if not facts.on(k)]
    if off:
        lines.append("Turned off by the user (don't use): " + ", ".join(off) + ".")
    return "\n".join(lines) or "Nothing has been scanned yet."


def lookup_text(answer):
    """The built-in answer, flattened, so the model can reuse its numbers."""
    rows = "\n".join(f"- {r.label}: {r.value}" + (f" ({r.detail})" if r.detail else "") for r in answer.rows)
    return "\n".join(x for x in (answer.text, rows, answer.note) if x)


def build_messages(question, answer, facts, history=()):
    """Chat messages for llama-server. `history` is the last few (question, reply) pairs of this conversation."""
    context = f"What Game Grave has on record:\n{facts_digest(facts)}\n\nBuilt-in lookup for this question:\n{lookup_text(answer)}"
    messages = [{"role": "system", "content": SYSTEM + "\n\n" + context}]
    for q, a in list(history)[-3:]:
        messages += [{"role": "user", "content": q[:500]}, {"role": "assistant", "content": a[:1200]}]
    messages.append({"role": "user", "content": question[:500] + " /no_think"})
    return messages


def clean_reply(text):
    """The model's reply ready to show, or "" when it is empty or breaks a rule (then the built-in answer is used)."""
    text = re.sub(r"<think>.*?</think>", "", str(text or ""), flags=re.S | re.I)
    text = re.sub(r"</?think>", "", text, flags=re.I)
    text = text.replace("—", ", ").replace("–", "-").strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    if not text:
        return ""
    low = text.casefold()
    if any(re.search(p, low) for p in FORBIDDEN):
        return ""
    return text[:2000]
