"""Everyday comforts on screen: Back, keyboard shortcuts, the notification centre on the bell, a pop-up when a job finishes,
the "Paused while you play" note, Copy diagnostics, and the tray icon. Rules live in `comfort_core`.

None of this changes anything on the PC except two switches the owner flips in the tray menu: "Keep running when closed"
(a Game Grave setting) and "Start with Windows" (one value in the owner's own Run key, removed again when switched off, and
written to the activity log).
"""
from __future__ import annotations

import os
import platform
import sys
from types import SimpleNamespace

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import QDialog, QFrame, QLabel, QMenu, QScrollArea, QSystemTrayIcon, QWidget
from shiboken6 import isValid

from gg_desktop import comfort_core as core
from gg_desktop.widgets import button, column, label, row

TOAST_MS = 8000
PAUSE_CHECK_MS = 10_000
TONE = {"good": "#32d67a", "warn": "#f6be24", "bad": "#ff5a6e", "info": "#13bcf5"}


def state_of(window):
    if not hasattr(window, "_comfort"):
        window._comfort = SimpleNamespace(history=core.History(), going_back=False, notices=None, toast=None,
                                          tray=None, errors=[], pause_timer=None, told_tray=False)
    return window._comfort


def _alive(widget):
    return widget is not None and isValid(widget)


def _save(window, settings):
    from core import save_settings
    try:
        save_settings(settings)
    except (OSError, ValueError):
        return False
    window.settings = settings
    return True


# ------------------------------------------------------------------ install
def install(window, topbox, bell):
    """Called once by the window after the shell is built."""
    st = state_of(window)
    st.notices = core.load_notices(window.settings)
    from gg_desktop.reference_widgets import tool
    window.back_button = tool("", "back", lambda: go_back(window), kind="chromeButton",
                              tip="Back to the tab you were on (Alt+Left)")
    window.back_button.setAccessibleName("Back")
    window.back_button.setEnabled(False)
    topbox.insertWidget(0, window.back_button)
    window.bell_button = bell
    bell.setToolTip("Notifications and scan status (Ctrl+Shift+N)")
    bell.setAccessibleName("Notifications")
    window.bell_badge = QLabel(bell)
    window.bell_badge.setObjectName("bellBadge")
    window.bell_badge.setAlignment(Qt.AlignCenter)
    window.bell_badge.setStyleSheet("QLabel#bellBadge{background:#ff284a;color:white;border-radius:7px;font-size:9px;"
                                    "font-weight:800;padding:0 3px;}")
    window.bell_badge.setFixedHeight(14)
    window.bell_badge.setAttribute(Qt.WA_TransparentForMouseEvents)
    sync_badge(window)
    window.paused_chip = QLabel("")
    window.paused_chip.setObjectName("pausedChip")
    window.paused_chip.setStyleSheet("QLabel#pausedChip{color:#f6be24;background:rgba(246,190,36,28);border:1px solid "
                                     "rgba(246,190,36,90);border-radius:10px;padding:1px 9px;font-size:11px;font-weight:700;}")
    window.paused_chip.setToolTip("A game is running, so Game Grave has paused its own background work (scans it starts by "
                                  "itself, routines, the local AI). Anything you start yourself still runs.")
    window.paused_chip.hide()
    at = topbox.indexOf(window.scan_time) if hasattr(window, "scan_time") else -1
    topbox.insertWidget(at + 1 if at >= 0 else topbox.count(), window.paused_chip)
    for sequence, action in (("Alt+Left", lambda: go_back(window)), ("Ctrl+/", lambda: show_shortcuts(window)),
                             ("Ctrl+Shift+N", lambda: open_notices(window))):
        QShortcut(QKeySequence(sequence), window, activated=action)
    for n in range(1, 10):
        QShortcut(QKeySequence(f"Ctrl+{n}"), window, activated=lambda n=n: open_number(window, n))
    window.installEventFilter(_MouseBack(window))
    _wrap_errors(window)
    st.pause_timer = QTimer(window)
    st.pause_timer.setInterval(PAUSE_CHECK_MS)
    st.pause_timer.timeout.connect(lambda: sync_paused(window))
    st.pause_timer.start()
    install_tray(window)


class _MouseBack(QObject):
    """The mouse's side "back" button goes back too."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.BackButton:
            go_back(self.window)
            return True
        return False


def _wrap_errors(window):
    """Remember the last error messages shown, for Copy diagnostics."""
    original = window.error
    st = state_of(window)

    def error(title, message):
        st.errors.append(f"{title}: {str(message)[:200]}")
        del st.errors[:-20]
        return original(title, message)
    window.error = error


# ------------------------------------------------------------------ back and numbers
def visited(window, route):
    st = state_of(window)
    st.history.visit(route, going_back=st.going_back)
    st.going_back = False
    if _alive(getattr(window, "back_button", None)):
        window.back_button.setEnabled(st.history.can_back())
        target = st.history.stack[-1] if st.history.stack else ""
        from gg_desktop.nav_groups import display_name
        window.back_button.setToolTip(f"Back to {display_name(target)} (Alt+Left)" if target else "Back (Alt+Left)")


def go_back(window):
    st = state_of(window)
    route = st.history.back()
    if route:
        st.going_back = True
        window.navigate(route)


def open_number(window, n):
    from gg_desktop import nav_groups
    visible = {route for route, control in window.nav_buttons.items() if not control.isHidden()} \
        if hasattr(window, "nav_buttons") else set()
    routes = core.numbered_routes(nav_groups.routes(), visible or set(nav_groups.routes()))
    if 1 <= n <= len(routes):
        window.navigate(routes[n - 1])


def show_shortcuts(window):
    dialog = QDialog(window)
    dialog.setWindowTitle("Keyboard shortcuts")
    lay = column(spacing=8, margins=(20, 18, 20, 16))
    dialog.setLayout(lay)
    lay.addWidget(label("Keyboard shortcuts", "sectionTitle"))
    for keys, what in core.SHORTCUTS:
        line = row(spacing=12)
        key = label(keys, "detailValue")
        key.setFixedWidth(150)
        key.setStyleSheet("font-family:Consolas,monospace;color:#ffffff;font-weight:700;")
        line.addWidget(key)
        line.addWidget(label(what, "subtle", wrap=True), 1)
        lay.addLayout(line)
    foot = row(spacing=8)
    foot.addStretch()
    foot.addWidget(button("Close", dialog.accept, kind="primary"))
    lay.addLayout(foot)
    window._shortcuts_dialog = dialog
    dialog.exec()


# ------------------------------------------------------------------ notices
def notify(window, title, text, tone="good", target="", action=None, toast=True):
    """Add one notice to the bell and pop it up. `action` is (caption, function) for one extra button (Undo)."""
    st = state_of(window)
    if st.notices is None:
        st.notices = core.load_notices(window.settings)
    item = core.notice(title, text, tone, target)
    st.notices = core.add_notice(st.notices, item)
    _save(window, core.with_notices(window.settings, st.notices))
    sync_badge(window)
    if toast and not getattr(window, "reference_preview", False):
        show_toast(window, item, action)
    return item


def sync_badge(window):
    badge = getattr(window, "bell_badge", None)
    if not _alive(badge):
        return
    count = core.unread(state_of(window).notices or [])
    badge.setText(str(count) if count < 100 else "99+")
    badge.adjustSize()
    badge.setFixedWidth(max(14, badge.sizeHint().width()))
    bell = window.bell_button
    badge.move(max(0, bell.width() - badge.width() - 1), 1)
    badge.setVisible(count > 0)


def _open(window, target):
    if not target:
        return
    from gg_desktop import autopilot_ui
    autopilot_ui.open_target(window, target)


def show_toast(window, item, action=None):
    st = state_of(window)
    minimized = window.isMinimized() or not window.isVisible()
    if minimized and st.tray is not None:
        st.tray.showMessage(item.title, item.text, QSystemTrayIcon.Information, 6000)
        return None
    if _alive(st.toast):
        st.toast.hide()
        st.toast.deleteLater()
    color = TONE.get(item.tone, TONE["info"])
    toast = QFrame(window)
    toast.setObjectName("comfortToast")
    toast.setStyleSheet(f"QFrame#comfortToast{{background:#0a131c;border:1px solid {color};border-radius:12px;}}"
                        "QLabel{background:transparent;color:#e8eef5;}")
    lay = column(spacing=6, margins=(14, 10, 10, 10))
    toast.setLayout(lay)
    top = row(spacing=8)
    dot = QLabel("●")
    dot.setStyleSheet(f"color:{color};font-size:14px;")
    top.addWidget(dot, 0, Qt.AlignTop)
    words = column(spacing=1)
    title = label(item.title, "detailValue")
    title.setStyleSheet("font-weight:800;color:#ffffff;font-size:13px;")
    words.addWidget(title)
    words.addWidget(label(item.text, "caption", wrap=True))
    top.addLayout(words, 1)
    close = button("×", lambda: (toast.hide(), toast.deleteLater()))
    close.setFixedSize(24, 24)
    close.setAccessibleName("Close the pop-up")
    top.addWidget(close, 0, Qt.AlignTop)
    lay.addLayout(top)
    if action or item.target:
        buttons = row(spacing=6)
        buttons.addStretch()
        if action:
            extra = button(action[0], lambda: (action[1](), toast.hide(), toast.deleteLater()), kind="primary")
            extra.setAccessibleName(action[0])
            buttons.addWidget(extra)
            toast.action_button = extra
        if item.target:
            buttons.addWidget(button("Open", lambda: (_open(window, item.target), toast.hide(), toast.deleteLater())))
        lay.addLayout(buttons)
    toast.setFixedWidth(360)
    toast.adjustSize()
    area = window.rect()
    toast.move(area.width() - toast.width() - 20, area.height() - toast.height() - 64)
    toast.show()
    toast.raise_()
    toast.item = item
    st.toast = toast
    QTimer.singleShot(TOAST_MS * (2 if action else 1), lambda: _alive(toast) and (toast.hide(), toast.deleteLater()))
    return toast


class NoticePanel(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window_ = window
        self.setWindowTitle("Notifications")
        self.setMinimumSize(440, 420)
        lay = column(spacing=8, margins=(16, 14, 16, 12))
        self.setLayout(lay)
        head = row(spacing=8)
        head.addWidget(label("Notifications", "sectionTitle"), 1)
        clear = button("Clear all", self.clear, tip="Remove every notice from this list")
        head.addWidget(clear)
        lay.addLayout(head)
        status = window.status.text()
        warnings = list(getattr(window.inventory, "warnings", []) or [])
        self.status = label("Scan status: " + status + ("\n" + "\n".join(warnings) if warnings else ""), "caption",
                            wrap=True)
        lay.addWidget(self.status)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        self.scroll.viewport().setAutoFillBackground(False)
        holder = QWidget()
        holder.setObjectName("noticeRows")
        holder.setStyleSheet("QWidget#noticeRows{background:transparent;}")
        self.rows = column(spacing=6, margins=(0, 0, 4, 0))
        holder.setLayout(self.rows)
        self.scroll.setWidget(holder)
        self.scroll.viewport().setStyleSheet("background:transparent;")
        lay.addWidget(self.scroll, 1)
        foot = row(spacing=8)
        foot.addWidget(button("Copy diagnostics", lambda: copy_diagnostics(window),
                              tip="Copy version, scan counts, warnings and recent errors to paste into a message. Your "
                                  "user name is taken out of paths."))
        foot.addWidget(button("Shortcuts", lambda: show_shortcuts(window)))
        foot.addStretch()
        foot.addWidget(button("Close", self.reject, kind="primary"))
        lay.addLayout(foot)
        self.fill()

    def fill(self):
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        notices = state_of(self.window_).notices or []
        if not notices:
            self.rows.addWidget(label("Nothing yet. Finished scans, clean-ups, kits, driver installs and routines show "
                                      "up here.", "caption", wrap=True))
        for item in notices:
            frame = QFrame()
            frame.setObjectName("noticeRow")
            color = TONE.get(item.tone, TONE["info"])
            frame.setStyleSheet(f"QFrame#noticeRow{{background:#0a131c;border:1px solid #1d2a37;border-left:3px solid "
                                f"{color};border-radius:8px;}}")
            line = row(spacing=8, margins=(10, 8, 8, 8))
            frame.setLayout(line)
            words = column(spacing=2)
            title = label(item.title + ("" if item.read else "  •"), "detailValue")
            title.setStyleSheet("font-weight:800;color:#ffffff;")
            words.addWidget(title)
            words.addWidget(label(item.text, "caption", wrap=True))
            words.addWidget(label(core.ago(item.at), "caption"))
            line.addLayout(words, 1)
            if item.target:
                line.addWidget(button("Open", lambda _=False, t=item.target: (self.accept(), _open(self.window_, t))),
                               0, Qt.AlignTop)
            self.rows.addWidget(frame)
        self.rows.addStretch()

    def clear(self):
        st = state_of(self.window_)
        st.notices = []
        _save(self.window_, core.with_notices(self.window_.settings, []))
        sync_badge(self.window_)
        self.fill()


def open_notices(window):
    panel = NoticePanel(window)
    window._notice_panel = panel
    st = state_of(window)
    core.mark_read(st.notices or [])
    _save(window, core.with_notices(window.settings, st.notices or []))
    QTimer.singleShot(0, lambda: sync_badge(window))
    panel.exec()


# ------------------------------------------------------------------ diagnostics
def diagnostics(window):
    from gg_desktop import __version__
    inv = window.inventory
    counts = {"scanned_at": inv.scanned_at, "games": len(inv.games), "mods": len(inv.mods), "old files": len(inv.files),
              "captures": len(inv.recordings) + len(inv.screenshots), "saves": len(inv.saves),
              "graveyard": len(inv.graveyard)}
    try:
        from core import get_activity
        events = [f"{e.get('date', '')[:16]} {e.get('kind', '')}: {str(e.get('details', ''))[:120]}"
                  for e in get_activity()[-20:]]
    except Exception:
        events = []
    keys = ("assistant_enabled", "autopilot_on", "local_ai_enabled", core.TRAY_KEY, core.START_KEY, "scan_on_launch",
            "check_updates_on_launch")
    switches = {k: window.settings.get(k) is True for k in keys}
    return core.diagnostics_text(__version__, platform.platform(), counts, list(inv.warnings or []),
                                 state_of(window).errors, events, switches)


def copy_diagnostics(window):
    QGuiApplication.clipboard().setText(diagnostics(window))
    window.status.setText("Diagnostics copied. Your user name was taken out of paths.")


# ------------------------------------------------------------------ paused while you play
def sync_paused(window):
    chip = getattr(window, "paused_chip", None)
    if not _alive(chip):
        return
    tracker = getattr(window, "_games_tracker", None)
    active = list(getattr(getattr(tracker, "ledger", None), "active", None) or [])
    names = {g.key: g.name for g in getattr(window.inventory, "games", [])}
    text = core.paused_text([names.get(key, "a game") for key in active])
    chip.setText(text)
    chip.setVisible(bool(text))


# ------------------------------------------------------------------ tray
def tray_wanted():
    return os.environ.get("GAME_GRAVE_TRAY", "1") != "0" and QSystemTrayIcon.isSystemTrayAvailable()


def install_tray(window):
    if getattr(window, "reference_preview", False) or not tray_wanted():
        return None
    st = state_of(window)
    tray = QSystemTrayIcon(window.windowIcon(), window)
    tray.setToolTip("Game Grave")
    menu = QMenu(window)
    menu.addAction("Open Game Grave", lambda: show_window(window))
    pop = menu.addAction("Pop out the AI Assistant", lambda: _pop(window))
    pop.setEnabled(window.assistant_enabled())
    menu.addAction("Scan PC", lambda: (show_window(window), window.start_scan()))
    menu.addAction("Notifications", lambda: (show_window(window), open_notices(window)))
    menu.addSeparator()
    keep = QAction("Keep running when closed", menu, checkable=True)
    keep.setChecked(keep_running(window))
    keep.toggled.connect(lambda on: _save(window, dict(window.settings, **{core.TRAY_KEY: bool(on)})))
    menu.addAction(keep)
    start = QAction("Start with Windows (in the tray)", menu, checkable=True)
    start.setChecked(window.settings.get(core.START_KEY) is True)
    start.setEnabled(getattr(sys, "frozen", False) and sys.platform == "win32")
    start.setToolTip("Adds Game Grave to your own Windows start-up list. Switch it off to remove it.")
    start.toggled.connect(lambda on: set_start_with_windows(window, on))
    menu.addAction(start)
    menu.addSeparator()
    menu.addAction("Quit Game Grave", lambda: quit_app(window))
    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: show_window(window) if reason in (QSystemTrayIcon.Trigger,
                                                                            QSystemTrayIcon.DoubleClick) else None)
    tray.show()
    st.tray, st.tray_menu = tray, menu
    return tray


def _pop(window):
    from gg_desktop import assistant_popout
    assistant_popout.open_popout(window)


def keep_running(window):
    return window.settings.get(core.TRAY_KEY, True) is not False


def show_window(window):
    window.showNormal() if window.isMinimized() else window.show()
    window.raise_()
    window.activateWindow()


def quit_app(window):
    window._quitting = True
    window.close()
    st = state_of(window)
    if st.tray is not None and not window.isVisible():
        st.tray.hide()


def close_to_tray(window, event):
    """True when the close was turned into hiding in the tray."""
    st = state_of(window)
    if st.tray is None or getattr(window, "_quitting", False) or not keep_running(window):
        return False
    event.ignore()
    window.hide()
    if not st.told_tray:
        st.told_tray = True
        st.tray.showMessage("Game Grave is still running", "It's in the tray by the clock. Right-click it to quit, or switch "
                            "off \"Keep running when closed\" there.", QSystemTrayIcon.Information, 6000)
    return True


def set_start_with_windows(window, on):
    """One value in the owner's own Run key (HKCU). Only in the installed app; logged either way."""
    if not (getattr(sys, "frozen", False) and sys.platform == "win32"):
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, core.RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if on:
                winreg.SetValueEx(key, core.RUN_NAME, 0, winreg.REG_SZ, core.run_command(sys.executable))
            else:
                try:
                    winreg.DeleteValue(key, core.RUN_NAME)
                except FileNotFoundError:
                    pass
    except OSError as exc:
        window.error("Start with Windows not changed", str(exc))
        return False
    _save(window, dict(window.settings, **{core.START_KEY: bool(on), "start_minimized": bool(on) or
                                            window.settings.get("start_minimized") is True}))
    from core import log_event
    log_event("start_with_windows", ("Added" if on else "Removed") + " Game Grave in HKCU\\" + core.RUN_KEY,
              result="on" if on else "off", source="tray")
    return True



# ------------------------------------------------------------------ undo right after a removal
def removal_started(window):
    """Remember which Recycle Bin records already exist, so the ones a removal adds can be offered back."""
    try:
        from recovery import get_records
        state_of(window).undo_before = core.record_ids(get_records())
    except Exception:
        state_of(window).undo_before = None


def removal_finished(window):
    st = state_of(window)
    before, st.undo_before = getattr(st, "undo_before", None), None
    if before is None:
        return
    try:
        from recovery import get_records
        rows = core.new_removals(before, get_records())
    except Exception:
        return
    if not rows:
        return
    notify(window, "Moved to the Recycle Bin", core.undo_text(rows), "warn", "tab:Undo Center",
           action=("Undo", lambda: undo_recent(window, rows)))


def undo_recent(window, rows):
    """Restore through the same checked path as the Undo Center: check each record, restore only AVAILABLE ones."""
    if window.cleaning or window.scanning:
        window.info("Game Grave is busy", "Finish the current operation first, then use Undo Center.")
        return
    rows = rows[:core.UNDO_MAX]
    if not window.confirm("Undo this removal?", core.undo_confirmation(rows)):
        return
    from recovery import check_restore, restore as restore_recycled
    from gg_desktop import undo_actions
    entries = [SimpleNamespace(recovery_id=r["id"], name=os.path.basename(str(r.get("path", ""))) or str(r.get("path", "")),
                               state="", path=str(r.get("path", ""))) for r in rows]
    window.cleaning = True
    window.status.setText("Putting files back through Windows. Each one is checked first.")

    def done(outcome):
        window.cleaning = False
        status, value = outcome if isinstance(outcome, tuple) and len(outcome) == 2 else ("ok", outcome)
        if status == "error":
            window.error("Undo failed", str(value))
            return
        restored = sum(1 for _, code in value if code == "RESTORED")
        window.status.setText(f"{restored} of {len(value)} put back.")
        notify(window, "Undo finished", undo_actions.summarize(value).split("\n\n")[0],
               "good" if restored == len(value) else "warn", "tab:Undo Center")
        if restored < len(value):
            window.info("Undo results", undo_actions.summarize(value))

    def work(progress):
        try:
            return ("ok", undo_actions.restore(entries, check_restore, restore_recycled))
        except Exception as exc:
            return ("error", str(exc))
    window.job(work, done, error_title="Undo")



# ------------------------------------------------------------------ remember sort and filters per tab
def remember_views(window, route=None):
    """Put back the sort and filter choices last used on this tab, then keep any change. Only lists whose
    accessible name starts with Sort or Filter are touched, and only to a choice the list still offers."""
    from PySide6.QtWidgets import QComboBox
    route = route or getattr(window, "current_route", "")
    page = getattr(window, "page", None)
    if not route or not _alive(page):
        return
    for combo in page.findChildren(QComboBox):
        name = combo.accessibleName()
        if not core.remembers(name) or combo.property("gg_remembered"):
            continue
        combo.setProperty("gg_remembered", True)
        value = core.remembered(window.settings, route, name)
        if value and value != combo.currentText() and combo.findText(value) >= 0:
            combo.setCurrentText(value)
        combo.currentTextChanged.connect(lambda text, r=route, n=name: _keep_view(window, r, n, text))


def _keep_view(window, route, name, text):
    if text:
        _save(window, core.with_view(window.settings, route, name, text))
