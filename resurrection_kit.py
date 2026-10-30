"""Portable, verified *save-folder* Resurrection Kit, built on Game Grave Save Vault.

A kit is one verified ZIP plus a sidecar manifest. Full mod reinstalls,
working load orders, game binaries and automatic restoration are NOT promised.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from save_vault import create_backup

KIT_SCHEMA = 1
MAX_MANIFEST = 1_000_000


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def create_resurrection_kit(game: str, source: Path, destination: Path,
                            mod_references=(), cancel=None) -> dict:
    """Create a backup only after the caller requests and approves a specific folder.

    No destination overwrite. The sidecar never includes personal absolute paths.
    Mod references are *names only* and do not establish recovery availability.
    """
    if not isinstance(game, str) or not 1 <= len(game.strip()) <= 120:
        raise ValueError("Enter a game name.")
    destination = Path(destination)
    if destination.suffix.casefold() != ".zip":
        raise ValueError("Select a ZIP destination.")
    sidecar = destination.with_name(destination.name + ".ggkit.json")
    if sidecar.exists():
        raise FileExistsError("A Resurrection Kit manifest already exists here.")
    refs = []
    for item in mod_references:
        if not isinstance(item, str) or len(item) > 140 or "/" in item or "\\" in item:
            raise ValueError("Mod references must be short names without paths.")
        if item.strip() and len(refs) < 500:
            refs.append(item.strip())
    result = create_backup(Path(source), destination, cancel=cancel)
    manifest = {
        "schema": KIT_SCHEMA,
        "game": game.strip(),
        "folder_label": Path(source).name,
        "archive": destination.name,
        "archive_sha256": _sha256(destination),
        "files": result["files"],
        "source_bytes": result["original_bytes"],
        "mod_references": refs,
        "actual_mod_files_preserved": False,
        "automatic_restore": False,
        "verified_zip": result["verified"],
        "note": "Only this selected save/profile folder was archived. No game/mod restoration is guaranteed.",
    }
    partial = sidecar.with_name(sidecar.name + ".partial")
    if partial.exists():
        raise FileExistsError("An incomplete Resurrection Kit manifest already exists.")
    try:
        with partial.open("x", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        partial.replace(sidecar)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return {
        "archive": str(destination), "manifest": str(sidecar),
        "files": result["files"], "verified": True,
        "limits": manifest["note"],
    }


def verify_resurrection_kit(manifest_path: Path) -> dict:
    """Verify a portable kit without extracting, restoring or overwriting anything."""
    manifest_path = Path(manifest_path)
    if manifest_path.is_symlink() or manifest_path.stat().st_size > MAX_MANIFEST:
        raise ValueError("Invalid Resurrection Kit manifest.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema") != KIT_SCHEMA:
        raise ValueError("Unsupported Resurrection Kit.")
    archive_name = manifest.get("archive")
    if (not isinstance(archive_name, str) or not archive_name or
            Path(archive_name).name != archive_name or
            archive_name in (".", "..") or "\\" in archive_name):
        raise ValueError("Invalid archive name.")
    archive = manifest_path.parent / archive_name
    if not archive.is_file() or archive.is_symlink():
        return {"verified": False, "reason": "Backup ZIP is missing."}
    actual_hash = _sha256(archive)
    if actual_hash != manifest.get("archive_sha256"):
        return {"verified": False, "reason": "Backup ZIP checksum does not match."}
    import zipfile
    try:
        with zipfile.ZipFile(archive) as zip_file:
            bad = zip_file.testzip()
            verified = bad is None and len(zip_file.namelist()) == manifest.get("files")
    except (OSError, ValueError, zipfile.BadZipFile):
        verified = False
    return {
        "verified": verified,
        "game": manifest.get("game", "Unknown"),
        "reason": "ZIP integrity and checksum verified." if verified else "ZIP verification failed.",
        "restored": False,
    }
