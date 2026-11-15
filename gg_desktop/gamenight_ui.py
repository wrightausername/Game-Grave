"""Game Night, inside Squad Sync: share your installed games as one code, paste friends' codes, and see what you can all
play tonight. Reading and comparing only; nothing is installed or changed. Steam's store tags are asked only for matched
Steam games, cached, and skipped while a game runs."""
from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFrame, QInputDialog, QScrollArea, QWidget

from gg_desktop import gamenight_core as gn
from gg_desktop.tools_shell import Steps
from gg_desktop.widgets import button, column, label, row

PILL = ("QLabel{{color:{0};background:{1};border:1px solid {0};border-radius:9px;padding:1px 8px;font-size:11px;"
        "font-weight:700;}}")


def _human(n):
    from core import human_size
    return human_size(n) if isinstance(n, int) and n > 0 else ""


class GameNightBody(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window_owner = window
        self.friends = gn.friends_from(window.settings)
        self.modes = gn.load_modes()
        self.rows = []
        box = column(spacing=8)
        self.setLayout(box)
        self.steps = Steps(("Share your code", "Paste friends' codes", "Pick a game"), "#e5243b")
        box.addWidget(self.steps)
        box.addWidget(label("Everyone shares one code from here (it lists installed games only, with the name you pick). "
                            "Paste your friends' codes to see what you can all play tonight and who still needs a download.",
                            "readyDetail", wrap=True))
        actions = row(spacing=8)
        self.copy_button = button("Copy my game night code", self.copy_code, kind="primary",
                                  tip="Copies a code with the name you pick and your installed games. Paste it in your "
                                      "group chat.")
        self.paste_button = button("Paste a friend's code", self.paste_code,
                                   tip="Reads a Game Night code from the clipboard, even inside a whole chat message.")
        self.clear_button = button("Remove friends", self.clear_friends, kind="actionLink")
        self.save_button = button("Save as file", self.save_file, kind="actionLink",
                                  tip="For a big library: a small text file to send instead of a long chat message.")
        self.open_button = button("Open a code file", self.open_file, kind="actionLink")
        for control in (self.copy_button, self.paste_button, self.save_button, self.open_button):
            actions.addWidget(control)
        actions.addStretch()
        actions.addWidget(self.clear_button)
        box.addLayout(actions)
        self.who = label("", "caption", wrap=True)
        box.addWidget(self.who)
        self.headline = label("", "readyGameTitle", wrap=True)
        box.addWidget(self.headline)
        holder = QWidget()
        holder.setObjectName("nightRows")
        holder.setStyleSheet("QWidget#nightRows{background:transparent;}")
        self.list = column(spacing=6)
        holder.setLayout(self.list)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        scroll.viewport().setStyleSheet("background:transparent;")
        scroll.setWidget(holder)
        box.addWidget(scroll, 1)
        self.refresh()

    # ------------------------------------------------------------ sharing
    def _my_name(self):
        name = str(self.window_owner.settings.get(gn.NAME_KEY) or "").strip()
        if name:
            return name
        name, ok = QInputDialog.getText(self, "Your name for game night",
                                        "The name your friends will see next to your games:")
        name = " ".join((name or "").split())[:24]
        if not ok or not name:
            return ""
        self._save(dict(self.window_owner.settings, **{gn.NAME_KEY: name}))
        return name

    def copy_code(self):
        name = self._my_name()
        if not name:
            return
        games = list(getattr(self.window_owner.inventory, "games", []) or [])
        if not games:
            self.window_owner.info("Scan first", "Scan your PC so Game Grave knows which games you have installed.")
            return
        code = gn.make_code(name, games)
        QGuiApplication.clipboard().setText(code)
        self.steps.set(max(self.steps.current, 1))
        self.window_owner.status.setText(f"Game night code copied ({len(games)} games). Paste it in your group chat.")
        long = len(code) > gn.CHAT_LIMIT
        self.who.setText(("Copied, but it is " + f"{len(code):,} characters, longer than one Discord message. Use Save as "
                          "file and send the file instead." if long else
                          "Copied. Paste it in your group chat; each friend presses Paste a friend's code with it."))

    def save_file(self):
        from PySide6.QtWidgets import QFileDialog
        name = self._my_name()
        games = list(getattr(self.window_owner.inventory, "games", []) or [])
        if not name or not games:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save game night code", f"{name} game night.txt", "Text (*.txt)")
        if not path:
            return
        try:
            with open(path, "x", encoding="utf-8") as handle:     # never over an existing file
                handle.write(gn.make_code(name, games) + "\n")
        except FileExistsError:
            self.window_owner.info("Not saved", "A file with that name already exists. Pick another name.")
            return
        except OSError as problem:
            self.window_owner.error("Not saved", str(problem))
            return
        self.steps.set(max(self.steps.current, 1))
        self.who.setText("Saved. Send the file in your group chat; friends press Open a code file.")

    def open_file(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "Open a game night code", "", "Text (*.txt);;All files (*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                text = handle.read(2_000_000)
        except OSError as problem:
            self.window_owner.error("Could not open it", str(problem))
            return
        self.paste_code(text)

    def paste_code(self, text=None):
        text = text if isinstance(text, str) else QGuiApplication.clipboard().text()
        try:
            friend = gn.read_code(text)
        except gn.GameNightError as problem:
            self.window_owner.info("No game night code found", str(problem))
            return False
        if friend.name.casefold() == str(self.window_owner.settings.get(gn.NAME_KEY) or "").casefold():
            self.window_owner.info("That's your own code", "Paste a code a friend sent you.")
            return False
        self.friends = gn.with_friend(self.friends, friend, time.time())
        self._save(gn.friends_to(self.window_owner.settings, self.friends))
        self.steps.set(2)
        self.refresh(fetch=True)
        return True

    def clear_friends(self):
        if self.friends and self.window_owner.confirm("Remove friends' codes?",
                                                      "Forget the friends' game lists saved here. Your own games stay."):
            self.friends = []
            self._save(gn.friends_to(self.window_owner.settings, []))
            self.refresh()

    def _save(self, settings):
        from core import save_settings
        try:
            save_settings(settings)
            self.window_owner.settings = settings
        except OSError as problem:
            self.window_owner.error("Not saved", str(problem))

    # ------------------------------------------------------------ comparing
    def _my_games(self):
        return gn.game_entries(getattr(self.window_owner.inventory, "games", []) or [])

    def refresh(self, fetch=False):
        me = str(self.window_owner.settings.get(gn.NAME_KEY) or "You")
        self.rows = gn.with_modes(gn.overlap(me, self._my_games(), self.friends), self.modes) if self.friends else []
        names = ", ".join(f"{f.name} ({len(f.games)} games)" for f in self.friends)
        self.who.setText(("Friends: " + names) if names else "No friends' codes yet.")
        self.headline.setText(gn.summary(self.rows, self.friends))
        self.clear_button.setVisible(bool(self.friends))
        self._draw()
        if fetch:
            self._fetch_modes()

    def _fetch_modes(self):
        window = self.window_owner
        wanted = [r.app_id for r in self.rows if r.app_id and r.app_id not in self.modes][:gn.MAX_LOOKUPS]
        if not wanted:
            return
        tracker = getattr(window, "_games_tracker", None)
        running = lambda: bool(getattr(getattr(tracker, "ledger", None), "active", None))

        def work(_progress):
            cache = gn.fetch_modes(wanted, dict(self.modes), game_running=running)
            try:
                gn.save_modes(cache)
            except OSError:
                pass
            return cache

        def done(cache):
            self.modes = cache
            try:
                self.refresh()
            except RuntimeError:
                pass     # the panel was closed meanwhile
        window.job(work, done, error_title="Steam's store tags could not be read")

    def _draw(self):
        while self.list.count():
            item = self.list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        shown = [r for r in self.rows if gn.together(r)][:40]
        for r in shown:
            card = QFrame()
            card.setObjectName("nightCard")
            card.setStyleSheet("QFrame#nightCard{background:#0b1118;border:1px solid #1f2c3a;border-radius:8px;}")
            line = row(spacing=10, margins=(10, 7, 10, 7))
            card.setLayout(line)
            words = column(spacing=2)
            title = label(r.title, "readyDetail")
            title.setStyleSheet("font-weight:700;")
            words.addWidget(title)
            if r.everyone:
                note = "Everyone has it installed."
            else:
                note = "Needs a download: " + ", ".join(r.missing) + (f" (about {_human(r.size)})" if _human(r.size) else "")
            words.addWidget(label(note, "caption", wrap=True))
            line.addLayout(words, 1)
            for mode in r.modes[:2]:
                tag = label(mode, "")
                tag.setStyleSheet(PILL.format("#32d67a" if "co-op" in mode.casefold() else "#13bcf5", "#0b1a14"))
                line.addWidget(tag, 0, Qt.AlignVCenter)
            state = label("Ready" if r.everyone else f"{len(r.missing)} missing", "")
            state.setStyleSheet(PILL.format("#32d67a" if r.everyone else "#f6be24", "#101a12" if r.everyone else "#211b08"))
            line.addWidget(state, 0, Qt.AlignVCenter)
            self.list.addWidget(card)
        if self.friends and not shown:
            self.list.addWidget(label("No game you can play together yet.", "caption"))
        self.list.addStretch()
