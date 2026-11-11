"""Local AI panel on the AI Assistant tab, and the background answering. Qt layer over local_ai_core / local_ai_prompt.

The owner picks Small, Medium or Large, presses Download (asked first, sizes and sources named), and can switch the local
model on or off or remove it. Answers: the built-in answer is computed first; with the local model on, the model rewrites
it in plain language from the same facts in a background job. If the model is off, missing, busy, breaks a rule, fails or
a game is running, the built-in answer is shown and says why.
"""
from __future__ import annotations

import threading
from types import SimpleNamespace

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QComboBox, QLabel, QProgressBar, QWidget

from core import human_size, log_event
from gg_desktop import local_ai_core as ai
from gg_desktop import local_ai_prompt as prompt
from gg_desktop.reference_widgets import icon
from gg_desktop.settings_page import Switch
from gg_desktop.widgets import button, column, label, panel, row

IDLE_STOP_MS = 5 * 60 * 1000
GAME_CHECK_MS = 30 * 1000


# ------------------------------------------------------------------ state
def state_of(window):
    if not hasattr(window, "_local_ai"):
        window._local_ai = SimpleNamespace(server=None, lock=threading.Lock(), busy=False, downloading=False,
                                           cancel=threading.Event(), timer=None, widgets=None)
    return window._local_ai


def chosen(window):
    key = window.settings.get("local_ai_model")
    return key if key in ai.BY_KEY else ai.DEFAULT_MODEL


def enabled(window):
    return bool(window.settings.get("local_ai_enabled")) and ready(window)


def ready(window):
    return chosen(window) in ai.installed_models() and bool(ai.installed_runtime())


def game_running(window):
    tracker = getattr(window, "_games_tracker", None)
    return bool(tracker is not None and getattr(getattr(tracker, "ledger", None), "active", None))


def model_name(key):
    choice = ai.BY_KEY[key]
    return f"{choice.label} ({choice.repo.split('/')[-1].replace('-GGUF', '')})"


# ------------------------------------------------------------------ panel
def build_panel(window, accent):
    st = state_of(window)
    box, lay = panel(kind="fileFilterPanel", padding=9, spacing=5)
    accent(box, "assistantLocalAI", "green")
    head = row(spacing=6)
    pic = QLabel()
    pic.setPixmap(icon("sparkles", "#32d67a", 18).pixmap(18, 18))
    head.addWidget(pic)
    head.addWidget(label("Local AI", "sectionTitle"), 1)
    switch = Switch(bool(window.settings.get("local_ai_enabled")), name="Use the local AI model for answers")
    switch.setToolTip("When on, a downloaded AI model on this PC writes the answers in plain language. Off: the "
                      "built-in answers.")
    head.addWidget(switch)
    lay.addLayout(head)
    status = label("", "caption", wrap=True)
    lay.addWidget(status)
    combo = QComboBox()
    combo.setAccessibleName("Local AI model size")
    for choice in ai.MODELS:
        combo.addItem(choice.title + (" · recommended" if choice.key == ai.DEFAULT_MODEL else ""), choice.key)
        combo.setItemData(combo.count() - 1, f"{choice.blurb} Needs about {choice.ram_gb} GB of memory.", 3)
    combo.setCurrentIndex(max(0, combo.findData(chosen(window))))
    lay.addWidget(combo)
    buttons = row(spacing=6)
    get = button("Download", lambda: download(window), kind="primary")
    remove = button("Remove", lambda: remove_model(window))
    cancel = button("Cancel", lambda: st.cancel.set())
    for b in (get, remove, cancel):
        b.setFixedHeight(28)
        buttons.addWidget(b)
    lay.addLayout(buttons)
    bar = QProgressBar()
    bar.setFixedHeight(8)
    bar.setTextVisible(False)
    bar.setRange(0, 1000)
    lay.addWidget(bar)
    lay.addWidget(label("Runs on this PC only; nothing you ask leaves it. Pauses while a game runs. The assistant never "
                        "deletes, moves or changes anything.", "warning", wrap=True))
    lay.addStretch()
    st.widgets = SimpleNamespace(switch=switch, status=status, combo=combo, get=get, remove=remove, cancel=cancel, bar=bar)

    def picked(_i):
        window.settings = dict(window.settings, local_ai_model=combo.currentData())
        _save(window)
        stop(window)
        sync(window)
    combo.currentIndexChanged.connect(picked)

    def toggled(on):
        if on and not ready(window):
            switch.setChecked(False)
            window.status.setText("Download a model first. Pick a size, then press Download.")
            return
        window.settings = dict(window.settings, local_ai_enabled=bool(on))
        _save(window)
        if not on:
            stop(window)
        sync(window)
    switch.toggled.connect(toggled)
    sync(window)
    return box


def _alive(widget):
    try:
        widget.objectName()
        return True
    except RuntimeError:
        return False


def sync(window):
    st = state_of(window)
    w = st.widgets
    if w is None or not _alive(w.status):
        return
    key = chosen(window)
    have = key in ai.installed_models()
    engine = ai.installed_runtime()
    if st.downloading:
        text = "Downloading…"
    elif have and engine:
        size = human_size(ai.model_path(key).stat().st_size)
        text = (f"{model_name(key)} is ready ({size}). " +
                ("Answers are written by it." if window.settings.get("local_ai_enabled") else "Switch it on to use it."))
    elif have:
        text = f"{model_name(key)} is downloaded; the AI engine still needs downloading (about 30 MB)."
    else:
        others = [ai.BY_KEY[k].label for k in ai.installed_models()]
        text = (f"Not downloaded. {ai.BY_KEY[key].blurb} Answers use the built-in lookup until then." +
                (f" Also on this PC: {', '.join(others)}." if others else ""))
    w.status.setText(text)
    w.get.setVisible(not st.downloading and not (have and engine))
    w.get.setText("Download" if not have else "Finish download")
    w.remove.setVisible(not st.downloading and have)
    w.cancel.setVisible(st.downloading)
    w.bar.setVisible(st.downloading)
    w.combo.setEnabled(not st.downloading)
    w.switch.blockSignals(True)
    w.switch.setChecked(bool(window.settings.get("local_ai_enabled")) and have and bool(engine))
    w.switch.blockSignals(False)
    w.switch.setEnabled(have and bool(engine) and not st.downloading)


def _save(window):
    from gg_desktop import assistant_page
    assistant_page.save(window, window.settings)


# ------------------------------------------------------------------ download / remove
def download(window):
    st = state_of(window)
    if st.downloading:
        return
    key = chosen(window)
    choice = ai.BY_KEY[key]
    need_engine = not ai.installed_runtime()
    need_model = key not in ai.installed_models()
    parts = []
    if need_model:
        parts.append(f"the {choice.label} AI model, Qwen3 ({choice.approx_bytes / ai.GB:.1f} GB) from Hugging Face "
                     f"({choice.repo})")
    if need_engine:
        parts.append(f"llama.cpp's AI engine {ai.RUNTIME_TAG} (about 30 MB) from GitHub (ggml-org/llama.cpp)")
    if not parts:
        return
    if not window.confirm("Download the local AI model?",
                          "Game Grave will download " + " and ".join(parts) + f" into\n{ai.ai_dir()}\n\n"
                          "Each file is checked against the SHA-256 its publisher records and deleted if it doesn't "
                          f"match. It needs about {choice.ram_gb} GB of memory to run. Nothing else is installed, and "
                          "Remove takes it all away again."):
        return
    st.downloading = True
    st.cancel.clear()
    sync(window)
    window.status.setText("Downloading the local AI model. You can keep using Game Grave.")

    def work(progress):
        steps = (["engine"] if need_engine else []) + (["model"] if need_model else [])
        for i, step in enumerate(steps):
            def report(done, total, i=i):
                share = done / total if total else 0
                progress(int((i + share) / len(steps) * 1000), step)
            if step == "engine":
                try:
                    ai.install_runtime("vulkan", report, st.cancel.is_set)
                except ai.Canceled:
                    raise
                except Exception:
                    ai.install_runtime("cpu", report, st.cancel.is_set)
            else:
                ai.install_model(key, report, st.cancel.is_set)
        return ""

    def progressed(value, _step):
        w = st.widgets
        if w is not None and _alive(w.bar):
            w.bar.setValue(value)

    def finished(_result):
        st.downloading = False
        window.settings = dict(window.settings, local_ai_enabled=True, local_ai_model=key)
        _save(window)
        log_event("local_ai_download", f"Downloaded the local AI model ({model_name(key)})", result="downloaded",
                  source="assistant")
        window.status.setText(f"Local AI ready: {model_name(key)}. Ask a question to try it.")
        sync(window)

    def failed(message):
        st.downloading = False
        canceled = st.cancel.is_set()
        window.status.setText("Download canceled; nothing was kept." if canceled else
                              "The local AI download didn't finish: " + message[:140])
        sync(window)

    _job(window, work, finished, failed, progressed)


def remove_model(window):
    key = chosen(window)
    path = ai.model_path(key)
    if not path.is_file():
        return
    last = ai.installed_models() == [key]
    what = f"the {ai.BY_KEY[key].label} model ({human_size(path.stat().st_size)})"
    if last and ai.installed_runtime():
        what += " and the AI engine"
    if not window.confirm("Remove the local AI model?", f"This deletes {what} from\n{ai.ai_dir()}\n\nThe assistant goes "
                          "back to its built-in answers. You can download it again any time.", destructive=True):
        return
    stop(window)
    freed = ai.remove_all() if last else ai.remove_model(key)
    window.settings = dict(window.settings, local_ai_enabled=False if last else window.settings.get("local_ai_enabled"))
    _save(window)
    log_event("local_ai_remove", f"Removed {what} ({human_size(freed)})", result="removed", source="assistant")
    window.status.setText(f"Removed {what}.")
    sync(window)


def _job(window, fn, done, failed, progress=None):
    """Like window.job, but failures come back here instead of a message box."""
    from gg_desktop.app import Job
    job = Job(fn)
    key = id(job)
    window.workers[key] = job

    def ok(result):
        window.workers.pop(key, None)
        done(result)

    def bad(message):
        window.workers.pop(key, None)
        failed(message)
    job.signals.done.connect(ok)
    job.signals.failed.connect(bad)
    if progress:
        job.signals.progress.connect(progress)
    window.pool.start(job)


# ------------------------------------------------------------------ answering
def answer_async(window, question, base_answer, facts, history, deliver):
    """Ask the local model in the background, then call deliver(answer). Always delivers exactly once."""
    from gg_desktop import assistant_engine as engine
    st = state_of(window)
    if game_running(window):
        deliver(_with_note(base_answer, "Local AI pauses while a game is running, so this is the built-in answer."))
        return
    if st.busy:
        deliver(_with_note(base_answer, "Local AI was still answering the last question, so this is the built-in answer."))
        return
    key = chosen(window)
    st.busy = True

    def work(_progress):
        with st.lock:
            server = st.server
            if server is None or server.model_key != key or not server.running:
                if server is not None:
                    server.stop()
                server = st.server = ai.LocalServer(key)
                ai.start_best(server)
            return server.chat(prompt.build_messages(question, base_answer, facts, history))

    def done(reply):
        st.busy = False
        text = prompt.clean_reply(reply)
        _arm_idle(window)
        if not text:
            deliver(_with_note(base_answer, "The local AI's reply didn't keep Game Grave's rules, so this is the "
                                            "built-in answer."))
            return
        deliver(engine.Answer(base_answer.intent, text, base_answer.rows, base_answer.note,
                              tuple(base_answer.sources) + (f"Local AI: {ai.BY_KEY[key].label}",), base_answer.handoffs))

    def failed(message):
        st.busy = False
        stop(window)
        deliver(_with_note(base_answer, "Local AI couldn't answer (" + message.split(":", 1)[-1].strip()[:120] +
                           "), so this is the built-in answer."))

    _job(window, work, done, failed)


def _with_note(answer, note):
    from gg_desktop import assistant_engine as engine
    joined = (answer.note + " " + note).strip() if answer.note else note
    return engine.Answer(answer.intent, answer.text, answer.rows, joined, answer.sources, answer.handoffs)


def _arm_idle(window):
    st = state_of(window)
    if st.timer is None:
        st.timer = QTimer(window)
        st.timer.setInterval(GAME_CHECK_MS)
        st.timer.timeout.connect(lambda: _tick(window))
    st.timer.start()


def _tick(window):
    st = state_of(window)
    server = st.server
    if server is None or not server.running:
        st.timer.stop()
        return
    import time
    if st.busy:
        return
    if game_running(window) or time.monotonic() - server.last_used > IDLE_STOP_MS / 1000:
        stop(window)


def stop(window):
    st = state_of(window)
    server, st.server = st.server, None
    if server is not None:
        threading.Thread(target=server.stop, daemon=True).start()
    if st.timer is not None:
        st.timer.stop()


def shutdown(window):
    """Called when Game Grave closes: the model never outlives the app."""
    st = state_of(window)
    st.cancel.set()
    server, st.server = st.server, None
    if server is not None:
        server.stop()
