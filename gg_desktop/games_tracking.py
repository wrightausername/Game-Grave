"""A Games-owned process observer. It never starts or stops game processes."""
from PySide6.QtCore import QObject, QEvent, QTimer, Signal
from shiboken6 import isValid

from gg_desktop.games_library_data import PlaytimeLedger, running_games, windows_process_paths


class GameTracker(QObject):
    changed = Signal()

    def __init__(self, window):
        super().__init__(window)
        self.window, self.games = window, ()
        self.ledger = PlaytimeLedger()
        self.busy, self.stopped = False, False
        self.timer = QTimer(self)
        self.timer.setInterval(5000)
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

    def sample(self):
        if self.busy or self.stopped:
            return
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
