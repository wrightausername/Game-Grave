"""A Games-owned process observer. It never starts or stops game processes."""
from PySide6.QtCore import QObject, QEvent, QTimer, Signal
from shiboken6 import isValid

from gg_desktop.games_library_data import PlaytimeLedger, running_games, windows_process_paths


# How often running games are checked. Playtime is only charged for gaps of 20 seconds or less, so every pace stays
# under that. The check is lighter while a game runs and when no installed game has been seen for a while.
FAST, PLAYING, QUIET = 5000, 10000, 15000
QUIET_AFTER = 12          # idle checks in a row before slowing down


def next_interval(active, idle_checks):
    if active:
        return PLAYING
    return QUIET if idle_checks >= QUIET_AFTER else FAST


class GameTracker(QObject):
    changed = Signal()

    def __init__(self, window):
        super().__init__(window)
        self.window, self.games = window, ()
        self.ledger = PlaytimeLedger()
        self.busy, self.stopped = False, False
        self.idle_checks = 0
        self.timer = QTimer(self)
        self.timer.setInterval(FAST)
        self.timer.timeout.connect(self.sample)
        self.timer.start()
        window.installEventFilter(self)

    def eventFilter(self, target, event):
        if target is self.window and event.type() == QEvent.Close and not self.window.scanning and not self.window.cleaning:
            self.stopped = True
            self.timer.stop()
        return False

    def register(self, games):
        self.games = tuple(game for game in games if game.install_path and "open_folder" in game.capabilities)
        self.idle_checks = 0
        self.timer.setInterval(FAST)

    def sample(self):
        if self.busy or self.stopped:
            return
        if not self.games:
            return          # nothing to look for until a scan has found installed games
        self.busy = True
        games = self.games
        def work(_progress):
            try:
                return running_games(games, windows_process_paths())
            except (OSError, ValueError, RuntimeError):
                return set()
        def finish(active):
            if not isValid(self) or self.stopped:
                return
            self.busy = False
            self.idle_checks = 0 if active else self.idle_checks + 1
            wanted = next_interval(active, self.idle_checks)
            if self.timer.interval() != wanted:
                self.timer.setInterval(wanted)
            try:
                if self.ledger.sample(active):
                    self.changed.emit()
            except (OSError, ValueError):
                # Preserve the previous counter on storage failure. Tracking
                # must never interrupt another tab or a running game.
                pass
        self.window.job(work, finish)


def tracker_for(window):
    tracker = getattr(window, "_games_tracker", None)
    if tracker is None or not isValid(tracker):
        tracker = window._games_tracker = GameTracker(window)
    return tracker
