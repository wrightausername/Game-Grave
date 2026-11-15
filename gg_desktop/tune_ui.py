"""Make it run better (opened from Soulbind): a measured before/after test with PresentMon and Autopsy. Every change asks
first, is logged, and is undone through Game Optimizer's own backup. Recording needs the game running and asks Windows
for permission (PresentMon reads frame timing through an administrator-only Windows trace)."""
from __future__ import annotations

import base64
import os
import subprocess
from datetime import datetime

from PySide6.QtWidgets import QComboBox

from core import log_event
from gg_desktop import tune_core as tc
from gg_desktop.tools_shell import ChoiceRow, ToolDialog, card
from gg_desktop.widgets import button, label, row


class TuneDialog(ToolDialog):
    def __init__(self, window, game=None):
        super().__init__(window, "tune", "Make it run better", "sparkles", width=640, step_names=tc.STEPS,
                         summary="Play two minutes, try changes, play two minutes again. Game Grave measures both runs on "
                                 "your PC and keeps the changes only if they helped.", color="#32d67a")
        self.window_ = window
        self.before = self.after = None
        self.applied = False
        self.games = sorted((g for g in window.inventory.games if getattr(g, "install_path", "")),
                            key=lambda g: g.name.casefold())
        top = row(spacing=8)
        top.addWidget(label("Game", "caption"))
        self.combo = QComboBox()
        self.combo.setAccessibleName("Game to make run better")
        for g in self.games:
            self.combo.addItem(g.name)
        if game is not None:
            at = next((i for i, g in enumerate(self.games) if g.name == game.name), -1)
            if at >= 0:
                self.combo.setCurrentIndex(at)
        top.addWidget(self.combo, 1)
        self.body.addLayout(top)
        frame, lay = card(spacing=0)
        self.rows = {}
        for n, (key, words, technical) in enumerate(tc.TWEAKS):
            choice = ChoiceRow(words, technical, "Try", "blue", last=n == len(tc.TWEAKS) - 1)
            choice.check.setChecked(True)
            self.rows[key] = choice
            lay.addWidget(choice)
        self.body.addWidget(frame)
        self.note = label("", "caption", wrap=True)
        self.body.addWidget(self.note)
        self.details.set_lines(["Frame times: Intel PresentMon " + tc.PRESENTMON_VERSION + " (" + tc.PRESENTMON_URL + ")",
                                "SHA-256 " + tc.PRESENTMON_SHA256,
                                "Recording: " + str(tc.RECORD_SECONDS) + " seconds of the game's own program, asked "
                                "through the Windows permission prompt.",
                                "Changes are Game Optimizer's; Put back uses its saved backup."])
        self.get_button = button("Get PresentMon (free, from Intel)", self.get_presentmon)
        self.record_button = button("Record before", self.record, kind="primary")
        self.try_button = button("Try the changes", self.try_changes, kind="primary")
        self.keep_button = button("Keep changes", self.keep, kind="primary")
        self.back_button = button("Put back", self.put_back)
        self.add_actions(self.get_button, self.back_button, self.try_button, self.keep_button, self.record_button)
        self.sync()

    # ------------------------------------------------------------ state
    def game(self):
        i = self.combo.currentIndex()
        return self.games[i] if 0 <= i < len(self.games) else None

    def sync(self):
        have = tc.presentmon_path().is_file()
        self.get_button.setVisible(not have)
        stage = 0 if self.before is None else (2 if not self.applied else (3 if self.after is None else 4))
        self.step(1 if (have and stage == 0 and self.game()) else stage)
        self.record_button.setVisible(have and stage in (0, 3))
        self.record_button.setText("Record before" if stage == 0 else "Record after")
        self.try_button.setVisible(stage == 2)
        self.keep_button.setVisible(stage == 4)
        self.back_button.setVisible(self.applied)
        self.combo.setEnabled(stage == 0)
        if not have:
            self.note.setText("Recording needs Intel's free PresentMon (about 1 MB, downloaded once from Intel's GitHub and "
                              "checked against its published SHA-256).")
        elif stage == 0:
            self.note.setText("Start the game, get into normal play, then press Record before. Keep playing the same kind "
                              f"of scene for {tc.RECORD_SECONDS // 60} minutes.")

    # ------------------------------------------------------------ PresentMon
    def get_presentmon(self):
        if not self.window_.confirm("Download PresentMon?", "Download Intel PresentMon " + tc.PRESENTMON_VERSION +
                                    " (MIT licence) from:\n" + tc.PRESENTMON_URL + "\n\nIt is checked against its published "
                                    "SHA-256 and kept in Game Grave's tools folder. Nothing else is installed."):
            return
        from gg_desktop import local_ai_core as ai
        self.result("Downloading PresentMon…", "info")
        dest = tc.presentmon_path()

        def work(progress):
            ai.download(tc.remote(), dest, progress=lambda d, t: progress(int(d * 100 / max(1, t or 1)), "Downloading"))
            return str(dest)

        def done(path):
            log_event("tool_download", "Downloaded Intel PresentMon " + tc.PRESENTMON_VERSION, path=path,
                      result="Verified SHA-256", source="Soulbind")
            self.result("PresentMon is ready.", "good")
            self.sync()
        self.window_.job(work, done, error_title="PresentMon was not downloaded")

    def record(self):
        game = self.game()
        if game is None:
            return
        label_ = "before" if self.before is None else "after"
        out = tc.captures_dir() / tc.capture_name(game.name, label_, datetime.now())
        out.parent.mkdir(parents=True, exist_ok=True)
        script = tc.record_script(tc.presentmon_path(), game.install_path, out)
        self.record_button.setEnabled(False)
        self.result(f"Recording {label_}: keep playing for {tc.RECORD_SECONDS // 60} minutes. Windows asks to allow it.",
                    "info")

        def work(_progress):
            encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
            run = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                                 capture_output=True, text=True, timeout=tc.RECORD_SECONDS + 120,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return run.returncode

        def done(code):
            self.record_button.setEnabled(True)
            self.finish_record(label_, out, code)
        self.window_.job(work, done, error_title="The recording did not finish")

    def finish_record(self, label_, out, code):
        from gg_desktop import autopsy_core as ap
        if code != 0 or not os.path.exists(out):
            self.result(tc.RECORD_CODES.get(code, f"PresentMon stopped with code {code}. Nothing was recorded."), "warn")
            return
        try:
            stats = ap.stats_for(ap.read_capture(out))
        except Exception as problem:
            self.result("The recording could not be read: " + str(problem)[:160], "warn")
            return
        if label_ == "before":
            self.before = stats
            self.result(f"Before: {stats.avg_fps:.0f} FPS average, {stats.low1_fps:.0f} FPS 1% low. Now try the changes.",
                        "good")
        else:
            self.after = stats
            self.show_verdict()
        self.sync()

    # ------------------------------------------------------------ changes
    def chosen(self):
        return [k for k, choice in self.rows.items() if choice.check.isChecked()]

    def try_changes(self):
        keys = self.chosen()
        if not keys:
            self.result("Tick at least one change to try.", "warn")
            return
        lines = [f"{words}: {technical}" for key, words, technical in tc.TWEAKS if key in keys]
        if not self.window_.confirm("Try these changes?", "\n".join(lines) + "\n\nGame Grave saves the current values first; "
                                    "Put back restores them."):
            return
        from core import config_dir
        from gg_desktop import autopilot_run, winpc
        notes = winpc.apply_optimizer(winpc.default_registry(), winpc.Runner(), set(keys),
                                      os.path.join(config_dir(), autopilot_run.BACKUP_NAME))
        log_event("tune_try", "Make it run better: " + " ".join(notes), source="Soulbind")
        self.applied = True
        self.result("Changes made. Keep playing the same scene, then press Record after.", "good")
        self.sync()

    def show_verdict(self):
        from gg_desktop import autopsy_core as ap
        v = tc.verdict(ap.compare(self.before, self.after))
        a, b = self.after, self.before
        self.result(f"{v.title}. {v.detail} (Before {b.avg_fps:.0f} / {b.low1_fps:.0f} FPS, after {a.avg_fps:.0f} / "
                    f"{a.low1_fps:.0f} FPS average / 1% low.)", v.tone)
        self.keep_button.setText("Keep changes" if v.keep else "Keep anyway")
        self.back_button.setText("Put back" if v.keep else "Put back (suggested)")

    def keep(self):
        log_event("tune_keep", "Make it run better: kept the changes", source="Soulbind")
        self.result("Kept. Put them back any time in Toolbox > Game Optimizer.", "good")
        self.applied = False
        self.before = self.after = None
        self.sync()

    def put_back(self):
        from core import config_dir
        from gg_desktop import autopilot_run, winpc
        notes = winpc.undo_optimizer(winpc.default_registry(), winpc.Runner(),
                                     os.path.join(config_dir(), autopilot_run.BACKUP_NAME))
        log_event("tune_undo", "Make it run better: put back. " + " ".join(notes), source="Soulbind")
        self.applied = False
        self.before = self.after = None
        self.result("Your previous settings are back.", "good")
        self.sync()


def open_tune(window, game=None):
    dialog = TuneDialog(window, game)
    window.tune_dialog = dialog
    dialog.show()
    return dialog

