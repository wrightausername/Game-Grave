"""Resurrection Kit v2: multi-folder preservation (optionally the whole game install) and no-overwrite restore.

The owner chooses every source (the Easy Setup flow only suggests them). Files are never deleted and programs are never
run. `restore_kit` always makes a fresh review folder. `restore_installation` (owner approved, 2026-11-10) puts the
installation into a NEW folder in a library the owner picks and returns saves, settings and load-order files to their
original place only where nothing exists yet. Nothing is ever overwritten. There is no size cap: the free-space check and
the owner's confirmation are the limit.
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

MAX_FILES = 5_000_000      # structural bound for listing a ZIP in memory, not a limit on a real game
MAX_BYTES = 1 << 62        # no practical size cap; free space is checked before anything is written
MAX_MANIFEST_BYTES = 1024 * 1024
MIN_SPACE_BUFFER = 64 * 1024**2
ROLE_NAMES = {"Saves", "Mods", "Profiles", "Configs", "Game", "LoadOrder", "Launcher"}
FILE_ROLES = {"LoadOrder", "Launcher"}          # given as explicit files, not a whole folder
AUTO_PLACE = {"Saves", "Configs", "LoadOrder"}  # returned to their original place when that place is free
ORIGIN_TOKENS = ("%LOCALAPPDATA%", "%APPDATA%", "%USERPROFILE%", "%DOCUMENTS%")
# Already compressed game data: storing it is much faster and the ZIP is no larger.
STORE_EXTENSIONS = {".bsa", ".ba2", ".pak", ".zip", ".7z", ".rar", ".mp4", ".webm", ".ogg", ".mp3", ".wem", ".png",
                    ".jpg", ".jpeg", ".bk2", ".bik", ".vpk", ".archive", ".utoc", ".ucas", ".cab", ".wav", ".dds"}
NAME_LIMIT = 180
DOS_NAMES = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
} | {
    # Windows also reserves COM¹, COM², COM³, LPT¹, LPT² and LPT³.
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in ("¹", "²", "³")
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


def _ordinary_ancestry(path: Path, *, directory=False) -> bool:
    """Reject a linked/reparse ancestor, not only a linked final component."""
    current = Path(path).absolute()
    first = True
    try:
        while True:
            if not _regular(current, directory=(directory if first else True)):
                return False
            parent = current.parent
            if parent == current:
                return True
            first = False
            current = parent
    except (OSError, ValueError, RuntimeError):
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
    if not _ordinary_ancestry(path):
        raise ValueError("Choose a manifest without linked or redirected parent folders.")
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
    if not _ordinary_ancestry(archive):
        raise ValueError("The backup ZIP is missing, linked or under an unsafe folder.")
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


def _sha256_ticked(file: Path, tick) -> str:
    """Same digest as _sha256, calling tick(bytes_read) so a long check can show progress or be cancelled."""
    digest = hashlib.sha256()
    with file.open("rb") as source:
        for chunk in iter(lambda: source.read(2**20), b""):
            digest.update(chunk)
            tick(len(chunk))
    return digest.hexdigest()


def _ticker(progress, cancel, phase, total, message="The check was cancelled. Nothing was changed."):
    """A tick(n) callable that reports at most five times a second and raises on cancel."""
    import time as _time
    state = {"done": 0, "last": 0.0}

    def tick(amount):
        state["done"] += amount
        now = _time.monotonic()
        if now - state["last"] > .2:
            state["last"] = now
            if cancel is not None and cancel():
                raise InterruptedError(message)
            if progress is not None:
                progress(phase, min(state["done"], total), total, "")
    return tick


def documents_dir(environ=None):
    """The real Documents folder. Windows can move it (OneDrive does), so ask Windows when no test environment is given."""
    if environ is None and os.name == "nt":
        try:
            import ctypes
            import uuid
            from ctypes import wintypes

            class _Guid(ctypes.Structure):
                _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]
            known = uuid.UUID("FDD39AD0-238F-46AF-ADB4-6C85480369C7")
            guid = _Guid(known.time_low, known.time_mid, known.time_hi_version, (ctypes.c_ubyte * 8)(*known.bytes[8:]))
            found = ctypes.c_wchar_p()
            call = ctypes.windll.shell32.SHGetKnownFolderPath
            call.argtypes = [ctypes.POINTER(_Guid), wintypes.DWORD, wintypes.HANDLE, ctypes.POINTER(ctypes.c_wchar_p)]
            call.restype = ctypes.c_long
            if call(ctypes.byref(guid), 0, None, ctypes.byref(found)) == 0 and found.value:
                value = found.value
                free = ctypes.windll.ole32.CoTaskMemFree
                free.argtypes = [ctypes.c_void_p]
                free(ctypes.cast(found, ctypes.c_void_p))
                if Path(value).is_absolute():
                    return Path(value)
        except Exception:
            pass
    env = os.environ if environ is None else environ
    return Path(env["USERPROFILE"]) / "Documents" if env.get("USERPROFILE") else None


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
        if info.file_size < 0:
            raise ValueError("Backup has an invalid file size.")
    if kinds.intersection(names):
        raise ValueError("ZIP has a file/directory collision.")
    return infos, total, sorted({parts[0] for info in infos
                                 for parts in [_valid_member(info, schema)]})


def inspect_restore(manifest_path: Path, parent: Path | None = None, *, progress=None, cancel=None) -> dict:
    """Read-only full checksum+CRC validation and safe restore preview."""
    manifest, archive_path = _manifest_for(manifest_path)
    watched = progress is not None or cancel is not None
    if watched:
        size = archive_path.stat().st_size
        digest = _sha256_ticked(archive_path, _ticker(progress, cancel, "Checking the kit (1 of 2)", size))
    else:
        digest = _sha256(archive_path)
    if digest.lower() != manifest["archive_sha256"].lower():
        raise ValueError("Backup checksum mismatch. Restore was not attempted.")
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            infos, total, roles = _scan_archive(archive, manifest["schema"])
            if len(infos) != manifest.get("files"):
                raise ValueError("Backup file count differs from its manifest.")
            tick = _ticker(progress, cancel, "Checking the kit (2 of 2)", total) if watched else None
            for info in infos:
                # ZIP CRC validation streams data through bounded chunks.
                with archive.open(info) as source:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        if tick is not None:
                            tick(len(chunk))
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
        "archive_sha256": manifest["archive_sha256"].lower(),
        "no_overwrite": True,
    }
    if parent is not None:
        parent = Path(parent)
        if not _ordinary_ancestry(parent, directory=True):
            raise ValueError("Choose a restore parent without linked or redirected folders.")
        target = parent / (_safe_label(outcome["game"]) + "_Restored")
        if target.exists() or target.is_symlink():
            raise FileExistsError("A restored folder with that name already exists. Choose another parent folder.")
        if shutil.disk_usage(parent).free < total + MIN_SPACE_BUFFER:
            raise OSError("Not enough free space for a conservative restoration.")
        outcome["target"] = str(target)
    return outcome


MAX_EMPTY_FOLDERS = 5000   # per kit part; a manifest stays small


def _clean_empty(values) -> list:
    """Empty-folder names from a manifest: plain relative paths only, anything else is dropped."""
    out = []
    for value in values if isinstance(values, list) else []:
        if len(out) >= MAX_EMPTY_FOLDERS:
            break
        try:
            if isinstance(value, str) and 0 < len(value) <= 400:
                out.append("/".join(_relative_name(value)))
        except ValueError:
            continue
    return out


def _safe_tree(source: Path, dest_zip: Path, empties: list | None = None):
    """Bounded preflight; never follow symlink/reparse directories or files. When `empties` is a list, the relative
    names of folders that hold nothing are added to it, so a restore can recreate them."""
    if not _ordinary_ancestry(source, directory=True):
        raise ValueError("Choose source folders without links or redirected ancestors.")
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
        if empties is not None and not folders and not files and directory != source \
                and len(empties) < MAX_EMPTY_FOLDERS:
            try:
                empties.append("/".join(_relative_name(directory.relative_to(source).as_posix())))
            except ValueError:
                pass
        for name in folders:
            if not _regular(directory / name, directory=True):
                raise ValueError("The folder contains a linked or unsupported folder (a link or junction), which a kit does not follow: "
                                 + str((directory / name).relative_to(source))[:160] + ". Nothing was backed up.")
        for name in files:
            path = directory / name
            if not _regular(path):
                raise ValueError("The folder contains a linked or unsupported file, which a kit does not follow: "
                                 + str(path.relative_to(source))[:160] + ". Nothing was backed up.")
            relative = path.relative_to(source).as_posix()
            try:
                _relative_name(relative)
            except ValueError:
                raise ValueError(f"A file name in the selected folder cannot be stored in a kit: {relative[:120]}") from None
            st = path.stat()
            rows.append((path, relative, st.st_size, st.st_mtime_ns))
            if len(rows) > MAX_FILES:
                raise ValueError(f"Selected folders hold more than {MAX_FILES:,} files.")
    if not rows:
        raise ValueError("No ordinary files were found in the selected folder.")
    return rows


def _publish_no_replace(temporary: Path, destination: Path) -> None:
    """Publish with an atomic no-overwrite hardlink, not replace-over-a-placeholder.

    This works on local NTFS and POSIX filesystems. On unsupported filesystems
    publishing fails closed instead of risking a time-of-check/use overwrite.
    """
    os.link(temporary, destination)
    temporary.unlink()


def _portable_manager_context(metadata: dict | None, roles) -> dict | None:
    """Only portable, reviewed identifiers, never local usernames or paths."""
    if metadata is None:
        return None
    if not isinstance(metadata, dict):
        raise ValueError("Manager hints must be a dictionary.")
    kind = metadata.get("kind")
    if kind not in ("MO2", "Vortex", "unknown"):
        raise ValueError("Unknown manager hint.")
    result = {"kind": kind, "auto_discovered": bool(metadata.get("auto_discovered"))}
    if kind == "MO2":
        profile = metadata.get("profile", "")
        if profile:
            if (not isinstance(profile, str) or not 1 <= len(profile) <= 140
                    or len(_relative_name(profile)) != 1):
                raise ValueError("MO2 profile label is not portable.")
        elif "Profiles" in roles:
            raise ValueError("MO2 profile name missing from restore metadata.")
        result["profile"] = profile
    return result


def _safe_files(files, dest_zip: Path):
    """Explicit single files (load order, launcher manifest). Same link refusal as folders; stored by file name."""
    rows, seen = [], set()
    for raw in files:
        path = Path(raw)
        if not _ordinary_ancestry(path):
            raise ValueError(f"{path.name} is a link or sits inside a linked folder, so it was not backed up.")
        try:
            _relative_name(path.name)
        except ValueError:
            raise ValueError(f"The file name {path.name[:80]} cannot be stored in a kit.") from None
        if path.name.casefold() in seen:
            raise ValueError("Two files with the same name were chosen for one kit part.")
        seen.add(path.name.casefold())
        st = path.stat()
        rows.append((path, path.name, st.st_size, st.st_mtime_ns))
    if not rows:
        raise ValueError("No files were chosen for this kit part.")
    return rows


def _clean_origin(origin):
    """Only a templated place such as %LOCALAPPDATA%\\Skyrim Special Edition. Never a path with a user name in it."""
    if origin in (None, ""):
        return None
    if (not isinstance(origin, str) or len(origin) > 300
            or not any(origin == t or origin.startswith(t + "\\") for t in ORIGIN_TOKENS)):
        raise ValueError("A kit part's original place must start with %LOCALAPPDATA%, %APPDATA%, %USERPROFILE% or %DOCUMENTS%.")
    rest = origin.split("\\")[1:]
    if any(part in ("", ".", "..") or any(c in part for c in '<>:"|?*/') for part in rest):
        raise ValueError("A kit part's original place is not a plain folder path.")
    return origin


def expand_origin(origin, environ=None):
    """Turn a templated origin into a path on THIS PC, or None when it cannot be done safely."""
    try:
        origin = _clean_origin(origin)
    except ValueError:
        return None
    if not origin:
        return None
    env = os.environ if environ is None else environ
    token, _, rest = origin.partition("\\")
    documents = documents_dir(environ)
    base = {"%LOCALAPPDATA%": env.get("LOCALAPPDATA"), "%APPDATA%": env.get("APPDATA"),
            "%USERPROFILE%": env.get("USERPROFILE"),
            "%DOCUMENTS%": str(documents) if documents else None}.get(token)
    if not base:
        return None
    path = Path(base)
    if not path.is_absolute():
        return None
    return path.joinpath(*rest.split("\\")) if rest else path


def _zip_info(archive_name: str, path: Path, modified_ns: int) -> zipfile.ZipInfo:
    import time as _time
    try:
        stamp = _time.localtime(modified_ns / 1e9)[:6]
        if stamp[0] < 1980:
            raise ValueError
    except (OverflowError, OSError, ValueError):
        stamp = (1980, 1, 1, 0, 0, 0)
    info = zipfile.ZipInfo(archive_name, stamp)
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    if path.suffix.lower() in STORE_EXTENSIONS:
        info.compress_type = zipfile.ZIP_STORED
    else:
        info.compress_type = zipfile.ZIP_DEFLATED
        info._compresslevel = 1
    return info


def create_complete_kit(game: str, sources: dict, destination: Path,
                        manager_context: dict | None = None, *, origins: dict | None = None,
                        progress=None, cancel=None) -> dict:
    """Back up explicitly chosen folders (and, for LoadOrder and Launcher, explicit files).

    `sources` maps a role to a folder, or to a list of files for the FILE_ROLES. The whole game install is the role
    "Game". There is no size cap. `progress(phase, done_bytes, total_bytes, note)` and `cancel()` are optional; a
    cancel removes everything this call wrote.
    """
    import time as _time
    if not isinstance(game, str) or not game.strip() or len(game) > 120:
        raise ValueError("Enter a short game name.")
    if not isinstance(sources, dict) or not 1 <= len(sources) <= len(ROLE_NAMES):
        raise ValueError("Select one or more folders.")
    if any(role not in ROLE_NAMES for role in sources):
        raise ValueError("Unknown backup folder type.")
    for role, raw in sources.items():
        listed = isinstance(raw, (list, tuple))
        if listed != (role in FILE_ROLES):
            raise ValueError(f"{role} must be " + ("a list of files." if role in FILE_ROLES else "a folder."))
    origins = {role: _clean_origin(value) for role, value in (origins or {}).items() if role in sources}
    manager_hint = _portable_manager_context(manager_context, sources)
    destination = Path(destination).absolute()
    if destination.suffix.lower() != ".zip":
        raise ValueError("Select a ZIP file destination.")
    sidecar = destination.with_name(destination.name + ".ggkit.json")
    partial = destination.with_name(destination.name + ".partial")
    partial_manifest = sidecar.with_name(sidecar.name + ".partial")
    if any(p.exists() or p.is_symlink() for p in
           (destination, sidecar, partial, partial_manifest)):
        raise FileExistsError("Kit output already exists; choose a new ZIP name.")
    if not _ordinary_ancestry(destination.parent, directory=True):
        raise ValueError("Choose a local destination without linked or redirected folders.")

    def report(phase, done=0, total=0, note=""):
        if progress is not None:
            progress(phase, done, total, note)

    def check_cancel():
        if cancel is not None and cancel():
            raise InterruptedError("Kit creation was cancelled. Nothing was kept.")

    captured, labels, overlap, hollow = {}, {}, [], {}
    report("Reading folders", 0, 0, "")
    for role, raw in sources.items():
        check_cancel()
        if role in FILE_ROLES:
            rows = _safe_files(raw, destination)
            captured[role] = (Path(rows[0][0]).parent, rows)
            labels[role] = Path(rows[0][0]).parent.name
            overlap.extend(Path(path).resolve(strict=True) for path, *_ in rows)
        else:
            root = Path(raw).expanduser()
            hollow[role] = []
            rows = _safe_tree(root, destination, hollow[role])
            captured[role] = (root, rows)
            labels[role] = root.name
            overlap.append(root.resolve(strict=True))
    for i, root in enumerate(overlap):
        for other in overlap[i+1:]:
            if root == other or root in other.parents or other in root.parents:
                raise ValueError("Kit source folders cannot overlap. The game install already contains its own mods folder.")
    count = sum(len(rows) for _, rows in captured.values())
    total = sum(size for _, rows in captured.values() for _, _, size, _ in rows)
    if count > MAX_FILES:
        raise ValueError(f"Kit holds more than {MAX_FILES:,} files.")
    if shutil.disk_usage(destination.parent).free < total + MIN_SPACE_BUFFER:
        raise OSError("Not enough free space to create the kit safely.")
    partial_owned = False
    manifest_owned = False
    try:
        done_bytes, last_tick = 0, 0.0
        with zipfile.ZipFile(partial, "x", compression=zipfile.ZIP_DEFLATED,
                             compresslevel=1, allowZip64=True) as archive:
            partial_owned = True
            for role, (_, entries) in captured.items():
                for path, rel, size, modified in entries:
                    check_cancel()
                    if not _ordinary_ancestry(path):
                        raise RuntimeError(f"Source or parent changed during backup: {path.name}")
                    old = path.stat()
                    if old.st_size != size or old.st_mtime_ns != modified:
                        raise RuntimeError(f"A file changed while the kit was being made (is the game running?): {path.name}")
                    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
                    fd = os.open(path, flags)
                    with os.fdopen(fd, "rb") as input_file:
                        actual = os.fstat(input_file.fileno())
                        if (not stat.S_ISREG(actual.st_mode)
                                or actual.st_size != size or actual.st_mtime_ns != modified):
                            raise RuntimeError(f"A file changed while the kit was being made (is the game running?): {path.name}")
                        info = _zip_info(f"{role}/{rel}", path, modified)
                        with archive.open(info, "w", force_zip64=True) as output:
                            while True:
                                chunk = input_file.read(1024 * 1024)
                                if not chunk:
                                    break
                                output.write(chunk)
                                done_bytes += len(chunk)
                                now = _time.monotonic()
                                if now - last_tick > .2:
                                    last_tick = now
                                    check_cancel()
                                    report("Copying", done_bytes, total, path.name)
                    if not _ordinary_ancestry(path) or path.stat().st_mtime_ns != modified:
                        raise RuntimeError(f"Source or parent changed during backup: {path.name}")
        check_cancel()
        report("Checking the ZIP", 0, total, "")
        cancelled = "Kit creation was cancelled. Nothing was kept."
        with zipfile.ZipFile(partial) as archive:
            infos, actual_total, roles = _scan_archive(archive, 2)
            if len(infos) != count or actual_total != total or len(roles) != len(captured):
                raise RuntimeError("Kit content count and size verification failed.")
            tick = _ticker(progress, cancel, "Checking the ZIP", total, cancelled)
            try:
                for info in infos:
                    with archive.open(info) as member:
                        while True:
                            chunk = member.read(1024 * 1024)
                            if not chunk:
                                break
                            tick(len(chunk))
            except (zipfile.BadZipFile, EOFError) as exc:
                raise RuntimeError("Kit failed ZIP CRC verification.") from exc
        check_cancel()
        packed = partial.stat().st_size
        report("Fingerprinting", 0, packed, "")
        fingerprint = _sha256_ticked(partial, _ticker(progress, cancel, "Fingerprinting", packed, cancelled))
        entries_out = []
        for role, (root, entries) in captured.items():
            item = {"name": role, "folder_label": labels[role], "files": len(entries)}
            if hollow.get(role):
                item["empty_folders"] = sorted(hollow[role])
            if origins.get(role):
                item["origin"] = origins[role]
            entries_out.append(item)
        manifest = {
            "schema": 2, "game": game.strip(),
            "archive": destination.name, "archive_sha256": fingerprint,
            "files": count, "source_bytes": total, "roles": entries_out,
            "includes_game_install": "Game" in captured,
            "automatic_game_repair": False,
            "note": ("Includes the whole game install folder, so a restore can run the game without downloading it again. "
                     "Launcher accounts and licences are not part of a kit." if "Game" in captured else
                     "Explicitly selected folders only. A kit does not automatically reinstall a game or activate mods."),
        }
        if manager_hint is not None:
            manifest["manager_context"] = manager_hint
        text = json.dumps(manifest, indent=2)
        if len(text.encode("utf-8")) > MAX_MANIFEST_BYTES // 2:
            # Thousands of empty folders: leave their names out so the manifest stays readable by every version.
            for item in entries_out:
                item.pop("empty_folders", None)
            text = json.dumps(manifest, indent=2)
        with partial_manifest.open("x", encoding="utf-8") as out:
            manifest_owned = True
            out.write(text)
        _publish_no_replace(partial, destination)
        try:
            _publish_no_replace(partial_manifest, sidecar)
        except BaseException:
            # Keep the already-published ZIP for manual inspection. Another
            # process could have changed the name, so never delete it blindly.
            raise RuntimeError("Kit ZIP was created, but the manifest could not be "
                               "published. Review the incomplete output manually.")
        report("Done", total, total, "")
        return {"archive": str(destination), "manifest": str(sidecar),
                "verified": True, "files": count, "bytes": total,
                "roles": [item["name"] for item in manifest["roles"]]}
    finally:
        # Only remove outputs we actually created. An intervening file
        # collision while opening with "x" must never delete its owner file.
        if partial_owned and _regular(partial):
            partial.unlink(missing_ok=True)
        if manifest_owned and _regular(partial_manifest):
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
        if (manifest["archive_sha256"].lower() != plan["archive_sha256"]
                or str(archive_path) != plan["archive"]):
            raise ValueError("Kit manifest or archive changed since approval preview.")
        with zipfile.ZipFile(archive_path) as archive:
            infos, _, _ = _scan_archive(archive, manifest["schema"])
            for info in infos:
                parts = _valid_member(info, manifest["schema"])
                destination = target.joinpath(*parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                if not _ordinary_ancestry(destination.parent, directory=True):
                    raise RuntimeError("Restore directory or ancestor changed; stopping.")
                flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
                descriptor = os.open(destination, flags, 0o600)
                # Own the fd before opening the ZIP member; even if ZIP
                # decompression fails the new staging file handle is closed.
                with os.fdopen(descriptor, "wb") as output, archive.open(info) as source:
                    shutil.copyfileobj(source, output, 1024 * 1024)
                if (not _ordinary_ancestry(destination) or
                        destination.stat().st_size != info.file_size):
                    raise RuntimeError("Restore file verification failed.")
        # CRC validates individual ZIP members, but the original SHA-256 proves
        # the exact reviewed backup did not mutate between preview and extraction.
        if _sha256(archive_path).lower() != plan["archive_sha256"]:
            raise ValueError("Resurrection Kit archive changed during restore; extracted files discarded.")
        return {"restored": True, "target": str(target), "files": plan["files"],
                "roles": plan["roles"], "no_overwrite": True,
                "note": "Files recovered to a new directory. Reconnect in the game/mod manager manually; no live installation was changed."}
    except BaseException:
        # Only remove this operation's new, private recovery directory on error.
        if _ordinary_ancestry(target, directory=True):
            shutil.rmtree(target)
        raise


# ------------------------------------------------------------------ whole-installation restore
def _folder_name(label) -> str:
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(label)).strip(" .")[:100]
    return clean or "Game"


def _usable_empty_or_new(path: Path) -> bool:
    """True when nothing is there to overwrite: the folder is absent, or exists and is empty, and its nearest
    existing ancestor is an ordinary folder."""
    try:
        if path.exists() or path.is_symlink():
            return _regular(path, directory=True) and not any(path.iterdir())
        ancestor = path.parent
        while not ancestor.exists():
            if ancestor.parent == ancestor:
                return False
            ancestor = ancestor.parent
        return _ordinary_ancestry(ancestor, directory=True)
    except OSError:
        return False


def plan_installation(manifest_path: Path, library_parent: Path, *, place_back: bool = True, environ=None) -> dict:
    """Read-only preview of where each part of a kit would be restored. It does not read the ZIP's contents.

    A part's `mode` is "new_folder" (the game install, a folder that must not exist yet), "place" (back to its original
    place, which is free), "place_files" (individual files, never over an existing file) or "review" (a fresh review
    folder next to the library). `blocked` lists reasons nothing can start.
    """
    manifest, archive_path = _manifest_for(manifest_path)
    parent = Path(library_parent)
    blocked = []
    if not _ordinary_ancestry(parent, directory=True):
        raise ValueError("Choose a library folder without linked or redirected folders.")
    game = str(manifest.get("game", "Unknown game"))[:120]
    listed = manifest.get("roles", [])
    metas = {r.get("name"): r for r in (listed if isinstance(listed, list) else []) if isinstance(r, dict)}
    if not metas:
        # Kits made before roles were recorded: read the ZIP's own list. They carry no original places, so every
        # part goes to the review folder.
        try:
            with zipfile.ZipFile(archive_path) as archive:
                _, _, found = _scan_archive(archive, manifest["schema"])
        except (zipfile.BadZipFile, EOFError, OSError) as exc:
            raise ValueError("The kit ZIP could not be read.") from exc
        metas = {role: {"name": role} for role in found}
    review = parent / (_safe_label(game) + "_Restored")
    parts, uses_review = [], False
    for role in sorted(metas, key=lambda r: ("Game", "Launcher", "Saves", "Configs", "LoadOrder", "Profiles", "Mods").index(r)
                       if r in ("Game", "Launcher", "Saves", "Configs", "LoadOrder", "Profiles", "Mods") else 99):
        if role not in ROLE_NAMES:
            continue
        meta = metas[role]
        label = _folder_name(meta.get("folder_label", role))
        part = {"role": role, "files": int(meta.get("files", 0) or 0), "folder_label": label,
                "empty_folders": _clean_empty(meta.get("empty_folders"))}
        if role == "Game":
            dest = parent / label
            part.update(mode="new_folder", destination=str(dest))
            if dest.exists() or dest.is_symlink():
                blocked.append(f"A folder named {label} already exists in this library. Choose another library folder.")
        elif role == "Launcher":
            steam = parent.name.casefold() == "common" and parent.parent.name.casefold() == "steamapps"
            if steam:
                part.update(mode="place_files", destination=str(parent.parent))
            else:
                part.update(mode="review", destination=str(review / role),
                            note="Only a Steam library folder (steamapps\\common) can use this file.")
                uses_review = True
        elif role in AUTO_PLACE and place_back:
            target = expand_origin(meta.get("origin"), environ)
            if target is None:
                part.update(mode="review", destination=str(review / role),
                            note="The kit does not record where this belongs on this PC.")
                uses_review = True
            elif role in FILE_ROLES:
                part.update(mode="place_files", destination=str(target))
            elif _usable_empty_or_new(target):
                part.update(mode="place", destination=str(target))
            else:
                part.update(mode="review", destination=str(review / role),
                            note="Files already exist in the original place, so nothing was put over them.")
                uses_review = True
        else:
            part.update(mode="review", destination=str(review / role))
            uses_review = True
        parts.append(part)
    if uses_review and (review.exists() or review.is_symlink()):
        blocked.append(f"A folder named {review.name} already exists in this library. Choose another library folder.")
    return {"game": game, "archive": str(archive_path), "parts": parts, "blocked": blocked,
            "review_folder": str(review) if uses_review else "", "includes_install": any(p["role"] == "Game" for p in parts),
            "bytes": int(manifest.get("source_bytes", 0) or 0), "files": int(manifest.get("files", 0) or 0)}


def restore_installation(manifest_path: Path, library_parent: Path, *, approved: bool = False,
                         place_back: bool = True, progress=None, cancel=None, environ=None) -> dict:
    """Restore a kit so the game can be launched: the install goes into a NEW folder in `library_parent`, the Steam
    manifest beside it, and saves, settings and load-order files back to where they came from, each only where nothing
    exists yet. Mod-manager folders go to a review folder. Nothing is overwritten, deleted or run. Any failure or cancel
    removes exactly what this call created."""
    import time as _time
    if approved is not True:
        raise PermissionError("Explicit user approval is required to restore a kit.")
    # Cheap refusals first, then the full SHA-256 and CRC check, all before anything is written.
    plan = plan_installation(manifest_path, library_parent, place_back=place_back, environ=environ)
    if plan["blocked"]:
        raise FileExistsError(plan["blocked"][0])
    verified = inspect_restore(manifest_path, progress=progress, cancel=cancel)
    manifest, archive_path = _manifest_for(manifest_path)
    if (manifest["archive_sha256"].lower() != verified["archive_sha256"] or str(archive_path) != verified["archive"]):
        raise ValueError("Kit manifest or archive changed since approval preview.")
    parent = Path(library_parent)
    where = {p["role"]: p for p in plan["parts"]}
    created_files, created_dirs = [], []

    def make_dirs(path: Path):
        missing = []
        probe = path
        while not probe.exists():
            missing.append(probe)
            if probe.parent == probe:
                break
            probe = probe.parent
        for folder in reversed(missing):
            folder.mkdir(mode=0o700)
            created_dirs.append(folder)

    def report(phase, done=0, total=0, note=""):
        if progress is not None:
            progress(phase, done, total, note)

    skipped, placed = [], {}
    total = verified["bytes"]
    done = 0
    last_tick = 0.0
    try:
        free_needed = total + MIN_SPACE_BUFFER
        if shutil.disk_usage(parent).free < free_needed:
            raise OSError("Not enough free space in this library for the whole kit.")
        with zipfile.ZipFile(archive_path) as archive:
            infos, _, _ = _scan_archive(archive, manifest["schema"])
            for info in infos:
                if cancel is not None and cancel():
                    raise InterruptedError("Restore was cancelled. Everything this restore wrote was removed.")
                parts = _valid_member(info, manifest["schema"])
                part = where.get(parts[0])
                if part is None:
                    continue
                destination = Path(part["destination"]).joinpath(*parts[1:])
                if part["mode"] == "place_files" and (destination.exists() or destination.is_symlink()):
                    skipped.append(destination.name)
                    continue
                make_dirs(destination.parent)
                if not _ordinary_ancestry(destination.parent, directory=True):
                    raise RuntimeError("Restore directory or ancestor changed; stopping.")
                flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
                descriptor = os.open(destination, flags, 0o600)
                created_files.append(destination)
                with os.fdopen(descriptor, "wb") as output, archive.open(info) as source:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)
                        done += len(chunk)
                        now = _time.monotonic()
                        if now - last_tick > .2:
                            last_tick = now
                            if cancel is not None and cancel():
                                raise InterruptedError("Restore was cancelled. Everything this restore wrote was removed.")
                            report("Restoring", done, total, destination.name)
                if (not _ordinary_ancestry(destination) or destination.stat().st_size != info.file_size):
                    raise RuntimeError("Restore file verification failed.")
                # Give the file back its recorded time. Older games order plugins by file time, and launchers
                # compare it when they check an install.
                try:
                    stamp = _time.mktime(tuple(info.date_time) + (0, 0, -1))
                    os.utime(destination, (stamp, stamp))
                except (OverflowError, OSError, ValueError):
                    pass
                placed[parts[0]] = placed.get(parts[0], 0) + 1
        # Folders that were empty when the kit was made (some games expect them to exist).
        for part in plan["parts"]:
            if part["mode"] == "place_files":
                continue
            for name in part.get("empty_folders", ()):
                folder = Path(part["destination"]).joinpath(*name.split("/"))
                if not folder.exists() and not folder.is_symlink():
                    make_dirs(folder)
        packed = archive_path.stat().st_size
        report("Final check", 0, packed, "")
        final = _sha256_ticked(archive_path, _ticker(progress, cancel, "Final check", packed,
                                                     "Restore was cancelled. Everything this restore wrote was removed."))
        if final.lower() != verified["archive_sha256"]:
            raise ValueError("Resurrection Kit archive changed during restore; extracted files discarded.")
        report("Done", total, total, "")
        return {"restored": True, "no_overwrite": True, "game": plan["game"], "files": len(created_files),
                "parts": [dict(p, restored=placed.get(p["role"], 0)) for p in plan["parts"]],
                "skipped_existing": skipped,
                "game_folder": where.get("Game", {}).get("destination", ""),
                "review_folder": plan["review_folder"],
                "note": ("The whole install was restored. Open your launcher (or the game's own exe) to start it. "
                         "Launcher accounts and licences are not part of a kit, so a launcher may sign in or re-verify first."
                         if "Game" in placed else
                         "This kit did not hold the game install, so only the parts listed were restored.")}
    except BaseException:
        for file in reversed(created_files):
            if _regular(file):
                file.unlink(missing_ok=True)
        for folder in reversed(created_dirs):
            try:
                folder.rmdir()
            except OSError:
                pass
        raise
