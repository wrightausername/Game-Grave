"""Working actions owned exclusively by the Ready Room page."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QLineEdit,
    QListWidget, QListWidgetItem,
)

from gg_desktop.ready_room_data import reference_ready_room
from gg_desktop.ready_room_services import (
    backup_receipt, backup_status, inspect_local, load_state, news_targets,
    news_url, refresh_news, save_state,
)
from gg_desktop.widgets import button, column, label, row


class ReadyRoomActions:
    def ready_init(self):
        if not hasattr(self, "_ready_state"):
            self._ready_state = load_state()
            self._ready_evidence = {}
            self._ready_evidence_stamp = ""
            self._ready_evidence_inventory = None
            self._ready_checks_busy = self._ready_news_busy = False

    def ready_reload(self):
        if self.current_route == "Ready Room":
            query = self.page.search.text()
            scroll = self.page.verticalScrollBar().value()
            self.ready_room_page()
            self.page.search.setText(query)
            self.page.verticalScrollBar().setValue(scroll)

    def _ready_write(self, state):
        try:
            save_state(state)
        except (OSError, ValueError) as exc:
            self.error("Ready Room history could not be saved", str(exc))
            return False
        self._ready_state = state
        return True

    def _ready_task(self, title, fn, done):
        # Return errors as data so a separate news/check task cannot reset an
        # unrelated shared scan/backup through the shell's generic error handler.
        def run(_progress):
            try:
                return fn(), ""
            except Exception as exc:
                return None, str(exc)[:350] or type(exc).__name__
        self.job(run, lambda packet: done(*packet), error_title=title)

    def _ready_dialog(self, title, detail):
        dialog = QDialog(self)
        dialog.setWindowTitle("Game Grave · " + title)
        dialog.resize(760, 500)
        dialog.setMinimumSize(560, 350)
        dialog.setStyleSheet('QWidget { font-family: "Roboto Condensed", "Segoe UI"; }')
        stack = column(spacing=12, margins=(20, 18, 20, 18))
        dialog.setLayout(stack)
        heading = label(title, "sectionTitle")
        heading.setTextFormat(Qt.PlainText)
        stack.addWidget(heading)
        note = label(detail, "subtle", wrap=True)
        note.setTextFormat(Qt.PlainText)
        stack.addWidget(note)
        return dialog, stack

    def ready_refresh_checks(self, done=None):
        self.ready_init()
        if self.reference_preview or self._ready_checks_busy:
            return
        if not self.inventory.scanned_at:
            self.info("Scan PC first", "Run the local scan to check game and manager records.")
            return
        self._ready_checks_busy = True
        inventory = self.inventory
        stamp = inventory.scanned_at
        roots = list(self.settings.get("steam_extra_roots", []))
        def finish(result, error):
            self._ready_checks_busy = False
            self._ready_evidence_stamp = stamp
            if error:
                self.status.setText("Ready Room checks could not finish. " + error)
            if self.inventory is inventory:
                self._ready_evidence = result if not error else {}
                self._ready_evidence_inventory = inventory
            self.ready_reload()
            if done:
                done()
        self._ready_task("Ready Room local checks", lambda: inspect_local(inventory, roots), finish)

    def ready_refresh_news(self, done=None):
        self.ready_init()
        if self.reference_preview or self._ready_news_busy:
            return
        if not news_targets(self.inventory.games, self._ready_state["followed"]):
            self.info("Choose a Steam game", "Scan your installed games first, then refresh Patch Watch. "
                      "News for other launchers is not available from Steam.")
            return
        self._ready_news_busy = True
        games, state = tuple(self.inventory.games), dict(self._ready_state)
        def finish(result, error):
            self._ready_news_busy = False
            if error:
                self.error("Patch Watch could not refresh", error)
            else:
                updated = {**self._ready_state, **{key: result[key] for key in (
                    "news", "news_checked", "news_warnings")}}
                if self._ready_write(updated):
                    self.status.setText(f"Patch Watch refreshed {result['succeeded']} Steam games. "
                                        + ("Some feeds are unavailable; cached news is retained."
                                           if result["news_warnings"] else "Official news is saved for offline use."))
                    self.ready_reload()
            if done:
                done()
        self._ready_task("Patch Watch", lambda: refresh_news(games, state), finish)

    def ready_updates(self, category="all"):
        if self.reference_preview:
            self.info("Patch Watch · reference preview", "These are the sample updates in your design reference.\n\n" +
                      "\n\n".join(p.game + "\n" + p.detail for p in reference_ready_room().patches))
            return
        self.ready_init()
        dialog, stack = self._ready_dialog("Patch Watch", "Official Steam announcements, saved for offline reading. "
            "Refresh connects to Steam only when you ask. A news post does not mean your installed game needs an update.")
        controls = row()
        query = QLineEdit()
        query.setPlaceholderText("Search all updates…")
        query.setAccessibleName("Search all Patch Watch posts")
        kinds = QComboBox()
        categories = (("All news", "all"), ("Game updates", "updates"), ("Maintenance", "maintenance"),
                      ("Release news", "release"), ("Mod news", "mod"))
        for caption, key in categories:
            kinds.addItem(caption, key)
        kinds.setAccessibleName("Filter news category")
        kinds.setCurrentIndex(max(0, kinds.findData(category)))
        controls.addWidget(query, 1)
        controls.addWidget(kinds)
        stack.addLayout(controls)
        posts = QListWidget()
        posts.setAccessibleName("Official game news")
        posts.setWordWrap(True)
        stack.addWidget(posts, 1)
        summary = label("", "subtle", wrap=True)
        summary.setTextFormat(Qt.PlainText)
        stack.addWidget(summary)
        actions = row()
        refresh = button("Refresh official news")
        open_post = button("Open official post")
        actions.addWidget(refresh)
        actions.addWidget(open_post)
        actions.addStretch()
        actions.addWidget(button("Close", dialog.accept))
        stack.addLayout(actions)
        def fill(*_):
            posts.clear()
            for item in self._ready_state["news"]:
                kind = kinds.currentData()
                if kind != "all" and not (kind == "updates" and item["kind"] in ("update", "hotfix", "mod")) and kind != item["kind"]:
                    continue
                if query.text().strip().casefold() not in (item["game"] + " " + item["title"] + " " + item["detail"]).casefold():
                    continue
                line = QListWidgetItem(item["game"] + " · " + datetime.fromtimestamp(item["timestamp"]).strftime("%d %b %Y") + "\n" + item["title"])
                line.setData(Qt.UserRole, item)
                line.setToolTip(item["detail"])
                posts.addItem(line)
            warnings = self._ready_state["news_warnings"]
            summary.setText(f"{posts.count()} matching cached posts." +
                            (" Some feeds are unavailable. Hover for details." if warnings else ""))
            summary.setToolTip("\n".join(warnings))
            refresh.setEnabled(not self._ready_news_busy)
            refresh.setText("Refreshing…" if self._ready_news_busy else "Refresh official news")
            open_post.setEnabled(False)
        def start_refresh():
            self.ready_refresh_news(done=fill)
            fill()
        def open_selected(*_):
            item = posts.currentItem()
            if item:
                value = item.data(Qt.UserRole)
                self.ready_open_news(value["url"], value["app_id"])
        refresh.clicked.connect(start_refresh)
        open_post.clicked.connect(open_selected)
        posts.itemDoubleClicked.connect(open_selected)
        posts.itemSelectionChanged.connect(lambda: open_post.setEnabled(posts.currentItem() is not None))
        query.textChanged.connect(fill)
        kinds.currentIndexChanged.connect(fill)
        fill()
        dialog.exec()

    def ready_open_news(self, url, steam_id):
        safe = news_url(url, steam_id)
        if not safe or not QDesktopServices.openUrl(QUrl(safe)):
            self.error("Could not open Steam news", "Your browser could not open the official Steam page.")

    def ready_metric_details(self, caption):
        if self.reference_preview:
            if caption == "Mod Alerts":
                self.navigate("Mods")
            else:
                self.info(caption + " · reference preview", "Sample data from the supplied Ready Room design. "
                          "This does not describe your PC or live services.")
        elif caption == "Followed Games":
            self.ready_followed_games()
        elif caption == "Mod Alerts":
            self.ready_mod_alerts()
        else:
            self.ready_updates({"Game Updates": "updates", "Maintenance": "maintenance", "New Releases": "release"}.get(caption, "all"))

    def ready_patch_details(self, notice):
        if self.reference_preview:
            self.info(notice.game + " · reference preview", notice.status + "\n\n" + notice.detail +
                      "\n\nDesign sample; no game files were checked or changed.")
            return
        self.ready_open_news(notice.url, notice.app_id)

    def ready_followed_games(self):
        self.ready_init()
        dialog, stack = self._ready_dialog("Followed Games", "Choose the games to keep on your watch list. "
            "Followed Steam games take priority when you refresh Patch Watch, even after uninstalling them.")
        query = QLineEdit()
        query.setPlaceholderText("Find a game or launcher…")
        query.setAccessibleName("Search games to follow")
        stack.addWidget(query)
        choices = QListWidget()
        choices.setAccessibleName("Games to follow")
        records = {g["key"]: g for g in self._ready_state["followed"]}
        followed = set(records)
        for game in self.inventory.games:
            records[game.key] = dict(key=game.key, name=game.name, launcher=game.launcher, app_id=str(game.app_id or ""))
        for record in sorted(records.values(), key=lambda g: g["name"].casefold()):
            item = QListWidgetItem(record["name"] + " · " + record["launcher"])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if record["key"] in followed else Qt.Unchecked)
            item.setData(Qt.UserRole, record)
            choices.addItem(item)
        stack.addWidget(choices, 1)
        if not records:
            stack.addWidget(label("Scan PC to discover games you can follow.", "subtle"))
        def filter_games(text):
            for i in range(choices.count()):
                item = choices.item(i)
                item.setHidden(text.casefold() not in item.text().casefold())
        query.textChanged.connect(filter_games)
        actions = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        actions.rejected.connect(dialog.reject)
        def save():
            selected = [choices.item(i).data(Qt.UserRole) for i in range(choices.count())
                        if choices.item(i).checkState() == Qt.Checked]
            if len(selected) > 200:
                self.error("Watch list full", "Choose up to 200 followed games.")
                return
            if self._ready_write({**self._ready_state, "followed": selected}):
                self.ready_reload()
                dialog.accept()
        actions.accepted.connect(save)
        stack.addWidget(actions)
        dialog.exec()

    def ready_game_details(self, pulse):
        if self.reference_preview:
            self.info(pulse.name + " · reference preview", pulse.hours + " · " + pulse.status +
                      "\n\nSample data from the design reference.")
            return
        # Keep the existing precise Games route for inspection and its actions.
        self.navigate("Games")
        self.game_search.setText(pulse.name)
        for index, game in enumerate(self._shown_games):
            if game.key == pulse.key:
                self.game_table.selectRow(index)
                break

    def ready_mod_alerts(self):
        self.ready_init()
        dialog, stack = self._ready_dialog("Mod Radar · review warnings", "These are local association and profile warnings. "
            "Mod update availability and in-game compatibility need confirmation in the mod manager.")
        findings = QListWidget()
        findings.setWordWrap(True)
        findings.setAccessibleName("Mod evidence warnings")
        audit = self._ready_evidence.get("audit", {})
        for item in audit.get("examples", []):
            findings.addItem(item["item"] + "\n" + item["reason"])
        for warning in self._ready_evidence.get("profiles", {}).get("warnings", []):
            findings.addItem(warning)
        if not findings.count():
            findings.addItem("No association warnings recorded." if self._ready_evidence else "Run a local scan to review mod evidence.")
        stack.addWidget(findings, 1)
        controls = row()
        controls.addWidget(button("View Mods", lambda: (dialog.accept(), self.navigate("Mods"))))
        controls.addWidget(button("Run Mod Scan", lambda: (dialog.accept(), self.start_scan()), kind="primary"))
        controls.addStretch()
        controls.addWidget(button("Close", dialog.accept))
        stack.addLayout(controls)
        dialog.exec()

    def ready_health_details(self):
        if self.reference_preview:
            self.info("System & Game Health · reference preview", "The 92% gauge is sample data from the reference.")
            return
        dialog, stack = self._ready_dialog("System & Game Health", "Local checks cover free space, installation-folder access, "
            "scan-source availability and detected manager folders. Game integrity and mod compatibility require launcher or manager verification.")
        findings = QListWidget()
        findings.setAccessibleName("Local health check results")
        stack.addWidget(findings, 1)
        refresh = button("Refresh local checks")
        def fill():
            findings.clear()
            if self.current_route == "Ready Room":
                for title, tone in self.page.data.health:
                    findings.addItem(("✓ " if tone == "green" else "• ") + title)
            refresh.setEnabled(not self._ready_checks_busy)
            refresh.setText("Checking…" if self._ready_checks_busy else "Refresh local checks")
        def start():
            self.ready_refresh_checks(done=fill)
            fill()
        refresh.clicked.connect(start)
        controls = row()
        controls.addWidget(refresh)
        controls.addWidget(button("Scan PC", lambda: (dialog.accept(), self.start_scan())))
        controls.addStretch()
        controls.addWidget(button("Close", dialog.accept))
        stack.addLayout(controls)
        fill()
        dialog.exec()

    def ready_manage_saves(self):
        if self.reference_preview:
            self.navigate("Save Vault")
            return
        self.ready_init()
        dialog, stack = self._ready_dialog("Save Vault", "Backups created here are verified ZIPs. "
            "Local save folders and originals stay untouched. Older backups created through other tools are not counted.")
        entries = QListWidget()
        entries.setWordWrap(True)
        entries.setAccessibleName("Save folders and backup history")
        for backup in reversed(self._ready_state["backups"]):
            item = QListWidgetItem(Path(backup["destination"]).name + " · " + backup_status(backup) +
                                   "\n" + datetime.fromtimestamp(backup["created_at"]).strftime("%d %b %Y %H:%M"))
            item.setToolTip(backup["destination"])
            item.setData(Qt.UserRole, str(Path(backup["destination"]).parent))
            entries.addItem(item)
        for save in self.inventory.saves:
            item = QListWidgetItem(save.game + " · " + save.kind)
            item.setToolTip(save.path)
            item.setData(Qt.UserRole, save.path)
            entries.addItem(item)
        if not entries.count():
            entries.addItem("No backup history yet. Choose Backup Now to preserve a save folder.")
        stack.addWidget(entries, 1)
        controls = row()
        def open_folder():
            item = entries.currentItem()
            if item and item.data(Qt.UserRole):
                self._open_folder(item.data(Qt.UserRole))
        controls.addWidget(button("Open selected folder", open_folder))
        controls.addWidget(button("Backup Now", lambda: (dialog.accept(), self.ready_backup_now()), kind="primary"))
        controls.addWidget(button("Recovery tools", lambda: (dialog.accept(), self.navigate("More Tools"))))
        controls.addStretch()
        controls.addWidget(button("Close", dialog.accept))
        stack.addLayout(controls)
        dialog.exec()

    def ready_backup_now(self):
        from save_vault import create_backup
        if self.scanning or self.cleaning:
            self.info("Game Grave is busy", "Finish the current scan or backup first.")
            return
        self.ready_init()
        source = QFileDialog.getExistingDirectory(self, "Choose exact save / game profile folder to preserve")
        if not source:
            return
        output, _ = QFileDialog.getSaveFileName(self, "Create a NEW verified Save Vault ZIP",
            str(Path(source).parent / (Path(source).name + "_SaveVault.zip")), "ZIP archives (*.zip)")
        if not output:
            return
        if not output.casefold().endswith(".zip"):
            output += ".zip"
        if not self.confirm("Back up this selected save or profile folder?",
            "Source: " + source + "\n\nNew ZIP: " + output +
            "\n\nOnly this folder is copied. Choose a new destination outside the source. "
            "Close the game first for consistent saves. Original files are never overwritten."):
            return
        self.cleaning = True
        self.status.setText("Save Vault: creating and verifying your backup…")
        def finish(report, error):
            self.cleaning = False
            if error:
                self.error("Save Vault backup failed", error)
                self.status.setText("Backup did not complete. Original files untouched.")
                return
            try:
                receipt = backup_receipt(report)
                history = [b for b in self._ready_state["backups"] if b["destination"] != receipt["destination"]]
                saved = self._ready_write({**self._ready_state, "backups": (history + [receipt])[-200:]})
            except (OSError, ValueError) as exc:
                saved = False
                self.error("Backup created; history unavailable", str(exc))
            self.status.setText("Verified backup created." + (" Saved in Ready Room history." if saved else " History could not be saved."))
            self.ready_reload()
            self.info("Save Vault backup completed", str(report["files"]) + " files preserved in\n" + output +
                      "\n\nZIP integrity verified. Original save files untouched.")
        self._ready_task("Save Vault", lambda: create_backup(Path(source), Path(output)), finish)
