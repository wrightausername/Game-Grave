"""Explicit per-game cover override, saved only to Game Grave user cache.

For games with no source-verified Steam AppID, allow the player to choose a
real image themselves. Never search random image sites, invent matching game
identity, or copy artwork into an installed game or launcher directory.
"""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import shutil
import tempfile

_MAX_BYTES = 8 * 1024 * 1024
_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def override_dir() -> Path:
    appdata = os.environ.get("LOCALAPPDATA")
    root = Path(appdata) if appdata else Path.home() / ".cache"
    return root / "GameGrave" / "CustomGameCovers"


def _cover_id(game) -> str:
    # Distinguish same-title games in different launchers and locations.
    key = str(getattr(game, "key", ""))
    path = str(getattr(game, "install_path", ""))
    if not key or not path:
        return ""
    return sha256((key + "\n" + os.path.normcase(os.path.abspath(path))
                   ).encode("utf-8", errors="replace")).hexdigest()


def override_path(game) -> str:
    ident = _cover_id(game)
    if not ident:
        return ""
    for extension in (".jpg", ".png", ".webp"):
        result = override_dir() / (ident + extension)
        try:
            if (result.is_file() and not result.is_symlink()
                    and 1024 <= result.stat().st_size <= _MAX_BYTES):
                return str(result)
        except OSError:
            continue
    return ""


def _image_signature(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            head = handle.read(16)
    except OSError:
        return False
    return (head.startswith(b"\xff\xd8\xff")
            or head.startswith(b"\x89PNG\r\n\x1a\n")
            or (head[:4] == b"RIFF" and head[8:12] == b"WEBP"))


def choose_custom_cover(game, source: str) -> str:
    ident = _cover_id(game)
    if not ident:
        raise ValueError("Choose a verified game record first.")
    path = Path(source)
    try:
        if (not path.is_file() or path.is_symlink() or
                path.suffix.lower() not in _EXTENSIONS or
                not 1024 <= path.stat().st_size <= _MAX_BYTES or
                not _image_signature(path)):
            raise ValueError("Choose an existing JPG, PNG or WebP image under 8 MB.")
    except OSError as exc:
        raise ValueError("Selected cover is not readable.") from exc
    dest = override_dir()
    dest.mkdir(parents=True, exist_ok=True)
    extension = ".jpg" if path.suffix.lower() in (".jpg", ".jpeg") else path.suffix.lower()
    output = dest / (ident + extension)
    fd, tmp = tempfile.mkstemp(prefix=ident[:10], suffix=".tmp", dir=dest)
    try:
        with os.fdopen(fd, "wb") as target, path.open("rb") as reader:
            shutil.copyfileobj(reader, target, length=1024 * 1024)
        if not 1024 <= os.stat(tmp).st_size <= _MAX_BYTES:
            raise ValueError("Cover exceeded the size limit.")
        os.replace(tmp, output)
        for extension in (".jpg", ".png", ".webp"):
            other = dest / (ident + extension)
            if other != output:
                try:
                    other.unlink(missing_ok=True)
                except OSError:
                    pass
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return str(output)


def clear_custom_cover(game) -> bool:
    existing = override_path(game)
    if not existing:
        return False
    try:
        Path(existing).unlink()
        return True
    except OSError:
        return False
