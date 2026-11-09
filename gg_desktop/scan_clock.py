"""Timing for the scan bar: elapsed time, a smoothed bar position and an honest "about N left" estimate.

The scan reports whole stages (five of them, very uneven in length), so the estimate is the average length of the
stages finished so far (or the previous scan's length when there is nothing finished yet) applied to the stages that
remain. It is always shown as "about", and not at all until there is something to base it on.
"""
from __future__ import annotations


class ScanClock:
    def __init__(self, stages: int = 5, last_total: float | None = None):
        self.stages = max(1, stages)
        self.last_total = last_total if last_total and last_total > 0 else None
        self.start(0.0)

    def start(self, now: float) -> None:
        self.t0 = now
        self.stage_started = now
        self.done = 0
        self.stage_times: list[float] = []

    def advance(self, percent: int, now: float) -> None:
        """The scan says `percent` of its stages are finished; record how long the newly finished ones took."""
        finished = min(self.stages, max(0, int(round(percent * self.stages / 100))))
        if finished > self.done:
            each = max(0.0, now - self.stage_started) / (finished - self.done)
            self.stage_times.extend([each] * (finished - self.done))
            self.done = finished
            self.stage_started = now

    def elapsed(self, now: float) -> float:
        return max(0.0, now - self.t0)

    def average_stage(self) -> float | None:
        if self.stage_times:
            return sum(self.stage_times) / len(self.stage_times)
        if self.last_total:
            return self.last_total / self.stages
        return None

    def remaining(self, now: float) -> float | None:
        if self.done >= self.stages:
            return 0.0
        average = self.average_stage()
        if average is None:
            return None
        in_stage = max(0.0, now - self.stage_started)
        current = max(average - in_stage, average * .2)  # a long stage is never "almost done" by arithmetic alone
        return current + average * (self.stages - self.done - 1)

    def fraction(self, now: float) -> float:
        """Bar position 0..1: finished stages plus a creep through the current one, never into the next."""
        base = self.done / self.stages
        average = self.average_stage()
        if self.done >= self.stages:
            return 1.0
        creep = min(max(0.0, now - self.stage_started) / average, .9) if average else 0.0
        return base + creep / self.stages


def clock_text(seconds: float) -> str:
    seconds = int(max(0, seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def eta_text(seconds: float | None) -> str:
    if seconds is None:
        return "Estimating time left…"
    if seconds < 6:
        return "A few seconds left"
    if seconds < 60:
        return f"About {int(round(seconds / 5.0) * 5)} s left"
    minutes, rest = divmod(int(round(seconds / 5.0) * 5), 60)
    return f"About {minutes} min {rest:02d} s left" if rest else f"About {minutes} min left"
