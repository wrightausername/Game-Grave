"""Manual, local-only game performance comparison with ZERO game hooks.

The user enters results from their own reproducible benchmark. Game Grave
never injects frame probes, scans GPU state, or polls FPS in the background.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path

from core import config_dir
from gg_desktop.ready_room_health import _identity

MAX_RECORDS = 60
MAX_BYTES = 60_000


def _history_path(game) -> Path:
    return config_dir() / "performance_watch" / (_identity(game) + ".json")


def read_benchmarks(game) -> list[dict]:
    target = _history_path(game)
    try:
        if not target.is_file() or target.is_symlink() or target.stat().st_size > MAX_BYTES:
            return []
        data = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return []
        return [x for x in data[:MAX_RECORDS] if
                isinstance(x, dict) and type(x.get("average_fps")) in (int, float) and
                type(x.get("one_percent_low")) in (int, float)]
    except (OSError, UnicodeError, ValueError, TypeError):
        return []


def add_benchmark(game, average_fps: float, one_percent_low: float,
                  notes: str = "") -> list[dict]:
    if any(type(x) not in (int, float) or not math.isfinite(x)
           for x in (average_fps, one_percent_low)):
        raise ValueError("FPS values must be finite numbers.")
    if not (1 <= one_percent_low <= average_fps <= 2000):
        raise ValueError("1% low must be positive and at most the average FPS.")
    row = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "average_fps": round(float(average_fps), 1),
        "one_percent_low": round(float(one_percent_low), 1),
        "note": str(notes).strip()[:180],
        "method": "manually entered by user, not automatically measured",
    }
    records = [row, *read_benchmarks(game)][:MAX_RECORDS]
    target = _history_path(game)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".new")
    try:
        tmp.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
    return records


def benchmark_summary(records: list[dict]) -> str:
    if not records:
        return "No benchmarks recorded. This feature uses manually entered results."
    latest = records[0]
    message = (f"Latest: {latest['average_fps']:.1f} average FPS / "
               f"{latest['one_percent_low']:.1f} 1% low. "
               f"{latest.get('at', '')[:10]}.")
    if len(records) > 1:
        previous = records[1]
        change = latest["average_fps"] - previous["average_fps"]
        change_low = latest["one_percent_low"] - previous["one_percent_low"]
        message += (f" Versus previous entry: {change:+.1f} average FPS, "
                    f"{change_low:+.1f} 1% low.")
    return message + " Only comparable when hardware, settings and benchmark scene match."
