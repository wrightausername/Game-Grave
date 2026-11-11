"""Soulbind for newly installed games, switched on in Settings (off by default).

Owner's plan: "a Settings switch to Soulbind new games before first launch". What that can honestly mean: after a scan
finds a game that was not there before, Game Grave applies your saved Soulbind profile to that game's settings file
as soon as the file exists. Most games only write that file on their first launch, so a new game waits on a short
list and is tried again on later scans.

Same rules as pressing Apply yourself: only supported games, only values whose exact key is in the real file, a dated
backup first, an entry in the activity log (so it shows in Undo Center), and Undo in the Soulbind panel. It never runs
while a game is running, handles a bounded number of games per scan, and games that were already installed when the
switch was turned on are left alone. No Qt here.
"""
from __future__ import annotations

from gg_desktop import soulbind_core as sb

SWITCH = "soulbind_new_games"
KNOWN = "soulbind_known_games"
WAITING = "soulbind_waiting_games"
MAX_KNOWN = 4000
MAX_WAITING = 100
PER_SCAN = 20


def _keys(value, limit):
    return [k for k in value if isinstance(k, str) and 0 < len(k) <= 400][:limit] if isinstance(value, list) else []


def run(games, profile, settings, *, game_running=False, roots=None, apply=None, config=None):
    """Returns (settings to save or None when nothing changed, [(game title, number of values changed)], [notes])."""
    if settings.get(SWITCH) is not True:
        if KNOWN in settings or WAITING in settings:
            # Switched off: forget the lists, so turning it on again starts from the games installed at that moment.
            cleared = {k: v for k, v in settings.items() if k not in (KNOWN, WAITING)}
            return cleared, [], []
        return None, [], []
    apply = apply or sb.apply_profile
    config = config or sb.config_file
    keys = [str(getattr(g, "key", "")) for g in games if getattr(g, "key", "")]
    first_time = KNOWN not in settings
    known = set(_keys(settings.get(KNOWN), MAX_KNOWN))
    waiting = _keys(settings.get(WAITING), MAX_WAITING)
    updated = dict(settings)
    if first_time:
        # Games already here when the switch was turned on are not "new": remember them and change nothing.
        updated[KNOWN], updated[WAITING] = keys[:MAX_KNOWN], []
        return updated, [], []
    if game_running or not profile:
        return None, [], []          # try again after a later scan; nothing is marked as handled
    present = {str(getattr(g, "key", "")): g for g in games}
    candidates = [g for g in games if getattr(g, "key", "") and g.key not in known]
    candidates += [present[k] for k in waiting if k in present and present[k] not in candidates]
    applied, notes, still_waiting = [], [], [k for k in waiting if k in present]
    for game in candidates[:PER_SCAN]:
        known.add(game.key)
        adapter = sb.adapter_for(game.name)
        if adapter is None:
            if game.key in still_waiting:
                still_waiting.remove(game.key)
            continue                  # not a game Soulbind supports
        path = config(adapter, roots)
        if path is None:
            if game.key not in still_waiting:
                still_waiting.append(game.key)   # no settings file yet (usually: not launched once)
            continue
        if game.key in still_waiting:
            still_waiting.remove(game.key)
        try:
            done = apply(adapter, path, profile)
        except (OSError, ValueError, UnicodeError) as problem:
            notes.append(f"{adapter.title}: Soulbind could not apply ({problem})")
            continue
        if done is not None:
            applied.append((adapter.title, len(done.changes)))
    updated[KNOWN] = sorted(known)[:MAX_KNOWN]
    updated[WAITING] = still_waiting[-MAX_WAITING:]
    changed = updated[KNOWN] != _keys(settings.get(KNOWN), MAX_KNOWN) or updated[WAITING] != waiting
    return (updated if changed else None), applied, notes


def after_scan(window):
    """Called once a scan has finished. Quiet unless something was applied."""
    try:
        settings = window.settings
        if settings.get(SWITCH) is not True and KNOWN not in settings and WAITING not in settings:
            return
        tracker = getattr(window, "_games_tracker", None)
        running = bool(tracker is not None and getattr(getattr(tracker, "ledger", None), "active", None))
        updated, applied, notes = run(list(window.inventory.games), sb.load_profile(), settings, game_running=running)
        if updated is not None:
            from core import save_settings
            save_settings(updated)
            window.settings = updated
        if applied:
            names = ", ".join(title for title, _ in applied[:3]) + ("…" if len(applied) > 3 else "")
            window.status.setText(f"Soulbind applied your preferences to {len(applied)} new game"
                                  f"{'s' if len(applied) != 1 else ''}: {names}. Backups saved; undo in Ready Room, Soulbind.")
        elif notes:
            window.status.setText(notes[0][:200])
    except Exception:
        pass   # an optional convenience must never break a scan
