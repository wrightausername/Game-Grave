"""Qt-free Undo Center actions: restore planning and running through the protected recovery engine, and hiding rows.

Restoring always goes through recovery.check_restore and recovery.restore, which need exactly one matching item in
the Windows Recycle Bin and a free original path, and never overwrite. This module adds no path of its own and never
moves, copies or deletes a file. "Hide" only records the row key in settings; the recovery records and the activity
log are never edited, so the audit trail stays whole.
"""
from __future__ import annotations

from gg_desktop import undo_data as data

MAX_BATCH = 20
HIDDEN_KEY = "undo_hidden"
RESULT_TEXT = {
    "RESTORED": "Restored to its original location.",
    "AVAILABLE": "Windows reports one matching Recycle Bin item. It can be restored.",
    "NOT_FOUND": "Not found in the Recycle Bin. Windows may have emptied it.",
    "AMBIGUOUS": "More than one matching item. Restore it by hand in Windows so the right one is chosen.",
    "ORIGINAL_EXISTS": "A file already exists at the original path. Nothing was overwritten.",
    "RESTORED_ALREADY": "Already restored.",
}


def plan(entries, limit=MAX_BATCH):
    """(restorable entries, problem sentences). Problems are plain English and never blame the file."""
    problems = []
    if not entries:
        return [], ["Nothing is selected."]
    usable = []
    for e in entries:
        if not e.recovery_id:
            problems.append(f"{e.name}: no recovery record, so Game Grave cannot restore it.")
        elif e.state == "Restored":
            problems.append(f"{e.name}: already restored.")
        else:
            usable.append(e)
    if len(usable) > limit:
        problems.append(f"Choose at most {limit} records at a time.")
        usable = usable[:limit]
    return usable, problems[:12]


def describe(code):
    return RESULT_TEXT.get(code, f"Windows reported {code}. No restore was verified.")


def check(entries, check_restore, canceled=lambda: False):
    """[(entry, result)] with each result a recovery code or an ERROR sentence. Read-only apart from the engine's own record update."""
    output = []
    for e in entries:
        if canceled():
            raise InterruptedError("Check canceled")
        try:
            output.append((e, check_restore(e.recovery_id)))
        except Exception as exc:  # per record; one bad record must not hide the rest
            output.append((e, "ERROR: " + str(exc)[:200]))
    return output


def restore(entries, check_restore, restore_recycled, canceled=lambda: False):
    """Check every record first; restore only those Windows reports as AVAILABLE. Never restores a stale answer."""
    output = []
    for e in entries:
        if canceled():
            raise InterruptedError("Restore canceled")
        try:
            state = check_restore(e.recovery_id)
            output.append((e, restore_recycled(e.recovery_id) if state == "AVAILABLE" else state))
        except Exception as exc:
            output.append((e, "ERROR: " + str(exc)[:200]))
    return output


def summarize(results):
    lines, restored = [], 0
    for e, code in results:
        if code == "RESTORED":
            restored += 1
        lines.append(f"{e.name}: " + (code[7:].strip() if code.startswith("ERROR:") else describe(code)))
    head = f"{restored} of {len(results)} restored." if results else "Nothing to restore."
    return head + "\n\n" + "\n".join(lines[:20])


def hidden_keys(settings):
    values = settings.get(HIDDEN_KEY, [])
    return {v for v in values if isinstance(v, str)} if isinstance(values, list) else set()


def with_hidden(settings, keys):
    merged = sorted(hidden_keys(settings) | set(keys))
    if len(merged) > data.MAX_HIDDEN:
        return None
    return dict(settings, **{HIDDEN_KEY: merged})


def without_hidden(settings, keys):
    return dict(settings, **{HIDDEN_KEY: sorted(hidden_keys(settings) - set(keys))})
