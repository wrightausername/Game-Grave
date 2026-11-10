"""The Autopsy panel in Ready Room: pick a before capture and an after capture, see the frame-time traces and a
plain comparison. Display only; every rule lives in autopsy_core. Nothing here goes online or records frames."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QFileDialog, QFrame, QGridLayout, QLabel, QLineEdit, QWidget

from gg_desktop import autopsy_core as au
from gg_desktop.widgets import button, column, label, row

TONES = {"green": "#35DC7C", "amber": "#DFAC46", "muted": "#9AA4AC"}
BEFORE_COLOR, AFTER_COLOR = "#CED3D8", "#E5384F"
POINTS = 700


@dataclass
class Result:
    comparison: object = None
    error: str = ""
    before_points: list = None
    after_points: list = None
    before_name: str = ""
    after_name: str = ""


def build_panel(panel_cls, window):
    panel = panel_cls("Autopsy", "Compare two frame-time captures from before and after a change.", "pulse")
    panel.setMinimumHeight(360)
    body = AutopsyBody(window)
    panel.body_layout.setContentsMargins(14, 8, 14, 10)
    panel.body_layout.addWidget(body)
    panel.autopsy = body
    return panel


def compute(before_path, after_path) -> Result:
    """Runs off the main thread. Problems with a file come back as text, never as a dialog."""
    try:
        before, after = au.read_capture(before_path), au.read_capture(after_path)
    except au.CaptureError as problem:
        return Result(error=str(problem))
    comparison = au.compare(au.stats_for(before), au.stats_for(after))
    return Result(comparison, "", au.downsample_max(before, POINTS), au.downsample_max(after, POINTS),
                  Path(before_path).name, Path(after_path).name)


def deliver(window, result):
    """The page can be rebuilt while a comparison runs, so keep the newest result on the window."""
    window.autopsy_result = result
    panel = getattr(window.page, "autopsy", None)
    body = getattr(panel, "autopsy", None)
    if body is not None:
        try:
            body.show_result(result)
        except RuntimeError:
            pass


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
        self.paths = {"before": None, "after": None}
        self.names = {}
        self.result = None
        layout = column(spacing=8)
        self.setLayout(layout)
        for key, title in (("before", "Before"), ("after", "After")):
            line = row(spacing=10)
            heading = label(title, "readyGameTitle")
            heading.setFixedWidth(52)
            line.addWidget(heading)
            name = label("No file chosen", "readyDetail")
            self.names[key] = name
            line.addWidget(name, 1)
            choose = button("Choose capture…", lambda _=False, k=key: self.choose(k), kind="actionLink",
                            tip="A CSV saved by PresentMon, CapFrameX or FrameView with a MsBetweenPresents or FrameTime column.")
            choose.setAccessibleName(f"Choose {title.lower()} capture")
            setattr(self, f"{key}_button", choose)
            line.addWidget(choose)
            layout.addLayout(line)
        line = row(spacing=10)
        self.note = QLineEdit()
        self.note.setMaxLength(120)
        self.note.setPlaceholderText("What changed between the two? For example: updated the graphics driver")
        self.note.setAccessibleName("What changed")
        line.addWidget(self.note, 1)
        self.compare_button = button("Compare", self.compare, kind="primary",
                                     tip="Reads the two files and does arithmetic on them. Changes nothing.")
        line.addWidget(self.compare_button)
        layout.addLayout(line)
        self.summary = label("", "readyDetail", wrap=True)
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
        saved = getattr(window, "autopsy_paths", None)
        if saved:
            self.paths.update(saved["paths"])
            self.note.setText(saved["note"])
            self._names()
        self.note.textChanged.connect(self._remember)
        last = getattr(window, "autopsy_result", None)
        if last is not None:
            self.show_result(last)
        else:
            self.summary.setText("Game Grave does not record frames. Capture before and after with PresentMon, "
                                 "CapFrameX or FrameView, then choose the two files here.")
        self._sync()

    def _remember(self, *_):
        self.window_owner.autopsy_paths = {"paths": dict(self.paths), "note": self.note.text()}

    def _names(self):
        for key, path in self.paths.items():
            self.names[key].setText(Path(path).name if path else "No file chosen")

    def _sync(self):
        self.compare_button.setEnabled(all(self.paths.values()))
        self.copy_button.setEnabled(bool(self.result and self.result.comparison))

    def choose(self, key):
        path, _ = QFileDialog.getOpenFileName(self.window_owner, f"Choose the {key} capture", "",
                                              "Frame-time captures (*.csv);;All files (*)")
        if not path:
            return
        self.paths[key] = path
        self._names()
        self._remember()
        self._sync()

    def compare(self):
        before, after = self.paths["before"], self.paths["after"]
        if not (before and after):
            return
        self.compare_button.setEnabled(False)
        self.summary.setText("Reading both captures…")
        self.window_owner.job(lambda _progress: compute(before, after), lambda r: deliver(self.window_owner, r),
                              error_title="Autopsy could not compare the captures")

    def show_result(self, result):
        self.result = result
        self._clear_grid()
        if result.error:
            self.summary.setText(result.error)
            self.graph.set_data([], [], 40)
        else:
            comparison = result.comparison
            self.summary.setText(comparison.summary)
            cap = 40.0
            if comparison.comparable:
                cap = max(34.0, 1.3 * max(comparison.before.p99_ms, comparison.after.p99_ms))
            self.graph.set_data(result.before_points, result.after_points, cap)
            self._fill_grid(comparison)
        self.compare_button.setEnabled(all(self.paths.values()))
        self._sync()

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
