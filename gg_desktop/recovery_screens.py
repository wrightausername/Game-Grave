"""Reference Graveyard and Undo layouts using the existing guarded workers."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
import os
import time

from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtWidgets import QAbstractItemView, QCheckBox, QHeaderView, QListWidget, QListWidgetItem, QSizePolicy
from core import get_activity, human_size, is_protected_path, save_settings
from graveyard_protection import protection_action, set_item_protection
from recovery import get_records, check_restore, restore as restore_recycled
from gg_desktop.backend import refresh_graveyard
from gg_desktop.insight_models import grave_bucket, history_items, timestamp
from gg_desktop.insight_widgets import ActionFlow
from gg_desktop.reference_library import _check, _checked, _combo, _detail_scroll, _search, _split, _table, _text, _widget
from gg_desktop.models import graveyard_totals, graveyard_protection_decision, readable_bytes
from gg_desktop.reference_widgets import CoverArt, DetailPanel, InventoryPager, MetricStrip, TabStrip, detail_line, detail_section, icon, tool
from gg_desktop.widgets import button, column, destroy_layout, label, panel, row
from ui_paging import page_window


class RecoveryScreens:
    def _insight_page(self, title, subtitle, scene, symbol=None, height=60):
        page = self._reference_page(title, subtitle, scene, symbol)
        page.content.itemAt(0).widget().setFixedHeight(height)
        return page

    def graveyard_page(self):
        page = self._insight_page("Graveyard", "Unearth old and leftover game files. Review every finding and keep full control.", "graveyard")
        entries = self.inventory.graveyard
        totals = graveyard_totals(entries)
        buckets = Counter(grave_bucket(e) for e in entries)
        page.content.addWidget(MetricStrip([
            ("storage", len(entries), "Items Found", "#df74e9"),
            ("storage", human_size(totals["apparent_bytes"]), "Apparent Size", "#15c7ed"),
            ("clock", "—", "Last Use Unknown", "#f8c82c"),
            ("game", buckets["Games"], "Installed Games", "#ff2145"),
            ("mods", buckets["Mods / Addons"], "Mod Locations", "#d76ce6"),
            ("download", buckets["Downloads"], "Downloads", "#16baf1"),
            ("shield", totals["reviewable_items"], "Reviewable Files", "#2bd971"),
        ], compact=True))
        self.grave_tabs = TabStrip([(f"All Items ({len(entries)})", "box"), ("Games", "game"),
            ("Mods / Addons", "mods"), ("Downloads", "download"), ("Caches", "storage"),
            ("Captures", "camera"), ("Orphans (—)", "box")])
        page.content.addWidget(self.grave_tabs)
        filters, scan = panel(kind="fileFilterPanel", padding=9, spacing=7)
        filters.setFixedWidth(185)
        scan.addWidget(label("Scan & Filter", "sectionTitle"))
        scan.addWidget(button("Clear All", self._clear_grave_filters, kind="link"))
        detail_section(scan, "Age Signal")
        self.grave_age = _combo(["All Ages", "30+ Days", "3+ Months", "6+ Months", "12+ Months", "24+ Months"], "Filter Graveyard age signal")
        scan.addWidget(self.grave_age)
        scan.addWidget(label("File age uses modification time; installed games use known last-play records.", "caption", wrap=True))
        detail_section(scan, "Size")
        self.grave_size = _combo(["Any Size", "Under 100 MB", "100 MB – 1 GB", "1 GB – 10 GB", "Over 10 GB"], "Filter Graveyard size")
        scan.addWidget(self.grave_size)
        detail_section(scan, "Type")
        self.grave_type = _combo(["All types"] + sorted({e.category for e in entries}), "Filter Graveyard category")
        scan.addWidget(self.grave_type)
        detail_section(scan, "Protection")
        self.grave_state = _combo(["All findings", "Ready for review", "Protected / preview only"], "Filter Graveyard protection")
        scan.addWidget(self.grave_state)
        scan.addStretch()
        scan.addWidget(label("Age never proves abandonment. Managed games, saves and mod profiles remain protected.", "warning", wrap=True))
        scan.addWidget(tool("Scan PC", "refresh", self.start_scan, kind="primary"))
        results, contents = panel(kind="fileResults", padding=8, spacing=7)
        heading = row(spacing=5)
        title = label("Graveyard Items", "sectionTitle")
        title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        heading.addWidget(title, 1)
        self.grave_sort = _combo(["Size (Largest)", "Age Signal (Oldest)", "Name (A–Z)"], "Sort Graveyard findings")
        self.grave_sort.setFixedWidth(140)
        heading.addWidget(self.grave_sort)
        contents.addWidget(_widget(heading))
        self.grave_search = _search("Search games, files, mods, or Graveyard items…", "Search Graveyard")
        contents.addWidget(self.grave_search)
        self.grave_notice = label("", "caption", wrap=True)
        contents.addWidget(self.grave_notice)
        self.grave_table = _table(["", "Name", "Source / Relation", "Age / Protection", "Size", "Status"])
        for c, width in enumerate((25, 170, 105, 105, 65, 70)):
            self.grave_table.setColumnWidth(c, width)
        self.grave_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.grave_table.setSelectionMode(QAbstractItemView.SingleSelection)
        contents.addWidget(self.grave_table, 1)
        self.grave_pager = InventoryPager()
        self.grave_pager.changed.connect(lambda page: self._fill_graveyard(requested_page=page))
        contents.addWidget(self.grave_pager)
        footer = ActionFlow()
        self.grave_selection = label("0 selected", "caption")
        self.grave_selection.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        contents.addWidget(self.grave_selection)
        footer.addWidget(tool("Select Reviewable", "check", self._select_eligible, tip="Check eligible files on this page only"))
        footer.addWidget(tool("Protect", "shield", self._protect_grave_selected))
        footer.addWidget(tool("Unprotect…", "shield", self._unprotect_grave_selected))
        self.grave_delete = tool("Recycle…", "trash", self._delete_grave_selected, kind="danger")
        footer.addWidget(self.grave_delete)
        contents.addWidget(_widget(footer))
        self.grave_details_frame = DetailPanel()
        self.grave_detail = self.grave_details_frame.content
        page.content.addWidget(_split(_split(filters, results, [185, 540]), _detail_scroll(self.grave_details_frame), [735, 292]), 1)
        self._grave_tab = "All Items"
        self.grave_tabs.changed.connect(self._set_grave_tab)
        for control in (self.grave_type, self.grave_state, self.grave_age, self.grave_size, self.grave_sort):
            control.currentTextChanged.connect(self._fill_graveyard)
        self.grave_search.textChanged.connect(self._fill_graveyard)
        self.grave_table.itemSelectionChanged.connect(self._grave_details)
        self.grave_table.itemChanged.connect(self._grave_selection_count)
        self._fill_graveyard()

    def _clear_grave_filters(self):
        for control in (self.grave_type, self.grave_state, self.grave_age, self.grave_size):
            control.setCurrentIndex(0)
        self.grave_search.clear()
        self._grave_tab = "All Items"
        self.grave_tabs.select(next(iter(self.grave_tabs.buttons)))
        self._fill_graveyard()

    def _set_grave_tab(self, name):
        self._grave_tab = name.split(" (")[0]
        self._fill_graveyard()

    def _fill_graveyard(self, *_, requested_page=0):
        query = self.grave_search.text().strip().casefold()
        category, mode = self.grave_type.currentText(), self.grave_state.currentText()
        days = (0, 30, 90, 180, 365, 730)[self.grave_age.currentIndex()]
        size = self.grave_size.currentIndex()
        tab = self._grave_tab
        rows = [e for e in self.inventory.graveyard
            if (category == "All types" or e.category == category)
            and (tab == "All Items" or grave_bucket(e) == tab)
            and (not query or query in (e.name + " " + e.path + " " + e.category + " " + e.relationship).casefold())
            and (not days or e.age_days is not None and e.age_days >= days)
            and (size == 0 or size == 1 and e.apparent_bytes < 100 * 1024 ** 2
                 or size == 2 and 100 * 1024 ** 2 <= e.apparent_bytes < 1024 ** 3
                 or size == 3 and 1024 ** 3 <= e.apparent_bytes <= 10 * 1024 ** 3
                 or size == 4 and e.apparent_bytes > 10 * 1024 ** 3)
            and (mode == "All findings" or mode == "Ready for review" and e.can_recycle
                 or mode == "Protected / preview only" and not e.can_recycle)]
        sort = self.grave_sort.currentText()
        rows.sort(key=(lambda e: (e.age_days is None, -(e.age_days or 0), e.name.casefold()))
                  if sort == "Age Signal (Oldest)" else (lambda e: e.name.casefold())
                  if sort == "Name (A–Z)" else (lambda e: (-e.apparent_bytes, e.name.casefold())))
        pending = getattr(self, "_pending_grave_key", None)
        if pending:
            requested_page = next((i // 160 for i, e in enumerate(rows) if e.key == pending), 0)
        checked = {e.key for e in self._selected_grave_entries()} if hasattr(self, "_shown_graves") else set()
        window = page_window(rows, requested_page)
        self.grave_pager.update_window(window)
        self._shown_graves = list(window.items)
        with QSignalBlocker(self.grave_table):
            self.grave_table.setRowCount(0)
            self.grave_table.setRowCount(len(self._shown_graves))
            for i, e in enumerate(self._shown_graves):
                _check(self.grave_table, i)
                if e.key in checked:
                    self.grave_table.item(i, 0).setCheckState(Qt.Checked)
                symbol = "game" if grave_bucket(e) == "Games" else "camera" if grave_bucket(e) == "Captures" else "mods" if grave_bucket(e) == "Mods / Addons" else "download"
                _text(self.grave_table, i, 1, e.name, symbol, "#e5b72e")
                _text(self.grave_table, i, 2, e.relationship)
                _text(self.grave_table, i, 3, f"{e.age_days:,} days" if e.age_days is not None else "Unknown")
                _text(self.grave_table, i, 4, human_size(e.apparent_bytes))
                _text(self.grave_table, i, 5, "Reviewable" if e.can_recycle else "Preview" if e.category == "Old game screenshot" else "Protected")
                if protection_action(e.path, self.settings.get("never_touch", []))[0] == "Unprotect":
                    unlock = button("Unprotect this item", lambda _=False, entry=e: self._unprotect_grave(entry))
                    unlock.setAccessibleName("Unprotect your personal rule for " + e.name)
                    unlock.setToolTip("Remove this exact personal rule after confirmation. No file is removed.")
                    self.grave_table.setCellWidget(i, 3, unlock)
                self.grave_table.setRowHeight(i, 40)
            if self._shown_graves:
                index = next((i for i, e in enumerate(self._shown_graves) if e.key == pending), 0)
                self.grave_table.selectRow(index)
        self._pending_grave_key = None
        self.grave_notice.setText("Orphan status is unknown; age cannot establish abandonment." if tab == "Orphans" else
                                  "No findings match these filters." if not rows else "")
        self.grave_notice.setVisible(bool(self.grave_notice.text()))
        self._grave_selection_count()
        self._grave_details()

    def _selected_grave_entries(self):
        return [self._shown_graves[i] for i in _checked(self.grave_table) if i < len(getattr(self, "_shown_graves", []))]

    def _grave_selection_count(self, *_):
        chosen = self._selected_grave_entries()
        self.grave_selection.setText(f"{len(chosen)} selected ({human_size(sum(e.apparent_bytes for e in chosen))})")
        self.grave_delete.setEnabled(bool(chosen) and len(chosen) <= 200 and all(
            e.can_recycle and e.old_file is not None and e.category != "Old game screenshot"
            and not is_protected_path(Path(e.path), self.settings.get("never_touch", [])) for e in chosen))

    def _select_eligible(self):
        with QSignalBlocker(self.grave_table):
            for i, e in enumerate(self._shown_graves):
                allowed = e.can_recycle and e.old_file is not None and e.category != "Old game screenshot" and not is_protected_path(Path(e.path), self.settings.get("never_touch", []))
                self.grave_table.item(i, 0).setCheckState(Qt.Checked if allowed else Qt.Unchecked)
        self._grave_selection_count()

    def _grave_details(self):
        contents = self.grave_detail
        destroy_layout(contents)
        contents.setSpacing(5)
        index = self.grave_table.currentRow()
        if not 0 <= index < len(getattr(self, "_shown_graves", [])):
            contents.addWidget(label("Select a finding", "detailTitle"))
            contents.addWidget(label("Review the evidence and protection before choosing an action.", "subtle", wrap=True))
            contents.addStretch()
            return
        e = self._shown_graves[index]
        contents.addWidget(label(e.name, "detailTitle", wrap=True))
        contents.addWidget(label("Review required" if e.can_recycle else "Protected / preview only", "warning"))
        contents.addWidget(CoverArt(e.name if grave_bucket(e) == "Games" else "Game Grave", height=83))
        detail_section(contents, "Details")
        for symbol, title, value in (("game", "Related Source", e.relationship), ("folder", "Location", e.path),
            ("clock", "Age Signal", f"{e.age_days} days" if e.age_days is not None else "Unknown"),
            ("storage", "Apparent Size", human_size(e.apparent_bytes)), ("mods", "Type", e.category)):
            detail_line(contents, symbol, title, value)
        detail_section(contents, "Why It's in the Graveyard")
        contents.addWidget(label(e.finding, "subtle", wrap=True))
        action, reason = graveyard_protection_decision(e, self.settings.get("never_touch", []))
        detail_section(contents, "What You Can Do")
        contents.addWidget(label(reason, "warning", wrap=True))
        if action == "Unprotect this item":
            contents.addWidget(tool("Unprotect This Item…", "shield", lambda: self._unprotect_grave(e), kind="primary"))
        elif action == "Manage parent rule":
            contents.addWidget(tool("Manage Parent Rule", "settings", lambda: self._manage_parent_rule(e)))
        if e.category == "Old game screenshot":
            contents.addWidget(tool("Preview This Screenshot", "camera", lambda: self._preview_grave_image(e), kind="primary"))
        elif e.can_recycle:
            contents.addWidget(tool("Review Recycle Bin Move…", "trash", lambda: self._approve_recycle([e]), kind="danger"))
        contents.addWidget(tool("Open Containing Folder", "folder", lambda: self._open_folder(str(Path(e.path).parent))))
        contents.addStretch()

    def _protect_paths(self, paths, refresh):
        if self.scanning or self.cleaning:
            self.info("Game Grave is busy", "Finish the current operation before changing protection.")
            return
        if not paths:
            self.info("Choose items", "Check the specific items you want to protect.")
            return
        rules = list(self.settings.get("never_touch", []))
        try:
            for path in paths:
                if protection_action(path, rules)[0] == "Protect":
                    rules = set_item_protection(rules, path, protect=True)
            updated = dict(self.settings, never_touch=rules)
            save_settings(updated)
        except (OSError, ValueError) as exc:
            self.error("Protection not saved", str(exc))
            return
        self.settings = updated
        refresh_graveyard(self.inventory, self.settings)
        self.status.setText("Protection saved. No files were moved.")
        refresh()

    def _protect_grave_selected(self):
        self._protect_paths([e.path for e in self._selected_grave_entries()], self._fill_graveyard)

    def _unprotect_grave_selected(self):
        entries = self._selected_grave_entries()
        if len(entries) != 1:
            self.info("Choose one item", "Check one finding to review its exact personal protection rule.")
            return
        action, _ = protection_action(entries[0].path, self.settings.get("never_touch", []))
        if action == "Unprotect":
            self._unprotect_grave(entries[0])
        else:
            self._manage_parent_rule(entries[0])

    def undo_page(self):
        page = self._insight_page("Undo Center", "Review recorded changes, check Windows recovery, and restore with your approval.", "undo", "undo", 58)
        self._history = history_items(get_records(), get_activity())
        rows = self._history
        recycled = [r for r in rows if r.recovery_id]
        page.content.addWidget(MetricStrip([
            ("box", len(rows), "Recorded Actions", "#e175eb"),
            ("check", len(recycled), "Recycled Files", "#30d76b"),
            ("warning", sum(r.state in {"Needs review", "Not found"} for r in rows), "Needs Review", "#f6be24"),
            ("warning", sum("fail" in r.state.casefold() for r in rows), "Failed Records", "#ff254a"),
            ("undo", sum(r.state == "Restored" for r in rows), "Restored", "#13bcf5"),
            ("storage", human_size(sum(r.size or 0 for r in recycled)), "Recycled · Not Freed", "#f2a5b2"),
            ("shield", "Check", "Restore Availability", "#32d67a"),
        ], compact=True))
        filters, scan = panel(kind="fileFilterPanel", padding=9, spacing=7)
        filters.setFixedWidth(182)
        scan.addWidget(label("Filters", "sectionTitle"))
        scan.addWidget(button("Clear All", self._clear_undo_filters, kind="link"))
        detail_section(scan, "Time Range")
        self.undo_period = _combo(["All Time", "Last 24 Hours", "Last 7 Days", "Last 30 Days"], "Filter cleanup history time")
        scan.addWidget(self.undo_period)
        detail_section(scan, "Action Type")
        self.undo_action = _combo(["All Actions", "Recovery Records", "Restored", "Other Activity"], "Filter history actions")
        scan.addWidget(self.undo_action)
        detail_section(scan, "Game / Source")
        self.undo_source = _combo(["All Sources"] + sorted({r.source for r in rows}), "Filter history source")
        scan.addWidget(self.undo_source)
        scan.addStretch()
        scan.addWidget(label("A recorded recycle is not guaranteed recovery or reclaimed space. Windows must still hold a unique matching item.", "warning", wrap=True))
        scan.addWidget(tool("Refresh Records", "refresh", lambda: self.navigate("Undo Center")))
        results, contents = panel(kind="fileResults", padding=8, spacing=7)
        heading = row(spacing=6)
        title = label("Cleanup History", "sectionTitle")
        title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        heading.addWidget(title, 1)
        self.undo_sort = _combo(["Date (Newest)", "Date (Oldest)", "Size (Largest)", "Name (A–Z)"], "Sort cleanup history")
        self.undo_sort.setFixedWidth(130)
        heading.addWidget(self.undo_sort)
        contents.addWidget(_widget(heading))
        self.undo_search = _search("Search games, files, actions, or history…", "Search cleanup history")
        contents.addWidget(self.undo_search)
        self.undo_table = _table(["", "Action", "Item / Target", "Source", "Size", "Date & Time", "State"])
        for c, width in enumerate((24, 75, 150, 85, 63, 110, 80)):
            self.undo_table.setColumnWidth(c, width)
        self.undo_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        contents.addWidget(self.undo_table, 1)
        self.undo_empty = label("", "caption", wrap=True)
        contents.addWidget(self.undo_empty)
        self.undo_pager = InventoryPager()
        self.undo_pager.changed.connect(lambda page: self._fill_undo(requested_page=page))
        contents.addWidget(self.undo_pager)
        footer = ActionFlow()
        self.undo_selection = label("0 selected", "caption")
        self.undo_selection.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        contents.addWidget(self.undo_selection)
        footer.addWidget(tool("Restore Selected…", "undo", self._restore_undo_selected, kind="primary"))
        footer.addWidget(tool("Check Availability", "check", self._check_undo_selected))
        contents.addWidget(_widget(footer))
        self.undo_details = DetailPanel()
        page.content.addWidget(_split(_split(filters, results, [182, 546]), _detail_scroll(self.undo_details), [735, 292]), 1)
        for control in (self.undo_period, self.undo_action, self.undo_source, self.undo_sort):
            control.currentTextChanged.connect(self._fill_undo)
        self.undo_search.textChanged.connect(self._fill_undo)
        self.undo_table.itemSelectionChanged.connect(self._undo_details)
        self.undo_table.itemChanged.connect(self._undo_selection_count)
        self._fill_undo()

    def _clear_undo_filters(self):
        for control in (self.undo_period, self.undo_action, self.undo_source):
            control.setCurrentIndex(0)
        self.undo_search.clear()

    def _fill_undo(self, *_, requested_page=0):
        query = self.undo_search.text().strip().casefold()
        days = (0, 1, 7, 30)[self.undo_period.currentIndex()]
        action = self.undo_action.currentText()
        source = self.undo_source.currentText()
        rows = [r for r in self._history
            if (not query or query in (r.path + " " + r.action + " " + r.source + " " + r.note).casefold())
            and (not days or timestamp(r.recorded) is not None and timestamp(r.recorded) >= time.time() - days * 86400)
            and (source == "All Sources" or source == r.source)
            and (action == "All Actions" or action == "Recovery Records" and r.recovery_id
                 or action == "Restored" and r.state == "Restored" or action == "Other Activity" and not r.recovery_id)]
        sort = self.undo_sort.currentText()
        rows.sort(key=(lambda r: timestamp(r.recorded) or 0) if sort == "Date (Oldest)" else
                  (lambda r: (r.size is None, -(r.size or 0))) if sort == "Size (Largest)" else
                  (lambda r: r.path.casefold()) if sort == "Name (A–Z)" else
                  (lambda r: -(timestamp(r.recorded) or 0)))
        window = page_window(rows, requested_page)
        self.undo_pager.update_window(window)
        self._shown_history = list(window.items)
        with QSignalBlocker(self.undo_table):
            self.undo_table.setRowCount(0)
            self.undo_table.setRowCount(len(self._shown_history))
            for i, r in enumerate(self._shown_history):
                _check(self.undo_table, i)
                values = (r.action, Path(r.path).name if r.path else r.note[:100], r.source,
                          readable_bytes(r.size), r.recorded.replace("T", " ")[:16] or "Unknown", r.state)
                for c, value in enumerate(values, 1):
                    _text(self.undo_table, i, c, value)
                self.undo_table.setRowHeight(i, 39)
            if self._shown_history:
                self.undo_table.selectRow(0)
        self.undo_empty.setText("No recorded actions match these filters." if not rows else "")
        self.undo_empty.setVisible(not rows)
        self._undo_selection_count()
        self._undo_details()

    def _undo_selection_count(self, *_):
        self.undo_selection.setText(f"{len(_checked(self.undo_table))} selected")

    def _chosen_undo(self):
        checked = _checked(self.undo_table)
        indices = checked or ([self.undo_table.currentRow()] if self.undo_table.currentRow() >= 0 else [])
        return [self._shown_history[i] for i in indices if i < len(self._shown_history)]

    def _undo_details(self):
        contents = self.undo_details.content
        destroy_layout(contents)
        contents.setSpacing(6)
        detail_section(contents, "Action Details")
        i = self.undo_table.currentRow()
        if not 0 <= i < len(getattr(self, "_shown_history", [])):
            contents.addWidget(label("Select a recorded action", "detailTitle", wrap=True))
            contents.addStretch()
            return
        r = self._shown_history[i]
        title = Path(r.path).name if r.path else r.action
        contents.addWidget(label(title, "detailTitle", wrap=True))
        for symbol, name, value in (("trash", "Action", r.action), ("storage", "Size", readable_bytes(r.size)),
            ("clock", "Recorded", r.recorded or "Unknown"), ("folder", "Location", r.path or "Not recorded"),
            ("check", "Last State", r.state), ("shield", "Recovery", "Check in Windows" if r.recovery_id else "No recovery ID")):
            detail_line(contents, symbol, name, value)
        contents.addWidget(label(r.note, "subtle", wrap=True))
        detail_section(contents, "Restore Options")
        contents.addWidget(label("A fresh Windows check is required. Existing files are never overwritten.", "subtle", wrap=True))
        restore = tool("Restore Item…", "undo", self._restore_undo_selected, kind="primary")
        restore.setEnabled(bool(r.recovery_id) and r.state != "Restored")
        contents.addWidget(restore)
        check = tool("Check Availability", "check", self._check_undo_selected)
        check.setEnabled(bool(r.recovery_id))
        contents.addWidget(check)
        contents.addWidget(tool("Open Original Folder", "folder", lambda: self._open_folder(str(Path(r.path).parent))))
        contents.addWidget(tool("Open Windows Recycle Bin", "archive", self._open_recycle_bin))
        detail_section(contents, "Recorded Evidence")
        contents.addWidget(label("The audit trail is retained. A restore record cannot establish that every prior change is reversible.", "warning", wrap=True))
        contents.addStretch()

    def _open_recycle_bin(self):
        if os.name != "nt":
            self.error("Windows only", "The Windows Recycle Bin is available on Windows.")
            return
        try:
            os.startfile("shell:RecycleBinFolder")
        except OSError as exc:
            self.error("Recycle Bin unavailable", str(exc))

    def _check_undo_selected(self):
        if self.cleaning or self.scanning:
            self.info("Game Grave is busy", "Finish the current operation first.")
            return
        entries = self._chosen_undo()
        if not entries or len(entries) > 20 or any(not r.recovery_id for r in entries):
            self.info("Choose recovery records", "Select up to 20 records with a recovery ID.")
            return
        ids = tuple(r.recovery_id for r in entries)
        self.cleaning = True
        def done(values):
            self.cleaning = False
            self.info("Windows Restore Availability", "\n".join(values))
            self.navigate("Undo Center")
        self.job(lambda _: [check_restore(rid) for rid in ids], done, error_title="Cannot check recovery")

    def _restore_undo_selected(self):
        if self.cleaning or self.scanning:
            self.info("Game Grave is busy", "Finish the current operation first.")
            return
        entries = self._chosen_undo()
        if not entries or len(entries) > 20 or any(not r.recovery_id for r in entries):
            self.info("Choose recovery records", "Select up to 20 records with a recovery ID.")
            return
        paths = "\n".join(r.path for r in entries)
        if not self.confirm("Restore from Windows Recycle Bin?", "Check and restore these exact original locations:\n\n" + paths +
            "\n\nWindows must hold a unique matching item. Conflicts and unavailable entries are refused. No existing file will be overwritten."):
            return
        ids = tuple(r.recovery_id for r in entries)
        self.cleaning = True
        def work(_):
            output = []
            for rid in ids:
                state = check_restore(rid)
                output.append(restore_recycled(rid) if state == "AVAILABLE" else state)
            return output
        def done(values):
            self.cleaning = False
            self.info("Restore Results", "\n".join(values))
            self.navigate("Undo Center")
        self.job(work, done, error_title="Restore could not be verified")
