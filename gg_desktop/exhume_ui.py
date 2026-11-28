"""The Exhume panel in Ready Room: see the current display driver, mark a working one as good, and roll back to an
older stored driver. Display and confirmation only; every rule lives in exhume_core. A rollback is the one thing here
that changes Windows, so it names the exact commands, asks first, and is logged."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QWidget

from gg_desktop import exhume_core as ex
from gg_desktop.feature_strip import collapsible
from gg_desktop.widgets import button, column, label, row

TONES = {"green": "#35DC7C", "amber": "#DFAC46", "muted": "#9AA4AC"}


def build_panel(panel_cls, window):
    panel = collapsible(panel_cls, "Exhume", "Bring back an older graphics driver that Windows still has stored. Open to check.",
                        "undo", open_height=230)
    body = ExhumeBody(window)
    body.on_status = panel.set_subtitle
    panel.body_layout.setContentsMargins(14, 8, 14, 10)
    panel.body_layout.addWidget(body)
    panel.exhume = body
    body.report_status()
    return panel


def check(_progress):
    """Off the main thread. A Windows problem comes back as text, not a dialog."""
    try:
        return ex.build_cards(ex.parse_current(ex.query_current()), ex.parse_store(ex.query_store()),
                              ex.load_marks()), ""
    except OSError as problem:
        return [], str(problem)


def deliver_check(window, result):
    window.exhume_result = result
    body = _live(window)
    if body is not None:
        try:
            body.show(result)
        except RuntimeError:
            pass


def _live(window):
    return getattr(getattr(window.page, "exhume", None), "exhume", None)


def deliver_outcome(window, outcome):
    window.status.setText(outcome.message[:110])
    (window.info if outcome.ok else window.error)("Exhume", outcome.message)
    body = _live(window)
    if body is not None:
        try:
            body.check()
        except RuntimeError:
            pass


class ExhumeBody(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window_owner = window
        self.cards = []
        self.on_status = None
        layout = column(spacing=8)
        self.setLayout(layout)
        top = row(spacing=10)
        self.check_button = button("Check display drivers", self.check, kind="primary",
                                   tip="Asks Windows which display driver is in use and which older ones it still stores. Changes nothing.")
        top.addWidget(self.check_button)
        self.summary = label("", "readyDetail", wrap=True)
        top.addWidget(self.summary, 1)
        layout.addLayout(top)
        self.cards_box = column(spacing=8)
        layout.addLayout(self.cards_box)
        layout.addStretch()
        self.note = label("Game Grave cannot tell which driver is good. \"Good\" means a version you marked while it "
                          "was working. A rollback removes the current driver package from Windows and installs the "
                          "older one. Game Grave keeps no copy of the driver it removes, and Windows needs a restart "
                          "afterwards.", "readyDetail", wrap=True)
        layout.addWidget(self.note)
        last = getattr(window, "exhume_result", None)
        if last is not None:
            self.show(last)
        else:
            self.summary.setText("Press Check to see your graphics driver. Nothing is changed by checking.")

    def report_status(self):
        """The one line shown while the panel is closed. Nothing is asked of Windows until the owner presses Check."""
        if self.on_status is None:
            return
        last = getattr(self.window_owner, "exhume_result", None)
        if last is None:
            return
        cards, error = last
        if error:
            self.on_status("Windows would not share its driver list.")
        elif not cards:
            self.on_status("Windows reports no display adapter with a driver.")
        else:
            older = sum(len(card.older) for card in cards)
            self.on_status(f"{len(cards)} display adapter{'s' if len(cards) != 1 else ''}; "
                           f"{older} older driver{'s' if older != 1 else ''} still stored.")

    def check(self):
        self.check_button.setEnabled(False)
        self.summary.setText("Asking Windows…")
        self.window_owner.job(check, lambda r: deliver_check(self.window_owner, r),
                              error_title="Exhume could not check the drivers")

    def show(self, result):
        cards, error = result
        self.cards = cards
        self.check_button.setEnabled(True)
        self._clear()
        self.report_status()
        if error:
            self.summary.setText(f"Windows would not share its driver list: {error}")
            return
        if not cards:
            self.summary.setText("Windows reports no display adapter with a driver.")
            return
        admin = ex.is_admin()
        self.summary.setText(f"{len(cards)} display adapter{'s' if len(cards) != 1 else ''} found. "
                             + ("" if admin else "Game Grave is not running as administrator, so a rollback will ask "
                                                 "you to reopen it that way."))
        for index, card in enumerate(cards):
            self.cards_box.addWidget(self._card(index, card))

    def _clear(self):
        while self.cards_box.count():
            item = self.cards_box.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

    def _pill(self, text, tone):
        pill = QLabel(text)
        pill.setAlignment(Qt.AlignCenter)
        color = TONES[tone]
        pill.setStyleSheet(f"font-size:11px;font-weight:700;color:{color};border:1px solid {color};"
                           "border-radius:9px;padding:1px 8px;background:transparent;")
        return pill

    def _card(self, index, card):
        frame = QFrame()
        frame.setStyleSheet("QFrame{border:1px solid #222A30;border-radius:6px;}QLabel{border:0;background:transparent;}")
        line = row(spacing=18, margins=(12, 10, 12, 10))
        frame.setLayout(line)
        left = column(spacing=3)
        left.addWidget(label(card.current.name, "readyGameTitle"))
        facts = " · ".join(x for x in (f"Driver {card.current.version}", card.current.date, card.current.provider) if x)
        left.addWidget(label(facts, "readyDetail", wrap=True))
        if card.current_is_marked:
            left.addWidget(self._pill(f"Marked good on {card.marked['marked']}", "green"), 0, Qt.AlignLeft)
        else:
            mark = button("Mark this driver as good", lambda _=False, c=card: self.mark(c), kind="actionLink",
                          tip="Saves this version in Game Grave's own file so you can find it later. Changes nothing in Windows.")
            left.addWidget(mark, 0, Qt.AlignLeft)
            if card.marked:
                left.addWidget(label(f"You marked {card.marked['version']} as good on {card.marked['marked']}.",
                                     "readyDetail", wrap=True))
        left.addStretch()
        line.addLayout(left, 4)
        right = column(spacing=4)
        right.addWidget(label("Older drivers still on this PC", "readyWhen"))
        if card.reason:
            right.addWidget(label(card.reason, "readyDetail", wrap=True))
        for package in card.older[:5]:
            item = row(spacing=8)
            item.addWidget(label(f"{package.version}  ({package.date})", "readyDetail"), 1)
            if card.marked and card.marked["version"] == package.version:
                item.addWidget(self._pill("You marked this good", "green"))
            roll = button("Roll back…", lambda _=False, c=card, p=package: self.roll_back(c, p), kind="primary",
                          tip="Shows the exact commands and asks before anything changes.")
            roll.setAccessibleName(f"Roll back {card.current.name} to {package.version}")
            item.addWidget(roll)
            right.addLayout(item)
        right.addStretch()
        line.addLayout(right, 5)
        return frame

    def mark(self, card):
        try:
            ex.save_mark(card.current.name, card.current.version)
        except OSError as problem:
            self.window_owner.error("Exhume", f"Could not save the mark: {problem}")
            return
        marks = ex.load_marks()
        for each in self.cards:
            each.marked = marks.get(each.current.name)
            each.current_is_marked = bool(each.marked and each.marked["version"] == each.current.version)
        self.window_owner.exhume_result = (self.cards, "")
        self.show((self.cards, ""))
        self.window_owner.status.setText("Marked as good in Game Grave. Windows was not changed.")

    def roll_back(self, card, package):
        window = self.window_owner
        try:
            commands = ex.plan_rollback(card, package)
        except ValueError as problem:
            window.error("Exhume", str(problem))
            return
        message = (f"Roll back {card.current.name}\nfrom {card.current.version} to {package.version}\n\n"
                   "Game Grave will ask Windows to run exactly:\n" + ex.command_text(commands) + "\n\n"
                   "This removes the current driver package from Windows and installs the older one. "
                   "Game Grave keeps no copy of the driver it removes. The screen may flicker or go dark for a "
                   "moment and Windows needs a restart afterwards. Creating a Windows restore point first is wise.")
        if not window.confirm("Roll back graphics driver", message, destructive=True):
            return
        window.status.setText("Rolling back the graphics driver…")
        window.job(lambda _progress: ex.rollback(card, package), lambda o: deliver_outcome(window, o),
                   error_title="Exhume could not roll back")
