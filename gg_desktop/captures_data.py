"""Qt-free Captures discovery: known capture folders, game ownership evidence and image headers.

Scanning reads file metadata only. Image headers (width and height) are read in a separate, cancelable step.
Nothing is created, changed or removed here. Game ownership is only claimed from a Steam screenshot path
with an app ID, or from a folder name that exactly matches an installed game (labeled as unproven).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import stat
import time
import warnings

from core import OldFile, _has_reparse_component, _steam_roots, is_protected_path, safe_scan_root
from gg_desktop.models import _path_key
from recordings import RECORDING_EXTENSIONS, default_recording_roots, looks_like_recording
from screenshot_preview import ALLOWED_FORMATS, MAX_IMAGE_BYTES, MAX_IMAGE_PIXELS
from screenshots import SCREENSHOT_EXTENSIONS, _steam_screenshot_root, default_screenshot_roots, looks_like_screenshot

REPARSE = 0x400
MAX_CAPTURES = 40_000
MAX_DEPTH = 8
SKIP_DIRS = frozenset({"thumbnails", "thumbnail", "thumbs", "cache", ".cache", "$recycle.bin"})
UNVERIFIED = "Unverified"


@dataclass(frozen=True)
class Root:
    path: Path
    kind: str  # "Screenshots" or "Recordings"
    steam: bool = False
    user: bool = False

    @property
    def label(self):
        return f"{self.kind[:-1]} folder" + (" (added by you)" if self.user else " (Steam)" if self.steam else "")


@dataclass(eq=False)
class Capture:
    key: str
    path: str
    kind: str
    size: int
    modified: float
    game: str
    source: str
    old_file: OldFile
    root: str = ""
    verified: bool = False
    width: int | None = None
    height: int | None = None
    dims_failed: bool = False

    @property
    def record(self):
        return self.old_file

    @property
    def name(self):
        return Path(self.path).name

    @property
    def folder(self):
        return str(Path(self.path).parent)

    @property
    def removable(self):
        return self.old_file.hardlinks in (None, 1)

    @property
    def dimensions(self):
        return (self.width, self.height) if self.width and self.height else None


@dataclass
class CaptureReport:
    captures: list = field(default_factory=list)
    roots: list = field(default_factory=list)
    scanned_at: float = 0.0
    partial: bool = False
    problems: list = field(default_factory=list)

    def summary(self):
        shots = sum(c.kind == "Screenshots" for c in self.captures)
        videos = len(self.captures) - shots
        text = f"{shots:,} screenshots and {videos:,} recordings in {len(self.roots)} capture folders"
        if self.partial:
            text += " (stopped at the safety limit)"
        return text


def _reparse(state):
    return bool(getattr(state, "st_file_attributes", 0) & REPARSE)


def walk(root, extensions, canceled, *, direct_only=False, depth=MAX_DEPTH):
    """Ordinary files with a wanted extension. Links and reparse points are never entered or returned."""
    stack = [(Path(root), 0)]
    while stack:
        folder, level = stack.pop()
        if canceled():
            raise InterruptedError("Capture scan canceled")
        try:
            listing = os.scandir(folder)
        except OSError:
            continue
        with listing:
            for entry in listing:
                try:
                    if entry.is_symlink():
                        continue
                    state = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                if _reparse(state):
                    continue
                if stat.S_ISDIR(state.st_mode):
                    if not direct_only and level < depth and entry.name.casefold() not in SKIP_DIRS:
                        stack.append((Path(entry.path), level + 1))
                elif stat.S_ISREG(state.st_mode) and Path(entry.name).suffix.casefold() in extensions:
                    yield Path(entry.path)


def capture_roots(settings, *, steam_roots=None, home=None):
    """Known capture folders plus any the user added. Only existing, ordinary folders are returned."""
    steam = _steam_roots(list(settings.get("steam_extra_roots", []))) if steam_roots is None else list(steam_roots)
    roots, seen = [], set()

    def add(path, kind, user=False):
        path = Path(path)
        key = (kind, _path_key(str(path)))
        if key in seen:
            return
        trusted = kind == "Screenshots" and _steam_screenshot_root(path, steam)
        try:
            if _has_reparse_component(path) or not path.is_dir() or (not trusted and not safe_scan_root(path)):
                return
        except OSError:
            return
        seen.add(key)
        roots.append(Root(path, kind, trusted, user))

    for path in default_screenshot_roots(home, steam):
        add(path, "Screenshots")
    for path in settings.get("screenshot_roots", [])[:30]:
        if isinstance(path, str) and path.strip():
            add(Path(path).expanduser(), "Screenshots", True)
    for path in default_recording_roots(home):
        add(path, "Recordings")
    for path in settings.get("recording_roots", [])[:30]:
        if isinstance(path, str) and path.strip():
            add(Path(path).expanduser(), "Recordings", True)
    return roots


def steam_owner(path, steam_roots, games):
    """(app id, game or None) for a path inside <steam>/userdata/<account>/760/remote/<app>/screenshots."""
    key = _path_key(str(path))
    for steam in steam_roots:
        prefix = _path_key(str(Path(steam) / "userdata")).rstrip("\\") + "\\"
        if not key.startswith(prefix):
            continue
        parts = key[len(prefix):].split("\\")
        if len(parts) >= 6 and parts[0].isdecimal() and parts[1:3] == ["760", "remote"] and parts[3].isdecimal() \
                and parts[4] == "screenshots":
            game = next((g for g in games if str(getattr(g, "app_id", "")) == parts[3]), None)
            return parts[3], game
    return None, None


def owner(path, steam_roots, games):
    """(game, evidence, verified). Never guesses from a file name."""
    app_id, game = steam_owner(path, steam_roots, games)
    if app_id:
        if game is not None:
            return game.name, f"Steam screenshot folder for app ID {app_id}, an installed game.", True
        return f"Steam app {app_id}", f"Steam screenshot folder for app ID {app_id}. No installed game with this ID was found.", False
    parts = {p.casefold() for p in Path(path).parts[:-1]}
    for game in games:
        name = str(getattr(game, "name", "")).strip()
        if len(name) >= 4 and name.casefold() in parts:
            return name, "The folder name matches an installed game. This is a naming match, not proof.", False
    return UNVERIFIED, "No game link could be proven for this file.", False


def _make(path, kind, root, steam_roots, games):
    try:
        state = os.lstat(path)
    except OSError:
        return None
    if not stat.S_ISREG(state.st_mode) or _reparse(state):
        return None
    game, evidence, verified = owner(path, steam_roots, games)
    old = OldFile(str(path), state.st_size, state.st_mtime, state.st_dev, state.st_ino, state.st_mtime_ns, state.st_nlink)
    return Capture(_path_key(str(path)), str(path), kind, state.st_size, state.st_mtime, game, evidence, old,
                   str(root.path), verified)


def discover(settings, *, games=(), steam_roots=None, home=None, canceled=lambda: False,
             progress=lambda text: None, now=time.time, limit=MAX_CAPTURES):
    """List every screenshot and recording in the known and user-added capture folders."""
    steam = _steam_roots(list(settings.get("steam_extra_roots", []))) if steam_roots is None else list(steam_roots)
    roots = capture_roots(settings, steam_roots=steam, home=home)
    report = CaptureReport(roots=roots)
    seen = set()
    for index, root in enumerate(roots, 1):
        progress(f"Listing {root.path.name or root.path} ({index} of {len(roots)})")
        shots = root.kind == "Screenshots"
        extensions = SCREENSHOT_EXTENSIONS if shots else RECORDING_EXTENSIONS
        for path in walk(root.path, extensions, canceled, direct_only=root.steam):
            if shots and not looks_like_screenshot(path):
                continue
            if not shots and not looks_like_recording(path, root.path, user_selected=root.user):
                continue
            key = _path_key(str(path))
            if key in seen:
                continue
            if len(report.captures) >= limit:
                report.partial = True
                break
            capture = _make(path, root.kind, root, steam, games)
            if capture is not None:
                seen.add(key)
                report.captures.append(capture)
        if report.partial:
            break
    report.captures.sort(key=lambda c: (-c.modified, c.path.casefold()))
    report.scanned_at = now()
    return report


def from_inventory(inventory):
    """Captures the last PC scan already found. Used until a capture scan has run and for gaps in it."""
    output, seen = [], set()
    games = list(getattr(inventory, "steam", []))
    steam_roots = []
    for kind, files in (("Screenshots", getattr(inventory, "screenshots", [])), ("Recordings", getattr(inventory, "recordings", []))):
        for old in files:
            key = _path_key(old.path)
            if key in seen:
                continue
            seen.add(key)
            roots = {str(Path(g.library)) for g in games}
            game, evidence, verified = owner(old.path, [Path(r) for r in roots], games)
            output.append(Capture(key, old.path, kind, old.size, old.modified, game, evidence, old, "", verified))
    return output


def merge(scanned, inventory_captures):
    keys = {c.key for c in scanned}
    return list(scanned) + [c for c in inventory_captures if c.key not in keys]


def read_dimensions(captures, canceled=lambda: False, progress=lambda done, total: None, limit=MAX_CAPTURES):
    """Width and height from image headers only. Returns how many files were read."""
    try:
        from PIL import Image
    except ImportError:
        return 0
    todo = [c for c in captures if c.kind == "Screenshots" and c.width is None and not c.dims_failed][:limit]
    for index, capture in enumerate(todo, 1):
        if canceled():
            raise InterruptedError("Header reading canceled")
        path = Path(capture.path)
        try:
            if capture.size > MAX_IMAGE_BYTES or is_protected_path(path, []) or _has_reparse_component(path):
                raise ValueError("not readable")
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(path) as image:
                    if image.format not in ALLOWED_FORMATS or image.width * image.height > MAX_IMAGE_PIXELS:
                        raise ValueError("unsupported")
                    capture.width, capture.height = image.size
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            capture.dims_failed = True
        if index % 25 == 0:
            progress(index, len(todo))
    return len(todo)
