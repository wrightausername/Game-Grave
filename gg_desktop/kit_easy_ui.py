"""Resurrection Kit, the easy way: pick a game, see what a kit would hold, press Create. Restore is the same in reverse.

Qt layer only. What is offered lives in `kit_easy` (pure); the kit is made and restored by `resurrection_v2`. Nothing here
changes a file except by calling those, after the owner confirms, and every long job runs off the main thread with a
progress bar and a Cancel that removes what it wrote.
"""
from __future__ import annotations

from pathlib import Path
import threading

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QLineEdit, QProgressBar, QScrollArea,
                               QWidget)

import kit_easy
import resurrection_v2 as engine
from core import human_size
from gg_desktop.widgets import button, column, label, row

NOT_INCLUDED = ("Launcher accounts and licences are not part of a kit, so your launcher may sign in or re-verify the "
                "files the first time you start the restored game.")
ROLE_ORDER = ("Game", "Launcher", "Saves", "Configs", "LoadOrder", "Profiles", "Mods")


def _busy(window) -> bool:
    if getattr(window, "scanning", False) or getattr(window, "cleaning", False):
        window.info("Game Grave is busy", "Finish the current scan or backup first.")
        return True
    return False


def _game_running(window) -> bool:
    tracker = getattr(window, "_games_tracker", None)
    return bool(tracker is not None and getattr(getattr(tracker, "ledger", None), "active", None))


def kits_folder() -> Path:
    return Path.home() / "Documents" / "Game Grave Kits"


def _open_folder(path):
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


class _Base(QDialog):
    """A dialog with a progress strip. While a job runs it cannot be closed except through Cancel."""

    def __init__(self, window, title):
        super().__init__(window)
        self.window_ = window
        self.setWindowTitle(title)
        self.setMinimumWidth(640)
        self.cancel = threading.Event()
        self.working = False
        self.box = column(spacing=10, margins=(18, 16, 18, 14))
        self.setLayout(self.box)
        self.status = label("", "subtle", wrap=True)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(True)
        self.bar.hide()
        self.cancel_button = button("Cancel", self.stop)
        self.cancel_button.hide()

    def stop(self):
        self.cancel.set()
        self.cancel_button.setEnabled(False)
        self.status.setText("Cancelling. Anything written so far is being removed…")

    def reject(self):
        if self.working:
            self.stop()
            return
        super().reject()

    def run(self, work, done, *, title):
        """Run `work(progress)` off the main thread. `progress(percent, text)` updates the strip."""
        window = self.window_
        self.cancel.clear()
        self.working = True
        window.cleaning = True
        self.bar.setValue(0)
        self.bar.show()
        self.cancel_button.setEnabled(True)
        self.cancel_button.show()

        def finish(result):
            self.working = False
            window.cleaning = False
            self.bar.hide()
            self.cancel_button.hide()
            done(result, None)

        def update(percent, text):
            self.bar.setValue(max(0, min(100, int(percent))))
            self.status.setText(text)

        def failed(message):
            self.working = False
            window.cleaning = False
            self.bar.hide()
            self.cancel_button.hide()
            done(None, message)

        from gg_desktop.app import Job
        job = Job(work)
        window.workers[id(job)] = job

        def ok(result):
            window.workers.pop(id(job), None)
            finish(result)

        def bad(message):
            window.workers.pop(id(job), None)
            failed(message)
        job.signals.done.connect(ok)
        job.signals.failed.connect(bad)
        job.signals.progress.connect(update)
        window.pool.start(job)


def _percent(done, total):
    return 0 if not total else min(99, int(done * 100 / total))


# ====================================================================== create
class EasySetup(_Base):
    def __init__(self, window):
        super().__init__(window, "Set up a Resurrection Kit")
        self.plan = None
        self.checks = {}
        self.games = [g for g in window.inventory.games if getattr(g, "install_path", "")]
        self.box.addWidget(label("Set up a Resurrection Kit", "sectionTitle"))
        self.box.addWidget(label(
            "Pick a game. Game Grave finds its install, saves, load order and mod manager and saves them into one verified ZIP, so "
            "the game can be restored and played without downloading or setting it up again.", "subtle", wrap=True))
        top = row(spacing=8)
        top.addWidget(label("Game", "caption"))
        self.combo = QComboBox()
        self.combo.setMinimumWidth(360)
        self.combo.setAccessibleName("Game for the kit")
        for game in self.games:
            self.combo.addItem(f"{game.name}  ·  {game.launcher}")
        top.addWidget(self.combo, 1)
        self.box.addLayout(top)
        self.parts_box = column(spacing=6)
        holder = QWidget()
        holder.setLayout(self.parts_box)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setMinimumHeight(250)
        scroll.setWidget(holder)
        self.box.addWidget(scroll, 1)
        self.notes = label("", "caption", wrap=True)
        self.box.addWidget(self.notes)
        where = row(spacing=8)
        where.addWidget(label("Save the kit in", "caption"))
        self.folder = QLineEdit(str(kits_folder()))
        self.folder.setAccessibleName("Folder for the kit")
        self.folder.textChanged.connect(self.refresh_summary)
        where.addWidget(self.folder, 1)
        where.addWidget(button("Browse…", self.browse))
        self.box.addLayout(where)
        self.summary = label("", "subtle", wrap=True)
        self.box.addWidget(self.summary)
        self.box.addWidget(label("Close the game first so its files aren't changing. " + NOT_INCLUDED, "caption", wrap=True))
        self.box.addWidget(self.status)
        self.box.addWidget(self.bar)
        buttons = row(spacing=8)
        buttons.addStretch()
        buttons.addWidget(self.cancel_button)
        self.create_button = button("Create kit", self.create, kind="primary",
                                    tip="Writes one new ZIP and a small manifest file. Your game files are only read.")
        self.close_button = button("Close", self.reject)
        buttons.addWidget(self.create_button)
        buttons.addWidget(self.close_button)
        self.box.addLayout(buttons)
        self.combo.currentIndexChanged.connect(self.load_plan)
        self.create_button.setEnabled(False)
        if not self.games:
            self.status.setText("Run Scan PC first so Game Grave knows which games are installed.")
        else:
            self.load_plan()

    # ---- the plan
    def clear_parts(self):
        while self.parts_box.count():
            item = self.parts_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.checks = {}

    def load_plan(self):
        if self.working or not self.games:
            return
        game = self.games[self.combo.currentIndex()]
        window = self.window_
        self.clear_parts()
        self.plan = None
        self.create_button.setEnabled(False)
        self.status.setText("Looking at this game's install, saves and mods…")
        self.summary.setText("")
        self.notes.setText("")
        token = self.token = object()

        def work(_progress):
            from gg_desktop import dna_actions
            from kit_discovery import discover_setup
            from manager_profiles import inspect_manager_profiles
            inventory = window.inventory
            discovery = None
            try:
                report = inspect_manager_profiles(inventory.mods, inventory.steam, inventory.other)
                discovery = discover_setup(game, mods=list(inventory.mods), saves=list(inventory.saves), manager_report=report)
            except (ValueError, OSError):
                discovery = None
            return kit_easy.build_plan(game, saves=list(inventory.saves), links=dna_actions.links_for(window.settings, game.key),
                                       discovery=discovery)

        def done(plan, error):
            if token is not self.token:
                return
            if error:
                self.status.setText("Could not read this game: " + error[:160])
                return
            self.plan = plan
            self.show_plan()

        from gg_desktop.app import Job
        job = Job(work)
        window.workers[id(job)] = job

        def ok(result):
            window.workers.pop(id(job), None)
            done(result, None)

        def bad(message):
            window.workers.pop(id(job), None)
            done(None, message)
        job.signals.done.connect(ok)
        job.signals.failed.connect(bad)
        window.pool.start(job)

    def show_plan(self):
        self.status.setText("")
        for part in sorted(self.plan.parts, key=lambda p: ROLE_ORDER.index(p.role) if p.role in ROLE_ORDER else 99):
            box = QCheckBox(f"{part.title}   ·   {human_size(part.bytes)}, {part.files:,} file{'s' if part.files != 1 else ''}")
            box.setChecked(part.on and not part.problem)
            box.setEnabled(not part.problem)
            box.setAccessibleName(part.title)
            box.setToolTip(part.why)
            box.toggled.connect(lambda state, p=part: self.toggled(p, state))
            self.parts_box.addWidget(box)
            self.parts_box.addWidget(label(part.problem or part.why, "caption", wrap=True))
            self.checks[part.role] = box
        self.notes.setText(" ".join(self.plan.notes))
        self.refresh_summary()

    def toggled(self, part, state):
        part.on = bool(state)
        self.refresh_summary()

    def browse(self):
        chosen = QFileDialog.getExistingDirectory(self, "Choose where to save the kit", self.folder.text())
        if chosen:
            self.folder.setText(chosen)

    def destination(self):
        folder = Path(self.folder.text().strip() or str(kits_folder()))
        return kit_easy.default_destination(self.plan.game, folder)

    def refresh_summary(self):
        if self.plan is None:
            return
        folder = Path(self.folder.text().strip() or str(kits_folder()))
        state = kit_easy.readiness(self.plan, folder)
        free = state["free"]
        text = (f"The kit will hold about {human_size(self.plan.total_bytes)} in {self.plan.total_files:,} files. "
                + (f"Free space there: {human_size(free)}." if free is not None else "Free space there is unknown."))
        if not state["ok"]:
            text += "  " + state["why"]
        self.summary.setText(text)
        self.create_button.setEnabled(state["ok"] and not self.working)

    # ---- create
    def create(self):
        if self.plan is None or self.working or _busy(self.window_):
            return
        sources, origins, manager = kit_easy.to_sources(self.plan)
        destination = self.destination()
        chosen = ", ".join(p.title for p in self.plan.chosen())
        warning = "\n\nA game looks like it is running. Close it first or the kit may stop." if _game_running(self.window_) else ""
        if not self.window_.confirm(
                "Create this Resurrection Kit?",
                f"Game: {self.plan.game}\nParts: {chosen}\nSize: about {human_size(self.plan.total_bytes)}\n"
                f"New ZIP: {destination}\n\nYour game, save and mod files are only read. Nothing existing is overwritten."
                + warning):
            return
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.status.setText("Could not create the folder: " + str(exc)[:160])
            return
        game_name = self.plan.game
        for control in (self.create_button, self.combo, self.folder):
            control.setEnabled(False)
        self.close_button.setEnabled(False)
        cancel = self.cancel

        def work(progress):
            def report(phase, done, total, note):
                text = {"Copying": f"Copying {note}", "Reading folders": "Reading folders…",
                        "Checking the ZIP": "Checking the finished ZIP…", "Fingerprinting": "Fingerprinting the ZIP…"}.get(phase, phase)
                progress(_percent(done, total) if phase == "Copying" else (99 if phase != "Reading folders" else 0), text)
            return engine.create_complete_kit(game_name, sources, destination, manager, origins=origins,
                                              progress=report, cancel=cancel.is_set)

        def done(result, error):
            self.close_button.setEnabled(True)
            self.close_button.setText("Close")
            if error:
                for control in (self.create_button, self.combo, self.folder):
                    control.setEnabled(True)
                self.status.setText(("Cancelled. Nothing was kept." if "cancel" in error.lower() else "The kit was not made: " + error[:220]))
                self.refresh_summary()
                return
            self.status.setText(f"Kit saved and checked: {result['archive']}\n{result['files']:,} files, {human_size(result['bytes'])}. "
                                f"Parts: {', '.join(result['roles'])}.")
            self.create_button.hide()
            self.box.addWidget(button("Open folder", lambda: _open_folder(Path(result["archive"]).parent)))
            try:
                from core import log_event
                log_event("kit_created", f"Resurrection Kit for {game_name}: {result['files']} files, {human_size(result['bytes'])}")
            except Exception:
                pass
        self.run(work, done, title="Kit")


def open_easy_setup(window):
    if _busy(window):
        return
    dialog = EasySetup(window)
    window._kit_easy_dialog = dialog
    dialog.exec()


# ====================================================================== restore
class EasyRestore(_Base):
    def __init__(self, window):
        super().__init__(window, "Restore a game from a kit")
        self.manifest = None
        self.plan = None
        self.box.addWidget(label("Restore a game from a kit", "sectionTitle"))
        self.box.addWidget(label(
            "Choose a kit and the library folder the game should go into. The install is restored as a new folder there, and saves, "
            "settings and load-order files go back to where they came from only if nothing is there yet. Nothing is overwritten.",
            "subtle", wrap=True))
        pick = row(spacing=8)
        self.kit_label = label("No kit chosen", "caption", wrap=True)
        pick.addWidget(self.kit_label, 1)
        pick.addWidget(button("Choose kit…", self.choose_kit))
        self.box.addLayout(pick)
        lib = row(spacing=8)
        lib.addWidget(label("Library folder", "caption"))
        self.library = QComboBox()
        self.library.setEditable(True)
        self.library.setMinimumWidth(380)
        self.library.setAccessibleName("Library folder to restore into")
        seen = []
        for game in window.inventory.games:
            parent = str(Path(game.install_path).parent) if getattr(game, "install_path", "") else ""
            if parent and parent not in seen:
                seen.append(parent)
        for item in seen[:12]:
            self.library.addItem(item)
        self.library.currentTextChanged.connect(self.preview)
        lib.addWidget(self.library, 1)
        lib.addWidget(button("Browse…", self.browse))
        self.box.addLayout(lib)
        self.preview_label = label("", "subtle", wrap=True)
        self.box.addWidget(self.preview_label)
        self.box.addWidget(label("Games that need a launcher may still sign in or re-verify first. " + NOT_INCLUDED, "caption", wrap=True))
        self.box.addWidget(self.status)
        self.box.addWidget(self.bar)
        buttons = row(spacing=8)
        buttons.addStretch()
        buttons.addWidget(self.cancel_button)
        self.go = button("Restore", self.restore, kind="primary", tip="Checks the whole kit first, then restores. Never overwrites.")
        self.go.setEnabled(False)
        self.close_button = button("Close", self.reject)
        buttons.addWidget(self.go)
        buttons.addWidget(self.close_button)
        self.box.addLayout(buttons)

    def choose_kit(self):
        start = kits_folder() if kits_folder().exists() else Path.home()
        chosen, _ = QFileDialog.getOpenFileName(self, "Choose a Resurrection Kit", str(start),
                                                "Kit manifest (*.ggkit.json);;All files (*)")
        if chosen:
            self.manifest = Path(chosen)
            self.kit_label.setText(str(self.manifest))
            self.preview()

    def browse(self):
        chosen = QFileDialog.getExistingDirectory(self, "Choose the library folder to restore into", self.library.currentText())
        if chosen:
            self.library.setEditText(chosen)

    def preview(self, *_):
        self.plan = None
        self.go.setEnabled(False)
        text = self.library.currentText().strip()
        if self.manifest is None or not text:
            self.preview_label.setText("")
            return
        try:
            self.plan = engine.plan_installation(self.manifest, Path(text))
        except (ValueError, OSError) as exc:
            self.preview_label.setText(str(exc)[:240])
            return
        names = {"new_folder": "new folder", "place": "back to its original place", "place_files": "into place, never over an existing file",
                 "review": "review folder"}
        lines = [f"{self.plan['game']}: {self.plan['files']:,} files, about {human_size(self.plan['bytes'])}."]
        for part in self.plan["parts"]:
            lines.append(f"• {part['role']}: {names.get(part['mode'], part['mode'])}  →  {part['destination']}"
                         + (f"   ({part['note']})" if part.get("note") else ""))
        if not self.plan["includes_install"]:
            lines.append("This kit does not hold the game install, only the parts listed.")
        lines.extend(self.plan["blocked"])
        self.preview_label.setText("\n".join(lines))
        self.go.setEnabled(not self.plan["blocked"])

    def restore(self):
        if self.plan is None or self.working or _busy(self.window_):
            return
        if not self.window_.confirm("Restore this kit?",
                                    f"{self.plan['game']}\n\n" + self.preview_label.text()
                                    + "\n\nThe whole kit is checked first. Nothing is overwritten, and a cancel removes what was written."):
            return
        manifest, library = self.manifest, Path(self.library.currentText().strip())
        self.go.setEnabled(False)
        self.close_button.setEnabled(False)
        cancel = self.cancel

        def work(progress):
            progress(0, "Checking the whole kit before anything is written…")

            def report(phase, done, total, note):
                progress(_percent(done, total) if phase == "Restoring" else 99, f"Restoring {note}" if phase == "Restoring" else phase)
            return engine.restore_installation(manifest, library, approved=True, progress=report, cancel=cancel.is_set)

        def done(result, error):
            self.close_button.setEnabled(True)
            if error:
                self.status.setText("Cancelled. Nothing was kept." if "cancel" in error.lower() else "Nothing was restored: " + error[:220])
                self.preview()
                return
            skipped = f" Left alone because they already existed: {', '.join(result['skipped_existing'][:6])}." if result["skipped_existing"] else ""
            review = f" Parts for you to place yourself are in {result['review_folder']}." if result["review_folder"] else ""
            self.status.setText(f"Restored {result['files']:,} files.{skipped}{review} {result['note']}")
            try:
                from core import log_event
                log_event("kit_restored", f"Resurrection Kit restored for {result['game']}: {result['files']} files")
            except Exception:
                pass
            if result["game_folder"]:
                self.box.addWidget(button("Open game folder", lambda: _open_folder(result["game_folder"])))
        self.run(work, done, title="Restore")


def open_easy_restore(window):
    if _busy(window):
        return
    dialog = EasyRestore(window)
    window._kit_restore_dialog = dialog
    dialog.exec()
