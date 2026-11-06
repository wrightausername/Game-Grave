"""Reference Other Storage, Captures and Game DNA screens with live scan data."""
from __future__ import annotations

from collections import Counter, OrderedDict
from datetime import datetime
from pathlib import Path
import time

from PySide6.QtCore import Qt, QSignalBlocker, QSize
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QCheckBox, QHeaderView, QLabel, QListWidget, QListWidgetItem, QSizePolicy, QSlider, QStackedWidget
from core import age_text, human_size, is_protected_path, save_settings
from game_intelligence import build_game_dna
from screenshot_preview import decode_screenshot_preview
from ui_paging import page_window
from gg_desktop.backend import refresh_graveyard
from gg_desktop.insight_models import (
    STORAGE_COLORS, STORAGE_TYPES, capture_items, dna_footprint, storage_items,
)
from gg_desktop.insight_widgets import ActionFlow, CAPTURE_ROLE, CaptureGrid, FootprintRing, ReferenceArt
from gg_desktop.reference_library import _check, _checked, _combo, _detail_scroll, _search, _split, _table, _text, _view_switch, _widget
from gg_desktop.models import _path_key, readable_bytes
from gg_desktop.reference_widgets import (
    CoverArt, DetailPanel, InventoryPager, MetricStrip, TabStrip, cover_icon,
    detail_line, detail_section, icon, tile_action, tool,
)
from gg_desktop.widgets import button, column, destroy_layout, label, panel, row


class StorageScreens:
    def other_storage_page(self):
        page = self._insight_page("Other Storage", "Find game-related storage outside an install.\nCaches, shader data, logs, configuration, and other detected files.", "other_storage", "storage", 82)
        self._storage = storage_items(self.inventory)
        totals = {kind: sum(r.size for r in self._storage if r.category == kind) for kind in STORAGE_TYPES}
        symbols = ("storage", "box", "settings", "file", "trash", "box")
        page.content.addWidget(MetricStrip([("storage", human_size(sum(totals.values())), "Apparent Other Storage", "#e274e8")] + [
            (symbol, human_size(totals[kind]), kind, color)
            for kind, color, symbol in zip(STORAGE_TYPES[:5], STORAGE_COLORS, symbols)], compact=True))
        self.storage_tabs = TabStrip([("Storage Breakdown", "storage"), ("By Game", "game"),
            ("Caches", "storage"), ("Shader Cache", "box"), ("Configs", "settings"),
            ("Logs", "file"), ("Temporary", "trash"), ("Cleanup Assistant", "sparkles")])
        page.content.addWidget(self.storage_tabs)
        filters, scan = panel(kind="fileFilterPanel", padding=9, spacing=6)
        filters.setFixedWidth(230 if self.width() >= 1100 else 175)
        scan.addWidget(label("Storage Overview", "sectionTitle"))
        self.storage_categories = QListWidget()
        self.storage_categories.setObjectName("sourceFilters")
        self.storage_categories.setIconSize(QSize(16, 16))
        self.storage_categories.setAccessibleName("Filter other storage category")
        for kind, amount, symbol, color in [("All Other Storage", sum(totals.values()), "storage", "#e474e7")] + list(zip(STORAGE_TYPES, [totals[k] for k in STORAGE_TYPES], symbols, STORAGE_COLORS)):
            item = QListWidgetItem(icon(symbol, color, 17), kind + "   " + human_size(amount))
            item.setData(Qt.UserRole, kind)
            self.storage_categories.addItem(item)
        self.storage_categories.setCurrentRow(0)
        self.storage_categories.setMinimumHeight(150)
        scan.addWidget(self.storage_categories)
        self.storage_ring = FootprintRing(caption="OTHER STORAGE")
        self.storage_ring.set_segments([(k, totals[k], c) for k, c in zip(STORAGE_TYPES, STORAGE_COLORS)])
        scan.addWidget(self.storage_ring, 1)
        scan.addWidget(label("Reported bytes; hardlinks can share physical space. No removal safety is inferred.", "caption", wrap=True))
        results, contents = panel(kind="fileResults", padding=8, spacing=7)
        header = row(spacing=5)
        header.addWidget(label("Storage Items", "sectionTitle"), 1)
        self.storage_sort = _combo(["Size (Largest)", "Name (A–Z)", "Type"], "Sort other storage")
        self.storage_sort.setFixedWidth(120)
        header.addWidget(self.storage_sort)
        contents.addWidget(_widget(header))
        self.storage_search = _search("Search games, files, folders, or storage types…", "Search other storage")
        contents.addWidget(self.storage_search)
        self.storage_notice = label("", "caption", wrap=True)
        contents.addWidget(self.storage_notice)
        self.storage_table = _table(["", "Name", "Related Source", "Size", "Items", "Type"])
        for c, width in enumerate((25, 180, 105, 70, 55, 85)):
            self.storage_table.setColumnWidth(c, width)
        self.storage_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        contents.addWidget(self.storage_table, 1)
        self.storage_pager = InventoryPager()
        self.storage_pager.changed.connect(lambda page: self._fill_storage(requested_page=page))
        contents.addWidget(self.storage_pager)
        self.storage_details = DetailPanel()
        page.content.addWidget(_split(_split(filters, results, [230, 495]), _detail_scroll(self.storage_details), [735, 292]), 1)
        actions, bar = panel(kind="fileResults", padding=8, spacing=0)
        footer = ActionFlow(spacing=8)
        footer.addWidget(tool("Scan Other Storage", "refresh", self.start_scan, kind="primary"))
        self.storage_selection = label("0 selected", "caption")
        footer.addWidget(self.storage_selection)
        footer.addWidget(tool("Protect", "shield", lambda: self._protect_paths([r.path for r in self._selected_storage()], self._fill_storage)))
        footer.addWidget(tool("Add to Graveyard", "grave", self._watch_storage))
        footer.addWidget(tool("Review & Clean…", "trash", self._review_storage, kind="danger"))
        footer.addWidget(tool("Cleanup Tools", "settings", self._launch_classic_tools))
        bar.addWidget(_widget(footer))
        page.content.addWidget(actions)
        self._storage_tab = "Storage Breakdown"
        self.storage_tabs.changed.connect(self._set_storage_tab)
        self.storage_search.textChanged.connect(self._fill_storage)
        self.storage_sort.currentTextChanged.connect(self._fill_storage)
        self.storage_categories.currentRowChanged.connect(self._fill_storage)
        self.storage_table.itemSelectionChanged.connect(self._storage_details)
        self.storage_table.itemChanged.connect(self._storage_selection_count)
        self._fill_storage()

    def _set_storage_tab(self, name):
        self._storage_tab = name
        self._fill_storage()

    def _fill_storage(self, *_, requested_page=0):
        query = self.storage_search.text().strip().casefold()
        current = self.storage_categories.currentItem()
        category = current.data(Qt.UserRole) if current else "All Other Storage"
        tab = self._storage_tab
        tab_kind = {"Caches": "Caches", "Shader Cache": "Shader Cache", "Configs": "Config / Settings",
                    "Logs": "Logs / Reports", "Temporary": "Temporary Files"}.get(tab)
        rows = [r for r in self._storage if (category == "All Other Storage" or r.category == category)
                and (not tab_kind or r.category == tab_kind)
                and (not query or query in (r.name + " " + r.path + " " + r.category + " " + r.source).casefold())]
        sort = self.storage_sort.currentText()
        rows.sort(key=(lambda r: r.name.casefold()) if sort == "Name (A–Z)" else
                  (lambda r: (r.category, -r.size)) if sort == "Type" else (lambda r: (-r.size, r.name.casefold())))
        window = page_window(rows, requested_page)
        self.storage_pager.update_window(window)
        self._shown_storage = list(window.items)
        with QSignalBlocker(self.storage_table):
            self.storage_table.setRowCount(0)
            self.storage_table.setRowCount(len(self._shown_storage))
            for i, r in enumerate(self._shown_storage):
                _check(self.storage_table, i)
                symbol = {"Shader Cache": "box", "Caches": "storage", "Config / Settings": "settings", "Logs / Reports": "file", "Temporary Files": "trash"}.get(r.category, "box")
                _text(self.storage_table, i, 1, r.name, symbol, STORAGE_COLORS[STORAGE_TYPES.index(r.category)])
                for c, value in enumerate((r.source, human_size(r.size), f"{r.items:,}", r.category), 2):
                    _text(self.storage_table, i, c, value)
                self.storage_table.setRowHeight(i, 41)
            if self._shown_storage:
                self.storage_table.selectRow(0)
        notice = ("Ownership is shown only when the source supplies evidence; unverified files stay unassigned." if tab == "By Game" else
                  "Inspect the selected source before cleanup. Shared driver caches are not cleared here." if tab == "Cleanup Assistant" else
                  "No detected storage matches these filters. Scan PC to refresh." if not rows else "")
        self.storage_notice.setText(notice)
        self.storage_notice.setVisible(bool(notice))
        self._storage_selection_count()
        self._storage_details()

    def _selected_storage(self):
        return [self._shown_storage[i] for i in _checked(self.storage_table) if i < len(self._shown_storage)]

    def _storage_selection_count(self, *_):
        rows = self._selected_storage()
        self.storage_selection.setText(f"{len(rows)} selected ({human_size(sum(r.size for r in rows))})")

    def _storage_details(self):
        contents = self.storage_details.content
        destroy_layout(contents)
        contents.setSpacing(6)
        i = self.storage_table.currentRow()
        if not 0 <= i < len(getattr(self, "_shown_storage", [])):
            contents.addWidget(label("Select a storage item", "detailTitle", wrap=True))
            contents.addStretch()
            return
        r = self._shown_storage[i]
        contents.addWidget(label(r.name, "detailTitle", wrap=True))
        contents.addWidget(label(r.category + " · Review required", "warning"))
        contents.addWidget(ReferenceArt("other_storage", (998, 295, 262, 73), height=83))
        detail_section(contents, "Details")
        for symbol, name, value in (("folder", "Location", r.path), ("storage", "Size", human_size(r.size)),
            ("file", "Items", f"{r.items:,}"), ("game", "Source", r.source),
            ("clock", "Last Use", "Unknown"), ("shield", "Protection", "Protected" if
                is_protected_path(Path(r.path), self.settings.get("never_touch", [])) else "Review required")):
            detail_line(contents, symbol, name, value)
        detail_section(contents, "What It Is")
        contents.addWidget(label(r.evidence, "subtle", wrap=True))
        detail_section(contents, "Recommendation")
        contents.addWidget(label("Keep configuration and active storage. Cache regeneration can cause downloads or stutter; inspect the game and launcher first.", "warning", wrap=True))
        contents.addWidget(tool("Open Folder", "folder", lambda: self._open_folder(str(Path(r.path).parent) if r.old_file else r.path)))
        contents.addStretch()

    def _watch_storage(self):
        rows = self._selected_storage()
        if not rows:
            self.info("Choose items", "Check the mod storage locations you want to keep in the Graveyard review list.")
            return
        if self.scanning or self.cleaning:
            self.info("Game Grave is busy", "Finish the current operation first.")
            return
        mod_paths = {m.path for m in self.inventory.mods}
        eligible = [r.path for r in rows if r.path in mod_paths]
        if len(eligible) != len(rows):
            self.info("Review ordinary files in Old Files", "Only detected mod/cache locations can be added to the protected watchlist. Ordinary files keep their existing scan scope.")
            return
        updated = dict(self.settings, graveyard_watchlist=list(dict.fromkeys([*self.settings.get("graveyard_watchlist", []), *eligible])))
        try:
            save_settings(updated)
        except (OSError, ValueError) as exc:
            self.error("Watchlist not saved", str(exc))
            return
        self.settings = updated
        refresh_graveyard(self.inventory, self.settings)
        self.navigate("Graveyard")

    def _review_storage(self):
        rows = self._selected_storage()
        if not rows:
            self.info("Choose items", "Check a storage item to open its existing review workflow.")
            return
        if all(r.old_file is not None for r in rows):
            self.navigate("Old Files")
            if len(rows) == 1:
                self.old_search.setText(Path(rows[0].path).name)
        else:
            self.info("Managed storage stays protected", "Use the original launcher or classic per-game cache tools. This screen does not clear shared driver caches or active configuration.")

    def captures_page(self):
        page = self._insight_page("Captures", "Manage your in-game screenshots, recordings, and clips across your games.\nPreview, organize, and safely review old captures.", "captures", "camera", 74)
        self._captures = capture_items(self.inventory)
        if not hasattr(self, "_capture_previews"):
            self._capture_previews = OrderedDict()
        rows = self._captures
        oldest = max((int((time.time() - r.record.modified) / 86400) for r in rows), default=None)
        page.content.addWidget(MetricStrip([
            ("camera", sum(r.kind == "Screenshots" for r in rows), "Screenshots", "#db77e6"),
            ("play", sum(r.kind == "Recordings" for r in rows), "Recordings", "#13baef"),
            ("box", human_size(sum(r.record.size for r in rows)), "Apparent Captures", "#f3c52c"),
            ("game", len({r.game for r in rows if r.game != "Unverified"}), "Verified Game Links", "#ff2145"),
            ("clock", f"{oldest // 30}+ Months" if oldest is not None else "—", "Oldest Modified", "#f7c327"),
            ("shield", "Preview", "Individual Review", "#dc60d6"),
        ], compact=True))
        self.capture_tabs = TabStrip([("Screenshots", "camera"), ("Recordings", "play"), ("By Game", "game"),
            ("Timeline", "clock"), ("Duplicates", "box"), ("Similar", "camera"), ("Clean Up", "sparkles"), ("Settings", "settings")])
        page.content.addWidget(self.capture_tabs)
        filters, scan = panel(kind="fileFilterPanel", padding=9, spacing=7)
        filters.setFixedWidth(185)
        scan.addWidget(label("Filters", "sectionTitle"))
        scan.addWidget(button("Clear All", self._clear_capture_filters, kind="link"))
        detail_section(scan, "Game / Source")
        self.capture_game = QListWidget()
        self.capture_game.setObjectName("sourceFilters")
        self.capture_game.setIconSize(QSize(14, 14))
        self.capture_game.setAccessibleName("Filter captures by verified game")
        self.capture_game.setMinimumHeight(95)
        self.capture_game.setMaximumHeight(135)
        game_counts = Counter(r.game for r in rows)
        for game, count in [("All Games", len(rows))] + sorted(game_counts.items()):
            item = QListWidgetItem(icon("game", "#e3c52d", 14), f"{game}  ({count})")
            item.setData(Qt.UserRole, game)
            self.capture_game.addItem(item)
        self.capture_game.setCurrentRow(0)
        scan.addWidget(self.capture_game)
        detail_section(scan, "Capture Type")
        self.capture_types = []
        for kind in ("Screenshots", "Recordings"):
            check = QCheckBox(kind)
            check.setChecked(True)
            self.capture_types.append(check)
            scan.addWidget(check)
        self.capture_age = _combo(["Age: All Modified Dates", "Age: 30+ Days", "Age: 6+ Months", "Age: 12+ Months"], "Filter capture modification age")
        scan.addWidget(self.capture_age)
        self.capture_size = _combo(["Size: Any", "Size: Under 10 MB", "Size: 10 MB or More", "Size: 1 GB or More"], "Filter capture size")
        scan.addWidget(self.capture_size)
        scan.addStretch()
        scan.addWidget(label("Individual preview required", "caption"))
        scan.addWidget(tool("Add Capture Folder", "folder", self._add_capture_folder))
        results, contents = panel(kind="fileResults", padding=7, spacing=6)
        header = row(spacing=5)
        self.capture_heading = label("Screenshots", "sectionTitle")
        self.capture_heading.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        header.addWidget(self.capture_heading, 1)
        self.capture_sort = _combo(["Date (Newest)", "Date (Oldest)", "Size (Largest)", "Name (A–Z)"], "Sort captures")
        self.capture_sort.setFixedWidth(118)
        header.addWidget(self.capture_sort)
        self.capture_grid = CaptureGrid()
        self.capture_grid.setAccessibleName("Local captures with individual opt-in previews")
        self.capture_zoom = QSlider(Qt.Horizontal)
        self.capture_zoom.setRange(115, 210)
        self.capture_zoom.setValue(125)
        self.capture_zoom.setFixedWidth(62)
        self.capture_zoom.setAccessibleName("Capture tile size")
        self.capture_zoom.valueChanged.connect(self._zoom_captures)
        header.addWidget(self.capture_zoom)
        contents.addWidget(_widget(header))
        self.capture_search = _search("Search games, captures, recordings, or folders…", "Search captures")
        contents.addWidget(self.capture_search)
        self.capture_notice = label("", "caption", wrap=True)
        contents.addWidget(self.capture_notice)
        contents.addWidget(self.capture_grid, 1)
        self.capture_pager = InventoryPager()
        self.capture_pager.changed.connect(lambda page: self._fill_captures(requested_page=page))
        contents.addWidget(self.capture_pager)
        footer = ActionFlow()
        self.capture_selection = label("0 selected", "caption")
        self.capture_selection.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        contents.addWidget(self.capture_selection)
        footer.addWidget(tool("Protect", "shield", lambda: self._protect_paths([r.record.path for r in self._selected_captures()], self._capture_details)))
        footer.addWidget(tool("Graveyard", "grave", self._captures_to_graveyard))
        footer.addWidget(tool("Review Removal…", "trash", self._review_capture_selection, kind="danger"))
        contents.addWidget(_widget(footer))
        self.capture_details = DetailPanel()
        page.content.addWidget(_split(_split(filters, results, [185, 540]), _detail_scroll(self.capture_details), [735, 292]), 1)
        self._capture_tab = "Screenshots"
        self.capture_tabs.changed.connect(self._set_capture_tab)
        for control in (self.capture_age, self.capture_size, self.capture_sort):
            control.currentTextChanged.connect(self._fill_captures)
        self.capture_game.currentRowChanged.connect(self._fill_captures)
        for control in self.capture_types:
            control.toggled.connect(self._fill_captures)
        self.capture_search.textChanged.connect(self._fill_captures)
        self.capture_grid.currentRowChanged.connect(self._capture_details)
        self.capture_grid.itemChanged.connect(self._capture_selection_count)
        self.capture_grid.previewRequested.connect(self._request_capture_preview)
        self._fill_captures()

    def _set_capture_tab(self, name):
        if name == "Settings":
            self.navigate("Settings")
            return
        self._capture_tab = name
        self._fill_captures()

    def _zoom_captures(self, value):
        self.capture_grid.tile_width = value
        self.capture_grid._fit()
        self.capture_grid.doItemsLayout()

    def _clear_capture_filters(self):
        self.capture_game.setCurrentRow(0)
        for control in (self.capture_age, self.capture_size):
            control.setCurrentIndex(0)
        for control in self.capture_types:
            control.setChecked(True)
        self.capture_search.clear()

    def _fill_captures(self, *_, requested_page=0):
        query = self.capture_search.text().strip().casefold()
        selected = self.capture_game.currentItem()
        game = selected.data(Qt.UserRole) if selected else "All Games"
        kinds = {c.text() for c in self.capture_types if c.isChecked()}
        days = (0, 30, 180, 365)[self.capture_age.currentIndex()]
        size = self.capture_size.currentIndex()
        tab = self._capture_tab
        rows = [r for r in self._captures if r.kind in kinds and (game == "All Games" or r.game == game)
            and (tab not in {"Screenshots", "Recordings"} or r.kind == tab)
            and (not query or query in (r.record.path + " " + r.game).casefold())
            and (not days or r.record.modified <= time.time() - days * 86400)
            and (size == 0 or size == 1 and r.record.size < 10 * 1024 ** 2
                 or size == 2 and r.record.size >= 10 * 1024 ** 2 or size == 3 and r.record.size >= 1024 ** 3)]
        sort = self.capture_sort.currentText()
        rows.sort(key=(lambda r: r.record.modified) if sort == "Date (Oldest)" else
                  (lambda r: -r.record.size) if sort == "Size (Largest)" else
                  (lambda r: Path(r.record.path).name.casefold()) if sort == "Name (A–Z)" else
                  (lambda r: -r.record.modified))
        notice = {"Duplicates": "Content comparison has not run; duplicate status is unknown.",
                  "Similar": "Visual similarity has not been analyzed. Preview images individually.",
                  "Clean Up": "Images require individual preview and a separate Recycle Bin confirmation.",
                  "Timeline": "Timeline order uses modification time; actual capture dates are unverified.",
                  "By Game": "Game links use verified Steam screenshot paths and app IDs."}.get(tab, "")
        if tab in {"Duplicates", "Similar"}:
            rows = []
        checked = {r.key for r in self._selected_captures()} if hasattr(self, "_shown_captures") else set()
        window = page_window(rows, requested_page)
        self.capture_pager.update_window(window)
        self._shown_captures = list(window.items)
        with QSignalBlocker(self.capture_grid):
            self.capture_grid.clear()
            for r in self._shown_captures:
                item = QListWidgetItem(Path(r.record.path).name)
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                item.setCheckState(Qt.Checked if r.key in checked else Qt.Unchecked)
                preview, dims = self._capture_previews.get(r.key, (None, None))
                item.setData(CAPTURE_ROLE, {"item": r, "preview": preview, "dimensions": dims})
                item.setToolTip(r.record.path + "\n" + r.game + " · " + r.source)
                self.capture_grid.addItem(item)
            if self._shown_captures:
                self.capture_grid.setCurrentRow(0)
        self.capture_grid.doItemsLayout()
        self.capture_heading.setText(f"{tab if tab in {'Screenshots', 'Recordings'} else 'Captures'} ({len(rows):,})")
        self.capture_notice.setText(notice or ("No captures match these filters. Scan PC to refresh." if not rows else ""))
        self.capture_notice.setVisible(bool(self.capture_notice.text()))
        self._capture_selection_count()
        self._capture_details()

    def _selected_captures(self, fallback=False):
        indices = [i for i in range(self.capture_grid.count()) if self.capture_grid.item(i).checkState() == Qt.Checked]
        if not indices and fallback and self.capture_grid.currentRow() >= 0:
            indices = [self.capture_grid.currentRow()]
        return [self._shown_captures[i] for i in indices if i < len(getattr(self, "_shown_captures", []))]

    def _capture_selection_count(self, *_):
        rows = self._selected_captures()
        self.capture_selection.setText(f"{len(rows)} selected ({human_size(sum(r.record.size for r in rows))})")
        self.capture_grid.viewport().update()

    def _capture_details(self, *_):
        contents = self.capture_details.content
        destroy_layout(contents)
        contents.setSpacing(5)
        i = self.capture_grid.currentRow()
        if not 0 <= i < len(getattr(self, "_shown_captures", [])):
            contents.addWidget(label("Select a capture", "detailTitle"))
            contents.addWidget(label("Your images load only after you request a preview.", "subtle", wrap=True))
            contents.addStretch()
            return
        r = self._shown_captures[i]
        contents.addWidget(label(r.game if r.game != "Unverified" else "Local Capture", "detailTitle", wrap=True))
        contents.addWidget(label(r.kind.rstrip("s") + " · " + human_size(r.record.size), "caption"))
        image = QLabel()
        image.setAlignment(Qt.AlignCenter)
        image.setFixedHeight(108)
        image.setMinimumWidth(0)
        preview, dims = self._capture_previews.get(r.key, (None, None))
        if preview is not None:
            image.setPixmap(preview.scaled(270, 108, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            image.setText("Preview this image to load it" if r.kind == "Screenshots" else "Recording · Open its folder to inspect")
            image.setWordWrap(True)
            image.setStyleSheet("background:#0b1822;color:#8aa3b9;border:1px solid #25384a;border-radius:5px;")
        contents.addWidget(image)
        preview_btn = tool("Preview This Screenshot" if r.kind == "Screenshots" else "Open Recording Folder", "camera", lambda: self._request_capture_preview(i), kind="primary")
        contents.addWidget(preview_btn)
        detail_section(contents, "Details")
        for symbol, title, value in (("file", "File Name", Path(r.record.path).name), ("folder", "Location", r.record.path),
            ("camera", "Resolution", f"{dims[0]} × {dims[1]}" if dims else "Unknown · Preview to inspect"),
            ("storage", "Size", human_size(r.record.size)), ("clock", "Modified", datetime.fromtimestamp(r.record.modified).strftime("%b %d, %Y %H:%M")),
            ("game", "Game", r.game), ("shield", "Source", r.source),
            ("shield", "Protection", "Protected" if is_protected_path(Path(r.record.path), self.settings.get("never_touch", [])) else "Individual review")):
            detail_line(contents, symbol, title, value)
        detail_section(contents, "Recommendations")
        contents.addWidget(label("Last use, duplicates and saved-highlight status are unknown. Keep captures you value; age alone is not a removal recommendation.", "warning", wrap=True))
        contents.addWidget(tool("Review This Capture…", "trash", lambda: self._review_capture(r)))
        contents.addStretch()

    def _request_capture_preview(self, index):
        if not 0 <= index < len(self._shown_captures):
            return
        item = self._shown_captures[index]
        if item.kind != "Screenshots":
            self._open_folder(str(Path(item.record.path).parent))
            return
        key = item.key
        def ready(image):
            qimage = QImage(image.tobytes(), image.width, image.height, image.width * 3, QImage.Format_RGB888).copy()
            pix = QPixmap.fromImage(qimage).scaled(480, 320, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._capture_previews[key] = (pix, image.info.get("source_size", image.size))
            self._capture_previews.move_to_end(key)
            while len(self._capture_previews) > 32:
                self._capture_previews.popitem(last=False)
            if self.current_route == "Captures":
                for i, r in enumerate(self._shown_captures):
                    if r.key == key:
                        data = self.capture_grid.item(i).data(CAPTURE_ROLE)
                        data.update(preview=pix, dimensions=self._capture_previews[key][1])
                        self.capture_grid.item(i).setData(CAPTURE_ROLE, data)
                self._capture_details()
        self.job(lambda _: decode_screenshot_preview(item.record), ready, error_title="Could not safely preview image")

    def _review_capture_selection(self):
        rows = self._selected_captures(fallback=True)
        if not rows:
            self.info("Choose captures", "Select a capture to review.")
            return
        if len(rows) != 1:
            self.error("Individual preview required", "Review one capture at a time. Screenshot batches are never authorized from this gallery.")
            return
        self._review_capture(rows[0])

    def _review_capture(self, capture):
        if capture.kind == "Screenshots":
            self._preview_capture(capture.record)
            return
        entry = next((e for e in self.inventory.graveyard if e.old_file == capture.record and e.category == "Old game recording"), None)
        if entry is None:
            self.info("Capture not eligible", "This recording is not in the reviewed old-capture inventory. Nothing was removed.")
        else:
            self._approve_recycle([entry])

    def _captures_to_graveyard(self):
        rows = self._selected_captures(fallback=True)
        if not rows:
            return
        entry = next((e for e in self.inventory.graveyard if e.old_file == rows[0].record), None)
        if entry is None:
            self.info("Not in Graveyard", "This capture does not meet the current Graveyard scan criteria. It remains protected.")
        else:
            self._go_grave_item(entry.key)

    def _add_capture_folder(self):
        from PySide6.QtWidgets import QFileDialog
        from core import _has_reparse_component, safe_scan_root
        chosen = QFileDialog.getExistingDirectory(self, "Choose a local screenshot folder for read-only discovery")
        if not chosen:
            return
        if not safe_scan_root(Path(chosen)) or _has_reparse_component(Path(chosen)):
            self.error("Folder not allowed", "Choose a normal local capture folder, not a drive root or redirected path.")
            return
        updated = dict(self.settings, screenshot_roots=list(dict.fromkeys([*self.settings.get("screenshot_roots", []), chosen])))
        try:
            save_settings(updated)
        except (OSError, ValueError) as exc:
            self.error("Folder not saved", str(exc))
            return
        self.settings = updated
        self.start_scan()

    def dna_page(self):
        page = self._insight_page("Game DNA", "A complete view of each game's known storage, verified relationships, and protected data.", "dna", height=58)
        self._dna_model = build_game_dna(self.inventory.steam, self.inventory.other, self.inventory.mods, self.inventory.saves)
        self.dna_metrics = MetricStrip([
            ("game", "—", "Game DNA Profile", "#ff2245"), ("storage", "—", "Known Reported Size", "#16c9eb"),
            ("folder", "—", "Known Locations", "#eac329"), ("box", "—", "Item Count Unknown", "#dd73e6"),
            ("clock", "—", "Last Played", "#ff244b"), ("check", "Evidence", "Relationship Status", "#3ad371"),
        ], compact=True)
        self.dna_metrics.values[0].setStyleSheet("font-size:16px;font-weight:650;")
        page.content.addWidget(self.dna_metrics)
        sidebar, filters = panel(kind="fileFilterPanel", padding=9, spacing=7)
        sidebar.setFixedWidth(205 if self.width() >= 1100 else 180)
        filters.addWidget(label("Select Game", "sectionTitle"))
        self.dna_search = _search("Search your games…", "Search Game DNA games")
        filters.addWidget(self.dna_search)
        self.dna_games = QListWidget()
        self.dna_games.setObjectName("sourceFilters")
        self.dna_games.setIconSize(QSize(28, 32))
        self.dna_games.setAccessibleName("Select Game DNA profile")
        filters.addWidget(self.dna_games, 1)
        right = _widget(column(spacing=7))
        self.dna_game_header, self.dna_game_header_content = panel(kind="fileResults", padding=7, spacing=3)
        right.layout().addWidget(self.dna_game_header)
        self.dna_tabs = TabStrip([("Storage DNA", "box"), ("Files & Locations", "folder"), ("Saves", "archive"),
            ("Mods & Addons", "mods"), ("Caches", "storage"), ("Config / Settings", "settings"),
            ("Screenshots", "camera"), ("Recordings", "play")])
        right.layout().addWidget(self.dna_tabs)
        footprint, chart = panel(kind="fileResults", padding=10, spacing=7)
        self.dna_chart_heading = label("Storage Footprint", "sectionTitle")
        chart.addWidget(self.dna_chart_heading)
        self.dna_chart_stack = QStackedWidget()
        chart.addWidget(self.dna_chart_stack, 1)
        ringbox = row(spacing=8)
        self.dna_ring = FootprintRing(caption="KNOWN FOOTPRINT")
        ringbox.addWidget(self.dna_ring, 1)
        self.dna_legend = _widget(column(spacing=6))
        ringbox.addWidget(self.dna_legend, 1)
        self.dna_chart_stack.addWidget(_widget(ringbox))
        self.dna_asset_table = _table(["Location", "Kind", "Apparent Size"])
        self.dna_asset_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.dna_chart_stack.addWidget(self.dna_asset_table)
        self.dna_summary = DetailPanel()
        self.dna_summary.setMinimumWidth(220)
        self.dna_summary.setMaximumWidth(300)
        right.layout().addWidget(_split(footprint, _detail_scroll(self.dna_summary), [460, 290]), 1)
        page.content.addWidget(_split(sidebar, right, [205, 820]), 1)
        bottom = row(spacing=8)
        locations, loc = panel(kind="fileResults", padding=8, spacing=5)
        title = row(spacing=5)
        title.addWidget(label("Top Locations", "sectionTitle"), 1)
        title.addWidget(button("View All Locations", lambda: self._set_dna_tab("Files & Locations"), kind="link"))
        loc.addWidget(_widget(title))
        self.dna_locations = _table(["Location", "Reported Size"])
        self.dna_locations.setMinimumHeight(90)
        self.dna_locations.setMaximumHeight(103)
        self.dna_locations.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.dna_locations.setColumnWidth(1, 100)
        loc.addWidget(self.dna_locations)
        bottom.addWidget(locations, 5)
        suggestions, suggest = panel(kind="fileResults", padding=9, spacing=7)
        suggest.addWidget(label("Cleanup Suggestions", "sectionTitle"))
        suggest.addWidget(label("Inspect source evidence before cleanup. Save, mod and configuration ownership does not establish that files are disposable.", "subtle", wrap=True))
        suggest.addWidget(tool("Review Related Findings", "sparkles", self._dna_review_findings, kind="primary"))
        suggest.addWidget(tool("Open Selected Location", "folder", self._dna_open_location))
        bottom.addWidget(suggestions, 3)
        page.content.addWidget(_widget(bottom))
        self._dna_tab = "Storage DNA"
        self.dna_search.textChanged.connect(self._fill_dna_games)
        self.dna_games.currentRowChanged.connect(self._show_dna_game)
        self.dna_tabs.changed.connect(self._set_dna_tab)
        self._fill_dna_games()

    def _fill_dna_games(self, *_):
        query = self.dna_search.text().strip().casefold()
        self._shown_dna_games = [g for g in self.inventory.games if not query or query in (g.name + " " + g.launcher).casefold()]
        with QSignalBlocker(self.dna_games):
            self.dna_games.clear()
            for g in self._shown_dna_games:
                item = QListWidgetItem(cover_icon(g.name), g.name + "\n" + readable_bytes(g.size_bytes))
                item.setToolTip(g.name + "\n" + g.install_path)
                self.dna_games.addItem(item)
            if self._shown_dna_games:
                pending = getattr(self, "_pending_dna_game_key", None)
                selected = next((i for i, g in enumerate(self._shown_dna_games) if g.key == pending), 0)
                self.dna_games.setCurrentRow(selected)
                self._pending_dna_game_key = None
        self._show_dna_game()

    def _set_dna_tab(self, name):
        self._dna_tab = name
        self.dna_tabs.select(name)
        self._show_dna_game()

    def _show_dna_game(self, *_):
        header = self.dna_game_header_content
        contents = self.dna_summary.content
        destroy_layout(header)
        destroy_layout(contents)
        destroy_layout(self.dna_legend.layout())
        index = self.dna_games.currentRow()
        self.dna_locations.setRowCount(0)
        self.dna_asset_table.setRowCount(0)
        if not 0 <= index < len(self._shown_dna_games):
            header.addWidget(label("Select a detected game", "detailTitle"))
            contents.addWidget(label("Scan PC to build evidence-backed game profiles.", "subtle", wrap=True))
            self.dna_ring.set_segments([], "Unknown")
            for i in range(6):
                self.dna_metrics.set_value(i, "—")
            self._dna_current = None
            return
        game = self._shown_dna_games[index]
        self._dna_current = game
        match = next((g for g in self._dna_model["games"] if _path_key(g["install_path"]) == _path_key(game.install_path)
                      and g["launcher"] == game.launcher), None) if len(game.claimed_by) == 1 and game.status.startswith("Installed") else None
        assets = match["assets"] if match else []
        total, segments, external = dna_footprint(game, assets)
        self.dna_ring.set_segments(segments, human_size(total) if segments else "Unknown")
        for i, value in enumerate((game.name, human_size(total) if segments else "Unknown", 1 + len(assets), "—",
                                   age_text(game.last_played_at) if game.last_played_at is not None else "Unknown", "Linked" if match else "Unverified")):
            self.dna_metrics.set_value(i, value)
        intro = row(spacing=10)
        from gg_desktop.artwork import game_app_id
        art = CoverArt(game.name, height=80, artwork=self.artwork, app_id=game_app_id(game))
        art.setMaximumWidth(270)
        intro.addWidget(art, 1)
        text = column(spacing=4)
        text.addWidget(label(game.name, "detailTitle", wrap=True))
        text.addWidget(label(game.launcher + " · " + game.status, "caption", wrap=True))
        text.addWidget(label(game.install_path, "caption", wrap=True))
        intro.addLayout(text, 1)
        buttons = column(spacing=4)
        play = tool("Open Game", "play", lambda: self._launch_game(game), kind="primary")
        play.setEnabled("steam_uninstall" in game.capabilities)
        buttons.addWidget(play)
        folder = tool("Open Folder", "folder", lambda: self._open_folder(game.install_path))
        folder.setEnabled("open_folder" in game.capabilities)
        buttons.addWidget(folder)
        intro.addLayout(buttons)
        header.addWidget(_widget(intro))
        for name, amount, color in segments:
            info = label("●  " + name + "\n    " + human_size(amount), "subtle", wrap=True)
            info.setStyleSheet("color:" + color + ";font-size:11px;")
            self.dna_legend.layout().addWidget(info)
        self.dna_legend.layout().addWidget(label(f"{len(assets) - len(external)} linked locations are already included in the install size. Saves, configs and captures are not guessed.", "caption", wrap=True))
        self.dna_legend.layout().addStretch()
        detail_section(contents, "Game DNA Summary")
        for symbol, title, value in (("storage", "Reported Size", human_size(total) if segments else "Unknown"),
            ("folder", "Locations", str(1 + len(assets))), ("box", "Total Items", "Unknown"),
            ("clock", "Last Access", "Unknown"), ("clock", "Install Date", "Unknown"), ("game", "Game Status", game.status)):
            detail_line(contents, symbol, title, value)
        detail_section(contents, "What It Is")
        contents.addWidget(label("Known relationships use installation paths or source-specific IDs. Nested mod bytes are included once. Unresolved data remains protected.", "subtle", wrap=True))
        contents.addStretch()
        self._dna_location_rows = [(game.install_path, game.size_bytes, "Game install")] + [
            (a["path"], a["apparent_bytes"], "Linked storage · protected") for a in assets]
        for i, (path, amount, kind) in enumerate(self._dna_location_rows[:5]):
            self.dna_locations.insertRow(i)
            _text(self.dna_locations, i, 0, path)
            _text(self.dna_locations, i, 1, readable_bytes(amount))
            self.dna_locations.setRowHeight(i, 24)
        if self.dna_locations.rowCount():
            self.dna_locations.selectRow(0)
        self.dna_chart_heading.setText("Storage Footprint" if self._dna_tab == "Storage DNA" else self._dna_tab)
        self.dna_chart_stack.setCurrentIndex(0 if self._dna_tab == "Storage DNA" else 1)
        entries = self._dna_location_rows if self._dna_tab == "Files & Locations" else [
            (a["path"], a["apparent_bytes"], a["kind"]) for a in assets] if self._dna_tab == "Mods & Addons" else []
        if self._dna_tab in {"Screenshots", "Recordings"}:
            entries = [(r.record.path, r.record.size, r.kind) for r in capture_items(self.inventory)
                       if r.game == game.name and r.kind == self._dna_tab]
        for i, (path, amount, kind) in enumerate(entries):
            self.dna_asset_table.insertRow(i)
            for c, value in enumerate((path, kind, readable_bytes(amount))):
                _text(self.dna_asset_table, i, c, value)
            self.dna_asset_table.setRowHeight(i, 32)
        if self._dna_tab != "Storage DNA" and not entries:
            self.dna_asset_table.setRowCount(1)
            _text(self.dna_asset_table, 0, 0, "No verified links for this category. Unknown content stays protected.")

    def _dna_open_location(self):
        index = self.dna_locations.currentRow()
        if 0 <= index < len(getattr(self, "_dna_location_rows", [])):
            self._open_folder(self._dna_location_rows[index][0])

    def _dna_review_findings(self):
        if not self._dna_current:
            self.info("Choose a game", "Select a detected game first.")
            return
        name = self._dna_current.name
        self.navigate("Graveyard")
        self.grave_search.setText(name)
