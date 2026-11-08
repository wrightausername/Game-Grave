"""More Tools page: the approved toolkit mockup, built only from tools that really exist.

Tiles that belong to another tab open that tab. Tiles that do a job here (reports, hash checker, backups, kits) do it.
Tiles that cannot work would stay visible but dimmed and
say why when clicked. System Health shows live readings only, and Active Tasks lists only work that is really running.
"""
from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QBoxLayout, QFrame, QGridLayout, QLabel, QPushButton, QSizePolicy, QToolButton,
                               QWidget)
from shiboken6 import isValid

from core import get_activity
from gg_desktop import tools_actions as actions
from gg_desktop import tools_data as data
from gg_desktop import tools_system as system
from gg_desktop.header_banner import HeaderBannerArtwork
from gg_desktop.reference_widgets import icon, tool
from gg_desktop.widgets import button, column, label, panel, row

SUBTITLE = "Back up, report on and manage your games."
TONES = {"red": "255,37,74", "cyan": "19,188,245", "purple": "180,85,255", "magenta": "223,80,200",
         "blue": "40,140,255", "yellow": "246,190,36", "green": "50,214,122"}
HEX = {"red": "#ff3b57", "cyan": "#13bcf5", "purple": "#b455ff", "magenta": "#df50c8", "blue": "#288cff",
       "yellow": "#f6be24", "green": "#32d67a"}
WIDE_AT = 880     # side column beside the categories
TWO_AT = 600      # two columns of panels
TICK_MS = 500


def accent(frame, name, tone):
    rgb = TONES[tone]
    frame.setObjectName(name)
    frame.setStyleSheet(
        f"QFrame#{name}{{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba({rgb},38),stop:.4 #08101a,stop:1 #060b12);"
        f"border:1.5px solid rgba({rgb},215);border-radius:10px;}}")
    return frame


def chip(text, tone="cyan"):
    color = HEX[tone]
    chip_label = QLabel(text)
    chip_label.setStyleSheet(f"color:{color};border:1px solid {color};background:rgba({TONES[tone]},28);"
                             "border-radius:4px;padding:1px 7px;font-size:10px;font-weight:700;")
    return chip_label


# ------------------------------------------------------------------ state
def state_of(window):
    if not hasattr(window, "_tools_state"):
        window._tools_state = SimpleNamespace(
            tab="hub", cpu=system.CpuMeter(), cpu_value=None, storage=None, memory=None, ticks=0,
            hash_name="", hash_percent=0, hash_cancel=None, task_signature=None, log_signature=None)
    return window._tools_state


def live(window):
    return (window.current_route == "More Tools" and hasattr(window, "tools_tabs") and isValid(window.tools_holder)
            and hasattr(window.page, "tools_ready"))


# ------------------------------------------------------------------ small widgets
class Meter(QWidget):
    """A thin bar for one live reading, or an empty track when the reading is unavailable."""

    def __init__(self, color):
        super().__init__()
        self.value, self.color = None, QColor(color)
        self.setFixedHeight(8)
        self.setMinimumWidth(30)

    def set_value(self, value):
        self.value = value
        self.update()

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#1a2430"))
        painter.drawRoundedRect(QRectF(0, 0, self.width(), 8), 4, 4)
        if self.value is not None:
            painter.setBrush(self.color)
            painter.drawRoundedRect(QRectF(0, 0, max(6.0, self.width() * self.value / 100), 8), 4, 4)


class Ring(QWidget):
    """A progress ring. A percent shows the value; None shows a plain ring because the work cannot report progress."""

    def __init__(self, percent):
        super().__init__()
        self.percent = percent
        self.setFixedSize(46, 46)

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        box = QRectF(5, 5, 36, 36)
        painter.setPen(QPen(QColor("#1d2a38"), 4))
        painter.drawEllipse(box)
        if self.percent is not None:
            painter.setPen(QPen(QColor("#32d67a"), 4, Qt.SolidLine, Qt.RoundCap))
            painter.drawArc(box, 90 * 16, -int(360 * 16 * self.percent / 100))
            painter.setPen(QColor("#e8eef5"))
            painter.drawText(self.rect(), Qt.AlignCenter, f"{self.percent}%")


class ToolTile(QToolButton):
    def __init__(self, tile, tone, on_click):
        super().__init__()
        self.tile = tile
        off = tile.kind == data.OFF
        self.setText(tile.title.replace(" ", "\n", 1))
        self.setIcon(icon(tile.symbol, "#5b6675" if off else "#e8eef5", 22))
        self.setIconSize(QSize(22, 22))
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.setAccessibleName(tile.title + (", not offered" if off else ""))
        self.setToolTip(tile.note or tile.title)
        self.setMinimumWidth(0)
        self.setFixedHeight(66)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setCursor(Qt.ArrowCursor if off else Qt.PointingHandCursor)
        rgb = TONES[tone]
        if off:
            self.setStyleSheet("QToolButton{background:#080d13;border:1px dashed #243242;border-radius:7px;color:#6b7788;font-size:10px;}"
                               "QToolButton:hover{border-color:#44566b;}")
        elif tile.key == "resurrection_kit":
            self.setStyleSheet(f"QToolButton{{background:rgba({rgb},40);border:1.5px solid rgba({rgb},230);border-radius:7px;"
                               "color:#e8eef5;font-size:10px;font-weight:700;}}")
        else:
            self.setStyleSheet("QToolButton{background:#0a1118;border:1px solid #243242;border-radius:7px;color:#e8eef5;font-size:10px;}"
                               f"QToolButton:hover{{border-color:rgba({rgb},230);background:rgba({rgb},26);}}")
        self.clicked.connect(lambda _=False: on_click(tile))


class ToolsTab(QPushButton):
    def __init__(self, title, subtitle, symbol):
        super().__init__()
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setFixedHeight(52)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setAccessibleName(title)
        self.setToolTip(subtitle)
        self.setCursor(Qt.PointingHandCursor)
        lay = row(spacing=8, margins=(10, 0, 6, 0))
        self.setLayout(lay)
        self.glyph = QLabel()
        self.glyph.setPixmap(icon(symbol, "#e8eef5", 20).pixmap(20, 20))
        self.glyph.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay.addWidget(self.glyph)
        words = column(spacing=0)
        self.title = label(title, "detailValue")
        self.title.setStyleSheet("font-size:13px;font-weight:700;")
        self.sub = label(subtitle, "caption")
        for part in (self.title, self.sub):
            part.setAttribute(Qt.WA_TransparentForMouseEvents)
            part.setMinimumWidth(0)
            part.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            words.addWidget(part)
        lay.addLayout(words, 1)
        self.setStyleSheet(
            "QPushButton{background:#08101a;border:1px solid #1d2a38;border-radius:8px;text-align:left;}"
            "QPushButton:hover{border-color:#44566b;}"
            "QPushButton:checked{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #ff254a,stop:1 #b3112b);"
            "border:1px solid #ff6b81;}")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.sub.setVisible(self.width() >= 150)
        self.glyph.setVisible(self.width() >= 128)


class Relay(QObject):
    """Calls back when the page holder changes width, so the panels can reflow."""

    def __init__(self, target, callback):
        super().__init__(target)
        self.callback, self.width = callback, -1
        target.installEventFilter(self)

    def eventFilter(self, target, event):
        if event.type() == QEvent.Resize and target.width() != self.width:
            self.width = target.width()
            self.callback()
        return False


def heading(symbol, text, tone):
    line = row(spacing=7)
    mark = QLabel()
    mark.setPixmap(icon(symbol, HEX[tone], 20).pixmap(20, 20))
    line.addWidget(mark)
    title = label(text, "sectionTitle")
    title.setMinimumWidth(0)
    title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    line.addWidget(title, 1)
    return line


def category_panel(window, category):
    frame, stack = panel(kind="fileFilterPanel", padding=9, spacing=6)
    accent(frame, "tools_" + category.key, category.tone)
    symbol = {"maintenance": "trash", "optimization": "sparkles", "backup": "archive", "analysis": "list",
              "utilities": "box", "advanced": "settings"}[category.key]
    frame.setAccessibleName(category.title)
    top = column(spacing=0)
    top.addLayout(heading(symbol, category.title, category.tone))
    blurb = label(category.blurb, "caption")
    blurb.setMinimumWidth(0)
    blurb.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    top.addWidget(blurb)
    stack.addLayout(top)
    tiles = row(spacing=6)
    for tile in category.tiles:
        control = ToolTile(tile, category.tone, lambda t: actions.run_tile(window, t))
        window.tools_tiles[tile.key] = control
        tiles.addWidget(control, 1)
    stack.addLayout(tiles)
    return frame


# ------------------------------------------------------------------ build
def build(window):
    self = window
    state = state_of(self)
    state.tab, state.task_signature, state.log_signature, state.ticks = "hub", None, None, 0
    self.tools_tiles, self.tools_panels = {}, {}
    page = self._insight_page("More Tools", SUBTITLE, "more_tools", "settings", 66)
    banner = page.content.itemAt(0).widget()
    page.banner_artwork = HeaderBannerArtwork(self, page, banner, route="More Tools", scene="more_tools",
                                              source=(1012, 0, 660, 150), excluded=((1425, 0, 247, 50),))
    try:  # the TOOLKIT chip sits beside the title, as in the photo
        text_column = banner.layout().itemAt(1).layout()
        title = text_column.takeAt(0).widget()
        line = row(spacing=10)
        line.addWidget(title)
        line.addWidget(chip("TOOLKIT", "red"), 0, Qt.AlignVCenter)
        line.addStretch()
        text_column.insertLayout(0, line)
    except (AttributeError, RuntimeError):
        pass

    strip = QFrame()
    strip.setObjectName("toolsTabs")
    strip_lay = row(spacing=7, margins=(0, 0, 0, 0))
    strip.setLayout(strip_lay)
    self.tools_tabs = {}
    for key, title, caption, symbol, _cats in data.TABS:
        control = ToolsTab(title, caption, symbol)
        control.setChecked(key == "hub")
        control.clicked.connect(lambda _=False, k=key: set_tab(self, k))
        self.tools_tabs[key] = control
        strip_lay.addWidget(control, 1)
    page.content.addWidget(strip)

    self.tools_holder = QWidget()
    holder_lay = column(spacing=8)
    self.tools_holder.setLayout(holder_lay)
    self.tools_main = QWidget()
    self.tools_grid = QGridLayout(self.tools_main)
    self.tools_grid.setContentsMargins(0, 0, 0, 0)
    self.tools_grid.setHorizontalSpacing(8)
    self.tools_grid.setVerticalSpacing(8)
    for category in data.CATEGORIES:
        self.tools_panels[category.key] = category_panel(self, category)
    self.tools_side = QWidget()
    self.tools_side_lay = column(spacing=8)
    self.tools_side.setLayout(self.tools_side_lay)
    self.tools_side.setFixedWidth(250)
    self.tools_health = health_panel(self)
    self.tools_quick = quick_panel(self)
    holder_lay.addWidget(self.tools_main)
    self.tools_bottom = QWidget()
    self.tools_bottom_lay = QBoxLayout(QBoxLayout.LeftToRight, self.tools_bottom)
    self.tools_bottom_lay.setContentsMargins(0, 0, 0, 0)
    self.tools_bottom_lay.setSpacing(8)
    self.tools_tasks = tasks_panel(self)
    self.tools_log = log_panel(self)
    holder_lay.addWidget(self.tools_bottom)
    holder_lay.addStretch(1)
    page.content.addWidget(self.tools_holder, 1)
    page.tools_relay = Relay(self.tools_holder, lambda: relayout(self))
    page.tools_ready = True
    relayout(self)
    tick(self, full=True)
    page.tools_timer = QTimer(page)
    page.tools_timer.setInterval(TICK_MS)
    page.tools_timer.timeout.connect(lambda: tick(self))
    if not self.reference_preview:
        page.tools_timer.start()


# ------------------------------------------------------------------ side panels
def health_panel(window):
    frame, stack = panel(kind="fileFilterPanel", padding=9, spacing=6)
    accent(frame, "toolsHealth", "green")
    top = row(spacing=7)
    top.addLayout(heading("check", "System Health", "green"), 1)
    top.addWidget(chip("Live reading", "cyan"))
    stack.addLayout(top)
    window.tools_meters, window.tools_values = {}, {}
    for key, name, symbol, color in (("storage", "Storage", "storage", "#30d76b"), ("memory", "Memory", "list", "#30d76b"),
                                     ("cpu", "CPU", "settings", "#30d76b")):
        line = row(spacing=7)
        mark = QLabel()
        mark.setPixmap(icon(symbol, "#e8eef5", 16).pixmap(16, 16))
        line.addWidget(mark)
        caption = label(name, "subtle")
        caption.setFixedWidth(46)
        line.addWidget(caption)
        meter = Meter(color)
        meter.setAccessibleName(name + " in use")
        line.addWidget(meter, 1)
        value = label("…", "detailValue")
        value.setFixedWidth(88)
        value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        line.addWidget(value)
        window.tools_meters[key], window.tools_values[key] = meter, value
        stack.addLayout(line)
    stack.addWidget(label("Readings are taken from Windows now. They are not a health verdict.", "caption", wrap=True))
    return frame


def quick_panel(window):
    frame, stack = panel(kind="fileFilterPanel", padding=9, spacing=6)
    frame.setObjectName("toolsQuick")
    stack.addLayout(heading("sparkles", "Quick Actions", "red"))
    window.tools_quick_buttons = {}
    for key, title, symbol, tone, tip in data.QUICK_ACTIONS:
        control = QPushButton(title)
        control.setIcon(icon(symbol, "#e8eef5", 20))
        control.setIconSize(QSize(20, 20))
        control.setToolTip(tip)
        control.setAccessibleName(title)
        control.setFixedHeight(36)
        control.setMinimumWidth(0)
        control.setCursor(Qt.PointingHandCursor)
        rgb = TONES[tone]
        control.setStyleSheet(
            f"QPushButton{{text-align:left;padding-left:12px;font-weight:700;color:#e8eef5;border-radius:7px;"
            f"background:rgba({rgb},{150 if tone == 'red' else 60});border:1.5px solid rgba({rgb},230);}}"
            f"QPushButton:hover{{background:rgba({rgb},120);}}")
        control.clicked.connect(lambda _=False, k=key: actions.run_quick(window, k))
        window.tools_quick_buttons[key] = control
        stack.addWidget(control)
    return frame


def tasks_panel(window):
    frame, stack = panel(kind="fileFilterPanel", padding=9, spacing=6)
    accent(frame, "toolsTasks", "red")
    window.tools_tasks_title = label("Active Tasks (0)", "sectionTitle")
    top = row(spacing=7)
    mark = QLabel()
    mark.setPixmap(icon("clock", HEX["red"], 20).pixmap(20, 20))
    top.addWidget(mark)
    top.addWidget(window.tools_tasks_title, 1)
    stack.addLayout(top)
    window.tools_task_box = column(spacing=6)
    stack.addLayout(window.tools_task_box)
    stack.addStretch(1)
    return frame


def log_panel(window):
    frame, stack = panel(kind="fileFilterPanel", padding=9, spacing=6)
    accent(frame, "toolsLog", "red")
    stack.addLayout(heading("file", "Tool Log", "red"))
    window.tools_log_box = column(spacing=3)
    stack.addLayout(window.tools_log_box)
    stack.addStretch(1)
    window.tools_log_open = tool("Open Tool Log", "file", lambda: window.navigate("Undo Center"),
                                 tip="Open the Undo Center, which holds the full activity history")
    window.tools_log_open.setFixedHeight(34)
    stack.addWidget(window.tools_log_open)
    return frame


# ------------------------------------------------------------------ behavior
def visible_keys(window):
    return [c.key for c in data.categories_for(state_of(window).tab)]


def set_tab(window, key):
    if not live(window) or key not in window.tools_tabs:
        return
    state_of(window).tab = key
    for name, control in window.tools_tabs.items():
        control.setChecked(name == key)
    relayout(window)


def _detach(layout):
    while layout.count():
        layout.takeAt(0)


def relayout(window):
    """Place the visible panels for this tab and this width. Widgets are moved, never rebuilt."""
    if not live(window):
        return
    width = window.tools_holder.width()
    wide = width >= WIDE_AT
    show = visible_keys(window)
    grid = window.tools_grid
    _detach(grid)
    _detach(window.tools_side_lay)
    _detach(window.tools_bottom_lay)
    for key, frame in window.tools_panels.items():
        frame.setVisible(key in show)
    shown = [window.tools_panels[k] for k in show]
    for column_index in range(4):
        grid.setColumnStretch(column_index, 0)
        grid.setColumnMinimumWidth(column_index, 0)
    if wide:
        for i, frame in enumerate(shown):
            grid.addWidget(frame, i // 2, i % 2)
        window.tools_side_lay.addWidget(window.tools_health)
        window.tools_side_lay.addWidget(window.tools_quick)
        window.tools_side_lay.addStretch(1)
        grid.addWidget(window.tools_side, 0, 2, max(1, (len(shown) + 1) // 2), 1)
        window.tools_side.show()
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        columns = 2
    else:
        window.tools_side.hide()
        flow = shown + [window.tools_health, window.tools_quick]
        columns = 2 if width >= TWO_AT else 1
        for i, frame in enumerate(flow):
            grid.addWidget(frame, i // columns, i % columns)
        for column_index in range(columns):
            grid.setColumnStretch(column_index, 1)
    window.tools_health.setVisible(True)
    window.tools_quick.setVisible(True)
    window.tools_bottom_lay.setDirection(QBoxLayout.LeftToRight if width >= TWO_AT else QBoxLayout.TopToBottom)
    window.tools_bottom_lay.addWidget(window.tools_tasks, 3)
    window.tools_bottom_lay.addWidget(window.tools_log, 2)


def percent_text(value):
    return "Unavailable" if value is None else f"{value}%"


def tick(window, *, full=False):
    """Refresh live readings, Active Tasks and the Tool Log. Stops quietly once the page is gone."""
    if not live(window):
        timer = getattr(window.page, "tools_timer", None) if getattr(window, "page", None) else None
        if timer is not None and isValid(timer):
            timer.stop()
        return
    state = state_of(window)
    state.ticks += 1
    state.cpu_value = state.cpu.sample()
    if full or state.ticks % 4 == 1:
        state.storage, state.memory = system.storage_percent(), system.memory_percent()
    readings = {"storage": state.storage, "memory": state.memory, "cpu": state.cpu_value}
    for key, value in readings.items():
        window.tools_meters[key].set_value(value)
        waiting = key == "cpu" and value is None and state.cpu.waiting
        window.tools_values[key].setText("…" if waiting else percent_text(value))
        window.tools_values[key].setToolTip(system.storage_text() if key == "storage" else "")
    refresh_tasks(window)
    if full or state.ticks % 10 == 0:
        refresh_log(window)


def refresh_tasks(window):
    state = state_of(window)
    tasks = data.build_tasks(scanning=window.scanning, scan_percent=window.progress.value(),
                             scan_stage=window.status.text().split(" (")[0].replace("Scanning: ", "") if window.scanning else "",
                             cleaning=window.cleaning, hash_name=state.hash_name, hash_percent=state.hash_percent)
    signature = tuple(tasks)
    if signature == state.task_signature:
        return
    state.task_signature = signature
    box = window.tools_task_box
    while box.count():
        item = box.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
    window.tools_tasks_title.setText(f"Active Tasks ({len(tasks)})")
    window.tools_task_cancel = {}
    if not tasks:
        box.addWidget(label("No tasks running. Scans, backups and checksums show up here while they work.", "subtle", wrap=True))
        return
    for task in tasks:
        card = QFrame()
        card.setObjectName("toolsTask")
        card.setStyleSheet("QFrame#toolsTask{background:#0a1118;border:1px solid #1d2a38;border-radius:8px;}")
        line = row(spacing=10, margins=(8, 6, 8, 6))
        card.setLayout(line)
        line.addWidget(Ring(task.percent))
        words = column(spacing=1)
        name = label(task.title, "detailValue")
        name.setMinimumWidth(0)
        name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        detail = label(task.detail, "caption", wrap=True)
        detail.setMinimumWidth(0)
        detail.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        words.addWidget(name)
        words.addWidget(detail)
        line.addLayout(words, 1)
        if task.cancelable:
            stop = tool("", "close", lambda _=False, kind=task.kind: cancel_task(window, kind), kind="danger",
                        tip="Cancel this task")
            stop.setFixedSize(34, 34)
            stop.setAccessibleName("Cancel " + task.title)
            window.tools_task_cancel[task.kind] = stop
            line.addWidget(stop)
        box.addWidget(card)


def cancel_task(window, kind):
    if kind == "scan":
        window.cancel_scan()
    elif kind == "hash":
        actions.cancel_hash(window)


def refresh_log(window):
    try:
        events = get_activity()
    except Exception:  # an unreadable history file must not break the page; the log just stays empty
        events = []
    lines = data.log_lines(events, 3)
    state = state_of(window)
    if tuple(lines) == state.log_signature:
        return
    state.log_signature = tuple(lines)
    box = window.tools_log_box
    while box.count():
        item = box.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
    if not lines:
        box.addWidget(label("Nothing has been recorded yet. Scans, cleanups and restores are listed here.", "subtle", wrap=True))
        return
    box.addWidget(label("Latest activity", "caption"))
    for title, when, status in lines:
        entry = label(f"{title}  ·  {status}", "detailValue")
        entry.setTextFormat(Qt.PlainText)
        entry.setMinimumWidth(0)
        entry.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        entry.setToolTip(when)
        box.addWidget(entry)
        stamp = label(when, "caption")
        stamp.setMinimumWidth(0)
        stamp.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        box.addWidget(stamp)
