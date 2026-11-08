"""The seven More Tools that change or inspect Windows. No Qt here, and every outside effect goes through an
injectable backend so the logic is tested without touching a real PC.

Owner-approved exception (polish pass): Game Grave may change Windows settings and run commands, but only through
these tools, and only after the screen has named exactly what will change and the owner said yes. Every change is
written to the activity log by the caller. Nothing here uses the shell for anything the owner did not type, nothing
removes a folder tree, and nothing is called "safe" or "freed".
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

# Registry value kinds (the winreg constants, repeated so tests run on any OS).
REG_SZ, REG_BINARY, REG_DWORD = 1, 3, 4
HKCU, HKLM, HKCR = "HKCU", "HKLM", "HKCR"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_KEY_WOW = r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"
APPROVED = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved"
REPARSE = 0x400


# ------------------------------------------------------------------ backends
class WinRegistry:
    """The real Windows registry."""

    def __init__(self):
        import winreg
        self.w = winreg
        self.roots = {HKCU: winreg.HKEY_CURRENT_USER, HKLM: winreg.HKEY_LOCAL_MACHINE, HKCR: winreg.HKEY_CLASSES_ROOT}

    def read(self, hive, path, name):
        try:
            with self.w.OpenKey(self.roots[hive], path, 0, self.w.KEY_READ) as key:
                value, kind = self.w.QueryValueEx(key, name)
                return value, kind
        except OSError:
            return None

    def write(self, hive, path, name, value, kind):
        with self.w.CreateKeyEx(self.roots[hive], path, 0, self.w.KEY_SET_VALUE) as key:
            self.w.SetValueEx(key, name, 0, kind, value)

    def delete(self, hive, path, name):
        try:
            with self.w.OpenKey(self.roots[hive], path, 0, self.w.KEY_SET_VALUE) as key:
                self.w.DeleteValue(key, name)
        except OSError:
            pass

    def values(self, hive, path):
        found = []
        try:
            with self.w.OpenKey(self.roots[hive], path, 0, self.w.KEY_READ) as key:
                index = 0
                while True:
                    try:
                        name, value, kind = self.w.EnumValue(key, index)
                    except OSError:
                        break
                    found.append((name, value, kind))
                    index += 1
        except OSError:
            pass
        return found


def default_registry():
    return WinRegistry() if sys.platform == "win32" else None


@dataclass
class RunResult:
    code: int
    output: str
    timed_out: bool = False
    truncated: bool = False


class Runner:
    """Runs one program with an argument list (never through a shell unless the owner typed the shell line)."""

    def run(self, args, *, timeout=60, cwd=None, limit=64 * 1024):
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            done = subprocess.run(args, capture_output=True, timeout=timeout, cwd=cwd, creationflags=flags,
                                  stdin=subprocess.DEVNULL)
            raw = done.stdout + done.stderr
            code, timed_out = done.returncode, False
        except subprocess.TimeoutExpired as exc:
            raw = (exc.stdout or b"") + (exc.stderr or b"")
            code, timed_out = -1, True
        except OSError as exc:
            return RunResult(-1, "Could not start the program: " + str(exc))
        truncated = len(raw) > limit
        return RunResult(code, raw[:limit].decode("oem" if sys.platform == "win32" else "utf-8", "replace"),
                         timed_out, truncated)


def activity(kind, details, **extra):
    """One line in the activity log (the same log the Undo Center and More Tools read)."""
    from core import log_event
    log_event(kind, details, **extra)


# ------------------------------------------------------------------ 1. Windows Cleanup
MIN_AGE_DAYS = 2
PLAN_LIMIT = 6000


@dataclass
class CleanupItem:
    path: str
    size: int


@dataclass
class CleanupPlan:
    roots: list
    items: list = field(default_factory=list)
    truncated: bool = False

    @property
    def total(self):
        return sum(i.size for i in self.items)


def cleanup_roots(env=None):
    env = os.environ if env is None else env
    roots = []
    for value in (env.get("TEMP"), env.get("TMP")):
        if value:
            roots.append(Path(value))
    local = env.get("LOCALAPPDATA")
    if local:
        roots.append(Path(local) / "Temp")
        roots.append(Path(local) / "CrashDumps")
    unique, seen = [], set()
    for root in roots:
        key = os.path.normcase(os.path.abspath(str(root)))
        if key not in seen:
            seen.add(key)
            unique.append(Path(os.path.abspath(str(root))))
    return unique


def _is_link(entry_path, st):
    return os.path.islink(entry_path) or bool(getattr(st, "st_file_attributes", 0) & REPARSE)


def plan_cleanup(roots, *, now=None, min_age_days=MIN_AGE_DAYS, never_touch=(), limit=PLAN_LIMIT):
    """Files in the roots that have not changed for `min_age_days`. Links, protected paths and younger files are left alone."""
    from core import is_protected_path
    now = time.time() if now is None else now
    cutoff = now - min_age_days * 86400
    plan = CleanupPlan([str(r) for r in roots])
    stack = [Path(r) for r in roots if Path(r).is_dir() and not os.path.islink(r)]
    while stack:
        folder = stack.pop()
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for entry in entries:
            try:
                st = entry.stat(follow_symlinks=False)
                if _is_link(entry.path, st):
                    continue
                if entry.is_dir(follow_symlinks=False):
                    stack.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False) and st.st_mtime <= cutoff:
                    if is_protected_path(Path(entry.path), list(never_touch)):
                        continue
                    if len(plan.items) >= limit:
                        plan.truncated = True
                        return plan
                    plan.items.append(CleanupItem(entry.path, st.st_size))
            except OSError:
                continue
    return plan


@dataclass
class CleanupResult:
    removed: int = 0
    reported_bytes: int = 0
    skipped: int = 0
    notes: list = field(default_factory=list)


def _inside(path, roots):
    full = os.path.normcase(os.path.realpath(path))
    for root in roots:
        base = os.path.normcase(os.path.realpath(str(root))).rstrip("\\/") + os.sep
        if full.startswith(base):
            return True
    return False


def run_cleanup(items, roots, *, now=None, min_age_days=MIN_AGE_DAYS, canceled=lambda: False):
    """Permanently delete only the planned files, re-checking each one first. Files in use are skipped, not forced."""
    now = time.time() if now is None else now
    cutoff = now - min_age_days * 86400
    result = CleanupResult()
    parents = set()
    for item in items:
        if canceled():
            result.notes.append("Stopped when you asked. The rest was left alone.")
            break
        try:
            st = os.lstat(item.path)
            if (_is_link(item.path, st) or not _inside(item.path, roots) or st.st_mtime > cutoff
                    or not os.path.isfile(item.path)):
                result.skipped += 1
                continue
            os.unlink(item.path)
            result.removed += 1
            result.reported_bytes += st.st_size
            parents.add(os.path.dirname(item.path))
        except OSError:
            result.skipped += 1
    # Tidy folders the cleanup emptied. rmdir only ever removes an empty folder, never a tree.
    root_keys = {os.path.normcase(os.path.realpath(str(r))) for r in roots}
    for folder in sorted(parents, key=len, reverse=True):
        current = folder
        while os.path.normcase(os.path.realpath(current)) not in root_keys and _inside(current, roots):
            try:
                os.rmdir(current)
            except OSError:
                break
            current = os.path.dirname(current)
    return result


# ------------------------------------------------------------------ 2. Game Optimizer
HIGH_PERFORMANCE = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
GAME_MODE = (HKCU, r"Software\Microsoft\GameBar", "AutoGameModeEnabled")
DVR_STORE = (HKCU, r"System\GameConfigStore", "GameDVR_Enabled")
DVR_CAPTURE = (HKCU, r"Software\Microsoft\Windows\CurrentVersion\GameDVR", "AppCaptureEnabled")

OPTIMIZER_SETTINGS = (
    dict(key="game_mode", title="Turn Windows Game Mode on",
         detail="Sets one value for your account: Software\\Microsoft\\GameBar, AutoGameModeEnabled = 1.",
         targets=((GAME_MODE, 1),)),
    dict(key="background_recording", title="Turn background game recording off",
         detail="Sets two values for your account: System\\GameConfigStore, GameDVR_Enabled = 0 and "
                "Software\\Microsoft\\Windows\\CurrentVersion\\GameDVR, AppCaptureEnabled = 0.",
         targets=((DVR_STORE, 0), (DVR_CAPTURE, 0))),
    dict(key="power_plan", title="Switch to the High performance power plan",
         detail="Runs powercfg /setactive " + HIGH_PERFORMANCE + " (the High performance plan). Your current plan is "
                "remembered so Undo can switch back.",
         targets=()),
)


@dataclass
class SettingState:
    key: str
    title: str
    detail: str
    current: str
    applied: bool


def _dword(reg, target):
    got = reg.read(*target) if reg else None
    return None if got is None else got[0]


def active_plan(runner):
    """(guid, name) of the active Windows power plan, or None when powercfg cannot say."""
    result = runner.run(["powercfg", "/getactivescheme"], timeout=15)
    found = re.search(r"([0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})\s*(?:\(([^)]*)\))?", result.output)
    return (found.group(1).lower(), (found.group(2) or "").strip()) if result.code == 0 and found else None


def read_optimizer(reg, runner):
    states = []
    for spec in OPTIMIZER_SETTINGS:
        if spec["key"] == "power_plan":
            plan = active_plan(runner)
            current = (plan[1] or plan[0]) if plan else "Could not be read"
            applied = bool(plan and plan[0] == HIGH_PERFORMANCE)
        else:
            values = [_dword(reg, target) for target, _want in spec["targets"]]
            applied = all(v == want for v, (_t, want) in zip(values, spec["targets"]))
            current = ", ".join("not set" if v is None else str(v) for v in values)
            current = "Currently: " + current + (" (Windows default applies)" if all(v is None for v in values) else "")
        states.append(SettingState(spec["key"], spec["title"], spec["detail"], current, applied))
    return states


def _load_backup(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def has_backup(path):
    return bool(_load_backup(path).get("registry") or _load_backup(path).get("power_plan"))


def apply_optimizer(reg, runner, keys, backup_path):
    """Apply the chosen settings, remembering each previous value first (kept from the earliest apply until Undo)."""
    backup = _load_backup(backup_path) or {}
    saved = {(e["hive"], e["path"], e["name"]): e for e in backup.get("registry", [])}
    notes = []
    for spec in OPTIMIZER_SETTINGS:
        if spec["key"] not in keys:
            continue
        if spec["key"] == "power_plan":
            plan = active_plan(runner)
            if plan is None:
                notes.append("Power plan: could not read the current plan, so nothing was changed.")
                continue
            backup.setdefault("power_plan", plan[0])
            if plan[0] == HIGH_PERFORMANCE:
                notes.append("Power plan: already High performance.")
                continue
            done = runner.run(["powercfg", "/setactive", HIGH_PERFORMANCE], timeout=20)
            notes.append("Power plan: switched to High performance." if done.code == 0 else
                         "Power plan: Windows did not accept the change (" + (done.output.strip()[:120] or "no detail") + ").")
            continue
        if reg is None:
            notes.append(spec["title"] + ": the registry is not available on this PC.")
            continue
        for (hive, path, name), want in spec["targets"]:
            key = (hive, path, name)
            if key not in saved:
                before = reg.read(hive, path, name)
                saved[key] = dict(hive=hive, path=path, name=name, existed=before is not None,
                                  value=before[0] if before else None, kind=before[1] if before else REG_DWORD)
            reg.write(hive, path, name, want, REG_DWORD)
        notes.append(spec["title"] + ": done.")
    backup["registry"] = list(saved.values())
    backup["saved_at"] = datetime.now().isoformat(timespec="seconds")
    Path(backup_path).parent.mkdir(parents=True, exist_ok=True)
    Path(backup_path).write_text(json.dumps(backup, indent=2), encoding="utf-8")
    return notes


def undo_optimizer(reg, runner, backup_path):
    """Put back exactly what was there before the first apply, then forget the backup."""
    backup = _load_backup(backup_path)
    notes = []
    for entry in backup.get("registry", []):
        if reg is None:
            break
        if entry.get("existed"):
            reg.write(entry["hive"], entry["path"], entry["name"], entry["value"], entry.get("kind", REG_DWORD))
        else:
            reg.delete(entry["hive"], entry["path"], entry["name"])
        notes.append(f"Restored {entry['name']}.")
    plan = backup.get("power_plan")
    if plan:
        done = runner.run(["powercfg", "/setactive", plan], timeout=20)
        notes.append("Power plan restored." if done.code == 0 else "Power plan could not be restored automatically.")
    if notes or backup:
        try:
            Path(backup_path).unlink()
        except OSError:
            pass
    return notes or ["Nothing to undo."]


# ------------------------------------------------------------------ 3. Memory Optimizer
PROTECTED_PROCESSES = frozenset(name.casefold() for name in (
    "System", "System Idle Process", "Registry", "Memory Compression", "smss.exe", "csrss.exe", "wininit.exe",
    "services.exe", "lsass.exe", "winlogon.exe", "svchost.exe", "dwm.exe", "explorer.exe", "fontdrvhost.exe",
    "sihost.exe", "taskhostw.exe", "ctfmon.exe", "conhost.exe", "RuntimeBroker.exe", "SearchHost.exe",
    "ShellExperienceHost.exe", "StartMenuExperienceHost.exe", "TextInputHost.exe", "audiodg.exe", "spoolsv.exe",
    "MsMpEng.exe", "SecurityHealthService.exe", "SecurityHealthSystray.exe", "wudfhost.exe", "dllhost.exe",
    "lsm.exe", "tasklist.exe", "taskkill.exe", "cmd.exe", "powershell.exe", "WmiPrvSE.exe", "OneDrive.exe",
    "Game Grave.exe", "GameGrave.exe", "python.exe", "pythonw.exe"))


@dataclass
class Proc:
    name: str
    pid: int
    kb: int


def list_processes(runner, *, own_pid=None):
    """Apps running in your own session (not services), largest memory first. Core Windows and Game Grave are left out."""
    own_pid = os.getpid() if own_pid is None else own_pid
    result = runner.run(["tasklist", "/FO", "CSV", "/NH"], timeout=30)
    if result.code != 0:
        return []
    procs = []
    for row in csv.reader(io.StringIO(result.output)):
        if len(row) < 5:
            continue
        name, pid, session, _num, mem = row[:5]
        digits = re.sub(r"[^0-9]", "", mem)
        if (session.casefold() != "console" or not pid.isdigit() or int(pid) == own_pid
                or name.casefold() in PROTECTED_PROCESSES or not digits):
            continue
        procs.append(Proc(name, int(pid), int(digits)))
    return sorted(procs, key=lambda p: -p.kb)


def close_processes(runner, pids):
    """Ask each app to close normally (no forcing). Returns (pid, closed_message) lines from what Windows reported."""
    notes = []
    for pid in pids:
        done = runner.run(["taskkill", "/PID", str(int(pid))], timeout=20)
        notes.append((int(pid), "Asked to close." if done.code == 0 else
                      (done.output.strip().splitlines() or ["Windows did not close it."])[0][:140]))
    return notes


# ------------------------------------------------------------------ 4. Startup Manager
@dataclass
class StartupEntry:
    name: str
    command: str
    source: str          # "Run" or "Startup folder"
    scope: str           # "user" or "all users"
    enabled: bool
    can_toggle: bool
    approved_key: str = ""


def _approved_enabled(reg, hive, kind_key, name):
    got = reg.read(hive, APPROVED + "\\" + kind_key, name) if reg else None
    if got is None or not isinstance(got[0], (bytes, bytearray)) or not got[0]:
        return True
    return got[0][0] % 2 == 0


def list_startup(reg, env=None):
    env = os.environ if env is None else env
    entries = []
    if reg is not None:
        for hive, path, scope, toggle in ((HKCU, RUN_KEY, "user", True), (HKLM, RUN_KEY, "all users", False),
                                          (HKLM, RUN_KEY_WOW, "all users", False)):
            for name, value, _kind in reg.values(hive, path):
                if not name:
                    continue
                entries.append(StartupEntry(name, str(value), "Run", scope,
                                            _approved_enabled(reg, hive, "Run", name), toggle, "Run"))
    appdata, program = env.get("APPDATA"), env.get("PROGRAMDATA")
    for base, scope, toggle in ((appdata, "user", True), (program, "all users", False)):
        if not base:
            continue
        folder = Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        try:
            files = sorted(f for f in folder.iterdir() if f.is_file() and f.name.casefold() != "desktop.ini")
        except OSError:
            continue
        for item in files:
            entries.append(StartupEntry(item.name, str(item), "Startup folder", scope,
                                        _approved_enabled(reg, HKCU if toggle else HKLM, "StartupFolder", item.name),
                                        toggle, "StartupFolder"))
    return sorted(entries, key=lambda e: (e.scope != "user", e.name.casefold()))


def set_startup_enabled(reg, entry, enabled):
    """Flip the same switch Task Manager's Startup tab uses. The entry itself is never deleted or edited."""
    if reg is None or not entry.can_toggle:
        raise ValueError("Changing this entry needs administrator rights, so Game Grave leaves it alone.")
    if enabled:
        data = bytes([2]) + bytes(11)
    else:
        filetime = int((time.time() + 11644473600) * 10_000_000)
        data = bytes([3, 0, 0, 0]) + filetime.to_bytes(8, "little")
    reg.write(HKCU, APPROVED + "\\" + entry.approved_key, entry.name, data, REG_BINARY)


# ------------------------------------------------------------------ 5. Command Runner
PRESETS = (
    ("Show network details", "ipconfig /all"),
    ("Test the internet connection", "ping -n 4 1.1.1.1"),
    ("List running programs", "tasklist"),
    ("Show Windows version", "ver"),
    ("Show who you are signed in as", "whoami"),
    ("Show disk drives and free space", "powershell -NoProfile -Command \"Get-PSDrive -PSProvider FileSystem | "
                                         "Format-Table Name,Used,Free -AutoSize\""),
)
MAX_COMMAND = 2000


def validate_command(text):
    """A reason the line cannot be run, or an empty string."""
    text = (text or "").strip()
    if not text:
        return "Type a command first."
    if len(text) > MAX_COMMAND:
        return "That command is too long."
    if any(ch in text for ch in "\r\n\x00"):
        return "Use a single line."
    return ""


def command_args(text):
    return ["cmd.exe", "/d", "/s", "/c", text.strip()]


def run_command(runner, text, *, cwd=None, timeout=120):
    reason = validate_command(text)
    if reason:
        raise ValueError(reason)
    return runner.run(command_args(text), timeout=timeout, cwd=cwd)


# ------------------------------------------------------------------ 6. File Associations
COMMON_EXTENSIONS = (".zip", ".7z", ".rar", ".json", ".ini", ".cfg", ".log", ".txt", ".xml", ".esp", ".esm", ".bsa",
                     ".ba2", ".pak", ".sav", ".exe")


@dataclass
class Association:
    ext: str
    prog_id: str
    app: str
    command: str
    source: str


def normalize_extension(text):
    text = (text or "").strip().lower()
    if text.startswith("*"):
        text = text[1:]
    if text and not text.startswith("."):
        text = "." + text
    return text if re.fullmatch(r"\.[a-z0-9_+\-]{1,20}", text) else ""


def read_association(reg, ext):
    ext = normalize_extension(ext)
    if not ext:
        raise ValueError("Type an extension such as .zip or .json.")
    if reg is None:
        return Association(ext, "", "Unavailable", "", "The registry is not available on this PC")
    chosen = reg.read(HKCU, rf"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\{ext}\UserChoice", "ProgId")
    prog_id, source = (chosen[0], "You chose this in Windows") if chosen else ("", "")
    if not prog_id:
        default = reg.read(HKCR, ext, "")
        if default and default[0]:
            prog_id, source = default[0], "Windows default"
    if not prog_id:
        return Association(ext, "", "No app is set", "", "Nothing opens this type yet")
    app = reg.read(HKCR, prog_id, "FriendlyTypeName") or reg.read(HKCR, prog_id, "") or (prog_id,)
    command = reg.read(HKCR, prog_id + r"\shell\open\command", "") or ("",)
    return Association(ext, str(prog_id), str(app[0] or prog_id), str(command[0]), source)


# ------------------------------------------------------------------ 7. Junction Manager
@dataclass
class Link:
    path: str
    target: str
    kind: str      # "junction" or "symlink"
    exists: bool


def _strip_prefix(text):
    return text[4:] if text.startswith("\\\\?\\") and not text.startswith("\\\\?\\UNC") else text


def link_kind(path):
    """'junction', 'symlink' or '' for a real file or folder."""
    try:
        if os.path.islink(path):
            return "symlink"
        isjunction = getattr(os.path, "isjunction", None)
        if isjunction and isjunction(path):
            return "junction"
    except OSError:
        pass
    return ""


def link_target(path):
    try:
        return _strip_prefix(os.readlink(path))
    except (OSError, ValueError):
        return ""


def scan_links(root, *, depth=3, limit=500):
    """Junctions and symbolic links under a folder. Links are listed, never followed."""
    found, stack = [], [(Path(root), 0)]
    while stack and len(found) < limit:
        folder, level = stack.pop()
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for entry in entries:
            kind = link_kind(entry.path)
            if kind:
                target = link_target(entry.path)
                found.append(Link(entry.path, target, kind, bool(target) and os.path.exists(entry.path)))
                if len(found) >= limit:
                    break
            elif level < depth:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append((Path(entry.path), level + 1))
                except OSError:
                    continue
    return sorted(found, key=lambda l: l.path.casefold())


def _in_never_touch(path, rules):
    """True when the path is inside a folder the owner listed under Never Touch."""
    for rule in rules or ():
        if not isinstance(rule, str) or not rule.strip():
            continue
        try:
            base = os.path.normcase(os.path.abspath(rule))
            if os.path.normcase(os.path.commonpath([os.path.abspath(path), base])) == base:
                return True
        except ValueError:
            continue
    return False


def check_new_link(link, target, never_touch=()):
    """A plain-English reason a junction cannot be made here, or an empty string."""
    link, target = os.path.abspath(link), os.path.abspath(target)
    if not os.path.isdir(target):
        return "The folder it should point to does not exist."
    if os.path.lexists(link):
        return "Something already exists at the new link's location."
    if not os.path.isdir(os.path.dirname(link)):
        return "The folder that should hold the link does not exist."
    if os.path.normcase(link) == os.path.normcase(target):
        return "A link cannot point at itself."
    if _in_never_touch(link, never_touch):
        return "That location is protected by your Never Touch rules."
    return ""


def create_junction(runner, link, target, *, never_touch=()):
    reason = check_new_link(link, target, never_touch)
    if reason:
        raise ValueError(reason)
    done = runner.run(["cmd.exe", "/d", "/c", "mklink", "/J", os.path.abspath(link), os.path.abspath(target)], timeout=30)
    if done.code != 0 or not link_kind(link):
        raise ValueError("Windows did not create the junction. " + done.output.strip()[:200])
    return os.path.abspath(link)


def remove_link(path, *, never_touch=()):
    """Remove the link itself. Refuses a real folder or file, and never touches what the link points to."""
    kind = link_kind(path)
    if not kind:
        raise ValueError("That is a real folder or file, not a link, so Game Grave will not remove it.")
    if _in_never_touch(path, never_touch):
        raise ValueError("That location is protected by your Never Touch rules.")
    target = link_target(path)
    try:
        os.rmdir(path)   # a junction or directory link on Windows; removes only the link
    except OSError:
        os.unlink(path)  # a file or directory link on other systems
    return target, bool(target) and os.path.exists(target)
