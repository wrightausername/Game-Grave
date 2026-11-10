"""Mod Bisect, the tab's brain: state, what each button does, and what the panel and table say. No Qt.

The Qt layer (`bisect_tab.py`) draws `rows()` and `panel()` and forwards clicks and typing here. Slow work (reading
mod folders, reading crash reports, building a test profile) is exposed as a `*_job` function that touches nothing
shared plus a `*_done` function that applies the result, so the screen can run the job on a worker thread.

Honest-claims rules from the engine carry through: only the owner's launches prove anything; reports and dates only
order the search; nothing is ever called safe.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from gg_desktop import bisect_apply as apply_mod
from gg_desktop import bisect_clues as clues_mod
from gg_desktop import bisect_flow as flow_mod
from gg_desktop import bisect_store as store
from gg_desktop import bisect_units as units_mod
from gg_desktop.bisect_core import Verdict


@dataclass(frozen=True)
class ProfileInfo:
    key: str
    name: str
    manager: str
    folder: Path | None                 # the profile's own folder when Game Grave can write a test copy (MO2 only)
    game_name: str = ""
    install_path: str = ""
    base_folder: str = ""               # Mod Organizer 2 instance folder, for its logs

    @property
    def can_write(self) -> bool:
        return self.folder is not None and self.manager == "Mod Organizer 2"


@dataclass(frozen=True)
class Button:
    key: str
    text: str
    symbol: str = "scan"
    enabled: bool = True
    primary: bool = False
    tip: str = ""


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    placeholder: str
    value: str


@dataclass(frozen=True)
class Toggle:
    key: str
    text: str
    checked: bool


@dataclass(frozen=True)
class Panel:
    stage: str                           # unavailable | loading | setup | testing | done
    title: str
    lines: tuple = ()                    # ("text"|"caption"|"warn"|"good"|"section"|"key:<Name>", text)
    fields: tuple = ()
    toggles: tuple = ()
    buttons: tuple = ()


class Model:
    def __init__(self, store_root: Path, *, now=time.time, apply_module=apply_mod):
        self.store_root = Path(store_root)
        self.now = now
        self.apply = apply_module
        self.profile: ProfileInfo | None = None
        self.marker = None
        self.loading = False
        self.units: list = []
        self.files: dict = {}
        self.folders: dict = {}           # mod key -> folder name, which is the name modlist.txt uses
        self.notes: list = []
        self.loaded_at = 0.0
        # the owner's clues
        self.last_text = ""
        self.started_text = ""
        self.sometimes = False
        self.hints: tuple = ()
        self.hint_label = ""
        self.always_on: tuple = ()
        # crash reports
        self.clues = None
        self.reports_state = ""           # "", "reading", "done"
        self.reports_found = 0
        # the run
        self.flow: flow_mod.Flow | None = None
        self.copy = None
        self.applied = 0
        self.applying = False
        self.message = ""
        self.warn = ""                    # blocks Start (e.g. profile keeps its own saves)

    # ------------------------------------------------------------ profile and mods
    def sync(self, profile: ProfileInfo | None, marker) -> bool:
        """Note the chosen profile. True when the mods must be (re)read in the background."""
        if profile is None:
            if self.profile is not None:
                self._reset_run()
            self.profile, self.marker, self.units, self.loading = None, None, [], False
            self.hints, self.hint_label, self.always_on = (), "", ()
            return False
        previous = self.profile
        same = previous is not None and previous.key == profile.key and self.marker == marker
        self.profile = profile
        if same:
            return False
        if previous is None or previous.key != profile.key:
            self.hints, self.hint_label, self.always_on = (), "", ()      # picks belong to one profile's mods
        self._reset_run()
        self.marker, self.loading, self.units, self.files, self.folders = marker, True, [], {}, {}
        self.warn = ""
        if profile.can_write and self.apply.keeps_own_saves(profile.folder):
            self.warn = ("This profile keeps its own saves, so a copy would not see them and Bisect will not use it. "
                         "Pick another profile.")
        return True

    def _reset_run(self):
        self.flow, self.copy, self.applied, self.applying = None, None, 0, False
        self.clues, self.reports_state, self.reports_found = None, "", 0
        self.message = ""

    def load_job(self, catalog, profile_obj, canceled):
        """Runs on a worker. Reads mod folders only."""
        def work(_emit=None):
            units, files, notes = units_mod.units_for_profile(catalog, profile_obj, cancelled=canceled)
            folders = {e.key: Path(e.path).name for e in catalog.entries if e.kind == "mod"}
            return units, files, notes, folders
        return work

    def load_done(self, result, error):
        self.loading = False
        if error or result is None:
            self.message = "The mods in this profile could not be read. " + (error or "")
            return
        self.units, self.files, self.notes = result[0], result[1], result[2]
        self.folders = dict(result[3]) if len(result) > 3 else {u.key: u.name for u in self.units}
        self.loaded_at = self.now()
        saved = store.load(self.store_root, self.profile.key) if self.profile else None
        if saved:
            try:
                self.flow = flow_mod.Flow.restore(self.units, saved, self.profile.key)
                self.clues = self.flow.clues
                self.hints, self.always_on = self.flow.setup.hint_keys, self.flow.setup.always_on
                self.sometimes = self.flow.setup.sometimes
                self.message = "Continuing the search you started earlier."
            except ValueError as exc:
                store.forget(self.store_root, self.profile.key)
                self.message = "An earlier search was dropped: " + str(exc)

    # ------------------------------------------------------------ the owner's clues
    def set_field(self, key: str, value: str):
        if key == "last":
            self.last_text = value
        elif key == "started":
            self.started_text = value

    def set_sometimes(self, on: bool):
        self.sometimes = bool(on)

    def use_hints(self, keys, label=""):
        valid = {u.key for u in self.units}
        self.hints = tuple(k for k in keys if k in valid)
        self.hint_label = label or (f"{len(self.hints)} mods you picked" if self.hints else "")
        self.message = ""

    def clear_hints(self):
        self.hints, self.hint_label = (), ""

    def mark_always_on(self, keys):
        valid = {u.key for u in self.units}
        merged = tuple(dict.fromkeys(list(self.always_on) + [k for k in keys if k in valid]))
        self.always_on = merged
        self.hints = tuple(k for k in self.hints if k not in merged)

    def clear_always_on(self):
        self.always_on = ()

    def setup(self):
        """(Setup, problem text). A date that cannot be read is reported, never guessed."""
        now = self.loaded_at or self.now()
        last, p1 = flow_mod.parse_when(self.last_text, now)
        began, p2 = flow_mod.parse_when(self.started_text, now)
        problem = " ".join(p for p in (("It last worked: " + p1) if p1 else "", ("Crashes started: " + p2) if p2 else "") if p)
        return flow_mod.Setup(last, began, self.hints, self.always_on, self.sometimes), problem

    def pack_choices(self) -> list:
        return self._flow().batch_choices() if self.units else []

    # ------------------------------------------------------------ crash reports
    def reports_job(self, collect):
        """`collect(units, files, profile, folders)` does the reading (patched in tests). Runs on a worker."""
        units, files, profile, folders = list(self.units), dict(self.files), self.profile, dict(self.folders)
        self.reports_state = "reading"
        def work(_emit=None):
            return collect(units, files, profile, folders)
        return work

    def reports_done(self, result, error):
        if error or result is None:
            self.reports_state, self.message = "", "Crash reports could not be read. " + (error or "")
            return
        self.clues, self.reports_found = result
        self.reports_state = "done"
        self.message = ""

    # ------------------------------------------------------------ the run
    def _flow(self) -> flow_mod.Flow:
        if self.flow is not None:
            return self.flow
        setup, _ = self.setup()
        return flow_mod.Flow(self.units, setup, now=self.loaded_at or self.now(), clues=self.clues,
                             profile_key=self.profile.key if self.profile else "")

    def can_start(self) -> bool:
        return bool(self.units) and not self.warn and not self.loading and self.flow is None

    def start(self) -> bool:
        if not self.can_start():
            return False
        setup, problem = self.setup()
        if problem:
            return False
        self.flow = flow_mod.Flow(self.units, setup, now=self.loaded_at or self.now(), clues=self.clues,
                                  profile_key=self.profile.key)
        self.applied, self.message = 0, ""
        self._save()
        return True

    def _save(self):
        if self.flow and self.profile:
            store.save(self.store_root, self.profile.key, self.flow.snapshot())

    def answer(self, result: str) -> bool:
        if self.flow is None or self.flow.done():
            return False
        step = self.flow.step()
        if self.profile and self.profile.can_write and result != "unsure" and self.applied != step.number:
            self.message = "Build this test first, so the answer is about exactly these mods."
            return False
        self.flow.answer(result)
        if result != "unsure":
            self.applied = 0
        self.message = ""
        self._save()
        return True

    def undo(self) -> bool:
        if self.flow is None or not self.flow.undo():
            return False
        self.applied = 0
        self._save()
        return True

    def stop(self):
        if self.profile:
            store.forget(self.store_root, self.profile.key)
        self.flow, self.applied, self.message = None, 0, ""

    # ------------------------------------------------------------ building the test profile (Mod Organizer 2)
    def apply_job(self):
        step = self.flow.step() if self.flow else None
        if not isinstance(step, flow_mod.StepView) or not self.profile or not self.profile.can_write:
            return None
        folder, number = self.profile.folder, step.number
        names = sorted(self.folders.get(k, self.flow.units_by_key[k].name) for k in step.on_keys
                       if k in self.flow.units_by_key)
        self.applying = True
        def work(_emit=None):
            info = self.apply.make_copy(folder)
            self.apply.write_test(info.folder, names)
            return info, number
        return work

    def apply_done(self, result, error):
        self.applying = False
        if error or result is None:
            self.message = error or "The test could not be built."
            return
        self.copy, self.applied = result
        self.message = ""

    # ------------------------------------------------------------ what to show
    def rows(self) -> list:
        return self._flow().rows() if self.units else []

    def reasons_for(self, key: str) -> list:
        """Plain reasons this mod is where Bisect looks (or not), for the selected row."""
        if not self.units:
            return []
        flow = self._flow()
        return list(flow.session.reasons.get(key, []))

    def notice(self) -> str:
        if self.profile is None:
            return ("No saved profile was found. Scan for Mods first: Bisect works from a profile's list of "
                    "switched-on mods.")
        if self.loading:
            return "Reading the mods in this profile…"
        if not self.units:
            return "This profile has no switched-on mods to test."
        if self.flow is None:
            return ("Ordered by where to look first: mods added after it last worked, then newer ones. "
                    "Tick mods to use as clues, then press Start.")
        return self.flow.progress_text() if not self.flow.done() else "Search finished."

    def report_text(self) -> str:
        return self.flow.report_text(self.profile.name if self.profile else "") if self.flow else ""

    def copy_text_for_step(self) -> str:
        step = self.flow.step() if self.flow else None
        return flow_mod.mods_to_turn_on(step) if isinstance(step, flow_mod.StepView) else ""

    def panel(self) -> Panel:
        if self.profile is None:
            return Panel("unavailable", "Find what is crashing", (("text", self.notice()),))
        if self.loading:
            return Panel("loading", "Find what is crashing", (("text", "Reading the mods in this profile…"),))
        if not self.units:
            return Panel("unavailable", "Find what is crashing", (("text", self.notice()),))
        if self.flow is None:
            return self._setup_panel()
        if self.flow.done():
            return self._done_panel()
        return self._testing_panel()

    def _profile_lines(self) -> list:
        p = self.profile
        lines = [("key:Profile", f"{p.name} · {p.manager}"), ("key:Mods on", str(len(self.units)))]
        if p.game_name:
            lines.insert(1, ("key:Game", p.game_name))
        return lines

    def _setup_panel(self) -> Panel:
        p = self.profile
        lines = [("text", "Game Grave turns groups of your mods on and off, you start the game and tell it if it "
                          "crashed, and it narrows down which mods cause it. Your own profile is never changed."),
                 *self._profile_lines()]
        if p.can_write:
            lines.append(("caption", f"It works in a copy named “{apply_mod.copy_name(p.name)}”. Close Mod Organizer 2 "
                                     "before each test."))
        else:
            lines.append(("warn", f"Game Grave can only build a test profile for Mod Organizer 2. For {p.manager} it "
                                  "shows exactly which mods to turn on each time, and you set them yourself."))
        if self.warn:
            lines.append(("warn", self.warn))
        lines.append(("section", "What you know (all optional)"))
        lines.append(("caption", "These only decide what is tested first. Wrong guesses cost extra launches, never the answer."))
        if self.hints:
            lines.append(("key:Starting with", self.hint_label or f"{len(self.hints)} mods"))
        if self.always_on:
            lines.append(("key:Always on", f"{len(self.always_on)} mods"))
        if self.clues is not None:
            lines.append(("key:Crash reports", f"{self.clues.reports_read} read, {len(self.clues.hits)} mods named"))
            for note in self.clues.notes[:2]:
                lines.append(("caption", note))
            for line in clues_mod.what_reports_say(self.clues)[:3]:
                lines.append(("caption", line))
        elif self.reports_state == "reading":
            lines.append(("caption", "Reading crash reports…"))
        _, problem = self.setup()
        if problem:
            lines.append(("warn", problem))
        if self.message:
            lines.append(("warn", self.message))
        for note in self.notes:
            lines.append(("caption", note))
        fields = (Field("last", "It last worked", "e.g. 2026-10-30 or 2 weeks ago", self.last_text),
                  Field("started", "Crashes started", "e.g. last week", self.started_text))
        toggles = (Toggle("sometimes", "It only crashes sometimes", self.sometimes),)
        buttons = (Button("use_checked", "Use Checked Mods As The New Ones", "check",
                          tip="Tick the mods you added just before the crashes began, then press this."),
                   Button("pick_pack", "Pick A Downloaded Pack…", "download",
                          tip="Mods installed together are grouped so you can pick the pack."),
                   Button("always_on", "Keep Checked Mods Always On", "shield",
                          tip="For frameworks other mods need. They stay on in every test."),
                   Button("clear_clues", "Clear Picks", "close", enabled=bool(self.hints or self.always_on)),
                   Button("read_reports", "Read Crash Reports", "scan", enabled=self.reports_state != "reading"),
                   Button("start", "Start Finding", "wand", enabled=self.can_start() and not problem, primary=True))
        return Panel("setup", "Find what is crashing", tuple(lines), fields, toggles, buttons)

    def _testing_panel(self) -> Panel:
        flow, p = self.flow, self.profile
        step = flow.step()
        lines = [("key:Progress", flow.progress_text()), ("section", f"Test {step.number}: {step.title}"),
                 ("text", step.instructions), ("caption", step.why),
                 ("key:Mods on", f"{len(step.on_names)} of {len(flow.units)}")]
        ready = True
        if p.can_write:
            if self.applying:
                lines.append(("caption", "Building the test…"))
                ready = False
            elif self.applied == step.number and self.copy is not None:
                lines.append(("good", f"Ready. Open Mod Organizer 2, choose the profile “{self.copy.folder.name}” "
                                      "(restart it if it is not listed) and start the game."))
            else:
                lines.append(("text", "Close Mod Organizer 2, then press Build This Test."))
                ready = False
        else:
            lines.append(("text", "Set your mods up exactly as listed, start the game, then answer."))
        if self.message:
            lines.append(("warn", self.message))
        buttons = []
        if p.can_write:
            buttons.append(Button("build", "Build This Test", "wand", enabled=not self.applying, primary=not ready))
        else:
            buttons += [Button("copy_list", "Copy Mods To Turn On", "file"), Button("save_list", "Save List As .txt", "save")]
        buttons += [Button("crash", "It Crashed", "warning", enabled=ready and not self.applying, primary=ready),
                    Button("ok", "It Ran Fine", "check", enabled=ready and not self.applying),
                    Button("unsure", "Not Sure", "help", enabled=ready and not self.applying,
                           tip="Adds nothing; the same test is asked again."),
                    Button("undo", "Undo Last Answer", "undo", enabled=bool(flow.answers)),
                    Button("stop", "Stop Searching", "close")]
        if p.can_write and self.copy is not None:
            buttons.append(Button("open_copy", "Open Test Profile Folder", "folder"))
        return Panel("testing", "Find what is crashing", tuple(lines), (), (), tuple(buttons))

    def _done_panel(self) -> Panel:
        flow = self.flow
        verdict = flow.step()
        lines = [("section", {"culprit": "Found it", "interaction": "Found it: mods that crash together",
                              "multiple": "Found several causes", "outside": "Not a mod",
                              "unreproducible": "It did not crash", "undetermined": "Narrowed, not finished"}.get(
                                  verdict.kind, "Result")),
                 ("good" if verdict.kind in ("culprit", "interaction", "multiple") else "warn", verdict.text)]
        for line in flow.cross_check():
            lines.append(("caption", line))
        if verdict.kind in ("culprit", "interaction", "multiple") and self.profile:
            lines.append(("caption", "Game Grave changed nothing in your own profile. To fix the crash, turn the "
                                     f"mod(s) off in {self.profile.manager}, or update or remove them there."))
        buttons = (Button("copy_report", "Copy Report", "file", primary=True), Button("save_report", "Save Report", "save"),
                   Button("undo", "Undo Last Answer", "undo", enabled=bool(flow.answers),
                          tip="Took a wrong answer? Go back and continue."),
                   Button("restart", "Start Over", "sync"))
        return Panel("done", "Find what is crashing", tuple(lines), (), (), buttons)

    # ------------------------------------------------------------ saving the report
    def save_report(self, folder: Path | None = None) -> Path:
        """Write the plain-text report under Game Grave's own folder; returns the file."""
        import re
        from datetime import datetime
        root = Path(folder) if folder else self.store_root / "bisect" / "reports"
        root.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^A-Za-z0-9]+", "-", self.profile.name if self.profile else "profile").strip("-")[:40] or "profile"
        path = root / f"bisect-{slug}-{datetime.fromtimestamp(self.now()).strftime('%Y%m%d-%H%M%S')}.txt"
        path.write_text(self.report_text(), encoding="utf-8")
        return path

    def restart(self):
        self.stop()
        self.clues, self.reports_state = None, ""
