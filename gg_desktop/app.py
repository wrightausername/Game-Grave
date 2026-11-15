"""Crimson Command application shell: premium presentation, existing safe backend.

Run only with: python -m gg_desktop --ui-preview
The existing Tk app remains the normal launcher until human UI parity signoff.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QRunnable, QThreadPool, Signal, Qt, QTimer, QSize
from PySide6.QtGui import QIcon, QKeySequence, QShortcut, QFontDatabase
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QProgressBar, QVBoxLayout, QWidget, QScrollArea, QLineEdit,
)
from gg_desktop.settings_store import load_settings
from gg_desktop.backend import Inventory, scan_inventory, ScanCanceled
from gg_desktop.theme import STYLE
from gg_desktop.widgets import label, button, row, column, ScrollPage
from gg_desktop.reference_screens import ScreenMethods
from gg_desktop.photo_integration import PhotoIntegration
from gg_desktop.artwork import SteamArtwork
from gg_desktop.reference_widgets import Brand, NavRail, ROUTE_SYMBOLS, TitleBar, icon, tool
from gg_desktop.scan_progress import ScanProgress
from gg_desktop.ready_room import ReadyRoomMethods

from gg_desktop import nav_groups as _nav_groups

ROUTES = tuple((route, ROUTE_SYMBOLS[route]) for route in _nav_groups.routes())

ROUTE_ALIASES = {
    "Steam Games": "Games", "Other Launchers": "Games",
    "The Graveyard": "Graveyard", "Game Mods": "Mods",
    "Save Vault": "More Tools", "Resurrection Lab": "More Tools",
    "Cleanup History": "More Tools", "Automation": "More Tools",
    "Make Room": "More Tools", "Storage History": "More Tools",
    "Toolbox": "More Tools",
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
        def progress(*args):
            try:
                self.signals.progress.emit(*args)
            except RuntimeError:
                pass  # the window was closed while this job was still running
        try:
            result = self.fn(progress)
        except Exception as exc:
            try:
                self.signals.failed.emit(type(exc).__name__ + ": " + str(exc)[:300])
            except RuntimeError:
                pass
            return
        try:
            self.signals.done.emit(result)
        except RuntimeError:
            pass


class CrimsonWindow(ReadyRoomMethods, PhotoIntegration, ScreenMethods, QMainWindow):
    @property
    def cleaning(self):
        return self.__dict__.get("_cleaning", False)

    @cleaning.setter
    def cleaning(self, value):
        """Every removal sets this flag. Starting notes the Recycle Bin records; finishing offers Undo for new ones."""
        was = self.__dict__.get("_cleaning", False)
        self.__dict__["_cleaning"] = bool(value)
        if "_comfort_ready" not in self.__dict__ or bool(value) == was:
            return
        from gg_desktop import comfort
        (comfort.removal_started if value else comfort.removal_finished)(self)

    def __init__(self, *, reference_preview=False):
        super().__init__()
        self.reference_preview = reference_preview
        from gg_desktop import reference_widgets as _rw
        _rw.PHOTO_COVERS["on"] = bool(reference_preview)
        _rw.cover_icon.cache_clear()
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
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        QFontDatabase.addApplicationFont(str(Path(__file__).parent / "assets/ready_room/RobotoCondensed.ttf"))
        self.artwork = SteamArtwork(self)
        self._create_shell()
        from gg_desktop import comfort          # Back, shortcuts, notifications, paused note, tray
        comfort.install(self, self._top_box, self.bell_button)
        self._comfort_ready = True
        from gg_desktop import crashdoctor_ui   # mods a closed Crash Doctor run left aside are offered back
        QTimer.singleShot(1500, lambda: crashdoctor_ui.check_leftovers(self))
        from gg_desktop import search_popup     # results from everything under the top search box
        search_popup.install(self)
        if not reference_preview:
            from gg_desktop import scan_cache    # the last results stay until the owner scans again
            try:
                if scan_cache.restore(self):
                    self.status.setText(f"Showing results from {scan_cache.when_text(self.inventory.scanned_at) or 'the last scan'}. "
                                        "Scan again to refresh them.")
            except Exception:
                pass                              # an unreadable results file only means starting empty
        self.navigate("Ready Room" if reference_preview else "Overview")
        if self.settings.get("scan_on_launch", False) and not reference_preview:
            QTimer.singleShot(0, self.start_scan)
        if not reference_preview:
            from gg_desktop import autopilot_ui   # routines: wakes every 5 minutes, does nothing unless one is due
            autopilot_ui.install(self)
        if self.settings.get("check_updates_on_launch") is True and not reference_preview:
            def ask():
                from gg_desktop import settings_page
                settings_page.check_updates_on_launch(self)
            QTimer.singleShot(4000, ask)

    def _create_shell(self):
        root = QWidget()
        root.setObjectName("appRoot")
        outer = row(spacing=0)
        root.setLayout(outer)
        self.setCentralWidget(root)

        rail = NavRail()
        self.nav_rail = rail
        r = column(spacing=0, margins=(0, 0, 0, 10))
        rail.setLayout(r)
        self.brand = Brand()
        r.addWidget(self.brand)
        r.addSpacing(8)
        from gg_desktop import nav_rail
        self.nav_buttons = nav_rail.build(self, r)
        self._sync_assistant_nav()
        outer.addWidget(rail)

        main = QWidget()
        main.setMinimumWidth(0)
        base = column(spacing=0, margins=(0, 0, 0, 0))
        main.setLayout(base)
        top = TitleBar()
        self.top_bar = top
        top.setFixedHeight(46)
        topbox = row(spacing=7, margins=(20, 8, 7, 6))
        top.setLayout(topbox)
        self.global_search = QLineEdit()
        self.global_search.setObjectName("globalSearch")
        self.global_search.setPlaceholderText("Search games, mods, files, and more…")
        self.global_search.setAccessibleName("Search the current page")
        self.global_search.addAction(icon("search", size=18), QLineEdit.LeadingPosition)
        self.global_search.setFixedHeight(30)
        self.global_search.setMinimumWidth(160)
        self.global_search.setClearButtonEnabled(True)
        self.global_search.textChanged.connect(self._search_current_page)
        self.search_shell = QFrame()
        self.search_shell.setObjectName("searchShell")
        self.search_shell.setMaximumWidth(550)
        searchbox = row(spacing=3, margins=(2, 0, 6, 0))
        self.search_shell.setLayout(searchbox)
        searchbox.addWidget(self.global_search, 1)
        shortcut_hint = label("Ctrl + K", "searchKey")
        shortcut_hint.setFixedHeight(17)
        searchbox.addWidget(shortcut_hint)
        topbox.addWidget(self.search_shell, 1)
        topbox.addStretch(0)
        self.scan_time = label("", "caption")
        self.scan_time.setObjectName("scanTime")
        self.scan_time.setStyleSheet("QLabel#scanTime{color:#9fb0c2;font-size:12px;padding:0 6px;}")
        self.scan_time.setToolTip("When the results on this page were scanned. They stay until you scan again.")
        self.scan_time.setAccessibleName("Scan time")
        topbox.addWidget(self.scan_time)
        self.status = label("No scan yet. Scan PC (F5) to begin.", "caption", wrap=True)
        self.status.setMaximumWidth(195)
        self.status.setMaximumHeight(44)
        self.status.hide()
        r.addWidget(self.status)
        self.cancel_button = button("Cancel scan", self.cancel_scan)
        self.cancel_button.setEnabled(False)
        self.cancel_button.hide()
        topbox.addWidget(self.cancel_button)
        self.scan_button = tool("Scan PC", "search", self.start_scan, kind="primary", tip="Scan PC (F5)")
        self.scan_button.setAccessibleName("Scan PC")
        self.scan_button.setFixedSize(105, 30)
        self.scan_button.setToolTip("Scan PC (F5). Right-click for a quicker scan of one part.")
        self.scan_button.setContextMenuPolicy(Qt.CustomContextMenu)
        self.scan_button.customContextMenuRequested.connect(self._scan_menu)
        topbox.addWidget(self.scan_button)
        self.scan_button.hide()
        from gg_desktop import comfort
        self.bell_button = tool("", "bell", lambda: comfort.open_notices(self), kind="chromeButton",
                                tip="Notifications and scan status (Ctrl+Shift+N)")
        topbox.addWidget(self.bell_button)
        self._top_box = topbox
        from gg_desktop import assistant_popout
        self.assistant_popout_button = tool("", "sparkles", lambda: assistant_popout.toggle(self), kind="chromeButton",
                                            tip="Pop out the AI Assistant so it stays beside any tab (Ctrl+Shift+A)")
        self.assistant_popout_button.setAccessibleName("Pop out the AI Assistant")
        topbox.addWidget(self.assistant_popout_button)
        QShortcut(QKeySequence("Ctrl+Shift+A"), self, activated=lambda: assistant_popout.toggle(self))
        help_button = tool("", "help", lambda: self.open_welcome_tour(), kind="chromeButton",
                           tip="Help: watch the welcome tour of Game Grave")
        help_button.setAccessibleName("Help: watch the welcome tour")
        topbox.addWidget(help_button)
        for symbol, action, tip in (("minus", self.showMinimized, "Minimize"),
                                    ("maximize", self._toggle_maximize, "Maximize or restore"),
                                    ("close", self.close, "Close")):
            control = tool("", symbol, action, kind="chromeButton", tip=tip)
            control.setAccessibleName(tip)
            control.setFixedWidth(28)
            topbox.addWidget(control)
        base.addWidget(top)
        # The scan bar sits along the bottom of the main area (never between the top bar and the page), so it is
        # always visible during a scan without splitting the banner artwork or moving anything at the top.
        self.progress = ScanProgress(main)
        self.progress.cancel_requested.connect(self.cancel_scan)
        self._last_scan_seconds = None
        self.stack_holder = QWidget()
        self.stack_layout = column(spacing=0)
        self.stack_holder.setLayout(self.stack_layout)
        self.page = None
        base.addWidget(self.stack_holder, 1)
        base.addWidget(self.progress)
        outer.addWidget(main, 1)
        QShortcut(QKeySequence("Ctrl+K"), self, activated=self.global_search.setFocus)
        QShortcut(QKeySequence("F5"), self, activated=self._scan_current_route)
        QShortcut(QKeySequence("Escape"), self, activated=self._escape_current_route)



    def open_welcome_tour(self):
        from gg_desktop import welcome_ui
        return welcome_ui.open_tour(self)

    def _welcome_setting_changed(self):
        """The tour changed the startup choice; a Settings page on screen shows it straight away."""
        if self.current_route == "Settings":
            from gg_desktop import settings_page
            settings_page.state_of(self).pending = None
            self.navigate("Settings")

    def _toggle_maximize(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def _sync_shell_layout(self):
        if not hasattr(self, "nav_rail"):
            return
        wide_overview = False
        self.nav_rail.setFixedWidth(296 if wide_overview else 219)
        self.top_bar.setFixedHeight(56 if wide_overview else 46)
        self.brand.setFixedHeight(80 if wide_overview else 65)

    def _search_current_page(self, text):
        attr = {"Games": "game_search", "Mods": "mod_search", "Old Files": "old_search",
                "Other Storage": "storage_search", "Captures": "capture_search", "Graveyard": "grave_search",
                "Game DNA": "dna_search", "Undo Center": "undo_search"}.get(self.current_route)
        control = getattr(self, attr, None) if attr else None
        if control is not None:
            control.setText(text)

    def mousePressEvent(self, event):
        # Preserve edge resizing with the reference's borderless window chrome.
        if event.button() == Qt.LeftButton and not self.isMaximized():
            edges = Qt.Edges()
            pos = event.position()
            if pos.x() < 6:
                edges |= Qt.LeftEdge
            elif pos.x() > self.width() - 6:
                edges |= Qt.RightEdge
            if pos.y() < 6:
                edges |= Qt.TopEdge
            elif pos.y() > self.height() - 6:
                edges |= Qt.BottomEdge
            if edges and self.windowHandle():
                self.windowHandle().startSystemResize(edges)
                return
        super().mousePressEvent(event)

    def page_for(self, title: str, *, page=None) -> ScrollPage:
        self.artwork.set_library(self.inventory.games, [g.library for g in self.inventory.steam])
        if self.page is not None:
            if self.current_route == "Ready Room":
                self.page.release_ready_shell()
            self.stack_layout.removeWidget(self.page)
            self.page.deleteLater()
        self.page = page if page is not None else ScrollPage()
        self.stack_layout.addWidget(self.page, 1)
        self.current_route = title
        self._sync_shell_layout()
        self.global_search.blockSignals(True)
        self.global_search.clear()
        self.global_search.blockSignals(False)
        self.search_shell.setMaximumWidth({"Games":452, "Ready Room":452, "Old Files":475}.get(title, 550))
        for route, control in self.nav_buttons.items():
            control.set_active(route == title)
        from gg_desktop import nav_rail
        nav_rail.follow(self, title)
        return self.page

    def assistant_enabled(self) -> bool:
        """The AI Assistant tab is optional and off until the owner turns it on in Settings."""
        return self.settings.get("assistant_enabled") is True

    def _sync_assistant_nav(self):
        control = self.nav_buttons.get("AI Assistant")
        if control is not None:
            control.setVisible(self.assistant_enabled())
        if hasattr(self, "assistant_popout_button"):
            self.assistant_popout_button.setVisible(self.assistant_enabled())
            pop = getattr(self, "_assistant_popout", None)
            if pop is not None and not self.assistant_enabled():
                pop.close()
        from gg_desktop import nav_rail
        nav_rail.sync_groups(self)

    def navigate(self, route: str):
        route = ROUTE_ALIASES.get(route, route)
        if route not in self.nav_buttons:
            route = "More Tools"
        if route == "AI Assistant" and not self.assistant_enabled():
            route = "Settings"
            self.status.setText("The AI Assistant is off. Turn it on in Settings to use it.")
        methods = {
            "Overview": self.overview_page,
            "Ready Room": self.ready_room_page,
            "Games": self.games_page,
            "Mods": self.mods_page,
            "Other Storage": self.other_storage_page,
            "Captures": self.captures_page,
            "AI Assistant": self.assistant_page,
            "Old Files": self.old_files_page,
            "Graveyard": self.graveyard_page,
            "Game DNA": self.dna_page,
            "Hardware": self.hardware_page,
            "Undo Center": self.undo_page,
            "Settings": self.settings_page,
            "More Tools": self.tools_page,
            "Fix Kit": self.fix_kit_page,
        }
        methods[route]()
        self._name_controls()
        self._sync_scan_time()
        from gg_desktop import comfort
        comfort.visited(self, route)
        comfort.remember_views(self, route)
        QTimer.singleShot(400, lambda r=route: self.current_route == r and comfort.remember_views(self, r))
        from gg_desktop import assistant_popout
        pop = assistant_popout.current(self)
        if pop is not None:
            pop.follow(route)
        QTimer.singleShot(400, self._name_controls)   # tables and panels that fill in a moment later

    def _name_controls(self):
        """Screen-reader names for any control a page left unnamed. Invisible to sighted users."""
        try:
            from gg_desktop import a11y
            a11y.name_controls(self)
        except RuntimeError:
            pass  # the page was replaced while this ran

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
            self._sync_scan_controls()
        job.signals.done.connect(finish)
        job.signals.failed.connect(fail)
        if progress:
            job.signals.progress.connect(progress)
        self.pool.start(job)

    def _sync_scan_time(self):
        if not hasattr(self, "scan_time"):
            return
        from gg_desktop import scan_cache
        if self.reference_preview:
            self.scan_time.setText("")
            return
        quick = None
        parts = tuple(getattr(self.inventory, "quick_parts", ()) or ())
        if parts:
            from gg_desktop import scan_parts
            quick = (scan_parts.describe(parts), getattr(self.inventory, "full_scanned_at", ""))
        self.scan_time.setText(scan_cache.label_for(self.current_route, self.inventory.scanned_at,
                                                    scan_cache.times_of(self), quick=quick))

    def _scan_menu(self, pos=None):
        from PySide6.QtWidgets import QMenu
        from gg_desktop import scan_parts
        menu = QMenu(self.scan_button)
        for caption, parts in scan_parts.MENU:
            action = menu.addAction(caption, lambda p=parts: self.start_scan(p))
            action.setEnabled(not self.scanning and (parts is None or bool(self.inventory.scanned_at)))
        self.scan_menu = menu
        menu.popup(self.scan_button.mapToGlobal(pos if pos is not None else self.scan_button.rect().bottomLeft()))
        return menu

    def start_scan(self, parts=None):
        """Scan PC. `parts` (games, mods, files, captures, saves) rescans only those and keeps the rest of the last scan."""
        if self.scanning or self.cleaning:
            return
        if not isinstance(parts, (set, frozenset, tuple, list)) or not self.inventory.scanned_at:
            parts = None                     # a button's checked flag, or no earlier scan to keep from
        base = self.inventory if parts else None
        self.scanning = True
        self.cancel.clear()
        self.scan_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.begin(self._last_scan_seconds)
        self.status.setText("Scanning local gaming records. No files are being changed.")
        self._sync_scan_controls()
        settings = dict(self.settings)
        rules = tuple(settings.get("never_touch", []))
        settings["never_touch"] = list(rules)

        def progress(percent, stage):
            self.progress.report(percent, stage)
            self.status.setText("Scanning: " + stage + " (" + str(percent) + "%)")
            self._sync_scan_controls()
        def finish(inventory):
            self.scanning = False
            self.scan_button.setEnabled(True)
            self.cancel_button.setEnabled(False)
            seconds = self.progress.finish()
            self._sync_scan_controls()
            if self.cancel.is_set():
                self.status.setText("Scan canceled. The earlier inventory was not replaced.")
                return
            self._last_scan_seconds = seconds
            self.inventory = inventory
            from gg_desktop import scan_cache
            scan_cache.keep_async("inventory", inventory)
            self._sync_scan_time()
            from gg_desktop import comfort
            comfort.notify(self, "Quick scan finished" if parts else "Scan finished", f"{len(inventory.games)} games, {len(inventory.mods)} mod locations, "
                           f"{len(inventory.graveyard)} Graveyard findings." + (" Some sources weren't available."
                                                                               if inventory.warnings else ""),
                           "warn" if inventory.warnings else "good", "Overview")
            self.status.setText(
                f"Scanned {inventory.scanned_at}  •  {len(inventory.games)} game installs, "
                f"{len(inventory.mods)} mod locations, {len(inventory.graveyard)} Graveyard findings."
                + ("  •  Some sources unavailable." if inventory.warnings else ""))
            self.navigate(self.current_route)
            from gg_desktop import first_scan
            first_scan.after_scan(self, quick=bool(parts))   # once, after the first full scan
            from gg_desktop import space_ui
            space_ui.notify_if_low(self)                     # at most once a day, only when a game drive is low
            from gg_desktop import soulbind_auto
            soulbind_auto.after_scan(self)      # only acts when the owner switched it on in Settings
        if parts:
            from gg_desktop import scan_parts
            self.status.setText("Quick scan: " + scan_parts.describe(parts) + ". The rest of the last scan is kept.")
        self.job(lambda emitter: (scan_inventory(settings, self.cancel.is_set, emitter, parts=parts, base=base) if parts
                                  else scan_inventory(settings, self.cancel.is_set, emitter)),
                 finish, error_title="Local scan incomplete", progress=progress)

    def cancel_scan(self):
        if self.scanning:
            self.cancel.set()
            self.progress.stopping()
            self.status.setText("Stopping the read-only scan…")
            self._sync_scan_controls()

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
        from gg_desktop import comfort
        if comfort.close_to_tray(self, event):   # "Keep running when closed": hide in the tray instead
            return
        if self.scanning or self.cleaning:
            self.error("Game Grave is busy",
                       "Cancel the scan or finish the approved recovery operation before closing.")
            event.ignore()
            return
        try:  # the optional local AI model never outlives the app
            from gg_desktop import local_ai_ui
            local_ai_ui.shutdown(self)
        except Exception:
            pass
        super().closeEvent(event)


def apply_interface_scale(environ=None, loader=None):
    """Before Qt starts: use the interface size saved in Settings. Never overrides a scale the user set for Qt themselves."""
    import os
    env = os.environ if environ is None else environ
    if env.get("QT_SCALE_FACTOR"):
        return None
    try:
        from gg_desktop import settings_data
        factor = settings_data.scale_factor((loader or load_settings)())
    except Exception:
        return None
    if factor:
        env["QT_SCALE_FACTOR"] = factor
    return factor


def main() -> int:
    if QApplication.instance() is None:
        apply_interface_scale()
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Game Grave")
    app.setOrganizationName("Game Grave")
    app.setStyleSheet(STYLE)
    app.setQuitOnLastWindowClosed(True)
    win = CrimsonWindow(reference_preview="--ready-room-reference" in sys.argv)
    hidden = "--minimized" in sys.argv or win.settings.get("start_minimized") is True
    if hidden and not win.reference_preview:
        from gg_desktop import comfort
        if comfort.state_of(win).tray is None:
            win.showMinimized()                   # no tray: start minimized on the taskbar
    else:
        win.show()
        from gg_desktop import welcome_ui      # first launch only: what Game Grave is, then the first scan
        QTimer.singleShot(350, lambda: welcome_ui.show_if_needed(win))
    return app.exec()
