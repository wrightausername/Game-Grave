"""Scan results that stay until the owner scans again (owner instruction, 2026-11-14: "after scanning things the results
should stay there unless i hit rescan or scan again... also with a timestamp of when the scan was").

After each scan the results are written to one file in Game Grave's own settings folder, and read back when Game Grave
starts, so every tab shows the last results with the time they were taken instead of "No scan yet". Only a new scan
replaces them. Nothing here touches the scanned files; every action still checks the file again before it changes it.

Only Game Grave's own result records (an allowlist of dataclasses) are written and read back; anything else in the file
is ignored, so a damaged or edited file can never run code or break the app.
"""
from __future__ import annotations

import dataclasses
import importlib
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path

VERSION = 1
FILE_NAME = "last_scan.json"
MAX_BYTES = 60 * 1024 * 1024
SLOTS = ("inventory", "old_files", "storage", "captures", "grave")
ALLOWED_MODULES = ("core", "launchers", "graveyard", "save_discovery", "gg_desktop.models", "gg_desktop.backend",
                   "gg_desktop.old_files_data", "gg_desktop.other_storage_data", "gg_desktop.captures_data",
                   "gg_desktop.grave_data")
_LOCK = threading.Lock()


def active():
    """On, except where a test run switches it off (GAME_GRAVE_SCAN_CACHE=0) so one check never sees another's results."""
    return os.environ.get("GAME_GRAVE_SCAN_CACHE", "1") != "0"


def cache_path(base=None):
    if base is None:
        from core import config_dir
        base = config_dir()
    return Path(base) / FILE_NAME


# ------------------------------------------------------------------ encoding
def encode(value):
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        cls = type(value)
        if cls.__module__ not in ALLOWED_MODULES:
            raise TypeError("Not a Game Grave result record: " + cls.__module__ + "." + cls.__name__)
        data = {f.name: encode(getattr(value, f.name)) for f in dataclasses.fields(value)}
        return {"__t": cls.__module__ + "." + cls.__qualname__, "v": data}
    if isinstance(value, tuple):
        return {"__tuple": [encode(v) for v in value]}
    if isinstance(value, list):
        return [encode(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return {"__set": [encode(v) for v in sorted(value, key=str)]}
    if isinstance(value, dict):
        return {"__dict": [[encode(k), encode(v)] for k, v in value.items()]}
    if isinstance(value, Path):
        return str(value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError("Cannot keep a " + type(value).__name__)


def _class(name):
    module, _, qual = name.rpartition(".")
    if module not in ALLOWED_MODULES:
        raise ValueError("Not allowed: " + name)
    cls = getattr(importlib.import_module(module), qual)
    if not (isinstance(cls, type) and dataclasses.is_dataclass(cls)):
        raise ValueError("Not a record: " + name)
    return cls


def decode(value):
    if isinstance(value, list):
        return [decode(v) for v in value]
    if isinstance(value, dict):
        if "__t" in value:
            cls = _class(str(value["__t"]))
            raw = value.get("v") or {}
            fields = {f.name: f for f in dataclasses.fields(cls) if f.init}
            kwargs = {k: decode(v) for k, v in raw.items() if k in fields}
            missing = [n for n, f in fields.items() if n not in kwargs and f.default is dataclasses.MISSING
                       and f.default_factory is dataclasses.MISSING]
            if missing:
                raise ValueError(f"{cls.__name__} is missing {missing}")
            return cls(**kwargs)
        if "__tuple" in value:
            return tuple(decode(v) for v in value["__tuple"])
        if "__set" in value:
            return set(decode(v) for v in value["__set"])
        if "__dict" in value:
            return {decode(k): decode(v) for k, v in value["__dict"]}
        return {k: decode(v) for k, v in value.items()}
    return value


# ------------------------------------------------------------------ the file
def read_all(base=None):
    path = cache_path(base)
    try:
        if path.stat().st_size > MAX_BYTES:
            return {}
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict) or raw.get("version") != VERSION:
        return {}
    out = {}
    for slot in SLOTS:
        item = raw.get(slot)
        if not isinstance(item, dict) or "data" not in item:
            continue
        try:
            out[slot] = (decode(item["data"]), float(item.get("saved") or 0))
        except Exception:  # one damaged slot is skipped; the others still come back
            continue
    return out


def keep(slot, value, base=None):
    """Write one slot's results (the others stay). Returns True when written."""
    if slot not in SLOTS:
        raise ValueError(slot)
    with _LOCK:
        return _keep(slot, value, base)


def keep_async(slot, value, base=None):
    """Write after a scan without holding up the screen. The results are not changed by the scan once it has finished."""
    if not active():
        return None
    worker = threading.Thread(target=lambda: keep(slot, value, base), name="gg-scan-cache", daemon=True)
    worker.start()
    return worker


def _keep(slot, value, base=None):
    path = cache_path(base)
    try:
        raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if not isinstance(raw, dict) or raw.get("version") != VERSION:
            raw = {}
    except (OSError, ValueError):
        raw = {}
    try:
        raw[slot] = {"saved": time.time(), "data": encode(value)}
    except TypeError:
        return False
    raw["version"] = VERSION
    text = json.dumps(raw, ensure_ascii=False, separators=(",", ":"))
    if len(text.encode("utf-8")) > MAX_BYTES:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    try:
        temp.write_text(text, encoding="utf-8")
        os.replace(temp, path)
    except OSError:
        try:
            temp.unlink()
        except OSError:
            pass
        return False
    return True


# ------------------------------------------------------------------ words
def when_text(moment, now=None):
    """'Today 5:40 PM', 'Yesterday 9:05 AM', 'Mon 3 Nov, 8:00 PM'. Accepts a timestamp or 'YYYY-MM-DD HH:MM'."""
    if not moment:
        return ""
    if isinstance(moment, str):
        try:
            moment = datetime.strptime(moment, "%Y-%m-%d %H:%M")
        except ValueError:
            return moment
    elif not isinstance(moment, datetime):
        moment = datetime.fromtimestamp(float(moment))
    now = now or datetime.now()
    clock = moment.strftime("%I:%M %p").lstrip("0")
    days = (now.date() - moment.date()).days
    if days == 0:
        return "Today " + clock
    if days == 1:
        return "Yesterday " + clock
    if moment.year == now.year:
        return moment.strftime("%a %d %b").replace(" 0", " ") + ", " + clock
    return moment.strftime("%d %b %Y").lstrip("0") + ", " + clock


def label_for(route, inventory_time, others, now=None):
    """The words for the top bar: which scan the page shows and when it ran."""
    own = {"Other Storage": "storage", "Captures": "captures", "Old Files": "old_files"}.get(route)
    if own == "old_files" and not others.get("old_files"):
        own = None
    if own:
        moment = others.get(own)
        return ("Scanned " + when_text(moment, now)) if moment else "Not scanned yet"
    if route == "Graveyard" and others.get("grave"):
        return "Leftovers scanned " + when_text(others["grave"], now)
    return ("Last scan " + when_text(inventory_time, now)) if inventory_time else "Not scanned yet"


# ------------------------------------------------------------------ putting results back when Game Grave starts
def _still_there(items):
    """Drop files that are gone since the scan, so a restored list never shows something already removed."""
    return [i for i in items if os.path.exists(str(getattr(i, "path", "")))]


def restore(window, base=None):
    """Put the last results back into the tabs. Returns the slots that came back."""
    if not active():
        return []
    found = read_all(base)
    back = []
    inventory = found.get("inventory", (None, 0))[0]
    from gg_desktop.backend import Inventory
    if isinstance(inventory, Inventory) and inventory.scanned_at:
        for name in ("files", "recordings", "screenshots"):
            setattr(inventory, name, _still_there(getattr(inventory, name) or []))
        window.inventory = inventory
        back.append("inventory")
    old = found.get("old_files", (None, 0))[0]
    from gg_desktop.old_files_data import ScanResult
    if isinstance(old, ScanResult):
        old.files = _still_there(old.files)
        from gg_desktop.old_files import OldFilesSession
        session = window._old_files_session = OldFilesSession(window)
        session.result, session.message = old, old.summary()
        back.append("old_files")
    from gg_desktop.other_storage_data import StorageReport
    storage = found.get("storage", (None, 0))[0]
    if isinstance(storage, StorageReport):
        from gg_desktop import other_storage_page
        other_storage_page.state_of(window).report = storage
        back.append("storage")
    from gg_desktop.captures_data import CaptureReport
    captures = found.get("captures", (None, 0))[0]
    if isinstance(captures, CaptureReport):
        captures.captures = _still_there(captures.captures)
        from gg_desktop import captures_page
        state = captures_page.state_of(window)
        state.report, state.scanned = captures, True
        back.append("captures")
    grave = found.get("grave", (None, 0))[0]
    if isinstance(grave, StorageReport):
        from gg_desktop import grave_page
        state = grave_page.state_of(window)
        state.report, state.scanned = grave, True
        back.append("grave")
    return back


def times_of(window):
    """When each result on screen was taken, for the top bar."""
    out = {}
    for slot, getter in (("storage", lambda: window._storage_state.report),
                         ("captures", lambda: window._captures_state.report),
                         ("grave", lambda: window._grave_state.report),
                         ("old_files", lambda: window._old_files_session.result)):
        try:
            report = getter()
        except AttributeError:
            continue
        moment = getattr(report, "scanned_at", 0) if report is not None else 0
        if moment:
            out[slot] = moment
    return out
