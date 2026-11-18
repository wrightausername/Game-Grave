"""Crash Doctor window (from Mod Bisect, Fix Kit, the assistant and the "your game just crashed" notice). Easy by default:
Game Grave picks the game, finds its mods (Mod Organizer 2, Vortex or a plain mod folder) and how to start it, and asks one
question, "When does it crash?". The choices stay behind "Change". Start runs every Bisect test itself; Stop or the end
puts every mod back, and the answer comes with Turn it off / Look it up online / Leave everything as it is."""
from __future__ import annotations

import dataclasses
import os
import subprocess
import time
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QGridLayout, QVBoxLayout, QWidget

from core import log_event
from gg_desktop import crashdoctor_core as cd
from gg_desktop.tools_shell import ToolDialog
from gg_desktop.widgets import button, label, row

ACTIVE_KEY = "crash_doctor_active"     # holding folders in use, so a closed app can put mods back next start
STEPS = ("Check what Game Grave found", "Start", "Tests run by themselves", "See the answer")
CRASH_SEEN_KEY = "crash_doctor_offered"   # {game name: time} so the "just crashed" notice shows at most once a day per game


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


def has_mods(window, game):
    """Whether Crash Doctor can find mods for this game without asking (MO2 setup, Vortex list or a known mod folder)."""
    if not getattr(game, "install_path", ""):
        return False
    if cd.vortex_manifests(game.install_path) or cd.find_mod_folder(game.install_path, game.name):
        return True
    return _mo2_instance(window, game)[0] is not None


def _default_game(window, games):
    """The modded game played most recently, else the first."""
    modded = [g for g in games if has_mods(window, g)]
    pool = modded or games
    return max(pool, key=lambda g: getattr(g, "last_played_at", None) or 0) if pool else None


class DoctorDialog(ToolDialog):
    def __init__(self, window, game=None):
        super().__init__(window, "crash_doctor", "Crash Doctor", "warning", width=660, step_names=STEPS,
                         summary="Finds the mod that crashes your game. It starts the game with different mods switched "
                                 "off, sees when it crashes, and puts everything back at the end.",
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
        game = game or _default_game(window, self.games)
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
        # The easy part: one sentence about what was found, one question, Start.
        self.found_line = label("", "toolLead", wrap=True)
        self.body.addWidget(self.found_line)
        self.when_box = QComboBox()
        self.when_box.setAccessibleName("When does it crash?")
        for key, words, *_rest in cd.WHEN:
            self.when_box.addItem(words, key)
        self.when_label = label("When does it crash?", "caption")
        self.body.addWidget(self.when_label)
        self.body.addWidget(self.when_box)
        self.when_note = label("", "caption", wrap=True)
        self.body.addWidget(self.when_note)
        self.change_button = button("Change game, mods or how it starts", self.toggle_advanced, kind="actionLink")
        self.body.addWidget(self.change_button)
        self.advanced = QWidget()
        box = QVBoxLayout(self.advanced)
        box.setContentsMargins(0, 0, 0, 0)
        box.addLayout(grid)
        self.folder_button = button("Choose the mod folder…", self.choose_folder, kind="actionLink")
        box.addWidget(self.folder_button)
        self.sometimes = QCheckBox("It only crashes sometimes (each test runs up to 3 times)")
        box.addWidget(self.sometimes)
        self.note = label("", "caption", wrap=True)
        box.addWidget(self.note)
        self.advanced.hide()
        self.body.addWidget(self.advanced)
        self.start_button = button("Start", self.start, kind="primary")
        self.stop_button = button("Stop and put everything back", self.stop)
        self.off_button = button("Turn it off", self.keep_off, kind="primary")
        self.look_button = button("Look it up online", self.look_up)
        self.leave_button = button("Leave everything as it is", self.leave)
        self.on_button = button("Turn them back on", self.back_on)
        for extra in (self.off_button, self.look_button, self.leave_button, self.on_button):
            extra.hide()
        self.stop_button.hide()
        answer = row(spacing=8)                # the three answer buttons get a row of their own, full labels
        answer.addWidget(self.leave_button)
        answer.addWidget(self.look_button)
        answer.addStretch(1)
        answer.addWidget(self.off_button)
        self.body.addLayout(answer)
        self.add_actions(self.on_button, self.stop_button, self.start_button)
        self.found = ()                  # mods the finished search named
        self.folder = ""
        self.switcher = self.flow = self.proc = None
        self.timer = QTimer(self, interval=2000)
        self.timer.timeout.connect(self.tick)
        self.phase = "idle"
        self.game_box.currentIndexChanged.connect(lambda _i: (setattr(self, "folder", ""), self.fill()))
        self.method_box.currentIndexChanged.connect(lambda _i: self.fill_launch())
        self.when_box.currentIndexChanged.connect(lambda _i: self.pick_when())
        self.fine_box.currentIndexChanged.connect(lambda _i: self.show_found())
        self.ready = False
        self.fill()
        self.pick_when()
        self.ready = True
        self.show_found()

    # ------------------------------------------------------------ the easy part
    def toggle_advanced(self):
        self.advanced.setVisible(not self.advanced.isVisible())
        self.change_button.setText("Hide the choices" if self.advanced.isVisible() else "Change game, mods or how it starts")

    def pick_when(self):
        _key, _words, seconds, sometimes, note = cd.when_choice(self.when_box.currentData())
        at = self.fine_box.findData(seconds)
        if at >= 0:
            self.fine_box.setCurrentIndex(at)
        self.sometimes.setChecked(sometimes)
        self.when_note.setText(note)
        self.when_note.setVisible(bool(note))
        self.show_found()

    def mod_count(self):
        """How many mods the current choice would test, without changing anything (None when none can be found)."""
        game, method = self.game(), self.method()
        try:
            if method == "Mod Organizer 2" and self.mo2_profile is not None:
                return len(cd.MO2Switcher(self.mo2_profile).units())
            if method == "Vortex":
                return len(cd.vortex_files(cd.vortex_manifests(game.install_path)))
            if method == "Folder" and self.folder:
                return len(cd.FolderSwitcher(self.folder).units())
        except Exception:
            return None
        return None

    def show_found(self):
        if not hasattr(self, "ready"):
            return
        game, method = self.game(), self.method()
        count = self.mod_count() if game is not None else None
        if game is None:
            text = "Scan your PC first so Game Grave knows your games."
        elif not count:
            text = (f"Game Grave couldn't find {game.name}'s mods by itself. Press \"Change\" below and choose the "
                    "folder that holds them.")
            if self.ready and not self.advanced.isVisible():
                self.toggle_advanced()
        else:
            where = {"Mod Organizer 2": "in Mod Organizer 2", "Vortex": "installed with Vortex",
                     "Folder": f"in {Path(self.folder).name or self.folder} (no mod manager)"}[method]
            fine = int(self.fine_box.currentData() or 120)
            _lo, _hi, low_min, high_min = cd.estimate(count, fine, self.sometimes.isChecked())
            text = (f"Game Grave will test your {count} {game.name} mod{'s' if count != 1 else ''} {where}. It takes about {low_min} to "
                    f"{high_min} minutes; leave the PC alone while it runs.")
        self.found_line.setText(text)
        self.start_button.setEnabled(bool(count) and self.phase == "idle")

    # ------------------------------------------------------------ choices
    def game(self):
        i = self.game_box.currentIndex()
        return self.games[i] if 0 <= i < len(self.games) else None

    def fill(self):
        game = self.game()
        self.method_box.blockSignals(True)
        self.method_box.clear()
        self.mo2 = self.mo2_profile = None
        if game is not None:
            self.mo2, self.mo2_profile = _mo2_instance(self.window_, game)
            if not self.folder:
                self.folder = cd.find_mod_folder(game.install_path, game.name)
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
        self.on_button.setVisible(bool(self._kept_off()))
        self.note.setText({"Mod Organizer 2": "Game Grave starts Mod Organizer 2 for each test.",
                           "Vortex": "Don't deploy in Vortex while it runs.",
                           "Folder": ("Mod folder: " + self.folder) if self.folder else
                           "Choose the folder that holds this game's mods. Each file or folder in it counts as one mod."}[
            self.method()])
        self.show_found()

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

    def _where(self, switcher):
        return getattr(switcher, "folder", None) or getattr(switcher, "profile_folder", None) or self.game().install_path

    def _store(self):
        from core import config_dir
        return config_dir()

    def _saved_flow(self, units):
        """A search stopped earlier for the same game and mods: offer to carry on from its answers."""
        from gg_desktop import bisect_flow, bisect_store
        saved = bisect_store.load(self._store(), self.key)
        if not saved:
            return None
        try:
            flow = bisect_flow.Flow.restore(units, saved, self.key)
        except ValueError as problem:
            bisect_store.forget(self._store(), self.key)
            self.result(f"The last search can't continue: {problem} Starting a new one.", "warn")
            return None
        answered = len(flow.answers)
        if self.window_.confirm("Continue where it left off?",
                                f"Crash Doctor already ran {answered} test{'s' if answered != 1 else ''} for this game "
                                f"({flow.progress_text()}).\n\nYes carries on from there. No starts a new search and "
                                "forgets those answers."):
            return flow
        bisect_store.forget(self._store(), self.key)
        return None

    def _save(self):
        from gg_desktop import bisect_store
        try:
            bisect_store.save(self._store(), self.key, self.flow.snapshot())
        except Exception:
            pass

    def start(self):
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
        if not self._clear_the_way(game):
            return
        plan = cd.Plan(switcher.method, game.name, self.launch_box.currentText(), int(self.fine_box.currentData()),
                       self.sometimes.isChecked())
        self.key = cd.resume_key(switcher.method, game.name, self._where(switcher))
        flow = self._saved_flow(units)
        if flow is None and not self.window_.confirm("Start Crash Doctor?", cd.confirmation(plan, len(units), self.folder)):
            return
        if flow is None:                          # crash reports first, so likely suspects are tested first
            self.result("Reading this game's crash reports so the likely mods are tested first…", "info")
            self.start_button.setEnabled(False)
            if isinstance(switcher, cd.MO2Switcher) and self.mo2 is not None:
                switcher.mods_dir = Path(self.mo2.mods_dir)

            def work(_progress):
                return self._read_clues(switcher, units, game)

            def done(clues):
                self._begin(switcher, units, plan, None, clues)
            self.window_.job(work, done)
            return
        self._begin(switcher, units, plan, flow, None)

    def _read_clues(self, switcher, units, game):
        try:
            from gg_desktop import bisect_tab
            from types import SimpleNamespace
            place = SimpleNamespace(install_path=game.install_path, base_folder="")
            clues, _count = bisect_tab.collect_reports(units, cd.files_by_mod(switcher), place)
            return clues
        except Exception:
            return None                            # no clues only means a plainer order, never a wrong answer

    def _clear_the_way(self, game):
        """Mod managers and the game itself must be closed first: offer to close them instead of failing."""
        try:
            from gg_desktop import winpc
            processes = winpc.list_processes(winpc.Runner())
        except Exception:
            return True
        games, _loaders = cd.game_programs(game.install_path)
        open_now = cd.blockers([p.name for p in processes], games)
        if not open_now:
            return True
        names = ", ".join(sorted({friendly for _exe, friendly in open_now}))
        if not self.window_.confirm("Close them for you?", f"{names[0].upper() + names[1:]} must be closed while Crash "
                                    "Doctor runs. Close it for you now?\n\nGame Grave asks each program to close the "
                                    "normal way, so it can save first. Nothing else is closed."):
            self.result(f"Close {names} first, then press Start.", "warn")
            return False
        exes = {exe.casefold() for exe, _f in open_now}
        for proc in processes:
            if proc.name.casefold() in exes:
                try:
                    subprocess.run(["taskkill", "/PID", str(proc.pid)], capture_output=True, timeout=15,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                except Exception:
                    pass
        log_event("crash_doctor_close", f"Crash Doctor asked {names} to close before testing", source="Mod Bisect")
        for _ in range(20):                         # up to 10 s for them to close
            time.sleep(0.5)
            try:
                still = cd.blockers([p.name for p in winpc.list_processes(winpc.Runner())], games)
            except Exception:
                still = []
            if not still:
                return True
        self.result(f"{names} didn't close. Close it yourself, then press Start.", "warn")
        return False

    def _begin(self, switcher, units, plan, flow, clues):
        from gg_desktop import bisect_flow
        game = self.game()
        if flow is not None:
            plan = dataclasses.replace(plan, sometimes=flow.setup.sometimes)
        self.switcher, self.plan, self.found = switcher, plan, ()
        for extra in (self.off_button, self.look_button, self.leave_button):
            extra.hide()
        self.stop_button.show()
        self.flow = flow or bisect_flow.Flow(units, bisect_flow.Setup(sometimes=plan.sometimes), now=time.time(),
                                             clues=clues, profile_key=self.key)
        self.runs = 0
        self.phase = "running"
        self.gen = getattr(self, "gen", 0) + 1    # timers from an earlier, stopped run are ignored
        self._remember_active(True)
        log_event("crash_doctor_start", f"Crash Doctor started for {game.name} ({switcher.method}, {len(units)} mods)",
                  source="Mod Bisect")
        for control in (self.game_box, self.method_box, self.launch_box, self.fine_box, self.sometimes, self.start_button,
                        self.when_box, self.change_button):
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
        if not finished_text and self.flow is not None and self.flow.answers:
            text += (f" The {len(self.flow.answers)} answers so far are kept: press Start to carry on from where it "
                     "stopped.")
        log_event("crash_doctor_end", text[:300], source="Mod Bisect")
        self.result(text, tone)
        self.step(4 if finished_text else 1)
        self.phase = "idle"
        self.stop_button.hide()
        for extra in (self.off_button, self.look_button, self.leave_button):
            extra.setVisible(bool(self.found))
        self.show_setup(not self.found)
        if self.found:
            self.off_button.setText("Turn it off" if len(self.found) == 1 else f"Turn off these {len(self.found)}")
        else:
            self.switcher = None
        for control in (self.game_box, self.method_box, self.launch_box, self.fine_box, self.sometimes, self.start_button,
                        self.when_box, self.change_button):
            control.setEnabled(True)
        self.show_found()

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
        if self.flow.done():
            self.finish_search()
            return
        if self.runs >= cd.MAX_RUNS:
            self._save()
            self.stop()
            self.result(f"Paused after {cd.MAX_RUNS} launches ({self.flow.progress_text()}). Every mod is back. Press "
                        "Start to carry on from where it stopped.", "info")
            return
        step = self.flow.step()
        if not isinstance(step, bisect_flow.StepView):
            self.finish_search()
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
        self.result(self.progress_words(step, "starting the game…"), "info")
        try:
            self._launch()
        except Exception as problem:     # no Steam, a moved game, a launcher Windows can't open: stop and put back
            self._save()
            self.stop()
            why = "Couldn't start the game that way (" + (str(problem) or type(problem).__name__)[:160] + "). "
            after = self.result_line.label.text()
            if cd.HOLD_NAME in after:            # some mods are waiting in the holding folder: say so, never "all back"
                self.result(why + after, "warn")
            else:
                self.result(why + "Every mod is back. Pick another way under \"Start the game with\" and press Start "
                            "to carry on.", "warn")
            return
        self.started_at, self.seen_at, self.phase = time.time(), None, "starting"
        self.timer.start()

    def progress_words(self, step, now_doing):
        """"Test 3 of about 7 · 18 mods still suspected · about 12 minutes left · running 40 of 120 seconds"."""
        info = self.flow.session.progress()
        left, minutes = cd.remaining(info["suspects"], self.plan.fine_after, self.plan.sometimes)
        number = getattr(step, "number", 0)
        repeat = f" (try {self.repeat} of {step.runs})" if getattr(step, "runs", 1) > 1 else ""
        return (f"Test {number}{repeat} of about {number + left - 1} · {info['suspects']} mods still suspected · about "
                f"{minutes} minutes left · {now_doing}")

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
                self.result(self.progress_words(self.flow.step(), f"running {int(ran)} of {self.plan.fine_after} seconds…"),
                            "info")

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
        self.no_starts = getattr(self, "no_starts", 0) + 1 if not obs.started else 0
        if self.no_starts >= 2:          # twice in a row the game never appeared: stop asking it to, and say so
            self.no_starts = 0
            self._save()
            self.stop()
            after = self.result_line.label.text()
            why = "The game didn't start twice in a row, so Crash Doctor stopped. "
            self.result(why + after if cd.HOLD_NAME in after else why + "Every mod is back. Check the game starts on its "
                        "own, or pick another way under \"Start the game with\", then press Start to carry on.", "warn")
            return
        step = self.flow.step()
        if result == "ok" and getattr(step, "runs", 1) > self.repeat and self.runs < cd.MAX_RUNS:
            self.repeat += 1                          # "only crashes sometimes": run the same test again
            QTimer.singleShot(3000, self._later(lambda: self._start_run(step)))
            return
        self.flow.answer(result)
        self._save()                                  # Stop, a closed app or the launch limit can carry on later
        QTimer.singleShot(3000, self._later(self.next_test))      # a moment for files to unlock before the next switch

    def _later(self, fn):
        gen = self.gen

        def run():
            if self.phase != "idle" and self.gen == gen:
                fn()
        return run

    def finish_search(self):
        """The whole search is done (it keeps going after the first cause until every cause is found)."""
        from gg_desktop import bisect_store
        verdict = self.flow.step()
        bisect_store.forget(self._store(), self.key)
        names = self.flow.names if hasattr(self.flow, "names") else {}
        if getattr(verdict, "kind", "") in ("culprit", "interaction", "multiple"):
            self.found = tuple(names.get(k, k) for k in verdict.keys)
            self.found_keys = tuple(verdict.keys)
        kind = getattr(verdict, "kind", "")
        self.details.set_lines(self.flow.report_text(self.plan.game))     # the full report, folded under the answer
        words = cd.headline(kind, list(self.found)) + " " + cd.HINTS.get(kind, "")
        if self.found:
            words += " Every mod is back for now; choose what to do below."
            if self.plan.method == "Vortex":
                words += " (Vortex may deploy a turned-off mod again; to keep it off for good, disable it in Vortex.)"
        self.stop(words)

    def keep_off(self):
        names = ", ".join(self.found[:10])
        how = {"Mod Organizer 2": "unticks them in your Mod Organizer 2 profile (My Mods keeps a snapshot, so Undo there "
                                  "turns them back on)",
               "Vortex": f"moves their files into {cd.OFF_NAME} in the game folder",
               "Folder": f"moves them into {cd.OFF_NAME} inside the mod folder"}[self.plan.method]
        if not self.window_.confirm("Turn the cause off?", f"Turn off {names}?\n\nGame Grave {how}. Nothing is "
                                    "deleted, and \"Turn them back on\" here puts them back."):
            return
        try:
            failed = cd.turn_off(self.switcher, self.found_keys)
        except Exception as problem:
            self.result("Couldn't turn them off: " + str(problem)[:200], "warn")
            return
        log_event("crash_doctor_off", f"Crash Doctor turned off {names} for {self.plan.game} ({self.plan.method})",
                  source="Mod Bisect")
        self.found, self.switcher = (), None
        for extra in (self.off_button, self.look_button, self.leave_button):
            extra.hide()
        self.show_setup(True)
        self.result(f"Turned off: {names}. Start the game to check it's fixed." + (
            " Couldn't move: " + ", ".join(failed[:6]) if failed else ""), "warn" if failed else "good")
        self.fill_launch()

    def show_setup(self, on):
        """The question, the Change link and Start are for setting up; with an answer on screen they step aside."""
        for widget in (self.found_line, self.when_label, self.when_box, self.change_button, self.start_button):
            widget.setVisible(on)
        self.when_note.setVisible(on and bool(self.when_note.text()))
        if not on:
            self.advanced.hide()
        self.adjustSize()

    def look_up(self):
        mod = self.found[0] if self.found else ""
        QDesktopServices.openUrl(QUrl(cd.look_up_url(mod, self.plan.game)))

    def leave(self):
        self.found, self.switcher = (), None
        for extra in (self.off_button, self.look_button, self.leave_button):
            extra.hide()
        self.result("Left as it is. Every mod is where it was before the tests.", "info")
        self.show_setup(True)

    def _kept_off(self):
        game = self.game()
        if game is None or self.method() == "Mod Organizer 2":
            return []
        return cd.turned_off([p for p in (self.folder, game.install_path) if p])

    def back_on(self):
        left = []
        for root in self._kept_off():
            left += cd.turn_back_on(root)
        log_event("crash_doctor_on", "Crash Doctor turned kept-off mods back on", source="Mod Bisect")
        self.result("Turned back on." if not left else
                    "Some couldn't go back because something new has the same name: " + ", ".join(left[:8]),
                    "good" if not left else "warn")
        self.fill_launch()

    def closeEvent(self, event):
        if self.phase != "idle":
            self.stop()
        super().closeEvent(event)

    def done(self, code):                # Close, Esc: never leave mods aside
        if self.phase != "idle":
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


def watch_crashes(window):
    """When a modded game closes, look once for a Windows crash record from the last minute; if there is one, offer Crash
    Doctor. Bounded: one record query per closed game, never while another game runs or Crash Doctor is testing, at most
    once a day per game."""
    from gg_desktop.games_tracking import tracker_for
    tracker = tracker_for(window)

    def closed(keys):
        if window.settings.get("crash_notice", True) is False:   # switched off in Settings > Notifications
            return
        if getattr(getattr(window, "crash_doctor", None), "phase", "idle") != "idle":
            return
        if tracker.last_active:                   # another game is running: do nothing now
            return
        games = [g for g in tracker.games if getattr(g, "key", None) in keys and getattr(g, "install_path", "")]
        seen = dict(window.settings.get(CRASH_SEEN_KEY, {}))
        now = time.time()
        games = [g for g in games if now - float(seen.get(g.name, 0)) > 86400]
        if not games:
            return

        def work(_progress):
            from gg_desktop import blackbox_core as bb
            try:
                crashes = bb.parse_events(bb.query_events(20))
            except Exception:
                return []
            hits = []
            for game in games:
                folder = str(game.install_path).casefold()
                if any(now - c.when.timestamp() < 90 and str(c.path or "").casefold().startswith(folder) for c in crashes):
                    hits.append((game, has_mods(window, game)))
            return hits

        def done(hits):
            for game, modded in hits[:1]:
                seen[game.name] = now
                window.settings = dict(window.settings, **{CRASH_SEEN_KEY: seen})
                from gg_desktop import assistant_page, comfort
                if not modded:             # not modded: find out why (crash records, the PC, what changed)
                    if assistant_page.speak_first(
                            window, f"Game Grave saw {game.name} close and Windows recorded a crash for it just now. "
                            "Tell the user briefly, check its crash records, and offer Fix Kit's Find out why.",
                            f"{game.name} just crashed", "The Gravekeeper can look into it with you."):
                        continue
                    from gg_desktop import crash_investigate_ui
                    comfort.notify(window, f"{game.name} just crashed", "Find out why? Game Grave reads the crash "
                                   "records, the game's logs and your PC and tells you the likely cause.", "warn",
                                   "Fix Kit", action=("Find out why",
                                                      lambda g=game: crash_investigate_ui.open_investigation(window, g)))
                    continue
                if assistant_page.speak_first(
                        window, f"Game Grave saw {game.name} close and Windows recorded a crash for it just now. It is "
                        "modded. Tell the user briefly, check its crash records, and offer Crash Doctor (it tests the "
                        "mods and puts everything back) or the usual fixes.",
                        f"{game.name} just crashed", "The Gravekeeper can look into it with you."):
                    continue
                comfort.notify(window, f"{game.name} just crashed", "Find the mod causing it? Crash Doctor tests "
                               "your mods for you and puts everything back.", "warn", "Mods",
                               action=("Find the mod", lambda g=game: open_doctor(window, g)))
        window.job(work, done)
    tracker.game_closed.connect(closed)
    return closed
