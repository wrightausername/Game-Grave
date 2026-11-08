"""Excluded folders: keep results that live inside folders the owner excluded out of a scan.

This only removes entries from a freshly scanned inventory. It never touches a file, and saves are never
filtered, so protection and recovery always see everything they did before.
"""
from __future__ import annotations

import os

FILTERED = ("steam", "other", "games", "mods", "files", "recordings", "screenshots")


def _norm(path):
    return os.path.normcase(os.path.abspath(str(path)))


def inside(path, folders) -> bool:
    target = _norm(path)
    for folder in folders:
        base = _norm(folder)
        if target == base or target.startswith(base.rstrip(os.sep) + os.sep):
            return True
    return False


def item_path(item):
    value = getattr(item, "install_path", None) or getattr(item, "path", None)
    return value if isinstance(value, (str, os.PathLike)) and str(value) else None


def filter_inventory(inventory, folders) -> int:
    """Drop entries inside the excluded folders. Returns how many were left out."""
    folders = [f for f in folders if isinstance(f, str) and f]
    if not folders:
        return 0
    left_out = 0
    for name in FILTERED:
        items = getattr(inventory, name, None)
        if not isinstance(items, list):
            continue
        kept = []
        for item in items:
            path = item_path(item)
            if path is not None and inside(path, folders):
                left_out += 1
            else:
                kept.append(item)
        setattr(inventory, name, kept)
    return left_out
