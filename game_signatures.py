"""Read-only, bounded identification of game-specific executables.

A game-specific executable at an ordinary installation directory is positive
evidence that game files exist, *not* proof that a purchased license is present,
that the launcher owns it, or that the game is playable. Do not delete from it.

The catalog is purposefully small and exact. New signatures require a test and
an official/verified executable name. No recursive search and no file contents.
"""
from __future__ import annotations

from pathlib import Path

# Canonical title -> known case-insensitive executable path relative to a game
# install directory. Exact names only, no wildcard or fuzzy "game.exe".
GAME_EXECUTABLES = {
    "Red Dead Redemption 2": ("RDR2.exe", "PlayRDR2.exe"),
    "Grand Theft Auto V": ("GTA5.exe", "GTA5_Enhanced.exe"),
    "Grand Theft Auto IV": ("GTAIV.exe",),
    "L.A. Noire": ("LANoire.exe",),
    "Max Payne 3": ("MaxPayne3.exe",),
    "Cyberpunk 2077": ("bin/x64/Cyberpunk2077.exe",),
    "The Elder Scrolls V: Skyrim Special Edition": ("SkyrimSE.exe",),
    "Fallout 4": ("Fallout4.exe",),
    "Starfield": ("Starfield.exe",),
    "Elden Ring": ("Game/eldenring.exe",),
    "Baldur's Gate 3": ("bin/bg3.exe", "bin/bg3_dx11.exe"),
    "The Witcher 3": ("bin/x64/witcher3.exe", "bin/x64_dx12/witcher3.exe"),
    "Hogwarts Legacy": ("Phoenix/Binaries/Win64/HogwartsLegacy.exe",),
}

ROCKSTAR_TITLES = frozenset((
    "Red Dead Redemption 2", "Grand Theft Auto V",
    "Grand Theft Auto IV", "L.A. Noire", "Max Payne 3",
))


def _ordinary_file(path: Path) -> bool:
    """Do not traverse links or Windows reparse points, including parents."""
    try:
        current = path
        while True:
            info = current.lstat()
            if current.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
                return False
            if current.parent == current:
                break
            current = current.parent
        return path.is_file()
    except (OSError, ValueError):
        return False


def identify_game_install(folder: Path, *, only_rockstar=False):
    """Return (canonical_title, verified_executable_relative_path) or None.

    Never descends into arbitrary folders; only exact small candidate paths
    within the supplied known directory, which may be a user-chosen root.
    """
    try:
        if not folder.is_dir() or folder.is_symlink():
            return None
        for name, candidates in GAME_EXECUTABLES.items():
            if only_rockstar and name not in ROCKSTAR_TITLES:
                continue
            for relative in candidates:
                executable = folder.joinpath(*relative.split("/"))
                if _ordinary_file(executable):
                    return name, relative
    except (OSError, ValueError, TypeError):
        return None
    return None


def is_rockstar_title(name: str) -> bool:
    """A narrow name check for vendor registry subkeys, not an ownership claim."""
    normalized = " ".join(str(name).casefold().split())
    return any(normalized == title.casefold() for title in ROCKSTAR_TITLES)
