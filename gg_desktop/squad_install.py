"""Squad Sync's install step: put a downloaded mod archive into Mod Organizer 2 as a NEW, switched-off mod folder.

Owner instruction (2026-11-11, checklist "one-push download all and install"). Pure logic and file writes, no Qt, no
network. It only handles what can be installed without choices:

  * .zip archives (read with Python itself; no outside program is run),
  * whose layout is plain game data: files such as .esp/.esm/.bsa or folders such as meshes/textures at the top, or the
    same inside one wrapper folder or inside a Data folder.

Anything else is left in Mod Organizer 2's Downloads for its own installer, with the reason in words: archives with a
FOMOD installer (they ask you to choose options), 7z and rar archives, and layouts this cannot recognise.

What it writes: one new folder `<mods>/<name>` and a small meta.ini in it so Mod Organizer 2 knows where the mod came
from. It never overwrites or changes an existing mod, never edits a profile or load order (Mod Organizer 2 lists the
new mod switched off), and a failure removes exactly what it created.
"""
from __future__ import annotations

import os
import re
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

MAX_FILES = 60_000
MAX_BYTES = 30 * 1024 ** 3
MAX_RATIO = 400                      # a zip that unpacks to more than 400x its size is refused
BAD_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
DATA_FILES = (".esp", ".esm", ".esl", ".bsa", ".ba2")
DATA_FOLDERS = {"meshes", "textures", "scripts", "interface", "sound", "music", "strings", "skse", "f4se", "nvse",
                "obse", "sfse", "fose", "seq", "shadersfx", "materials", "video", "grass", "lodsettings", "dialogueviews",
                "calientetools", "netscriptframework", "source", "tools", "facegen", "menus", "fonts", "distantlod",
                "trees", "shaders", "platform", "edit scripts", "mcm", "vis", "dyndolod", "lightplacer", "nemesis_engine"}


class InstallError(Exception):
    """A plain sentence for the person."""


@dataclass(frozen=True)
class Layout:
    ok: bool
    reason: str = ""                 # why it is left for Mod Organizer 2, when not ok
    root: tuple = ()                 # path parts to strip from every member
    files: int = 0
    size: int = 0


def clean_mod_name(name: str) -> str:
    """A folder name Windows accepts, or '' when the name cannot be used as it is."""
    name = str(name or "").strip()
    if not name or len(name) > 120 or BAD_NAME.search(name) or name.endswith((".", " ")) or name in (".", ".."):
        return ""
    if name.split(".")[0].casefold() in RESERVED:
        return ""
    return name


def _parts(member: str):
    """Safe relative parts of a zip member, or None when the name is unsafe."""
    if not member or member.startswith(("/", "\\")) or "\\" in member or ":" in member or "\0" in member:
        return None
    parts = tuple(p for p in PurePosixPath(member).parts)
    if not parts or any(p in ("", ".", "..") or BAD_NAME.search(p) or p.endswith((".", " "))
                        or p.split(".")[0].casefold() in RESERVED for p in parts):
        return None
    return parts


def _looks_like_data(names) -> bool:
    """`names` are the first parts of every member below a candidate root, with a flag for folders."""
    for name, is_folder in names:
        low = name.casefold()
        if is_folder and low in DATA_FOLDERS:
            return True
        if not is_folder and low.endswith(DATA_FILES):
            return True
    return False


def inspect(archive: Path) -> Layout:
    """Read-only: can this archive be installed without asking anything?"""
    archive = Path(archive)
    suffix = archive.suffix.casefold()
    if suffix in (".7z", ".rar"):
        return Layout(False, f"{suffix[1:]} archives are left for Mod Organizer 2 to install")
    if suffix != ".zip":
        return Layout(False, "not a zip archive")
    try:
        packed = archive.stat().st_size
        with zipfile.ZipFile(archive) as z:
            infos = z.infolist()
    except (OSError, zipfile.BadZipFile, EOFError):
        return Layout(False, "the archive could not be read")
    members, total = [], 0
    for info in infos:
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode):
            return Layout(False, "the archive holds links")
        if info.flag_bits & 0x1:
            return Layout(False, "the archive is password protected")
        if info.is_dir():
            continue
        parts = _parts(info.filename)
        if parts is None:
            return Layout(False, "the archive holds an unsafe file name")
        members.append(parts)
        total += info.file_size
    if not members:
        return Layout(False, "the archive is empty")
    if len(members) > MAX_FILES or total > MAX_BYTES or (packed and total > packed * MAX_RATIO):
        return Layout(False, "the archive is too large to install automatically")
    if any(part.casefold() == "fomod" for parts in members for part in parts[:3]):
        return Layout(False, "it has an installer with choices (FOMOD)")

    def below(root):
        seen = set()
        for parts in members:
            if parts[:len(root)] == root and len(parts) > len(root):
                seen.add((parts[len(root)], len(parts) > len(root) + 1))
        return seen

    def only_child(root):
        names = {name for name, _ in below(root)}
        folders = {name for name, is_folder in below(root) if is_folder}
        return next(iter(folders)) if len(names) == 1 and len(folders) == 1 else None

    root = ()
    for _ in range(3):                                   # top, one wrapper folder, then a Data folder inside it
        top = below(root)
        data = next((name for name, is_folder in top if is_folder and name.casefold() == "data"), None)
        if _looks_like_data(top):
            break
        if data is not None and _looks_like_data(below(root + (data,))):
            root = root + (data,)
            break
        child = only_child(root)
        if child is None:
            return Layout(False, "its folders are not laid out as plain game data")
        root = root + (child,)
    else:
        return Layout(False, "its folders are not laid out as plain game data")
    kept = [p for p in members if p[:len(root)] == root and len(p) > len(root)]
    lowered = set()
    for parts in kept:
        key = "/".join(parts[len(root):]).casefold()
        if key in lowered:
            return Layout(False, "two files in the archive would land on the same name")
        lowered.add(key)
    return Layout(True, "", root, len(kept), total)


def meta_text(nexus_ref: str, archive_name: str) -> str:
    """The meta.ini Mod Organizer 2 reads. Only the Nexus game and mod number Game Grave already holds."""
    game, _, mod_id = str(nexus_ref or "").partition("/")
    lines = ["[General]"]
    if re.fullmatch(r"[a-z0-9_]{1,40}", game or "") and mod_id.isdigit():
        lines += [f"gameName={game}", f"modid={mod_id}", "repository=Nexus"]
    lines += [f"installationFile={re.sub(r'[^ -~]', '_', archive_name)[:200]}",
              "comments=Installed by Game Grave Squad Sync. Switched off until you tick it."]
    return "\n".join(lines) + "\n"


def _plain_dir(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    return stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400


def install(archive: Path, mods_folder: Path, name: str, nexus_ref: str = "") -> dict:
    """Extract into the NEW folder `mods_folder/name`. Raises InstallError with a plain reason; on any failure the
    new folder is removed again. Returns {"folder", "files", "bytes"}."""
    archive, mods_folder = Path(archive), Path(mods_folder)
    clean = clean_mod_name(name)
    if not clean:
        raise InstallError("the mod's name cannot be used as a folder name")
    layout = inspect(archive)
    if not layout.ok:
        raise InstallError(layout.reason)
    if not _plain_dir(mods_folder):
        raise InstallError("Mod Organizer 2's mods folder is missing or is a link")
    target = mods_folder / clean
    if target.exists() or target.is_symlink():
        raise InstallError("a mod with that name is already installed, so nothing was changed")
    created_files, created_dirs = [], []

    def make(folder: Path):
        missing = []
        while not folder.exists():
            missing.append(folder)
            folder = folder.parent
        for item in reversed(missing):
            item.mkdir()
            created_dirs.append(item)

    try:
        os.mkdir(target)
        created_dirs.append(target)
        written = 0
        with zipfile.ZipFile(archive) as z:
            for info in z.infolist():
                if info.is_dir():
                    continue
                parts = _parts(info.filename)
                if parts is None or parts[:len(layout.root)] != layout.root or len(parts) <= len(layout.root):
                    continue
                destination = target.joinpath(*parts[len(layout.root):])
                make(destination.parent)
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
                handle = os.open(destination, flags, 0o644)
                created_files.append(destination)
                with os.fdopen(handle, "wb") as out, z.open(info) as source:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > layout.size + 1024:
                            raise InstallError("the archive unpacked larger than it said")
                        out.write(chunk)
        meta = target / "meta.ini"
        if not meta.exists():
            text = meta_text(nexus_ref, archive.name)
            created_files.append(meta)
            with open(meta, "x", encoding="utf-8", newline="\r\n") as out:
                out.write(text)
        return {"folder": str(target), "files": layout.files, "bytes": written}
    except BaseException as problem:
        for file in reversed(created_files):
            try:
                file.unlink()
            except OSError:
                pass
        for folder in reversed(created_dirs):
            try:
                folder.rmdir()
            except OSError:
                pass
        if isinstance(problem, InstallError):
            raise
        if isinstance(problem, (OSError, zipfile.BadZipFile, EOFError)):
            raise InstallError(f"it could not be unpacked ({type(problem).__name__})") from None
        raise


def mods_folder(instance: Path, ini_lines) -> Path:
    """The mods folder of a Mod Organizer 2 instance, honouring a custom mod_directory."""
    custom = next((l.split("=", 1)[1].strip() for l in ini_lines if l.casefold().startswith("mod_directory=")), "")
    return Path(custom.replace("%BASE_DIR%", str(instance))) if custom else Path(instance) / "mods"
