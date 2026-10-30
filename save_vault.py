"""User-directed, verified ZIP backups for saves and mod profiles.

Never deletes or overwrites source files. No background backup or cloud upload.
"""
from __future__ import annotations

import json
import os
import time
import zipfile
from pathlib import Path
from typing import Callable

MAX_FILES = 150_000
MAX_BYTES = 80 * 1024**3


def create_backup(source: Path, destination: Path, cancel: Callable[[], bool] | None = None) -> dict:
    source, destination = Path(source), Path(destination)
    if not source.is_dir() or source.is_symlink():
        raise ValueError("Select an existing, ordinary folder.")
    source = source.resolve(strict=True)
    destination = destination.absolute()
    if destination.suffix.lower() != '.zip':
        raise ValueError("Choose a ZIP archive destination.")
    if destination.exists():
        raise FileExistsError("A backup already exists there; choose a new filename.")
    if source == Path(source.anchor) or source == Path.home().resolve():
        raise ValueError("Choose the save/profile folder itself, not an entire drive or home folder.")
    if not destination.parent.is_dir():
        raise ValueError("Destination folder doesn't exist.")
    # Compare canonical directories, not a mix of .absolute() and .resolve().
    # Avoid Windows short-name, case and alias mismatches.
    dest_parent = destination.parent.resolve(strict=True)
    try:
        dest_parent.relative_to(source)
    except ValueError:
        pass
    else:
        raise ValueError("Save the ZIP outside the folder being backed up.")

    total = 0
    files = []
    for root, dirs, names in os.walk(source, followlinks=False):
        if cancel and cancel():
            raise InterruptedError('Backup canceled')
        here = Path(root)
        dirs[:] = [d for d in dirs if not (here / d).is_symlink()]
        for name in names:
            item = here / name
            if item.is_symlink() or not item.is_file():
                continue
            try:
                stat = item.stat()
            except OSError:
                continue
            total += stat.st_size
            files.append((item, stat.st_size))
            if len(files) > MAX_FILES or total > MAX_BYTES:
                raise ValueError('Backup exceeds safe processing limits (150,000 files or 80 GiB).')
    if not files:
        raise ValueError('No ordinary files found in the selected folder.')
    free = __import__('shutil').disk_usage(destination.parent).free
    if free < total + 64 * 1024**2:
        raise OSError('Not enough free space at the backup destination for a conservative preflight.')
    partial = destination.with_name(destination.name + '.partial')
    if partial.exists():
        raise FileExistsError("An incomplete archive with this name already exists; choose another name.")
    try:
        with zipfile.ZipFile(partial, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=3,
                             allowZip64=True) as archive:
            for item, original_size in files:
                if cancel and cancel():
                    raise InterruptedError('Backup canceled')
                if item.is_symlink() or not item.is_file() or item.stat().st_size != original_size:
                    raise RuntimeError(f'Source changed during backup: {item.name}')
                archive.write(item, item.relative_to(source).as_posix())
        with zipfile.ZipFile(partial, 'r') as archive:
            if archive.testzip() is not None:
                raise RuntimeError('ZIP CRC verification failed')
            if len(archive.namelist()) != len(files):
                raise RuntimeError('Backup file-count verification failed')
        partial.replace(destination)
        return {'source': str(source), 'destination': str(destination),
                'files': len(files), 'original_bytes': total,
                'archive_bytes': destination.stat().st_size,
                'verified': True, 'note': 'ZIP integrity verified. Close games before backup for consistent saves.'}
    except BaseException:
        try:
            partial.unlink(missing_ok=True)
        except OSError:
            pass
        raise
