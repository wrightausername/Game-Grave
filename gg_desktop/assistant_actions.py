"""AI Assistant conversations: validated, size-limited, and kept in the owner's own settings file.

Only the question text and the assistant's answer are saved. Nothing here touches scanned files, recovery records or
the activity log, and clearing or deleting a conversation only removes the saved text.
"""
from __future__ import annotations

import json
import uuid

from gg_desktop import assistant_engine as engine

CHATS_KEY = "assistant_chats"
SCOPE_KEY = "assistant_scope"
MAX_CHATS = 20
MAX_MESSAGES = 40
MAX_QUESTION = 500
MAX_BYTES = 56_000  # well inside the 128 KB settings limit, which holds every other preference too
NEW_TITLE = "New chat"


def new_chat(now):
    return {"id": uuid.uuid4().hex[:12], "title": NEW_TITLE, "updated": float(now), "messages": []}


def _clean_message(raw):
    if not isinstance(raw, dict) or raw.get("role") not in ("user", "assistant"):
        return None
    text = str(raw.get("text", ""))[:2000]
    message = {"role": raw["role"], "text": text, "at": float(raw.get("at") or 0)}
    if raw["role"] == "assistant":
        answer = engine.answer_from_dict(raw.get("answer") or {})
        if answer is None:
            return None
        message["answer"] = answer.to_dict()
    return message


def load_chats(settings):
    """Saved conversations, newest first. Damaged entries are skipped, never fatal."""
    raw = settings.get(CHATS_KEY) if isinstance(settings, dict) else None
    chats = []
    for item in raw if isinstance(raw, list) else []:
        try:
            messages = [m for m in (_clean_message(x) for x in item.get("messages", [])[:MAX_MESSAGES]) if m]
            chats.append({"id": str(item["id"])[:24], "title": str(item.get("title") or NEW_TITLE)[:60],
                          "updated": float(item.get("updated") or 0), "messages": messages})
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
    return sorted(chats, key=lambda c: -c["updated"])[:MAX_CHATS]


def title_for(question):
    line = " ".join(question.split())
    return line if len(line) <= 42 else line[:41].rstrip() + "…"


def add_exchange(chat, question, answer, now):
    """Append one question and its answer to a chat (in place) and return it."""
    question = " ".join(question.split())[:MAX_QUESTION]
    chat["messages"].append({"role": "user", "text": question, "at": float(now)})
    chat["messages"].append({"role": "assistant", "text": answer.text, "at": float(now), "answer": answer.to_dict()})
    del chat["messages"][:-MAX_MESSAGES]
    if chat["title"] == NEW_TITLE:
        chat["title"] = title_for(question)
    chat["updated"] = float(now)
    return chat


def clear_chat(chat):
    chat["messages"] = []
    chat["title"] = NEW_TITLE
    return chat


def delete_chat(chats, chat_id):
    return [c for c in chats if c["id"] != chat_id]


def with_chats(settings, chats):
    """Settings with the conversations stored; oldest conversations are dropped first if the budget is exceeded."""
    kept = sorted(chats, key=lambda c: -c["updated"])[:MAX_CHATS]
    while kept and len(json.dumps(kept, ensure_ascii=False)) > MAX_BYTES:
        kept.pop()
    return dict(settings, **{CHATS_KEY: kept})


def scope_of(settings):
    value = settings.get(SCOPE_KEY) if isinstance(settings, dict) else None
    return value if isinstance(value, str) else ""


def with_scope(settings, key):
    return dict(settings, **{SCOPE_KEY: key or ""})


def answer_text(question, answer):
    """Plain text for Copy: the question, the answer, its rows, its note and the data it used."""
    lines = ["Q: " + question, answer.text]
    lines += [f"- {r.label}: {r.value}" if r.value else f"- {r.label}" for r in answer.rows]
    if answer.note:
        lines.append(answer.note)
    if answer.sources:
        lines.append("Sources: " + ", ".join(answer.sources))
    return "\n".join(lines)
