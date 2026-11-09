"""The scan bar: always visible while a scan runs, with the step, percent, time elapsed and an estimate of time left."""
from __future__ import annotations

import time

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton

from gg_desktop.scan_clock import ScanClock, clock_text, eta_text

STEPS = 5


class ScanProgress(QFrame):
    """Sits at the bottom of the main area while a scan runs (hidden otherwise). The top of the window never moves."""
    cancel_requested = Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("scanProgress")
        self.setFixedHeight(46)
        self.clock = ScanClock(STEPS)
        self._stage = "Starting"
        self._percent = 0
        self.busy = False
        self.caption = ""
        self._now = time.monotonic
        self.setStyleSheet(
            "QFrame#scanProgress{background:#0a121a;border-top:1px solid #4a1520;}"
            "QFrame#scanProgress QLabel{background:transparent;color:#e7eef5;font-size:13px;}"
            "QLabel#scanStage{font-weight:700;}"
            "QLabel#scanPercent{font-weight:800;font-size:15px;color:#ffffff;}"
            "QLabel#scanEta,QLabel#scanElapsed{color:#b8c6d3;}"
            "QProgressBar#scanBar{background:#05090d;border:1px solid #2a3846;border-radius:8px;}"
            "QProgressBar#scanBar::chunk{border-radius:7px;background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #b3112b,stop:1 #ff3b5c);}"
            "QPushButton#scanCancel{background:#141d27;border:1px solid #4b5a69;border-radius:6px;padding:4px 14px;"
            "color:#e7eef5;font-size:12px;}QPushButton#scanCancel:hover{border-color:#ff5269;}")
        box = QHBoxLayout(self)
        box.setContentsMargins(18, 6, 14, 6)
        box.setSpacing(14)
        self.stage_label = QLabel("Scanning")
        self.stage_label.setObjectName("scanStage")
        self.stage_label.setMinimumWidth(150)
        box.addWidget(self.stage_label, 0)
        self.bar = QProgressBar()
        self.bar.setObjectName("scanBar")
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(18)
        self.bar.setAccessibleName("Scan progress")
        box.addWidget(self.bar, 1)
        self.percent_label = QLabel("0%")
        self.percent_label.setObjectName("scanPercent")
        self.percent_label.setFixedWidth(46)
        self.percent_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        box.addWidget(self.percent_label)
        self.eta_label = QLabel(eta_text(None))
        self.eta_label.setObjectName("scanEta")
        self.eta_label.setMinimumWidth(165)
        self.eta_label.setToolTip("An estimate from how long the finished steps took. Steps differ in length, so it can change.")
        box.addWidget(self.eta_label)
        self.elapsed_label = QLabel("0:00")
        self.elapsed_label.setObjectName("scanElapsed")
        self.elapsed_label.setFixedWidth(44)
        self.elapsed_label.setToolTip("Time since the scan started")
        box.addWidget(self.elapsed_label)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("scanCancel")
        self.cancel_button.setAccessibleName("Cancel the scan")
        self.cancel_button.setCursor(Qt.PointingHandCursor)
        self.cancel_button.clicked.connect(self.cancel_requested.emit)
        box.addWidget(self.cancel_button)
        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.refresh)
        self.hide()

    # -- driven by the window -------------------------------------------------------------------------
    def begin(self, last_total=None):
        self.setRange(0, 100)
        self.clock = ScanClock(STEPS, last_total)
        self.clock.start(self._now())
        self._stage, self._percent = "Starting", 0
        self.cancel_button.setEnabled(True)
        self.refresh()
        self.show()
        self.timer.start()

    def report(self, percent, stage):
        self._percent, self._stage = percent, stage
        self.clock.advance(percent, self._now())
        self.refresh()

    def stopping(self):
        self.cancel_button.setEnabled(False)
        self.stage_label.setText("Stopping the scan…")

    def finish(self):
        """Hide the bar and return how long the scan took, so the next scan can start with an estimate."""
        total = self.clock.elapsed(self._now())
        self.timer.stop()
        self.hide()
        return total

    # -- compatibility with the old thin bar (the shell smoke drives these) ---------------------------------
    def setRange(self, low, high):
        """Other jobs (Old Files) show the bar as 'busy' with setRange(0, 0): no steps or estimate, just elapsed time."""
        self.busy = high == 0
        if self.busy and not self.isVisible():
            self.clock = ScanClock(STEPS)
            self.clock.start(self._now())
        self.cancel_button.setEnabled(True)
        self.bar.setRange(0, 0 if self.busy else 1000)
        self.percent_label.setVisible(not self.busy)
        self.caption = ""
        self.refresh()

    def set_caption(self, text):
        self.caption = text
        self.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        if not self.timer.isActive():
            self.timer.start()

    def value(self):
        """The percent of scan steps finished, as reported by the scan itself."""
        return int(self._percent)

    def setValue(self, percent):
        if not self.isVisible():
            self.show()
        self.report(percent, self._stage)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def refresh(self):
        now = self._now()
        self.elapsed_label.setText(clock_text(self.clock.elapsed(now)))
        if self.busy:
            self.stage_label.setText(self.caption or "Working…")
            self.stage_label.setToolTip(self.stage_label.text())
            self.eta_label.setText("No time estimate for this scan")
            return
        step = min(STEPS, self.clock.done + 1)
        self.stage_label.setText(f"Scanning · {self._stage} (step {step} of {STEPS})")
        self.stage_label.setToolTip(self.stage_label.text())
        fraction = self.clock.fraction(now)
        self.bar.setValue(int(fraction * 1000))
        self.percent_label.setText(f"{int(fraction * 100)}%")
        self.eta_label.setText(eta_text(self.clock.remaining(now)))
        self.elapsed_label.setText(clock_text(self.clock.elapsed(now)))
        self.setAccessibleDescription(f"{self.percent_label.text()} · {self.eta_label.text()}")
