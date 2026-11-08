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
        from gg_desktop.games_page import GamesScreens
        GamesScreens._game_details(self)

    def _photo_game_dna(self, game):
        self._pending_dna_game_key = game.key
        self.navigate("Game DNA")

    def games_page(self):
        from gg_desktop.games_page import GamesScreens
        GamesScreens.games_page(self)

    def _fill_games(self, *_):
        from gg_desktop.games_page import GamesScreens
        GamesScreens._fill_games(self)

    def _toggle_favorite(self, game):
        from gg_desktop.games_page import GamesScreens
        GamesScreens._toggle_favorite(self, game)

    def _update_game_artwork_status(self):
        from gg_desktop.games_page import GamesScreens
        GamesScreens._update_game_artwork_status(self)

    def _steam_game_action(self, game, action):
        self.page.games.launcher_action(game, action)

    def _launch_game(self, game):
        self.page.games.launch(game)

    def _steam_uninstall(self, game):
        if self.current_route == "Games" and hasattr(self.page, "games"):
            self.page.games.launcher_action(game, "uninstall")

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
        from gg_desktop import mods_page
        mods_page.build(self, control)
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
        from gg_desktop import mods_page
        mods_page.catalog_changed(self, control)
        self._fill_mods(requested_page=self.mod_pager.page)

    def _fill_mods(self, *args, **kwargs):
        from gg_desktop import mods_page
        mods_page.fill(self, *args, **kwargs)

    def _mod_details(self):
        from gg_desktop import mods_page
        mods_page.details(self)

    def _mod_selection_count(self, *_):
        from gg_desktop import mods_page
        mods_page.selection_count(self)

    def _photo_mod_explain(self):
        from gg_desktop import mods_page
        mods_page.activate(self)

    def _set_mod_tab(self, name):
        from gg_desktop import mods_page
        mods_page.set_tab(self, name)

    def _launch_classic_tools(self):
        if self.current_route == "Mods" and hasattr(self.page, "mods"):
            self.page.mods.open_tools()
            return
        self.navigate("More Tools")

    def other_storage_page(self):
        from gg_desktop import other_storage_page
        other_storage_page.build(self)

    def _scan_other_storage(self):
        from gg_desktop import other_storage_page
        other_storage_page.scan(self)

    def _fill_storage(self, *args, requested_page=0, **kwargs):
        from gg_desktop import other_storage_page
        other_storage_page.fill(self, *args, requested_page=requested_page, **kwargs)

    def _set_storage_tab(self, name):
        from gg_desktop import other_storage_page
        other_storage_page.set_tab(self, name)

    def _selected_storage(self):
        from gg_desktop import other_storage_page
        return other_storage_page.checked_entries(self)

    def _storage_selection_count(self, *_):
        from gg_desktop import other_storage_page
        other_storage_page.selection_count(self)

    def _storage_details(self):
        from gg_desktop import other_storage_page
        other_storage_page.details(self)

    def _watch_storage(self):
        from gg_desktop import other_storage_page
        other_storage_page.add_to_graveyard(self)

    def _review_storage(self):
        from gg_desktop import other_storage_page
        other_storage_page.delete_selected(self)

    def captures_page(self):
        from gg_desktop import captures_page
        captures_page.build(self)

    def _request_capture_preview(self, index):
        from gg_desktop import captures_page
        captures_page.request_preview(self, index)

    def old_files_page(self):
        from gg_desktop import old_files_page
        old_files_page.build(self)

    def _refresh_photo_drives(self):
        from gg_desktop import old_files_page
        old_files_page.refresh_drives(self)

    def _photo_choose_drive(self, index):
        from gg_desktop import old_files_page
        old_files_page.choose_drive(self, index)

    def _photo_old_changed(self, page):
        from gg_desktop import old_files_page
        old_files_page.changed(self, page)

    def _fill_old_files(self, *args, requested_page=0, **kwargs):
        from gg_desktop import old_files_page
        old_files_page.fill(self, *args, requested_page=requested_page, **kwargs)

    def _set_old_tab(self, name):
        from gg_desktop import old_files_page
        old_files_page.set_tab(self, name)

    def _select_old_visible(self, selected):
        from gg_desktop import old_files_page
        old_files_page.select_visible(self, selected)

    def _selected_old(self):
        from gg_desktop import old_files_page
        return old_files_page.selected_files(self)

    def _old_selection_count(self, *_):
        from gg_desktop import old_files_page
        old_files_page.selection_count(self)

    def _old_details(self):
        from gg_desktop import old_files_page
        old_files_page.details(self)

    def _protect_old_selected(self):
        from gg_desktop import old_files_page
        old_files_page.protect_selected(self)

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

    def dna_page(self):
        from gg_desktop import dna_page
        dna_page.build(self)

    def undo_page(self):
        from gg_desktop import undo_page
        undo_page.build(self)

    def assistant_page(self):
        from gg_desktop import assistant_page
        assistant_page.build(self)

    def settings_page(self):
        from gg_desktop import settings_page
        settings_page.build(self)

    def tools_page(self):
        from gg_desktop import tools_page
        tools_page.build(self)

    def graveyard_page(self):
        from gg_desktop import grave_page
        self._merge_manual_reviews()
        grave_page.build(self)

    def _select_eligible(self):
        from gg_desktop import grave_page
        grave_page.select_reviewable(self)

    def overview_page(self):
        OverviewScreens.overview_page(self)

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
