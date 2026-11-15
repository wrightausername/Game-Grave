"""Qt-free "Never run out of space", part of the Graveyard: when a drive that holds games runs low, suggest games you
haven't played in a long time. Putting one to rest = a Resurrection Kit of it on another drive, then the launcher's own
uninstall; bringing it back = Restore a game from that kit. Only games with a real last-played time are suggested.
"""
from __future__ import annotations

import ntpath
import time
from dataclasses import dataclass

LOW_FRACTION = 0.10          # under 10% free ...
LOW_BYTES = 40 * 1024 ** 3   # ... or under 40 GB free
UNPLAYED_DAYS = 90
NOTICE_KEY = "space_notice_day"


@dataclass
class Drive:
    root: str
    free: int
    total: int

    @property
    def low(self):
        return self.total > 0 and (self.free < LOW_BYTES or self.free / self.total < LOW_FRACTION)

    @property
    def target(self):
        """How much to free so the drive is out of the low zone, with some room."""
        want = max(LOW_BYTES, int(self.total * LOW_FRACTION)) + 20 * 1024 ** 3
        return max(0, want - self.free)


@dataclass
class Pick:
    game: object
    size: int
    days: int


def drive_of(path):
    drive = ntpath.splitdrive(str(path))[0]     # Windows rules, whatever runs the check
    return (drive.upper() + "\\") if drive else ""


def game_drives(games, usage=None):
    """Drives that hold at least one installed game, with free and total bytes."""
    import shutil
    usage = usage or (lambda root: shutil.disk_usage(root))
    roots = sorted({drive_of(g.install_path) for g in games if getattr(g, "install_path", "")} - {""})
    out = []
    for root in roots:
        try:
            u = usage(root)
            out.append(Drive(root, int(u.free), int(u.total)))
        except OSError:
            continue
    return out


def suggestions(games, drive, now=None, days=UNPLAYED_DAYS, need=None):
    """Big games on this drive not played for `days`, biggest first, until `need` bytes (or all of them)."""
    now = now or time.time()
    need = drive.target if need is None else need
    found = []
    for g in games:
        if drive_of(getattr(g, "install_path", "")) != drive.root:
            continue
        played, size = getattr(g, "last_played_at", None), getattr(g, "size_bytes", None)
        if not isinstance(played, (int, float)) or played <= 0 or not isinstance(size, int) or size <= 0:
            continue
        idle = int((now - played) // 86400)
        if idle >= days:
            found.append(Pick(g, size, idle))
    found.sort(key=lambda p: (-p.size, -p.days))
    picked, total = [], 0
    for p in found:
        picked.append(p)
        total += p.size
        if need and total >= need:
            break
    return picked


def rest_drive(drives, from_root, need):
    """Another drive with room for the kits (need plus 10%), most free first, or None."""
    room = [d for d in drives if d.root != from_root and d.free > need * 1.1 + 5 * 1024 ** 3]
    return max(room, key=lambda d: d.free) if room else None


def headline(drive, picks):
    from core import human_size
    freed = sum(p.size for p in picks)
    base = f"{drive.root} has {human_size(drive.free)} free of {human_size(drive.total)}."
    if not picks:
        return base + " No installed game there has gone unplayed long enough to suggest."
    names = ", ".join(p.game.name for p in picks[:3]) + (f" and {len(picks) - 3} more" if len(picks) > 3 else "")
    return (base + f" Putting {names} to rest would give back about {human_size(freed)}. Each one is kept as a "
            "Resurrection Kit you can restore in minutes instead of downloading it again.")


def uninstall_link(game):
    if getattr(game, "launcher", "") == "Steam" and str(getattr(game, "app_id", "")).isdigit():
        return "steam://uninstall/" + str(game.app_id)
    return ""


def notice_due(settings, today=None):
    today = today or time.strftime("%Y-%m-%d")
    return settings.get(NOTICE_KEY) != today
