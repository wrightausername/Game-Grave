"""Autopsy: compare two frame-time captures taken before and after a change.

Game Grave does not record frames itself. The owner captures with a tool such as PresentMon, CapFrameX or NVIDIA
FrameView (each writes a CSV with a MsBetweenPresents or FrameTime column) and gives Autopsy the two files. Autopsy
only does arithmetic on those numbers. It cannot tell whether both captures covered the same scene and load, and
it says so. Nothing here goes online, runs a game or changes a file.
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

COLUMNS = ("msbetweenpresents", "frametime", "frametimes", "frametime(ms)", "frame time", "ms between presents")
MAX_BYTES = 250 * 1024 * 1024
MAX_FRAMES = 2_000_000
MIN_FRAMES = 600
MIN_SECONDS = 10.0
SAME_FLOOR = 0.02      # changes under 2% are never called a difference
SPIKE_FACTOR = 2.0     # a spike is a frame longer than twice the median
SPIKE_FLOOR = 0.10     # spike counts are small whole numbers, so under 10% is never called a difference


class CaptureError(ValueError):
    pass


@dataclass
class Stats:
    frames: int
    seconds: float
    avg_fps: float
    low1_fps: float          # fps at the 99th percentile frame time
    low01_fps: float         # fps at the 99.9th percentile frame time
    median_ms: float
    p99_ms: float
    longest_ms: float
    spikes: int
    wobble: float            # fractional difference in average fps between the two halves of this capture


def read_capture(path) -> list[float]:
    """Frame times in milliseconds from a capture CSV. Refuses anything that is not clearly one."""
    path = Path(path)
    try:
        size = path.stat().st_size
    except OSError as problem:
        raise CaptureError(f"Could not open that file: {problem}")
    if size > MAX_BYTES:
        raise CaptureError("That file is larger than 250 MB, so Autopsy will not read it.")
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, None)
            if not header:
                raise CaptureError("That file is empty.")
            names = [h.strip().casefold() for h in header]
            column = next((names.index(c) for c in COLUMNS if c in names), None)
            if column is None:
                raise CaptureError("This is not a frame-time capture. Autopsy needs a CSV with a MsBetweenPresents "
                                   "or FrameTime column, such as one saved by PresentMon, CapFrameX or FrameView.")
            frames = []
            for line in reader:
                if column >= len(line):
                    continue
                try:
                    value = float(line[column])
                except ValueError:
                    continue
                if math.isfinite(value) and value > 0:
                    frames.append(value)
                    if len(frames) > MAX_FRAMES:
                        raise CaptureError("That capture has more than 2 million frames, so Autopsy will not read it.")
    except OSError as problem:
        raise CaptureError(f"Could not read that file: {problem}")
    if not frames:
        raise CaptureError("No frame times were found in that file.")
    return frames


def _percentile(sorted_values: list[float], fraction: float) -> float:
    if not sorted_values:
        return 0.0
    at = min(len(sorted_values) - 1, max(0, math.ceil(fraction * len(sorted_values)) - 1))
    return sorted_values[at]


def _avg_fps(frames: list[float]) -> float:
    total = sum(frames)
    return 1000.0 * len(frames) / total if total > 0 else 0.0


def stats_for(frames: list[float]) -> Stats:
    ordered = sorted(frames)
    median = _percentile(ordered, 0.5)
    p99, p999 = _percentile(ordered, 0.99), _percentile(ordered, 0.999)
    half = len(frames) // 2
    first, second = _avg_fps(frames[:half]), _avg_fps(frames[half:])
    wobble = abs(first - second) / max(first, second) if half and max(first, second) > 0 else 0.0
    return Stats(len(frames), sum(frames) / 1000.0, _avg_fps(frames), 1000.0 / p99 if p99 else 0.0,
                 1000.0 / p999 if p999 else 0.0, median, p99, ordered[-1],
                 sum(1 for f in frames if f > SPIKE_FACTOR * median), wobble)


def too_short(stats: Stats) -> bool:
    return stats.frames < MIN_FRAMES or stats.seconds < MIN_SECONDS


def downsample_max(frames: list[float], points: int) -> list[float]:
    """At most `points` values, keeping the longest frame in each bucket so a spike is never smoothed away."""
    if points <= 0 or not frames:
        return []
    if len(frames) <= points:
        return list(frames)
    out = []
    for i in range(points):
        lo, hi = i * len(frames) // points, (i + 1) * len(frames) // points
        out.append(max(frames[lo:max(hi, lo + 1)]))
    return out


# ------------------------------------------------------------------ comparison
@dataclass
class Row:
    metric: str
    before: str
    after: str
    change: str
    verdict: str      # "better", "worse", "within noise" or ""
    tone: str         # green, amber or muted


@dataclass
class Comparison:
    before: Stats
    after: Stats
    rows: list
    summary: str
    comparable: bool


def _verdict(before: float, after: float, higher_is_better: bool, noise: float):
    if before <= 0:
        return "", "muted", ""
    change = (after - before) / before
    shown = f"{change * 100:+.1f}%"
    if abs(change) < max(noise, SAME_FLOOR):
        return shown, "muted", "within noise"
    good = (change > 0) == higher_is_better
    return shown, "green" if good else "amber", "better" if good else "worse"


def compare(before: Stats, after: Stats) -> Comparison:
    if too_short(before) or too_short(after):
        return Comparison(before, after, [], f"A capture needs at least {MIN_FRAMES} frames and {MIN_SECONDS:.0f} seconds "
                          "to compare. One of these is shorter, so Autopsy will not draw a conclusion.", False)
    noise = max(before.wobble, after.wobble)
    spec = (("Average FPS", before.avg_fps, after.avg_fps, True, "{:.1f}"),
            ("1% low FPS", before.low1_fps, after.low1_fps, True, "{:.1f}"),
            ("0.1% low FPS", before.low01_fps, after.low01_fps, True, "{:.1f}"),
            ("Median frame time (ms)", before.median_ms, after.median_ms, False, "{:.2f}"),
            ("Slowest 1% frame time (ms)", before.p99_ms, after.p99_ms, False, "{:.2f}"),
            ("Longest frame (ms)", before.longest_ms, after.longest_ms, False, "{:.1f}"))
    rows = []
    for name, b, a, higher, fmt in spec:
        change, tone, verdict = _verdict(b, a, higher, noise)
        rows.append(Row(name, fmt.format(b), fmt.format(a), change, verdict, tone))
    spike_b = before.spikes / (before.seconds / 60)
    spike_a = after.spikes / (after.seconds / 60)
    change, tone, verdict = _verdict(spike_b, spike_a, False, max(noise, SPIKE_FLOOR))
    rows.append(Row("Spikes per minute", f"{spike_b:.1f}", f"{spike_a:.1f}", change, verdict, tone))
    return Comparison(before, after, rows, _summary(rows, noise), True)


def _summary(rows: list, noise: float) -> str:
    moved = [r for r in rows if r.verdict in ("better", "worse")]
    caveat = ("One capture each. Autopsy cannot tell whether both covered the same scene, settings and background "
              "load, and any difference there can look like a change.")
    if not moved:
        return ("The two captures are within the normal wobble inside each capture "
                f"(about {noise * 100:.1f}%). Autopsy sees no difference it can stand behind. " + caveat)
    parts = [f"{r.metric.split(' (')[0].lower()} {r.verdict} ({r.change})" for r in moved[:4]]
    return ("Beyond the wobble inside each capture (about " + f"{noise * 100:.1f}%): " + ", ".join(parts) + ". " + caveat)


def report_text(note: str, before_name: str, after_name: str, comparison: Comparison) -> str:
    lines = ["Game Grave Autopsy: before and after", f"Change: {note.strip() or 'not described'}",
             f"Before: {before_name}", f"After: {after_name}", ""]
    if comparison.comparable:
        lines.append(f"{'Metric':<28}{'Before':>10}{'After':>10}{'Change':>10}  Verdict")
        for r in comparison.rows:
            lines.append(f"{r.metric:<28}{r.before:>10}{r.after:>10}{r.change:>10}  {r.verdict}")
        lines.append("")
    lines.append(comparison.summary)
    return "\n".join(lines) + "\n"
