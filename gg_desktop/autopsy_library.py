"""Autopsy's own small library of frame-time captures: found automatically, kept to the newest ten.

Why it exists: comparing "before" and "after" used to mean choosing two files by hand. Now Game Grave looks in the
folders that PresentMon, CapFrameX and FrameView save to, reads any new capture once, keeps only its summary numbers
and a thin trace in its own file, and compares the newest capture with the one before it for the same game.

Safe by design:
* It only ever reads capture CSVs. It never writes, moves or deletes one. "Replaces after 10" means Game Grave drops
  the oldest summary from its own library, never your file.
* It is built to stay out of the way of a game: small bounded passes (a few files, a size cap, a time gap between
  passes), no background watcher, and the screen layer skips a pass while a game is running.
* The game name comes from the capture's file name and is only a guess; it says so.

Pure Python (no Qt) so every rule is unit tested.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from gg_desktop import autopsy_core as au

KEEP = 10                         # captures kept in total; the oldest summary is replaced by a newer one
AUTO_FILES_PER_PASS = 2           # new captures read in one automatic pass
AUTO_MAX_BYTES = 80 * 1024 * 1024  # automatic passes skip bigger files; adding one by hand allows 250 MB
MIN_BYTES = 8 * 1024              # smaller files cannot hold the 600 frames a comparison needs
MAX_AGE_DAYS = 180
MAX_VISITED = 600                 # directory entries looked at per pass, so a huge folder cannot stall anything
MAX_DEPTH = 2
POINTS = 200
LIBRARY_MAX_BYTES = 2 * 1024 * 1024
MIN_GAP_SECONDS = 30 * 60         # automatic passes are at least this far apart
TOOL_WORDS = {"presentmon", "frameview", "capframex", "log", "capture", "csv", "benchmark", "bench"}
DATE_WORD = re.compile(r"^(\d{4}-?\d{2}-?\d{2}.*|\d{6,}|t?\d{6}|\d{1,2}h\d{2}.*)$", re.I)


@dataclass
class Entry:
    id: str
    path: str
    name: str
    game: str
    mtime: float
    size: int
    stats: dict = field(default_factory=dict)
    points: list = field(default_factory=list)

    def stats_obj(self) -> au.Stats:
        return au.Stats(**self.stats)

    def label(self) -> str:
        from datetime import datetime
        when = datetime.fromtimestamp(self.mtime).strftime("%b %d %H:%M")
        return f"{self.game} · {when} · {self.stats.get('avg_fps', 0):.0f} fps avg"


@dataclass
class Refresh:
    added: list = field(default_factory=list)
    dropped: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    looked: bool = False


# ------------------------------------------------------------------ where captures usually are
def default_roots(home: Path | None = None) -> list[Path]:
    home = home or Path.home()
    docs = [home / "Documents", home / "OneDrive" / "Documents"]
    names = ("PresentMon", "PresentMon/Captures", "CapFrameX/Captures", "FrameView", "NVIDIA/FrameView")
    return [base / name for base in docs for name in names]


def guess_game(file_name: str) -> str:
    """A game name from a capture's file name: tool words, dates and times are dropped. A guess, never a fact."""
    stem = re.sub(r"\.csv$", "", file_name, flags=re.I)
    stem = re.sub(r"\d{4}-\d{2}-\d{2}(?:[T_ -]?\d{4,6})?", " ", stem)
    words = [w for w in re.split(r"[-_ ]+", stem) if w]
    kept = [w for w in words if w.casefold() not in TOOL_WORDS and not DATE_WORD.match(w)]
    text = re.sub(r"\.exe$", "", " ".join(kept), flags=re.I).strip()
    return text[:60] or "Unknown game"


def entry_id(path: Path, size: int, mtime: float) -> str:
    return hashlib.sha1(f"{str(path).casefold()}|{size}|{int(mtime)}".encode("utf-8", "replace")).hexdigest()[:16]


def find_candidates(roots, known: set, *, now: float | None = None, max_bytes: int = AUTO_MAX_BYTES,
                    limit: int = AUTO_FILES_PER_PASS) -> tuple[list, list]:
    """(new capture paths newest first, notes). Looks at a bounded number of directory entries and reads no file."""
    now = time.time() if now is None else now
    oldest = now - MAX_AGE_DAYS * 86400
    found, notes, visited = [], [], 0
    skipped_big = 0
    for root in roots:
        stack = [(Path(root), 0)]
        while stack and visited < MAX_VISITED:
            folder, depth = stack.pop()
            try:
                with os.scandir(folder) as scan:
                    for item in scan:
                        visited += 1
                        if visited >= MAX_VISITED:
                            break
                        try:
                            if item.is_symlink():
                                continue
                            if item.is_dir(follow_symlinks=False):
                                if depth < MAX_DEPTH:
                                    stack.append((Path(item.path), depth + 1))
                                continue
                            if not item.name.casefold().endswith(".csv"):
                                continue
                            info = item.stat(follow_symlinks=False)
                        except OSError:
                            continue
                        if info.st_mtime < oldest or info.st_size < MIN_BYTES:
                            continue
                        if info.st_size > max_bytes:
                            skipped_big += 1
                            continue
                        if entry_id(Path(item.path), info.st_size, info.st_mtime) in known:
                            continue
                        found.append((info.st_mtime, Path(item.path)))
            except OSError:
                continue
    found.sort(key=lambda pair: pair[0], reverse=True)
    if skipped_big:
        notes.append(f"{skipped_big} capture{'s are' if skipped_big != 1 else ' is'} bigger than "
                     f"{max_bytes // (1024 * 1024)} MB, so the automatic check skipped "
                     f"{'them' if skipped_big != 1 else 'it'}. Add {'them' if skipped_big != 1 else 'it'} by hand if you want.")
    return [path for _when, path in found[:limit]], notes


def make_entry(path, *, max_bytes: int = au.MAX_BYTES) -> Entry:
    """Read one capture and keep its summary. Raises au.CaptureError when it is not a usable capture."""
    path = Path(path)
    try:
        info = path.stat()
    except OSError as problem:
        raise au.CaptureError(f"Could not open that file: {problem}")
    if info.st_size > max_bytes:
        raise au.CaptureError(f"That file is larger than {max_bytes // (1024 * 1024)} MB.")
    frames = au.read_capture(path)
    stats = au.stats_for(frames)
    points = [round(v, 1) for v in au.downsample_max(frames, POINTS)]
    return Entry(entry_id(path, info.st_size, info.st_mtime), str(path), path.name, guess_game(path.name),
                 info.st_mtime, info.st_size, asdict(stats), points)


# ------------------------------------------------------------------ the library
def merge(entries: list, new: list, keep: int = KEEP) -> tuple[list, list]:
    """(kept newest first, dropped). The oldest summaries are replaced once there are more than `keep`."""
    by_id = {e.id: e for e in entries}
    for item in new:
        by_id[item.id] = item
    ordered = sorted(by_id.values(), key=lambda e: e.mtime, reverse=True)
    return ordered[:keep], ordered[keep:]


def pair_for(entries: list, game: str | None = None):
    """(before, after) for the game of the newest capture: its newest capture and the one before, else the newest game that has two. (None, None) if none does."""
    if not entries:
        return None, None
    ordered = sorted(entries, key=lambda e: e.mtime, reverse=True)
    # The newest capture's game first; if it has no partner yet, the newest game that does (a stray capture of another game
    # must not hide a comparison that is already possible).
    targets = [game.casefold()] if game else []
    targets += [e.game.casefold() for e in ordered]
    for target in dict.fromkeys(targets):
        same = [e for e in ordered if e.game.casefold() == target]
        if len(same) >= 2:
            return same[1], same[0]
    return None, None


def headline(comparison) -> str:
    """One short sentence for the closed strip. Says nothing the comparison does not prove."""
    if comparison is None:
        return "Waiting for a second capture of the same game."
    if not comparison.comparable:
        return "The latest two captures are too short to compare."
    first = comparison.rows[0]
    if first.verdict in ("better", "worse"):
        return f"Latest capture: average FPS {first.change} ({first.verdict}) than the one before."
    return "Latest two captures are within normal wobble of each other."


# ------------------------------------------------------------------ storage
def library_dir() -> Path:
    import core
    return core.config_dir() / "autopsy"


def load(root: Path | None = None) -> list:
    path = (root or library_dir()) / "library.json"
    try:
        if path.stat().st_size > LIBRARY_MAX_BYTES:
            return []
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    entries = []
    for item in raw if isinstance(raw, list) else []:
        try:
            entry = Entry(str(item["id"]), str(item["path"]), str(item["name"]), str(item["game"]),
                          float(item["mtime"]), int(item["size"]), dict(item["stats"]),
                          [float(v) for v in item["points"]][:POINTS])
            entry.stats_obj()
        except (KeyError, TypeError, ValueError):
            continue
        entries.append(entry)
    return sorted(entries, key=lambda e: e.mtime, reverse=True)[:KEEP]


def save(entries: list, root: Path | None = None) -> None:
    root = root or library_dir()
    root.mkdir(parents=True, exist_ok=True)
    target = root / "library.json"
    temp = target.with_name(target.name + ".tmp")
    temp.write_text(json.dumps([asdict(e) for e in entries[:KEEP]], separators=(",", ":")), encoding="utf-8")
    os.replace(temp, target)


def refresh(roots=None, *, root: Path | None = None, now: float | None = None,
            max_bytes: int = AUTO_MAX_BYTES, limit: int = AUTO_FILES_PER_PASS) -> Refresh:
    """One bounded automatic pass. Never raises for a bad capture: it becomes a note."""
    result = Refresh(looked=True)
    entries = load(root)
    paths, notes = find_candidates(default_roots() if roots is None else roots, {e.id for e in entries},
                                   now=now, max_bytes=max_bytes, limit=limit)
    result.notes.extend(notes)
    new = []
    for path in paths:
        try:
            new.append(make_entry(path, max_bytes=max_bytes))
        except au.CaptureError as problem:
            result.notes.append(f"Skipped {path.name}: {problem}")
    if new:
        kept, dropped = merge(entries, new)
        try:
            save(kept, root)
        except OSError as problem:
            result.notes.append(f"Could not save the capture library: {problem}")
            return result
        result.added, result.dropped = new, dropped
    return result


def add_by_hand(path, *, root: Path | None = None) -> tuple[Entry, list]:
    """Add one chosen capture (up to 250 MB). Returns (entry, dropped). Raises au.CaptureError."""
    entry = make_entry(path)
    kept, dropped = merge(load(root), [entry])
    save(kept, root)
    return entry, dropped


def due(last_run: float | None, now: float | None = None) -> bool:
    now = time.monotonic() if now is None else now
    return last_run is None or now - last_run >= MIN_GAP_SECONDS
