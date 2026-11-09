"""Pure helpers for the Mods graphics. No Qt here, so every rule is unit tested.

Nothing in this module invents a fact: each helper only turns numbers the Mods tab already shows
(counts, sizes, positions) into proportions for a picture.
"""
from __future__ import annotations

import hashlib

SEGMENTS = 10


def hue_for(text: str) -> int:
    """A stable colour angle (0-359) for one mod, so its picture never changes between runs."""
    digest = hashlib.sha1(str(text).casefold().encode("utf-8")).hexdigest()
    return int(digest[:6], 16) % 360


def initials(name: str, limit: int = 2) -> str:
    words = [w for w in "".join(c if c.isalnum() else " " for c in str(name)).split() if w]
    if not words:
        return "?"
    return "".join(w[0] for w in words[:limit]).upper()


def lit_segments(part, total, segments: int = SEGMENTS) -> int:
    """How many of `segments` boxes to light for part/total. A non-zero part always lights one."""
    if not total or not part or part < 0:
        return 0
    return max(1, min(segments, round(part / total * segments)))


def size_fraction(size, biggest) -> float | None:
    """Bar length for one mod against the largest shown. Unknown sizes get no bar at all."""
    if size is None or not biggest or size < 0:
        return None
    return max(0.04, min(1.0, size / biggest))


def share_parts(sizes, keep: int = 4):
    """Fractions (summing to 1) for the `keep` largest sizes plus one combined remainder.
    Returns [] when no size is known."""
    known = sorted((s for s in sizes if s and s > 0), reverse=True)
    total = sum(known)
    if not total:
        return []
    parts = [s / total for s in known[:keep]]
    rest = sum(known[keep:]) / total
    if rest > 0:
        parts.append(rest)
    return parts


def order_window(position: int, count: int, span: int = 5):
    """1-based (start, end) of at most `span` positions centred on `position`."""
    if count <= 0:
        return 0, 0
    span = max(1, min(span, count))
    start = max(1, min(position - span // 2, count - span + 1))
    return start, start + span - 1


PILLS = {
    #            text       border     fill       dot
    "On":         ("#7bf0a6", "#1d5a38", "#0b1f14", "#3cda63"),
    "Off":        ("#9aa7b3", "#2a3b4b", "#0c141b", "#8794a1"),
    "On in some": ("#eab464", "#6b5120", "#1a140a", "#eab464"),
}
QUIET = ("#9aa7b3", "#2a3b4b", "#0c141b", "#6f7f8d")


def pill_colors(word: str):
    return PILLS.get(word, QUIET)
