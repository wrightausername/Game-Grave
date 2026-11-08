"""Qt-free Undo Center filters, live facet counts, sorting, metrics and CSV rows. Read-only."""
from __future__ import annotations

import csv
import io
import time

from core import human_size
from gg_desktop import undo_data as data

SORTS = ("Date (Newest)", "Date (Oldest)", "Size (Largest)", "Name (A-Z)")
SOURCE_SHOWN = 6


def _csv_safe(value):
    value = str(value)
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


class Filters:
    def __init__(self, range_name="All Time", start=None, end=None, categories=None, sources=None, query="",
                 show_hidden=False):
        self.range_name, self.start, self.end = range_name, start, end
        self.categories = set(data.CATEGORIES) if categories is None else set(categories)
        self.sources = set(sources or ())      # empty means every source
        self.query = query.strip().casefold()
        self.show_hidden = show_hidden


def in_range(entry, filters, now):
    if filters.range_name == "All Time":
        return True
    if entry.when is None:
        return False
    if filters.range_name == "Custom Range":
        low = filters.start if filters.start is not None else float("-inf")
        high = filters.end if filters.end is not None else float("inf")
        return low <= entry.when <= high
    days = data.RANGE_DAYS.get(filters.range_name, 0)
    return entry.when >= now - days * data.DAY


def matches(entry, filters, hidden, now, *, skip=()):
    if "hidden" not in skip and not filters.show_hidden and entry.key in hidden:
        return False
    if "range" not in skip and not in_range(entry, filters, now):
        return False
    if "category" not in skip and entry.category not in filters.categories:
        return False
    if "source" not in skip and filters.sources and entry.source not in filters.sources:
        return False
    if filters.query and filters.query not in " ".join((entry.path, entry.name, entry.action, entry.source, entry.note,
                                                        entry.status)).casefold():
        return False
    return True


def apply(entries, filters, hidden, sort="Date (Newest)", now=None):
    now = time.time() if now is None else now
    rows = [e for e in entries if matches(e, filters, hidden, now)]
    if sort == "Date (Oldest)":
        rows.sort(key=lambda e: e.when or 0)
    elif sort == "Size (Largest)":
        rows.sort(key=lambda e: (e.size is None, -(e.size or 0)))
    elif sort == "Name (A-Z)":
        rows.sort(key=lambda e: (e.name.casefold(), -(e.when or 0)))
    else:
        rows.sort(key=lambda e: -(e.when or 0))
    return rows


def range_counts(entries, filters, hidden, now=None):
    """How many entries each preset would show with every other filter kept."""
    now = time.time() if now is None else now
    pool = [e for e in entries if matches(e, filters, hidden, now, skip=("range",))]
    counts = {}
    for name in data.RANGES:
        if name == "Custom Range":
            continue
        days = data.RANGE_DAYS[name]
        counts[name] = sum(1 for e in pool if not days or (e.when is not None and e.when >= now - days * data.DAY))
    return counts


def category_counts(entries, filters, hidden, now=None):
    now = time.time() if now is None else now
    counts = dict.fromkeys(data.CATEGORIES, 0)
    for e in entries:
        if matches(e, filters, hidden, now, skip=("category",)):
            counts[e.category] += 1
    return counts


def source_counts(entries, filters, hidden, now=None):
    now = time.time() if now is None else now
    counts = {}
    for e in entries:
        if matches(e, filters, hidden, now, skip=("source",)):
            counts[e.source] = counts.get(e.source, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].casefold())))


def metrics(entries, hidden):
    """Seven honest numbers. Recycled bytes are not freed bytes."""
    live = [e for e in entries if e.key not in hidden]
    recycled = [e for e in live if e.recovery_id and e.state != "Restored"]
    return {
        "total": len(live),
        "recycled": sum(1 for e in live if e.recovery_id),
        "review": sum(1 for e in live if e.tone == "amber"),
        "failed": sum(1 for e in live if e.tone == "red"),
        "restored": sum(1 for e in live if e.state == "Restored" and e.recovery_id),
        "bytes": sum(e.size or 0 for e in recycled),
        "available": sum(1 for e in recycled if e.state == "Available"),
    }


def selection_text(rows):
    known = sum(e.size or 0 for e in rows)
    return f"{len(rows):,} selected ({human_size(known)})" if rows else "0 selected"


def csv_rows(rows):
    output = [["Action", "Item", "Path", "Source", "Size (bytes)", "Recorded", "Status", "Recovery ID", "Note"]]
    for e in rows:
        output.append([_csv_safe(v) for v in (e.action, e.name, e.path, e.source, "" if e.size is None else e.size,
                                              e.recorded, e.status, e.recovery_id or "", e.note)])
    return output


def csv_text(rows):
    buffer = io.StringIO()
    csv.writer(buffer).writerows(csv_rows(rows))
    return buffer.getvalue()
