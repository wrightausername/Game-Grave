"""Old Files page: the owner's photo layout wired to the existing scan and Recycle Bin engines.

Only this tab. The scanner, review rules and recycling live in old_files.py / old_files_data.py
and are unchanged. Everything shown is derived from a completed scan (see old_files_insight).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import shutil
import time

from PySide6.QtCore import QRect, Qt, QSignalBlocker
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox, QFrame,
                               QHeaderView, QLabel, QSizePolicy, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QWidget)
from shiboken6 import isValid

from core import human_size, is_protected_path
from gg_desktop import old_files_insight as oi
from gg_desktop.header_banner import HeaderBannerArtwork
from gg_desktop.old_files import OldFilesController
from gg_desktop.old_files_data import protected_roots
from gg_desktop.reference_library import (_check, _checked, _combo, _detail_scroll, _search, _split, _table, _text,
                                          _widget, destroy_layout)
from gg_desktop.reference_widgets import (CoverArt, DetailPanel, InventoryPager, MetricStrip, TabStrip, detail_line,
                                          detail_section, icon, tool)
from gg_desktop.widgets import column, label, panel, row
from screenshots import looks_like_screenshot
from ui_paging import page_window

TABS = [("File Scan", "search"), ("Results", "list"), ("By Game", "game"), ("Downloads", "download"),
        ("Archives", "file"), ("Unused Installers", "box"), ("Large Files", "storage"), ("Settings", "settings")]
SORTS = ["Size (Largest)", "Name (A–Z)", "Oldest Modified", "Newest Modified"]
AGES = (("30+ Days", 30), ("3+ Months", 90), ("6+ Months", 180), ("12+ Months", 365))
PILL_COLORS = {"Game": "#ff4d5a", "Cache": "#2ec4ff", "Downloads": "#a779ff", "Installer": "#ffb020",
               "Archive": "#c26cff", "Logs": "#36c5ff", "Media": "#4be36b", "Other": "#9ca8bd"}
PILL_ICONS = {"Game": ("game", "#ff4d5a"), "Cache": ("folder", "#2ec4ff"), "Downloads": ("download", "#a779ff"),
              "Installer": ("box", "#e7be1f"), "Archive": ("storage", "#d67ee9"), "Logs": ("file", "#c5d5e2"),
              "Media": ("camera", "#70db65"), "Other": ("file", "#ccd7e0")}
FOLDER_ICON = ("folder", "#f1c232")


def font_delta(font, points):
    font = QFont(font)
    if font.pointSizeF() > 0:
        font.setPointSizeF(max(7.0, font.pointSizeF() + points))
    elif font.pixelSize() > 0:
        font.setPixelSize(max(9, font.pixelSize() + int(points * 1.3)))
    return font


class NameDelegate(QStyledItemDelegate):
    """Two-line name cell: title, then a muted subtitle (stored under Qt.UserRole)."""

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        title, opt.text = opt.text, ""
        widget = opt.widget
        style = widget.style() if widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, widget)
        rect = style.subElementRect(QStyle.SE_ItemViewItemText, opt, widget).adjusted(4, 0, -4, 0)
        half = rect.height() // 2
        painter.save()
        bold = font_delta(opt.font, 0.5)
        bold.setBold(True)
        painter.setFont(bold)
        painter.setPen(QColor("#f4f7fc"))
        top = QRect(rect.left(), rect.top() + 3, rect.width(), half)
        painter.drawText(top, int(Qt.AlignLeft | Qt.AlignVCenter), QFontMetrics(bold).elidedText(title, Qt.ElideRight, top.width()))
        small = font_delta(opt.font, -1.5)
        painter.setFont(small)
        painter.setPen(QColor("#9ca8bd"))
        bottom = QRect(rect.left(), rect.top() + half, rect.width(), half - 2)
        painter.drawText(bottom, int(Qt.AlignLeft | Qt.AlignVCenter),
                         QFontMetrics(small).elidedText(str(index.data(Qt.UserRole) or ""), Qt.ElideRight, bottom.width()))
        painter.restore()


class PillDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text, opt.text = opt.text, ""
        widget = opt.widget
        style = widget.style() if widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, widget)
        color = QColor(PILL_COLORS.get(text, "#9ca8bd"))
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        small = font_delta(opt.font, -1.5)
        painter.setFont(small)
        width = min(opt.rect.width() - 6, QFontMetrics(small).horizontalAdvance(text) + 16)
        pill = QRect(0, 0, width, 20)
        pill.moveCenter(opt.rect.center())
        painter.setPen(color)
        painter.setBrush(QColor(color.red(), color.green(), color.blue(), 28))
        painter.drawRoundedRect(pill, 5, 5)
        painter.drawText(pill, int(Qt.AlignCenter), text)
        painter.restore()


def set_active(button, on):
    button.setProperty("active", on)
    button.style().unpolish(button)
    button.style().polish(button)


def small_caption(text, tone="caption"):
    item = label(str(text), tone, wrap=True)
    item.setTextFormat(Qt.PlainText)
    return item


# ------------------------------------------------------------------ page
def build(window):
    self = window
    page = self._reference_page("Old Files", "Find and manage old, unused, and forgotten files taking up space on your drives.", "old_files")
    page.content.itemAt(0).widget().setFixedHeight(74)
    page.banner_artwork = HeaderBannerArtwork(self, page, page.content.itemAt(0).widget(), route="Old Files",
                                              art="banner_old_files.png")
    current_root = str(self.settings.get("scan_folder", ""))
    inventory_root = self.inventory.file_scan_root
    self._old_root = inventory_root or current_root
    self._old_days = self.inventory.file_scan_days if self.inventory.file_scan_days is not None else int(self.settings.get("files_stale_days", 180))
    self._old_source = list(self.inventory.files)
    self._old_entries_key = None
    self._old_entries = []
    self._shown_old_files = []
    self._shown_old_entries = []
    self._shown_old_groups = []
    self._old_view = "files"
    self._old_tab = "File Scan"
    self.old_metrics = MetricStrip([
        ("folder", "0", "Old Files Found", "#dd76ea"),
        ("storage", "0 B", "Total Size", "#13d5e2"),
        ("clock", "—", "Oldest Modified", "#f7c327"),
        ("game", "0", "Possible Game Files", "#fb173d",
         "Files whose names resemble gaming content. Not verified; game, mod and save folders are protected and never scanned."),
        ("download", "0", "Downloads / Archives", "#15b9f5"),
        ("file", "0", "Other Files", "#d4d9e2"),
    ], compact=True)
    page.content.addWidget(self.old_metrics)
    self.old_tabs = TabStrip(TABS)
    self.old_tabs.setFixedHeight(39)
    page.content.addWidget(self.old_tabs)

    # --- Scan & Filter
    filters, scan = panel(kind="fileFilterPanel", padding=9, spacing=6)
    self.old_filters = filters
    filters.setFixedWidth(190 if self.width() >= 1100 else 176)
    scan.addWidget(label("Scan & Filter", "sectionTitle"))
    detail_section(scan, "Scan Location")
    self.photo_drives = QComboBox()  # source of truth for the drive choice; the rows below mirror it
    self.photo_drives.setAccessibleName("Old Files scan drive or selected folder")
    self.photo_drives.hide()
    scan.addWidget(self.photo_drives)
    self.old_drive_box = column(spacing=3)
    scan.addWidget(_widget(self.old_drive_box))
    self.old_drive_checks = []
    self.photo_full = QCheckBox("Full scan (optional)")
    self.photo_full.setToolTip("Unchecked: Downloads, Documents and your selected folder on this drive. Checked: inspect the whole drive, excluding protected/system locations and linked or offline content.")
    scan.addWidget(self.photo_full)
    scan.addWidget(tool("Change Folder", "folder", self._choose_scan_folder))
    detail_section(scan, "Age (Last Modified)")
    self.old_age_controls = []
    self.old_age_group = QButtonGroup(filters)
    self.old_age_group.setExclusive(False)
    for text, days in AGES:
        control = QCheckBox(text)
        control.setProperty("days", days)
        control.toggled.connect(lambda on, c=control: old_age_toggled(self, c, on))
        scan.addWidget(control)
        self.old_age_controls.append(control)
    detail_section(scan, "File Type")
    self.old_type_controls = []
    for name in oi.FILTER_GROUPS:
        control = QCheckBox(name)
        control.setChecked(True)
        control.toggled.connect(self._fill_old_files)
        scan.addWidget(control)
        self.old_type_controls.append(control)
    scan.addStretch()
    scan.addWidget(tool("Scan Now", "refresh", self._old_scan, kind="primary"))
    self.photo_cancel = tool("Cancel Scan", "close")
    scan.addWidget(self.photo_cancel)

    # --- Scan Results
    results, contents = panel(kind="fileResults", padding=8, spacing=6)
    toolbar = row(spacing=4)
    heading = column(spacing=0)
    heading.addWidget(label("Scan Results", "sectionTitle"))
    self.old_result_count = label("", "caption")
    heading.addWidget(self.old_result_count)
    toolbar.addLayout(heading, 1)
    toolbar.addWidget(label("Sort By:", "caption"))
    self.old_sort = _combo(SORTS, "Sort old files")
    self.old_sort.setFixedWidth(110)
    toolbar.addWidget(self.old_sort)
    self.old_view_folders = tool("", "grid", lambda: set_view(self, "folders"), tip="Group by folder (review only)")
    self.old_view_files = tool("", "list", lambda: set_view(self, "files"), active=True, tip="Individual files")
    for button in (self.old_view_folders, self.old_view_files):
        button.setFixedSize(30, 28)
        toolbar.addWidget(button)
    contents.addWidget(_widget(toolbar))
    self.old_search = _search("Search files, folders, or file types…", "Search old files")
    self.old_search.hide()  # The shared search above the page drives this field.
    contents.addWidget(self.old_search)
    self.old_notice = label("", "caption", wrap=True)
    self.old_notice.setTextFormat(Qt.PlainText)
    contents.addWidget(self.old_notice)
    self.old_table = _table(["", "Name", "Location", "Last Modified", "Size", "Type"])
    self.old_table.setItemDelegateForColumn(1, NameDelegate(self.old_table))
    self.old_table.setItemDelegateForColumn(5, PillDelegate(self.old_table))
    for i, width in enumerate((24, 178, 122, 86, 65, 62)):
        self.old_table.setColumnWidth(i, width)
    self.old_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
    self.old_table.setSelectionMode(QAbstractItemView.SingleSelection)
    self.old_table.setIconSize(self.old_table.iconSize().__class__(28, 28))
    contents.addWidget(self.old_table, 1)
    self.old_pager = InventoryPager()
    self.old_pager.changed.connect(lambda number: self._fill_old_files(requested_page=number))
    contents.addWidget(self.old_pager)
    footer = row(spacing=3)
    self.old_select_all = QCheckBox("Select All")
    self.old_select_all.setAccessibleName("Select all visible old files")
    self.old_select_all.toggled.connect(self._select_old_visible)
    footer.addWidget(self.old_select_all)
    self.old_selection = label("0 selected", "caption")
    self.old_selection.setMinimumWidth(0)
    self.old_selection.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    footer.addWidget(self.old_selection, 1)
    footer.addWidget(tool("Add to Graveyard", "grave", self._add_old_to_graveyard,
                          tip="Adds the checked paths to protected Graveyard review. Nothing is moved."))
    footer.addWidget(tool("Protect", "shield", self._protect_old_selected,
                          tip="Adds Never Touch rules for the checked rows"))
    self.old_delete = tool("Delete…", "trash", self._recycle_old_selected, kind="danger",
                           tip="Moves the reviewed individual files to the Windows Recycle Bin after confirmation. Nothing is permanently deleted.")
    footer.addWidget(self.old_delete)
    contents.addWidget(_widget(footer))
    left = _split(filters, results, [190, 532])
    self.old_details = DetailPanel()
    page.content.addWidget(_split(left, _detail_scroll(self.old_details), [740, 292]), 1)

    # --- controller, shortcuts and wiring
    from PySide6.QtGui import QKeySequence, QShortcut
    from gg_desktop.photo_integration import ResponsiveInspector
    holder = QWidget(page)
    hidden = column()
    holder.setLayout(hidden)
    holder.hide()
    page.old_files = OldFilesController(self, page, hidden)
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
    self.photo_cancel.clicked.connect(control.state.cancel)
    self.photo_full.setChecked(control.state.full)
    self.photo_full.toggled.connect(control.full.setChecked)
    self.photo_drives.currentIndexChanged.connect(lambda index: self._photo_choose_drive(index))
    self.photo_drives.currentIndexChanged.connect(lambda *_: sync_drive_rows(self))
    copy_drives(self, control)
    self.old_tabs.changed.connect(self._set_old_tab)
    self.old_sort.currentTextChanged.connect(self._fill_old_files)
    self.old_search.textChanged.connect(self._fill_old_files)
    self.old_table.itemSelectionChanged.connect(self._old_details)
    self.old_table.itemChanged.connect(self._old_selection_count)
    control.state.changed.connect(lambda: self._photo_old_changed(page) if isValid(page) and self.page is page else None)
    self._photo_old_changed(page)
    page.photo_inspector = ResponsiveInspector(page, self.old_details.parentWidget().parentWidget())


# ------------------------------------------------------------------ drives
def copy_drives(window, control):
    combo = window.photo_drives
    with QSignalBlocker(combo):
        combo.clear()
        for index in range(control.drives.count()):
            combo.addItem(control.drives.itemText(index), control.drives.itemData(index))
        combo.setCurrentIndex(control.drives.currentIndex())
    destroy_layout(window.old_drive_box)
    window.old_drive_checks = []
    for index in range(combo.count()):
        root = combo.itemData(index)
        text = combo.itemText(index).split("•")[0].strip() if root else "Selected folder"
        line = row(spacing=3)
        check = QCheckBox(text)
        check.setToolTip(combo.itemText(index))
        check.toggled.connect(lambda on, i=index: drive_toggled(window, i, on))
        line.addWidget(check, 1)
        if root:
            try:
                line.addWidget(label(human_size(shutil.disk_usage(root).total), "caption"))
            except OSError:
                pass
        window.old_drive_box.addWidget(_widget(line))
        window.old_drive_checks.append(check)
    sync_drive_rows(window)


def sync_drive_rows(window):
    current = window.photo_drives.currentIndex()
    for index, check in enumerate(window.old_drive_checks):
        if isValid(check):
            with QSignalBlocker(check):
                check.setChecked(index == current)


def drive_toggled(window, index, on):
    if on:
        window.photo_drives.setCurrentIndex(index)
    sync_drive_rows(window)  # one location is always chosen


def refresh_drives(window):
    control = window.page.old_files
    control.refresh_drives()
    copy_drives(window, control)
    window.photo_full.setChecked(control.state.full)
    changed(window, window.page)


def choose_drive(window, index):
    control = window.page.old_files
    control.drives.setCurrentIndex(index)
    window.photo_full.setEnabled(bool(control.drives.currentData()))


def old_age_toggled(window, control, on):
    if on:
        for other in window.old_age_controls:
            if other is not control and other.isChecked():
                with QSignalBlocker(other):
                    other.setChecked(False)
    window._fill_old_files()


# ------------------------------------------------------------------ state changes
def changed(window, page):
    if not isValid(page) or window.page is not page:
        return
    state = page.old_files.state
    window.photo_cancel.setVisible(state.busy)
    window.photo_drives.setEnabled(not state.busy and not window.cleaning)
    for check in window.old_drive_checks:
        check.setEnabled(not state.busy and not window.cleaning)
    window.photo_full.setEnabled(not state.busy and bool(state.location))
    if state.result:
        window._old_source = list(state.result.files)
        window._old_root, window._old_days = state.result.plan.root, state.result.plan.days
    update_metrics(window, state)
    fill(window)


def entries_for(window):
    state = window.page.old_files.state if hasattr(window.page, "old_files") else None
    result = state.result if state else None
    files = result.files if result else window._old_source  # before a scan: the accepted inventory
    key = (id(result), len(files), id(files))
    if window._old_entries_key != key:
        window._old_entries = [(f, oi.classify(f.path)) for f in files]
        window._old_entries_key = key
    return window._old_entries, result


def update_metrics(window, state):
    entries, result = entries_for(window)
    m = oi.metrics(entries)
    strip = window.old_metrics
    strip.set_value(0, f"{m['total']:,}")
    strip.set_value(1, human_size(m["size"]))
    strip.set_value(2, f"{m['oldest_days'] // 30}+ Months" if m["oldest_days"] is not None else "—")
    strip.set_value(3, f"{m['possible_game']:,}")
    strip.set_value(4, f"{m['downloads_archives']:,}")
    strip.set_value(5, f"{m['other']:,}")
    if result:
        strip.setToolTip(f"{result.plan.mode.capitalize()} scan: {result.plan.root}\n{result.summary()}")


def set_view(window, view):
    window._old_view = view
    set_active(window.old_view_files, view == "files")
    set_active(window.old_view_folders, view == "folders")
    window._fill_old_files()


def set_tab(window, name):
    if name == "Settings":
        window.navigate("Settings")
        return
    window._old_tab = name
    window._fill_old_files()


# ------------------------------------------------------------------ table
def fill(window, *args, requested_page=0, **kwargs):
    if not hasattr(window, "old_table") or window.current_route != "Old Files" or not hasattr(window.page, "old_files"):
        return
    table = window.old_table
    entries, result = entries_for(window)
    days = next((c.property("days") for c in window.old_age_controls if c.isChecked()), 0)
    groups = {c.text() for c in window.old_type_controls if c.isChecked()}
    rows, notice = oi.tab_entries(window._old_tab, entries)
    rows = oi.filter_entries(rows, groups=groups, query=window.old_search.text(), min_days=days or 0,
                             sort=window.old_sort.currentText()) if groups else []
    if not groups:
        notice = "Choose at least one file type."
    folders = window._old_view == "folders"
    shown_groups = oi.group_folders(rows, result.plan.roots if result else [window._old_root]) if folders else []
    items = shown_groups if folders else rows
    if not items and not notice:
        notice = "No files match these filters." if result else "Choose a drive or folder and use Scan Now. No files have been changed."
    previous_checked = checked_keys(window)
    current = table.currentRow()
    previous_key = row_key(window, current)
    window.old_result_count.setText(f"{len(rows):,} files  ({human_size(sum(f.size for f, _ in rows))})" +
                                    (f" in {len(shown_groups):,} folders" if folders else ""))
    page = page_window(items, requested_page)
    window.old_pager.update_window(page)
    shown = list(page.items)
    window._shown_old_groups = shown if folders else []
    window._shown_old_entries = [] if folders else shown
    window._shown_old_files = [f for f, _ in shown] if not folders else []
    with QSignalBlocker(table):
        table.setRowCount(0)
        table.setRowCount(len(shown))
        for i, item in enumerate(shown):
            _check(table, i)
            if folders:
                fill_group_row(table, i, item)
            else:
                fill_file_row(table, i, *item)
            table.setRowHeight(i, 41)
            if row_key(window, i, item) in previous_checked:
                table.item(i, 0).setCheckState(Qt.Checked)
        if shown:
            pick = next((i for i in range(len(shown)) if row_key(window, i, shown[i]) == previous_key), 0)
            table.selectRow(pick)
    state = window.page.old_files.state
    if state.busy or (state.result and state.result.limited) or "failed" in state.message.lower():
        notice = "\n".join(part for part in (notice, state.message) if part)
    window.old_notice.setText(notice)
    window.old_notice.setVisible(bool(notice))
    window._old_selection_count()
    window._old_details()


def fill_file_row(table, i, f, info):
    symbol, color = PILL_ICONS[info.pill]
    cell = _text(table, i, 1, Path(f.path).name, symbol, color)
    cell.setData(Qt.UserRole, info.subtitle)
    _text(table, i, 2, str(Path(f.path).parent))
    _text(table, i, 3, datetime.fromtimestamp(f.modified).strftime("%b %d, %Y"))
    _text(table, i, 4, human_size(f.size))
    _text(table, i, 5, info.pill).setToolTip(info.subtitle)


def fill_group_row(table, i, group):
    cell = _text(table, i, 1, group.name, *FOLDER_ICON)
    cell.setData(Qt.UserRole, group.subtitle)
    _text(table, i, 2, str(Path(group.path).parent))
    _text(table, i, 3, datetime.fromtimestamp(group.newest).strftime("%b %d, %Y"))
    _text(table, i, 4, human_size(group.size))
    _text(table, i, 5, group.pill).setToolTip(group.subtitle)


def row_key(window, index, item=None):
    if item is None:
        shown = window._shown_old_groups if window._old_view == "folders" else window._shown_old_entries
        if not 0 <= index < len(shown):
            return None
        item = shown[index]
    return ("g", item.path) if window._old_view == "folders" else ("f", item[0].path)


def checked_keys(window):
    shown = window._shown_old_groups if window._old_view == "folders" else getattr(window, "_shown_old_entries", [])
    return {row_key(window, i, shown[i]) for i in _checked(window.old_table) if i < len(shown)}


def selected_files(window):
    """Individual files behind the checked rows (a folder row stands for the files the scan found in it)."""
    table = window.old_table
    if window._old_view == "folders":
        out, seen = [], set()
        for i in _checked(table):
            if i < len(window._shown_old_groups):
                for f in window._shown_old_groups[i].files:
                    if f.path not in seen:
                        seen.add(f.path)
                        out.append(f)
        return out
    return [window._shown_old_files[i] for i in _checked(table) if i < len(window._shown_old_files)]


def select_visible(window, on):
    with QSignalBlocker(window.old_table):
        for i in range(window.old_table.rowCount()):
            window.old_table.item(i, 0).setCheckState(Qt.Checked if on else Qt.Unchecked)
    window._old_selection_count()


def selection_count(window):
    selected = selected_files(window)
    rows = len(_checked(window.old_table))
    size = human_size(sum(f.size for f in selected))
    window.old_selection.setText(f"{rows} selected ({size})" if window._old_view == "files" or not rows else
                                 f"{rows} folders, {len(selected):,} files ({size})")
    with QSignalBlocker(window.old_select_all):
        window.old_select_all.setChecked(bool(window.old_table.rowCount()) and rows == window.old_table.rowCount())
    rules = window.settings.get("never_touch", [])
    shots = any(looks_like_screenshot(Path(f.path)) for f in selected)
    blocked = any(is_protected_path(Path(f.path), rules) for f in selected)
    window.old_delete.setEnabled(bool(selected) and len(selected) <= 200 and not shots and not blocked)
    if len(selected) > 200:
        tip = "Review sets of up to 200 individual files at a time. Check fewer rows or use the file view."
    elif shots:
        tip = "Images need individual preview in Captures or Graveyard."
    else:
        tip = "Moves the reviewed individual files to the Windows Recycle Bin after confirmation. Nothing is permanently deleted."
    window.old_delete.setToolTip(tip)


# ------------------------------------------------------------------ details
def chip(text, symbol, color="#c5d5e2"):
    frame = QFrame()
    frame.setObjectName("previewChip")
    frame.setFixedSize(58, 58)
    frame.setStyleSheet("QFrame#previewChip { border:1px solid #2e3a46; border-radius:7px; background:#0b1118; }"
                        "QLabel { border:0; background:transparent; }")
    box = column(spacing=1, margins=(2, 4, 2, 2))
    frame.setLayout(box)
    image = QLabel()
    image.setAlignment(Qt.AlignCenter)
    if symbol:
        image.setPixmap(icon(symbol, color, 22).pixmap(22, 22))
    box.addWidget(image)
    name = QLabel(QFontMetrics(frame.font()).elidedText(text, Qt.ElideMiddle, 52))
    name.setAlignment(Qt.AlignCenter)
    name.setToolTip(text)
    name.setStyleSheet("font-size:9px; color:#c5d0da;")
    box.addWidget(name)
    return frame


def badge(text, good):
    item = QLabel(text)
    color = "#27dc74" if good else "#f7b737"
    item.setStyleSheet(f"color:{color}; border:1px solid {color}; border-radius:9px; padding:2px 8px; font-size:10px;")
    item.setAlignment(Qt.AlignCenter)
    return item


def details(window):
    contents = window.old_details.content
    contents.setSpacing(5)
    destroy_layout(contents)
    index = window.old_table.currentRow()
    folders = window._old_view == "folders"
    shown = window._shown_old_groups if folders else getattr(window, "_shown_old_entries", [])
    if not 0 <= index < len(shown):
        contents.addWidget(label("Select a file", "detailTitle"))
        contents.addWidget(label("Review its location, last modified date and protection before deciding what to keep.", "subtle", wrap=True))
        contents.addStretch()
        return
    control = window.page.old_files
    result = control.state.result
    rules = protected_roots(window.inventory, window.settings)
    entries, _ = entries_for(window)
    siblings_source = shown[index].files if folders else None
    if folders:
        group = shown[index]
        files, name, size = list(group.files), group.name, group.size
        location, modified = group.path, group.newest
        info = None
        reasons = [oi.review_reason(f, result, rules) for f in files[:200]] if result else []
        reviewable = bool(reasons) and all(r == oi.REVIEWABLE for r in reasons)
        symbol, color = FOLDER_ICON
        kind_line = f"Folder ({human_size(size)})"
        lines = [(f"Newest file modified {oi.age_days(SimpleNamespace(modified=group.newest)):,} days ago", True),
                 (f"{group.count:,} old file{'s' if group.count != 1 else ''} found here by this scan", True),
                 (", ".join(f"{n} {k}" for k, n in sorted(group.kinds.items(), key=lambda kv: -kv[1])[:4]), True)]
        if not reviewable and reasons:
            lines.append((next(r for r in reasons if r != oi.REVIEWABLE), False))
        elif reviewable:
            lines.append(("Outside protected game, mod, save and system locations", True))
        items = f"{group.count:,} files found by this scan"
        pill = group.pill
        first = files[0] if files else None
    else:
        f, info = shown[index]
        files, name, size, location, modified = [f], Path(f.path).name, f.size, f.path, f.modified
        reason = oi.review_reason(f, result, rules) if result else "No completed scan"
        reviewable = reason == oi.REVIEWABLE
        symbol, color = PILL_ICONS[info.pill]
        kind_line = f"{info.subtitle} ({human_size(size)})"
        lines = oi.evidence(f, info, result, rules)
        items = "1 file"
        pill, first = info.pill, f
    header = row(spacing=6)
    glyph = QLabel()
    glyph.setPixmap(icon(symbol, color, 30).pixmap(30, 30))
    header.addWidget(glyph)
    titles = column(spacing=0)
    title = label(name, "detailTitle", wrap=True)
    title.setTextFormat(Qt.PlainText)
    titles.addWidget(title)
    titles.addWidget(small_caption(kind_line))
    header.addLayout(titles, 1)
    header.addWidget(badge("Reviewable" if reviewable else "Protected", reviewable))
    contents.addWidget(_widget(header))
    contents.addWidget(CoverArt(name, height=83))
    detail_section(contents, "Details")
    days = oi.age_days(SimpleNamespace(modified=modified))
    possible = (not folders and info.possible_game) or (folders and pill == "Game")
    for sym, title_text, value in (
        ("game", "Related Game", "Unverified (name resembles gaming content)" if possible else "None established"),
        ("folder", "Location", location),
        ("clock", "Last Modified", f"{datetime.fromtimestamp(modified).strftime('%b %d, %Y')} ({days:,} days ago)"),
        ("storage", "Size", human_size(size)),
        ("file", "Items", items),
    ):
        detail_line(contents, sym, title_text, value)
    detail_section(contents, "Why It's Flagged")
    for text, good in lines:
        line = row(spacing=6)
        mark = QLabel()
        mark.setPixmap(icon("check" if good else "warning", "#27dc74" if good else "#f7b737", 15).pixmap(15, 15))
        line.addWidget(mark)
        line.addWidget(small_caption(text, "detailValue" if good else "warning"), 1)
        contents.addWidget(_widget(line))
    contents.addWidget(small_caption("Age does not prove a file is unused. Game Grave never claims a file is safe to remove.", "caption"))
    detail_section(contents, "Preview (Files)")
    folder = str(Path(first.path).parent) if first else ""
    pool = files if folders else [e[0] for e in entries if str(Path(e[0].path).parent) == folder]
    chips = row(spacing=4)
    for other in pool[:4]:
        other_info = next((i for g, i in entries if g.path == other.path), None)
        sym, col = PILL_ICONS[other_info.pill] if other_info else PILL_ICONS["Other"]
        chips.addWidget(chip(Path(other.path).name, sym, col))
    if len(pool) > 4:
        chips.addWidget(chip(f"+{len(pool) - 4:,}", None))
    chips.addStretch()
    contents.addWidget(_widget(chips))
    detail_section(contents, "Quick Actions")
    contents.addWidget(tool("Open Containing Folder" if not folders else "Open Folder", "folder",
                            lambda: window._open_folder(folder if not folders else location)))
    contents.addWidget(tool("Review in Graveyard", "grave", lambda: window.navigate("Graveyard")))
    if not folders and looks_like_screenshot(Path(files[0].path)):
        contents.addWidget(tool("Preview This Screenshot", "camera", lambda: window._preview_capture(files[0])))
    contents.addStretch()


# ------------------------------------------------------------------ protection
def protect_selected(window):
    from core import save_settings
    from gg_desktop.backend import refresh_graveyard
    from graveyard_protection import set_item_protection
    if window.scanning or window.cleaning:
        window.info("Game Grave is busy", "Finish the current operation before changing protection.")
        return
    targets = ([g.path for i, g in enumerate(window._shown_old_groups) if i in _checked(window.old_table)]
               if window._old_view == "folders" else [f.path for f in selected_files(window)])
    if not targets:
        window.info("Choose items", "Check the rows you want to protect.")
        return
    rules = list(window.settings.get("never_touch", []))
    try:
        for path in targets:
            if not is_protected_path(Path(path), rules):
                rules = set_item_protection(rules, path, protect=True)
        updated = dict(window.settings, never_touch=rules)
        save_settings(updated)
    except (OSError, ValueError) as exc:
        window.error("Protection not saved", str(exc))
        return
    window.settings = updated
    refresh_graveyard(window.inventory, window.settings)
    window._old_selection_count()
    window._old_details()
    window.status.setText(f"Protected {len(targets)} selected item(s). Manage personal rules in Settings.")
