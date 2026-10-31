"""Crimson Command application shell: premium presentation, existing safe backend.

Run only with: python -m gg_desktop --ui-preview
The existing Tk app remains the normal launcher until human UI parity signoff.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QProgressBar, QVBoxLayout, QWidget, QScrollArea,
)
from core import load_settings
from gg_desktop.backend import Inventory, scan_inventory, ScanCanceled
from gg_desktop.theme import STYLE
from gg_desktop.widgets import label, button, row, column, ScrollPage
from gg_desktop.screens import ScreenMethods

ROUTES = (
    ("Overview", "⌂"),
    ("Games", "▣"),
    ("Mods", "♜"),
    ("Old Files", "▤"),
    ("Graveyard", "♱"),
    ("Game DNA", "⌁"),
    ("Undo Center", "↶"),
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
        self.setWindowTitle("Game Grave  |  Crimson Command preview")
        self.setWindowIcon(QIcon(str(Path(__file__).parent / "assets" / "app_icon.svg")))
        self.setMinimumSize(960, 650)
        self.resize(1450, 900)
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
        brand = label("♱   GAME GRAVE", "brand")
        brand.setStyleSheet("color:#FFFFFF; font-size:20px; font-weight:900;")
        r.addWidget(brand)
        kicker = label("CLEANER GAMES.  A LIGHTER PC.", "brandKicker")
        kicker.setWordWrap(True)
        r.addWidget(kicker)
        r.addSpacing(24)
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
        motto = label("SAME GAMES.\nA CLEANER TOMORROW.", "subtle", wrap=True)
        motto.setStyleSheet("color:#A1B2C2;font-size:12px;letter-spacing:1px;")
        r.addWidget(motto)
        r.addSpacing(15)
        policy = label("LOCAL FIRST  •  RECYCLE BIN ONLY", "caption", wrap=True)
        r.addWidget(policy)
        outer.addWidget(rail)

        main = QWidget()
        base = column(spacing=6, margins=(0, 0, 0, 0))
        main.setLayout(base)
        top = QWidget()
        topbox = row(spacing=10, margins=(20, 13, 20, 9))
        top.setLayout(topbox)
        self.status = label("No scan yet. Choose Scan PC to begin.", "subtle", wrap=True)
        topbox.addWidget(self.status, 1)
        self.cancel_button = button("Cancel scan", self.cancel_scan)
        self.cancel_button.setEnabled(False)
        topbox.addWidget(self.cancel_button)
        self.scan_button = button("⌕  Scan PC", self.start_scan, kind="primary")
        topbox.addWidget(self.scan_button)
        base.addWidget(top)
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
            "Games": self.games_page,
            "Mods": self.mods_page,
            "Old Files": self.old_files_page,
            "Graveyard": self.graveyard_page,
            "Game DNA": self.dna_page,
            "Undo Center": self.undo_page,
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
