"""Exhume: bring back an older display (GPU) driver that Windows still has stored.

Honesty rules. Game Grave cannot tell which driver was good. "Known good" here means a driver version the owner
marked while it was working, kept in Game Grave's own file. Exhume only lists what Windows reports (the current display
driver and older packages of the same maker still in the driver store). A rollback is the one thing here that changes
Windows: it removes the current driver package from Windows and installs the chosen older one, using the Windows
`pnputil` tool, only after the owner confirms the exact commands. It needs administrator rights, never elevates by
itself, and every attempt is written to the activity log. Game Grave keeps no copy of a removed driver.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

DISPLAY_GUID = "{4d36e968-e325-11ce-bfc1-08002be10318}"
OEM_INF = re.compile(r"oem\d+\.inf", re.I)
VERSION = re.compile(r"(\d{1,4}[/.\-]\d{1,2}[/.\-]\d{1,4})\s+(\d+(?:\.\d+){1,3})")
GUID = re.compile(r"\{[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\}")
CURRENT_SCRIPT = (
    "Get-CimInstance Win32_PnPSignedDriver | Where-Object { $_.DeviceClass -eq 'DISPLAY' } | "
    "Select-Object DeviceName, DriverVersion, InfName, DriverProviderName, "
    "@{n='Date';e={ if ($_.DriverDate) { $_.DriverDate.ToString('yyyy-MM-dd') } else { '' } }} | "
    "ConvertTo-Json -Compress")


@dataclass
class Current:
    name: str
    version: str
    inf: str
    provider: str
    date: str


@dataclass
class Package:
    published: str       # oemNN.inf
    original: str
    provider: str
    version: str
    date: str
    signer: str = ""


@dataclass
class Card:
    current: Current
    older: list = field(default_factory=list)       # Packages, newest first
    marked: dict | None = None                       # the owner's "good" mark for this card, if any
    current_is_marked: bool = False
    reason: str = ""                                 # why rollback is not offered, when it is not


def version_key(text: str) -> tuple:
    parts = re.findall(r"\d+", text or "")
    return tuple(int(p) for p in parts) or (0,)


# ------------------------------------------------------------------ reading what Windows reports
def _run(command: list[str], timeout: int = 40) -> str:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=timeout, creationflags=flags,
                              errors="replace")
    except (OSError, subprocess.SubprocessError):
        raise OSError("Windows would not run that check on this PC.")
    if done.returncode != 0:
        raise OSError((done.stdout or done.stderr or "Windows reported an error.").strip()[:300])
    return done.stdout[:3_000_000]


def query_current() -> str:
    return _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", CURRENT_SCRIPT])


def query_store() -> str:
    return _run(["pnputil", "/enum-drivers"])


def parse_current(text: str) -> list[Current]:
    try:
        data = json.loads(text) if (text or "").strip() else []
    except ValueError:
        return []
    if isinstance(data, dict):
        data = [data]
    found = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        inf = str(item.get("InfName") or "")
        found.append(Current(str(item.get("DeviceName") or "Display adapter"), str(item.get("DriverVersion") or ""),
                             inf, str(item.get("DriverProviderName") or ""), str(item.get("Date") or "")))
    return found


def parse_store(text: str) -> list[Package]:
    """Display-class driver packages from `pnputil /enum-drivers`. Field names are localized on non-English Windows, so
    this goes by the values (an oemNN.inf name, the display class GUID, a date and version) and not by the labels."""
    records, current = [], None
    for line in (text or "").splitlines():
        if ":" not in line:
            continue
        value = line.split(":", 1)[1].strip()
        if OEM_INF.fullmatch(value):
            current = [value]
            records.append(current)
        elif current is not None:
            current.append(value)
    packages = []
    for values in records:
        joined = "\n".join(values)
        guid = GUID.search(joined)
        if not guid or guid.group(0).casefold() != DISPLAY_GUID:
            continue
        match = next((VERSION.search(v) for v in values if VERSION.search(v)), None)
        if match is None or len(values) < 4:
            continue
        packages.append(Package(values[0], values[1], values[2], match.group(2), match.group(1), values[-1]))
    return packages


# ------------------------------------------------------------------ the owner's "good" marks
def exhume_dir() -> Path:
    import core
    return core.config_dir() / "exhume"


def load_marks(root: Path | None = None) -> dict:
    path = (root or exhume_dir()) / "marks.json"
    try:
        if path.stat().st_size > 50_000:
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    clean = {}
    for name, mark in (data.items() if isinstance(data, dict) else ()):
        if isinstance(mark, dict) and isinstance(mark.get("version"), str):
            clean[str(name)[:120]] = {"version": mark["version"][:40], "marked": str(mark.get("marked", ""))[:25]}
    return clean


def save_mark(card_name: str, version: str, root: Path | None = None, now: datetime | None = None) -> None:
    root = Path(root) if root else exhume_dir()
    marks = load_marks(root)
    marks[card_name[:120]] = {"version": version[:40], "marked": (now or datetime.now()).strftime("%Y-%m-%d")}
    root.mkdir(parents=True, exist_ok=True)
    tmp = root / "marks.json.tmp"
    tmp.write_text(json.dumps(marks, indent=2), encoding="utf-8")
    os.replace(tmp, root / "marks.json")


# ------------------------------------------------------------------ putting it together
def build_cards(currents: list[Current], store: list[Package], marks: dict) -> list[Card]:
    cards = []
    for cur in currents:
        card = Card(cur, marked=marks.get(cur.name))
        card.current_is_marked = bool(card.marked and card.marked["version"] == cur.version)
        if not OEM_INF.fullmatch(cur.inf or ""):
            card.reason = "Windows reports this adapter's driver as a built-in one, so there is nothing to roll back."
        elif not cur.provider:
            card.reason = "Windows did not report who made this driver."
        else:
            mine = version_key(cur.version)
            card.older = sorted((p for p in store if p.provider.casefold() == cur.provider.casefold()
                                 and version_key(p.version) < mine and p.published.casefold() != cur.inf.casefold()),
                                key=lambda p: version_key(p.version), reverse=True)
            if not card.older:
                card.reason = "No older driver from the same maker is still stored on this PC."
        cards.append(card)
    return cards


# ------------------------------------------------------------------ the one Windows change
def system_inf_dir() -> str:
    return os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "INF")


def plan_rollback(card: Card, target: Package) -> list[list[str]]:
    """The exact commands, after checking every name. Raises ValueError when any rule is not met."""
    cur = card.current
    if not OEM_INF.fullmatch(cur.inf or "") or not OEM_INF.fullmatch(target.published or ""):
        raise ValueError("Only driver packages Windows has published (oemNN.inf) can be rolled back.")
    if target not in card.older:
        raise ValueError("That driver is not one of the older drivers Windows reports for this adapter.")
    if version_key(target.version) >= version_key(cur.version):
        raise ValueError("That driver is not older than the current one.")
    return [["pnputil", "/delete-driver", cur.inf, "/uninstall", "/force"],
            ["pnputil", "/add-driver", os.path.join(system_inf_dir(), target.published), "/install"]]


def command_text(commands: list[list[str]]) -> str:
    return "\n".join(" ".join(f'"{c}"' if " " in c else c for c in command) for command in commands)


def is_admin() -> bool:
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


@dataclass
class Outcome:
    ok: bool
    message: str
    output: str = ""


def rollback(card: Card, target: Package, *, run=None, log=None, admin=None) -> Outcome:
    """Remove the current package then install the chosen one. Stops at the first failure and says exactly where."""
    commands = plan_rollback(card, target)
    if not (is_admin() if admin is None else admin):
        return Outcome(False, "Windows needs administrator rights for this. Close Game Grave, open it again with "
                              "Run as administrator, and try again. Nothing was changed.")
    run = run or (lambda c: _run(c, timeout=180))
    if log is None:
        import core
        log = core.log_event
    done, details = [], f"{card.current.name}: {card.current.version} to {target.version}"
    for command in commands:
        try:
            output = run(command)
        except OSError as problem:
            log("exhume_rollback", f"{details}. Stopped at: {' '.join(command[:2])}. {problem}",
                result="failed", source="exhume")
            where = ("Nothing was changed." if not done else
                     "The current driver package was removed but the older one did not install. Windows may now be "
                     "using another driver. Check Display adapters in Device Manager, or install a driver from the "
                     "maker's website.")
            return Outcome(False, f"Windows reported: {problem} {where}", "\n".join(done))
        done.append(output.strip())
    log("exhume_rollback", details, result="completed", source="exhume")
    return Outcome(True, "Done. Restart the PC so Windows finishes switching drivers.", "\n".join(done))
