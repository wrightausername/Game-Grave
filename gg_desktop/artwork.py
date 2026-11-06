"""Local artwork bridge for the restored photo layouts and existing game tools."""
from collections import OrderedDict

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap

from gg_desktop.game_artwork import local_artwork


def game_app_id(game):
    return game.key


class SteamArtwork(QObject):
    changed = Signal(str, str)

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.records = {}
        self.images = OrderedDict()
        self.failed, self.pending, self.queue = set(), set(), []
        self.busy = False
        self.roots = ()
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.flush)

    def set_library(self, games, roots=()):
        self.records = {game.key: game for game in games}
        self.roots = tuple(roots)

    def pixmap(self, ident, kind="cover"):
        cached = self.images.get((ident, "cover"))
        if cached is not None:
            return cached
        if ident in self.records and (ident, "cover") not in self.failed and ident not in self.pending:
            self.pending.add(ident)
            self.queue.append(self.records[ident])
            self.timer.start(0)
        return None

    def flush(self):
        if self.busy or not self.queue:
            return
        self.busy = True
        batch, self.queue = self.queue[:24], self.queue[24:]
        roots = self.roots
        def work(_emit):
            rows = []
            for game in batch:
                try:
                    rows.append((game, local_artwork(game, roots)))
                except (OSError, ValueError, TypeError):
                    rows.append((game, None))
            return rows
        def done(rows):
            self.busy = False
            for game, art in rows:
                self.pending.discard(game.key)
                if art is not None and art.image is not None:
                    self.publish(game, art)
                else:
                    self.failed.add((game.key, "cover"))
            if self.queue:
                self.timer.start(0)
        self.window.job(work, done)

    def publish(self, game, art):
        if art and art.image is not None:
            rgb = art.image.convert("RGB")
            image = QImage(rgb.tobytes(), rgb.width, rgb.height, rgb.width * 3, QImage.Format_RGB888).copy()
            self.images[(game.key, "cover")] = QPixmap.fromImage(image)
            self.images.move_to_end((game.key, "cover"))
            while len(self.images) > 256:
                self.images.popitem(last=False)
            self.changed.emit(game.key, "cover")

    def retry(self):
        self.failed.clear()
        self.images.clear()
        self.changed.emit("", "cover")
