"""Resurrection Kit v2: optional multi-folder preservation and no-overwrite restore.

User chooses every source directory. Files are never deleted, programs are never
run, and restoration ALWAYS creates a fresh folder for review, not live game
directories. This is intentionally a safe bridge to later manager-aware restores.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import zipfile
from pathlib import Path

MAX_FILES = 40000
MAX_BYTES = 80 * 1024**3
MAX_MANIFEST_BYTES = 1024 * 1024
MIN_SPACE_BUFFER = 64 * 1024**2
ROLE_NAMES = {"Saves", "Mods", "Profiles", "Configs"}
NAME_LIMIT = 180
DOS_NAMES = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
}


def _regular(path: Path, directory: bool = False) -> bool:
    """Exclude symlinks, junctions and other reparse points even on Windows."""
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            return False
        return stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    except (OSError, ValueError):
        return False


def _relative_name(name: str) -> tuple[str, ...]:
    """Use strict portable Windows-safe ZIP names; don't normalize unsafe names."""
    if not isinstance(name, str) or not name or len(name) > 2048:
        raise ValueError("Invalid backup file name.")
    if name.startswith("/") or "\\" in name or "\x00" in name or ":" in name:
        raise ValueError("Unsafe or absolute ZIP path.")
    pieces = name.split("/")
    for part in pieces:
        if (part in ("", ".", "..") or len(part) > 255
                or part.endswith((" ", ".")) or
                any(ord(c) < 32 or c in '<>:"|?*' for c in part) or
                part.split(".", 1)[0].upper() in DOS_NAMES):
            raise ValueError("Unsafe ZIP file name.")
    return tuple(pieces)


def _safe_label(label: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9 _.-]+", "_", str(label)).strip(" ._")[:50]
    return clean or "Game"


def _manifest_for(path: Path) -> tuple[dict, Path]:
    path = Path(path)
    if not _regular(path):
        raise ValueError("Choose an ordinary Resurrection Kit manifest file.")
    if path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError("Resurrection Kit manifest exceeds size limit.")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("Resurrection Kit manifest could not be read.") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") not in (1, 2):
        raise ValueError("This Resurrection Kit version is not supported.")
    archive_name = manifest.get("archive")
    if (not isinstance(archive_name, str) or not archive_name.casefold().endswith(".zip")
            or Path(archive_name).name != archive_name
            or not _relative_name(archive_name) or "/" in archive_name):
        raise ValueError("The backup ZIP filename is invalid.")
    archive = path.parent / archive_name
    if not _regular(archive):
        raise ValueError("The backup ZIP is missing, linked or not an ordinary file.")
    checksum = manifest.get("archive_sha256", "")
    if (not isinstance(checksum, str) or
            re.fullmatch(r"[0-9a-fA-F]{64}", checksum) is None):
        raise ValueError("Backup checksum is missing or malformed.")
    return manifest, archive


def _sha256(file: Path) -> str:
    digest = hashlib.sha256()
    with file.open("rb") as source:
        for chunk in iter(lambda: source.read(2**20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_member(info: zipfile.ZipInfo, schema: int) -> tuple[str, ...]:
    # ZIP directory or symlink records are not needed for regular-file backups.
    if info.is_dir():
        raise ValueError("Unexpected directory record in backup ZIP.")
    attrs = info.external_attr >> 16
    if stat.S_ISLNK(attrs) or stat.S_ISDIR(attrs):
        raise ValueError("ZIP links and directory records cannot be restored.")
    parts = _relative_name(info.filename)
    if schema == 2:
        if parts[0] not in ROLE_NAMES or len(parts) < 2:
            raise ValueError("Backup member has an unknown storage role.")
        return parts
    # Legacy Kit 1.0 archived one selected save folder at ZIP root.
    return ("Saves",) + parts


def _scan_archive(archive: zipfile.ZipFile, schema: int):
    infos = archive.infolist()
    if not infos or len(infos) > MAX_FILES:
        raise ValueError("ZIP has no files or exceeds the restore entry cap.")
    names = set()
    kinds = set()
    total = 0
    for info in infos:
        parts = _valid_member(info, schema)
        canonical = "/".join(parts).casefold()
        if canonical in names:
            raise ValueError("ZIP contains duplicate or case-colliding file paths.")
        names.add(canonical)
        # No file may also be treated as a parent directory.
        for depth in range(1, len(parts)):
            parent = "/".join(parts[:depth]).casefold()
            kinds.add(parent)
        total += info.file_size
        if info.file_size < 0 or total > MAX_BYTES:
            raise ValueError("Backup exceeds the safe restore size cap.")
    if kinds.intersection(names):
        raise ValueError("ZIP has a file/directory collision.")
    return infos, total, sorted({parts[0] for info in infos
                                 for parts in [_valid_member(info, schema)]})


def inspect_restore(manifest_path: Path, parent: Path | None = None) -> dict:
    """Read-only full checksum+CRC validation and safe restore preview."""
    manifest, archive_path = _manifest_for(manifest_path)
    if _sha256(archive_path).lower() != manifest["archive_sha256"].lower():
        raise ValueError("Backup checksum mismatch. Restore was not attempted.")
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            infos, total, roles = _scan_archive(archive, manifest["schema"])
            if len(infos) != manifest.get("files"):
                raise ValueError("Backup file count differs from its manifest.")
            for info in infos:
                # ZIP CRC validation streams data through bounded chunks.
                with archive.open(info) as source:
                    while source.read(1024 * 1024):
                        pass
    except (zipfile.BadZipFile, EOFError, RuntimeError) as exc:
        raise ValueError("Backup failed ZIP integrity verification.") from exc
    outcome = {
        "verified": True,
        "game": str(manifest.get("game", "Unknown game"))[:120],
        "roles": roles,
        "files": len(infos),
        "bytes": total,
        "schema": manifest["schema"],
        "archive": str(archive_path),
        "no_overwrite": True,
    }
    if parent is not None:
        parent = Path(parent)
        if not _regular(parent, directory=True):
            raise ValueError("Choose an existing, ordinary restore parent directory.")
        target = parent / (_safe_label(outcome["game"]) + "_Restored")
        if target.exists() or target.is_symlink():
            raise FileExistsError("A restored folder with that name already exists. Choose another parent folder.")
        if shutil.disk_usage(parent).free < total + MIN_SPACE_BUFFER:
            raise OSError("Not enough free space for a conservative restoration.")
        outcome["target"] = str(target)
    return outcome


def _safe_tree(source: Path, dest_zip: Path):
    """Bounded preflight; never follow symlink/reparse directories or files."""
    if not _regular(source, directory=True):
        raise ValueError("Choose existing ordinary save/mod folders, not links or junctions.")
    source = source.resolve(strict=True)
    if source == Path(source.anchor) or source == Path.home().resolve():
        raise ValueError("A drive root or entire home folder cannot be preserved as a kit source.")
    if dest_zip.resolve(strict=False) == source or source in dest_zip.resolve(strict=False).parents:
        raise ValueError("Save the kit outside the directories being preserved.")
    rows = []
    def _walk_error(error):
        raise OSError("A selected folder could not be fully inspected; no backup was completed.") from error
    for here, folders, files in os.walk(source, topdown=True, followlinks=False,
                                        onerror=_walk_error):
        directory = Path(here)
        if any(not _regular(directory / name, directory=True) for name in folders):
            raise ValueError("Source contains linked or unsupported folders. Choose ordinary folders only; nothing was backed up.")
        for name in files:
            path = directory / name
            if not _regular(path):
                raise ValueError("Source contains linked or unsupported files. Choose ordinary folders only; nothing was backed up.")
            relative = path.relative_to(source).as_posix()
            _relative_name(relative)
            st = path.stat()
            rows.append((path, relative, st.st_size, st.st_mtime_ns))
            if len(rows) > MAX_FILES:
                raise ValueError("Selected folders exceed the maximum 40,000 files.")
    if not rows:
        raise ValueError("No ordinary files were found in the selected folder.")
    return rows


def _publish_no_replace(temporary: Path, destination: Path) -> None:
    """Reserve destination exclusively before replacing *our own* placeholder."""
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
    fd = os.open(destination, flags, 0o600)
    os.close(fd)
    try:
        temporary.replace(destination)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def create_complete_kit(game: str, sources: dict[str, Path], destination: Path) -> dict:
    """Backup 1-4 explicitly chosen folders. Does not assume all mods are included."""
    if not isinstance(game, str) or not game.strip() or len(game) > 120:
        raise ValueError("Enter a short game name.")
    if not isinstance(sources, dict) or not 1 <= len(sources) <= len(ROLE_NAMES):
        raise ValueError("Select one or more folders.")
    if any(role not in ROLE_NAMES for role in sources):
        raise ValueError("Unknown backup folder type.")
    destination = Path(destination).absolute()
    if destination.suffix.lower() != ".zip":
        raise ValueError("Select a ZIP file destination.")
    sidecar = destination.with_name(destination.name + ".ggkit.json")
    partial = destination.with_name(destination.name + ".partial")
    partial_manifest = sidecar.with_name(sidecar.name + ".partial")
    if any(p.exists() or p.is_symlink() for p in
           (destination, sidecar, partial, partial_manifest)):
        raise FileExistsError("Kit output already exists; choose a new ZIP name.")
    if not _regular(destination.parent, directory=True):
        raise ValueError("Choose a local, ordinary destination directory.")
    captured = {}
    folders = []
    for role, raw in sources.items():
        root = Path(raw).expanduser()
        captured[role] = (root, _safe_tree(root, destination))
        folders.append(root.resolve(strict=True))
    for i, root in enumerate(folders):
        for other in folders[i+1:]:
            if root == other or root in other.parents or other in root.parents:
                raise ValueError("Kit source folders cannot overlap.")
    count = sum(len(rows) for _, rows in captured.values())
    total = sum(size for _, rows in captured.values() for _, _, size, _ in rows)
    if count > MAX_FILES or total > MAX_BYTES:
        raise ValueError("Kit exceeds 40,000 files or 80 GiB.")
    if shutil.disk_usage(destination.parent).free < total + MIN_SPACE_BUFFER:
        raise OSError("Not enough free space to create the kit safely.")
    try:
        with zipfile.ZipFile(partial, "x", compression=zipfile.ZIP_DEFLATED,
                             compresslevel=3, allowZip64=True) as archive:
            for role, (_, entries) in captured.items():
                for path, rel, size, modified in entries:
                    if not _regular(path):
                        raise RuntimeError(f"Source changed during backup: {path.name}")
                    old = path.stat()
                    if old.st_size != size or old.st_mtime_ns != modified:
                        raise RuntimeError(f"Source changed during backup: {path.name}")
                    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
                    fd = os.open(path, flags)
                    with os.fdopen(fd, "rb") as input_file:
                        actual = os.fstat(input_file.fileno())
                        if (not stat.S_ISREG(actual.st_mode)
                                or actual.st_size != size or actual.st_mtime_ns != modified):
                            raise RuntimeError(f"Source changed during backup: {path.name}")
                        with archive.open(f"{role}/{rel}", "w", force_zip64=True) as output:
                            shutil.copyfileobj(input_file, output, 1024 * 1024)
                    if not _regular(path) or path.stat().st_mtime_ns != modified:
                        raise RuntimeError(f"Source changed during backup: {path.name}")
        with zipfile.ZipFile(partial) as archive:
            infos, actual_total, roles = _scan_archive(archive, 2)
            if len(infos) != count or actual_total != total or len(roles) != len(captured):
                raise RuntimeError("Kit content count and size verification failed.")
            if archive.testzip() is not None:
                raise RuntimeError("Kit failed ZIP CRC verification.")
        manifest = {
            "schema": 2, "game": game.strip(),
            "archive": destination.name, "archive_sha256": _sha256(partial),
            "files": count, "source_bytes": total, "roles": [
                {"name": role, "folder_label": root.name, "files": len(entries)}
                for role, (root, entries) in captured.items()
            ],
            "automatic_game_repair": False,
            "note": "Explicitly selected folders only. A kit does not automatically reinstall a game, enable mods or reconnect manager profiles.",
        }
        with partial_manifest.open("x", encoding="utf-8") as out:
            json.dump(manifest, out, indent=2)
        _publish_no_replace(partial, destination)
        try:
            _publish_no_replace(partial_manifest, sidecar)
        except BaseException:
            # Remove only the ZIP created by this attempt; never touch source files.
            destination.unlink(missing_ok=True)
            raise
        return {"archive": str(destination), "manifest": str(sidecar),
                "verified": True, "files": count, "bytes": total,
                "roles": [item["name"] for item in manifest["roles"]]}
    finally:
        partial.unlink(missing_ok=True)
        partial_manifest.unlink(missing_ok=True)


def restore_kit(manifest_path: Path, parent: Path, *, approved: bool = False) -> dict:
    """Only explicit approval, always into a new folder, never live game locations."""
    if approved is not True:
        raise PermissionError("Explicit user approval is required to restore a kit.")
    plan = inspect_restore(manifest_path, parent)
    target = Path(plan["target"])
    # mkdir(exist_ok=False) reserves destination without replacing an existing tree.
    target.mkdir(mode=0o700, exist_ok=False)
    try:
        manifest, archive_path = _manifest_for(manifest_path)
        with zipfile.ZipFile(archive_path) as archive:
            infos, _, _ = _scan_archive(archive, manifest["schema"])
            for info in infos:
                parts = _valid_member(info, manifest["schema"])
                destination = target.joinpath(*parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                if not _regular(destination.parent, directory=True):
                    raise RuntimeError("Restore directory changed; stopping.")
                with archive.open(info) as source:
                    with destination.open("xb") as output:
                        shutil.copyfileobj(source, output, 1024 * 1024)
                if destination.stat().st_size != info.file_size:
                    raise RuntimeError("Restore file-size verification failed.")
        return {"restored": True, "target": str(target), "files": plan["files"],
                "roles": plan["roles"], "no_overwrite": True,
                "note": "Files recovered to a new directory. Reconnect in the game/mod manager manually; no live installation was changed."}
    except BaseException:
        # Only remove this operation's new, private recovery directory on error.
        if _regular(target, directory=True):
            shutil.rmtree(target)
        raise
