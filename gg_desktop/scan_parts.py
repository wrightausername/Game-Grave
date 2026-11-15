"""Faster rescans: which parts of the PC scan a tab needs. F5 on Games, Ready Room, Mods or Captures rescans only that
part and keeps the rest of the last scan; the Scan PC button and F5 elsewhere still scan everything. Right-click Scan PC
to pick a part. Reading only, like every scan."""
from __future__ import annotations

NAMES = {"games": "games", "mods": "mods", "files": "old files", "captures": "captures", "saves": "saves"}
FOR_ROUTE = {"Games": ("games",), "Ready Room": ("games",), "Mods": ("mods",), "Captures": ("captures",)}
MENU = (("Everything", None), ("Games only", ("games",)), ("Mods only", ("mods",)), ("Captures only", ("captures",)),
        ("Saves only", ("saves",)), ("Old files only", ("files",)))


def for_route(route, scanned):
    """The parts F5 rescans on this tab, or None for a full scan (also when nothing was scanned yet)."""
    return FOR_ROUTE.get(route) if scanned else None


def describe(parts):
    names = [NAMES[p] for p in ("games", "mods", "files", "captures", "saves") if p in set(parts or ())]
    return " and ".join(names) if names else "everything"
