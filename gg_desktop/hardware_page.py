"""Hardware tab: your PC's parts, live load, play sessions you record, and upgrade notes built only from them.

Display and wiring only; every rule lives in hardware_core. Reading is read-only: Game Grave asks Windows what is
installed and samples load. The one file it writes is its own sessions list, and only when you stop a recording.
"""
from __future__ import annotations

from collections import deque
import time
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFileDialog, QFrame, QGridLayout, QLabel, QWidget

from core import human_size, log_event
from gg_desktop import hardware_core as hw
from gg_desktop import hardware_graphics as hg
from gg_desktop.header_banner import HeaderBannerArtwork
from gg_desktop.reference_widgets import MetricStrip, TabStrip
from gg_desktop.widgets import button, column, label, panel, row

SUBTITLE = "Your PC's real parts and live load. Upgrade notes appear only when your own recorded sessions point to them."
TONES = {"red": "#FF3B57", "green": "#35DC7C", "cyan": "#42D4F2", "amber": "#DFAC46", "muted": "#9AA4AC"}
HISTORY = 48
TICK_SECONDS = 2   # what the caption tells the person; tests may speed up TICK_MS but not this
TICK_MS = TICK_SECONDS * 1000
RECORD_CAP = 7200  # readings (4 hours); a longer recording is saved when it reaches this


# ------------------------------------------------------------------ the one sampler, kept on the window
class Monitor(QObject):
    """Samples every 2 seconds while a Hardware tab is open or a recording is running, one reading at a time."""

    def __init__(self, window, sampler=None, clock=None):
        super().__init__(window)
        self.clock = clock or time.time
        self.window_owner = window
        self.sampler = sampler or hw.Sampler()
        self.history = deque(maxlen=HISTORY)
        self.viewers = []          # callables told about each new reading
        self.recording = False
        self.readings = []
        self.started = 0.0
        self.busy = False
        self.timer = QTimer(self)
        self.timer.setInterval(TICK_MS)
        self.timer.timeout.connect(self.tick)

    def attach(self, viewer):
        self.viewers.append(viewer)
        self.refresh_timer()
        self.tick()

    def detach(self, viewer):
        if viewer in self.viewers:
            self.viewers.remove(viewer)
        self.refresh_timer()

    def refresh_timer(self):
        if self.viewers or self.recording:
            if not self.timer.isActive():
                self.timer.start()
        else:
            self.timer.stop()

    def tick(self):
        if self.busy:
            return
        self.busy = True
        self.window_owner.job(lambda _progress: self.sampler.sample(), self.arrived,
                              error_title="Hardware reading failed")

    def arrived(self, live):
        self.busy = False
        self.history.append(live)
        if self.recording:
            self.readings.append(live)
            if len(self.readings) >= RECORD_CAP:
                self.stop()
        for viewer in list(self.viewers):
            try:
                viewer(live)
            except RuntimeError:
                self.viewers.remove(viewer)

    def start(self):
        self.recording, self.readings, self.started = True, [], self.clock()
        self.refresh_timer()
        self.tick()

    def stop(self):
        """Returns (session or None, message). A recording shorter than two minutes counts as nothing."""
        ended = self.clock()
        self.recording = False
        readings, self.readings = self.readings, []
        self.refresh_timer()
        session = hw.summarize(readings, self.started, ended)
        if session is None:
            return None, (f"That recording was shorter than {hw.MIN_SESSION_SECONDS // 60} minutes, so it was not "
                          "saved. A session that short is not evidence.")
        hw.save_session(session)
        log_event("Hardware session recorded", f"{hw.short_time(session.seconds)}, {session.samples} readings", result="saved",
                  source="Hardware")
        return session, f"Saved a {hw.short_time(session.seconds)} session."


def monitor_of(window) -> Monitor:
    monitor = getattr(window, "hardware_monitor", None)
    if monitor is None:
        monitor = window.hardware_monitor = Monitor(window)
    return monitor


# ------------------------------------------------------------------ small widgets
def _pill(text, tone):
    pill = QLabel(text)
    pill.setAlignment(Qt.AlignCenter)
    color = TONES[tone]
    pill.setStyleSheet(f"font-size:11px;font-weight:700;color:{color};border:1px solid {color};"
                       "border-radius:9px;padding:1px 9px;background:transparent;")
    return pill


def _clear(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().hide()
            item.widget().deleteLater()
        elif item.layout():
            _clear(item.layout())


def _card_frame(accent):
    frame = QFrame()
    frame.setObjectName("hwCard")
    frame.setStyleSheet(f"QFrame#hwCard{{border:1px solid #1f2d37;border-left:3px solid {accent};border-radius:9px;"
                        "background:#0a131a;}QLabel{border:0;background:transparent;}")
    return frame


def _spec_card(code, name, detail, tone="cyan", extra=()):
    frame = _card_frame(TONES[tone])
    line = row(spacing=12, margins=(12, 10, 12, 10))
    frame.setLayout(line)
    chip = QLabel(code)
    chip.setAlignment(Qt.AlignCenter)
    chip.setFixedSize(46, 30)
    chip.setStyleSheet(f"font-size:11px;font-weight:700;color:{TONES[tone]};border:1px solid {TONES[tone]};"
                       "border-radius:6px;background:transparent;")
    line.addWidget(chip, 0, Qt.AlignTop)
    words = column(spacing=1)
    title = label(name, "readyGameTitle", wrap=True)
    title.setAccessibleName(f"{code} {name}")
    words.addWidget(title)
    if detail:
        words.addWidget(label(detail, "readyDetail", wrap=True))
    for widget in extra:
        words.addSpacing(3)
        words.addWidget(widget)
    line.addLayout(words, 1)
    line.setAlignment(words, Qt.AlignTop)
    return frame


def _peak_chip(name, value, color):
    chip = QLabel(f"{name} {'—' if value is None else str(round(value)) + '%'}")
    chip.setAlignment(Qt.AlignCenter)
    chip.setStyleSheet(f"font-size:11px;font-weight:700;color:{color if value is not None else '#6c7a86'};"
                       f"border:1px solid {color if value is not None else '#2a3b4b'};border-radius:9px;padding:1px 8px;"
                       "background:transparent;")
    return chip


def _session_card(session):
    import datetime
    frame = _card_frame("#42D4F2")
    line = row(spacing=8, margins=(12, 8, 12, 8))
    frame.setLayout(line)
    words = column(spacing=0)
    when = datetime.datetime.fromtimestamp(session.started).strftime("%b %d, %H:%M")
    words.addWidget(label(when, "readyGameTitle"))
    words.addWidget(label(f"{hw.short_time(session.seconds)} · {session.samples} readings", "caption"))
    line.addLayout(words, 1)
    for name, color, value in zip(("CPU", "GPU", "RAM", "VRAM"), ("#42D4F2", "#FF3B57", "#35DC7C", "#df83ec"),
                                  hg.SessionPeaks.values(session)):
        line.addWidget(_peak_chip(name, value, color))
    frame.setAccessibleName(f"Session {when}, {hw.short_time(session.seconds)}")
    return frame


# ------------------------------------------------------------------ the page
def percent(value):
    return "—" if value is None else f"{round(value)}%"


def build(window):
    self = window
    monitor = monitor_of(self)
    page = self._insight_page("Hardware", SUBTITLE, "undo", "chip", 66)
    page.banner_artwork = HeaderBannerArtwork(self, page, page.content.itemAt(0).widget(), route="Hardware",
                                              scene="undo", source=(915, 28, 365, 83), excluded=((1090, 0, 190, 40),))
    ui = page.hardware = Body(self, monitor)
    ui.tabs = TabStrip([("Your PC", "chip"), ("Upgrade Advisor", "radio")], selected=getattr(self, "hardware_tab", "Your PC"))
    ui.tabs.setMinimumWidth(420)
    ui.tabs.setMaximumWidth(560)
    page.content.addWidget(ui.metrics)
    page.content.addWidget(ui.tabs)
    ui.pc_tab, pc = QWidget(), column(spacing=10)
    ui.pc_tab.setLayout(pc)
    pc.addWidget(ui.rig)
    pc.addWidget(ui.monitor_panel)   # the live monitor is the centre of this tab: full width, above the rest
    bottom = row(spacing=10)
    bottom.addWidget(ui.parts_panel, 2)
    bottom.addWidget(ui.drives_panel, 1)
    pc.addLayout(bottom)
    ui.adv_tab, adv = QWidget(), row(spacing=10)
    ui.adv_tab.setLayout(adv)
    adv.addWidget(ui.advice_panel, 6)
    side = column(spacing=10)
    side.addWidget(ui.peaks_panel)
    side.addWidget(ui.sessions_panel)
    side.addStretch()
    adv.addLayout(side, 5)
    page.content.addWidget(ui.pc_tab)
    page.content.addWidget(ui.adv_tab)
    page.content.addStretch()
    ui.tabs.changed.connect(ui.show_tab)
    ui.show_tab(getattr(self, "hardware_tab", "Your PC"))
    ui.start()
    page.destroyed.connect(ui.stop_viewing)
    return page


class Body(QObject):
    def __init__(self, window, monitor):
        super().__init__()
        self.window_owner, self.monitor = window, monitor
        self.filter = "all"
        self.last = None
        self._viewer = self.on_live

        self.metrics = MetricStrip([
            ("chip", "—", "CPU Load", "#15c7ed"), ("game", "—", "GPU Load", "#ff2145"),
            ("storage", "—", "Memory In Use", "#2bd971"), ("grid", "—", "Video Memory", "#d76ce6"),
            ("radio", "—", "GPU Temp", "#f8c82c"), ("storage", "—", "Drives Found", "#16baf1")], compact=True)

        self.rig = hg.RigMap()
        self.peaks_panel, peaks = panel(kind="libraryPanel", padding=12, spacing=6)
        peaks_head = row(spacing=8)
        peaks_head.addWidget(label("Session Peaks", "sectionTitle"), 1)
        peaks_head.addWidget(label("The highest reading of each recorded play session. The upgrade notes are built from these.", "caption"))
        peaks.addLayout(peaks_head)
        self.peaks = hg.SessionPeaks()
        peaks.addWidget(self.peaks)
        self.sessions_panel, sessions = panel(kind="libraryPanel", padding=12, spacing=8)
        sessions.addWidget(label("Recorded Sessions", "sectionTitle"))
        self.sessions_box = column(spacing=8)
        sessions.addLayout(self.sessions_box)
        self.parts_panel, parts = panel(kind="libraryPanel", padding=12, spacing=8)
        head = row(spacing=10)
        head.addWidget(label("Your Parts", "sectionTitle"))
        self.parts_when = label("", "caption")
        head.addWidget(self.parts_when)
        head.addStretch()
        self.copy_button = button("Copy Specs", self.copy_specs, kind="actionLink",
                                  tip="Copies a plain text list of your parts. It stays on this PC until you paste it.")
        head.addWidget(self.copy_button)
        self.save_button = button("Save as .txt", self.save_specs, kind="actionLink")
        head.addWidget(self.save_button)
        self.reread = button("Re-read Hardware", self.read_parts, kind="primary",
                             tip="Asks Windows what is installed. Changes nothing.")
        head.addWidget(self.reread)
        parts.addLayout(head)
        self.parts_box = QGridLayout()
        self.parts_box.setContentsMargins(0, 0, 0, 0)
        self.parts_box.setSpacing(10)
        self.parts_box.setColumnStretch(0, 1)
        self.parts_box.setColumnStretch(1, 1)
        parts.addLayout(self.parts_box)

        self.advice_panel, advice = panel(kind="libraryPanel", padding=12, spacing=8)
        head = row(spacing=8)
        head.addWidget(label("Upgrade Advisor", "sectionTitle"), 1)
        self.session_count = label("", "caption")
        head.addWidget(self.session_count)
        advice.addLayout(head)
        advice.addWidget(label("Each note shows what was measured and what it cannot tell you. No frame rate promises, "
                               "no prices, no claim that anything is safe to buy.", "readyDetail", wrap=True))
        rec = row(spacing=8)
        self.record = button("Record Play Session", self.toggle_record, kind="primary",
                             tip="Samples your PC every 2 seconds until you stop. Keep Game Grave open while you play.")
        rec.addWidget(self.record)
        self.clear_button = button("Clear Sessions", self.clear_sessions, kind="actionLink",
                                   tip="Deletes only Game Grave's own recorded sessions file.")
        rec.addWidget(self.clear_button)
        self.record_status = label("", "readyDetail", wrap=True)
        rec.addWidget(self.record_status, 1)
        advice.addLayout(rec)
        chips = row(spacing=6)
        self.chip_buttons = {}
        for key, text in (("all", "All"), ("gpu", "Graphics"), ("memory", "Memory"), ("storage", "Storage"),
                          ("cpu", "Processor"), ("power", "Power")):
            chip = button(text, lambda _=False, k=key: self.set_filter(k), kind="chip")
            chip.setCheckable(True)
            chip.setAccessibleName(f"Show {text} notes")
            self.chip_buttons[key] = chip
            chips.addWidget(chip)
        chips.addStretch()
        advice.addLayout(chips)
        self.notes_box = column(spacing=8)
        advice.addLayout(self.notes_box)
        advice.addStretch()

        self.monitor_panel, mon = panel(kind="libraryPanel", padding=12, spacing=6)
        title = label("Live Monitor", "sectionTitle")
        title.setAlignment(Qt.AlignHCenter)
        mon.addWidget(title)
        caption = label(f"Last {HISTORY * TICK_SECONDS} seconds, updated every {TICK_SECONDS} seconds while "
                        "this tab is open", "caption")
        caption.setAlignment(Qt.AlignHCenter)
        mon.addWidget(caption)
        charts = row(spacing=18)
        self.charts = {}
        self.gauges = {}
        for key, title, color, empty in (("cpu", "CPU", "#42D4F2", "Not readable"),
                                         ("gpu", "GPU", "#FF3B57", "Needs an NVIDIA card"),
                                         ("mem", "MEMORY", "#35DC7C", "Not readable"),
                                         ("vram", "VIDEO MEMORY", "#df83ec", "Needs an NVIDIA card"),
                                         ("temp", "GPU TEMP", "#f8c82c", "Needs an NVIDIA card")):
            cell = column(spacing=2)
            now = label("—", "readyWhen")
            gauge = hg.RingGauge(color, title, 150)
            cell.addWidget(gauge, 0, Qt.AlignHCenter)
            chart = hg.AreaChart(color, empty, HISTORY, "100 °C" if key == "temp" else "100%")
            chart.setAccessibleName(f"{title} load, last {HISTORY * TICK_SECONDS} seconds")
            cell.addWidget(chart)
            now.hide()   # the gauge above shows the same reading
            self.charts[key] = (chart, now)
            self.gauges[key] = gauge
            charts.addLayout(cell, 1)
        mon.addLayout(charts)
        self.monitor_note = label("", "readyDetail", wrap=True)
        mon.addWidget(self.monitor_note)

        self.drives_panel, drives = panel(kind="libraryPanel", padding=12, spacing=8)
        drives.addWidget(label("Drives", "sectionTitle"))
        self.donut = hg.StorageDonut()
        drives.addWidget(self.donut)
        self.drives_box = column(spacing=8)
        drives.addLayout(self.drives_box)
        drives.addStretch()

    # -------------------------------------------------------------- lifecycle
    def start(self):
        self.show_sessions()
        specs = getattr(self.window_owner, "hardware_specs", None)
        if specs is None:
            self.read_parts()
        else:
            self.show_parts(specs)
        if self.monitor.history:
            self.draw_live(self.monitor.history[-1])
        self.monitor.attach(self._viewer)
        self.sync_record()

    def stop_viewing(self, *_):
        self.monitor.detach(self._viewer)

    # -------------------------------------------------------------- parts
    def read_parts(self):
        self.reread.setEnabled(False)
        self.parts_when.setText("Asking Windows…")

        def work(_progress):
            try:
                return hw.read_specs(), ""
            except OSError as problem:
                return None, str(problem)
        self.window_owner.job(work, self.parts_arrived, error_title="Could not read the hardware")

    def parts_arrived(self, result):
        specs, error = result
        window = self.window_owner
        if specs is not None:
            window.hardware_specs = specs
        window.hardware_error = error
        try:
            self.reread.setEnabled(True)
            self.show_parts(specs, error)
        except RuntimeError:
            pass

    def show_parts(self, specs, error=""):
        _clear(self.parts_box)
        if specs is None:
            self.parts_when.setText("")
            self.rig.set_specs(None, "Windows would not share the hardware list.")
            self.parts_box.addWidget(label(f"Windows would not share the hardware list: {error}", "readyDetail", wrap=True),
                                     0, 0, 1, 2)
            return
        self.parts_when.setText("Read from Windows just now")
        cards = []
        if specs.cpu:
            c = specs.cpu
            detail = f"{c.cores} cores, {c.threads} threads, base {c.base_ghz} GHz" + (f", socket {c.socket}" if c.socket else "")
            cards.append(_spec_card("CPU", c.name, detail, "cyan", extra=(hg.CoreGrid(c.cores, c.threads),)))
        for gpu in specs.gpus:
            cards.append(_spec_card("GPU", gpu.name, f"Driver {gpu.driver}" if gpu.driver else "", "red"))
        if specs.memory:
            m = specs.memory
            slots = f"{m.sticks} of {m.slots} slots used" if m.slots else f"{m.sticks} module{'s' if m.sticks != 1 else ''}"
            speed = (f"Running at {m.running_mts} MT/s" + (f", rated {m.rated_mts}" if m.rated_mts else "")) if m.running_mts else ""
            kind = f" {m.kind}" if m.kind else ""
            extra = []
            if m.slots or m.sticks:
                extra.append(hg.SlotStrip(m.sticks, m.slots))
            if m.running_mts and m.rated_mts:
                extra.append(hg.SpeedBars(m.running_mts, m.rated_mts))
            cards.append(_spec_card("RAM", f"{hw._gb(m.total_gb)}{kind}", ". ".join(x for x in (slots, speed) if x),
                                    "green", extra=tuple(extra)))
        for drive in specs.drives:
            model = drive.model or "Unnamed drive"
            hard = drive.kind == "hard drive"
            used = 1 - drive.free / drive.total if drive.total else 0
            cards.append(_spec_card("SSD" if drive.fast else "HDD" if hard else "DRV", f"{drive.letter}: {model}",
                                    f"{drive.kind[:1].upper() + drive.kind[1:]}, {human_size(drive.total)}, {human_size(drive.free)} free",
                                    "amber" if hard else "cyan",
                                    extra=(hg.DriveBar(used, "#DFAC46" if hard else "#42D4F2"),)))
        if specs.board:
            cards.append(_spec_card("MB", specs.board, f"BIOS {specs.bios}" if specs.bios else "", "cyan"))
        if specs.display:
            cards.append(_spec_card("DSP", specs.display, "", "green"))
        if specs.os_name:
            cards.append(_spec_card("OS", specs.os_name, f"Version {specs.os_version}" if specs.os_version else "", "green"))
        for index, card in enumerate(cards):
            self.parts_box.addWidget(card, index // 2, index % 2)
        self.rig.set_specs(specs)
        self.show_advice()
        self.show_drives(specs)
        self.draw_metrics_static(specs)

    def show_tab(self, name):
        name = name if name in ("Your PC", "Upgrade Advisor") else "Your PC"
        self.window_owner.hardware_tab = name
        self.pc_tab.setVisible(name == "Your PC")
        self.adv_tab.setVisible(name == "Upgrade Advisor")
        self.tabs.select(name)

    def draw_metrics_static(self, specs):
        self.metrics.values[5].setText(str(len(specs.drives)))

    # -------------------------------------------------------------- advice
    def set_filter(self, key):
        self.filter = key
        self.show_advice()

    def show_sessions(self):
        self.sessions = hw.load_sessions()
        n = len(self.sessions)
        self.session_count.setText(f"{n} recorded session{'s' if n != 1 else ''}")
        self.clear_button.setVisible(n > 0)
        self.peaks.set_sessions(self.sessions)
        _clear(self.sessions_box)
        if not self.sessions:
            self.sessions_box.addWidget(label("No sessions yet. Press Record Play Session, play for a while, then stop it.",
                                              "readyDetail", wrap=True))
        for session in reversed(self.sessions[-8:]):
            self.sessions_box.addWidget(_session_card(session))

    def show_advice(self):
        for key, chip in self.chip_buttons.items():
            chip.setChecked(key == self.filter)
        _clear(self.notes_box)
        specs = getattr(self.window_owner, "hardware_specs", None)
        if specs is None:
            self.notes_box.addWidget(label("Notes appear once the hardware has been read.", "readyDetail", wrap=True))
            return
        notes = hw.advise(specs, self.sessions, self.window_owner.inventory.games)
        for note in notes:
            if self.filter in ("all", note.key):
                self.notes_box.addWidget(self.note_card(note))

    def note_card(self, note):
        color = TONES[note.tone]
        frame = QFrame()
        frame.setStyleSheet(f"QFrame{{border:1px solid {color};border-radius:7px;}}QLabel{{border:0;background:transparent;}}")
        box = column(spacing=4, margins=(12, 9, 12, 9))
        frame.setLayout(box)
        top = row(spacing=8)
        top.addWidget(label(note.title, "readyGameTitle"), 1)
        top.addWidget(_pill(note.tag, note.tone))
        box.addLayout(top)
        box.addWidget(label(note.summary, "readyDetail", wrap=True))
        for point in note.points:
            box.addWidget(label("•  " + point, "readyDetail", wrap=True))
        box.addWidget(label("Cannot tell you: " + note.limit, "caption", wrap=True))
        if note.action:
            go = button(note.action[0], lambda _=False, r=note.action[1]: self.window_owner.navigate(r), kind="actionLink")
            box.addWidget(go, 0, Qt.AlignLeft)
        frame.setAccessibleName(f"{note.title}: {note.tag}")
        return frame

    # -------------------------------------------------------------- recording
    def toggle_record(self):
        window = self.window_owner
        if not self.monitor.recording:
            self.monitor.start()
            window.status.setText("Recording a play session. Keep Game Grave open while you play.")
            self.sync_record()
            return
        session, message = self.monitor.stop()
        window.status.setText(message[:110])
        self.show_sessions()
        self.show_advice()
        self.sync_record(message)

    def sync_record(self, note=""):
        if self.monitor.recording:
            self.record.setText("Stop and Save Session")
            self.record_status.setText("Recording… Keep Game Grave open while you play. It ends if you close it.")
        else:
            self.record.setText("Record Play Session")
            self.record_status.setText(note or "Start this, then play. Stop it after at least 2 minutes.")

    def clear_sessions(self):
        window = self.window_owner
        if not window.confirm("Clear recorded sessions", "Delete the sessions Game Grave recorded? Only Game Grave's "
                              "own list is removed. No game or Windows file is touched."):
            return
        hw.clear_sessions()
        log_event("Hardware sessions cleared", "recorded sessions list removed", result="cleared", source="Hardware")
        self.show_sessions()
        self.show_advice()

    # -------------------------------------------------------------- live
    def on_live(self, live):
        self.last = live
        self.draw_live(live)

    def draw_live(self, live):
        self.rig.set_live(live)
        history = list(self.monitor.history)
        cpu = [r.cpu for r in history]
        gpu = [(r.gpu.load if r.gpu else None) for r in history]
        mem = [(100.0 * r.mem_used_gb / r.mem_total_gb if r.mem_used_gb is not None and r.mem_total_gb else None)
               for r in history]
        vram = [(100.0 * r.gpu.mem_used_mb / r.gpu.mem_total_mb
                 if r.gpu and r.gpu.mem_used_mb is not None and r.gpu.mem_total_mb else None) for r in history]
        temp = [(r.gpu.temp_c if r.gpu and r.gpu.temp_c is not None else None) for r in history]
        for key, values in (("cpu", cpu), ("gpu", gpu), ("mem", mem), ("vram", vram), ("temp", temp)):
            chart, _now = self.charts[key]
            chart.set_values(values)
        g = live.gpu
        self.charts["cpu"][1].setText(percent(live.cpu))
        self.charts["gpu"][1].setText(percent(g.load if g else None))
        self.charts["mem"][1].setText("—" if live.mem_used_gb is None else f"{live.mem_used_gb:.1f} GB")
        mem_fraction = (live.mem_used_gb / live.mem_total_gb if live.mem_used_gb is not None and live.mem_total_gb else None)
        self.gauges["cpu"].set_value(None if live.cpu is None else live.cpu / 100.0, percent(live.cpu), "in use")
        self.gauges["gpu"].set_value(None if not g or g.load is None else g.load / 100.0, percent(g.load if g else None),
                                     "in use" if g else "needs NVIDIA")
        has_vram = bool(g and g.mem_used_mb is not None and g.mem_total_mb)
        self.gauges["vram"].set_value(g.mem_used_mb / g.mem_total_mb if has_vram else None,
                                      f"{g.mem_used_mb / 1024:.1f}" if has_vram else "—",
                                      f"GB of {g.mem_total_mb / 1024:.0f}" if has_vram else "needs NVIDIA")
        has_temp = bool(g and g.temp_c is not None)
        self.gauges["temp"].set_value(g.temp_c / 100.0 if has_temp else None, f"{round(g.temp_c)}°" if has_temp else "—",
                                      "celsius" if has_temp else "needs NVIDIA")
        self.gauges["mem"].set_value(mem_fraction, "—" if live.mem_used_gb is None else f"{live.mem_used_gb:.1f}",
                                     "GB of " + f"{live.mem_total_gb:.0f}" if live.mem_total_gb else "GB")
        values = self.metrics.values
        values[0].setText(percent(live.cpu))
        values[1].setText(percent(g.load if g else None))
        values[2].setText("—" if live.mem_used_gb is None else f"{live.mem_used_gb:.1f} of {live.mem_total_gb:.0f} GB")
        values[3].setText("—" if not g or g.mem_used_mb is None or not g.mem_total_mb
                          else f"{g.mem_used_mb / 1024:.1f} of {g.mem_total_mb / 1024:.0f} GB")
        values[4].setText("—" if not g or g.temp_c is None else f"{round(g.temp_c)} °C")
        self.monitor_note.setText(
            "" if g else "Graphics load, video memory and graphics temperature can be read only from NVIDIA cards "
                         "(through nvidia-smi). Windows does not report a trustworthy CPU temperature, so none is shown.")

    # -------------------------------------------------------------- drives and spec sheet
    def show_drives(self, specs):
        self.donut.set_drives(specs.drives)
        _clear(self.drives_box)
        if not specs.drives:
            self.drives_box.addWidget(label("Windows did not report any drives.", "readyDetail", wrap=True))
        for d in specs.drives:
            line = column(spacing=2)
            top = row(spacing=8)
            top.addWidget(label(f"{d.letter}: {d.model or 'Drive'}  ({d.kind})", "readyWhen", wrap=True), 1)
            top.addWidget(label(f"{human_size(d.free)} free of {human_size(d.total)}", "caption"))
            line.addLayout(top)
            used = 1 - d.free / d.total if d.total else 0
            line.addWidget(hg.DriveBar(used, "#DFAC46" if d.kind == "hard drive" else "#42D4F2"))
            self.drives_box.addLayout(line)

    def copy_specs(self):
        specs = getattr(self.window_owner, "hardware_specs", None)
        if specs is None:
            self.window_owner.info("Spec sheet", "The hardware has not been read yet.")
            return
        QGuiApplication.clipboard().setText(hw.spec_sheet(specs))
        self.window_owner.status.setText("Spec sheet copied. It stays on this PC until you paste it.")

    def save_specs(self):
        specs = getattr(self.window_owner, "hardware_specs", None)
        if specs is None:
            self.window_owner.info("Spec sheet", "The hardware has not been read yet.")
            return
        start = str(Path.home() / "GameGrave-specs.txt")
        name, _ = QFileDialog.getSaveFileName(self.window_owner, "Save spec sheet", start, "Text file (*.txt)")
        if not name:
            return
        try:
            Path(name).write_text(hw.spec_sheet(specs) + "\n", encoding="utf-8")
        except OSError as problem:
            self.window_owner.error("Spec sheet", f"Could not save it: {problem}")
            return
        self.window_owner.status.setText("Spec sheet saved.")
