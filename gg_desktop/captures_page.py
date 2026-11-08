"""Captures page: the owner's photo layout on a real, read-only capture scanner.

Scanning reads metadata only. Thumbnails decode in memory for the tiles on screen and are never written to disk.
Duplicates and Similar read file contents only when asked. Removal is the Recycle Bin only, in small verified runs.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict
from datetime import datetime
import csv
import io
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QRect, QSignalBlocker, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QFontMetrics, QGuiApplication, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QDialog, QFileDialog, QHeaderView,
                               QInputDialog, QLabel, QListWidget, QListWidgetItem, QMenu, QPushButton, QScrollArea,
                               QSizePolicy, QSlider, QStackedWidget, QStyle, QStyledItemDelegate, QStyleOptionViewItem,
                               QVBoxLayout, QWidget)
from shiboken6 import isValid

from core import _has_reparse_component, human_size, is_protected_path, safe_scan_root, save_settings
from screenshot_preview import decode_screenshot_preview
from gg_desktop import captures_actions as actions
from gg_desktop import captures_analysis as analysis
from gg_desktop import captures_data as data
from gg_desktop import captures_insight as insight
from gg_desktop import captures_state as tag_store
from gg_desktop.backend import refresh_graveyard
from gg_desktop.header_banner import HeaderBannerArtwork
from gg_desktop.insight_widgets import CAPTURE_ROLE, ActionFlow, CaptureGrid
from gg_desktop.reference_library import _check, _combo, _detail_scroll, _search, _split, _table, _text, _widget
from gg_desktop.reference_widgets import (DetailPanel, InventoryPager, MetricStrip, TabStrip, detail_line,
                                          detail_section, icon, tool)
from gg_desktop.widgets import column, destroy_layout, label, panel, row
from ui_paging import page_window

TABS = [("Screenshots", "camera"), ("Recordings", "play"), ("By Game", "game"), ("Timeline", "clock"),
        ("Duplicates", "box"), ("Similar", "camera"), ("Clean Up", "sparkles"), ("Settings", "settings")]
PAGE_SIZE = 120
THUMB_BATCH = 4
THUMB_CACHE = 240
TONES = {"ok": ("check", "#27dc74"), "info": ("shield", "#9ca8bd"), "warn": ("shield", "#f7b737")}


def font_delta(font, points):
    font = QFont(font)
    if font.pointSizeF() > 0:
        font.setPointSizeF(max(7.0, font.pointSizeF() + points))
    elif font.pixelSize() > 0:
        font.setPixelSize(max(9, font.pixelSize() + int(points * 1.3)))
    return font


class CountDelegate(QStyledItemDelegate):
    """Marker, name and a right-aligned count, like the photo's Game / Source list."""

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        name, opt.text = opt.text, ""
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
        painter.setFont(font_delta(opt.font, -1))
        metrics = QFontMetrics(painter.font())
        count = str(index.data(Qt.UserRole + 1) or "")
        count_width = metrics.horizontalAdvance(count)
        left = box.right() + 8
        painter.setPen(QColor("#f4f7fc") if selected else QColor("#d3dae3"))
        space = rect.right() - left - count_width - 6
        painter.drawText(QRect(left, rect.top(), max(10, space), rect.height()), int(Qt.AlignLeft | Qt.AlignVCenter),
                         metrics.elidedText(name, Qt.ElideRight, max(10, space)))
        painter.setPen(QColor("#9ca8bd"))
        painter.drawText(QRect(rect.right() - count_width - 2, rect.top(), count_width + 2, rect.height()),
                         int(Qt.AlignRight | Qt.AlignVCenter), count)
        painter.restore()

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), 21)


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


class Section(QWidget):
    """A collapsible filter section with a chevron, like the photo."""

    def __init__(self, title, body, expanded=False):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(3)
        self.head = QPushButton()
        self.head.setFlat(True)
        self.head.setCursor(Qt.PointingHandCursor)
        self.head.setFixedHeight(27)
        self.head.setAccessibleName(title)
        self.head.setStyleSheet("QPushButton{border:0;border-top:1px solid #1f2b36;padding:0;text-align:left;}"
                                "QPushButton:hover{background:#0f1923;}")
        line = row(spacing=4, margins=(2, 5, 2, 5))
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


# ------------------------------------------------------------------ state
def state_of(window):
    if not hasattr(window, "_captures_state"):
        window._captures_state = SimpleNamespace(
            busy="", cancel=threading.Event(), report=None, scanned=False, message="", checked=set(),
            tags=None, duplicates=None, similar=None, similar_compared=0, generation=0, thumbs=OrderedDict(),
            pending=[], loading=False, compact=False, headers_running=False, all=None, all_key=None, tab="Screenshots")
    return window._captures_state


def live(window):
    return (window.current_route == "Captures" and hasattr(window, "capture_grid") and isValid(window.capture_grid)
            and hasattr(window.page, "captures_ready"))


def tags_of(window):
    state = state_of(window)
    if state.tags is None:
        state.tags = tag_store.load_tags()
    return state.tags


def universe(window):
    """Scanned captures plus any the last PC scan found outside the scan."""
    state = state_of(window)
    scanned = state.report.captures if state.report else []
    inv = window.inventory
    key = (id(state.report), len(scanned), id(inv), len(inv.screenshots), len(inv.recordings))
    if state.all_key != key:
        state.all = data.merge(scanned, data.from_inventory(inv))
        state.all_key = key
    return state.all


def invalidate(window):
    state_of(window).all_key = None


def never_touch(window):
    return window.settings.get("never_touch", [])


def now():
    return time.time()


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


# ------------------------------------------------------------------ page
def build(window):
    self = window
    state = state_of(self)
    page = self._insight_page("Captures", "Manage your in-game screenshots, recordings, and clips across your games.\nPreview, organize, and safely clean up old or unwanted captures.",
                              "captures", "camera", 74)
    page.banner_artwork = HeaderBannerArtwork(self, page, page.content.itemAt(0).widget(), route="Captures",
                                              scene="captures", source=(700, 0, 580, 126), excluded=((1090, 0, 190, 40),))
    state.tab = state.tab if state.tab in {n for n, _ in TABS} else "Screenshots"
    self.capture_metrics = MetricStrip([
        ("camera", "0", "Screenshots", "#db77e6"), ("play", "0", "Recordings", "#13baef"),
        ("box", "0 B", "Total Captures", "#f3c52c"), ("game", "0", "Games", "#ff2145"),
        ("clock", "None", "Oldest Capture", "#f7c327"), ("trash", "0 B", "Cleanup Candidates", "#e867c5")], compact=True)
    page.content.addWidget(self.capture_metrics)
    self.capture_tabs = TabStrip(TABS, selected=state.tab)
    for control in self.capture_tabs.buttons.values():
        control.setStyleSheet("font-size:11px; padding:4px 3px;")
        control.setIconSize(QSize(15, 15))
    page.content.addWidget(self.capture_tabs)

    # --- Filters
    filters, side = panel(kind="fileFilterPanel", padding=8, spacing=4)
    filters.setMinimumWidth(158)
    filters.setMaximumWidth(215)
    head = row(spacing=4)
    head.addWidget(label("Filters", "sectionTitle"), 1)
    clear = QPushButton("Clear All")
    clear.setObjectName("link")
    clear.clicked.connect(lambda: clear_filters(self))
    head.addWidget(clear)
    side.addLayout(head)
    holder = QWidget()
    stack = column(spacing=4)
    holder.setLayout(stack)

    self.capture_game_search = _search("Search games…", "Search game filter")
    self.capture_game = QListWidget()
    self.capture_game.setObjectName("sourceFilters")
    self.capture_game.setItemDelegate(CountDelegate(self.capture_game))
    self.capture_game.setAccessibleName("Filter captures by game")
    self.capture_game.setFixedHeight(76)
    self.capture_game.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    self.capture_game.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    game_body = QWidget()
    game_layout = column(spacing=4)
    game_body.setLayout(game_layout)
    game_layout.addWidget(self.capture_game_search)
    game_layout.addWidget(self.capture_game)
    stack.addWidget(Section("Game / Source", game_body, True))

    self.capture_types = []
    type_body = QWidget()
    type_layout = column(spacing=2)
    type_body.setLayout(type_layout)
    for kind in ("Screenshots", "Recordings"):
        box = QCheckBox(kind)
        box.setChecked(True)
        box.setProperty("kind", kind)
        self.capture_types.append(box)
        type_layout.addWidget(box)
    stack.addWidget(Section("Capture Type", type_body, True))

    self.capture_age = _combo(list(insight.AGE_CHOICES), "Filter capture age")
    self.capture_size = _combo(list(insight.SIZE_CHOICES), "Filter capture size")
    self.capture_resolution = _combo(list(insight.RES_CHOICES), "Filter capture resolution")
    self.capture_tag = _combo([insight.ALL_TAGS, insight.UNTAGGED], "Filter capture tag")
    for title, control in (("Age", self.capture_age), ("Size", self.capture_size), ("Resolution", self.capture_resolution),
                           ("Tags", self.capture_tag)):
        stack.addWidget(Section(title, control, False))
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
    glyph = QLabel()
    glyph.setPixmap(icon("camera", "#ff3b57", 18).pixmap(18, 18))
    header.addWidget(glyph)
    self.capture_heading = label("Screenshots", "sectionTitle")
    for shrinkable in (self.capture_heading,):
        shrinkable.setMinimumWidth(0)
        shrinkable.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    header.addWidget(self.capture_heading, 1)
    self.capture_month = _combo([insight.ALL_MONTHS], "Timeline month")
    self.capture_month.setMinimumWidth(92)
    self.capture_month.setMaximumWidth(120)
    header.addWidget(self.capture_month)
    header.addWidget(label("Sort By:", "caption"))
    self.capture_sort = _combo(list(insight.SORTS), "Sort captures")
    self.capture_sort.setMinimumWidth(92)
    self.capture_sort.setMaximumWidth(150)
    header.addWidget(self.capture_sort)
    self.capture_view_grid = tool("", "grid", lambda: set_compact(self, False), active=not state.compact, tip="Thumbnails")
    self.capture_view_list = tool("", "list", lambda: set_compact(self, True), active=state.compact, tip="List")
    for control in (self.capture_view_grid, self.capture_view_list):
        control.setFixedSize(26, 28)
        header.addWidget(control)
    self.capture_zoom = QSlider(Qt.Horizontal)
    self.capture_zoom.setRange(100, 230)
    self.capture_zoom.setValue(125)
    self.capture_zoom.setFixedWidth(54)
    self.capture_zoom.setAccessibleName("Capture tile size")
    minus, plus = QLabel("\u2212"), QLabel("+")
    for sign in (minus, plus):
        sign.setStyleSheet("color:#d3dae3;font-size:15px;font-weight:600;")
        sign.setAlignment(Qt.AlignCenter)
        sign.setFixedWidth(12)
    header.addWidget(minus)
    header.addWidget(self.capture_zoom)
    header.addWidget(plus)
    top = Adaptive([minus, plus], 440)
    top.setLayout(header)
    contents.addWidget(top)
    self.capture_search = _search("Search games, captures, recordings, or folders…", "Search captures")
    self.capture_search.hide()  # the shared search above the page drives this field
    contents.addWidget(self.capture_search)
    notice_row = row(spacing=6)
    self.capture_notice = label("", "caption", wrap=True)
    self.capture_notice.setTextFormat(Qt.PlainText)
    notice_row.addWidget(self.capture_notice, 1)
    self.capture_action = QPushButton("")
    self.capture_action.clicked.connect(lambda: contextual_action(self))
    self.capture_action.hide()
    notice_row.addWidget(self.capture_action)
    contents.addWidget(_widget(notice_row))
    self.capture_stack = QStackedWidget()
    self.capture_grid = CaptureGrid()
    self.capture_grid.setAccessibleName("Captures")
    self.capture_stack.addWidget(self.capture_grid)
    self.capture_table = _table(["", "Name", "Game / Source", "Modified", "Size", "Resolution"])
    for c, width in enumerate((24, 150, 96, 82, 58, 78)):
        self.capture_table.setColumnWidth(c, width)
    self.capture_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
    self.capture_table.setSelectionMode(QAbstractItemView.SingleSelection)
    self.capture_stack.addWidget(self.capture_table)
    self.capture_settings = QWidget()
    self.capture_stack.addWidget(self.capture_settings)
    contents.addWidget(self.capture_stack, 1)
    self.capture_pager = InventoryPager()
    self.capture_pager.changed.connect(lambda number: fill(self, requested_page=number))
    contents.addWidget(self.capture_pager)
    self.capture_details = DetailPanel()
    page.content.addWidget(_split(_split(filters, results, [205, 520]), _detail_scroll(self.capture_details), [735, 292]), 1)

    # --- Footer
    bar_panel, bar = panel(kind="fileResults", padding=7, spacing=0)
    footer = ActionFlow(spacing=8)
    self.capture_select_all = QCheckBox("0 selected (0 B)")
    self.capture_select_all.setTristate(False)
    self.capture_select_all.clicked.connect(lambda checked: select_visible(self, checked))
    footer.addWidget(self.capture_select_all)
    footer.addWidget(tool("Protect", "shield", lambda: protect(self), tip="Adds Never Touch rules for the checked captures"))
    footer.addWidget(tool("Add to Graveyard", "grave", lambda: add_to_graveyard(self),
                          tip="Adds the checked files to protected Graveyard review. Nothing is moved."))
    self.capture_delete = tool("Delete…", "trash", lambda: delete_selected(self), kind="danger")
    footer.addWidget(self.capture_delete)
    self.capture_more = tool("More Actions", "settings", None, tip="Open, copy, tag, rescan and selection tools")
    self.capture_menu = QMenu(self.capture_more)
    self.capture_more.setMenu(self.capture_menu)
    footer.addWidget(self.capture_more)
    bar.addWidget(_widget(footer))
    page.content.addWidget(bar_panel)
    build_menu(self)

    page.captures_ready = True
    self.capture_tabs.changed.connect(lambda name: set_tab(self, name))
    self.capture_zoom.valueChanged.connect(lambda value: zoom(self, value))
    for control in (self.capture_age, self.capture_size, self.capture_resolution, self.capture_tag, self.capture_sort,
                    self.capture_month):
        control.currentTextChanged.connect(lambda *_: fill(self))
    for box in self.capture_types:
        box.toggled.connect(lambda *_: fill(self))
    self.capture_game.currentRowChanged.connect(lambda *_: fill(self))
    self.capture_game_search.textChanged.connect(lambda *_: rebuild_game_list(self))
    self.capture_search.textChanged.connect(lambda *_: fill(self))
    self.capture_grid.currentRowChanged.connect(lambda *_: details(self))
    self.capture_grid.itemChanged.connect(lambda item: grid_checked(self, item))
    self.capture_grid.previewRequested.connect(lambda row_: open_viewer(self, row_))
    self.capture_table.itemSelectionChanged.connect(lambda: details(self))
    self.capture_table.itemChanged.connect(lambda item: table_checked(self, item))
    self.capture_table.cellDoubleClicked.connect(lambda row_, _: open_viewer(self, row_))
    zoom(self, self.capture_zoom.value())
    refresh(self)
    if not state.scanned and not state.busy and not self.reference_preview and not self.scanning:
        QTimer.singleShot(150, lambda: scan(self, automatic=True) if live(self) and not state.scanned and not state.busy else None)


def build_menu(window):
    menu = window.capture_menu
    menu.clear()
    for entry in (
        ("Open File", lambda: open_file(window)), ("Open Containing Folder", lambda: open_folder(window)),
        ("View Larger", lambda: open_viewer(window, current_index(window))), None,
        ("Copy To Folder…", lambda: copy_selected(window)), ("Copy File Paths", lambda: copy_paths(window)),
        ("Export List (CSV)…", lambda: export_csv(window)), None,
        ("Add Tag…", lambda: add_tag(window)), ("Remove Tag…", lambda: remove_tag(window)), None,
        ("Select All Shown", lambda: select_visible(window, True)), ("Clear Selection", lambda: select_visible(window, False)),
        ("Select Extra Copies", lambda: select_extra_copies(window)), None,
        ("Rescan Capture Folders", lambda: scan(window)),
    ):
        if entry is None:
            menu.addSeparator()
        else:
            menu.addAction(entry[0], entry[1])


# ------------------------------------------------------------------ filters, counts, summary
def refresh(window):
    """Metrics, tab counts and filter lists from the current captures, then the gallery."""
    captures = universe(window)
    t = insight.totals(captures, never_touch(window), now())
    strip = window.capture_metrics
    strip.set_value(0, f"{t['screenshots']:,}")
    strip.set_value(1, f"{t['recordings']:,}")
    strip.set_value(2, human_size(t["bytes"]))
    strip.set_value(3, f"{t['games']:,}")
    strip.set_value(4, insight.age_text(t["oldest"]) if captures else "None")
    strip.set_value(5, human_size(t["candidate_bytes"]))
    report = state_of(window).report
    strip.setToolTip(((report.summary() + ".") if report else "Showing captures from the last PC scan. Rescan Capture Folders finds all of them.")
                     + "\nCleanup Candidates are captures last modified over 6 months ago that are not protected. "
                       "Age alone does not make a capture unwanted.")
    window.capture_tabs.buttons["Screenshots"].setText(f"Screenshots ({t['screenshots']:,})")
    window.capture_tabs.buttons["Recordings"].setText(f"Recordings ({t['recordings']:,})")
    for box in window.capture_types:
        box.setText(f"{box.property('kind')}   {t['screenshots'] if box.property('kind') == 'Screenshots' else t['recordings']:,}")
    rebuild_game_list(window, refill=False)
    tag_names = [insight.ALL_TAGS, insight.UNTAGGED] + tag_store.all_tags(tags_of(window))
    keep = window.capture_tag.currentText()
    with QSignalBlocker(window.capture_tag):
        window.capture_tag.clear()
        window.capture_tag.addItems(tag_names)
        window.capture_tag.setCurrentText(keep if keep in tag_names else insight.ALL_TAGS)
    month_names = [insight.ALL_MONTHS] + [insight.month_label(m) for m in insight.months(captures)]
    keep = window.capture_month.currentText()
    with QSignalBlocker(window.capture_month):
        window.capture_month.clear()
        window.capture_month.addItems(month_names)
        window.capture_month.setCurrentText(keep if keep in month_names else insight.ALL_MONTHS)
    fill(window)


def rebuild_game_list(window, refill=True):
    captures = universe(window)
    wanted = window.capture_game_search.text().strip().casefold()
    current = window.capture_game.currentItem()
    keep = current.data(Qt.UserRole) if current else insight.ALL_GAMES
    with QSignalBlocker(window.capture_game):
        window.capture_game.clear()
        entries = [(insight.ALL_GAMES, len(captures))] + [(g, n) for g, n in insight.game_counts(captures)
                                                          if not wanted or wanted in g.casefold()]
        for name, count in entries:
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, name)
            item.setData(Qt.UserRole + 1, f"{count:,}")
            window.capture_game.addItem(item)
        row_ = next((i for i, (n, _) in enumerate(entries) if n == keep), 0)
        window.capture_game.setCurrentRow(row_)
    window.capture_game.setFixedHeight(min(max(window.capture_game.count(), 1), 6) * 22 + 6)
    window.capture_game.viewport().update()
    if refill:
        fill(window)


def clear_filters(window):
    with QSignalBlocker(window.capture_game_search):
        window.capture_game_search.clear()
    for control in (window.capture_age, window.capture_size, window.capture_resolution):
        control.setCurrentIndex(0)
    window.capture_tag.setCurrentText(insight.ALL_TAGS)
    window.capture_month.setCurrentText(insight.ALL_MONTHS)
    for box in window.capture_types:
        box.setChecked(True)
    window.capture_search.clear()
    rebuild_game_list(window, refill=False)
    window.capture_game.setCurrentRow(0)
    fill(window)


def current_filters(window):
    state = state_of(window)
    item = window.capture_game.currentItem()
    month_label = window.capture_month.currentText()
    month = insight.ALL_MONTHS
    if month_label != insight.ALL_MONTHS:
        month = next((m for m in insight.months(universe(window)) if insight.month_label(m) == month_label), insight.ALL_MONTHS)
    return dict(
        tab=state.tab, game=item.data(Qt.UserRole) if item else insight.ALL_GAMES,
        kinds=tuple(b.property("kind") for b in window.capture_types if b.isChecked()),
        age=window.capture_age.currentIndex(), size=window.capture_size.currentIndex(),
        resolution=window.capture_resolution.currentIndex(), tag=window.capture_tag.currentText(),
        query=window.capture_search.text(), sort=window.capture_sort.currentText(), month=month, tags=tags_of(window),
        duplicates=state.duplicates, similar=state.similar, never_touch=never_touch(window), now=now())


def rows_now(window):
    return insight.filter_captures(universe(window), **current_filters(window))


def set_tab(window, name):
    state = state_of(window)
    state.tab = name
    fill(window)


def set_compact(window, compact):
    state_of(window).compact = compact
    set_active(window.capture_view_grid, not compact)
    set_active(window.capture_view_list, compact)
    fill(window)


def set_active(control, on):
    control.setProperty("active", on)
    control.style().unpolish(control)
    control.style().polish(control)


def zoom(window, value):
    window.capture_grid.tile_width = value
    window.capture_grid._fit()
    window.capture_grid.doItemsLayout()


# ------------------------------------------------------------------ gallery
def checked_keys(window):
    return state_of(window).checked


def fill(window, *args, requested_page=0, **kwargs):
    if not live(window):
        return
    state = state_of(window)
    rows = rows_now(window)
    window._cap_rows = rows
    visible = {c.key for c in rows}
    state.checked &= {c.key for c in universe(window)}
    previous = current_capture(window)
    page = insight_page(rows, requested_page)
    window.capture_pager.update_window(page)
    window._shown_captures = list(page.items)
    settings_tab = state.tab == "Settings"
    compact = state.compact and not settings_tab
    window.capture_stack.setCurrentIndex(2 if settings_tab else 1 if compact else 0)
    window.capture_view_grid.setEnabled(not settings_tab)
    window.capture_view_list.setEnabled(not settings_tab)
    window.capture_zoom.setVisible(not compact and not settings_tab)
    window.capture_month.setVisible(state.tab == "Timeline")
    window.capture_sort.setEnabled(state.tab not in ("By Game", "Duplicates", "Similar"))
    if settings_tab:
        fill_settings(window)
    elif compact:
        fill_table(window, previous)
    else:
        fill_grid(window, previous)
    noun = state.tab if state.tab in ("Screenshots", "Recordings", "Duplicates", "Similar", "Clean Up") else "Captures"
    window.capture_heading.setText(f"{noun} ({len(rows):,})")
    update_notice(window, rows)
    selection_count(window)
    details(window)
    request_thumbnails(window)


def insight_page(rows, requested_page):
    return page_window(rows, requested_page, PAGE_SIZE)


def current_capture(window):
    index = current_index(window)
    shown = getattr(window, "_shown_captures", [])
    return shown[index] if 0 <= index < len(shown) else None


def current_index(window):
    state = state_of(window)
    if state.compact and window.capture_stack.currentIndex() == 1:
        return window.capture_table.currentRow()
    return window.capture_grid.currentRow()


def fill_grid(window, previous):
    state = state_of(window)
    grid = window.capture_grid
    with QSignalBlocker(grid):
        grid.clear()
        for capture in window._shown_captures:
            item = QListWidgetItem(capture.name)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            item.setCheckState(Qt.Checked if capture.key in state.checked else Qt.Unchecked)
            thumb = state.thumbs.get(capture.key)
            item.setData(CAPTURE_ROLE, {"item": capture, "preview": thumb, "dimensions": capture.dimensions})
            item.setToolTip(f"{capture.path}\n{capture.game}")
            grid.addItem(item)
        if window._shown_captures:
            grid.setCurrentRow(next((i for i, c in enumerate(window._shown_captures) if previous and c.key == previous.key), 0))
    grid.doItemsLayout()


def fill_table(window, previous):
    state = state_of(window)
    table = window.capture_table
    with QSignalBlocker(table):
        table.setRowCount(0)
        table.setRowCount(len(window._shown_captures))
        for i, c in enumerate(window._shown_captures):
            _check(table, i)
            if c.key in state.checked:
                table.item(i, 0).setCheckState(Qt.Checked)
            _text(table, i, 1, c.name, "camera" if c.kind == "Screenshots" else "play", "#a8b5c6")
            _text(table, i, 2, c.game)
            _text(table, i, 3, datetime.fromtimestamp(c.modified).strftime("%Y-%m-%d"))
            _text(table, i, 4, human_size(c.size))
            _text(table, i, 5, f"{c.width} × {c.height}" if c.dimensions else "Unknown")
            table.setRowHeight(i, 28)
        if window._shown_captures:
            table.selectRow(next((i for i, c in enumerate(window._shown_captures) if previous and c.key == previous.key), 0))


def fill_settings(window):
    old = window.capture_settings.layout()
    if old is not None:
        destroy_layout(old)
        QWidget().setLayout(old)
    layout = column(spacing=7)
    window.capture_settings.setLayout(layout)
    layout.addWidget(label("Capture Folders", "sectionTitle"))
    roots = data.capture_roots(window.settings)
    window.capture_roots_list = QListWidget()
    window.capture_roots_list.setObjectName("sourceFilters")
    window.capture_roots_list.setAccessibleName("Capture folders")
    for root in roots:
        item = QListWidgetItem(f"{root.path}   ({root.label})")
        item.setData(Qt.UserRole, str(root.path))
        item.setData(Qt.UserRole + 1, root.user)
        item.setToolTip(str(root.path))
        window.capture_roots_list.addItem(item)
    if not roots:
        layout.addWidget(label("No capture folders were found. Add the folder where your games or recorder save captures.", "caption", wrap=True))
    layout.addWidget(window.capture_roots_list, 1)
    buttons = ActionFlow(spacing=6)
    buttons.addWidget(tool("Add Screenshot Folder…", "folder", lambda: add_folder(window, "screenshot_roots"),
                           tip="Read-only discovery of image files in the folder you choose"))
    buttons.addWidget(tool("Add Recording Folder…", "play", lambda: add_folder(window, "recording_roots"),
                           tip="Read-only discovery of video files in the folder you choose"))
    window.capture_remove_root = tool("Remove Selected Folder", "close", lambda: remove_folder(window),
                                      tip="Stops scanning a folder you added. The folder and its files are untouched.")
    buttons.addWidget(window.capture_remove_root)
    buttons.addWidget(tool("Rescan", "refresh", lambda: scan(window)))
    layout.addWidget(_widget(buttons))
    layout.addWidget(label("Scanning reads names, sizes and dates only. Thumbnails are decoded in memory for the tiles on screen and "
                           "are never saved. Resolution comes from image headers. Folders Game Grave did not find are not scanned.",
                           "caption", wrap=True))


def update_notice(window, rows):
    state = state_of(window)
    notice = insight.NOTICES.get(state.tab, "")
    action = ""
    captures = universe(window)
    if state.busy:
        notice = state.message or "Working. Nothing is changed."
        action = "Cancel"
    elif state.tab == "Duplicates":
        if state.duplicates is None:
            notice, action = "Exact duplicates are found by comparing file contents. Nothing is read until you ask.", "Find Duplicates"
        else:
            notice = f"{len(state.duplicates):,} {'group' if len(state.duplicates) == 1 else 'groups'} of identical files from the last check." if state.duplicates else \
                "No identical files were found in the last check."
            action = "Check Again"
    elif state.tab == "Similar":
        if state.similar is None:
            notice, action = ("Similar screenshots are found by comparing a small image fingerprint. "
                              f"Up to {analysis.MAX_SIMILAR_IMAGES:,} of the newest are compared."), "Find Similar"
        else:
            notice = (f"{len(state.similar):,} {'group' if len(state.similar) == 1 else 'groups'} of similar screenshots ({state.similar_compared:,} compared). "
                      "Similar is not identical; review each one.") if state.similar else \
                f"No similar screenshots were found among {state.similar_compared:,} compared."
            action = "Check Again"
    elif state.tab == "Settings":
        notice = "Folders Game Grave scans for captures."
    elif not rows and not notice:
        if not captures and not state.scanned:
            notice = "Scanning your capture folders. Nothing is changed."
        elif not captures:
            notice = "No captures were found. Add a capture folder in Settings, or check where your games save them."
        else:
            notice = "No captures match these filters."
    elif state.report is None and rows and not notice:
        notice = "Showing captures from the last PC scan. Rescan Capture Folders finds all of them."
    window.capture_notice.setText(notice)
    window.capture_notice.setVisible(bool(notice))
    window.capture_action.setText(action)
    window.capture_action.setVisible(bool(action))


def contextual_action(window):
    state = state_of(window)
    if state.busy:
        state.cancel.set()
        state.message = "Canceling…"
        update_notice(window, getattr(window, "_cap_rows", []))
    elif state.tab == "Duplicates":
        find_duplicates(window)
    elif state.tab == "Similar":
        find_similar(window)


# ------------------------------------------------------------------ selection
def grid_checked(window, item):
    state = state_of(window)
    payload = item.data(CAPTURE_ROLE) or {}
    capture = payload.get("item")
    if capture is None:
        return
    (state.checked.add if item.checkState() == Qt.Checked else state.checked.discard)(capture.key)
    selection_count(window)
    window.capture_grid.viewport().update()


def table_checked(window, item):
    if item.column() != 0 or not 0 <= item.row() < len(window._shown_captures):
        return
    state = state_of(window)
    key = window._shown_captures[item.row()].key
    (state.checked.add if item.checkState() == Qt.Checked else state.checked.discard)(key)
    selection_count(window)


def selected_captures(window, fallback=False):
    state = state_of(window)
    rows = [c for c in getattr(window, "_cap_rows", []) if c.key in state.checked]
    if not rows and fallback:
        current = current_capture(window)
        return [current] if current else []
    return rows


def select_visible(window, selected):
    state = state_of(window)
    keys = {c.key for c in getattr(window, "_cap_rows", [])}
    state.checked = (state.checked | keys) if selected else (state.checked - keys)
    sync_checks(window)


def sync_checks(window):
    state = state_of(window)
    with QSignalBlocker(window.capture_grid):
        for i in range(window.capture_grid.count()):
            payload = window.capture_grid.item(i).data(CAPTURE_ROLE) or {}
            item = payload.get("item")
            if item is not None:
                window.capture_grid.item(i).setCheckState(Qt.Checked if item.key in state.checked else Qt.Unchecked)
    with QSignalBlocker(window.capture_table):
        for i in range(window.capture_table.rowCount()):
            if i < len(window._shown_captures) and window.capture_table.item(i, 0):
                window.capture_table.item(i, 0).setCheckState(
                    Qt.Checked if window._shown_captures[i].key in state.checked else Qt.Unchecked)
    window.capture_grid.viewport().update()
    selection_count(window)


def select_extra_copies(window):
    state = state_of(window)
    if state.duplicates is None:
        window.info("Check duplicates first", "Open the Duplicates tab and use Find Duplicates. The oldest copy of each group stays unchecked.")
        return
    by_key = {c.key: c for c in universe(window)}
    extras = insight.duplicate_extras(state.duplicates, by_key)
    visible = {c.key for c in getattr(window, "_cap_rows", [])}
    state.checked |= extras & visible
    sync_checks(window)
    window.status.setText(f"{len(extras & visible)} extra copies checked. The oldest copy of each group is kept.")


def selection_count(window):
    if not live(window):
        return
    rows = selected_captures(window)
    box = window.capture_select_all
    total = len(getattr(window, "_cap_rows", []))
    with QSignalBlocker(box):
        box.setText(f"{len(rows):,} selected ({insight.size_text(rows)})")
        box.setChecked(bool(total) and len(rows) == total)
    hit = any(is_protected_path(Path(c.path), never_touch(window)) for c in rows)
    enabled, tip = insight.selection_state(rows, hit)
    state = state_of(window)
    window.capture_delete.setEnabled(enabled and not state.busy and not window.cleaning and not window.scanning)
    window.capture_delete.setToolTip(tip)


# ------------------------------------------------------------------ details
def details(window):
    if not live(window):
        return
    state = state_of(window)
    contents = window.capture_details.content
    destroy_layout(contents)
    contents.setSpacing(5)
    capture = current_capture(window)
    if capture is None or state.tab == "Settings":
        contents.addWidget(label("Select a capture", "detailTitle"))
        contents.addWidget(label("Choose a thumbnail to see its details, game link and anything related to it.", "subtle", wrap=True))
        contents.addStretch()
        return
    mine = tags_of(window).get(capture.key, [])
    title = label(capture.game if capture.game != data.UNVERIFIED else "Local Capture", "detailTitle", wrap=True)
    contents.addWidget(title)
    modified = datetime.fromtimestamp(capture.modified).strftime("%b %d, %Y")
    contents.addWidget(label(f"{capture.kind[:-1]} · {modified} · {human_size(capture.size)}", "caption"))
    image = QLabel()
    image.setAlignment(Qt.AlignCenter)
    image.setFixedHeight(128)
    image.setMinimumWidth(0)
    thumb = state.thumbs.get(capture.key)
    if thumb is not None and not thumb.isNull():
        image.setPixmap(thumb.scaled(300, 128, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        image.setCursor(Qt.PointingHandCursor)
    else:
        image.setText("Loading preview…" if capture.kind == "Screenshots" else "Recording. Use Open File to play it.")
        image.setStyleSheet("background:#0b1822;color:#8aa3b9;border:1px solid #25384a;border-radius:5px;")
    contents.addWidget(image)
    chips = TabStrip([("Details", "file"), ("Game Info", "game"),
                      (f"Related ({len(related_for(window, capture))})", "box")], framed=False)
    sub = getattr(window, "_capture_subtab", "Details")
    keys = list(chips.buttons)
    pick = next((k for k in keys if k.startswith(sub)), keys[0])
    chips.select(pick)
    chips.changed.connect(lambda name: (setattr(window, "_capture_subtab", name.split(" (")[0]), details(window)))
    contents.addWidget(chips)
    if pick.startswith("Game Info"):
        game_info(window, capture, contents)
    elif pick.startswith("Related"):
        related_list(window, capture, contents)
    else:
        file_details(window, capture, contents, mine)
    contents.addStretch()


def file_details(window, capture, contents, mine):
    state = state_of(window)
    rules = never_touch(window)
    protected = is_protected_path(Path(capture.path), rules)
    for symbol, name, value in (
        ("file", "File Name", capture.name), ("folder", "Location", capture.folder),
        ("camera", "Resolution", f"{capture.width} × {capture.height}" if capture.dimensions else "Unknown"),
        ("storage", "Size", human_size(capture.size)),
        ("clock", "Modified", datetime.fromtimestamp(capture.modified).strftime("%b %d, %Y %H:%M")),
        ("game", "Game", capture.game), ("shield", "Source", capture.source),
        ("shield", "Protection", "Protected" if protected else "Not protected"),
        ("box", "Tags", ", ".join(mine) if mine else "None"),
    ):
        detail_line(contents, symbol, name, value)
    detail_section(contents, "Recommendations")
    for tone, text in insight.facts(capture, never_touch=rules, duplicates=state.duplicates, similar=state.similar):
        symbol, color = TONES[tone]
        line = QWidget()
        box = row(spacing=6)
        line.setLayout(box)
        mark = QLabel()
        mark.setPixmap(icon(symbol, color, 14).pixmap(14, 14))
        mark.setAlignment(Qt.AlignTop)
        box.addWidget(mark)
        text_label = label(text, "subtle", wrap=True)
        box.addWidget(text_label, 1)
        contents.addWidget(line)
    if "steam" in capture.source.casefold():
        contents.addWidget(label("Steam may keep listing a removed screenshot until it is removed in Steam too.", "caption", wrap=True))
    buttons = row(spacing=6)
    buttons.addWidget(tool("View", "camera", lambda: open_viewer(window, current_index(window)), kind="primary"))
    buttons.addWidget(tool("Folder", "folder", lambda: open_folder(window)))
    contents.addWidget(_widget(buttons))


def game_info(window, capture, contents):
    captures = [c for c in universe(window) if c.game == capture.game]
    steam = next((g for g in window.inventory.steam if g.name == capture.game), None)
    detail_line(contents, "game", "Game", capture.game)
    detail_line(contents, "shield", "Evidence", capture.source)
    if capture.game == data.UNVERIFIED:
        contents.addWidget(label("Game Grave found no proof of which game this came from, so it does not guess.", "subtle", wrap=True))
        return
    detail_line(contents, "camera", "Captures", f"{len(captures):,} ({human_size(sum(c.size for c in captures))})")
    detail_line(contents, "clock", "Oldest", datetime.fromtimestamp(min(c.modified for c in captures)).strftime("%b %d, %Y"))
    detail_line(contents, "clock", "Newest", datetime.fromtimestamp(max(c.modified for c in captures)).strftime("%b %d, %Y"))
    if steam is not None:
        detail_line(contents, "folder", "Install", getattr(steam, "install_path", "Unknown"))
        detail_line(contents, "game", "Steam ID", str(steam.app_id))
        contents.addWidget(tool("Open Game in Games", "game", lambda: window.navigate("Games")))
    contents.addWidget(tool("Show Only This Game", "camera", lambda: show_game(window, capture.game)))


def related_for(window, capture):
    state = state_of(window)
    return insight.related(capture, universe(window), state.duplicates, state.similar)


def related_list(window, capture, contents):
    found = related_for(window, capture)
    if not found:
        contents.addWidget(label("Nothing is known to be related yet. Run Find Duplicates or Find Similar to compare files.", "subtle", wrap=True))
        return
    for reason, other in found:
        contents.addWidget(tool(f"{other.name}", "camera" if other.kind == "Screenshots" else "play",
                                lambda _=False, o=other: focus_capture(window, o), tip=reason))
        contents.addWidget(label(f"{reason} · {human_size(other.size)}", "caption"))


def show_game(window, game):
    for i in range(window.capture_game.count()):
        if window.capture_game.item(i).data(Qt.UserRole) == game:
            window.capture_game.setCurrentRow(i)
            return


def focus_capture(window, capture):
    rows = getattr(window, "_cap_rows", [])
    if capture.key not in {c.key for c in rows}:
        window.info("Not shown", "That capture is hidden by the current filters. Use Clear All to see it.")
        return
    index = next(i for i, c in enumerate(rows) if c.key == capture.key)
    fill(window, requested_page=index // PAGE_SIZE)
    local = index % PAGE_SIZE
    if state_of(window).compact:
        window.capture_table.selectRow(local)
    else:
        window.capture_grid.setCurrentRow(local)


# ------------------------------------------------------------------ thumbnails
def to_pixmap(image):
    qimage = QImage(image.tobytes(), image.width, image.height, image.width * 3, QImage.Format_RGB888).copy()
    return QPixmap.fromImage(qimage).scaled(360, 230, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def remember(window, capture, image):
    state = state_of(window)
    state.thumbs[capture.key] = to_pixmap(image)
    state.thumbs.move_to_end(capture.key)
    while len(state.thumbs) > THUMB_CACHE:
        state.thumbs.popitem(last=False)
    size = image.info.get("source_size", image.size)
    if capture.dimensions is None and size and size[0] and size[1]:
        capture.width, capture.height = size


def apply_thumbnails(window, keys):
    state = state_of(window)
    if not live(window):
        return
    shown = {c.key: i for i, c in enumerate(window._shown_captures)}
    for key in keys:
        i = shown.get(key)
        if i is None:
            continue
        item = window.capture_grid.item(i)
        if item is not None:
            payload = item.data(CAPTURE_ROLE) or {}
            payload.update(preview=state.thumbs.get(key), dimensions=payload["item"].dimensions)
            item.setData(CAPTURE_ROLE, payload)
    window.capture_grid.viewport().update()
    current = current_capture(window)
    if current is not None and current.key in keys:
        details(window)


def request_thumbnails(window):
    """Decode the screenshots on this page, a few at a time, in memory only."""
    state = state_of(window)
    state.generation += 1
    if state.tab == "Settings":
        state.pending = []
        return
    state.pending = [c for c in window._shown_captures if c.kind == "Screenshots" and c.key not in state.thumbs
                     and not c.dims_failed]
    if not state.loading:
        pump_thumbnails(window, state.generation)


def pump_thumbnails(window, generation):
    state = state_of(window)
    if state.generation != generation or not state.pending or not live(window):
        state.loading = False
        return
    batch, state.pending = state.pending[:THUMB_BATCH], state.pending[THUMB_BATCH:]
    state.loading = True

    def work(_progress):
        output = []
        for capture in batch:
            try:
                output.append((capture, decode_screenshot_preview(capture.old_file), ""))
            except Exception as exc:  # a bad image must never stop the gallery
                output.append((capture, None, str(exc)))
        return output

    def done(outcome):
        state.loading = False
        keys = []
        results = outcome[1] if outcome[0] == "ok" else [(c, None, "") for c in batch]
        for capture, image, reason in results:
            if image is not None:
                remember(window, capture, image)
                keys.append(capture.key)
            else:
                capture.dims_failed = True
        if live(window):
            apply_thumbnails(window, keys)
            if state.pending and state.generation == generation:
                pump_thumbnails(window, generation)
            elif state.pending:
                pump_thumbnails(window, state.generation)

    window.job(guarded(work), done, error_title="Could not safely preview image")


def request_preview(window, index):
    """Decode one screenshot now. Kept as the single-image entry point used by the reference renderer."""
    if not 0 <= index < len(window._shown_captures):
        return
    capture = window._shown_captures[index]
    if capture.kind != "Screenshots":
        window._open_folder(capture.folder)
        return

    def ready(outcome):
        if outcome[0] != "ok":
            capture.dims_failed = True
            window.status.setText("This image could not be previewed safely: " + str(outcome[1]))
            return
        remember(window, capture, outcome[1])
        if live(window):
            apply_thumbnails(window, [capture.key])

    window.job(guarded(lambda _: decode_screenshot_preview(capture.old_file)), ready, error_title="Could not safely preview image")


# ------------------------------------------------------------------ viewer
class Viewer(QDialog):
    def __init__(self, window, capture):
        super().__init__(window)
        self.window_ref, self.capture = window, capture
        self.setWindowTitle(capture.name)
        self.setMinimumSize(560, 420)
        layout = column(spacing=8, margins=(12, 12, 12, 12))
        self.setLayout(layout)
        self.image = QLabel("Loading…")
        self.image.setAlignment(Qt.AlignCenter)
        self.image.setMinimumSize(520, 320)
        layout.addWidget(self.image, 1)
        self.caption = label(f"{capture.path}\n{human_size(capture.size)}", "caption", wrap=True)
        layout.addWidget(self.caption)
        buttons = row(spacing=6)
        buttons.addWidget(tool("Open File", "file", lambda: open_capture_file(window, capture)))
        buttons.addWidget(tool("Open Folder", "folder", lambda: window._open_folder(capture.folder)))
        buttons.addStretch()
        close = tool("Close", "close", self.close)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    def show_image(self, image):
        pix = QPixmap.fromImage(QImage(image.tobytes(), image.width, image.height, image.width * 3, QImage.Format_RGB888).copy())
        self.image.setPixmap(pix.scaled(self.image.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        size = image.info.get("source_size", image.size)
        self.caption.setText(f"{self.capture.path}\n{size[0]} × {size[1]}  ·  {human_size(self.capture.size)}")


def open_viewer(window, index):
    shown = getattr(window, "_shown_captures", [])
    if not 0 <= index < len(shown):
        window.info("Choose a capture", "Select a capture to view it larger.")
        return
    capture = shown[index]
    if capture.kind != "Screenshots":
        open_capture_file(window, capture)
        return
    viewer = Viewer(window, capture)
    window._capture_viewer = viewer
    viewer.show()

    def ready(outcome):
        if not isValid(viewer):
            return
        if outcome[0] == "ok":
            viewer.show_image(outcome[1])
        else:
            viewer.image.setText("This image could not be previewed safely.\n" + str(outcome[1]))

    window.job(guarded(lambda _: decode_screenshot_preview(capture.old_file)), ready, error_title="Could not safely preview image")


# ------------------------------------------------------------------ open, copy, tag, export
def capture_roots_now(window):
    return [r.path for r in data.capture_roots(window.settings)]


def open_capture_file(window, capture):
    path = Path(capture.path)
    if (not actions.inside(path, capture_roots_now(window)) or _has_reparse_component(path) or not path.is_file()
            or is_protected_path(path, [])):
        window.error("File unavailable", "The file is missing, redirected, or outside the capture folders.")
        return
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def open_file(window):
    capture = current_capture(window)
    if capture is None:
        window.info("Choose a capture", "Select a capture to open.")
        return
    open_capture_file(window, capture)


def open_folder(window):
    capture = current_capture(window)
    if capture is None:
        window.info("Choose a capture", "Select a capture to open its folder.")
        return
    window._open_folder(capture.folder)


def copy_paths(window):
    rows = selected_captures(window, fallback=True)
    if not rows:
        window.info("Choose captures", "Check the captures whose paths you want to copy.")
        return
    QGuiApplication.clipboard().setText("\n".join(c.path for c in rows))
    window.status.setText(f"Copied {len(rows)} file path(s).")


def export_csv(window):
    rows = getattr(window, "_cap_rows", [])
    if not rows:
        window.info("Nothing to export", "No captures are shown.")
        return
    chosen, _ = QFileDialog.getSaveFileName(window, "Export the shown captures as a list", "captures.csv", "CSV (*.csv)")
    if not chosen:
        return
    buffer = io.StringIO()
    out = csv.writer(buffer)
    out.writerow(["Name", "Path", "Kind", "Game", "Game evidence", "Size (bytes)", "Modified", "Resolution"])
    for c in rows:
        out.writerow([c.name, c.path, c.kind, c.game, c.source, c.size,
                      datetime.fromtimestamp(c.modified).isoformat(timespec="seconds"),
                      f"{c.width}x{c.height}" if c.dimensions else ""])
    try:
        Path(chosen).write_text(buffer.getvalue(), encoding="utf-8", newline="")
    except OSError as exc:
        window.error("List not saved", str(exc))
        return
    window.status.setText(f"Exported {len(rows):,} captures to {chosen}. Nothing was changed.")


def copy_selected(window):
    rows = selected_captures(window, fallback=True)
    if not rows:
        window.info("Choose captures", "Check the captures you want to copy.")
        return
    if len(rows) > actions.MAX_COPY:
        window.info("Too many captures", f"Copy at most {actions.MAX_COPY} files at a time.")
        return
    chosen = QFileDialog.getExistingDirectory(window, "Copy the selected captures to this folder")
    if not chosen:
        return

    def work(_progress):
        return actions.copy_to(rows, chosen)

    def done(outcome):
        status, result = outcome
        if status != "ok":
            window.error("Copy not completed", result or "Copy canceled.")
            return
        window.status.setText(f"Copied {len(result['copied'])} file(s) to {chosen}. Originals were not changed.")
        window.info("Copy finished", f"{len(result['copied'])} copied, {len(result['skipped'])} skipped. Originals were not changed." +
                    ("\n" + "\n".join(result["skipped"][:8]) if result["skipped"] else ""))

    window.job(guarded(work), done, error_title="Copy not completed")


def ask_tag(window, title):
    text, accepted = QInputDialog.getText(window, title, "Tag name (up to 24 characters):")
    return text if accepted else None


def add_tag(window):
    rows = selected_captures(window, fallback=True)
    if not rows:
        window.info("Choose captures", "Check the captures you want to tag.")
        return
    text = ask_tag(window, "Add Tag")
    if text is None:
        return
    try:
        updated = tag_store.add_tag(tags_of(window), [c.key for c in rows], text)
        tag_store.save_tags(updated)
    except (OSError, ValueError) as exc:
        window.error("Tag not saved", str(exc))
        return
    state_of(window).tags = updated
    window.status.setText(f"Tagged {len(rows)} capture(s). Tags are stored by Game Grave only; the files are untouched.")
    refresh(window)


def remove_tag(window):
    rows = selected_captures(window, fallback=True)
    names = sorted({t for c in rows for t in tags_of(window).get(c.key, [])}, key=str.casefold)
    if not rows or not names:
        window.info("No tags to remove", "The selected captures have no tags.")
        return
    tag, accepted = QInputDialog.getItem(window, "Remove Tag", "Tag to remove from the selection:", names, 0, False)
    if not accepted:
        return
    try:
        updated = tag_store.remove_tag(tags_of(window), [c.key for c in rows], tag)
        tag_store.save_tags(updated)
    except (OSError, ValueError) as exc:
        window.error("Tag not saved", str(exc))
        return
    state_of(window).tags = updated
    refresh(window)


# ------------------------------------------------------------------ settings folders
def add_folder(window, setting):
    chosen = QFileDialog.getExistingDirectory(window, "Choose a local capture folder for read-only discovery")
    if not chosen:
        return
    path = Path(chosen)
    if _has_reparse_component(path) or not safe_scan_root(path):
        window.error("Folder not allowed", "Choose a normal local capture folder, not a drive root, system folder or redirected path.")
        return
    updated = dict(window.settings, **{setting: list(dict.fromkeys([*window.settings.get(setting, []), chosen]))})
    try:
        save_settings(updated)
    except (OSError, ValueError) as exc:
        window.error("Folder not saved", str(exc))
        return
    window.settings = updated
    scan(window)
    if live(window):
        fill_settings(window)


def remove_folder(window):
    item = window.capture_roots_list.currentItem()
    if item is None or not item.data(Qt.UserRole + 1):
        window.info("Choose a folder you added", "Folders Game Grave found itself cannot be removed here.")
        return
    path = item.data(Qt.UserRole)
    updated = dict(window.settings)
    for setting in ("screenshot_roots", "recording_roots"):
        updated[setting] = [p for p in window.settings.get(setting, []) if p != path]
    try:
        save_settings(updated)
    except (OSError, ValueError) as exc:
        window.error("Folder not saved", str(exc))
        return
    window.settings = updated
    scan(window)
    if live(window):
        fill_settings(window)


# ------------------------------------------------------------------ scanning and analysis
def begin(window, kind, message):
    state = state_of(window)
    state.busy, state.cancel, state.message = kind, threading.Event(), message
    return state.cancel


def scan(window, automatic=False):
    state = state_of(window)
    if state.busy:
        return
    if window.scanning or window.cleaning:
        if not automatic:
            window.info("Game Grave is busy", "Finish the current operation before scanning captures.")
        return
    cancel = begin(window, "scan", "Scanning capture folders. Nothing is changed.")
    settings = dict(window.settings)
    games = list(window.inventory.steam)

    def work(progress):
        return data.discover(settings, games=games, canceled=cancel.is_set, progress=lambda text: progress(0, text))

    def progress(_, text):
        state.message = text
        if live(window) and state.busy == "scan":
            window.capture_notice.setText(text)

    def done(outcome):
        status, report = outcome
        state.busy = ""
        state.scanned = True
        state.message = ""
        if status == "error":
            window.status.setText("Capture scan failed. Earlier results are unchanged.")
            window.error("Capture scan failed", report)
        elif status == "canceled":
            window.status.setText("Capture scan canceled. Earlier results are unchanged.")
        else:
            state.report = report
            state.duplicates = state.similar = None
            state.thumbs.clear()
            invalidate(window)
            window.status.setText(report.summary() + ". Nothing was changed.")
        if live(window):
            refresh(window)
            start_headers(window)

    window.job(guarded(work), done, error_title="Capture scan failed", progress=progress)
    if live(window):
        update_notice(window, getattr(window, "_cap_rows", []))


def start_headers(window):
    """Read image headers for resolution, a chunk at a time, in the background."""
    state = state_of(window)
    if state.headers_running:
        return
    todo = [c for c in universe(window) if c.kind == "Screenshots" and c.width is None and not c.dims_failed]
    if not todo:
        return
    state.headers_running = True
    chunk = todo[:400]

    def work(_progress):
        return data.read_dimensions(chunk, canceled=lambda: False)

    def done(outcome):
        state.headers_running = False
        if outcome[0] != "ok":
            for capture in chunk:
                capture.dims_failed = capture.width is None
        if live(window):
            if window.capture_resolution.currentIndex() or state_of(window).compact:
                fill(window)
            else:
                refresh_dimensions(window)
                details(window)
            start_headers(window)

    window.job(guarded(work), done, error_title="Could not read image headers")


def refresh_dimensions(window):
    """Give the visible tiles the resolution that was just read from the image headers."""
    grid = window.capture_grid
    with QSignalBlocker(grid):
        for i in range(grid.count()):
            payload = grid.item(i).data(CAPTURE_ROLE) or {}
            capture = payload.get("item")
            if capture is not None:
                payload["dimensions"] = capture.dimensions
                grid.item(i).setData(CAPTURE_ROLE, payload)
    grid.viewport().update()


def analyze(window, kind, work_fn, message, finish):
    state = state_of(window)
    if state.busy:
        return
    if window.scanning or window.cleaning:
        window.info("Game Grave is busy", "Finish the current operation first.")
        return
    cancel = begin(window, kind, message)
    captures = list(universe(window))

    def work(progress):
        return work_fn(captures, cancel.is_set, lambda done_, total: progress(0, f"{message} ({done_:,} of {total:,})"))

    def progress(_, text):
        state.message = text
        if live(window) and state.busy == kind:
            window.capture_notice.setText(text)

    def done(outcome):
        status, result = outcome
        state.busy = ""
        state.message = ""
        if status == "error":
            window.status.setText("Capture analysis failed. Earlier results are unchanged.")
            window.error("Capture analysis failed", result)
        elif status == "canceled":
            window.status.setText("Analysis canceled. Earlier results are unchanged.")
        else:
            finish(result)
        if live(window):
            fill(window)

    window.job(guarded(work), done, error_title="Capture analysis failed", progress=progress)
    if live(window):
        update_notice(window, getattr(window, "_cap_rows", []))


def find_duplicates(window):
    state = state_of(window)

    def finish(groups):
        state.duplicates = groups
        window.status.setText(f"{len(groups)} group(s) of identical captures found. Nothing was changed.")

    analyze(window, "duplicates", analysis.find_duplicates, "Comparing file contents. Nothing is changed", finish)


def find_similar(window):
    state = state_of(window)

    def finish(result):
        state.similar, state.similar_compared = result
        window.status.setText(f"{len(state.similar)} group(s) of similar screenshots found. Nothing was changed.")

    analyze(window, "similar", analysis.find_similar, "Comparing image fingerprints. Nothing is changed", finish)


# ------------------------------------------------------------------ Protect, Graveyard, Delete
def protect(window):
    rows = selected_captures(window, fallback=True)
    window._protect_paths([c.path for c in rows], lambda: refresh(window))


def add_to_graveyard(window):
    rows = selected_captures(window, fallback=True)
    if not rows:
        window.info("Choose captures", "Check the captures you want to keep in protected Graveyard review.")
        return
    if window.scanning or window.cleaning:
        window.info("Game Grave is busy", "Finish the current operation first.")
        return
    values = {r["path"]: r for r in window.settings.get("manual_review_files", []) if isinstance(r, dict) and "path" in r}
    for capture in rows:
        values[capture.path] = asdict(capture.old_file)
    if len(values) > 1000:
        window.error("Review list full", "Review the existing items before adding more paths.")
        return
    updated = dict(window.settings, manual_review_files=list(values.values()))
    try:
        save_settings(updated)
    except (OSError, ValueError) as exc:
        window.error("Review list not saved", str(exc))
        return
    window.settings = updated
    window._merge_manual_reviews()
    window.status.setText(f"{len(rows)} capture(s) added to protected Graveyard review. No files were moved.")
    window.info("Added to Graveyard review", f"{len(rows)} capture(s) added for review. No files were moved or removed.")


def delete_selected(window):
    state = state_of(window)
    rows = selected_captures(window)
    if window.scanning or window.cleaning or state.busy:
        window.info("Game Grave is busy", "Finish the current operation first.")
        return
    rules = never_touch(window)
    enabled, tip = insight.selection_state(rows, any(is_protected_path(Path(c.path), rules) for c in rows))
    if not enabled:
        window.info("Nothing to remove", tip)
        return
    window.cleaning = True
    window.capture_delete.setEnabled(False)
    settings = dict(window.settings)

    def check(_progress):
        return actions.inspect(rows, [r.path for r in data.capture_roots(settings)], rules)

    def checked(outcome):
        window.cleaning = False
        if outcome[0] != "ok":
            window.error("Capture check failed", str(outcome[1]))
            selection_count(window)
            return
        plans = outcome[1]
        bad = [f"{p.capture.name}: {p.reason}" for p in plans if not p.ok]
        if bad:
            window.error("Cannot remove these captures", "\n".join(bad[:8]) + "\n\nNothing was removed.")
            selection_count(window)
            return
        names = "\n".join(f"  {p.capture.path}" for p in plans[:12]) + (f"\n  and {len(plans) - 12} more" if len(plans) > 12 else "")
        steam = any("steam" in p.capture.source.casefold() for p in plans)
        if not window.confirm(
                "Move these captures to the Recycle Bin?",
                f"{len(plans)} capture(s), {insight.size_text([p.capture for p in plans])}:\n{names}\n\n"
                "Every file is re-checked right before it moves, and Windows must prove recovery works for each one, so this can take a "
                "while. Nothing is permanently deleted. Files in the Recycle Bin may still occupy disk space." +
                ("\n\nSteam may keep listing removed screenshots until you remove them in Steam too." if steam else ""),
                destructive=True):
            selection_count(window)
            return
        window.cleaning = True
        session = "crimson-captures-" + uuid.uuid4().hex[:10]
        keep = tuple(window.settings.get("never_touch", []))
        roots = [r.path for r in data.capture_roots(window.settings)]

        def run(_progress):
            return actions.recycle([p.capture for p in plans], roots, keep, session)

        def complete(result):
            window.cleaning = False
            if result[0] != "ok":
                window.error("Capture removal blocked", str(result[1]) + "\nNothing further was removed.")
                selection_count(window)
                return
            outcome = result[1]
            moved = set(outcome["moved"])
            gone = {c.path for c in universe(window) if c.key in moved}
            report = state.report
            if report is not None:
                report.captures = [c for c in report.captures if c.key not in moved]
            window.inventory.screenshots = [f for f in window.inventory.screenshots if f.path not in gone]
            window.inventory.recordings = [f for f in window.inventory.recordings if f.path not in gone]
            try:
                refresh_graveyard(window.inventory, window.settings)
            except Exception:  # the page must still refresh if the Graveyard rebuild cannot run
                pass
            for key in moved:
                state.thumbs.pop(key, None)
            state.checked -= moved
            if state.duplicates:
                state.duplicates = [g for g in ([k for k in grp if k not in moved] for grp in state.duplicates) if len(g) > 1]
            if state.similar:
                state.similar = [g for g in ([k for k in grp if k not in moved] for grp in state.similar) if len(g) > 1]
            invalidate(window)
            window.status.setText(f"{outcome['completed']} capture(s) moved to Recycle Bin. They may still occupy disk space.")
            if live(window):
                refresh(window)
            window.info("Captures removed", f"{outcome['completed']} moved to Recycle Bin, {len(outcome['skipped'])} skipped." +
                        ("\n" + "\n".join(outcome["skipped"][:8]) if outcome["skipped"] else ""))

        window.job(guarded(run), complete, error_title="Capture removal blocked")

    window.job(guarded(check), checked, error_title="Capture check failed")
