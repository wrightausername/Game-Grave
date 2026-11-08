"""Live readings for the System Health panel. Read only, no Qt, no third-party packages.

Each reader returns a whole percentage 0 to 100, or None when Windows (or this platform) cannot say. The page shows
"Unavailable" for None and never invents a verdict such as "Good".
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys


def clamp_percent(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return int(round(max(0.0, min(100.0, number))))


def system_drive() -> str:
    """The drive Windows runs from, or the root of the current directory elsewhere."""
    if sys.platform == "win32":
        return os.environ.get("SystemDrive", "C:") + "\\"
    return str(Path(os.getcwd()).anchor or "/")


def storage_percent(path=None):
    """Used share of the drive holding `path`, as Windows reports it."""
    try:
        usage = shutil.disk_usage(path or system_drive())
    except OSError:
        return None
    return clamp_percent(usage.used * 100 / usage.total) if usage.total > 0 else None


def storage_text(path=None) -> str:
    from core import human_size
    try:
        usage = shutil.disk_usage(path or system_drive())
    except OSError:
        return "Unavailable"
    return f"{human_size(usage.used)} of {human_size(usage.total)} used"


def memory_percent():
    """Share of physical memory in use (Windows GlobalMemoryStatusEx)."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class Status(ctypes.Structure):
            _fields_ = [("length", wintypes.DWORD), ("load", wintypes.DWORD), ("total", ctypes.c_ulonglong),
                        ("avail", ctypes.c_ulonglong), ("page_total", ctypes.c_ulonglong),
                        ("page_avail", ctypes.c_ulonglong), ("virtual_total", ctypes.c_ulonglong),
                        ("virtual_avail", ctypes.c_ulonglong), ("extended", ctypes.c_ulonglong)]

        status = Status()
        status.length = ctypes.sizeof(Status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None
        return clamp_percent(status.load)
    except (AttributeError, OSError, ValueError):
        return None


def _times():
    import ctypes
    from ctypes import wintypes

    idle, kernel, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
    if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
        return None
    def whole(ft):
        return (ft.dwHighDateTime << 32) | ft.dwLowDateTime
    return whole(idle), whole(kernel) + whole(user)  # kernel time already includes idle time


class CpuMeter:
    """CPU use between two samples. The first call has nothing to compare with and returns None."""

    def __init__(self, reader=None):
        self._reader = reader or (_times if sys.platform == "win32" else (lambda: None))
        self._last = None
        self.waiting = False  # True after the first sample, which has nothing to compare with

    def sample(self):
        try:
            now = self._reader()
        except (AttributeError, OSError, ValueError):
            return None
        if not now:
            return None
        last, self._last = self._last, now
        self.waiting = not last
        if not last:
            return None
        idle, total = now[0] - last[0], now[1] - last[1]
        if total <= 0:
            return None
        return clamp_percent((total - idle) * 100 / total)


def report_lines(cpu_percent=None) -> list:
    """Label and value pairs for the text report. Values are readings taken now."""
    def fmt(value):
        return "Unavailable" if value is None else f"{value}%"
    return [("Operating system", sys.platform), ("Storage in use", fmt(storage_percent()) + " (" + storage_text() + ")"),
            ("Memory in use", fmt(memory_percent())), ("CPU in use", fmt(cpu_percent))]
