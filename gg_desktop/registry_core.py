"""Registry Cleanup (Hardware > Registry Cleanup): finds registry entries that point to programs and files that are no
longer on this PC, the kind of leftovers CCleaner's registry cleaner lists. Pure: the registry, the file check and the
drive check are handed in, so every rule is tested without Windows.

Priority is never breaking the PC, so an entry is only listed when ALL of these hold:
  * it names one absolute file or folder on a drive letter (commands are parsed; MsiExec and relative names are skipped),
  * that drive is present and is a fixed drive (an unplugged USB or network drive never makes something "missing"),
  * the path is not inside the Windows folder (32/64-bit redirection makes those look missing when they are not),
  * the file is really not there, checked again right before anything changes.
Riskier kinds (Windows Installer and Microsoft uninstall records, services) are shown for review only and never changed.
Every change is backed up first (reg export) and can be undone; nothing here claims a cleaner registry makes games faster.
"""
from __future__ import annotations

import ntpath
import re
from dataclasses import dataclass, field

RUN_KEYS = (("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Run"),
            ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\RunOnce"),
            ("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
            ("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce"),
            ("HKLM", r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"),
            ("HKLM", r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\RunOnce"))
UNINSTALL_KEYS = (("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
                  ("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                  ("HKLM", r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"))
APP_PATHS = (("HKCU", r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
             ("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
             ("HKLM", r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths"))
SHARED_DLLS = (("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\SharedDLLs"),
               ("HKLM", r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\SharedDLLs"))
MUI_CACHE = (("HKCU", r"Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\MuiCache"),)
COMPAT = (("HKCU", r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"),
          ("HKLM", r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"),
          ("HKCU", r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Compatibility Assistant\Store"))
HELP = (("HKLM", r"SOFTWARE\Microsoft\Windows\HTML Help"), ("HKLM", r"SOFTWARE\Microsoft\Windows\Help"),
        ("HKLM", r"SOFTWARE\WOW6432Node\Microsoft\Windows\HTML Help"),
        ("HKLM", r"SOFTWARE\WOW6432Node\Microsoft\Windows\Help"))
INSTALLER_FOLDERS = (("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Installer\Folders"),)
SOUNDS = ("HKCU", r"AppEvents\Schemes\Apps")
OPEN_WITH_APPS = ("HKCU", r"Software\Classes\Applications")
SERVICES = ("HKLM", r"SYSTEM\CurrentControlSet\Services")

# category key -> (title, plain words, ticked by default)
CATEGORIES = {
    "startup": ("Startup entries", "Programs set to start with Windows that are no longer on this PC.", True),
    "uninstall": ("Uninstall list leftovers", "Entries in Installed apps whose program folder and uninstaller are "
                  "both gone. Removing one only takes the dead line out of the list.", True),
    "app_paths": ("Program shortcuts (App Paths)", "Names Windows uses to start a program from Run, pointing to a "
                  "program that's gone.", True),
    "open_with": ("\"Open with\" programs", "Programs offered in \"Open with\" that are no longer on this PC.", True),
    "shared_dlls": ("Shared file counts", "Counts of programs using a shared file, for files that are gone.", True),
    "mui_cache": ("Program name cache", "Names Windows remembered for programs that are gone.", True),
    "compat": ("Compatibility settings", "\"Run in compatibility mode\" settings and records for programs that are "
               "gone.", True),
    "help": ("Help files", "Links to help files that are gone.", True),
    "sounds": ("Sound events", "Windows sounds set to sound files that are gone (the sound is set to none).", True),
    "installer_folders": ("Installer folder records", "Folders Windows Installer recorded that are gone. Left unticked "
                          "because Windows Installer keeps them for repairs; tick them if you want.", False),
    "review": ("Review only, never changed", "Things that look like leftovers but are too risky to change "
               "automatically: Windows Installer and Microsoft uninstall records, and services.", False),
}
ORDER = tuple(CATEGORIES)
MAX_FIX = 500                   # one fix never changes more than this many entries
EXECUTABLE = r"exe|dll|sys|cpl|ocx|com|bat|cmd|msc|scr|lnk|wav|chm|hlp|ico|ax|drv"


@dataclass(frozen=True)
class Finding:
    category: str
    hive: str                     # HKCU or HKLM
    key: str                      # full key path inside the hive (WOW6432Node written out)
    value: str | None             # value name; None = the whole key; "" = the key's default value
    target: str                   # the file or folder that's gone
    action: str = "delete_value"  # delete_value | delete_key | clear_value | none
    name: str = ""                # what a person recognises (program name, file name)
    note: str = ""

    @property
    def fixable(self) -> bool:
        return self.action != "none" and self.category != "review"

    @property
    def ident(self) -> str:
        return f"{self.hive}\\{self.key}|{'' if self.value is None else self.value}|{self.action}"

    @property
    def full_key(self) -> str:
        return ("HKEY_CURRENT_USER" if self.hive == "HKCU" else "HKEY_LOCAL_MACHINE") + "\\" + self.key


@dataclass
class Checks:
    """What the scan is allowed to ask about the PC. `exists(path)`, `drive_ok(letter)` (present and fixed),
    `expand(text)` (environment variables), `windows_dir`."""
    exists: object
    drive_ok: object
    expand: object = lambda text: text
    windows_dir: str = r"C:\Windows"
    cache: dict = field(default_factory=dict)

    def gone(self, path: str) -> bool:
        """True only when the path is a real local path on a present fixed drive, outside Windows, and not there."""
        if not path:
            return False
        path = ntpath.normpath(path)
        drive = ntpath.splitdrive(path)[0]
        if not re.fullmatch(r"[A-Za-z]:", drive or "") or path.startswith("\\\\"):
            return False
        if len(path) <= 3:
            return False
        windows = ntpath.normpath(self.windows_dir).casefold().rstrip("\\") + "\\"
        if path.casefold().startswith(windows) or path.casefold() == windows.rstrip("\\"):
            return False
        letter = drive[0].upper()
        key = ("drive", letter)
        if key not in self.cache:
            self.cache[key] = bool(self.drive_ok(letter))
        if not self.cache[key]:
            return False
        if path.casefold() not in self.cache:
            self.cache[path.casefold()] = bool(self.exists(path))
        return not self.cache[path.casefold()]


def target_from(command, expand=lambda t: t):
    """The one file a command or path names, or "" when it can't be told for sure."""
    if not isinstance(command, str):
        return ""
    text = expand(command.strip()).strip()
    if not text or text.startswith("@"):            # @resource strings
        return ""
    if text.startswith('"'):
        end = text.find('"', 1)
        first = text[1:end] if end > 0 else text[1:]
        rest = text[end + 1:].strip() if end > 0 else ""
    else:
        match = re.match(rf"^([A-Za-z]:\\[^\"<>|*?]*?\.(?:{EXECUTABLE}))(?=$|[\s,])", text, re.I)
        if match:
            first, rest = match.group(1), text[match.end():].strip()
        else:
            parts = re.split(r"\s", text, maxsplit=1)
            first, rest = parts[0], (parts[1] if len(parts) > 1 else "")
    base = ntpath.basename(first).casefold()
    if base in ("msiexec", "msiexec.exe"):
        return ""
    if base in ("rundll32", "rundll32.exe"):        # the file is the first argument up to the comma
        arg = rest.strip().split(",")[0].strip().strip('"')
        return target_from(arg, expand) if arg else ""
    first = re.sub(r",\s*-?\d+$", "", first.strip())  # "file.exe,0" icon index
    if not re.match(r"^[A-Za-z]:\\", first):
        return ""
    return first


def _missing(checks, raw, expand=True):
    target = target_from(raw, checks.expand if expand else (lambda t: t))
    return target if target and checks.gone(target) else ""


# ---------------------------------------------------------------- scanners; reg is (hive, key) -> subkeys / values
def scan(reg, checks: Checks, progress=None) -> list:
    """Every finding, in category order. `reg.subkeys(hive, key)` and `reg.values(hive, key)` ({name: data}) return
    empty for a key that can't be read."""
    found = []
    steps = ((_startup, "startup entries"), (_uninstall, "the uninstall list"), (_app_paths, "program shortcuts"),
             (_open_with, "\"Open with\" programs"), (_shared, "shared file counts"), (_mui, "the program name cache"),
             (_compat, "compatibility settings"), (_help, "help files"), (_sounds, "sound events"),
             (_installer_folders, "installer folders"), (_services, "services"))
    for i, (scanner, words) in enumerate(steps):
        if progress:
            progress(int(i * 100 / len(steps)), "Checking " + words)
        try:
            found += scanner(reg, checks)
        except Exception:          # one unreadable area never stops the rest
            continue
    seen, unique = set(), []
    for f in found:
        # Some keys (App Paths, SharedDLLs on many PCs) are one key seen through both the 64-bit and the WOW6432Node
        # path. Listing both would remove it once and then "fail" on the second, so the same entry is kept once.
        alias = (f.hive, re.sub(r"(?i)\\WOW6432Node\\", lambda _m: "\\", f.key).casefold(),
                 None if f.value is None else f.value.casefold(), f.target.casefold())
        if f.ident not in seen and alias not in seen:
            seen.update((f.ident, alias))
            unique.append(f)
    return unique


def _startup(reg, checks):
    out = []
    for hive, key in RUN_KEYS:
        for name, data in reg.values(hive, key).items():
            target = _missing(checks, data)
            if target and name:
                out.append(Finding("startup", hive, key, name, target, "delete_value", name))
    return out


def _uninstall(reg, checks):
    out = []
    for hive, base in UNINSTALL_KEYS:
        for sub in reg.subkeys(hive, base):
            key = base + "\\" + sub
            v = reg.values(hive, key)
            name = str(v.get("DisplayName") or "")
            if not name or str(v.get("SystemComponent", "0")) == "1" or v.get("ParentKeyName"):
                continue
            uninstaller = target_from(v.get("UninstallString", ""), checks.expand)
            location = str(v.get("InstallLocation") or "").strip().strip('"')
            if not uninstaller or not checks.gone(uninstaller):
                continue                                   # the uninstaller is still there: a real program
            if location and not checks.gone(location):
                continue                                   # its folder is still there: leave it
            msi = str(v.get("WindowsInstaller", "0")) == "1" or "msiexec" in str(v.get("UninstallString", "")).casefold()
            microsoft = "microsoft" in str(v.get("Publisher") or "").casefold()
            if msi or microsoft:
                out.append(Finding("review", hive, key, None, uninstaller, "none", name,
                                   "Windows Installer or Microsoft record: use Microsoft's \"Program Install and "
                                   "Uninstall\" troubleshooter for these." if msi else
                                   "Microsoft record: left alone."))
            else:
                out.append(Finding("uninstall", hive, key, None, uninstaller, "delete_key", name))
    return out


def _app_paths(reg, checks):
    out = []
    for hive, base in APP_PATHS:
        for sub in reg.subkeys(hive, base):
            key = base + "\\" + sub
            target = _missing(checks, reg.values(hive, key).get("", ""))
            if target:
                out.append(Finding("app_paths", hive, key, None, target, "delete_key", sub))
    return out


def _open_with(reg, checks):
    out = []
    hive, base = OPEN_WITH_APPS
    for sub in reg.subkeys(hive, base):
        command = reg.values(hive, base + "\\" + sub + r"\shell\open\command").get("", "")
        target = _missing(checks, command)
        if target and sub.casefold().endswith(".exe"):
            out.append(Finding("open_with", hive, base + "\\" + sub, None, target, "delete_key", sub))
    return out


def _value_paths(reg, checks, places, category, expand=True):
    """Values whose NAME is the path (SharedDLLs, Layers, Installer Folders, MuiCache)."""
    out = []
    for hive, key in places:
        for name in reg.values(hive, key):
            path = name
            if category == "mui_cache":                    # "C:\x\y.exe.FriendlyAppName"
                path = re.sub(r"\.(FriendlyAppName|ApplicationCompany)$", "", name, flags=re.I)
            target = _missing(checks, '"' + path.rstrip("\\") + '"' if path else "", expand)
            if target:
                out.append(Finding(category, hive, key, name, target, "delete_value", ntpath.basename(target)))
    return out


def _shared(reg, checks):
    return _value_paths(reg, checks, SHARED_DLLS, "shared_dlls")


def _mui(reg, checks):
    return _value_paths(reg, checks, MUI_CACHE, "mui_cache")


def _compat(reg, checks):
    return _value_paths(reg, checks, COMPAT, "compat")


def _installer_folders(reg, checks):
    return _value_paths(reg, checks, INSTALLER_FOLDERS, "installer_folders")


def _help(reg, checks):
    out = []
    for hive, key in HELP:
        for name, data in reg.values(hive, key).items():
            folder = str(data or "").strip()
            if not name or not folder:
                continue
            target = ntpath.join(checks.expand(folder), name)
            if checks.gone(target):
                out.append(Finding("help", hive, key, name, target, "delete_value", name))
    return out


def _sounds(reg, checks):
    out = []
    hive, base = SOUNDS
    for app in reg.subkeys(hive, base):
        for event in reg.subkeys(hive, base + "\\" + app):
            key = "\\".join((base, app, event, ".Current"))
            target = _missing(checks, '"' + str(reg.values(hive, key).get("", "") or "") + '"')
            if target:
                out.append(Finding("sounds", hive, key, "", target, "clear_value", event))
    return out


def _services(reg, checks):
    out = []
    hive, base = SERVICES
    for sub in reg.subkeys(hive, base):
        image = reg.values(hive, base + "\\" + sub).get("ImagePath", "")
        target = _missing(checks, image)
        if target:
            out.append(Finding("review", hive, base + "\\" + sub, None, target, "none", sub,
                               "Service: left alone. Services can be removed by their own uninstaller."))
    return out


# ---------------------------------------------------------------- choosing and wording
def default_ticked(findings) -> set:
    return {f.ident for f in findings if f.fixable and CATEGORIES[f.category][2]}


def grouped(findings) -> list:
    """[(category, title, words, [findings])] in display order, empty groups left out."""
    out = []
    for cat in ORDER:
        items = sorted((f for f in findings if f.category == cat), key=lambda f: (f.name.casefold(), f.key))
        if items:
            title, words, _tick = CATEGORIES[cat]
            out.append((cat, title, words, items))
    return out


def what_changes(f: Finding) -> str:
    where = f.full_key + ("" if f.value is None else f" value \"{f.value or '(Default)'}\"")
    verb = {"delete_key": "Delete key", "delete_value": "Delete", "clear_value": "Set to empty:"}.get(f.action, "")
    return f"{verb} {where}  (points to {f.target})"


def confirmation(chosen, restore_point: bool, backup_folder: str) -> str:
    hklm = sum(1 for f in chosen if f.hive == "HKLM")
    lines = [f"Remove {len(chosen)} registry entr{'y' if len(chosen) == 1 else 'ies'} that point to things no longer "
             "on this PC?", ""]
    lines.append("First: " + ("a System Restore point is made, then " if restore_point else "") +
                 f"every key is exported to {backup_folder} so Undo can put it back.")
    lines.append("Each entry is checked again just before it changes; if its file has come back, it's left alone.")
    if hklm:
        lines.append(f"{hklm} of them are for all users, so Windows will ask you to allow the change.")
    shown = chosen[:500]                 # the most one fix takes; the window scrolls
    lines += ["", "Exactly what changes:"] + ["  " + what_changes(f) for f in shown]
    if len(chosen) > len(shown):
        lines.append(f"  … and {len(chosen) - len(shown)} more, listed in the backup folder.")
    return "\n".join(lines)


def summary(findings) -> str:
    fix = [f for f in findings if f.fixable]
    review = len(findings) - len(fix)
    if not findings:
        return "Nothing found: no registry entries point to programs or files that are gone."
    text = f"Found {len(fix)} entr{'y' if len(fix) == 1 else 'ies'} pointing to programs or files that are no longer here"
    return text + (f", plus {review} to review only." if review else ".")


HONEST_NOTE = ("A tidier registry doesn't make games faster; this removes leftovers that point to programs that are gone, "
               "so lists like Installed apps and Open with stay accurate. Only entries whose file is really missing are "
               "listed, unplugged drives and the Windows folder are never treated as missing, and every change is backed "
               "up first.")
