"""Overview's behavior, attached to the existing widgets without restyling them."""
from __future__ import annotations

from pathlib import Path
import threading
import weakref

from PySide6.QtCore import QObject, QEvent, Qt, QTimer
from PySide6.QtGui import QImage, QPixmap, QShortcut, QKeySequence
from PySide6.QtWidgets import QDialog, QLabel, QListWidget, QListWidgetItem, QPushButton, QTableWidget, QWidget
from shiboken6 import isValid

from core import human_size, is_unchanged
from gg_desktop.overview_data import disk_reading, latest_capture, launcher_games
from gg_desktop.widgets import button, column, label, row
from screenshot_preview import decode_screenshot_preview


class OverviewController(QObject):
    def __init__(self, window, page):
        super().__init__(page)
        self.window = window
        self.page = page
        self.active = threading.Event()
        self.active.set()
        active = self.active
        page.destroyed.connect(lambda: active.clear())
        self.storage_busy = False
        self.capture_busy = False
        self.targets = {}
        self.latest = None
        self.capture_layout = None
        self.disk = self.summary = None
        self.shortcuts = [QShortcut(QKeySequence("F5"), page)]
        self.shortcuts[0].activated.connect(self.scan)
        self.timer = QTimer(page)
        self.timer.setInterval(30000)
        self.timer.timeout.connect(self.refresh_storage)
        self.timer.start()

    def bind_action(self, card, action):
        # ActionCard's child labels accept text-selection events. On Overview,
        # clicking the displayed title should activate the same card action.
        for child in card.findChildren(QWidget):
            if not isinstance(child, QPushButton):
                child.installEventFilter(self)
                self.targets[child] = action

    def eventFilter(self, target, event):
        action = self.targets.get(target)
        if action and event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            if target.rect().contains(event.position().toPoint()):
                action()
                return True
        if target is self.disk:
            if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                self.storage_details()
                return True
            if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Return, Qt.Key_Space, Qt.Key_Enter):
                self.storage_details()
                return True
        return super().eventFilter(target, event)

    def _task(self, fn, done):
        owner = weakref.ref(self)
        def run(_progress):
            try:
                return fn(), ""
            except Exception as exc:
                return None, str(exc)[:300] or type(exc).__name__
        def finish(packet):
            control = owner()
            if (control is not None and isValid(control) and control.active.is_set()
                    and isValid(control.window) and control.window.isVisible()
                    and control.window.page is control.page):
                done(*packet)
        # Returning errors as data keeps background Overview reads from changing
        # the shell's unrelated scan/cleanup flags through its error handler.
        self.window.job(run, finish, error_title="Overview check unavailable")

    def scan(self):
        if self.window.scanning or self.window.cleaning:
            self.window.status.setText("Finish the current scan or backup first.")
        else:
            self.window.start_scan()

    def bind_storage(self, disk, summary):
        self.disk, self.summary = disk, summary
        disk.installEventFilter(self)
        disk.setFocusPolicy(Qt.StrongFocus)
        disk.setCursor(Qt.PointingHandCursor)
        disk.setToolTip("Open system-drive details. The reading refreshes while Overview is open.")

    def refresh_storage(self, done=None):
        if self.storage_busy or not self.active.is_set():
            return
        self.storage_busy = True
        def finish(result, error):
            self.storage_busy = False
            if error:
                self.disk.update_amounts(0, 0)
                self.summary.setText("Drive usage not available")
                self.summary.setToolTip(error)
            else:
                path, usage = result
                self.disk.update_amounts(usage.total, usage.free)
                self.summary.setText(f"{human_size(usage.used)} used  •  {human_size(usage.free)} free  •  {human_size(usage.total)} capacity")
                self.summary.setToolTip(str(path))
            if done:
                done(result, error)
        self._task(disk_reading, finish)

    def storage_details(self):
        dialog = QDialog(self.window)
        dialog.setWindowTitle("Game Grave · Storage Overview")
        dialog.resize(580, 330)
        stack = column(margins=(20, 18, 20, 18))
        dialog.setLayout(stack)
        stack.addWidget(label("Storage Overview", "sectionTitle"))
        reading = label(self.summary.text(), "subtle", wrap=True)
        stack.addWidget(reading)
        stack.addWidget(label("This is the operating-system drive's used and free space. Game and mod sizes may overlap; "
                              "Recycle Bin contents can still occupy disk space.", "subtle", wrap=True))
        stack.addStretch()
        actions = row()
        refresh = button("Refresh reading")
        def completed(result, error):
            if isValid(dialog) and dialog.isVisible():
                reading.setText(error or self.summary.text())
                refresh.setEnabled(True)
        def start():
            if self.storage_busy:
                return
            refresh.setEnabled(False)
            self.refresh_storage(completed)
        refresh.clicked.connect(start)
        actions.addWidget(refresh)
        actions.addStretch()
        actions.addWidget(button("Close", dialog.accept))
        stack.addLayout(actions)
        dialog.exec()

    def show_launcher(self, name):
        if name != "Multiple launchers":
            self.window._go_launcher(name)
            return
        records = launcher_games(self.window.inventory.games, name)
        dialog = QDialog(self.window)
        dialog.setWindowTitle("Game Grave · Multiple launchers")
        dialog.resize(700, 430)
        stack = column(margins=(20, 18, 20, 18))
        dialog.setLayout(stack)
        stack.addWidget(label("Multiple launchers", "sectionTitle"))
        stack.addWidget(label("These installations have more than one launcher claim. Each installation is counted once.", "subtle", wrap=True))
        entries = QListWidget()
        entries.setAccessibleName("Installations claimed by multiple launchers")
        for game in records:
            item = QListWidgetItem(game.name + " · " + game.launcher)
            item.setData(Qt.UserRole, game.key)
            item.setToolTip(game.install_path)
            entries.addItem(item)
        stack.addWidget(entries, 1)
        def inspect(*_):
            item = entries.currentItem()
            game = next((g for g in self.window.inventory.games if item and g.key == item.data(Qt.UserRole)), None)
            if game:
                dialog.accept()
                self.window.navigate("Games")
                self.window.game_filter.setCurrentText(game.launcher)
                self.window.game_search.setText(game.install_path)
                for index, record in enumerate(self.window._shown_games):
                    if record.key == game.key:
                        self.window.game_table.selectRow(index)
                        break
        entries.itemDoubleClicked.connect(inspect)
        actions = row()
        actions.addWidget(button("Inspect selected installation", inspect))
        actions.addStretch()
        actions.addWidget(button("Close", dialog.accept))
        stack.addLayout(actions)
        dialog.exec()

    def show_finding(self, key):
        finding = next((e for e in self.window.inventory.graveyard if e.key == key), None)
        if finding is None:
            self.window.status.setText("This finding is no longer in the accepted scan. Scan again to refresh Overview.")
            return
        self.window._go_grave_item(key)
        self.window.grave_search.setText(finding.path)
        for index, entry in enumerate(self.window._shown_graves):
            if entry.key == key:
                self.window.grave_table.selectRow(index)
                self.window.grave_table.scrollToItem(self.window.grave_table.item(index, 0))
                break

    def show_mod(self, mod):
        self.window.navigate("Mods")
        table = self.window.page.findChild(QTableWidget)
        if table:
            for index in range(table.rowCount()):
                if table.item(index, 0).text() == str(mod.path):
                    table.selectRow(index)
                    table.scrollToItem(table.item(index, 0))
                    break

    def render_capture(self, record):
        self.latest = record
        layout = self.capture_layout
        while layout.count() > 2:
            child = layout.takeAt(2)
            if child.widget():
                child.widget().hide()
                child.widget().deleteLater()
        if record:
            layout.addWidget(label("▧", "metricValue"))
            layout.addWidget(label(Path(record.path).name, "sectionTitle", wrap=True))
            layout.addWidget(label(human_size(record.size) + "  •  Content not opened automatically", "caption", wrap=True))
            layout.addWidget(button("Preview this image", self.preview_capture))
        else:
            layout.addWidget(label("No old in-game screenshots recorded. Personal photos are never browsed by default.", "subtle", wrap=True))
        layout.addStretch()

    def refresh_capture(self):
        if not self.window.inventory.scanned_at or self.capture_busy:
            return
        self.capture_busy = True
        inventory = self.window.inventory
        settings = {key: list(self.window.settings.get(key, [])) for key in ("steam_extra_roots", "screenshot_roots")}
        stop = self.active
        def finish(result, error):
            self.capture_busy = False
            if self.window.inventory is not inventory:
                return
            if error:
                self.page.setToolTip("Latest screenshot check incomplete: " + error)
            else:
                self.render_capture(result.latest)
                if result.limited or result.warnings:
                    self.page.setToolTip("Latest screenshot within the inspected capture locations. " + " ".join(result.warnings))
        self._task(lambda: latest_capture(settings, canceled=lambda: not stop.is_set()), finish)

    def preview_capture(self):
        record = self.latest
        if record is None or not is_unchanged(record):
            self.window.error("Screenshot unavailable", "The screenshot was moved or changed. Scan again before previewing it.")
            return
        def finish(image, error):
            if error:
                self.window.error("Could not preview screenshot", error)
                return
            if not is_unchanged(record):
                self.window.error("Screenshot changed", "Scan again before previewing the changed image.")
                return
            qimage = QImage(image.tobytes(), image.width, image.height, image.width * 3, QImage.Format_RGB888).copy()
            dialog = QDialog(self.window)
            dialog.setWindowTitle("Game Grave · Latest Screenshot")
            dialog.resize(920, 680)
            stack = column(margins=(18, 18, 18, 18))
            dialog.setLayout(stack)
            title = label(Path(record.path).name, "sectionTitle", wrap=True)
            title.setTextFormat(Qt.PlainText)
            stack.addWidget(title)
            picture = QLabel()
            picture.setAlignment(Qt.AlignCenter)
            picture.setPixmap(QPixmap.fromImage(qimage).scaled(870, 535, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            stack.addWidget(picture, 1)
            stack.addWidget(label("Previewed locally at your request. Your screenshot stays untouched.", "subtle", wrap=True))
            actions = row()
            actions.addWidget(button("Open containing folder", lambda: self.window._open_folder(str(Path(record.path).parent))))
            actions.addStretch()
            actions.addWidget(button("Close", dialog.accept))
            stack.addLayout(actions)
            dialog.exec()
        self._task(lambda: decode_screenshot_preview(record), finish)
