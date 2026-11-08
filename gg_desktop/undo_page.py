"""Undo Center page: the owner's photo layout on what Game Grave recorded.

Rows come from the protected recovery records and the activity log. Restore goes only through the existing recovery
engine (one matching Windows Recycle Bin item, free original path, never overwrite) after confirmation. Recycled files
are never called reclaimed space, and nothing promises that every change can be undone. "Hide from History" only hides
a row on this page; the recovery records and activity log are never edited.
"""
from __future__ import annotations

from datetime import datetime, time as clock
from pathlib import Path
from types import SimpleNamespace
import threading

from PySide6.QtCore import QDate, QRect, QSignalBlocker, QSize, Qt
from PySide6.QtGui import QColor, QFontMetrics, QGuiApplication, QPainter
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QDateEdit, QFileDialog,
                               QHeaderView, QLabel, QLineEdit, QMenu, QPushButton, QRadioButton, QScrollArea,
                               QSizePolicy, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QWidget)
from shiboken6 import isValid

from core import get_activity, human_size, save_settings
from recovery import check_restore, get_records, restore as restore_recycled
from gg_desktop import undo_actions as actions
from gg_desktop import undo_data as data
from gg_desktop import undo_insight as insight
from gg_desktop.grave_page import Adaptive, CheckRow, ElidedLabel, NameDelegate, Section, font_delta, set_active
from gg_desktop.header_banner import HeaderBannerArtwork
from gg_desktop.insight_widgets import ActionFlow
from gg_desktop.models import readable_bytes
from gg_desktop.reference_library import _check, _combo, _detail_scroll, _search, _split, _table, _text, _widget
from gg_desktop.reference_widgets import DetailPanel, InventoryPager, MetricStrip, detail_line, detail_section, icon, tool
from gg_desktop.widgets import button, column, destroy_layout, label, panel, row
from ui_paging import page_window

SUBTITLE = ("Review what Game Grave changed, check Windows recovery, and restore with your approval. "
            "Every cleanup is logged.")
PAGE_SIZE = 100
COLUMNS = ["", "Action", "Item / Target", "Game / Source", "Size", "Date & Time", "Status"]
EMPTY_ALL = ("Nothing has been recorded yet. Cleanups, restores, scans and skipped items appear here as Game Grave "
             "logs them.")


class StatusDelegate(QStyledItemDelegate):
    """A coloured pill. The text is the display role and the colour is stored under Qt.UserRole."""

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text, opt.text = opt.text, ""
        widget = opt.widget
        style = widget.style() if widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, widget)
        color = QColor(index.data(Qt.UserRole) or "#9ca8bd")
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


class RadioRow(QWidget):
    """A radio button, its name and a right-aligned live count."""

    def __init__(self, text, group):
        super().__init__()
        line = row(spacing=6, margins=(2, 0, 2, 0))
        self.setLayout(line)
        self.setMinimumWidth(0)
        self.setFixedHeight(22)
        self.button = QRadioButton()
        self.button.setAccessibleName(text)
        group.addButton(self.button)
        self.name = ElidedLabel(text)
        self.name.clicked.connect(self.button.click)
        self.count = QLabel("0")
        self.count.setStyleSheet("color:#9ca8bd;font-size:10px;")
        self.count.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        line.addWidget(self.button)
        line.addWidget(self.name, 1)
        line.addWidget(self.count)

    def set_count(self, value):
        self.count.setText("" if value is None else f"{value:,}")


def state_of(window):
    if not hasattr(window, "_undo_state"):
        window._undo_state = SimpleNamespace(
            entries=[], hidden=set(), checked=set(), compact=False, range_name="All Time", sources=set(),
            expand_sources=False, source_query="", show_hidden=False, busy=False, cancel=threading.Event(),
            shown=[], rows=[], source_rows={}, message="")
    return window._undo_state


def live(window):
    return (window.current_route == "Undo Center" and hasattr(window, "undo_table") and isValid(window.undo_table)
            and hasattr(window.page, "undo_ready"))


def guarded(fn):
    def run(progress):
        try:
            return "ok", fn(progress)
        except InterruptedError:
            return "canceled", None
        except Exception as exc:  # reported on the page
            return "error", f"{type(exc).__name__}: {str(exc)[:300]}"
    return run


def load(window):
    state = state_of(window)
    state.entries = data.build_entries(get_records(), get_activity())
    state.hidden = actions.hidden_keys(window.settings)
    state.checked &= {e.key for e in state.entries}


# ------------------------------------------------------------------ page
def build(window):
    self = window
    state = state_of(self)
    load(self)
    page = self._insight_page("Undo Center", SUBTITLE, "undo", "undo", 66)
    page.banner_artwork = HeaderBannerArtwork(self, page, page.content.itemAt(0).widget(), route="Undo Center",
                                              scene="undo", source=(900, 0, 380, 110), excluded=((1090, 0, 190, 40),))
    self.undo_metrics = MetricStrip([
        ("box", "0", "Total Actions", "#e175eb"), ("check", "0", "Recycled Files", "#30d76b"),
        ("warning", "0", "Needs Review", "#f6be24"), ("warning", "0", "Failed", "#ff254a"),
        ("undo", "0", "Restored", "#13bcf5"), ("storage", "0 B", "Recycled Size", "#f2a5b2"),
        ("shield", "0", "Restore Available", "#32d67a")], compact=True)
    page.content.addWidget(self.undo_metrics)

    # --- Filters
    filters, side = panel(kind="fileFilterPanel", padding=8, spacing=4)
    filters.setMinimumWidth(165)
    filters.setMaximumWidth(190)
    head = row(spacing=4)
    glyph = QLabel()
    glyph.setPixmap(icon("filter", "#ff3b57", 17).pixmap(17, 17))
    head.addWidget(glyph)
    head.addWidget(label("Filters", "sectionTitle"), 1)
    clear = QPushButton("Clear All")
    clear.setObjectName("link")
    clear.clicked.connect(lambda: clear_filters(self))
    head.addWidget(clear)
    side.addLayout(head)
    holder = QWidget()
    stack = column(spacing=4)
    holder.setLayout(stack)

    self.undo_range_group = QButtonGroup(self)
    self.undo_range_rows = {name: RadioRow(name, self.undo_range_group) for name in data.RANGES}
    range_body = QWidget()
    range_lay = column(spacing=1)
    range_body.setLayout(range_lay)
    for control in self.undo_range_rows.values():
        range_lay.addWidget(control)
    self.undo_custom = QWidget()
    custom = row(spacing=4, margins=(18, 0, 0, 0))
    self.undo_from, self.undo_to = QDateEdit(), QDateEdit()
    for editor, tip in ((self.undo_from, "Start date"), (self.undo_to, "End date")):
        editor.setCalendarPopup(True)
        editor.setDisplayFormat("MMM d, yyyy")
        editor.setAccessibleName(tip)
        editor.setFixedHeight(26)
        custom.addWidget(editor)
    self.undo_custom.setLayout(custom)
    self.undo_custom.hide()
    range_lay.addWidget(self.undo_custom)
    stack.addWidget(Section("Time Range", range_body, True))

    self.undo_type_rows = {name: CheckRow(name, True) for name in data.CATEGORIES}
    type_body = QWidget()
    type_lay = column(spacing=1)
    type_body.setLayout(type_lay)
    for control in self.undo_type_rows.values():
        type_lay.addWidget(control)
    stack.addWidget(Section("Action Type", type_body, True))

    source_body = QWidget()
    self.undo_source_lay = column(spacing=1)
    source_body.setLayout(self.undo_source_lay)
    self.undo_source_find = QLineEdit()
    self.undo_source_find.setPlaceholderText("Search sources…")
    self.undo_source_find.setAccessibleName("Search sources")
    self.undo_source_find.setFixedHeight(26)
    self.undo_source_find.setClearButtonEnabled(True)
    self.undo_source_lay.addWidget(self.undo_source_find)
    self.undo_source_rows_box = QWidget()
    self.undo_source_rows_lay = column(spacing=1)
    self.undo_source_rows_box.setLayout(self.undo_source_rows_lay)
    self.undo_source_lay.addWidget(self.undo_source_rows_box)
    self.undo_source_more = QPushButton("More…")
    self.undo_source_more.setObjectName("link")
    self.undo_source_more.clicked.connect(lambda: toggle_sources(self))
    self.undo_source_lay.addWidget(self.undo_source_more)
    stack.addWidget(Section("Game / Source", source_body, True))

    self.undo_hidden_row = CheckRow("Show hidden rows", False)
    self.undo_hidden_row.setToolTip("Rows you hid with Hide from History. The logs themselves are never edited.")
    stack.addWidget(self.undo_hidden_row)
    stack.addStretch()
    scroller = QScrollArea()
    scroller.setWidgetResizable(True)
    scroller.setFrameShape(QScrollArea.NoFrame)
    scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroller.setStyleSheet("QScrollArea{background:transparent;} QScrollArea > QWidget > QWidget{background:transparent;}")
    scroller.setWidget(holder)
    side.addWidget(scroller, 1)
    side.addWidget(label("A recorded recycle is not guaranteed recovery or reclaimed space. Windows must still hold "
                         "one matching item.", "warning", wrap=True))

    # --- Results
    results, contents = panel(kind="fileResults", padding=7, spacing=5)
    header = row(spacing=4)
    mark = QLabel()
    mark.setPixmap(icon("undo", "#ff3b57", 18).pixmap(18, 18))
    header.addWidget(mark)
    self.undo_heading = label("Cleanup History", "sectionTitle")
    self.undo_heading.setMinimumWidth(0)
    self.undo_heading.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    header.addWidget(self.undo_heading, 1)
    sort_caption = label("Sort By:", "caption")
    header.addWidget(sort_caption)
    self.undo_sort = _combo(list(insight.SORTS), "Sort cleanup history")
    self.undo_sort.setMinimumWidth(100)
    self.undo_sort.setMaximumWidth(165)
    header.addWidget(self.undo_sort)
    self.undo_view_grid = tool("", "grid", lambda: set_compact(self, False), active=not state.compact, tip="Detailed rows")
    self.undo_view_list = tool("", "list", lambda: set_compact(self, True), active=state.compact, tip="Compact rows")
    for control in (self.undo_view_grid, self.undo_view_list):
        control.setFixedSize(26, 28)
        header.addWidget(control)
    top = Adaptive([sort_caption], 400)
    top.setLayout(header)
    contents.addWidget(top)
    self.undo_search = _search("Search games, files, actions, or history…", "Search cleanup history")
    self.undo_search.hide()  # the shared search above the page drives this field
    contents.addWidget(self.undo_search)
    self.undo_notice = label("", "caption", wrap=True)
    self.undo_notice.setTextFormat(Qt.PlainText)
    contents.addWidget(self.undo_notice)
    self.undo_table = _table(COLUMNS)
    for c, width in enumerate((24, 80, 150, 84, 54, 104, 80)):
        self.undo_table.setColumnWidth(c, width)
    self.undo_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
    self.undo_table.setSelectionMode(QAbstractItemView.SingleSelection)
    self.undo_table.setItemDelegateForColumn(2, NameDelegate(self.undo_table))
    self.undo_table.setItemDelegateForColumn(6, StatusDelegate(self.undo_table))
    contents.addWidget(self.undo_table, 1)
    self.undo_pager = InventoryPager()
    self.undo_pager.changed.connect(lambda number: fill(self, requested_page=number))
    contents.addWidget(self.undo_pager)
    footer = ActionFlow(spacing=8)
    self.undo_select_all = QCheckBox("0 selected")
    self.undo_select_all.setTristate(False)
    self.undo_select_all.clicked.connect(lambda checked: select_visible(self, checked))
    footer.addWidget(self.undo_select_all)
    self.undo_restore_button = tool("Restore Selected", "undo", lambda: restore_selected(self), kind="primary",
                                    tip="Checks Windows first, then restores to the original location. Nothing is overwritten")
    footer.addWidget(self.undo_restore_button)
    footer.addWidget(tool("Open Location", "folder", lambda: open_location(self), tip="Opens the folder the file was in"))
    self.undo_hide_button = tool("Hide from History", "trash", lambda: hide_selected(self),
                                 tip="Hides the row on this page. The logs are not edited and nothing is deleted")
    footer.addWidget(self.undo_hide_button)
    self.undo_more = tool("More", "settings", None, tip="Check availability, copy, export, select and refresh")
    self.undo_menu = QMenu(self.undo_more)
    self.undo_more.setMenu(self.undo_menu)
    footer.addWidget(self.undo_more)
    contents.addWidget(_widget(footer))
    build_menu(self)
    self.undo_details = DetailPanel()
    page.content.addWidget(_split(_split(filters, results, [190, 545]), _detail_scroll(self.undo_details), [735, 292]), 1)

    page.undo_ready = True
    self.undo_range_rows[state.range_name].button.setChecked(True)
    self.undo_range_group.buttonToggled.connect(lambda *_: range_changed(self))
    for control in self.undo_type_rows.values():
        control.box.toggled.connect(lambda *_: fill(self))
    self.undo_from.dateChanged.connect(lambda *_: fill(self))
    self.undo_to.dateChanged.connect(lambda *_: fill(self))
    self.undo_source_find.textChanged.connect(lambda text: source_query(self, text))
    self.undo_hidden_row.box.toggled.connect(lambda on: show_hidden(self, on))
    self.undo_sort.currentTextChanged.connect(lambda *_: fill(self))
    self.undo_search.textChanged.connect(lambda *_: fill(self))
    self.undo_table.itemSelectionChanged.connect(lambda: details(self))
    self.undo_table.itemChanged.connect(lambda item: table_checked(self, item))
    today = QDate.currentDate()
    with QSignalBlocker(self.undo_from), QSignalBlocker(self.undo_to):
        self.undo_from.setDate(today.addDays(-30))
        self.undo_to.setDate(today)
    refresh(self)


def build_menu(window):
    menu = window.undo_menu
    menu.clear()
    for entry in (
        ("Check Availability", lambda: check_selected(window)),
        ("Open Windows Recycle Bin", lambda: open_recycle_bin(window)), None,
        ("Copy Paths", lambda: copy_paths(window)), ("Export List (CSV)…", lambda: export_csv(window)), None,
        ("Select All Shown", lambda: select_visible(window, True)),
        ("Clear Selection", lambda: select_visible(window, False)), None,
        ("Unhide Selected", lambda: unhide_selected(window)),
        ("Refresh Records", lambda: reload(window)),
    ):
        if entry is None:
            menu.addSeparator()
        else:
            menu.addAction(entry[0], entry[1])


# ------------------------------------------------------------------ filters
def filters_now(window):
    state = state_of(window)
    start = end = None
    if state.range_name == "Custom Range":
        low, high = window.undo_from.date(), window.undo_to.date()
        if high < low:
            low, high = high, low
        start = datetime.combine(low.toPython(), clock.min).timestamp()
        end = datetime.combine(high.toPython(), clock.max).timestamp()
    return insight.Filters(
        state.range_name, start, end, [n for n, c in window.undo_type_rows.items() if c.box.isChecked()],
        state.sources, window.undo_search.text(), state.show_hidden)


def rows_now(window):
    state = state_of(window)
    return insight.apply(state.entries, filters_now(window), state.hidden, window.undo_sort.currentText())


def range_changed(window):
    state = state_of(window)
    chosen = next((n for n, c in window.undo_range_rows.items() if c.button.isChecked()), "All Time")
    state.range_name = chosen
    window.undo_custom.setVisible(chosen == "Custom Range")
    fill(window)


def clear_filters(window):
    state = state_of(window)
    with QSignalBlocker(window.undo_range_group):
        window.undo_range_rows["All Time"].button.setChecked(True)
    state.range_name, state.sources, state.source_query, state.show_hidden = "All Time", set(), "", False
    window.undo_custom.hide()
    for control in window.undo_type_rows.values():
        with QSignalBlocker(control.box):
            control.box.setChecked(True)
    with QSignalBlocker(window.undo_hidden_row.box):
        window.undo_hidden_row.box.setChecked(False)
    for control in (window.undo_search, window.undo_source_find):
        with QSignalBlocker(control):
            control.clear()
    fill(window)


def set_compact(window, compact):
    state = state_of(window)
    state.compact = compact
    set_active(window.undo_view_grid, not compact)
    set_active(window.undo_view_list, compact)
    fill(window)


def show_hidden(window, on):
    state_of(window).show_hidden = bool(on)
    fill(window)


def source_query(window, text):
    state_of(window).source_query = text.strip().casefold()
    update_sources(window)


def toggle_sources(window):
    state = state_of(window)
    state.expand_sources = not state.expand_sources
    update_sources(window)


def source_toggled(window, name, on):
    state = state_of(window)
    (state.sources.add if on else state.sources.discard)(name)
    fill(window)


def update_sources(window):
    """Rebuild the Game / Source list from live counts. No source ticked means every source."""
    state = state_of(window)
    lay = window.undo_source_rows_lay
    destroy_layout(lay)
    counts = insight.source_counts(state.entries, filters_now(window), state.hidden)
    for name in state.sources:
        counts.setdefault(name, 0)
    names = [n for n in counts if not state.source_query or state.source_query in n.casefold()]
    shown = names if state.expand_sources or state.source_query else names[:insight.SOURCE_SHOWN]
    state.source_rows = {}
    everything = CheckRow("All Sources", not state.sources)
    everything.set_count(sum(counts.values()) if counts else 0)
    everything.box.toggled.connect(lambda on: all_sources(window, on))
    lay.addWidget(everything)
    for name in shown:
        control = CheckRow(name, name in state.sources)
        control.set_count(counts[name])
        control.setToolTip(name)
        control.box.toggled.connect(lambda on, n=name: source_toggled(window, n, on))
        state.source_rows[name] = control
        lay.addWidget(control)
    window.undo_source_more.setVisible(len(names) > insight.SOURCE_SHOWN and not state.source_query)
    window.undo_source_more.setText("Show fewer" if state.expand_sources else f"More… ({len(names) - insight.SOURCE_SHOWN})")


def all_sources(window, on):
    state = state_of(window)
    if on and state.sources:
        state.sources = set()
        fill(window)
    elif not on and not state.sources:
        update_sources(window)  # "All Sources" cannot be unticked while nothing else is chosen


def update_facets(window):
    state = state_of(window)
    filters = filters_now(window)
    for name, count in insight.range_counts(state.entries, filters, state.hidden).items():
        window.undo_range_rows[name].set_count(count)
    window.undo_range_rows["Custom Range"].set_count(None)
    for name, count in insight.category_counts(state.entries, filters, state.hidden).items():
        window.undo_type_rows[name].set_count(count)
    update_sources(window)
    hidden = len([e for e in state.entries if e.key in state.hidden])
    window.undo_hidden_row.name.setText(f"Show hidden rows ({hidden})")
    window.undo_hidden_row.count.setText("")


# ------------------------------------------------------------------ table
def refresh(window):
    """Metrics from the loaded records, then facets and the table."""
    state = state_of(window)
    m = insight.metrics(state.entries, state.hidden)
    strip = window.undo_metrics
    strip.set_value(0, f"{m['total']:,}")
    strip.set_value(1, f"{m['recycled']:,}")
    strip.set_value(2, f"{m['review']:,}")
    strip.set_value(3, f"{m['failed']:,}")
    strip.set_value(4, f"{m['restored']:,}")
    strip.set_value(5, human_size(m["bytes"]))
    strip.set_value(6, f"{m['available']:,}")
    strip.setToolTip("Recycled Files counts files Game Grave sent to the Windows Recycle Bin.\n"
                     "Recycled Size is the size of those still-restorable files. A recycled file still takes disk space "
                     "until Windows empties the bin.\nRestore Available counts records Windows last reported as restorable. "
                     "Check Availability asks Windows again.")
    fill(window)


def reload(window):
    load(window)
    if live(window):
        refresh(window)
        window.status.setText("Records reloaded. Nothing was changed.")


def current_entry(window):
    index = window.undo_table.currentRow() if hasattr(window, "undo_table") and isValid(window.undo_table) else -1
    shown = state_of(window).shown
    return shown[index] if 0 <= index < len(shown) else None


def fill(window, *args, requested_page=0, **kwargs):
    if not live(window):
        return
    state = state_of(window)
    previous = current_entry(window)
    rows = rows_now(window)
    state.rows = rows
    window._undo_rows = rows
    page = page_window(rows, requested_page, PAGE_SIZE)
    window.undo_pager.update_window(page)
    state.shown = window._shown_history = list(page.items)
    fill_table(window, previous)
    window.undo_heading.setText(f"Cleanup History ({len(rows):,})")
    update_facets(window)
    update_notice(window, rows)
    selection_count(window)
    details(window)


def fill_table(window, previous):
    state = state_of(window)
    table = window.undo_table
    with QSignalBlocker(table):
        table.setRowCount(0)
        table.setRowCount(len(state.shown))
        for n, e in enumerate(state.shown):
            _check(table, n)
            if e.key in state.checked:
                table.item(n, 0).setCheckState(Qt.Checked)
            _text(table, n, 1, e.action, data.CATEGORY_ICONS[e.category], data.CATEGORY_COLORS[e.category])
            name = _text(table, n, 2, e.name, "file" if e.path else "box", "#e5b72e")
            name.setData(Qt.UserRole, "" if state.compact else (e.folder or e.note[:80]))
            name.setToolTip(f"{e.name}\n{e.path or e.note}")
            _text(table, n, 3, e.source)
            _text(table, n, 4, readable_bytes(e.size))
            _text(table, n, 5, data.when_text(e))
            pill = _text(table, n, 6, e.status)
            pill.setData(Qt.UserRole, data.TONES[e.tone])
            pill.setToolTip(data.reversible_text(e) if e.recovery_id else e.note or e.status)
            if e.key in state.hidden:
                for c in range(1, 6):
                    table.item(n, c).setForeground(QColor("#6b7683"))
            table.setRowHeight(n, 30 if state.compact else 44)
        if state.shown:
            wanted = previous.key if previous else None
            index = next((n for n, e in enumerate(state.shown) if e.key == wanted), 0)
            table.selectRow(index)


def update_notice(window, rows):
    state = state_of(window)
    notice = ""
    if state.busy:
        notice = state.message or "Working with Windows. Please wait."
    elif not state.entries:
        notice = EMPTY_ALL
    elif not rows:
        notice = "No recorded actions match these filters."
    window.undo_notice.setText(notice)
    window.undo_notice.setVisible(bool(notice))


# ------------------------------------------------------------------ selection
def table_checked(window, item):
    state = state_of(window)
    if item.column() != 0 or not 0 <= item.row() < len(state.shown):
        return
    key = state.shown[item.row()].key
    (state.checked.add if item.checkState() == Qt.Checked else state.checked.discard)(key)
    selection_count(window)


def selected_entries(window, fallback=False):
    state = state_of(window)
    rows = [e for e in state.entries if e.key in state.checked]
    if not rows and fallback:
        current = current_entry(window)
        return [current] if current else []
    return rows


def select_visible(window, selected):
    state = state_of(window)
    keys = {e.key for e in state.rows}
    state.checked = (state.checked | keys) if selected else (state.checked - keys)
    with QSignalBlocker(window.undo_table):
        for n, e in enumerate(state.shown):
            if window.undo_table.item(n, 0):
                window.undo_table.item(n, 0).setCheckState(Qt.Checked if e.key in state.checked else Qt.Unchecked)
    selection_count(window)


def selection_count(window):
    if not live(window):
        return
    state = state_of(window)
    rows = selected_entries(window)
    box = window.undo_select_all
    with QSignalBlocker(box):
        box.setText(insight.selection_text(rows))
        box.setChecked(bool(state.rows) and all(e.key in state.checked for e in state.rows))
    sync_buttons(window)


def sync_buttons(window):
    if not live(window):
        return
    state = state_of(window)
    chosen = selected_entries(window, fallback=True)
    usable, _ = actions.plan(chosen)
    free = not state.busy and not window.cleaning and not window.scanning
    window.undo_restore_button.setEnabled(bool(usable) and free)
    window.undo_hide_button.setEnabled(bool(chosen) and not state.busy)


# ------------------------------------------------------------------ details
def pill(text, color):
    item = QLabel(text)
    item.setStyleSheet(f"color:{color}; border:1px solid {color}; border-radius:9px; padding:2px 8px; font-size:10px;")
    item.setAlignment(Qt.AlignCenter)
    return item


def details(window):
    if not live(window):
        return
    state = state_of(window)
    contents = window.undo_details.content
    destroy_layout(contents)
    contents.setSpacing(5)
    detail_section(contents, "Action Details")
    e = current_entry(window)
    if e is None:
        contents.addWidget(label("Select a recorded action", "detailTitle", wrap=True))
        contents.addWidget(label("Choose a row to see what was recorded and what Windows last reported.", "subtle", wrap=True))
        contents.addStretch()
        sync_buttons(window)
        return
    head = row(spacing=8)
    glyph = QLabel()
    glyph.setPixmap(icon(data.CATEGORY_ICONS[e.category], data.CATEGORY_COLORS[e.category], 30).pixmap(30, 30))
    head.addWidget(glyph)
    names = column(spacing=0)
    title = label(e.name, "detailTitle", wrap=True)
    title.setTextFormat(Qt.PlainText)
    names.addWidget(title)
    names.addWidget(label(e.source, "caption", wrap=True))
    head.addLayout(names, 1)
    head.addWidget(pill(e.status, data.TONES[e.tone]))
    contents.addWidget(_widget(head))
    run = data.run_members(state.entries, e)
    for symbol, name, value in (
            ("trash", "Action", e.action), ("storage", "Size", readable_bytes(e.size)),
            ("box", "Items", f"{len(run):,} in this run" if len(run) > 1 else "1"),
            ("clock", "Date", data.when_text(e)), ("file", "Type", e.file_type),
            ("folder", "Location", e.path or "Not recorded"), ("check", "Result", e.note or e.status),
            ("undo", "Reversible", data.reversible_text(e))):
        detail_line(contents, symbol, name, value)
    detail_section(contents, "Restore Options")
    contents.addWidget(label("Windows is asked again before anything is restored. The file returns to where it was and "
                             "nothing is overwritten.", "subtle", wrap=True))
    free = not state.busy and not window.cleaning and not window.scanning
    restore = tool("Restore Item", "undo", lambda: restore_selected(window), kind="primary",
                   tip=data.reversible_text(e))
    restore.setEnabled(e.restorable and free)
    contents.addWidget(restore)
    check = tool("Check Availability", "check", lambda: check_selected(window), tip="Asks Windows whether one matching item is in the Recycle Bin")
    check.setEnabled(bool(e.recovery_id) and free)
    contents.addWidget(check)
    contents.addWidget(tool("Open Windows Recycle Bin", "archive", lambda: open_recycle_bin(window),
                            tip="Restore to another place by hand from here"))
    if len(run) > 1:
        detail_section(contents, f"Same Cleanup Run ({len(run):,})")
        for member in run[:6]:
            line = label(f"{member.name}  ·  {readable_bytes(member.size)}  ·  {member.status}", "caption", wrap=True)
            line.setTextFormat(Qt.PlainText)
            contents.addWidget(line)
        if len(run) > 6:
            contents.addWidget(label(f"and {len(run) - 6:,} more", "caption"))
        contents.addWidget(tool("Select This Run", "check", lambda: select_run(window, e),
                                tip="Checks the rows from this run that are shown"))
    detail_section(contents, "Recorded Evidence")
    contents.addWidget(label("The audit trail is kept. A restore record cannot show that every earlier change can be "
                             "undone.", "warning", wrap=True))
    contents.addStretch()
    sync_buttons(window)


def select_run(window, entry):
    state = state_of(window)
    members = {m.key for m in data.run_members(state.entries, entry)} & {e.key for e in state.rows}
    state.checked |= members
    with QSignalBlocker(window.undo_table):
        for n, e in enumerate(state.shown):
            if window.undo_table.item(n, 0) and e.key in members:
                window.undo_table.item(n, 0).setCheckState(Qt.Checked)
    selection_count(window)


# ------------------------------------------------------------------ actions
def open_location(window):
    e = current_entry(window)
    if e is None or not e.folder:
        window.info("Choose an item", "Select a recorded file to open its folder.")
        return
    window._open_folder(e.folder)


def open_recycle_bin(window):
    window._open_recycle_bin()


def copy_paths(window):
    rows = [e for e in selected_entries(window, fallback=True) if e.path]
    if not rows:
        window.info("Choose items", "Check the records whose paths you want to copy.")
        return
    QGuiApplication.clipboard().setText("\n".join(e.path for e in rows))
    window.status.setText(f"Copied {len(rows)} path(s).")


def export_csv(window):
    rows = state_of(window).rows
    if not rows:
        window.info("Nothing to export", "No records are shown.")
        return
    chosen, _ = QFileDialog.getSaveFileName(window, "Export the shown history as a list", "undo-history.csv", "CSV (*.csv)")
    if not chosen:
        return
    try:
        Path(chosen).write_text(insight.csv_text(rows), encoding="utf-8", newline="")
    except OSError as exc:
        window.error("List not saved", str(exc))
        return
    window.status.setText(f"Exported {len(rows):,} records to {chosen}. Nothing was changed.")


def hide_selected(window):
    state = state_of(window)
    rows = selected_entries(window, fallback=True)
    if not rows:
        window.info("Choose items", "Check the rows you want to hide.")
        return
    updated = actions.with_hidden(window.settings, [e.key for e in rows])
    if updated is None:
        window.error("Hidden list full", "Unhide some rows before hiding more.")
        return
    try:
        save_settings(updated)
    except OSError as exc:
        window.error("Not saved", str(exc))
        return
    window.settings = updated
    state.hidden = actions.hidden_keys(updated)
    state.checked -= {e.key for e in rows}
    window.status.setText(f"Hid {len(rows)} row(s). The recovery records and activity log are unchanged.")
    refresh(window)


def unhide_selected(window):
    state = state_of(window)
    rows = [e for e in selected_entries(window, fallback=True) if e.key in state.hidden]
    if not rows:
        window.info("Choose hidden rows", "Turn on Show hidden rows, then check the rows to unhide.")
        return
    updated = actions.without_hidden(window.settings, [e.key for e in rows])
    try:
        save_settings(updated)
    except OSError as exc:
        window.error("Not saved", str(exc))
        return
    window.settings = updated
    state.hidden = actions.hidden_keys(updated)
    refresh(window)


def run_job(window, work, finish, title, message):
    """One Windows-facing job at a time. A failure always reaches the page and clears the busy flags."""
    state = state_of(window)
    state.busy, state.cancel, state.message = True, threading.Event(), message
    window.cleaning = True
    cancel = state.cancel

    def done(outcome):
        status, value = outcome
        state.busy = False
        state.message = ""
        window.cleaning = False
        if status == "error":
            window.status.setText(title + " failed. Nothing further was changed.")
            window.error(title + " failed", value)
        elif status == "canceled":
            window.status.setText(title + " canceled.")
        else:
            finish(value)
        if live(window):
            load(window)
            refresh(window)

    window.job(guarded(lambda progress: work(cancel.is_set)), done, error_title=title)
    if live(window):
        update_notice(window, state.rows)
        sync_buttons(window)


def check_selected(window):
    if window.cleaning or window.scanning:
        window.info("Game Grave is busy", "Finish the current operation first.")
        return
    usable = [e for e in selected_entries(window, fallback=True) if e.recovery_id][:actions.MAX_BATCH]
    if not usable:
        window.info("Choose recovery records", f"Select up to {actions.MAX_BATCH} records that have a recovery ID.")
        return

    def finish(results):
        window.info("Windows Restore Availability",
                    "\n".join(f"{e.name}: " + (c[7:].strip() if c.startswith("ERROR:") else actions.describe(c))
                              for e, c in results))
    run_job(window, lambda cancel: actions.check(usable, check_restore, cancel), finish, "Availability check",
            "Asking Windows whether matching Recycle Bin items exist.")


def restore_selected(window):
    if window.cleaning or window.scanning:
        window.info("Game Grave is busy", "Finish the current operation first.")
        return
    usable, problems = actions.plan(selected_entries(window, fallback=True))
    if not usable:
        window.info("Nothing to restore", "\n".join(problems))
        return
    paths = "\n".join(e.path for e in usable)
    if not window.confirm("Restore from Windows Recycle Bin?",
                          "Check and restore these exact original locations:\n\n" + paths +
                          "\n\nWindows must hold exactly one matching item. Conflicts and unavailable items are refused. "
                          "No existing file will be overwritten." + ("\n\nNot included:\n" + "\n".join(problems) if problems else "")):
        return
    run_job(window, lambda cancel: actions.restore(usable, check_restore, restore_recycled, cancel),
            lambda results: window.info("Restore Results", actions.summarize(results)), "Restore",
            "Restoring through Windows. Each record is checked first.")
