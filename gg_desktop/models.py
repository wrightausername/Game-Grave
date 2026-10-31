"""Qt-independent read models. Presentation does not grant delete authority."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import os
from typing import Iterable


@dataclass(frozen=True)
class GameRecord:
    key: str
    name: str
    launcher: str
    app_id: str | None
    install_path: str
    install_evidence: str
    size_bytes: int | None
    size_source: str
    last_played_at: float | None
    last_played_source: str
    status: str
    capabilities: tuple[str, ...]
    claimed_by: tuple[str, ...] = ()


def _path_key(path: str) -> str:
    """Compare install locations without following untrusted links."""
    return os.path.normcase(os.path.abspath(os.fspath(path))).replace("/", "\\").casefold()


def merge_games(steam: Iterable, others: Iterable) -> list[GameRecord]:
    """One record per verified install path; never deduplicate by game title.

    A conflicting launcher claim becomes an explicit ambiguous owner, not a
    duplicate disk-space charge or evidence of uninstall availability.
    """
    sources: list[GameRecord] = []
    for g in steam:
        path = str(getattr(g, "install_path", "") or "")
        if not path:
            continue
        size = getattr(g, "size", None)
        size = int(size) if type(size) is int and size >= 0 else None
        sources.append(GameRecord(
            key="Steam:" + str(getattr(g, "app_id", "")) + ":" + _path_key(path),
            name=str(getattr(g, "name", "Unknown Steam game"))[:170],
            launcher="Steam", app_id=str(getattr(g, "app_id", "")),
            install_path=path,
            install_evidence="Steam appmanifest and existing installation directory",
            size_bytes=size, size_source="Steam manifest" if size is not None else "Unknown",
            last_played_at=getattr(g, "last_played", None),
            last_played_source=str(getattr(g, "source", "Unknown")),
            status="Installed (Steam record)", capabilities=("inspect", "open_folder", "steam_uninstall"),
            claimed_by=("Steam",),
        ))
    for g in others:
        path = str(getattr(g, "install_path", "") or "")
        if not path:
            continue
        launcher = str(getattr(g, "launcher", "Unknown launcher"))
        size = getattr(g, "reported_bytes", None)
        size = int(size) if type(size) is int and size >= 0 else None
        verified = launcher != "Custom library" and "not verified" not in str(getattr(g, "status", "")).casefold()
        sources.append(GameRecord(
            key=launcher + ":" + str(getattr(g, "app_id", "")) + ":" + _path_key(path),
            name=str(getattr(g, "name", "Unknown game"))[:170],
            launcher=launcher, app_id=str(getattr(g, "app_id", "")),
            install_path=path, install_evidence=str(getattr(g, "status", "")),
            size_bytes=size, size_source=("Launcher-reported" if size is not None else "Unknown"),
            last_played_at=None, last_played_source="Unknown",
            status="Installed (launcher evidence)" if verified else "Unverified folder",
            capabilities=("inspect", "open_folder") if verified else ("inspect",),
            claimed_by=(launcher,),
        ))
    groups: dict[str, list[GameRecord]] = {}
    for row in sources:
        groups.setdefault(_path_key(row.install_path), []).append(row)
    output = []
    for path, rows in groups.items():
        if len(rows) == 1:
            output.append(rows[0])
            continue
        claimed_by = tuple(sorted({p for row in rows for p in row.claimed_by}))
        # Different records from Steam plus the same launcher may describe one
        # legitimate install. Never decide ownership from app names alone.
        first = next((r for r in rows if r.launcher == "Steam"), rows[0])
        size_values = {r.size_bytes for r in rows if r.size_bytes is not None}
        size = first.size_bytes if len(size_values) == 1 else None
        output.append(GameRecord(
            key="shared:" + path, name=first.name,
            launcher=" / ".join(claimed_by),
            app_id=None, install_path=first.install_path,
            install_evidence="More than one launcher claims the same installation directory.",
            size_bytes=size,
            size_source=first.size_source if size is not None else "Conflicting or unknown",
            last_played_at=first.last_played_at,
            last_played_source=first.last_played_source,
            status="Ambiguous launcher ownership",
            capabilities=("inspect", "open_folder"), claimed_by=claimed_by,
        ))
    return sorted(output, key=lambda r: (r.name.casefold(), r.launcher.casefold(), r.key))


def unique_launcher_counts(games: Iterable[GameRecord]) -> dict[str, int]:
    counts: Counter = Counter()
    for game in games:
        # Count installations once, even when more than one launcher claims it.
        if len(game.claimed_by) == 1:
            counts[game.launcher] += 1
        else:
            counts["Multiple launchers"] += 1
    return dict(counts)


def reported_game_bytes(games: Iterable[GameRecord]) -> tuple[int, int]:
    """Known apparent/reported bytes and count with unknown sizes.

    Do NOT call these verified disk consumption or recovered space.
    """
    rows = tuple(games)
    return sum(g.size_bytes for g in rows if g.size_bytes is not None), sum(
        g.size_bytes is None for g in rows)


def graveyard_protection_decision(entry, never_touch: Iterable[str]) -> tuple[str, str]:
    """Returns presentation action, NOT permission to remove a source file."""
    from graveyard_protection import protection_action
    action, reason = protection_action(entry.path, list(never_touch))
    if action == "Unprotect":
        return "Unprotect this item", reason
    if action is None and reason.startswith("A parent folder"):
        return "Manage parent rule", reason
    if action is None:
        return "Why protected?", reason
    if entry.category == "Old game screenshot":
        return "Preview screenshot", "Images need individual user preview and approval."
    if entry.can_recycle:
        return "Move to Recycle Bin…", "Only after separate confirmation and safety rechecks."
    return "Review details", entry.finding


def readable_bytes(value: int | None) -> str:
    if value is None:
        return "Unknown"
    from core import human_size
    return human_size(max(0, int(value)))


def graveyard_totals(rows) -> dict[str, int]:
    """Counts are apparent and never falsely labeled disk space reclaimed."""
    entries = tuple(rows)
    return {
        "items": len(entries),
        "apparent_bytes": sum(max(0, e.apparent_bytes) for e in entries),
        "reviewable_items": sum(e.can_recycle for e in entries),
        "reviewable_bytes": sum(max(0, e.apparent_bytes) for e in entries if e.can_recycle),
        "protected_items": sum(not e.can_recycle for e in entries),
    }
