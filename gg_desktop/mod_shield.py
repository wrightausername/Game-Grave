"""Mod Shield: read-only checks of mod folders for files that do not belong there. No Qt in this module.

Honesty rules:
* Mod Shield only reads. It never moves, renames, quarantines, changes or deletes a file.
* A finding is a reason to look, never a verdict. Mod Shield does not call a file malware, and it never calls a
  file or folder safe. Plenty of real mods ship programs (BodySlide, xEdit) and code libraries (SKSE, BepInEx).
* The Microsoft Defender scan runs only when the owner presses the button, with remediation turned off, so Defender
  reports what it finds and changes nothing. A clean result is Defender's answer for that scan, not a guarantee.
* Fingerprints (SHA-256) are computed on this PC. Looking one up on VirusTotal sends only the fingerprint, and only
  when the owner clicks; the file itself is never uploaded.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import glob
import hashlib
import os
from pathlib import Path
import re
import time

# Levels, strongest first. Words only; the dialog never shows "malware" or "safe" for these.
CHECK_FIRST, NOTE, EXPECTED = "Check first", "Note", "Expected"
LEVEL_ORDER = {CHECK_FIRST: 0, NOTE: 1, EXPECTED: 2}

PROGRAM_EXT = frozenset({".exe", ".scr", ".com", ".pif", ".msi", ".msp", ".cpl"})
SCRIPT_EXT = frozenset({".bat", ".cmd", ".ps1", ".psm1", ".vbs", ".vbe", ".wsf", ".wsh", ".hta", ".jse", ".lnk", ".reg"})
LIBRARY_EXT = frozenset({".dll", ".asi"})
# Endings that a disguised program pretends to be ("readme.txt.exe", "preview.png.scr").
DECOY_EXT = frozenset({".zip", ".rar", ".7z", ".txt", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".dds", ".mp4",
                       ".esp", ".esm", ".esl", ".pak", ".ba2", ".bsa", ".ini", ".json", ".xml", ".doc", ".docx"})
# Folders where mod loaders keep their plugins. A DLL here is what the loader expects.
LOADER_FOLDERS = ("skse/plugins", "skse64/plugins", "f4se/plugins", "sfse/plugins", "obse/plugins", "nvse/plugins",
                  "fose/plugins", "bepinex/plugins", "bepinex/core", "bepinex/patchers", "melonloader", "plugins/melon",
                  "scripts/asi", "red4ext/plugins", "bin/x64/plugins")
# File names that games load from their own folder. ReShade, ENB and ASI loaders use these names on purpose.
PROXY_NAMES = frozenset({"dxgi.dll", "d3d9.dll", "d3d10.dll", "d3d11.dll", "d3d12.dll", "dinput8.dll", "version.dll",
                         "winmm.dll", "xinput1_3.dll", "xinput1_4.dll", "opengl32.dll", "winhttp.dll"})
# Characters that make a name display differently from what Windows runs ("gpj.exe" shown as "exe.jpg").
BIDI_CHARS = frozenset("‪‫‬‭‮⁦⁧⁨⁩‎‏")

FILE_ATTRIBUTE_HIDDEN = 0x2
REPARSE = 0x400
FILE_LIMIT = 300_000
HASH_LIMIT = 256 * 1024 * 1024
CHUNK = 1024 * 1024


@dataclass
class Finding:
    path: str
    name: str
    size: int
    level: str
    kind: str
    reason: str
    root: str
    sha256: str = ""


@dataclass
class ShieldReport:
    roots: list
    files_checked: int = 0
    findings: list = field(default_factory=list)
    truncated: bool = False
    links_skipped: int = 0
    unreadable: int = 0
    canceled: bool = False
    seconds: float = 0.0

    def count(self, level):
        return sum(1 for f in self.findings if f.level == level)

    def summary(self):
        if self.canceled:
            return "Stopped before the check finished. Nothing was changed."
        folders = len(self.roots)
        text = (f"Checked {self.files_checked:,}{'+' if self.truncated else ''} files in {folders:,} "
                f"folder{'' if folders == 1 else 's'}. ")
        parts = [f"{self.count(CHECK_FIRST):,} to check first", f"{self.count(NOTE):,} notes",
                 f"{self.count(EXPECTED):,} expected plugin files"]
        text += ", ".join(parts) + ". Nothing was changed."
        if self.truncated:
            text += f" The check stopped at {FILE_LIMIT:,} files."
        if self.links_skipped:
            text += f" {self.links_skipped:,} linked folders were not followed."
        return text


def _key(path):
    return os.path.normcase(os.path.abspath(str(path))).rstrip("\\/")


def unique_roots(paths):
    """Existing folders only, nested folders folded into their parent, order kept."""
    keyed = []
    for raw in paths:
        if not raw:
            continue
        path = Path(str(raw))
        try:
            if not path.is_dir():
                continue
        except OSError:
            continue
        keyed.append((_key(path), path))
    keyed.sort(key=lambda kp: len(kp[0]))
    kept = []
    for key, path in keyed:
        if any(key == k or key.startswith(k + os.sep) for k, _p in kept):
            continue
        kept.append((key, Path(os.path.abspath(str(path)))))
    return [p for _k, p in kept]


def mod_roots(inventory):
    """Folders the last scan recorded as mod or game-content storage."""
    return unique_roots(getattr(m, "path", "") for m in getattr(inventory, "mods", ()) or ())


def _suffixes(name):
    lower = name.casefold()
    parts = lower.split(".")
    return ["." + p for p in parts[1:]] if len(parts) > 1 else []


def _in_loader_folder(path):
    folder = "/" + str(path).replace("\\", "/").rsplit("/", 1)[0].casefold().strip("/") + "/"
    return any("/" + loader + "/" in folder for loader in LOADER_FOLDERS)


def classify(path, root, *, hidden=False):
    """Return (level, kind, reason) for one file, or None when nothing about it stands out."""
    name = str(path).replace("\\", "/").rsplit("/", 1)[-1]
    lower = name.casefold()
    suffixes = _suffixes(name)
    ext = suffixes[-1] if suffixes else ""
    runnable = ext in PROGRAM_EXT or ext in SCRIPT_EXT
    if any(ch in BIDI_CHARS for ch in name):
        return CHECK_FIRST, "Disguised name", ("The name contains hidden direction characters, so it can look like a "
                                                "different file type than the one Windows would run.")
    if runnable and len(suffixes) >= 2 and suffixes[-2] in DECOY_EXT:
        return CHECK_FIRST, "Disguised name", (f"It looks like a {suffixes[-2]} file but it is a {ext} file that "
                                                "Windows can run.")
    if runnable and hidden:
        return CHECK_FIRST, "Hidden program", "A file Windows can run, with the hidden attribute set."
    if ext in PROGRAM_EXT:
        return CHECK_FIRST, "Program", ("A program inside a mod folder. Some mods ship real tools, so check that this "
                                         "one came with a mod you installed.")
    if ext in SCRIPT_EXT:
        return CHECK_FIRST, "Script or shortcut", ("A script or shortcut Windows can run. Mods rarely need one, so "
                                                    "check where it came from.")
    if ext in LIBRARY_EXT:
        if _in_loader_folder(path):
            return EXPECTED, "Loader plugin", "A code library in a mod loader's plugin folder, which is where it belongs."
        if lower in PROXY_NAMES:
            return NOTE, "Proxy loader", ("Games load this file name from their own folder. ReShade, ENB and ASI "
                                          "loaders use it on purpose; make sure you installed one.")
        return NOTE, "Code library", "A code library outside a known mod loader folder. Check it came with a mod."
    return None


def _is_link(entry):
    try:
        if entry.is_symlink():
            return True
        st = entry.stat(follow_symlinks=False)
    except OSError:
        return False
    return bool(getattr(st, "st_file_attributes", 0) & REPARSE)


def sha256_file(path, *, limit=HASH_LIMIT, canceled=lambda: False):
    """Fingerprint a file by reading it. Returns "" for files over the limit or when stopped."""
    try:
        if os.path.getsize(path) > limit:
            return ""
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            while True:
                if canceled():
                    return ""
                block = handle.read(CHUNK)
                if not block:
                    break
                digest.update(block)
        return digest.hexdigest()
    except OSError:
        return ""


def scan(roots, *, limit=FILE_LIMIT, canceled=lambda: False, progress=None, hash_findings=True):
    """Walk each folder without following links and list what stands out. Reads only."""
    started = time.monotonic()
    report = ShieldReport(roots=[str(r) for r in unique_roots(roots)])
    for root in report.roots:
        stack = [root]
        while stack:
            if canceled():
                report.canceled = True
                break
            folder = stack.pop()
            try:
                with os.scandir(folder) as entries:
                    items = list(entries)
            except OSError:
                report.unreadable += 1
                continue
            for entry in items:
                if _is_link(entry):
                    report.links_skipped += 1
                    continue
                try:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    st = entry.stat(follow_symlinks=False)
                except OSError:
                    report.unreadable += 1
                    continue
                report.files_checked += 1
                if report.files_checked >= limit:
                    report.truncated = True
                    break
                hidden = bool(getattr(st, "st_file_attributes", 0) & FILE_ATTRIBUTE_HIDDEN)
                verdict = classify(entry.path, root, hidden=hidden)
                if verdict:
                    level, kind, reason = verdict
                    report.findings.append(Finding(entry.path, entry.name, int(st.st_size), level, kind, reason, root))
            if progress and report.files_checked % 500 == 0:
                progress(report.files_checked)
            if report.truncated:
                break
        if report.truncated or report.canceled:
            break
    report.findings.sort(key=lambda f: (LEVEL_ORDER[f.level], f.name.casefold(), f.path.casefold()))
    if hash_findings and not report.canceled:
        for finding in report.findings:
            if finding.level == EXPECTED:
                continue
            if canceled():
                report.canceled = True
                break
            finding.sha256 = sha256_file(finding.path, canceled=canceled)
    report.seconds = time.monotonic() - started
    return report


def virustotal_url(sha256):
    """The public lookup page for a fingerprint. Only the fingerprint is in the address; no file is sent."""
    if not re.fullmatch(r"[0-9a-f]{64}", sha256 or ""):
        raise ValueError("Not a SHA-256 fingerprint")
    return "https://www.virustotal.com/gui/file/" + sha256


# ------------------------------------------------------------------ Microsoft Defender
@dataclass
class DefenderResult:
    status: str            # "clean", "threats", "error" or "unavailable"
    folder: str = ""
    threats: list = field(default_factory=list)
    files: list = field(default_factory=list)
    code: int = 0
    output: str = ""

    def line(self):
        name = Path(self.folder).name or self.folder
        if self.status == "clean":
            return f"{name}: Microsoft Defender reported no threats in this scan."
        if self.status == "threats":
            return (f"{name}: Microsoft Defender reported {len(self.threats)} threat"
                    f"{'' if len(self.threats) == 1 else 's'}: " + "; ".join(self.threats[:5]))
        if self.status == "unavailable":
            return "Microsoft Defender's command line tool was not found on this PC."
        return f"{name}: Microsoft Defender could not finish this scan (code {self.code})."


def find_defender(env=None):
    """The newest MpCmdRun.exe: the platform folder Defender updates itself into, then the classic location."""
    env = os.environ if env is None else env
    found = []
    data = env.get("PROGRAMDATA") or env.get("ProgramData")
    if data:
        pattern = os.path.join(data, "Microsoft", "Windows Defender", "Platform", "*", "MpCmdRun.exe")
        for path in glob.glob(pattern):
            version = os.path.basename(os.path.dirname(path)).split("-")[0]
            parts = tuple(int(p) for p in version.split(".") if p.isdigit())
            found.append((parts, path))
    if found:
        return max(found)[1]
    program_files = env.get("PROGRAMFILES") or env.get("ProgramFiles")
    if program_files:
        classic = os.path.join(program_files, "Windows Defender", "MpCmdRun.exe")
        if os.path.isfile(classic):
            return classic
    return ""


def defender_args(exe, folder):
    # -DisableRemediation: Defender reports what it finds and applies no action, so nothing is quarantined or deleted.
    return [exe, "-Scan", "-ScanType", "3", "-File", str(folder), "-DisableRemediation"]


_THREAT = re.compile(r"^\s*Threat\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_FILE = re.compile(r"^\s*file\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)


def parse_defender(code, output, folder, *, timed_out=False):
    threats = list(dict.fromkeys(_THREAT.findall(output or "")))
    files = list(dict.fromkeys(_FILE.findall(output or "")))
    if timed_out:
        return DefenderResult("error", str(folder), threats, files, code, output)
    if threats:
        return DefenderResult("threats", str(folder), threats, files, code, output)
    if code == 0:
        return DefenderResult("clean", str(folder), [], [], code, output)
    # Code 2 without a listed threat is Defender's "scanning error" case.
    return DefenderResult("error", str(folder), [], files, code, output)


def defender_scan(runner, exe, folder, *, timeout=1800):
    if not exe:
        return DefenderResult("unavailable", str(folder))
    result = runner.run(defender_args(exe, folder), timeout=timeout, limit=256 * 1024)
    return parse_defender(result.code, result.output, folder, timed_out=result.timed_out)


def activity_text(report, defender=()):
    text = report.summary()
    for result in defender:
        text += " " + result.line()
    return text
