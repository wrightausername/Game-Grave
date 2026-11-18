"""Crash investigation: why did this game crash? Qt-free.

Reads every place Windows and games record a crash, plus the PC's state and what changed before the crashes started,
weighs the clues against a library of known crash signatures, and ranks the likely causes with the evidence for each.
When the clues don't settle it, it never stops at "unknown": it hands over the next tests that will (software,
hardware, the game itself) and the online lookups for the game.

Honesty rules: every cause shows the clues behind it and how sure Game Grave is ("Very likely", "Likely", "Possible").
Nothing here changes the PC. Online lookups are separate (`steam_news`), only run when the person allows them, and send
only the game's Steam ID. Reports hide the Windows user name.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus

from gg_desktop import blackbox_core as bb

WINDOW_DAYS = 30                 # crashes looked at
CHANGE_DAYS = 14                 # changes looked for before the first recent crash
NEAR = timedelta(minutes=3)      # a system event this close to a game crash belongs to it
FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# ------------------------------------------------------------------ causes
# id: (title, what it means, the fix, tests that settle it)
CAUSES = {
    "gpu_driver": ("Graphics driver", "The crash happened inside the graphics driver.",
                   "Install the newest driver from NVIDIA, AMD or Intel, or, if the crashes began after a driver update, "
                   "go back to the previous one with Exhume.", ("driver_back", "driver_new")),
    "gpu_unstable": ("Graphics card stopped responding", "Windows had to reset the graphics card (a driver timeout or a "
                     "'device removed' error). Usually heat, an overclock, power, or the driver.",
                     "Remove any graphics overclock, check temperatures while playing, then try the previous driver.",
                     ("temps", "no_overclock", "driver_back")),
    "overlay": ("An overlay or hook", "The crash happened inside a program that draws on top of games (an overlay, "
                "recorder or monitoring tool).", "Turn that program's in-game overlay off, or close it, and play again.",
                ("overlays_off",)),
    "missing_runtime": ("Missing Microsoft runtime", "The game needs a Microsoft file (Visual C++ or DirectX) that isn't "
                        "installed or is damaged.", "Install Microsoft's Visual C++ 2015-2022 runtime (both 64-bit and "
                        "32-bit), and DirectX for older games.", ("runtimes",)),
    "game_files": ("Damaged or mismatched game files", "One of the game's own files is damaged, missing or from a "
                   "different version.", "Verify the game's files in its launcher; it replaces only what is wrong.",
                   ("verify",)),
    "memory": ("Ran out of memory", "Windows ran low on memory (RAM plus the page file) while the game was running.",
               "Let Windows manage the page file size, close heavy background apps, and keep 15 GB free on drive C.",
               ("pagefile", "space")),
    "vram": ("Ran out of video memory", "The game ran out of graphics card memory.",
             "Lower texture quality and resolution, or turn off ray tracing.", ("lower_settings",)),
    "storage": ("Drive trouble or not enough space", "Windows recorded drive errors, or the drive was nearly full.",
                "Free up space, and check the drive's health; back up important files if it reports problems.",
                ("disk_health", "space")),
    "hardware": ("Unstable hardware", "Windows recorded hardware errors or a blue screen. This points to an overclock, "
                 "memory, power or overheating rather than the game.", "Remove overclocks (including memory XMP/EXPO "
                 "profiles for a test), test memory, and check temperatures.", ("memory_test", "temps", "no_overclock")),
    "power": ("The PC lost power or restarted", "Windows restarted without shutting down properly while playing. Usually "
              "power supply, overheating or hardware instability.", "Check temperatures and the power supply; remove "
              "overclocks for a test.", ("temps", "no_overclock")),
    "anti_cheat": ("Anti-cheat", "The game's anti-cheat stopped it or crashed.", "Repair the anti-cheat from the game's "
                   "folder or launcher, and close tools it may object to (overlays, trainers, monitoring).",
                   ("verify", "overlays_off")),
    "antivirus": ("Antivirus blocked a game file", "Windows Security blocked or removed a file the game uses.",
                  "Check Windows Security's protection history; restore the file only if you trust the game, then "
                  "verify the game's files.", ("defender", "verify")),
    "mod": ("A mod", "The crash points at a mod, or mod files changed just before the crashes started.",
            "Crash Doctor tests the mods for you and names the one crashing the game.", ("crash_doctor",)),
    "game_patch": ("A game update", "The crashes started right after the game updated.",
                   "Check the game's news and discussions for a known issue and a fix; mods made for the old version "
                   "often need updating.", ("online", "crash_doctor")),
    "windows_update": ("A Windows update", "The crashes started right after a Windows update.",
                       "Check for a newer update or a known issue; uninstalling the update is a last resort.",
                       ("online",)),
    "settings": ("The game's settings", "The game's settings or config file changed just before the crashes started.",
                 "Reset the game's settings (Game Grave can move the config aside so the game makes a fresh one).",
                 ("reset_settings",)),
    "audio": ("Audio software", "The crash happened inside audio enhancement software, a known cause of game crashes.",
              "Turn off or uninstall the audio enhancer (for example Nahimic or Sonic Studio) and play again.",
              ("overlays_off",)),
    "dotnet": ("The game's own code", "The game (or a tool it uses) hit an error in its own code.",
               "Verify the game's files; if it keeps happening, check the game's news for a known issue.",
               ("verify", "online")),
}

# ------------------------------------------------------------------ signatures
# (pattern on the crashing file's name, cause, weight, plain words)
MODULE_RULES = (
    (r"^(nvwgf2umx|nvwgf2um|nvoglv64|nvoglv32|nvd3dumx|nvd3dum|nvlddmkm|nvgpucomp64|nvwgf2umx_cfg)\.(dll|sys)$",
     "gpu_driver", 6, "NVIDIA's graphics driver"),
    (r"^(amdxx64|amdxx32|atidxx64|atidxx32|atiumd64|atioglxx|amdvlk64|amdxc64|atikmdag|amdkmdag)\.(dll|sys)$",
     "gpu_driver", 6, "AMD's graphics driver"),
    (r"^(igd10iumd64|igd12umd64|igdumdim64|igxelpicd64|igc64|igdkmd64)\.(dll|sys)$", "gpu_driver", 6,
     "Intel's graphics driver"),
    (r"^(d3d11|d3d12|d3d12core|dxgi|d3d9|dxcore|vulkan-1)\.dll$", "gpu_driver", 2, "DirectX or Vulkan"),
    (r"^(rtsshooks64|rtsshooks|rtsshooks64v|rtssvkhooks64)\.dll$", "overlay", 7, "RivaTuner's overlay (MSI Afterburner)"),
    (r"^(gameoverlayrenderer64|gameoverlayrenderer)\.dll$", "overlay", 5, "Steam's overlay"),
    (r"^(discordhook64|discordhook)\.dll$", "overlay", 7, "Discord's overlay"),
    (r"^(owclient|ow-graphics-vulkan|ow-graphics-hook64)\.dll$", "overlay", 7, "Overwolf's overlay"),
    (r"^(graphics-hook64|graphics-hook32|obs-vulkan64)\.dll$", "overlay", 7, "OBS game capture"),
    (r"^(nvspcap64|nvcamera64|nvpcf)\.dll$", "overlay", 5, "NVIDIA's overlay (GeForce Experience / app)"),
    (r"^(medalhook64|medal)\.dll$", "overlay", 6, "Medal's recorder"),
    (r"^(reshade64|reshade32|dxgi_reshade)\.dll$", "overlay", 6, "ReShade"),
    (r"^(specialk64|specialk32)\.dll$", "overlay", 6, "Special K"),
    (r"^(rzchromasdk64|rzchromaconnect|cue4|icue|lghub_agent|steelseries)\.*.*dll$", "overlay", 4,
     "RGB lighting software hooking the game"),
    (r"^(nahimicosd|nahimicmsiosd|nahimic.*|a-volute.*|ss3svc64|sonicstudio.*|rtkapo64|ssaudioosd.*)\.dll$", "audio",
     7, "audio enhancement software (Nahimic / Sonic Studio)"),
    (r"^(vcruntime140|vcruntime140_1|msvcp140|msvcp140_1|msvcp140_2|concrt140|vcomp140|mfc140u?)\.dll$",
     "missing_runtime", 4, "Microsoft's Visual C++ runtime"),
    (r"^(d3dx9_\d+|d3dx10_\d+|d3dx11_\d+|xinput1_3|x3daudio1_7|xaudio2_7|d3dcompiler_\d+)\.dll$", "missing_runtime", 4,
     "an older DirectX file"),
    (r"^(easyanticheat.*|eac.*|beclient.*|beclient_x64|battleye.*|vgk|vgc|faceit.*|xigncode.*|nprotect.*|"
     r"gameguard.*)\.(dll|sys|exe)$", "anti_cheat", 6, "the game's anti-cheat"),
    (r"^(clr|coreclr|mscorwks|kernelbase)\.dll$", "dotnet", 1, "Windows or .NET reporting an error"),
    (r"^(skse64_.*|f4se_.*|sfse_.*|nvse_.*|obse_.*|xsee_.*|script_extender.*)\.dll$", "mod", 6,
     "the script extender (mods)"),
    (r"^(dinput8|winmm|version|d3d9|dsound|xinput1_4)\.dll$", "mod", 0, "a proxy file mods often replace"),
)
CODE_RULES = {
    "0xc0000135": ("missing_runtime", 8, "a required program file (DLL) was missing"),
    "0xc000007b": ("missing_runtime", 7, "a 32-bit and 64-bit file mix-up, usually a damaged runtime"),
    "0xc0000142": ("missing_runtime", 5, "the game couldn't start (often runtimes or an antivirus)"),
    "0xc0000006": ("storage", 6, "Windows couldn't read part of the game from the drive"),
    "0xc000012f": ("game_files", 7, "a game file is damaged"),
    "0xc0000017": ("memory", 6, "Windows ran out of memory"),
    "0xc000009a": ("memory", 6, "Windows ran out of system resources"),
    "0xc0000374": ("hardware", 2, "memory got corrupted (a bug, a mod, or unstable memory)"),
    "0xc0000409": ("dotnet", 2, "the program stopped itself after detecting a problem"),
    "0xc000001d": ("hardware", 3, "the processor was asked to run an instruction it doesn't have"),
    "0xc0000096": ("hardware", 2, "a privileged instruction (often anti-cheat or unstable hardware)"),
    "0xe0434352": ("dotnet", 4, "an unhandled .NET error in the game's code"),
    "0x80000003": ("dotnet", 2, "the game hit a deliberate stop in its code"),
    "0xc0000005": ("", 0, "an access violation (read memory it shouldn't); the crashing file says who"),
}
# (pattern in a game's own log or crash report, cause, weight, plain words)
LOG_RULES = (
    (r"DXGI_ERROR_DEVICE_(REMOVED|HUNG|RESET)|device (was )?removed|VK_ERROR_DEVICE_LOST|GPU crashed|"
     r"D3D Device Removed|GPU has crashed|TDR", "gpu_unstable", 7, "the game reported the graphics card stopped"),
    (r"out of video memory|E_OUTOFMEMORY.*(texture|resource)|VK_ERROR_OUT_OF_DEVICE_MEMORY|"
     r"ran out of (gpu|video) memory|Out of VRAM", "vram", 7, "the game reported it ran out of video memory"),
    (r"\bout of memory\b|OutOfMemoryException|bad_alloc|Ran out of memory|failed to allocate|"
     r"MemoryAllocationFailed|Couldn't allocate", "memory", 6, "the game reported it ran out of memory"),
    (r"EasyAntiCheat|BattlEye|Anti-?cheat (error|violation|failed)|Untrusted system file", "anti_cheat", 5,
     "the game's log mentions its anti-cheat failing"),
    (r"(missing|could not (find|load)|failed to load).{0,40}\.(dll)", "missing_runtime", 4,
     "the game's log says a program file couldn't be loaded"),
    (r"(checksum|hash) (mismatch|failed)|corrupt(ed)? (pak|archive|file|data)|failed to (open|mount) pak",
     "game_files", 6, "the game's log reports damaged files"),
    (r"(PLUGIN|Probable callstack|POSSIBLE RELEVANT OBJECTS|SKSE|F4SE|Crash Logger|Buffout|Trainwreck)",
     "mod", 4, "a mod crash logger recorded this crash"),
    (r"Shader (compil\w* )?(error|failed)|PSO (cache )?(failed|error)|pipeline cache", "gpu_driver", 3,
     "the game's log reports shader trouble (driver or shader cache)"),
)
SYSTEM_EVENTS = {
    # (log, provider match, id): (cause, weight, words)
    ("System", "Display", 4101): ("gpu_unstable", 8, "Windows reset the graphics driver (it stopped responding)"),
    ("System", "Kernel-Power", 41): ("power", 6, "the PC restarted without shutting down properly"),
    ("System", "EventLog", 6008): ("power", 3, "the previous shutdown was unexpected"),
    ("System", "WER-SystemErrorReporting", 1001): ("hardware", 7, "the PC had a blue screen"),
    ("System", "WHEA-Logger", 17): ("hardware", 5, "Windows recorded a corrected hardware error"),
    ("System", "WHEA-Logger", 18): ("hardware", 9, "Windows recorded a fatal hardware error"),
    ("System", "WHEA-Logger", 19): ("hardware", 5, "Windows recorded a corrected hardware error"),
    ("System", "WHEA-Logger", 47): ("hardware", 5, "Windows recorded a corrected memory error"),
    ("System", "Resource-Exhaustion-Detector", 2004): ("memory", 8, "Windows warned it was low on memory"),
    ("System", "disk", 7): ("storage", 8, "a drive reported a bad block"),
    ("System", "disk", 153): ("storage", 5, "a drive was slow to respond and Windows retried"),
    ("System", "Ntfs", 55): ("storage", 7, "Windows found file system damage"),
    ("System", "Ntfs", 98): ("storage", 3, "a drive needed checking"),
}
CHANGE_CAUSE = {"driver": "gpu_driver", "windows": "windows_update", "game": "game_patch", "mods": "mod",
                "settings": "settings"}
SURE = ((14, "Very likely"), (8, "Likely"), (4, "Possible"))
SETTLED = 8                       # below this, the result says what to test next rather than naming a cause


@dataclass
class Clue:
    source: str                  # where it was seen, in plain words
    text: str                    # what was seen
    cause: str = ""
    weight: int = 0
    when: datetime | None = None


@dataclass
class Cause:
    id: str
    score: int
    clues: list

    @property
    def title(self):
        return CAUSES[self.id][0]

    @property
    def evidence(self):
        """Each different clue once, with how many times it was seen: [(clue, times)]."""
        seen = {}
        for clue in self.clues:
            key = (clue.source, clue.text)
            if key in seen:
                seen[key][1] += 1
            else:
                seen[key] = [clue, 1]
        return [tuple(v) for v in seen.values()]

    @property
    def sure(self):
        return next((words for floor, words in SURE if self.score >= floor), "Possible")


@dataclass
class Investigation:
    game: str
    folder: str
    made: datetime
    crashes: list = field(default_factory=list)          # (when, exe, module, code) of this game's crashes
    clues: list = field(default_factory=list)
    causes: list = field(default_factory=list)
    changes: list = field(default_factory=list)          # (when, kind, words), newest first
    fine: list = field(default_factory=list)             # what was checked and came back fine
    looked: list = field(default_factory=list)           # every place looked at
    tests: list = field(default_factory=list)            # test ids, best first
    settled: bool = False
    app_id: str = ""
    search: dict = field(default_factory=dict)           # name: url for the browser


# ------------------------------------------------------------------ reading Windows
def _run(command, timeout=30):
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=timeout, creationflags=FLAGS,
                              errors="replace")
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout if done.returncode == 0 else ""


def query_log(log, xpath, limit=200):
    return _run(["wevtutil", "qe", log, f"/q:{xpath}", f"/c:{limit}", "/rd:true", "/f:xml"])[:6_000_000]


def parse_log(xml_text):
    """[(provider, event id, when (local, naive), [data...])] from wevtutil XML. Malformed events are skipped."""
    cleaned = re.sub(r'\sxmlns="[^"]+"', "", xml_text or "")
    try:
        root = ET.fromstring("<Events>" + cleaned + "</Events>")
    except ET.ParseError:
        return []
    out = []
    for event in root.findall("Event"):
        provider = event.find("./System/Provider")
        number = event.find("./System/EventID")
        stamp = event.find("./System/TimeCreated")
        if provider is None or number is None or stamp is None:
            continue
        when = bb._parse_loose(stamp.get("SystemTime", ""))
        try:
            ident = int((number.text or "").strip())
        except ValueError:
            continue
        if when is None:
            continue
        data = [(d.text or "").strip() for d in event.findall("./EventData/Data")]
        data += [(d.text or "").strip() for d in event.findall("./UserData//*") if (d.text or "").strip()]
        out.append((provider.get("Name", ""), ident, when.astimezone().replace(tzinfo=None), data))
    return out


def _filetime(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return (datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=number / 10)).astimezone().replace(
        tzinfo=None)


def parse_wer(text):
    """A Windows Error Report (Report.wer) as a dict: EventType, AppPath, EventTime, sigs {name: value}."""
    out, sigs, names = {}, {}, {}
    for line in (text or "").splitlines():
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key, value = key.strip(), value.strip()
        match = re.match(r"Sig\[(\d+)\]\.(Name|Value)$", key)
        if match:
            (names if match.group(2) == "Name" else sigs)[match.group(1)] = value
        else:
            out[key] = value
    out["sigs"] = {names.get(i, i): v for i, v in sigs.items()}
    out["when"] = _filetime(out.get("EventTime"))
    return out


def wer_reports(roots=None, since=None, limit=400):
    """Every Report.wer under Windows' error report folders (newest first), parsed."""
    if roots is None:
        roots = []
        for base in (os.environ.get("ProgramData", r"C:\ProgramData"), os.environ.get("LOCALAPPDATA", "")):
            if base:
                for part in ("ReportArchive", "ReportQueue"):
                    roots.append(Path(base) / "Microsoft" / "Windows" / "WER" / part)
    found = []
    for root in roots:
        try:
            folders = [p for p in Path(root).iterdir() if p.is_dir()]
        except OSError:
            continue
        for folder in folders:
            report = folder / "Report.wer"
            try:
                stamp = datetime.fromtimestamp(report.stat().st_mtime)
            except OSError:
                continue
            if since and stamp < since:
                continue
            found.append((stamp, report))
    found.sort(reverse=True)
    out = []
    for _stamp, report in found[:limit]:
        try:
            raw = report.read_bytes()
        except OSError:
            continue
        text = raw.decode("utf-16", errors="ignore") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else \
            raw.decode("utf-8", errors="ignore")
        data = parse_wer(text)
        data["file"] = str(report)
        out.append(data)
    return out


# ------------------------------------------------------------------ matching
def module_clue(module, source, when=None):
    name = (module or "").strip().casefold()
    name = name.rsplit("\\", 1)[-1]
    for pattern, cause, weight, words in MODULE_RULES:
        if weight and re.match(pattern, name):
            return Clue(source, f"crashed inside {module} ({words})", cause, weight, when)
    return None


def code_clue(code, source, when=None):
    code = (code or "").strip().casefold()
    if code and not code.startswith("0x"):
        code = "0x" + code
    rule = CODE_RULES.get(code)
    if rule and rule[0]:
        return Clue(source, f"error {code}: {rule[2]}", rule[0], rule[1], when)
    return None


def in_folder(path, folder, exes):
    path = (path or "").strip().strip('"')
    if not path:
        return False
    lowered = path.casefold().replace("/", "\\")
    root = str(folder).casefold().replace("/", "\\").rstrip("\\") + "\\"
    return lowered.startswith(root) or lowered.rsplit("\\", 1)[-1] in exes


def game_crashes(app_events, wer, folder, exes, since):
    """This game's crashes and their clues, from event 1000/1002/1026 and Windows Error Reports."""
    crashes, clues = [], []
    for provider, ident, when, data in app_events:
        if when < since:
            continue
        if ident == 1000 and len(data) >= 8 and in_folder(data[10] if len(data) > 10 else data[0], folder, exes):
            crashes.append((when, data[0], data[3], data[6]))
            for clue in (module_clue(data[3], "Windows crash record", when), code_clue(data[6], "Windows crash record", when)):
                if clue:
                    clues.append(clue)
            if data[3] and in_folder(data[3], folder, exes) is False and data[3].casefold().endswith(".dll"):
                pass
        elif ident == 1002 and data and in_folder(data[0], folder, exes):
            crashes.append((when, data[0], "(stopped responding)", ""))
            clues.append(Clue("Windows crash record", f"{data[0]} stopped responding and was closed", "", 0, when))
        elif ident == 1026 and data and any(in_folder(x, folder, exes) or any(e in x.casefold() for e in exes)
                                               for x in data[:1]):
            text = data[0]
            crashes.append((when, next((e for e in exes if e in text.casefold()), "game"), ".NET", ""))
            if re.search(r"OutOfMemoryException", text):
                clues.append(Clue("Windows crash record", "the game ran out of memory (.NET)", "memory", 7, when))
            elif re.search(r"FileNotFoundException|DllNotFoundException|TypeLoadException", text):
                clues.append(Clue("Windows crash record", "a file the game needs wasn't found (.NET)", "game_files", 6,
                                  when))
            else:
                clues.append(Clue("Windows crash record", "an error in the game's own code (.NET)", "dotnet", 4, when))
    seen = {(round(c[0].timestamp() / 60), c[2].casefold()) for c in crashes}
    for report in wer:
        when = report.get("when")
        if not when or when < since:
            continue
        kind = report.get("EventType", "")
        path = report.get("AppPath", "")
        sigs = report.get("sigs", {})
        if kind in ("APPCRASH", "BEX64", "BEX", "AppHangB1", "AppHangXProcB1", "MoAppCrash", "CLR20r3") and \
                in_folder(path or sigs.get("Application Name", ""), folder, exes):
            module = sigs.get("Fault Module Name", "") or sigs.get("Problem Signature 04", "")
            code = sigs.get("Exception Code", "") or sigs.get("Problem Signature 07", "")
            key = (round(when.timestamp() / 60), module.casefold())
            if key not in seen:
                seen.add(key)
                crashes.append((when, Path(path).name or sigs.get("Application Name", ""),
                                module or ("(stopped responding)" if "Hang" in kind else ""), code))
            for clue in (module_clue(module, "Windows error report", when), code_clue(code, "Windows error report", when)):
                if clue:
                    clues.append(clue)
            if "Hang" in kind:
                clues.append(Clue("Windows error report", "the game stopped responding and Windows closed it", "", 0,
                                  when))
    crashes.sort(key=lambda c: c[0], reverse=True)
    return crashes, clues


def system_clues(system_events, wer, crash_times, since):
    """Driver resets, blue screens, power loss, hardware and drive errors near (or, for some, any time around) the
    game's crashes."""
    clues = []
    near = lambda when: any(abs(when - t) <= NEAR for t in crash_times)
    for provider, ident, when, data in system_events:
        if when < since:
            continue
        for (log, match, number), (cause, weight, words) in SYSTEM_EVENTS.items():
            if number == ident and match.casefold() in provider.casefold():
                close = near(when)
                # hardware, drive and memory warnings count over the whole window, at less weight when not close
                if close or cause in ("hardware", "storage", "memory"):
                    detail = (" " + data[0][:80]) if cause == "gpu_unstable" and data else ""
                    clues.append(Clue("Windows system log", words + detail + ("" if close else " (around that time)"),
                                      cause, weight if close else max(1, weight // 2), when))
                break
    for report in wer:
        when = report.get("when")
        if when and when >= since and report.get("EventType", "") == "LiveKernelEvent":
            code = report.get("sigs", {}).get("Parameter 1", "") or report.get("sigs", {}).get("Code", "")
            if code.strip().casefold() in ("141", "117", "1a8", "0x141", "0x117"):
                clues.append(Clue("Windows error report", "the graphics card hung and Windows recovered it "
                                  f"(LiveKernelEvent {code})", "gpu_unstable", 7 if near(when) else 4, when))
    return clues


# ------------------------------------------------------------------ the game's own logs
def _tail(path, size=96_000):
    try:
        with open(path, "rb") as handle:
            handle.seek(0, 2)
            end = handle.tell()
            handle.seek(max(0, end - size))
            return handle.read().decode("utf-8", errors="ignore")
    except OSError:
        return ""


def _squash(text):
    return re.sub(r"[^a-z0-9]+", "", (text or "").casefold())


def log_places(game_name, folder, home=None, local=None, locallow=None, temp=None, documents=None):
    """Where engines and mod crash loggers keep crash logs for this game."""
    home = Path(home or os.environ.get("USERPROFILE") or Path.home())
    local = Path(local or os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local")
    locallow = Path(locallow or home / "AppData" / "LocalLow")
    temp = Path(temp or os.environ.get("TEMP") or local / "Temp")
    try:
        from save_discovery import documents_folders
        docs = documents_folders(home)
    except Exception:
        docs = [home / "Documents"]
    if documents:
        docs = [Path(documents)] + docs
    want = _squash(game_name)
    folder = Path(folder)
    project = {_squash(p.name) for p in _children(folder)} | {_squash(folder.name)}
    places = []

    def matches(name):
        flat = _squash(name)
        return len(flat) >= 4 and (flat in want or want in flat or flat in project)

    for app in _children(local):                                   # Unreal: %LOCALAPPDATA%\<Project>\Saved\...
        if matches(app.name):
            places += [app / "Saved" / "Crashes", app / "Saved" / "Logs"]
    for company in _children(locallow):                            # Unity: LocalLow\<Company>\<Product>\Player.log
        for product in _children(company):
            if matches(product.name):
                places.append(product)
    for company in _children(temp):                                 # Unity crash folders in %TEMP%
        for product in _children(company):
            if matches(product.name):
                places.append(product / "Crashes")
    for doc in docs:
        for mygames in _children(doc / "My Games"):                # Bethesda games and mod crash loggers
            if matches(mygames.name):
                places += [mygames, mygames / "SKSE", mygames / "F4SE", mygames / "SFSE", mygames / "OBSE"]
        for app in _children(doc):
            if matches(app.name):
                places.append(app)
    places += [folder / "logs", folder / "Logs", folder / "crash-reports", folder / "CrashDumps"]
    for child in _children(folder):
        places += [child / "Saved" / "Logs", child / "Saved" / "Crashes"]
    unique = {}
    for place in places:
        unique.setdefault(str(place).casefold(), place)
    return [p for p in unique.values() if p.is_dir()]


def _children(path):
    try:
        return [p for p in Path(path).iterdir() if p.is_dir()]
    except OSError:
        return []


def game_logs(places, since, folder=None, limit=60):
    """Recent log and crash files in those places (two levels deep), newest first."""
    found = []
    for place in places:
        for depth_root in [place] + _children(place)[:200]:
            try:
                entries = list(Path(depth_root).iterdir())
            except OSError:
                continue
            for entry in entries:
                name = entry.name.casefold()
                if not entry.is_file() or not name.endswith((".log", ".txt", ".runtime-xml", ".xml", ".crash", ".rpt")):
                    continue
                if name.endswith(".xml") and "crash" not in name:
                    continue
                try:
                    when = datetime.fromtimestamp(entry.stat().st_mtime)
                except OSError:
                    continue
                if when >= since:
                    found.append((when, entry))
    found.sort(reverse=True)
    unique = []
    seen = set()
    for when, entry in found:
        if str(entry).casefold() not in seen:
            seen.add(str(entry).casefold())
            unique.append((when, entry))
    return unique[:limit]


def log_clues(logs, read=_tail):
    clues = []
    mods = []
    for when, path in logs:
        text = read(path)
        if not text:
            continue
        hits = set()
        for pattern, cause, weight, words in LOG_RULES:
            if cause not in hits and re.search(pattern, text, re.IGNORECASE):
                hits.add(cause)
                clues.append(Clue(f"game log {Path(path).name}", words, cause, weight, when))
        for match in re.finditer(r"([\w .'&()+-]{2,60}\.(?:esp|esm|esl))", text, re.IGNORECASE):
            name = match.group(1).strip()
            if name.casefold() not in {m.casefold() for m in mods} and not re.match(
                    r"(?i)(skyrim|update|dawnguard|hearthfires|dragonborn|fallout4|dlc\w*|starfield|ccbgs\w*|ccq\w*)"
                    r"\.es[mpl]$", name):
                mods.append(name)
        module = re.search(r"(?:Unhandled exception|Exception)[^\n]{0,80}?\bat\b[^\n]{0,20}?([\w.-]+\.(?:dll|exe))\+",
                           text, re.IGNORECASE)
        if module:
            clue = module_clue(module.group(1), f"game log {Path(path).name}", when)
            if clue:
                clues.append(clue)
    if mods:
        clues.append(Clue("mod crash log", "mod files named in the crash log: " + ", ".join(mods[:6]), "mod", 6))
    return clues


# ------------------------------------------------------------------ the PC itself
def disk_free(paths):
    out = {}
    for path in paths:
        anchor = Path(path).anchor or str(path)
        if anchor in out:
            continue
        try:
            usage = shutil.disk_usage(anchor)
        except OSError:
            continue
        out[anchor] = (usage.free, usage.total)
    return out


def memory_status():
    """(total RAM, page file allowed total) in bytes, or None."""
    try:
        import ctypes

        class Status(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        status = Status()
        status.dwLength = ctypes.sizeof(Status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None
        return status.ullTotalPhys, status.ullTotalPageFile
    except (AttributeError, OSError, ImportError):
        return None


def page_file_setting():
    """The PagingFiles registry value: '' means no page file, None means unknown."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management") as key:
            value = winreg.QueryValueEx(key, "PagingFiles")[0]
        return " ".join(value).strip() if isinstance(value, (list, tuple)) else str(value).strip()
    except (OSError, ImportError):
        return None


def ps_json(script, timeout=40):
    raw = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                script + " | ConvertTo-Json -Depth 3 -Compress"], timeout)
    try:
        data = json.loads(raw) if raw.strip() else []
    except ValueError:
        return []
    return data if isinstance(data, list) else [data]


def gpus():
    """[{Name, DriverVersion, DriverDate}] for the graphics cards."""
    rows = ps_json("Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion,"
                   "@{n='DriverDate';e={$_.DriverDate.ToString('yyyy-MM-dd')}}")
    return [r for r in rows if isinstance(r, dict) and r.get("Name")]


def disks():
    """[{FriendlyName, HealthStatus, MediaType}] from Windows' own drive health."""
    rows = ps_json("Get-PhysicalDisk | Select-Object FriendlyName,HealthStatus,MediaType,"
                   "@{n='Op';e={($_.OperationalStatus -join ',')}}")
    return [r for r in rows if isinstance(r, dict)]


def defender_blocks(events, folder, since):
    out = []
    root = str(folder).casefold()
    for provider, ident, when, data in events:
        if when >= since and ident in (1116, 1117, 1118, 1119, 1123, 1124) and any(root in str(d).casefold()
                                                                                for d in data):
            out.append((when, ident))
    return out


def steam_manifest_time(game):
    """When Steam last updated the game (from its appmanifest), or None."""
    app_id = str(getattr(game, "app_id", "") or "")
    install = Path(getattr(game, "install_path", "") or "")
    if not app_id.isdigit() or not install.parts:
        return None
    manifest = install.parent.parent / f"appmanifest_{app_id}.acf"
    try:
        text = manifest.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    match = re.search(r'"LastUpdated"\s+"(\d+)"', text)
    return datetime.fromtimestamp(int(match.group(1))) if match and int(match.group(1)) > 0 else None


def settings_changes(places, since):
    out = []
    for place in places:
        for entry in [place] + _children(place)[:40]:
            try:
                files = [p for p in Path(entry).iterdir() if p.is_file()]
            except OSError:
                continue
            for p in files:
                if p.suffix.casefold() in (".ini", ".cfg", ".json", ".xml", ".sav") and \
                        any(w in p.name.casefold() for w in ("setting", "config", "prefs", "options", "custom", ".ini")):
                    try:
                        when = datetime.fromtimestamp(p.stat().st_mtime)
                    except OSError:
                        continue
                    if when >= since:
                        out.append((when, p.name))
    return out


# ------------------------------------------------------------------ putting it together
@dataclass
class Sources:
    """Everything read from the PC. Tests fill this in directly; `read_sources` reads the real PC."""
    app_events: list = field(default_factory=list)
    system_events: list = field(default_factory=list)
    defender_events: list = field(default_factory=list)
    update_events: list = field(default_factory=list)     # (when, title)
    driver_events: list = field(default_factory=list)     # (when, words)
    wer: list = field(default_factory=list)
    logs: list = field(default_factory=list)               # (when, path)
    log_reader: object = None
    settings: list = field(default_factory=list)           # (when, file name)
    changed_files: list = field(default_factory=list)      # bb.FileFact
    game_updated: datetime | None = None
    free: dict = field(default_factory=dict)               # anchor: (free, total)
    memory: tuple | None = None                            # (RAM, commit limit)
    page_file: str | None = None
    gpus: list = field(default_factory=list)
    disks: list = field(default_factory=list)
    overlays: list = field(default_factory=list)           # friendly names running now
    runtimes: tuple | None = None                          # (vc x64, vc x86, d3dx9)
    exes: set = field(default_factory=set)
    looked: list = field(default_factory=list)


def read_sources(game, now=None, progress=None):
    now = now or datetime.now()
    since = now - timedelta(days=WINDOW_DAYS)
    folder = Path(game.install_path)
    src = Sources(exes=bb.exe_names(folder))
    say = progress or (lambda _t: None)
    say("Reading Windows' crash records…")
    src.app_events = parse_log(query_log("Application", "*[System[(EventID=1000 or EventID=1002 or EventID=1026)]]",
                                         300))
    src.looked.append("Windows Application log (crashes, hangs, .NET errors)")
    say("Reading Windows' error reports…")
    src.wer = wer_reports(since=since)
    src.looked.append("Windows Error Reports")
    say("Reading the system log (driver resets, blue screens, power, hardware, drives)…")
    ids = " or ".join(f"EventID={i}" for i in sorted({k[2] for k in SYSTEM_EVENTS}))
    src.system_events = parse_log(query_log("System", f"*[System[({ids})]]", 400))
    src.looked.append("Windows System log")
    src.update_events = [(when, data[0] if data else "an update") for provider, ident, when, data in
                         parse_log(query_log("System", "*[System[Provider[@Name='Microsoft-Windows-WindowsUpdateClient']"
                                                       " and (EventID=19)]]", 60))]
    src.driver_events = [(when, " ".join(data[:3])) for provider, ident, when, data in
                         parse_log(query_log("System", "*[System[Provider[@Name='Microsoft-Windows-UserPnp'] and "
                                                       "(EventID=20001)]]", 80))
                         if re.search(r"(?i)display|nvidia|amd|radeon|intel.*graphics|geforce", " ".join(data))]
    src.defender_events = parse_log(query_log("Microsoft-Windows-Windows Defender/Operational",
                                              "*[System[(EventID=1116 or EventID=1117 or EventID=1123)]]", 100))
    src.looked.append("Windows Security protection history")
    say("Looking for the game's own crash logs…")
    places = log_places(game.name, folder)
    src.logs = game_logs(places, since, folder)
    src.looked.append(f"the game's own logs ({len(places)} place{'s' if len(places) != 1 else ''})")
    src.settings = settings_changes([p for p in places if "my games" in str(p).casefold()
                                     or "saved" in str(p).casefold()], since)
    _logs, changed, _limited = bb.scan_folder(folder, now, now)
    src.changed_files = changed
    src.game_updated = steam_manifest_time(game)
    say("Checking the PC (space, memory, graphics driver, drives, overlays, runtimes)…")
    src.free = disk_free([folder, os.environ.get("SystemDrive", "C:") + "\\"])
    src.memory = memory_status()
    src.page_file = page_file_setting()
    src.gpus = gpus()
    src.disks = disks()
    try:
        from gg_desktop import fixgame_core, winpc
        src.overlays = fixgame_core.overlay_findings([p.name for p in winpc.list_processes(winpc.Runner())])
    except Exception:
        src.overlays = []
    try:
        from gg_desktop.autopilot_run import _read_runtimes
        src.runtimes = _read_runtimes()
    except Exception:
        src.runtimes = None
    src.looked.append("the PC: free space, memory and page file, graphics driver, drive health, overlays, runtimes")
    return src


def investigate(game, src: Sources, now=None) -> Investigation:
    now = now or datetime.now()
    since = now - timedelta(days=WINDOW_DAYS)
    folder = Path(game.install_path)
    inv = Investigation(game.name, str(folder), now, app_id=str(getattr(game, "app_id", "") or ""))
    inv.looked = list(src.looked)
    crashes, clues = game_crashes(src.app_events, src.wer, folder, src.exes or bb.exe_names(folder), since)
    inv.crashes = crashes
    times = [c[0] for c in crashes]
    clues += system_clues(src.system_events, src.wer, times, since)
    clues += log_clues(src.logs, src.log_reader or _tail)
    first = min(times) if times else None
    newest = max(times) if times else now

    # what changed in the days before the crashes started
    start = (first or now) - timedelta(days=CHANGE_DAYS)
    end = first or now
    changes = []
    for when, words in src.driver_events:
        if start <= when <= end:
            changes.append((when, "driver", f"graphics driver installed: {words[:90]}"))
    for when, title in src.update_events:
        if start <= when <= end:
            changes.append((when, "windows", f"Windows update: {title[:90]}"))
    if src.game_updated and start <= src.game_updated <= end:
        changes.append((src.game_updated, "game", "the game was updated by Steam"))
    mod_files = [f for f in src.changed_files if re.search(r"(?i)(^|[\\/])(mods?|data|plugins|bepinex|skse|"
                                                           r"f4se|r6mods|~mods|paks[\\/]~mods)([\\/]|$)", f.path)
                 or f.path.casefold().endswith((".esp", ".esm", ".esl", ".pak", ".ba2", ".bsa"))]
    if mod_files and start <= mod_files[0].when <= end:
        changes.append((mod_files[0].when, "mods", f"{len(mod_files)} mod file{'s' if len(mod_files) != 1 else ''} "
                                                   f"changed (newest {mod_files[0].path})"))
    for when, name in src.settings:
        if start <= when <= end:
            changes.append((when, "settings", f"settings file changed: {name}"))
            break
    changes.sort(key=lambda c: c[0], reverse=True)
    inv.changes = changes
    if first:
        before = [c for c in changes if c[0] <= first]
        if before:
            when, kind, words = before[0]                       # the nearest change before the crashes began
            clues.append(Clue("timeline", f"the crashes started after this: {words}", CHANGE_CAUSE[kind],
                              6 if (first - when) <= timedelta(days=3) else 3, when))

    # the PC's state
    for anchor, (free, total) in src.free.items():
        if free < 10 * 1024 ** 3 or (total and free / total < 0.05):
            clues.append(Clue("this PC", f"drive {anchor} has only {free / 1024 ** 3:.1f} GB free", "storage", 4))
            if anchor.casefold().startswith(os.environ.get("SystemDrive", "C:").casefold()):
                clues.append(Clue("this PC", "very little space on the Windows drive also shrinks the page file",
                                  "memory", 3))
        else:
            inv.fine.append(f"Drive {anchor} has {free / 1024 ** 3:.0f} GB free")
    if src.page_file == "":
        clues.append(Clue("this PC", "the page file is switched off; many games crash without one", "memory", 6))
    elif src.page_file is not None:
        inv.fine.append("A page file is set up")
    if src.memory:
        ram = src.memory[0] / 1024 ** 3
        if ram < 11:
            clues.append(Clue("this PC", f"only {ram:.0f} GB of memory; many newer games need 16 GB", "memory", 3))
        else:
            inv.fine.append(f"{ram:.0f} GB of memory")
    bad = [d for d in src.disks if str(d.get("HealthStatus", "")).casefold() not in ("healthy", "0", "")]
    if bad:
        for d in bad:
            clues.append(Clue("drive health", f"Windows reports {d.get('FriendlyName', 'a drive')} as "
                              f"{d.get('HealthStatus')}", "storage", 8))
    elif src.disks:
        inv.fine.append("Windows reports every drive as healthy")
    for g in src.gpus:
        try:
            age = (now - datetime.strptime(str(g.get("DriverDate", ""))[:10], "%Y-%m-%d")).days
        except ValueError:
            continue
        if age > 365:
            clues.append(Clue("this PC", f"the {g.get('Name')} driver is over a year old ({g.get('DriverDate')})",
                              "gpu_driver", 3))
        else:
            inv.fine.append(f"The {g.get('Name')} driver is recent ({g.get('DriverDate')})")
    if src.overlays:
        clues.append(Clue("running now", "overlays running: " + ", ".join(src.overlays), "overlay", 2))
    else:
        inv.fine.append("No known overlays running right now")
    if src.runtimes is not None:
        x64, x86, d3dx = src.runtimes
        if not (x64 and x86):
            clues.append(Clue("this PC", "Microsoft's Visual C++ runtime isn't fully installed", "missing_runtime", 5))
        else:
            inv.fine.append("Microsoft's Visual C++ runtimes are installed")
    blocks = defender_blocks(src.defender_events, folder, since)
    if blocks:
        clues.append(Clue("Windows Security", f"Windows Security acted on a file in the game folder "
                          f"{len(blocks)} time{'s' if len(blocks) != 1 else ''}", "antivirus", 9, blocks[0][0]))
    else:
        inv.fine.append("Windows Security didn't block anything in the game folder")
    if not any(c.cause == "hardware" for c in clues):
        inv.fine.append("No hardware errors or blue screens recorded")
    if not any(c.cause == "gpu_unstable" for c in clues):
        inv.fine.append("No graphics driver resets recorded")

    # weigh: the same signal seen many times counts more, but not without limit
    inv.clues = clues
    scores, grouped = {}, {}
    seen = {}
    for clue in clues:
        if not clue.cause or clue.cause not in CAUSES:
            continue
        key = (clue.cause, clue.text.split(" (")[0])
        seen[key] = seen.get(key, 0) + 1
        bonus = clue.weight if seen[key] == 1 else (2 if seen[key] <= 4 else 0)
        scores[clue.cause] = scores.get(clue.cause, 0) + bonus
        grouped.setdefault(clue.cause, []).append(clue)
    inv.causes = sorted((Cause(cid, score, grouped[cid]) for cid, score in scores.items() if score >= 3),
                        key=lambda c: c.score, reverse=True)
    inv.settled = bool(inv.causes) and inv.causes[0].score >= SETTLED and (
        len(inv.causes) == 1 or inv.causes[0].score >= inv.causes[1].score + 3)
    inv.tests = next_tests(inv, game)
    inv.search = search_links(game, crashes)
    return inv


GENERAL_TESTS = ("verify", "overlays_off", "crash_doctor", "driver_back", "runtimes", "temps", "memory_test",
                 "disk_health", "reset_settings", "online")


def next_tests(inv, game):
    tests = []
    for cause in inv.causes[:3]:
        for t in CAUSES[cause.id][3]:
            if t not in tests:
                tests.append(t)
    if not inv.settled:                                  # not settled: the full ladder, cheapest and safest first
        for t in GENERAL_TESTS:
            if t not in tests:
                tests.append(t)
    try:
        from gg_desktop import crashdoctor_core  # noqa: F401
    except Exception:
        pass
    return tests


def search_words(game_name, crashes):
    module = next((c[2] for c in crashes if c[2] and not c[2].startswith("(")), "")
    code = next((c[3] for c in crashes if c[3]), "")
    return " ".join(w for w in (game_name, "crash", module, code) if w)


def search_links(game, crashes):
    words = search_words(game.name, crashes)
    links = {"Search the web": "https://duckduckgo.com/?q=" + quote_plus(words)}
    app_id = str(getattr(game, "app_id", "") or "")
    if app_id.isdigit():
        links["Steam discussions"] = (f"https://steamcommunity.com/app/{app_id}/discussions/search/?q="
                                      + quote_plus("crash " + (crashes[0][2] if crashes and crashes[0][2] and
                                                               not crashes[0][2].startswith("(") else "")).strip("+"))
        links["Steam news"] = f"https://store.steampowered.com/news/app/{app_id}"
    links["PCGamingWiki"] = "https://www.pcgamingwiki.com/w/index.php?search=" + quote_plus(game.name)
    return links


def steam_news(app_id, fetch=None, count=8):
    """The game's recent Steam news (patch notes), [(when, title, url)]. Sends only the Steam ID. Raises OSError."""
    if not str(app_id).isdigit():
        return []
    url = ("https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid=" + str(app_id)
           + f"&count={count}&maxlength=300&format=json")
    if fetch is None:
        from urllib.request import Request, urlopen
        request = Request(url, headers={"User-Agent": "GameGrave"})
        with urlopen(request, timeout=12) as response:
            raw = response.read(400_000).decode("utf-8", errors="replace")
    else:
        raw = fetch(url)
    try:
        items = json.loads(raw).get("appnews", {}).get("newsitems", [])
    except (ValueError, AttributeError):
        return []
    out = []
    for item in items:
        try:
            out.append((datetime.fromtimestamp(int(item.get("date", 0))), str(item.get("title", ""))[:140],
                        str(item.get("url", ""))))
        except (TypeError, ValueError, OSError):
            continue
    return out


def news_clue(news, crashes):
    """A patch shortly before the crashes started is a clue for "A game update"."""
    if not crashes:
        return None
    first = min(c[0] for c in crashes)
    for when, title, _url in news:
        if first - timedelta(days=5) <= when <= first and re.search(r"(?i)patch|update|hotfix|version|v\d|fix", title):
            return Clue("Steam news", f"the game posted \"{title[:80]}\" on {when:%d %b}, just before the crashes began",
                        "game_patch", 5, when)
    return None


def add_clue(inv, clue, game):
    """Fold a late clue (an online one) into a finished investigation and re-rank."""
    if clue is None:
        return inv
    inv.clues.append(clue)
    causes = {c.id: c for c in inv.causes}
    if clue.cause in causes:
        causes[clue.cause].score += clue.weight
        causes[clue.cause].clues.append(clue)
    else:
        causes[clue.cause] = Cause(clue.cause, clue.weight, [clue])
    inv.causes = sorted((c for c in causes.values() if c.score >= 3), key=lambda c: c.score, reverse=True)
    inv.settled = bool(inv.causes) and inv.causes[0].score >= SETTLED and (
        len(inv.causes) == 1 or inv.causes[0].score >= inv.causes[1].score + 3)
    inv.tests = next_tests(inv, game)
    return inv


# ------------------------------------------------------------------ words
def headline(inv):
    if not inv.crashes and not inv.causes:
        return (f"Windows hasn't recorded a crash of {inv.game} in the last {WINDOW_DAYS} days, and nothing on this PC "
                "points to a cause yet. The tests below find it; start with the first one.")
    if inv.settled:
        top = inv.causes[0]
        return f"{top.sure}: {top.title.lower()}. {CAUSES[top.id][1]}"
    if inv.causes:
        names = ", ".join(c.title.lower() for c in inv.causes[:3])
        return (f"Not settled yet. The leads are {names}. The tests below settle it, best lead first; each one asks "
                "before it changes anything and can be undone.")
    return ("The crash records don't name a cause on their own. The tests below find it, safest first; each one asks "
            "before it changes anything and can be undone.")


TEST_WORDS = {
    "verify": ("Game", "Verify the game's files", "The launcher checks every game file and replaces only damaged ones."),
    "crash_doctor": ("Game", "Find the crashing mod", "Crash Doctor turns mods off in halves and names the one."),
    "reset_settings": ("Game", "Reset the game's settings", "Move the game's settings aside so it makes fresh ones; "
                       "put them back any time."),
    "lower_settings": ("Game", "Lower texture quality", "Lower textures and resolution, or turn off ray tracing, "
                       "then play again."),
    "online": ("Game", "Look for a known issue online", "The game's patch notes and other players with this crash."),
    "overlays_off": ("Software", "Turn overlays off", "Close overlays and hooks (Discord, Steam, RivaTuner, Overwolf, "
                     "OBS, audio enhancers) and play again."),
    "driver_back": ("Software", "Try the previous graphics driver", "Exhume puts back the last driver that worked."),
    "driver_new": ("Software", "Install the newest graphics driver", "From NVIDIA, AMD or Intel's own site."),
    "runtimes": ("Software", "Install Microsoft's runtimes", "Visual C++ 2015-2022 (64-bit and 32-bit) from Microsoft."),
    "defender": ("Software", "Check Windows Security", "See whether it blocked or removed a game file."),
    "pagefile": ("Software", "Let Windows manage the page file", "System Properties, Advanced, Performance, "
                 "Virtual memory: 'Automatically manage'."),
    "space": ("Hardware", "Free up space", "Keep at least 15 GB free on drive C and the game's drive."),
    "disk_health": ("Hardware", "Check the drives", "Windows' own health status for each drive."),
    "memory_test": ("Hardware", "Test the memory", "Windows Memory Diagnostic checks your RAM on the next restart."),
    "temps": ("Hardware", "Watch temperatures", "Hardware shows live CPU and graphics temperatures while you play."),
    "no_overclock": ("Hardware", "Remove overclocks for a test", "Reset GPU overclocks in Afterburner and turn off "
                     "XMP/EXPO in the BIOS for one test."),
}


def render(inv):
    stamp = lambda d: d.strftime("%Y-%m-%d %H:%M") if d else ""
    out = [f"Game Grave crash investigation: {inv.game}", f"Made {stamp(inv.made)}.", "", headline(inv), ""]
    out.append(f"Crashes of this game Windows recorded (last {WINDOW_DAYS} days): {len(inv.crashes)}")
    for when, exe, module, code in inv.crashes[:10]:
        out.append(f"  {stamp(when)}  {exe}  in {module or 'unknown'}" + (f"  code {code}" if code else ""))
    out += ["", "Likely causes, with the evidence"]
    if not inv.causes:
        out.append("  None stand out from the records yet.")
    for cause in inv.causes[:6]:
        out.append(f"  {cause.sure}: {cause.title}  (score {cause.score})")
        out.append(f"    Fix: {CAUSES[cause.id][2]}")
        for clue, times in cause.evidence[:6]:
            out.append(f"    - {clue.source}: {clue.text}" + (f" ({times} times, newest {stamp(clue.when)})" if times > 1
                                                                 else (f" ({stamp(clue.when)})" if clue.when else "")))
    out += ["", f"What changed in the {CHANGE_DAYS} days before the crashes started"]
    out += [f"  {stamp(w)}  {words}" for w, _k, words in inv.changes[:10]] or ["  Nothing found."]
    out += ["", "Checked and fine"] + [f"  {line}" for line in inv.fine] or []
    out += ["", "Next tests"] + [f"  {TEST_WORDS[t][0]}: {TEST_WORDS[t][1]}. {TEST_WORDS[t][2]}" for t in inv.tests
                                 if t in TEST_WORDS]
    out += ["", "Looked at: " + "; ".join(inv.looked)]
    return bb.hide_user("\n".join(out)) + "\n"
