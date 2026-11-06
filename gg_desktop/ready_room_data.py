"""Ready Room presentation data, with explicit separation of fixtures and evidence.

The local inventory does not supply patch feeds, playtime totals, mod version
compatibility, a backup registry or an overall health score. Unknown stays unknown.
"""
from __future__ import annotations

from dataclasses import dataclass


def game_artwork(name: str) -> str:
    """Recognize decorative thumbnails only; titles never establish scan evidence."""
    title = "".join(c for c in name.casefold() if c.isalnum())
    return {
        "cyberpunk2077": "cyberpunk", "baldursgate3": "baldurs_gate",
        "thewitcher3": "witcher", "thewitcher3wildhunt": "witcher",
        "thewitcher3wildhuntgameoftheyearedition": "witcher",
        "starfield": "starfield", "skyrimse": "skyrim",
        "skyrimspecialedition": "skyrim",
        "theelderscrollsvskyrimspecialedition": "skyrim",
    }.get(title, "")


@dataclass(frozen=True)
class PatchNotice:
    game: str
    detail: str
    when: str
    status: str
    tone: str
    glyph: str
    artwork: str = ""


@dataclass(frozen=True)
class GamePulse:
    name: str
    hours: str
    status: str
    tone: str
    glyph: str
    artwork: str = ""
    key: str = ""


@dataclass(frozen=True)
class ReadyRoomData:
    counts: tuple[str, ...]
    patches: tuple[PatchNotice, ...] = ()
    games: tuple[GamePulse, ...] = ()
    mod_state: str = "Not scanned"
    mod_note: str = "Scan your local mod locations."
    mod_stats: tuple[tuple[str, str], ...] = (
        ("—", "Mod locations"), ("—", "Updates available"), ("—", "Compatibility checks"))
    backup_title: str = "Backup history unavailable"
    backup_note: str = "Choose a save folder to back up."
    health_score: int | None = None
    health: tuple[tuple[str, str], ...] = (
        ("Storage not checked", "muted"), ("Game files not verified", "muted"),
        ("Conflicts not checked", "muted"), ("Managers not checked", "muted"))
    reference: bool = False


def live_ready_room(inventory, *, disk_free_percent: float | None = None,
                    session_backups: int = 0) -> ReadyRoomData:
    """Only values supported by an accepted local inventory or OS disk reading."""
    scanned = bool(inventory.scanned_at)
    games = tuple(GamePulse(g.name, "— hrs", "Recorded install", "muted", "shield",
                            artwork=game_artwork(g.name), key=g.key)
                  for g in inventory.games)
    mod_count = str(len(inventory.mods)) if scanned else "—"
    storage = (("Storage available", "green") if disk_free_percent >= 10
               else ("Storage running low", "amber")) if disk_free_percent is not None else (
                   "Storage unavailable", "muted")
    return ReadyRoomData(
        counts=("—", "—", "—", "—", "—"),
        games=games,
        mod_state="Review mods" if scanned else "Not scanned",
        mod_note="Open Mod Radar for evidence." if scanned else "Scan your local mod locations.",
        mod_stats=((mod_count, "Mod locations"), ("—", "Updates available"),
                   ("—", "Compatibility checks")),
        backup_title=(f"{session_backups} Verified Backup" + ("s" if session_backups != 1 else "")
                      if session_backups else "Backup history unavailable"),
        backup_note="Created this session" if session_backups else "Choose a save folder to back up.",
        health=(storage, ("Game files not verified", "muted"),
                ("Partial scan: review warnings", "amber") if inventory.warnings else
                ("Conflicts not checked", "muted"), ("Managers not checked", "muted")),
    )


def reference_ready_room() -> ReadyRoomData:
    """The supplied design's sample values. Never mixed into Inventory or settings.

    Used only by the explicit --ready-room-reference switch and visual QA.
    """
    return ReadyRoomData(
        counts=("17", "6", "3", "2", "5"),
        patches=(
            PatchNotice("Cyberpunk 2077", "Patch 2.21 – Performance, fixes, and new content.",
                        "Today", "Major Update", "red", "download", "cyberpunk"),
            PatchNotice("Baldur’s Gate 3", "Hotfix #32 – Crash fixes and stability improvements.",
                        "Yesterday", "Hotfix", "amber", "wrench", "baldurs_gate"),
            PatchNotice("The Witcher 3: Wild Hunt", "Update 4.04 – Quest fixes and mod compatibility.",
                        "2 days ago", "Update", "cyan", "sync", "witcher"),
            PatchNotice("Starfield", "Patch 1.12.36 – General fixes and performance.",
                        "3 days ago", "Update", "cyan", "sync", "starfield"),
            PatchNotice("Skyrim Special Edition", "Creation Kit – Additional fixes and mod stability.",
                        "4 days ago", "Mod Impact", "purple", "puzzle", "skyrim"),
        ),
        games=(
            GamePulse("Cyberpunk 2077", "112 hrs", "Up to date", "green", "shield", "cyberpunk"),
            GamePulse("Baldur’s Gate 3", "98 hrs", "Hotfix Available", "amber", "wrench", "baldurs_gate"),
            GamePulse("The Witcher 3", "76 hrs", "Up to date", "green", "shield", "witcher"),
            GamePulse("Starfield", "54 hrs", "Up to date", "green", "shield", "starfield"),
            GamePulse("Skyrim SE", "48 hrs", "Mod Update", "purple", "wand", "skyrim"),
        ),
        mod_state="All Clear", mod_note="No critical mod issues detected.",
        mod_stats=(("342", "Installed Mods"), ("12", "Updates Available"),
                   ("3", "Compatibility Warnings")),
        backup_title="6 Games Backed Up", backup_note="Last backup: 2 hours ago",
        health_score=92,
        health=tuple((s, "green") for s in (
            "Storage Healthy", "Game Files Verified", "No Critical Conflicts", "Mod Managers Online")),
        reference=True,
    )
