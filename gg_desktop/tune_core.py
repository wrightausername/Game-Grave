"""Qt-free "Make it run better", part of Soulbind: a measured before/after test on your own PC.

1. Play 2 minutes while Game Grave records frame times with Intel's PresentMon (an optional one-time download, MIT
   licence, checked against its published SHA-256).
2. Try changes Game Grave already knows how to make and undo (the Game Optimizer settings, closing big apps).
3. Play 2 minutes again; Autopsy compares the two. Keep the changes only if they measurably helped, else put them back.
Nothing here claims a game will run better before it is measured, and a difference inside the normal wobble is called that.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PRESENTMON_VERSION = "2.4.1"
PRESENTMON_NAME = f"PresentMon-{PRESENTMON_VERSION}-x64.exe"
PRESENTMON_URL = f"https://github.com/GameTechDev/PresentMon/releases/download/v{PRESENTMON_VERSION}/{PRESENTMON_NAME}"
# Published in winget's manifest for Intel.PresentMon.Console 2.4.1.0 (x64 portable).
PRESENTMON_SHA256 = "d74183e7ae630f72cd3690be0373ecbfdc6cbb86578148aab8fa2a7166068f34"
RECORD_SECONDS = 120
TWEAKS = (  # (key, words, technical line); all undone by Game Optimizer's own backup
    ("game_mode", "Turn on Game Mode", r"HKCU\Software\Microsoft\GameBar AutoGameModeEnabled = 1"),
    ("background_recording", "Turn off background recording",
     r"HKCU\System\GameConfigStore GameDVR_Enabled = 0; ...\GameDVR AppCaptureEnabled = 0"),
    ("power_plan", "Switch to High performance power", "powercfg /setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"),
)
STEPS = ("Pick a game", "Play 2 min", "Try changes", "Play 2 min again", "Keep or put back")


def tools_dir(base=None):
    if base is None:
        from core import config_dir
        base = config_dir()
    return Path(base) / "tools"


def presentmon_path(base=None):
    return tools_dir(base) / PRESENTMON_NAME


def captures_dir(base=None):
    if base is None:
        from core import config_dir
        base = config_dir()
    return Path(base) / "tune_captures"


def remote():
    from gg_desktop.local_ai_core import Remote
    return Remote(PRESENTMON_NAME, PRESENTMON_URL, 0, PRESENTMON_SHA256)


def _ps(value):
    return "'" + str(value).replace("'", "''") + "'"


def record_script(presentmon, install_path, output, seconds=RECORD_SECONDS):
    """PowerShell (run with the Windows prompt, since PresentMon needs administrator rights to read frame timing):
    find the game's biggest running program inside its install folder and record it for `seconds`."""
    folder = str(install_path).rstrip("\\/") + "\\"
    return "\n".join([
        "$ErrorActionPreference = 'Stop'",
        f"$folder = {_ps(folder)}; $out = {_ps(output)}; $pm = {_ps(presentmon)}",
        "$p = Get-Process | Where-Object { $_.Path -and $_.Path.StartsWith($folder, [StringComparison]::OrdinalIgnoreCase) } |"
        " Sort-Object WorkingSet64 -Descending | Select-Object -First 1",
        "if (-not $p) { exit 3 }",
        f"$pmArgs = @('--process_id', $p.Id, '--output_file', $out, '--timed', '{int(seconds)}', '--terminate_after_timed',"
        " '--no_console_stats', '--stop_existing_session')",
        "try { $r = Start-Process -FilePath $pm -ArgumentList $pmArgs -Verb RunAs -Wait -PassThru -WindowStyle Hidden }",
        "catch { exit 1223 }",
        "exit $r.ExitCode",
    ])


RECORD_CODES = {3: "The game isn't running. Start it, get into play, then press Record.",
                1223: "Windows' permission prompt was declined, so nothing was recorded."}


@dataclass
class Verdict:
    keep: bool
    title: str
    detail: str
    tone: str       # good, warn, info


def verdict(comparison):
    """Keep only a measured improvement; anything else suggests putting the changes back."""
    if not comparison.comparable:
        return Verdict(False, "Not enough to compare", comparison.summary, "warn")
    rows = {r.metric: r for r in comparison.rows}
    avg, low = rows.get("Average FPS"), rows.get("1% low FPS")
    better = [r for r in (avg, low) if r and r.verdict == "better"]
    worse = [r for r in (avg, low) if r and r.verdict == "worse"]
    if better and not worse:
        moved = ", ".join(f"{r.metric} {r.change}" for r in better)
        return Verdict(True, "It runs better", f"Measured on your PC: {moved}. Keeping the changes is suggested.", "good")
    if worse and not better:
        moved = ", ".join(f"{r.metric} {r.change}" for r in worse)
        return Verdict(False, "It ran worse", f"Measured: {moved}. Putting the changes back is suggested.", "warn")
    if better and worse:
        return Verdict(False, "Mixed result", "Some numbers went up and some went down. Putting the changes back is the "
                       "careful choice; try again on the same scene to be sure.", "info")
    return Verdict(False, "No real difference", "The difference is inside the normal wobble between two runs, so these "
                   "changes don't seem to matter for this game. Putting them back is suggested.", "info")


def capture_name(game_name, label, when):
    import re
    slug = re.sub(r"[^A-Za-z0-9]+", "-", game_name).strip("-")[:40] or "game"
    return f"{slug}-{label}-{when:%Y%m%d-%H%M%S}.csv"
