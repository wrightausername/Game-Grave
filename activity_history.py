"""Build expandable, local-only history sessions from append-only audit entries.

Old v1/v2 activity.jsonl records remain readable. A cleanup session carries one
session_id across start, every result, and finish, making omissions visible.
"""
from __future__ import annotations

from collections import OrderedDict


def group_activity(events: list[dict]) -> list[dict]:
    """Newest-first sessions; old ungrouped log records remain individual items."""
    grouped: OrderedDict[str, dict] = OrderedDict()
    for index, event in enumerate(events):
        token = event.get("session_id")
        key = f"session:{token}" if isinstance(token, str) and token else f"event:{index}"
        if key not in grouped:
            grouped[key] = {"key": key, "events": [], "session": key.startswith("session:")}
        grouped[key]["events"].append(event)
    return list(grouped.values())


def session_counts(events: list[dict]) -> dict[str, int]:
    result = {"removed": 0, "skipped": 0, "restored": 0, "reviewed": 0}
    for event in events:
        kind = event.get("kind", "")
        if kind in ("Manual recycled", "Auto recycled"):
            result["removed"] += 1
        elif kind == "Cleanup skipped":
            result["skipped"] += 1
        elif kind == "Restored from Recycle Bin":
            result["restored"] += 1
        elif kind == "Cleanup reviewed":
            result["reviewed"] += 1
    return result


def session_caption(group: dict) -> str:
    events = group["events"]
    if not group["session"]:
        return "View full details"
    counts = session_counts(events)
    if any(counts.values()):
        return (f"{counts['removed']} recycled • {counts['skipped']} skipped • "
                f"{counts['restored']} restored • {counts['reviewed']} reviewed")
    return f"{len(events)} recorded steps"
