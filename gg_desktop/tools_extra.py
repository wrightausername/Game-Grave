"""Exhume, Black Box and Autopsy windows (More Tools). Logic lives in `exhume`, `black_box` and `autopsy` (no Qt).

Each window reads first and changes nothing on its own. Outside effects are limited to: opening Device Manager or an
official web page the owner clicks, writing a report or capture summary into Game Grave's folder or where the owner
saves it, and starting PresentMon for the seconds shown after the owner presses Capture.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QListWidget
from shiboken6 import isValid

from core import config_dir, human_size
from gg_desktop import autopsy, black_box, exhume, winpc
from gg_desktop.tools_windows import _busy, _close_row, _dialog, _job, _text
from gg_desktop.widgets import button, row


def _history_path():
    return Path(config_dir()) / exhume.HISTORY_NAME


def open_device_manager():
    if sys.platform == "win32":
        os.startfile("devmgmt.msc")  # Windows' own Device Manager; Game Grave changes nothing itself


def _open_url(url):
    QDesktopServices.openUrl(QUrl(url))


# ------------------------------------------------------------------ Exhume
def open_exhume(window):
    if _busy(window):
        return None
    dialog, box = _dialog(window, "Exhume",
                          "Exhume remembers the graphics drivers you play on, so after a bad driver update you know "
                          "exactly which one to go back to. Game Grave never installs or removes a driver: going back "
                          "uses Windows' own Roll Back Driver or the vendor's official download.", width=620)
    dialog.drivers, dialog.entries = [], []
    dialog.listing = QListWidget()
    dialog.listing.setAccessibleName("Graphics adapters")
    dialog.listing.setMaximumHeight(110)
    box.addWidget(dialog.listing)
    dialog.detail = _text("", "detailValue")
    dialog.detail.setAccessibleName("Driver history")
    box.addWidget(dialog.detail)
    actions = row(spacing=8)
    dialog.good_button = button("Mark this driver known good", kind="primary",
                                tip="Only you decide a driver is good. Game Grave never guesses.")
    dialog.devices_button = button("Open Device Manager", tip="Roll Back Driver lives in Device Manager")
    dialog.vendor_button = button("Official driver page", tip="Opens the vendor's official driver page")
    for control in (dialog.good_button, dialog.devices_button, dialog.vendor_button):
        control.setEnabled(False)
        actions.addWidget(control)
    actions.addStretch()
    box.addLayout(actions)

    def current():
        index = dialog.listing.currentRow()
        return dialog.drivers[index] if 0 <= index < len(dialog.drivers) else None

    def show():
        driver = current()
        for control in (dialog.good_button, dialog.devices_button):
            control.setEnabled(driver is not None)
        dialog.vendor_button.setEnabled(bool(driver and exhume.vendor_page(driver)))
        if driver is None:
            return
        entry = next((e for e in dialog.entries if e.adapter == driver.adapter and e.version == driver.version), None)
        good = bool(entry and entry.known_good)
        dialog.good_button.setText("Unmark known good" if good else "Mark this driver known good")
        page = exhume.vendor_page(driver)
        dialog.vendor_button.setText(f"Official {page[0]} driver page" if page else "Official driver page")
        dialog.detail.setText("\n".join(exhume.advice(dialog.entries, driver)))

    def toggle_good():
        driver = current()
        if driver is None:
            return
        entry = next((e for e in dialog.entries if e.adapter == driver.adapter and e.version == driver.version), None)
        good = not (entry and entry.known_good)
        exhume.mark_known_good(dialog.entries, driver, good)
        exhume.save_history(_history_path(), dialog.entries)
        winpc.activity("Exhume", ("Marked known good: " if good else "Unmarked known good: ") + driver.label())
        dialog.result_line.setText("Saved." if good else "No longer marked known good.")
        show()

    def vendor():
        driver = current()
        page = exhume.vendor_page(driver) if driver else None
        if page:
            _open_url(page[1])
            dialog.result_line.setText(f"Opened {page[0]}'s official driver page.")

    def devices():
        open_device_manager()
        dialog.result_line.setText("Opened Device Manager. Display adapters > your card > Properties > Driver.")

    def loaded(packet, error):
        if not isValid(dialog):
            return
        if error:
            dialog.result_line.setText("Could not read the drivers: " + error)
            return
        dialog.drivers, dialog.entries = packet
        dialog.listing.clear()
        for driver in dialog.drivers:
            dialog.listing.addItem(driver.label())
        if dialog.drivers:
            dialog.listing.setCurrentRow(0)
        else:
            dialog.detail.setText("Windows did not report a graphics driver Game Grave can read on this PC.")

    def work():
        return exhume.refresh_history(winpc.default_registry(), _history_path())

    dialog.listing.currentRowChanged.connect(lambda _i: show())
    dialog.good_button.clicked.connect(toggle_good)
    dialog.vendor_button.clicked.connect(vendor)
    dialog.devices_button.clicked.connect(devices)
    _close_row(dialog, box)
    _job(window, work, loaded, "Exhume")
    window._tools_dialog = dialog
    dialog.exec()
    return dialog


# ------------------------------------------------------------------ Black Box
def _crash_text(crash):
    return (f"{crash.app} {crash.app_version} crashed {crash.when:%Y-%m-%d %H:%M}.\n"
            f"Exception {crash.exception_text()}.\n{crash.module_note()}")


def open_black_box(window):
    if _busy(window):
        return None
    dialog, box = _dialog(window, "Black Box",
                          "Black Box reads the crashes Windows recorded and shows what changed in that game's folder "
                          "in the days before. A change before a crash is a lead, not proof. It only reads.", width=680)
    dialog.crashes, dialog.shown, dialog.findings = [], [], None
    dialog.summary = _text("Reading Windows' crash log…", "detailValue")
    box.addWidget(dialog.summary)
    dialog.all_box = QCheckBox("Also show crashes of programs that are not scanned games")
    box.addWidget(dialog.all_box)
    dialog.listing = QListWidget()
    dialog.listing.setAccessibleName("Recorded crashes")
    dialog.listing.setMinimumHeight(140)
    box.addWidget(dialog.listing)
    dialog.detail = _text("", "caption")
    dialog.detail.setAccessibleName("Crash details")
    box.addWidget(dialog.detail)
    actions = row(spacing=8)
    dialog.changes_button = button("What changed before this?", kind="primary")
    dialog.report_button = button("Save shareable report…", tip="User name, PC name and profile folder are replaced")
    for control in (dialog.changes_button, dialog.report_button):
        control.setEnabled(False)
        actions.addWidget(control)
    actions.addStretch()
    box.addLayout(actions)

    def fill():
        show_all = dialog.all_box.isChecked()
        dialog.shown = [c for c in dialog.crashes if show_all or c.game]
        dialog.listing.clear()
        for crash in dialog.shown:
            dialog.listing.addItem(f"{crash.when:%Y-%m-%d %H:%M}  ·  {crash.game or crash.app}  ·  {crash.module or 'unknown module'}")
        dialog.listing.setVisible(bool(dialog.shown))
        if dialog.shown:
            dialog.listing.setCurrentRow(0)
        else:
            dialog.detail.setText("No crashes to show." + ("" if show_all else
                                  " Tick the box to include programs that are not scanned games."))
            select()

    def current():
        index = dialog.listing.currentRow()
        return dialog.shown[index] if 0 <= index < len(dialog.shown) else None

    def select():
        crash = current()
        dialog.findings = None
        dialog.changes_button.setEnabled(crash is not None)
        dialog.report_button.setEnabled(crash is not None)
        if crash is None:
            return
        dialog.detail.setText(_crash_text(crash))

    def investigate():
        crash = current()
        if crash is None:
            return
        dialog.changes_button.setEnabled(False)
        dialog.result_line.setText("Looking for changes. Files are only read.")
        history = exhume.load_history(_history_path())

        def done(findings, error):
            if not isValid(dialog):
                return
            dialog.changes_button.setEnabled(True)
            if error:
                dialog.result_line.setText("Could not look: " + error)
                return
            dialog.findings = findings
            lines = [_crash_text(crash), ""]
            if not crash.game_path:
                lines.append("Changed files: this program is not in a scanned game's folder, so there is no folder to check.")
            elif findings.changes:
                lines.append(f"Changed in the {black_box.CHANGE_WINDOW_DAYS} days before ({len(findings.changes)}"
                             f"{'+' if findings.truncated else ''}):")
                lines += [f"  {c.when:%m-%d %H:%M}  {Path(c.path).name}  ({human_size(c.size)})" for c in findings.changes[:12]]
            else:
                lines.append(f"Nothing in the game's folder changed in the {black_box.CHANGE_WINDOW_DAYS} days before.")
            if findings.drivers:
                lines.append("New graphics driver in that time: " +
                             ", ".join(f"{e.driver().friendly_version} ({e.first_seen})" for e in findings.drivers))
            dialog.detail.setText("\n".join(lines))
            dialog.result_line.setText("")
        _job(window, lambda: black_box.investigate(crash, history), done, "Black Box")

    def save_report():
        crash = current()
        if crash is None:
            return
        if dialog.findings and dialog.findings.crash is crash:
            write_report(crash, dialog.findings)
            return
        # Looking through a large game folder can take a moment, so it runs off the window's thread.
        dialog.report_button.setEnabled(False)
        dialog.result_line.setText("Looking for changes first. Files are only read.")
        history = exhume.load_history(_history_path())

        def done(findings, error):
            if not isValid(dialog):
                return
            dialog.report_button.setEnabled(True)
            if error:
                dialog.result_line.setText("Could not build the report: " + error)
                return
            dialog.findings = findings
            dialog.result_line.setText("")
            write_report(crash, findings)
        _job(window, lambda: black_box.investigate(crash, history), done, "Black Box")

    def write_report(crash, findings):
        path, _f = QFileDialog.getSaveFileName(dialog, "Save the Black Box report",
                                               str(Path.home() / black_box.report_name(crash)), "Text files (*.txt)")
        if not path:
            return
        try:
            Path(path).write_text(black_box.report_text(findings), encoding="utf-8")
        except OSError as exc:
            dialog.result_line.setText("The report was not saved: " + str(exc))
            return
        winpc.activity("Black Box", f"Saved a crash report for {crash.game or crash.app} ({crash.when:%Y-%m-%d %H:%M}).",
                       path=path)
        dialog.result_line.setText("Report saved. Your user name, PC name and profile folder were replaced.")

    def loaded(crashes, error):
        if not isValid(dialog):
            return
        if error:
            dialog.summary.setText("Windows' crash log could not be read: " + error)
            return
        dialog.crashes = crashes
        dialog.summary.setText(black_box.summary(crashes))
        fill()

    dialog.all_box.toggled.connect(lambda _c: fill())
    dialog.listing.currentRowChanged.connect(lambda _i: select())
    dialog.changes_button.clicked.connect(investigate)
    dialog.report_button.clicked.connect(save_report)
    _close_row(dialog, box)
    games = list(window.inventory.games)

    def work():
        # Note today's graphics driver too, so later crashes can show when it changed.
        try:
            exhume.refresh_history(winpc.default_registry(), _history_path())
        except OSError:
            pass
        return black_box.read_crashes(winpc.Runner(), games)
    _job(window, work, loaded, "Black Box")
    window._tools_dialog = dialog
    dialog.exec()
    return dialog


# ------------------------------------------------------------------ Autopsy
def _autopsy_dir():
    return Path(config_dir()) / "autopsy"


def _saved_presentmon():
    try:
        path = (_autopsy_dir() / "presentmon-path.txt").read_text(encoding="utf-8").strip()
        return path if os.path.isfile(path) else ""
    except OSError:
        return ""


def open_autopsy(window):
    if _busy(window):
        return None
    dialog, box = _dialog(window, "Autopsy",
                          "Autopsy measures a game before and after a change (a mod, a setting, a driver) and tells you "
                          "plainly whether it helped. It uses Intel's free, open-source PresentMon. Take both captures "
                          "in the same spot with the same settings apart from the change.", width=640)
    dialog.exe = _saved_presentmon() or autopsy.find_presentmon()
    dialog.captures = {}
    dialog.tool_line = _text("", "detailValue")
    box.addWidget(dialog.tool_line)
    tools = row(spacing=8)
    dialog.get_button = button("Get PresentMon", tip="Opens Intel's PresentMon releases on GitHub")
    dialog.choose_button = button("Choose PresentMon…")
    tools.addWidget(dialog.get_button)
    tools.addWidget(dialog.choose_button)
    tools.addStretch()
    box.addLayout(tools)
    pick = row(spacing=8)
    dialog.process_box = QComboBox()
    dialog.process_box.setAccessibleName("Game to measure")
    dialog.process_box.setMinimumWidth(260)
    dialog.refresh_button = button("Refresh list")
    dialog.seconds_box = QComboBox()
    dialog.seconds_box.setAccessibleName("Capture length")
    for seconds in (30, 60, 120):
        dialog.seconds_box.addItem(f"{seconds} seconds", seconds)
    dialog.seconds_box.setCurrentIndex(1)
    pick.addWidget(dialog.process_box, 1)
    pick.addWidget(dialog.refresh_button)
    pick.addWidget(dialog.seconds_box)
    box.addLayout(pick)
    captures = row(spacing=8)
    dialog.before_button = button("Capture Before", kind="primary")
    dialog.after_button = button("Capture After", kind="primary")
    captures.addWidget(dialog.before_button)
    captures.addWidget(dialog.after_button)
    captures.addStretch()
    box.addLayout(captures)
    dialog.results = _text("No captures yet.", "detailValue")
    dialog.results.setAccessibleName("Autopsy results")
    box.addWidget(dialog.results)

    def update():
        dialog.tool_line.setText(f"PresentMon: {dialog.exe}" if dialog.exe else
                                 "PresentMon was not found. Download the console app (for example PresentMon-2.x-x64.exe) "
                                 "into your Downloads folder, or choose it.")
        ready = bool(dialog.exe) and dialog.process_box.count() > 0 and dialog.process_box.currentData() is not None
        dialog.before_button.setEnabled(ready)
        dialog.after_button.setEnabled(ready)
        lines = [c.line() for c in (dialog.captures.get("Before"), dialog.captures.get("After")) if c]
        if "Before" in dialog.captures and "After" in dialog.captures:
            lines += [""] + autopsy.verdict(dialog.captures["Before"], dialog.captures["After"])
        dialog.results.setText("\n".join(lines) if lines else "No captures yet.")

    def refresh():
        procs = winpc.list_processes(winpc.Runner())
        dialog.process_box.clear()
        for proc in procs:
            dialog.process_box.addItem(f"{proc.name}  ({human_size(proc.kb * 1024)})", proc.name)
        if not procs:
            dialog.process_box.addItem("Start the game, then press Refresh list", None)
        update()

    def choose():
        path, _f = QFileDialog.getOpenFileName(dialog, "Choose PresentMon", str(Path.home() / "Downloads"),
                                               "Programs (*.exe)")
        if path:
            dialog.exe = path
            _autopsy_dir().mkdir(parents=True, exist_ok=True)
            (_autopsy_dir() / "presentmon-path.txt").write_text(path, encoding="utf-8")
            update()

    def capture(label):
        process = dialog.process_box.currentData()
        if not (dialog.exe and process):
            return
        seconds = int(dialog.seconds_box.currentData())
        if not window.confirm("Start an Autopsy capture",
                              f"Measure {process} for {seconds} seconds with PresentMon?\n\nSwitch to the game now and "
                              "play normally in the same spot you will use for the other capture. PresentMon only "
                              "reads frame timing; nothing in the game is changed."):
            return
        dialog.before_button.setEnabled(False)
        dialog.after_button.setEnabled(False)
        dialog.result_line.setText(f"Capturing {label.lower()} for {seconds} seconds…")
        raw = _autopsy_dir() / "raw"
        raw.mkdir(parents=True, exist_ok=True)
        csv_path = raw / f"capture-{label.lower()}.csv"
        exe = dialog.exe

        def work():
            if csv_path.exists():
                csv_path.unlink()
            result = winpc.Runner().run(autopsy.capture_args(exe, process, csv_path, seconds), timeout=seconds + 45)
            if not csv_path.is_file():
                raise OSError(autopsy.failure_text(result))
            try:
                cap = autopsy.capture_from_csv(csv_path, label=label, game=process)
            finally:
                csv_path.unlink(missing_ok=True)
            autopsy.save_capture(_autopsy_dir(), cap)
            return cap

        def done(cap, error):
            if not isValid(dialog):
                return
            if error:
                dialog.result_line.setText(error)
            else:
                dialog.captures[label] = cap
                dialog.result_line.setText(f"{label} capture saved.")
                winpc.activity("Autopsy", cap.line())
            update()
        _job(window, work, done, "Autopsy")

    dialog.get_button.clicked.connect(lambda: _open_url(autopsy.PRESENTMON_PAGE))
    dialog.choose_button.clicked.connect(choose)
    dialog.refresh_button.clicked.connect(refresh)
    dialog.process_box.currentIndexChanged.connect(lambda _i: update())
    dialog.before_button.clicked.connect(lambda: capture("Before"))
    dialog.after_button.clicked.connect(lambda: capture("After"))
    _close_row(dialog, box)
    refresh()
    window._tools_dialog = dialog
    dialog.exec()
    return dialog
