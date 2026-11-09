"""The Soulbind panel in Ready Room: set preferences once, see which games Game Grave can verify, apply with a backup.

Display and confirmation only; every file rule lives in soulbind_core. Nothing here runs a game or goes online.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFrame, QGridLayout, QInputDialog, QLabel,
                               QSpinBox, QWidget)

from gg_desktop import soulbind_core as sb
from gg_desktop.widgets import button, column, label, row

TONES = {"green": "#35DC7C", "amber": "#DFAC46", "muted": "#9AA4AC"}
MAX_GAMES = 6


def build_panel(panel_cls, window, roots=None):
    panel = panel_cls("Soulbind", "Set your game preferences once. Apply them to every game Game Grave can verify.",
                      "star")
    panel.setMinimumHeight(330)
    body = SoulbindBody(window, roots)
    panel.body_layout.setContentsMargins(14, 8, 14, 10)
    panel.body_layout.addWidget(body)
    panel.soulbind = body
    return panel


class SoulbindBody(QWidget):
    def __init__(self, window, roots=None):
        super().__init__()
        self.window_owner = window
        self.roots = roots
        self.profile = sb.load_profile()
        self.uses, self.controls = {}, {}
        self._loading = False
        layout = row(spacing=20, margins=(0, 0, 0, 0))
        self.setLayout(layout)
        layout.addLayout(self._profile_column(), 5)
        divider = QFrame()
        divider.setFixedWidth(1)
        divider.setStyleSheet("background:#222A30;")
        layout.addWidget(divider)
        self.games_column = column(spacing=0)
        layout.addLayout(self.games_column, 6)
        self._load_controls()
        self.refresh()

    # ------------------------------------------------------------ your preferences
    def _profile_column(self):
        box = column(spacing=4)
        box.addWidget(label("Your preferences", "readyGameTitle"))
        box.addWidget(label("Tick what you want every game to follow. Unticked preferences are left alone.",
                            "readyDetail", wrap=True))
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(5)
        grid.setColumnStretch(1, 1)
        at = 0
        for group in sb.GROUPS:
            heading = label(group.upper(), "readyWhen")
            heading.setStyleSheet("font-size:11px;font-weight:700;color:#9AA4AC;")
            grid.addWidget(heading, at, 0, 1, 3)
            at += 1
            for pref in (p for p in sb.PREFS if p.group == group):
                use = QCheckBox()
                use.setAccessibleName("Use " + pref.label)
                use.toggled.connect(self._changed)
                text = label(pref.label, "readyDetail")
                text.setToolTip(pref.tip or pref.label)
                text.setStyleSheet("font-size:13px;color:#E6E8EB;")
                control = self._control(pref)
                control.setAccessibleName(pref.label)
                (control.valueChanged if pref.kind == "number" else control.currentIndexChanged).connect(self._changed)
                grid.addWidget(use, at, 0)
                grid.addWidget(text, at, 1)
                grid.addWidget(control, at, 2)
                self.uses[pref.id], self.controls[pref.id] = use, control
                at += 1
        box.addLayout(grid)
        box.addStretch()
        tools = row(spacing=14)
        self.copy_button = button("Copy my Soulbind code", self.copy_code, kind="readyLink",
                                  tip="A short code you can send to a friend. It holds only these preferences.")
        self.import_button = button("Import a code…", self.import_code, kind="readyLink")
        tools.addWidget(self.copy_button)
        tools.addWidget(self.import_button)
        tools.addStretch()
        box.addLayout(tools)
        return box

    @staticmethod
    def _control(pref):
        if pref.kind == "number":
            spin = QSpinBox()
            spin.setRange(*pref.options)
            spin.setSuffix("°")
            spin.setFixedWidth(96)
            return spin
        combo = QComboBox()
        combo.setFixedWidth(120)
        if pref.kind == "toggle":
            combo.addItem("On", True)
            combo.addItem("Off", False)
        else:
            for value, text in pref.options:
                combo.addItem(text, value)
        return combo

    def _load_controls(self):
        self._loading = True
        for pref in sb.PREFS:
            use, control = self.uses[pref.id], self.controls[pref.id]
            value = self.profile.get(pref.id, pref.default)
            use.setChecked(pref.id in self.profile)
            if pref.kind == "number":
                control.setValue(int(value))
            else:
                control.setCurrentIndex(max(0, control.findData(value)))
            control.setEnabled(pref.id in self.profile)
        self._loading = False

    def _changed(self, *_):
        if self._loading:
            return
        profile = {}
        for pref in sb.PREFS:
            use, control = self.uses[pref.id], self.controls[pref.id]
            control.setEnabled(use.isChecked())
            if use.isChecked():
                profile[pref.id] = control.value() if pref.kind == "number" else control.currentData()
        self.profile = sb.clean_profile(profile)
        try:
            sb.save_profile(self.profile)
        except OSError:
            pass
        self.refresh()

    def copy_code(self):
        if not self.profile:
            self.window_owner.info("Soulbind", "Tick at least one preference first.")
            return
        QApplication.clipboard().setText(sb.make_code(self.profile))
        self.window_owner.status.setText("Soulbind code copied. It holds only your ticked preferences.")

    def import_code(self):
        code, ok = QInputDialog.getText(self.window_owner, "Import a Soulbind code", "Paste the code:")
        if not ok or not code.strip():
            return
        try:
            profile = sb.read_code(code)
        except ValueError as problem:
            self.window_owner.error("Soulbind", str(problem))
            return
        if self.profile and not self.window_owner.confirm(
                "Replace your preferences?", "This replaces the preferences you have ticked now with the ones in the code."):
            return
        self.profile = profile
        try:
            sb.save_profile(profile)
        except OSError:
            pass
        self._load_controls()
        self.refresh()

    # ------------------------------------------------------------ your games
    def _games(self):
        seen, games = set(), []
        for game in getattr(self.window_owner.inventory, "games", ()) or ():
            if game.name.casefold() in seen:
                continue
            seen.add(game.name.casefold())
            games.append(game)
        return games

    def _clear(self):
        while self.games_column.count():
            item = self.games_column.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().hide()
                        child.widget().deleteLater()

    def refresh(self):
        self._clear()
        self.rows = []
        self.games_column.addWidget(label("Your games", "readyGameTitle"))
        games = self._games()
        known = [(g, sb.adapter_for(g.name)) for g in games]
        verifiable = [(g, a) for g, a in known if a is not None]
        others = len(games) - len(verifiable)
        if not games:
            self.games_column.addWidget(label("Scan your PC to see which of your games Soulbind can check.",
                                              "readyDetail", wrap=True))
        elif not verifiable:
            self.games_column.addWidget(label(
                "None of your scanned games have settings Game Grave can verify yet.", "readyDetail", wrap=True))
        for game, adapter in verifiable[:MAX_GAMES]:
            self.games_column.addWidget(self._game_row(game, adapter))
        if others and games:
            note = label(f"{others} other game{'s' if others != 1 else ''} found. Game Grave cannot verify "
                         f"{'its' if others == 1 else 'their'} settings yet, so Soulbind leaves "
                         f"{'it' if others == 1 else 'them'} alone.", "readyDetail", wrap=True)
            note.setContentsMargins(0, 8, 0, 0)
            self.games_column.addWidget(note)
        self.games_column.addStretch()
        self.copy_button.setEnabled(bool(self.profile))

    def _game_row(self, game, adapter):
        path = sb.config_file(adapter, self.roots)
        plan, text = None, None
        if path is not None:
            try:
                text, _bom = sb._decode(path.read_bytes())
                plan = sb.make_plan(adapter, text, self.profile)
            except (OSError, UnicodeError):
                path = None
        if path is None:
            score = sb.Score("No settings file yet", "muted",
                             "Start the game once so it creates its settings file, then check again.")
        else:
            score = sb.score_for(plan, len(self.profile))
        frame = QFrame()
        frame.setStyleSheet("QFrame{border-bottom:1px solid #222A30;}QLabel{border:0;background:transparent;}")
        line = row(spacing=10, margins=(0, 7, 0, 7))
        frame.setLayout(line)
        words = column(spacing=0)
        words.addWidget(label(game.name, "readyGameTitle"))
        detail = label(score.detail, "readyDetail", wrap=True)
        words.addWidget(detail)
        line.addLayout(words, 1)
        pill = QLabel(score.text)
        pill.setAlignment(Qt.AlignCenter)
        tone = TONES[score.tone]
        pill.setStyleSheet(f"font-size:12px;font-weight:700;color:{tone};border:1px solid {tone};"
                           "border-radius:10px;padding:2px 10px;background:transparent;")
        pill.setAccessibleName(f"{game.name}: {score.text}")
        line.addWidget(pill, 0, Qt.AlignVCenter)
        if plan is not None and plan.differing:
            apply_button = button("Apply", lambda _=False, a=adapter, p=path: self.apply(a, p), kind="primary",
                                  tip="Shows exactly what changes, saves a backup, then applies.")
            line.addWidget(apply_button, 0, Qt.AlignVCenter)
        previous = self._last_apply(adapter)
        if previous is not None:
            undo = button("Undo", lambda _=False, e=previous: self.undo(e), tip="Restore the file from before Soulbind.")
            line.addWidget(undo, 0, Qt.AlignVCenter)
        self.rows.append((game, adapter, score, frame))
        return frame

    @staticmethod
    def _last_apply(adapter):
        entries = [e for e in sb.ledger() if e.get("game") == adapter.title and not e.get("reverted")]
        return entries[-1] if entries else None

    def apply(self, adapter, path):
        window = self.window_owner
        try:
            text, _bom = sb._decode(path.read_bytes())
        except (OSError, UnicodeError) as problem:
            window.error("Soulbind", f"Could not read that settings file: {problem}")
            return
        plan = sb.make_plan(adapter, text, self.profile)
        if not plan.differing:
            self.refresh()
            return
        changes = "\n".join(f"  {c.label}: {c.old} to {c.new}" for c in plan.differing)
        if not window.confirm(
                f"Apply Soulbind to {adapter.title}",
                f"Soulbind will change this file:\n{path}\n\n{changes}\n\n"
                "Game Grave saves a backup of the file first, and you can undo this here. "
                "Close the game before you apply."):
            return
        try:
            done = sb.apply_profile(adapter, path, self.profile)
        except (OSError, ValueError, UnicodeError) as problem:
            window.error("Soulbind could not apply", str(problem))
            return
        if done is not None:
            window.status.setText(f"Soulbind applied to {adapter.title}. Backup saved.")
        self.refresh()

    def undo(self, entry):
        window = self.window_owner
        if not window.confirm("Undo Soulbind",
                              f"Restore {entry['game']}'s settings file from before Soulbind?\n{entry['path']}"):
            return
        try:
            sb.revert(entry["id"])
        except (OSError, ValueError) as problem:
            window.error("Soulbind could not undo", str(problem))
            return
        window.status.setText(f"Soulbind undone for {entry['game']}.")
        self.refresh()
