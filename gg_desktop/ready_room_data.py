"""Ready Room presentation: observed local records and official cached news.

News never establishes an installed version or mod compatibility. The live gauge
describes the displayed local checks, not a game's integrity or an overall score.
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
    url: str = ""
    timestamp: int = 0
    kind: str = "news"
    app_id: str = ""


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
    health_caption: str = "System Ready"
    health_note: str = "Game integrity and mod compatibility have not been verified."
    news_note: str = "Refresh public Steam news to connect Patch Watch."


def live_ready_room(inventory, *, disk_free_percent: float | None = None,
                    session_backups: int = 0, state=None, evidence=None) -> ReadyRoomData:
    """Only values supported by an accepted local inventory or OS disk reading."""
    scanned = bool(inventory.scanned_at)
    games = tuple(GamePulse(g.name, "— hrs", "Recorded install", "muted", "shield",
                            artwork=game_artwork(g.name), key=g.key)
                  for g in inventory.games)
    mod_count = str(len(inventory.mods)) if scanned else "—"
    storage = (("Storage available", "green") if disk_free_percent >= 10
               else ("Storage running low", "amber")) if disk_free_percent is not None else (
                   "Storage unavailable", "muted")
    result = ReadyRoomData(
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
    if state is None:
        return result
    from dataclasses import replace
    from gg_desktop.ready_room_services import backup_status, date_label, news_targets
    evidence = evidence or {}
    audit = evidence.get("audit", {})
    alerts = audit.get("unresolved_records", 0) + len(evidence.get("profiles", {}).get("warnings", []))
    kinds = {"hotfix": ("Hotfix", "amber", "wrench"),
             "update": ("Update", "cyan", "sync"), "mod": ("Mod Impact", "purple", "puzzle"),
             "maintenance": ("Maintenance", "amber", "calendar"),
             "release": ("Release News", "cyan", "download"), "news": ("News", "blue", "megaphone")}
    active = {steam_id for steam_id, _ in news_targets(inventory.games, state.get("followed", []))}
    patches = tuple(PatchNotice(n["game"], n["title"], date_label(n["timestamp"]),
                               *kinds.get(n["kind"], kinds["news"]), artwork=game_artwork(n["game"]),
                               url=n["url"], timestamp=n["timestamp"], kind=n["kind"], app_id=n["app_id"])
                    for n in state.get("news", []) if n["app_id"] in active)
    playtimes = evidence.get("playtimes", {})
    ordered = sorted(inventory.games, key=lambda g: (
        -playtimes.get(getattr(g, "app_id", ""), -1) if getattr(g, "launcher", "") == "Steam" else 1,
        -(g.last_played_at or 0), g.name.casefold()))
    games = []
    for game in ordered:
        steam_id = getattr(game, "app_id", "") if getattr(game, "launcher", "") == "Steam" else ""
        minutes = playtimes.get(steam_id)
        latest = next((p for p in patches if p.app_id == steam_id), None)
        status, tone, glyph = ("Recorded install", "muted", "shield")
        launcher = getattr(game, "launcher", "")
        if launcher and launcher != "Steam":
            status = "No official feed"
        if latest:
            status = {"update": "Patch news", "hotfix": "Hotfix news", "mod": "Mod news",
                      "maintenance": "Service news", "release": "Release news"}.get(latest.kind, "Game news")
            tone, glyph = latest.tone, latest.glyph
        hours = f"{minutes / 60:.1f}".rstrip("0").rstrip(".") + " hrs" if minutes is not None else "— hrs"
        games.append(GamePulse(game.name, hours,
                               status, tone, glyph, game_artwork(game.name), game.key))
    connected = bool(state.get("news_checked"))
    counts = (str(sum(p.kind in ("update", "hotfix", "mod") for p in patches)) if connected else "—",
              str(alerts) if evidence else "—",
              str(sum(p.kind == "maintenance" for p in patches)) if connected else "—",
              str(sum(p.kind == "release" for p in patches)) if connected else "—",
              str(len(state.get("followed", []))))
    available = [b for b in state.get("backups", []) if backup_status(b) == "Verified when created"]
    health = list(result.health)
    if evidence and scanned:
        total = len(inventory.games)
        health[1] = ((f"{total} install folders available", "green") if evidence["accessible_games"] == total
                     else ("Install folder missing", "amber")) if total else ("No game folders to check", "muted")
        health[2] = ("Scan sources available", "green") if not inventory.warnings else ("Partial scan: review warnings", "amber")
        managers = evidence["manager_count"]
        health[3] = (("Manager folders available", "green") if evidence["accessible_managers"] == managers
                     else ("Manager folder unavailable", "amber")) if managers else ("No managers detected", "muted")
    checked = sum(tone != "muted" for _, tone in health)
    passed = sum(tone == "green" for _, tone in health)
    return replace(result, patches=patches, games=tuple(games), counts=counts,
                   mod_state=("Needs Review" if alerts else "Reviewed") if evidence else result.mod_state,
                   mod_note=(f"{alerts} evidence warnings." if alerts else "No association warnings.") if evidence else result.mod_note,
                   mod_stats=((mod_count, "Mod locations"),
                              (str(audit.get("enabled_profile_references", 0) + audit.get("disabled_profile_references", 0)), "Profile references") if evidence else ("—", "Profile references"),
                              (str(alerts), "Review warnings") if evidence else ("—", "Review warnings")),
                   backup_title=f"{len(available)} Saved Backup" + ("s" if len(available) != 1 else ""),
                   backup_note=("Last backup: " + date_label(max(b["created_at"] for b in available))) if available else "Choose a save folder to back up.",
                   health=tuple(health), health_score=round(passed * 100 / checked) if evidence and scanned and checked else None,
                   health_caption="Local checks",
                   health_note=f"{passed} of {checked} available local checks passed. "
                               "Folder access is checked; game-file integrity, mod compatibility and running managers are not verified.",
                   news_note=("Cached official Steam posts; news is not an installed-version check." if connected else result.news_note))


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
