"""Opt-in local watchlist for Resurrection Kit source folders.

Nothing runs in the background. File metadata is read only on an explicit
user action. No contents are uploaded; only local JSON stores the user-chosen
paths. A "changed" result prompts a full on-demand review, never an automatic
backup. Metadata changes alone do not establish changed file contents.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from core import config_dir
from resurrection_v2 import _manifest_for, _regular, _safe_tree, inspect_restore

WATCH_SCHEMA = 1
WATCH_LIMIT = 16
WATCH_FILE_LIMIT = 96000
ROLE_SET = {"Saves", "Mods", "Profiles", "Configs"}


def _watch_path() -> Path:
    return config_dir() / "living_kit_watches.json"


def list_kit_watches() -> list[dict]:
    """Return a bounded local list, never silently trust its paths for writes."""
    path = _watch_path()
    try:
        if not _regular(path) or path.stat().st_size > WATCH_FILE_LIMIT:
            return []
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict) or document.get("schema") != WATCH_SCHEMA:
            return []
        entries = document.get("watches")
        if not isinstance(entries, list):
            return []
        result = []
        for row in entries[:WATCH_LIMIT]:
            if (not isinstance(row, dict) or
                    not isinstance(row.get("id"), str) or
                    not isinstance(row.get("manifest"), str) or
                    not isinstance(row.get("sources"), dict) or
                    not row["sources"] or
                    set(row["sources"]) - ROLE_SET or
                    any(not isinstance(v, str) or len(v) > 4096
                        for v in row["sources"].values())):
                continue
            result.append(row)
        return result
    except (OSError, ValueError, TypeError):
        return []


def _write_watches(rows: list[dict]) -> None:
    path = _watch_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="w", dir=path.parent, prefix="living-kit-", suffix=".tmp",
                delete=False, encoding="utf-8") as stream:
            temp = Path(stream.name)
            json.dump({"schema": WATCH_SCHEMA, "watches": rows[:WATCH_LIMIT]},
                      stream, ensure_ascii=False, indent=2)
        temp.replace(path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def _metadata_signature(sources: dict[str, Path], archive: Path) -> tuple[str, int]:
    """Bounded file metadata signature; detects suspect changes, not correctness."""
    if not sources or set(sources) - ROLE_SET:
        raise ValueError("Unknown or missing source category.")
    pieces = []
    count = 0
    for role, location in sorted(sources.items()):
        files = _safe_tree(Path(location), archive)
        for path, relative, size, modified in files:
            pieces.append((role, relative.casefold(), size, modified))
            count += 1
    if count > 40000:
        raise ValueError("Too many source files to monitor safely.")
    signature = hashlib.sha256()
    for role, relative, size, modified in sorted(pieces):
        signature.update(
            json.dumps([role, relative, size, modified],
                       ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        signature.update(b"\n")
    return signature.hexdigest(), count


def register_kit_watch(manifest_path: Path, sources: dict[str, Path],
                       *, approved=False) -> dict:
    """Requires explicit user opt-in; stores user-chosen local paths only."""
    if approved is not True:
        raise PermissionError("Only explicit opt-in can save watch paths.")
    meta, archive = _manifest_for(manifest_path)
    report = inspect_restore(manifest_path)
    if report["schema"] != 2 or set(sources) != set(report["roles"]):
        raise ValueError("Tracked folders must match a complete v2 kit's backup categories.")
    fingerprint, count = _metadata_signature(sources, archive)
    manifest = str(Path(manifest_path).resolve(strict=True))
    identity = hashlib.sha256(manifest.encode("utf-8")).hexdigest()[:20]
    row = {
        "id": identity,
        "game": report["game"],
        "manifest": manifest,
        "sources": {role: str(Path(folder).resolve(strict=True))
                    for role, folder in sources.items()},
        "baseline": fingerprint,
        "archive_hash": meta["archive_sha256"],
        "files_at_registration": count,
        "registered": datetime.now(timezone.utc).isoformat(),
        "opt_in": True,
    }
    previous = [r for r in list_kit_watches() if r["id"] != identity]
    _write_watches([row] + previous[:WATCH_LIMIT - 1])
    return {"id": identity, "game": row["game"],
            "folders": len(sources), "local_only": True,
            "note": "File metadata is checked only when you press Check watched kits."}


def check_kit_watches() -> list[dict]:
    """On-demand metadata comparison; errors are UNKNOWN, never no-change."""
    findings = []
    for row in list_kit_watches():
        state = "unknown"
        reason = ""
        try:
            meta, archive = _manifest_for(Path(row["manifest"]))
            if meta.get("archive_sha256") != row.get("archive_hash"):
                state = "unknown"
                reason = "Kit manifest has changed; review integrity before continuing."
            else:
                current, count = _metadata_signature(
                    {role: Path(path) for role, path in row["sources"].items()},
                    archive)
                state = "possible changes" if current != row.get("baseline") else "unchanged metadata"
                reason = (f"{count} source files examined. "
                          "Possible changes require full content review."
                          if state == "possible changes" else
                          f"{count} source files have unchanged sizes and timestamps; "
                          "this does not prove identical contents.")
        except (OSError, ValueError, RuntimeError) as exc:
            state = "unknown"
            reason = "Unable to inspect one or more selected folders; do not assume unchanged."
        findings.append({
            "id": row["id"], "game": row.get("game", "Unknown"),
            "manifest": row["manifest"], "sources": row["sources"],
            "status": state, "reason": reason,
            "no_automatic_backup": True,
        })
    return findings


def stop_kit_watch(watch_id: str, *, approved=False) -> bool:
    """Forget the locally watched paths; never changes any game or backup."""
    if approved is not True:
        raise PermissionError("Explicit approval is required to stop tracking.")
    if not isinstance(watch_id, str):
        raise ValueError("Invalid watch ID.")
    old = list_kit_watches()
    retained = [row for row in old if row["id"] != watch_id]
    if len(retained) == len(old):
        return False
    _write_watches(retained)
    return True
