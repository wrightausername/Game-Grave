"""Other Storage page: the owner's photo layout on a real read-only scanner.

Only this tab. Discovery lives in other_storage_data (metadata only), removal in other_storage_actions
(verified small runs to the Recycle Bin). Nothing shown here is inferred beyond what a scan can prove.
"""
from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime
import os
from pathlib import Path
from types import SimpleNamespace
import threading
import uuid

from PySide6.QtCore import QRect, QRectF, QSignalBlocker, QSize, Qt, QUrl, QProcess
from PySide6.QtGui import QColor, QDesktopServices, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QFrame, QHeaderView, QLabel, QListWidget,
                               QListWidgetItem, QMenu, QSizePolicy, QStyle, QStyledItemDelegate, QStyleOptionViewItem)
from shiboken6 import isValid

from core import human_size, is_protected_path, save_settings
from gg_desktop import other_storage_actions as actions
from gg_desktop.backend import refresh_graveyard
from gg_desktop import other_storage_data as data
from gg_desktop import other_storage_insight as insight
from gg_desktop.header_banner import HeaderBannerArtwork
from gg_desktop.insight_models import STORAGE_COLORS, STORAGE_TYPES, storage_items
from gg_desktop.insight_widgets import ActionFlow, FootprintRing, ReferenceArt
from gg_desktop.reference_library import _check, _checked, _combo, _detail_scroll, _search, _split, _table, _text, _widget
from gg_desktop.reference_widgets import (DetailPanel, InventoryPager, MetricStrip, TabStrip, detail_line, detail_section,
                                          icon, tool)
from gg_desktop.widgets import column, destroy_layout, label, panel, row
from ui_paging import page_window

TABS = [("Storage Breakdown", "storage"), ("By Game", "game"), ("Caches", "storage"), ("Shader Cache", "box"),
        ("Configs", "settings"), ("Logs", "file"), ("Temporary", "trash"), ("Cleanup Assistant", "sparkles")]
SYMBOLS = {"Caches": "box", "Shader Cache": "box", "Config / Settings": "settings", "Logs / Reports": "file",
           "Temporary Files": "trash", "Other": "box"}
TILE_SYMBOLS = ("storage", "box", "settings", "file", "trash", "box")
PILL_COLORS = {"Shader": "#ffb020", "Cache": "#2ec4ff", "Config": "#ff4d5a", "Logs": "#4f8cff", "Temp": "#c26cff",
               "Other": "#9ca8bd"}
BADGE_COLORS = {"Reviewable": "#27dc74", "Review only": "#f7b737", "Protected": "#ff7a85"}


def font_delta(font, points):
    font = QFont(font)
    if font.pointSizeF() > 0:
        font.setPointSizeF(max(7.0, font.pointSizeF() + points))
    elif font.pixelSize() > 0:
        font.setPixelSize(max(9, font.pixelSize() + int(points * 1.3)))
    return font


class NameDelegate(QStyledItemDelegate):
    """Two lines: the item name, then a muted summary (stored under Qt.UserRole)."""

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        title, opt.text = opt.text, ""
        widget = opt.widget
        style = widget.style() if widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, widget)
        rect = style.subElementRect(QStyle.SE_ItemViewItemText, opt, widget).adjusted(4, 0, -4, 0)
        compact = rect.height() < 36
        half = rect.height() if compact else rect.height() // 2
        painter.save()
        bold = font_delta(opt.font, 0.5)
        bold.setBold(True)
        painter.setFont(bold)
        painter.setPen(QColor("#f4f7fc"))
        top = QRect(rect.left(), rect.top() + (0 if compact else 3), rect.width(), half)
        painter.drawText(top, int(Qt.AlignLeft | Qt.AlignVCenter), QFontMetrics(bold).elidedText(title, Qt.ElideRight, top.width()))
        if compact:
            painter.restore()
            return
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
        pill = QRect(0, 0, min(opt.rect.width() - 6, QFontMetrics(small).horizontalAdvance(text) + 16), 20)
        pill.moveCenter(opt.rect.center())
        painter.setPen(color)
        painter.setBrush(QColor(color.red(), color.green(), color.blue(), 28))
        painter.drawRoundedRect(pill, 5, 5)
        painter.drawText(pill, int(Qt.AlignCenter), text)
        painter.restore()


class CategoryDelegate(QStyledItemDelegate):
    """Square marker, icon, name and a right-aligned size, like the photo's Storage Overview list."""

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        name, opt.text, opt.icon = opt.text, "", QApplication.style().standardIcon(QStyle.SP_CustomBase)
        widget = opt.widget
        style = widget.style() if widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, widget)
        selected = bool(opt.state & QStyle.State_Selected)
        rect = opt.rect.adjusted(6, 0, -6, 0)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        box = QRect(rect.left(), rect.center().y() - 6, 12, 12)
        painter.setPen(QColor("#ff1a3d") if selected else QColor("#5a6573"))
        painter.setBrush(QColor("#ff1a3d") if selected else Qt.NoBrush)
        painter.drawRoundedRect(box, 3, 3)
        if selected:
            painter.setPen(QColor("#ffffff"))
            painter.drawText(box, int(Qt.AlignCenter), "✓")
        pic = index.data(Qt.DecorationRole)
        left = box.right() + 8
        if pic is not None:
            pic.paint(painter, QRect(left, rect.center().y() - 8, 16, 16))
            left += 22
        painter.setFont(font_delta(opt.font, -0.5))
        painter.setPen(QColor("#f4f7fc") if selected else QColor("#d3dae3"))
        size_text = str(index.data(Qt.UserRole + 1) or "")
        size_width = QFontMetrics(painter.font()).horizontalAdvance(size_text)
        painter.drawText(QRect(left, rect.top(), rect.right() - left - size_width - 6, rect.height()),
                         int(Qt.AlignLeft | Qt.AlignVCenter),
                         QFontMetrics(painter.font()).elidedText(name, Qt.ElideRight, rect.right() - left - size_width - 6))
        painter.setPen(QColor("#9ca8bd"))
        painter.drawText(QRect(rect.right() - size_width - 2, rect.top(), size_width + 2, rect.height()),
                         int(Qt.AlignRight | Qt.AlignVCenter), size_text)
        painter.restore()

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), 24)


def set_active(button, on):
    button.setProperty("active", on)
    button.style().unpolish(button)
    button.style().polish(button)


def caption(text, tone="caption"):
    item = label(str(text), tone, wrap=True)
    item.setTextFormat(Qt.PlainText)
    return item


def steam_context(settings):
    """Steam install roots and libraries from the registry and settings. Read-only."""
    from core import _steam_roots, steam_libraries
    roots = _steam_roots(list(settings.get("steam_extra_roots", [])))
    return roots, steam_libraries(roots)


def open_storage_settings():
    return QDesktopServices.openUrl(QUrl("ms-settings:storagesense"))


def open_disk_cleanup():
    if os.name != "nt":
        return False
    return QProcess.startDetached("cleanmgr.exe", [])


# ------------------------------------------------------------------ state
def state_of(window):
    if not hasattr(window, "_storage_state"):
        window._storage_state = SimpleNamespace(busy=False, cancel=threading.Event(), report=None, message="")
    return window._storage_state


def live(window):
    return (window.current_route == "Other Storage" and hasattr(window, "storage_table")
            and isValid(window.storage_table) and hasattr(window.page, "storage_ready"))


def all_entries(window):
    """Scan results plus entries from the last PC scan that do not overlap them."""
    report = state_of(window).report
    scanned = report.entries if report else []
    legacy = data.from_inventory(storage_items(window.inventory))
    key = (id(report), len(scanned), id(window.inventory), len(window.inventory.mods), len(window.inventory.files))
    if getattr(window, "_storage_key", None) != key:
        window._storage_all = data.merge(scanned, legacy)
        window._storage_key = key
    return window._storage_all


# ------------------------------------------------------------------ page
def build(window):
    self = window
    page = self._insight_page("Other Storage", "Find and manage game-related storage that isn't part of a game install.\nCaches, shader data, logs, temporary files, configuration, and other hidden space.",
                              "other_storage", "storage", 82)
    page.banner_artwork = HeaderBannerArtwork(self, page, page.content.itemAt(0).widget(), route="Other Storage",
                                              scene="other_storage", source=(700, 0, 580, 126),
                                              excluded=((1090, 0, 190, 40),))
    state = state_of(self)
    self._storage = all_entries(self)
    self._shown_storage = []
    self._storage_tab = "Storage Breakdown"
    self._storage_compact = False
    self.storage_metrics = MetricStrip([("storage", "0 B", "Total Other Storage", "#e274e8")] + [
        (symbol, "0 B", kind, color) for kind, color, symbol in zip(STORAGE_TYPES[:5], STORAGE_COLORS, TILE_SYMBOLS[1:])],
        compact=True)
    page.content.addWidget(self.storage_metrics)
    self.storage_tabs = TabStrip(TABS)
    page.content.addWidget(self.storage_tabs)

    # --- Storage Overview
    filters, scan = panel(kind="fileFilterPanel", padding=9, spacing=6)
    filters.setMinimumWidth(176)
    filters.setMaximumWidth(250)
    scan.addWidget(label("Storage Overview", "sectionTitle"))
    self.storage_categories = QListWidget()
    self.storage_categories.setObjectName("sourceFilters")
    self.storage_categories.setItemDelegate(CategoryDelegate(self.storage_categories))
    self.storage_categories.setAccessibleName("Filter other storage category")
    self.storage_categories.setMinimumHeight(158)
    self.storage_categories.setMaximumHeight(170)
    self.storage_categories.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    for kind, symbol, color in [("All Other Storage", "storage", "#e474e7")] + list(zip(STORAGE_TYPES, TILE_SYMBOLS[1:], STORAGE_COLORS)):
        item = QListWidgetItem(icon(symbol, color, 16), kind)
        item.setData(Qt.UserRole, kind)
        self.storage_categories.addItem(item)
    self.storage_categories.setCurrentRow(0)
    scan.addWidget(self.storage_categories)
    self.storage_ring = FootprintRing(caption="OTHER STORAGE")
    scan.addWidget(self.storage_ring, 1)
    self.storage_legend = column(spacing=2)
    scan.addWidget(_widget(self.storage_legend))
    scan.addWidget(caption("Reported bytes. Hardlinks can share physical space, and nothing here is assumed removable.", "caption"))

    # --- Storage Items
    results, contents = panel(kind="fileResults", padding=8, spacing=6)
    header = row(spacing=5)
    heading = column(spacing=0)
    heading.addWidget(label("Storage Items", "sectionTitle"))
    self.storage_count = label("", "caption")
    heading.addWidget(self.storage_count)
    header.addLayout(heading, 1)
    header.addWidget(label("Sort By:", "caption"))
    self.storage_sort = _combo(list(insight.SORTS), "Sort other storage")
    self.storage_sort.setFixedWidth(118)
    header.addWidget(self.storage_sort)
    self.storage_view_grid = tool("", "grid", lambda: set_density(self, False), active=True, tip="Detailed rows with a summary line")
    self.storage_view_list = tool("", "list", lambda: set_density(self, True), tip="Compact rows")
    for button in (self.storage_view_grid, self.storage_view_list):
        button.setFixedSize(30, 28)
        header.addWidget(button)
    contents.addWidget(_widget(header))
    self.storage_search = _search("Search games, files, folders, or storage types…", "Search other storage")
    self.storage_search.hide()  # The shared search above the page drives this field.
    contents.addWidget(self.storage_search)
    self.storage_notice = label("", "caption", wrap=True)
    self.storage_notice.setTextFormat(Qt.PlainText)
    contents.addWidget(self.storage_notice)
    self.storage_table = _table(["", "Name", "Related Game / App", "Size", "Items", "Type"])
    self.storage_table.setItemDelegateForColumn(1, NameDelegate(self.storage_table))
    self.storage_table.setItemDelegateForColumn(5, PillDelegate(self.storage_table))
    for c, width in enumerate((24, 150, 96, 60, 50, 58)):
        self.storage_table.setColumnWidth(c, width)
    self.storage_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
    self.storage_table.setSelectionMode(QAbstractItemView.SingleSelection)
    contents.addWidget(self.storage_table, 1)
    self.storage_pager = InventoryPager()
    self.storage_pager.changed.connect(lambda number: self._fill_storage(requested_page=number))
    contents.addWidget(self.storage_pager)
    self.storage_details = DetailPanel()
    page.content.addWidget(_split(_split(filters, results, [250, 480]), _detail_scroll(self.storage_details), [735, 292]), 1)

    # --- footer bar
    actions_panel, bar = panel(kind="fileResults", padding=8, spacing=0)
    footer = ActionFlow(spacing=8)
    self.storage_scan = tool("Cancel Scan" if state.busy else "Scan Other Storage", "close" if state.busy else "refresh",
                             self._scan_other_storage, kind="primary",
                             tip="Reads sizes and dates of known game-related folders. Nothing is changed.")
    footer.addWidget(self.storage_scan)
    self.storage_selection = label("0 selected", "caption")
    footer.addWidget(self.storage_selection)
    footer.addWidget(tool("Protect", "shield", lambda: self._protect_paths([r.path for r in self._selected_storage()], self._fill_storage),
                          tip="Adds Never Touch rules for the checked items"))
    footer.addWidget(tool("Add to Graveyard", "grave", self._watch_storage,
                          tip="Adds checked loose files to protected Graveyard review. Nothing is moved."))
    self.storage_delete = tool("Delete…", "trash", self._review_storage, kind="danger")
    footer.addWidget(self.storage_delete)
    tools_button = tool("Windows Tools", "settings", None,
                        tip="Open Windows' own storage tools. Game Grave does not schedule or run unattended cleanup.")
    menu = QMenu(tools_button)
    menu.addAction("Windows Storage settings", lambda: open_storage_settings())
    menu.addAction("Disk Cleanup (includes DirectX Shader Cache)", lambda: open_disk_cleanup())
    tools_button.setMenu(menu)
    footer.addWidget(tools_button)
    bar.addWidget(_widget(footer))
    page.content.addWidget(actions_panel)

    page.storage_ready = True
    self.storage_tabs.changed.connect(self._set_storage_tab)
    self.storage_search.textChanged.connect(self._fill_storage)
    self.storage_sort.currentTextChanged.connect(self._fill_storage)
    self.storage_categories.currentRowChanged.connect(self._fill_storage)
    self.storage_table.itemSelectionChanged.connect(self._storage_details)
    self.storage_table.itemChanged.connect(self._storage_selection_count)
    refresh(self)


# ------------------------------------------------------------------ summary widgets
def refresh(window):
    """Metrics, category list, ring and legend from the current entries, then the table."""
    entries = all_entries(window)
    window._storage = entries
    totals = insight.totals(entries)
    whole = sum(totals.values())
    strip = window.storage_metrics
    strip.set_value(0, human_size(whole))
    for i, kind in enumerate(STORAGE_TYPES[:5], 1):
        strip.set_value(i, human_size(totals[kind]))
    report = state_of(window).report
    strip.setToolTip(report.summary() if report else "Run Scan Other Storage to measure known locations.")
    cats = window.storage_categories
    with QSignalBlocker(cats):
        for index in range(cats.count()):
            item = cats.item(index)
            kind = item.data(Qt.UserRole)
            item.setData(Qt.UserRole + 1, human_size(whole if kind == "All Other Storage" else totals.get(kind, 0)))
    cats.viewport().update()
    window.storage_ring.set_segments([(k, totals[k], c) for k, c in zip(STORAGE_TYPES, STORAGE_COLORS)])
    destroy_layout(window.storage_legend)
    shares = insight.shares(entries)
    for left in range(0, len(shares), 2):
        line = row(spacing=6)
        for kind, _, percent in shares[left:left + 2]:
            cell = row(spacing=4)
            dot = QLabel("■")
            dot.setStyleSheet(f"color:{STORAGE_COLORS[STORAGE_TYPES.index(kind)]}; font-size:10px;")
            cell.addWidget(dot)
            text = label(f"{insight.PILLS[kind]}  {percent}", "caption")
            text.setMinimumWidth(0)
            text.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            cell.addWidget(text)
            cell.addStretch()
            line.addWidget(_widget(cell), 1)
        window.storage_legend.addWidget(_widget(line))
    fill(window)


def set_density(window, compact):
    window._storage_compact = compact
    set_active(window.storage_view_grid, not compact)
    set_active(window.storage_view_list, compact)
    fill(window)


def set_tab(window, name):
    window._storage_tab = name
    fill(window)


def fill(window, *args, requested_page=0, **kwargs):
    if not live(window):
        return
    table = window.storage_table
    state = state_of(window)
    current = window.storage_categories.currentItem()
    category = current.data(Qt.UserRole) if current else "All Other Storage"
    rows, tab_notice = insight.tab_rows(window._storage_tab, window._storage)
    rows = insight.filter_rows(rows, category=category, query=window.storage_search.text(), sort=window.storage_sort.currentText())
    previous_checked = {e.key for e in checked_entries(window)}
    selected_row = table.currentRow()
    previous_key = window._shown_storage[selected_row].key if 0 <= selected_row < len(window._shown_storage) else None
    window.storage_count.setText(f"{len(rows):,} items  ({human_size(sum(e.size for e in rows))})")
    page = page_window(rows, requested_page)
    window.storage_pager.update_window(page)
    window._shown_storage = list(page.items)
    with QSignalBlocker(table):
        table.setRowCount(0)
        table.setRowCount(len(window._shown_storage))
        for i, entry in enumerate(window._shown_storage):
            _check(table, i)
            cell = _text(table, i, 1, entry.name, SYMBOLS.get(entry.category, "box"),
                         STORAGE_COLORS[STORAGE_TYPES.index(entry.category)] if entry.category in STORAGE_TYPES else "#a8b5c6")
            cell.setData(Qt.UserRole, entry.summary)
            _text(table, i, 2, entry.related)
            _text(table, i, 3, human_size(entry.size) + ("+" if entry.partial else ""))
            _text(table, i, 4, f"{entry.items:,}" + ("+" if entry.partial else ""))
            _text(table, i, 5, insight.PILLS.get(entry.category, "Other")).setToolTip(entry.badge)
            table.setRowHeight(i, 28 if window._storage_compact else 41)
            if entry.key in previous_checked:
                table.item(i, 0).setCheckState(Qt.Checked)
        if window._shown_storage:
            table.selectRow(next((i for i, e in enumerate(window._shown_storage) if e.key == previous_key), 0))
    notice = tab_notice
    if not rows and not notice:
        notice = ("No storage found yet. Use Scan Other Storage to measure known locations. Nothing is changed."
                  if state.report is None else "No detected storage matches these filters.")
    if state.busy:
        notice = "\n".join(part for part in (notice, state.message) if part)
    elif state.report is None and rows and not notice:
        notice = "Showing items from the last PC scan. Use Scan Other Storage for caches, logs and settings folders."
    window.storage_notice.setText(notice)
    window.storage_notice.setVisible(bool(notice))
    selection_count(window)
    details(window)


def checked_entries(window):
    shown = getattr(window, "_shown_storage", [])
    return [shown[i] for i in _checked(window.storage_table) if i < len(shown)] if hasattr(window, "storage_table") and isValid(window.storage_table) else []


def selection_count(window):
    if not live(window):
        return
    rows = checked_entries(window)
    window.storage_selection.setText(f"{len(rows)} selected ({human_size(sum(e.size for e in rows))})")
    rules = window.settings.get("never_touch", [])
    hit = any(is_protected_path(Path(e.path), rules) for e in rows)
    enabled, tip = insight.selection_state(rows, hit)
    window.storage_delete.setEnabled(enabled and not state_of(window).busy and not window.cleaning)
    window.storage_delete.setToolTip(tip)


# ------------------------------------------------------------------ details
def badge(text):
    item = QLabel(text)
    color = BADGE_COLORS.get(text, "#f7b737")
    item.setStyleSheet(f"color:{color}; border:1px solid {color}; border-radius:9px; padding:2px 8px; font-size:10px;")
    item.setAlignment(Qt.AlignCenter)
    return item


def details(window):
    if not live(window):
        return
    contents = window.storage_details.content
    destroy_layout(contents)
    contents.setSpacing(6)
    index = window.storage_table.currentRow()
    if not 0 <= index < len(window._shown_storage):
        contents.addWidget(label("Select a storage item", "detailTitle", wrap=True))
        contents.addWidget(caption("Review where it lives, how big it is and what owns it before deciding anything."))
        contents.addStretch()
        return
    entry = window._shown_storage[index]
    rules = window.settings.get("never_touch", [])
    on_list = is_protected_path(Path(entry.path), rules)
    header = row(spacing=6)
    glyph = QLabel()
    kind_index = STORAGE_TYPES.index(entry.category) if entry.category in STORAGE_TYPES else 5
    glyph.setPixmap(icon(SYMBOLS.get(entry.category, "box"), STORAGE_COLORS[kind_index], 30).pixmap(30, 30))
    header.addWidget(glyph)
    titles = column(spacing=0)
    title = label(entry.name, "detailTitle", wrap=True)
    title.setTextFormat(Qt.PlainText)
    titles.addWidget(title)
    titles.addWidget(caption(entry.related))
    header.addLayout(titles, 1)
    header.addWidget(badge("Protected" if on_list else entry.badge))
    contents.addWidget(_widget(header))
    directx = entry.category == "Shader Cache" and any(word in entry.name for word in ("DirectX", "Direct3D"))
    contents.addWidget(ReferenceArt("other_storage", (998, 295, 262, 73) if directx else (870, 15, 330, 105), height=83))
    detail_section(contents, "Details")
    newest = datetime.fromtimestamp(entry.newest).strftime("%b %d, %Y") if entry.newest else "Unknown"
    protection = ("On your Never Touch list" if on_list else "Settings and saves are never removed" if entry.protected_kind
                  else "Review only" if not entry.cleanable else "Can be cleared in small verified runs")
    for symbol, title_text, value in (
        ("folder", "Location", entry.path),
        ("storage", "Size", human_size(entry.size) + (" (partly measured)" if entry.partial else "")),
        ("file", "Items", f"{entry.items:,} file{'s' if entry.items != 1 else ''}" + ("+" if entry.partial else "")),
        ("clock", "Last Modified", newest),
        ("shield", "Protection", protection),
    ):
        detail_line(contents, symbol, title_text, value)
    detail_section(contents, "What It Is")
    contents.addWidget(caption(entry.evidence, "subtle"))
    detail_section(contents, "Recommendation")
    contents.addWidget(caption(entry.note, "warning" if entry.protected_kind or not entry.cleanable else "subtle"))
    folder = str(Path(entry.path).parent) if entry.old_file is not None else entry.path
    contents.addWidget(tool("Open Folder", "folder", lambda: window._open_folder(folder)))
    if entry.category == "Shader Cache" and not entry.cleanable and entry.related != "No installed game":
        contents.addWidget(tool("Open Disk Cleanup", "settings", lambda: open_disk_cleanup()))
    if entry.old_file is not None:
        contents.addWidget(tool("Review in Old Files", "file", lambda: window.navigate("Old Files")))
    contents.addStretch()


# ------------------------------------------------------------------ scanning
def scan(window):
    state = state_of(window)
    if state.busy:
        state.cancel.set()
        state.message = "Canceling the scan…"
        fill(window)
        return
    if window.scanning or window.cleaning:
        window.info("Game Grave is busy", "Finish the current operation before scanning other storage.")
        return
    state.busy, state.cancel, state.message = True, threading.Event(), "Scanning known locations. Nothing is changed."
    cancel = state.cancel
    settings = dict(window.settings)
    games = list(window.inventory.steam)

    def work(progress):
        try:
            roots, libraries = steam_context(settings)
        except (OSError, ValueError):
            roots, libraries = [], []
        try:
            return data.discover(steam_roots=roots, libraries=libraries, games=games, canceled=cancel.is_set,
                                 progress=lambda text: progress(0, text))
        except InterruptedError:
            return None

    def progress(_, text):
        state.message = text
        if live(window):
            window.storage_notice.setText(text)
            window.storage_notice.setVisible(True)

    def done(report):
        state.busy = False
        if report is None:
            state.message = "Scan canceled. Earlier results are unchanged."
            window.status.setText(state.message)
        else:
            state.report, state.message = report, ""
            window._storage_key = None
            window.status.setText(report.summary() + ". Nothing was changed.")
        if live(window):
            window.storage_scan.setText("Scan Other Storage")
            window.storage_scan.setIcon(icon("refresh"))
            refresh(window)

    window.storage_scan.setText("Cancel Scan")
    window.storage_scan.setIcon(icon("close"))
    window.job(work, done, error_title="Other Storage scan failed", progress=progress)
    fill(window)


# ------------------------------------------------------------------ Graveyard review (loose files only)
def add_to_graveyard(window):
    rows = checked_entries(window)
    if not rows:
        window.info("Choose items", "Check the loose files or mod storage folders you want to keep in protected review.")
        return
    if window.scanning or window.cleaning:
        window.info("Game Grave is busy", "Finish the current operation first.")
        return
    mod_paths = {m.path for m in window.inventory.mods}
    files = [e.old_file for e in rows if e.old_file is not None]
    folders = [e.path for e in rows if e.old_file is None and e.path in mod_paths]
    left = len(rows) - len(files) - len(folders)
    if not files and not folders:
        window.info("Folders are reviewed here", "Only loose files and detected mod storage can be added to Graveyard review. "
                    "Use Protect to keep other folders out of any cleanup.")
        return
    updated = dict(window.settings)
    if files:
        values = {r["path"]: r for r in window.settings.get("manual_review_files", []) if isinstance(r, dict) and "path" in r}
        for file in files:
            values[file.path] = asdict(file)
        if len(values) > 1000:
            window.error("Review list full", "Review the existing items before adding more paths.")
            return
        updated["manual_review_files"] = list(values.values())
    if folders:
        updated["graveyard_watchlist"] = list(dict.fromkeys([*window.settings.get("graveyard_watchlist", []), *folders]))
    try:
        save_settings(updated)
    except (OSError, ValueError) as exc:
        window.error("Review list not saved", str(exc))
        return
    window.settings = updated
    if files:
        window._merge_manual_reviews()
    if folders:
        refresh_graveyard(window.inventory, window.settings)
    window.status.setText(f"{len(files) + len(folders)} item(s) added to protected Graveyard review. No files were moved.")
    window.info("Added to Graveyard review", f"{len(files) + len(folders)} item(s) added for review. No files were moved or removed." +
                (f" {left} other folder(s) stay here." if left else ""))


# ------------------------------------------------------------------ Delete… (verified, Recycle Bin, small runs)
def delete_selected(window):
    state = state_of(window)
    rows = checked_entries(window)
    if window.scanning or window.cleaning or state.busy:
        window.info("Game Grave is busy", "Finish the current operation first.")
        return
    rules = window.settings.get("never_touch", [])
    enabled, tip = insight.selection_state(rows, any(is_protected_path(Path(e.path), rules) for e in rows))
    if not enabled:
        window.info("Nothing to clear", tip)
        return
    window.cleaning = True
    window.storage_delete.setEnabled(False)

    def check(_progress):
        return actions.inspect(rows)

    def checked(found):
        window.cleaning = False
        problems = [f"{e.name}: {reason}" for e, plan, reason in found if plan is None]
        if problems:
            window.error("Cannot clear these folders", "\n".join(problems[:8]) + "\n\nNothing was removed.")
            selection_count(window)
            return
        plans = [plan for _, plan, _ in found]
        files = sum(len(p.files) for p in plans)
        size = sum(p.size for p in plans)
        skipped = sum(p.skipped for p in plans)
        names = "\n".join(f"  {p.entry.name}  ({len(p.files)} files, {human_size(p.size)})" for p in plans[:8])
        if not window.confirm(
                "Move these files to the Recycle Bin?",
                f"{files} verified files ({human_size(size)}) from {len(plans)} folder(s):\n{names}\n\n"
                "Close the launcher or program that owns these files first. Every file is re-checked right before it moves, "
                "and Windows must prove recovery works before each one, so this can take a while. "
                f"{skipped} unsafe or linked item(s) were left out. Nothing is permanently deleted, and "
                "files in the Recycle Bin may still occupy disk space.", destructive=True):
            selection_count(window)
            return
        window.cleaning = True
        session = "crimson-storage-" + uuid.uuid4().hex[:10]
        never = tuple(window.settings.get("never_touch", []))

        def run(progress):
            outcome = actions.recycle(plans, never, session)
            remeasured = {}
            for plan in plans:
                try:
                    remeasured[plan.entry.key] = data.measure(plan.root)
                except OSError:
                    remeasured[plan.entry.key] = None
            return outcome, remeasured

        def complete(result):
            outcome, remeasured = result
            window.cleaning = False
            report = state.report
            keys = {p.entry.key for p in plans}
            if report is not None:
                updated = []
                for entry in report.entries:
                    if entry.key in keys:
                        found_now = remeasured.get(entry.key)
                        if found_now is None or found_now.files == 0:
                            continue
                        entry = replace(entry, size=found_now.bytes, items=found_now.files, newest=found_now.newest,
                                        partial=found_now.partial)
                    updated.append(entry)
                report.entries = updated
                window._storage_key = None
            window.status.setText(f"{outcome['completed']} file(s) moved to Recycle Bin. They may still occupy disk space.")
            if live(window):
                refresh(window)
            window.info("Other Storage cleanup completed",
                        f"{outcome['completed']} moved to Recycle Bin, {len(outcome['skipped'])} skipped." +
                        ("\n" + "\n".join(outcome["skipped"][:8]) if outcome["skipped"] else ""))
        window.job(run, complete, error_title="Other Storage cleanup blocked")

    window.job(check, checked, error_title="Other Storage check failed")
