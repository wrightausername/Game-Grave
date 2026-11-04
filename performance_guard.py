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
import sys
import time
from typing import Callable, Iterable
from ctypes import wintypes


# These can remain running after a game exits, including inside Steam libraries.
_NON_GAME_PROCESSES = frozenset({
    "steam.exe", "steamwebhelper.exe", "gameoverlayui.exe",
    "epicgameslauncher.exe", "galaxyclient.exe", "galaxyclient helper.exe",
    "eadesktop.exe", "ealauncher.exe", "eabackgroundservice.exe",
    "ubisoftconnect.exe", "upc.exe", "riotclientservices.exe",
    "riotclientux.exe", "riotclientuxrender.exe",
    "wallpaper32.exe", "wallpaper64.exe", "wallpaperservice32.exe",
    "wallpaperservice64.exe", "wallpaperui.exe", "lively.exe",
    "crashpad_handler.exe", "crashreportclient.exe", "crashreporter.exe",
    "unitycrashhandler32.exe", "unitycrashhandler64.exe",
    "unins000.exe", "uninstall.exe",
})


def _normalize_windows_path(value: str) -> str:
    return ntpath.normcase(ntpath.normpath(value)).rstrip("\\/")


class _Rect(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


class _MonitorInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", _Rect),
                ("rcWork", _Rect), ("dwFlags", wintypes.DWORD)]


def _windows_user32():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    signatures = {
        "GetForegroundWindow": ([], wintypes.HWND),
        "GetDesktopWindow": ([], wintypes.HWND),
        "GetShellWindow": ([], wintypes.HWND),
        "GetWindowThreadProcessId": ([wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD),
        "GetClassNameW": ([wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
        "GetWindowLongW": ([wintypes.HWND, ctypes.c_int], wintypes.LONG),
        "GetWindowRect": ([wintypes.HWND, ctypes.POINTER(_Rect)], wintypes.BOOL),
        "MonitorFromWindow": ([wintypes.HWND, wintypes.DWORD], wintypes.HMONITOR),
        "GetMonitorInfoW": ([wintypes.HMONITOR, ctypes.POINTER(_MonitorInfo)], wintypes.BOOL),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(user32, name)
        function.argtypes = arguments
        function.restype = result
    return user32


def _window_is_fullscreen(user32, hwnd) -> bool:
    """Require another app's borderless window to match its monitor bounds."""
    if not hwnd or hwnd in (user32.GetDesktopWindow(), user32.GetShellWindow()):
        return False
    pid = wintypes.DWORD()
    if not user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)):
        return False
    if not pid.value or pid.value == os.getpid():
        return False
    window_class = ctypes.create_unicode_buffer(256)
    if not user32.GetClassNameW(hwnd, window_class, len(window_class)):
        return False
    if window_class.value.casefold() in {
            "progman", "workerw", "shell_traywnd", "shell_secondarytraywnd"}:
        return False
    style = user32.GetWindowLongW(hwnd, -16)  # GWL_STYLE; 32-bit flags on Win64 too.
    if not style or style & 0x00C00000:  # WS_CAPTION: ordinary/maximized app frame.
        return False
    rect = _Rect()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return False
    monitor = user32.MonitorFromWindow(hwnd, 2)
    if not monitor:
        return False
    info = _MonitorInfo()
    info.cbSize = ctypes.sizeof(info)
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return False
    bounds = info.rcMonitor
    return (rect.right > rect.left and rect.bottom > rect.top and
            all(abs(a - b) <= 4 for a, b in zip(
                (rect.left, rect.top, rect.right, rect.bottom),
                (bounds.left, bounds.top, bounds.right, bounds.bottom))))


def _foreground_is_fullscreen() -> bool:
    """Pause for foreign borderless fullscreen apps, including videos.

    The desktop, taskbars, Game Grave and ordinary maximized apps do not count.
    """
    if os.name != "nt":
        return False
    try:
        user32 = _windows_user32()
        return _window_is_fullscreen(user32, user32.GetForegroundWindow())
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
        self.pause_reason = ""
        self._own_executable = _normalize_windows_path(sys.executable)
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
                if process.pid == os.getpid():
                    continue
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
        if (path == self._own_executable or not path.endswith(".exe")
                or ntpath.basename(path) in _NON_GAME_PROCESSES):
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
        )):
            return True
        return any(path.startswith(prefix) for prefix in self._game_prefixes)

    def active(self) -> bool:
        now = self._clock()
        if (self._last_checked is not None and
                now - self._last_checked < self.refresh_seconds):
            return self._last_active
        self._last_checked = now
        self.pause_reason = ""
        try:
            # Process evidence catches borderless/windowed or background games.
            running = next((p for p in self._process_paths() if self._looks_like_game(p)), None)
            if running:
                self.pause_reason = "Running game process: " + ntpath.basename(running)
                self._last_active = True
            else:
                self._last_active = bool(self._fullscreen())
                if self._last_active:
                    self.pause_reason = "Fullscreen application — leave fullscreen to resume"
        except (OSError, ValueError, TypeError):
            # An unavailable process list must never crash a scan. The
            # fullscreen fallback is independent and may still pause it.
            try:
                self._last_active = bool(self._fullscreen())
                if self._last_active:
                    self.pause_reason = "Fullscreen application — leave fullscreen to resume"
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
