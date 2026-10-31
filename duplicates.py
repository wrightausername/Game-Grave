"""M2 read-only duplicate game-archive evidence.

Hash comparison is opt-in. Identical content is not proof that an archive is
unused, safe to delete, or physically reclaimable. This module has no cleanup
functions, Windows Shell calls, or filesystem mutations.
"""
from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from core import OldFile, _has_reparse_component, is_protected_path, is_unchanged
from graveyard import looks_like_game_archive

MAX_CANDIDATES = 600
MAX_SINGLE_FILE = 4 * 1024**3
MAX_HASHED_BYTES = 12 * 1024**3
CHUNK_BYTES = 1024 * 1024


@dataclass(frozen=True)
class DuplicateGroup:
    """Different ordinary file identities with identical complete SHA-256."""
    paths: tuple[str, ...]
    size_bytes: int
    sha256: str
    device: int


@dataclass(frozen=True)
class DuplicateReport:
    groups: tuple[DuplicateGroup, ...]
    examined_candidates: int
    hashed_files: int
    hashed_bytes: int
    skipped: int
    truncated: bool
    potential_redundant_apparent_bytes: int
    verified_reclaimable_bytes: int = 0


def _metadata(path: Path) -> tuple[int, int, int, int, int]:
    """Revalidate every identity field; refuse symlinks and hardlinked entries."""
    if _has_reparse_component(path) or not path.is_file():
        raise ValueError("Linked, redirected or unavailable candidate")
    info = path.stat()
    if info.st_nlink != 1 or info.st_size > MAX_SINGLE_FILE:
        raise ValueError("Hardlink or too-large file is excluded")
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_nlink)


def _full_hash(path: Path, expected: tuple[int, int, int, int, int],
               cancel: Callable[[], bool] | None = None) -> str:
    """Hash complete file, not just its prefix, and recheck after read."""
    digest = hashlib.sha256()
    if cancel and cancel():
        raise InterruptedError("Duplicate inspection canceled")
    with path.open("rb") as stream:
        # fstat binds the actual open handle, guarding path replacements.
        before = os.fstat(stream.fileno())
        current = (before.st_dev, before.st_ino, before.st_size,
                   before.st_mtime_ns, before.st_nlink)
        if current != expected:
            raise ValueError("Candidate changed before content check")
        while True:
            if cancel and cancel():
                raise InterruptedError("Duplicate inspection canceled")
            block = stream.read(CHUNK_BYTES)
            if not block:
                break
            digest.update(block)
        after = os.fstat(stream.fileno())
        if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
                after.st_nlink) != expected:
            raise ValueError("Candidate changed during content check")
    if _metadata(path) != expected:
        raise ValueError("Candidate changed after content check")
    return digest.hexdigest()


def inspect_duplicate_archives(
    files: Iterable[OldFile],
    never_touch: Iterable[str] = (),
    *,
    cancel: Callable[[], bool] | None = None,
    max_candidates: int = MAX_CANDIDATES,
    max_hashed_bytes: int = MAX_HASHED_BYTES,
) -> DuplicateReport:
    """Hash only unchanged standalone game/mod archives in explicit scan results.

    Group by file size and *device* before hashing, so same-size files on
    unrelated drives never imply space savings on a target drive. All actual
    reclaimable-space estimates remain zero by design, including for
    byte-identical content (filesystem compression/reflinks may apply).
    """
    if not 1 <= max_candidates <= MAX_CANDIDATES or not 1 <= max_hashed_bytes <= MAX_HASHED_BYTES:
        raise ValueError("Invalid bounded duplicate-inspection limits")
    candidates: dict[tuple[int, int], list[tuple[Path, tuple[int, int, int, int, int]]]] = defaultdict(list)
    seen_paths: set[str] = set()
    skipped = 0
    examined = 0
    truncated = False
    protected = list(never_touch)
    for old in files:
        if cancel and cancel():
            raise InterruptedError("Duplicate inspection canceled")
        if examined >= max_candidates:
            truncated = True
            break
        examined += 1
        path = Path(old.path)
        path_key = os.path.normcase(os.path.abspath(str(path))).casefold()
        if path_key in seen_paths:
            continue
        seen_paths.add(path_key)
        if not looks_like_game_archive(path) or is_protected_path(path, protected):
            skipped += 1
            continue
        try:
            if not is_unchanged(old):
                skipped += 1
                continue
            state = _metadata(path)
        except (OSError, ValueError):
            skipped += 1
            continue
        if state[2] <= 0:
            skipped += 1
            continue
        candidates[(state[0], state[2])].append((path, state))
    # Sort for stable output, even if filesystem traversal order differs.
    exact: dict[tuple[int, int, str], list[str]] = defaultdict(list)
    hashed_files = 0
    hashed_bytes = 0
    for (device, size), entries in sorted(candidates.items()):
        if len(entries) < 2:
            continue
        for path, state in sorted(entries, key=lambda pair: str(pair[0]).casefold()):
            if cancel and cancel():
                raise InterruptedError("Duplicate inspection canceled")
            if hashed_bytes + size > max_hashed_bytes:
                truncated = True
                skipped += 1
                continue
            try:
                digest = _full_hash(path, state, cancel=cancel)
            except (OSError, ValueError):
                skipped += 1
                continue
            hashed_bytes += size
            hashed_files += 1
            exact[(device, size, digest)].append(str(path))
    groups = tuple(
        DuplicateGroup(tuple(sorted(paths, key=str.casefold)), size, digest, device)
        for (device, size, digest), paths in sorted(exact.items())
        if len(paths) >= 2
    )
    # Not a filesystem-verified saving claim. No deletion ever authorized.
    apparent = sum((len(group.paths) - 1) * group.size_bytes for group in groups)
    return DuplicateReport(groups, examined, hashed_files, hashed_bytes,
                           skipped, truncated, apparent)
