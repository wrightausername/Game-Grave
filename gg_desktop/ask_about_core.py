"""Qt-free "Ask the assistant about this": what Game Grave already knows about one game, mod, file or folder, in
plain words, with buttons to the tab and tool that act on it. It reads only the row it is given and never says an item
is safe to remove: it says what the scan saw and what each button would do.
"""
from __future__ import annotations

import re
import time

from gg_desktop.assistant_engine import Answer

KINDS = {"game": "game", "mod": "mod", "old_file": "old file", "storage": "storage item", "capture": "capture",
         "grave": "Graveyard item"}
TAB_OF = {"game": "Games", "mod": "Mods", "old_file": "Old Files", "storage": "Other Storage", "capture": "Captures",
          "grave": "Graveyard"}


def _size(value):
    if not isinstance(value, (int, float)) or value < 0:
        return ""
    from core import human_size
    return human_size(int(value))


def _date(value):
    if not isinstance(value, (int, float)) or value <= 0:
        return ""
    return time.strftime("%Y-%m-%d", time.localtime(value))


def info_of(kind, item):
    """The few fields every kind of row can offer, read with getattr so any row type works."""
    get = lambda *names: next((getattr(item, n) for n in names if getattr(item, n, None) not in (None, "")), "")
    path = str(get("path", "install_path", "folder") or "")
    name = str(get("name") or re.split(r"[\\/]", path.rstrip("\\/"))[-1] or "this item")
    old = getattr(item, "old_file", None)
    modified = get("modified", "newest", "last_played") or (getattr(old, "modified", None) if old else None)
    return {"kind": kind, "name": name, "path": path, "size": get("size", "size_bytes"),
            "modified": modified if isinstance(modified, (int, float)) else None,
            "related": str(get("related", "game", "manager") or ""), "category": str(get("category", "kind") or ""),
            "why": str(get("summary", "why", "evidence", "note", "install_evidence") or "")[:400]}


def question(info):
    kind = info.get("kind", "")
    if kind == "game":
        return f"Tell me about {info['name']}"
    return f"What is the {KINDS.get(kind, 'item')} \"{info['name']}\" and what can I do with it?"


def answer(info, protected=False):
    kind = info.get("kind", "")
    tab = TAB_OF.get(kind, "Overview")
    lines = [f"{info['name']} is in {tab}."]
    facts = []
    if info.get("category"):
        facts.append("type: " + info["category"])
    if info.get("related"):
        facts.append("related to: " + info["related"])
    if _size(info.get("size")):
        facts.append("size: " + _size(info["size"]))
    if _date(info.get("modified")):
        facts.append("last changed: " + _date(info["modified"]))
    if facts:
        lines.append("What the scan saw: " + "; ".join(facts) + ".")
    if info.get("path"):
        lines.append("Where it is: " + info["path"])
    if info.get("why"):
        lines.append("Why it is listed: " + info["why"])
    if protected:
        lines.append("It is covered by a Never Touch rule, so Game Grave will not remove it.")
    elif kind in ("old_file", "storage", "capture", "grave"):
        lines.append("Game Grave cannot tell whether you still need it. Open the folder to look first. If you want it "
                     "gone, Delete moves it to the Windows Recycle Bin after you confirm, and Undo puts it back. "
                     "Protect adds a Never Touch rule, and Review later in Graveyard keeps it for review without moving it.")
    elif kind == "mod":
        lines.append("Turning a mod off in My Mods does not delete it. Mod Organizer keeps the files.")
    return Answer("about_item", "\n\n".join(lines), sources=(tab,), handoffs=(("Open " + tab, tab),))
