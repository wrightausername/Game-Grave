"""Pure presentation-only sorting/filtering for the user-customizable Game Grave views.

This module never reads, writes, or deletes files. A filtered-out item is not
permission to delete it; cleanup authorization is separately enforced by core.
"""
from __future__ import annotations

from pathlib import Path

GRAVE_SORT_KEYS = ("Size", "Age", "Name", "Category", "Safety")
SORT_DIRECTIONS = ("Descending", "Ascending")
GRAVE_STATES = ("All findings", "Ready to delete", "Protected / review only")
LEGACY_READY_STATUS = "Reviewable archives"
GRAVE_SIZES = {"Any size": 0, "100 MB+": 100 * 1024**2,
               "1 GB+": 1024**3, "10 GB+": 10 * 1024**3}
GAMES_SORT_OPTIONS = ("Oldest first", "Newest first", "Largest first", "Smallest first",
                      "Name A-Z", "Name Z-A", "Date source A-Z", "Date source Z-A")
MOD_SORT_OPTIONS = ("Largest first", "Smallest first", "Name A-Z", "Name Z-A",
                    "Source A-Z", "Most items first")
FILES_SORT_OPTIONS = ("Largest first", "Smallest first", "Oldest first", "Newest first",
                      "Name A-Z", "Name Z-A")
GRAVE_PRESET_FIELDS = ("graveyard_sort", "graveyard_order", "graveyard_category",
                       "graveyard_status", "graveyard_min_size", "graveyard_search",
                       "graveyard_days")


def validated_choice(value, choices, default):
    return value if isinstance(value, str) and value in choices else default


def filter_sort_graveyard(entries, *, search="", category="All types",
                          status="All findings", minimum="Any size", sort="Size",
                          order="Descending"):
    """Filter by evidence, then sort stably. Unknown ages always appear last."""
    sort = validated_choice(sort, GRAVE_SORT_KEYS, "Size")
    order = validated_choice(order, SORT_DIRECTIONS, "Descending")
    if status == LEGACY_READY_STATUS:
        status = "Ready to delete"
    status = validated_choice(status, GRAVE_STATES, "All findings")
    minimum = validated_choice(minimum, tuple(GRAVE_SIZES), "Any size")
    query = (search if isinstance(search, str) else "").strip().casefold()
    visible = []
    for entry in entries:
        if category != "All types" and entry.category != category:
            continue
        if status == "Ready to delete" and not entry.can_recycle:
            continue
        if status == "Protected / review only" and entry.can_recycle:
            continue
        if entry.apparent_bytes < GRAVE_SIZES[minimum]:
            continue
        if query and query not in " ".join((entry.name, entry.path, entry.category,
                                             entry.relationship, entry.finding)).casefold():
            continue
        visible.append(entry)
    # Stable tie-breaker independent of scan order. Sort unknown ages separately.
    visible.sort(key=lambda e: (e.name.casefold(), e.path.casefold()))
    rev = order == "Descending"
    if sort == "Size":
        visible.sort(key=lambda e: e.apparent_bytes, reverse=rev)
    elif sort == "Age":
        visible.sort(key=lambda e: e.age_days if e.age_days is not None else -1,
                     reverse=rev)
        visible.sort(key=lambda e: e.age_days is None)
    elif sort == "Name":
        visible.sort(key=lambda e: e.name.casefold(), reverse=rev)
    elif sort == "Category":
        visible.sort(key=lambda e: e.category.casefold(), reverse=rev)
    elif sort == "Safety":
        visible.sort(key=lambda e: e.can_recycle, reverse=rev)
    return visible


def sort_games(games, sort="Oldest first"):
    sort = validated_choice(sort, GAMES_SORT_OPTIONS, "Oldest first")
    values = sorted(games, key=lambda g: (g.name.casefold(), g.app_id))
    if sort in ("Oldest first", "Newest first"):
        values.sort(key=lambda g: g.last_played if g.last_played is not None else 0,
                    reverse=sort == "Newest first")
        values.sort(key=lambda g: g.last_played is None)
    elif sort in ("Largest first", "Smallest first"):
        values.sort(key=lambda g: g.size, reverse=sort == "Largest first")
    elif sort == "Name Z-A":
        values.sort(key=lambda g: g.name.casefold(), reverse=True)
    elif sort in ("Date source A-Z", "Date source Z-A"):
        values.sort(key=lambda g: g.source.casefold(), reverse=sort.endswith("Z-A"))
    return values


def sort_mods(mods, sort="Largest first"):
    sort = validated_choice(sort, MOD_SORT_OPTIONS, "Largest first")
    values = sorted(mods, key=lambda m: (m.name.casefold(), m.path.casefold()))
    if sort in ("Largest first", "Smallest first"):
        values.sort(key=lambda m: m.apparent_bytes, reverse=sort == "Largest first")
    elif sort == "Name Z-A":
        values.sort(key=lambda m: m.name.casefold(), reverse=True)
    elif sort == "Source A-Z":
        values.sort(key=lambda m: m.source.casefold())
    elif sort == "Most items first":
        values.sort(key=lambda m: m.item_count, reverse=True)
    return values


def sort_files(files, sort="Largest first"):
    sort = validated_choice(sort, FILES_SORT_OPTIONS, "Largest first")
    values = sorted(files, key=lambda f: (Path(f.path).name.casefold(), f.path.casefold()))
    if sort in ("Largest first", "Smallest first"):
        values.sort(key=lambda f: f.size, reverse=sort == "Largest first")
    elif sort in ("Oldest first", "Newest first"):
        values.sort(key=lambda f: f.modified, reverse=sort == "Newest first")
    elif sort == "Name Z-A":
        values.sort(key=lambda f: Path(f.path).name.casefold(), reverse=True)
    return values


def sanitize_saved_views(saved):
    """Treat editable local settings as untrusted; bound record sizes and contents."""
    if not isinstance(saved, dict):
        return {}
    cleaned = {}
    for name, data in list(saved.items())[:30]:
        if not isinstance(name, str) or not (1 <= len(name.strip()) <= 32):
            continue
        if not isinstance(data, dict):
            continue
        days = data.get("graveyard_days", 365)
        if not isinstance(days, int) or days not in (180, 365, 730, 1095):
            days = 365
        cleaned[name.strip()] = {
            "graveyard_sort": validated_choice(data.get("graveyard_sort"), GRAVE_SORT_KEYS, "Size"),
            "graveyard_order": validated_choice(data.get("graveyard_order"), SORT_DIRECTIONS, "Descending"),
            "graveyard_category": str(data.get("graveyard_category", "All types"))[:100],
            "graveyard_status": validated_choice(
                "Ready to delete" if data.get("graveyard_status") == LEGACY_READY_STATUS
                else data.get("graveyard_status"), GRAVE_STATES, "All findings"),
            "graveyard_min_size": validated_choice(data.get("graveyard_min_size"), tuple(GRAVE_SIZES), "Any size"),
            "graveyard_search": str(data.get("graveyard_search", ""))[:120],
            "graveyard_days": days,
        }
    return cleaned
