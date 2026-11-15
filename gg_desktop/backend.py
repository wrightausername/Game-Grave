"""Reuses the existing Game Grave evidence and safety engines without Qt imports."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import Callable
import os

from core import (
    find_games, find_all_mod_storage, load_settings, save_settings, scan_old_files,
    safe_scan_root, is_protected_path, log_event, _has_reparse_component,
)
from launchers import find_launcher_games
from recordings import find_old_recordings
from screenshots import find_old_screenshots
from graveyard import build_graveyard
from graveyard_protection import set_item_protection
from gg_desktop.models import merge_games


@dataclass
class Inventory:
    steam: list = field(default_factory=list)
    other: list = field(default_factory=list)
    games: list = field(default_factory=list)
    mods: list = field(default_factory=list)
    files: list = field(default_factory=list)
    recordings: list = field(default_factory=list)
    screenshots: list = field(default_factory=list)
    saves: list = field(default_factory=list)
    graveyard: list = field(default_factory=list)
    scanned_at: str = ""
    warnings: list[str] = field(default_factory=list)
    source_reports: list = field(default_factory=list)
    file_scan_root: str = ""
    file_scan_days: int | None = None
    full_scanned_at: str = ""          # when everything was last scanned (a quick scan keeps the earlier time)
    quick_parts: tuple = ()            # the parts the newest scan covered, when it was a quick scan


STAGES = ("Steam and launchers", "Mod Radar", "Old files", "Game captures", "Protected saves")


class ScanCanceled(InterruptedError):
    pass


PARTS = ("games", "mods", "files", "captures", "saves")


def scan_inventory(settings: dict, canceled: Callable[[], bool],
                   progress: Callable[[int, str], None] | None = None,
                   parts=None, base: Inventory | None = None) -> Inventory:
    """Read-only scan, built off-thread; partial noncritical failures are explicit.

    `parts` (a subset of PARTS) rescans only those; everything else is carried over from `base`, the last accepted
    scan, unchanged. The Graveyard is always rebuilt from the result. None, or no base, scans everything."""
    wanted = set(PARTS) if parts is None or base is None else set(parts) & set(PARTS)
    order = [i for i, part in enumerate(PARTS) if part in wanted]

    def stage(i, name):
        if canceled():
            raise ScanCanceled("Scan canceled. The earlier accepted inventory is unchanged.")
        if progress and i in order:
            progress(int(order.index(i) * 100 / max(1, len(order))), name)
    staged = Inventory()
    if base is not None and wanted != set(PARTS):
        staged.warnings = [w for w in base.warnings]
    if "games" in wanted:
        stage(0, STAGES[0])
        staged.steam = find_games(list(settings.get("steam_extra_roots", [])), cancel=canceled)
        staged.other = find_launcher_games(list(settings.get("other_library_roots", [])), cancel=canceled)
        staged.games = merge_games(staged.steam, staged.other)
    else:
        staged.steam, staged.other, staged.games = list(base.steam), list(base.other), list(base.games)
    if "mods" in wanted:
        stage(1, STAGES[1])
        staged.mods = find_all_mod_storage(
            list(settings.get("steam_extra_roots", [])),
            list(settings.get("mod_extra_roots", [])),
            games=staged.steam, cancel=canceled,
        )
    else:
        staged.mods = list(base.mods)
    if "files" in wanted:
        stage(2, STAGES[2])
        staged.warnings = [w for w in staged.warnings if not w.startswith("Old Files folder")]
        try:
            staged.files = scan_old_files(Path(settings.get("scan_folder", str(Path.home() / "Downloads"))),
                                         int(settings.get("files_stale_days", 180)), cancel=canceled)
        except (ValueError, OSError) as exc:
            staged.warnings.append("Old Files folder unavailable (" + type(exc).__name__ + ").")
    else:
        staged.files = list(base.files)
        staged.file_scan_root, staged.file_scan_days = base.file_scan_root, base.file_scan_days
    if "captures" in wanted:
        stage(3, STAGES[3])
        staged.warnings = [w for w in staged.warnings if not w.startswith(("Recordings", "Screenshots"))]
        days = min(int(settings.get("files_stale_days", 180)),
                   int(settings.get("graveyard_days", 365)))
        try:
            staged.recordings = find_old_recordings(
                days, list(settings.get("recording_roots", [])), cancel=canceled)
        except (OSError, ValueError) as exc:
            staged.warnings.append("Recordings partially unavailable (" + type(exc).__name__ + ").")
        if canceled():
            raise ScanCanceled("Scan canceled.")
        try:
            staged.screenshots = find_old_screenshots(
                days, list(settings.get("screenshot_roots", [])),
                extra_steam_roots=list(settings.get("steam_extra_roots", [])), cancel=canceled)
        except (OSError, ValueError) as exc:
            staged.warnings.append("Screenshots partially unavailable (" + type(exc).__name__ + ").")
    else:
        staged.recordings, staged.screenshots = list(base.recordings), list(base.screenshots)
    excluded = settings.get("excluded_folders", [])
    if excluded:
        from gg_desktop.settings_rules import filter_inventory
        filter_inventory(staged, list(excluded))
    if "saves" in wanted:
        stage(4, STAGES[4])
        from save_discovery import discover_saves
        staged.saves = discover_saves()
    else:
        staged.saves = list(base.saves)
    staged.source_reports = list(getattr(base, "source_reports", []) or []) if base is not None and wanted != set(PARTS) else staged.source_reports
    if canceled():
        raise ScanCanceled("Scan canceled.")
    staged.graveyard = build_graveyard(
        staged.steam, staged.mods, staged.files,
        int(settings.get("graveyard_days", 365)),
        list(settings.get("never_touch", [])),
        watched_mods=list(settings.get("graveyard_watchlist", [])),
        recordings=staged.recordings, screenshots=staged.screenshots,
    )
    staged.scanned_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    if wanted == set(PARTS):
        staged.full_scanned_at, staged.quick_parts = staged.scanned_at, ()
    else:
        staged.full_scanned_at = base.full_scanned_at or base.scanned_at
        staged.quick_parts = tuple(p for p in PARTS if p in wanted)
    if progress:
        progress(100, "Scan finished")
    return staged


def refresh_graveyard(inventory: Inventory, settings: dict) -> None:
    inventory.graveyard = build_graveyard(
        inventory.steam, inventory.mods, inventory.files,
        int(settings.get("graveyard_days", 365)),
        list(settings.get("never_touch", [])),
        watched_mods=list(settings.get("graveyard_watchlist", [])),
        recordings=inventory.recordings, screenshots=inventory.screenshots,
    )


def unprotect_exact_personal_item(settings: dict, path: str) -> dict:
    """Remove one exact user Never Touch item. No cleanup is performed."""
    updated = dict(settings)
    updated["never_touch"] = set_item_protection(
        list(settings.get("never_touch", [])), path, protect=False)
    save_settings(updated)
    log_event("Protection removed", "Exact user Never Touch rule removed for manual review",
              path=path, source="Crimson Graveyard")
    return updated


def add_never_touch_path(settings: dict, path: str) -> dict:
    target = Path(path).expanduser().absolute()
    if (not safe_scan_root(target) or _has_reparse_component(target)
            or is_protected_path(target, [])):
        raise ValueError("Choose an ordinary folder outside built-in game, mod, save or system protection.")
    updated = dict(settings)
    updated["never_touch"] = [*list(settings.get("never_touch", [])), str(target)]
    save_settings(updated)
    return updated
