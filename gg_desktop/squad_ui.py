"""The Squad Sync panel in Ready Room: read your real mod list, share it as a code, and see exactly what differs from a
friend's code or from your own earlier snapshot. Display and confirmation only; every rule lives in squad_core.
Steam Workshop items open in Steam, where you press Subscribe. With a Nexus Premium account it downloads the missing
Nexus files and installs the plain zip ones into Mod Organizer 2 as new, switched-off mods (squad_install)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QComboBox, QInputDialog, QLabel, QLineEdit, QWidget

from gg_desktop import nexus_core as nx
from gg_desktop import squad_install as installer
from gg_desktop import squad_core as sq
from gg_desktop.feature_strip import collapsible
from gg_desktop.widgets import button, column, label, row

TONES = {"green": "#35DC7C", "amber": "#DFAC46", "muted": "#9AA4AC"}
SHOWN = 8
OPEN_MAX = 10
PACE_MS = 900                 # pause between opened pages so Steam and the browser are never flooded
IDLE = "Match your co-op group's mods. Open to read your setup and compare it with a friend's."


def build_panel(panel_cls, window):
    panel = collapsible(panel_cls, "Squad Sync", IDLE, "sync", open_height=420)
    body = SquadBody(window)
    body.on_status = panel.set_subtitle
    panel.body_layout.setContentsMargins(14, 8, 14, 10)
    panel.body_layout.addWidget(body)
    panel.squad = body
    body.report_status()
    return panel


def _live(window):
    return getattr(getattr(window.page, "squad", None), "squad", None)


class SquadBody(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window_owner = window
        self.setup = None
        self.comparison = None
        self.on_status = None
        self._pending = []
        layout = column(spacing=8)
        self.setLayout(layout)
        top = row(spacing=10)
        top.addWidget(label("Game", "readyDetail"))
        self.games = QComboBox()
        self.games.setMinimumWidth(300)
        self.games.setAccessibleName("Game for Squad Sync")
        top.addWidget(self.games)
        self.read_button = button("Read my setup", self.read, kind="primary",
                                  tip="Reads the Steam Workshop manifest, a Mod Organizer 2 profile and the Bethesda plugin list. Changes nothing.")
        top.addWidget(self.read_button)
        top.addStretch()
        self.nexus_label = label("", "readyDetail")
        top.addWidget(self.nexus_label)
        self.nexus_button = button("Sign in to Nexus…", self.nexus_toggle, kind="actionLink",
                                   tip="Nexus's one-click login needs Nexus to register Game Grave, which it has not yet. "
                                       "Until then Game Grave uses your own Nexus API key, kept only on this PC.")
        top.addWidget(self.nexus_button)
        layout.addLayout(top)
        self.summary = label("", "readyDetail", wrap=True)
        layout.addWidget(self.summary)
        columns = row(spacing=20)
        left = column(spacing=6)
        left.addWidget(label("Share your setup", "readyGameTitle"))
        self.copy_button = button("Copy squad code", self.copy_code, kind="actionLink",
                                  tip="A code for your friends. It holds mod names and Workshop numbers only, no paths or user name.")
        self.snapshot_button = button("Save a snapshot", self.snapshot, kind="actionLink",
                                      tip="Saves your mod list (not the mod files) so you can compare against it later.")
        left.addWidget(self.copy_button, 0, Qt.AlignLeft)
        left.addWidget(self.snapshot_button, 0, Qt.AlignLeft)
        left.addWidget(label("Squad Sync shows what differs. Steam Workshop items open in Steam for you to subscribe. "
                             "With Nexus Premium it downloads missing Nexus mods and installs the plain ones into Mod "
                             "Organizer 2, switched off. Anything else you get where your friend did.",
                             "readyDetail", wrap=True))
        left.addStretch()
        columns.addLayout(left, 4)
        right = column(spacing=6)
        right.addWidget(label("Match a friend or a snapshot", "readyGameTitle"))
        pick = row(spacing=14)
        self.import_button = button("Paste a squad code…", self.import_code, kind="actionLink")
        self.compare_snapshot_button = button("Compare with a snapshot…", self.compare_snapshot, kind="actionLink")
        pick.addWidget(self.import_button)
        pick.addWidget(self.compare_snapshot_button)
        pick.addStretch()
        right.addLayout(pick)
        self.result_summary = label("", "readyDetail", wrap=True)
        right.addWidget(self.result_summary)
        self.rows_box = column(spacing=3)
        right.addLayout(self.rows_box)
        fetch = row(spacing=14)
        self.open_button = button("Get what's missing", self.get_missing, kind="primary",
                                  tip="One press: opens each missing Steam Workshop item in Steam, and with Nexus Premium "
                                      "downloads the missing Nexus files and installs the plain zip ones into Mod Organizer 2 "
                                      "as new, switched-off mods. Without Premium it opens each mod's page.")
        self.console_button = button("Use Steam's download command", self.steam_console, kind="actionLink",
                                     tip="Copies Steam's own workshop_download_item commands and opens Steam's console. "
                                         "Steam decides whether it allows this for the game.")
        fetch.addWidget(self.open_button)
        fetch.addWidget(self.console_button)
        fetch.addStretch()
        right.addLayout(fetch)
        self.fetch_note = label("", "readyDetail", wrap=True)
        right.addWidget(self.fetch_note)
        right.addStretch()
        columns.addLayout(right, 6)
        layout.addLayout(columns, 1)
        self.refresh_games()
        self._sync_account()
        state = getattr(window, "squad_state", None)
        if state:
            at = self.games.findText(state["game"])
            if at >= 0:
                self.games.setCurrentIndex(at)
            self.setup, self.comparison = state["setup"], state["comparison"]
            self._show_setup()
            self._show_comparison()
        elif self.games.count():
            self.read()                      # a few small local files; no need to make the owner press a button
        else:
            self.summary.setText("Scan your PC to choose a game.")
        self.games.currentIndexChanged.connect(self._game_changed)
        self._sync()

    # ------------------------------------------------------------ state
    def _save_state(self):
        game = self.games.currentText()
        self.window_owner.squad_state = {"game": game, "setup": self.setup, "comparison": self.comparison}

    def refresh_games(self):
        self.games.clear()
        seen = set()
        for game in sorted(getattr(self.window_owner.inventory, "games", ()) or (), key=lambda g: g.name.casefold()):
            if game.name.casefold() not in seen:
                seen.add(game.name.casefold())
                self.games.addItem(game.name, game)
        self.games.setEnabled(self.games.count() > 0)
        self.read_button.setEnabled(self.games.count() > 0)

    def _game_changed(self, *_):
        self.setup = self.comparison = None
        self._clear_rows()
        self.result_summary.setText("")
        self.fetch_note.setText("")
        self.read()

    def _sync(self):
        have = bool(self.setup and self.setup.items)
        self.copy_button.setEnabled(have)
        self.snapshot_button.setEnabled(bool(self.setup and self.setup.read_any))
        ready = bool(self.setup and self.setup.read_any)
        self.import_button.setEnabled(ready)
        game = self.games.currentText()
        self.compare_snapshot_button.setEnabled(ready and bool(game and sq.list_snapshots(game)))
        missing = [i for i in (self.comparison.missing if self.comparison else []) if sq.workshop_url(i) or sq.nexus_url(i)]
        self.open_button.setVisible(bool(missing))
        self.console_button.setVisible(bool([i for i in (self.comparison.missing if self.comparison else [])
                                             if sq.workshop_url(i)]))
        self.report_status()

    # ------------------------------------------------------------ reading
    def read(self):
        game = self.games.currentData()
        if game is None:
            return
        library = next((s.library for s in getattr(self.window_owner.inventory, "steam", ())
                        if str(s.app_id) == str(game.app_id)), None)
        self.setup = sq.read_setup(game.name, game.app_id, library)
        self.comparison = None
        self._clear_rows()
        self.result_summary.setText("")
        self._show_setup()
        self._save_state()
        self._sync()

    def _show_setup(self):
        setup = self.setup
        if setup is None:
            return
        found = len(setup.items)
        head = (f"Found {found} mod item{'s' if found != 1 else ''} for {setup.game}. " if setup.read_any
                else f"Could not read any mod list for {setup.game}. ")
        self.summary.setText(head + " · ".join(setup.notes))

    # ------------------------------------------------------------ sharing
    def copy_code(self):
        if self.setup and self.setup.items:
            QApplication.clipboard().setText(sq.make_code(self.setup))
            self.window_owner.status.setText("Squad code copied. It holds mod names and Workshop numbers only.")

    def snapshot(self):
        if not (self.setup and self.setup.read_any):
            return
        try:
            path = sq.save_snapshot(self.setup)
        except OSError as problem:
            self.window_owner.error("Squad Sync", f"Could not save the snapshot: {problem}")
            return
        self.window_owner.status.setText(f"Snapshot saved ({path.name}). It records the list, not the mod files.")
        self._sync()

    # ------------------------------------------------------------ comparing
    def import_code(self):
        code, ok = QInputDialog.getText(self.window_owner, "Paste a squad code", "Paste the code your friend sent:")
        if not ok or not code.strip():
            return
        try:
            theirs = sq.read_code(code)
            self._compare(theirs)
        except ValueError as problem:
            self.window_owner.error("Squad Sync", str(problem))

    def compare_snapshot(self):
        game = self.games.currentText()
        options = sq.list_snapshots(game)
        if not options:
            return
        labels = [f"{made} · {count} item{'s' if count != 1 else ''}" for _p, made, count in options]
        choice, ok = QInputDialog.getItem(self.window_owner, "Compare with a snapshot", "Snapshot:", labels, 0, False)
        if not ok:
            return
        try:
            self._compare(sq.load_snapshot(options[labels.index(choice)][0]))
        except ValueError as problem:
            self.window_owner.error("Squad Sync", str(problem))

    def _compare(self, theirs):
        self.comparison = sq.compare(theirs, self.setup)
        self._show_comparison()
        self._save_state()
        self._sync()

    def _clear_rows(self):
        while self.rows_box.count():
            item = self.rows_box.takeAt(0)
            if item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().hide()
                        child.widget().deleteLater()
            elif item.widget():
                item.widget().hide()
                item.widget().deleteLater()

    def _pill(self, text, tone):
        pill = QLabel(text)
        pill.setAlignment(Qt.AlignCenter)
        color = TONES[tone]
        pill.setStyleSheet(f"font-size:11px;font-weight:700;color:{color};border:1px solid {color};"
                           "border-radius:9px;padding:1px 8px;background:transparent;")
        return pill

    def _show_comparison(self):
        self._clear_rows()
        result = self.comparison
        if result is None:
            self.result_summary.setText("")
            return
        self.result_summary.setText(result.summary)
        shown = 0
        for item in result.missing:
            if shown >= SHOWN:
                break
            shown += 1
            line = row(spacing=8)
            line.addWidget(label(item.label, "readyDetail"), 1)
            line.addWidget(self._pill("Missing", "amber"))
            if sq.workshop_url(item):
                open_one = button("Open in Steam", lambda _=False, i=item: self.open_item(i), kind="actionLink")
                open_one.setAccessibleName(f"Open {item.label} in Steam")
                line.addWidget(open_one)
            elif sq.nexus_url(item):
                open_nexus = button("Open on Nexus", lambda _=False, i=item: self.open_item(i), kind="actionLink")
                open_nexus.setAccessibleName(f"Open {item.label} on Nexus")
                line.addWidget(open_nexus)
            self.rows_box.addLayout(line)
        for theirs, mine in result.different:
            if shown >= SHOWN:
                break
            shown += 1
            line = row(spacing=8)
            line.addWidget(label(theirs.label, "readyDetail"), 1)
            older = int(mine.stamp) < int(theirs.stamp)
            line.addWidget(self._pill("Yours is older" if older else "Yours is newer", "amber" if older else "muted"))
            if sq.workshop_url(theirs):
                line.addWidget(button("Open in Steam", lambda _=False, i=theirs: self.open_item(i), kind="actionLink"))
            self.rows_box.addLayout(line)
        hidden = len(result.missing) + len(result.different) - shown
        if hidden > 0:
            self.rows_box.addWidget(label(f"and {hidden} more", "readyDetail"))

    # ------------------------------------------------------------ status line for the closed strip
    def status_line(self) -> str:
        if self.setup is None:
            return IDLE
        comparison = self.comparison
        if comparison is None:
            if not self.setup.read_any:
                return f"Could not read any mod list for {self.setup.game}."
            found = len(self.setup.items)
            return f"{found} mod item{'s' if found != 1 else ''} read for {self.setup.game}. Paste a friend's code to compare."
        if not comparison.comparable:
            return comparison.summary
        if comparison.missing or comparison.different:
            return (f"{len(comparison.missing)} missing and {len(comparison.different)} out of step "
                    "compared with your friend's setup.")
        return "Nothing is missing or out of step compared with your friend's setup."

    def report_status(self):
        if self.on_status is not None:
            self.on_status(self.status_line())

    # ------------------------------------------------------------ opening pages
    def open_item(self, item):
        url = sq.workshop_url(item) or sq.nexus_url(item)
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def _open_urls(self, urls):
        """Open pages one after another with a short pause, so Steam and the browser are never flooded."""
        self._pending = list(urls)
        self._pump()

    def _pump(self):
        if not self._pending:
            return
        QDesktopServices.openUrl(QUrl(self._pending.pop(0)))
        if self._pending:
            QTimer.singleShot(PACE_MS, self._pump_safely)

    def _pump_safely(self):
        try:
            self._pump()
        except RuntimeError:        # the page was rebuilt while pages were still queued
            pass

    def get_missing(self):
        comparison = self.comparison
        if comparison is None:
            return
        workshop = [i for i in comparison.missing if sq.workshop_url(i)][:OPEN_MAX]
        nexus = [i for i in comparison.missing if sq.nexus_url(i) and not sq.workshop_url(i)][:nx.BATCH]
        skipped = len(comparison.missing) - len(workshop) - len(nexus)
        notes = []
        urls = [sq.workshop_url(i) for i in workshop]
        if workshop:
            notes.append(f"Opened {len(workshop)} Workshop page{'s' if len(workshop) != 1 else ''} in Steam. "
                         "Press Subscribe on each one and Steam downloads it.")
        if nexus:
            key = nx.load_key()
            if key and self._confirm_download(nexus):
                self._open_urls(urls)
                self.fetch_note.setText(" ".join(notes + ["Asking Nexus for the files…"]))
                self._download_from_nexus(nexus, key, skipped, notes)
                return
            urls += [sq.nexus_url(i) for i in nexus]
            notes.append(f"Opened {len(nexus)} Nexus page{'s' if len(nexus) != 1 else ''} in your browser. "
                         "Nexus makes you press its own download button (Slow download on a free account).")
        if skipped > 0:
            notes.append(f"{skipped} more item{'s have' if skipped != 1 else ' has'} no download source in the code "
                         "or are over the limit for one press, so Game Grave left them for you to get where your friend did.")
        self._open_urls(urls)
        self.fetch_note.setText(" ".join(notes))
        self.window_owner.status.setText("Squad Sync opened the missing mods' pages.")

    def steam_console(self):
        game = self.games.currentData()
        comparison = self.comparison
        if comparison is None or game is None:
            return
        ids = [i.key for i in comparison.missing if sq.workshop_url(i)][:OPEN_MAX * 3]
        if not ids:
            return
        app_id = str(getattr(game, "app_id", "") or "")
        if not app_id.isdigit():
            self.window_owner.error("Squad Sync", "Game Grave does not know this game's Steam number, so it cannot "
                                                  "write Steam's download commands for it.")
            return
        QApplication.clipboard().setText("\n".join(f"workshop_download_item {app_id} {i}" for i in ids))
        QDesktopServices.openUrl(QUrl("steam://nav/console"))
        self.fetch_note.setText(f"Copied {len(ids)} Steam download command{'s' if len(ids) != 1 else ''}. In Steam's console, "
                                "paste them and press Enter. Steam decides whether it allows this for the game; "
                                "subscribing on the Workshop page always works.")

    # ------------------------------------------------------------ Nexus
    def _sync_account(self):
        window = self.window_owner
        account = getattr(window, "nexus_account", None)
        has_key = bool(nx.load_key())
        if account is not None and has_key:
            self.nexus_label.setText(f"Nexus: {account.name} · {'Premium' if account.premium else 'Free account'}")
        elif has_key:
            self.nexus_label.setText("Nexus: key saved")
        else:
            self.nexus_label.setText("Nexus: not signed in")
        self.nexus_button.setText("Sign out of Nexus" if has_key else "Sign in to Nexus…")
        self.nexus_button.setAccessibleName(self.nexus_button.text().replace("…", ""))

    def nexus_toggle(self):
        if nx.load_key():
            nx.forget_key()
            self.window_owner.nexus_account = None
            self._sync_account()
            self.window_owner.status.setText("Signed out of Nexus. Game Grave forgot the key.")
            return
        QDesktopServices.openUrl(QUrl(nx.KEY_PAGE))
        key, ok = QInputDialog.getText(self.window_owner, "Sign in to Nexus",
                                       "On the Nexus page that just opened, copy your Personal API Key and paste it here.\n"
                                       "It stays on this PC and is only ever sent to Nexus.", QLineEdit.Password)
        if not ok or not key.strip():
            return
        key = key.strip()
        self.nexus_button.setEnabled(False)
        self.nexus_label.setText("Nexus: checking…")

        def work(_progress):
            try:
                return nx.validate(key), ""
            except nx.NexusError as problem:
                return None, str(problem)

        def finish(result):
            window = self.window_owner
            try:
                self.nexus_button.setEnabled(True)
                account, problem = result
                if account is not None:
                    try:
                        nx.save_key(key)
                    except nx.NexusError as saving:
                        account, problem = None, str(saving)
                if account is None:
                    self._sync_account()
                    window.error("Nexus", problem)
                    return
                window.nexus_account = account
                self._sync_account()
                window.status.setText(f"Signed in to Nexus as {account.name}.")
            except RuntimeError:
                pass

        self.window_owner.job(work, finish, error_title="Nexus sign-in did not finish")

    def _download_folder(self):
        found = sq.mo2_instance(self.games.currentText(), sq.default_roots())
        fallback = Path.home() / "Documents" / "Game Grave" / "Nexus Downloads"
        return nx.downloads_folder(found[0] if found else None, fallback)

    def _mods_folder(self):
        """The Mod Organizer 2 mods folder for the chosen game, or None when there is no instance to install into."""
        found = sq.mo2_instance(self.games.currentText(), sq.default_roots())
        if not found:
            return None
        folder = installer.mods_folder(found[0], found[1])
        return folder if folder.is_dir() else None

    def _confirm_download(self, items) -> bool:
        folder = self._download_folder()
        return self.window_owner.confirm(
            "Download from Nexus",
            f"Game Grave will ask Nexus for the main file of {len(items)} mod{'s' if len(items) != 1 else ''} and save "
            f"{'them' if len(items) != 1 else 'it'} in:\n{folder}\n\n"
            "This needs a Nexus Premium account; on a free account Game Grave only opens the pages. Files are saved as "
            "new files and nothing is overwritten.\n\n"
            + ("Plain zip mods are then installed into Mod Organizer 2 as NEW mods, switched off, under your friend's "
               "mod names. Mods with an installer that asks questions, and 7z or rar files, wait in Mod Organizer 2's "
               "Downloads tab for you. No existing mod, profile or load order is changed."
               if self._mods_folder() is not None else
               "No Mod Organizer 2 setup was found for this game, so nothing is installed."))

    def _download_from_nexus(self, items, key, skipped, notes):
        folder = self._download_folder()
        mods = self._mods_folder()

        def work(_progress):
            out = {"done": [], "failed": [], "free": False, "error": "", "installed": [], "waiting": []}
            try:
                account = nx.validate(key)
            except nx.NexusError as problem:
                out["error"] = str(problem)
                return out
            out["account"] = account
            if not account.premium:
                out["free"] = True
                return out
            for item in items:
                try:
                    choice = nx.main_file(item.nexus, key)
                    url = nx.download_url(item.nexus, choice.file_id, key)
                    path = nx.download(url, folder, choice.name, expected_kb=choice.size_kb)
                    out["done"].append((item.label, path.name))
                    if mods is not None:
                        try:
                            installer.install(path, mods, item.label, item.nexus)
                            out["installed"].append(item.label)
                        except installer.InstallError as reason:
                            out["waiting"].append((item.label, str(reason)))
                except nx.NexusError as problem:
                    out["failed"].append((item.label, str(problem)))
            return out

        def finish(out):
            window = self.window_owner
            try:
                account = out.get("account")
                if account is not None:
                    window.nexus_account = account
                    self._sync_account()
                lines = list(notes)
                if out["error"]:
                    lines.append(out["error"])
                elif out["free"]:
                    self._open_urls([sq.nexus_url(i) for i in items])
                    lines.append("Your Nexus account is not Premium, so direct downloads are not allowed. Opened "
                                 f"{len(items)} Nexus page{'s' if len(items) != 1 else ''} in your browser instead.")
                else:
                    if out["done"]:
                        lines.append(f"Downloaded {len(out['done'])} file{'s' if len(out['done']) != 1 else ''} to {folder}.")
                    if out["installed"]:
                        count = len(out["installed"])
                        lines.append(f"Installed {count} as new mod{'s' if count != 1 else ''}, switched off: "
                                     f"{', '.join(out['installed'][:5])}{'…' if count > 5 else ''}. In Mod Organizer 2 press F5, "
                                     "then tick them.")
                    if out["waiting"]:
                        count = len(out["waiting"])
                        lines.append(f"{count} wait{'s' if count == 1 else ''} in Mod Organizer 2's Downloads tab for you to install: "
                                     + "; ".join(f"{name} ({why})" for name, why in out["waiting"][:4]) + ".")
                    elif out["done"] and mods is None:
                        lines.append("Install them from your mod manager.")
                    if out["installed"]:
                        try:
                            from core import log_event
                            log_event("squad_install", f"Squad Sync installed {len(out['installed'])} new mod folder(s) into Mod Organizer 2")
                        except Exception:
                            pass
                    for name, problem in out["failed"][:4]:
                        lines.append(f"{name}: {problem}")
                if skipped > 0:
                    lines.append(f"{skipped} more item{'s were' if skipped != 1 else ' was'} left for you.")
                self.fetch_note.setText(" ".join(lines))
                window.status.setText("Squad Sync finished asking Nexus.")
            except RuntimeError:
                pass

        self.window_owner.job(work, finish, error_title="Squad Sync could not reach Nexus")
