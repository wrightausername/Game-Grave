"""AI Assistant automation on screen: the plan card in the chat, the Automation panel with routines, the routine timer
and the notice that asks for an OK. The rules live in `autopilot_core` and the work in `autopilot_run`.

Off until the owner switches it on. Checks run straight away; changes run only after Run all (one confirmation that
lists every change and its exact line). Routines run their checks on time and leave their changes waiting for an OK.
Nothing starts while a game runs, a scan runs or a clean-up runs; the timer wakes every 5 minutes and does nothing else.
"""
from __future__ import annotations

import re
import time
from datetime import datetime
from types import SimpleNamespace

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QCheckBox, QFrame, QInputDialog, QLabel
from shiboken6 import isValid

from gg_desktop import autopilot_core as core, autopilot_run as run, tools_shell as shell
from gg_desktop.widgets import button, column, label, panel, row

TICK_MS = 5 * 60 * 1000
FIRST_TICK_MS = 90 * 1000
STATUS = {"waiting": ("Waiting", shell.words.IDLE), "running": ("Running…", shell.words.INFO),
          "done": ("Done", shell.words.GOOD), "problem": ("Look at this", shell.words.WARN),
          "skipped": ("Skipped", shell.words.IDLE)}
ROUTINES_CHAT = "Routines"


def state_of(window):
    if not hasattr(window, "_autopilot"):
        window._autopilot = SimpleNamespace(plans={}, envs={}, cards={}, running="", timer=None, busy=False, notice=None)
    return window._autopilot


def enabled(window):
    return window.settings.get(core.SETTING) is True


def game_running(window):
    from gg_desktop.autopsy_ui import game_running as running
    return running(window)


def _alive(widget):
    return widget is not None and isValid(widget)


def _save(window, settings):
    from gg_desktop import assistant_page
    return assistant_page.save(window, settings)


# ------------------------------------------------------------------ the plan card
class PlanCard(QFrame):
    def __init__(self, window, plan, live, off=False):
        super().__init__()
        self.window_, self.plan, self.live, self.off = window, plan, live, off
        self.setObjectName("autopilotCard")
        self.setStyleSheet(shell.STYLE + "QFrame#autopilotCard{background:#08111a;border:1px solid #1d3346;border-radius:12px;}")
        lay = column(spacing=8, margins=(14, 12, 14, 12))
        self.setLayout(lay)
        head = row(spacing=10)
        head.addWidget(shell.badge("sparkles", shell.HEX["cyan"], 30), 0, Qt.AlignTop)
        words = column(spacing=1)
        self.title = shell.text("Plan", "toolLead", wrap=False)
        self.sub = shell.text("")
        words.addWidget(self.title)
        words.addWidget(self.sub)
        head.addLayout(words, 1)
        self.count = shell.pill("", shell.words.INFO)
        head.addWidget(self.count, 0, Qt.AlignTop)
        lay.addLayout(head)
        self.rows = column(spacing=0)
        holder = QFrame()
        holder.setObjectName("toolCard")
        holder.setLayout(self.rows)
        self.rows.setContentsMargins(12, 2, 12, 2)
        lay.addWidget(holder)
        self.banner = shell.Banner("Plan result")
        lay.addWidget(self.banner)
        buttons = row(spacing=8)
        self.run_button = button("Run all", lambda: run_all(window, plan.id), kind="primary")
        self.run_button.setAccessibleName("Run all")
        self.save_button = button("Save as routine", lambda: save_routine(window, plan.id),
                                  tip="Keep this as a routine that runs on its schedule. Changes wait for your OK.")
        self.cancel_button = button("Cancel", lambda: cancel_plan(window, plan.id), tip="Do nothing with this plan")
        buttons.addWidget(self.cancel_button)
        buttons.addStretch()
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.run_button)
        lay.addLayout(buttons)
        self.update_view()

    def update_view(self):
        plan, st = self.plan, state_of(self.window_)
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        running = st.running == plan.id
        changeable = self.live and not running and any(s.status == "waiting" for s in plan.steps if s.kind == core.CHANGE)
        visible = [s for s in plan.steps]
        for n, step in enumerate(visible):
            self.rows.addWidget(self._row(step, n == len(visible) - 1, changeable))
        changes, checks = core.counts(plan)
        self.title.setText("Routine: " + plan.request.split(": ", 1)[-1] if plan.routine_id else "Plan")
        when = core.describe_schedule(plan.schedule) if plan.schedule else ""
        self.sub.setText(when + (". " if when else "") + (
            "Checks run straight away. Changes wait for Run all." if self.live else
            "What it would do. Running tools is switched off." if self.off else
            "From an earlier visit. Ask again to run it."))
        shell.set_pill(self.count, core.summary(plan), shell.words.INFO)
        waiting_changes = [s for s in plan.steps if s.ticked and s.kind == core.CHANGE and s.status == "waiting"]
        preparing = any(s.status == "running" for s in plan.steps) and not running
        self.run_button.setVisible(self.live and any(s.ticked and s.status == "waiting" for s in plan.steps))
        self.run_button.setEnabled(self.live and not running and not preparing and
                                   any(s.ticked and s.status == "waiting" for s in plan.steps))
        self.run_button.setText(("Run all (" + str(len(waiting_changes)) + (" change)" if len(waiting_changes) == 1
                                                                             else " changes)")) if waiting_changes else "Run all")
        self.save_button.setVisible(self.live and plan.schedule is not None and not plan.routine_id)
        self.cancel_button.setVisible(self.live and not running and any(s.status == "waiting" and s.ticked
                                                                        for s in plan.steps))
        if preparing:
            self.banner.setText("Running the checks. They only read.", shell.words.WORKING)
        elif running:
            self.banner.setText("Working through the plan…", shell.words.WORKING)
        elif not any(s.status == "waiting" and s.ticked for s in plan.steps) and any(s.status != "waiting"
                                                                                    for s in plan.steps if s.kind == core.CHANGE):
            text, tone = run.outcome(plan)
            self.banner.setText(text, tone)
        elif self.banner.tone == shell.words.WORKING:
            self.banner.setText("")

    def _row(self, step, last, changeable):
        frame = QFrame()
        frame.setObjectName("toolRowLast" if last else "toolRow")
        line = row(spacing=10, margins=(0, 8, 0, 8))
        frame.setLayout(line)
        left = column(spacing=2)
        check = QCheckBox(step.title)
        check.setChecked(step.ticked)
        check.setAccessibleName(step.title)
        tickable = changeable and step.kind == core.CHANGE and step.status == "waiting"
        check.setEnabled(tickable)
        if not tickable:
            # Only a change still waiting for your OK gets a tick box; anything else would look clickable and isn't.
            check.setFocusPolicy(Qt.NoFocus)
            check.setStyleSheet("QCheckBox{spacing:0px;color:#e8eef5;}"
                                "QCheckBox::indicator{width:0px;height:0px;border:none;margin:0px;}")
        check.toggled.connect(lambda on, s=step: self._tick(s, on))
        left.addWidget(check)
        caption = step.result or step.detail or step.action.plain
        if step.kind == core.CHANGE and step.status == "waiting" and step.action.undo:
            caption += "  " + step.action.undo
        note = shell.text(caption)
        note.setContentsMargins(28 if tickable else 0, 0, 0, 0)
        left.addWidget(note)
        line.addLayout(left, 1)
        side = column(spacing=3)
        kind = shell.text("Reads only" if step.kind == core.CHECK else "Change", "toolNote", wrap=False)
        kind.setAlignment(Qt.AlignRight)
        side.addWidget(kind, 0, Qt.AlignRight)
        word, tone = STATUS.get(step.status, STATUS["waiting"])
        if step.status == "waiting" and not self.live:
            word = "Off" if self.off else "Not run"
        side.addWidget(shell.pill(word, tone), 0, Qt.AlignRight)
        line.addLayout(side)
        frame.check = check
        return frame

    def _tick(self, step, on):
        step.ticked = bool(on)
        self.update_view()


def card(window, plan_dict, off=False):
    """The card for a plan saved with a chat message: live (with buttons) when this run of the app made it."""
    st = state_of(window)
    plan = st.plans.get((plan_dict or {}).get("id", ""))
    live = plan is not None
    plan = plan or core.plan_from_dict(plan_dict or {})
    if plan is None:
        return None
    widget = PlanCard(window, plan, live, off)
    if live:
        st.cards[plan.id] = [w for w in st.cards.get(plan.id, []) if _alive(w)] + [widget]
    return widget


def cards_of(window, plan_id):
    return [w for w in state_of(window).cards.get(plan_id, []) if _alive(w)]


def redraw(window, plan):
    for widget in cards_of(window, plan.id):  # the tab and the pop-out window each have their own copy
        widget.update_view()


def remember(window, plan):
    """Write the plan's current state into its chat message, so the chat shows what happened after a restart."""
    from gg_desktop import assistant_page
    st = assistant_page.state_of(window)
    for chat in st.chats:
        for message in chat["messages"]:
            if (message.get("plan") or {}).get("id") == plan.id:
                message["plan"] = core.plan_to_dict(plan)
                assistant_page.persist_chats(window)
                return


# ------------------------------------------------------------------ opening a tool for the owner
def open_target(window, target):
    """Open exactly the tool an answer's button names: a Toolbox window, the kit setup, Mod Bisect, the tour, a tab (with
    its inner tab), or send a request to the assistant ("ask:..."). Opening changes nothing; the tool asks before it does."""
    target = str(target or "")
    if target.startswith("ask:"):
        from gg_desktop import assistant_page
        if not assistant_page.views(window):
            window.navigate("AI Assistant")
        QTimer.singleShot(0, lambda: assistant_page.send(window, target[4:]))
        return True
    if target.startswith("tool:"):
        from gg_desktop import tools_actions
        QTimer.singleShot(0, lambda: tools_actions.run_action(window, target[5:]))
        return True
    if target in ("kit:easy", "kit:restore"):
        from gg_desktop import kit_easy_ui
        opener = kit_easy_ui.open_easy_setup if target == "kit:easy" else kit_easy_ui.open_easy_restore
        QTimer.singleShot(0, lambda: opener(window))
        return True
    if target == "bisect":
        from gg_desktop import fix_kit_page
        fix_kit_page.open_bisect(window)
        return True
    if target == "doctor":
        from gg_desktop import crashdoctor_ui
        QTimer.singleShot(0, lambda: crashdoctor_ui.open_doctor(window))
        return True
    if target == "tune":
        from gg_desktop import tune_ui
        QTimer.singleShot(0, lambda: tune_ui.open_tune(window))
        return True
    if target == "tour":
        QTimer.singleShot(0, window.open_welcome_tour)
        return True
    tab = target[4:] if target.startswith("tab:") else target
    route, _, inner = tab.partition("/")
    if route == "Hardware" and inner:
        window.hardware_tab = inner
    window.navigate(route)
    return True


_OPEN_WORDS = re.compile(r"\b(open|launch|start|bring up|pull up|show me|take me to|go to|use|set up|setup|make a|"
                         r"run the|get to)\b")


def opens_for(text):
    """The feature a request asks to open ("open the hash checker", "take me to drivers"), or None."""
    from gg_desktop import assistant_features as features
    t = " ".join(text.casefold().split())
    if not _OPEN_WORDS.search(t) or features.is_how_to(t) and not t.startswith(("open", "take me", "go to")):
        return None
    feature = features.find_feature(t)
    return feature if feature is not None and (feature.opens or feature.tab) else None


# ------------------------------------------------------------------ chat requests
def handle(window, text, shown=None):
    """Called by the AI Assistant before its built-in answers. True when the request became a plan or opened a tool.
    `shown` is what the chat shows as the person's message (a follow-up like "proceed" instead of the original request)."""
    feature = opens_for(text)
    leads = re.match(r"^(please |can you |could you )?(open|take me|go to|launch|show me|bring up|pull up|start)\b",
                     " ".join(text.casefold().split()))
    plan = None if feature is not None and leads else core.plan_for(text)
    if plan is None:
        if feature is None:
            return False
        from gg_desktop import assistant_engine as engine, assistant_features as features
        buttons = tuple(b for b in engine.guide_buttons(feature) if not b[0].startswith("Open "))
        answer = engine.Answer("feature", features.explain(feature) + "\n\nI've opened it for you.", handoffs=buttons + (("Open it again", feature.opens or
                                                                               feature.tab),))
        _post(window, text, answer, None)
        open_target(window, feature.opens or feature.tab)
        return True
    return post_plan(window, plan, shown or text)


def post_plan(window, plan, shown, text=None, sources=None):
    """Show a plan in the chat: a preview when running tools is off, the card with Run all when it is on. `text` is the
    Gravekeeper's own words for it (then they are said instead of the standard introduction)."""
    from gg_desktop import assistant_engine as engine
    on = enabled(window)
    tabs = []
    for step in plan.steps:
        tab = {"check_drivers": "Hardware", "install_drivers": "Hardware", "check_startup": "Hardware",
               "startup_off": "Hardware", "scan_library": "Overview"}.get(step.key, "More Tools")
        if tab not in tabs:
            tabs.append(tab)
    tab_names = {"More Tools": "Toolbox"}
    words = core.intro(plan, on)
    if text:
        words = text.strip() + ("" if on else "\n\nRunning tools is switched off, so this is only a preview. Say go "
                                             "ahead and I'll switch it on; nothing changes until you press Run all.")
    answer = engine.Answer("autopilot" if on else "autopilot_off", words, sources=sources or ("Game Grave tools",),
                           handoffs=() if text else tuple(("Open " + tab_names.get(t, t), t) for t in tabs[:3]))
    _post(window, shown, answer, plan if on else None, off_plan=None if on else plan)
    return True


def _post(window, question, answer, plan, off_plan=None, chat_title=None, prepared=False):
    from gg_desktop import assistant_actions as actions, assistant_page
    st = assistant_page.state_of(window)
    if not st.chats:
        st.chats = actions.load_chats(window.settings)
    chat = None
    if chat_title:
        chat = next((c for c in st.chats if c["title"] == chat_title), None)
        if chat is None:
            chat = actions.new_chat(time.time())
            chat["title"] = chat_title
            st.chats.insert(0, chat)
    else:
        chat = assistant_page.current_chat(window)
        if chat is None:
            chat = actions.new_chat(time.time())
            st.chats.insert(0, chat)
            st.current = chat["id"]
    shown = plan or off_plan
    actions.add_exchange(chat, question, answer, time.time(), plan=core.plan_to_dict(shown) if shown else None)
    if chat_title:
        chat["title"] = chat_title
    if plan is not None:
        state_of(window).plans[plan.id] = plan
    assistant_page.persist_chats(window)
    assistant_page.refresh_all(window)
    if plan is not None and not prepared:
        prepare(window, plan)
    return chat


def env_for(window, plan):
    st = state_of(window)
    if plan.id not in st.envs:
        env = run.default_env(window.settings.get("never_touch", []))
        env.mo2_profiles = lambda: run.mo2_profiles(getattr(window.inventory, "mods", []))
        fallback = getattr(env, "games", lambda: [])
        env.games = lambda: list(getattr(window.inventory, "games", []) or []) or fallback()
        st.envs[plan.id] = env
    return st.envs[plan.id]


def prepare(window, plan, after=None):
    for step in plan.steps:
        if step.kind == core.CHECK and step.key not in core.UI_CHECKS and step.status == "waiting":
            step.status = "running"
    redraw(window, plan)
    try:
        env = env_for(window, plan)
    except Exception as exc:
        for step in plan.steps:
            if step.status == "running":
                step.status, step.result = "problem", "Could not start: " + str(exc)[:200]
        redraw(window, plan)
        return
    running = game_running(window)

    def work(_progress):
        for step in plan.steps:
            if step.status == "running":
                step.status = "waiting"
        return run.prepare(plan, env, game_running=lambda: running)

    def done(_plan):
        remember(window, plan)
        redraw(window, plan)
        screen_checks = [s for s in plan.steps if s.key in core.UI_CHECKS and s.status == "waiting"]

        def next_check():
            if not screen_checks:
                remember(window, plan)
                redraw(window, plan)
                if after:
                    after(plan)
                return
            run_scan(window, plan, screen_checks.pop(0), lambda: (redraw(window, plan), next_check()))
        next_check()
    window.job(work, done, error_title="The plan's checks stopped")


def _screen_scan(window, key):
    """(start, still running, result sentence) for the scans that the tabs run themselves."""
    if key == "scan_leftovers":
        from gg_desktop import grave_page as page
        state = page.state_of(window)
        return (lambda: page.scan(window, automatic=True), lambda: state.busy,
                lambda: (state.report.summary() + ". See Graveyard.") if state.report else "No leftovers found.")
    if key == "scan_storage":
        from gg_desktop import other_storage_page as page
        state = page.state_of(window)
        return (lambda: page.scan(window), lambda: state.busy,
                lambda: (state.report.summary() + ". See Other Storage.") if state.report else "Nothing found.")
    if key == "scan_captures":
        from gg_desktop import captures_page as page
        state = page.state_of(window)
        return (lambda: page.scan(window, automatic=True), lambda: bool(state.busy),
                lambda: (state.report.summary() + ". See Captures.") if state.report else "No captures found.")
    return (window.start_scan, lambda: window.scanning,
            lambda: f"Scan finished: {len(window.inventory.games):,} games, {len(window.inventory.mods):,} mod "
                    "locations.")


def run_scan(window, plan, step, then):
    if game_running(window):
        step.status, step.result = "skipped", "A game is running, so the scan waits."
        then()
        return
    step.status = "running"
    redraw(window, plan)
    start, busy, result = _screen_scan(window, step.key)
    if window.scanning or window.cleaning:
        step.status, step.result = "problem", "Another scan or clean-up is running. Ask again when it finishes."
        then()
        return
    try:
        start()
    except Exception as exc:
        step.status, step.result = "problem", "The scan could not start: " + str(exc)[:160]
        then()
        return
    timer = QTimer(window)
    timer.setInterval(500)

    def poll():
        if busy():
            return
        timer.stop()
        timer.deleteLater()
        step.status, step.result = "done", result()
        then()
    timer.timeout.connect(poll)
    timer.start()


def cancel_plan(window, plan_id):
    st = state_of(window)
    plan = st.plans.get(plan_id)
    if plan is None or st.running == plan_id:
        return
    for step in plan.steps:
        if step.status == "waiting":
            step.status, step.result = "skipped", "Cancelled by you."
    remember(window, plan)
    redraw(window, plan)
    window.status.setText("Plan cancelled. Nothing was changed.")


def run_all(window, plan_id):
    st = state_of(window)
    plan = st.plans.get(plan_id)
    if plan is None or st.running:
        return
    if game_running(window):
        window.info("A game is running", "Game Grave does not run plans while a game is open. Try again after you close it.")
        return
    order = core.run_order(plan)
    if not order:
        return
    lines = core.confirmation(plan)
    if lines and not window.confirm("Run this plan", "Game Grave will make these changes, one after another:\n\n" + lines +
                                    "\n\nEach one reads your PC again first and is written to the activity log."):
        return
    st.running = plan.id
    env = env_for(window, plan)
    window.status.setText("Running the plan…")

    def finish():
        st.running = ""
        remember(window, plan)
        redraw(window, plan)
        text, tone = run.outcome(plan)
        window.status.setText(text)
        env.log(f"Plan \"{plan.request[:120]}\": {text}", "Plan finished")
        from gg_desktop import comfort
        comfort.notify(window, "Plan finished", f"{plan.request[:80]}: {text}", tone, "AI Assistant",
                       toast=window.current_route != "AI Assistant")
        from gg_desktop import assistant_page
        assistant_page.after_plan(window, plan)          # a fix for a game is remembered, then "Did that fix it?"

    def next_step():
        if not order:
            finish()
            return
        if game_running(window):
            for step in order:
                step.status, step.result = "skipped", "A game started, so Game Grave stopped here."
            order.clear()
            finish()
            return
        step = order.pop(0)
        if step.key in core.UI_CHECKS:
            run_scan(window, plan, step, lambda: (redraw(window, plan), next_step()))
            return
        step.status = "running"
        redraw(window, plan)

        def work(_progress):
            if step.kind == core.CHECK:
                step.status = "waiting"
                run._check(step, env, plan)
                return step
            return run.run_change(step, env)

        def done(_step):
            remember(window, plan)
            redraw(window, plan)
            next_step()
        window.job(work, done, error_title="The plan stopped")
    next_step()


def save_routine(window, plan_id):
    plan = state_of(window).plans.get(plan_id)
    if plan is None or plan.schedule is None:
        return
    routines = core.load_routines(window.settings)
    if len(routines) >= core.MAX_ROUTINES:
        window.info("Too many routines", f"Game Grave keeps up to {core.MAX_ROUTINES} routines. Delete one first.")
        return
    suggested = core.describe_schedule(plan.schedule).replace(" at ", " ").split(" ")[0:2]
    name, ok = QInputDialog.getText(window, "Name this routine", "Name:", text=" ".join(suggested) + " routine")
    if not ok:
        return
    routine, left_out = core.routine_from_plan(plan, name.strip() or "My routine", datetime.now())
    if not routine["steps"]:
        window.info("Nothing to save", "None of these steps can run on a schedule.")
        return
    if not _save(window, core.with_routines(window.settings, routines + [routine])):
        return
    note = "Saved: " + core.routine_line(routine, datetime.now()) + " Changes will wait for your OK."
    if left_out:
        note += " Left out (they need you there): " + ", ".join(left_out) + "."
    for widget in cards_of(window, plan.id):
        widget.banner.setText(note, shell.words.GOOD)
        widget.save_button.hide()
    sync_panel(window)


# ------------------------------------------------------------------ the Automation panel
def build_panel(window, accent):
    from gg_desktop.reference_widgets import icon
    from gg_desktop.settings_page import Switch
    box, lay = panel(kind="fileFilterPanel", padding=9, spacing=5)
    accent(box, "assistantAutomation", "cyan")
    head = row(spacing=6)
    pic = QLabel()
    pic.setPixmap(icon("play", "#13bcf5", 18).pixmap(18, 18))
    head.addWidget(pic)
    head.addWidget(label("Automation", "sectionTitle"), 1)
    switch = Switch(enabled(window), name="Let the assistant run tools")
    switch.setToolTip("When on, ask things like \"get my PC ready to play\" and the assistant plans it with Game Grave's own "
                      "tools. Checks run straight away; changes wait for Run all.")
    head.addWidget(switch)
    lay.addLayout(head)
    status = label("", "caption", wrap=True)
    lay.addWidget(status)
    routines = column(spacing=4)
    lay.addLayout(routines)
    window.autopilot_switch, window.autopilot_status, window.autopilot_routines = switch, status, routines

    def toggled(on):
        _save(window, dict(window.settings, **{core.SETTING: bool(on)}))
        sync_panel(window)
        from gg_desktop import assistant_page
        assistant_page.refresh_all(window)
    switch.toggled.connect(toggled)
    sync_panel(window)
    return box


def sync_panel(window):
    status = getattr(window, "autopilot_status", None)
    if not _alive(status):
        return
    on = enabled(window)
    status.setText("On. Ask \"get my PC ready to play\" or \"clean up temp files\". Checks run straight away; changes "
                   "wait for Run all." if on else
                   "Off. Switch on to let the assistant run Game Grave's own tools when you ask. It never types commands.")
    box = window.autopilot_routines
    while box.count():
        item = box.takeAt(0)
        if item.widget():
            item.widget().hide()
            item.widget().deleteLater()
    routines = core.load_routines(window.settings)
    now = datetime.now()
    if not routines:
        box.addWidget(label("No routines yet. Ask: \"every Sunday at 9pm clean temp files and check drivers\".", "caption",
                            wrap=True))
        return
    for routine in routines:
        frame = QFrame()
        frame.setObjectName("toolCard")
        frame.setStyleSheet("QFrame#toolCard{background:#09121a;border:1px solid #1b2836;border-radius:8px;}")
        lay = column(spacing=3, margins=(8, 6, 8, 6))
        frame.setLayout(lay)
        name = label(routine["name"] + ("" if routine["on"] else "  (paused)"), "subtle")
        name.setStyleSheet("color:#ffffff;font-weight:700;font-size:12px;")
        lay.addWidget(name)
        line = label(core.routine_line(routine, now), "caption", wrap=True)
        lay.addWidget(line)
        if routine.get("last_note"):
            lay.addWidget(label("Last time: " + routine["last_note"], "caption", wrap=True))
        actions = row(spacing=4)
        for caption, fn, tip in (("Run now", lambda _=False, r=routine["id"]: run_routine_now(window, r),
                                  "Run its checks now; changes wait for Run all"),
                                 ("Resume" if not routine["on"] else "Pause",
                                  lambda _=False, r=routine["id"]: pause_routine(window, r), "Pause or resume the schedule"),
                                 ("Delete", lambda _=False, r=routine["id"]: delete_routine(window, r), "Delete this routine")):
            control = button(caption, fn, tip=tip)
            control.setFixedHeight(24)
            control.setStyleSheet("font-size:11px;padding:0 6px;")
            control.setAccessibleName(f"{caption} {routine['name']}")
            actions.addWidget(control)
        lay.addLayout(actions)
        frame.routine_id = routine["id"]
        box.addWidget(frame)


def _update_routine(window, routine_id, **changes):
    routines = core.load_routines(window.settings)
    for routine in routines:
        if routine["id"] == routine_id:
            routine.update(changes)
    return _save(window, core.with_routines(window.settings, routines))


def pause_routine(window, routine_id):
    routine = next((r for r in core.load_routines(window.settings) if r["id"] == routine_id), None)
    if routine is not None and _update_routine(window, routine_id, on=not routine["on"]):
        sync_panel(window)


def delete_routine(window, routine_id):
    routine = next((r for r in core.load_routines(window.settings) if r["id"] == routine_id), None)
    if routine is None or not window.confirm("Delete routine", f"Delete the routine \"{routine['name']}\"? Nothing it did "
                                             "before is changed."):
        return
    if _save(window, core.with_routines(window.settings, [r for r in core.load_routines(window.settings)
                                                          if r["id"] != routine_id])):
        sync_panel(window)


def run_routine_now(window, routine_id):
    routine = next((r for r in core.load_routines(window.settings) if r["id"] == routine_id), None)
    if routine is None:
        return
    if not enabled(window):
        window.info("Automation is off", "Switch on \"Let the assistant run tools\" first.")
        return
    from gg_desktop import assistant_engine as engine
    plan = core.routine_plan(routine)
    answer = engine.Answer("autopilot", "Running the routine's checks now. Changes wait for Run all.",
                           sources=("Game Grave tools",))
    _post(window, "Run my routine: " + routine["name"], answer, plan)


# ------------------------------------------------------------------ routines on a schedule
def install(window):
    """Start the routine timer. It wakes every 5 minutes and does nothing unless a routine is due and the PC is free."""
    if getattr(window, "reference_preview", False):
        return
    st = state_of(window)
    st.timer = QTimer(window)
    st.timer.setInterval(TICK_MS)
    st.timer.timeout.connect(lambda: tick(window))
    st.timer.start()
    QTimer.singleShot(FIRST_TICK_MS, lambda: tick(window))


def tick(window, now=None):
    """One look at the routines. Returns the routine it started, or None."""
    st = state_of(window)
    if not enabled(window) or st.busy or st.running or window.scanning or window.cleaning or game_running(window):
        return None
    now = now or datetime.now()
    routine = next((r for r in core.load_routines(window.settings) if core.is_due(r, now)), None)
    if routine is None:
        return None
    if not _update_routine(window, routine["id"], last_run=now.timestamp()):
        return None
    st.busy = True
    plan = core.routine_plan(routine)
    st.plans[plan.id] = plan

    def after(done_plan):
        st.busy = False
        checks = "; ".join(s.result.rstrip(".") for s in done_plan.steps if s.kind == core.CHECK and s.result)
        waiting = [s for s in done_plan.steps if s.kind == core.CHANGE and s.ticked and s.status == "waiting"]
        note = (checks + ". " if checks else "") + (f"{len(waiting)} change" + ("" if len(waiting) == 1 else "s") +
                                                  " waiting for your OK." if waiting else "No changes needed.")
        _update_routine(window, routine["id"], last_note=note[:300])
        sync_panel(window)
        from gg_desktop import assistant_engine as engine
        answer = engine.Answer("autopilot", ("Your routine ran its checks. These changes are waiting for your OK." if waiting
                                             else "Your routine ran its checks. Nothing needs changing."),
                               sources=("Game Grave tools",))
        chat = _post(window, f"Routine: {routine['name']} ({core.describe_schedule(done_plan.schedule)})", answer,
                     done_plan, chat_title=ROUTINES_CHAT, prepared=True)
        show_notice(window, routine["name"], note, chat["id"], done_plan.id if waiting else "")
        from gg_desktop import comfort
        comfort.notify(window, "Routine: " + routine["name"], note, "warn" if waiting else "good", "AI Assistant",
                       toast=False)
    prepare(window, plan, after=after)
    return routine


def show_notice(window, name, note, chat_id, plan_id):
    st = state_of(window)
    if _alive(st.notice):
        st.notice.hide()
        st.notice.deleteLater()
    notice = QFrame(window)
    notice.setObjectName("autopilotNotice")
    notice.setStyleSheet(shell.STYLE + "QFrame#autopilotNotice{background:#0a141d;border:1px solid #13bcf5;border-radius:12px;}")
    lay = column(spacing=8, margins=(14, 12, 14, 12))
    notice.setLayout(lay)
    head = row(spacing=10)
    head.addWidget(shell.badge("clock", shell.HEX["cyan"], 30), 0, Qt.AlignTop)
    words = column(spacing=2)
    words.addWidget(shell.text("Routine: " + name, "toolLead"))
    words.addWidget(shell.text(note))
    head.addLayout(words, 1)
    lay.addLayout(head)
    buttons = row(spacing=8)

    def close():
        notice.hide()
        notice.deleteLater()

    def review():
        close()
        from gg_desktop import assistant_page
        assistant_page.state_of(window).current = chat_id
        if assistant_page.popout_of(window) is not None or (window.current_route == "AI Assistant"
                                                            and assistant_page.live(window)):
            assistant_page.refresh_all(window)
        else:
            window.navigate("AI Assistant")

    def skip():
        plan = st.plans.get(plan_id)
        if plan is not None:
            cancel_plan(window, plan_id)
        close()
    if plan_id:
        buttons.addWidget(button("Skip", skip, tip="Leave everything as it is this time"))
        buttons.addStretch()
        buttons.addWidget(button("Review and OK", review, kind="primary", tip="Open the plan in AI Assistant"))
    else:
        buttons.addStretch()
        buttons.addWidget(button("Show", review, tip="Open the results in AI Assistant"))
        buttons.addWidget(button("OK", close, kind="primary"))
        QTimer.singleShot(20000, lambda: _alive(notice) and close())
    lay.addLayout(buttons)
    notice.setFixedWidth(380)
    notice.adjustSize()
    area = window.rect()
    notice.move(area.width() - notice.width() - 20, area.height() - notice.height() - 20)
    notice.show()
    notice.raise_()
    notice.review, notice.skip = review, skip
    st.notice = notice
    QApplication.alert(window, 0)
    return notice
