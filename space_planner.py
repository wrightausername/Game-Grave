"""Small, cautious space-planning helper for specific target drives.

Read-only. Outputs ranked *review* paths, not delete authorizations or promises
of available space. Real free space is read from the OS, not inferred from files.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import shutil

from core import is_protected_path, is_game_neglected
from graveyard import looks_like_game_archive


@dataclass(frozen=True)
class SpaceSuggestion:
    name: str
    path: str
    apparent_bytes: int
    action: str
    reason: str


def same_volume(path: str | Path, target: str | Path) -> bool:
    """Compare Windows drive anchors where present and device IDs otherwise."""
    first, second = Path(path), Path(target)
    # On Windows, avoid drive-less or nonexistent directory wildcard matches.
    if os.name == 'nt':
        return bool(first.drive and second.drive and first.drive.casefold() == second.drive.casefold())
    try:
        return first.stat().st_dev == second.stat().st_dev
    except OSError:
        return False


def plan_for_drive(target_gb: int, drive: str | Path, old_files, games,
                   never_touch: list[str] | None = None, reserve_gb: int = 10) -> dict:
    """Plan a target amount of *free* disk space, including a modest reserve.

    Hardlinked duplicate files are not counted twice in the apparent candidate
    subtotal, but that number remains unverified and is NOT reclaimable space.
    """
    if not 1 <= int(target_gb) <= 4000 or not 0 <= int(reserve_gb) <= 1000:
        raise ValueError('Choose a realistic size and reserve')
    root = Path(drive)
    usage = shutil.disk_usage(root)  # Raises if drive absent. Do not invent metrics.
    gigabyte = 1024 ** 3
    needed = max(0, (int(target_gb) + int(reserve_gb)) * gigabyte - usage.free)
    candidates: list[SpaceSuggestion] = []
    seen_paths: set[str] = set()
    seen_ids: set[tuple[int, int]] = set()
    # Review only archive-shaped old downloads. Other old files appear in Old Files,
    # not in a gaming cleanup plan with a misleading game association.
    for f in old_files:
        path = Path(f.path)
        if (not same_volume(path, root) or not looks_like_game_archive(path)
                or is_protected_path(path, never_touch)):
            continue
        try:
            if not path.is_file() or path.is_symlink():
                continue
            st = path.stat()
            if st.st_size != f.size or st.st_mtime != f.modified:
                continue  # Changed since scan; needs rescan.
        except OSError:
            continue
        identity = (st.st_dev, st.st_ino)
        path_id = str(path.resolve()).casefold()
        if identity in seen_ids or path_id in seen_paths:
            continue
        seen_paths.add(path_id)
        seen_ids.add(identity)
        candidates.append(SpaceSuggestion(path.name, str(path), max(0, st.st_size),
                    'Review in The Graveyard',
                    ('Multiple hardlinks exist; removing this copy may reclaim no space. ' if st.st_nlink > 1 else '') + 'Looks like an older game/mod archive, but its purpose is unverified.'))
    # Do not add managed game installations to the same subtotal: their uninstall
    # is launcher-mediated and the scan may overlap or be inaccurate.
    stale_games = []
    for g in games:
        if same_volume(g.install_path, root) and is_game_neglected(g, 180):
            stale_games.append(g)
    candidates.sort(key=lambda c: (-c.apparent_bytes, c.name.casefold()))
    return {
        'drive': str(root), 'target_bytes': int(target_gb)*gigabyte,
        'reserve_bytes': int(reserve_gb)*gigabyte,
        'free_bytes': usage.free, 'missing_bytes': needed,
        'candidates': candidates[:30], 'more_candidates': max(0, len(candidates)-30),
        'candidate_apparent_bytes': sum(c.apparent_bytes for c in candidates),
        'games_to_review': sorted(stale_games, key=lambda g: -g.size)[:8],
        'verified_reclaimable_bytes': 0,
    }
