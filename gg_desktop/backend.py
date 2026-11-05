"""Reuses the existing Game Grave evidence and safety engines without Qt imports."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import Callable
import os
import time

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
    file_scan_root: str = ""
    file_scan_days: int | None = None
    source_reports: list[dict] = field(default_factory=list)


STAGES = ("Steam and launchers", "Mod Radar", "Old files", "Game captures", "Protected saves")


class ScanCanceled(InterruptedError):
    pass


def scan_inventory(settings: dict, canceled: Callable[[], bool],
                   progress: Callable[[int, str], None] | None = None) -> Inventory:
    """Read-only scan with independent source failures and explicit coverage."""
    staged = Inventory()
    active = [0, "Starting", time.monotonic()]
    last_pulse = [0.0]

    def checkpoint():
        if canceled():
            raise ScanCanceled("Scan canceled. Earlier accepted inventory retained.")
        now = time.monotonic()
        if progress and now - last_pulse[0] >= .4:
            elapsed = int(now - active[2])
            progress(active[0], active[1] + (f" · {elapsed}s" if elapsed else ""))
            last_pulse[0] = now
        return False

    def stage(i, name):
        active[:] = [int(i * 100 / len(STAGES)), name, time.monotonic()]
        checkpoint()
        if progress:
            progress(active[0], name)

    def report(source, status, count, detail, paths=()):
        staged.source_reports.append({"source": source, "status": status, "count": count,
                                      "detail": detail, "paths": list(paths)})
        if status == "Unavailable":
            staged.warnings.append(source + ": " + detail)
        if progress:
            progress(active[0], f"{source}: {count} found" if status == "Checked" else source + ": " + status)

    def read(source, fn, paths=(), detail="Supported local metadata"):
        checkpoint()
        try:
            rows = fn()
        except InterruptedError:
            raise
        except (OSError, ValueError, RuntimeError) as exc:
            report(source, "Unavailable", 0, type(exc).__name__ + ": " + str(exc)[:180], paths)
            return []
        report(source, "Checked", len(rows), detail, paths)
        return rows

    stage(0, STAGES[0])
    from core import _steam_roots, steam_libraries
    roots = _steam_roots(list(settings.get("steam_extra_roots", [])))
    libraries = [str(p) for p in steam_libraries(roots)]
    staged.steam = read("Steam", lambda: find_games(list(settings.get("steam_extra_roots", [])), cancel=checkpoint),
                        libraries, "Steam manifests and existing install folders" if libraries else
                        "No Steam library was detected. Add the Steam or SteamLibrary folder in Scan Locations.")
    staged.other = read("Other launchers", lambda: find_launcher_games(
        list(settings.get("other_library_roots", [])), cancel=checkpoint, report=report),
        settings.get("other_library_roots", []))
    staged.games = merge_games(staged.steam, staged.other)
    stage(1, STAGES[1])
    staged.mods = read("Mod Radar", lambda: find_all_mod_storage(
        list(settings.get("steam_extra_roots", [])),
        list(settings.get("mod_extra_roots", [])),
        games=staged.steam, cancel=checkpoint), settings.get("mod_extra_roots", []),
        "Known game markers and supported manager locations; active state is not inferred")
    stage(2, STAGES[2])
    staged.file_scan_root = str(Path(settings.get("scan_folder", str(Path.home() / "Downloads"))))
    staged.file_scan_days = max(1, int(settings.get("files_stale_days", 180)))
    staged.files = read("Old Files", lambda: scan_old_files(
        Path(staged.file_scan_root), staged.file_scan_days, cancel=checkpoint),
        [staged.file_scan_root], f"Selected folder only; modified {staged.file_scan_days}+ days ago")
    stage(3, STAGES[3])
    days = min(int(settings.get("files_stale_days", 180)),
               int(settings.get("graveyard_days", 365)))
    days = max(1, days)
    staged.recordings = read("Recordings", lambda: find_old_recordings(
        days, list(settings.get("recording_roots", [])), cancel=checkpoint, include_recent=True),
        settings.get("recording_roots", []), "Known or selected capture locations, all ages; metadata only")
    staged.screenshots = read("Screenshots", lambda: find_old_screenshots(
        days, list(settings.get("screenshot_roots", [])),
        extra_steam_roots=list(settings.get("steam_extra_roots", [])), cancel=checkpoint, include_recent=True),
        settings.get("screenshot_roots", []), "Steam and known or selected capture locations, all ages; metadata only")
    stage(4, STAGES[4])
    from save_discovery import discover_saves
    staged.saves = read("Save locations", discover_saves, detail="Known save/profile locations; contents stay protected")
    checkpoint()
    staged.graveyard = build_graveyard(
        staged.steam, staged.mods, staged.files,
        int(settings.get("graveyard_days", 365)),
        list(settings.get("never_touch", [])),
        watched_mods=list(settings.get("graveyard_watchlist", [])),
        recordings=staged.recordings, screenshots=staged.screenshots,
    )
    staged.scanned_at = datetime.now().strftime("%Y-%m-%d %H:%M")
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
