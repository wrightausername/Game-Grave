"""Connect the recovered photo layouts to the completed functional controllers."""
from __future__ import annotations

from html import escape
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QObject, QEvent, Qt, QTimer, QSignalBlocker
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QLabel, QListWidgetItem, QPushButton, QSplitter, QTableWidget, QWidget
from shiboken6 import isValid

from gg_desktop.games import GamesController
from gg_desktop.mods import ModsController
from gg_desktop.old_files import OldFilesController
from gg_desktop.reference_library import LibraryScreens, _widget, destroy_layout
from gg_desktop.reference_overview import OverviewScreens
from gg_desktop.library_models import ModView
from gg_desktop.reference_widgets import CoverArt, MetricStrip, detail_line, detail_section, icon, tool
from gg_desktop.widgets import column, label, row
from core import human_size
from gg_desktop.library_models import file_kind


class PhotoGameActions(GamesController):
    def selected(self):
        return self.window._current_game()

    def fill(self, *_, **__):
        if self._valid():
            self.window.artwork.retry()
            self.window._fill_games()

    def details(self):
        if self._valid():
            self.window._game_details()

    def remember(self, game, art):
        self.window.artwork.publish(game, art)
        self.window.game_grid.viewport().update()
        self.details()

    def load_visible_artwork(self):
        if self._valid():
            self.window.artwork.retry()
            self.window.game_grid.viewport().update()
            self.details()

    def show_dna(self, game):
        self.current(game)
        self.window._pending_dna_game_key = game.key
        self.window.navigate("Game DNA")


class PhotoMods(ModsController):
    def notify(self, fill=True):
        super().notify(fill)
        if self.valid() and hasattr(self.window, "mod_details"):
            self.window._photo_mod_catalog(self)


class DrivePicker(QComboBox):
    def __init__(self, refresh):
        super().__init__()
        self.refresh = refresh

    def showPopup(self):
        self.refresh()
        super().showPopup()


class ResponsiveInspector(QObject):
    def __init__(self, page, splitter):
        super().__init__(page)
        while not isinstance(splitter, QSplitter):
            splitter = splitter.parentWidget()
        self.page, self.splitter = page, splitter
        self.inspector = splitter.widget(1)
        self.dialog = None
        self.toggle = tool("Details", "list", self.open)
        self.toggle.setParent(page.body)
        self.toggle.setFixedSize(85, 28)
        page.viewport().installEventFilter(self)
        self.sync()

    def eventFilter(self, target, event):
        if event.type() == QEvent.Resize:
            self.sync()
        return False

    def sync(self):
        narrow = self.page.viewport().width() < 900
        if not self.dialog:
            self.inspector.setVisible(not narrow)
        self.toggle.setVisible(narrow)
        self.toggle.move(max(8, self.page.viewport().width() - 98), 10)
        self.toggle.raise_()

    def open(self):
        if self.dialog:
            self.dialog.raise_()
            return
        dialog = self.dialog = QDialog(self.page)
        dialog.setWindowTitle("Selected item details")
        dialog.setStyleSheet("QDialog { background:#020609; }")
        dialog.resize(350, min(650, self.page.window().height() - 60))
        layout = column(margins=(8, 8, 8, 8))
        dialog.setLayout(layout)
        layout.addWidget(self.inspector)
        self.inspector.show()
        layout.addWidget(tool("Close", "close", dialog.accept))
        def finished(_):
            self.dialog = None
            if isValid(self.splitter) and isValid(self.inspector):
                self.splitter.addWidget(self.inspector)
                self.sync()
            dialog.deleteLater()
        dialog.finished.connect(finished)
        dialog.show()


class PhotoIntegration:
    def _game_details(self, *_):
        LibraryScreens._game_details(self)
        control = getattr(self.page, "games", None)
        game = self._current_game()
        if control and game:
            for play in self.game_details.findChildren(QPushButton):
                if play.text() == "Play":
                    play.setEnabled("open_folder" in game.capabilities)

    def _photo_game_dna(self, game):
        self._pending_dna_game_key = game.key
        self.navigate("Game DNA")

    def games_page(self):
        LibraryScreens.games_page(self)
        self.game_table = self.game_grid
        self.game_count.hide()
        self.game_artwork_status.parentWidget().hide()
        self.page.games = PhotoGameActions(self, self.page)
        self.game_grid.setContextMenuPolicy(Qt.CustomContextMenu)
        self.game_grid.customContextMenuRequested.connect(lambda point: self.page.games.options(
            self._current_game(), self.game_grid.viewport().mapToGlobal(point)) if self._current_game() else None)
        self._game_details()
        self.page.photo_inspector = ResponsiveInspector(self.page, self.game_details.parentWidget().parentWidget())

    def _launch_game(self, game):
        self.page.games.launch(game)

    def _steam_uninstall(self, game):
        if self.current_route == "Games" and hasattr(self.page, "games"):
            self.page.games.uninstall(game)

    def _reload_game_artwork(self):
        if hasattr(self.page, "games"):
            self.page.games.download_artwork(tuple(self._shown_games), missing_only=True)

    def mods_page(self):
        LibraryScreens.mods_page(self)
        page = self.page
        holder = QWidget(page)
        layout = column()
        holder.setLayout(layout)
        table = QTableWidget(0, 4)
        layout.addWidget(table)
        holder.hide()
        control = PhotoMods(self, page, table)
        page.mods = control
        control.bind(layout)
        self.mod_table.itemDoubleClicked.connect(lambda *_: self._photo_mod_explain())
        self._photo_mod_catalog(control)
        page.photo_inspector = ResponsiveInspector(page, self.mod_details.parentWidget().parentWidget())

    def _photo_mod_catalog(self, control):
        games = {g.key: g.name for g in self.inventory.games}
        views = []
        for entry in control.catalog.entries:
            record = SimpleNamespace(path=entry.path, name=entry.name, source=entry.source,
                status=entry.state, apparent_bytes=entry.apparent_bytes, file_count="Unknown",
                indicators=(entry.metadata_source,), advice=entry.description, catalog_entry=entry)
            views.append(ModView(record, entry.name, games.get(entry.game_key, "Unverified"), entry.source,
                                 entry.version, entry.description, entry.apparent_bytes))
        self._mod_views = views
        previous = self.mod_game_filters.currentItem()
        selected = previous.data(Qt.UserRole) if previous else "All Games"
        counts = Counter(view.game for view in views)
        with QSignalBlocker(self.mod_game_filters):
            self.mod_game_filters.clear()
            for name, count in [("All Games", len(views)), *sorted(counts.items())]:
                item = QListWidgetItem(icon("mods", "#e15e78", 18), f"{name} ({count})")
                item.setData(Qt.UserRole, name)
                self.mod_game_filters.addItem(item)
                if name == selected:
                    self.mod_game_filters.setCurrentItem(item)
            if self.mod_game_filters.currentRow() < 0:
                self.mod_game_filters.setCurrentRow(0)
        managers = Counter(view.manager for view in views)
        for checkbox in self.mod_manager_checks:
            manager = checkbox.property("manager")
            checkbox.setText(f"{manager} ({managers[manager]})")
        metrics = self.page.findChild(MetricStrip)
        individuals = [entry for entry in control.catalog.entries if entry.kind == "mod"]
        metrics.set_value(0, len(individuals) if individuals else len(control.catalog.entries), "Total Mods" if individuals else "Mod Locations")
        metrics.set_value(1, sum(any(marker == "+" for marker in entry.profiles.values()) for entry in individuals), "Enabled (saved)")
        if control.report:
            metrics.set_value(3, len(control.report.findings), "Findings · partial" if control.report.limited else "Conflict Findings")
        self._fill_mods(requested_page=self.mod_pager.page)

    def _fill_mods(self, *args, **kwargs):
        if not hasattr(self, "mod_table") or self.current_route != "Mods":
            return
        current = self.mod_table.currentRow()
        prior = self._shown_mods[current].record.path if 0 <= current < len(getattr(self, "_shown_mods", [])) else None
        LibraryScreens._fill_mods(self, *args, **kwargs)
        if prior:
            selected = next((index for index, view in enumerate(self._shown_mods) if view.record.path == prior), -1)
            if selected >= 0:
                self.mod_table.selectRow(selected)
        control = getattr(self.page, "mods", None)
        if control:
            for index, view in enumerate(self._shown_mods):
                entry = getattr(view.record, "catalog_entry", None)
                if entry:
                    for col in range(self.mod_table.columnCount()):
                        cell = self.mod_table.item(index, col)
                        if cell:
                            cell.setToolTip(control.tooltip(entry))

    def _mod_details(self):
        control = getattr(self.page, "mods", None)
        index = self.mod_table.currentRow()
        view = self._shown_mods[index] if 0 <= index < len(getattr(self, "_shown_mods", [])) else None
        entry = getattr(view.record, "catalog_entry", None) if view else None
        if not entry or not control:
            return LibraryScreens._mod_details(self)
        contents = self.mod_details.content
        destroy_layout(contents)
        contents.addWidget(CoverArt(view.game if view.game != "Unverified" else entry.name, height=84))
        title = label(entry.name, "detailTitle", wrap=True)
        title.setTextFormat(Qt.PlainText)
        contents.addWidget(title)
        description = label(entry.description, "subtle", wrap=True)
        description.setTextFormat(Qt.PlainText)
        contents.addWidget(description)
        for symbol, title, value in (("game", "Game", view.game), ("mods", "Manager", entry.source),
            ("file", "Version", entry.version), ("help", "Author", entry.author), ("folder", "Location", entry.path)):
            detail_line(contents, symbol, title, value)
        contents.addWidget(tool("Open Folder", "folder", lambda: control.open_folder(entry), kind="primary"))
        actions = row(spacing=4)
        actions.addWidget(tool("Details", "file", lambda: control.explain(entry)))
        actions.addWidget(tool("Mod Page", "search", lambda: control.open_page(entry)))
        actions.addWidget(tool("Manager", "mods", lambda: control.open_folder(entry, True)))
        contents.addWidget(_widget(actions))
        detail_section(contents, "Saved Profile Evidence")
        contents.addWidget(label(entry.state, "subtle", wrap=True))
        detail_section(contents, "Dependencies & Conflicts")
        findings = control.findings(entry)
        for finding in findings[:4]:
            text = label(finding.kind + ": " + finding.detail, "caption", wrap=True)
            text.setTextFormat(Qt.PlainText)
            contents.addWidget(text)
        if not findings:
            contents.addWidget(label("No findings in the completed checks. Runtime compatibility is unverified." if control.report
                                    else "Checks pending. Runtime compatibility is unverified.", "caption", wrap=True))
        contents.addWidget(tool("Open Mod Radar Tools", "radio", control.open_tools))
        contents.addStretch()

    def _photo_mod_explain(self):
        index = self.mod_table.currentRow()
        if 0 <= index < len(self._shown_mods):
            entry = getattr(self._shown_mods[index].record, "catalog_entry", None)
            if entry:
                self.page.mods.explain(entry)

    def _set_mod_tab(self, name):
        self._mod_tab = "Library" if name in {"Conflicts", "Profiles", "Load Order"} else name
        self._fill_mods()
        if name in {"Conflicts", "Profiles", "Load Order"} and hasattr(self.page, "mods"):
            self.page.mods.open_tools()

    def _launch_classic_tools(self):
        if self.current_route == "Mods" and hasattr(self.page, "mods"):
            self.page.mods.open_tools()
            return
        self.navigate("More Tools")

    def old_files_page(self):
        LibraryScreens.old_files_page(self)
        page = self.page
        page.content.itemAt(0).widget().setFixedHeight(74)
        self.old_search.hide()  # The photo uses the global search above this workspace.
        self.old_age_controls[0].hide()
        holder = QWidget(page)
        contents = column()
        holder.setLayout(contents)
        holder.hide()
        page.old_files = OldFilesController(self, page, contents)
        control = page.old_files
        for shortcut in control.shortcuts:
            shortcut.setEnabled(False)
        page.photo_search_shortcut = QShortcut(QKeySequence("Ctrl+F"), page)
        page.photo_search_shortcut.activated.connect(self.global_search.setFocus)
        page.photo_page_shortcuts = []
        for sequence, direction in (("Ctrl+PgDown", 1), ("Ctrl+PgUp", -1)):
            shortcut = QShortcut(QKeySequence(sequence), page)
            shortcut.activated.connect(lambda direction=direction: self._fill_old_files(requested_page=self.old_pager.page + direction))
            page.photo_page_shortcuts.append(shortcut)
        filters = self.old_filters.layout()
        # The location selector replaces the old textual location line.
        filters.itemAt(2).widget().hide()
        for index in range(filters.count()):
            widget = filters.itemAt(index).widget()
            if isinstance(widget, QLabel) and widget.text().startswith("Scan includes files"):
                widget.hide()
        self.photo_drives = DrivePicker(self._refresh_photo_drives)
        self.photo_drives.setAccessibleName("Old Files scan drive or selected folder")
        self.photo_drives.setToolTip("Choose a scan drive. Opening this list refreshes connected drives.")
        for index in range(control.drives.count()):
            self.photo_drives.addItem(control.drives.itemText(index), control.drives.itemData(index))
        self.photo_drives.setCurrentIndex(control.drives.currentIndex())
        filters.insertWidget(3, self.photo_drives)
        self.photo_full = QCheckBox("Full scan (optional)")
        self.photo_full.setChecked(control.state.full)
        self.photo_full.setEnabled(bool(self.photo_drives.currentData()))
        filters.insertWidget(4, self.photo_full)
        self.photo_drives.currentIndexChanged.connect(lambda index: self._photo_choose_drive(index))
        self.photo_full.toggled.connect(control.full.setChecked)
        self.photo_cancel = tool("Cancel Scan", "close", control.state.cancel)
        filters.insertWidget(filters.count() - 1, self.photo_cancel)
        control.state.changed.connect(lambda: self._photo_old_changed(page) if isValid(page) and self.page is page else None)
        self._photo_old_changed(page)
        page.photo_inspector = ResponsiveInspector(page, self.old_details.parentWidget().parentWidget())

    def _refresh_photo_drives(self):
        control = self.page.old_files
        control.refresh_drives()
        with QSignalBlocker(self.photo_drives):
            self.photo_drives.clear()
            for index in range(control.drives.count()):
                self.photo_drives.addItem(control.drives.itemText(index), control.drives.itemData(index))
            self.photo_drives.setCurrentIndex(control.drives.currentIndex())
        self.photo_full.setChecked(control.state.full)
        self._photo_old_changed(self.page)

    def _photo_choose_drive(self, index):
        control = self.page.old_files
        control.drives.setCurrentIndex(index)
        self.photo_full.setEnabled(bool(control.drives.currentData()))

    def _photo_old_changed(self, page):
        if not isValid(page) or self.page is not page:
            return
        state = page.old_files.state
        self.photo_cancel.setVisible(state.busy)
        self.photo_drives.setEnabled(not state.busy and not self.cleaning)
        self.photo_full.setEnabled(not state.busy and bool(state.location))
        if state.result:
            self._old_source = list(state.result.files)
            self._old_root, self._old_days = state.result.plan.root, state.result.plan.days
            metrics = page.findChild(MetricStrip)
            metrics.set_value(0, f"{len(self._old_source):,}")
            metrics.set_value(1, human_size(sum(file.size for file in self._old_source)))
            downloads = sum(file_kind(file.path) in {"Archives", "Installers"} for file in self._old_source)
            metrics.set_value(4, downloads)
            metrics.set_value(5, len(self._old_source) - downloads)
            metrics.setToolTip(f"{state.result.plan.mode.capitalize()} scan: {state.result.plan.root}\n{state.result.summary()}")
        self._fill_old_files()
        self.old_notice.setText(state.message)
        self.old_notice.setTextFormat(Qt.PlainText)
        self.old_notice.setVisible(state.busy or bool(state.result and state.result.limited) or "failed" in state.message.lower())

    def _old_scan(self):
        if hasattr(self.page, "old_files"):
            self.page.old_files.state.days_override = next((c.property("days") for c in self.old_age_controls if c.isChecked()), None)
            self.page.old_files.state.start()

    def _choose_scan_folder(self):
        if self.current_route == "Old Files" and hasattr(self.page, "old_files"):
            self.page.old_files.change_folder()
            self._refresh_photo_drives()
            return
        from gg_desktop.reference_screens import ScreenMethods
        ScreenMethods._choose_scan_folder(self)

    def _recycle_old_selected(self):
        if hasattr(self.page, "old_files"):
            self.page.old_files.remove_files(self._selected_old())

    def _add_old_to_graveyard(self):
        from dataclasses import asdict
        from core import save_settings
        selected = self._selected_old()
        if not selected:
            self.info("Choose files", "Check the individual files to add for protected review.")
            return
        values = {row["path"]: row for row in self.settings.get("manual_review_files", []) if isinstance(row, dict) and "path" in row}
        for file in selected:
            values[file.path] = asdict(file)
        if len(values) > 1000:
            self.error("Review list full", "Review the existing items before adding more paths.")
            return
        updated = dict(self.settings, manual_review_files=list(values.values()))
        try:
            save_settings(updated)
        except OSError as exc:
            self.error("Review list not saved", str(exc))
            return
        self.settings = updated
        self._merge_manual_reviews()
        self.info("Added to Graveyard review", f"{len(selected)} paths added for review. No files were moved or removed.")

    def _merge_manual_reviews(self):
        from core import OldFile, is_unchanged
        from graveyard import GraveyardEntry
        seen = {entry.path for entry in self.inventory.graveyard}
        for row in self.settings.get("manual_review_files", [])[:1000]:
            if not isinstance(row, dict):
                continue
            try:
                file = OldFile(**{key: row[key] for key in ("path", "size", "modified", "device", "inode", "modified_ns", "hardlinks")})
                if file.path in seen or not is_unchanged(file):
                    continue
                self.inventory.graveyard.append(GraveyardEntry(
                    key="manual:" + file.path, name=Path(file.path).name, path=file.path,
                    category="Manual review", apparent_bytes=file.size, age_days=0,
                    relationship="Explicitly selected in Old Files", finding="Manually added for protected review. Age and filename do not establish disuse.",
                    protection="Protected manual review; use the reviewed Old Files action", can_recycle=False, old_file=file))
                seen.add(file.path)
            except (KeyError, TypeError, ValueError, OSError):
                continue

    def graveyard_page(self):
        from gg_desktop.recovery_screens import RecoveryScreens
        self._merge_manual_reviews()
        RecoveryScreens.graveyard_page(self)

    def overview_page(self):
        OverviewScreens.overview_page(self)
        from gg_desktop.overview import OverviewController
        from gg_desktop.widgets import StorageRing
        control = self.page.overview = OverviewController(self, self.page)
        for shortcut in control.shortcuts:
            shortcut.setEnabled(False)
        disk, summary = StorageRing(), QLabel()
        disk.hide()
        summary.hide()
        control.bind_storage(disk, summary)
        self.overview_ring.installEventFilter(control)
        control.targets[self.overview_ring] = control.storage_details
        self.overview_ring.setCursor(Qt.PointingHandCursor)
        self.overview_ring.setToolTip("Open live system-drive details")
        QTimer.singleShot(0, control.refresh_storage)

    def _sync_scan_controls(self):
        self.scan_button.setEnabled(not self.scanning and not self.cleaning)
        self.cancel_button.setEnabled(self.scanning and not self.cancel.is_set())
        if self.current_route == "Overview" and hasattr(self, "overview_scan_status"):
            self.overview_scan_status.setText(self.status.text())
            self.overview_cancel.setVisible(self.scanning)

    def _scan_current_route(self):
        if self.current_route == "Old Files" and hasattr(self.page, "old_files"):
            self._old_scan()
        else:
            self.start_scan()

    def _escape_current_route(self):
        if self.scanning:
            self.cancel_scan()
        else:
            self.global_search.clear()
