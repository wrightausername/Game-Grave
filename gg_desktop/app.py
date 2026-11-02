"""Game Grave locked-theme application shell, existing safe backend.

Run only with: python -m gg_desktop --ui-preview
The existing Tk app remains the normal launcher until human UI parity signoff.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Qt, QTimer
from PySide6.QtGui import QIcon, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QProgressBar, QVBoxLayout, QWidget, QScrollArea, QLineEdit, QDialog,
    QTableWidget, QTableWidgetItem, QAbstractItemView,
)
from core import load_settings
from gg_desktop.backend import Inventory, scan_inventory, ScanCanceled
from gg_desktop.theme import STYLE
from gg_desktop.widgets import label, button, row, column, ScrollPage
from gg_desktop.screens import ScreenMethods

ROUTES = (
    ("Overview", "⌂"),
    ("Ready Room", "◉"),
    ("Games", "▣"),
    ("Mods", "✣"),
    ("Old Files", "▤"),
    ("Other Storage", "≡"),
    ("Captures", "▧"),
    ("Graveyard", "♱"),
    ("Game DNA", "⌁"),
    ("Undo Center", "↶"),
    ("AI Assistant", "✧"),
    ("Settings", "⚙"),
    ("More Tools", "⋯"),
)

ROUTE_ALIASES = {
    "Steam Games": "Games", "Other Launchers": "Games",
    "The Graveyard": "Graveyard", "Game Mods": "Mods",
    "Save Vault": "More Tools", "Resurrection Lab": "More Tools",
    "Cleanup History": "More Tools", "Automation": "More Tools",
    "Make Room": "More Tools", "Storage History": "More Tools",
}


class JobSignals(QObject):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(int, str)


class Job(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.signals = JobSignals()
        self.setAutoDelete(True)

    def run(self):
        try:
            result = self.fn(self.signals.progress.emit)
            self.signals.done.emit(result)
        except Exception as exc:
            self.signals.failed.emit(type(exc).__name__ + ": " + str(exc)[:300])


class CrimsonWindow(ScreenMethods, QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.inventory = Inventory()
        self.scanning = False
        self.cleaning = False
        self.cancel = threading.Event()
        self.workers = {}
        self.pool = QThreadPool.globalInstance()
        self.current_route = "Overview"
        self.setWindowTitle("Game Grave  |  cinematic Qt preview")
        self.setWindowIcon(QIcon(str(Path(__file__).parent / "assets" / "app_icon.svg")))
        self.setMinimumSize(1040, 690)
        self.resize(1672, 941)
        self.setStyleSheet(STYLE)
        self._create_shell()
        self.navigate("Overview")
        if self.settings.get("scan_on_launch", False):
            QTimer.singleShot(0, self.start_scan)

    def _create_shell(self):
        root = QWidget()
        root.setObjectName("appRoot")
        outer = row(spacing=0)
        root.setLayout(outer)
        self.setCentralWidget(root)

        rail = QFrame()
        rail.setObjectName("navRail")
        rail.setFixedWidth(219)
        r = column(spacing=7, margins=(12, 23, 12, 18))
        rail.setLayout(r)
        identity = QWidget()
        identity_row = row(spacing=9)
        identity.setLayout(identity_row)
        mark = label("GG", "brand")
        mark.setStyleSheet(
            "color:#FF4055;font-size:30px;font-weight:900;"
            "font-style:italic;letter-spacing:-3px;")
        identity_row.addWidget(mark)
        name = label("GAME GRAVE", "brand")
        name.setStyleSheet("color:#F7F9FD;font-size:17px;font-weight:850;")
        identity_row.addWidget(name)
        identity_row.addStretch()
        r.addWidget(identity)
        r.addSpacing(17)
        self.nav_buttons = {}
        for route, icon in ROUTES:
            control = button(icon + "    " + route,
                             lambda _checked=False, route=route: self.navigate(route),
                             kind="navButton")
            control.setProperty("active", route == self.current_route)
            control.setAccessibleName(route + " page")
            control.setFocusPolicy(Qt.StrongFocus)
            r.addWidget(control)
            self.nav_buttons[route] = control
        r.addStretch()
        policy = label("LOCAL FIRST  •  RECYCLE BIN ONLY", "caption", wrap=True)
        r.addWidget(policy)
        outer.addWidget(rail)

        main = QWidget()
        base = column(spacing=6, margins=(0, 0, 0, 0))
        main.setLayout(base)
        top = QWidget()
        topbox = row(spacing=10, margins=(20, 13, 20, 9))
        top.setLayout(topbox)
        self.global_search = QLineEdit()
        self.global_search.setObjectName("globalSearch")
        self.global_search.setPlaceholderText("⌕  Search games, mods, files, and more…     Ctrl + K")
        self.global_search.setAccessibleName("Search scanned Game Grave items")
        self.global_search.returnPressed.connect(self.open_global_search)
        topbox.addWidget(self.global_search, 1)
        self.cancel_button = button("Cancel scan", self.cancel_scan)
        self.cancel_button.setEnabled(False)
        self.cancel_button.hide()
        topbox.addWidget(self.cancel_button)
        self.scan_button = button("Scan PC", self.start_scan, kind="primary")
        topbox.addWidget(self.scan_button)
        base.addWidget(top)
        self.status = label(
            "Not scanned. Use Scan PC to discover local items; no files will be changed.",
            "caption", wrap=True)
        base.addWidget(self.status)
        self.search_shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        self.search_shortcut.activated.connect(self.global_search.setFocus)
        self.progress = QProgressBar()
        self.progress.setFixedHeight(5)
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.hide()
        base.addWidget(self.progress)
        self.stack_holder = QWidget()
        self.stack_layout = column(spacing=0)
        self.stack_holder.setLayout(self.stack_layout)
        self.page = None
        base.addWidget(self.stack_holder, 1)
        outer.addWidget(main, 1)

    def page_for(self, title: str) -> ScrollPage:
        if self.page is not None:
            self.stack_layout.removeWidget(self.page)
            self.page.deleteLater()
        self.page = ScrollPage()
        self.stack_layout.addWidget(self.page, 1)
        self.current_route = title
        for route, control in self.nav_buttons.items():
            control.setProperty("active", route == title)
            control.style().unpolish(control)
            control.style().polish(control)
        return self.page

    def navigate(self, route: str):
        route = ROUTE_ALIASES.get(route, route)
        if route not in self.nav_buttons:
            route = "More Tools"
        methods = {
            "Overview": self.overview_page,
            "Ready Room": self.ready_room_page,
            "Games": self.games_page,
            "Mods": self.mods_page,
            "Old Files": self.old_files_page,
            "Other Storage": self.other_storage_page,
            "Captures": self.captures_page,
            "Graveyard": self.graveyard_page,
            "Game DNA": self.dna_page,
            "Undo Center": self.undo_page,
            "AI Assistant": self.ai_assistant_page,
            "Settings": self.settings_page,
            "More Tools": self.tools_page,
        }
        methods[route]()

    def job(self, fn, on_success, *, error_title="Operation not completed", progress=None):
        job = Job(fn)
        key = id(job)
        self.workers[key] = job
        def finish(data):
            self.workers.pop(key, None)
            on_success(data)
        def fail(message):
            self.workers.pop(key, None)
            if message.startswith("ScanCanceled:"):
                self.status.setText("Scan canceled. Previous inventory retained.")
            else:
                self.status.setText("Could not finish: " + message[:110])
                QMessageBox.warning(self, error_title, message)
            if self.scanning:
                self.scanning = False
                self.scan_button.setEnabled(True)
                self.cancel_button.setEnabled(False)
                self.progress.hide()
            if self.cleaning:
                self.cleaning = False
        job.signals.done.connect(finish)
        job.signals.failed.connect(fail)
        if progress:
            job.signals.progress.connect(progress)
        self.pool.start(job)

    def open_global_search(self):
        """Search real scanned inventory across tabs; never fabricate results."""
        needle = self.global_search.text().strip().casefold()
        if not needle:
            self.global_search.setFocus()
            return
        if not self.inventory.scanned_at:
            self.info("Scan first", "Run a local Scan PC before searching discovered files.")
            return
        candidates = []
        for game in self.inventory.games:
            candidates.append(("Games", game.name, game.install_path, "Games"))
        for entry in self.inventory.graveyard:
            candidates.append(("Graveyard", entry.name, entry.path, "Graveyard"))
        for mod in self.inventory.mods:
            path = str(getattr(mod, "path", ""))
            candidates.append(("Mods", str(getattr(mod, "source", "Mod")), path, "Mods"))
        for entry in [*self.inventory.screenshots, *self.inventory.recordings]:
            path = str(getattr(entry, "path", ""))
            candidates.append(("Captures", Path(path).name, path, "Captures"))
        for entry in self.inventory.files:
            path = str(getattr(entry, "path", ""))
            candidates.append(("Old Files", Path(path).name, path, "Old Files"))
        for entry in self.inventory.saves:
            path = str(getattr(entry, "path", ""))
            candidates.append(("Other Storage", Path(path).name, path, "Other Storage"))
        matches = [item for item in candidates if needle in
                   (item[0] + " " + item[1] + " " + item[2]).casefold()][:250]
        if not matches:
            self.info("No matching scanned items",
                      "Nothing matched in the current local inventory. "
                      "Try a different query or scan again.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Search results — Game Grave")
        dialog.resize(900, 520)
        layout = column(spacing=10, margins=(16, 16, 16, 16))
        dialog.setLayout(layout)
        layout.addWidget(label(
            f"{len(matches)} matching results (up to 250); select a row to open its tab.",
            "subtle", wrap=True))
        table = QTableWidget(len(matches), 3)
        table.setHorizontalHeaderLabels(["SOURCE", "ITEM", "PATH"])
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.setColumnWidth(0, 120)
        table.setColumnWidth(1, 235)
        table.horizontalHeader().setStretchLastSection(True)
        for i, (source, name, path, _) in enumerate(matches):
            for j, text in enumerate((source, name, path)):
                table.setItem(i, j, QTableWidgetItem(text))
        layout.addWidget(table)
        actions = QWidget()
        controls = row()
        actions.setLayout(controls)
        controls.addStretch()
        controls.addWidget(button("Cancel", dialog.reject))
        controls.addWidget(button("Open selected", dialog.accept, kind="primary"))
        layout.addWidget(actions)
        table.cellDoubleClicked.connect(lambda _r, _c: dialog.accept())
        if dialog.exec() != QDialog.Accepted:
            return
        indexes = table.selectionModel().selectedRows()
        if not indexes:
            self.info("Choose a result", "Select one result row.")
            return
        source, name, path, target = matches[indexes[0].row()]
        if target == "Games":
            self._pending_game_query = name
        elif target == "Graveyard":
            self._pending_grave_query = path
        elif target == "Captures":
            self._pending_capture_query = path
        elif target == "Other Storage":
            self._pending_other_query = path
        self.navigate(target)

    def start_scan(self):
        if self.scanning or self.cleaning:
            return
        self.scanning = True
        self.cancel.clear()
        self.scan_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.show()
        self.progress.setValue(0)
        self.status.setText("Scanning local gaming records. No files are being changed.")
        settings = dict(self.settings)
        rules = tuple(settings.get("never_touch", []))
        settings["never_touch"] = list(rules)

        def progress(percent, stage):
            self.progress.setValue(percent)
            self.status.setText("Scanning: " + stage + " (" + str(percent) + "%)")
        def finish(inventory):
            self.scanning = False
            self.scan_button.setEnabled(True)
            self.cancel_button.setEnabled(False)
            self.progress.setValue(100)
            self.progress.hide()
            if self.cancel.is_set():
                self.status.setText("Scan canceled. The earlier inventory was not replaced.")
                return
            self.inventory = inventory
            self.status.setText(
                f"Scanned {inventory.scanned_at}  •  {len(inventory.games)} game installs, "
                f"{len(inventory.mods)} mod locations, {len(inventory.graveyard)} Graveyard findings."
                + ("  •  Some sources unavailable." if inventory.warnings else ""))
            self.navigate(self.current_route)
        self.job(lambda emitter: scan_inventory(settings, self.cancel.is_set, emitter),
                 finish, error_title="Local scan incomplete", progress=progress)

    def cancel_scan(self):
        if self.scanning:
            self.cancel.set()
            self.status.setText("Stopping the read-only scan…")

    def confirm(self, title: str, message: str, *, destructive: bool = False) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(message)
        box.setIcon(QMessageBox.Warning if destructive else QMessageBox.Question)
        box.setStandardButtons(QMessageBox.Cancel | QMessageBox.Yes)
        box.setDefaultButton(QMessageBox.Cancel)
        return box.exec() == QMessageBox.Yes

    def info(self, title: str, message: str):
        QMessageBox.information(self, title, message)

    def error(self, title: str, message: str):
        QMessageBox.warning(self, title, message)

    def closeEvent(self, event):
        if self.scanning or self.cleaning:
            self.error("Game Grave is busy",
                       "Cancel the scan or finish the approved recovery operation before closing.")
            event.ignore()
            return
        super().closeEvent(event)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Game Grave")
    app.setOrganizationName("Game Grave")
    app.setStyleSheet(STYLE)
    app.setQuitOnLastWindowClosed(True)
    win = CrimsonWindow()
    win.show()
    return app.exec()
