"""Game Grave cinematic application shell: approved design, safe real backend.

Run only with: python -m gg_desktop --ui-preview
The existing Tk app remains the normal launcher until human UI parity signoff.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Qt, QTimer, QSize
from PySide6.QtGui import QColor, QIcon, QPalette, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QProgressBar, QVBoxLayout, QWidget, QScrollArea, QLineEdit,
    QDialog, QTableWidget, QTableWidgetItem, QAbstractItemView,
)
from core import load_settings
from gg_desktop.backend import Inventory, scan_inventory, ScanCanceled
from gg_desktop.theme import STYLE
from gg_desktop.widgets import label, button, row, column, ScrollPage, LandscapeArt
from gg_desktop.visuals import nav_icon
from gg_desktop.screens import ScreenMethods

ROUTES = (
    ("Overview", "⌂"),
    ("Ready Room", "◉"),
    ("Games", "▣"),
    ("Mods", "♜"),
    ("Old Files", "▤"),
    ("Other Storage", "◉"),
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
    "Game Screenshots": "Captures", "In-game Screenshots": "Captures",
    "Screenshots": "Captures", "Videos": "Captures",
    "Recordings": "Captures", "Game Recordings": "Captures",
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


def configure_crimson_dialog_palette(app: QApplication) -> None:
    """Provide readable dark native/Qt prompts when Windows uses light mode.

    Style sheets cover Qt widget dialogs, while this palette covers child
    widgets or system styles that otherwise inherit an unusable white-on-white
    combination for Yes/No, file and typed override prompts.
    """
    app.setStyle("Fusion")
    palette = QPalette(app.palette())
    for role, hex_color in (
        (QPalette.Window, "#111B27"),
        (QPalette.WindowText, "#F5FAFF"),
        (QPalette.Base, "#0D1722"),
        (QPalette.AlternateBase, "#1D2C3A"),
        (QPalette.Text, "#F5FAFF"),
        (QPalette.Button, "#243446"),
        (QPalette.ButtonText, "#F5FAFF"),
        (QPalette.Highlight, "#345E74"),
        (QPalette.HighlightedText, "#FFFFFF"),
        (QPalette.ToolTipBase, "#111B27"),
        (QPalette.ToolTipText, "#F5FAFF"),
        (QPalette.PlaceholderText, "#ACBDCE"),
    ):
        palette.setColor(role, QColor(hex_color))
    app.setPalette(palette)


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
        self._ai_companion = None
        self.setWindowTitle("Game Grave  |  Cinematic UI preview")
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
        rail.setFixedWidth(252)
        r = column(spacing=5, margins=(10, 20, 10, 12))
        rail.setLayout(r)
        brand_holder = QWidget()
        brand_layout = row(spacing=9)
        brand_holder.setLayout(brand_layout)
        glyph = QLabel()
        glyph.setPixmap(QIcon(str(Path(__file__).parent / "assets" / "app_icon.svg"))
                        .pixmap(64, 56))
        glyph.setFixedSize(64, 56)
        glyph.setAccessibleName("Game Grave red GG monogram")
        brand_layout.addWidget(glyph)
        name = label("GAME GRAVE", "brand")
        name.setStyleSheet("color:#F5F7FB;font-size:17px;font-weight:900;")
        brand_layout.addWidget(name, 1)
        r.addWidget(brand_holder)
        r.addSpacing(12)
        rail_scroll = QScrollArea()
        rail_scroll.setObjectName("navScroll")
        rail_scroll.setFrameShape(QFrame.NoFrame)
        rail_scroll.setWidgetResizable(True)
        rail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        nav_body = QWidget()
        nav_body.setObjectName("navBody")
        nav_stack = column(spacing=4)
        nav_body.setLayout(nav_stack)
        self.nav_buttons = {}
        for route, _legacy_icon in ROUTES:
            control = button(route,
                             lambda _checked=False, route=route: self.navigate(route),
                             kind="navButton")
            control.setIcon(nav_icon(route))
            control.setIconSize(QSize(20, 20))
            control.setProperty("active", route == self.current_route)
            control.setAccessibleName(route + " page")
            control.setFocusPolicy(Qt.StrongFocus)
            nav_stack.addWidget(control)
            self.nav_buttons[route] = control
        nav_stack.addStretch()
        rail_scroll.setWidget(nav_body)
        r.addWidget(rail_scroll, 1)
        # Decorative local artwork remains separate from scan findings and
        # disappears on shorter screens so every navigation control stays usable.
        self.sidebar_art = LandscapeArt(224, scene="footer")
        footer_layout = column(margins=(14, 22, 12, 4))
        self.sidebar_art.setLayout(footer_layout)
        footer_layout.addWidget(label(
            "KEEP THE GAMES.\\nLOSE THE CLUTTER.", "caption", wrap=True))
        footer_layout.addStretch()
        self.sidebar_art.setVisible(self.height() >= 795)
        r.addWidget(self.sidebar_art)
        outer.addWidget(rail)

        main = QWidget()
        base = column(spacing=6, margins=(0, 0, 0, 0))
        main.setLayout(base)
        top = QWidget()
        topbox = row(spacing=8, margins=(18, 5, 18, 4))
        top.setLayout(topbox)
        self.global_search = QLineEdit()
        self.global_search.setObjectName("globalSearch")
        self.global_search.setAccessibleName("Search scanned games, mods and paths")
        self.global_search.setPlaceholderText(
            "⌕  Search games, mods, files, and more…           Ctrl + K")
        self.global_search.returnPressed.connect(self.open_global_search)
        topbox.addWidget(self.global_search, 1)
        # The approved Nov 2 shell has quiet notification/help controls, not
        # a persistent SCAN PC toolbar on every route. Scanning remains in
        # Overview, Graveyard and other explicit user-invoked workflows.
        self.cancel_button = button("Cancel scan", self.cancel_scan)
        self.cancel_button.setAccessibleName("Cancel active scan")
        self.cancel_button.setEnabled(False)
        self.cancel_button.hide()
        topbox.addWidget(self.cancel_button)
        self.scan_button = button("Scan PC", self.start_scan, kind="primary")
        self.scan_button.setAccessibleName("Scan PC from a page action")
        self.scan_button.hide()
        topbox.addWidget(self.scan_button)
        self.notification_button = button("", self._show_notifications, kind="chromeButton")
        self.notification_button.setIcon(nav_icon("Notifications"))
        self.notification_button.setIconSize(QSize(20, 20))
        self.notification_button.setToolTip("Notifications and scan status")
        self.notification_button.setAccessibleName("Notifications and scan status")
        topbox.addWidget(self.notification_button)
        self.help_button = button("?", self._show_help, kind="chromeButton")
        self.help_button.setToolTip("Help and safety information")
        self.help_button.setAccessibleName("Help")
        topbox.addWidget(self.help_button)
        base.addWidget(top)
        self.status = label(
            "Not scanned. Scan PC reads local records; no files are changed.",
            "caption", wrap=True)
        self.status.setObjectName("scanStatus")
        self.status.hide()
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

    def _show_notifications(self):
        """Show actual local status; do not fabricate notifications."""
        if self.scanning:
            message = self.status.text()
        elif self.inventory.scanned_at:
            message = "Last scan: " + str(self.inventory.scanned_at)
        else:
            message = "No scan has run yet. Open Overview to scan your PC."
        warnings = list(getattr(self.inventory, "warnings", []) or [])
        if warnings:
            message += "\n\nScan coverage warnings:\n" + "\n".join(
                str(w) for w in warnings[:8])
        self.info("Game Grave status", message)

    def _show_help(self):
        """Help is an actual action, not an inert decoration."""
        self.info(
            "Game Grave help",
            "Ctrl+K searches your scanned local inventory.\n\n"
            "Start a read-only scan from Overview or the relevant tool. "
            "Graveyard deletion requires explicit review and confirmation; "
            "protected saves and Windows locations remain blocked. "
            "Undo Center can restore only files still verified as recoverable.\n\n"
            "The optional local AI is off by default in Settings.")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "sidebar_art"):
            self.sidebar_art.setVisible(event.size().height() >= 795)

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

    def open_ai_companion(self):
        """Non-modal local assistant: persists when navigating any other tab."""
        from gg_desktop.ai_companion import open_companion
        open_companion(self)

    def navigate(self, route: str):
        # Assistant has a dedicated approved page; the optional dock remains available.
        # Legacy links to the recording viewer open Captures on its Video tab.
        self._show_capture_videos = route in ("Videos", "Recordings", "Game Recordings")
        route = ROUTE_ALIASES.get(route, route)
        if route not in self.nav_buttons:
            route = "More Tools"
        # The owner's locked Overview and Graveyard have dedicated Qt views.
        # Both preserve the existing scan and reversible cleanup backends.
        if route == "Overview":
            from gg_desktop.approved_overview import render_approved_overview
            render_approved_overview(self)
            return
        if route == "Graveyard":
            from gg_desktop.approved_graveyard import render_approved_graveyard
            render_approved_graveyard(self)
            return
        if route == "Undo Center":
            from gg_desktop.approved_undo import render_approved_undo
            render_approved_undo(self)
            return
        if route == "Game DNA":
            from gg_desktop.approved_dna import render_approved_dna
            render_approved_dna(self)
            return
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
                self.cancel_button.hide()
                self.progress.hide()
            if self.cleaning:
                self.cleaning = False
        job.signals.done.connect(finish)
        job.signals.failed.connect(fail)
        if progress:
            job.signals.progress.connect(progress)
        self.pool.start(job)

    def open_global_search(self):
        """Find real scanned items; never invent search hits or edit any file."""
        query = self.global_search.text().strip().casefold()
        if not query:
            return
        if not self.inventory.scanned_at:
            self.info("Scan first", "Run Scan PC to discover local content.")
            return
        records = []
        for game in self.inventory.games:
            records.append(("Games", game.name, game.install_path))
        for entry in self.inventory.graveyard:
            records.append(("Graveyard", entry.name, entry.path))
        for mod in self.inventory.mods:
            records.append(("Mods", str(getattr(mod, "source", "Mods")),
                            str(getattr(mod, "path", ""))))
        for entry in (*self.inventory.screenshots, *self.inventory.recordings):
            p = str(getattr(entry, "path", ""))
            records.append(("Captures", Path(p).name, p))
        for entry in self.inventory.files:
            p = str(getattr(entry, "path", ""))
            records.append(("Old Files", Path(p).name, p))
        for entry in self.inventory.saves:
            p = str(getattr(entry, "path", ""))
            records.append(("Other Storage", Path(p).name, p))
        matching = [x for x in records if query in (" ".join(x)).casefold()][:250]
        if not matching:
            self.info("No matching scanned items", "No hits in the latest inventory.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Game Grave — Local Search")
        dialog.resize(950, 510)
        body = column(spacing=10, margins=(15, 15, 15, 15))
        dialog.setLayout(body)
        body.addWidget(label(f"{len(matching)} results (up to 250). Select one to open its tab.",
                             "subtle", wrap=True))
        table = QTableWidget(len(matching), 3)
        table.setHorizontalHeaderLabels(["SOURCE", "ITEM", "PATH"])
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.setColumnWidth(0, 130)
        table.setColumnWidth(1, 260)
        table.horizontalHeader().setStretchLastSection(True)
        for i, rowdata in enumerate(matching):
            for j, value in enumerate(rowdata):
                table.setItem(i, j, QTableWidgetItem(str(value)))
        body.addWidget(table, 1)
        controls = QWidget()
        buttons = row()
        controls.setLayout(buttons)
        buttons.addStretch()
        buttons.addWidget(button("Close", dialog.reject))
        buttons.addWidget(button("Open selected", dialog.accept, kind="primary"))
        body.addWidget(controls)
        table.cellDoubleClicked.connect(lambda _r, _c: dialog.accept())
        if dialog.exec() != QDialog.Accepted:
            return
        selected = table.selectionModel().selectedRows()
        if not selected:
            return
        source, name, path = matching[selected[0].row()]
        if source == "Games":
            self._pending_game_query = name
        elif source == "Graveyard":
            self._pending_grave_query = path
        self.navigate(source)

    def start_scan(self):
        if self.scanning or self.cleaning:
            return
        self.scanning = True
        self.cancel.clear()
        self.cancel_button.show()
        self.scan_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.show()
        self.progress.setValue(0)
        self.status.setText("Scanning local gaming records. No files are being changed.")
        self.status.show()
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
            self.cancel_button.hide()
            self.progress.setValue(100)
            self.progress.hide()
            if self.cancel.is_set():
                self.status.setText("Scan canceled. The earlier inventory was not replaced.")
                return
            self.inventory = inventory
            # Disk contributions must be re-analyzed after a new scan changes
            # installed-game ownership; never show a stale Other breakdown.
            self._other_storage_report = None
            self._other_storage_report_drive = None
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
    configure_crimson_dialog_palette(app)
    app.setStyleSheet(STYLE)
    app.setQuitOnLastWindowClosed(True)
    win = CrimsonWindow()
    win.show()
    return app.exec()
