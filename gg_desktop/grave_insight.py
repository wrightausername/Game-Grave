"""Qt-free Graveyard view helpers: filters with live counts, sorting, metrics and honest explanations."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from core import human_size, is_protected_path
from gg_desktop import grave_data as data
from graveyard_protection import protection_action

MB = 1024 ** 2
GB = 1024 ** 3
AGE_STEPS = (("30+ Days", 30), ("3+ Months", 90), ("6+ Months", 180), ("12+ Months", 365), ("24+ Months", 730))
AGE_LABELS = tuple(label for label, _ in AGE_STEPS)
SIZE_BUCKETS = (("< 100 MB", 0, 100 * MB), ("100 MB - 1 GB", 100 * MB, GB),
                ("1 GB - 10 GB", GB, 10 * GB), ("> 10 GB", 10 * GB, None))
SIZE_LABELS = tuple(label for label, _, _ in SIZE_BUCKETS)
SORTS = ("Last Touched (Oldest)", "Last Touched (Newest)", "Size (Largest)", "Size (Smallest)", "Name (A-Z)")
MAX_RECYCLE = 200
IDLE_DAYS = 180


def size_index(size):
    for i, (_, low, high) in enumerate(SIZE_BUCKETS):
        if size >= low and (high is None or size < high):
            return i
    return 0


def age_threshold(labels):
    steps = dict(AGE_STEPS)
    return min((steps[l] for l in labels if l in steps), default=None)


def search_text(item):
    return " ".join((item.name, item.path, item.category, item.related, item.kind, item.evidence)).casefold()


def matches(item, tab="All Items", ages=(), sizes=(), types=None, query="", skip=None):
    """True when the item passes every filter except the facet named in skip."""
    if tab != "All Items" and item.tab != tab:
        return False
    if query and query.strip().casefold() not in search_text(item):
        return False
    if skip != "age" and ages:
        floor = age_threshold(ages)
        if floor is not None and (item.age_days is None or item.age_days < floor):
            return False
    if skip != "size" and sizes and SIZE_LABELS[size_index(item.size)] not in sizes:
        return False
    if skip != "type" and types is not None and item.kind not in types:
        return False
    return True


def sort_items(items, sort):
    if sort == "Last Touched (Newest)":
        return sorted(items, key=lambda i: (i.modified is None, -(i.modified or 0), i.name.casefold()))
    if sort == "Size (Largest)":
        return sorted(items, key=lambda i: (-i.size, i.name.casefold()))
    if sort == "Size (Smallest)":
        return sorted(items, key=lambda i: (i.size, i.name.casefold()))
    if sort == "Name (A-Z)":
        return sorted(items, key=lambda i: i.name.casefold())
    return sorted(items, key=lambda i: (i.modified is None, i.modified or 0, i.name.casefold()))


def filter_items(items, *, tab="All Items", ages=(), sizes=(), types=None, query="", sort=SORTS[0]):
    return sort_items([i for i in items if matches(i, tab, ages, sizes, types, query)], sort)


def tab_counts(items):
    counts = {name: 0 for name in data.TABS}
    counts["All Items"] = len(items)
    for item in items:
        counts[item.tab] += 1
    return counts


def facet_counts(items, *, tab="All Items", ages=(), sizes=(), types=None, query=""):
    """Counts for each filter choice given the other filters, so a count says what checking it would show."""
    age = {label: 0 for label in AGE_LABELS}
    size = {label: 0 for label in SIZE_LABELS}
    kind = {label: 0 for label in data.TYPES}
    for item in items:
        if matches(item, tab, ages, sizes, types, query, skip="age"):
            for label, days in AGE_STEPS:
                if item.age_days is not None and item.age_days >= days:
                    age[label] += 1
        if matches(item, tab, ages, sizes, types, query, skip="size"):
            size[SIZE_LABELS[size_index(item.size)]] += 1
        if matches(item, tab, ages, sizes, types, query, skip="type"):
            kind[item.kind] += 1
    return age, size, kind


def recyclable(item):
    """The existing engine can move this single file to the Recycle Bin after its own re-checks."""
    entry = item.entry
    return bool(entry is not None and entry.can_recycle and entry.old_file is not None
                and entry.category != "Old game screenshot")


def needs_preview(item):
    return item.entry is not None and item.entry.category == "Old game screenshot"


def totals(items, never_touch=(), now=None):
    games = {i.game for i in items if i.game}
    return {
        "items": len(items), "bytes": sum(i.size for i in items),
        "idle": sum(i.age_days is not None and i.age_days >= IDLE_DAYS for i in items),
        "games": len(games), "mods": sum(i.tab == "Mods" for i in items),
        "downloads": sum(i.tab == "Downloads" for i in items),
        "reviewable": sum(recyclable(i) and not data.is_protected(i, never_touch) for i in items),
    }


def size_text(items):
    return human_size(sum(i.size for i in items))


def date_text(item):
    return datetime.fromtimestamp(item.modified).strftime("%b %d, %Y") if item.modified is not None else "Unknown"


def age_phrase(item):
    if item.age_days is None:
        return "Unknown"
    return f"{date_text(item)} ({item.age_days:,} days ago)"


def items_text(item):
    if item.items is None:
        return "Not counted"
    if item.is_folder_item and item.storage is not None:
        return f"{item.items:,} files" + (" or more" if item.partial else "")
    return "1 file"


def protection_state(item, never_touch):
    """(action, reason) from the protected engine. Action is Protect, Unprotect or None."""
    if item.storage is not None and item.storage.protected_kind:
        return None, "Settings and saves are never removed. Protect is not needed."
    return protection_action(item.path, list(never_touch))


def reasons(item, never_touch):
    """Plain facts about what can be done with this item, never a recommendation to delete."""
    lines = []
    protected = data.is_protected(item, never_touch)
    action, why = protection_state(item, never_touch)
    if protected and action != "Unprotect":
        lines.append(("shield", why or "Protected by Game Grave."))
    if recyclable(item) and not protected:
        lines.append(("trash", "This single file can move to the Recycle Bin after you confirm. It is re-checked first and can be restored."))
    elif needs_preview(item) and not protected:
        lines.append(("camera", "Screenshots are removed one at a time, only after you preview that exact image."))
    elif item.tab == "Games":
        lines.append(("game", "Installed games are removed only through Steam. Game Grave never deletes a game folder."))
    elif item.tab == "Mods":
        lines.append(("mods", "Mod folders are reviewed in Mods, where your mod manager's profiles are checked. Not removed here."))
    elif item.storage is not None and item.storage.cleanable and not protected:
        lines.append(("storage", "A small launcher cache or log folder like this can be cleared from Other Storage, file by file."))
    elif item.storage is not None:
        lines.append(("storage", "This is review only here. Use the owning launcher or Windows to clear it."))
    if action == "Protect":
        lines.append(("shield", "Protect keeps it out of every future cleanup."))
    elif action == "Unprotect":
        lines.append(("shield", "You protected this. Unprotect removes only that one rule."))
    lines.append(("undo", "Anything moved to the Recycle Bin is listed in Undo Center and can be restored."))
    return lines


def delete_options(items, never_touch):
    """Menu entries for the Delete button: (key, label, enabled, tip)."""
    protected = any(data.is_protected(i, never_touch) for i in items)
    recyclables = [i for i in items if recyclable(i)]
    options = []
    ok = bool(items) and not protected and len(recyclables) == len(items) and len(items) <= MAX_RECYCLE
    tip = ("Moves each checked file to the Recycle Bin after confirmation and per-file re-checks." if ok else
           "Check ordinary archives or recordings. Protected items, screenshots, games, mods and folders cannot be batched."
           if items else "Check one or more files first.")
    options.append(("recycle", "Move Files to Recycle Bin…", ok, tip))
    one = items[0] if len(items) == 1 else None
    options.append(("preview", "Preview Screenshot Then Remove…", bool(one) and needs_preview(one) and not protected,
                    "Opens the exact image. Removal stays one image at a time."))
    options.append(("steam", "Uninstall in Steam…", bool(one) and one.tab == "Games" and bool(one.app_id),
                    "Opens Steam's own uninstall prompt for this game."))
    options.append(("mods", "Review in Mods", bool(one) and one.tab == "Mods", "Opens the Mods tab."))
    options.append(("storage", "Review in Other Storage", bool(one) and one.storage is not None,
                    "Opens Other Storage, where small launcher caches and logs can be cleared."))
    return options


def csv_rows(items):
    yield ["Name", "Path", "Tab", "Type", "Related", "Last touched", "Age (days)", "Size (bytes)", "Evidence", "Why it is here"]
    for i in items:
        yield [i.name, i.path, i.tab, i.kind, i.related, date_text(i), "" if i.age_days is None else i.age_days,
               i.size, i.evidence, i.why]
