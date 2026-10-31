"""Explicit, integrity-verified Game Grave installer download. Never executes setup.

Only after the user approves a release already authenticated by updates.py.
Fail closed on redirects, wrong host, wrong byte count, bad SHA-256, linked
destinations and cancellation. The signed update manifest is not a Windows
Authenticode certificate: users must verify Windows publisher trust before
manually installing.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from core import _has_reparse_component, is_protected_path, safe_scan_root
from updates import (
    MAX_INSTALLER_BYTES, UpdateError, VerifiedRelease, _NoRedirect, _https_url,
)

CHUNK = 1024 * 1024


def download_verified_installer(
    release: VerifiedRelease,
    destination: Path,
    *,
    download_host: str,
    approved: bool = False,
    opener=None,
    canceled: Callable[[], bool] | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> dict:
    """Save exact signed-manifest installer bytes to a NEW local .exe file.

    Uses an exclusive random temporary file and atomic no-overwrite hardlink
    publication on the same local volume. Does not modify a current Game Grave
    installation or auto-run the downloaded executable.
    """
    if approved is not True:
        raise PermissionError("You must explicitly approve the exact update download.")
    if not isinstance(release, VerifiedRelease):
        raise UpdateError("Choose a previously verified signed stable release.")
    url = _https_url(release.download_url, host=download_host)
    if release.channel != "stable" or not url.lower().endswith(".exe"):
        raise UpdateError("This is not an approved stable installer URL.")
    if (type(release.size_bytes) is not int or
            not 0 < release.size_bytes <= MAX_INSTALLER_BYTES):
        raise UpdateError("Invalid signed installer size.")
    expected = release.installer_sha256
    if (not isinstance(expected, str) or len(expected) != 64 or
            any(c not in "0123456789abcdef" for c in expected)):
        raise UpdateError("Installer checksum was not verified.")

    target = Path(destination).expanduser().absolute()
    parent = target.parent
    if (target.suffix.casefold() != ".exe" or not safe_scan_root(parent) or
            _has_reparse_component(parent) or is_protected_path(target)):
        raise UpdateError("Choose an ordinary unprotected local folder for the installer.")
    if target.exists() or target.is_symlink():
        raise FileExistsError("Installer filename already exists; choose a new name.")
    if canceled and canceled():
        raise InterruptedError("Update download canceled before starting.")

    request = urllib.request.Request(url, headers={
        "User-Agent": "GameGrave-Verified-Update/1",
        "Accept": "application/octet-stream",
    }, method="GET")
    stream = opener or urllib.request.build_opener(_NoRedirect()).open
    owned = None
    published = False
    owned_identity = None
    try:
        fd, raw = tempfile.mkstemp(prefix=".gg-update-", suffix=".partial", dir=parent)
        owned = Path(raw)
        with os.fdopen(fd, "wb") as sink:
            state = os.fstat(sink.fileno())
            owned_identity = (state.st_dev, state.st_ino)
            digest = hashlib.sha256()
            total = 0
            try:
                response = stream(request, timeout=30)
                with response as remote:
                    actual_url = remote.geturl() if hasattr(remote, "geturl") else url
                    if actual_url != url:
                        raise UpdateError("Update provider redirected the signed download URL.")
                    while True:
                        if canceled and canceled():
                            raise InterruptedError("Update download canceled.")
                        block = remote.read(min(CHUNK, release.size_bytes - total + 1))
                        if not block:
                            break
                        total += len(block)
                        if total > release.size_bytes:
                            raise UpdateError("Update download exceeded signed size.")
                        digest.update(block)
                        sink.write(block)
                        if progress and (total == release.size_bytes or total % (8 * CHUNK) == 0):
                            progress(total, release.size_bytes)
            except (OSError, urllib.error.URLError, TimeoutError) as exc:
                raise UpdateError("Could not securely download the stable update.") from exc
            sink.flush()
            os.fsync(sink.fileno())
            final_state = os.fstat(sink.fileno())
            if (final_state.st_dev, final_state.st_ino) != owned_identity:
                raise UpdateError("Update staging file changed during download.")
        if total != release.size_bytes or digest.hexdigest() != expected:
            raise UpdateError("Downloaded installer does not match its signed SHA-256 and size.")
        if (_has_reparse_component(parent) or
                target.exists() or target.is_symlink()):
            raise UpdateError("Installer output folder changed during verification.")
        state = owned.stat()
        if (state.st_dev, state.st_ino) != owned_identity:
            raise UpdateError("Update staging file identity changed.")
        # Close-then-publish with an atomic no-overwrite operation.
        os.link(owned, target)
        published = True
        # Verify the exact published bytes one more time after linking.
        digest2 = hashlib.sha256()
        with target.open("rb") as verify:
            for block in iter(lambda: verify.read(CHUNK), b""):
                digest2.update(block)
        if (target.stat().st_size != total or
                digest2.hexdigest() != expected):
            raise UpdateError("Published installer failed final SHA-256 check.")
        return {
            "saved_path": str(target),
            "bytes": total,
            "sha256": expected,
            "manifest_verified_download": True,
            "windows_authenticode_verified": False,
            "installer_executed": False,
            "existing_game_grave_changed": False,
            "note": "Run Windows publisher/Authenticode verification before manually installing.",
        }
    finally:
        # Only unlink paths belonging to this exact uniquely created file.
        # Do not delete unrelated outputs that another program created.
        if published:
            try:
                state = target.lstat()
                if (state.st_dev, state.st_ino) == owned_identity and (
                        not target.is_symlink()):
                    # On success leave the verified target alone. On error,
                    # caller must inspect the target; do not hide ambiguity.
                    pass
            except OSError:
                pass
        if owned is not None:
            try:
                state = owned.lstat()
                if (state.st_dev, state.st_ino) == owned_identity and (
                        not owned.is_symlink()):
                    owned.unlink()
            except OSError:
                pass
