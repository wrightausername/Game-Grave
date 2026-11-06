"""Games-tab controls and artwork. Other screens and the shared shell stay intact."""
from __future__ import annotations

from collections import OrderedDict
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import threading
import weakref

from PySide6.QtCore import QObject, Qt, QSize, QRectF, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QImage, QKeySequence, QLinearGradient, QPainter, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import QComboBox, QFileDialog, QGridLayout, QInputDialog, QLabel, QMenu, QSizePolicy, QTableWidgetItem, QWidget
from shiboken6 import isValid

from core import age_text
from gg_desktop.game_artwork import (Artwork, choose_artwork, clear_artwork, game_id,
    load_preferences, local_artwork, official_artwork, save_preferences)
from gg_desktop.games_data import chosen_executable, filtered_games, install_directory, launch_uri, steam_install_current
from gg_desktop.models import readable_bytes
from gg_desktop.widgets import button, column, destroy_layout, label, row

PAGE_SIZE = 500


class GameActions(QWidget):
    def __init__(self):
        super().__init__()
        self.buttons = []
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(10)
        self.columns = 0

    def add(self, control):
        self.buttons.append(control)
        self.reflow()

    def reflow(self):
        columns = 2 if self.width() < 740 else 3 if self.width() < 1000 else 5
        if columns == self.columns and self.grid.count() == len(self.buttons):
            return
        self.columns = columns
        for control in self.buttons:
            self.grid.removeWidget(control)
        for i, control in enumerate(self.buttons):
            self.grid.addWidget(control, i // columns, i % columns)

    def resizeEvent(self, event):
        self.reflow()
        super().resizeEvent(event)


def fallback_artwork(game, size=QSize(240, 360)):
    """An original, title-specific local cover. Never presented as official art."""
    pixmap = QPixmap(size)
    pixmap.fill(QColor("#0D141D"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    w, h = size.width(), size.height()
    digest = sha256((game.name + game.launcher).encode()).digest()
    color = QColor.fromHsl(int.from_bytes(digest[:2], "big") % 360, 155, 105)
    gradient = QLinearGradient(0, 0, w, h)
    gradient.setColorAt(0, color.darker(280))
    gradient.setColorAt(.65, color.darker(145))
    gradient.setColorAt(1, QColor("#080C13"))
    painter.fillRect(pixmap.rect(), gradient)
    painter.setPen(QPen(color.lighter(145), max(1, w / 140)))
    painter.drawEllipse(QRectF(w * .36, h * .13, w * .8, w * .8))
    for i in range(6):
        x = w * (i * .19 - .12)
        painter.fillRect(QRectF(x, h * (.38 + digest[i] / 900), w * .12, h * .38), QColor(6, 11, 19, 175))
    painter.fillRect(QRectF(0, h * .68, w, h * .32), QColor(4, 8, 14, 225))
    painter.setPen(QColor("#F4F7FC"))
    font = QFont("Segoe UI")
    font.setBold(True)
    font.setPixelSize(max(10, int(w / (11 if h > 90 else 3.6))))
    painter.setFont(font)
    text = game.name if h > 90 else "".join(word[:1] for word in game.name.split()[:2]).upper()
    painter.drawText(QRectF(w * .08, h * .69 if h > 90 else 0, w * .84, h * .22 if h > 90 else h),
                     Qt.AlignCenter | Qt.TextWordWrap, text)
    if h > 90:
        font.setBold(False)
        font.setPixelSize(max(10, int(w / 19)))
        painter.setFont(font)
        painter.setPen(QColor("#A3B4C5"))
        painter.drawText(QRectF(5, h * .93, w - 10, h * .05), Qt.AlignCenter, game.launcher)
    painter.end()
    return pixmap


def artwork_roots(inventory, settings):
    from core import _steam_roots
    roots = [Path(g.library) for g in inventory.steam]
    roots.extend(_steam_roots(list(settings.get("steam_extra_roots", []))))
    return list(dict.fromkeys(roots))[:12]


class GamesController(QObject):
    def __init__(self, window, page):
        super().__init__(page)
        self.window, self.page = window, page
        self.closed = threading.Event()
        closed = self.closed
        page.destroyed.connect(lambda: closed.set())
        self.download_cancel = threading.Event()
        self.preferences = load_preferences()
        self.pictures = OrderedDict()
        self.loading = self.downloading = False
        self.load_again = False
        self.index = 0
        self.selected_key = None
        self.rows = []
        self.paging = None
        self.pending_pick = ""
        self.art_label = None
        self.art_picture = None
        self.art_timer = QTimer(page)
        self.art_timer.setSingleShot(True)
        self.art_timer.setInterval(60)
        self.art_timer.timeout.connect(self.load_visible_artwork)
        self.shortcuts = []

    def _valid(self):
        return (not self.closed.is_set() and isValid(self.window) and self.window.page is self.page)

    def _task(self, fn, done, *, progress=None):
        owner = weakref.ref(self)
        def work(emitter):
            try:
                return fn(emitter), ""
            except Exception as exc:
                return None, str(exc)[:350] or type(exc).__name__
        def finish(packet):
            control = owner()
            if control is not None and isValid(control) and control._valid():
                done(*packet)
        def update(amount, message):
            control = owner()
            if control is not None and isValid(control) and control._valid() and progress:
                progress(amount, message)
        self.window.job(work, finish, progress=update)

    def bind(self, table_layout):
        table = self.window.game_table
        table.setIconSize(QSize(32, 26))
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(self.context_menu)
        table.verticalScrollBar().valueChanged.connect(lambda *_: self.art_timer.start())
        table.itemDoubleClicked.connect(lambda *_: self.page.ensureWidgetVisible(self.window.game_details))
        self.paging = QWidget()
        controls = row()
        self.paging.setLayout(controls)
        self.previous = button("← Previous", lambda: self.change_page(-1))
        self.next = button("Next →", lambda: self.change_page(1))
        self.page_count = label("", "caption")
        controls.addWidget(self.previous)
        controls.addWidget(self.page_count, 1, Qt.AlignCenter)
        controls.addWidget(self.next)
        table_layout.addWidget(self.paging)
        self.paging.hide()
        for keys, action in (("Ctrl+K", self.window.game_search.setFocus),
                             ("Escape", self.window.game_search.clear),
                             ("Shift+F10", lambda: self.options(self.selected()) if self.selected() else None),
                             ("Ctrl+PgDown", lambda: self.change_page(1)),
                             ("Ctrl+PgUp", lambda: self.change_page(-1))):
            shortcut = QShortcut(QKeySequence(keys), self.page)
            shortcut.activated.connect(action)
            self.shortcuts.append(shortcut)

    def selected(self):
        table = self.window.game_table
        selection = table.selectionModel().selectedRows()
        index = selection[0].row() if selection else -1
        shown = getattr(self.window, "_shown_games", [])
        return shown[index] if 0 <= index < len(shown) else None

    def current(self, game):
        result = next((g for g in self.window.inventory.games if g.key == game.key), None)
        if result is None or result.install_path != game.install_path or result.launcher != game.launcher or result.app_id != game.app_id:
            raise ValueError("This game record changed. Run Scan PC again.")
        return result

    def fill(self, *_ , keep_page=False):
        previous = self.selected()
        if previous:
            self.selected_key = previous.key
        rows = filtered_games(self.window.inventory.games, self.window.game_search.text(),
                              self.window.game_filter.currentText(), self.window.game_sort.currentText())
        if not keep_page:
            self.index = 0
            location = next((i for i, g in enumerate(rows) if g.key == self.selected_key), -1)
            if location >= 0:
                self.index = location // PAGE_SIZE
        self.index = max(0, min(self.index, max(0, (len(rows) - 1) // PAGE_SIZE)))
        self.rows = rows
        start = self.index * PAGE_SIZE
        shown = rows[start:start + PAGE_SIZE]
        self.window._shown_games = shown
        table = self.window.game_table
        table.blockSignals(True)
        table.clearSelection()
        table.setRowCount(len(shown))
        for i, game in enumerate(shown):
            values = (game.name, game.launcher, readable_bytes(game.size_bytes),
                      age_text(game.last_played_at) if game.last_played_at is not None else "Unknown", game.status)
            for c, text in enumerate(values):
                item = QTableWidgetItem(str(text))
                item.setToolTip(str(text))
                table.setItem(i, c, item)
            self.paint_row(i, game)
            table.setRowHeight(i, 36)
        pick = next((i for i, game in enumerate(shown) if game.key == self.selected_key), 0)
        if shown:
            table.selectRow(pick)
        table.blockSignals(False)
        self.paging.setVisible(len(rows) > PAGE_SIZE)
        self.previous.setEnabled(self.index > 0)
        self.next.setEnabled(start + PAGE_SIZE < len(rows))
        self.page_count.setText(f"{start + 1 if rows else 0}–{start + len(shown)} of {len(rows)} matching games")
        if not shown:
            self.selected_key = None
        self.details()
        self.art_timer.start()

    def change_page(self, amount):
        new = self.index + amount
        if 0 <= new <= max(0, (len(self.rows) - 1) // PAGE_SIZE):
            self.index = new
            self.selected_key = None
            self.window.game_table.clearSelection()
            self.fill(keep_page=True)
            self.window.game_table.scrollToTop()

    def picture(self, game, size):
        data = self.pictures.get(game.key)
        if data and data[0] is not None:
            return data[0].scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        return fallback_artwork(game, size)

    def paint_row(self, index, game):
        item = self.window.game_table.item(index, 0)
        if item is not None:
            item.setIcon(QIcon(self.picture(game, QSize(32, 26))))
            source = self.pictures.get(game.key, (None, Artwork().source))[1]
            item.setToolTip(game.name + "\n" + source)

    def remember(self, game, art):
        pixmap = None
        if art.image is not None:
            image = art.image.copy()
            image.thumbnail((240, 360))
            qimage = QImage(image.tobytes(), image.width, image.height, image.width * 3, QImage.Format_RGB888).copy()
            pixmap = QPixmap.fromImage(qimage)
        self.pictures[game.key] = (pixmap, art.source)
        self.pictures.move_to_end(game.key)
        while len(self.pictures) > 100:
            self.pictures.popitem(last=False)
        for index, record in enumerate(self.window._shown_games):
            if record.key == game.key:
                self.paint_row(index, record)
        selected = self.selected()
        if selected and selected.key == game.key and self.art_picture is not None and isValid(self.art_picture):
            self.art_picture.setPixmap(self.picture(game, QSize(120, 180)))
            self.art_label.setText(art.source)

    def load_visible_artwork(self):
        if self.loading:
            self.load_again = True
            return
        if not self._valid() or not self.window._shown_games:
            return
        table = self.window.game_table
        first = max(0, table.rowAt(0))
        last = table.rowAt(max(0, table.viewport().height() - 1))
        if last < first:
            last = min(len(self.window._shown_games) - 1, first + 15)
        selected = self.selected()
        records = list(self.window._shown_games[first:min(last + 12, first + 40)])
        if selected and selected not in records:
            records.append(selected)
        records = [g for g in records if g.key not in self.pictures]
        if not records:
            return
        self.loading = True
        inventory, settings, closed = self.window.inventory, dict(self.window.settings), self.closed
        def run(_progress):
            roots = artwork_roots(inventory, settings)
            results = []
            for game in records:
                if closed.is_set():
                    break
                results.append((game, local_artwork(game, roots)))
            return results
        def finish(result, error):
            self.loading = False
            for game, art in result or []:
                self.remember(game, art)
            if self.load_again:
                self.load_again = False
                self.art_timer.start()
        self._task(run, finish)

    def details(self):
        game = self.selected()
        destroy_layout(self.window.game_details_col)
        self.art_picture = self.art_label = None
        if game is None:
            self.window.game_details_col.addWidget(label("No games match these filters. Clear the search or choose another launcher.", "subtle", wrap=True))
            return
        self.selected_key = game.key
        title = label(game.name, "sectionTitle", wrap=True)
        title.setTextFormat(Qt.PlainText)
        self.window.game_details_col.addWidget(title)
        content = QWidget()
        body = row(spacing=18)
        content.setLayout(body)
        art = column(spacing=5)
        self.art_picture = QLabel()
        self.art_picture.setFixedSize(120, 180)
        self.art_picture.setAlignment(Qt.AlignCenter)
        self.art_picture.setPixmap(self.picture(game, QSize(120, 180)))
        self.art_picture.setAccessibleName(game.name + " artwork")
        art.addWidget(self.art_picture)
        self.art_label = label(self.pictures.get(game.key, (None, Artwork().source))[1], "caption", wrap=True)
        self.art_label.setMaximumWidth(120)
        art.addWidget(self.art_label)
        body.addLayout(art)
        words = column()
        for text in (f"Launcher: {game.launcher}", f"Install location: {game.install_path}",
                     f"Install status: {game.status}", f"Evidence: {game.install_evidence}",
                     f"Size: {readable_bytes(game.size_bytes)} ({game.size_source})",
                     f"Last played: {age_text(game.last_played_at) if game.last_played_at is not None else 'Unknown'}"):
            line = label(text, "subtle", wrap=True)
            line.setTextFormat(Qt.PlainText)
            line.setMinimumWidth(0)
            line.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            line.setToolTip(text)
            words.addWidget(line)
        words.addStretch()
        body.addLayout(words, 1)
        self.window.game_details_col.addWidget(content)
        actions = GameActions()
        launch = button("Launch game", lambda _=False, g=game: self.launch(g), kind="primary")
        launch.setEnabled(bool(launch_uri(game) or self.preferences["executables"].get(game_id(game))))
        if not launch.isEnabled():
            launch.setToolTip("Use Game options to choose this game's EXE when its launcher has no supported shortcut.")
        actions.add(launch)
        open_folder = button("Open installation folder", lambda _=False, g=game: self.open_folder(g))
        open_folder.setEnabled("open_folder" in game.capabilities)
        actions.add(open_folder)
        actions.add(button("See related Game DNA", lambda _=False, g=game: self.show_dna(g)))
        if "steam_uninstall" in game.capabilities:
            actions.add(button("Open Steam uninstall…", lambda _=False, g=game: self.uninstall(g), kind="danger"))
        actions.add(button("Game options…", lambda _=False, g=game: self.options(g)))
        self.window.game_details_col.addWidget(actions)
        self.art_timer.start()

    def open_folder(self, game):
        try:
            self.window._open_folder(str(install_directory(self.current(game))))
        except (OSError, ValueError) as exc:
            self.window.error("Installation unavailable", str(exc))

    def launch(self, game):
        try:
            game = self.current(game)
            install_directory(game)
            executable = self.preferences["executables"].get(game_id(game))
            if executable:
                executable = chosen_executable(game, executable)
                if sys.platform != "win32":
                    raise ValueError("This game EXE can be launched from the Windows application.")
                os.startfile(executable, cwd=str(Path(executable).parent))
            else:
                uri = launch_uri(game)
                if game.launcher == "Steam" and not steam_install_current(game, self.window.inventory.steam):
                    raise ValueError("Steam's current installation record differs from the scan. Scan PC again.")
                if not uri or not QDesktopServices.openUrl(QUrl(uri)):
                    raise ValueError("The launcher could not open this game. Check that it is installed, or choose the game's EXE in Game options.")
            self.window.status.setText("Launch requested for " + game.name + ". The game or launcher controls startup.")
        except (OSError, ValueError) as exc:
            self.window.error("Could not launch game", str(exc))

    def uninstall(self, game):
        try:
            game = self.current(game)
            if "steam_uninstall" not in game.capabilities or not steam_install_current(game, self.window.inventory.steam):
                raise ValueError("The exact Steam installation could not be revalidated. Scan PC again.")
            if not self.window.confirm("Open Steam uninstall?", "Open Steam's own uninstall dialog for\n\n" + game.name +
                "?\n\nGame Grave will not remove game files directly.", destructive=True):
                return
            if not steam_install_current(game, self.window.inventory.steam):
                raise ValueError("The Steam installation changed while the dialog was open. Scan again.")
            if not QDesktopServices.openUrl(QUrl("steam://uninstall/" + game.app_id)):
                raise ValueError("Steam did not accept the uninstall request.")
            self.window.status.setText("Steam uninstall requested for " + game.name + ". Finish in Steam; removal is not confirmed.")
        except (OSError, ValueError) as exc:
            self.window.error("Could not open Steam uninstall", str(exc))

    def show_dna(self, game):
        from game_intelligence import build_game_dna
        try:
            game = self.current(game)
        except ValueError as exc:
            self.window.error("Game record unavailable", str(exc))
            return
        inventory = self.window.inventory
        records = build_game_dna(inventory.steam, inventory.other, inventory.mods, inventory.saves)["games"]
        identity = os.path.normcase(os.path.abspath(game.install_path))
        index = next((i for i, record in enumerate(records)
                      if os.path.normcase(os.path.abspath(record["install_path"])) == identity
                      and record["launcher"] in (game.launcher, *game.claimed_by)), -1)
        self.window.navigate("Game DNA")
        chooser = self.window.page.findChild(QComboBox)
        if chooser and index >= 0:
            chooser.setCurrentIndex(index)

    def context_menu(self, point):
        table = self.window.game_table
        index = table.rowAt(point.y())
        if index < 0:
            return
        table.selectRow(index)
        self.options(self.selected(), table.viewport().mapToGlobal(point))

    def options(self, game, position=None):
        if not self._valid():
            return
        menu = QMenu(self.window)
        menu.addAction("View source evidence", lambda: self.window.info("Game Source Evidence",
            game.install_evidence + "\n\nSize source: " + game.size_source + "\nLast played source: " + game.last_played_source))
        menu.addAction("Choose artwork…", lambda: self.choose_picture(game))
        menu.addAction("Download official artwork", lambda: self.download_artwork([game]))
        menu.addAction("Use a Steam artwork app ID…", lambda: self.choose_art_id(game))
        menu.addAction("Reset chosen artwork", lambda: self.reset_picture(game))
        menu.addSeparator()
        menu.addAction("Download missing artwork for all games", lambda: self.download_artwork(tuple(self.window.inventory.games), missing_only=True))
        cancel = menu.addAction("Cancel artwork downloads", self.download_cancel.set)
        cancel.setEnabled(self.downloading)
        menu.addSeparator()
        choose = menu.addAction("Choose game launch EXE…", lambda: self.choose_executable(game))
        choose.setEnabled("open_folder" in game.capabilities)
        menu.addAction("Use default launcher", lambda: self.clear_executable(game))
        menu.addAction("Copy installation path", lambda: self.copy_path(game))
        menu.exec(position or self.window.game_table.mapToGlobal(self.window.game_table.rect().center()))

    def copy_path(self, game):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(game.install_path)

    def choose_executable(self, game):
        if not self._valid():
            return
        source, _ = QFileDialog.getOpenFileName(self.window, "Choose this game's launch EXE", game.install_path, "Windows game EXE (*.exe)")
        if not source or not self._valid():
            return
        try:
            target = chosen_executable(self.current(game), source)
            updated = {"schema": 1, "executables": {**self.preferences["executables"], game_id(game): target}}
            save_preferences(updated)
            self.preferences = updated
            self.details()
        except (OSError, ValueError) as exc:
            self.window.error("Launch EXE not saved", str(exc))

    def clear_executable(self, game):
        try:
            updated = {"schema": 1, "executables": {k: v for k, v in self.preferences["executables"].items() if k != game_id(game)}}
            save_preferences(updated)
            self.preferences = updated
            self.details()
        except (OSError, ValueError) as exc:
            self.window.error("Launch preference not saved", str(exc))

    def choose_picture(self, game):
        if not self._valid():
            return
        source, _ = QFileDialog.getOpenFileName(self.window, "Choose artwork for " + game.name, "", "Game artwork (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not source or not self._valid():
            return
        def run(_progress):
            choose_artwork(game, source)
            return local_artwork(game)
        def finish(art, error):
            if error:
                self.window.error("Artwork not saved", error)
            else:
                self.remember(game, art)
        self._task(run, finish)

    def reset_picture(self, game):
        try:
            clear_artwork(game)
            self.pictures.pop(game.key, None)
            self.art_timer.start()
        except (OSError, ValueError) as exc:
            self.window.error("Artwork not reset", str(exc))

    def choose_art_id(self, game):
        if not self._valid():
            return
        ident, accepted = QInputDialog.getText(self.window, "Choose official artwork", "Steam app ID for the artwork you want (does not change this game's launcher):")
        if accepted and self._valid():
            if not ident.strip().isascii() or not ident.strip().isdecimal():
                self.window.error("Invalid artwork ID", "Enter the numeric Steam app ID.")
                return
            self.download_artwork([game], steam_id=ident.strip())

    def download_artwork(self, games, steam_id=None, missing_only=False):
        if not self._valid():
            return
        if self.downloading:
            self.window.status.setText("Artwork download is already running. Game options can cancel it.")
            return
        games = tuple(games)
        inventory, settings = self.window.inventory, dict(self.window.settings)
        self.downloading = True
        self.download_cancel.clear()
        stop, closed = self.download_cancel, self.closed
        self.window.status.setText("Downloading official game artwork… Only public game IDs/titles are sent.")
        def run(progress):
            found = failures = completed = 0
            roots = artwork_roots(inventory, settings) if missing_only else ()
            for index, game in enumerate(games):
                if stop.is_set() or closed.is_set():
                    break
                try:
                    present = local_artwork(game, roots) if missing_only else Artwork()
                    art = Artwork() if present.image is not None else official_artwork(
                        game, canceled=lambda: stop.is_set() or closed.is_set(), steam_id=steam_id)
                    if art.image is not None:
                        found += 1
                    failures = 0
                except (OSError, ValueError, TypeError):
                    failures += 1
                completed = index + 1
                progress(int(completed * 100 / max(1, len(games))), json.dumps({"key": game.key, "count": completed, "total": len(games)}))
                if failures >= 3:
                    break
            return found, completed, len(games)
        def progress(percent, message):
            data = json.loads(message)
            self.pictures.pop(data["key"], None)
            self.art_timer.start()
            self.window.status.setText(f"Artwork: checked {data['count']} of {data['total']} games ({percent}%). Cached art stays available offline.")
        def finish(result, error):
            self.downloading = False
            if error:
                self.window.error("Artwork download incomplete", error)
            else:
                found, completed, total = result
                self.window.status.setText(f"Artwork: {found} official covers downloaded; {completed} of {total} games checked. "
                                          "Games without an exact match retain local artwork or their labeled fallback.")
            self.art_timer.start()
        self._task(run, finish, progress=progress)
