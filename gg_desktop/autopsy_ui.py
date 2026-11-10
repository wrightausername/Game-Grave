"""The Autopsy panel in Ready Room: captures are found automatically, the newest ten are kept, and the latest two of the
same game are compared. Display only; every rule lives in autopsy_core and autopsy_library. Nothing here goes online or
records frames, and automatic passes are small, spaced out and skipped while a game is running."""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QFrame, QGridLayout, QLabel, QLineEdit, QWidget)

from gg_desktop import autopsy_core as au
from gg_desktop import autopsy_library as lib
from gg_desktop.feature_strip import collapsible
from gg_desktop.widgets import button, column, label, row

TONES = {"green": "#35DC7C", "amber": "#DFAC46", "muted": "#9AA4AC"}
BEFORE_COLOR, AFTER_COLOR = "#CED3D8", "#E5384F"
RETRY_MS = 8 * 1000             # when Game Grave's own scan is busy, look again soon (at most RETRY_LIMIT times per start)
RETRY_LIMIT = 6
TICK_MS = 5 * 60 * 1000          # how often a visible panel checks whether a pass is due (the check itself is free)
INTRO = ("Game Grave looks in the folders PresentMon, CapFrameX and FrameView save to, about every 30 minutes while "
         "this page is open and no game is running. It keeps the newest ten captures and compares the latest two of "
         "the same game. Your capture files are never changed or deleted.")


@dataclass
class Result:
    comparison: object = None
    error: str = ""
    before_points: list = None
    after_points: list = None
    before_name: str = ""
    after_name: str = ""


def build_panel(panel_cls, window):
    panel = collapsible(panel_cls, "Autopsy", "Automatic. Compares your newest frame-time captures, ten kept.", "pulse",
                        open_height=420)
    body = AutopsyBody(window)
    body.on_status = panel.set_subtitle
    panel.body_layout.setContentsMargins(14, 8, 14, 10)
    panel.body_layout.addWidget(body)
    panel.autopsy = body
    body.reload()
    body.auto_scan()
    return panel


def result_for(before, after) -> Result:
    """A comparison of two library entries. Pure arithmetic on stored numbers, so it is instant."""
    comparison = au.compare(before.stats_obj(), after.stats_obj())
    return Result(comparison, "", before.points, after.points, before.name, after.name)


def game_running(window) -> bool:
    """True when the Games tracker, which already samples processes, last saw a game running. Costs nothing extra."""
    tracker = getattr(window, "_games_tracker", None)
    return bool(tracker is not None and getattr(getattr(tracker, "ledger", None), "active", None))


def scan_allowed(window, now=None) -> bool:
    if getattr(window, "scanning", False) or getattr(window, "cleaning", False):
        return False
    if game_running(window) or getattr(window, "autopsy_busy", False):
        return False
    return lib.due(getattr(window, "autopsy_last_pass", None), now)


def run_pass(window, done=None, *, by_hand: bool = False):
    """One bounded capture check in the background. Errors become notes, never a dialog (it may run during a game)."""
    window.autopsy_busy = True
    window.autopsy_last_pass = time.monotonic()

    def work(_progress):
        try:
            return lib.refresh()
        except Exception as problem:     # noqa: BLE001 - a background pass must never raise a dialog
            return lib.Refresh(notes=[f"Capture check stopped: {problem}"], looked=True)

    def finish(result):
        window.autopsy_busy = False
        window.autopsy_notes = result.notes
        body = getattr(getattr(window.page, "autopsy", None), "autopsy", None)
        if body is not None:
            try:
                body.after_pass(result, by_hand)
            except RuntimeError:
                pass
        if done:
            done(result)

    window.job(work, finish, error_title="Autopsy could not check for captures")


class FrameGraph(QWidget):
    def __init__(self):
        super().__init__()
        self.before, self.after, self.cap = [], [], 40.0
        self.setMinimumSize(300, 170)
        self.setAccessibleName("Frame time graph, before and after")

    def set_data(self, before, after, cap):
        self.before, self.after, self.cap = before or [], after or [], max(cap, 20.0)
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        box = QRectF(0, 0, self.width(), self.height())
        p.fillRect(box, QColor("#0B0F12"))
        p.setPen(QPen(QColor("#222A30"), 1))
        p.drawRect(box.adjusted(0.5, 0.5, -0.5, -0.5))
        plot = QRectF(40, 22, self.width() - 52, self.height() - 36)
        small = QFont(self.font())
        small.setPointSize(8)
        p.setFont(small)
        if not self.before and not self.after:
            p.setPen(QColor("#9AA4AC"))
            p.drawText(box, Qt.AlignCenter, "Choose two captures and press Compare")
            return

        def y_of(ms):
            return plot.bottom() - plot.height() * min(ms, self.cap) / self.cap

        for ms, name in ((0, "0"), (16.7, "60 FPS"), (33.3, "30 FPS"), (self.cap, f"{self.cap:.0f} ms")):
            if ms > self.cap + 0.01:
                continue
            y = y_of(ms)
            p.setPen(QPen(QColor("#222A30"), 1, Qt.DashLine if 0 < ms < self.cap else Qt.SolidLine))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(QColor("#9AA4AC"))
            p.drawText(QRectF(0, y - 8, 38, 16), Qt.AlignRight | Qt.AlignVCenter, name)
        for values, color in ((self.before, BEFORE_COLOR), (self.after, AFTER_COLOR)):
            if len(values) < 2:
                continue
            path = QPainterPath()
            for i, ms in enumerate(values):
                point = QPointF(plot.left() + plot.width() * i / (len(values) - 1), y_of(ms))
                path.moveTo(point) if i == 0 else path.lineTo(point)
            p.setPen(QPen(QColor(color), 1.3))
            p.drawPath(path)
        for at, (name, color) in enumerate((("Before", BEFORE_COLOR), ("After", AFTER_COLOR))):
            x = plot.left() + 6 + at * 70
            p.setPen(QPen(QColor(color), 2))
            p.drawLine(QPointF(x, 11), QPointF(x + 14, 11))
            p.setPen(QColor("#E6E8EB"))
            p.drawText(QRectF(x + 18, 3, 50, 16), Qt.AlignLeft | Qt.AlignVCenter, name)


class AutopsyBody(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window_owner = window
        self.entries = []
        self.result = None
        self.on_status = None
        self._loading = False
        layout = column(spacing=8)
        self.setLayout(layout)
        top = row(spacing=14)
        self.count = label("", "readyGameTitle")
        top.addWidget(self.count, 1)
        self.check_button = button("Check for new captures", self.check_now, kind="actionLink",
                                   tip="Looks in the PresentMon, CapFrameX and FrameView folders once, right now.")
        self.add_button = button("Add a capture…", self.add_by_hand, kind="actionLink",
                                 tip="Adds one CSV from anywhere. It counts toward the ten kept.")
        top.addWidget(self.check_button)
        top.addWidget(self.add_button)
        layout.addLayout(top)
        pick = row(spacing=10)
        self.combos = {}
        for key, title in (("before", "Before"), ("after", "After")):
            heading = label(title, "readyGameTitle")
            heading.setFixedWidth(52)
            combo = QComboBox()
            combo.setMinimumWidth(240)
            combo.setAccessibleName(f"{title} capture")
            combo.currentIndexChanged.connect(self._picked)
            self.combos[key] = combo
            pick.addWidget(heading)
            pick.addWidget(combo, 1)
        layout.addLayout(pick)
        line = row(spacing=10)
        self.note = QLineEdit()
        self.note.setMaxLength(120)
        self.note.setPlaceholderText("What changed between the two? For example: updated the graphics driver")
        self.note.setAccessibleName("What changed")
        self.note.textChanged.connect(self._remember)
        line.addWidget(self.note, 1)
        layout.addLayout(line)
        self.summary = label(INTRO, "readyDetail", wrap=True)
        layout.addWidget(self.summary)
        middle = row(spacing=14)
        self.graph = FrameGraph()
        middle.addWidget(self.graph, 5)
        self.grid_frame = QFrame()
        self.grid = QGridLayout(self.grid_frame)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(3)
        middle.addWidget(self.grid_frame, 6)
        layout.addLayout(middle, 1)
        tools = row(spacing=14)
        self.copy_button = button("Copy comparison", self.copy, kind="actionLink",
                                  tip="Copies the table and the plain summary as text.")
        tools.addWidget(self.copy_button)
        tools.addStretch()
        layout.addLayout(tools)
        saved = getattr(window, "autopsy_choice", None)
        if saved:
            self.note.setText(saved.get("note", ""))
        # Only a visible page checks, and only when a pass is due and no game is running.
        self._retries = 0
        self.timer = QTimer(self)
        self.timer.setInterval(TICK_MS)
        self.timer.timeout.connect(self.auto_scan)
        self.timer.start()

    # ------------------------------------------------------------ library
    def reload(self, *, choose_newest: bool = False):
        self.entries = lib.load()
        self._loading = True
        saved = getattr(self.window_owner, "autopsy_choice", None) or {}
        for key, combo in self.combos.items():
            combo.clear()
            for entry in self.entries:
                combo.addItem(entry.label(), entry.id)
        before, after = lib.pair_for(self.entries)
        wanted = {"before": before, "after": after}
        if not choose_newest and saved.get("before") and saved.get("after"):
            ids = {e.id for e in self.entries}
            if saved["before"] in ids and saved["after"] in ids:
                wanted = {"before": next(e for e in self.entries if e.id == saved["before"]),
                          "after": next(e for e in self.entries if e.id == saved["after"])}
        for key, entry in wanted.items():
            if entry is not None:
                self.combos[key].setCurrentIndex(max(0, self.combos[key].findData(entry.id)))
            else:
                self.combos[key].setCurrentIndex(-1)
        self._loading = False
        self.count.setText(f"{len(self.entries)} of {lib.KEEP} captures kept")
        self._show()

    def _chosen(self):
        by_id = {e.id: e for e in self.entries}
        return tuple(by_id.get(self.combos[k].currentData()) for k in ("before", "after"))

    def _picked(self, *_):
        if not self._loading:
            self._remember()
            self._show()

    def _remember(self, *_):
        before, after = self._chosen()
        self.window_owner.autopsy_choice = {"before": before.id if before else "", "after": after.id if after else "",
                                            "note": self.note.text()}

    def _show(self):
        before, after = self._chosen()
        self._clear_grid()
        self.result = None
        if not self.entries:
            self.graph.set_data([], [], 40)
            self.summary.setText(INTRO + " Nothing found yet. Save a capture and it will appear here.")
            self._status("Automatic. Save a capture with PresentMon, CapFrameX or FrameView and it appears here.")
        elif before is None or after is None:
            self.graph.set_data([], [], 40)
            self.summary.setText("Pick a Before and an After capture. " + INTRO if len(self.entries) > 1 else
                                 "One capture kept. Autopsy needs a second capture of the same game to compare.")
            self._status(f"{len(self.entries)} of {lib.KEEP} captures kept. Waiting for a second capture of the same game.")
        elif before.id == after.id:
            self.graph.set_data([], [], 40)
            self.summary.setText("Before and After are the same capture. Choose two different ones.")
            self._status(f"{len(self.entries)} of {lib.KEEP} captures kept.")
        else:
            self.result = result_for(before, after)
            comparison = self.result.comparison
            self.summary.setText(comparison.summary)
            cap = 40.0
            if comparison.comparable:
                cap = max(34.0, 1.3 * max(comparison.before.p99_ms, comparison.after.p99_ms))
            self.graph.set_data(self.result.before_points, self.result.after_points, cap)
            self._fill_grid(comparison)
            guessed = before.game.casefold() != after.game.casefold()
            if guessed:
                self.summary.setText(self.summary.text() + " These two look like different games by their file names.")
            self._status(f"{len(self.entries)} of {lib.KEEP} kept. " + lib.headline(comparison))
        self.copy_button.setEnabled(bool(self.result and self.result.comparison))

    def _status(self, text):
        if self.on_status is not None:
            self.on_status(text)

    # ------------------------------------------------------------ automatic and manual passes
    def auto_scan(self):
        """A quiet pass, only while Ready Room is the page on screen, the window is up, no game is running and a pass is
        due. Nothing runs in the background otherwise."""
        owner = self.window_owner
        live = getattr(getattr(owner, "page", None), "autopsy", None)
        if getattr(live, "autopsy", None) is not self:
            return
        if not owner.isVisible() or owner.isMinimized():
            return
        if scan_allowed(owner):
            run_pass(owner)
        elif (getattr(owner, "scanning", False) or getattr(owner, "cleaning", False)) \
                and lib.due(getattr(owner, "autopsy_last_pass", None)) and self._retries < RETRY_LIMIT:
            # Another job of Game Grave's own is busy: look again shortly instead of waiting for the next five minute tick.
            # A running game never schedules a retry; that waits for the slow tick.
            self._retries += 1
            QTimer.singleShot(RETRY_MS, self.auto_scan)

    def check_now(self):
        if getattr(self.window_owner, "autopsy_busy", False):
            return
        self.check_button.setEnabled(False)
        self.summary.setText("Looking in the capture folders…")
        run_pass(self.window_owner, by_hand=True)

    def after_pass(self, result, by_hand):
        self.check_button.setEnabled(True)
        if result.added:
            self.reload(choose_newest=True)
            tail = f" Replaced the oldest {len(result.dropped)}." if result.dropped else ""
            self.summary.setText(self.summary.text() + f" Found {len(result.added)} new capture"
                                 f"{'s' if len(result.added) != 1 else ''}.{tail}")
        elif by_hand:
            self.summary.setText(("No new captures found. " + " ".join(result.notes)).strip())
        if result.notes and not by_hand and not result.added:
            self.window_owner.autopsy_notes = result.notes

    def add_by_hand(self):
        path, _ = QFileDialog.getOpenFileName(self.window_owner, "Add a frame-time capture", "",
                                              "Frame-time captures (*.csv);;All files (*)")
        if not path:
            return
        self.add_button.setEnabled(False)
        self.summary.setText("Reading the capture…")

        def work(_progress):
            try:
                return lib.add_by_hand(path), ""
            except (au.CaptureError, OSError) as problem:
                return None, str(problem)

        def finish(result):
            self.add_button.setEnabled(True)
            outcome, problem = result
            if problem:
                self.summary.setText(problem)
                return
            self.reload(choose_newest=True)
            if outcome[1]:
                self.summary.setText(self.summary.text() + " Replaced the oldest one.")

        self.window_owner.job(work, finish, error_title="Autopsy could not add the capture")

    def _clear_grid(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

    def _fill_grid(self, comparison):
        if not comparison.comparable:
            return
        for col, text in enumerate(("Metric", "Before", "After", "Change")):
            head = label(text, "readyWhen")
            head.setStyleSheet("font-size:11px;font-weight:700;color:#9AA4AC;")
            self.grid.addWidget(head, 0, col, Qt.AlignLeft if col == 0 else Qt.AlignRight)
        for at, r in enumerate(comparison.rows, start=1):
            self.grid.addWidget(label(r.metric, "readyDetail"), at, 0)
            for col, text in ((1, r.before), (2, r.after)):
                value = label(text, "readyDetail")
                value.setStyleSheet("font-size:13px;color:#E6E8EB;")
                self.grid.addWidget(value, at, col, Qt.AlignRight)
            tone = TONES[r.tone]
            pill = QLabel(f"{r.change}  {r.verdict}" if r.verdict else r.change)
            pill.setAlignment(Qt.AlignCenter)
            pill.setStyleSheet(f"font-size:11px;font-weight:700;color:{tone};border:1px solid {tone};"
                               "border-radius:9px;padding:1px 8px;background:transparent;")
            pill.setAccessibleName(f"{r.metric}: {r.change} {r.verdict}")
            self.grid.addWidget(pill, at, 3, Qt.AlignRight)
        self.grid.setColumnStretch(0, 1)

    def copy(self):
        result = self.result
        if result and result.comparison:
            QApplication.clipboard().setText(au.report_text(self.note.text(), result.before_name, result.after_name,
                                                            result.comparison))
            self.window_owner.status.setText("Autopsy comparison copied.")
