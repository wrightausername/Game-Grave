"""Crimson Command application shell: premium presentation, existing safe backend.

Run only with: python -m gg_desktop --ui-preview
The existing Tk app remains the normal launcher until human UI parity signoff.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Qt, QTimer, QSize, QEvent
from PySide6.QtGui import QColor, QFontDatabase, QIcon, QKeySequence, QPalette, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication, QFrame, QLabel, QMainWindow, QMessageBox,
    QProgressBar, QWidget, QLineEdit,
)
from core import load_settings
from gg_desktop.backend import Inventory, scan_inventory
from gg_desktop.theme import STYLE
from gg_desktop.widgets import label, button, row, column, ScrollPage
from gg_desktop.screens import ScreenMethods
from gg_desktop.icons import icon, icon_label
from gg_desktop.ready_room import (
    ASSETS, READY_STYLE, MainCanvas, NavigationButton, NavigationRail,
    ReadyRoomMethods, WindowHeader,
)

ROUTES = (
    ("Overview", "home"),
    ("Ready Room", "radio"),
    ("Games", "gamepad"),
    ("Mods", "puzzle"),
    ("Old Files", "archive"),
    ("Other Storage", "database"),
    ("Captures", "camera"),
    ("Graveyard", "grave"),
    ("Game DNA", "dna"),
    ("Undo Center", "undo"),
    ("AI Assistant", "sparkles"),
    ("Settings", "settings"),
    ("More Tools", "grid"),
)

ROUTE_ALIASES = {
    "Steam Games": "Games", "Other Launchers": "Games",
    "The Graveyard": "Graveyard", "Game Mods": "Mods",
    "Resurrection Lab": "More Tools",
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


class CrimsonWindow(ReadyRoomMethods, ScreenMethods, QMainWindow):
    def __init__(self, *, reference_preview=False):
        super().__init__()
        QFontDatabase.addApplicationFont(str(ASSETS / "RobotoCondensed.ttf"))
        self.reference_preview = reference_preview
        self.session_backups = 0
        self.settings = load_settings()
        self.inventory = Inventory()
        self.scanning = False
        self.cleaning = False
        self.cancel = threading.Event()
        self.workers = {}
        self.pool = QThreadPool.globalInstance()
        self.current_route = "Ready Room"
        self.setWindowTitle("Game Grave | Ready Room" +
                            (" | Reference preview · sample data" if reference_preview else ""))
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
        self.setWindowIcon(QIcon(str(Path(__file__).parent / "assets" / "app_icon.svg")))
        self.setMinimumSize(960, 650)
        self.resize(1280, 720)
        self.setStyleSheet(STYLE + READY_STYLE)
        self._create_shell()
        self.navigate("Ready Room")
        self.main_canvas.setFocusPolicy(Qt.StrongFocus)
        self.main_canvas.setFocus()
        if self.settings.get("scan_on_launch", False) and not reference_preview:
            QTimer.singleShot(0, self.start_scan)

    def _create_shell(self):
        root = QWidget()
        root.setObjectName("appRoot")
        outer = row(spacing=0)
        root.setLayout(outer)
        self.setCentralWidget(root)

        rail = NavigationRail()
        r = column(spacing=0)
        rail.setLayout(r)
        brand = QWidget()
        brand.setFixedHeight(82)
        brand_row = row(spacing=6, margins=(28, 15, 13, 25))
        brand.setLayout(brand_row)
        mark = QLabel()
        mark.setPixmap(QPixmap(str(ASSETS / "gg_mark.png")))
        mark.setFixedSize(50, 41)
        mark.setAccessibleName("Game Grave GG logo")
        brand_row.addWidget(mark)
        brand_words = label("GAME GRAVE<sup>®</sup>")
        brand_words.setStyleSheet("font-family:Arial;font-size:17px;font-weight:700;color:#F0F0F2;")
        brand_row.addWidget(brand_words, 1)
        r.addWidget(brand)
        self.nav_buttons = {}
        for route, glyph in ROUTES:
            control = NavigationButton(route, glyph,
                lambda _checked=False, route=route: self.navigate(route))
            control.setProperty("active", route == self.current_route)
            control.setAccessibleName(route + " page")
            control.setFocusPolicy(Qt.StrongFocus)
            r.addWidget(control)
            self.nav_buttons[route] = control
        r.addStretch()
        outer.addWidget(rail)

        self.main_canvas = MainCanvas()
        base = column(spacing=0)
        self.main_canvas.setLayout(base)
        top = WindowHeader()
        top.setFixedHeight(52)
        topbox = row(spacing=12, margins=(22, 12, 8, 8))
        top.setLayout(topbox)
        search_box = QFrame()
        search_box.setObjectName("globalSearchBox")
        search_box.setFixedHeight(31)
        search_box.setMaximumWidth(452)
        search_box.setStyleSheet(
            "QFrame#globalSearchBox {background:rgba(5,9,12,215);border:1px solid #3B424B;border-radius:8px;}"
            "QLineEdit {background:transparent;border:none;padding:0;font-size:14px;}"
            "QLabel {background:transparent;}")
        search_row = row(spacing=12, margins=(10, 2, 6, 2))
        search_box.setLayout(search_row)
        search_row.addWidget(icon_label("search", "#E0E1E5", 18))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search games, mods, files, and more…")
        search_palette = self.search.palette()
        search_palette.setColor(QPalette.PlaceholderText, QColor("#BFC3C9"))
        self.search.setPalette(search_palette)
        self.search.setAccessibleName("Search Ready Room or installed games")
        self.search.textChanged.connect(self._search_changed)
        self.search.returnPressed.connect(self._submit_search)
        search_row.addWidget(self.search, 1)
        shortcut_hint = label("Ctrl + K")
        shortcut_hint.setStyleSheet("font-size:12px;color:#D0D3D9;background:#181E24;border-radius:4px;padding:2px 6px;")
        search_row.addWidget(shortcut_hint)
        topbox.addWidget(search_box, 1)
        if self.reference_preview:
            preview_tag = label("REFERENCE PREVIEW · SAMPLE DATA")
            preview_tag.setStyleSheet("font-size:10px;color:#AAB1BA;")
            topbox.addWidget(preview_tag)
        topbox.addStretch()
        for glyph, name, action in (
            ("bell", "Notifications", self.show_notifications),
            ("help", "Help", lambda: self.info("Ready Room", "Your local Game Grave dashboard.\n\n"
                "Ctrl+K: Search\nF5: Scan PC\nEscape: Clear search\n\n"
                "Patch feeds, compatibility and game-file verification show as unknown until supported by evidence.")),
        ):
            topbox.addWidget(self._chrome_button(glyph, name, action))
        divider = QFrame()
        divider.setFixedSize(1, 24)
        divider.setStyleSheet("background:#42484E;")
        topbox.addWidget(divider)
        for glyph, name, action in (
            ("minus", "Minimize", self.showMinimized),
            ("square", "Maximize or restore", self._toggle_maximized),
            ("close", "Close", self.close),
        ):
            topbox.addWidget(self._chrome_button(glyph, name, action))
        base.addWidget(top)

        self.operation_bar = QWidget()
        topbox = row(spacing=10, margins=(20, 4, 20, 6))
        self.operation_bar.setLayout(topbox)
        self.status = label("No scan yet. Choose Scan PC to begin.", "subtle", wrap=True)
        topbox.addWidget(self.status, 1)
        self.cancel_button = button("Cancel scan", self.cancel_scan)
        self.cancel_button.setEnabled(False)
        topbox.addWidget(self.cancel_button)
        self.scan_button = button("⌕  Scan PC", self.start_scan, kind="primary")
        topbox.addWidget(self.scan_button)
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
        base.addWidget(self.operation_bar)
        self.operation_bar.hide()
        outer.addWidget(self.main_canvas, 1)
        self.search_shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        self.search_shortcut.activated.connect(self.search.setFocus)
        self.scan_shortcut = QShortcut(QKeySequence("F5"), self)
        self.scan_shortcut.activated.connect(self.start_scan)
        self.clear_search_shortcut = QShortcut(QKeySequence("Escape"), self)
        self.clear_search_shortcut.activated.connect(self.search.clear)
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, watched, event):
        # Preserve native edge resizing with the reference's custom window chrome.
        if (event.type() == QEvent.MouseButtonPress and isinstance(watched, QWidget)
                and watched.window() is self and event.button() == Qt.LeftButton
                and not self.isMaximized() and self.windowHandle()):
            point = self.mapFromGlobal(event.globalPosition().toPoint())
            edges = Qt.Edges()
            if point.x() < 5:
                edges |= Qt.LeftEdge
            elif point.x() >= self.width() - 5:
                edges |= Qt.RightEdge
            if point.y() < 5:
                edges |= Qt.TopEdge
            elif point.y() >= self.height() - 5:
                edges |= Qt.BottomEdge
            if edges and self.windowHandle().startSystemResize(edges):
                return True
        return super().eventFilter(watched, event)

    def _chrome_button(self, glyph, name, action):
        control = button("", action, tip=name)
        control.setAccessibleName(name)
        control.setFixedSize(25, 28)
        control.setIcon(icon(glyph, "#D4D6DB", 20))
        control.setIconSize(QSize(20, 20))
        control.setStyleSheet("QPushButton {background:transparent;border:0;padding:0;}"
                             "QPushButton:hover {background:#49202A;}"
                             "QPushButton:focus {border:1px solid #4DD8E2;}")
        return control

    def _toggle_maximized(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def show_notifications(self):
        self.info("Notifications", "\n".join(self.inventory.warnings) if self.inventory.warnings
                  else "No notifications. " + ("Reference preview uses sample data." if self.reference_preview
                                               else "Scan PC to refresh your local inventory."))

    def _search_changed(self, text):
        if self.current_route == "Ready Room" and self.page is not None:
            self.page.filter_rows(text)
        elif self.current_route == "Games" and self.inventory.scanned_at:
            self.game_search.setText(text)

    def _submit_search(self):
        if self.current_route != "Ready Room":
            self.navigate("Games")
            if self.inventory.scanned_at:
                self.game_search.setText(self.search.text())

    def page_for(self, title: str, *, page=None) -> ScrollPage:
        if self.page is not None:
            self.stack_layout.removeWidget(self.page)
            self.page.hide()
            self.page.deleteLater()
        self.page = page if page is not None else ScrollPage()
        self.stack_layout.addWidget(self.page, 1)
        self.current_route = title
        self.main_canvas.ready = title == "Ready Room"
        self.main_canvas.update()
        self.operation_bar.setVisible(title != "Ready Room" or self.scanning or self.cleaning)
        for route, control in self.nav_buttons.items():
            control.setProperty("active", route == ("More Tools" if title == "Save Vault" else title))
            control.style().unpolish(control)
            control.style().polish(control)
            control.update()
        return self.page

    def navigate(self, route: str):
        route = ROUTE_ALIASES.get(route, route)
        if route not in self.nav_buttons and route != "Save Vault":
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
            "Settings": self.settings_page,
            "AI Assistant": self.assistant_page,
            "Save Vault": self.save_vault_page,
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
        self.operation_bar.show()
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
    win = CrimsonWindow(reference_preview="--ready-room-reference" in sys.argv)
    win.show()
    return app.exec()
