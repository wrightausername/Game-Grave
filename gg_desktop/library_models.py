"""Evidence-preserving presentation helpers for the reference library layouts."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gg_desktop.models import _path_key


def launcher_bucket(launcher):
    value = launcher.casefold()
    if " / " in value:
        return "Other"
    if value in {"ea", "ea app", "electronic arts", "origin"}:
        return "EA"
    for needle, name in (("steam", "Steam"), ("epic", "Epic"),
                         ("battle.net", "Battle.net"), ("blizzard", "Battle.net"),
                         ("ubisoft", "Ubisoft"), ("xbox", "Xbox (PC)"),
                         ("microsoft", "Xbox (PC)"), ("gog", "GOG")):
        if needle in value:
            return name
    return "Other"


def file_kind(path):
    suffix = Path(str(path)).suffix.casefold()
    if suffix in {".zip", ".rar", ".7z", ".gz", ".tar", ".bz2"}:
        return "Archives"
    if suffix in {".exe", ".msi", ".iso"}:
        return "Installers"
    if suffix in {".log", ".dmp", ".tmp"}:
        return "Logs / Crash Reports"
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mkv", ".avi"}:
        return "Media"
    return "Other"


@dataclass(frozen=True)
class ModView:
    record: object
    name: str
    game: str
    manager: str
    version: str
    evidence: str
    size: int | None


def mod_view(record, games) -> ModView:
    """Associate only a scanned path inside a detected game, never a title guess.

    The current scanner inventories storage locations, not an authoritative list
    of enabled mods, versions, conflicts or unused profiles. Keep those unknown.
    """
    path = _path_key(str(record.path))
    matches = [g for g in games if path == _path_key(g.install_path)
               or path.startswith(_path_key(g.install_path).rstrip("\\") + "\\")]
    game = max(matches, key=lambda g: len(g.install_path)).name if matches else "Unverified"
    source = str(getattr(record, "source", "Unknown"))
    manager = next((name for name in ("Vortex", "Mod Organizer 2", "Steam Workshop",
                                    "Thunderstore", "Minion", "CurseForge")
                    if name.casefold() in source.casefold()), source)
    return ModView(record, str(getattr(record, "name", "Mod storage")), game,
                   manager, "Unknown", str(getattr(record, "status", "Unknown")),
                   getattr(record, "apparent_bytes", None))


def old_file_rows(files, *, query="", kinds=(), days=0, sort="Size (Largest)", now=None):
    import time
    now = time.time() if now is None else now
    query = query.strip().casefold()
    kinds = set(kinds)
    rows = [f for f in files
            if (not query or query in str(f.path).casefold())
            and (not kinds or file_kind(f.path) in kinds)
            and (not days or f.modified <= now - days * 86400)]
    if sort == "Name (A–Z)":
        rows.sort(key=lambda f: (Path(f.path).name.casefold(), str(f.path)))
    elif sort == "Oldest Modified":
        rows.sort(key=lambda f: (f.modified, str(f.path)))
    elif sort == "Newest Modified":
        rows.sort(key=lambda f: (-f.modified, str(f.path)))
    else:
        rows.sort(key=lambda f: (-f.size, str(f.path)))
    return rows
