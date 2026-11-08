"""Qt-free view helpers for Other Storage: totals, tabs, filters, ring shares and honest captions."""
from __future__ import annotations

from gg_desktop.insight_models import STORAGE_TYPES
from gg_desktop.other_storage_data import MAX_FILES

PILLS = {"Caches": "Cache", "Shader Cache": "Shader", "Config / Settings": "Config", "Logs / Reports": "Logs",
         "Temporary Files": "Temp", "Other": "Other"}
TAB_CATEGORY = {"Caches": "Caches", "Shader Cache": "Shader Cache", "Configs": "Config / Settings",
                "Logs": "Logs / Reports", "Temporary": "Temporary Files"}
SORTS = ("Size (Largest)", "Name (A–Z)", "Type")
CLEANUP_NOTICE = (f"Only launcher cache and log folders with {MAX_FILES} files or fewer appear here, because Game Grave "
                  "can re-check them file by file. Driver caches, Steam library folders and settings are review only.")
BY_GAME_NOTICE = ("Ownership is shown only where the source proves it, such as a Steam app ID for an installed game. "
                  "Everything else stays under its launcher, driver or system name.")


def totals(entries):
    return {kind: sum(e.size for e in entries if e.category == kind) for kind in STORAGE_TYPES}


def shares(entries):
    """[(category, bytes, percent text)] in legend order; percentages of the reported total."""
    amounts = totals(entries)
    whole = sum(amounts.values())
    return [(kind, amounts[kind], f"{amounts[kind] * 100 / whole:.1f}%" if whole else "0.0%") for kind in STORAGE_TYPES]


def tab_rows(tab, entries):
    """Rows for one tab and its caption."""
    if tab == "By Game":
        rows = sorted(entries, key=lambda e: (e.related == "No installed game", e.related.casefold(), -e.size))
        return rows, BY_GAME_NOTICE
    if tab == "Cleanup Assistant":
        return [e for e in entries if e.cleanable], CLEANUP_NOTICE
    kind = TAB_CATEGORY.get(tab)
    if kind:
        return [e for e in entries if e.category == kind], ""
    return list(entries), ""


def filter_rows(rows, *, category="All Other Storage", query="", sort="Size (Largest)"):
    tokens = query.casefold().split()
    output = []
    for e in rows:
        if category != "All Other Storage" and e.category != category:
            continue
        text = " ".join((e.name, e.path, e.category, e.related, e.summary, PILLS.get(e.category, ""))).casefold()
        if tokens and not all(t in text for t in tokens):
            continue
        output.append(e)
    if sort == "Name (A–Z)":
        output.sort(key=lambda e: e.name.casefold())
    elif sort == "Type":
        output.sort(key=lambda e: (STORAGE_TYPES.index(e.category) if e.category in STORAGE_TYPES else 99, -e.size))
    else:
        output.sort(key=lambda e: (-e.size, e.name.casefold()))
    return output


def selection_state(selected, never_touch_hit):
    """(delete enabled, tooltip) from the checked entries. `never_touch_hit` is True when any is protected."""
    if not selected:
        return False, "Check a launcher cache or log folder to clear it. Other items are review only."
    if never_touch_hit:
        return False, "A checked item is protected by Game Grave or your Never Touch list."
    if any(e.protected_kind for e in selected):
        return False, "Settings and save folders are never removed by Game Grave."
    if not all(e.cleanable for e in selected):
        return False, f"Only launcher cache and log folders with {MAX_FILES} files or fewer can be cleared here."
    if sum(e.items for e in selected) > MAX_FILES:
        return False, f"Check fewer folders: one run moves at most {MAX_FILES} files."
    return True, "Moves the verified files to the Windows Recycle Bin after you confirm. Nothing is permanently deleted."
