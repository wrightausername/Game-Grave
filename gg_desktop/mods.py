"""Native Mods controls and hover details, isolated from other screens."""
from __future__ import annotations

from datetime import datetime
from html import escape
import json
import os
from pathlib import Path
import threading
import weakref

from PySide6.QtCore import QObject, QEvent, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QFileDialog, QLabel,
    QGridLayout, QLineEdit, QPlainTextEdit, QTableWidgetItem, QToolTip, QWidget)
from shiboken6 import isValid

from gg_desktop.mod_conflicts import inspect_conflicts
from gg_desktop.mods_data import base_catalog, build_catalog, identity, mod_page, ordinary
from gg_desktop.models import readable_bytes
from gg_desktop.widgets import button, column, data_table, label, row

PAGE_SIZE = 400
MARKERS = {"+": "enabled in saved profile", "-": "disabled in saved profile", "?": "activation unknown"}
DIALOG_STYLE = """
QDialog#modsDialog { background: #080C13; }
QPlainTextEdit { color: #F4F7FC; background: #0E161F; border: 1px solid #2E3A46;
    border-radius: 7px; padding: 10px; selection-background-color: #2E5667; }
"""


def stamp(value):
    return datetime.fromtimestamp(value).astimezone().strftime("%Y-%m-%d %H:%M %Z")


class ModsController(QObject):
    def __init__(self, window, page, table):
        super().__init__(page)
        self.window, self.page, self.table = window, page, table
        self.inventory = window.inventory
        self.catalog = base_catalog(self.inventory)
        self.report = None
        self.finding_index = {}
        self.entry_names = {e.key: e.name for e in self.catalog.entries}
        self.profile_names = {}
        self.closed = threading.Event()
        closed = self.closed
        page.destroyed.connect(lambda: closed.set())
        self.cancel = threading.Event()
        self.busy = False
        self.message = "Reading local mod descriptions and saved profiles…"
        self.index = 0
        self.shown = []
        self.views = []
        self.tools = None
        table.setMouseTracking(True)
        table.viewport().installEventFilter(self)
        table.itemDoubleClicked.connect(lambda *_: self.explain())
        table.setAccessibleName("Mod locations and individual mods; hover for descriptions, F1 for details")
        self.shortcuts = []
        for keys, action in (("F1", self.explain), ("Ctrl+F", self.open_tools),
                             ("Ctrl+PgDown", lambda: self.change_page(1)),
                             ("Ctrl+PgUp", lambda: self.change_page(-1))):
            shortcut = QShortcut(QKeySequence(keys), page)
            shortcut.activated.connect(action)
            self.shortcuts.append(shortcut)

    def valid(self):
        return not self.closed.is_set() and isValid(self.window) and self.window.page is self.page

    def bind(self, contents):
        self.paging = QWidget()
        layout = row()
        self.paging.setLayout(layout)
        self.previous = button("← Previous", lambda: self.change_page(-1))
        self.next = button("Next →", lambda: self.change_page(1))
        self.count = label("", "caption")
        layout.addWidget(self.previous)
        layout.addWidget(self.count, 1, Qt.AlignCenter)
        layout.addWidget(self.next)
        contents.addWidget(self.paging)
        self.fill()
        QTimer.singleShot(0, self.refresh_catalog)

    def task(self, function, finish):
        owner = weakref.ref(self)
        def work(emitter):
            try:
                return function(emitter), ""
            except Exception as exc:
                return None, str(exc)[:500] or type(exc).__name__
        def ready(packet):
            control = owner()
            if control is not None and isValid(control) and control.valid():
                finish(*packet)
        def progress(_amount, message):
            control = owner()
            if control is not None and isValid(control) and control.valid():
                control.message = message
                control.notify(fill=False)
        self.window.job(work, ready, progress=progress)

    def canceled(self):
        return self.closed.is_set() or self.cancel.is_set()

    def refresh_catalog(self):
        if not self.valid() or self.busy:
            return
        self.busy = True
        self.cancel.clear()
        self.message = "Reading local descriptions and saved profiles…"
        self.notify(fill=False)
        def finish(result, error):
            self.busy = False
            if error or self.cancel.is_set():
                self.message = ("Inspection canceled; previous details and report retained." if self.cancel.is_set()
                                else "Inspection failed; previous details retained. " + error)
                self.notify()
                return
            self.catalog, self.report = result
            self.message = self.report.summary()
            self.notify()
        def work(emit):
            catalog = build_catalog(self.inventory, self.canceled)
            emit(0, "Descriptions read; checking saved profile evidence…")
            return catalog, inspect_conflicts(catalog, self.canceled, emit)
        self.task(work, finish)

    def check_conflicts(self):
        if not self.valid() or self.busy:
            return
        self.busy = True
        self.cancel.clear()
        self.message = "Checking enabled mods in each saved profile…"
        self.notify(fill=False)
        def finish(report, error):
            self.busy = False
            if error or self.cancel.is_set():
                self.message = ("Checks canceled; previous report retained." if self.cancel.is_set()
                                else "Checks failed; previous report retained. " + error)
            else:
                self.report = report
                self.message = report.summary()
            self.notify()
        self.task(lambda emit: inspect_conflicts(self.catalog, self.canceled, emit), finish)

    def stop(self):
        if self.busy:
            self.cancel.set()
            self.message = "Cancel requested; retaining the last completed result…"
            self.notify(fill=False)

    def notify(self, fill=True):
        if not self.valid():
            return
        if fill:
            self.finding_index = {}
            self.entry_names = {e.key: e.name for e in self.catalog.entries}
            self.profile_names = {p.key: p.name for p in self.catalog.profiles}
            roots = {e.key: e.root_key for e in self.catalog.entries}
            if self.report:
                for finding in self.report.findings:
                    keys = set(finding.mods) | {roots[k] for k in finding.mods if k in roots}
                    for key in keys:
                        self.finding_index.setdefault(key, []).append(finding)
            self.fill()
        self.views = [v for v in self.views if isValid(v)]
        for view in self.views:
            view.refresh()

    def selected(self):
        rows = self.table.selectionModel().selectedRows()
        index = rows[0].row() if rows else -1
        return self.shown[index] if 0 <= index < len(self.shown) else None

    def fill(self):
        selected = self.selected()
        key = selected.key if selected else ""
        count = len(self.catalog.entries)
        self.index = max(0, min(self.index, max(0, (count - 1) // PAGE_SIZE)))
        start = self.index * PAGE_SIZE
        self.shown = self.catalog.entries[start:start + PAGE_SIZE]
        self.table.setRowCount(len(self.shown))
        for i, entry in enumerate(self.shown):
            location = entry.path if entry.kind == "location" else entry.name + " — " + entry.path
            for col, value in enumerate((location, entry.source, entry.state, readable_bytes(entry.apparent_bytes))):
                cell = QTableWidgetItem(value)
                cell.setToolTip(self.tooltip(entry))
                self.table.setItem(i, col, cell)
        if key:
            picked = next((i for i, entry in enumerate(self.shown) if entry.key == key), -1)
            if picked >= 0:
                self.table.selectRow(picked)
        self.paging.setVisible(count > PAGE_SIZE)
        self.previous.setEnabled(self.index > 0)
        self.next.setEnabled(start + PAGE_SIZE < count)
        self.count.setText(f"{start + 1 if count else 0}–{start + len(self.shown)} of {count} locations and mods")

    def change_page(self, direction):
        if not self.valid():
            return
        self.index += direction
        self.fill()

    def findings(self, entry):
        return self.finding_index.get(entry.key, [])

    def tooltip(self, entry):
        profiles = {p.key: p for p in self.catalog.profiles}
        state = "; ".join(profiles[k].name + ": " + MARKERS.get(v, "unknown") +
                          (" (snapshot older than seven days)" if profiles[k].stale else "")
                          for k, v in list(entry.profiles.items())[:8] if k in profiles)
        findings = self.findings(entry)
        conflicts = ("; ".join(f.kind + " (" + self.profile_names.get(f.profile, "unknown profile") + ")" +
                              (": " + ", ".join(self.entry_names.get(k, "Unknown mod") for k in f.mods if k != entry.key))
                              for f in findings[:4]) if findings else
                     "No findings in the completed checks" if self.report else "No completed check: " + self.message)
        if self.report and self.report.limited:
            conflicts = "Coverage limited. " + conflicts
        return ("<qt><b>" + escape(entry.name) + "</b><p>" + escape(entry.description) + "</p><p>" +
                escape(f"Version: {entry.version} • Author: {entry.author}") + "<br>" + escape(entry.source) + "<br>" +
                escape(state or "Activation not established by a saved profile") + "</p><p>" + escape(conflicts) +
                "<br>Runtime compatibility is unverified. File overlaps may be intentional.</p><p>" +
                escape(" ".join(entry.warnings)) + "<br>" + escape("Metadata: " + entry.metadata_source) +
                "<br>F1 or double-click for full details.</p></qt>")

    def eventFilter(self, watched, event):
        if event.type() == QEvent.ToolTip and watched is self.table.viewport():
            index = self.table.rowAt(event.pos().y())
            if 0 <= index < len(self.shown):
                QToolTip.showText(event.globalPos(), self.tooltip(self.shown[index]), self.table.viewport())
            else:
                QToolTip.hideText()
            return True
        return super().eventFilter(watched, event)

    def explain(self, entry=None):
        if not self.valid():
            return
        entry = entry or self.selected()
        if not entry:
            self.window.info("Choose a mod location", "Select one inventory row. Hover, double-click or press F1 to inspect it.")
            return
        dialog = ModDetails(self, entry.key)
        self.views.append(dialog)
        dialog.show()
        return dialog

    def open_tools(self):
        if not self.valid():
            return
        if self.tools and isValid(self.tools):
            self.tools.show()
            self.tools.raise_()
            self.tools.activateWindow()
            return self.tools
        self.tools = ModTools(self)
        self.views.append(self.tools)
        self.tools.show()
        return self.tools

    def open_folder(self, entry, manager=False):
        if not self.valid() or not entry:
            return
        target = entry.manager_folder if manager else entry.path
        if not target or not ordinary(target, True):
            self.window.info("Folder unavailable", "This folder is missing, unreadable or redirected. Run Scan PC again if its location changed.")
        elif not QDesktopServices.openUrl(QUrl.fromLocalFile(target)):
            self.window.error("Could not open folder", "The system did not accept this folder. " + target)

    def open_page(self, entry):
        if self.valid() and entry and mod_page(entry.page):
            if not QDesktopServices.openUrl(QUrl(entry.page)):
                self.window.error("Could not open mod page", "The system did not accept the source page.")

    def dna(self, entry=None):
        from game_intelligence import build_game_dna
        if not self.valid():
            return
        entry = entry or self.selected()
        game = next((g for g in self.inventory.games if entry and g.key == entry.game_key), None)
        if not game or not ordinary(game.install_path, True):
            self.window.info("Game association unverified", "Select a mod whose manager or installation path matches exactly one scanned game. Scan PC again after changing a manager's game path.")
            return
        records = build_game_dna(self.inventory.steam, self.inventory.other, self.inventory.mods, self.inventory.saves)["games"]
        index = next((i for i, record in enumerate(records) if identity(record["install_path"]) == identity(game.install_path)
                      and record["launcher"] in (game.launcher, *game.claimed_by)), -1)
        if index < 0:
            self.window.info("Game association unavailable", "The associated installation has no Game DNA record. Run Scan PC again.")
            return
        self.window.navigate("Game DNA")
        chooser = self.window.page.findChild(QComboBox)
        if chooser:
            chooser.setCurrentIndex(index)

    def export(self, parent):
        if not self.valid() or not self.report:
            return
        report, catalog = self.report, self.catalog
        filename, _ = QFileDialog.getSaveFileName(parent, "Export Mod Radar report to a new file", "Mod-Radar-Report.json", "JSON report (*.json)")
        if not filename or not self.valid() or not isValid(parent):
            return
        try:
            target = Path(filename)
            if not target.suffix:
                target = target.with_suffix(".json")
            if not ordinary(target.parent, True):
                raise ValueError("Choose an existing ordinary destination folder.")
            protected = [e.path for e in catalog.entries] + [e.manager_folder for e in catalog.entries if e.manager_folder]
            protected += [g.install_path for g in self.inventory.games]
            protected += [str(getattr(s, "path", "")) for s in self.inventory.saves]
            normalized = identity(target)
            for folder in protected:
                root = identity(folder)
                if root and (normalized == root or normalized.startswith(root.rstrip("/\\") + os.sep)):
                    raise ValueError("Save reports outside game, mod, manager and save locations.")
            payload = json.dumps(report.export(catalog), ensure_ascii=False, indent=2).encode("utf-8")
            with target.open("xb") as stream:
                stream.write(payload)
            self.window.info("Report exported", str(target) + "\nThe report contains local paths, descriptions and saved-profile evidence.")
        except FileExistsError:
            self.window.info("Choose a new report filename", "That file already exists. Choose a new name to keep both reports.")
        except (OSError, ValueError, TypeError) as exc:
            self.window.error("Could not export report", str(exc))


class ModDetails(QDialog):
    def __init__(self, control, key):
        super().__init__(control.page)
        self.control, self.key = control, key
        self.setObjectName("modsDialog")
        self.setStyleSheet(DIALOG_STYLE)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle("Mod Radar — source and compatibility details")
        self.resize(min(820, control.window.width() - 60), min(680, control.window.height() - 80))
        layout = column(margins=(18, 18, 18, 18))
        self.setLayout(layout)
        self.title = label("", "sectionTitle", wrap=True)
        self.title.setTextFormat(Qt.PlainText)
        layout.addWidget(self.title)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setAccessibleName("Mod description, saved profiles and conflict evidence")
        layout.addWidget(self.text, 1)
        controls = row()
        self.folder = button("Open folder", lambda: control.open_folder(self.entry()))
        self.manager = button("Manager folder", lambda: control.open_folder(self.entry(), True))
        self.web = button("Mod page", lambda: control.open_page(self.entry()))
        self.dna = button("Game DNA", lambda: control.dna(self.entry()))
        for b in (self.folder, self.manager, self.web, self.dna):
            controls.addWidget(b)
        controls.addWidget(button("Copy path", self.copy))
        layout.addLayout(controls)
        layout.addWidget(button("Close", self.close))
        self.refresh()

    def entry(self):
        return next((e for e in self.control.catalog.entries if e.key == self.key), None)

    def copy(self):
        if self.control.valid() and self.entry():
            QApplication.clipboard().setText(self.entry().path)

    def refresh(self):
        entry = self.entry()
        if not entry:
            self.close()
            return
        control = self.control
        profiles = {p.key: p for p in control.catalog.profiles}
        text = [entry.description, "", "LOCATION: " + entry.path, "SOURCE: " + entry.source,
                "VERSION: " + entry.version, "AUTHOR: " + entry.author, "EVIDENCE: " + entry.metadata_source,
                "STATE: " + entry.state, "", "SAVED PROFILES"]
        for key, marker in entry.profiles.items():
            profile = profiles.get(key)
            if profile:
                text += [profile.name + ": " + MARKERS.get(marker, "unknown") +
                         ("; selected at inspection" if profile.selected else "") + ("; stale snapshot" if profile.stale else ""), profile.source]
        if not entry.profiles:
            text.append("No activation state has been established for this location.")
        if entry.dependencies:
            text += ["", "DECLARED REQUIREMENTS"]
            text += [d.name + " " + d.version + (" (optional)" if d.optional else " (incompatible)" if d.incompatible else "") for d in entry.dependencies]
        text += ["", "COMPATIBILITY EVIDENCE"]
        if control.report:
            text += ["Checked: " + stamp(control.report.checked_at), control.report.summary()]
            for finding in control.findings(entry):
                profile = profiles.get(finding.profile)
                names = [e.name for e in control.catalog.entries if e.key in finding.mods]
                text += ["", finding.kind + " — " + (profile.name if profile else "Unknown profile"),
                         " / ".join(names), finding.detail, *finding.paths]
            if not control.findings(entry):
                text.append("No findings involve this entry in the completed checks. This is not a runtime compatibility verdict.")
            text += ["", "COVERAGE NOTES", *control.report.warnings]
        else:
            text += [control.message, "No completed compatibility report is available."]
        text += [*entry.warnings, "", "All managed assets remain protected. No unused status or deletion safety is inferred."]
        scroll = self.text.verticalScrollBar().value()
        self.title.setText(entry.name)
        self.text.setPlainText("\n".join(text))
        self.text.verticalScrollBar().setValue(scroll)
        self.folder.setEnabled(ordinary(entry.path, True))
        self.manager.setEnabled(bool(entry.manager_folder) and ordinary(entry.manager_folder, True))
        self.web.setEnabled(bool(mod_page(entry.page)))
        self.dna.setEnabled(bool(entry.game_key))


class ModTools(QDialog):
    def __init__(self, control):
        super().__init__(control.page)
        self.control, self.index, self.shown = control, 0, []
        self.setObjectName("modsDialog")
        self.setStyleSheet(DIALOG_STYLE)
        self.profile_keys = None
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle("Mod Radar tools")
        self.resize(min(1060, control.window.width() - 60), min(760, control.window.height() - 70))
        layout = column(margins=(18, 18, 18, 18))
        self.setLayout(layout)
        layout.addWidget(label("MOD RADAR", "sectionTitle"))
        self.status = label("", "subtle", wrap=True)
        self.status.setTextFormat(Qt.PlainText)
        layout.addWidget(self.status)
        filters = row()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search mods, descriptions, authors, paths or findings…")
        self.search.setAccessibleName("Search all detected mods")
        self.profiles = QComboBox()
        self.profiles.setAccessibleName("Filter by saved mod profile")
        filters.addWidget(self.search, 1)
        filters.addWidget(self.profiles)
        layout.addLayout(filters)
        self.table = data_table(["MOD / LOCATION", "SAVED STATE", "SOURCE", "VERSION", "FINDINGS"])
        self.table.setColumnWidth(0, 260)
        self.table.setColumnWidth(1, 230)
        self.table.setColumnWidth(2, 130)
        self.table.setColumnWidth(3, 90)
        self.table.itemDoubleClicked.connect(lambda *_: control.explain(self.selected()))
        layout.addWidget(self.table, 1)
        paging = row()
        self.previous = button("← Previous", lambda: self.change_page(-1))
        self.next = button("Next →", lambda: self.change_page(1))
        self.count = label("", "caption")
        paging.addWidget(self.previous)
        paging.addWidget(self.count, 1, Qt.AlignCenter)
        paging.addWidget(self.next)
        layout.addLayout(paging)
        actions = QGridLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(10)
        self.details = button("Inspect selected", lambda: control.explain(self.selected()))
        self.folder = button("Open folder", lambda: control.open_folder(self.selected()))
        self.refresh_button = button("Refresh details", control.refresh_catalog)
        self.check_button = button("Check conflicts", control.check_conflicts, kind="primary")
        self.cancel_button = button("Cancel checks", control.stop)
        self.export_button = button("Export report…", lambda: control.export(self))
        for index, b in enumerate((self.details, self.folder, self.refresh_button, self.check_button, self.cancel_button, self.export_button)):
            actions.addWidget(b, index // 3, index % 3)
        layout.addLayout(actions)
        layout.addWidget(button("Close", self.close))
        self.search.textChanged.connect(self.filter)
        self.profiles.currentIndexChanged.connect(self.filter)
        self.table.itemSelectionChanged.connect(self.selection_changed)
        self.refresh()

    def selection_changed(self):
        selected = self.selected()
        self.details.setEnabled(selected is not None)
        self.folder.setEnabled(bool(selected) and ordinary(selected.path, True))

    def selected(self):
        rows = self.table.selectionModel().selectedRows()
        index = rows[0].row() if rows else -1
        return self.shown[index] if 0 <= index < len(self.shown) else None

    def filter(self, *_):
        self.index = 0
        self.fill()

    def change_page(self, direction):
        self.index += direction
        self.fill()

    def fill(self):
        previous = self.selected()
        query = self.search.text().casefold().split()
        profile_key = self.profiles.currentData()
        rows = []
        for entry in self.control.catalog.entries:
            findings = self.control.findings(entry)
            haystack = " ".join((entry.name, entry.path, entry.description, entry.source, entry.author,
                                 entry.version, *[f.kind for f in findings])).casefold()
            if all(token in haystack for token in query) and (not profile_key or profile_key in entry.profiles):
                rows.append(entry)
        self.index = max(0, min(self.index, max(0, (len(rows) - 1) // PAGE_SIZE)))
        start = self.index * PAGE_SIZE
        self.shown = rows[start:start + PAGE_SIZE]
        self.table.setRowCount(len(self.shown))
        for i, entry in enumerate(self.shown):
            findings = [f for f in self.control.findings(entry) if not profile_key or f.profile == profile_key]
            state = MARKERS.get(entry.profiles.get(profile_key), "unknown") if profile_key else entry.state
            values = (entry.name, state, entry.source, entry.version, str(len(findings)))
            for col, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setToolTip(self.control.tooltip(entry))
                self.table.setItem(i, col, cell)
        if self.shown:
            self.table.selectRow(next((i for i, e in enumerate(self.shown) if previous and e.key == previous.key), 0))
        self.details.setEnabled(bool(self.shown))
        selected = self.selected()
        self.folder.setEnabled(bool(selected) and ordinary(selected.path, True))
        self.previous.setEnabled(self.index > 0)
        self.next.setEnabled(start + PAGE_SIZE < len(rows))
        self.count.setText(f"{start + 1 if rows else 0}–{start + len(self.shown)} of {len(rows)}")

    def refresh(self):
        control = self.control
        keys = tuple((p.key, p.name) for p in control.catalog.profiles)
        if keys != self.profile_keys:
            previous = self.profiles.currentData()
            self.profiles.blockSignals(True)
            self.profiles.clear()
            self.profiles.addItem("All saved profiles / locations", "")
            for profile in control.catalog.profiles:
                self.profiles.addItem(profile.name + " • " + profile.manager, profile.key)
            self.profiles.setCurrentIndex(max(0, self.profiles.findData(previous)))
            self.profiles.blockSignals(False)
            self.profile_keys = keys
        self.status.setText(control.message + ("\nLast completed check: " + stamp(control.report.checked_at) if control.report else ""))
        self.refresh_button.setEnabled(not control.busy)
        self.check_button.setEnabled(not control.busy)
        self.cancel_button.setEnabled(control.busy and not control.cancel.is_set())
        self.export_button.setEnabled(control.report is not None)
        self.fill()
