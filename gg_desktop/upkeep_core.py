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
  * Lists what Task Manager's Startup apps lists (the Run keys for you and for all users, the two Startup folders and
    Microsoft Store apps' startup tasks) plus scheduled tasks that start a program when you sign in or Windows starts.
    Microsoft's own scheduled tasks and Windows services are left out, and the tab says so.
  * Each switch is the one Windows itself uses: Task Manager's StartupApproved value, a Store app's startup-task state,
    or the scheduled task's Enabled flag. Nothing is ever deleted, and switching back on puts it back. Changes that
    need administrator rights go through the Windows prompt.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import re
import time
from types import SimpleNamespace
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
    source: str           # "Run", "Run32", "StartupFolder", "StoreApp" or "Task"
    enabled: bool
    target: str = ""      # the program file, when it can be read from the command
    company: str = ""
    description: str = ""
    exists: bool | None = None
    ref: str = ""         # StoreApp: "<package family>\\<task id>"; Task: the task's full path
    locked: bool = False  # set by a policy; Windows does not let it be switched here

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
        if not name or scope not in ("user", "machine") or source not in SOURCES:
            continue
        ref = str(row.get("Ref") or "")
        if source in ("StoreApp", "Task") and not ref:
            continue
        key = (scope, source, name.casefold())
        if key in seen:
            continue
        seen.add(key)
        raw = row.get("Approved")
        state = row.get("State")
        if source == "StoreApp":
            enabled, locked = state in (2, 4), state in (3, 4)
        elif source == "Task":
            enabled, locked = state is not False, False
        if isinstance(raw, str):
            try:
                raw = bytes.fromhex(raw)
            except ValueError:
                raw = None
        command = str(row.get("Command") or "")
        target = str(row.get("Target") or "") or program_path(command)
        exists = row.get("Exists")
        if source not in ("StoreApp", "Task"):
            enabled, locked = approved_enabled(raw), False
        found.append(StartupApp(name[:200], command[:1000], scope, source, enabled, target[:500],
                                str(row.get("Company") or "")[:120], str(row.get("Description") or "")[:160],
                                exists if isinstance(exists, bool) else None, ref[:500], locked))
    found.sort(key=lambda a: (not a.enabled, a.title.casefold()))
    return found


SOURCES = ("Run", "Run32", "StartupFolder", "StoreApp", "Task")
STORE_TASKS = r"Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\SystemAppData"


def store_state_value(enabled: bool) -> int:
    """A Store app startup task's State: 2 enabled, 1 disabled by the user (what Task Manager writes)."""
    return 2 if enabled else 1


def ps_quote(text: str) -> str:
    """A PowerShell single-quoted string: nothing inside is ever run."""
    return "'" + str(text).replace("'", "''") + "'"


def approved_path(app: StartupApp) -> str:
    """The registry key (without the hive) that holds this app's on/off value."""
    sub = {"Run": "Run", "Run32": "Run32", "StartupFolder": "StartupFolder"}[app.source]
    return APPROVED + "\\" + sub


def task_script(app: StartupApp, enabled: bool) -> str:
    """PowerShell that switches one scheduled task on or off. Nothing else about the task changes."""
    folder, _, name = app.ref.rpartition("\\")
    return ("$ErrorActionPreference='Stop'\n"
            f"{'Enable' if enabled else 'Disable'}-ScheduledTask -TaskPath {ps_quote(folder + chr(92))} "
            f"-TaskName {ps_quote(name)} | Out-Null\n")


def toggle_script(app: StartupApp, enabled: bool, now: datetime | None = None) -> str:
    """PowerShell that writes only this app's StartupApproved value (used for all-users apps, run with admin rights)."""
    if app.source == "Task":
        return task_script(app, enabled)
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
    if app.locked:
        raise UpkeepError("A policy on this PC controls this app's startup, so Windows does not let it be changed here.")
    if app.source == "StoreApp":
        pkg, _, task = app.ref.partition("\\")
        if not pkg or not task or "\\" in task or ".." in app.ref:
            raise UpkeepError("This Store app's startup entry could not be read.")
        if writer is not None:
            writer(STORE_TASKS + "\\" + app.ref, "State", store_state_value(enabled))
            return
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STORE_TASKS + "\\" + app.ref, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "State", 0, winreg.REG_DWORD, store_state_value(enabled))
        return
    if app.source == "Task":
        raise UpkeepError("Scheduled tasks are switched with PowerShell, not here.")
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
MICROSOFT_UPDATE = "7971f918-a847-4430-9279-4a52d1efe18d"
# Ask three ways and merge: this PC's default update source, Windows Update online directly (a PC pointed at a company
# server otherwise sees only that server), and the Microsoft Update service when it is registered (it carries more
# optional drivers from hardware makers). Each update is listed once.
SEARCHERS_PS = (
    "$sels = @(@(0, '', 'Windows Update'), @(2, '', 'Windows Update'), @(3, '" + MICROSOFT_UPDATE + "', 'Microsoft Update'))\n"
    "function Searcher($s, $sel) { $q = $s.CreateUpdateSearcher(); $q.Online = $true; $q.ServerSelection = $sel[0];"
    " if ($sel[1]) { $q.ServiceID = $sel[1] }; $q }\n")
UPDATES_SCRIPT = (
    "$s = New-Object -ComObject Microsoft.Update.Session; $s.ClientApplicationID = 'Game Grave'\n"
    + SEARCHERS_PS +
    "$seen = @{}; $out = New-Object System.Collections.ArrayList; $errs = @(); $ok = 0\n"
    "foreach ($sel in $sels) {\n"
    f"  try {{ $r = (Searcher $s $sel).Search(\"{SEARCH}\"); $ok++ }} catch {{ $errs += $_.Exception.Message; continue }}\n"
    "  foreach ($u in $r.Updates) { $id = $u.Identity.UpdateID; if ($seen[$id]) { continue }; $seen[$id] = 1\n"
    "    [void]$out.Add([pscustomobject]@{ Id = $id; Title = $u.Title; Class = $u.DriverClass; Maker = $u.DriverManufacturer;"
    " Model = $u.DriverModel; Date = $(if ($u.DriverVerDate) { $u.DriverVerDate.ToString('yyyy-MM-dd') } else { '' });"
    " Size = [int64]$u.MaxDownloadSize; Source = $sel[2] }) }\n"
    "}\n"
    "if ($ok -eq 0) { throw ($errs | Select-Object -First 1) }\n"
    "@($out) | ConvertTo-Json -Compress")

PROBLEM_SCRIPT = (
    "Get-CimInstance Win32_PnPEntity | Where-Object { $_.ConfigManagerErrorCode -and $_.ConfigManagerErrorCode -ne 22 "
    "-and $_.ConfigManagerErrorCode -ne 45 } | "
    "Select-Object Name, PNPClass, ConfigManagerErrorCode, DeviceID | ConvertTo-Json -Compress")

# What Device Manager's problem codes mean, in plain words (the common ones).
PROBLEM_CODES = {1: "not set up correctly", 3: "driver may be damaged", 10: "can't start", 12: "not enough resources",
                 14: "needs a restart", 18: "driver needs reinstalling", 19: "settings damaged", 21: "being removed",
                 24: "not present or not working", 28: "no driver installed", 31: "driver didn't load",
                 32: "driver service disabled", 37: "driver failed to start", 39: "driver missing or damaged",
                 41: "driver loaded but device not found", 43: "stopped after reporting a problem",
                 48: "driver blocked", 52: "driver not digitally signed"}


@dataclass(frozen=True)
class DeviceProblem:
    name: str
    device_class: str
    code: int
    device_id: str

    @property
    def meaning(self):
        return PROBLEM_CODES.get(self.code, f"Windows problem code {self.code}")

    @property
    def missing_driver(self):
        return self.code in (1, 18, 28, 31, 39, 52)


def parse_problems(text) -> list[DeviceProblem]:
    found = []
    for row in _rows(text):
        code = _int(row.get("ConfigManagerErrorCode"))
        name = str(row.get("Name") or row.get("DeviceID") or "Unknown device").strip()
        if code:
            found.append(DeviceProblem(name[:160], str(row.get("PNPClass") or ""), code, str(row.get("DeviceID") or "")[:200]))
    return found


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
# Microsoft Store apps' startup tasks (what Task Manager shows for Store apps)
$store = 'HKCU:\Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\SystemAppData'
if (Test-Path -LiteralPath $store) {
  $pk = @{}
  Get-AppxPackage | ForEach-Object { $pk[$_.PackageFamilyName] = $_ }
  foreach ($p in Get-ChildItem -LiteralPath $store) {
    foreach ($t in Get-ChildItem -LiteralPath $p.PSPath) {
      $st = (Get-ItemProperty -LiteralPath $t.PSPath).State
      if ($null -eq $st) { continue }
      $a = $pk[$p.PSChildName]; $title = ''; $pub = ''
      if ($a) {
        $m = ($a | Get-AppxPackageManifest).Package.Properties
        if ($m.DisplayName -and $m.DisplayName -notlike 'ms-resource*') { $title = [string]$m.DisplayName } else { $title = $a.Name }
        if ($m.PublisherDisplayName -and $m.PublisherDisplayName -notlike 'ms-resource*') { $pub = [string]$m.PublisherDisplayName }
      }
      $out += [pscustomobject]@{ Name = $t.PSChildName; Command = $p.PSChildName; Scope = 'user'; Source = 'StoreApp';
        Ref = "$($p.PSChildName)\$($t.PSChildName)"; State = [int]$st; Company = $pub; Description = $title; Exists = [bool]$a }
    }
  }
}
# Scheduled tasks that start something at sign-in or when Windows starts (Microsoft's own are left out)
$me = "$env:USERDOMAIN\$env:USERNAME"
foreach ($t in Get-ScheduledTask | Where-Object { $_.TaskPath -notlike '\Microsoft\*' }) {
  $starts = @($t.Triggers | Where-Object { $_.CimClass.CimClassName -in @('MSFT_TaskLogonTrigger', 'MSFT_TaskBootTrigger') })
  if (-not $starts) { continue }
  $exec = @($t.Actions | Where-Object { $_.Execute }) | Select-Object -First 1
  if (-not $exec) { continue }
  $path = [Environment]::ExpandEnvironmentVariables(($exec.Execute).Trim('"')); $f = Info $path
  $uid = [string]$t.Principal.UserId
  $scope = if ($uid -and ($uid -eq $env:USERNAME -or $uid -eq $me)) { 'user' } else { 'machine' }
  $out += [pscustomobject]@{ Name = $t.TaskName; Command = (($exec.Execute) + ' ' + ($exec.Arguments)).Trim(); Scope = $scope;
    Source = 'Task'; Ref = "$($t.TaskPath)$($t.TaskName)"; State = ($t.State -ne 'Disabled'); Target = $path;
    Company = $f.Company; Description = $f.Description; Exists = $f.Exists }
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


def read_firmware():
    """BIOS / board / drive firmware facts from Windows. Read only."""
    from gg_desktop import upkeep_vendor as vendor
    return vendor.parse_firmware(_powershell(vendor.FIRMWARE_SCRIPT, 60))


def graphics_drivers(installed):
    """(card, Windows driver version, date) for each graphics card in the installed driver list."""
    return [(d.device, d.version, d.date) for d in installed if d.device_class.upper() == "DISPLAY"
            and "basic" not in d.device.casefold() and "remote" not in d.device.casefold()]


def read_problems() -> list[DeviceProblem]:
    """Devices Windows itself reports a problem with (Device Manager's yellow mark). Read only."""
    return parse_problems(_powershell(PROBLEM_SCRIPT, 60))


def read_startup() -> list[StartupApp]:
    return parse_startup(_powershell(STARTUP_SCRIPT, 60))


def search_any(criteria: str):
    """Same as search_updates for another Windows Update search (used by the real-Windows check)."""
    return parse_updates(_powershell(UPDATES_SCRIPT.replace(SEARCH, criteria), 600))


def install_script(update_ids, result_path: str, criteria: str = SEARCH, progress_path: str = "") -> str:
    """Elevated script: finds exactly these update IDs (through the same three searches), then downloads and installs
    them one at a time, writing each step to progress_path so the app can show it, and each result to result_path."""
    ids = ",".join(ps_quote(i) for i in update_ids if re.fullmatch(r"[0-9a-fA-F-]{36}", str(i)))
    prog = ps_quote(progress_path) if progress_path else "''"
    return ("$ErrorActionPreference='Stop'\n"
            f"$out = {ps_quote(result_path)}; $prog = {prog}\n"
            "function Step($o) { if ($prog) { ($o | ConvertTo-Json -Compress) | Set-Content -Encoding UTF8 -LiteralPath $prog } }\n"
            "try {\n"
            f"  $ids = @({ids})\n"
            "  $s = New-Object -ComObject Microsoft.Update.Session; $s.ClientApplicationID = 'Game Grave'\n"
            + "  " + SEARCHERS_PS.replace("\n", "\n  ").rstrip() + "\n"
            "  Step @{ step = 'find'; index = 0; count = $ids.Count; title = '' }\n"
            "  $todo = New-Object System.Collections.ArrayList; $got = @{}\n"
            "  foreach ($sel in $sels) {\n"
            "    if ($got.Count -ge $ids.Count) { break }\n"
            f"    try {{ $r = (Searcher $s $sel).Search(\"{criteria}\") }} catch {{ continue }}\n"
            "    foreach ($u in $r.Updates) { $id = $u.Identity.UpdateID\n"
            "      if (($ids -contains $id) -and -not $got[$id]) { $got[$id] = 1; if (-not $u.EulaAccepted) { $u.AcceptEula() }; [void]$todo.Add($u) } }\n"
            "  }\n"
            "  $res = @{ found = $todo.Count; results = @(); reboot = $false }\n"
            "  for ($k = 0; $k -lt $todo.Count; $k++) {\n"
            "    $u = $todo[$k]; $c = New-Object -ComObject Microsoft.Update.UpdateColl; [void]$c.Add($u)\n"
            "    try {\n"
            "      Step @{ step = 'download'; index = $k + 1; count = $todo.Count; title = $u.Title }\n"
            "      $d = $s.CreateUpdateDownloader(); $d.Updates = $c; [void]$d.Download()\n"
            "      Step @{ step = 'install'; index = $k + 1; count = $todo.Count; title = $u.Title }\n"
            "      $i = $s.CreateUpdateInstaller(); $i.Updates = $c; $ir = $i.Install()\n"
            "      if ($ir.RebootRequired) { $res.reboot = $true }\n"
            "      $res.results += @{ title = $u.Title; code = [int]$ir.GetUpdateResult(0).ResultCode }\n"
            "    } catch { $res.results += @{ title = $u.Title; code = 4; error = $_.Exception.Message } }\n"
            "  }\n"
            "  Step @{ step = 'done'; index = $todo.Count; count = $todo.Count; title = '' }\n"
            "} catch { $res = @{ error = $_.Exception.Message } }\n"
            "$res | ConvertTo-Json -Compress -Depth 4 | Set-Content -Encoding UTF8 -LiteralPath $out\n")


def read_step(text):
    """The installer's latest step as (step, index, count, title), or None."""
    try:
        data = json.loads(text.lstrip("\ufeff"))
        return (str(data.get("step") or ""), int(data.get("index") or 0), int(data.get("count") or 0),
                str(data.get("title") or "")[:200])
    except (ValueError, TypeError, AttributeError):
        return None


def step_text(step):
    if not step:
        return ""
    kind, index, count, title = step
    if kind == "find":
        return f"Finding the {count} update{'s' if count != 1 else ''} in Windows Update…"
    if kind == "download":
        return f"Downloading {index} of {count}: {title}"
    if kind == "install":
        return f"Installing {index} of {count}: {title}"
    if kind == "done":
        return "Finishing…"
    return ""


def run_elevated(script: str, timeout: int = 3600, result_name: str = "", on_step=None) -> str:
    """Runs a script in a separate PowerShell that Windows asks you to allow (UAC). Returns what the script wrote to
    its result file, or '' when it writes none. Refusing the prompt changes nothing. With on_step, the script's
    __PROGRESS__ file is read every second and each new step is passed to on_step."""
    if os.name != "nt":
        raise UpkeepError("This works on Windows only.")
    folder = Path(tempfile.mkdtemp(prefix="GameGrave-"))
    script_path, result_path = folder / "task.ps1", folder / (result_name or "result.json")
    progress_path = folder / "progress.json"
    try:
        script_path.write_text(script.replace("__RESULT__", str(result_path)).replace("__PROGRESS__", str(progress_path)),
                               encoding="utf-8-sig")
        launcher = ("$p = Start-Process -FilePath 'powershell.exe' -Verb RunAs -Wait -PassThru -WindowStyle Hidden "
                    f"-ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',{ps_quote(str(script_path))}); "
                    "exit $p.ExitCode")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            proc = subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-Command", launcher],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=flags,
                                    errors="replace")
        except (OSError, subprocess.SubprocessError):
            raise UpkeepError("Windows would not start the task.") from None
        deadline, last = time.monotonic() + timeout, None
        while proc.poll() is None:
            if time.monotonic() > deadline:
                proc.kill()
                raise UpkeepError("Windows did not finish in time. Check Windows Update in Settings for what happened.")
            if on_step is not None and progress_path.exists():
                try:
                    step = read_step(progress_path.read_text(encoding="utf-8-sig"))
                except OSError:
                    step = None
                if step and step != last:
                    last = step
                    on_step(step)
            time.sleep(1)
        if on_step is not None and progress_path.exists():   # a quick task can finish between two looks
            try:
                step = read_step(progress_path.read_text(encoding="utf-8-sig"))
            except OSError:
                step = None
            if step and step != last:
                on_step(step)
        out, err = proc.communicate()
        done = SimpleNamespace(returncode=proc.returncode, stdout=out, stderr=err)
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
        for item in (script_path, result_path, progress_path):
            try:
                item.unlink()
            except OSError:
                pass
        try:
            folder.rmdir()
        except OSError:
            pass


def install_updates(updates, on_step=None) -> tuple[bool, str, bool]:
    ids = [u.update_id for u in updates]
    if not ids:
        raise UpkeepError("Pick at least one driver update.")
    text = run_elevated(install_script(ids, "__RESULT__", progress_path="__PROGRESS__"), on_step=on_step)
    return summarize_install(text, len(ids))


def set_enabled(app: StartupApp, enabled: bool) -> None:
    """Turn a startup app on or off with Windows' own switch. Changes that need admin rights go through the prompt."""
    if app.locked:
        raise UpkeepError("A policy on this PC controls this app's startup, so Windows does not let it be changed here.")
    if app.source == "Task":
        try:
            _powershell(task_script(app, enabled), 60)          # your own tasks change without a prompt
        except UpkeepError:
            run_elevated(task_script(app, enabled), timeout=120)
        return
    if app.needs_admin:
        run_elevated(toggle_script(app, enabled), timeout=120)
    else:
        set_enabled_user(app, enabled)


def restart_pc(seconds: int = 60) -> None:
    """Ask Windows to restart after a short delay, with a message. `shutdown /a` cancels it."""
    if os.name != "nt":
        raise UpkeepError("This works on Windows only.")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    done = subprocess.run(["shutdown", "/r", "/t", str(max(10, int(seconds))), "/c",
                           "Game Grave: restarting to finish driver updates."],
                          capture_output=True, text=True, creationflags=flags, errors="replace")
    if done.returncode != 0:
        raise UpkeepError("Windows would not schedule the restart: " + (done.stderr or done.stdout).strip()[:160])


def cancel_restart() -> None:
    if os.name == "nt":
        subprocess.run(["shutdown", "/a"], capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
