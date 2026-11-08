"""Graveyard page: the owner's photo layout on evidence Game Grave already has.

Items come from the existing Graveyard engine and, when you press Scan Leftovers, a read-only look at known
config, cache, log and shader-cache folders. Nothing is called safe or unused: age is shown as a signal and each
item says what proves it. Removal is only the existing Recycle Bin path for single ordinary files, after the
usual confirmation and per-file re-checks. Games go through Steam, mods through Mods, folders through Other Storage.
"""
from __future__ import annotations

import csv
import io
import os
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QRect, QSignalBlocker, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QFileDialog, QHeaderView, QLabel, QMenu,
                               QPushButton, QScrollArea, QSizePolicy, QStyle, QStyledItemDelegate, QStyleOptionViewItem,
                               QVBoxLayout, QWidget)
from shiboken6 import isValid

from core import human_size, is_protected_path
from gg_desktop import grave_actions as actions
from gg_desktop import grave_data as data
from gg_desktop import grave_insight as insight
from gg_desktop.header_banner import HeaderBannerArtwork
from gg_desktop.insight_widgets import ActionFlow
from gg_desktop.reference_library import _check, _combo, _detail_scroll, _search, _split, _table, _text, _widget
from gg_desktop.reference_widgets import (CoverArt, DetailPanel, InventoryPager, MetricStrip, TabStrip, detail_line,
                                          icon, tool)
from gg_desktop.widgets import button, column, destroy_layout, label, panel, row
from ui_paging import page_window

TAB_ICONS = {"All Items": "storage", "Games": "game", "Mods": "mods", "Downloads": "download", "Configs": "settings",
             "Leftovers": "box", "Orphans": "trash"}
KIND_ICONS = {data.TYPES[0]: "game", data.TYPES[1]: "mods", data.TYPES[2]: "download", data.TYPES[3]: "storage",
              data.TYPES[4]: "settings", data.TYPES[5]: "camera", data.TYPES[6]: "folder"}
PILL_COLORS = {"Direct": "#27dc74", "Location": "#2ec4ff", "Name hint": "#f7b737", "Age only": "#9ca8bd", "Yours": "#c26cff"}
TONES = {"shield": "#f7b737", "trash": "#27dc74", "camera": "#2ec4ff", "game": "#9ca8bd", "mods": "#9ca8bd",
         "storage": "#9ca8bd", "undo": "#9ca8bd"}
EMPTY = {
    "Games": "No installed Steam game has an old last-play record.",
    "Mods": "No old mod folders were found by the last PC scan.",
    "Downloads": "No old game-looking archives were found by the last PC scan.",
    "Configs": "No config folders found yet. Scan Leftovers checks My Games, Saved Games and similar known locations.",
    "Leftovers": "Nothing found yet. Scan Leftovers checks known cache, log and temporary locations.",
    "Orphans": "No orphaned Steam shader caches found yet. Scan Leftovers compares Steam's shader cache folders with your installed games.",
}
PAGE_SIZE = 100


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
        sub = str(index.data(Qt.UserRole) or "")
        painter.save()
        bold = font_delta(opt.font, 0.5)
        bold.setBold(True)
        painter.setFont(bold)
        painter.setPen(QColor("#f4f7fc"))
        if not sub:
            painter.drawText(rect, int(Qt.AlignLeft | Qt.AlignVCenter), QFontMetrics(bold).elidedText(title, Qt.ElideRight, rect.width()))
            painter.restore()
            return
        half = rect.height() // 2
        top = QRect(rect.left(), rect.top() + 3, rect.width(), half)
        painter.drawText(top, int(Qt.AlignLeft | Qt.AlignVCenter), QFontMetrics(bold).elidedText(title, Qt.ElideRight, top.width()))
        small = font_delta(opt.font, -1.5)
        painter.setFont(small)
        painter.setPen(QColor("#9ca8bd"))
        bottom = QRect(rect.left(), rect.top() + half, rect.width(), half - 2)
        painter.drawText(bottom, int(Qt.AlignLeft | Qt.AlignVCenter), QFontMetrics(small).elidedText(sub, Qt.ElideRight, bottom.width()))
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


class ElidedLabel(QLabel):
    clicked = Signal()

    def __init__(self, text):
        super().__init__(text)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(QColor("#d3dae3"))
        painter.setFont(self.font())
        painter.drawText(self.rect(), int(Qt.AlignLeft | Qt.AlignVCenter),
                         QFontMetrics(self.font()).elidedText(self.text(), Qt.ElideRight, self.width()))

    def mousePressEvent(self, event):
        self.clicked.emit()


class CheckRow(QWidget):
    """A checkbox, its name and a right-aligned live count, like the photo's filter lists."""

    def __init__(self, text, checked=False):
        super().__init__()
        line = row(spacing=6, margins=(2, 0, 2, 0))
        self.setLayout(line)
        self.setMinimumWidth(0)
        self.setFixedHeight(22)
        self.box = QCheckBox()
        self.box.setChecked(checked)
        self.box.setAccessibleName(text)
        self.name = ElidedLabel(text)
        self.name.setToolTip(text)
        self.name.clicked.connect(self.box.toggle)
        self.count = QLabel("0")
        self.count.setStyleSheet("color:#9ca8bd;font-size:10px;")
        self.count.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        line.addWidget(self.box)
        line.addWidget(self.name, 1)
        line.addWidget(self.count)

    def set_count(self, value):
        self.count.setText(f"{value:,}")


class Section(QWidget):
    """A collapsible section with a chevron, like the photo."""

    def __init__(self, title, body, expanded=True):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(3)
        self.head = QPushButton()
        self.head.setFlat(True)
        self.head.setCursor(Qt.PointingHandCursor)
        self.head.setFixedHeight(30)
        self.head.setAccessibleName(title)
        self.head.setStyleSheet("QPushButton{border:0;border-top:1px solid #1f2b36;padding:0;text-align:left;}"
                                "QPushButton:hover{background:#0f1923;}")
        line = row(spacing=4, margins=(2, 2, 2, 2))
        self.head.setLayout(line)
        name = QLabel(title)
        name.setStyleSheet("font-weight:600;color:#eef3f8;")
        name.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.arrow = QLabel()
        self.arrow.setAttribute(Qt.WA_TransparentForMouseEvents)
        line.addWidget(name, 1)
        line.addWidget(self.arrow)
        self.body = body
        outer.addWidget(self.head)
        outer.addWidget(body)
        self.head.clicked.connect(lambda: self.set_open(not self.body.isVisible()))
        self.set_open(expanded)

    def set_open(self, opened):
        self.body.setVisible(opened)
        self.arrow.setText("▾" if opened else "▸")


class Adaptive(QWidget):
    """A header row that shows its optional parts only when there is room for them."""

    def __init__(self, extras, threshold):
        super().__init__()
        self.extras, self.threshold = extras, threshold
        self.setMinimumWidth(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        room = event.size().width() >= self.threshold
        for control in self.extras:
            if control.isVisibleTo(self) != room:
                control.setVisible(room)


# ------------------------------------------------------------------ state
def state_of(window):
    if not hasattr(window, "_grave_state"):
        window._grave_state = SimpleNamespace(
            busy=False, cancel=threading.Event(), report=None, scanned=False, message="", checked=set(),
            tab="All Items", all=None, all_key=None, compact=False, subtab="Details")
    return window._grave_state


def live(window):
    return (window.current_route == "Graveyard" and hasattr(window, "grave_table") and isValid(window.grave_table)
            and hasattr(window.page, "grave_ready"))


def never_touch(window):
    return window.settings.get("never_touch", [])


def guarded(fn):
    """Run in a worker and return (status, value) so a failure always reaches the page, never strands it."""
    def run(progress):
        try:
            return "ok", fn(progress)
        except InterruptedError:
            return "canceled", None
        except Exception as exc:  # reported on the page
            return "error", f"{type(exc).__name__}: {str(exc)[:300]}"
    return run


def universe(window):
    state = state_of(window)
    report = state.report
    inv = window.inventory
    key = (id(report), len(report.entries) if report else 0, id(inv.graveyard), len(inv.graveyard))
    if state.all_key != key:
        scanned = data.from_storage(report.entries) if report else []
        state.all = data.merge(data.from_graveyard(inv.graveyard), scanned)
        state.all_key = key
    return state.all


def invalidate(window):
    state_of(window).all_key = None


# ------------------------------------------------------------------ page
def build(window):
    self = window
    state = state_of(self)
    pending = getattr(self, "_pending_grave_key", None)
    if pending and any(i.key == pending for i in universe(self)):
        state.tab = "All Items"
    state.tab = state.tab if state.tab in data.TABS else "All Items"
    page = self._insight_page("Graveyard", "Unearth old and leftover game files, mods, and data. Review what the evidence shows, "
                              "then clean up with full control.", "graveyard", None, 74)
    page.banner_artwork = HeaderBannerArtwork(self, page, page.content.itemAt(0).widget(), route="Graveyard",
                                              scene="graveyard", source=(700, 0, 580, 126), excluded=((1090, 0, 190, 40),))
    self.grave_metrics = MetricStrip([
        ("storage", "0", "Items Found", "#df74e9"), ("storage", "0 B", "Total Size", "#15c7ed"),
        ("clock", "0", "Not Touched 6+ Mo", "#f8c82c"), ("game", "0", "Related Games", "#ff2145"),
        ("mods", "0", "Mods / Addons", "#d76ce6"), ("download", "0", "Downloads", "#16baf1"),
        ("shield", "0", "Reviewable", "#2bd971")], compact=True)
    page.content.addWidget(self.grave_metrics)
    self.grave_tabs = TabStrip([(name, TAB_ICONS[name]) for name in data.TABS], selected=state.tab)
    for control in self.grave_tabs.buttons.values():
        control.setStyleSheet("font-size:11px; padding:4px 3px;")
        control.setIconSize(QSize(15, 15))
    page.content.addWidget(self.grave_tabs)

    # --- Scan & Filter
    filters, side = panel(kind="fileFilterPanel", padding=8, spacing=4)
    filters.setMinimumWidth(150)
    filters.setMaximumWidth(215)
    head = row(spacing=4)
    glyph = QLabel()
    glyph.setPixmap(icon("filter", "#ff3b57", 17).pixmap(17, 17))
    head.addWidget(glyph)
    head.addWidget(label("Scan & Filter", "sectionTitle"), 1)
    clear = QPushButton("Clear All")
    clear.setObjectName("link")
    clear.clicked.connect(lambda: clear_filters(self))
    head.addWidget(clear)
    side.addLayout(head)
    holder = QWidget()
    stack = column(spacing=4)
    holder.setLayout(stack)
    self.grave_age_rows = {l: CheckRow(l) for l in insight.AGE_LABELS}
    self.grave_size_rows = {l: CheckRow(l) for l in insight.SIZE_LABELS}
    self.grave_type_rows = {l: CheckRow(l, True) for l in data.TYPES}
    for title, rows in (("Age (Not Touched)", self.grave_age_rows), ("Size", self.grave_size_rows), ("Type", self.grave_type_rows)):
        body = QWidget()
        lay = column(spacing=1)
        body.setLayout(lay)
        for control in rows.values():
            lay.addWidget(control)
        stack.addWidget(Section(title, body, True))
    stack.addStretch()
    scroller = QScrollArea()
    scroller.setWidgetResizable(True)
    scroller.setFrameShape(QScrollArea.NoFrame)
    scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroller.setStyleSheet("QScrollArea{background:transparent;} QScrollArea > QWidget > QWidget{background:transparent;}")
    scroller.setWidget(holder)
    side.addWidget(scroller, 1)

    # --- Results
    results, contents = panel(kind="fileResults", padding=7, spacing=5)
    header = row(spacing=4)
    mark = QLabel()
    mark.setPixmap(icon("grave", "#ff3b57", 18).pixmap(18, 18))
    header.addWidget(mark)
    self.grave_heading = label("Graveyard Items", "sectionTitle")
    self.grave_heading.setMinimumWidth(0)
    self.grave_heading.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    header.addWidget(self.grave_heading, 1)
    sort_caption = label("Sort By:", "caption")
    header.addWidget(sort_caption)
    self.grave_sort = _combo(list(insight.SORTS), "Sort Graveyard items")
    self.grave_sort.setMinimumWidth(100)
    self.grave_sort.setMaximumWidth(165)
    header.addWidget(self.grave_sort)
    self.grave_view_grid = tool("", "grid", lambda: set_compact(self, False), active=not state.compact, tip="Detailed rows")
    self.grave_view_list = tool("", "list", lambda: set_compact(self, True), active=state.compact, tip="Compact rows")
    for control in (self.grave_view_grid, self.grave_view_list):
        control.setFixedSize(26, 28)
        header.addWidget(control)
    top = Adaptive([sort_caption], 400)
    top.setLayout(header)
    contents.addWidget(top)
    self.grave_search = _search("Search games, files, mods, or Graveyard items…", "Search Graveyard")
    self.grave_search.hide()  # the shared search above the page drives this field
    contents.addWidget(self.grave_search)
    notice_row = row(spacing=6)
    self.grave_notice = label("", "caption", wrap=True)
    self.grave_notice.setTextFormat(Qt.PlainText)
    notice_row.addWidget(self.grave_notice, 1)
    self.grave_action = QPushButton("")
    self.grave_action.clicked.connect(lambda: contextual_action(self))
    self.grave_action.hide()
    notice_row.addWidget(self.grave_action)
    contents.addWidget(_widget(notice_row))
    self.grave_table = _table(["", "Name", "Related Game / Source", "Last Touched", "Size", "Evidence"])
    for c, width in enumerate((24, 150, 104, 82, 62, 74)):
        self.grave_table.setColumnWidth(c, width)
    self.grave_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
    self.grave_table.setSelectionMode(QAbstractItemView.SingleSelection)
    self.grave_table.setItemDelegateForColumn(1, NameDelegate(self.grave_table))
    self.grave_table.setItemDelegateForColumn(5, PillDelegate(self.grave_table))
    contents.addWidget(self.grave_table, 1)
    self.grave_pager = InventoryPager()
    self.grave_pager.changed.connect(lambda number: fill(self, requested_page=number))
    contents.addWidget(self.grave_pager)
    self.grave_details = DetailPanel()
    page.content.addWidget(_split(_split(filters, results, [205, 520]), _detail_scroll(self.grave_details), [735, 292]), 1)

    # --- Footer
    bar_panel, bar = panel(kind="fileResults", padding=7, spacing=0)
    footer = ActionFlow(spacing=8)
    self.grave_select_all = QCheckBox("0 selected (0 B)")
    self.grave_select_all.setTristate(False)
    self.grave_select_all.clicked.connect(lambda checked: select_visible(self, checked))
    footer.addWidget(self.grave_select_all)
    footer.addWidget(tool("Protect", "shield", lambda: protect(self), tip="Adds Never Touch rules for the checked items"))
    footer.addWidget(tool("Unprotect", "shield", lambda: unprotect(self), tip="Removes your own rule for one checked item"))
    footer.addWidget(tool("Restore", "undo", lambda: self.navigate("Undo Center"),
                          tip="Opens Undo Center, where everything moved to the Recycle Bin can be restored"))
    self.grave_delete = tool("Delete…", "trash", None, kind="danger", tip="Removal choices for the checked items")
    self.grave_delete_menu = QMenu(self.grave_delete)
    self.grave_delete_menu.aboutToShow.connect(lambda: build_delete_menu(self))
    self.grave_delete.setMenu(self.grave_delete_menu)
    footer.addWidget(self.grave_delete)
    self.grave_more = tool("More", "settings", None, tip="Open, copy, export, select and scan tools")
    self.grave_menu = QMenu(self.grave_more)
    self.grave_more.setMenu(self.grave_menu)
    footer.addWidget(self.grave_more)
    bar.addWidget(_widget(footer))
    page.content.addWidget(bar_panel)
    build_menu(self)

    page.grave_ready = True
    self.grave_tabs.changed.connect(lambda name: set_tab(self, name.split(" (")[0]))
    self.grave_sort.currentTextChanged.connect(lambda *_: fill(self))
    for control in [*self.grave_age_rows.values(), *self.grave_size_rows.values(), *self.grave_type_rows.values()]:
        control.box.toggled.connect(lambda *_: fill(self))
    self.grave_search.textChanged.connect(lambda *_: fill(self))
    self.grave_table.itemSelectionChanged.connect(lambda: details(self))
    self.grave_table.itemChanged.connect(lambda item: table_checked(self, item))
    refresh(self)


def build_menu(window):
    menu = window.grave_menu
    menu.clear()
    for entry in (
        ("Open Containing Folder", lambda: open_folder(window)),
        ("Copy File Paths", lambda: copy_paths(window)), ("Export List (CSV)…", lambda: export_csv(window)), None,
        ("Select Reviewable Files", lambda: select_reviewable(window)),
        ("Select All Shown", lambda: select_visible(window, True)),
        ("Clear Selection", lambda: select_visible(window, False)), None,
        ("Scan Leftovers", lambda: scan(window)),
    ):
        if entry is None:
            menu.addSeparator()
        else:
            menu.addAction(entry[0], entry[1])


def build_delete_menu(window):
    menu = window.grave_delete_menu
    menu.clear()
    items = selected_items(window, fallback=True)
    handlers = {"recycle": lambda: recycle(window), "preview": lambda: preview(window), "steam": lambda: steam_uninstall(window),
                "mods": lambda: window.navigate("Mods"), "storage": lambda: window.navigate("Other Storage")}
    for key, text, enabled, tip in insight.delete_options(items, never_touch(window)):
        action = menu.addAction(text, handlers[key])
        action.setEnabled(enabled and not state_of(window).busy and not window.cleaning and not window.scanning)
        action.setToolTip(tip)
        action.setStatusTip(tip)


# ------------------------------------------------------------------ filters, counts, summary
def current_filters(window):
    state = state_of(window)
    return dict(
        tab=state.tab,
        ages=tuple(l for l, c in window.grave_age_rows.items() if c.box.isChecked()),
        sizes=tuple(l for l, c in window.grave_size_rows.items() if c.box.isChecked()),
        types=tuple(l for l, c in window.grave_type_rows.items() if c.box.isChecked()),
        query=window.grave_search.text())


def rows_now(window):
    return insight.filter_items(universe(window), sort=window.grave_sort.currentText(), **current_filters(window))


def clear_filters(window):
    for control in [*window.grave_age_rows.values(), *window.grave_size_rows.values()]:
        with QSignalBlocker(control.box):
            control.box.setChecked(False)
    for control in window.grave_type_rows.values():
        with QSignalBlocker(control.box):
            control.box.setChecked(True)
    with QSignalBlocker(window.grave_search):
        window.grave_search.clear()
    state_of(window).tab = "All Items"
    window.grave_tabs.select("All Items")
    fill(window)


def set_tab(window, name):
    state_of(window).tab = name
    fill(window)


def set_compact(window, compact):
    state_of(window).compact = compact
    set_active(window.grave_view_grid, not compact)
    set_active(window.grave_view_list, compact)
    fill(window)


def set_active(control, on):
    control.setProperty("active", on)
    control.style().unpolish(control)
    control.style().polish(control)


def refresh(window):
    """Metrics, tab counts and filter counts from the current items, then the table."""
    items = universe(window)
    t = insight.totals(items, never_touch(window))
    strip = window.grave_metrics
    strip.set_value(0, f"{t['items']:,}")
    strip.set_value(1, human_size(t["bytes"]))
    strip.set_value(2, f"{t['idle']:,}")
    strip.set_value(3, f"{t['games']:,}")
    strip.set_value(4, f"{t['mods']:,}")
    strip.set_value(5, f"{t['downloads']:,}")
    strip.set_value(6, f"{t['reviewable']:,}")
    report = state_of(window).report
    strip.setToolTip((report.summary() + "." if report else
                      "Findings from the last PC scan. Scan Leftovers also checks known config, cache, log and shader-cache folders.")
                     + "\nNot Touched counts items whose last known use or change is over 6 months ago. Age alone does not make an item unwanted."
                       "\nReviewable counts single ordinary files that can move to the Recycle Bin after you confirm. It does not mean safe to remove.")
    counts = insight.tab_counts(items)
    for name, control in window.grave_tabs.buttons.items():
        control.setText(f"{name} ({counts[name]:,})")
    fill(window)


def update_facets(window, rows_scope):
    filters = current_filters(window)
    age, size, kind = insight.facet_counts(rows_scope, **filters)
    for name, control in window.grave_age_rows.items():
        control.set_count(age[name])
    for name, control in window.grave_size_rows.items():
        control.set_count(size[name])
    for name, control in window.grave_type_rows.items():
        control.set_count(kind[name])


# ------------------------------------------------------------------ table
def fill(window, *args, requested_page=0, **kwargs):
    if not live(window):
        return
    state = state_of(window)
    items = universe(window)
    rows = rows_now(window)
    window._grave_rows = rows
    state.checked &= {i.key for i in items}
    pending = getattr(window, "_pending_grave_key", None)
    previous = current_item(window)
    if pending:
        index = next((n for n, i in enumerate(rows) if i.key == pending), None)
        requested_page = 0 if index is None else index // PAGE_SIZE
    page = page_window(rows, requested_page, PAGE_SIZE)
    window.grave_pager.update_window(page)
    window._shown_graves = list(page.items)
    fill_table(window, previous, pending)
    window._pending_grave_key = None
    window.grave_heading.setText(f"Graveyard Items ({len(rows):,})")
    update_facets(window, items)
    update_notice(window, rows)
    selection_count(window)
    details(window)


def fill_table(window, previous, pending=None):
    state = state_of(window)
    table = window.grave_table
    rules = never_touch(window)
    with QSignalBlocker(table):
        table.setRowCount(0)
        table.setRowCount(len(window._shown_graves))
        for n, item in enumerate(window._shown_graves):
            _check(table, n)
            if item.key in state.checked:
                table.item(n, 0).setCheckState(Qt.Checked)
            protected = data.is_protected(item, rules)
            name = _text(table, n, 1, item.name, KIND_ICONS.get(item.kind, "file"), "#e5b72e")
            name.setData(Qt.UserRole, "" if state.compact else item.subtitle + (" · Protected" if protected else ""))
            name.setToolTip(f"{item.name}\n{item.path}")
            _text(table, n, 2, item.related)
            _text(table, n, 3, insight.date_text(item))
            _text(table, n, 4, human_size(item.size))
            _text(table, n, 5, item.evidence).setToolTip(data.EVIDENCE_TEXT[item.evidence])
            if insight.protection_state(item, rules)[0] == "Unprotect":
                # your own rule can be removed right in the row; the Evidence pill returns afterwards
                unlock = button("Unprotect", lambda _=False, entry=item: window._unprotect_grave(entry))
                unlock.setAccessibleName("Unprotect your personal rule for " + item.name)
                unlock.setToolTip("Remove this exact personal rule after confirmation. No file is removed.\nEvidence: "
                                  + data.EVIDENCE_TEXT[item.evidence])
                unlock.setFixedHeight(24)
                unlock.setStyleSheet("font-size:10px; padding:0 4px;")
                table.setCellWidget(n, 5, unlock)
            table.setRowHeight(n, 30 if state.compact else 44)
        if window._shown_graves:
            wanted = pending or (previous.key if previous else None)
            index = next((n for n, i in enumerate(window._shown_graves) if i.key == wanted), 0)
            table.selectRow(index)
            if pending:
                table.scrollToItem(table.item(index, 0))


def update_notice(window, rows):
    state = state_of(window)
    notice, action = "", ""
    if state.busy:
        notice, action = state.message or "Scanning known locations. Nothing is changed.", "Cancel"
    elif not rows:
        here = [i for i in universe(window) if state.tab == "All Items" or i.tab == state.tab]
        if here:
            notice = "No items match these filters."
        else:
            notice = EMPTY.get(state.tab, "Nothing found yet. Scan Leftovers checks known game-related locations.")
        if not state.scanned and state.tab in ("All Items", "Configs", "Leftovers", "Orphans"):
            action = "Scan Leftovers"
    elif not state.scanned and state.tab in ("All Items", "Configs", "Leftovers", "Orphans"):
        notice = ("Showing findings from the last PC scan. Scan Leftovers also checks known config, cache, log and "
                  "shader-cache folders. Nothing is changed.")
        action = "Scan Leftovers"
    elif state.tab == "Orphans":
        notice = "Orphan means Steam has a shader cache folder for an app ID with no installed game in the scanned libraries."
    window.grave_notice.setText(notice)
    window.grave_notice.setVisible(bool(notice))
    window.grave_action.setText(action)
    window.grave_action.setVisible(bool(action))


def contextual_action(window):
    state = state_of(window)
    if state.busy:
        state.cancel.set()
        state.message = "Canceling…"
        update_notice(window, getattr(window, "_grave_rows", []))
    else:
        scan(window)


# ------------------------------------------------------------------ selection
def current_item(window):
    index = window.grave_table.currentRow() if hasattr(window, "grave_table") and isValid(window.grave_table) else -1
    shown = getattr(window, "_shown_graves", [])
    return shown[index] if 0 <= index < len(shown) else None


def table_checked(window, item):
    if item.column() != 0 or not 0 <= item.row() < len(window._shown_graves):
        return
    state = state_of(window)
    key = window._shown_graves[item.row()].key
    (state.checked.add if item.checkState() == Qt.Checked else state.checked.discard)(key)
    selection_count(window)


def selected_items(window, fallback=False):
    state = state_of(window)
    rows = [i for i in universe(window) if i.key in state.checked]
    if not rows and fallback:
        current = current_item(window)
        return [current] if current else []
    return rows


def select_visible(window, selected):
    state = state_of(window)
    keys = {i.key for i in getattr(window, "_grave_rows", [])}
    state.checked = (state.checked | keys) if selected else (state.checked - keys)
    sync_checks(window)


def sync_checks(window):
    state = state_of(window)
    with QSignalBlocker(window.grave_table):
        for n, item in enumerate(window._shown_graves):
            if window.grave_table.item(n, 0):
                window.grave_table.item(n, 0).setCheckState(Qt.Checked if item.key in state.checked else Qt.Unchecked)
    selection_count(window)


def select_reviewable(window):
    """Check the single ordinary files the Recycle Bin path accepts, up to its per-run limit."""
    state = state_of(window)
    rules = never_touch(window)
    rows = getattr(window, "_grave_rows", None)
    if rows is None:
        rows = list(getattr(window, "_shown_graves", []))
    chosen = [i for i in rows if insight.recyclable(i) and not data.is_protected(i, rules)]
    state.checked = {i.key for i in chosen[:insight.MAX_RECYCLE]}
    sync_checks(window)
    if len(chosen) > insight.MAX_RECYCLE:
        window.status.setText(f"{insight.MAX_RECYCLE} of {len(chosen):,} reviewable files checked, the most one run can move.")


def selection_count(window):
    if not live(window):
        return
    rows = selected_items(window)
    box = window.grave_select_all
    total = len(getattr(window, "_grave_rows", []))
    with QSignalBlocker(box):
        box.setText(f"{len(rows):,} selected ({insight.size_text(rows)})")
        box.setChecked(bool(total) and len(rows) >= total and all(i.key in state_of(window).checked for i in window._grave_rows))


# ------------------------------------------------------------------ details
def pill(text, color):
    item = QLabel(text)
    item.setStyleSheet(f"color:{color}; border:1px solid {color}; border-radius:9px; padding:2px 8px; font-size:10px;")
    item.setAlignment(Qt.AlignCenter)
    return item


def status_badge(item, rules):
    if data.is_protected(item, rules):
        return "Protected", "#f7b737"
    if insight.recyclable(item):
        return "Reviewable", "#27dc74"
    if insight.needs_preview(item):
        return "Preview first", "#2ec4ff"
    return "Review only", "#9ca8bd"


def details(window):
    if not live(window):
        return
    state = state_of(window)
    contents = window.grave_details.content
    destroy_layout(contents)
    contents.setSpacing(5)
    item = current_item(window)
    if item is None:
        contents.addWidget(label("Select an item", "detailTitle"))
        contents.addWidget(label("Review the evidence and protection before choosing an action.", "subtle", wrap=True))
        contents.addStretch()
        return
    rules = never_touch(window)
    header = row(spacing=6)
    glyph = QLabel()
    glyph.setPixmap(icon(KIND_ICONS.get(item.kind, "file"), "#f1c232", 28).pixmap(28, 28))
    header.addWidget(glyph)
    title = label(item.name, "detailTitle", wrap=True)
    title.setTextFormat(Qt.PlainText)
    header.addWidget(title, 1)
    text, color = status_badge(item, rules)
    header.addWidget(pill(text, color))
    contents.addWidget(_widget(header))
    contents.addWidget(label(f"{human_size(item.size)} · {insight.items_text(item)}", "caption"))
    contents.addWidget(CoverArt(item.game or "Game Grave", height=83))
    refs = references_for(window, item)
    chips = TabStrip([("Details", "file"), (f"Contents ({item.items:,})" if item.items else "Contents", "box"),
                      (f"References ({len(refs)})" if refs else "References", "shield")], framed=False)
    keys = list(chips.buttons)
    pick = next((k for k in keys if k.startswith(state.subtab)), keys[0])
    chips.select(pick)
    chips.changed.connect(lambda name: (setattr(state, "subtab", name.split(" (")[0]), details(window)))
    contents.addWidget(chips)
    if pick.startswith("Contents"):
        contents_list(item, contents)
    elif pick.startswith("References"):
        references_list(window, item, refs, contents)
    else:
        item_details(window, item, rules, contents)
    contents.addStretch()


def item_details(window, item, rules, contents):
    for symbol, name, value in (
        ("game", "Related Game", item.related), ("folder", "Location", item.path),
        ("clock", "Last Touched", insight.age_phrase(item)),
        ("storage", "Size", human_size(item.size) + (" (partly measured)" if item.partial else "")),
        ("box", "Type", item.kind), ("file", "Items", insight.items_text(item)),
        ("shield", "Evidence", item.evidence),
    ):
        detail_line(contents, symbol, name, value)
    why_body = QWidget()
    why = column(spacing=3, margins=(0, 0, 0, 0))
    why_body.setLayout(why)
    why.addWidget(label(item.why, "subtle", wrap=True))
    why.addWidget(label(data.EVIDENCE_TEXT[item.evidence], "caption", wrap=True))
    if item.note:
        why.addWidget(label(item.note, "caption", wrap=True))
    contents.addWidget(Section("Why It's in the Graveyard", why_body, True))
    can_body = QWidget()
    can = column(spacing=3, margins=(0, 0, 0, 0))
    can_body.setLayout(can)
    for symbol, text in insight.reasons(item, rules):
        line = QWidget()
        box = row(spacing=6)
        line.setLayout(box)
        mark = QLabel()
        mark.setPixmap(icon("check" if symbol in ("trash", "undo") else "shield" if symbol == "shield" else symbol,
                            TONES.get(symbol, "#9ca8bd"), 14).pixmap(14, 14))
        mark.setAlignment(Qt.AlignTop)
        box.addWidget(mark)
        box.addWidget(label(text, "subtle", wrap=True), 1)
        can.addWidget(line)
    contents.addWidget(Section("What You Can Do", can_body, True))
    buttons = ActionFlow(spacing=6)
    if insight.needs_preview(item):
        buttons.addWidget(tool("Preview", "camera", lambda: preview(window, preview_only=True), kind="primary"))
    if item.tab == "Games" and actions.uninstall_url(item):
        buttons.addWidget(tool("Steam", "steam", lambda: steam_uninstall(window)))
    buttons.addWidget(tool("Folder", "folder", lambda: open_folder(window)))
    contents.addWidget(_widget(buttons))


def contents_list(item, contents):
    if not item.is_folder_item:
        detail_line(contents, "file", "File", item.name)
        detail_line(contents, "storage", "Size", human_size(item.size))
        contents.addWidget(label("A single file. Nothing is opened.", "caption", wrap=True))
        return
    rows, truncated = actions.list_contents(item.path)
    if not rows:
        contents.addWidget(label("Nothing could be listed. The folder may be empty, unreadable or moved.", "subtle", wrap=True))
        return
    for name, kind, size in rows:
        detail_line(contents, "folder" if kind == "folder" else "file", name, "Folder" if kind == "folder" else
                    "Link, not entered" if kind == "link" else human_size(size))
    contents.addWidget(label("Names only" + (f", first {len(rows)} shown" if truncated else "") + ". Nothing is opened or changed.",
                             "caption", wrap=True))


def references_for(window, item):
    """Other Graveyard items tied to this one by the same proven game or the same folder."""
    found = []
    for other in universe(window):
        if other.key == item.key:
            continue
        if item.game and other.game == item.game:
            found.append(("Same game", other))
        elif other.folder == item.folder and not (item.is_folder_item and other.is_folder_item):
            found.append(("Same folder", other))
    return found


def references_list(window, item, refs, contents):
    rules = never_touch(window)
    covering = [r for r in rules if isinstance(r, str) and is_protected_path(Path(item.path), [r])]
    detail_line(contents, "shield", "Never Touch", "; ".join(covering[:3]) if covering else "No personal rule covers this")
    if item.game:
        detail_line(contents, "game", "Proven game", item.game)
        contents.addWidget(tool("Open Games", "game", lambda: window.navigate("Games")))
    if not refs:
        contents.addWidget(label("No other Graveyard item shares this game or folder.", "subtle", wrap=True))
    for reason, other in refs[:8]:
        contents.addWidget(tool(other.name, KIND_ICONS.get(other.kind, "file"), lambda _=False, o=other: focus_item(window, o), tip=reason))
        contents.addWidget(label(f"{reason} · {human_size(other.size)}", "caption"))
    contents.addWidget(tool("Open Undo Center", "undo", lambda: window.navigate("Undo Center")))


def focus_item(window, item):
    rows = getattr(window, "_grave_rows", [])
    if item.key not in {i.key for i in rows}:
        clear_filters(window)
        rows = getattr(window, "_grave_rows", [])
    index = next((n for n, i in enumerate(rows) if i.key == item.key), None)
    if index is None:
        return
    fill(window, requested_page=index // PAGE_SIZE)
    local = index % PAGE_SIZE
    if local < window.grave_table.rowCount():
        window.grave_table.selectRow(local)


# ------------------------------------------------------------------ open, copy, export
def open_folder(window):
    item = current_item(window)
    if item is None:
        window.info("Choose an item", "Select an item to open its folder.")
        return
    window._open_folder(item.path if item.is_folder_item else item.folder)


def copy_paths(window):
    rows = selected_items(window, fallback=True)
    if not rows:
        window.info("Choose items", "Check the items whose paths you want to copy.")
        return
    QGuiApplication.clipboard().setText("\n".join(i.path for i in rows))
    window.status.setText(f"Copied {len(rows)} path(s).")


def export_csv(window):
    rows = getattr(window, "_grave_rows", [])
    if not rows:
        window.info("Nothing to export", "No items are shown.")
        return
    chosen, _ = QFileDialog.getSaveFileName(window, "Export the shown Graveyard items as a list", "graveyard.csv", "CSV (*.csv)")
    if not chosen:
        return
    buffer = io.StringIO()
    out = csv.writer(buffer)
    for line in insight.csv_rows(rows):
        out.writerow(line)
    try:
        Path(chosen).write_text(buffer.getvalue(), encoding="utf-8", newline="")
    except OSError as exc:
        window.error("List not saved", str(exc))
        return
    window.status.setText(f"Exported {len(rows):,} items to {chosen}. Nothing was changed.")


# ------------------------------------------------------------------ scanning
def scan(window, automatic=False):
    state = state_of(window)
    if state.busy:
        return
    if window.scanning or window.cleaning:
        if not automatic:
            window.info("Game Grave is busy", "Finish the current operation before scanning leftovers.")
        return
    state.busy, state.cancel, state.message = True, threading.Event(), "Checking known locations. Nothing is changed."
    cancel = state.cancel
    settings = dict(window.settings)
    games = list(window.inventory.steam)

    def work(progress):
        return data.discover_leftovers(settings, games, cancel.is_set, lambda text: progress(0, text))

    def progress(_, text):
        state.message = text
        if live(window) and state.busy:
            window.grave_notice.setText(text)
            window.grave_notice.setVisible(True)

    def done(outcome):
        status, report = outcome
        state.busy = False
        state.message = ""
        if status == "error":
            window.status.setText("Leftover scan failed. Earlier results are unchanged.")
            window.error("Leftover scan failed", report)
        elif status == "canceled":
            window.status.setText("Leftover scan canceled. Earlier results are unchanged.")
        else:
            state.report, state.scanned = report, True
            invalidate(window)
            window.status.setText(report.summary() + ". Nothing was changed.")
        if live(window):
            refresh(window)

    window.job(guarded(work), done, error_title="Leftover scan failed", progress=progress)
    if live(window):
        update_notice(window, getattr(window, "_grave_rows", []))


# ------------------------------------------------------------------ Protect, Unprotect, Delete
def protect(window):
    rows = selected_items(window, fallback=True)
    if not rows:
        window.info("Choose items", "Check the specific items you want to protect.")
        return
    rules = never_touch(window)
    able = [i for i in rows if insight.protection_state(i, rules)[0] == "Protect"]
    if not able:
        window.info("Already protected", insight.protection_state(rows[0], rules)[1])
        return
    window._protect_paths([i.path for i in able], lambda: refresh(window) if live(window) else None)


def unprotect(window):
    rows = selected_items(window, fallback=True)
    if len(rows) != 1:
        window.info("Choose one item", "Check one item to review its exact personal protection rule.")
        return
    item = rows[0]
    action, reason = insight.protection_state(item, never_touch(window))
    if action == "Unprotect":
        window._unprotect_grave(item)
    elif "parent folder" in reason:
        window._manage_parent_rule(item)
    else:
        window.info("Protection stays on", reason)


def recycle(window):
    rows = selected_items(window, fallback=True)
    problems = actions.blockers(rows, never_touch(window))
    if problems:
        window.error("Cannot remove these items", "\n".join(problems) + "\n\nNothing was removed.")
        return
    window._approve_recycle([i.entry for i in rows])


def preview(window, preview_only=False):
    rows = selected_items(window, fallback=True)
    item = rows[0] if len(rows) == 1 else None
    if item is None or not insight.needs_preview(item):
        window.info("Choose one screenshot", "Check a single old screenshot to preview it.")
        return
    window._preview_grave_image(item.entry)


def steam_uninstall(window):
    rows = selected_items(window, fallback=True)
    item = rows[0] if len(rows) == 1 else None
    url = actions.uninstall_url(item) if item else None
    if url is None:
        window.info("Choose one Steam game", "Check a single installed Steam game.")
        return
    if not window.confirm("Open Steam uninstall?", f"Open Steam's own uninstall dialog for\n\n{item.name}?\n\n"
                          "Game Grave will not remove the installation directly.", destructive=True):
        return
    if sys.platform != "win32":
        window.error("Windows only", "Steam uninstall shortcut requires Windows.")
        return
    try:
        os.startfile(url)
    except OSError as exc:
        window.error("Steam unavailable", str(exc))
