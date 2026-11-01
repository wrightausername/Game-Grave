"""Qt-independent read models. Presentation does not grant delete authority."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
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
        # A local executable or supporting installed-app registration does not
        # claim a second store license. It corroborates the source which owns
        # the original manifest, instead of creating false "ambiguous" status.
        supplemental = {"Custom library", "Local game files",
                        "Windows installed games"}
        primary = [r for r in rows if r.launcher not in supplemental]
        if len(primary) == 1 and all(
                r is primary[0] or r.launcher in supplemental
                or (r.launcher == "Rockstar Games"
                    and primary[0].launcher in ("Steam", "Epic Games"))
                for r in rows):
            main = primary[0]
            supporting = [r.launcher for r in rows if r is not main]
            output.append(replace(
                main, install_evidence=main.install_evidence +
                ("; corroborated by local " + ", ".join(sorted(set(supporting))) +
                 " evidence (not additional storefront ownership)"
                 if supporting else "")))
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


def graveyard_detail_text(entry, never_touch=()) -> str:
    """Plain-English, read-only item explanation for sidebar/modal/context menu.

    Never confuses review eligibility with deletion authorization.
    """
    from graveyard_protection import protection_action
    name = str(getattr(entry, "name", "Unknown finding"))
    category = str(getattr(entry, "category", "Unknown category"))
    path = str(getattr(entry, "path", "Unavailable"))
    size = readable_bytes(getattr(entry, "apparent_bytes", None))
    age = getattr(entry, "age_days", None)
    age_text = f"{age} days since modified/played" if type(age) is int else "Unknown"
    finding = str(getattr(entry, "finding", "") or "No detailed evidence available.")
    relationship = str(getattr(entry, "relationship", "") or "Not verified")
    protection = str(getattr(entry, "protection", "") or "Requires review")
    permitted = bool(getattr(entry, "can_recycle", False) and
                     getattr(entry, "old_file", None) is not None)
    action, reason = protection_action(path, list(never_touch))
    if category == "Old game screenshot":
        next_step = (
            "Preview this exact screenshot, then approve an individual Recycle Bin move "
            "if it is unprotected. Screenshots cannot be bulk deleted."
        )
    elif permitted:
        next_step = (
            "Review the file, then choose Move to Recycle Bin. Game Grave will "
            "request confirmation and verify Windows Recycle Bin recovery first."
        )
    elif action == "Unprotect":
        next_step = (
            "You added an exact Never Touch rule. Right-click and select Unprotect, "
            "then review this item again. Removing protection does not delete anything."
        )
    elif action is None and reason.startswith("A parent folder"):
        next_step = (
            "A parent Never Touch rule applies. Use Settings to review that rule. "
            "No folder or game content is force-deleted."
        )
    elif category == "Neglected installed game":
        next_step = (
            "This is a still-installed game. The launcher is the recommended "
            "way to uninstall it. If you intentionally want the folder removed, "
            "the Graveyard offers a one-time Advanced override with typed "
            "confirmation and verified Windows Recycle Bin safeguards."
        )
    elif getattr(entry, "old_file", None) is None:
        next_step = (
            "This is a folder or an unverified association, not an eligible individual "
            "file. Inspect it in its original game or mod manager first."
        )
    else:
        next_step = (
            "This item is protected or needs more evidence. No automatic deletion "
            "is available. Open its folder to inspect it."
        )
    return (
        f"ITEM\n{name}\n\nCATEGORY\n{category}\n\n"
        f"SIZE\n{size} apparent (not freed storage)\n\n"
        f"AGE\n{age_text}\n\n"
        f"LOCATION\n{path}\n\n"
        f"WHY GAME GRAVE FOUND IT\n{finding}\n\n"
        f"RELATIONSHIP TO YOUR GAMES\n{relationship}\n\n"
        f"PROTECTION\n{protection}\n{reason}\n\n"
        f"WHAT YOU CAN DO\n{next_step}\n\n"
        "SAFETY\nNo permanent deletion, and no unverified file is treated "
        "as disposable. Emptying Windows Recycle Bin is separate."
    )


def game_detail_text(game) -> str:
    """Display verified launcher facts without inventing sizes or play history."""
    from core import age_text
    last = getattr(game, "last_played_at", None)
    return (
        f"GAME\n{getattr(game, 'name', 'Unknown')}\n\n"
        f"LAUNCHER\n{getattr(game, 'launcher', 'Unknown')}\n\n"
        f"STORAGE\n{readable_bytes(getattr(game, 'size_bytes', None))} "
        f"({getattr(game, 'size_source', 'source unknown')})\n\n"
        f"LAST PLAYED\n{age_text(last) if last is not None else 'Unknown'}\n\n"
        f"INSTALL LOCATION\n{getattr(game, 'install_path', 'Unavailable')}\n\n"
        f"WHY GAME GRAVE FOUND IT\n"
        f"{getattr(game, 'install_evidence', 'Installation evidence unavailable')}\n\n"
        f"STATUS\n{getattr(game, 'status', 'Unknown')}\n\n"
        "WHAT YOU CAN DO\nInspect the installation folder, review Game DNA, "
        "or uninstall through the original launcher where supported. "
        "Game Grave will not directly delete installed game folders."
    )
