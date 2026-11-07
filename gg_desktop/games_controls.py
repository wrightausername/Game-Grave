"""Controllers and artwork owned exclusively by a Games page."""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QEvent, Qt, QRect, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QMenu, QWidget
from shiboken6 import isValid

from gg_desktop.artwork import SteamArtwork
from gg_desktop.game_artwork import Artwork, clear_artwork, game_id, local_artwork, official_artwork
from gg_desktop.games import GamesController, artwork_roots
from gg_desktop.games_data import install_directory, launch_uri, steam_install_current
from gg_desktop.games_sources import LAUNCHERS, combine_games, launcher_bucket, launcher_symbol, registered_games
from gg_desktop.reference_widgets import CARD_ROLE, CoverDelegate, icon, pixel_font


def launcher_icon(symbol, size=22):
    if symbol != "rockstar":
        return icon(symbol, size=size)
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(QColor("#f6b628"))
    painter = QPainter(pixmap)
    painter.setPen(QColor("#101010"))
    painter.setFont(pixel_font(size, True))
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "R★")
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


class GamesCoverDelegate(CoverDelegate):
    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        if not self.list_mode:
            data = index.data(CARD_ROLE) or {}
            area = option.rect.adjusted(3, 3, -3, -3)
            painter.save()
            painter.fillRect(QRect(area.left() + 2, area.top() + 2, 28, 24), QColor("#080d13"))
            launcher_icon(launcher_symbol(data.get("source", "")), 17).paint(
                painter, QRect(area.left() + 7, area.top() + 5, 17, 17))
            painter.restore()


class GamesArtwork(SteamArtwork):
    def __init__(self, window, page):
        super().__init__(window)
        self.setParent(page)
        self.closed = threading.Event()
        closed = self.closed
        page.destroyed.connect(lambda: closed.set())

    def flush(self):
        if self.busy or not self.queue or self.closed.is_set():
            return
        self.busy = True
        batch, self.queue = self.queue[:24], self.queue[24:]
        roots, closed = self.roots, self.closed
        def work(_emit):
            rows = []
            for game in batch:
                if closed.is_set():
                    break
                try:
                    art = local_artwork(game, roots)
                except (OSError, ValueError, TypeError):
                    art = Artwork()
                rows.append((game, art))
            return rows
        def done(rows):
            if closed.is_set() or not isValid(self):
                return
            self.busy = False
            for game, art in rows:
                self.pending.discard(game.key)
                if art.image is not None:
                    self.failed.discard((game.key, "cover"))
                    self.publish(game, art)
                else:
                    self.failed.add((game.key, "cover"))
            self.changed.emit("", "cover")
            if self.queue:
                self.timer.start(0)
        self.window.job(work, done)


class MetricFilter(QObject):
    def __init__(self, control, bucket):
        super().__init__(control.page)
        self.control, self.bucket = control, bucket

    def eventFilter(self, target, event):
        if (event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton
                or event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space)):
            self.control.filter_bucket(self.bucket)
            return True
        return False


class GamesActions(GamesController):
    def __init__(self, window, page):
        super().__init__(window, page)
        self.records = list(window.inventory.games)
        self.bucket = None
        self.metric_filters = []
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, target, event):
        if event.type() == QEvent.Close and target is self.window and self._valid():
            self.download_cancel.set()
        if (event.type() in (QEvent.Polish, QEvent.Show) and isinstance(target, QDialog)
                and self._valid() and target.parentWidget() is self.window
                and not target.property("gamesReadable")):
            target.setProperty("gamesReadable", True)
            target.setStyleSheet(target.styleSheet() + " QDialog, QMessageBox { background:#020609; color:#F4F7FC; }")
        return False

    def selected(self):
        return self.window._current_game()

    def current(self, game):
        result = next((row for row in self.records if row.key == game.key), None)
        if not self._valid() or result != game:
            raise ValueError("This game record changed. Run Scan PC again.")
        return result

    def fill(self, *_, **__):
        if self._valid():
            self.window._fill_games()

    def details(self):
        if self._valid():
            self.window._game_details()

    def remember(self, game, art):
        if self._valid():
            self.page.game_artwork.publish(game, art)
            self.details()

    def load_visible_artwork(self):
        if self._valid():
            self.page.game_artwork.retry()
            self.window.game_grid.viewport().update()
            self.details()

    def bind_metrics(self, metrics):
        cells = [item.widget() for index in range(metrics.layout().count())
                 if (item := metrics.layout().itemAt(index)).widget().objectName() == "stripCell"]
        for index, cell in enumerate(cells):
            bucket = None if index == 0 else LAUNCHERS[index - 1][0]
            handler = MetricFilter(self, bucket)
            self.metric_filters.append(handler)
            cell.setFocusPolicy(Qt.StrongFocus)
            cell.setCursor(Qt.PointingHandCursor)
            cell.setAccessibleName("Filter games: " + (bucket or "All launchers"))
            cell.setToolTip("Show " + (bucket or "all") + " games")
            for target in (cell, *cell.findChildren(QWidget)):
                target.installEventFilter(handler)
            if bucket == "Rockstar":
                cell.findChildren(QLabel)[0].setPixmap(launcher_icon("rockstar", 26).pixmap(26, 26))

    def filter_bucket(self, bucket):
        if not self._valid():
            return
        self.window.game_filter.blockSignals(True)
        self.window.game_filter.setCurrentIndex(0)
        self.window.game_filter.blockSignals(False)
        self.bucket = bucket
        self.window.game_search.setPlaceholderText("Search " + (bucket or "your") + " games…")
        self.window.game_filter.show()
        self.window._set_game_tab("Library")
        self.window.game_tabs.select("Library")
        self.window.game_search.clear()
        self.window.status.setText("Showing " + (bucket or "all launcher") + " games.")
        self.fill()

    def launcher_changed(self):
        self.bucket = None
        self.window.game_search.setPlaceholderText("Search your games…")
        self.fill()

    def refresh_sources(self):
        if not self._valid() or not self.window.inventory.scanned_at:
            return
        closed = self.closed
        def finish(extra, error):
            if error:
                self.window.status.setText("Additional launcher records unavailable. Existing library retained.")
                return
            self.records = combine_games(self.records, extra)
            self.page.game_artwork.set_library(self.records, self.page.game_artwork.roots)
            selected = self.window.game_filter.currentText()
            self.window.game_filter.blockSignals(True)
            self.window.game_filter.clear()
            self.window.game_filter.addItems(["All launchers"] + sorted({game.launcher for game in self.records}))
            self.window.game_filter.setCurrentText(selected)
            self.window.game_filter.blockSignals(False)
            metrics = self.window.game_metrics
            metrics.set_value(0, len(self.records))
            for index, (bucket, _, _) in enumerate(LAUNCHERS, 1):
                metrics.set_value(index, sum(launcher_bucket(game.launcher) == bucket for game in self.records))
            for name, button in self.window.game_chips.buttons.items():
                if name.startswith("All Games"):
                    button.setText(f"All Games ({len(self.records)})")
                elif name.startswith("Installed"):
                    button.setText(f"Installed ({sum(game.status.startswith('Installed') for game in self.records)})")
            self.fill()
        self._task(lambda _progress: registered_games(canceled=closed.is_set), finish)

    def context_menu(self, point):
        item = self.window.game_grid.itemAt(point)
        if item is None:
            return
        self.window.game_grid.setCurrentItem(item)
        self.options(self.selected(), self.window.game_grid.viewport().mapToGlobal(point))

    def keyboard_options(self):
        if self.selected():
            self.options(self.selected())

    def launch(self, game):
        try:
            game = self.current(game)
            install_directory(game)
            if not launch_uri(game) and not self.preferences["executables"].get(game_id(game)):
                self.choose_executable(game)
                if not self.preferences["executables"].get(game_id(game)):
                    return
            super().launch(game)
        except (OSError, ValueError) as exc:
            self.window.error("Could not launch game", str(exc))

    def launcher_action(self, game, action):
        try:
            game = self.current(game)
            install_directory(game)
            if game.launcher == "Steam":
                if not steam_install_current(game, self.window.inventory.steam):
                    raise ValueError("Steam's current installation record differs from the scan. Scan PC again.")
                if action == "uninstall":
                    return self.uninstall(game)
                uri = {"validate": "steam://validate/", "details": "steam://nav/games/details/"}.get(action)
                if not uri or not QDesktopServices.openUrl(QUrl(uri + game.app_id)):
                    raise ValueError("Steam could not open this game's controls.")
            else:
                instruction = {"validate": "Find this game in your launcher and choose Verify, Repair or Verify integrity.",
                               "details": "Open this game's page in your launcher to manage add-ons and DLC.",
                               "uninstall": "Find this game in your launcher and choose Uninstall. The launcher will ask you to confirm."}[action]
                self.window.info("Manage " + game.name, game.launcher + "\n\n" + instruction +
                                 "\n\nThis launcher does not expose a verified shortcut for this action.")
        except (OSError, ValueError) as exc:
            self.window.error("Game action unavailable", str(exc))

    def show_dna(self, game):
        self.current(game)
        self.window._pending_dna_game_key = game.key
        self.window.navigate("Game DNA")

    def reset_picture(self, game):
        try:
            clear_artwork(self.current(game))
            self.page.game_artwork.images.pop((game.key, "cover"), None)
            self.page.game_artwork.failed.discard((game.key, "cover"))
            self.page.game_artwork.changed.emit(game.key, "cover")
            self.details()
        except (OSError, ValueError) as exc:
            self.window.error("Artwork not reset", str(exc))

    def options(self, game, position=None):
        if not self._valid() or game is None:
            return
        menu = QMenu(self.page)
        menu.setStyleSheet("QMenu {background:#0b1118;color:#e5e8ee;border:1px solid #49535e;} QMenu::item:selected {background:#7d1529;}")
        menu.addAction("View source evidence", lambda: self.window.info("Game Source Evidence",
            game.install_evidence + "\n\nLauncher: " + game.launcher + "\nSize source: " + game.size_source + "\nLast played source: " + game.last_played_source))
        menu.addAction("Choose artwork…", lambda: self.choose_picture(game))
        menu.addAction("Download official artwork", lambda: self.download_artwork([game]))
        menu.addAction("Use a Steam artwork app ID…", lambda: self.choose_art_id(game))
        menu.addAction("Reset chosen artwork", lambda: self.reset_picture(game))
        menu.addSeparator()
        menu.addAction("Download missing artwork for all games", lambda: self.download_artwork(tuple(self.records), missing_only=True))
        cancel = menu.addAction("Cancel artwork downloads", self.download_cancel.set)
        cancel.setEnabled(self.downloading)
        menu.addSeparator()
        choose = menu.addAction("Choose game launch EXE…", lambda: self.choose_executable(game))
        choose.setEnabled("open_folder" in game.capabilities)
        menu.addAction("Use default launcher", lambda: self.clear_executable(game))
        menu.addAction("Copy installation path", lambda: self.copy_path(game))
        menu.exec(position or self.window.game_grid.mapToGlobal(self.window.game_grid.rect().center()))
        menu.deleteLater()

    def download_artwork(self, games, steam_id=None, missing_only=False):
        if not self._valid():
            return
        if self.downloading:
            self.window.status.setText("Artwork download is already running. Game options can cancel it.")
            return
        games = tuple(games)
        roots = artwork_roots(self.window.inventory, self.window.settings)
        self.downloading = True
        self.download_cancel.clear()
        stop, closed = self.download_cancel, self.closed
        self.window.status.setText("Downloading artwork for all launchers… Only public game IDs/titles are sent.")
        def run(progress):
            found = completed = failures = 0
            for game in games:
                if stop.is_set() or closed.is_set():
                    break
                try:
                    present = local_artwork(game, roots) if missing_only else Artwork()
                    art = Artwork() if present.image is not None else official_artwork(
                        game, canceled=lambda: stop.is_set() or closed.is_set(), steam_id=steam_id)
                    found += int(art.image is not None)
                    failures = 0
                except (OSError, ValueError, TypeError):
                    failures += 1
                completed += 1
                progress(int(completed * 100 / max(1, len(games))), str(completed))
                if failures >= 3:
                    break
            return found, completed
        def progress(percent, message):
            self.window.status.setText(f"Artwork: checked {message} of {len(games)} games ({percent}%).")
        def finish(result, error):
            self.downloading = False
            self.load_visible_artwork()
            if error:
                self.window.error("Artwork download incomplete", error)
                return
            found, completed = result
            outcome = "Canceled" if stop.is_set() else "Incomplete" if completed < len(games) else "Complete"
            self.window.status.setText(f"Artwork {outcome.lower()}: {found} covers downloaded; {completed} of {len(games)} checked. "
                                      "No exact match? Choose artwork in Game options. Cached covers work offline.")
        self._task(run, finish, progress=progress)
