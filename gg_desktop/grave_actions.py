"""Graveyard selection checks and read-only helpers.

Removal itself stays in the existing verified Recycle Bin path (cleanup_actions.recycle_reviewed_entries through
the window's approval dialog), which re-checks each file, applies Never Touch rules and Windows' recovery proof,
and logs to Undo Center. Nothing here widens what that path accepts, deletes a folder or deletes permanently.
"""
from __future__ import annotations

from gg_desktop import grave_data as data
from gg_desktop import grave_insight as insight


def blockers(items, never_touch):
    """Reasons the selection cannot go to the engine. Empty list means it may be offered for confirmation."""
    reasons = []
    if not items:
        reasons.append("Nothing is checked.")
    if len(items) > insight.MAX_RECYCLE:
        reasons.append(f"Choose at most {insight.MAX_RECYCLE} files at a time.")
    for item in items:
        if data.is_protected(item, never_touch):
            reasons.append(f"{item.name}: protected by Game Grave or your Never Touch list")
        elif insight.needs_preview(item):
            reasons.append(f"{item.name}: screenshots need a preview of that exact image")
        elif not insight.recyclable(item):
            reasons.append(f"{item.name}: not an ordinary file this tab may remove")
    return reasons[:12]


def uninstall_url(item):
    """The steam:// address for a proven installed Steam game, otherwise None."""
    if item.tab == "Games" and item.app_id.isdecimal() and len(item.app_id) <= 12:
        return "steam://uninstall/" + item.app_id
    return None


def list_contents(path, limit=60):
    """Names directly inside a folder, read-only, never entering links. Returns (rows, truncated)."""
    import os
    import stat
    rows, truncated = [], False
    try:
        with os.scandir(path) as scan:
            for entry in scan:
                if len(rows) >= limit:
                    truncated = True
                    break
                try:
                    info = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                linked = entry.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & 0x400)
                kind = "link" if linked else "folder" if stat.S_ISDIR(info.st_mode) else "file"
                rows.append((entry.name, kind, 0 if kind != "file" else info.st_size))
    except OSError:
        return [], False
    rows.sort(key=lambda r: (r[1] != "folder", r[0].casefold()))
    return rows, truncated
