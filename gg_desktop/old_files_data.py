"""Old Files drive/folder scans. Metadata only; shared safety engines stay intact."""
from __future__ import annotations

from dataclasses import dataclass, field
import ctypes
import os
from pathlib import Path
import stat
import time

from core import OldFile, _has_reparse_component, is_protected_path, is_unchanged, safe_scan_root
from cleanup_actions import recycle_old_files

MAX_ENTRIES = 1000000
MAX_RESULTS = 100000
MAX_DEPTH = 64
GUARDED_NAMES = {
    "windows", "windows.old", "program files", "program files (x86)", "programdata", "appdata",
    "$recycle.bin", "system volume information", "recovery", "efi", "config.msi", "msocache",
    ".git", ".svn", "node_modules", "games", "xboxgames", "xbox", "gog games", "riot games",
    "epic games", "ubisoft game launcher", "steam", "ea games", "battlenet", "battle.net",
    "bin", "sbin", "dev", "proc", "sys", "etc", "usr", "lib", "lib64", "var", "snap",
}
SKIP_ATTRIBUTES = 0x2 | 0x4 | 0x1000 | 0x40000 | 0x400000


def key(path):
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def within(path, root):
    try:
        return os.path.commonpath((key(path), key(root))) == key(root)
    except (OSError, ValueError):
        return False


def ordinary_folder(path):
    try:
        return not _has_reparse_component(Path(path)) and stat.S_ISDIR(Path(path).lstat().st_mode)
    except (OSError, ValueError):
        return False


def fingerprint(path):
    if not ordinary_folder(path):
        raise ValueError("The scan location is missing, unreadable or redirected.")
    info = Path(path).stat()
    return info.st_dev, info.st_ino


@dataclass(frozen=True)
class Drive:
    root: str
    label: str
    kind: str = "Local drive"


def local_drives():
    """Enumerate local/removable volumes without probing network shares."""
    if os.name == "nt":
        kernel = ctypes.windll.kernel32
        kernel.GetLogicalDrives.restype = ctypes.c_ulong
        kernel.GetDriveTypeW.argtypes = [ctypes.c_wchar_p]
        mask = kernel.GetLogicalDrives()
        result = []
        for index in range(26):
            if mask & (1 << index):
                root = chr(65 + index) + ":\\"
                kind = kernel.GetDriveTypeW(root)
                if kind in (2, 3):
                    label = "Removable drive" if kind == 2 else "Local drive"
                    result.append(Drive(root, root + "  •  " + label, label))
        return result
    # Portable preview fallback. Windows uses the actual drive list above.
    result = [Drive("/", "/  •  Local filesystem")]
    for base in (Path("/mnt"), Path("/media"), Path("/run/media") / Path.home().name):
        if ordinary_folder(base):
            try:
                for path in list(base.iterdir())[:50]:
                    if ordinary_folder(path) and os.path.ismount(path):
                        result.append(Drive(str(path), str(path) + "  •  Mounted drive"))
            except OSError:
                continue
    return result


def protected_roots(inventory, settings):
    roots = list(settings.get("never_touch", []))
    roots += [g.install_path for g in inventory.games]
    roots += [str(getattr(item, "path", "")) for item in (*inventory.mods, *inventory.saves)]
    roots += [os.environ[name] for name in ("WINDIR", "SYSTEMROOT", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMDATA", "APPDATA", "LOCALAPPDATA") if os.environ.get(name)]
    return tuple(dict.fromkeys(str(p) for p in roots if isinstance(p, (str, Path)) and str(p).strip()))


def blocked(path, protections):
    path = Path(path)
    return (is_protected_path(path, list(protections))
            or any(part.casefold() in GUARDED_NAMES or part.startswith("$") for part in path.parts))


@dataclass(frozen=True)
class ScanPlan:
    root: str
    mode: str
    days: int
    roots: tuple[str, ...]
    identity: tuple[int, int]
    protections: tuple[str, ...]


@dataclass
class ScanResult:
    plan: ScanPlan
    files: list[OldFile] = field(default_factory=list)
    visited: int = 0
    folders: int = 0
    skipped: int = 0
    issues: list[str] = field(default_factory=list)
    limited: bool = False
    scanned_at: float = field(default_factory=time.time)
    origin: str = "Old Files scan"

    def summary(self):
        prefix = "Partial scan. " if self.limited else "Scan finished. "
        return (f"{prefix}{len(self.files):,} files at least {self.plan.days} days old; "
                f"{self.visited:,} entries checked, {self.folders:,} folders inspected, {self.skipped:,} protected or excluded entries. "
                "Age does not prove a file is unused.")


def make_plan(root, mode, days, protections=(), *, drives=None, folder="", home=None):
    root = str(Path(root).absolute())
    if mode not in ("folder", "quick", "full") or type(days) is not int or not 1 <= days <= 10000:
        raise ValueError("Choose a supported scan mode and age threshold.")
    if mode == "folder":
        if not safe_scan_root(Path(root)) or blocked(root, protections):
            raise ValueError("Choose an ordinary folder outside games, saves, mod managers and system locations.")
        roots = [root]
    else:
        available = local_drives() if drives is None else drives
        if not any(key(d.root) == key(root) for d in available):
            raise ValueError("This drive is no longer in the local drive list. Refresh drives or choose another drive.")
        if mode == "full":
            roots = [root]
        else:
            user = Path.home() if home is None else Path(home)
            candidates = [str(user / name) for name in ("Downloads", "Documents")]
            candidates += [str(Path(root) / name) for name in ("Downloads", "Documents")]
            if folder:
                candidates.insert(0, str(folder))
            roots = [p for p in candidates if within(p, root) and safe_scan_root(Path(p)) and not blocked(p, protections)]
            roots = [p for i, p in enumerate(roots) if not any(key(p) == key(other) or within(p, other) for other in roots[:i])]
            if not roots:
                raise ValueError("No Downloads, Documents or selected scan folder was found on this drive. Choose a folder or enable Full scan.")
    return ScanPlan(root, mode, days, tuple(roots), fingerprint(root), tuple(protections))


def validate_plan(plan):
    if fingerprint(plan.root) != plan.identity:
        raise ValueError("The original scan location changed or the drive was replaced. Scan again.")


def scan_files(plan, canceled=lambda: False, progress=lambda *_: None):
    validate_plan(plan)
    result = ScanResult(plan)
    cutoff, last_update = time.time() - plan.days * 86400, 0.0
    stack = [(Path(root), 0) for root in reversed(plan.roots)]
    seen = set()
    def check():
        if canceled():
            raise InterruptedError("Old Files scan canceled. Previous results retained.")
    def issue(message):
        result.limited = True
        if len(result.issues) < 40:
            result.issues.append(message)
    while stack:
        check()
        folder, depth = stack.pop()
        if blocked(folder, plan.protections):
            result.skipped += 1
            continue
        if not ordinary_folder(folder):
            result.skipped += 1
            issue("Folder became unavailable or redirected: " + str(folder))
            continue
        if key(folder) in seen:
            continue
        seen.add(key(folder))
        result.folders += 1
        try:
            with os.scandir(folder) as stream:
                for item in stream:
                    check()
                    result.visited += 1
                    if result.visited > MAX_ENTRIES:
                        issue("Entry limit reached. Choose a smaller folder to continue reviewing this drive.")
                        stack.clear()
                        break
                    path = Path(item.path)
                    try:
                        # Windows DirEntry.stat caches zero device/inode/link
                        # fields. lstat supplies the full identity used by the
                        # volume boundary, hardlink and later recovery checks.
                        info = path.lstat()
                        if (blocked(path, plan.protections) or _has_reparse_component(path) or stat.S_ISLNK(info.st_mode)
                                or getattr(info, "st_file_attributes", 0) & (SKIP_ATTRIBUTES | 0x400)):
                            result.skipped += 1
                            continue
                        if stat.S_ISDIR(info.st_mode):
                            if depth < MAX_DEPTH and info.st_dev == plan.identity[0]:
                                stack.append((path, depth + 1))
                            else:
                                issue("A nested volume or depth limit was excluded: " + str(path))
                        elif stat.S_ISREG(info.st_mode) and info.st_mtime <= cutoff:
                            if info.st_nlink != 1:
                                result.skipped += 1
                                continue
                            result.files.append(OldFile(str(path), info.st_size, info.st_mtime,
                                info.st_dev, info.st_ino, info.st_mtime_ns, info.st_nlink))
                            if len(result.files) >= MAX_RESULTS:
                                issue("Result limit reached. Choose a smaller folder for the remaining files.")
                                stack.clear()
                                break
                    except (OSError, ValueError):
                        issue("Entry became unavailable: " + str(path))
                    if time.monotonic() - last_update > .15:
                        progress(0, f"{result.visited:,} entries checked • {len(result.files):,} old files • {folder}")
                        last_update = time.monotonic()
        except OSError:
            issue("Folder could not be read: " + str(folder))
    check()
    validate_plan(plan)
    result.files.sort(key=lambda f: (-f.size, f.path.casefold()))
    result.scanned_at = time.time()
    progress(100, result.summary())
    return result


def review_reason(file, result, protections, *, live=False):
    if blocked(file.path, (*result.plan.protections, *protections)):
        return "Protected by game, manager, system or Never Touch rules"
    if not any(within(file.path, root) for root in result.plan.roots):
        return "Outside the reviewed scan scope"
    parent = Path(file.path).parent
    if (key(parent) in (key(parent.anchor), key(Path.home()))) or live and not safe_scan_root(parent):
        return "Review only: choose an ordinary parent folder before recycling"
    if file.hardlinks != 1:
        return "Protected: file identity or link count is unverified"
    return "Reviewable (not proven unused)"


def recycle_reviewed(result, files, protections, session, progress=lambda *_: None):
    """Adapt drive results to existing per-folder Windows recovery checks."""
    files = tuple(files)
    if not 1 <= len(files) <= 200:
        raise ValueError("Select between 1 and 200 individual files.")
    accepted = {key(f.path): f for f in result.files}
    outcome = {"completed": 0, "skipped": [], "recovery_warnings": 0, "requested": len(files)}
    rules = tuple(dict.fromkeys((*result.plan.protections, *protections)))
    for index, file in enumerate(files, 1):
        validate_plan(result.plan)
        if accepted.get(key(file.path)) != file or review_reason(file, result, rules, live=True) != "Reviewable (not proven unused)":
            raise ValueError("The selected file is protected or no longer belongs to this scan. Rescan before reviewing it.")
        # The unchanged worker rechecks identity, age, protections, ancestry and
        # the real Windows recovery canary. No drive-root exemption is granted.
        item = recycle_old_files((file,), rules, session, review_root=Path(file.path).parent,
                                 min_age_days=result.plan.days)
        outcome["completed"] += item["completed"]
        outcome["skipped"].extend(item["skipped"])
        outcome["recovery_warnings"] += item["recovery_warnings"]
        progress(int(index * 100 / len(files)), f"Reviewed {index} of {len(files)} individual files")
    return outcome
