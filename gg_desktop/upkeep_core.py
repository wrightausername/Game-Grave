"""Drivers & Startup (Hardware tab). Pure parsing and planning, plus the few Windows calls, which run only on a press.

Owner instruction (2026-11-11): "a section that detects outdated drivers and a way to update them all along with what starts
up automatically when windows does so i can turn off unwanted apps easily".

Drivers, honestly:
  * "Update available" comes only from Windows Update's own driver search (the Windows Update Agent), the same list
    Settings > Windows Update > Optional updates shows. Game Grave does not guess that a driver is outdated.
  * The installed list shows each driver's date. An old date is a hint, never proof a newer one exists.
  * Graphics card makers often publish newer drivers than Windows Update. The tab links to the maker's own app; it
    does not download from anywhere else.
  * Installing uses Windows Update itself, in a separate PowerShell that Windows asks you to allow (UAC). Nothing is
    installed without that prompt, and every attempt is written to the activity log.

Startup, honestly:
  * Lists exactly what Task Manager's Startup apps lists from: the Run keys (for you, and for all users) and the two
    Startup folders. Programs started by scheduled tasks, services or Store apps are not listed, and the tab says so.
  * The switch is Task Manager's own switch (the StartupApproved value). Turning an app off never deletes its entry or
    its files, and turning it back on puts it back. Apps for all users need administrator rights (Windows asks).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN32_KEY = r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"
APPROVED = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved"
OLD_YEARS = 3
MAX_ROWS = 400
RESULT_WORDS = {0: "not started", 1: "in progress", 2: "installed", 3: "installed with errors", 4: "failed", 5: "stopped"}
MAKER_PAGES = {
    "nvidia": ("NVIDIA App", "https://www.nvidia.com/en-us/software/nvidia-app/"),
    "amd": ("AMD Software: Adrenalin Edition", "https://www.amd.com/en/support/download/drivers.html"),
    "radeon": ("AMD Software: Adrenalin Edition", "https://www.amd.com/en/support/download/drivers.html"),
    "intel": ("Intel Driver & Support Assistant", "https://www.intel.com/content/www/us/en/support/detect.html"),
}


class UpkeepError(Exception):
    """A plain sentence for the person."""


# ====================================================================== drivers
@dataclass(frozen=True)
class DriverUpdate:
    update_id: str
    title: str
    device_class: str
    maker: str
    model: str
    date: str
    size: int


@dataclass(frozen=True)
class InstalledDriver:
    device: str
    device_class: str
    maker: str
    version: str
    date: str


def _rows(text):
    try:
        data = json.loads(text) if (text or "").strip() else []
    except ValueError:
        return []
    if isinstance(data, dict):
        data = [data]
    return [d for d in data if isinstance(d, dict)][:MAX_ROWS] if isinstance(data, list) else []


def _int(value):
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def parse_updates(text) -> list[DriverUpdate]:
    found, seen = [], set()
    for row in _rows(text):
        update_id = str(row.get("Id") or "")
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", update_id) or update_id in seen:
            continue
        seen.add(update_id)
        found.append(DriverUpdate(update_id, str(row.get("Title") or "Driver update")[:200], str(row.get("Class") or ""),
                                  str(row.get("Maker") or ""), str(row.get("Model") or ""), str(row.get("Date") or "")[:10],
                                  _int(row.get("Size"))))
    return found


def parse_installed(text) -> list[InstalledDriver]:
    found = []
    for row in _rows(text):
        device = str(row.get("DeviceName") or "").strip()
        if not device:
            continue
        found.append(InstalledDriver(device[:160], str(row.get("DeviceClass") or ""), str(row.get("Manufacturer") or ""),
                                     str(row.get("DriverVersion") or ""), str(row.get("Date") or "")[:10]))
    return found


def years_old(day: str, today: date | None = None) -> float | None:
    try:
        when = datetime.strptime(day, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    return max(0.0, ((today or date.today()) - when).days / 365.25)


# Classes worth a look for games; system plumbing (volumes, software devices) is left out of the "old" hint.
GAME_CLASSES = {"DISPLAY", "MEDIA", "NET", "HIDCLASS", "BLUETOOTH", "SYSTEM", "USB", "AUDIOENDPOINT", "MOUSE", "KEYBOARD"}


def old_drivers(installed, today: date | None = None, limit: int = 8):
    """The oldest drivers in classes that matter for games, older than OLD_YEARS. A hint, not a verdict."""
    aged = []
    for driver in installed:
        age = years_old(driver.date, today)
        if age is not None and age >= OLD_YEARS and driver.device_class.upper() in GAME_CLASSES \
                and not driver.date.startswith("2006-06-21"):     # Windows' own inbox drivers all carry this date
            aged.append((age, driver))
    aged.sort(key=lambda pair: -pair[0])
    return aged[:limit]


def maker_page(gpu_names):
    """(app name, official page) for the first graphics card whose maker is known, else None."""
    for name in gpu_names:
        low = str(name).casefold()
        for word, page in MAKER_PAGES.items():
            if word in low:
                return page
    return None


def summarize_install(text, chosen: int) -> tuple[bool, str, bool]:
    """(any installed, sentence, restart needed) from the elevated installer's JSON result."""
    try:
        data = json.loads(text or "{}")
    except ValueError:
        return False, "Windows did not report a result, so Game Grave cannot say what was installed.", False
    if not isinstance(data, dict):
        return False, "Windows did not report a result.", False
    if data.get("error"):
        return False, "Windows Update stopped: " + str(data["error"])[:240], False
    results = [r for r in data.get("results") or [] if isinstance(r, dict)]
    if not results:
        missing = chosen - _int(data.get("found"))
        return False, ("Windows Update no longer offers " + ("these drivers" if missing > 1 else "that driver")
                       + ". It may already be installed. Check again."), False
    ok = [r for r in results if _int(r.get("code")) in (2, 3)]
    bad = [r for r in results if _int(r.get("code")) not in (2, 3)]
    parts = [f"Installed {len(ok)} of {len(results)} driver update{'s' if len(results) != 1 else ''}."]
    for r in bad[:3]:
        parts.append(f"{str(r.get('title') or 'One update')[:80]}: {RESULT_WORDS.get(_int(r.get('code')), 'failed')}.")
    reboot = bool(data.get("reboot"))
    if reboot:
        parts.append("Windows needs a restart to finish.")
    return bool(ok), " ".join(parts), reboot


# ====================================================================== startup apps
@dataclass(frozen=True)
class StartupApp:
    name: str
    command: str
    scope: str            # "user" or "machine"
    source: str           # "Run", "Run32" or "StartupFolder"
    enabled: bool
    target: str = ""      # the program file, when it can be read from the command
    company: str = ""
    description: str = ""
    exists: bool | None = None

    @property
    def key(self):
        return f"{self.scope}|{self.source}|{self.name}"

    @property
    def needs_admin(self):
        return self.scope == "machine"

    @property
    def title(self):
        return self.description or Path(self.name).stem or self.name


def approved_enabled(raw) -> bool:
    """Task Manager's rule: no StartupApproved value, or an even first byte, means on; an odd first byte means off."""
    if not raw:
        return True
    try:
        first = raw[0] if isinstance(raw, (bytes, bytearray)) else int(raw[0])
    except (TypeError, ValueError, IndexError):
        return True
    return first % 2 == 0


def approved_value(enabled: bool, now: datetime | None = None) -> bytes:
    """The 12-byte value Task Manager writes: 02 and zeros for on; 03 and the time it was turned off for off."""
    if enabled:
        return bytes([2]) + bytes(11)
    moment = now or datetime.now(timezone.utc)
    filetime = int((moment.timestamp() + 11644473600) * 10_000_000)
    return bytes([3, 0, 0, 0]) + filetime.to_bytes(8, "little")


_ENV = re.compile(r"%([^%]+)%")


def program_path(command: str, environ=None) -> str:
    """The program a startup command runs: the quoted part, or everything up to the first .exe; environment names
    such as %ProgramFiles% are filled in. '' when it cannot be told."""
    env = os.environ if environ is None else environ
    text = str(command or "").strip()
    if not text:
        return ""
    if text.startswith('"'):
        end = text.find('"', 1)
        path = text[1:end] if end > 0 else text[1:]
    else:
        match = re.search(r"^(.+?\.(?:exe|bat|cmd|com|lnk|vbs|ps1))(?=\s|$)", text, re.I)
        path = match.group(1) if match else text.split(" ")[0]
    path = _ENV.sub(lambda m: env.get(m.group(1), env.get(m.group(1).upper(), m.group(0))), path)
    return path.strip()


def parse_startup(text) -> list[StartupApp]:
    found, seen = [], set()
    for row in _rows(text):
        name = str(row.get("Name") or "").strip()
        scope = str(row.get("Scope") or "")
        source = str(row.get("Source") or "")
        if not name or scope not in ("user", "machine") or source not in ("Run", "Run32", "StartupFolder"):
            continue
        key = (scope, source, name.casefold())
        if key in seen:
            continue
        seen.add(key)
        raw = row.get("Approved")
        if isinstance(raw, str):
            try:
                raw = bytes.fromhex(raw)
            except ValueError:
                raw = None
        command = str(row.get("Command") or "")
        target = str(row.get("Target") or "") or program_path(command)
        exists = row.get("Exists")
        found.append(StartupApp(name[:200], command[:1000], scope, source, approved_enabled(raw), target[:500],
                                str(row.get("Company") or "")[:120], str(row.get("Description") or "")[:160],
                                exists if isinstance(exists, bool) else None))
    found.sort(key=lambda a: (not a.enabled, a.title.casefold()))
    return found


def ps_quote(text: str) -> str:
    """A PowerShell single-quoted string: nothing inside is ever run."""
    return "'" + str(text).replace("'", "''") + "'"


def approved_path(app: StartupApp) -> str:
    """The registry key (without the hive) that holds this app's on/off value."""
    sub = {"Run": "Run", "Run32": "Run32", "StartupFolder": "StartupFolder"}[app.source]
    return APPROVED + "\\" + sub


def toggle_script(app: StartupApp, enabled: bool, now: datetime | None = None) -> str:
    """PowerShell that writes only this app's StartupApproved value (used for all-users apps, run with admin rights)."""
    hive = "HKLM:" if app.scope == "machine" else "HKCU:"
    value = ",".join(str(b) for b in approved_value(enabled, now))
    path = hive + "\\" + approved_path(app)
    return ("$ErrorActionPreference='Stop'\n"
            f"$p = {ps_quote(path)}\n"
            "if (-not (Test-Path -LiteralPath $p)) { New-Item -Path $p -Force | Out-Null }\n"
            f"Set-ItemProperty -LiteralPath $p -Name {ps_quote(app.name)} -Type Binary -Value ([byte[]]({value}))\n")


def set_enabled_user(app: StartupApp, enabled: bool, *, writer=None) -> None:
    """For apps that start for you only: write Task Manager's value in your own registry. No admin rights needed."""
    if app.needs_admin:
        raise UpkeepError("This app starts for all users, so Windows needs administrator rights to change it.")
    data = approved_value(enabled)
    if writer is not None:
        writer(approved_path(app), app.name, data)
        return
    import winreg
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, approved_path(app), 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, app.name, 0, winreg.REG_BINARY, data)


# ====================================================================== Windows calls (only on a press)
INSTALLED_SCRIPT = (
    "Get-CimInstance Win32_PnPSignedDriver | Where-Object { $_.DeviceName } | "
    "Select-Object DeviceName, DeviceClass, Manufacturer, DriverVersion, "
    "@{n='Date';e={ if ($_.DriverDate) { $_.DriverDate.ToString('yyyy-MM-dd') } else { '' } }} | "
    "ConvertTo-Json -Compress")

SEARCH = "IsInstalled=0 and Type='Driver' and IsHidden=0"
UPDATES_SCRIPT = (
    "$s = New-Object -ComObject Microsoft.Update.Session; $s.ClientApplicationID = 'Game Grave'; "
    f"$r = $s.CreateUpdateSearcher().Search(\"{SEARCH}\"); "
    "@($r.Updates | ForEach-Object { [pscustomobject]@{ Id = $_.Identity.UpdateID; Title = $_.Title; "
    "Class = $_.DriverClass; Maker = $_.DriverManufacturer; Model = $_.DriverModel; "
    "Date = $(if ($_.DriverVerDate) { $_.DriverVerDate.ToString('yyyy-MM-dd') } else { '' }); "
    "Size = [int64]$_.MaxDownloadSize } }) | ConvertTo-Json -Compress")

STARTUP_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$out = @()
function Approved($hive, $sub, $name) {
  $v = (Get-ItemProperty -LiteralPath "$hive\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\$sub" -Name $name).$name
  if ($v) { ($v | ForEach-Object { $_.ToString('x2') }) -join '' } else { '' }
}
function Info($path) {
  if ($path -and (Test-Path -LiteralPath $path -PathType Leaf)) {
    $i = (Get-Item -LiteralPath $path).VersionInfo
    @{ Company = $i.CompanyName; Description = $i.FileDescription; Exists = $true }
  } elseif ($path) { @{ Company = ''; Description = ''; Exists = $false } } else { @{ Company = ''; Description = ''; Exists = $null } }
}
function Target($cmd) {
  if ($cmd -match '^\s*"([^"]+)"') { $p = $Matches[1] } elseif ($cmd -match '^\s*(.+?\.(exe|bat|cmd|com|vbs))(\s|$)') { $p = $Matches[1] } else { $p = ($cmd -split ' ')[0] }
  [Environment]::ExpandEnvironmentVariables($p)
}
foreach ($k in @(@('HKCU:', 'Software\Microsoft\Windows\CurrentVersion\Run', 'user', 'Run'),
                 @('HKLM:', 'Software\Microsoft\Windows\CurrentVersion\Run', 'machine', 'Run'),
                 @('HKLM:', 'Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run', 'machine', 'Run32'))) {
  $item = Get-Item -LiteralPath "$($k[0])\$($k[1])"
  if (-not $item) { continue }
  foreach ($n in $item.GetValueNames()) {
    if (-not $n) { continue }
    $cmd = [string]$item.GetValue($n, '', 'DoNotExpandEnvironmentNames')
    $t = Target $cmd; $f = Info $t
    $out += [pscustomobject]@{ Name = $n; Command = $cmd; Scope = $k[2]; Source = $k[3]; Target = $t;
      Approved = (Approved $k[0] $k[3] $n); Company = $f.Company; Description = $f.Description; Exists = $f.Exists }
  }
}
$shell = New-Object -ComObject WScript.Shell
foreach ($d in @(@([Environment]::GetFolderPath('Startup'), 'user', 'HKCU:'), @([Environment]::GetFolderPath('CommonStartup'), 'machine', 'HKLM:'))) {
  if (-not $d[0] -or -not (Test-Path -LiteralPath $d[0])) { continue }
  foreach ($file in Get-ChildItem -LiteralPath $d[0] -File | Where-Object { $_.Name -ne 'desktop.ini' }) {
    $t = $file.FullName
    if ($file.Extension -eq '.lnk') { $t = $shell.CreateShortcut($file.FullName).TargetPath }
    $f = Info $t
    $out += [pscustomobject]@{ Name = $file.Name; Command = $file.FullName; Scope = $d[1]; Source = 'StartupFolder'; Target = $t;
      Approved = (Approved $d[2] 'StartupFolder' $file.Name); Company = $f.Company; Description = $f.Description; Exists = $f.Exists }
  }
}
@($out) | ConvertTo-Json -Compress
"""


def _powershell(script: str, timeout: int = 60) -> str:
    if os.name != "nt":
        raise UpkeepError("This works on Windows only.")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        done = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
                              capture_output=True, text=True, timeout=timeout, creationflags=flags, errors="replace")
    except subprocess.TimeoutExpired:
        raise UpkeepError("Windows took too long to answer. Try again in a minute.") from None
    except (OSError, subprocess.SubprocessError):
        raise UpkeepError("Windows would not run this check on this PC.") from None
    if done.returncode != 0:
        raise UpkeepError((done.stderr or done.stdout or "Windows reported an error.").strip().splitlines()[-1][:240])
    return done.stdout[:5_000_000]


def read_installed() -> list[InstalledDriver]:
    return parse_installed(_powershell(INSTALLED_SCRIPT, 90))


def search_updates() -> list[DriverUpdate]:
    """Asks Windows Update which driver updates it offers this PC. Can take a few minutes; contacts Microsoft."""
    return parse_updates(_powershell(UPDATES_SCRIPT, 600))


def read_startup() -> list[StartupApp]:
    return parse_startup(_powershell(STARTUP_SCRIPT, 60))


def install_script(update_ids, result_path: str) -> str:
    ids = ",".join(ps_quote(i) for i in update_ids if re.fullmatch(r"[0-9a-fA-F-]{36}", str(i)))
    return ("$ErrorActionPreference='Stop'\n"
            f"$out = {ps_quote(result_path)}\n"
            "try {\n"
            f"  $ids = @({ids})\n"
            "  $s = New-Object -ComObject Microsoft.Update.Session; $s.ClientApplicationID = 'Game Grave'\n"
            f"  $r = $s.CreateUpdateSearcher().Search(\"{SEARCH}\")\n"
            "  $c = New-Object -ComObject Microsoft.Update.UpdateColl\n"
            "  foreach ($u in $r.Updates) { if ($ids -contains $u.Identity.UpdateID) { if (-not $u.EulaAccepted) { $u.AcceptEula() }; [void]$c.Add($u) } }\n"
            "  $res = @{ found = $c.Count; results = @(); reboot = $false }\n"
            "  if ($c.Count -gt 0) {\n"
            "    $d = $s.CreateUpdateDownloader(); $d.Updates = $c; [void]$d.Download()\n"
            "    $i = $s.CreateUpdateInstaller(); $i.Updates = $c; $ir = $i.Install(); $res.reboot = [bool]$ir.RebootRequired\n"
            "    for ($k = 0; $k -lt $c.Count; $k++) { $res.results += @{ title = $c.Item($k).Title; code = [int]$ir.GetUpdateResult($k).ResultCode } }\n"
            "  }\n"
            "} catch { $res = @{ error = $_.Exception.Message } }\n"
            "$res | ConvertTo-Json -Compress -Depth 4 | Set-Content -Encoding UTF8 -LiteralPath $out\n")


def run_elevated(script: str, timeout: int = 3600, result_name: str = "") -> str:
    """Runs a script in a separate PowerShell that Windows asks you to allow (UAC). Returns what the script wrote to
    its result file, or '' when it writes none. Refusing the prompt changes nothing."""
    if os.name != "nt":
        raise UpkeepError("This works on Windows only.")
    folder = Path(tempfile.mkdtemp(prefix="GameGrave-"))
    script_path, result_path = folder / "task.ps1", folder / (result_name or "result.json")
    try:
        script_path.write_text(script.replace("__RESULT__", str(result_path)), encoding="utf-8-sig")
        launcher = ("$p = Start-Process -FilePath 'powershell.exe' -Verb RunAs -Wait -PassThru -WindowStyle Hidden "
                    f"-ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',{ps_quote(str(script_path))}); "
                    "exit $p.ExitCode")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            done = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", launcher], capture_output=True,
                                  text=True, timeout=timeout, creationflags=flags, errors="replace")
        except subprocess.TimeoutExpired:
            raise UpkeepError("Windows did not finish in time. Check Windows Update in Settings for what happened.") from None
        except (OSError, subprocess.SubprocessError):
            raise UpkeepError("Windows would not start the task.") from None
        text = (done.stderr or "") + (done.stdout or "")
        if done.returncode != 0 and ("canceled" in text.casefold() or "cancelled" in text.casefold() or "1223" in text):
            raise UpkeepError("Windows did not get permission (the prompt was declined). Nothing was changed.")
        if done.returncode != 0 and not result_path.exists():
            raise UpkeepError("Windows reported an error and nothing was changed: " + (text.strip().splitlines() or ["unknown"])[-1][:200])
        try:
            return result_path.read_text(encoding="utf-8-sig") if result_path.exists() else ""
        except OSError:
            return ""
    finally:
        for item in (script_path, result_path):
            try:
                item.unlink()
            except OSError:
                pass
        try:
            folder.rmdir()
        except OSError:
            pass


def install_updates(updates) -> tuple[bool, str, bool]:
    ids = [u.update_id for u in updates]
    if not ids:
        raise UpkeepError("Pick at least one driver update.")
    text = run_elevated(install_script(ids, "__RESULT__"))
    return summarize_install(text, len(ids))


def set_enabled(app: StartupApp, enabled: bool) -> None:
    """Turn a startup app on or off with Task Manager's own switch. All-users apps go through the Windows prompt."""
    if app.needs_admin:
        run_elevated(toggle_script(app, enabled), timeout=120)
    else:
        set_enabled_user(app, enabled)
