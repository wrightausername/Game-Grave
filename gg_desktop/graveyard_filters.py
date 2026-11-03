"""Evidence-based ordering and filtering for discovered Graveyard records."""
from __future__ import annotations
import ntpath

SORT_OPTIONS = ("Largest first", "Smallest first", "Oldest evidence first",
                "Newest evidence first", "Name A to Z", "Name Z to A")
AGE_OPTIONS = {"All ages": None, "1+ year": 365,
               "2+ years": 730, "3+ years": 1095}

def evidence_drive(path):
    text = str(path or "")
    drive = ntpath.splitdrive(text)[0]
    if drive:
        return drive.upper() if len(drive) == 2 and drive[1] == ":" else drive
    return "/" if text.startswith("/") else "Unknown drive"

def available_drives(entries):
    return sorted({evidence_drive(e.path) for e in entries}, key=str.casefold)

def select_graveyard_entries(entries, *, query="", category="All types",
                             state="All findings", drive="All drives",
                             min_age_days=None, sort_by="Largest first"):
    needle = str(query).strip().casefold()
    rows = []
    for e in entries:
        if category != "All types" and e.category != category:
            continue
        if state == "Ready for review" and not e.can_recycle:
            continue
        if state == "Protected / preview only" and e.can_recycle:
            continue
        if drive != "All drives" and evidence_drive(e.path) != drive:
            continue
        age = e.age_days
        if min_age_days is not None and (type(age) is not int or age < min_age_days):
            continue
        if needle and needle not in (" ".join((
                str(e.name), str(e.path), str(e.category),
                str(e.relationship), str(e.finding)))).casefold():
            continue
        rows.append(e)
    tie = lambda e: (str(e.name).casefold(), str(e.path).casefold(), str(e.key))
    if sort_by == "Name A to Z":
        return sorted(rows, key=tie)
    if sort_by == "Name Z to A":
        return sorted(rows, key=tie, reverse=True)
    if sort_by in ("Oldest evidence first", "Newest evidence first"):
        newest = sort_by == "Newest evidence first"
        return sorted(rows, key=lambda e: (
            type(e.age_days) is not int,
            (e.age_days if newest else -e.age_days)
            if type(e.age_days) is int else 0, tie(e)))
    if sort_by == "Smallest first":
        return sorted(rows, key=lambda e: (max(0, e.apparent_bytes), tie(e)))
    return sorted(rows, key=lambda e: (-max(0, e.apparent_bytes), tie(e)))
