"""Qt-free "Fix my game": the usual reasons a game won't start or keeps crashing that are not mods, checked in order.
Everything here reads; the fixes it offers are steps in an AI Assistant plan that run only after Run all and one OK.
It never says a cause is certain: each finding says what was seen and what the fix would do.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Overlays and hooks that commonly stop games starting or make them crash. Reported, never closed without a tick.
OVERLAYS = {
    "overwolf.exe": "Overwolf", "rtss.exe": "RivaTuner Statistics Server", "msiafterburner.exe": "MSI Afterburner",
    "discord.exe": "Discord (its in-game overlay)", "medal.exe": "Medal", "nvidia overlay.exe": "NVIDIA overlay",
    "obs64.exe": "OBS Studio (game capture)", "wallpaper64.exe": "Wallpaper Engine", "fpsmonitor.exe": "FPS Monitor",
    "xsplit.core.exe": "XSplit", "playclaw.exe": "PlayClaw", "evga precision x1.exe": "EVGA Precision X1",
}
VC_DOWNLOAD = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
VC_HOSTS = ("aka.ms", "download.visualstudio.microsoft.com", "download.microsoft.com")
DIRECTX_PAGE = "https://www.microsoft.com/en-us/download/details.aspx?id=35"

_FIX = re.compile(r"won'?t (start|launch|open|load|run|boot)|will not (start|launch|open|load|run)|doesn'?t (start|launch|open|"
                  r"load|run)|does not (start|launch|open|load|run)|not (starting|launching|opening|loading)|"
                  r"keeps? crash|crash(es|ing|ed)?\b|black screen|freez(es|ing)|stopped working|fix (my |the )?game|"
                  r"\bfix\b.*\b(game|crash)|closes (itself|on its own|by itself)|instantly closes|ctd\b")


def wants_fix(text):
    t = " ".join((text or "").casefold().replace("’", "'").split())
    switching_mods = bool(re.search(r"\bmods?\b", t) and re.search(r"\b(turn|switch|toggle|disable|enable)\b", t))
    return bool(_FIX.search(t)) and not switching_mods


def game_named(games, text):
    """The game the request names (longest title wins), or None. Never guesses a similar title."""
    t = (text or "").casefold()
    squash = lambda s: re.sub(r"[^a-z0-9]+", "", s.casefold())
    flat = squash(t)
    named = [g for g in games if len(g.name) >= 3 and (g.name.casefold() in t or (len(squash(g.name)) >= 5 and
                                                                                   squash(g.name) in flat))]
    return max(named, key=lambda g: len(g.name)) if named else None


@dataclass
class Finding:
    title: str
    detail: str
    tone: str = "info"     # good, warn, info


def overlay_findings(process_names):
    seen = []
    for name in process_names:
        label = OVERLAYS.get(str(name).casefold())
        if label and label not in seen:
            seen.append(label)
    return seen


def runtime_findings(vc_x64, vc_x86, d3dx9_present):
    out = []
    if not vc_x64 or not vc_x86:
        missing = " and ".join(n for n, ok in (("64-bit", vc_x64), ("32-bit", vc_x86)) if not ok)
        out.append(Finding("Visual C++ runtime missing", f"Microsoft's Visual C++ 2015-2022 runtime ({missing}) is not "
                           "installed. Many games need it to start.", "warn"))
    if not d3dx9_present:
        out.append(Finding("Older DirectX files not found", "Some older games need Microsoft's DirectX End-User Runtime "
                           "(d3dx9_43.dll was not found). Newer games don't need it.", "info"))
    return out


def crash_summary(crashes):
    """One sentence from Black Box's crash records for this game."""
    if not crashes:
        return "Windows recorded no crash of this game recently."
    newest = max(crashes, key=lambda c: c.when)
    modules = {}
    for c in crashes:
        modules[c.module] = modules.get(c.module, 0) + 1
    module, times = max(modules.items(), key=lambda kv: kv[1])
    hint = KNOWN_MODULES.get(module.casefold(), "")
    return (f"Windows recorded {len(crashes)} crash{'es' if len(crashes) != 1 else ''}, the newest "
            f"{newest.when:%d %b %H:%M}. Most were in {module}" + (f" ({hint})" if hint else "") + ".")


KNOWN_MODULES = {
    "nvwgf2umx.dll": "the NVIDIA graphics driver", "nvoglv64.dll": "the NVIDIA graphics driver",
    "amdxx64.dll": "the AMD graphics driver", "atidxx64.dll": "the AMD graphics driver",
    "igd10iumd64.dll": "the Intel graphics driver", "d3d11.dll": "DirectX 11", "d3d12.dll": "DirectX 12",
    "dxgi.dll": "DirectX graphics", "vcruntime140.dll": "the Visual C++ runtime", "msvcp140.dll": "the Visual C++ runtime",
    "ucrtbase.dll": "Windows' C runtime", "ntdll.dll": "Windows itself; often a symptom, not the cause",
    "kernelbase.dll": "Windows itself; often a symptom, not the cause", "rtsshooks64.dll": "RivaTuner's overlay",
    "owclient.dll": "Overwolf's overlay", "discordhook64.dll": "Discord's overlay", "gameoverlayrenderer64.dll": "Steam's overlay",
}


def verify_link(game):
    """The launcher's own verify for this game, when the launcher has one Game Grave can open."""
    if getattr(game, "launcher", "") == "Steam" and str(getattr(game, "app_id", "")).isdigit():
        return "steam://validate/" + str(game.app_id)
    return ""


def verify_words(game):
    launcher = getattr(game, "launcher", "") or "its launcher"
    if verify_link(game):
        return ""
    return {"Epic": "In the Epic Games Launcher: Library, the game's three dots, Manage, Verify.",
            "GOG": "In GOG Galaxy: the game, the settings button, Manage installation, Verify / Repair.",
            "EA": "In the EA app: the game, the three dots, Repair.",
            "Ubisoft": "In Ubisoft Connect: the game, Properties, Verify files.",
            "Battle.net": "In Battle.net: the game, the gear next to Play, Scan and Repair."}.get(
        launcher, f"Use {launcher}'s own Verify or Repair for this game.")


def safe_download(url):
    """Only Microsoft's own hosts, over https."""
    from urllib.parse import urlparse
    parts = urlparse(url)
    return parts.scheme == "https" and (parts.hostname or "").casefold() in VC_HOSTS
