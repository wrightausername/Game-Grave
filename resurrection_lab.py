"""Resurrection Lab: auditable kit checks, rehearsals, revisions, and portable transfers.

All functions are explicit, on-demand operations. No background scanning,
network operations, deletion of game data, or live manager modification.

An independently verified ZIP is not proof of mod compatibility or in-game
recovery. Versions are immutable full archives; incremental deduplication is
a future optimization, not silently claimed here.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path

from resurrection_v2 import (
    MAX_BYTES, MAX_FILES, MIN_SPACE_BUFFER, _manifest_for, _regular, _safe_label,
    _scan_archive, _sha256, _safe_tree, _valid_member, create_complete_kit,
    inspect_restore, restore_kit,
)

MAX_VISIBLE = 75
MAX_HISTORY = 100
MAX_MODLIST_BYTES = 2_000_000
MAX_DIFF_ENTRIES = MAX_FILES


def _verified(manifest_path: Path) -> tuple[dict, Path, dict]:
    path = Path(manifest_path)
    report = inspect_restore(path)
    meta, archive = _manifest_for(path)
    return meta, archive, report


def _zip_entries(archive_path: Path, schema: int) -> dict[str, zipfile.ZipInfo]:
    with zipfile.ZipFile(archive_path) as file:
        infos, _size, _roles = _scan_archive(file, schema)
        return {"/".join(_valid_member(info, schema)): info for info in infos}


def _mod_list(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> dict:
    if info.file_size > MAX_MODLIST_BYTES:
        return {"error": "MO2 modlist exceeds inspection cap.", "enabled": [], "disabled": []}
    try:
        contents = archive.read(info)
    except (OSError, RuntimeError, zipfile.BadZipFile):
        return {"error": "MO2 modlist could not be read.", "enabled": [], "disabled": []}
    try:
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = contents.decode("cp1252", errors="replace")
    enabled, disabled, malformed = [], [], []
    for row in text.splitlines():
        if not row or row.startswith("#") or row[0] not in "+-":
            continue
        name = row[1:].strip()
        if (not name or len(name) > 200 or
                name in (".", "..") or "/" in name or "\\" in name or
                any(ord(c) < 32 for c in name)):
            malformed.append(row[:60])
            continue
        if name.casefold().endswith("_separator"):
            continue
        (enabled if row[0] == "+" else disabled).append(name)
    return {"enabled": enabled[:MAX_FILES], "disabled": disabled[:MAX_FILES],
            "malformed_count": len(malformed)}


def missing_pieces(manifest_path: Path) -> dict:
    """Evidence-based readiness; no guessed dependencies or download links."""
    meta, archive, inspected = _verified(manifest_path)
    names = _zip_entries(archive, inspected["schema"])
    roles = set(inspected["roles"])
    issues, unknown = [], []
    missing_enabled = []
    manager = meta.get("manager_context")
    kind = manager.get("kind", "unknown") if isinstance(manager, dict) else "unknown"
    if "Saves" not in roles:
        unknown.append("Game saves were not included in this kit.")
    if "Configs" not in roles:
        unknown.append("External configuration files may not have been included.")
    if "Mods" not in roles:
        unknown.append("Mod binaries were not included.")
    if kind == "MO2":
        if "Profiles" not in roles:
            issues.append("MO2 profile data was not included.")
        profile_name = "Profiles/modlist.txt"
        info = names.get(profile_name)
        if info is None:
            issues.append("MO2 modlist.txt was not preserved at the expected profile root.")
        else:
            with zipfile.ZipFile(archive) as reader:
                inventory = _mod_list(reader, info)
            if inventory.get("error"):
                issues.append(inventory["error"])
            if inventory.get("malformed_count"):
                issues.append("MO2 modlist has unrecognized entries requiring review.")
            included = {p.split("/", 2)[1].casefold() for p in names
                        if p.startswith("Mods/") and len(p.split("/")) >= 3}
            missing_enabled = sorted({
                name for name in inventory.get("enabled", [])
                if name.casefold() not in included
            }, key=str.casefold)
            if missing_enabled:
                issues.append(f"{len(missing_enabled)} enabled MO2 mod folders are absent from the kit.")
        unknown.append("Plugin load order and version-specific dependencies were not independently verified.")
    elif kind == "Vortex":
        unknown.append("Vortex profile/deployment state was not reconstructed; no supported live API integration.")
        unknown.append("Mod dependencies and original download availability are not verified.")
    else:
        unknown.append("Game/mod-manager ownership, load order and dependency completeness are not verified.")
    unknown.append("A valid archive does not prove a game or modded setup will launch.")
    return {
        "game": inspected["game"], "manager": kind,
        "archive_verified": inspected["verified"], "files": inspected["files"],
        "roles": inspected["roles"],
        "missing_enabled_mods": missing_enabled[:MAX_VISIBLE],
        "missing_count": len(missing_enabled),
        "issues": issues, "unknown": unknown,
        "restore_rehearsed": False,
        "complete_game_recovery_verified": False,
        "readiness": ("Needs attention" if issues else "Archive intact; setup recovery unverified"),
        "source_manifest": str(Path(manifest_path)),
    }


def compare_kits(before: Path, after: Path) -> dict:
    """Compare two fully verified immutable recovery snapshots."""
    old_meta, old_archive, old = _verified(before)
    new_meta, new_archive, new = _verified(after)
    if old["game"].strip().casefold() != new["game"].strip().casefold():
        raise ValueError("Snapshots belong to different recorded games.")
    previous = _zip_entries(old_archive, old["schema"])
    current = _zip_entries(new_archive, new["schema"])
    before_names = {k.casefold(): (k, v) for k, v in previous.items()}
    after_names = {k.casefold(): (k, v) for k, v in current.items()}
    entries = []
    for key in sorted(set(before_names) | set(after_names)):
        a = before_names.get(key)
        b = after_names.get(key)
        if a is None:
            change, label = "added", b[0]
        elif b is None:
            change, label = "missing in newer snapshot", a[0]
        elif (a[1].file_size, a[1].CRC) != (b[1].file_size, b[1].CRC):
            change, label = "changed", b[0]
        else:
            continue
        entries.append({"path": label, "change": change})
    # Checksums verify whole ZIPs, CRC32 comparisons identify likely file
    # differences. Identical CRC/size does not prove byte-for-byte identity.
    return {
        "game": old["game"], "before": str(before), "after": str(after),
        "older_files": old["files"], "newer_files": new["files"],
        "change_count": len(entries), "changes": entries[:MAX_VISIBLE],
        "truncated_details": len(entries) > MAX_VISIBLE,
        "full_archive_checksums_verified": True,
        "file_identity_method": "Uncompressed size + ZIP CRC32; possible collisions",
        "no_overwrite": True,
        "note": "Choose a snapshot for separate staged recovery. This comparison never rolls back live files.",
    }


def _stream_hash(source) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: source.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def _source_entries(sources: dict, zip_destination: Path) -> dict:
    if not isinstance(sources, dict) or not sources:
        raise ValueError("Choose source folders for the new kit version.")
    discovered = {}
    all_roots = []
    for role, root in sources.items():
        if role not in {"Saves", "Mods", "Profiles", "Configs"}:
            raise ValueError("Unsupported kit source role.")
        scanned = _safe_tree(Path(root), zip_destination)
        all_roots.append(Path(root).resolve(strict=True))
        for item, relative, size, modified in scanned:
            name = f"{role}/{relative}"
            if name.casefold() in discovered:
                raise ValueError("Duplicate source path in update.")
            discovered[name.casefold()] = (name, item, size, modified)
    for i, first in enumerate(all_roots):
        if any(first == other or first in other.parents or other in first.parents
               for other in all_roots[i + 1:]):
            raise ValueError("Kit sources must not overlap.")
    if len(discovered) > MAX_FILES or sum(x[2] for x in discovered.values()) > MAX_BYTES:
        raise ValueError("Kit update exceeds safe file-count or size cap.")
    return discovered


def plan_living_update(previous_manifest: Path, sources: dict[str, Path]) -> dict:
    """Compare actual bytes, not timestamps alone; unchanged full backups are avoided."""
    meta, archive, prior = _verified(previous_manifest)
    if prior["schema"] != 2:
        raise ValueError("Living Kit revisions require an existing v2 kit.")
    if set(sources) != set(prior["roles"]):
        raise ValueError("Select exactly the same backup categories as the original kit.")
    originals = _zip_entries(archive, 2)
    current = _source_entries(sources, archive)
    old = {name.casefold(): (name, info) for name, info in originals.items()}
    changes = []
    hashes = hashlib.sha256()
    with zipfile.ZipFile(archive) as backup:
        for name in sorted(set(current) | set(old)):
            old_item = old.get(name)
            live = current.get(name)
            if live is None:
                changes.append({"path": old_item[0], "change": "missing from new version"})
                hashes.update(f"missing:{name}\n".encode())
                continue
            label, path, expected_size, expected_mtime = live
            if not _regular(path):
                raise ValueError("An input file changed type during the version check.")
            before = path.stat()
            if (before.st_size, before.st_mtime_ns) != (expected_size, expected_mtime):
                raise ValueError("A file changed during version planning. Retry.")
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(path, flags)
            with os.fdopen(fd, "rb") as file:
                if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
                    raise ValueError("A kit source stopped being an ordinary file.")
                live_hash = _stream_hash(file)
            if not _regular(path) or path.stat().st_mtime_ns != expected_mtime:
                raise ValueError("Source changed during version check.")
            hashes.update(f"{name}:{live_hash}\n".encode())
            if old_item is None:
                changes.append({"path": label, "change": "added"})
                continue
            if expected_size != old_item[1].file_size:
                changes.append({"path": label, "change": "changed"})
                continue
            with backup.open(old_item[1]) as reader:
                if _stream_hash(reader) != live_hash:
                    changes.append({"path": label, "change": "changed"})
    return {
        "game": prior["game"],
        "source_count": len(sources), "files": len(current),
        "changes": changes[:MAX_VISIBLE], "change_count": len(changes),
        "details_truncated": len(changes) > MAX_VISIBLE,
        "changed": bool(changes),
        "source_fingerprint": hashes.hexdigest(),
        "previous_archive_hash": meta["archive_sha256"],
        "manager_context_revalidated": False,
        "note": "A new complete, independent ZIP is made on demand. No background watching or deduplication yet.",
    }


def create_living_update(previous_manifest: Path, sources: dict[str, Path],
                         destination: Path, *, approved=False,
                         expected_source_fingerprint="") -> dict:
    if approved is not True or not expected_source_fingerprint:
        raise PermissionError("Approve the reviewed kit update first.")
    checked = plan_living_update(previous_manifest, sources)
    if not checked["changed"]:
        raise ValueError("Selected source folders match the existing kit; no new version needed.")
    if checked["source_fingerprint"] != expected_source_fingerprint:
        raise ValueError("Sources changed since the review. Review again.")
    # Deliberately do not inherit MO2/Vortex verified-manager status after
    # re-selecting folders. Auto-reconnect needs a fresh discovery evidence pass.
    result = create_complete_kit(checked["game"], sources, destination)
    result["previous_manifest"] = str(previous_manifest)
    result["version_type"] = "Full independent snapshot"
    result["manager_evidence_carried_over"] = False
    return result


def rehearse_kit(manifest_path: Path, parent: Path) -> dict:
    """Extract to an isolated, owned temp folder and compare file hashes.

    This exercises ZIP extraction and recovery logic, not game launching.
    The temporary directory belongs exclusively to this operation.
    """
    meta, archive, kit = _verified(manifest_path)
    parent = Path(parent)
    if not _regular(parent, directory=True):
        raise ValueError("Choose an ordinary rehearsal destination folder.")
    if shutil.disk_usage(parent).free < kit["bytes"] + MIN_SPACE_BUFFER:
        raise OSError("Insufficient free space to rehearse recovery.")
    checked_count = 0
    with tempfile.TemporaryDirectory(prefix="GameGrave-Rehearsal-", dir=parent) as temp:
        recovered = restore_kit(manifest_path, Path(temp), approved=True)
        extracted = Path(recovered["target"])
        with zipfile.ZipFile(archive) as backup:
            infos, _total, _roles = _scan_archive(backup, kit["schema"])
            for info in infos:
                relative = _valid_member(info, kit["schema"])
                source = extracted.joinpath(*relative)
                if not _regular(source):
                    raise RuntimeError("Rehearsal restored an unsafe or missing file.")
                with backup.open(info) as baseline, source.open("rb") as actual:
                    if _stream_hash(baseline) != _stream_hash(actual):
                        raise RuntimeError("Rehearsal file digest mismatch.")
                checked_count += 1
        if checked_count != kit["files"]:
            raise RuntimeError("Rehearsal file count mismatch.")
    return {
        "game": kit["game"], "files_verified": checked_count,
        "archive_verified": True, "isolated_extract_verified": True,
        "game_launch_verified": False,
        "manager_reconnection_verified": False,
        "temporary_files_cleaned": True,
        "note": "Extraction rehearsal passed. The actual game and mod manager were not launched or reconfigured.",
    }


def list_snapshots(folder: Path, game: str = "") -> list[dict]:
    """List locally visible sidecar versions; catalog does NOT imply verified."""
    folder = Path(folder)
    if not _regular(folder, directory=True):
        raise ValueError("Choose an ordinary folder containing Resurrection Kits.")
    result = []
    for file in sorted(folder.glob("*.ggkit.json"), key=lambda p: p.name.casefold()):
        if not _regular(file) or file.stat().st_size > 1024 * 1024:
            continue
        try:
            meta, archive = _manifest_for(file)
        except (OSError, ValueError, TypeError):
            continue
        title = str(meta.get("game", ""))[:120]
        if game and title.casefold() != game.casefold():
            continue
        result.append({
            "game": title, "manifest": str(file),
            "archive": str(archive), "files_claimed": meta.get("files"),
            "modified": file.stat().st_mtime,
            "verified": False,
        })
        if len(result) >= MAX_HISTORY:
            break
    return sorted(result, key=lambda x: x["modified"], reverse=True)


def prepare_pc_transfer(manifest_path: Path, destination_parent: Path,
                        *, approved=False) -> dict:
    """Make a self-contained portable *folder* with verified ZIP + sidecar.

    No game binaries or Steam licenses copied. Transfer via USB/network
    manually. Re-import with the exact same kit on the receiving PC.
    """
    if approved is not True:
        raise PermissionError("Approve the target transfer folder before copying.")
    manifest, archive, kit = _verified(manifest_path)
    destination_parent = Path(destination_parent)
    if not _regular(destination_parent, directory=True):
        raise ValueError("Choose an ordinary transfer destination directory.")
    target = destination_parent / (_safe_label(kit["game"]) + "_GameGrave_Transfer")
    if target.exists() or target.is_symlink():
        raise FileExistsError("Transfer folder already exists; select another parent.")
    bytes_needed = archive.stat().st_size + Path(manifest_path).stat().st_size
    if shutil.disk_usage(destination_parent).free < bytes_needed + MIN_SPACE_BUFFER:
        raise OSError("Insufficient free space for a full portable kit copy.")
    if destination_parent.resolve() in archive.resolve().parents:
        # Copy into a nested folder under the kit archive's parent can be valid,
        # but this branch prevents a buggy self-copy when creating the bundle.
        if target == archive.parent:
            raise ValueError("Destination would overlap the original backup.")
    target.mkdir(mode=0o700, exist_ok=False)
    completed = []
    try:
        for src in (archive, Path(manifest_path)):
            dst = target / src.name
            if not _regular(src):
                raise ValueError("Original kit file changed during copying.")
            with src.open("rb") as data, dst.open("xb") as output:
                shutil.copyfileobj(data, output, 1024 * 1024)
            completed.append(dst)
            if _sha256(src) != _sha256(dst):
                raise RuntimeError("Portable kit copy failed integrity verification.")
        guide = target / "READ_ME_FIRST.txt"
        guide.write_text(
            "GAME GRAVE — PC-TO-PC RESURRECTION\n\n"
            "1. Copy this entire folder to your new Windows PC. Keep the ZIP and "
            ".ggkit.json manifest together.\n"
            "2. Install the game through its official launcher (Steam, Epic or GOG "
            "as applicable). Licenses and binaries are NOT included.\n"
            "3. Install Game Grave on the destination PC and scan installed games.\n"
            "4. In Resurrection Lab, choose Preview / Restore Kit using the .ggkit.json "
            "file in this folder. Recover into a NEW directory, never over old files.\n"
            "5. For verified MO2 kits, use Reconnect verified MO2 kit only after "
            "installing and closing MO2, and after reviewing the exact destination "
            "and all conflicts. Vortex active-state auto-restore is not supported.\n"
            "6. Reconnect saves and unsupported mod-manager data manually after review. "
            "No in-game compatibility or launch success is guaranteed.\n",
            encoding="utf-8")
        result = inspect_restore(target / Path(manifest_path).name)
        if not result["verified"]:
            raise RuntimeError("Copied kit failed its final integrity check.")
    except BaseException:
        # Preserve incomplete transfer folder for inspection rather than risking
        # deletion of files placed there by another process.
        raise
    return {
        "game": kit["game"], "target": str(target),
        "archive": str(target / archive.name),
        "manifest": str(target / Path(manifest_path).name),
        "files_in_kit": kit["files"],
        "portable_copy_verified": True,
        "launcher_installation_included": False,
        "note": "Copy the whole folder to your new PC, install through the launcher, "
                "then use Game Grave staged restore or reviewed MO2 reconnection.",
    }
