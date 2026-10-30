"""Safe discovery and validation of Steam's *per-installed-game* shader cache.

This intentionally does not manipulate shared NVIDIA/AMD/Windows caches, game files,
Steam compatdata, Workshop downloads, or unknown game-created folders. Read-only until
an explicit, independently confirmed per-file Recycle Bin operation in the UI.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat

from core import SteamGame, read_vdf

MAX_FILES = 15000


@dataclass(frozen=True)
class ShaderFile:
    path: Path
    size: int
    mtime_ns: int
    inode: int
    device: int


@dataclass(frozen=True)
class ShaderCache:
    game: SteamGame
    directory: Path
    files: tuple[ShaderFile, ...]
    bytes_total: int
    skipped: int


def _normal_directory(directory: Path) -> bool:
    try:
        info = directory.lstat()
        # On Windows, junctions and mount points also carry FILE_ATTRIBUTE_REPARSE_POINT.
        return stat.S_ISDIR(info.st_mode) and not directory.is_symlink() and not (
            getattr(info, 'st_file_attributes', 0) & 0x400
        )
    except OSError:
        return False


def _normal_file(file: Path) -> bool:
    try:
        info = file.lstat()
        return stat.S_ISREG(info.st_mode) and not file.is_symlink() and not (
            getattr(info, 'st_file_attributes', 0) & 0x400
        ) and info.st_nlink == 1
    except OSError:
        return False


def _validated_location(game: SteamGame) -> Path | None:
    """Require matching installed Steam manifest, numeric ID, normal directories."""
    if not game.app_id.isdecimal() or not game.app_id or len(game.app_id) > 20:
        return None
    library = Path(game.library)
    apps = library / 'steamapps'
    manifest = apps / f'appmanifest_{game.app_id}.acf'
    root = apps / 'shadercache'
    folder = root / game.app_id
    if not all(map(_normal_directory, (library, apps, root, folder))):
        return None
    try:
        record = read_vdf(manifest).get('appstate', {})
        if not isinstance(record, dict) or str(record.get('appid')) != game.app_id:
            return None
        if int(record.get('stateflags', '0')) & 4 == 0:
            return None
        installdir = record.get('installdir')
        if not installdir or Path(installdir).name != installdir or installdir in ('.', '..'):
            return None
        if (apps / 'common' / installdir).resolve(strict=False) != Path(game.install_path).resolve(strict=False):
            return None
        if not _normal_directory(apps / 'common' / installdir):
            return None
        if not stat.S_ISREG(manifest.lstat().st_mode) or manifest.is_symlink():
            return None
    except (OSError, TypeError, ValueError):
        return None
    return folder


def inspect_steam_shader_cache(game: SteamGame) -> ShaderCache | None:
    folder = _validated_location(game)
    if folder is None:
        return None
    results: list[ShaderFile] = []
    skipped = 0
    # Refuse to descend into links/reparse points, even if they look like directories.
    for current, subdirs, filenames in os.walk(folder, topdown=True, followlinks=False):
        directory = Path(current)
        if not _normal_directory(directory):
            raise ValueError('Shader folder contains an unsafe directory.')
        safe_dirs = []
        for dirname in subdirs:
            candidate = directory / dirname
            if _normal_directory(candidate):
                safe_dirs.append(dirname)
            else:
                skipped += 1
        subdirs[:] = safe_dirs
        for filename in filenames:
            candidate = directory / filename
            if not _normal_file(candidate):
                skipped += 1
                continue
            info = candidate.lstat()
            results.append(ShaderFile(candidate, info.st_size, info.st_mtime_ns, info.st_ino, info.st_dev))
            if len(results) > MAX_FILES:
                raise ValueError('Too many cache files to verify safely. No files were removed.')
    return ShaderCache(game, folder, tuple(results), sum(f.size for f in results), skipped)


def file_still_matches(cache: ShaderCache, file: ShaderFile) -> bool:
    """Validate before recycling, including toctou-safe containment and original identity."""
    if _validated_location(cache.game) != cache.directory or not _normal_file(file.path):
        return False
    try:
        if not file.path.resolve(strict=True).is_relative_to(cache.directory.resolve(strict=True)):
            return False
        info = file.path.lstat()
        return (info.st_size == file.size and info.st_mtime_ns == file.mtime_ns and
                info.st_ino == file.inode and info.st_dev == file.device)
    except (OSError, ValueError):
        return False
