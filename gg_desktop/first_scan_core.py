"""Qt-free "Here's what Game Grave found": shown once, after the first full PC scan. The counts and the three suggested
next steps come only from what that scan found; each step opens a tab or tool that asks before changing anything."""
from __future__ import annotations

SEEN_KEY = "first_scan_summary_seen"


def counts(inventory):
    captures = len(getattr(inventory, "screenshots", []) or []) + len(getattr(inventory, "recordings", []) or [])
    return [("games", len(inventory.games)), ("mod locations", len(inventory.mods)), ("old files", len(inventory.files)),
            ("captures", captures), ("save folders", len(inventory.saves)), ("Graveyard findings", len(inventory.graveyard))]


def headline(inventory):
    shown = [f"{n:,} {name}" for name, n in counts(inventory) if n]
    return ("Found " + ", ".join(shown) + ".") if shown else "The scan finished but found nothing it recognises yet."


def _size(items):
    total = sum(int(getattr(i, "size", 0) or 0) for i in items)
    from core import human_size
    return human_size(total)


def next_steps(inventory, limit=3):
    """[(title, why, button words, target)], most useful first."""
    steps = []
    if inventory.mods:
        steps.append(("Check your mods", f"{len(inventory.mods):,} mod locations were found. My Mods shows problems, "
                      "updates and clashes in plain words.", "Open Mods", "tab:Mods"))
    if inventory.games:
        steps.append(("Back up a game you care about", "A Resurrection Kit keeps the whole install, saves and load order, "
                      "so a broken game can be put back.", "Set up a kit", "kit:easy"))
    if inventory.files:
        steps.append(("Review old files", f"{len(inventory.files):,} older files ({_size(inventory.files)}) in your scan "
                      "folder. Nothing is removed unless you choose it.", "Open Old Files", "tab:Old Files"))
    if inventory.graveyard:
        steps.append(("Look at leftovers", f"{len(inventory.graveyard):,} things that may belong to removed games. Review "
                      "only; each one says why it is listed.", "Open Graveyard", "tab:Graveyard"))
    steps.append(("Measure caches and logs", "Other Storage finds shader caches, logs and temp folders that games leave "
                  "behind.", "Open Other Storage", "tab:Other Storage"))
    steps.append(("Take the two-minute tour", "See what every tab is for.", "Start the tour", "tour"))
    return steps[:limit]


def should_show(settings, reference_preview=False, quick=False, enabled=True):
    return enabled and not reference_preview and not quick and settings.get(SEEN_KEY) is not True
