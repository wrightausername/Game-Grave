"""Hardware tab data: the parts Windows reports, live load, play sessions you record, and upgrade notes.

Honest by design. Parts come from what Windows reports (CIM) and nothing else. Live graphics numbers come from
`nvidia-smi` when it is present. With any other card (AMD, Intel), graphics load and video memory in use come from
Windows' own performance counters, the ones Task Manager shows; graphics temperature and the card's total video
memory are then not readable and are shown that way, never guessed. CPU temperature
is not offered because Windows does not report a trustworthy one. An upgrade note appears only when sessions that
YOU recorded point at it, says what was measured, and says what it cannot tell you. No frame-rate promises, no
prices, no "safe to upgrade" claims. Nothing here changes Windows or any file except its own sessions file.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

MIN_SESSIONS = 3          # fewer recorded sessions than this is not evidence
MIN_SESSION_SECONDS = 120  # a shorter recording is thrown away
KEEP_SESSIONS = 30
VRAM_FULL = .95
MEMORY_FULL = .90
CPU_BUSY = 85.0
GB = 1024 ** 3

MEMORY_TYPES = {20: "DDR", 21: "DDR2", 24: "DDR3", 26: "DDR4", 34: "DDR5"}

SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$cpu = Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed,SocketDesignation
$gpu = Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion,CurrentHorizontalResolution,CurrentVerticalResolution,CurrentRefreshRate
$mem = Get-CimInstance Win32_PhysicalMemory | Select-Object Capacity,Speed,ConfiguredClockSpeed,SMBIOSMemoryType
$slots = (Get-CimInstance Win32_PhysicalMemoryArray | Measure-Object -Property MemoryDevices -Sum).Sum
$board = Get-CimInstance Win32_BaseBoard | Select-Object Manufacturer,Product
$bios = Get-CimInstance Win32_BIOS | Select-Object SMBIOSBIOSVersion
$os = Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber
$disks = Get-PhysicalDisk | Select-Object DeviceId,FriendlyName,MediaType,BusType,Size
$parts = Get-Partition | Where-Object { $_.DriveLetter } | Select-Object DriveLetter,DiskNumber
$vols = Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" | Select-Object DeviceID,VolumeName,Size,FreeSpace
[pscustomobject]@{cpu=@($cpu);gpu=@($gpu);mem=@($mem);slots=$slots;board=$board;bios=$bios;os=$os;disks=@($disks);parts=@($parts);vols=@($vols)} | ConvertTo-Json -Depth 4 -Compress
"""


# ------------------------------------------------------------------ what Windows reports
@dataclass(frozen=True)
class Cpu:
    name: str
    cores: int
    threads: int
    base_ghz: float
    socket: str


@dataclass(frozen=True)
class Gpu:
    name: str
    driver: str


@dataclass(frozen=True)
class Memory:
    total_gb: float
    sticks: int
    slots: int
    kind: str
    rated_mts: int
    running_mts: int


@dataclass(frozen=True)
class Drive:
    letter: str
    label: str
    total: int
    free: int
    model: str
    kind: str  # "NVMe", "SSD", "hard drive" or "unknown"

    @property
    def fast(self) -> bool:
        return self.kind in ("NVMe", "SSD")


@dataclass(frozen=True)
class Specs:
    cpu: Cpu | None = None
    gpus: tuple = ()
    memory: Memory | None = None
    board: str = ""
    bios: str = ""
    os_name: str = ""
    os_version: str = ""
    display: str = ""
    drives: tuple = ()


def _list(value) -> list:
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _text(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def drive_kind(media: str, bus: str) -> str:
    media, bus = (media or "").casefold(), (bus or "").casefold()
    if bus == "nvme":
        return "NVMe"
    if media == "ssd":
        return "SSD"
    if media == "hdd":
        return "hard drive"
    return "unknown"


def parse_specs(text: str) -> Specs:
    try:
        data = json.loads(text) if (text or "").strip() else {}
    except ValueError:
        return Specs()
    if not isinstance(data, dict):
        return Specs()

    cpu = None
    first = next(iter(_list(data.get("cpu"))), None)
    if first and _text(first.get("Name")):
        cpu = Cpu(_text(first.get("Name")), _int(first.get("NumberOfCores")), _int(first.get("NumberOfLogicalProcessors")),
                  round(_int(first.get("MaxClockSpeed")) / 1000, 2), _text(first.get("SocketDesignation")))

    gpus, display = [], ""
    for item in _list(data.get("gpu")):
        name = _text(item.get("Name"))
        if not name or name.casefold().startswith(("microsoft basic", "microsoft remote")):
            continue
        gpus.append(Gpu(name, _text(item.get("DriverVersion"))))
        width, height, rate = (_int(item.get(k)) for k in ("CurrentHorizontalResolution", "CurrentVerticalResolution",
                                                          "CurrentRefreshRate"))
        if not display and width and height:
            display = f"{width} x {height}" + (f" at {rate} Hz" if rate > 1 else "")

    memory = None
    sticks = _list(data.get("mem"))
    capacity = sum(_int(s.get("Capacity")) for s in sticks)
    if capacity > 0:
        kinds = {MEMORY_TYPES.get(_int(s.get("SMBIOSMemoryType")), "") for s in sticks} - {""}
        rated = [_int(s.get("Speed")) for s in sticks if _int(s.get("Speed")) > 0]
        running = [_int(s.get("ConfiguredClockSpeed")) for s in sticks if _int(s.get("ConfiguredClockSpeed")) > 0]
        memory = Memory(round(capacity / GB, 1), len(sticks), _int(data.get("slots")),
                        kinds.pop() if len(kinds) == 1 else "", min(rated) if rated else 0, min(running) if running else 0)

    board_item = data.get("board") if isinstance(data.get("board"), dict) else {}
    board = _text(f"{board_item.get('Manufacturer', '')} {board_item.get('Product', '')}")
    bios_item = data.get("bios") if isinstance(data.get("bios"), dict) else {}
    os_item = data.get("os") if isinstance(data.get("os"), dict) else {}

    letters = {}  # drive letter -> disk number
    for part in _list(data.get("parts")):
        letter = _text(part.get("DriveLetter")).upper()[:1]
        if letter:
            letters[letter] = str(part.get("DiskNumber"))
    disks = {str(d.get("DeviceId")): d for d in _list(data.get("disks"))}
    drives = []
    for vol in _list(data.get("vols")):
        letter = _text(vol.get("DeviceID")).upper()[:1]
        total = _int(vol.get("Size"))
        if not letter or total <= 0:
            continue
        disk = disks.get(letters.get(letter, ""), {})
        drives.append(Drive(letter, _text(vol.get("VolumeName")), total, max(0, _int(vol.get("FreeSpace"))),
                            _text(disk.get("FriendlyName")), drive_kind(disk.get("MediaType"), disk.get("BusType"))))
    return Specs(cpu, tuple(gpus), memory, board, _text(bios_item.get("SMBIOSBIOSVersion")), _text(os_item.get("Caption")),
                 _text(os_item.get("Version")), display, tuple(sorted(drives, key=lambda d: d.letter)))


def query_specs() -> str:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        done = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", SCRIPT], capture_output=True,
                              text=True, timeout=60, creationflags=flags, errors="replace")
    except (OSError, subprocess.SubprocessError):
        raise OSError("Windows would not read the hardware list on this PC.")
    if done.returncode != 0 or not done.stdout.strip():
        raise OSError("Windows did not return a hardware list.")
    return done.stdout[:2_000_000]


def read_specs() -> Specs:
    return parse_specs(query_specs())


# ------------------------------------------------------------------ live readings
@dataclass(frozen=True)
class GpuLive:
    name: str
    load: float | None
    mem_used_mb: float | None
    mem_total_mb: float | None
    temp_c: float | None


@dataclass(frozen=True)
class Live:
    when: float
    cpu: float | None          # percent, None when not readable
    mem_used_gb: float | None
    mem_total_gb: float | None
    gpu: GpuLive | None        # nvidia-smi, else Windows' GPU counters, else None


def _number(value) -> float | None:
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def parse_nvidia(text: str) -> GpuLive | None:
    for line in (text or "").splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 5 and parts[0]:
            return GpuLive(parts[0], _number(parts[1]), _number(parts[2]), _number(parts[3]), _number(parts[4]))
    return None


def _nvidia_path() -> str | None:
    found = shutil.which("nvidia-smi")
    if found:
        return found
    for base in (os.environ.get("SystemRoot", r"C:\Windows"), os.environ.get("ProgramFiles", r"C:\Program Files")):
        for tail in (r"System32\nvidia-smi.exe", r"NVIDIA Corporation\NVSMI\nvidia-smi.exe"):
            path = Path(base) / tail
            if path.is_file():
                return str(path)
    return None


def query_nvidia() -> GpuLive | None:
    path = _nvidia_path()
    if not path:
        return None
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        done = subprocess.run([path, "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                               "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=8,
                              creationflags=flags, errors="replace")
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_nvidia(done.stdout) if done.returncode == 0 else None


def _win_cpu_times():
    """(idle, busy+idle) in 100 ns ticks from Windows, or None where this is not Windows."""
    if not sys.platform.startswith("win"):
        return None
    import ctypes
    from ctypes import wintypes
    idle, kernel, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
    if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
        return None
    ticks = lambda f: (f.dwHighDateTime << 32) | f.dwLowDateTime  # noqa: E731
    return ticks(idle), ticks(kernel) + ticks(user)  # kernel time already includes idle time


def _win_memory():
    """(used_gb, total_gb) from Windows, or None where this is not Windows."""
    if not sys.platform.startswith("win"):
        return None
    import ctypes

    class Status(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                    ("avail", ctypes.c_ulonglong), ("totalpage", ctypes.c_ulonglong), ("availpage", ctypes.c_ulonglong),
                    ("totalvirt", ctypes.c_ulonglong), ("availvirt", ctypes.c_ulonglong),
                    ("extended", ctypes.c_ulonglong)]
    status = Status()
    status.length = ctypes.sizeof(Status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return (status.total - status.avail) / GB, status.total / GB


# ------------------------------------------------------------------ any card: Windows' own GPU counters
_LUID = re.compile(r"luid_(0x[0-9a-f]+_0x[0-9a-f]+)")


def combine_gpu_counters(engine_rows, memory_rows):
    """(load percent or None, video memory in use in MB or None) from Windows' counter rows.

    `engine_rows` are (instance name, percent) of "GPU Engine \\ Utilization Percentage": one row per process and
    engine. Task Manager's figure for a card is the sum of its 3D engine rows, so that is what this returns, for the
    busiest card. `memory_rows` are (instance name, bytes) of "GPU Adapter Memory \\ Dedicated Usage"."""
    loads, memory = {}, {}
    for name, value in engine_rows or ():
        low = str(name).casefold()
        found = _LUID.search(low)
        if found and "engtype_3d" in low and isinstance(value, (int, float)) and value == value and value >= 0:
            loads[found.group(1)] = loads.get(found.group(1), 0.0) + float(value)
    for name, value in memory_rows or ():
        found = _LUID.search(str(name).casefold())
        if found and isinstance(value, (int, float)) and value == value and value >= 0:
            memory[found.group(1)] = max(memory.get(found.group(1), 0.0), float(value))
    card = None
    if loads:
        card = max(loads, key=lambda k: (round(loads[k], 1), memory.get(k, 0.0)))
    elif memory:
        card = max(memory, key=memory.get)
    load = min(100.0, loads[card]) if card in loads else None
    used = memory[card] / (1024 * 1024) if card in memory else None
    return load, used


class WindowsGpuCounters:
    """Reads the two counters through Windows' PDH library. One query is kept open so each reading is cheap; no
    program is started. Any failure simply means "not readable"."""

    MORE_DATA = 0x800007D2
    DOUBLE = 0x00000200

    def __init__(self):
        self._lock = threading.Lock()
        self._pdh = self._query = self._load = self._memory = None
        self._dead = os.name != "nt"

    def _open(self):
        import ctypes
        from ctypes import wintypes

        class Value(ctypes.Union):
            _fields_ = [("longValue", ctypes.c_long), ("doubleValue", ctypes.c_double), ("largeValue", ctypes.c_longlong),
                        ("ansi", ctypes.c_char_p), ("wide", ctypes.c_wchar_p)]

        class Counter(ctypes.Structure):
            _fields_ = [("status", ctypes.c_ulong), ("value", Value)]

        class Item(ctypes.Structure):
            _fields_ = [("name", ctypes.c_wchar_p), ("counter", Counter)]

        pdh = ctypes.WinDLL("pdh.dll")
        handle = wintypes.HANDLE
        pdh.PdhOpenQueryW.argtypes = [wintypes.LPCWSTR, ctypes.c_size_t, ctypes.POINTER(handle)]
        pdh.PdhAddEnglishCounterW.argtypes = [handle, wintypes.LPCWSTR, ctypes.c_size_t, ctypes.POINTER(handle)]
        pdh.PdhCollectQueryData.argtypes = [handle]
        pdh.PdhGetFormattedCounterArrayW.argtypes = [handle, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                                     ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        pdh.PdhCloseQuery.argtypes = [handle]
        for function in (pdh.PdhOpenQueryW, pdh.PdhAddEnglishCounterW, pdh.PdhCollectQueryData,
                         pdh.PdhGetFormattedCounterArrayW, pdh.PdhCloseQuery):
            function.restype = ctypes.c_ulong
        query = handle()
        if pdh.PdhOpenQueryW(None, 0, ctypes.byref(query)) != 0:
            raise OSError("PDH query")
        load, memory = handle(), handle()
        got_load = pdh.PdhAddEnglishCounterW(query, r"\GPU Engine(*)\Utilization Percentage", 0, ctypes.byref(load)) == 0
        got_memory = pdh.PdhAddEnglishCounterW(query, r"\GPU Adapter Memory(*)\Dedicated Usage", 0, ctypes.byref(memory)) == 0
        if not (got_load or got_memory):
            pdh.PdhCloseQuery(query)
            raise OSError("no GPU counters")
        pdh.PdhCollectQueryData(query)
        self._pdh, self._query, self._item = pdh, query, Item
        self._load, self._memory = (load if got_load else None), (memory if got_memory else None)

    def _rows(self, counter):
        import ctypes
        from ctypes import wintypes
        if counter is None:
            return []
        size, count = wintypes.DWORD(0), wintypes.DWORD(0)
        status = self._pdh.PdhGetFormattedCounterArrayW(counter, self.DOUBLE, ctypes.byref(size), ctypes.byref(count), None)
        if status != self.MORE_DATA or not 0 < size.value <= 16 * 1024 * 1024:
            return []
        buffer = ctypes.create_string_buffer(size.value)
        if self._pdh.PdhGetFormattedCounterArrayW(counter, self.DOUBLE, ctypes.byref(size), ctypes.byref(count), buffer) != 0:
            return []
        items = ctypes.cast(buffer, ctypes.POINTER(self._item))
        limit = min(count.value, size.value // ctypes.sizeof(self._item))
        rows = []
        for index in range(limit):
            item = items[index]
            if item.counter.status in (0, 1):          # valid data, new data
                rows.append((item.name or "", item.counter.value.doubleValue))
        return rows

    def read(self):
        """(load percent or None, MB in use or None), or None when Windows offers neither."""
        if self._dead:
            return None
        with self._lock:
            try:
                if self._pdh is None:
                    self._open()
                    return None                         # a rate needs two collections; the next reading has it
                self._pdh.PdhCollectQueryData(self._query)
                load, used = combine_gpu_counters(self._rows(self._load), self._rows(self._memory))
            except Exception:
                self._dead = True
                return None
        return None if load is None and used is None else (load, used)


_WINDOWS_GPU = WindowsGpuCounters()


def query_windows_gpu(reader=None) -> GpuLive | None:
    """Graphics load and video memory in use for any card, from Windows. No name, total or temperature: Windows'
    counters do not carry them, so they stay unknown."""
    found = (reader or _WINDOWS_GPU.read)()
    if not found:
        return None
    return GpuLive("", found[0], found[1], None, None)


def query_gpu() -> GpuLive | None:
    """NVIDIA's own tool when it answers (it also gives total memory and temperature), else Windows' counters."""
    return query_nvidia() or query_windows_gpu()


class Sampler:
    """One reading at a time. The three sources are injectable so the logic runs anywhere without a real PC."""

    def __init__(self, cpu_times=_win_cpu_times, memory=_win_memory, gpu=query_gpu, clock=time.time):
        self._cpu_times, self._memory, self._gpu, self._clock = cpu_times, memory, gpu, clock
        self._last = None

    def sample(self) -> Live:
        percent = None
        try:
            now = self._cpu_times()
        except Exception:
            now = None
        if now is not None and self._last is not None:
            idle, total = now[0] - self._last[0], now[1] - self._last[1]
            if total > 0:
                percent = max(0.0, min(100.0, 100.0 * (1 - idle / total)))
        if now is not None:
            self._last = now
        try:
            used = self._memory()
        except Exception:
            used = None
        try:
            gpu = self._gpu()
        except Exception:
            gpu = None
        return Live(self._clock(), percent, used[0] if used else None, used[1] if used else None, gpu)


# ------------------------------------------------------------------ sessions you record
@dataclass(frozen=True)
class Session:
    started: float
    seconds: int
    samples: int
    cpu_avg: float | None
    cpu_peak: float | None
    gpu_avg: float | None
    gpu_peak: float | None
    ram_peak_gb: float | None
    ram_total_gb: float | None
    vram_peak_mb: float | None
    vram_total_mb: float | None


def _avg(values):
    return sum(values) / len(values) if values else None


def summarize(readings: list, started: float, ended: float) -> Session | None:
    """None when the recording was too short to count as evidence."""
    seconds = int(ended - started)
    if seconds < MIN_SESSION_SECONDS or not readings:
        return None
    cpu = [r.cpu for r in readings if r.cpu is not None]
    gpu = [r.gpu.load for r in readings if r.gpu and r.gpu.load is not None]
    ram = [r.mem_used_gb for r in readings if r.mem_used_gb is not None]
    vram = [r.gpu.mem_used_mb for r in readings if r.gpu and r.gpu.mem_used_mb is not None]
    totals = [r.gpu.mem_total_mb for r in readings if r.gpu and r.gpu.mem_total_mb]
    ram_totals = [r.mem_total_gb for r in readings if r.mem_total_gb]
    return Session(started, seconds, len(readings), _avg(cpu), max(cpu, default=None), _avg(gpu), max(gpu, default=None),
                   max(ram, default=None), ram_totals[-1] if ram_totals else None, max(vram, default=None),
                   totals[-1] if totals else None)


def sessions_path(root: Path | None = None) -> Path:
    if root is None:
        import core
        root = Path(core.config_dir())
    return Path(root) / "hardware_sessions.json"


def _clean(item) -> Session | None:
    if not isinstance(item, dict):
        return None
    try:
        values = {}
        for name in Session.__dataclass_fields__:
            raw = item.get(name)
            values[name] = None if raw is None else float(raw)
        if values["started"] is None or values["seconds"] is None or values["samples"] is None:
            return None
        values["seconds"], values["samples"] = int(values["seconds"]), int(values["samples"])
        if values["seconds"] < MIN_SESSION_SECONDS or any(
                v is not None and (not math.isfinite(v) or v < 0) for v in values.values()):
            return None
        return Session(**values)
    except (TypeError, ValueError):
        return None


def load_sessions(root: Path | None = None) -> list[Session]:
    try:
        data = json.loads(sessions_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    found = [s for s in (_clean(i) for i in (data if isinstance(data, list) else [])) if s]
    return sorted(found, key=lambda s: s.started)[-KEEP_SESSIONS:]


def save_session(session: Session, root: Path | None = None) -> list[Session]:
    kept = (load_sessions(root) + [session])[-KEEP_SESSIONS:]
    path = sessions_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=".hw-", suffix=".tmp", dir=path.parent)
    with os.fdopen(fd, "w", encoding="utf-8") as sink:
        json.dump([{n: getattr(s, n) for n in Session.__dataclass_fields__} for s in kept], sink)
    os.replace(raw, path)
    return kept


def clear_sessions(root: Path | None = None) -> None:
    try:
        sessions_path(root).unlink()
    except OSError:
        pass


# ------------------------------------------------------------------ upgrade notes
@dataclass(frozen=True)
class Note:
    key: str          # gpu, memory, cpu, storage, power
    title: str
    tag: str
    tone: str         # red, green, cyan, amber, muted
    summary: str
    points: tuple
    limit: str
    action: tuple | None = None   # (button text, route)


def _gb(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".") + " GB"


def _need_more(have: int) -> str:
    missing = MIN_SESSIONS - have
    return (f"Record {missing} more play session{'s' if missing != 1 else ''} of at least "
            f"{MIN_SESSION_SECONDS // 60} minutes. Fewer than {MIN_SESSIONS} is not evidence.")


def _gpu_note(specs: Specs, sessions: list) -> Note:
    limit = "which card to buy, how much faster it would be, or whether your power supply and case can take it."
    name = specs.gpus[0].name if specs.gpus else "your graphics card"
    seen = [s for s in sessions if s.vram_peak_mb and s.vram_total_mb]
    if not seen and not sessions:
        return Note("gpu", "Graphics card", "NEEDS SESSIONS", "muted", "No play sessions recorded yet.",
                    (_need_more(0),), limit)
    if not seen:
        return Note("gpu", "Graphics card", "CANNOT BE READ", "amber",
                    f"Game Grave reads video memory and graphics load only from NVIDIA cards. This PC reports {name}.",
                    ("Your recorded sessions have no video memory readings.",), limit)
    if len(seen) < MIN_SESSIONS:
        return Note("gpu", "Graphics card", "NEEDS SESSIONS", "muted",
                    f"{len(seen)} session{'s' if len(seen) != 1 else ''} with video memory readings so far.",
                    (_need_more(len(seen)),), limit)
    full = [s for s in seen if s.vram_peak_mb >= VRAM_FULL * s.vram_total_mb]
    top = max(seen, key=lambda s: s.vram_peak_mb)
    total_gb = top.vram_total_mb / 1024
    if len(full) * 2 >= len(seen):
        points = [f"Video memory peaked at {_gb(top.vram_peak_mb / 1024)} of {_gb(total_gb)} in {len(full)} of "
                  f"{len(seen)} sessions."]
        loads = [s.gpu_avg for s in full if s.gpu_avg is not None]
        if loads:
            points.append(f"Graphics load averaged {round(_avg(loads))}% in those sessions.")
        return Note("gpu", "Graphics card", "STRONGEST SIGNAL", "red",
                    "Video memory ran close to full in at least half of your recorded sessions.", tuple(points), limit)
    return Note("gpu", "Graphics card", "NO SIGN OF A LIMIT", "cyan",
                "Video memory stayed below full in most of your recorded sessions.",
                (f"Highest video memory use was {_gb(top.vram_peak_mb / 1024)} of {_gb(total_gb)} across {len(seen)} sessions.",),
                limit)


def _memory_note(specs: Specs, sessions: list) -> Note:
    limit = "what newer games will need."
    seen = [s for s in sessions if s.ram_peak_gb and s.ram_total_gb]
    extra = []
    mem = specs.memory
    if mem and mem.rated_mts and mem.running_mts and mem.running_mts < mem.rated_mts * .95:
        extra.append(f"Memory runs at {mem.running_mts} MT/s but is rated for {mem.rated_mts} MT/s. A memory profile "
                     "(XMP or EXPO) may be off in your BIOS.")
    if len(seen) < MIN_SESSIONS:
        return Note("memory", "Memory", "NEEDS SESSIONS", "muted",
                    f"{len(seen)} recorded session{'s' if len(seen) != 1 else ''} so far.",
                    tuple([_need_more(len(seen))] + extra), limit)
    full = [s for s in seen if s.ram_peak_gb >= MEMORY_FULL * s.ram_total_gb]
    top = max(seen, key=lambda s: s.ram_peak_gb)
    if len(full) * 2 >= len(seen):
        return Note("memory", "Memory", "WORTH A LOOK", "amber",
                    "Memory use reached 90% or more in at least half of your recorded sessions.",
                    tuple([f"Highest use was {_gb(top.ram_peak_gb)} of {_gb(top.ram_total_gb)} across {len(seen)} sessions."]
                          + extra), limit)
    return Note("memory", "Memory", "NOT NEEDED YET", "cyan", "Your recorded sessions never came close to using it all.",
                tuple([f"Highest use was {_gb(top.ram_peak_gb)} of {_gb(top.ram_total_gb)} across {len(seen)} sessions."]
                      + extra), limit)


def _cpu_note(specs: Specs, sessions: list) -> Note:
    limit = "whether a faster processor would help in games you have not recorded."
    seen = [s for s in sessions if s.cpu_avg is not None and s.cpu_peak is not None]
    if len(seen) < MIN_SESSIONS:
        return Note("cpu", "Processor", "NEEDS SESSIONS", "muted",
                    f"{len(seen)} recorded session{'s' if len(seen) != 1 else ''} so far.", (_need_more(len(seen)),), limit)
    busy = [s for s in seen if s.cpu_avg >= CPU_BUSY]
    top = max(seen, key=lambda s: s.cpu_peak)
    if len(busy) * 2 >= len(seen):
        return Note("cpu", "Processor", "WORTH A LOOK", "amber",
                    f"Average processor load was {round(CPU_BUSY)}% or higher in at least half of your recorded sessions.",
                    (f"Highest average load was {round(max(s.cpu_avg for s in seen))}% across {len(seen)} sessions.",), limit)
    return Note("cpu", "Processor", "NO SIGN OF A LIMIT", "cyan", "Processor load stayed moderate on average.",
                (f"Highest load was {round(top.cpu_peak)}% across {len(seen)} sessions.",), limit)


def _storage_note(specs: Specs, games: list) -> Note:
    limit = "how much shorter load times would be. Game Grave does not time loads."
    by_letter = {d.letter: d for d in specs.drives}
    slow, unknown = [], 0
    for game in games:
        path = str(getattr(game, "install_path", "") or "")
        drive = by_letter.get(path[:1].upper()) if path[1:2] == ":" else None
        if drive is None or drive.kind == "unknown":
            continue
        if drive.kind == "hard drive":
            size = getattr(game, "size_bytes", None)
            if size is None:
                unknown += 1
            else:
                slow.append((game, drive, int(size)))
    fast = [d for d in specs.drives if d.fast]
    best = max(fast, key=lambda d: d.free, default=None)
    low = [d for d in specs.drives if d.total and d.free < d.total * .10]
    low_points = [f"{d.letter}: has {_gb(d.free / GB)} free of {_gb(d.total / GB)}, under 10%." for d in low]
    if slow:
        total = sum(size for _g, _d, size in slow)
        points = [f"{_gb(total / GB)} of games are on a hard drive ({len(slow)} game{'s' if len(slow) != 1 else ''}), "
                  "found from their install folders."]
        if unknown:
            points.append(f"{unknown} more on a hard drive have no known size.")
        if best:
            points.append(f"{best.letter}: ({best.kind}) has {_gb(best.free / GB)} free.")
        if best and best.free >= total:
            return Note("storage", "Move games off the hard drive", "NO PURCHASE NEEDED", "green",
                        "A fast drive here has room for the games that sit on a hard drive.",
                        tuple(points + low_points + ["Moving games is done in Steam or the launcher. Game Grave moves nothing."]),
                        limit, ("Open More Tools", "More Tools"))
        return Note("storage", "Move games off the hard drive", "WORTH A LOOK", "amber",
                    "Games sit on a hard drive and the fast drives here do not have room for all of them.",
                    tuple(points + low_points), limit, ("Open More Tools", "More Tools"))
    if not specs.drives:
        return Note("storage", "Drives", "CANNOT BE READ", "amber", "Windows did not report any drives.", (), limit)
    if low_points:
        return Note("storage", "Drive space", "LOW SPACE", "amber", "A drive is nearly full.", tuple(low_points), limit,
                    ("Open More Tools", "More Tools"))
    kinds = ", ".join(f"{d.letter}: {d.kind}" for d in specs.drives)
    return Note("storage", "Drives", "NOTHING TO MOVE", "cyan", "No installed game was found on a hard drive.",
                (f"Drives found: {kinds}.",), limit)


def _power_note() -> Note:
    return Note("power", "Power supply", "CANNOT BE READ", "amber",
                "Windows does not report the power supply, so Game Grave cannot judge it.",
                ("If you plan a graphics card upgrade, read the wattage on your power supply's label.",
                 "Compare it with the card maker's listed requirement."),
                "your wattage, age or connectors.")


def advise(specs: Specs, sessions: list, games: list) -> list[Note]:
    return [_gpu_note(specs, sessions), _storage_note(specs, games), _memory_note(specs, sessions),
            _cpu_note(specs, sessions), _power_note()]


# ------------------------------------------------------------------ display helpers
def spec_sheet(specs: Specs) -> str:
    lines = ["Game Grave spec sheet", "(read from Windows; nothing is guessed)", ""]
    if specs.cpu:
        c = specs.cpu
        lines.append(f"CPU: {c.name}, {c.cores} cores, {c.threads} threads, base {c.base_ghz} GHz")
    for g in specs.gpus:
        lines.append(f"GPU: {g.name}" + (f", driver {g.driver}" if g.driver else ""))
    if specs.memory:
        m = specs.memory
        kind = (m.kind + " ") if m.kind else ""
        speed = f" at {m.running_mts} MT/s" if m.running_mts else ""
        lines.append(f"Memory: {_gb(m.total_gb)} {kind}({m.sticks} module{'s' if m.sticks != 1 else ''}"
                     + (f", {m.slots} slots" if m.slots else "") + f"){speed}")
    if specs.board:
        lines.append(f"Motherboard: {specs.board}" + (f", BIOS {specs.bios}" if specs.bios else ""))
    for d in specs.drives:
        lines.append(f"Drive {d.letter}: {d.model or 'unnamed'} ({d.kind}), {_gb(d.total / GB)}, {_gb(d.free / GB)} free")
    if specs.display:
        lines.append(f"Display: {specs.display}")
    if specs.os_name:
        lines.append(f"Windows: {specs.os_name} {specs.os_version}".rstrip())
    return "\n".join(lines)


def short_time(seconds: int) -> str:
    minutes, sec = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min" if hours else f"{minutes} min {sec:02d} s"
