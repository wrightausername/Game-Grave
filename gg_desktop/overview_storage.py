"""Overview-only, read-only accounting of detected game and mod storage.

The chart uses measured logical file bytes, not launcher estimates or free-space
claims. Paths overlap; hardlinks share an identity. Both are counted once.
Nothing in the accepted inventory, preferences or source folders is modified.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import os
from pathlib import Path
import shutil
import stat
import time

from core import _has_reparse_component, _mod_markers
from gg_desktop.insight_models import capture_items, storage_items
from gg_desktop.mods_data import build_catalog

CATEGORIES = (("Games", "#ff2346"), ("Mods", "#ce8fe5"),
              ("Other Storage", "#40d8d3"), ("Captures", "#778dff"),
              ("Old Files", "#f0bc78"))
PRIORITY = {"Captures": 0, "Other Storage": 1, "Mods": 2, "Games": 3, "Old Files": 4}
SKIP_ATTRIBUTES = 0x400 | 0x1000 | 0x40000 | 0x400000


def path_key(path):
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def within(path, parent):
    return path == parent or path.startswith(parent.rstrip(os.sep) + os.sep)


@dataclass
class MeasuredRoot:
    path: str
    category: str
    name: str
    source: str
    game_key: str = ""
    reported_bytes: int | None = None
    listed_bytes: int = 0
    listed_files: int = 0
    counted_bytes: int = 0
    counted_files: int = 0
    shared_files: int = 0
    valid: bool = False
    problems: list[str] = field(default_factory=list)

    @property
    def key(self):
        return path_key(self.path)

    @property
    def status(self):
        return "Unavailable" if not self.valid else "Partial" if self.problems else "Measured"


@dataclass(frozen=True)
class VolumeReading:
    path: str
    total: int | None = None
    used: int | None = None
    free: int | None = None
    error: str = ""


@dataclass
class StorageSnapshot:
    roots: list[MeasuredRoot] = field(default_factory=list)
    totals: dict[str, int] = field(default_factory=lambda: dict.fromkeys((c for c, _ in CATEGORIES), 0))
    files: int = 0
    shared_files: int = 0
    skipped: int = 0
    limited: bool = False
    checked: int = 0
    measured_at: str = ""
    game_count: int = 0
    mod_count: int = 0
    mod_unit: str = "Mod locations"
    mod_count_partial: bool = False
    catalog: object = None
    volumes: tuple[VolumeReading, ...] = ()

    @property
    def total(self):
        return sum(self.totals.values())

    @property
    def partial(self):
        return self.limited or any(root.problems for root in self.roots)

    @property
    def segments(self):
        return [(name, self.totals[name], color) for name, color in CATEGORIES]

    def category_partial(self, category):
        return self.limited or any(root.category == category and root.problems for root in self.roots)


class RootIndex:
    def __init__(self, roots):
        self.tree = {}
        for index, root in enumerate(roots):
            node = self.tree
            for part in Path(root.key).parts:
                node = node.setdefault(part, {})
            node.setdefault(None, []).append(index)

    def matching(self, path):
        node, matches = self.tree, []
        for part in Path(path_key(path)).parts:
            node = node.get(part)
            if node is None:
                break
            matches.extend(node.get(None, ()))
        return matches


def inventory_key(inventory):
    """A cache key that changes when accepted scan findings change."""
    return (id(inventory), inventory.scanned_at,
            tuple((g.key, g.install_path, g.size_bytes) for g in inventory.games),
            tuple((m.path, m.source, m.apparent_bytes) for m in inventory.mods),
            tuple((f.path, f.size, f.modified_ns) for f in inventory.files),
            tuple((f.path, f.size, f.modified_ns) for f in (*inventory.screenshots, *inventory.recordings)))


def measurement_roots(inventory, catalog, canceled=lambda: False):
    roots, seen = [], set()
    game_paths = {path_key(g.install_path): g for g in inventory.games if g.install_path}

    def add(path, category, name, source, game_key="", reported=None, problem=""):
        if not path:
            return
        key = (path_key(path), category)
        if key in seen:
            return
        seen.add(key)
        root = MeasuredRoot(str(Path(path).absolute()), category, str(name), str(source),
                            game_key, reported if type(reported) is int and reported >= 0 else None)
        if problem:
            root.problems.append(problem)
        roots.append(root)

    for game in inventory.games:
        add(game.install_path, "Games", game.name, game.size_source, game.key, game.size_bytes,
            "" if "open_folder" in game.capabilities else "Installation is unverified; inspect its source before measuring.")
    for item in storage_items(inventory):
        add(item.path, "Other Storage", item.name, item.source, reported=item.size)
    storage_paths = {r.key for r in roots if r.category == "Other Storage"}
    for mod in inventory.mods:
        if canceled():
            raise InterruptedError("Overview measurement canceled")
        key = path_key(mod.path)
        if key in storage_paths:
            continue
        if key in game_paths:
            # Steam's installed-mod finding points at the GAME root but its
            # apparent_bytes cover only marker subpaths, not the whole game.
            markers = _mod_markers(Path(mod.path))
            for _, marker in markers:
                add(marker, "Mods", mod.name, mod.source, game_paths[key].key)
            if not markers:
                add(mod.path, "Mods", mod.name, mod.source, problem="Recorded mod markers are unavailable; rescan this game.")
        else:
            add(mod.path, "Mods", mod.name, mod.source, reported=mod.apparent_bytes)
    for entry in catalog.entries:
        if entry.kind == "mod":
            add(entry.path, "Mods", entry.name, entry.source, entry.game_key)
    for item in capture_items(inventory):
        add(item.record.path, "Captures", Path(item.record.path).name, item.source, reported=item.record.size)
    for file in inventory.files:
        add(file.path, "Old Files", Path(file.path).name, "Accepted file scan", reported=file.size)
    return roots


def measure_storage(inventory, *, canceled=lambda: False, progress=lambda checked, message: None,
                    max_entries=5_000_000, max_files=2_000_000, max_directories=250_000,
                    catalog_reader=build_catalog):
    """Measure the union of detected roots without reading game file contents.

    Mod descriptors are read through the existing bounded catalog reader.
    Missing, linked, offline and inaccessible content stays explicitly partial.
    Sparse/compressed physical allocation is not inferred from logical sizes.
    """
    def check():
        if canceled():
            raise InterruptedError("Overview measurement canceled")
    check()
    progress(0, "Reading detected mod locations and package metadata…")
    catalog = catalog_reader(inventory, canceled=canceled)
    result = StorageSnapshot(catalog=catalog)
    result.roots = measurement_roots(inventory, catalog, canceled)
    result.game_count = len({path_key(g.install_path) for g in inventory.games if g.install_path})
    individuals = {path_key(e.path) for e in catalog.entries if e.kind == "mod"}
    present = {key for key in individuals if not _has_reparse_component(Path(key))
               and (Path(key).is_dir() or Path(key).is_file())}
    result.mod_count = len(present) if individuals else len({path_key(e.path) for e in catalog.entries})
    result.mod_unit = "Mods" if individuals else "Mod locations"
    result.mod_count_partial = catalog.limited
    index = RootIndex(result.roots)
    valid, explicit_files = [], set()
    def problem(path, message, descendants=False):
        key = path_key(path)
        matches = index.matching(path)
        if descendants:
            matches = set(matches) | {i for i, root in enumerate(result.roots) if within(root.key, key)}
        for i in matches:
            root = result.roots[i]
            if len(root.problems) < 20 and message not in root.problems:
                root.problems.append(message)
        result.skipped += 1

    for root in result.roots:
        check()
        if root.problems:
            continue
        path = Path(root.path)
        try:
            if path.parent == path or _has_reparse_component(path):
                raise ValueError("Linked, unavailable or drive-root location was not measured.")
            info = path.lstat()
            if getattr(info, "st_file_attributes", 0) & SKIP_ATTRIBUTES:
                raise ValueError("Offline or redirected content was not opened.")
            if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                raise ValueError("Not an ordinary file or directory.")
            root.valid = True
            valid.append((path, info))
            if stat.S_ISREG(info.st_mode):
                explicit_files.add(root.key)
        except (OSError, ValueError) as exc:
            root.problems.append(str(exc)[:350])

    pending = sorted(valid, key=lambda item: len(item[0].parts), reverse=True)
    directories, explicit_seen, seen_files = set(), set(), {}
    last_progress = 0.0
    def file(path, info):
        # Windows DirEntry.stat() deliberately supplies zero for st_ino,
        # st_dev and st_nlink. Query the path itself before identifying links;
        # a path fallback would otherwise charge Vortex deployments twice.
        if os.name == "nt" or not info.st_ino:
            info = path.lstat()
        key = path_key(path)
        if key in explicit_files:
            if key in explicit_seen:
                return
            explicit_seen.add(key)
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & SKIP_ATTRIBUTES:
            problem(path, "Linked or offline files were skipped.")
            return
        if not stat.S_ISREG(info.st_mode):
            return
        matches = [i for i in index.matching(path) if result.roots[i].valid]
        if not matches:
            return
        size = max(0, info.st_size)
        for i in matches:
            result.roots[i].listed_bytes += size
            result.roots[i].listed_files += 1
        identity = (info.st_dev, info.st_ino) if info.st_ino else ("path", key)
        if not info.st_ino and info.st_nlink > 1:
            problem(path, "Hardlink identity unavailable; these bytes were not guessed.")
            return
        owner = min(matches, key=lambda i: (PRIORITY[result.roots[i].category], -len(result.roots[i].key), i))
        previous = seen_files.get(identity)
        if previous is not None:
            result.shared_files += 1
            result.roots[owner].shared_files += 1
            old_size, old_owner = previous
            if old_size != size:
                problem(path, "File size changed during measurement; refresh after updates finish.")
            if PRIORITY[result.roots[owner].category] < PRIORITY[result.roots[old_owner].category]:
                old = result.roots[old_owner]
                old.counted_bytes -= old_size
                old.counted_files -= 1
                result.totals[old.category] -= old_size
                new = result.roots[owner]
                new.counted_bytes += old_size
                new.counted_files += 1
                result.totals[new.category] += old_size
                seen_files[identity] = (old_size, owner)
            return
        seen_files[identity] = (size, owner)
        result.files += 1
        root = result.roots[owner]
        root.counted_bytes += size
        root.counted_files += 1
        result.totals[root.category] += size

    while pending:
        check()
        if result.checked >= max_entries or result.files >= max_files or len(directories) >= max_directories:
            result.limited = True
            break
        path, initial = pending.pop()
        try:
            info = path.lstat()
            if not stat.S_ISDIR(info.st_mode):
                file(path, info)
                continue
            key = path_key(path)
            if key in directories:
                continue
            if _has_reparse_component(path) or getattr(info, "st_file_attributes", 0) & SKIP_ATTRIBUTES:
                problem(path, "Linked or offline directory was skipped.", True)
                continue
            directories.add(key)
            with os.scandir(path) as entries:
                for entry in entries:
                    check()
                    if result.checked >= max_entries or result.files >= max_files:
                        result.limited = True
                        break
                    result.checked += 1
                    try:
                        state = entry.stat(follow_symlinks=False)
                        target = Path(entry.path)
                        if stat.S_ISDIR(state.st_mode):
                            pending.append((target, state))
                        else:
                            file(target, state)
                    except OSError as exc:
                        problem(entry.path, "Entry unavailable: " + str(exc)[:250])
                    now = time.monotonic()
                    if now-last_progress >= .25:
                        progress(result.checked, f"Measuring game/mod storage: {result.files:,} unique files checked…")
                        last_progress = now
            if result.limited:
                break
        except OSError as exc:
            problem(path, "Location could not be fully read: " + str(exc)[:250], True)
    check()
    volumes = []
    for anchor in sorted({Path(root.path).anchor for root in result.roots if Path(root.path).anchor}):
        try:
            usage = shutil.disk_usage(anchor)
            volumes.append(VolumeReading(anchor, usage.total, usage.used, usage.free))
        except OSError as exc:
            volumes.append(VolumeReading(anchor, error=str(exc)[:250]))
    result.volumes = tuple(volumes)
    result.measured_at = datetime.now().astimezone().isoformat(timespec="seconds")
    return result
