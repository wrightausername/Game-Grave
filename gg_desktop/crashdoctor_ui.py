"""Crash Doctor window (from Mod Bisect, Fix Kit and the assistant): pick the game, how its mods are switched (Mod
Organizer 2, Vortex or a plain folder), how to start it and how long it must run to count as fine; press Start and
Game Grave runs every Bisect test itself. Stop, or the end of the search, puts every mod back."""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QGridLayout

from core import log_event
from gg_desktop import crashdoctor_core as cd
from gg_desktop.tools_shell import ToolDialog
from gg_desktop.widgets import button, label

ACTIVE_KEY = "crash_doctor_active"     # holding folders in use, so a closed app can put mods back next start
STEPS = ("Pick the game", "Start", "Tests run by themselves", "Answer and everything put back")


def _mo2_instance(window, game):
    """(instance, profile folder) of the Mod Organizer 2 setup for this game, or (None, None)."""
    try:
        from manager_profiles import _mo2_roots
        from gg_desktop import mymods_core
    except Exception:
        return None, None
    for ini in _mo2_roots(getattr(window.inventory, "mods", []) or []):
        try:
            inst = mymods_core.read_instance(ini)
        except Exception:
            continue
        same_path = inst.game_path and game.install_path and Path(inst.game_path) == Path(game.install_path)
        same_name = inst.game and inst.game.casefold() in game.name.casefold()
        if same_path or same_name:
            return inst, inst.profiles_dir / (inst.selected or (inst.profiles[0] if inst.profiles else ""))
    return None, None


class DoctorDialog(ToolDialog):
    def __init__(self, window, game=None):
        super().__init__(window, "crash_doctor", "Crash Doctor", "warning", width=660, step_names=STEPS,
                         summary="Finds the mod that crashes your game by running the Mod Bisect tests for you: it "
                                 "switches mods, starts the game, watches it, and puts everything back at the end.",
                         color="#ff5a73")
        self.window_ = window
        self.games = sorted((g for g in window.inventory.games if getattr(g, "install_path", "")),
                            key=lambda g: g.name.casefold())
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        self.game_box, self.method_box, self.launch_box, self.fine_box = QComboBox(), QComboBox(), QComboBox(), QComboBox()
        for g in self.games:
            self.game_box.addItem(g.name)
        if game is not None:
            at = next((i for i, g in enumerate(self.games) if g.name == game.name), -1)
            if at >= 0:
                self.game_box.setCurrentIndex(at)
        for seconds in cd.FINE_CHOICES:
            self.fine_box.addItem(f"{seconds // 60} minute{'s' if seconds >= 120 else ''}", seconds)
        self.fine_box.setCurrentIndex(1)
        rows = (("Game", self.game_box), ("Switch mods with", self.method_box), ("Start the game with", self.launch_box),
                ("Counts as fine after", self.fine_box))
        for r, (words, control) in enumerate(rows):
            control.setAccessibleName(words)
            grid.addWidget(label(words, "caption"), r, 0)
            grid.addWidget(control, r, 1)
        self.body.addLayout(grid)
        self.folder_button = button("Choose the mod folder…", self.choose_folder, kind="actionLink")
        self.body.addWidget(self.folder_button)
        self.sometimes = QCheckBox("It only crashes sometimes (each test runs up to 3 times)")
        self.body.addWidget(self.sometimes)
        self.note = label("", "caption", wrap=True)
        self.body.addWidget(self.note)
        self.start_button = button("Start", self.start, kind="primary")
        self.stop_button = button("Stop and put everything back", self.stop)
        self.add_actions(self.stop_button, self.start_button)
        self.folder = ""
        self.switcher = self.flow = self.proc = None
        self.timer = QTimer(self, interval=2000)
        self.timer.timeout.connect(self.tick)
        self.phase = "idle"
        self.game_box.currentIndexChanged.connect(lambda _i: self.fill())
        self.method_box.currentIndexChanged.connect(lambda _i: self.fill_launch())
        self.fill()

    # ------------------------------------------------------------ choices
    def game(self):
        i = self.game_box.currentIndex()
        return self.games[i] if 0 <= i < len(self.games) else None

    def fill(self):
        game = self.game()
        self.method_box.blockSignals(True)
        self.method_box.clear()
        if game is not None:
            self.mo2, self.mo2_profile = _mo2_instance(self.window_, game)
            if self.mo2 is not None:
                self.method_box.addItem("Mod Organizer 2 (a test copy of your profile)", "Mod Organizer 2")
            if cd.vortex_manifests(game.install_path):
                self.method_box.addItem("Vortex (its deployment list)", "Vortex")
            self.method_box.addItem("A folder of mods (no mod manager)", "Folder")
        self.method_box.blockSignals(False)
        self.fill_launch()

    def method(self):
        return self.method_box.currentData() or "Folder"

    def fill_launch(self):
        game = self.game()
        self.launch_box.clear()
        if game is None:
            return
        if self.method() == "Mod Organizer 2" and self.mo2 is not None:
            try:
                text = Path(self.mo2.ini).read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            for title, binary in cd.mo2_executables(text):
                self.launch_box.addItem(f"{title} (through Mod Organizer 2)", ("mo2", title))
        for words, command in cd.launch_choices(game):
            self.launch_box.addItem(words, ("direct", command))
        self.folder_button.setVisible(self.method() == "Folder")
        self.note.setText({"Mod Organizer 2": "Mod Organizer 2 must be closed while it runs; Game Grave starts it for each test.",
                           "Vortex": "Close Vortex first, and don't deploy while it runs.",
                           "Folder": ("Mod folder: " + self.folder) if self.folder else
                           "Choose the folder that holds this game's mods. Each file or folder in it counts as one mod."}[
            self.method()])

    def choose_folder(self):
        game = self.game()
        start = game.install_path if game else ""
        folder = QFileDialog.getExistingDirectory(self, "The folder that holds the mods", start)
        if folder:
            self.folder = folder
            self.fill_launch()

    # ------------------------------------------------------------ start / stop
    def build_switcher(self):
        method, game = self.method(), self.game()
        if method == "Mod Organizer 2":
            return cd.MO2Switcher(self.mo2_profile)
        if method == "Vortex":
            return cd.VortexSwitcher(game.install_path)
        if not self.folder:
            raise cd.DoctorError("Choose the folder that holds the mods first.")
        return cd.FolderSwitcher(self.folder)

    def start(self):
        from gg_desktop import bisect_flow
        game = self.game()
        if game is None or self.launch_box.currentData() is None:
            self.result("Pick a game Game Grave can start.", "warn")
            return
        try:
            switcher = self.build_switcher()
            units = switcher.units()
        except (cd.DoctorError, OSError, ValueError) as problem:
            self.result(str(problem), "warn")
            return
        if len(units) < 1:
            self.result("No mods were found to test.", "warn")
            return
        plan = cd.Plan(switcher.method, game.name, self.launch_box.currentText(), int(self.fine_box.currentData()),
                       self.sometimes.isChecked())
        if not self.window_.confirm("Start Crash Doctor?", cd.confirmation(plan, len(units), self.folder)):
            return
        self.switcher, self.plan = switcher, plan
        self.flow = bisect_flow.Flow(units, bisect_flow.Setup(sometimes=plan.sometimes), now=time.time())
        self.runs = 0
        self._remember_active(True)
        log_event("crash_doctor_start", f"Crash Doctor started for {game.name} ({switcher.method}, {len(units)} mods)",
                  source="Mod Bisect")
        for control in (self.game_box, self.method_box, self.launch_box, self.fine_box, self.sometimes, self.start_button):
            control.setEnabled(False)
        self.step(2)
        self.next_test()

    def stop(self, finished_text=None):
        self.timer.stop()
        self._close_game()
        left = self.switcher.restore() if self.switcher is not None else []
        self._remember_active(False)
        if left:
            text = ("Most mods are back. These couldn't go back because something new has the same name, so they wait in "
                    f"the holding folder ({cd.HOLD_NAME}): " + ", ".join(left[:8]))
            tone = "warn"
        else:
            text = finished_text or "Stopped. Every mod is back where it was."
            tone = "good" if finished_text else "info"
        log_event("crash_doctor_end", text[:300], source="Mod Bisect")
        self.result(text, tone)
        self.step(4 if finished_text else 1)
        self.switcher = None
        self.phase = "idle"
        for control in (self.game_box, self.method_box, self.launch_box, self.fine_box, self.sometimes, self.start_button):
            control.setEnabled(True)

    def _remember_active(self, on):
        roots = []
        if isinstance(self.switcher, cd.FolderSwitcher):
            roots = [str(self.switcher.folder)]
        elif isinstance(self.switcher, cd.VortexSwitcher):
            roots = sorted({r for files in self.switcher.mods.values() for r, _ in files})
        saved = [r for r in self.window_.settings.get(ACTIVE_KEY, []) if r not in roots]
        settings = dict(self.window_.settings, **{ACTIVE_KEY: saved + (roots if on else [])})
        try:
            from core import save_settings
            save_settings(settings)
            self.window_.settings = settings
        except OSError:
            pass

    # ------------------------------------------------------------ one test
    def next_test(self):
        from gg_desktop import bisect_flow
        if self.flow.done() or self.runs >= cd.MAX_RUNS:
            self.stop(self.flow.report_text(self.plan.game) if self.flow.done() else
                      f"Stopped after {cd.MAX_RUNS} launches without a final answer. " + self.flow.progress_text())
            return
        step = self.flow.step()
        if not isinstance(step, bisect_flow.StepView):
            self.stop(self.flow.report_text(self.plan.game))
            return
        try:
            self.switcher.apply(step.on_keys)
        except Exception as problem:     # MO2 open, a locked file: stop and put back
            self.stop()
            self.result("Couldn't switch the mods for the next test: " + str(problem)[:200], "warn")
            return
        self.repeat = 1
        self._start_run(step)

    def _start_run(self, step):
        self.runs += 1
        extra = f" (run {self.repeat} of {step.runs})" if step.runs > 1 else ""
        self.result(f"Test {step.number}{extra}: {len(step.on_keys)} of {len(self.flow.units)} mods on. Starting the game…",
                    "info")
        self._launch()
        self.started_at, self.seen_at, self.phase = time.time(), None, "starting"
        self.timer.start()

    def _launch(self):
        kind, value = self.launch_box.currentData()
        if kind == "mo2":
            exe = Path(self.mo2.ini).parent / "ModOrganizer.exe"
            if not exe.is_file():
                exe = Path(self.window_.settings.get("mo2_exe", ""))
            if not exe.is_file():
                path, _ = QFileDialog.getOpenFileName(self, "Find ModOrganizer.exe", "", "ModOrganizer.exe (ModOrganizer.exe)")
                exe = Path(path) if path else exe
                if path:
                    self.window_.settings = dict(self.window_.settings, mo2_exe=path)
            self.proc = subprocess.Popen(cd.mo2_launch(exe, self.switcher.copy_name, value))
        elif isinstance(value, str):
            os.startfile(value)          # steam://rungameid/...
        else:
            self.proc = subprocess.Popen(value, cwd=str(Path(value[0]).parent))

    def _running(self):
        from gg_desktop import winpc
        games, _loaders = cd.game_programs(self.game().install_path)
        wanted = {g.casefold() for g in games}
        return [p for p in winpc.list_processes(winpc.Runner()) if p.name.casefold() in wanted]

    def tick(self):
        now = time.time()
        running = self._running()
        if self.phase == "starting":
            if running:
                self.phase, self.seen_at = "watching", now
            elif now - self.started_at > cd.START_WAIT:
                self.finish_test(cd.Observation(False, 0, False))
            return
        if self.phase == "watching":
            ran = now - self.seen_at
            if not running:
                self.finish_test(cd.Observation(True, ran, False, self._crash_recorded()))
            elif ran >= self.plan.fine_after:
                self._close_game()
                self.finish_test(cd.Observation(True, ran, True))
            else:
                self.result(f"Test {self.flow.step().number}: running {int(ran)} s of {self.plan.fine_after} s…", "info")

    def _crash_recorded(self):
        try:
            from gg_desktop import blackbox_core as bb
            folder = str(self.game().install_path).casefold()
            return any(c.when.timestamp() >= self.started_at - 5 and str(c.path or "").casefold().startswith(folder)
                       for c in bb.parse_events(bb.query_events(20)))
        except Exception:
            return False

    def _close_game(self):
        if self.switcher is None:
            return
        try:
            for proc in self._running():
                subprocess.run(["taskkill", "/PID", str(proc.pid)], capture_output=True, timeout=15,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            time.sleep(1)
            for proc in self._running():
                subprocess.run(["taskkill", "/F", "/PID", str(proc.pid)], capture_output=True, timeout=15,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception:
            pass
        if self.proc is not None:
            try:
                self.proc.wait(timeout=30)       # Mod Organizer 2 closes itself after the game
            except Exception:
                self.proc.kill()                 # only the copy Game Grave started
            self.proc = None

    def finish_test(self, obs):
        self.timer.stop()
        result = cd.judge(obs, self.plan.fine_after)
        self.result(cd.explain(result, obs, self.plan.fine_after), "warn" if result == "crash" else "info")
        self._close_game()
        step = self.flow.step()
        if result == "ok" and getattr(step, "runs", 1) > self.repeat and self.runs < cd.MAX_RUNS:
            self.repeat += 1                          # "only crashes sometimes": run the same test again
            QTimer.singleShot(3000, lambda: self._start_run(step))
            return
        self.flow.answer(result)
        QTimer.singleShot(3000, self.next_test)      # a moment for files to unlock before the next switch

    def closeEvent(self, event):
        if self.switcher is not None:
            self.stop()
        super().closeEvent(event)

    def done(self, code):                # Close, Esc: never leave mods aside
        if self.switcher is not None:
            self.stop()
        super().done(code)


def open_doctor(window, game=None):
    dialog = DoctorDialog(window, game)
    window.crash_doctor = dialog
    dialog.show()
    return dialog


def check_leftovers(window):
    """At start: mods Crash Doctor moved aside before Game Grave closed are offered back."""
    roots = [r for r in window.settings.get(ACTIVE_KEY, []) if isinstance(r, str)]
    waiting = cd.leftovers(roots)
    if not waiting:
        return

    def put_back():
        left = []
        for root in waiting:
            left += cd.put_back(root)
        window.settings = dict(window.settings, **{ACTIVE_KEY: []})
        window.info("Crash Doctor", "Every mod is back." if not left else
                    "Some couldn't go back because something new has the same name: " + ", ".join(left[:8]))
    from gg_desktop import comfort
    comfort.notify(window, "Crash Doctor left mods aside", "Game Grave closed during a test. Put them back where they were.",
                   "warn", "Mods", action=("Put back", put_back))
