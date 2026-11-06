"""Old Files controls, scoped drive scans and reviewed individual recycling."""
from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
import uuid

from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QLineEdit, QProgressBar, QTableWidgetItem, QWidget
from shiboken6 import isValid

from core import human_size, is_unchanged, save_settings
from gg_desktop.backend import refresh_graveyard
from gg_desktop.old_files_data import (ScanResult, key, local_drives, make_plan, protected_roots,
    recycle_reviewed, review_reason, scan_files)
from gg_desktop.widgets import button, data_table, label, row

PAGE_SIZE = 500


def message_text(value):
    return "<qt>" + escape(str(value)).replace("\n", "<br>") + "</qt>"


class OldFilesSession(QObject):
    changed = Signal()

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.inventory = window.inventory
        self.result = None
        self.folder = str(window.settings.get("scan_folder", str(Path.home() / "Downloads")))
        self.location, self.full = "", False
        self.busy = False
        self.message = "Choose a folder or drive, then Rescan. Scanning reads file metadata only."
        try:
            if self.inventory.scanned_at:
                plan = make_plan(self.folder, "folder", int(window.settings.get("files_stale_days", 180)),
                                 protected_roots(self.inventory, window.settings))
                try:
                    scanned_at = datetime.strptime(self.inventory.scanned_at, "%Y-%m-%d %H:%M").timestamp()
                except ValueError:
                    scanned_at = 0
                self.result = ScanResult(plan, list(self.inventory.files), scanned_at=scanned_at, origin="PC scan")
                self.message = "Last PC scan results. Rescan to refresh this folder or choose a drive."
        except (OSError, ValueError):
            self.message = "Choose an available folder or drive and Rescan to review its files."

    def task(self, work, finish):
        def run(emit):
            try:
                return work(emit), ""
            except Exception as exc:
                return None, str(exc)[:500] or type(exc).__name__
        def progress(amount, message):
            self.message = message
            self.window.status.setText(message_text("Old Files: " + message))
            self.changed.emit()
        self.window.job(run, lambda packet: finish(*packet), progress=progress)

    def start(self):
        window = self.window
        if self.busy or window.scanning or window.cleaning:
            window.info("Game Grave is busy", "Finish or cancel the current operation first.")
            return
        try:
            root = self.location or self.folder
            mode = "full" if self.location and self.full else "quick" if self.location else "folder"
            days = int(window.settings.get("files_stale_days", 180))
            rules, folder = protected_roots(window.inventory, window.settings), self.folder
        except (OSError, ValueError) as exc:
            window.error("Cannot scan this location", message_text(exc))
            return
        self.busy = window.scanning = True
        window.cancel.clear()
        window.scan_button.setEnabled(False)
        window.cancel_button.setEnabled(True)
        window.progress.setRange(0, 0)
        window.progress.show()
        self.message = "Scanning " + ("the selected drive" if mode == "full" else "selected folders") + ": " + root
        self.changed.emit()
        def finish(result, error):
            canceled = window.cancel.is_set()
            self.busy = window.scanning = False
            window.scan_button.setEnabled(True)
            window.cancel_button.setEnabled(False)
            window.progress.setRange(0, 100)
            window.progress.hide()
            if canceled or error:
                self.message = ("Scan canceled. Previous results retained." if canceled else
                                "Scan failed. Previous results retained. " + error)
            else:
                self.result = result
                self.message = result.summary()
            window.status.setText(message_text("Old Files: " + self.message))
            self.changed.emit()
        def work(emit):
            plan = make_plan(root, mode, days, rules, folder=folder)
            return scan_files(plan, window.cancel.is_set, emit)
        self.task(work, finish)

    def cancel(self):
        if self.busy:
            self.window.cancel.set()
            self.message = "Cancel requested. Previous results will remain available."
            self.changed.emit()


class OldFilesController(QObject):
    def __init__(self, window, page, contents):
        super().__init__(page)
        self.window, self.page = window, page
        state = getattr(window, "_old_files_session", None)
        if state is None or state.inventory is not window.inventory and not state.busy:
            if state is not None:
                state.deleteLater()
            state = window._old_files_session = OldFilesSession(window)
        self.state = state
        configured = str(window.settings.get("scan_folder", state.folder))
        if not state.busy and configured != state.folder:
            state.folder, state.location, state.full = configured, "", False
            state.message = "Folder preference changed. Rescan to refresh it. The table retains the last completed scan."
        self.index, self.shown, self.displayed = 0, [], object()
        self.heading = label("", "subtle", wrap=True)
        self.heading.setTextFormat(Qt.PlainText)
        contents.addWidget(self.heading)
        choose = QWidget()
        choose_row = row()
        choose.setLayout(choose_row)
        choose_row.addWidget(label("Scan location", "caption"))
        self.drives = QComboBox()
        self.drives.setAccessibleName("Old Files scan drive or selected folder")
        choose_row.addWidget(self.drives, 1)
        self.full = QCheckBox("Full scan of selected drive (optional)")
        self.full.setChecked(state.full)
        self.full.setToolTip("Unchecked: Downloads, Documents and your selected folder on this drive. Checked: inspect the selected drive, excluding protected/system locations and linked or offline content.")
        choose_row.addWidget(self.full)
        contents.addWidget(choose)
        actions = QWidget()
        top = row()
        actions.setLayout(top)
        self.choose_folder = button("Change scan folder", self.change_folder)
        self.rescan = button("Rescan", state.start)
        self.refresh = button("Refresh drives", self.refresh_drives)
        self.cancel = button("Cancel scan", state.cancel)
        for widget in (self.choose_folder, self.rescan, self.refresh, self.cancel):
            top.addWidget(widget)
        top.addStretch()
        contents.addWidget(actions)
        self.status = label("", "subtle", wrap=True)
        self.status.setTextFormat(Qt.PlainText)
        contents.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(8)
        contents.addWidget(self.progress)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search file names and paths…")
        self.search.setAccessibleName("Search all Old Files scan results")
        contents.addWidget(self.search)
        self.table = data_table(["FILE", "SIZE", "MODIFIED", "PROTECTION"])
        from PySide6.QtWidgets import QAbstractItemView
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setColumnWidth(0, 350)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 140)
        self.table.setAccessibleName("Old Files results; select up to 200 individual files for separate review")
        self.table.itemDoubleClicked.connect(self.details)
        window.old_files_table = self.table
        contents.addWidget(self.table)
        self.paging = QWidget()
        controls = row()
        self.paging.setLayout(controls)
        self.previous = button("← Previous", lambda: self.change_page(-1))
        self.next = button("Next →", lambda: self.change_page(1))
        self.count = label("", "caption")
        controls.addWidget(self.previous)
        controls.addWidget(self.count, 1, Qt.AlignCenter)
        controls.addWidget(self.next)
        contents.addWidget(self.paging)
        self.recycle = button("Move reviewed individual files to Recycle Bin…", self.remove, kind="danger")
        contents.addWidget(self.recycle)
        self.drives.currentIndexChanged.connect(self.location_changed)
        self.full.toggled.connect(self.location_changed)
        self.search.textChanged.connect(self.filter)
        self.refresh_drives()
        self.shortcuts = []
        for sequence, action in (("F5", state.start), ("Ctrl+F", self.search.setFocus), ("Escape", self.escape),
                                 ("Ctrl+PgDown", lambda: self.change_page(1)), ("Ctrl+PgUp", lambda: self.change_page(-1))):
            shortcut = QShortcut(QKeySequence(sequence), page)
            shortcut.activated.connect(action)
            self.shortcuts.append(shortcut)
        state.changed.connect(self.update)
        self.update()

    def valid(self):
        return isValid(self.page) and self.window.page is self.page

    def refresh_drives(self):
        if self.state.busy:
            return
        previous = self.state.location
        self.drives.blockSignals(True)
        self.drives.clear()
        self.drives.addItem("Selected folder", "")
        try:
            for drive in local_drives():
                self.drives.addItem(drive.label, drive.root)
        except OSError as exc:
            self.window.error("Drive list unavailable", message_text(exc))
        index = self.drives.findData(previous)
        self.drives.setCurrentIndex(max(0, index))
        self.drives.blockSignals(False)
        if index < 0 and previous:
            self.state.location, self.state.full = "", False
            self.full.setChecked(False)
            self.state.message = "The previously selected drive disconnected. Choose an available drive and Rescan."
        self.full.setEnabled(bool(self.drives.currentData()))
        self.update()

    def location_changed(self, *_):
        self.state.location = self.drives.currentData() or ""
        self.state.full = self.full.isChecked() if self.state.location else False
        self.full.setEnabled(bool(self.state.location))
        if not self.state.location and self.full.isChecked():
            self.full.setChecked(False)
        self.state.message = "Scan selection changed. Press Rescan. The table still shows the last completed scan."
        self.update()

    def change_folder(self):
        if self.state.busy or self.window.scanning or self.window.cleaning:
            self.window.info("Game Grave is busy", "Finish or cancel the current operation first.")
            return
        selected = QFileDialog.getExistingDirectory(self.window, "Select ordinary Old Files scan folder", self.state.folder)
        if not selected or not self.valid():
            return
        try:
            make_plan(selected, "folder", int(self.window.settings.get("files_stale_days", 180)),
                      protected_roots(self.window.inventory, self.window.settings))
            settings = dict(self.window.settings)
            settings["scan_folder"] = str(Path(selected).absolute())
            save_settings(settings)
        except (OSError, ValueError) as exc:
            self.window.error("Cannot choose this folder", message_text(exc))
            return
        self.window.settings = settings
        self.state.folder, self.state.location, self.state.full = settings["scan_folder"], "", False
        self.full.blockSignals(True)
        self.full.setChecked(False)
        self.full.blockSignals(False)
        self.refresh_drives()
        self.state.message = "Folder saved. Press Rescan to inspect it. The table still shows the last completed scan."
        self.update()

    def escape(self):
        if self.state.busy:
            self.state.cancel()
        else:
            self.search.clear()

    def filter(self, *_):
        self.index = 0
        self.fill()

    def change_page(self, direction):
        self.index += direction
        self.fill()

    def update(self):
        if not self.valid():
            return
        state = self.state
        if state.result is not self.displayed:
            self.index = 0
            self.displayed = state.result
            self.fill()
        pending = state.location or state.folder
        heading = "Scan selection: " + pending + (" • Full drive scan" if state.full else " • Quick scan" if state.location else " • Folder scan")
        if state.result:
            checked = datetime.fromtimestamp(state.result.scanned_at).strftime("%Y-%m-%d %H:%M") if state.result.scanned_at else "Scan time unavailable"
            heading += "\nShowing: " + state.result.plan.root + " • " + state.result.origin + " • " + checked
        self.heading.setText(heading)
        self.status.setText(state.message)
        self.status.setToolTip("<qt>" + "<br>".join(escape(issue) for issue in state.result.issues) + "</qt>" if state.result and state.result.issues else "")
        self.progress.setVisible(state.busy)
        self.cancel.setEnabled(state.busy and not self.window.cancel.is_set())
        self.cancel.setVisible(state.busy)
        for widget in (self.choose_folder, self.rescan, self.refresh, self.drives):
            widget.setEnabled(not state.busy and not self.window.cleaning)
        self.full.setEnabled(not state.busy and not self.window.cleaning and bool(state.location))
        self.recycle.setEnabled(state.result is not None and not state.busy and not self.window.cleaning)

    def fill(self):
        result = self.state.result
        tokens = self.search.text().casefold().split()
        rows = [file for file in result.files if all(token in file.path.casefold() for token in tokens)] if result else []
        self.index = max(0, min(self.index, max(0, (len(rows) - 1) // PAGE_SIZE)))
        start = self.index * PAGE_SIZE
        self.shown = rows[start:start + PAGE_SIZE]
        self.table.clearSelection()
        self.table.setRowCount(len(self.shown))
        rules = protected_roots(self.window.inventory, self.window.settings)
        for index, file in enumerate(self.shown):
            reason = review_reason(file, result, rules)
            values = (Path(file.path).name, human_size(file.size), datetime.fromtimestamp(file.modified).strftime("%Y-%m-%d"), reason)
            tooltip = "<qt>" + escape(file.path) + "<br>" + escape(reason) + "<br>File age does not establish disuse.</qt>"
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setToolTip(tooltip)
                self.table.setItem(index, column, cell)
        self.previous.setEnabled(self.index > 0)
        self.next.setEnabled(start + PAGE_SIZE < len(rows))
        self.count.setText(f"{start + 1 if rows else 0}–{start + len(self.shown)} of {len(rows):,}")
        self.paging.setVisible(len(rows) > PAGE_SIZE)

    def details(self, *_):
        rows = self.table.selectionModel().selectedRows()
        if rows:
            file = self.shown[rows[0].row()]
            reason = review_reason(file, self.state.result, protected_roots(self.window.inventory, self.window.settings))
            self.window.info("Old File details", message_text(file.path + "\n\n" + human_size(file.size) + "\n" + reason +
                "\n" + ("Unchanged since this scan" if is_unchanged(file) else "Changed or unavailable: Rescan before reviewing") +
                "\n\nAge does not prove disuse. Nothing is recycled by opening these details."))

    def remove(self):
        window, state = self.window, self.state
        if state.busy or window.scanning or window.cleaning:
            window.info("Game Grave is busy", "Finish or cancel the current operation first.")
            return
        selected = [self.shown[i.row()] for i in self.table.selectionModel().selectedRows()]
        if not 1 <= len(selected) <= 200:
            window.info("Choose files", "Select between 1 and 200 individual files.")
            return
        result = state.result
        rules = protected_roots(window.inventory, window.settings)
        if any(review_reason(file, result, rules) != "Reviewable (not proven unused)" for file in selected):
            window.error("Protected items selected", "The selection includes protected or unverified files. No files were moved. Review an ordinary folder or rescan.")
            return
        if not window.confirm("Move selected Old Files to Recycle Bin?",
            message_text(f"Reviewing {len(selected)} specific files from the completed {result.plan.mode} scan:\n{result.plan.root}\n\n" +
            "\n".join(file.path for file in selected[:15]) + (f"\n… and {len(selected) - 15} more selected files." if len(selected) > 15 else "") +
            "\n\nAge does not prove disuse. Every file identity, age, scope and Windows recovery safety check runs again. Recycle Bin may still use disk space."),
            destructive=True):
            return
        if not self.valid() or state.result is not result or window.scanning or window.cleaning:
            return
        # Re-evaluate current protection rules after the modal review.
        rules = protected_roots(window.inventory, window.settings)
        window.cleaning = True
        state.message = "Reviewing the approved individual files through Windows Recycle Bin…"
        state.changed.emit()
        session = "crimson-old-" + uuid.uuid4().hex[:10]
        def finish(outcome, error):
            window.cleaning = False
            if error:
                state.message = "Review could not finish. " + error + " Check Undo Center before retrying."
                window.error("Old Files cleanup blocked", message_text(state.message))
            else:
                result.files = [file for file in result.files if is_unchanged(file)]
                selected_paths = {key(file.path) for file in selected if not is_unchanged(file)}
                window.inventory.files = [file for file in window.inventory.files if key(file.path) not in selected_paths]
                refresh_graveyard(window.inventory, window.settings)
                state.message = (f"{outcome['completed']} file(s) moved to Recycle Bin; {len(outcome['skipped'])} skipped. "
                                 f"{outcome['recovery_warnings']} recovery-record warnings. Recycle Bin may still use disk space.")
                window.info("Old Files review completed", message_text(state.message + ("\n" + "\n".join(outcome["skipped"][:8]) if outcome["skipped"] else "")))
            window.status.setText(message_text("Old Files: " + state.message))
            active = getattr(window.page, "old_files", None)
            if active and isValid(active):
                active.fill()
            state.changed.emit()
        state.task(lambda emit: recycle_reviewed(result, selected, rules, session, emit), finish)
