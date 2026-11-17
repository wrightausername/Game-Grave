"""Shared bits for the real-world checks: an isolated Game Grave folder, a report, and waiting without freezing Qt.

Each check runs on the Windows build machine against the real PC (real Recycle Bin, real crashes, real files) but only
ever touches files it created itself in its own scratch folder. Results go to <output>/<name>.json and a summary line.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def isolate(prefix):
    """A fresh temp folder that Game Grave uses as its home (settings, caches, logs), set before Game Grave is imported."""
    scratch = Path(tempfile.mkdtemp(prefix=prefix, dir=os.environ.get("GG_RW_SCRATCH") or None))
    home = scratch / "GGHome"
    home.mkdir()
    os.environ["LOCALAPPDATA"] = str(home)
    os.environ.setdefault("GAME_GRAVE_TRAY", "0")
    os.environ.setdefault("GAME_GRAVE_FIRST_SCAN_CARD", "0")
    os.environ.setdefault("GAME_GRAVE_SPACE_CARD", "0")
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    return scratch


class Report:
    def __init__(self, name, output):
        self.name = name
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.items = []
        self.started = time.time()

    def check(self, what, ok, **detail):
        self.items.append(dict({"check": what, "ok": bool(ok)}, **detail))
        mark = "PASS" if ok else "FAIL"
        extra = ("  " + json.dumps(detail, default=str)[:600]) if detail else ""
        print(f"[{mark}] {what}{extra}", flush=True)
        return ok

    def note(self, what, **detail):
        self.items.append(dict({"check": what, "ok": None}, **detail))
        print(f"[NOTE] {what}  " + json.dumps(detail, default=str)[:800], flush=True)

    def finish(self):
        failed = [i for i in self.items if i["ok"] is False]
        data = {"check": self.name, "seconds": round(time.time() - self.started, 1), "passed": not failed,
                "items": self.items}
        (self.output / f"{self.name}.json").write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        print(f"\n{self.name}: {len(self.items) - len(failed)} of {len(self.items)} fine"
              + (f", FAILED: {[i['check'] for i in failed]}" if failed else ""), flush=True)
        return 0 if not failed else 1


def guarded(report, what, fn, *a, **k):
    """Run one part; an unexpected error is a failed check with its traceback, never the end of the whole run."""
    try:
        return fn(*a, **k)
    except Exception as exc:
        report.check(what, False, error=f"{type(exc).__name__}: {exc}", trace=traceback.format_exc()[-1500:])
        return None


def pump(seconds=0.05):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    end = time.time() + seconds
    while True:
        app.processEvents()
        if time.time() >= end:
            break
        time.sleep(0.01)


def wait_for(test, timeout=60, step=0.05):
    end = time.time() + timeout
    while time.time() < end:
        pump(step)
        if test():
            return True
    return False


def process_usage(pid=None):
    """(memory in MB, CPU seconds so far) for a process on Windows: private memory and user+kernel time."""
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
                    ("PrivateUsage", ctypes.c_size_t)]
    k32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.GetCurrentProcess.restype = wintypes.HANDLE        # a 64-bit pseudo handle; the default int would cut it
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
    k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.c_void_p] * 4
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    own = pid is None
    handle = k32.GetCurrentProcess() if own else k32.OpenProcess(0x1000 | 0x0010, False, int(pid))
    if not handle:
        raise OSError("can't open the process")
    try:
        c = Counters()
        c.cb = ctypes.sizeof(c)
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(c), c.cb):
            raise OSError("Windows didn't give the memory numbers")
        times = [wintypes.FILETIME() for _ in range(4)]
        k32.GetProcessTimes(handle, *[ctypes.byref(t) for t in times])
        cpu = sum(((t.dwHighDateTime << 32) | t.dwLowDateTime) for t in times[2:]) / 1e7
        return c.PrivateUsage / 1024 ** 2, cpu
    finally:
        if not own:
            k32.CloseHandle(handle)


def compile_cs(source: str, target: Path, unsafe=False):
    """Build a tiny C# test program with the .NET compiler that ships with Windows."""
    import subprocess
    csc = Path(os.environ.get("WINDIR", r"C:\Windows")) / r"Microsoft.NET\Framework64\v4.0.30319\csc.exe"
    code = Path(target).with_suffix(".cs")
    code.write_text(source, encoding="utf-8")
    flags = ["/unsafe"] if unsafe else []
    done = subprocess.run([str(csc), "/nologo", *flags, "/target:winexe", f"/out:{target}", str(code)],
                          capture_output=True, text=True)
    code.unlink()
    if done.returncode != 0 or not Path(target).is_file():
        raise RuntimeError("the test program didn't build: " + (done.stdout + done.stderr)[-500:])
