"""Hardware tab, third inner tab: Drivers & Startup. Thin Qt layer; every rule lives in upkeep_core.

Nothing here runs on its own: each read happens when the tab is first opened or a button is pressed, and every change
asks first. Driver installs and all-users startup apps go through the Windows administrator prompt.
"""
from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QCheckBox, QFrame, QScrollArea, QWidget

from core import human_size, log_event
from gg_desktop import upkeep_core as up
from gg_desktop.widgets import button, column, label, panel, row

SOURCE_WORDS = {"Run": "Starts from the registry", "Run32": "Starts from the registry (32-bit)",
                "StartupFolder": "Starts from the Startup folder"}


def _scroll(inner_layout, minimum=220):
    holder = QWidget()
    holder.setObjectName("upkeepList")
    holder.setLayout(inner_layout)
    holder.setStyleSheet("#upkeepList{background:transparent;}")
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setMinimumHeight(minimum)
    area.setStyleSheet("QScrollArea{background:transparent;border:none;}")
    area.viewport().setStyleSheet("background:transparent;")
    area.setWidget(holder)
    return area


def _clear(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().hide()
            item.widget().deleteLater()
        elif item.layout():
            _clear(item.layout())


class UpkeepTab(QWidget):
    def __init__(self, window, gpu_names=()):
        super().__init__()
        self.window_owner = window
        self.gpu_names = tuple(gpu_names)
        self.updates, self.update_checks = [], {}
        self.last_install = ""
        self.apps, self.loaded = [], False
        outer = row(spacing=10)
        self.setLayout(outer)

        # ---------------------------------------------------------- drivers
        self.drivers_panel, drivers = panel(kind="libraryPanel", padding=12, spacing=8)
        head = row(spacing=8)
        head.addWidget(label("Drivers", "sectionTitle"), 1)
        self.check_button = button("Check for driver updates", self.check_updates, kind="primary",
                                   tip="Asks Windows Update which driver updates it offers this PC (the same list as "
                                       "Settings, Windows Update, Optional updates). Changes nothing. Can take a few minutes.")
        head.addWidget(self.check_button)
        drivers.addLayout(head)
        drivers.addWidget(label("Updates come from Windows Update only. Installing asks for administrator permission, "
                                "and Windows may need a restart afterwards.", "readyDetail", wrap=True))
        self.driver_status = label("Press Check for driver updates to ask Windows Update.", "readyDetail", wrap=True)
        drivers.addWidget(self.driver_status)
        self.update_box = column(spacing=4)
        drivers.addWidget(_scroll(self.update_box, 140), 1)
        act = row(spacing=10)
        self.install_button = button("Update all", self.install_selected, kind="primary",
                                     tip="Downloads and installs the ticked driver updates through Windows Update.")
        self.install_button.hide()
        act.addWidget(self.install_button)
        self.maker_button = button("", self.open_maker, kind="actionLink")
        self.maker_button.hide()
        act.addWidget(self.maker_button)
        act.addStretch()
        drivers.addLayout(act)
        drivers.addWidget(label("Oldest drivers on this PC", "readyGameTitle"))
        drivers.addWidget(label("An old date is only a hint: many devices never get a newer driver.", "caption", wrap=True))
        self.old_box = column(spacing=3)
        drivers.addLayout(self.old_box)
        self.maker = None
        self.set_gpus(self.gpu_names)
        outer.addWidget(self.drivers_panel, 1)

        # ---------------------------------------------------------- startup
        self.startup_panel, startup = panel(kind="libraryPanel", padding=12, spacing=8)
        head = row(spacing=8)
        head.addWidget(label("Starts with Windows", "sectionTitle"), 1)
        self.refresh_button = button("Refresh", self.load_startup, kind="actionLink",
                                     tip="Reads the list again. Changes nothing.")
        head.addWidget(self.refresh_button)
        startup.addLayout(head)
        startup.addWidget(label("Turn off what you don't need at startup. This is the same switch as Task Manager's "
                                "Startup apps: the app stays installed, and you can turn it back on here or there.",
                                "readyDetail", wrap=True))
        self.startup_status = label("", "readyDetail", wrap=True)
        startup.addWidget(self.startup_status)
        self.app_box = column(spacing=2)
        startup.addWidget(_scroll(self.app_box, 300), 1)
        startup.addWidget(label("Apps started by scheduled tasks, services or the Microsoft Store are not listed here.",
                                "caption", wrap=True))
        outer.addWidget(self.startup_panel, 1)

    def set_gpus(self, names):
        self.gpu_names = tuple(names)
        self.maker = up.maker_page(self.gpu_names)
        if self.maker:
            self.maker_button.setText(f"Graphics: get {self.maker[0]}")
            self.maker_button.setToolTip("Graphics card makers often publish newer drivers than Windows Update. "
                                         "Opens the maker's official page in your browser.")
        self.maker_button.setVisible(bool(self.maker))

    # ============================================================== first open
    def showEvent(self, event):
        super().showEvent(event)
        if not self.loaded:
            self.loaded = True
            self.load_startup()
            self.load_installed()

    # ============================================================== drivers
    def load_installed(self):
        def done(result):
            installed, problem = result
            _clear(self.old_box)
            if problem:
                self.old_box.addWidget(label(problem, "caption", wrap=True))
                return
            aged = up.old_drivers(installed)
            if not aged:
                self.old_box.addWidget(label(f"{len(installed)} drivers read. None in the game-related groups is older "
                                             f"than {up.OLD_YEARS} years.", "caption", wrap=True))
            for years, driver in aged:
                line = row(spacing=8)
                line.addWidget(label(driver.device, "readyDetail"), 1)
                line.addWidget(label(f"{driver.date[:4]} · {years:.0f} years", "caption"))
                self.old_box.addLayout(line)

        def work(_progress):
            try:
                return up.read_installed(), ""
            except up.UpkeepError as problem:
                return [], str(problem)
        self.window_owner.job(work, done, error_title="Drivers could not be read")

    def check_updates(self):
        self.check_button.setEnabled(False)
        self.driver_status.setText("Asking Windows Update. This can take a few minutes…")
        _clear(self.update_box)
        self.install_button.hide()

        def work(_progress):
            try:
                return up.search_updates(), ""
            except up.UpkeepError as problem:
                return [], str(problem)

        def done(result):
            self.check_button.setEnabled(True)
            self.updates, problem = result
            if problem:
                self.driver_status.setText("Windows Update did not answer: " + problem)
                return
            self.show_updates()
        self.window_owner.job(work, done, error_title="Driver check did not finish")

    def show_updates(self):
        _clear(self.update_box)
        self.update_checks = {}
        before = (self.last_install + " ") if self.last_install else ""
        self.last_install = ""
        if not self.updates:
            self.driver_status.setText(before + "Windows Update has no other driver updates for this PC right now."
                                       + (" Graphics drivers can still be newer at the maker's site." if self.maker else ""))
            self.install_button.hide()
            return
        total = sum(u.size for u in self.updates)
        self.driver_status.setText(before + f"Windows Update offers {len(self.updates)} driver update{'s' if len(self.updates) != 1 else ''}"
                                   + (f", about {human_size(total)} to download." if total else "."))
        for update in self.updates:
            box = QCheckBox(update.title)
            box.setChecked(True)
            box.setAccessibleName(update.title)
            box.setToolTip(" · ".join(p for p in (update.device_class, update.maker, update.model,
                                                  ("dated " + update.date) if update.date else "",
                                                  human_size(update.size) if update.size else "") if p))
            box.setStyleSheet("QCheckBox{color:#F4F7FC;font-size:12px;}")
            box.toggled.connect(self.sync_install)
            self.update_checks[update.update_id] = box
            self.update_box.addWidget(box)
        self.update_box.addStretch(1)
        self.install_button.show()
        self.sync_install()

    def chosen(self):
        return [u for u in self.updates if self.update_checks.get(u.update_id) and self.update_checks[u.update_id].isChecked()]

    def sync_install(self, *_):
        chosen = self.chosen()
        self.install_button.setEnabled(bool(chosen))
        self.install_button.setText("Update all" if len(chosen) == len(self.updates) else f"Update {len(chosen)} selected")

    def install_selected(self):
        chosen = self.chosen()
        window = self.window_owner
        if not chosen or getattr(window, "cleaning", False):
            return
        names = "\n".join("• " + u.title for u in chosen[:12]) + ("\n…" if len(chosen) > 12 else "")
        if not window.confirm("Install driver updates?",
                              f"Windows Update will download and install:\n{names}\n\nWindows will ask for administrator "
                              "permission first. Save your work: a driver update can blank the screen for a moment, and "
                              "Windows may ask for a restart. Close any game that is running."):
            return
        self.install_button.setEnabled(False)
        self.check_button.setEnabled(False)
        window.cleaning = True
        self.driver_status.setText("Installing through Windows Update. Allow the Windows prompt; this can take a while…")

        def work(_progress):
            try:
                return up.install_updates(chosen)
            except up.UpkeepError as problem:
                return False, str(problem), False

        def done(result):
            window.cleaning = False
            self.check_button.setEnabled(True)
            ok, words, reboot = result
            self.driver_status.setText(words)
            log_event("driver_update", f"Driver updates through Windows Update: {words}",
                      result="installed" if ok else "not installed", source="hardware")
            if ok:
                self.last_install = words
                self.check_updates()           # read the list again so installed ones drop off
            else:
                self.sync_install()
        window.job(work, done, error_title="Driver install did not finish")

    def open_maker(self):
        if self.maker:
            QDesktopServices.openUrl(QUrl(self.maker[1]))

    # ============================================================== startup
    def load_startup(self):
        self.refresh_button.setEnabled(False)
        self.startup_status.setText("Reading what starts with Windows…")

        def work(_progress):
            try:
                return up.read_startup(), ""
            except up.UpkeepError as problem:
                return [], str(problem)

        def done(result):
            self.refresh_button.setEnabled(True)
            self.apps, problem = result
            if problem:
                self.startup_status.setText("Could not read the startup list: " + problem)
                return
            self.show_apps()
        self.window_owner.job(work, done, error_title="Startup list could not be read")

    def show_apps(self):
        from gg_desktop.settings_page import Switch
        _clear(self.app_box)
        on = sum(a.enabled for a in self.apps)
        self.startup_status.setText(f"{len(self.apps)} app{'s' if len(self.apps) != 1 else ''} can start with Windows; "
                                    f"{on} {'is' if on == 1 else 'are'} on." if self.apps else
                                    "Nothing starts with Windows from the places Task Manager lists.")
        for app in self.apps:
            line = QWidget()
            box = row(spacing=10, margins=(2, 4, 2, 4))
            line.setLayout(box)
            switch = Switch(app.enabled, name=f"Start {app.title} with Windows")
            switch.clicked.connect(lambda checked=False, a=app, s=switch: self.toggle(a, s))
            box.addWidget(switch)
            words = column(spacing=0)
            words.addWidget(label(app.title, "readyGameTitle"))
            detail = " · ".join(p for p in (app.company, "for all users (asks for admin)" if app.needs_admin else "for you",
                                            "file is missing" if app.exists is False else "") if p)
            words.addWidget(label(detail, "caption"))
            box.addLayout(words, 1)
            line.setToolTip(f"{SOURCE_WORDS[app.source]}: {app.name}\n{app.command}")
            self.app_box.addWidget(line)
        self.app_box.addStretch(1)

    def toggle(self, app, switch):
        window = self.window_owner
        wanted = switch.isChecked()
        if app.needs_admin and not window.confirm(
                ("Turn on " if wanted else "Turn off ") + app.title + "?",
                f"{app.title} starts for every user on this PC, so Windows will ask for administrator permission.\n\n"
                "Only Task Manager's on/off value changes; the app and its startup entry stay."):
            switch.setChecked(not wanted)
            return
        switch.setEnabled(False)

        def work(_progress):
            try:
                up.set_enabled(app, wanted)
                return ""
            except (up.UpkeepError, OSError) as problem:
                return str(problem) or type(problem).__name__

        def done(problem):
            try:
                switch.setEnabled(True)
            except RuntimeError:
                return
            if problem:
                switch.setChecked(not wanted)
                window.error("Startup app not changed", problem)
                return
            log_event("startup_toggle", f"{app.title} {'will start' if wanted else 'will not start'} with Windows",
                      result="on" if wanted else "off", source="hardware")
            window.status.setText(f"{app.title} {'will start' if wanted else 'will no longer start'} with Windows. "
                                  "Takes effect at the next sign-in.")
            self.apps = [a if a.key != app.key else replace(a, enabled=wanted) for a in self.apps]
            on = sum(a.enabled for a in self.apps)
            self.startup_status.setText(f"{len(self.apps)} apps can start with Windows; {on} {'is' if on == 1 else 'are'} on.")
        window.job(work, done, error_title="Startup app not changed")
