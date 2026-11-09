"""The Black Box panel in Ready Room: pick a game, build a crash report from what Windows and the game folder
recorded, then read, copy or save it. Display only; every rule lives in blackbox_core. Nothing here goes online."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QComboBox, QPlainTextEdit, QWidget

from gg_desktop import blackbox_core as bb
from gg_desktop.widgets import button, column, label, row


def build_panel(panel_cls, window):
    panel = panel_cls("Black Box", "After a crash, gather what Windows and the game folder recorded into one report.",
                      "warning")
    panel.setMinimumHeight(330)
    body = BlackBoxBody(window)
    panel.body_layout.setContentsMargins(14, 8, 14, 10)
    panel.body_layout.addWidget(body)
    panel.blackbox = body
    return panel


def deliver(window, report):
    """The page can be rebuilt while a report is being made (for example by the live news refresh), so keep the
    newest report on the window and hand it to whichever panel is showing now."""
    window.blackbox_last = report
    panel = getattr(window.page, "blackbox", None)
    body = getattr(panel, "blackbox", None)
    if body is not None:
        try:
            body.show_report(report)
        except RuntimeError:
            pass


class BlackBoxBody(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window_owner = window
        self.report = None
        self.text = ""
        self.saved = None
        layout = column(spacing=8)
        self.setLayout(layout)
        top = row(spacing=10)
        top.addWidget(label("Game", "readyDetail"))
        self.games = QComboBox()
        self.games.setMinimumWidth(300)
        self.games.setAccessibleName("Game for the Black Box report")
        top.addWidget(self.games)
        self.build_button = button("Build report", self.build, kind="primary",
                                   tip="Reads the Windows Application log and the game folder. Changes nothing.")
        top.addWidget(self.build_button)
        top.addStretch()
        layout.addLayout(top)
        self.summary = label("", "readyDetail", wrap=True)
        layout.addWidget(self.summary)
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setMinimumHeight(170)
        self.view.setAccessibleName("Black Box report")
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.Monospace)
        mono.setPointSize(9)
        self.view.setFont(mono)
        self.view.setStyleSheet("background:#0B0F12;border:1px solid #222A30;color:#CED3D8;")
        layout.addWidget(self.view, 1)
        tools = row(spacing=14)
        self.copy_button = button("Copy report", self.copy, kind="readyLink",
                                  tip="Copies the text. The Windows user name is already hidden.")
        self.save_button = button("Save report file", self.save, kind="readyLink")
        self.folder_button = button("Open reports folder", self.open_folder, kind="readyLink")
        for control in (self.copy_button, self.save_button, self.folder_button):
            tools.addWidget(control)
        tools.addStretch()
        layout.addLayout(tools)
        self.refresh()
        last = getattr(window, "blackbox_last", None)
        if last is not None:
            self.show_report(last)

    def _choices(self):
        seen, items = set(), []
        for game in getattr(self.window_owner.inventory, "games", ()) or ():
            path = getattr(game, "install_path", None)
            if not path or game.name.casefold() in seen or not Path(path).is_dir():
                continue
            seen.add(game.name.casefold())
            items.append(game)
        return sorted(items, key=lambda g: g.name.casefold())

    def refresh(self):
        current = self.games.currentText()
        self.games.clear()
        for game in self._choices():
            self.games.addItem(game.name, game)
        at = self.games.findText(current)
        if at >= 0:
            self.games.setCurrentIndex(at)
        has_games = self.games.count() > 0
        self.games.setEnabled(has_games)
        self.build_button.setEnabled(has_games)
        if not has_games and not self.text:
            self.summary.setText("Scan your PC to choose a game. Black Box only reads; it never changes a game file.")
        self._sync()

    def _sync(self):
        for control in (self.copy_button, self.save_button):
            control.setEnabled(bool(self.text))

    def build(self):
        game = self.games.currentData()
        if game is None:
            return
        self.build_button.setEnabled(False)
        self.summary.setText(f"Reading the Windows log and {game.name}'s folder…")

        def work(_progress):
            import core
            return bb.build_report(game.name, game.install_path, activity=core.get_activity())
        self.window_owner.job(work, lambda report: deliver(self.window_owner, report),
                              error_title="Black Box could not build the report")

    def show_report(self, report):
        at = self.games.findText(report.game)
        if at >= 0:
            self.games.setCurrentIndex(at)
        self.report = report
        self.text = bb.render(report)
        self.saved = None
        self.view.setPlainText(self.text)
        crashes, logs = len(report.crashes), len(report.logs)
        if not report.event_log_ok:
            head = "Windows would not share its crash log on this PC."
        else:
            head = f"{crashes} crash{'es' if crashes != 1 else ''} recorded by Windows"
        self.summary.setText(f"{head}, {logs} log or dump file{'s' if logs != 1 else ''} in the game folder. "
                             "This shows what was recorded, not why it crashed.")
        self.build_button.setEnabled(True)
        self._sync()

    def copy(self):
        if self.text:
            QApplication.clipboard().setText(self.text)
            self.window_owner.status.setText("Black Box report copied. The Windows user name is hidden.")

    def save(self):
        if not self.report:
            return
        try:
            self.saved = bb.save_report(self.report, self.text)
        except OSError as problem:
            self.window_owner.error("Black Box", f"Could not save the report: {problem}")
            return
        self.window_owner.status.setText(f"Black Box report saved: {self.saved.name}")

    def open_folder(self):
        folder = bb.blackbox_dir()
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            return
        self.window_owner._open_folder(str(folder))
