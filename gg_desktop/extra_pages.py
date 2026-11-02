"""Functional companion pages for the locked cinematic Game Grave shell.

These pages consume existing read-only inventory and preserve backend action authority.
No tab invents data, installs models, performs file deletion, or overrides protection.
"""
from __future__ import annotations

from collections import Counter
import json
import re
import urllib.request

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QGridLayout, QLabel, QLineEdit,
    QPlainTextEdit, QTableWidget, QWidget, QCheckBox,
)

from core import save_settings
from gg_desktop.widgets import (
    HeroBanner, MetricCard, ActionCard, button, column, data_table,
    label, panel, row, section_title,
)
from gg_desktop.models import readable_bytes


def _selected(table):
    return sorted({i.row() for i in table.selectionModel().selectedRows()})


def _readable_capture_time(record):
    from datetime import datetime
    try:
        timestamp = float(getattr(record, "modified", 0))
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d") if timestamp else "Unknown"
    except (ValueError, OSError, OverflowError, TypeError):
        return "Unknown"


def _local_ai_answer(question: str, model: str, counts: dict) -> str:
    """Explicit, on-demand loopback Ollama call. No paths or game names sent."""
    if len(question) > 800 or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", model):
        raise ValueError("Invalid question length or local model name.")
    request = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=json.dumps({
            "model": model,
            "stream": False,
            "messages": [
                {"role": "system", "content": (
                    "You help explain Game Grave, a local Windows gaming storage manager. "
                    "You are advisory only. Never claim you scanned or changed files, "
                    "verified a mod, or proved deletion safe. Never instruct users to bypass "
                    "system, save, or active game protection. "
                    "File operations require independent human confirmation and app checks. "
                    "Only aggregate counts are supplied: " + json.dumps(counts, sort_keys=True)
                )},
                {"role": "user", "content": question},
            ],
            "options": {"num_predict": 400, "temperature": 0.2},
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # Hard-coded loopback, no user-controlled URL or cloud fallback.
    with urllib.request.urlopen(request, timeout=45) as response:
        if response.status != 200:
            raise RuntimeError("Local inference service returned an error.")
        data = response.read(160_000)
    answer = json.loads(data).get("message", {}).get("content", "")
    if not isinstance(answer, str) or not answer.strip():
        raise RuntimeError("The local model returned no answer.")
    return answer.strip()[:5000]


class ExtraPages:
    """Mixed into ScreenMethods. Page actions use the existing safe methods."""

    def ready_room_page(self):
        page = self._new(
            "Ready Room",
            "Your installed games, local warnings and official update links in one place.",
        )
        if self._not_scanned(page):
            return
        metrics = QWidget()
        line = row()
        metrics.setLayout(line)
        for title, amount, hint, tone in (
            ("Installed games", str(len(self.inventory.games)), "Evidence-backed", "cyan"),
            ("Mod locations", str(len(self.inventory.mods)), "Not individually verified mods", "amber"),
            ("Save locations", str(len(self.inventory.saves)), "Protected / ownership may be unknown", "green"),
        ):
            line.addWidget(MetricCard(title, amount, hint, tone=tone))
        page.content.addWidget(metrics)

        p, contents = panel()
        contents.addWidget(section_title("YOUR LINEUP", "Observed installed games"))
        table = data_table(["GAME", "LAUNCHER", "LAST PLAYED", "SIZE"])
        games = sorted(self.inventory.games,
                       key=lambda g: (g.last_played_at is None,
                                      -(g.last_played_at or 0), g.name.casefold()))[:100]
        table.setRowCount(len(games))
        from core import age_text
        from gg_desktop.screens import _table_text
        for i, game in enumerate(games):
            for j, value in enumerate((
                game.name, game.launcher,
                age_text(game.last_played_at) if game.last_played_at else "Unknown",
                readable_bytes(game.size_bytes),
            )):
                _table_text(table, i, j, value)
        contents.addWidget(table)
        tools = QWidget()
        bar = row()
        tools.setLayout(bar)
        def open_game():
            indexes = _selected(table)
            if indexes:
                self._pending_game_query = games[indexes[0]].name
                self.navigate("Games")
            else:
                self.info("Choose a game", "Select a game to inspect it.")
        bar.addWidget(button("Open selected game", open_game, kind="primary"))
        bar.addWidget(button("Game DNA", lambda: self.navigate("Game DNA")))
        bar.addWidget(button("Check Mod Radar", lambda: self.navigate("Mods")))
        contents.addWidget(tools)
        page.content.addWidget(p)

        p, stack = panel()
        stack.addWidget(section_title("PATCH WATCH", "Official developer updates"))
        stack.addWidget(label(
            "Official patch notes are not connected in this preview. "
            "Game Grave will not invent versions, updates, compatibility warnings, "
            "or maintenance announcements. When a verified source is connected, "
            "your most-played and pinned games can be prioritized here.",
            "subtle", wrap=True,
        ))
        stack.addWidget(button("Review local mod findings", lambda: self.navigate("Mods")))
        page.content.addWidget(p)

    def other_storage_page(self):
        page = self._new(
            "Other Storage",
            "Explore local storage outside the verified install-size summaries, without guessing what is safe.",
        )
        if self._not_scanned(page):
            return
        rows = []
        for item in self.inventory.files:
            rows.append(("Old Files", str(getattr(item, "path", "")),
                         getattr(item, "size", None), "Ordinary review candidate"))
        for item in self.inventory.mods:
            rows.append(("Mod storage", str(getattr(item, "path", "")),
                         getattr(item, "apparent_bytes", None), "Protected manager content"))
        for item in self.inventory.saves:
            rows.append(("Possible saves", str(getattr(item, "path", "")),
                         None, "Protected, ownership unverified"))
        unique = []
        seen = set()
        for item in rows:
            key = item[1].casefold()
            if key and key not in seen:
                seen.add(key)
                unique.append(item)
        p, stack = panel()
        stack.addWidget(section_title("DISCOVERED LOCATIONS", str(len(unique)) + " distinct paths"))
        stack.addWidget(label(
            "These categories may overlap game installs. The values are apparent sizes, "
            "not confirmed extra disk use or space that can be reclaimed.",
            "subtle", wrap=True,
        ))
        search = QLineEdit()
        search.setPlaceholderText("Search scanned paths and sources…")
        search.setText(getattr(self, "_pending_other_query", ""))
        self._pending_other_query = ""
        stack.addWidget(search)
        table = data_table(["CATEGORY", "LOCATION", "APPARENT SIZE", "PROTECTION"])
        table.setMinimumHeight(420)
        stack.addWidget(table)
        visible = []
        from gg_desktop.screens import _table_text
        def fill(*_):
            nonlocal visible
            needle = search.text().strip().casefold()
            visible = [x for x in unique
                       if not needle or needle in (x[0] + " " + x[1]).casefold()][:500]
            table.setRowCount(len(visible))
            for i, (category, path, size, state) in enumerate(visible):
                for j, val in enumerate((category, path, readable_bytes(size), state)):
                    _table_text(table, i, j, val)
        search.textChanged.connect(fill)
        fill()
        tools = QWidget()
        bar = row()
        tools.setLayout(bar)
        def open_selection():
            indexes = _selected(table)
            if indexes and indexes[0] < len(visible):
                self._open_folder(str(__import__("pathlib").Path(visible[indexes[0]][1]).parent))
            else:
                self.info("Choose a location", "Select a row to open its parent folder.")
        bar.addWidget(button("Open selected location", open_selection))
        bar.addWidget(button("Review Old Files", lambda: self.navigate("Old Files")))
        bar.addWidget(button("Review Graveyard", lambda: self.navigate("Graveyard"), kind="primary"))
        stack.addWidget(tools)
        page.content.addWidget(p)

    def captures_page(self):
        page = self._new(
            "Captures",
            "Your detected in-game screenshots and recordings, with previews only on request.",
        )
        if self._not_scanned(page):
            return
        metrics = QWidget()
        bar = row()
        metrics.setLayout(bar)
        bar.addWidget(MetricCard("Screenshots", str(len(self.inventory.screenshots)),
                                 "Image content is not read until preview", tone="cyan"))
        bar.addWidget(MetricCard("Recordings", str(len(self.inventory.recordings)),
                                 "Video files remain unchanged", tone="amber"))
        page.content.addWidget(metrics)
        p, stack = panel()
        controls = QWidget()
        tools = row()
        controls.setLayout(tools)
        filter_by = QComboBox()
        filter_by.addItems(["All captures", "Screenshots", "Recordings"])
        search = QLineEdit()
        search.setPlaceholderText("Search filename or path…")
        search.setText(getattr(self, "_pending_capture_query", ""))
        self._pending_capture_query = ""
        tools.addWidget(filter_by)
        tools.addWidget(search, 1)
        stack.addWidget(controls)
        table = data_table(["FILE", "TYPE", "SIZE", "LAST MODIFIED"])
        table.setMinimumHeight(470)
        stack.addWidget(table)
        from gg_desktop.screens import _table_text
        all_rows = [(item, "Screenshot") for item in self.inventory.screenshots] + [
            (item, "Recording") for item in self.inventory.recordings]
        visible = []
        def fill(*_):
            nonlocal visible
            mode = filter_by.currentText()
            needle = search.text().strip().casefold()
            visible = [(x, kind) for x, kind in all_rows
                       if (mode == "All captures" or mode == kind + "s")
                       and (not needle or needle in str(getattr(x, "path", "")).casefold())][:500]
            table.setRowCount(len(visible))
            for i, (entry, kind) in enumerate(visible):
                for j, value in enumerate((
                    str(__import__("pathlib").Path(entry.path).name), kind,
                    readable_bytes(getattr(entry, "size", None)), _readable_capture_time(entry),
                )):
                    _table_text(table, i, j, value)
        filter_by.currentTextChanged.connect(fill)
        search.textChanged.connect(fill)
        fill()
        actions = QWidget()
        bar = row()
        actions.setLayout(bar)
        def choose():
            idx = _selected(table)
            return visible[idx[0]] if idx and idx[0] < len(visible) else None
        def open_selected():
            entry = choose()
            if entry:
                self._open_folder(str(__import__("pathlib").Path(entry[0].path).parent))
            else:
                self.info("Choose a capture", "Select a screenshot or recording.")
        def preview():
            entry = choose()
            if not entry:
                self.info("Choose a screenshot", "Select a screenshot first.")
                return
            record, kind = entry
            if kind != "Screenshot":
                self.info("Recording preview", "Video decoding is not available in this preview. "
                          "Open its folder in the native player.")
                return
            self._preview_capture_read_only(record)
        bar.addWidget(button("Preview selected screenshot", preview, kind="primary"))
        bar.addWidget(button("Open containing folder", open_selected))
        bar.addWidget(button("Review old captures in Graveyard",
                             lambda: self.navigate("Graveyard")))
        stack.addWidget(actions)
        page.content.addWidget(p)

    def _preview_capture_read_only(self, record):
        """Never provide delete action from this general media preview."""
        from screenshot_preview import decode_screenshot_preview
        from core import is_unchanged
        from PySide6.QtGui import QImage, QPixmap
        if not is_unchanged(record):
            self.error("Image changed", "This screenshot changed after scanning. Scan again.")
            return
        def ready(image):
            qimage = QImage(image.tobytes(), image.width, image.height,
                            image.width * 3, QImage.Format_RGB888).copy()
            dialog = QDialog(self)
            dialog.setWindowTitle("Game Grave — Local screenshot preview")
            dialog.resize(860, 650)
            layout = column(margins=(18, 18, 18, 18))
            dialog.setLayout(layout)
            picture = QLabel()
            picture.setAlignment(Qt.AlignCenter)
            picture.setPixmap(QPixmap.fromImage(qimage).scaled(
                805, 535, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            layout.addWidget(picture, 1)
            layout.addWidget(label("Preview only. No cleanup permission was granted.",
                                   "subtle"))
            layout.addWidget(button("Close preview", dialog.accept))
            dialog.exec()
        self.job(lambda _: decode_screenshot_preview(record), ready,
                 error_title="Cannot preview capture")

    def ai_assistant_page(self):
        page = self._new(
            "AI Assistant",
            "Optional private local advice. It cannot inspect your file contents or approve cleanup.",
        )
        enabled = self.settings.get("ai_assistant_enabled") is True
        p, stack = panel()
        toggle = QCheckBox("Enable optional AI Assistant (local Ollama only)")
        toggle.setChecked(enabled)
        stack.addWidget(toggle)
        stack.addWidget(label(
            "Off by default. This preview connects only to an already installed local "
            "Ollama model at 127.0.0.1. No automatic download or cloud fallback. "
            "Only your typed question and anonymous inventory counts are sent to the local model. "
            "AI suggestions cannot remove, move, unprotect, repair, or modify files.",
            "subtle", wrap=True,
        ))
        def change(state):
            updated = dict(self.settings)
            updated["ai_assistant_enabled"] = bool(state)
            try:
                save_settings(updated)
            except (OSError, ValueError) as exc:
                toggle.blockSignals(True)
                toggle.setChecked(enabled)
                toggle.blockSignals(False)
                self.error("Cannot change AI setting", str(exc))
                return
            self.settings = updated
            self.navigate("AI Assistant")
        toggle.stateChanged.connect(change)
        page.content.addWidget(p)

        p, chat = panel()
        chat.addWidget(section_title("LOCAL ASSISTANT", "Advisory only"))
        transcript = QPlainTextEdit()
        transcript.setReadOnly(True)
        transcript.setMinimumHeight(260)
        transcript.setPlaceholderText(
            "Ask about Game Grave controls, protection rules or gaming storage. "
            "Chats are not saved.")
        chat.addWidget(transcript)
        line = QWidget()
        askbar = row()
        line.setLayout(askbar)
        question = QLineEdit()
        question.setMaxLength(800)
        question.setPlaceholderText("Ask the local AI a question…")
        send = button("Ask local AI", kind="primary")
        question.setEnabled(enabled)
        send.setEnabled(enabled)
        askbar.addWidget(question, 1)
        askbar.addWidget(send)
        chat.addWidget(line)
        status = label(
            "Enabled; local inference runs only after you send a question."
            if enabled else "Disabled. Enable above to use the assistant.",
            "subtle", wrap=True,
        )
        chat.addWidget(status)
        page.content.addWidget(p)
        if enabled:
            def ask():
                msg = question.text().strip()
                if not msg or not send.isEnabled():
                    return
                transcript.appendPlainText("You: " + msg + "\n")
                send.setEnabled(False)
                question.setEnabled(False)
                status.setText("Waiting for local response…")
                context = {
                    name: len(getattr(self.inventory, name, []))
                    for name in ("games", "mods", "files", "recordings",
                                 "screenshots", "saves", "graveyard")
                }
                model = str(self.settings.get("ai_model", "qwen2.5:1.5b"))
                def complete(result):
                    success, answer = result
                    transcript.appendPlainText(
                        ("Game Grave AI: " if success else "Local AI unavailable: ") + answer + "\n")
                    status.setText("No files were changed.")
                    send.setEnabled(True)
                    question.setEnabled(True)
                    question.setFocus()
                def worker(_):
                    try:
                        return True, _local_ai_answer(msg, model, context)
                    except Exception as exc:
                        return False, type(exc).__name__ + ": " + str(exc)[:180]
                self.job(worker, complete, error_title="Local AI request error")
            send.clicked.connect(ask)
            question.returnPressed.connect(ask)

        quick = QWidget()
        grid = QGridLayout(quick)
        grid.setSpacing(11)
        options = [
            ("Review Graveyard", "Inspect old files with evidence", "Graveyard"),
            ("Check mods", "See discovered mod-manager storage", "Mods"),
            ("Open Game DNA", "Visualize verified relationships", "Game DNA"),
            ("Manage saves", "Access protected Save Vault tools", "More Tools"),
        ]
        for i, (name, detail, route) in enumerate(options):
            grid.addWidget(
                ActionCard("✧", name, detail,
                           lambda route=route: self.navigate(route)),
                i // 2, i % 2)
        page.content.addWidget(quick)
