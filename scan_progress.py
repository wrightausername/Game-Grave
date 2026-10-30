"""Honest scan-stage progress and deliberately approximate ETA estimates."""
from __future__ import annotations

from dataclasses import dataclass

STAGES = (
    ('Steam games', 0.16),
    ('Other launchers', 0.25),
    ('Mods and addons', 0.37),
    ('Old downloads', 0.16),
    ('Saved games', 0.06),
)


@dataclass(frozen=True)
class ScanProgress:
    label: str
    completed: int
    total: int = len(STAGES)

    @property
    def percent(self) -> int:
        return round(100 * sum(weight for _, weight in STAGES[:self.completed]))


def eta_seconds(elapsed: float, completed: int) -> int | None:
    """Only estimate once a significant portion of observed work is complete.

    This is a stage-weighted extrapolation, not a deadline or guaranteed ETA.
    """
    elapsed = max(0, elapsed)
    progress = sum(weight for _, weight in STAGES[:completed])
    if progress < 0.35 or elapsed < 2:
        return None
    return max(0, round(elapsed * (1 - progress) / progress))


def format_eta(seconds: int | None) -> str:
    if seconds is None:
        return 'Calculating ETA…'
    if seconds < 60:
        return f'Rough ETA: ~{max(1, seconds)} sec'
    return f'Rough ETA: ~{max(1, round(seconds/60))} min'
