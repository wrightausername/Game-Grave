"""Controllers and artwork owned exclusively by a Games page."""
from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QObject, QEvent, QPointF, QRectF, Qt, QRect, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QMenu, QWidget
from shiboken6 import isValid

from gg_desktop.artwork import SteamArtwork
from gg_desktop.game_artwork import Artwork, clear_artwork, game_id, local_artwork, official_artwork
from gg_desktop.games_account_store import read_document
from gg_desktop.games_catalogue_artwork import cached_artwork, reference_available, remote_artwork
from gg_desktop.games_live import LiveGames
from gg_desktop.games_native import native_action, registered_uninstaller, execute as execute_native
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
            badge = data.get("soulbind")
            if badge:
                self._soulbind_badge(painter, area, *badge)
            painter.restore()

    @staticmethod
    def _soulbind_badge(painter, area, text, tone):
        """A small pill saying whether this game already follows the owner's Soulbind preferences."""
        color = QColor({"green": "#35dc7c", "amber": "#dfac46"}.get(tone, "#9aa4ac"))
        font = painter.font()
        font.setPixelSize(10)
        font.setBold(True)
        painter.setFont(font)
        width = painter.fontMetrics().horizontalAdvance(text) + 18
        left, right = area.left() + 34, area.right() - 28
        if left + width > right:
            return
        pill = QRectF(left, area.top() + 6, width, 16)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(color)
        fill = QColor("#050a0e")
        fill.setAlpha(225)
        painter.setBrush(fill)
        painter.drawRoundedRect(pill, 8, 8)
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(pill.left() + 8, pill.center().y()), 2.6, 2.6)
        painter.setPen(color)
        painter.drawText(QRectF(pill.left() + 14, pill.top(), pill.width() - 16, pill.height()),
                         Qt.AlignVCenter | Qt.AlignLeft, text)


class GamesArtwork(SteamArtwork):
    def __init__(self, window, page):
        super().__init__(window)
        self.setParent(page)
        self.closed = threading.Event()
        closed = self.closed
        page.destroyed.connect(lambda: closed.set())
        self.page = page
        self.sources, self.fallbacks = {}, {}
        self.abort = threading.Event()
        self.generation = 0
        self.automatic_paused = False

    def invalidate(self, *, clear_images=False):
        self.abort.set()
        self.abort = threading.Event()
        self.generation += 1
        self.queue.clear()
        self.pending.clear()
        self.failed.clear()
        if clear_images:
            self.images.clear()

    def set_library(self, games, roots=()):
        games = tuple(games)
        if self.records and set(self.records) != {game.key for game in games}:
            self.invalidate()
        super().set_library(games, roots)

    def retry(self):
        self.invalidate(clear_images=True)
        self.changed.emit("", "cover")

    def cancel_automatic(self):
        self.invalidate()
        self.automatic_paused = True

    def pixmap(self, ident, kind="cover"):
        picture = super().pixmap(ident, kind)
        game = self.records.get(ident)
        if picture is not None or game is None or reference_available(game.name):
            return picture
        if ident not in self.fallbacks:
            from gg_desktop.games import fallback_artwork
            from PySide6.QtCore import QFileInfo
            from PySide6.QtWidgets import QFileIconProvider
            fallback = fallback_artwork(game)
            try:
                from core import _has_reparse_component
                candidates = [path for path in Path(game.install_path).glob("*.exe")
                    if not any(word in path.name.casefold() for word in ("unins", "setup", "crash", "launcher"))][:40] if game.install_path else []
                source = next((path for path in candidates if not _has_reparse_component(path)), None)
                if source:
                    image = QFileIconProvider().icon(QFileInfo(str(source))).pixmap(128, 128)
                    if not image.isNull():
                        painter = QPainter(fallback)
                        painter.drawPixmap(56, 75, image)
                        painter.end()
            except (OSError, ValueError):
                pass
            if len(self.fallbacks) >= 128:
                self.fallbacks.pop(next(iter(self.fallbacks)))
            self.fallbacks[ident] = fallback
        return self.fallbacks[ident]

    def publish(self, game, art):
        if art.image is not None:
            self.sources[game.key] = art.source
            thumbnail = art.image.copy()
            thumbnail.thumbnail((320, 480))
            super().publish(game, Artwork(thumbnail, art.source))

    def flush(self):
        if self.busy or not self.queue or self.closed.is_set():
            return
        self.busy = True
        batch, self.queue = self.queue[:8], self.queue[8:]
        roots, closed = self.roots, self.closed
        generation, abort = self.generation, self.abort
        facts = {game.key: dict(self.page.games.fact(game)) for game in batch}
        automatic = read_document("options.json", {}).get("automatic_artwork", True) and not self.automatic_paused
        from queue import SimpleQueue
        ready = SimpleQueue()
        def work(_emit):
            rows = []
            for game in batch:
                if closed.is_set() or abort.is_set():
                    break
                try:
                    art = cached_artwork(game, roots)
                    if art.image is None and automatic and not reference_available(game.name):
                        art = remote_artwork(game, facts[game.key], canceled=lambda: closed.is_set() or abort.is_set())
                except (OSError, ValueError, TypeError):
                    art = Artwork()
                rows.append((game, art))
                ready.put((game, art))
                _emit(0, "cover")
            return rows
        def progress(_amount, _message):
            if closed.is_set() or not isValid(self) or generation != self.generation:
                return
            while not ready.empty():
                game, art = ready.get()
                if art.image is not None:
                    self.publish(game, art)
        def done(rows):
            if closed.is_set() or not isValid(self):
                return
            self.busy = False
            if generation != self.generation:
                if self.queue:
                    self.timer.start(0)
                return
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
        self.window.job(work, done, progress=progress)


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


class GamesActions(LiveGames, GamesController):
    def __init__(self, window, page):
        super().__init__(window, page)
        self.records = list(window.inventory.games)
        self.bucket = None
        self.metric_filters = []
        self.initialize_live()
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, target, event):
        if event.type() == QEvent.Close and target is self.window and self._valid():
            self.download_cancel.set()
            self.sync_cancel.set()
            self.page.game_artwork.cancel_automatic()
            if not self.window.scanning and not self.window.cleaning:
                self.closed.set()
                self.live_timer.stop()
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
        index = self.window.game_filter.findData(bucket) if bucket else 0
        if index < 0:
            self.window.game_filter.addItem(bucket + " games", bucket)
            index = self.window.game_filter.count() - 1
        self.window.game_filter.setCurrentIndex(index)
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
        self.bucket = self.window.game_filter.currentData()
        self.window.game_search.setPlaceholderText("Search " + (self.bucket or "your") + " games…")
        self.fill()

    def refresh_sources(self):
        LiveGames.refresh_sources(self)

    def context_menu(self, point):
        item = self.window.game_grid.itemAt(point)
        if item is None:
            self.library_options(self.window.game_grid.viewport().mapToGlobal(point))
            return
        self.window.game_grid.setCurrentItem(item)
        self.options(self.selected(), self.window.game_grid.viewport().mapToGlobal(point))

    def keyboard_options(self):
        if self.selected():
            self.options(self.selected())

    def launch(self, game):
        try:
            game = self.current(game)
            if not self.is_installed(game) and self.fact(game).get("owned"):
                plan = native_action(game, self.fact(game), "install")
                execute_native(plan, lambda uri: QDesktopServices.openUrl(QUrl(uri)))
                self.window.status.setText("Installation requested for " + game.name + ". Finish in " + game.launcher + ".")
                return
            install_directory(game)
            if game.launcher == "Steam" or self.preferences["executables"].get(game_id(game)):
                return super().launch(game)
            try:
                plan = native_action(game, self.fact(game), "launch")
            except ValueError:
                self.choose_executable(game)
                if self.preferences["executables"].get(game_id(game)):
                    super().launch(game)
                return
            execute_native(plan, lambda uri: QDesktopServices.openUrl(QUrl(uri)))
            self.window.status.setText("Launch requested for " + game.name + ". The launcher controls startup.")
            self.tracker.sample()
        except (OSError, ValueError) as exc:
            self.window.error("Could not launch game", str(exc))

    def launcher_action(self, game, action):
        try:
            game = self.current(game)
            if game.launcher == "Steam":
                if not self.is_installed(game) and self.fact(game).get("owned") and action == "details":
                    plan = native_action(game, self.fact(game), action)
                    execute_native(plan, lambda uri: QDesktopServices.openUrl(QUrl(uri)))
                    return
                install_directory(game)
                if not steam_install_current(game, self.window.inventory.steam):
                    raise ValueError("Steam's current installation record differs from the scan. Scan PC again.")
                if action == "uninstall":
                    return self.uninstall(game)
            registered = registered_uninstaller(game) if action == "uninstall" else None
            plan = native_action(game, self.fact(game), action, uninstaller=registered)
            if plan.confirmation:
                root = install_directory(game)
                signature = root.stat()
                if not self.window.confirm("Uninstall " + game.name + "?",
                    "Open the native uninstaller for this game?\n\n" + game.name + "\n" + game.install_path +
                    "\n\nThe game's client or registered uninstaller controls file removal.", destructive=True):
                    return
                current = install_directory(self.current(game)).stat()
                if (signature.st_dev, signature.st_ino) != (current.st_dev, current.st_ino):
                    raise ValueError("The installation changed during confirmation. Scan again.")
                if registered and registered_uninstaller(game) != registered:
                    raise ValueError("The registered uninstaller changed. Scan again.")
            execute_native(plan, lambda uri: QDesktopServices.openUrl(QUrl(uri)))
            if plan.handoff:
                self.window.status.setText("Opened " + game.launcher + " controls for " + game.name + ". Finish the action in the launcher.")
            else:
                self.window.status.setText(plan.label + " requested for " + game.name + ". Completion is controlled by the launcher.")
        except (OSError, ValueError) as exc:
            self.window.error("Game action unavailable", str(exc))

    def show_dna(self, game):
        game = self.current(game)
        if not game.install_path:
            values = self.values(game)
            self.window.info("Game DNA · " + game.name,
                game.launcher + " connected library\n\nThis game is not installed.\nPlaytime: " + values["playtime"] +
                "\nLast played: " + values["last_played"] + "\n\n" + self.source_text(game, "status"))
            return
        if not any(row.key == game.key for row in self.window.inventory.games):
            # Additional Games-only installs must never fall through to an
            # unrelated default selection in the unchanged Game DNA tab.
            from game_intelligence import build_game_dna
            profile = build_game_dna(other_games=(game,), mods=self.window.inventory.mods,
                                     saves=self.window.inventory.saves)["games"][0]
            locations = [asset["path"] for asset in profile["assets"]]
            details = "\n".join(locations[:20]) if locations else "No associated mod locations verified in the current scan."
            self.window.info("Game DNA · " + game.name,
                game.launcher + "\n\nInstallation: " + game.install_path + "\n\n" +
                game.install_evidence + "\n\nAssociated locations:\n" + details +
                "\n\nProfile generated from this game's detected installation and the current local scan."
                "\nRelationships do not authorize file removal. Save ownership remains unverified.")
            return
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
            game.install_evidence + "\n\nLauncher: " + game.launcher + "\nSize source: " + game.size_source + "\n" + self.source_text(game, "status") + "\nPlaytime: " + self.source_text(game, "playtime")))
        menu.addAction("Connect game libraries…", self.connections)
        menu.addAction("Refresh library data", lambda: self.sync_libraries())
        link = menu.addAction("Link to an owned game…", lambda: self.link_owned(game))
        link.setEnabled(bool(game.install_path))
        menu.addAction("Choose artwork…", lambda: self.choose_picture(game))
        menu.addAction("Download official artwork", lambda: self.download_artwork([game]))
        menu.addAction("Use a Steam artwork app ID…", lambda: self.choose_art_id(game))
        menu.addAction("Reset chosen artwork", lambda: self.reset_picture(game))
        menu.addSeparator()
        menu.addAction("Download missing artwork for all games", lambda: self.download_artwork(tuple(self.records), missing_only=True))
        cancel = menu.addAction("Cancel artwork downloads", self.cancel_artwork)
        cancel.setEnabled(self.downloading or self.page.game_artwork.busy)
        menu.addSeparator()
        choose = menu.addAction("Choose game launch EXE…", lambda: self.choose_executable(game))
        choose.setEnabled("open_folder" in game.capabilities)
        menu.addAction("Use default launcher", lambda: self.clear_executable(game))
        copy = menu.addAction("Copy installation path", lambda: self.copy_path(game))
        copy.setEnabled(bool(game.install_path))
        menu.exec(position or self.window.game_grid.mapToGlobal(self.window.game_grid.rect().center()))
        menu.deleteLater()

    def cancel_artwork(self):
        self.download_cancel.set()
        self.page.game_artwork.cancel_automatic()
        self.window.status.setText("Canceling artwork downloads. Cached covers remain available.")

    def download_artwork(self, games, steam_id=None, missing_only=False):
        if not self._valid():
            return
        if self.downloading:
            self.window.status.setText("Artwork download is already running. Game options can cancel it.")
            return
        games = tuple(games)
        roots = artwork_roots(self.window.inventory, self.window.settings)
        facts = {game.key: dict(self.fact(game)) for game in games}
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
                    present = cached_artwork(game, roots) if missing_only else Artwork()
                    if present.image is not None:
                        art = Artwork()
                    elif steam_id:
                        art = official_artwork(game, canceled=lambda: stop.is_set() or closed.is_set(), steam_id=steam_id)
                    else:
                        art = remote_artwork(game, facts.get(game.key), canceled=lambda: stop.is_set() or closed.is_set())
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
