"""Settings tab: preferences saved on this PC, with every control either wired to real behavior or shown as fixed.

Preferences are staged and written only when Apply Changes is pressed. Never Touch rules, scan folders, export and
import act at once because each has its own confirmation. Nothing here moves, deletes or scans a file by itself.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QEvent, QObject, QRectF, QSignalBlocker, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPen
from PySide6.QtWidgets import (QAbstractButton, QComboBox, QFileDialog, QFrame, QLabel, QListWidget, QPushButton,
                               QScrollArea, QSizePolicy, QStackedWidget, QWidget)
from shiboken6 import isValid

import core
from core import get_activity, human_size, log_event, save_settings
from recovery import get_records
from gg_desktop import __version__
from gg_desktop import settings_data as data
from gg_desktop import settings_system as system
from gg_desktop import update_check
from gg_desktop.backend import add_never_touch_path, refresh_graveyard, unprotect_exact_personal_item
from gg_desktop.header_banner import HeaderBannerArtwork
from gg_desktop.insight_widgets import ActionFlow
from gg_desktop.reference_library import _widget
from gg_desktop.reference_widgets import icon, tool
from gg_desktop.widgets import column, label, panel, row

SUBTITLE = "Control how Game Grave scans, protects and looks. Changes apply to this PC only."
TABS = (("General", "Startup & language", "settings"), ("Scanning", "Folders & age rules", "filter"),
        ("Protection", "Safe removal rules", "shield"), ("Appearance", "Theme & scale", "sparkles"),
        ("Notifications", "Alerts & reminders", "bell"), ("Data & Privacy", "Logs & local data", "storage"))
TONES = {"yellow": "246,190,36", "cyan": "19,188,245", "purple": "180,85,255", "red": "255,37,74", "green": "50,214,122"}
TONE_HEX = {"yellow": "#f6be24", "cyan": "#13bcf5", "purple": "#b455ff", "red": "#ff3b57", "green": "#32d67a"}
FOOTER = "Changes save to this PC when you press Apply. Reset to Defaults never touches your files, mods or recovery records."
NAMES = {"start_minimized": "Start minimized", "scan_on_launch": "Scan when Game Grave starts",
         "files_stale_days": "Files idle after", "graveyard_days": "Graveyard age signal",
         "excluded_folders": "Excluded folders", "steam_artwork_downloads": "Steam artwork downloads",
         "autostart": "Launch with Windows", "assistant_enabled": "AI Assistant tab"}


# ------------------------------------------------------------------ small widgets
class Switch(QAbstractButton):
    """A real on/off control. A locked switch is always on and cannot be changed."""

    def __init__(self, checked=False, *, locked=False, name=""):
        super().__init__()
        self.locked = locked
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(40, 21)
        self.setAccessibleName(name)
        self.setFocusPolicy(Qt.NoFocus if locked else Qt.StrongFocus)
        self.setCursor(Qt.ArrowCursor if locked or not checked else Qt.PointingHandCursor)

    def nextCheckState(self):
        if not self.locked:
            super().nextCheckState()

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        dim = not self.isEnabled()
        track = QColor("#ff254a") if self.isChecked() else QColor("#2b3542")
        knob = QColor("#e8eef5")
        if dim:
            track.setAlpha(80)
            knob.setAlpha(120)
        painter.setPen(Qt.NoPen)
        painter.setBrush(track)
        h = self.height()
        painter.drawRoundedRect(QRectF(0, 0, self.width(), h), h / 2, h / 2)
        painter.setBrush(knob)
        x = self.width() - h + 3 if self.isChecked() else 3
        painter.drawEllipse(QRectF(x, 3, h - 6, h - 6))
        if self.hasFocus():
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor("#f6be24"), 1.5))
            painter.drawRoundedRect(QRectF(0.75, 0.75, self.width() - 1.5, h - 1.5), h / 2, h / 2)


class ElideLabel(QLabel):
    """One line of text that shortens in the middle instead of widening the page."""

    def __init__(self, text="", mode=Qt.ElideMiddle):
        super().__init__()
        self.setTextFormat(Qt.PlainText)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._full, self._mode = "", mode
        self.set_full(text)

    def full(self):
        return self._full

    def set_full(self, text):
        self._full = text
        self.setToolTip(text)
        self._fit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()

    def _fit(self):
        self.setText(self.fontMetrics().elidedText(self._full, self._mode, max(12, self.width() - 2)))


def frame(name, tone, title, symbol, badge="", header=True):
    box, body = panel(kind="fileFilterPanel", padding=11, spacing=5)
    rgb = TONES[tone]
    box.setObjectName(name)
    box.setStyleSheet(
        f"QFrame#{name}{{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba({rgb},38),stop:.4 #08101a,stop:1 #060b12);"
        f"border:1.5px solid rgba({rgb},215);border-radius:10px;}}")
    if not header:
        return box, body
    head = row(spacing=7)
    mark = QLabel()
    mark.setPixmap(icon(symbol, TONE_HEX[tone], 18).pixmap(18, 18))
    head.addWidget(mark)
    heading = label(title, "sectionTitle")
    heading.setMinimumWidth(0)
    heading.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    head.addWidget(heading, 1)
    if badge:
        chip = QLabel(badge)
        chip.setStyleSheet("color:#32d67a;border:1px solid #1c6a3a;background:#07160d;border-radius:4px;"
                           "padding:1px 7px;font-size:10px;font-weight:700;")
        head.addWidget(chip)
    body.addLayout(head)
    box.heading = heading
    return box, body


def line(title, caption, control, *, top=False):
    holder = QWidget()
    lay = row(spacing=8, margins=(0, 3, 0, 3))
    holder.setLayout(lay)
    words = column(spacing=1)
    heading = label(title, "detailValue", wrap=True)
    heading.setMinimumWidth(0)
    heading.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    words.addWidget(heading)
    if caption:
        note = label(caption, "caption", wrap=True)
        note.setMinimumWidth(0)
        note.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        words.addWidget(note)
    lay.addLayout(words, 1)
    lay.addWidget(control, 0, Qt.AlignTop if top else Qt.AlignVCenter)
    return holder


def pill(text):
    chip = QLabel(text)
    chip.setStyleSheet("color:#e8eef5;background:#0c1520;border:1px solid #243244;border-radius:6px;padding:4px 10px;font-size:12px;")
    chip.setMinimumWidth(0)
    return chip


class TabButton(QPushButton):
    def __init__(self, title, subtitle, symbol):
        super().__init__()
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setFixedHeight(52)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setAccessibleName(title + " settings")
        self.setToolTip(subtitle)
        self.setCursor(Qt.PointingHandCursor)
        lay = row(spacing=8, margins=(10, 0, 6, 0))
        self.setLayout(lay)
        self.glyph = QLabel()
        self.glyph.setPixmap(icon(symbol, "#e8eef5", 20).pixmap(20, 20))
        self.glyph.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay.addWidget(self.glyph)
        words = column(spacing=0)
        self.title = label(title, "detailValue")
        self.title.setStyleSheet("font-size:13px;font-weight:700;")
        self.sub = label(subtitle, "caption")
        for part in (self.title, self.sub):
            part.setAttribute(Qt.WA_TransparentForMouseEvents)
            part.setMinimumWidth(0)
            part.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            words.addWidget(part)
        lay.addLayout(words, 1)
        self.glyph_visible = True
        self.setStyleSheet(
            "QPushButton{background:#08101a;border:1px solid #1d2a38;border-radius:8px;text-align:left;}"
            "QPushButton:hover{border-color:#44566b;}"
            "QPushButton:checked{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #ff254a,stop:1 #b3112b);"
            "border:1px solid #ff6b81;}")


    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Narrow windows keep the tab names readable by dropping the caption, then the icon.
        self.sub.setVisible(self.width() >= 150)
        self.glyph.setVisible(self.width() >= 128)


class NarrowText(QObject):
    """Swaps a button's text for a shorter one when its panel gets narrow."""

    def __init__(self, panel_box, control, wide, short, limit):
        super().__init__(panel_box)
        self.control, self.wide, self.short, self.limit = control, wide, short, limit
        panel_box.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Resize:
            self.control.setText(self.short if watched.width() < self.limit else self.wide)
        return False


# ------------------------------------------------------------------ state
def state_of(window):
    if not hasattr(window, "_settings_state"):
        window._settings_state = SimpleNamespace(pending=None, autostart=None, tab="General")
    return window._settings_state


def live(window):
    return (window.current_route == "Settings" and hasattr(window, "settings_stack") and isValid(window.settings_stack)
            and hasattr(window.page, "settings_ready"))


def saved_prefs(window):
    return data.current(window.settings)


def saved_autostart():
    try:
        return system.is_enabled() if system.available() else False
    except OSError:
        return False


def edits(window):
    state = state_of(window)
    names = data.changed(saved_prefs(window), data.current(state.pending))
    if bool(state.autostart) != saved_autostart():
        names.append("autostart")
    return names


def persist(window, updated):
    try:
        save_settings(updated)
    except (OSError, ValueError) as exc:
        window.error("Settings not saved", str(exc))
        return False
    window.settings = updated
    window._sync_assistant_nav()
    return True


# ------------------------------------------------------------------ bound controls
def register(window, key, widget, refresh):
    window.settings_controls.setdefault(key, []).append(widget)
    window._settings_refreshers.append(refresh)


def bool_switch(window, key, title, caption, *, name=None):
    state = state_of(window)
    switch = Switch(bool(state.pending[key]), name=title)

    def toggled(on):
        state.pending[key] = bool(on)
        sync(window)

    def refresh():
        with QSignalBlocker(switch):
            switch.setChecked(bool(state.pending[key]))
    switch.toggled.connect(toggled)
    register(window, key, switch, refresh)
    return line(title, caption, switch)


def autostart_switch(window):
    state = state_of(window)
    usable = system.available()
    switch = Switch(bool(state.autostart), name="Launch with Windows")
    switch.setEnabled(usable)

    def toggled(on):
        state.autostart = bool(on)
        sync(window)

    def refresh():
        with QSignalBlocker(switch):
            switch.setChecked(bool(state.autostart))
    switch.toggled.connect(toggled)
    register(window, "autostart", switch, refresh)
    return line("Launch with Windows", "Opens Game Grave when you sign in to Windows." if usable else system.reason(), switch)


def fixed_switch(title, caption, *, on=True, enabled=True):
    switch = Switch(on, locked=True, name=title)
    switch.setEnabled(enabled)
    return line(title, caption, switch)


def day_combo(window, key, choices, name):
    state = state_of(window)
    box = QComboBox()
    box.setAccessibleName(name)
    box.setMinimumWidth(96)
    box.setMaximumWidth(150)
    for days in choices:
        box.addItem(f"{days} days" if days < 365 else ("1 year" if days == 365 else "2 years"), days)

    def refresh():
        with QSignalBlocker(box):
            box.setCurrentIndex(max(0, box.findData(state.pending[key])))

    def picked(_index):
        state.pending[key] = box.currentData()
        sync(window)
    box.currentIndexChanged.connect(picked)
    register(window, key, box, refresh)
    refresh()
    return box


# ------------------------------------------------------------------ panels
def startup_panel(window):
    box, body = frame("settingsStartup", "yellow", "Startup & Behavior", "settings")
    body.addWidget(autostart_switch(window))
    body.addWidget(bool_switch(window, "start_minimized", "Start minimized", "Opens in the taskbar instead of on screen."))
    body.addWidget(bool_switch(window, "scan_on_launch", "Scan when Game Grave starts",
                               "Runs a read-only scan each time the app opens."))
    body.addWidget(bool_switch(window, "assistant_enabled", "AI Assistant tab",
                               "Adds the AI Assistant to the sidebar. It is local, read only and off until you turn it on."))
    body.addWidget(fixed_switch("Check for updates on launch", "Update service not connected in this preview. Nothing is contacted.",
                                on=False, enabled=False))
    body.addStretch()
    return box


def language_panel(window):
    box, body = frame("settingsLanguage", "cyan", "Language & Region", "help")
    body.addWidget(line("Language", "", pill("English (US)")))
    body.addWidget(line("Size units", "", pill("GB (1024)")))
    body.addWidget(line("Date format", "", pill("YYYY-MM-DD")))
    note = label("Fixed in this version, so every tab shows the same units and dates.", "caption", wrap=True)
    body.addWidget(note)
    body.addStretch()
    return box


def old_files_folder(window):
    chosen = QFileDialog.getExistingDirectory(window, "Select ordinary Old Files scan folder",
                                              str(window.settings.get("scan_folder", str(Path.home()))))
    if not chosen:
        return
    target = Path(chosen)
    if not core.safe_scan_root(target) or core.is_protected_path(target, []):
        window.error("Folder not allowed", "Choose a normal local documents or download folder, not a drive root, "
                     "game install, mod manager or protected system directory.")
        return
    if persist(window, dict(window.settings, scan_folder=str(target))):
        window.status.setText("Old Files folder saved. Scan PC before reviewing files.")
        sync(window)


def scanning_panel(window, compact=False):
    box, body = frame("settingsScanning", "purple", "Scanning Defaults", "search")
    folder = ElideLabel("", Qt.ElideMiddle)
    folder.setObjectName("settingsFolder")
    pick = tool("Change", "folder", lambda: old_files_folder(window), tip="Choose the Old Files scan folder")
    pick.setFixedHeight(28)
    holder = QWidget()
    lay = row(spacing=8)
    holder.setLayout(lay)
    words = column(spacing=1)
    words.addWidget(label("Old Files folder", "detailValue"))
    words.addWidget(folder)
    lay.addLayout(words, 1)
    lay.addWidget(pick)
    body.addWidget(holder)
    body.addWidget(line("Files idle after", "", day_combo(window, "files_stale_days", data.FILE_DAYS, "Files idle after")))
    body.addWidget(line("Graveyard age signal", "", day_combo(window, "graveyard_days", data.GRAVE_DAYS, "Graveyard age signal")))
    counts = {}
    total = label("", "detailValue")
    if compact:
        summary = QWidget()
        inner = row(spacing=6, margins=(0, 1, 0, 1))
        summary.setLayout(inner)
        inner.addWidget(label("Scan locations", "caption"), 1)
        inner.addWidget(total)
        body.addWidget(summary)
    for key in () if compact else data.LIBRARY_KEYS:
        item = QWidget()
        inner = row(spacing=6, margins=(0, 1, 0, 1))
        item.setLayout(inner)
        name = label(data.LIBRARY_NAMES[key], "caption")
        name.setMinimumWidth(0)
        name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        inner.addWidget(name, 1)
        value = label("0", "detailValue")
        inner.addWidget(value)
        counts[key] = value
        body.addWidget(item)
    manage = tool("Manage Scan Locations…", "folder", window.open_scan_locations, tip="Add or remove library, mod and capture folders")
    manage.setFixedHeight(28)
    body.addWidget(manage)
    body.addWidget(label("Idle ages apply to the next scan.", "caption", wrap=True))
    body.addStretch()

    def refresh():
        folder.set_full(str(window.settings.get("scan_folder", "")))
        for key, value in counts.items():
            found = window.settings.get(key, [])
            value.setText(str(len(found) if isinstance(found, list) else 0))
        total.setText(str(sum(len(window.settings.get(k, [])) if isinstance(window.settings.get(k, []), list) else 0
                              for k in data.LIBRARY_KEYS)) + " folders")
    register(window, "scan_locations", folder, refresh)
    refresh()
    return box


def excluded_panel(window):
    state = state_of(window)
    box, body = frame("settingsExcluded", "red", "Excluded Folders", "folder")
    add = tool("Add Folder", "plus", lambda: add_excluded(window), tip="Leave a folder out of scan results")
    add.setFixedHeight(28)
    box.layout().itemAt(0).layout().addWidget(add)
    NarrowText(box, add, "Add Folder", "Add", 300)
    scroller = QScrollArea()
    scroller.setWidgetResizable(True)
    scroller.setFrameShape(QFrame.NoFrame)
    scroller.setMinimumHeight(54)
    scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroller.setStyleSheet("QScrollArea{background:transparent;} QScrollArea > QWidget > QWidget{background:transparent;}")
    inner = QWidget()
    rows = column(spacing=3)
    inner.setLayout(rows)
    scroller.setWidget(inner)
    body.addWidget(scroller, 1)
    empty = label("No folders are excluded.", "caption", wrap=True)
    body.addWidget(empty)
    body.addWidget(label("Games, mods and files inside these folders are left out of scan results. Nothing is deleted, "
                         "and saves are never hidden.", "caption", wrap=True))
    entries = []

    def refresh():
        while rows.count():
            item = rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        entries.clear()
        folders = state.pending["excluded_folders"]
        box.heading.setText(f"Excluded Folders ({len(folders)})")
        empty.setVisible(not folders)
        for path in folders:
            holder = QWidget()
            lay = row(spacing=6)
            holder.setLayout(lay)
            mark = QLabel()
            mark.setPixmap(icon("folder", "#b8c4d2", 15).pixmap(15, 15))
            lay.addWidget(mark)
            text = ElideLabel(path)
            lay.addWidget(text, 1)
            drop = tool("", "close", lambda _=False, p=path: remove_excluded(window, p), tip="Stop excluding this folder")
            drop.setFixedSize(24, 24)
            drop.setAccessibleName("Stop excluding " + path)
            lay.addWidget(drop)
            rows.addWidget(holder)
            entries.append((path, drop))
        rows.addStretch()
    register(window, "excluded_folders", scroller, refresh)
    window.settings_excluded_entries = entries
    refresh()
    return box


def add_excluded(window):
    state = state_of(window)
    chosen = QFileDialog.getExistingDirectory(window, "Choose a folder to leave out of scans")
    if not chosen:
        return
    problem = data.exclusion_problem(chosen, state.pending["excluded_folders"])
    if problem:
        window.error("Folder not excluded", problem)
        return
    state.pending["excluded_folders"].append(str(Path(chosen)))
    sync(window)


def remove_excluded(window, path):
    state = state_of(window)
    if path in state.pending["excluded_folders"]:
        state.pending["excluded_folders"].remove(path)
        sync(window)


def protection_panel(window):
    box, body = frame("settingsProtection", "green", "Protection", "shield", badge="ALWAYS ON")
    body.addWidget(fixed_switch("Recycle Bin only", "Removals never skip the Recycle Bin."))
    body.addWidget(fixed_switch("Confirm every cleanup", "You approve each action."))
    body.addWidget(fixed_switch("Protect launcher and save folders", "Built-in rules cannot be turned off."))
    count = label("", "detailValue")
    manage = tool("Manage Rules", "shield", lambda: show_tab(window, "Protection"), tip="Open your personal Never Touch rules")
    manage.setFixedHeight(28)
    holder = QWidget()
    lay = row(spacing=8)
    holder.setLayout(lay)
    lay.addWidget(count, 1)
    lay.addWidget(manage)
    body.addWidget(holder)
    body.addStretch()

    def refresh():
        rules = window.settings.get("never_touch", [])
        count.setText(f"Personal rules  {len(rules) if isinstance(rules, list) else 0}")
    register(window, "never_touch_count", count, refresh)
    refresh()
    return box


def never_touch_panel(window):
    box, body = frame("settingsNever", "red", "Never Touch Rules", "shield")
    body.addWidget(label("Folders you protect are never offered for cleanup. Built-in protection for games, mods, saves "
                         "and system folders cannot be switched off. Removing a parent folder rule frees every folder "
                         "beneath it for review; nothing is deleted.", "caption", wrap=True))
    rules = QListWidget()
    rules.setAccessibleName("Personal Never Touch rules")
    rules.setMinimumHeight(120)
    body.addWidget(rules, 1)
    window.settings_never_list = rules
    actions = row(spacing=8)
    add = tool("Protect a Folder", "plus", lambda: add_rule(window), tip="Protect an ordinary personal folder")
    drop = tool("Remove Selected Rule…", "trash", lambda: remove_rule(window), kind="danger", tip="Remove your selected personal rule")
    for control in (add, drop):
        control.setFixedHeight(30)
        actions.addWidget(control)
    actions.addStretch()
    body.addLayout(actions)

    def refresh():
        current = window.settings.get("never_touch", [])
        want = [str(r) for r in current] if isinstance(current, list) else []
        if want != [rules.item(i).text() for i in range(rules.count())]:
            rules.clear()
            rules.addItems(want)
    register(window, "never_touch", rules, refresh)
    refresh()
    return box


def add_rule(window):
    chosen = QFileDialog.getExistingDirectory(window, "Protect an ordinary personal folder")
    if not chosen:
        return
    try:
        window.settings = add_never_touch_path(window.settings, chosen)
        refresh_graveyard(window.inventory, window.settings)
    except (OSError, ValueError) as exc:
        window.error("Cannot add rule", str(exc))
        return
    window.status.setText("Folder protected. It will not be offered for cleanup.")
    sync(window)


def remove_rule(window):
    item = window.settings_never_list.currentItem()
    if not item:
        window.info("Choose a rule", "Select your personal Never Touch rule to remove.")
        return
    rule = item.text()
    if not window.confirm("Remove protected folder rule?",
                          "This removes a personal Never Touch rule for:\n" + rule +
                          "\n\nEvery child file beneath this folder may become reviewable if it otherwise meets safety "
                          "rules. NOTHING is deleted now. Built-in protection remains active.", destructive=True):
        return
    try:
        window.settings = unprotect_exact_personal_item(window.settings, rule)
        refresh_graveyard(window.inventory, window.settings)
    except (OSError, ValueError) as exc:
        window.error("Could not remove rule", str(exc))
        return
    window.status.setText("Rule removed. Nothing was deleted.")
    sync(window)


def appearance_panel(window):
    box, body = frame("settingsAppearance", "red", "Appearance", "sparkles")
    body.addWidget(line("Theme", "", pill("Crimson Command")))
    body.addWidget(line("Interface scale", "", pill("100% native")))
    body.addWidget(label("The look is fixed so every tab keeps its approved layout. Older themes stay in the classic tools.",
                         "caption", wrap=True))
    classic = tool("Classic Appearance and Advanced…", "more", window._launch_classic_tools,
                   tip="Open the classic tools, which hold the older appearance themes")
    classic.setFixedHeight(28)
    body.addWidget(classic)
    body.addStretch()
    return box


def scan_behavior_panel(window):
    box, body = frame("settingsScanBehavior", "yellow", "Scan Behavior", "refresh")
    body.addWidget(bool_switch(window, "scan_on_launch", "Scan when Game Grave starts", "Runs a read-only scan each time the app opens."))
    body.addWidget(label("Scans only read. Every cleanup still asks you first and goes to the Recycle Bin.", "caption", wrap=True))
    body.addStretch()
    return box


def notifications_panel(window):
    box, body = frame("settingsNotifications", "yellow", "Notifications", "bell")
    body.addWidget(label("Game Grave shows no pop-up alerts and runs nothing in the background. When a scan finishes, the "
                         "result appears in the status line at the bottom of the window.", "subtle", wrap=True))
    body.addWidget(label("Start minimized and Scan when Game Grave starts are under General.", "caption", wrap=True))
    body.addStretch()
    return box


def privacy_panel(window):
    box, body = frame("settingsPrivacy", "cyan", "Privacy", "shield")
    body.addWidget(label("Game Grave has no account and sends no telemetry. Settings, history, recovery records, saved "
                         "chats and folder links all stay in the data folder on this PC.", "subtle", wrap=True))
    body.addWidget(bool_switch(window, "steam_artwork_downloads", "Download missing Steam artwork",
                               "Public Steam cover images are downloaded only while this is on, and kept in a local cache."))
    body.addStretch()
    return box


def facts_panel(window):
    box, body = frame("settingsFacts", "purple", "Stored on This PC", "storage")
    values = {}
    for key, title in (("file", "Settings file"), ("events", "Activity log entries"), ("records", "Recovery records")):
        value = label("", "detailValue")
        values[key] = value
        body.addWidget(line(title, "", value))
    body.addStretch()

    def refresh():
        path = core.config_dir() / "settings.json"
        try:
            values["file"].setText(human_size(path.stat().st_size) if path.is_file() else "Not saved yet")
        except OSError:
            values["file"].setText("Unavailable")
        for key, reader in (("events", get_activity), ("records", get_records)):
            try:
                values[key].setText(f"{len(reader()):,}")
            except Exception:  # an unreadable history must not break Settings; the count simply reads Unavailable
                values[key].setText("Unavailable")
    register(window, "facts", values["file"], refresh)
    refresh()
    return box


# ------------------------------------------------------------------ actions
def check_updates(window):
    """Manual only: one request to the GitHub releases list, nothing downloaded or installed."""
    window.settings_update.setEnabled(False)
    window.settings_update_note.setText("Asking GitHub for the newest preview build...")

    def work():
        try:
            return update_check.check()
        except update_check.UpdateCheckError as problem:
            return ("error", str(problem))
        except Exception as problem:  # never leave the button stuck on a surprise
            return ("error", "The update check could not finish: %s" % (problem or type(problem).__name__))

    def finish(result):
        if not isValid(window.settings_update):  # the page was rebuilt while the answer was on its way
            return
        kind, sentence = result
        window.settings_update.setEnabled(True)
        window.settings_update_note.setText(sentence)
        window.settings_update_open.setVisible(kind in {"available", "unknown", "error"})

    window.job(work, finish, error_title="Update check failed")


def open_updater(window):
    import subprocess
    import sys
    app_folder = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else None
    path = update_check.updater_path(app_folder)
    if path:
        try:
            subprocess.Popen([str(path)], close_fds=True)
            return
        except OSError as exc:
            window.error("Updater would not open", str(exc))
            return
    QDesktopServices.openUrl(QUrl(update_check.RELEASES_PAGE))


def open_data_folder(window):
    folder = core.config_dir()
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        window.error("Data folder unavailable", str(exc))
        return
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))


def export_settings(window):
    chosen, _filter = QFileDialog.getSaveFileName(window, "Export Game Grave settings",
                                                  str(Path.home() / "game-grave-settings.json"), "JSON (*.json)")
    if not chosen:
        return
    target = Path(chosen)
    try:
        fd, raw = tempfile.mkstemp(prefix=".gg-export-", suffix=".tmp", dir=target.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(data.export_text(window.settings))
        os.replace(raw, target)
    except OSError as exc:
        window.error("Settings not exported", str(exc))
        return
    window.status.setText("Settings exported to " + target.name + ". Saved chats and hidden rows are not included.")


def import_settings(window):
    chosen, _filter = QFileDialog.getOpenFileName(window, "Import Game Grave settings", str(Path.home()), "JSON (*.json)")
    if not chosen:
        return
    try:
        with open(chosen, "rb") as handle:
            raw = handle.read(core.MAX_SETTINGS_BYTES + 1)
        report = data.import_settings(raw, window.settings)
    except (OSError, ValueError) as exc:
        window.error("Settings not imported", str(exc))
        return
    summary = "\n".join(report.notes)
    if not window.confirm("Import these settings?",
                          "Preferences and folder lists from this file replace or add to the ones on this PC.\n\n"
                          + summary + "\n\nNothing is scanned, moved or deleted.", destructive=False):
        return
    if not persist(window, report.settings):
        return
    refresh_graveyard(window.inventory, window.settings)
    state = state_of(window)
    state.pending = saved_prefs(window)
    window.status.setText("Settings imported. Scan PC to use the folder changes.")
    sync(window)


def reset_defaults(window):
    state = state_of(window)
    state.pending = data.defaults()
    state.autostart = False
    window.status.setText("Defaults staged. Press Apply to keep them or Cancel to undo. Your files, mods, recovery records "
                          "and Never Touch rules are not affected.")
    sync(window)


def cancel_changes(window):
    state = state_of(window)
    state.pending = saved_prefs(window)
    state.autostart = saved_autostart()
    sync(window)


def apply_changes(window):
    state = state_of(window)
    names = edits(window)
    if not names:
        return
    wanted = data.current(state.pending)
    updated = data.apply(window.settings, wanted)
    if not persist(window, updated):
        return
    window.artwork.allow_downloads = wanted["steam_artwork_downloads"]
    if "steam_artwork_downloads" in names and wanted["steam_artwork_downloads"]:
        window.artwork.retry()
    problem = ""
    if "autostart" in names:
        try:
            system.set_enabled(bool(state.autostart))
        except OSError as exc:
            problem = str(exc)
            state.autostart = saved_autostart()
    state.pending = saved_prefs(window)
    try:
        log_event("Settings changed", "Updated: " + ", ".join(NAMES[n] for n in names), source="Settings")
    except OSError:
        pass
    if problem:
        window.error("Launch with Windows not changed", problem)
    window.status.setText("Settings applied. Idle ages and excluded folders take effect on the next scan.")
    sync(window)


# ------------------------------------------------------------------ page
def sync(window):
    if not live(window):
        return
    state = state_of(window)
    for refresh in list(window._settings_refreshers):
        refresh()
    names = edits(window)
    dirty = bool(names)
    window.settings_apply.setEnabled(dirty)
    window.settings_cancel.setEnabled(dirty)
    window.settings_footer.setText(
        (f"{len(names)} unapplied change{'s' if len(names) != 1 else ''}: " + ", ".join(NAMES[n] for n in names)
         + ". They save to this PC when you press Apply.") if dirty else FOOTER)
    window.settings_footer.setToolTip(window.settings_footer.text())
    window.settings_path.set_full(str(core.config_dir()))
    for name, button in window.settings_tab_buttons.items():
        button.setChecked(name == state.tab)
    window.settings_stack.setCurrentIndex([t[0] for t in TABS].index(state.tab))


def show_tab(window, name):
    state_of(window).tab = name
    sync(window)


def columns(*cols):
    page = QWidget()
    lay = row(spacing=10)
    page.setLayout(lay)
    for weight, panels in cols:
        holder = QWidget()
        stack = column(spacing=10)
        holder.setLayout(stack)
        for item in panels:
            stack.addWidget(item, 1)
        stack.addStretch(0)
        holder.setMinimumWidth(0)
        holder.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        lay.addWidget(holder, weight)
    return page


def build(window):
    self = window
    state = state_of(self)
    if state.pending is None:
        state.pending = saved_prefs(self)
        state.autostart = saved_autostart()
    if state.tab not in [t[0] for t in TABS]:
        state.tab = "General"
    self.settings_controls = {}
    self._settings_refreshers = []

    page = self._insight_page("Settings", SUBTITLE, "settings", "settings", 66)
    page.banner_artwork = HeaderBannerArtwork(self, page, page.content.itemAt(0).widget(), route="Settings",
                                              scene="settings", source=(910, 0, 370, 110), excluded=((1090, 0, 190, 40),))

    strip = row(spacing=8)
    self.settings_tab_buttons = {}
    for title, subtitle, symbol in TABS:
        button = TabButton(title, subtitle, symbol)
        button.clicked.connect(lambda _=False, t=title: show_tab(self, t))
        self.settings_tab_buttons[title] = button
        strip.addWidget(button, 1)
    holder = QWidget()
    holder.setLayout(strip)
    holder.setFixedHeight(54)
    page.content.addWidget(holder)

    self.settings_stack = QStackedWidget()
    self.settings_stack.addWidget(columns((1, [startup_panel(self), language_panel(self)]),
                                          (1, [scanning_panel(self, compact=True), excluded_panel(self)]),
                                          (1, [protection_panel(self), appearance_panel(self)])))
    self.settings_stack.addWidget(columns((1, [scanning_panel(self)]), (1, [excluded_panel(self)]),
                                          (1, [scan_behavior_panel(self)])))
    self.settings_stack.addWidget(columns((1, [protection_panel(self)]), (2, [never_touch_panel(self)])))
    self.settings_stack.addWidget(columns((1, [appearance_panel(self)]), (1, [language_panel(self)]), (1, [])))
    self.settings_stack.addWidget(columns((1, [notifications_panel(self)]), (2, [])))
    self.settings_stack.addWidget(columns((1, [privacy_panel(self)]), (1, [facts_panel(self)]), (1, [])))
    scroller = QScrollArea()
    scroller.setWidgetResizable(True)
    scroller.setFrameShape(QFrame.NoFrame)
    scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroller.setMinimumHeight(120)
    scroller.setStyleSheet("QScrollArea{background:transparent;} QScrollArea > QWidget > QWidget{background:transparent;}")
    scroller.setWidget(self.settings_stack)
    page.content.addWidget(scroller, 1)

    strip_box, strip_body = frame("settingsData", "cyan", "", "storage", header=False)
    data_row = row(spacing=12, margins=(4, 2, 4, 2))
    words = column(spacing=1)
    words.addWidget(label("Game Grave data stays on this PC", "sectionTitle"))
    self.settings_path = ElideLabel(str(core.config_dir()))
    words.addWidget(self.settings_path)
    data_row.addLayout(words, 1)
    buttons = ActionFlow(spacing=8)
    self.settings_open = tool("Open Data Folder", "folder", lambda: open_data_folder(self), tip="Show the folder that holds your Game Grave data")
    self.settings_export = tool("Export Settings", "download", lambda: export_settings(self), tip="Save your preferences and folder lists to a file")
    self.settings_import = tool("Import Settings", "download", lambda: import_settings(self), tip="Load preferences and folder lists from a file")
    self.settings_reset = tool("Reset to Defaults", "undo", lambda: reset_defaults(self), kind="danger", tip="Stage the default preferences")
    for control in (self.settings_open, self.settings_export, self.settings_import, self.settings_reset):
        control.setFixedHeight(32)
        buttons.addWidget(control)
    data_row.addWidget(_widget(buttons), 3)
    version = column(spacing=1)
    version.addWidget(label("Game Grave " + __version__, "detailValue"))
    self.settings_update_note = label("Nothing is contacted until you press Check for Updates.", "caption", wrap=True)
    self.settings_update_note.setMinimumWidth(0)
    self.settings_update_note.setMaximumWidth(300)
    version.addWidget(self.settings_update_note)
    update_buttons = row(spacing=6)
    self.settings_update = tool("Check for Updates", "refresh", lambda: check_updates(self),
                                tip="Ask GitHub whether a newer preview build exists. Nothing is downloaded or installed.")
    self.settings_update_open = tool("Open Updater", "download", lambda: open_updater(self),
                                     tip="Open the Game Grave Updater, or the releases page if it is not installed")
    for control in (self.settings_update, self.settings_update_open):
        control.setFixedHeight(28)
        update_buttons.addWidget(control)
    self.settings_update_open.hide()
    version.addLayout(update_buttons)
    data_row.addLayout(version)
    strip_body.addLayout(data_row)
    page.content.addWidget(strip_box)

    footer = row(spacing=8)
    self.settings_footer = label(FOOTER, "caption", wrap=True)
    self.settings_footer.setMinimumWidth(0)
    self.settings_footer.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    footer.addWidget(self.settings_footer, 1)
    self.settings_cancel = tool("Cancel", "close", lambda: cancel_changes(self), tip="Discard unapplied changes")
    self.settings_apply = tool("Apply Changes", "check", lambda: apply_changes(self), kind="primary", tip="Save these changes to this PC")
    for control in (self.settings_cancel, self.settings_apply):
        control.setFixedHeight(36)
        footer.addWidget(control)
    footer_box = QWidget()
    footer_box.setLayout(footer)
    page.content.addWidget(footer_box)

    page.settings_ready = True
    focus = getattr(self, "_focus_never_touch_rule", None)
    if focus:
        # Graveyard sent the owner here to manage a parent folder rule: open that rule.
        self._focus_never_touch_rule = None
        state.tab = "Protection"
    sync(self)
    if focus:
        for index in range(self.settings_never_list.count()):
            if self.settings_never_list.item(index).text() == focus:
                self.settings_never_list.setCurrentRow(index)
                break
