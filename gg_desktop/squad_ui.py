"""The Squad Sync panel in Ready Room: read your real mod list, share it as a code, and see exactly what differs from a
friend's code or from your own earlier snapshot. Display and confirmation only; every rule lives in squad_core.
It cannot download or install mods. Steam Workshop items open in Steam, where you press Subscribe."""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QComboBox, QInputDialog, QLabel, QWidget

from gg_desktop import squad_core as sq
from gg_desktop.widgets import button, column, label, row

TONES = {"green": "#35DC7C", "amber": "#DFAC46", "muted": "#9AA4AC"}
SHOWN = 8
OPEN_MAX = 10


def build_panel(panel_cls, window):
    panel = panel_cls("Squad Sync", "Match your co-op group's mods using the real lists Game Grave can read.", "sync")
    panel.setMinimumHeight(290)
    body = SquadBody(window)
    panel.body_layout.setContentsMargins(14, 8, 14, 10)
    panel.body_layout.addWidget(body)
    panel.squad = body
    return panel


def _live(window):
    return getattr(getattr(window.page, "squad", None), "squad", None)


class SquadBody(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window_owner = window
        self.setup = None
        self.comparison = None
        layout = column(spacing=8)
        self.setLayout(layout)
        top = row(spacing=10)
        top.addWidget(label("Game", "readyDetail"))
        self.games = QComboBox()
        self.games.setMinimumWidth(300)
        self.games.setAccessibleName("Game for Squad Sync")
        top.addWidget(self.games)
        self.read_button = button("Read my setup", self.read, kind="primary",
                                  tip="Reads the Steam Workshop manifest, a Mod Organizer 2 profile and the Bethesda plugin list. Changes nothing.")
        top.addWidget(self.read_button)
        top.addStretch()
        layout.addLayout(top)
        self.summary = label("", "readyDetail", wrap=True)
        layout.addWidget(self.summary)
        columns = row(spacing=20)
        left = column(spacing=6)
        left.addWidget(label("Share your setup", "readyGameTitle"))
        self.copy_button = button("Copy squad code", self.copy_code, kind="actionLink",
                                  tip="A code for your friends. It holds mod names and Workshop numbers only, no paths or user name.")
        self.snapshot_button = button("Save a snapshot", self.snapshot, kind="actionLink",
                                      tip="Saves your mod list (not the mod files) so you can compare against it later.")
        left.addWidget(self.copy_button, 0, Qt.AlignLeft)
        left.addWidget(self.snapshot_button, 0, Qt.AlignLeft)
        left.addWidget(label("Squad Sync cannot download or install mods. It shows what differs; Steam Workshop items "
                             "open in Steam for you to subscribe, and anything else you get where your friend did.",
                             "readyDetail", wrap=True))
        left.addStretch()
        columns.addLayout(left, 4)
        right = column(spacing=6)
        right.addWidget(label("Match a friend or a snapshot", "readyGameTitle"))
        pick = row(spacing=14)
        self.import_button = button("Paste a squad code…", self.import_code, kind="actionLink")
        self.compare_snapshot_button = button("Compare with a snapshot…", self.compare_snapshot, kind="actionLink")
        pick.addWidget(self.import_button)
        pick.addWidget(self.compare_snapshot_button)
        pick.addStretch()
        right.addLayout(pick)
        self.result_summary = label("", "readyDetail", wrap=True)
        right.addWidget(self.result_summary)
        self.rows_box = column(spacing=3)
        right.addLayout(self.rows_box)
        self.open_button = button("Open missing Workshop items in Steam…", self.open_missing, kind="actionLink")
        right.addWidget(self.open_button, 0, Qt.AlignLeft)
        right.addStretch()
        columns.addLayout(right, 6)
        layout.addLayout(columns, 1)
        self.refresh_games()
        state = getattr(window, "squad_state", None)
        if state:
            at = self.games.findText(state["game"])
            if at >= 0:
                self.games.setCurrentIndex(at)
            self.setup, self.comparison = state["setup"], state["comparison"]
            self._show_setup()
            self._show_comparison()
        else:
            self.summary.setText("Choose a game and press Read my setup." if self.games.count()
                                 else "Scan your PC to choose a game.")
        self.games.currentIndexChanged.connect(self._game_changed)
        self._sync()

    # ------------------------------------------------------------ state
    def _save_state(self):
        game = self.games.currentText()
        self.window_owner.squad_state = {"game": game, "setup": self.setup, "comparison": self.comparison}

    def refresh_games(self):
        self.games.clear()
        seen = set()
        for game in sorted(getattr(self.window_owner.inventory, "games", ()) or (), key=lambda g: g.name.casefold()):
            if game.name.casefold() not in seen:
                seen.add(game.name.casefold())
                self.games.addItem(game.name, game)
        self.games.setEnabled(self.games.count() > 0)
        self.read_button.setEnabled(self.games.count() > 0)

    def _game_changed(self, *_):
        self.setup = self.comparison = None
        self.summary.setText("Choose a game and press Read my setup.")
        self._clear_rows()
        self.result_summary.setText("")
        self._save_state()
        self._sync()

    def _sync(self):
        have = bool(self.setup and self.setup.items)
        self.copy_button.setEnabled(have)
        self.snapshot_button.setEnabled(bool(self.setup and self.setup.read_any))
        ready = bool(self.setup and self.setup.read_any)
        self.import_button.setEnabled(ready)
        game = self.games.currentText()
        self.compare_snapshot_button.setEnabled(ready and bool(game and sq.list_snapshots(game)))
        missing = [i for i in (self.comparison.missing if self.comparison else []) if sq.workshop_url(i)]
        self.open_button.setVisible(bool(missing))

    # ------------------------------------------------------------ reading
    def read(self):
        game = self.games.currentData()
        if game is None:
            return
        library = next((s.library for s in getattr(self.window_owner.inventory, "steam", ())
                        if str(s.app_id) == str(game.app_id)), None)
        self.setup = sq.read_setup(game.name, game.app_id, library)
        self.comparison = None
        self._clear_rows()
        self.result_summary.setText("")
        self._show_setup()
        self._save_state()
        self._sync()

    def _show_setup(self):
        setup = self.setup
        if setup is None:
            return
        found = len(setup.items)
        head = (f"Found {found} mod item{'s' if found != 1 else ''} for {setup.game}. " if setup.read_any
                else f"Could not read any mod list for {setup.game}. ")
        self.summary.setText(head + " · ".join(setup.notes))

    # ------------------------------------------------------------ sharing
    def copy_code(self):
        if self.setup and self.setup.items:
            QApplication.clipboard().setText(sq.make_code(self.setup))
            self.window_owner.status.setText("Squad code copied. It holds mod names and Workshop numbers only.")

    def snapshot(self):
        if not (self.setup and self.setup.read_any):
            return
        try:
            path = sq.save_snapshot(self.setup)
        except OSError as problem:
            self.window_owner.error("Squad Sync", f"Could not save the snapshot: {problem}")
            return
        self.window_owner.status.setText(f"Snapshot saved ({path.name}). It records the list, not the mod files.")
        self._sync()

    # ------------------------------------------------------------ comparing
    def import_code(self):
        code, ok = QInputDialog.getText(self.window_owner, "Paste a squad code", "Paste the code your friend sent:")
        if not ok or not code.strip():
            return
        try:
            theirs = sq.read_code(code)
            self._compare(theirs)
        except ValueError as problem:
            self.window_owner.error("Squad Sync", str(problem))

    def compare_snapshot(self):
        game = self.games.currentText()
        options = sq.list_snapshots(game)
        if not options:
            return
        labels = [f"{made} · {count} item{'s' if count != 1 else ''}" for _p, made, count in options]
        choice, ok = QInputDialog.getItem(self.window_owner, "Compare with a snapshot", "Snapshot:", labels, 0, False)
        if not ok:
            return
        try:
            self._compare(sq.load_snapshot(options[labels.index(choice)][0]))
        except ValueError as problem:
            self.window_owner.error("Squad Sync", str(problem))

    def _compare(self, theirs):
        self.comparison = sq.compare(theirs, self.setup)
        self._show_comparison()
        self._save_state()
        self._sync()

    def _clear_rows(self):
        while self.rows_box.count():
            item = self.rows_box.takeAt(0)
            if item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().hide()
                        child.widget().deleteLater()
            elif item.widget():
                item.widget().hide()
                item.widget().deleteLater()

    def _pill(self, text, tone):
        pill = QLabel(text)
        pill.setAlignment(Qt.AlignCenter)
        color = TONES[tone]
        pill.setStyleSheet(f"font-size:11px;font-weight:700;color:{color};border:1px solid {color};"
                           "border-radius:9px;padding:1px 8px;background:transparent;")
        return pill

    def _show_comparison(self):
        self._clear_rows()
        result = self.comparison
        if result is None:
            self.result_summary.setText("")
            return
        self.result_summary.setText(result.summary)
        shown = 0
        for item in result.missing:
            if shown >= SHOWN:
                break
            shown += 1
            line = row(spacing=8)
            line.addWidget(label(item.label, "readyDetail"), 1)
            line.addWidget(self._pill("Missing", "amber"))
            if sq.workshop_url(item):
                open_one = button("Open in Steam", lambda _=False, i=item: self.open_item(i), kind="actionLink")
                open_one.setAccessibleName(f"Open {item.label} in Steam")
                line.addWidget(open_one)
            self.rows_box.addLayout(line)
        for theirs, mine in result.different:
            if shown >= SHOWN:
                break
            shown += 1
            line = row(spacing=8)
            line.addWidget(label(theirs.label, "readyDetail"), 1)
            older = int(mine.stamp) < int(theirs.stamp)
            line.addWidget(self._pill("Yours is older" if older else "Yours is newer", "amber" if older else "muted"))
            if sq.workshop_url(theirs):
                line.addWidget(button("Open in Steam", lambda _=False, i=theirs: self.open_item(i), kind="actionLink"))
            self.rows_box.addLayout(line)
        hidden = len(result.missing) + len(result.different) - shown
        if hidden > 0:
            self.rows_box.addWidget(label(f"and {hidden} more", "readyDetail"))

    # ------------------------------------------------------------ opening Steam
    def open_item(self, item):
        url = sq.workshop_url(item)
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def open_missing(self):
        if not self.comparison:
            return
        items = [i for i in self.comparison.missing if sq.workshop_url(i)][:OPEN_MAX]
        if not items:
            return
        if not self.window_owner.confirm(
                "Open in Steam",
                f"This opens {len(items)} Workshop page{'s' if len(items) != 1 else ''} in Steam, one after another. "
                "Press Subscribe on each one you want. Game Grave does not subscribe or download anything."):
            return
        for item in items:
            self.open_item(item)
