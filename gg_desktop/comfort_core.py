"""Everyday comforts for the whole app (owner, 2026-11-14: "like it all except for reopen... go ahead"). Pure: no Qt, no
file access, so every rule is tested.

- History: Back (Alt+Left, the mouse's back button, the top bar's arrow) returns to the tab a button sent you away from.
- Notices: every finished job lands in the bell's list (kept between runs, newest 40) and pops up once.
- Shortcuts: Ctrl+1 to Ctrl+9 open the sidebar's tabs in order; Ctrl+/ lists every shortcut.
- Diagnostics: one block of text to paste when something breaks, with the user name taken out of paths.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import asdict, dataclass

NOTICES_KEY = "notices"
MAX_NOTICES = 40
MAX_HISTORY = 30
TRAY_KEY = "close_to_tray"
START_KEY = "start_with_windows"


# ------------------------------------------------------------------ back
class History:
    def __init__(self, limit=MAX_HISTORY):
        self.stack, self.limit, self.current = [], limit, ""

    def visit(self, route, going_back=False):
        """Record a page change. Going back does not push; the same page twice is one entry."""
        if route == self.current:
            return
        if self.current and not going_back:
            self.stack.append(self.current)
            del self.stack[:-self.limit]
        self.current = route

    def back(self):
        """The page to go back to, or "" when there is none."""
        while self.stack:
            route = self.stack.pop()
            if route != self.current:
                return route
        return ""

    def can_back(self):
        return any(r != self.current for r in self.stack)


# ------------------------------------------------------------------ notices
@dataclass
class Notice:
    title: str
    text: str
    tone: str = "good"      # good, warn, bad, info
    target: str = ""        # where Open goes: a tab name or an assistant target ("tool:...", "tab:...")
    at: float = 0.0
    read: bool = False


def notice(title, text, tone="good", target="", now=None):
    return Notice(str(title)[:80], str(text)[:400], tone if tone in ("good", "warn", "bad", "info") else "info",
                  str(target)[:90], float(now if now is not None else time.time()))


def load_notices(settings):
    raw = settings.get(NOTICES_KEY) if isinstance(settings, dict) else None
    out = []
    for item in raw if isinstance(raw, list) else []:
        try:
            out.append(Notice(str(item["title"])[:80], str(item.get("text", ""))[:400], str(item.get("tone", "info")),
                              str(item.get("target", ""))[:90], float(item.get("at") or 0), bool(item.get("read"))))
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    return sorted(out, key=lambda n: -n.at)[:MAX_NOTICES]


def add_notice(notices, item):
    return sorted([item] + list(notices), key=lambda n: -n.at)[:MAX_NOTICES]


def with_notices(settings, notices):
    return dict(settings, **{NOTICES_KEY: [asdict(n) for n in notices[:MAX_NOTICES]]})


def unread(notices):
    return sum(1 for n in notices if not n.read)


def mark_read(notices):
    for n in notices:
        n.read = True
    return notices


def ago(at, now=None):
    seconds = max(0, int((now if now is not None else time.time()) - at))
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60} min ago"
    if seconds < 86400:
        hours = seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = seconds // 86400
    return f"{days} day{'s' if days != 1 else ''} ago"


# ------------------------------------------------------------------ shortcuts
SHORTCUTS = (
    ("Ctrl+K", "Search"),
    ("F5", "Scan PC (or rescan the tab you're on)"),
    ("Esc", "Stop a scan, or clear the search"),
    ("Alt+Left", "Back to the tab you were on"),
    ("Ctrl+1 to Ctrl+9", "Open the tabs in the sidebar, top to bottom"),
    ("Ctrl+Shift+A", "Pop out the AI Assistant"),
    ("Ctrl+Shift+N", "Notifications"),
    ("Ctrl+O", "Games: open the selected game's install folder"),
    ("Enter", "Games: play the selected game"),
    ("Shift+F10", "Games: more options for the selected game"),
    ("Ctrl+/", "This list"),
)


def numbered_routes(order, visible):
    """The first nine tabs in sidebar order that are on screen, for Ctrl+1 to Ctrl+9."""
    return [route for route in order if route in visible][:9]


# ------------------------------------------------------------------ diagnostics
def scrub(text, home=None, user=None):
    """Take the user's name out of paths so diagnostics can be pasted anywhere."""
    text = str(text)
    home = home if home is not None else os.path.expanduser("~")
    user = user if user is not None else (os.environ.get("USERNAME") or os.environ.get("USER") or "")
    if home and len(home) > 3:
        text = re.sub(re.escape(home), "%USERPROFILE%", text, flags=re.IGNORECASE)
    if user and len(user) > 2:
        text = re.sub(r"(?i)([\\/])" + re.escape(user) + r"([\\/])", r"\1<user>\2", text)
    # Any other account folder too (a second Windows user, an old profile path in a warning).
    text = re.sub(r"(?i)\b([a-z]:[\\/]users[\\/])(?!public\b|default\b|<user>)[^\\/\s\"']+", r"\1<user>", text)
    return text


def diagnostics_text(version, system, counts, warnings, errors, events, switches, home=None, user=None):
    lines = ["Game Grave diagnostics", "Version: " + str(version), "Windows: " + str(system), ""]
    lines.append("Last scan: " + str(counts.get("scanned_at") or "none"))
    for key in ("games", "mods", "old files", "captures", "saves", "graveyard"):
        if key in counts:
            lines.append(f"  {key}: {counts[key]:,}")
    lines += ["", "Switches: " + ", ".join(f"{k}={'on' if v else 'off'}" for k, v in sorted(switches.items()))]
    lines += ["", "Scan warnings:"] + (["  " + w for w in warnings] or ["  none"])
    lines += ["", "Recent errors shown:"] + (["  " + e for e in errors[-20:]] or ["  none"])
    lines += ["", "Recent activity:"] + (["  " + e for e in events[-20:]] or ["  none"])
    return scrub("\n".join(lines), home, user)


# ------------------------------------------------------------------ start with Windows
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "Game Grave"


def run_command(exe_path):
    return f'"{exe_path}" --minimized'


def paused_text(names):
    """The top bar's note while a game runs: Game Grave's own background work waits."""
    names = [n for n in names if n]
    if not names:
        return ""
    shown = names[0] if len(names) == 1 else f"{names[0]} +{len(names) - 1}"
    return f"Paused while you play {shown}"


# ------------------------------------------------------------------ undo right after a removal
UNDO_MAX = 20   # the Undo Center's own batch limit


def record_ids(records):
    return {r.get("id") for r in records if isinstance(r, dict) and r.get("id")}


def new_removals(before, records):
    """Recycle Bin records added since `before` (a set of ids), newest last. Only records, never a guess from a path."""
    return [r for r in records if isinstance(r, dict) and r.get("id") and r.get("id") not in before
            and r.get("state") != "Restored"]


def undo_text(rows):
    """The pop-up line for a removal that just finished."""
    if not rows:
        return ""
    name = os.path.basename(str(rows[0].get("path", "")).rstrip("\\/")) or "1 item"
    size = sum(max(0, int(r.get("size") or 0)) for r in rows if isinstance(r.get("size"), (int, float)))
    what = name if len(rows) == 1 else f"{len(rows):,} items"
    from core import human_size
    return f"{what} went to the Windows Recycle Bin ({human_size(size)}). Undo puts it back where it was."


def undo_confirmation(rows):
    shown = [str(r.get("path", "")) for r in rows[:UNDO_MAX]]
    more = len(rows) - len(shown)
    return ("Put these back from the Windows Recycle Bin to their exact original places?\n\n" + "\n".join(shown) +
            (f"\n\n{more:,} more are in the Undo Center; restore them there." if more > 0 else "") +
            "\n\nEach one is checked first. Windows must hold exactly one matching item, and nothing that already "
            "exists at the original place is overwritten.")


# ------------------------------------------------------------------ remember sort and filters per tab
VIEWS_KEY = "view_memory"
REMEMBER_PREFIXES = ("Sort ", "Filter ")


def remembers(name):
    """Only sort and filter choices are kept; search text and ticks never are."""
    return isinstance(name, str) and name.startswith(REMEMBER_PREFIXES)


def views_of(settings):
    value = settings.get(VIEWS_KEY)
    if not isinstance(value, dict):
        return {}
    return {r: {k: v for k, v in kept.items() if isinstance(k, str) and isinstance(v, str)}
            for r, kept in value.items() if isinstance(r, str) and isinstance(kept, dict)}


def remembered(settings, route, name):
    return views_of(settings).get(route, {}).get(name)


def with_view(settings, route, name, value):
    views = views_of(settings)
    kept = dict(views.get(route, {}))
    kept[name[:80]] = str(value)[:80]
    views[route] = dict(list(kept.items())[-24:])
    return dict(settings, **{VIEWS_KEY: dict(list(views.items())[-30:])})


def without_views(settings):
    return {k: v for k, v in settings.items() if k != VIEWS_KEY}
