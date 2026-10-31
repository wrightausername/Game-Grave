"""Read-only, evidence-first Graveyard inventory for Game Grave.

Aging and a missing Steam manifest do not establish abandonment. Only individual
ordinary files from the explicitly chosen Old Files scan or discovered recording
folders are eligible for review. Entire games/mod folders are never recyclable here.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import time

from core import OldFile, ModFolder, SteamGame, is_game_neglected, is_protected_path
from screenshots import looks_like_screenshot

ARCHIVE_EXTENSIONS = frozenset({".zip", ".7z", ".rar", ".oiv", ".mrpack"})
GAME_HINTS = frozenset({
    "mod", "mods", "modpack", "addon", "addons", "plugin", "plugins", "repack",
    "shader", "shaders", "texture", "textures", "workshop", "vortex", "wabbajack",
    "fivem", "redm", "skyrim", "fallout", "cyberpunk", "minecraft", "nolvus",
    "bepinex", "reframework", "thunderstore", "tmodloader", "warcraft", "eso",
    "war thunder", "war_thunder", "starfield", "gta", "sims4", "sims 4",
    "minion", "curseforge", "modrinth", "r2modman", "reshade", "melonsloader",
})


@dataclass(frozen=True)
class GraveyardEntry:
    key: str
    name: str
    path: str
    category: str
    apparent_bytes: int
    age_days: int | None
    relationship: str
    finding: str
    protection: str
    can_recycle: bool
    old_file: OldFile | None = None
    screenshot_reviewed: bool = False


def looks_like_game_archive(path: Path) -> bool:
    """Narrow heuristic. Results are *possible* game downloads, not proven mods."""
    if path.suffix.casefold() not in ARCHIVE_EXTENSIONS:
        return False
    if path.suffix.casefold() in {".oiv", ".mrpack"}:
        return True
    tokens = {v for v in re.split(r"[^a-z0-9]+", path.stem.casefold()) if v}
    text = path.stem.casefold()
    return bool(tokens & GAME_HINTS or any(term in text for term in GAME_HINTS if len(term) >= 5))


def build_graveyard(games: list[SteamGame], mods: list[ModFolder], old_files: list[OldFile],
                    min_days: int = 365, never_touch: list[str] | None = None,
                    now: float | None = None, watched_mods: list[str] | None = None,
                    recordings: list[OldFile] | None = None,
                    screenshots: list[OldFile] | None = None) -> list[GraveyardEntry]:
    """Create an evidence-led snapshot. Does NOT change any file on disk."""
    if min_days < 1:
        raise ValueError("Choose a positive age threshold")
    now = time.time() if now is None else now
    results: list[GraveyardEntry] = []
    watched = {str(Path(x)).casefold() for x in (watched_mods or []) if isinstance(x, str)}
    seen: set[str] = set()
    for f in old_files:
        path = Path(f.path)
        age = max(0, int((now - f.modified) / 86400))
        if age < min_days or looks_like_screenshot(path):
            # Images are never promoted through generic old-file review.
            continue
        key = str(path).casefold()
        if key in seen:
            continue
        seen.add(key)
        protected = is_protected_path(path, never_touch)
        gaming_hint = looks_like_game_archive(path)
        results.append(GraveyardEntry(
            key=f"file:{key}", name=path.name, path=str(path),
            category=("Possible mod / game download" if gaming_hint
                      else "Old file from reviewed folder"),
            apparent_bytes=max(0, f.size),
            age_days=age, relationship="Game association unverified",
            finding=(
                f"Filename resembles gaming content; last modified {age} days ago. "
                "Usage is unknown." if gaming_hint else
                f"Found in your explicitly chosen Old Files scan folder; "
                f"last modified {age} days ago. It may be personal or important. "
                "Review its contents before recycling. No game association is claimed."
            ),
            protection="Never Touch / managed game location" if protected else "User review required",
            can_recycle=not protected, old_file=f,
        ))
    for f in recordings or []:
        path = Path(f.path)
        if path.suffix.casefold() not in {".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".wmv"}:
            continue
        age = max(0, int((now - f.modified) / 86400))
        if age < min_days:
            continue
        key = str(path).casefold()
        if key in seen:
            continue
        seen.add(key)
        protected = is_protected_path(path, never_touch)
        results.append(GraveyardEntry(
            key=f"recording:{key}", name=path.name, path=str(path),
            category="Old game recording", apparent_bytes=max(0, f.size),
            age_days=age, relationship="Possible capture; not content-verified",
            finding=(f"Recording-folder or filename hint; modified {age} days ago. "
                     "This might be a personal video. Preview it before deletion."),
            protection="Never Touch / protected location" if protected else "Review before deleting",
            can_recycle=not protected, old_file=f,
        ))
    for f in screenshots or []:
        path = Path(f.path)
        if not looks_like_screenshot(path):
            continue
        age = max(0, int((now - f.modified) / 86400))
        if age < min_days:
            continue
        key = str(path).casefold()
        if key in seen:
            continue
        seen.add(key)
        protected = is_protected_path(path, never_touch)
        results.append(GraveyardEntry(
            key=f"screenshot:{key}", name=path.name, path=str(path),
            category="Old game screenshot", apparent_bytes=max(0, f.size),
            age_days=age, relationship="Possible game capture; contents not verified",
            finding=(f"Screenshot location and image extension; modified {age} days ago. "
                     "This may be a treasured screenshot or personal image. "
                     "Preview THIS image before choosing an individual Recycle Bin action."),
            protection=("Never Touch / protected location" if protected else
                        "Preview required; bulk cleanup disabled"),
            can_recycle=False, old_file=f,
        ))
    for g in games:
        if not is_game_neglected(g, min_days, now):
            continue
        age = max(0, int((now - (g.last_played or now)) / 86400))
        results.append(GraveyardEntry(
            key=f"steam:{g.app_id}", name=g.name, path=g.install_path,
            category="Neglected installed game", apparent_bytes=max(0, g.size),
            age_days=age, relationship="Steam game is still installed",
            finding=f"Steam last-play record is {age} days old ({g.source}).",
            protection="Protected; uninstall only through Steam", can_recycle=False,
        ))
    for m in mods:
        path = Path(m.path)
        try:
            modified = path.stat().st_mtime
        except OSError:
            continue
        age = max(0, int((now - modified) / 86400))
        marked = str(path).casefold() in watched
        if age < min_days and not marked:
            continue
        key = str(path).casefold()
        if key in seen:
            continue
        seen.add(key)
        active = any(s in m.status.casefold() for s in (
            "installed", "managed", "profile", "save", "world", "associated game",
        ))
        results.append(GraveyardEntry(
            key=f"mod:{key}", name=m.name, path=str(path),
            category=m.source, apparent_bytes=max(0, m.apparent_bytes),
            age_days=age, relationship=m.status,
            finding=(("Manually sent here for review. " if marked else "") +
                     f"Folder modified {age} days ago. {m.advice} "
                     "Folder age does not establish last use or orphan status."),
            protection="Active/managed: protected" if active else "Uncertain: review in manager",
            can_recycle=False,
        ))
    return sorted(results, key=lambda e: (not e.can_recycle, -e.apparent_bytes, e.name.casefold()))
