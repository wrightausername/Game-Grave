"""Read-only classification and grouping for the Old Files page. No Qt, no file access.

Everything here derives from a completed scan: the path, size, modified time and the existing
review rules. Nothing claims a file is safe or unused; evidence lines state only what the path and
timestamps show.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import PurePath
import re
import time

from gg_desktop.library_models import file_kind
from gg_desktop.old_files_data import key, review_reason, within

FILTER_GROUPS = ("Game Files / Leftovers", "Downloads", "Archives", "Installers", "Logs / Crash Reports", "Other")
CACHE_NAMES = {"cache", "shadercache", "shader cache", "gpucache", "code cache", "temp", "tmp", "crashdumps"}
LARGE_BYTES = 1024 ** 3
FOLDER_SELECT_LIMIT = 200
REVIEWABLE = "Reviewable (not proven unused)"
SUBTITLES = {
    "Game": "Possible game or mod download",
    "Cache": "Stored in a cache or temp folder",
    "Downloads": "In a Downloads folder",
    "Installer": "Setup program or disc image",
    "Archive": "Compressed archive",
    "Logs": "Log, dump or temp file",
    "Media": "Image or video",
    "Other": "Other file",
}
GROUP_OF = {"Game": "Game Files / Leftovers", "Cache": "Game Files / Leftovers", "Downloads": "Downloads",
            "Archive": "Archives", "Installer": "Installers", "Logs": "Logs / Crash Reports",
            "Media": "Other", "Other": "Other"}


@dataclass(frozen=True)
class Info:
    pill: str
    subtitle: str
    group: str
    possible_game: bool
    downloads: bool
    cache: str  # name of the matching folder, or ""
    extension: str


def _parents(path):
    return [part.casefold() for part in PurePath(str(path)).parts[:-1]]


def possible_game(path):
    """Existing narrow heuristic from the Graveyard: file name resembles gaming content."""
    from pathlib import Path
    from graveyard import looks_like_game_archive
    return looks_like_game_archive(Path(str(path)))


def classify(path) -> Info:
    ext = PurePath(str(path)).suffix.casefold()
    parents = _parents(path)
    downloads = "downloads" in parents
    cache = next((part for part in reversed(parents) if part in CACHE_NAMES), "")
    kind = file_kind(path)
    game = possible_game(path)
    if game:
        pill = "Game"
    elif kind == "Installers":
        pill = "Installer"
    elif kind == "Archives":
        pill = "Archive"
    elif kind == "Logs / Crash Reports":
        pill = "Logs"
    elif kind == "Media":
        pill = "Media"
    elif cache:
        pill = "Cache"
    elif downloads:
        pill = "Downloads"
    else:
        pill = "Other"
    subtitle = SUBTITLES[pill]
    if pill == "Other" and ext:
        subtitle = f"{ext} file"
    return Info(pill, subtitle, GROUP_OF[pill], game, downloads, cache, ext)


def age_days(file, now=None):
    return max(0, int(((time.time() if now is None else now) - file.modified) / 86400))


def age_label(days):
    if days >= 365:
        return f"{days // 365} year{'s' if days >= 730 else ''} ago"
    if days >= 60:
        return f"{days // 30} months ago"
    return f"{days} days ago"


def evidence(file, info, result, protections, now=None):
    """(text, good) lines for "Why It's Flagged". good=True is a plain fact, False is a warning."""
    days = age_days(file, now)
    lines = [(f"Last modified {days:,} days ago ({age_label(days)})", True)]
    if info.possible_game:
        lines.append(("File name resembles gaming content (not verified)", True))
    if info.cache:
        lines.append((f"Stored in a folder named \"{info.cache}\"", True))
    if info.downloads:
        lines.append(("Stored in a Downloads folder", True))
    reason = review_reason(file, result, protections) if result else "No completed scan"
    if reason == REVIEWABLE:
        lines.append(("Outside protected game, mod, save and system locations", True))
    else:
        lines.append((reason, False))
    return lines


# ---- metrics and tab views
def metrics(entries, now=None):
    """entries: list of (file, info). Counts only what the scan established."""
    now = time.time() if now is None else now
    files = [f for f, _ in entries]
    oldest = max((age_days(f, now) for f in files), default=None)
    game = sum(1 for _, i in entries if i.possible_game)
    downloads = sum(1 for _, i in entries if not i.possible_game and i.pill in {"Downloads", "Archive"})
    return {"total": len(files), "size": sum(f.size for f in files), "oldest_days": oldest,
            "possible_game": game, "downloads_archives": downloads,
            "other": len(files) - game - downloads}


def tab_entries(tab, entries):
    """Rows for one tab, and the honest caption for it."""
    if tab == "By Game":
        rows = [e for e in entries if e[1].possible_game]
        return rows, ("Files whose names resemble gaming content. Ownership is not verified; game folders "
                      "themselves are protected and never scanned." if rows else
                      "No files in this scan resemble gaming content. Game, mod and save folders are protected and not scanned.")
    if tab == "Downloads":
        rows = [e for e in entries if e[1].downloads]
        return rows, "Files inside a folder named Downloads." if rows else "No old files in a Downloads folder for this scan."
    if tab == "Archives":
        return [e for e in entries if file_kind(e[0].path) == "Archives"], ""
    if tab == "Unused Installers":
        return ([e for e in entries if file_kind(e[0].path) == "Installers"],
                "Installer files. This scan cannot establish whether they are unused.")
    if tab == "Large Files":
        return [e for e in entries if e[0].size >= LARGE_BYTES], "Files of 1 GB or more."
    return list(entries), ""


def filter_entries(entries, *, groups, query="", min_days=0, now=None, sort="Size (Largest)"):
    now = time.time() if now is None else now
    tokens = query.casefold().split()
    rows = []
    for f, info in entries:
        if info.group not in groups:
            continue
        if min_days and f.modified > now - min_days * 86400:
            continue
        if tokens and not all(t in (f.path + " " + info.pill + " " + info.subtitle).casefold() for t in tokens):
            continue
        rows.append((f, info))
    if sort == "Name (A–Z)":
        rows.sort(key=lambda e: (PurePath(e[0].path).name.casefold(), e[0].path))
    elif sort == "Oldest Modified":
        rows.sort(key=lambda e: (e[0].modified, e[0].path))
    elif sort == "Newest Modified":
        rows.sort(key=lambda e: (-e[0].modified, e[0].path))
    else:
        rows.sort(key=lambda e: (-e[0].size, e[0].path))
    return rows


# ---- folder groups (review only)
@dataclass(frozen=True)
class Group:
    path: str
    name: str
    files: tuple
    size: int
    oldest: float
    newest: float
    pill: str
    kinds: dict

    @property
    def count(self):
        return len(self.files)

    @property
    def selectable(self):
        return self.count <= FOLDER_SELECT_LIMIT

    @property
    def subtitle(self):
        return f"{self.count:,} file{'s' if self.count != 1 else ''} · {SUBTITLES[self.pill]}"


def group_folders(entries, scan_roots):
    """Group by the first folder beneath the scanned root; files directly in a root group as that root."""
    roots = sorted({str(r) for r in scan_roots}, key=lambda r: -len(key(r)))
    buckets = {}
    for f, info in entries:
        root = next((r for r in roots if within(f.path, r)), None)
        folder = str(PurePath(f.path).parent)
        if root:
            rel = PurePath(f.path).relative_to(PurePath(root)) if _relative(f.path, root) else None
            if rel is not None and len(rel.parts) > 1:
                folder = str(PurePath(root) / rel.parts[0])
            elif rel is not None:
                folder = root
        buckets.setdefault(key(folder), (folder, []))[1].append((f, info))
    groups = []
    for folder, items in buckets.values():
        by_bytes = Counter()
        for f, info in items:
            by_bytes[info.pill] += f.size
        files = tuple(f for f, _ in items)
        groups.append(Group(folder, PurePath(folder).name or folder, files, sum(f.size for f in files),
                            min(f.modified for f in files), max(f.modified for f in files),
                            by_bytes.most_common(1)[0][0], dict(Counter(i.pill for _, i in items))))
    groups.sort(key=lambda g: (-g.size, g.path.casefold()))
    return groups


def _relative(path, root):
    try:
        PurePath(path).relative_to(PurePath(root))
        return True
    except ValueError:
        return False


def clean_name(text):
    """File name without the underscore/dash noise, for the row title only."""
    return re.sub(r"\s+", " ", text).strip() or text
