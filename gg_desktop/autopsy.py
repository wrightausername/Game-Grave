"""Autopsy: measure a game before and after a change and say plainly what changed. No Qt in this module.

Frame times come from Intel's free, open-source PresentMon, which the owner downloads from Intel's GitHub page.
Game Grave starts it only when the owner presses Capture, for the seconds shown, on the one game picked.

Honesty rules:
* A verdict compares two captures and nothing else. It is only fair when both were taken in the same place in the
  game, with the same settings apart from the one change, and Autopsy says so.
* Differences under the noise margin are called "no real difference", never a win.
* Captures are small summaries saved on this PC. Nothing is uploaded.
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import datetime
import glob
import io
import json
import os
from pathlib import Path
import statistics

PRESENTMON_PAGE = "https://github.com/GameTechDev/PresentMon/releases"
NOISE_PERCENT = 3.0
FRAME_COLUMNS = ("MsBetweenPresents", "msBetweenPresents", "FrameTime", "MsBetweenDisplayChange")
MIN_FRAMES = 30


@dataclass
class Capture:
    label: str
    game: str
    taken: str
    seconds: float
    frames: int
    avg_fps: float
    low1_fps: float
    median_ms: float
    stutters: int

    def line(self):
        return (f"{self.label}: {self.avg_fps:.0f} FPS average, {self.low1_fps:.0f} FPS 1% low, "
                f"{self.stutters} stutters over {self.seconds:.0f} s ({self.frames:,} frames)")


def find_presentmon(extra_dirs=(), env=None):
    """A PresentMon console exe the owner put next to Game Grave, in Downloads, or in Game Grave's tools folder."""
    env = os.environ if env is None else env
    folders = list(extra_dirs)
    home = env.get("USERPROFILE") or str(Path.home())
    folders.append(os.path.join(home, "Downloads"))
    local = env.get("LOCALAPPDATA")
    if local:
        folders.append(os.path.join(local, "Game Grave", "tools"))
    candidates = []
    for folder in folders:
        for pattern in ("PresentMon*.exe", "presentmon*.exe"):
            candidates += glob.glob(os.path.join(str(folder), pattern))
    candidates = [c for c in candidates if "service" not in os.path.basename(c).casefold()
                  and "setup" not in os.path.basename(c).casefold()]
    candidates.sort(key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0, reverse=True)
    return candidates[0] if candidates else ""


def capture_args(exe, process_name, csv_path, seconds):
    return [exe, "--process_name", process_name, "--output_file", str(csv_path), "--timed", str(int(seconds)),
            "--terminate_after_timed"]


def frame_times(csv_text):
    """Milliseconds per frame from a PresentMon CSV (1.x and 2.x column names)."""
    reader = csv.DictReader(io.StringIO(csv_text or ""))
    column = next((c for c in FRAME_COLUMNS if reader.fieldnames and c in reader.fieldnames), None)
    if column is None:
        raise ValueError("The capture file has no frame time column. Is this a PresentMon CSV?")
    times = []
    for row in reader:
        try:
            value = float(row[column])
        except (TypeError, ValueError):
            continue
        if 0 < value < 5000:
            times.append(value)
    return times


def summarize(times, *, label, game, taken=None):
    if len(times) < MIN_FRAMES:
        raise ValueError(f"Only {len(times)} frames were captured. Keep the game in focus and running, then try again.")
    total_ms = sum(times)
    avg_fps = 1000.0 * len(times) / total_ms
    worst = sorted(times, reverse=True)
    count = max(1, len(times) // 100)
    low1_fps = 1000.0 / (sum(worst[:count]) / count)
    median = statistics.median(times)
    stutters = sum(1 for t in times if t > 2 * median and t > 25)
    return Capture(label, game, taken or datetime.now().strftime("%Y-%m-%d %H:%M"), total_ms / 1000.0, len(times),
                   round(avg_fps, 1), round(low1_fps, 1), round(median, 2), stutters)


def _percent(before, after):
    return 0.0 if before <= 0 else (after - before) * 100.0 / before


def verdict(before, after):
    """Plain words comparing two captures."""
    avg = _percent(before.avg_fps, after.avg_fps)
    low = _percent(before.low1_fps, after.low1_fps)
    lines = []
    if abs(avg) < NOISE_PERCENT and abs(low) < NOISE_PERCENT:
        headline = "Verdict: no real difference. The change did not measurably help or hurt."
    elif avg >= NOISE_PERCENT or low >= NOISE_PERCENT:
        headline = (f"Verdict: better. Average {before.avg_fps:.0f} → {after.avg_fps:.0f} FPS ({avg:+.0f}%), "
                    f"1% low {before.low1_fps:.0f} → {after.low1_fps:.0f} FPS ({low:+.0f}%).")
        if avg <= -NOISE_PERCENT or low <= -NOISE_PERCENT:
            headline = (f"Verdict: mixed. Average {avg:+.0f}%, 1% low {low:+.0f}%. One got better and one got worse.")
    else:
        headline = (f"Verdict: worse. Average {before.avg_fps:.0f} → {after.avg_fps:.0f} FPS ({avg:+.0f}%), "
                    f"1% low {before.low1_fps:.0f} → {after.low1_fps:.0f} FPS ({low:+.0f}%).")
    lines.append(headline)
    if before.stutters != after.stutters:
        lines.append(f"Stutters: {before.stutters} → {after.stutters}.")
    if before.game != after.game:
        lines.append("These captures are from different games, so the comparison means little.")
    lines.append("Fair only if both captures were taken in the same spot with the same settings apart from the change.")
    return lines


def save_capture(folder, capture):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    name = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + "".join(c for c in capture.label if c.isalnum())[:20] + ".json"
    path = folder / name
    path.write_text(json.dumps(asdict(capture), indent=1), encoding="utf-8")
    return path


def load_captures(folder, limit=30):
    captures = []
    for path in sorted(Path(folder).glob("*.json"), reverse=True)[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            captures.append(Capture(**{k: data[k] for k in Capture.__dataclass_fields__}))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return captures


def capture_from_csv(csv_path, *, label, game):
    text = Path(csv_path).read_text(encoding="utf-8", errors="replace")
    return summarize(frame_times(text), label=label, game=game)


def failure_text(result):
    text = (result.output or "").strip()
    if "access" in text.casefold() and "denied" in text.casefold() or "elevat" in text.casefold():
        return ("PresentMon needs permission to read frame timing. Run Game Grave as administrator, or add your "
                "account to the Windows group Performance Log Users, then try again.")
    if result.timed_out:
        return "PresentMon did not finish in time."
    return "PresentMon could not capture: " + (text[:200] or f"code {result.code}")
