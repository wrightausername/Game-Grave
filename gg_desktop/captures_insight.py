"""Qt-free view helpers for Captures: totals, tabs, filters, related items and honest recommendation facts."""
from __future__ import annotations

from pathlib import Path
import time

from core import is_protected_path, human_size
from gg_desktop.captures_data import UNVERIFIED

TABS = ("Screenshots", "Recordings", "By Game", "Timeline", "Duplicates", "Similar", "Clean Up", "Settings")
AGE_CHOICES = ("Any Age", "30+ Days", "6+ Months", "12+ Months", "2+ Years")
AGE_DAYS = (0, 30, 180, 365, 730)
SIZE_CHOICES = ("Any Size", "Under 5 MB", "5 to 20 MB", "20 MB or More", "1 GB or More")
RES_CHOICES = ("Any Resolution", "4K or Larger", "1440p or Larger", "1080p or Larger", "Under 1080p", "Unknown")
SORTS = ("Date (Newest)", "Date (Oldest)", "Size (Largest)", "Name (A–Z)")
ALL_GAMES, ALL_TAGS, ALL_MONTHS, UNTAGGED = "All Games", "All Tags", "All Months", "Untagged"
CANDIDATE_DAYS = 180
MB = 1024 ** 2

NOTICES = {
    "By Game": "Game links come from Steam screenshot folders with an app ID, or a folder name that matches an installed game.",
    "Timeline": "Timeline uses the file's modified date. The date a game captured it may differ.",
    "Clean Up": ("Captures last modified over 6 months ago, plus extra copies from the last duplicate check. "
                 "Age alone does not make a capture unwanted. Review before removing."),
}


def age_days(capture, now):
    return max(0, int((now - capture.modified) // 86400))


def age_text(days):
    if days is None:
        return "Unknown"
    if days >= 365:
        return f"{days // 365}+ Years"
    if days >= 30:
        return f"{days // 30}+ Months"
    return f"{days} Days"


def month_key(capture):
    return time.strftime("%Y-%m", time.localtime(capture.modified))


def month_label(key):
    year, month = key.split("-")
    names = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    return f"{names[int(month) - 1]} {year}"


def months(captures):
    return sorted({month_key(c) for c in captures}, reverse=True)


def game_counts(captures):
    counts = {}
    for c in captures:
        counts[c.game] = counts.get(c.game, 0) + 1
    named = sorted(((g, n) for g, n in counts.items() if g != UNVERIFIED), key=lambda p: (-p[1], p[0].casefold()))
    return named + ([(UNVERIFIED, counts[UNVERIFIED])] if UNVERIFIED in counts else [])


def is_candidate(capture, never_touch, now):
    return (capture.removable and age_days(capture, now) >= CANDIDATE_DAYS
            and not is_protected_path(Path(capture.path), never_touch))


def totals(captures, never_touch=(), now=None):
    now = time.time() if now is None else now
    shots = sum(c.kind == "Screenshots" for c in captures)
    oldest = max((age_days(c, now) for c in captures), default=None)
    return {
        "screenshots": shots, "recordings": len(captures) - shots, "bytes": sum(c.size for c in captures),
        "games": len({c.game for c in captures if c.game != UNVERIFIED}), "oldest": oldest,
        "candidate_bytes": sum(c.size for c in captures if is_candidate(c, never_touch, now)),
    }


def _size_ok(size, index):
    return (index == 0 or index == 1 and size < 5 * MB or index == 2 and 5 * MB <= size < 20 * MB
            or index == 3 and size >= 20 * MB or index == 4 and size >= 1024 ** 3)


def _resolution_ok(capture, index):
    dims = capture.dimensions
    if index == 0:
        return True
    if index == 5:
        return dims is None
    if dims is None:
        return False
    wide = max(dims)
    return (index == 1 and wide >= 3840 or index == 2 and wide >= 2560 or index == 3 and wide >= 1920
            or index == 4 and wide < 1920)


def duplicate_extras(groups, by_key):
    """Keys of every copy except the oldest of each exact-duplicate group."""
    extras = set()
    for group in groups or []:
        members = sorted((by_key[k] for k in group if k in by_key), key=lambda c: (c.modified, c.path.casefold()))
        extras.update(c.key for c in members[1:])
    return extras


def filter_captures(captures, *, tab="Screenshots", game=ALL_GAMES, kinds=("Screenshots", "Recordings"), age=0, size=0,
                    resolution=0, tag=ALL_TAGS, query="", sort=SORTS[0], month=ALL_MONTHS, tags=None,
                    duplicates=None, similar=None, never_touch=(), now=None):
    """Captures for one tab and the filters on the left. `duplicates` and `similar` are lists of key groups or None."""
    now = time.time() if now is None else now
    tags = tags or {}
    by_key = {c.key: c for c in captures}
    words = query.casefold().split()
    group_of = {}
    source = duplicates if tab == "Duplicates" else similar if tab == "Similar" else None
    for number, group in enumerate(source or []):
        for key in group:
            group_of[key] = number
    extras = duplicate_extras(duplicates, by_key)
    output = []
    for c in captures:
        if c.kind not in kinds or (game != ALL_GAMES and c.game != game):
            continue
        if tab == "Screenshots" and c.kind != "Screenshots" or tab == "Recordings" and c.kind != "Recordings":
            continue
        if tab in ("Duplicates", "Similar") and c.key not in group_of:
            continue
        if tab == "Clean Up" and not (is_candidate(c, never_touch, now) or c.key in extras):
            continue
        if tab == "Timeline" and month != ALL_MONTHS and month_key(c) != month:
            continue
        if AGE_DAYS[age] and age_days(c, now) < AGE_DAYS[age]:
            continue
        if not _size_ok(c.size, size) or not _resolution_ok(c, resolution):
            continue
        mine = tags.get(c.key, [])
        if tag == UNTAGGED and mine or tag not in (ALL_TAGS, UNTAGGED) and tag not in mine:
            continue
        if words:
            hay = " ".join((c.path, c.game, c.kind, " ".join(mine))).casefold()
            if not all(w in hay for w in words):
                continue
        output.append(c)
    if tab in ("Duplicates", "Similar"):
        output.sort(key=lambda c: (group_of[c.key], c.modified, c.path.casefold()))
    elif tab == "By Game":
        output.sort(key=lambda c: (c.game == UNVERIFIED, c.game.casefold(), -c.modified))
    else:
        output.sort(key=(lambda c: c.modified) if sort == SORTS[1] else (lambda c: (-c.size, c.path.casefold())) if sort == SORTS[2]
                    else (lambda c: c.name.casefold()) if sort == SORTS[3] else (lambda c: -c.modified))
    return output


def related(capture, captures, duplicates, similar, limit=12):
    """[(reason, capture)] for the Related tab: identical copies, similar images, same game and day."""
    by_key = {c.key: c for c in captures}
    output, seen = [], {capture.key}
    for reason, groups in (("Exact copy", duplicates), ("Looks similar", similar)):
        for group in groups or []:
            if capture.key in group:
                for key in group:
                    if key not in seen and key in by_key:
                        seen.add(key)
                        output.append((reason, by_key[key]))
    day = time.strftime("%Y-%m-%d", time.localtime(capture.modified))
    if capture.game != UNVERIFIED:
        for c in captures:
            if (c.key not in seen and c.game == capture.game
                    and time.strftime("%Y-%m-%d", time.localtime(c.modified)) == day):
                seen.add(c.key)
                output.append(("Same game, same day", c))
    return output[:limit]


def facts(capture, *, never_touch, duplicates, similar, now=None):
    """[(tone, text)] shown as Recommendations. Only what is known; never says a file is safe to delete."""
    now = time.time() if now is None else now
    days = age_days(capture, now)
    protected = is_protected_path(Path(capture.path), never_touch)
    output = [("ok" if days >= CANDIDATE_DAYS else "info", f"Last modified {days:,} days ago ({age_text(days)})")]
    if duplicates is None:
        output.append(("info", "Duplicates not checked. Use the Duplicates tab to compare file contents."))
    else:
        group = next((g for g in duplicates if capture.key in g), None)
        output.append(("warn", f"Identical copies: {len(group) - 1} other file(s)") if group
                      else ("ok", "No identical copy in the last duplicate check"))
    if similar is not None and any(capture.key in g for g in similar):
        output.append(("info", "Looks similar to other screenshots"))
    output.append(("warn", "Protected from removal") if protected else
                  ("warn", "Has more than one hard link, so it cannot be removed here") if not capture.removable else
                  ("info", "Moves to the Recycle Bin only after you confirm"))
    return output


def selection_state(selected, protected_hit):
    """(enabled, tooltip) for Delete…"""
    if not selected:
        return False, "Check one or more captures to remove them to the Recycle Bin."
    if protected_hit:
        return False, "A checked capture is protected by Game Grave or your Never Touch list."
    if any(not c.removable for c in selected):
        return False, "A checked capture has more than one hard link and cannot be removed here."
    from gg_desktop.captures_actions import MAX_RUN
    if len(selected) > MAX_RUN:
        return False, f"Check at most {MAX_RUN} captures: one run moves up to {MAX_RUN} files."
    return True, "Moves the checked captures to the Windows Recycle Bin after you confirm. Nothing is permanently deleted."


def size_text(selected):
    return human_size(sum(c.size for c in selected))
