"""Registry Cleanup, the Windows side: read the registry (64-bit view, WOW6432Node written out), back up keys with
`reg export`, remove entries (your own directly, all-users ones through one Windows prompt), and undo with `reg import`.
Every removal checks again that the entry's file is still missing; a file that has come back is left alone."""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from gg_desktop import registry_core as rc

FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class RegistryError(RuntimeError):
    pass


# ---------------------------------------------------------------- reading
class WinReg:
    def __init__(self):
        import winreg
        self.w = winreg
        self.hives = {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}
        self.view = winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0)

    def _open(self, hive, key):
        return self.w.OpenKey(self.hives[hive], key, 0, self.view)

    def subkeys(self, hive, key):
        out = []
        try:
            with self._open(hive, key) as handle:
                i = 0
                while True:
                    try:
                        out.append(self.w.EnumKey(handle, i))
                    except OSError:
                        break
                    i += 1
                    if i > 20000:
                        break
        except OSError:
            return []
        return out

    def values(self, hive, key):
        out = {}
        try:
            with self._open(hive, key) as handle:
                i = 0
                while True:
                    try:
                        name, data, kind = self.w.EnumValue(handle, i)
                    except OSError:
                        break
                    if kind in (self.w.REG_SZ, self.w.REG_EXPAND_SZ):
                        out[name] = data
                    elif kind == self.w.REG_DWORD:
                        out[name] = str(data)
                    else:
                        out[name] = ""
                    i += 1
                    if i > 50000:
                        break
        except OSError:
            return {}
        return out


def _drive_ok(letter):
    """Present and a fixed (internal) drive: removable, network and missing drives never make an entry 'missing'."""
    try:
        import ctypes
        kind = ctypes.windll.kernel32.GetDriveTypeW(f"{letter}:\\")
        return kind == 3 and os.path.exists(f"{letter}:\\")       # DRIVE_FIXED
    except Exception:
        return False


def checks():
    return rc.Checks(exists=os.path.exists, drive_ok=_drive_ok, expand=os.path.expandvars,
                     windows_dir=os.environ.get("SystemRoot", r"C:\Windows"))


def scan(progress=None):
    if os.name != "nt":
        raise RegistryError("This works on Windows only.")
    return rc.scan(WinReg(), checks(), progress)


# ---------------------------------------------------------------- backing up
def backup_root():
    from core import config_dir
    return Path(config_dir()) / "registry_backups"


def backup(findings, root=None, runner=subprocess.run):
    """Exports every key the findings touch into a new dated folder, plus a list of exactly what will change.
    Returns the folder. Raises if any export fails, so nothing changes without its backup."""
    base = Path(root or backup_root()) / time.strftime("%Y-%m-%d %H-%M-%S")
    folder, n = base, 1
    while folder.exists():
        n += 1
        folder = base.with_name(f"{base.name} ({n})")
    folder.mkdir(parents=True)
    keys = sorted({f.full_key for f in findings})
    files = []
    for i, key in enumerate(keys, 1):
        path = folder / f"{i:03d}.reg"
        result = runner(["reg", "export", key, str(path), "/y"], capture_output=True, text=True, timeout=60,
                        creationflags=FLAGS)
        if getattr(result, "returncode", 1) != 0 or not path.is_file():
            for done in folder.glob("*.reg"):          # an incomplete backup is not kept as if it were one
                done.unlink(missing_ok=True)
            folder.rmdir()
            raise RegistryError(f"Couldn't back up {key}, so nothing was changed.")
        files.append({"file": path.name, "key": key, "hive": "HKLM" if key.startswith("HKEY_LOCAL") else "HKCU"})
    (folder / "changes.json").write_text(json.dumps({
        "when": time.time(), "backups": files,
        "changes": [{"key": f.full_key, "value": f.value, "action": f.action, "target": f.target, "category": f.category,
                     "name": f.name} for f in findings]}, indent=1), encoding="utf-8")
    (folder / "changes.txt").write_text("\n".join(rc.what_changes(f) for f in findings), encoding="utf-8")
    return folder


def backups(root=None):
    """Backup folders, newest first: [(folder, number of changes, undone)]."""
    out = []
    base = Path(root or backup_root())
    try:
        folders = sorted((p for p in base.iterdir() if (p / "changes.json").is_file()), reverse=True)
    except OSError:
        return []
    for folder in folders[:30]:
        try:
            data = json.loads((folder / "changes.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out.append((folder, len(data.get("changes", [])), bool(data.get("undone"))))
    return out


# ---------------------------------------------------------------- changing
def _ps(text):
    return "'" + str(text).replace("'", "''") + "'"


def elevated_script(findings, restore_point):
    """One PowerShell run (through the Windows prompt) for a restore point and the all-users entries."""
    lines = ["$ErrorActionPreference = 'Continue'", "$out = @{ restore = ''; done = @(); kept = @(); failed = @() }"]
    if restore_point:
        lines += ["try { Checkpoint-Computer -Description 'Game Grave registry cleanup' -RestorePointType MODIFY_SETTINGS "
                  "-ErrorAction Stop; $out.restore = 'made' } catch { $out.restore = $_.Exception.Message }"]
    for f in findings:
        path = "Registry::" + f.full_key
        if f.action == "delete_key":
            change = f"Remove-Item -LiteralPath {_ps(path)} -Recurse -Force -ErrorAction Stop"
        elif f.action == "delete_value":
            change = f"Remove-ItemProperty -LiteralPath {_ps(path)} -Name {_ps(f.value)} -Force -ErrorAction Stop"
        else:
            continue
        lines.append(f"if (Test-Path -LiteralPath {_ps(f.target)}) {{ $out.kept += {_ps(f.ident)} }} else {{ "
                     f"try {{ {change}; $out.done += {_ps(f.ident)} }} catch {{ $out.failed += {_ps(f.ident)} }} }}")
    lines.append("$out | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath '__RESULT__' -Encoding UTF8")
    return "\n".join(lines)


def _delete_tree(winreg, root, key):
    with winreg.OpenKey(root, key, 0, winreg.KEY_ALL_ACCESS | getattr(winreg, "KEY_WOW64_64KEY", 0)) as handle:
        while True:
            try:
                child = winreg.EnumKey(handle, 0)
            except OSError:
                break
            _delete_tree(winreg, root, key + "\\" + child)
    winreg.DeleteKeyEx(root, key, getattr(winreg, "KEY_WOW64_64KEY", 0), 0)


def change_own(findings, exists=os.path.exists):
    """Your own (HKCU) entries, changed directly. Returns (done, kept, failed) as idents."""
    import winreg
    done, kept, failed = [], [], []
    root = winreg.HKEY_CURRENT_USER
    for f in findings:
        if exists(f.target):
            kept.append(f.ident)
            continue
        try:
            if f.action == "delete_key":
                _delete_tree(winreg, root, f.key)
            else:
                with winreg.OpenKey(root, f.key, 0, winreg.KEY_SET_VALUE) as handle:
                    if f.action == "delete_value":
                        winreg.DeleteValue(handle, f.value)
                    elif f.action == "clear_value":
                        winreg.SetValueEx(handle, f.value or "", 0, winreg.REG_SZ, "")
            done.append(f.ident)
        except OSError:
            failed.append(f.ident)
    return done, kept, failed


def fix(findings, restore_point=True, root=None, on_step=None):
    """Back up, then (one Windows prompt when needed) a restore point and all-users entries, then your own entries.
    Returns a dict: folder, restore ('made' / reason / ''), done, kept, failed."""
    from gg_desktop import upkeep_core
    findings = [f for f in findings if f.fixable][:rc.MAX_FIX]
    if not findings:
        raise RegistryError("Nothing to change.")
    if on_step:
        on_step("Backing up the registry keys…")
    folder = backup(findings, root)
    result = {"folder": str(folder), "restore": "", "done": [], "kept": [], "failed": []}
    machine = [f for f in findings if f.hive == "HKLM"]
    if machine or restore_point:
        if on_step:
            on_step("Waiting for you to allow the change in the Windows prompt…" if machine else
                    "Making a System Restore point (Windows asks to allow it)…")
        raw = upkeep_core.run_elevated(elevated_script(machine, restore_point), timeout=900)
        if not raw:
            raise RegistryError("The Windows prompt was declined or closed, so nothing was changed. The backup was "
                                f"kept in {folder}.")
        try:
            data = json.loads(raw)
        except ValueError:
            data = {}
        result["restore"] = str(data.get("restore") or "")
        for name in ("done", "kept", "failed"):
            got = data.get(name) or []
            result[name] += [got] if isinstance(got, str) else list(got)
    if on_step:
        on_step("Removing your own entries…")
    done, kept, failed = change_own([f for f in findings if f.hive == "HKCU"])
    result["done"] += done
    result["kept"] += kept
    result["failed"] += failed
    _note(folder, result)
    return result


def _note(folder, result):
    try:
        path = Path(folder) / "changes.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["result"] = {k: result[k] for k in ("restore", "done", "kept", "failed")}
        path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    except (OSError, ValueError):
        pass


def undo(folder, runner=subprocess.run):
    """Puts back everything a fix removed by importing its backups (all-users keys through the Windows prompt)."""
    from gg_desktop import upkeep_core
    folder = Path(folder)
    data = json.loads((folder / "changes.json").read_text(encoding="utf-8"))
    own = [b for b in data.get("backups", []) if b.get("hive") == "HKCU"]
    machine = [b for b in data.get("backups", []) if b.get("hive") == "HKLM"]
    failed = []
    for b in own:
        result = runner(["reg", "import", str(folder / b["file"])], capture_output=True, text=True, timeout=60,
                        creationflags=FLAGS)
        if getattr(result, "returncode", 1) != 0:
            failed.append(b["key"])
    if machine:
        script = "\n".join(["$bad = @()"] + [
            f"& reg.exe import {_ps(folder / b['file'])} 2>$null; if ($LASTEXITCODE -ne 0) {{ $bad += {_ps(b['key'])} }}"
            for b in machine] + ["@{ failed = $bad } | ConvertTo-Json | Set-Content -LiteralPath '__RESULT__' -Encoding UTF8"])
        raw = upkeep_core.run_elevated(script, timeout=600)
        if not raw:
            raise RegistryError("The Windows prompt was declined, so the all-users entries were not put back.")
        try:
            got = json.loads(raw).get("failed") or []
        except ValueError:
            got = []
        failed += [got] if isinstance(got, str) else list(got)
    data["undone"] = time.time()
    (folder / "changes.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    return failed
