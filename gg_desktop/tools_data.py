"""More Tools: the tile registry and the report, CSV and hash helpers. No Qt in this module.

Honesty rules for this tab:
* A tile is "go" (opens the tab that owns the work), "run" (a real action implemented in this tab) or "unavailable".
* Owner-approved exception (polish pass): seven tiles change or inspect Windows (Windows Cleanup, Game Optimizer,
  Memory Optimizer, Startup Manager, Command Runner, File Associations, Junction Manager). Each one names exactly what
  it will change, asks first and writes the activity log. See `winpc.py` and `tools_windows.py`.
* A tile that cannot work would stay visible, dimmed, and say why. Nothing else changes Windows or runs commands.
* Reports carry only numbers the scan reported. Sizes are "reported", never "freed", and nothing is called safe.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
from pathlib import Path
import re

GO, RUN, OFF = "go", "run", "unavailable"

OFF_REASON = "This tool is not available on this PC."


@dataclass(frozen=True)
class Tile:
    key: str
    title: str
    symbol: str
    kind: str
    target: str = ""   # a tab name for "go", an action key for "run"
    note: str = ""     # one honest line for the tooltip


@dataclass(frozen=True)
class Category:
    key: str
    title: str
    blurb: str
    tone: str
    tiles: tuple


def _off(key, title, symbol, why=OFF_REASON):
    return Tile(key, title, symbol, OFF, note=why)


CATEGORIES = (
    Category("maintenance", "Maintenance", "Keep your PC clean and running smoothly.", "red", (
        Tile("disk_cleanup", "Disk Cleanup", "trash", GO, "Other Storage", "Review reported storage items in Other Storage."),
        Tile("temp_files", "Temp Files", "file", GO, "Other Storage", "Temporary files found by the scan are reviewed in Other Storage."),
        Tile("clear_caches", "Clear Caches", "refresh", GO, "Other Storage", "Cache folders found by the scan are reviewed in Other Storage."),
        Tile("windows_cleanup", "Windows Cleanup", "settings", RUN, "windows_cleanup", "Delete temporary files older than 2 days from your Windows temp folders after you confirm."))),
    Category("optimization", "Optimization", "Reduce clutter that may slow down games.", "cyan", (
        Tile("game_optimizer", "Game Optimizer", "play", RUN, "game_optimizer", "Turn on Game Mode, turn off background recording or switch the power plan. Undo restores your values."),
        Tile("shader_cache", "Shader Cache", "dna", GO, "Game DNA", "Shader caches proven per game are shown in Game DNA."),
        Tile("memory_optimizer", "Memory Optimizer", "storage", RUN, "memory_optimizer", "Choose open apps to close politely, largest memory first. Windows itself is never listed."),
        Tile("startup_manager", "Startup Manager", "clock", RUN, "startup_manager", "Turn your startup programs off or on with the same switch Task Manager uses."))),
    Category("backup", "Backup and Recovery", "Back up and restore what matters most.", "purple", (
        Tile("game_backup", "Game Backup", "archive", RUN, "save_vault", "Back up a folder you choose into a verified Save Vault ZIP."),
        Tile("save_backup", "Save Backup", "shield", RUN, "save_vault", "Back up a save folder you choose into a verified Save Vault ZIP."),
        Tile("mod_backup", "Mod Backup", "mods", RUN, "save_vault", "Back up a mod folder you choose into a verified Save Vault ZIP."),
        Tile("resurrection_kit", "Resurrection Kit", "grave", RUN, "kit_menu", "Create, inspect, rehearse, compare or transfer verified kits."))),
    Category("analysis", "Analysis and Reporting", "Understand what uses your space.", "magenta", (
        Tile("storage_analyzer", "Storage Analyzer", "storage", GO, "Overview", "The reported storage breakdown lives in Overview."),
        Tile("game_size_report", "Game Size Report", "game", RUN, "game_report", "Save a CSV of installed games and their reported sizes."),
        Tile("mod_report", "Mod Report", "mods", RUN, "mod_report", "Save a CSV of the mod and game folders the scan found."),
        Tile("system_report", "System Report", "list", RUN, "system_report", "Save a text summary of the last scan and this PC."))),
    Category("utilities", "Utilities", "Handy tools for everyday tasks.", "blue", (
        Tile("screenshot_tools", "Screenshot Tools", "camera", GO, "Captures", "Screenshots are reviewed in Captures."),
        Tile("recording_tools", "Recording Tools", "radio", GO, "Captures", "Recordings are reviewed in Captures."),
        Tile("bulk_files", "Bulk File Manager", "folder", GO, "Old Files", "Review many files at once in Old Files."),
        Tile("hash_checker", "Hash Checker", "check", RUN, "hash", "Compute a SHA-256 checksum of any file you choose."))),
    Category("advanced", "Advanced Tools", "Powerful tools for experienced users.", "yellow", (
        Tile("command_runner", "Command Runner", "list", RUN, "command_runner", "Run one command line you type or pick, after you see it and confirm."),
        Tile("file_associations", "File Associations", "file", RUN, "file_associations", "Look up which app opens a file type and jump to Windows Default apps."),
        Tile("junction_manager", "Junction Manager", "folder", RUN, "junction_manager", "List, create or remove folder junctions. Removing deletes only the link."),
        Tile("advanced_cleanup", "Advanced Cleanup", "grave", GO, "Graveyard", "Reviewed items and protected folders live in the Graveyard."))),
)

TABS = (
    ("hub", "Toolbox Hub", "All tools and utilities", "grid",
     ("maintenance", "optimization", "backup", "analysis", "utilities", "advanced")),
    ("system", "System Tools", "PC maintenance and health", "settings", ("maintenance", "optimization", "analysis")),
    ("game", "Game Tools", "Game-specific utilities", "game", ("backup", "analysis", "utilities")),
    ("file", "File Tools", "Manage and work with files", "folder", ("maintenance", "utilities")),
    ("repair", "Repair and Fix", "Backups and recovery", "shield", ("backup", "maintenance")),
    ("advanced", "Advanced", "Power user tools", "star", ("advanced", "utilities")),
)

_by_tab = {key: cats for key, _t, _s, _i, cats in TABS}


def categories_for(tab_key):
    """Categories shown under a top tab, in registry order. Unknown tabs fall back to the full hub."""
    wanted = _by_tab.get(tab_key, _by_tab["hub"])
    return tuple(c for c in CATEGORIES if c.key in wanted)


def all_tiles():
    return tuple(t for c in CATEGORIES for t in c.tiles)


def tile(key):
    return next((t for t in all_tiles() if t.key == key), None)


QUICK_ACTIONS = (
    ("scan", "Scan This PC", "refresh", "red", "Run the read-only scan again."),
    ("size_report", "Game Size Report", "game", "cyan", "Save a CSV of installed games and their reported sizes."),
    ("caches", "Review Game Caches", "trash", "green", "Open Other Storage to review cache and temp findings."),
    ("saves", "Back Up My Saves", "download", "yellow", "Create a verified Save Vault ZIP of a folder you choose."),
    ("kit", "Open Resurrection Kit", "grave", "purple", "Create, inspect, rehearse, compare or transfer verified kits."),
)

KIT_ACTIONS = (
    ("create", "Create verified Resurrection Kit", "Build a new verified kit from folders you choose."),
    ("restore", "Inspect and restore a kit to a NEW folder", "Check a kit, then restore it into an empty folder."),
    ("rehearse", "Rehearse recovery in isolation", "Try a restore without touching active game files."),
    ("missing", "Check missing pieces", "A diagnostic, not proof that a kit is complete."),
    ("compare", "Compare two kit snapshots", "Show what changed between two verified kits."),
    ("versions", "Browse Time Machine snapshots", "List verified kit manifests in a folder, newest first."),
    ("transfer", "Prepare a portable PC-to-PC kit", "Build a new portable kit folder."),
)


# ------------------------------------------------------------------ CSV and reports
def csv_safe(value) -> str:
    """Spreadsheet programs may run a cell that starts with a formula character. Prefix it with a quote."""
    text = str(value)
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else text


def write_csv(path, header, rows) -> int:
    """Write a UTF-8 CSV that Excel opens correctly. Returns the number of data rows."""
    count = 0
    with Path(path).open("w", encoding="utf-8-sig", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(header)
        for line in rows:
            writer.writerow([csv_safe(cell) for cell in line])
            count += 1
    return count


def size_cell(value):
    return "" if value is None else str(max(0, int(value)))


GAME_HEADER = ("Game", "Launcher", "Reported size (bytes)", "Size source", "Install path", "Install evidence", "Status")


def game_rows(games):
    rows = []
    for g in sorted(games, key=lambda g: ((g.size_bytes is None), -(g.size_bytes or 0), g.name.casefold())):
        rows.append((g.name, g.launcher, size_cell(g.size_bytes), g.size_source if g.size_bytes is not None else "Not reported",
                     g.install_path, g.install_evidence, g.status))
    return rows


MOD_HEADER = ("Name", "Kind", "Reported size (bytes)", "Files", "Status", "Path", "Indicators", "Note")


def mod_rows(mods):
    rows = []
    for m in sorted(mods, key=lambda m: (-max(0, m.apparent_bytes), m.name.casefold())):
        rows.append((m.name, m.source, size_cell(m.apparent_bytes), max(0, m.file_count) if not m.truncated else
                     f"{max(0, m.file_count)}+", m.status, m.path, "; ".join(m.indicators), m.advice))
    return rows


def system_report_text(*, inventory, system, settings, generated: str, version: str = "") -> str:
    """A plain-text summary. Counts and sizes are what the scan reported on this PC; nothing leaves it."""
    sized = [g.size_bytes for g in inventory.games if g.size_bytes is not None]
    lines = [
        "Game Grave system report",
        f"Generated: {generated}",
    ]
    if version:
        lines.append(f"Version: {version}")
    lines += [
        "",
        "Last scan",
        f"  Completed: {inventory.scanned_at or 'No scan has finished in this session'}",
        f"  Games found: {len(inventory.games)} ({len(sized)} with a reported size)",
        f"  Reported game size total: {_size(sum(sized))}",
        f"  Mod and game folders: {len(inventory.mods)}",
        f"  Files in the selected folder: {len(inventory.files)}",
        f"  Screenshots: {len(inventory.screenshots)}, recordings: {len(inventory.recordings)}",
        f"  Protected save folders: {len(inventory.saves)}",
        f"  Graveyard items: {len(inventory.graveyard)}",
    ]
    if inventory.file_scan_root:
        lines.append(f"  File folder scanned: {inventory.file_scan_root}")
    if inventory.warnings:
        lines.append(f"  Scan warnings: {len(inventory.warnings)}")
        lines += [f"    - {w}" for w in inventory.warnings[:20]]
    roots = [("Steam library folders", settings.get("steam_extra_roots")), ("Other launcher folders", settings.get("other_library_roots")),
             ("Mod folders", settings.get("mod_extra_roots"))]
    lines += ["", "Folders you added"]
    for name, value in roots:
        items = [str(v) for v in value] if isinstance(value, list) else []
        lines.append(f"  {name}: {len(items)}")
        lines += [f"    {v}" for v in items[:20]]
    lines += ["", "This PC (live readings)"]
    for label_, value in system:
        lines.append(f"  {label_}: {value}")
    lines += ["", "Sizes are what the scan reported. They are not a promise of space freed and do not mean anything is safe to remove."]
    return "\n".join(lines) + "\n"


def _size(n):
    from core import human_size
    return human_size(n)


def write_text(path, text) -> int:
    data = text.replace("\r\n", "\n")
    Path(path).write_text(data, encoding="utf-8", newline="\r\n")
    return len(data.splitlines())


# ------------------------------------------------------------------ hash checker
CHUNK = 1024 * 1024
HEX = re.compile(r"[0-9a-fA-F]{64}")


def sha256_file(path, canceled=lambda: False, progress=None) -> str:
    """Stream a file so a large game archive never fills memory. Raises InterruptedError when canceled."""
    target = Path(path)
    total = target.stat().st_size
    digest, done = hashlib.sha256(), 0
    with target.open("rb") as source:
        while True:
            if canceled():
                raise InterruptedError("Hash check canceled.")
            block = source.read(CHUNK)
            if not block:
                break
            digest.update(block)
            done += len(block)
            if progress:
                progress(done, total)
    return digest.hexdigest()


def clean_expected(text) -> str:
    """Accept a pasted checksum with spaces, a trailing file name or upper case. Returns "" when it is not 64 hex digits."""
    for token in str(text or "").replace("*", " ").split():
        if HEX.fullmatch(token):
            return token.lower()
    squeezed = "".join(str(text or "").split())
    return squeezed.lower() if HEX.fullmatch(squeezed) else ""


def compare_hash(actual: str, expected_text: str):
    """(state, message): "empty", "invalid", "match" or "different". Never claims the file is good, only that bytes match."""
    if not str(expected_text or "").strip():
        return "empty", "Paste the checksum the publisher gave you to compare."
    expected = clean_expected(expected_text)
    if not expected:
        return "invalid", "That is not a SHA-256 checksum. It should be 64 hexadecimal digits."
    if expected == str(actual).lower():
        return "match", "The checksums match. The file is byte for byte what that checksum describes."
    return "different", "The checksums are different. This file is not the one that checksum describes."


# ------------------------------------------------------------------ active tasks and the tool log
@dataclass(frozen=True)
class Task:
    kind: str
    title: str
    detail: str
    percent: int | None   # None means the work cannot report progress
    cancelable: bool


def build_tasks(*, scanning=False, scan_percent=0, scan_stage="", cleaning=False, hash_name="", hash_percent=0):
    """The work Game Grave is really doing right now. Nothing is listed unless a flag says it is running."""
    tasks = []
    if scanning:
        tasks.append(Task("scan", "Scanning this PC (read only)", (scan_stage or "Reading local records") +
                          ". No files are changed.", max(0, min(100, int(scan_percent))), True))
    if cleaning:
        tasks.append(Task("work", "Backup or cleanup in progress",
                          "Existing files are not modified. This cannot report progress or be canceled.", None, False))
    if hash_name:
        tasks.append(Task("hash", "Checking " + hash_name, "Reading the file to compute its SHA-256 checksum.",
                          max(0, min(100, int(hash_percent))), True))
    return tasks


def log_lines(events, limit=3):
    """Newest activity first, in the same plain English the Undo Center uses: (title, when, status)."""
    from core import friendly_activity
    ordered = sorted((e for e in events if isinstance(e, dict)), key=lambda e: str(e.get("date", "")), reverse=True)
    lines = []
    for event in ordered[:max(0, limit)]:
        item = friendly_activity(event)
        lines.append((item["title"], item["date"], item["status"]))
    return lines
