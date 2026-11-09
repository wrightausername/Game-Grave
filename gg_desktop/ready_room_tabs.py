"""Ready Room sub-tabs: News (the approved Ready Room, unchanged), Soulbind and Squad. Owner request, 2026-11-08.

News is the existing page. The two new views are added below the title and shown in its place when picked, so the
News layout itself is not rebuilt. Logic lives in `soulbind` and `squad_sync` (no Qt).
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QListWidget, QPlainTextEdit, QPushButton,
                               QWidget)

from core import config_dir
from gg_desktop import soulbind, squad_sync, winpc
from gg_desktop.widgets import button, column, label, row

TABS = (("news", "News"), ("soulbind", "Soulbind"), ("squad", "Squad"))
TAB_STYLE = ("QPushButton{background:#11181f;color:#cfd5dc;border:1px solid #2b3742;border-radius:6px;"
             "padding:5px 16px;font-size:14px;font-weight:600;}"
             "QPushButton:hover{border-color:#718393;}"
             "QPushButton:checked{background:#8a1022;color:#ffffff;border-color:#ff284a;}"
             "QPushButton:focus{border:2px solid #4DD8E2;}")
FIELD_STYLE = ("QListWidget,QPlainTextEdit,QComboBox{background:rgba(5,9,12,215);color:#e8eef5;border:1px solid #2b3742;"
               "border-radius:5px;font-size:13px;} QListWidget::item{padding:5px;} "
               "QListWidget::item:selected{background:#2a0f17;color:#ffffff;} QCheckBox{color:#e8eef5;font-size:13px;"
               "spacing:8px;} QComboBox QAbstractItemView{background:#0a1118;color:#e8eef5;}")


def _text(value, role="readyDetail"):
    item = label(value, role, wrap=True)
    item.setMinimumWidth(0)
    return item


def _panel(title, subtitle, glyph):
    from gg_desktop.ready_room import ReadyPanel
    panel = ReadyPanel(title, subtitle, glyph)
    panel.body_layout.setSpacing(8)
    panel.setMinimumHeight(430)
    return panel


def install(page, window):
    """Add the sub-tab buttons to Ready Room's title row and build the two hidden views."""
    page.ready_tabs = {}
    holder = QWidget()
    tabs_row = row(spacing=6, margins=(0, 14, 14, 0))
    holder.setLayout(tabs_row)
    for key, title in TABS:
        control = QPushButton(title)
        control.setCheckable(True)
        control.setStyleSheet(TAB_STYLE)
        control.setAccessibleName("Ready Room " + title)
        control.clicked.connect(lambda _=False, k=key: show_tab(page, k))
        page.ready_tabs[key] = control
        tabs_row.addWidget(control)
    page.hero_row.addWidget(holder)
    page.news_widgets = [w for w in (page.metrics, page.news_bar, page.patches, page.games, page.mod_panel,
                                     page.save_panel, page.health_panel) if w is not None]
    page.soulbind_view = SoulbindView(window)
    page.squad_view = SquadView(window)
    for view in (page.soulbind_view, page.squad_view):
        view.hide()
        page.content.addWidget(view, 10)
    page.ready_tab = "news"
    page.ready_tabs["news"].setChecked(True)


def show_tab(page, key):
    page.ready_tab = key
    for name, control in page.ready_tabs.items():
        control.setChecked(name == key)
    for widget in page.news_widgets:
        widget.setVisible(key == "news")
    page.soulbind_view.setVisible(key == "soulbind")
    page.squad_view.setVisible(key == "squad")
    if key == "soulbind":
        page.soulbind_view.refresh()
    elif key == "squad":
        page.squad_view.refresh()


# ------------------------------------------------------------------ Soulbind
class SoulbindView(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window_ = window
        self.setStyleSheet(FIELD_STYLE)
        self.profile_path = Path(config_dir()) / soulbind.PROFILE_NAME
        self.backup_root = Path(config_dir()) / soulbind.BACKUP_FOLDER
        self.prefs = soulbind.load_profile(self.profile_path)
        self.targets = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(12)

        mine = _panel("Your Soulbind", "Set your comfort settings once. Every supported game follows them.", "sparkles")
        body = mine.body_layout
        body.addWidget(label("Applied to Unreal Engine games", "readyGameTitle"))
        self.checks = {}
        for key, title, _values in soulbind.ENGINE_PREFS:
            self.checks[key] = QCheckBox(title)
            body.addWidget(self.checks[key])
        body.addSpacing(6)
        body.addWidget(label("Kept in your Soulbind (per-game support is not built yet)", "readyGameTitle"))
        for key, title in soulbind.GAME_PREFS:
            self.checks[key] = QCheckBox(title)
            body.addWidget(self.checks[key])
        for key, check in self.checks.items():
            check.setChecked(bool(self.prefs.get(key)))
            check.toggled.connect(self._changed)
        actions = row(spacing=8)
        self.save_button = button("Save Soulbind", self.save, kind="readyPrimary")
        self.export_button = button("Share…", self.export, kind="readyButton", tip="Save your Soulbind as a small file")
        self.import_button = button("Import…", self.import_file, kind="readyButton")
        for control in (self.save_button, self.export_button, self.import_button):
            actions.addWidget(control)
        actions.addStretch()
        body.addStretch()
        body.addLayout(actions)
        self.mine_note = _text("")
        body.addWidget(self.mine_note)
        layout.addWidget(mine, 5)

        games = _panel("Soulbind Games", "Unreal Engine games with saved settings on this PC.", "gamepad")
        gbody = games.body_layout
        self.list = QListWidget()
        self.list.setAccessibleName("Games Soulbind can change")
        self.list.setMinimumHeight(190)
        gbody.addWidget(self.list, 1)
        self.score = _text("")
        gbody.addWidget(self.score)
        gactions = row(spacing=8)
        self.apply_button = button("Soulbind This Game", self.apply_selected, kind="readyPrimary")
        self.apply_all_button = button("Soulbind All", self.apply_all, kind="readyButton")
        self.restore_button = button("Restore Original", self.restore_selected, kind="readyButton")
        for control in (self.apply_button, self.apply_all_button, self.restore_button):
            gactions.addWidget(control)
        gactions.addStretch()
        gbody.addLayout(gactions)
        gbody.addWidget(_text("The game's original Engine.ini is kept by Game Grave, and Restore Original puts it back. "
                              "Use Soulbind on single-player games: online games with anti-cheat may ignore or reject "
                              "edited settings files.", "readyWhen"))
        self.games_note = _text("")
        gbody.addWidget(self.games_note)
        self.list.currentRowChanged.connect(lambda _i: self._buttons())
        layout.addWidget(games, 6)

    def _changed(self):
        self.prefs = {k: c.isChecked() for k, c in self.checks.items()}
        self.mine_note.setText("Not saved yet.")
        self._score()

    def _score(self):
        applied, chosen = soulbind.score(self.prefs)
        self.score.setText(f"Soulbind score for these games: {applied} of {chosen} of your preferences can be applied."
                           if chosen else "Pick at least one preference.")

    def refresh(self):
        self.targets = soulbind.find_targets()
        self.list.clear()
        for target in self.targets:
            bound = soulbind.has_backup(target, self.backup_root)
            self.list.addItem(f"{target.name}  ·  {'Soulbound' if bound else 'Not Soulbound yet'}")
        if self.targets:
            self.list.setCurrentRow(0)
        self.games_note.setText("" if self.targets else
                                "No Unreal Engine game settings were found yet. Launch a game once so it saves its "
                                "settings, then come back.")
        self._score()
        self._buttons()

    def _current(self):
        index = self.list.currentRow()
        return self.targets[index] if 0 <= index < len(self.targets) else None

    def _buttons(self):
        target = self._current()
        self.apply_button.setEnabled(target is not None)
        self.apply_all_button.setEnabled(bool(self.targets))
        self.restore_button.setEnabled(bool(target and soulbind.has_backup(target, self.backup_root)))

    def save(self):
        soulbind.save_profile(self.profile_path, self.prefs)
        self.mine_note.setText("Saved.")

    def export(self):
        path, _f = QFileDialog.getSaveFileName(self, "Share your Soulbind", str(Path.home() / "my.soulbind.json"),
                                               "Soulbind (*.json)")
        if path:
            soulbind.save_profile(path, self.prefs)
            self.mine_note.setText("Saved a copy you can share. It holds only these switches.")

    def import_file(self):
        path, _f = QFileDialog.getOpenFileName(self, "Import a Soulbind", str(Path.home()), "Soulbind (*.json)")
        if not path:
            return
        try:
            prefs = soulbind.import_profile(path)
        except (OSError, ValueError) as exc:
            self.mine_note.setText(str(exc))
            return
        for key, check in self.checks.items():
            check.setChecked(bool(prefs.get(key)))
        self.prefs = prefs
        self.mine_note.setText("Imported. Press Save Soulbind to keep it.")

    def _apply(self, targets):
        switches = soulbind.wanted_switches(self.prefs)
        if not switches:
            self.games_note.setText("Turn on at least one setting under 'Applied to Unreal Engine games'.")
            return
        names = "\n".join(t.name for t in targets)
        lines = "\n".join(f"{k}={v}" for k, v in switches.items())
        if not self.window_.confirm("Soulbind", f"Write these settings into Engine.ini for:\n{names}\n\n{lines}\n\n"
                                                "Game Grave keeps each original so Restore Original can put it back. "
                                                "Close the game first so it does not overwrite the file."):
            return
        done, failed = [], []
        for target in targets:
            try:
                soulbind.apply(target, self.prefs, self.backup_root)
                done.append(target.name)
            except (OSError, ValueError) as exc:
                failed.append(f"{target.name}: {exc}")
        soulbind.save_profile(self.profile_path, self.prefs)
        if done:
            winpc.activity("Soulbind", "Applied to " + ", ".join(done) + ". " + ", ".join(switches))
        self.refresh()
        self.games_note.setText((f"Soulbound {len(done)} game{'s' if len(done) != 1 else ''}. " if done else "") +
                                (" Not changed: " + "; ".join(failed) if failed else ""))

    def apply_selected(self):
        target = self._current()
        if target:
            self._apply([target])

    def apply_all(self):
        if self.targets:
            self._apply(list(self.targets))

    def restore_selected(self):
        target = self._current()
        if not target:
            return
        if not self.window_.confirm("Restore original settings", f"Put back the Engine.ini {target.name} had before "
                                                                 "Soulbind?"):
            return
        try:
            message = soulbind.restore(target, self.backup_root)
        except (OSError, ValueError) as exc:
            self.games_note.setText(str(exc))
            return
        winpc.activity("Soulbind", f"Restored {target.name}. {message}")
        self.refresh()
        self.games_note.setText(message)


# ------------------------------------------------------------------ Squad Sync
class SquadView(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window_ = window
        self.setStyleSheet(FIELD_STYLE)
        self.profiles = []
        self.squad = None
        self.last_file = ""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(12)

        share = _panel("Share Squad Setup", "Give your friends your exact mods and versions in one code.", "sync")
        body = share.body_layout
        body.addWidget(label("Your mod manager profile", "readyGameTitle"))
        self.share_box = QComboBox()
        self.share_box.setAccessibleName("Profile to share")
        body.addWidget(self.share_box)
        actions = row(spacing=8)
        self.code_button = button("Make Squad Code", self.make_code, kind="readyPrimary")
        self.copy_button = button("Copy", self.copy_code, kind="readyButton")
        self.file_button = button("Save Squad File…", self.save_file, kind="readyButton",
                                  tip="Also carries the profile's BepInEx config files")
        for control in (self.code_button, self.copy_button, self.file_button):
            actions.addWidget(control)
        actions.addStretch()
        body.addLayout(actions)
        self.code = QPlainTextEdit()
        self.code.setReadOnly(True)
        self.code.setAccessibleName("Your Squad Code")
        self.code.setPlaceholderText("Your Squad Code appears here. Send it in Discord or a text.")
        self.code.setMaximumHeight(110)
        body.addWidget(self.code)
        self.share_note = _text("Works with r2modman and the Thunderstore Mod Manager. The code holds only mod names and "
                                "versions: no files, no paths, nothing about you.")
        body.addWidget(self.share_note)
        body.addStretch()
        layout.addWidget(share, 5)

        join = _panel("Join a Squad", "Paste a friend's code, see the differences, and match in one press.", "download")
        jbody = join.body_layout
        self.paste = QPlainTextEdit()
        self.paste.setAccessibleName("Friend's Squad Code")
        self.paste.setPlaceholderText("Paste a Squad Code (GGSQ1...)")
        self.paste.setMaximumHeight(80)
        jbody.addWidget(self.paste)
        jrow = row(spacing=8)
        self.open_button = button("Open Squad File…", self.open_file, kind="readyButton")
        self.mine_box = QComboBox()
        self.mine_box.setAccessibleName("Your profile to compare")
        self.compare_button = button("Compare", self.compare, kind="readyButton")
        jrow.addWidget(self.open_button)
        jrow.addWidget(self.mine_box, 1)
        jrow.addWidget(self.compare_button)
        jbody.addLayout(jrow)
        self.results = QListWidget()
        self.results.setAccessibleName("Squad differences")
        self.results.setMinimumHeight(140)
        jbody.addWidget(self.results, 1)
        self.result_line = _text("")
        jbody.addWidget(self.result_line)
        mrow = row(spacing=8)
        self.match_button = button("Match Squad", self.match, kind="readyPrimary",
                                   tip="Builds a new profile with the squad's exact mods. Yours is not changed.")
        self.show_button = button("Show File", self.show_file, kind="readyButton")
        self.match_button.setEnabled(False)
        self.show_button.setEnabled(False)
        mrow.addWidget(self.match_button)
        mrow.addWidget(self.show_button)
        mrow.addStretch()
        jbody.addLayout(mrow)
        self.steps = _text("", "readyWhen")
        jbody.addWidget(self.steps)
        layout.addWidget(join, 6)

    def refresh(self):
        self.profiles = squad_sync.find_profiles()
        for box in (self.share_box, self.mine_box):
            box.clear()
            for profile in self.profiles:
                box.addItem(profile.label)
            if not self.profiles:
                box.addItem("No r2modman or Thunderstore Mod Manager profiles found")
        has = bool(self.profiles)
        for control in (self.code_button, self.copy_button, self.file_button):
            control.setEnabled(has)

    def _profile(self, box):
        index = box.currentIndex()
        return self.profiles[index] if self.profiles and 0 <= index < len(self.profiles) else None

    def make_code(self):
        profile = self._profile(self.share_box)
        if not profile:
            return
        try:
            mods = squad_sync.read_profile(profile)
            code = squad_sync.make_code(profile.game, profile.name, mods)
        except (OSError, ValueError) as exc:
            self.share_note.setText(str(exc))
            return
        self.code.setPlainText(code)
        count = len([m for m in mods if m.enabled])
        self.share_note.setText(f"Squad Code for {count} mods made. Copy it and send it to your squad.")
        winpc.activity("Squad Sync", f"Made a Squad Code for {profile.label} ({count} mods).")

    def copy_code(self):
        if not self.code.toPlainText():
            self.make_code()
        if self.code.toPlainText():
            QGuiApplication.clipboard().setText(self.code.toPlainText())
            self.share_note.setText("Copied.")

    def save_file(self):
        profile = self._profile(self.share_box)
        if not profile:
            return
        name = squad_sync.safe_name(f"Squad - {profile.name}") + ".r2z"
        path, _f = QFileDialog.getSaveFileName(self, "Save the squad file", str(Path.home() / "Downloads" / name),
                                               "Mod manager profile (*.r2z)")
        if not path:
            return
        try:
            mods = [m for m in squad_sync.read_profile(profile) if m.enabled]
            configs = squad_sync.collect_configs(profile.folder)
            squad_sync.write_squad_file(path, f"Squad - {profile.name}", mods, configs)
        except (OSError, ValueError) as exc:
            self.share_note.setText(str(exc))
            return
        self.share_note.setText(f"Saved with {len(mods)} mods and {len(configs)} config files. Send the file to your squad.")

    def open_file(self):
        path, _f = QFileDialog.getOpenFileName(self, "Open a squad file", str(Path.home() / "Downloads"),
                                               "Mod manager profile (*.r2z)")
        if not path:
            return
        try:
            self.squad = squad_sync.read_squad_file(path)
        except (OSError, ValueError, Exception) as exc:  # a damaged zip raises BadZipFile
            self.result_line.setText(str(exc))
            return
        self.paste.setPlainText("")
        self.last_file = path
        self.compare()

    def compare(self):
        text = self.paste.toPlainText().strip()
        if text:
            try:
                self.squad = squad_sync.read_code(text)
                self.last_file = ""
            except ValueError as exc:
                self.result_line.setText(str(exc))
                self.match_button.setEnabled(False)
                return
        if self.squad is None:
            self.result_line.setText("Paste a Squad Code or open a squad file first.")
            return
        if self.squad.game:
            same = [i for i, p in enumerate(self.profiles) if p.game.casefold() == self.squad.game.casefold()]
            if same and self._profile(self.mine_box) and self._profile(self.mine_box).game.casefold() != self.squad.game.casefold():
                self.mine_box.setCurrentIndex(same[0])
        mine_profile = self._profile(self.mine_box)
        try:
            mine = squad_sync.read_profile(mine_profile) if mine_profile else []
        except OSError:
            mine = []
        result = squad_sync.compare(self.squad.mods, mine)
        self.results.clear()
        for mod in result.missing:
            self.results.addItem(f"Missing  ·  {mod.name}  {mod.version}")
        for mod, have in result.wrong_version:
            self.results.addItem(f"Wrong version  ·  {mod.name}  you have {have}, squad uses {mod.version}")
        for mod in result.turned_off:
            self.results.addItem(f"Turned off  ·  {mod.name}  {mod.version}")
        for mod in result.extra:
            self.results.addItem(f"Extra  ·  {mod.name}  (not in the squad)")
        for mod in result.matching:
            self.results.addItem(f"Match  ·  {mod.name}  {mod.version}")
        who = self.squad.label or "your friend"
        compared = f"Compared with {mine_profile.label}. " if mine_profile else "You have no profile to compare. "
        self.result_line.setText(compared + result.summary() + f" Squad: {who}, {len(self.squad.mods)} mods.")
        self.match_button.setEnabled(True)

    def match(self):
        if self.squad is None:
            return
        label_text = squad_sync.safe_name(f"Squad - {self.squad.label or 'Friend'}")
        downloads = Path.home() / "Downloads"
        path = downloads / f"{label_text}.r2z"
        number = 2
        while path.exists():
            path = downloads / f"{label_text} ({number}).r2z"
            number += 1
        try:
            configs = {}
            if self.last_file:
                import zipfile
                with zipfile.ZipFile(self.last_file) as archive:
                    configs = {n: archive.read(n) for n in archive.namelist() if n.startswith("BepInEx/config/")}
            squad_sync.write_squad_file(path, label_text, self.squad.mods, configs)
        except (OSError, ValueError) as exc:
            self.result_line.setText("The squad profile was not written: " + str(exc))
            return
        self.match_path = str(path)
        self.show_button.setEnabled(True)
        manager = self._profile(self.mine_box).manager if self._profile(self.mine_box) else "r2modman"
        self.steps.setText(f"Saved {path.name} in Downloads with all {len(self.squad.mods)} mods at the squad's exact "
                           "versions.\n" + "\n".join(f"{n}. {s}" for n, s in enumerate(squad_sync.import_steps(manager), 1))
                           + "\nAfter it downloads, Mod Shield in More Tools can check the new profile.")
        winpc.activity("Squad Sync", f"Built a squad profile file with {len(self.squad.mods)} mods: {path}")

    def show_file(self):
        if getattr(self, "match_path", ""):
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.match_path).parent)))
