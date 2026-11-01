"""Conservative Windows gameplay guard for nonessential Game Grave scans.

No hooks, injection, overlays or polling inside games. Never run deep scans from a
timer during gameplay. Background-priority worker threads and cooperative checks
minimize contention; no software can promise an absolute 0-FPS impact on every PC.
"""
from __future__ import annotations

from contextlib import contextmanager
import ctypes
import ntpath
import os
import time
from typing import Callable, Iterable


def _normalize_windows_path(value: str) -> str:
    return ntpath.normcase(ntpath.normpath(value)).rstrip("\\/")


def _foreground_is_fullscreen() -> bool:
    """Conservatively treat another fullscreen app as gaming.

    This can also pause for videos/presentations, which is safer than stealing
    disk/CPU time. A maximized Game Grave window does not count as a game.
    """
    if os.name != "nt":
        return False
    try:
        from ctypes import wintypes

        class Rect(ctypes.Structure):
            _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                        ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

        class MonitorInfo(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", Rect),
                        ("rcWork", Rect), ("dwFlags", wintypes.DWORD)]

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        # Explicit pointer-sized signatures are essential on 64-bit Windows.
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.GetWindowRect.argtypes = [
            wintypes.HWND, ctypes.POINTER(Rect)]
        user32.GetWindowRect.restype = wintypes.BOOL
        user32.GetMonitorInfoW.argtypes = [
            wintypes.HMONITOR, ctypes.POINTER(MonitorInfo)]
        user32.GetMonitorInfoW.restype = wintypes.BOOL
        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.MonitorFromWindow.restype = wintypes.HMONITOR
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == os.getpid():
            return False
        rect = Rect()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return False
        monitor = user32.MonitorFromWindow(hwnd, 2)
        if not monitor:
            return False
        info = MonitorInfo()
        info.cbSize = ctypes.sizeof(info)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return False
        bounds = info.rcMonitor
        tolerance = 4
        return (rect.left <= bounds.left + tolerance and
                rect.top <= bounds.top + tolerance and
                rect.right >= bounds.right - tolerance and
                rect.bottom >= bounds.bottom - tolerance)
    except (OSError, AttributeError, TypeError, ValueError):
        return False


class GameActivityDetector:
    """Cached read-only checks for running game processes and fullscreen apps.

    Process enumeration runs at most once per refresh window. If psutil is not
    installed the safe fullscreen fallback remains available, but windowed game
    detection is reduced. Packaged Windows builds should include psutil.
    """

    def __init__(self, *, refresh_seconds: float = 3.0,
                 process_paths: Callable[[], Iterable[str]] | None = None,
                 fullscreen: Callable[[], bool] | None = None,
                 clock: Callable[[], float] = time.monotonic):
        self.refresh_seconds = max(0.1, float(refresh_seconds))
        self._clock = clock
        self._last_checked: float | None = None
        self._last_active = False
        self._game_roots: tuple[str, ...] = ()
        self._game_prefixes: tuple[str, ...] = ()
        self._process_paths = process_paths or self._running_process_paths
        self._fullscreen = fullscreen or _foreground_is_fullscreen

    @staticmethod
    def _running_process_paths() -> Iterable[str]:
        if os.name != "nt":
            return ()
        try:
            import psutil
        except ImportError:
            return ()
        paths = []
        for process in psutil.process_iter(attrs=("exe",), ad_value=None):
            try:
                exe = process.info.get("exe")
                if isinstance(exe, str) and exe:
                    paths.append(exe)
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                continue
        return paths

    def set_game_roots(self, roots: Iterable[str]) -> None:
        """Update from *verified* installed game directories, not user downloads."""
        clean = []
        for root in roots:
            if isinstance(root, str) and root.strip():
                path = _normalize_windows_path(root)
                if path and path not in clean:
                    clean.append(path)
        self._game_roots = tuple(clean[:5000])
        # Store prefixes once instead of rebuilding thousands on each query.
        self._game_prefixes = tuple(root + "\\" for root in self._game_roots)
        self._last_checked = None

    def _looks_like_game(self, raw: str) -> bool:
        path = _normalize_windows_path(raw)
        if not path.endswith(".exe"):
            return False
        # Launcher clients are often running all day. Never interpret them
        # as an active game merely because they live inside a store folder.
        if any(marker in path for marker in (
            "\\epic games\\launcher\\",
            "\\gog galaxy\\",
            "\\riot games\\riot client\\",
            "\\ea desktop\\",
            "\\ubisoft game launcher\\upc.exe",
            "\\ubisoft game launcher\\ubisoftconnect.exe",
        )):
            return False
        if any(marker in path for marker in (
            "\\steamapps\\common\\",
            "\\gog games\\", "\\epic games\\",
            "\\ubisoft game launcher\\games\\",
            "\\riot games\\league of legends\\",
            "\\riot games\\valorant\\",
            "\\xboxgames\\", "\\ea games\\",
            "\\games\\",  # Custom Windows game-library roots
        )):
            return True
        return any(path.startswith(prefix) for prefix in self._game_prefixes)

    def active(self) -> bool:
        now = self._clock()
        if (self._last_checked is not None and
                now - self._last_checked < self.refresh_seconds):
            return self._last_active
        self._last_checked = now
        try:
            # Process evidence catches borderless/windowed or background games.
            running = any(self._looks_like_game(p) for p in self._process_paths())
            self._last_active = bool(running or self._fullscreen())
        except (OSError, ValueError, TypeError):
            # An unavailable process list must never crash a scan. The
            # fullscreen fallback is independent and may still pause it.
            try:
                self._last_active = bool(self._fullscreen())
            except (OSError, ValueError, TypeError):
                self._last_active = False
        return self._last_active


class CooperativeGameplayPause:
    """Cancellation-compatible callback that suspends a scan during gameplay.

    Existing scanners already call cancel() at their bounded traversal points.
    Substitute checkpoint() to wait safely *between* those operations, with no
    busy-wait and no scan activity while waiting. A canceled wait stops promptly.
    """

    def __init__(self, canceled: Callable[[], bool],
                 detector: GameActivityDetector | None = None,
                 on_pause: Callable[[bool], None] | None = None,
                 sleep: Callable[[float], None] = time.sleep,
                 pause_interval: float = 0.3):
        self.canceled = canceled
        self.detector = detector or GameActivityDetector()
        self.on_pause = on_pause
        self.sleep = sleep
        self.pause_interval = max(0.05, pause_interval)

    def checkpoint(self) -> bool:
        if self.canceled():
            return True
        paused = False
        while self.detector.active():
            if not paused:
                paused = True
                if self.on_pause:
                    self.on_pause(True)
            if self.canceled():
                return True
            self.sleep(self.pause_interval)
        if paused and self.on_pause:
            self.on_pause(False)
        return bool(self.canceled())

    def raise_if_canceled(self) -> None:
        if self.checkpoint():
            raise InterruptedError("Scan canceled while checking gameplay activity.")


@contextmanager
def background_worker_priority():
    """Set only this worker thread to Windows background CPU/IO priority.

    Do not lower the entire process priority: that would also slow the UI.
    Windows THREAD_MODE_BACKGROUND_BEGIN/END applies to the calling thread.
    """
    if os.name != "nt":
        yield
        return
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentThread.restype = ctypes.c_void_p
        kernel32.SetThreadPriority.argtypes = [ctypes.c_void_p, ctypes.c_int]
        thread = kernel32.GetCurrentThread()
        entered = bool(kernel32.SetThreadPriority(thread, 0x00010000))
    except (OSError, AttributeError):
        entered = False
        kernel32 = None
        thread = None
    try:
        yield
    finally:
        if entered and kernel32 is not None:
            kernel32.SetThreadPriority(thread, 0x00020000)
