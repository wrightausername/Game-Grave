"""Connected Chromium Command screens: true data, no fake cleanup claims."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import datetime
from pathlib import Path
import os
import shutil
import subprocess
import sys
import uuid

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMenu, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSizePolicy, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)
from core import (
    human_size, age_text, is_game_neglected, is_protected_path, is_unchanged,
    safe_scan_root, save_settings,
)
from graveyard import GraveyardEntry, build_graveyard
from graveyard_protection import protection_action, set_item_protection
from cleanup_actions import recycle_reviewed_entries, recycle_old_files
from recovery import get_records, restore as restore_recycled, check_restore
from screenshot_preview import decode_screenshot_preview
from gg_desktop.backend import refresh_graveyard, unprotect_exact_personal_item, add_never_touch_path
from gg_desktop.models import (
    readable_bytes, reported_game_bytes, unique_launcher_counts,
    graveyard_protection_decision, graveyard_totals, graveyard_detail_text, game_detail_text,
)
from gg_desktop.widgets import (
    ActionCard, HeroBanner, LandscapeArt, MetricCard, ScrollPage, StorageRing,
    button, column, data_table, label, page_heading, panel, row, section_title,
)


def _table_text(table: QTableWidget, r: int, c: int, value) -> None:
    cell = QTableWidgetItem(str(value))
    cell.setToolTip(str(value))
    table.setItem(r, c, cell)


def _selected_indices(table: QTableWidget) -> list[int]:
    return sorted(set(idx.row() for idx in table.selectionModel().selectedRows()))


def _safe_open_path(target: str) -> bool:
    from core import _has_reparse_component
    path = Path(target)
    if not path.is_dir() or _has_reparse_component(path):
        return False
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def _box_notice(parent, message: str, *, warning=False):
    frame, stack = panel(padding=12)
    label_widget = label(message, "warning" if warning else "subtle", wrap=True)
    stack.addWidget(label_widget)
    parent.content.addWidget(frame)
    return frame


class ScreenMethods:
    """These methods are deliberately UI-only; the existing backend is authoritative."""

    def _new(self, title: str, subtitle: str) -> ScrollPage:
        page = self.page_for(title)
        page_heading(page, title, subtitle)
        if self.inventory.warnings:
            _box_notice(page, "Partial scan: " + " ".join(self.inventory.warnings), warning=True)
        return page

    def _not_scanned(self, page):
        if self.inventory.scanned_at:
            return False
        frame, stack = panel(padding=18)
        stack.addWidget(label("YOUR STORAGE. YOUR DECISION.", "eyebrow"))
        stack.addWidget(label("Run Scan PC to see what's actually installed. "
                              "Game Grave does not invent activity or disk usage.", "subtle", wrap=True))
        stack.addWidget(button("Scan PC now", self.start_scan, kind="primary"))
        page.content.addWidget(frame)
        return True

    def overview_page(self):
        page = self.page_for("Overview")
        hero_row = QWidget()
        hero_layout = row(spacing=12)
        hero_row.setLayout(hero_layout)
        banner = HeroBanner(
            title="YOUR GAMES.", subtitle="A CLEANER TOMORROW.",
            detail="Find what your games leave behind, remove what you don't need, "
                   "and keep your gaming library in top shape.")
        hero_layout.addWidget(banner, 7)
        # A Recycle Bin move is not reclaimed space. Never copy the fictional
        # "37.8 GB reclaimed" number from the reference mockup.
        now = datetime.now().astimezone()
        monthly = []
        for event in get_records():
            try:
                created = datetime.fromisoformat(str(event.get("time", "")))
                if created.year == now.year and created.month == now.month:
                    monthly.append(event)
            except (ValueError, TypeError, AttributeError):
                continue
        month_bytes = sum(max(0, int(e.get("size", 0)))
                          for e in monthly if isinstance(e.get("size"), int))
        hero_layout.addWidget(MetricCard(
            "RECYCLE BIN MOVES THIS MONTH",
            human_size(month_bytes),
            f"{len(monthly)} recorded • NOT freed space",
            tone="cyan"), 3)
        page.content.addWidget(hero_row)
        strip = QWidget()
        grid = QGridLayout(strip)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        cards = [
            ("⌕", "Scan PC", "Find game files, mods and captures", self.start_scan),
            ("♱", "Review Graveyard", "Check individual files and protections", lambda: self.navigate("Graveyard")),
            ("↶", "Open Undo Center", "Check what Windows can restore", lambda: self.navigate("Undo Center")),
            ("⚙", "Quick Settings", "Folders, exclusions and appearance", lambda: self.navigate("Settings")),
        ]
        compact = self.width() < 1220
        for index, (symbol, title, explanation, action) in enumerate(cards):
            card = ActionCard(symbol, title, explanation, action)
            if index == 0:
                card.setObjectName("actionCardPrimary")
            grid.addWidget(card, index // (2 if compact else 4),
                           index % (2 if compact else 4))
        page.content.addWidget(strip)

        metrics = QWidget()
        r = row(spacing=12)
        metrics.setLayout(r)
        storage, storage_col = panel()
        storage_col.addWidget(section_title("Storage Overview", "Local system disk"))
        disk = StorageRing()
        try:
            usage = shutil.disk_usage(Path.home())
            disk.update_amounts(usage.total, usage.free)
            total = human_size(usage.total)
            used = human_size(usage.used)
            free = human_size(usage.free)
            summary = f"{used} used  •  {free} free  •  {total} capacity"
        except OSError:
            summary = "Drive usage not available"
        storage_col.addWidget(disk, 1)
        storage_col.addWidget(label(summary, "caption", wrap=True))
        storage_col.addWidget(label(
            "OS disk usage only. App and mod bytes may overlap with installed games.", "subtle", wrap=True))
        r.addWidget(storage, 4)

        launcher, launcher_col = panel()
        launcher_col.addWidget(section_title("Launchers", "Observed installs"))
        if not self.inventory.scanned_at:
            launcher_col.addWidget(label("Run Scan PC to inspect installed launchers.", "subtle", wrap=True))
        else:
            counts = unique_launcher_counts(self.inventory.games)
            reported = defaultdict(int)
            missing = defaultdict(int)
            for game in self.inventory.games:
                family = game.launcher if len(game.claimed_by) == 1 else "Multiple launchers"
                if game.size_bytes is None:
                    missing[family] += 1
                else:
                    reported[family] += game.size_bytes
            for name, count in sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:9]:
                line = QWidget()
                inner = row(spacing=7)
                line.setLayout(inner)
                opening = button(name, lambda _=False, n=name: self._go_launcher(n), kind="link")
                inner.addWidget(opening)
                inner.addStretch()
                amount = (human_size(reported[name]) + " known" if reported[name] else "Size unknown")
                inner.addWidget(label(f"{count}  •  {amount}", "caption"))
                launcher_col.addWidget(line)
                bar = QProgressBar()
                bar.setTextVisible(False)
                bar.setMaximum(max(1, max(counts.values())))
                bar.setValue(count)
                bar.setFixedHeight(6)
                color = {
                    "Steam": "#27A6E5",
                    "Xbox": "#53CA64",
                    "Epic Games": "#B788EC",
                    "EA App": "#FF714D",
                    "Ubisoft Connect": "#8A9BFF",
                    "GOG Galaxy": "#D46ADB",
                    "Battle.net": "#56B9EC",
                }.get(name, "#91A5B6")
                bar.setStyleSheet(
                    "QProgressBar { background:#25303A; border:0; border-radius:3px; }"
                    "QProgressBar::chunk { background:" + color +
                    "; border-radius:3px; }")
                bar.setAccessibleName(f"{name}: {count} recorded installations, "
                                      "bar relative to launcher with most installs, "
                                      "not actual disk usage.")
                bar.setToolTip(
                    f"{count} observed installations out of "
                    f"{max(1, max(counts.values()))} in the most represented launcher. "
                    "This is NOT a disk-space chart.")
                launcher_col.addWidget(bar)
        launcher_col.addStretch()
        r.addWidget(launcher, 3)

        recent, recent_col = panel()
        recent_col.addWidget(section_title("Recent Findings", "Last scan"))
        findings = self.inventory.graveyard[:5]
        if not findings:
            recent_col.addWidget(label("No review findings yet. Scan first or adjust the age threshold.", "subtle", wrap=True))
        for item in findings:
            ctl = button(item.name[:24] + "  ›",
                         lambda _=False, key=item.key: self._go_grave_item(key), kind="link")
            ctl.setToolTip(item.finding)
            recent_col.addWidget(ctl)
            recent_col.addWidget(label(
                item.category + "  •  " + human_size(item.apparent_bytes) +
                " apparent", "caption"))
        recent_col.addStretch()
        r.addWidget(recent, 3)
        page.content.addWidget(metrics)

        bottom = QWidget()
        bottom_row = row(spacing=12)
        bottom.setLayout(bottom_row)
        capture, cap_col = panel()
        cap_title = QWidget()
        cap_top = row(spacing=5)
        cap_title.setLayout(cap_top)
        cap_top.addWidget(label("Latest Screenshot", "sectionTitle"))
        cap_top.addStretch()
        cap_top.addWidget(button("View all  ›", lambda: self.navigate("Screenshots"),
                                 kind="link"))
        cap_col.addWidget(cap_title)
        cap_col.addWidget(LandscapeArt(136))
        if self.inventory.screenshots:
            latest = max(self.inventory.screenshots, key=lambda x: x.modified)
            cap_col.addWidget(label("▧", "metricValue"))
            cap_col.addWidget(label(Path(latest.path).name, "sectionTitle", wrap=True))
            cap_col.addWidget(label(human_size(latest.size) +
                                   "  •  Content not opened automatically", "caption", wrap=True))
            cap_col.addWidget(button("Preview this image", lambda _=False, e=latest: self._preview_capture(e)))
        else:
            cap_col.addWidget(label(
                "No game screenshots found in supported locations. Scan PC or add a screenshot folder.",
                "subtle", wrap=True))
        cap_col.addStretch()
        bottom_row.addWidget(capture, 2)

        queue, queue_col = panel()
        queue_col.addWidget(section_title("Graveyard Review Queue",
                                          f"{len(self.inventory.graveyard)} findings"))
        queue_checks = []
        for item in self.inventory.graveyard[:4]:
            line = QWidget()
            inner = row(spacing=5)
            line.setLayout(inner)
            checkbox = QCheckBox()
            checkbox.setAccessibleName("Select " + item.name + " for Recycle Bin review")
            checkbox.setEnabled(item.can_recycle and item.old_file is not None)
            checkbox.setToolTip(
                "Safe review only; requires separate confirmation." if checkbox.isEnabled()
                else "Protected or information only. Right-click in Graveyard for the reason.")
            inner.addWidget(checkbox)
            ctl = button(item.name[:24] + "  ›",
                         lambda _=False, e=item: self._inspect_grave_entry(e),
                         kind="link")
            ctl.setToolTip(item.finding)
            inner.addWidget(ctl, 1)
            queue_col.addWidget(line)
            queue_col.addWidget(label(
                item.category + "  •  " +
                human_size(item.apparent_bytes) + " apparent", "caption", wrap=True))
            if checkbox.isEnabled():
                queue_checks.append((checkbox, item))
        if not self.inventory.graveyard:
            queue_col.addWidget(label(
                "Nothing queued. No cleanup is automatic.", "subtle", wrap=True))
        queue_col.addStretch()
        queue_actions = QWidget()
        actions_layout = row(spacing=6)
        queue_actions.setLayout(actions_layout)
        actions_layout.addWidget(button(
            "See all", lambda: self.navigate("Graveyard"), kind="primary"))
        recycle_button = button("Recycle selected…",
            lambda: self._approve_recycle(
                [entry for checkbox, entry in queue_checks if checkbox.isChecked()]),
            kind="danger")
        recycle_button.setEnabled(bool(queue_checks))
        actions_layout.addWidget(recycle_button)
        queue_col.addWidget(queue_actions)
        bottom_row.addWidget(queue, 2)

        attention, alert_col = panel(kind="alertCard")
        alert_col.addWidget(section_title("Needs Review"))
        alert_col.addWidget(LandscapeArt(91))
        uncertain = next((m for m in self.inventory.mods if getattr(m, "status", "")), None)
        if uncertain:
            alert_col.addWidget(label(str(getattr(uncertain, "source", "Mod storage")), "sectionTitle", wrap=True))
            alert_col.addWidget(label(
                "Related mod folder detected. Its age alone cannot establish whether it's safe to delete.",
                "subtle", wrap=True))
            alert_col.addWidget(button("Inspect protected mods", lambda: self.navigate("Mods"), kind="primary"))
        else:
            alert_col.addWidget(label(
                "Nothing identified for manual review. Protected content stays protected.",
                "subtle", wrap=True))
        alert_col.addStretch()
        bottom_row.addWidget(attention, 2)
        page.content.addWidget(bottom)
        page.content.addWidget(label(
            "Recycle Bin moves are NOT confirmed free space. No permanent deletion, "
            "automatic screenshot cleanup or fake savings metrics.", "caption", wrap=True))

    def _go_launcher(self, launcher):
        self._pending_launcher_filter = launcher
        self.navigate("Games")

    def games_page(self):
        page = self._new("Games", "All installed games Game Grave can verify, in one list across supported launchers.")
        if self._not_scanned(page):
            return
        ctrl = QWidget()
        filters = row()
        ctrl.setLayout(filters)
        self.game_search = QLineEdit()
        self.game_search.setPlaceholderText("Search any game, launcher, or install path…")
        self.game_search.setAccessibleName("Search installed games")
        filters.addWidget(self.game_search, 3)
        self.game_filter = QComboBox()
        self.game_filter.addItems(["All launchers"] + sorted({
            g.launcher for g in self.inventory.games
        }))
        self.game_filter.setAccessibleName("Filter by launcher")
        preferred = getattr(self, "_pending_launcher_filter", None)
        if preferred is not None:
            index = self.game_filter.findText(preferred)
            if index >= 0:
                self.game_filter.setCurrentIndex(index)
            self._pending_launcher_filter = None
        filters.addWidget(self.game_filter, 2)
        self.game_sort = QComboBox()
        self.game_sort.addItems(["Largest known size", "Smallest known size",
                                 "Recently played", "Oldest played", "Name A to Z", "Launcher"])
        filters.addWidget(self.game_sort, 2)
        page.content.addWidget(ctrl)

        known, unknown = reported_game_bytes(self.inventory.games)
        stats = QWidget()
        statrow = row()
        stats.setLayout(statrow)
        statrow.addWidget(MetricCard("Detected installations", str(len(self.inventory.games)), "Evidence-backed records"))
        statrow.addWidget(MetricCard("Known reported sizes", human_size(known), "Not equal to disk space reclaimed"))
        statrow.addWidget(MetricCard("Size unknown", str(unknown), "Never assumed to be zero", tone="amber"))
        page.content.addWidget(stats)
        p, pcol = panel()
        self.game_table = data_table(["GAME", "LAUNCHER", "SIZE", "LAST PLAYED", "EVIDENCE"])
        self.game_table.setColumnWidth(0, 245)
        self.game_table.setColumnWidth(1, 150)
        self.game_table.setColumnWidth(2, 106)
        self.game_table.setColumnWidth(3, 145)
        self.game_table.setMinimumHeight(370)
        pcol.addWidget(self.game_table)
        page.content.addWidget(p)
        self.game_details = panel()[0]
        self.game_details_col = self.game_details.layout()
        page.content.addWidget(self.game_details)
        self.game_search.textChanged.connect(self._fill_games)
        self.game_filter.currentTextChanged.connect(self._fill_games)
        self.game_sort.currentTextChanged.connect(self._fill_games)
        self.game_table.itemSelectionChanged.connect(self._game_details)
        self.game_table.cellDoubleClicked.connect(
            lambda row_idx, _column: self._inspect_game_record(
                self._shown_games[row_idx])
            if 0 <= row_idx < len(self._shown_games) else None)
        self.game_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.game_table.customContextMenuRequested.connect(self._games_context_menu)
        self._fill_games()

    def _fill_games(self, *_):
        if not hasattr(self, "game_table"):
            return
        query = self.game_search.text().casefold().strip()
        launcher = self.game_filter.currentText()
        rows = [g for g in self.inventory.games
                if (launcher == "All launchers" or g.launcher == launcher)
                and (not query or query in (g.name + " " + g.launcher + " " +
                                             g.install_path).casefold())]
        sort = self.game_sort.currentText()
        if sort == "Name A to Z":
            rows.sort(key=lambda g: (g.name.casefold(), g.launcher.casefold()))
        elif sort == "Launcher":
            rows.sort(key=lambda g: (g.launcher.casefold(), g.name.casefold()))
        elif sort in ("Recently played", "Oldest played"):
            rows.sort(key=lambda g: (g.last_played_at is None,
                                     -(g.last_played_at or 0) if sort == "Recently played"
                                     else g.last_played_at or 0))
        else:
            rows.sort(key=lambda g: (g.size_bytes is None,
                                     (g.size_bytes or 0) * (-1 if sort == "Largest known size" else 1)))
        self._shown_games = rows[:500]  # bounded presentation, full inventory retained
        self.game_table.setRowCount(len(self._shown_games))
        for i, g in enumerate(self._shown_games):
            fields = (g.name, g.launcher, readable_bytes(g.size_bytes),
                      age_text(g.last_played_at) if g.last_played_at is not None else "Unknown",
                      g.status)
            for c, text in enumerate(fields):
                _table_text(self.game_table, i, c, text)
            self.game_table.setRowHeight(i, 36)
        if rows and len(rows) > len(self._shown_games):
            self.status.setText(
                f"Showing first 500 of {len(rows)} filtered games. Narrow the search for later results.")
        if self._shown_games and not _selected_indices(self.game_table):
            self.game_table.selectRow(0)
        self._game_details()

    def _game_details(self):
        from gg_desktop.widgets import destroy_layout
        destroy_layout(self.game_details_col)
        selected = _selected_indices(self.game_table)
        if not selected or selected[0] >= len(getattr(self, "_shown_games", [])):
            self.game_details_col.addWidget(label("Select a game to see source evidence and safe actions.", "subtle"))
            return
        game = self._shown_games[selected[0]]
        self.game_details_col.addWidget(label(game.name, "sectionTitle", wrap=True))
        for line in (
            f"Launcher: {game.launcher}",
            f"Install location: {game.install_path}",
            f"Install status: {game.status}",
            f"Evidence: {game.install_evidence}",
            f"Size: {readable_bytes(game.size_bytes)} ({game.size_source})",
            f"Last played: {age_text(game.last_played_at) if game.last_played_at else 'Unknown'}",
        ):
            self.game_details_col.addWidget(label(line, "subtle", wrap=True))
        actions = QWidget()
        bar = row()
        actions.setLayout(bar)
        open_btn = button("Open installation folder",
                          lambda _=False, path=game.install_path: self._open_folder(path))
        open_btn.setEnabled("open_folder" in game.capabilities)
        bar.addWidget(open_btn)
        bar.addWidget(button("See related Game DNA", lambda: self.navigate("Game DNA")))
        if "steam_uninstall" in game.capabilities and game.app_id and game.app_id.isdecimal():
            bar.addWidget(button("Open Steam uninstall…",
                                 lambda _=False, g=game: self._steam_uninstall(g), kind="danger"))
        bar.addStretch()
        bar.addWidget(button("View complete details…",
                             lambda _=False, g=game: self._inspect_game_record(g)))
        self.game_details_col.addWidget(actions)

    def _steam_uninstall(self, game):
        if ("steam_uninstall" not in game.capabilities or game.launcher != "Steam"
                or not game.app_id or not game.app_id.isdecimal()):
            return
        if not self.confirm("Open Steam uninstall?", f"Open Steam's own uninstall dialog for\n\n{game.name}?\n\n"
                            "Game Grave will not remove the installation directly.", destructive=True):
            return
        if sys.platform != "win32":
            self.error("Windows only", "Steam uninstall shortcut requires Windows.")
            return
        try:
            os.startfile("steam://uninstall/" + game.app_id)
        except OSError as exc:
            self.error("Steam unavailable", str(exc))

    def _open_folder(self, path: str):
        if not _safe_open_path(path):
            self.error("Folder unavailable", "The directory is missing, redirected, or refused by Windows.")

    def _detail_dialog(self, title: str, description: str):
        """Fully populated, independently scrollable detail view; no blank popups."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Game Grave | " + title)
        dialog.resize(660, 570)
        layout = column(spacing=12, margins=(18, 18, 18, 18))
        dialog.setLayout(layout)
        layout.addWidget(label(title, "sectionTitle", wrap=True))
        details = QPlainTextEdit(dialog)
        details.setReadOnly(True)
        details.setPlainText(description)
        details.setAccessibleName("Game Grave item details")
        layout.addWidget(details, 1)
        close_button = button("Close", dialog.accept)
        close_button.setDefault(True)
        layout.addWidget(close_button)
        dialog.exec()

    def _inspect_grave_entry(self, entry):
        self._detail_dialog(
            str(entry.name), graveyard_detail_text(
                entry, self.settings.get("never_touch", [])))

    def _inspect_game_record(self, game):
        self._detail_dialog(str(game.name), game_detail_text(game))

    def _inspect_selected_grave(self):
        selected = self._selected_grave_entries()
        if len(selected) == 1:
            self._inspect_grave_entry(selected[0])
        elif selected:
            self.info("Choose one item", "Select one row for complete details.")
        else:
            self.info("Choose a finding", "Click a Graveyard row to inspect it.")

    def _inspect_selected_game(self):
        selected = _selected_indices(self.game_table)
        if len(selected) == 1 and selected[0] < len(self._shown_games):
            self._inspect_game_record(self._shown_games[selected[0]])
        else:
            self.info("Choose one game", "Select one Games row to inspect it.")

    def _set_personal_protection(self, path: str, *, protect: bool, return_route: str):
        """Explicit user Never Touch action, never a deletion shortcut."""
        try:
            action, reason = protection_action(path, list(self.settings.get("never_touch", [])))
            if action != ("Protect" if protect else "Unprotect"):
                self.info("Protection unchanged", reason)
                return
            if not self.confirm(
                "Protect this item?" if protect else "Remove your personal protection?",
                ("Add a Never Touch rule for:\n" if protect else
                 "Remove only your own exact Never Touch rule for:\n") + path +
                "\n\nNo files will be moved. Built-in protection cannot be removed."
            ):
                return
            updated = dict(self.settings)
            updated["never_touch"] = set_item_protection(
                list(self.settings.get("never_touch", [])), path, protect=protect)
            save_settings(updated)
            self.settings = updated
            refresh_graveyard(self.inventory, self.settings)
            self.status.setText(
                "Item protected. Nothing moved." if protect else
                "Personal rule removed. Deletion still requires separate safety checks.")
            self.navigate(return_route)
        except (ValueError, OSError) as exc:
            self.error("Cannot change item protection", str(exc))

    @staticmethod
    def _right_clicked_row(table, point):
        """Preserve a multi-selection if right-click is already inside it."""
        index = table.indexAt(point)
        if not index.isValid():
            return None
        row = index.row()
        if row not in _selected_indices(table):
            table.selectRow(row)
        return row

    def _graveyard_context_menu(self, point):
        row_idx = self._right_clicked_row(self.grave_table, point)
        if row_idx is None or row_idx >= len(self._shown_graves):
            return
        entry = self._shown_graves[row_idx]
        action, reason = protection_action(
            entry.path, list(self.settings.get("never_touch", [])))
        menu = QMenu(self.grave_table)
        menu.addAction("View complete details…",
                       lambda: self._inspect_grave_entry(entry))
        menu.addSeparator()
        if entry.category == "Old game screenshot":
            menu.addAction("Preview this screenshot…",
                           lambda: self._preview_grave_image(entry))
        else:
            move = menu.addAction("Move to Recycle Bin…",
                                  lambda: self._approve_recycle([entry]))
            move.setEnabled(entry.can_recycle and entry.old_file is not None)
            if not move.isEnabled():
                move.setToolTip("Protected or review-only: " + entry.protection)
        if action == "Protect":
            menu.addAction("Protect this item (Never Touch)",
                           lambda: self._set_personal_protection(
                               entry.path, protect=True, return_route="Graveyard"))
        elif action == "Unprotect":
            menu.addAction("Unprotect this item…",
                           lambda: self._unprotect_grave(entry))
        elif reason.startswith("A parent folder"):
            menu.addAction("Manage parent protection…",
                           lambda: self._manage_parent_rule(entry))
        else:
            notice = menu.addAction("Built-in protection: cannot override")
            notice.setEnabled(False)
        menu.addSeparator()
        menu.addAction("Open containing folder",
                       lambda: self._open_folder(str(Path(entry.path).parent)))
        menu.addAction("Why is this protected?",
                       lambda: self.info("Graveyard review status",
                           entry.protection + "\n\n" + entry.finding +
                           "\n\n" + reason))
        menu.exec(self.grave_table.viewport().mapToGlobal(point))

    def _games_context_menu(self, point):
        row_idx = self._right_clicked_row(self.game_table, point)
        if row_idx is None or row_idx >= len(self._shown_games):
            return
        game = self._shown_games[row_idx]
        menu = QMenu(self.game_table)
        menu.addAction("View complete game details…",
                       lambda: self._inspect_game_record(game))
        opener = menu.addAction("Open installation folder",
                  lambda: self._open_folder(game.install_path))
        opener.setEnabled("open_folder" in game.capabilities)
        menu.addAction("View Game DNA", lambda: self.navigate("Game DNA"))
        if ("steam_uninstall" in game.capabilities and game.app_id
                and game.app_id.isdecimal()):
            menu.addAction("Uninstall through Steam…",
                           lambda: self._steam_uninstall(game))
        else:
            disabled = menu.addAction("Direct deletion unavailable (protected game)")
            disabled.setEnabled(False)
        menu.exec(self.game_table.viewport().mapToGlobal(point))

    def _go_grave_item(self, key):
        self._pending_grave_key = key
        self.navigate("Graveyard")

    def graveyard_page(self):
        page = self._new("Graveyard",
                         "Review apparent storage, understand protections, and approve individual Recycle Bin moves.")
        if self._not_scanned(page):
            return
        totals = graveyard_totals(self.inventory.graveyard)
        summary = QWidget()
        sr = row()
        summary.setLayout(sr)
        for title, value, hint, tone in (
            ("Findings", str(totals["items"]), "Not deleted", "text"),
            ("Reviewable size", human_size(totals["reviewable_bytes"]), "Apparent, not reclaimed", "cyan"),
            ("Protected", str(totals["protected_items"]), "Built-in and personal safeguards", "amber"),
        ):
            sr.addWidget(MetricCard(title, value, hint, tone=tone))
        page.content.addWidget(summary)

        filters = QWidget()
        controls = row()
        filters.setLayout(controls)
        self.grave_search = QLineEdit()
        self.grave_search.setPlaceholderText("Search findings and paths…")
        controls.addWidget(self.grave_search, 3)
        self.grave_type = QComboBox()
        self.grave_type.addItems(["All types"] + sorted({e.category for e in self.inventory.graveyard}))
        controls.addWidget(self.grave_type, 2)
        self.grave_state = QComboBox()
        self.grave_state.addItems(["All findings", "Ready for review", "Protected / preview only"])
        controls.addWidget(self.grave_state, 2)
        page.content.addWidget(filters)

        content = QWidget()
        cr = row(spacing=12)
        content.setLayout(cr)
        table_box, table_col = panel(padding=8)
        self.grave_table = data_table(["ITEM", "TYPE", "APPARENT SIZE", "STATUS"])
        self.grave_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.grave_table.setColumnWidth(0, 250)
        self.grave_table.setColumnWidth(1, 195)
        self.grave_table.setColumnWidth(2, 118)
        self.grave_table.setMinimumHeight(440)
        table_col.addWidget(self.grave_table)
        actions = QWidget()
        ar = row()
        actions.setLayout(ar)
        ar.addWidget(button("Select reviewable", self._select_eligible))
        ar.addWidget(button("Clear selection", self.grave_table.clearSelection))
        ar.addWidget(button("Move selected to Recycle Bin…",
                            self._delete_grave_selected, kind="danger"))
        table_col.addWidget(actions)
        cr.addWidget(table_box, 7)
        detail, detail_col = panel()
        self.grave_detail = detail_col
        cr.addWidget(detail, 3)
        page.content.addWidget(content)
        guidance, guidance_col = panel(padding=12)
        reviewable = sum(e.can_recycle and e.old_file is not None
                         for e in self.inventory.graveyard)
        guidance_col.addWidget(label(
            f"{reviewable} ordinary file(s) available for safe Recycle Bin review. "
            "Installed games, managed mods and saves stay protected. "
            "Right-click any row for item-specific actions.",
            "subtle", wrap=True))
        guidance_col.addWidget(button(
            "Why won't these files recycle?",
            lambda: self.info(
                "Graveyard and Recycle Bin",
                "The Graveyard reviews older files in the folder you selected, "
                "game-related archives, and recordings. Other findings show "
                "protected game/mod data for inspection only.\n\n"
                "To recycle: right-click a REVIEWABLE ordinary file, choose "
                "'Move to Recycle Bin', and approve it. "
                "If none are eligible, visit Old Files to change the reviewed folder. "
                "For an exact personal Never Touch rule, right-click and Unprotect.\n\n"
                "Game Grave also runs a real, reversible Windows recovery check "
                "before touching any approved file. If that check fails, no "
                "user data is moved; use Windows File Explorer instead. "
                "Installed games should be uninstalled in their launcher.")))
        guidance_col.addWidget(button(
            "Test Windows Recycle Bin with a disposable file…",
            self._test_recycle_bin_safely))
        page.content.addWidget(guidance)
        page.content.addWidget(label(
            "IMPORTANT: User-added protection can be removed here. Built-in game/save/mod safeguards "
            "cannot. No permanent-delete fallback. Images require individual preview.", "warning", wrap=True))
        self.grave_search.textChanged.connect(self._fill_graveyard)
        self.grave_type.currentTextChanged.connect(self._fill_graveyard)
        self.grave_state.currentTextChanged.connect(self._fill_graveyard)
        self.grave_table.itemSelectionChanged.connect(self._grave_details)
        self.grave_table.cellDoubleClicked.connect(
            lambda row_idx, _column: self._inspect_grave_entry(
                self._shown_graves[row_idx])
            if 0 <= row_idx < len(self._shown_graves) else None)
        self.grave_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.grave_table.customContextMenuRequested.connect(self._graveyard_context_menu)
        self._fill_graveyard()

    def _fill_graveyard(self, *_):
        query = self.grave_search.text().casefold().strip()
        category = self.grave_type.currentText()
        mode = self.grave_state.currentText()
        rows = [
            e for e in self.inventory.graveyard
            if (category == "All types" or e.category == category)
            and (mode == "All findings" or
                 (mode == "Ready for review" and e.can_recycle) or
                 (mode == "Protected / preview only" and not e.can_recycle))
            and (not query or query in (e.name + " " + e.path + " " + e.category).casefold())
        ]
        rows.sort(key=lambda x: (-x.apparent_bytes, x.name.casefold()))
        self._shown_graves = rows[:500]
        self.grave_table.setRowCount(len(self._shown_graves))
        for i, e in enumerate(self._shown_graves):
            protection = protection_action(e.path, list(self.settings.get("never_touch", [])))[0]
            status = ("Unprotect available" if protection == "Unprotect" else
                      "Preview individually" if e.category == "Old game screenshot" and
                      not is_protected_path(Path(e.path), self.settings.get("never_touch", [])) else
                      "Reviewable" if e.can_recycle else "Protected / inspect")
            for c, value in enumerate((e.name, e.category,
                                       human_size(e.apparent_bytes), status)):
                _table_text(self.grave_table, i, c, value)
            if protection == "Unprotect":
                unlock = button(
                    "Unprotect this item",
                    lambda _checked=False, entry=e: self._unprotect_grave(entry))
                unlock.setAccessibleName("Unprotect your personal rule for " + e.name)
                unlock.setToolTip(
                    "Removes only your exact personal Never Touch rule after confirmation. "
                    "No file will be deleted.")
                self.grave_table.setCellWidget(i, 3, unlock)
                self.grave_table.setRowHeight(i, 45)
            elif protection is None and status == "Protected / inspect":
                self.grave_table.setRowHeight(i, 37)
            else:
                self.grave_table.setRowHeight(i, 37)
        selected_key = getattr(self, "_pending_grave_key", None)
        if selected_key is not None:
            for i, e in enumerate(self._shown_graves):
                if e.key == selected_key:
                    self.grave_table.selectRow(i)
                    self.grave_table.scrollToItem(self.grave_table.item(i, 0))
                    break
            self._pending_grave_key = None
        if self._shown_graves and not _selected_indices(self.grave_table):
            self.grave_table.selectRow(0)
        self._grave_details()

    def _selected_grave_entries(self):
        return [self._shown_graves[i] for i in _selected_indices(self.grave_table)
                if i < len(self._shown_graves)]

    def _grave_details(self):
        from gg_desktop.widgets import destroy_layout
        destroy_layout(self.grave_detail)
        entries = self._selected_grave_entries()
        if not entries:
            self.grave_detail.addWidget(label("Select a finding", "sectionTitle"))
            self.grave_detail.addWidget(label(
                "See why it is protected, preview images, or remove only your own exact Never Touch rule.",
                "subtle", wrap=True))
            self.grave_detail.addStretch()
            return
        if len(entries) != 1:
            self.grave_detail.addWidget(label(f"{len(entries)} items selected", "sectionTitle"))
            self.grave_detail.addWidget(label("Only eligible individual files can enter Recycle Bin review. "
                                              "Screen captures are never bulk eligible.", "warning", wrap=True))
            self.grave_detail.addStretch()
            return
        e = entries[0]
        action, reason = graveyard_protection_decision(
            e, self.settings.get("never_touch", []))
        self.grave_detail.addWidget(label(e.name, "sectionTitle", wrap=True))
        for text in (e.category, human_size(e.apparent_bytes) + " apparent", e.path, e.finding):
            self.grave_detail.addWidget(label(text, "subtle", wrap=True))
        self.grave_detail.addWidget(label(
            "WHY IT WAS FOUND", "eyebrow"))
        self.grave_detail.addWidget(label(e.finding, "subtle", wrap=True))
        self.grave_detail.addWidget(label(
            "WHY THIS IS PROTECTED" if not e.can_recycle else "REVIEW STATUS",
            "eyebrow"))
        self.grave_detail.addWidget(label(reason if not e.can_recycle else
                                          "Reviewable only. Nothing is moved without confirmation.",
                                          "warning", wrap=True))
        self.grave_detail.addSpacing(8)
        if action == "Unprotect this item":
            self.grave_detail.addWidget(button(
                "Unlock  •  Unprotect this item",
                lambda _=False, e=e: self._unprotect_grave(e), kind="primary"))
        elif action == "Manage parent rule":
            self.grave_detail.addWidget(button(
                "Manage parent Never Touch rule",
                lambda _=False, e=e: self._manage_parent_rule(e)))
        elif action == "Why protected?":
            self.grave_detail.addWidget(label(
                "Built-in protection cannot be overridden from Graveyard. "
                "Manage the installed game or active mod profile with its proper launcher.",
                "warning", wrap=True))
        if e.category == "Old game screenshot":
            self.grave_detail.addWidget(button(
                "Preview screenshot  ▧",
                lambda _=False, e=e: self._preview_grave_image(e)))
        elif e.can_recycle and action != "Unprotect this item":
            self.grave_detail.addWidget(button(
                "Review moving this file to Recycle Bin…",
                lambda _=False, e=e: self._approve_recycle([e]), kind="danger"))
        self.grave_detail.addWidget(button(
            "View complete details…", lambda _=False, e=e: self._inspect_grave_entry(e)))
        self.grave_detail.addWidget(button(
            "Open containing folder",
            lambda _=False, e=e: self._open_folder(str(Path(e.path).parent))))
        self.grave_detail.addStretch()

    def _unprotect_grave(self, entry):
        action, reason = protection_action(entry.path, list(self.settings.get("never_touch", [])))
        if action != "Unprotect":
            self.error("Protection stays on", reason)
            return
        if not self.confirm("Remove your protection?",
                            "Remove only the exact Never Touch rule for:\n" + entry.path +
                            "\n\nThis does NOT delete anything. Game Grave will run "
                            "all safety checks again before a separate Recycle Bin approval."):
            return
        try:
            self.settings = unprotect_exact_personal_item(self.settings, entry.path)
            refresh_graveyard(self.inventory, self.settings)
            self.status.setText("Exact personal rule removed. No files were moved.")
            self.navigate("Graveyard")
        except (OSError, ValueError) as exc:
            self.error("Protection not changed", str(exc))

    def _manage_parent_rule(self, entry):
        for rule in self.settings.get("never_touch", []):
            if (isinstance(rule, str) and
                    is_protected_path(Path(entry.path), [rule]) and
                    os.path.normcase(os.path.abspath(rule)) !=
                    os.path.normcase(os.path.abspath(entry.path))):
                self._focus_never_touch_rule = rule
                break
        self.navigate("Settings")

    def _test_recycle_bin_safely(self):
        """Verify desktop recovery without selecting or touching user files."""
        if self.cleaning or self.scanning:
            self.info("Finish the current operation", "Try the safe test after scanning ends.")
            return
        root = Path(str(self.settings.get("scan_folder", "")))
        if not self.confirm(
            "Run disposable Windows Recycle Bin test?",
            "Game Grave will create ONE tiny test file inside:\n" + str(root) +
            "\n\nIt will attempt to recycle and restore only those exact disposable "
            "bytes, then clean up its own test file if safe. "
            "No personal game, mod, save, or screenshot is selected. "
            "Results will explain whether verified cleanup is available on this PC."
        ):
            return
        self.status.setText("Testing Windows Recycle Bin using disposable data only…")
        def run(_emit):
            from safety_selftest import check_disposable_undo
            return check_disposable_undo(
                root, tuple(self.settings.get("never_touch", [])))
        def finished(outcome):
            self.status.setText("Verified disposable Recycle Bin + Undo round trip passed.")
            self.info("Recycle Bin verification passed",
                "Windows successfully recycled and restored a tiny Game Grave "
                "test file with byte-identical content. No user files were touched.\n\n"
                "A successful test does not override protection for installed games "
                "or guarantee every future file will recycle; each file is checked again.")
        self.job(run, finished, error_title="Recycle Bin test failed: no user data moved")

    def _select_eligible(self):
        from PySide6.QtCore import QItemSelectionModel
        self.grave_table.clearSelection()
        selector = self.grave_table.selectionModel()
        for i, entry in enumerate(self._shown_graves):
            if entry.can_recycle and entry.old_file is not None and (
                    entry.category != "Old game screenshot") and (
                    not is_protected_path(Path(entry.path),
                                          self.settings.get("never_touch", []))):
                index = self.grave_table.model().index(i, 0)
                selector.select(index, QItemSelectionModel.Select | QItemSelectionModel.Rows)

    def _delete_grave_selected(self):
        selected = self._selected_grave_entries()
        if not selected:
            self.info("Nothing selected", "Select ordinary reviewable files. "
                      "Screenshots must each be previewed individually.")
            return
        if any((not e.can_recycle or e.category == "Old game screenshot") for e in selected):
            self.error("Protected items in selection",
                       "Protected findings and screenshots cannot be batch deleted. "
                       "Select an item to unprotect or individually preview it.")
            return
        self._approve_recycle(selected)

    def _approve_recycle(self, selected, *, image_approved=False):
        if self.cleaning or self.scanning:
            self.info("Game Grave is busy", "Finish the scan or cleanup before choosing another action.")
            return
        if not selected or len(selected) > 200:
            self.error("Review too large", "Choose between 1 and 200 files at a time.")
            return
        if any(not e.can_recycle for e in selected):
            self.error("Not approved", "One or more files remain protected.")
            return
        if any(e.category == "Old game screenshot" for e in selected):
            if (len(selected) != 1 or not image_approved or
                    not selected[0].screenshot_reviewed):
                self.error("Preview required", "You must preview this exact image first.")
                return
        names = "\n".join(" • " + e.name[:100] for e in selected[:12])
        if len(selected) > 12:
            names += f"\n • ...and {len(selected) - 12} additional explicitly selected files"
        summary = ("Move these " + str(len(selected)) +
                   " reviewed file(s) to Windows Recycle Bin?\n\n" + names +
                   "\n\nNo permanent deletion. This does NOT immediately free disk space. "
                   "Windows restoration must be verified for each file first. "
                   "If a file changed, it will be skipped.")
        if not self.confirm("Move reviewed files to Recycle Bin?", summary, destructive=True):
            return
        self.cleaning = True
        rules = tuple(self.settings.get("never_touch", []))
        reviewed = tuple(selected)
        session = "crimson-" + uuid.uuid4().hex[:10]
        self.status.setText("Windows is validating Recycle Bin recovery for each approved file…")
        def success(report):
            self.cleaning = False
            self.status.setText(
                f"{report['completed']} item(s) moved to Recycle Bin; "
                f"{len(report['skipped'])} skipped. This is NOT reclaimed disk space.")
            if report["completed"]:
                self._remove_missing_inventory()
                refresh_graveyard(self.inventory, self.settings)
                self.navigate("Graveyard")
            self.info("Reviewed cleanup finished",
                      f"{report['completed']} moved to Recycle Bin, {len(report['skipped'])} not moved. "
                      f"{report['recovery_warnings']} Undo log warnings. "
                      "\n\nRecycle Bin may still occupy space."
                      + ("\n\n" + "\n".join(report["skipped"][:6]) if report["skipped"] else ""))
        reviewed_root = str(self.settings.get("scan_folder", ""))
        min_age_days = max(
            int(self.settings.get("files_stale_days", 180)),
            int(self.settings.get("graveyard_days", 365)))
        protected_ownership = tuple(
            str(row.install_path) for row in self.inventory.games
            if getattr(row, "install_path", None))
        protected_ownership += tuple(
            str(row.path) for row in self.inventory.mods
            if getattr(row, "path", None))
        self.job(lambda _emitter: recycle_reviewed_entries(
            reviewed, rules, session, review_root=reviewed_root,
            min_age_days=min_age_days, managed_roots=protected_ownership),
                 success, error_title="Recycling failed")

    def _remove_missing_inventory(self):
        # Recycle operation has completed. Filter stale entries; never infer
        # that an item disappeared from a previous partial scan.
        self.inventory.files = [f for f in self.inventory.files if is_unchanged(f)]
        self.inventory.recordings = [f for f in self.inventory.recordings if is_unchanged(f)]
        self.inventory.screenshots = [f for f in self.inventory.screenshots if is_unchanged(f)]

    def _preview_capture(self, record):
        e = next((e for e in self.inventory.graveyard if e.old_file == record
                  and e.category == "Old game screenshot"), None)
        if e is not None:
            self._preview_grave_image(e)
            return
        if record not in self.inventory.screenshots:
            self.error("Unknown screenshot", "Scan again before previewing an unrecognized image.")
            return
        # A discovered recent screenshot is not an old-file finding, but its
        # owner can still preview and explicitly review moving that image
        # through the same protected, reversible backend. No bulk authority.
        age = max(0, int((datetime.now().timestamp() - record.modified) / 86400))
        item = GraveyardEntry(
            key="screenshot:preview:" + str(record.path).casefold(),
            name=Path(record.path).name, path=record.path,
            category="Old game screenshot",
            apparent_bytes=record.size, age_days=age,
            relationship="Known screenshot folder; image contents not classified",
            finding="Screenshot found during your manual PC scan. "
                    "Preview it before choosing what to do. "
                    "No deletion happens without a separate approval.",
            protection="Individual preview required; bulk deletion prohibited",
            can_recycle=False, old_file=record,
        )
        self._preview_grave_image(item)

    def _preview_grave_image(self, entry):
        if entry.old_file is None or not is_unchanged(entry.old_file):
            self.error("Screenshot changed", "This image differs from the scanned file. Scan again.")
            return
        record = entry.old_file
        def ready(image):
            qimage = QImage(image.tobytes(), image.width, image.height,
                            image.width * 3, QImage.Format_RGB888).copy()
            dialog = QDialog(self)
            dialog.setWindowTitle("Game Grave  •  Preview before removing an image")
            dialog.resize(920, 710)
            layout = column(spacing=12, margins=(18, 18, 18, 18))
            dialog.setLayout(layout)
            layout.addWidget(label(entry.name, "sectionTitle", wrap=True))
            picture = QLabel()
            picture.setAlignment(Qt.AlignCenter)
            picture.setPixmap(QPixmap.fromImage(qimage).scaled(
                870, 535, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            layout.addWidget(picture, 1)
            layout.addWidget(label(
                "This image was decoded locally only after your request. "
                "A screenshot may be a personal memory. Keep it unless you're certain.",
                "subtle", wrap=True))
            actions = QWidget()
            bar = row()
            actions.setLayout(bar)
            keep = button("Keep screenshot", dialog.reject)
            bar.addWidget(keep)
            discard = button("Review moving THIS image to Recycle Bin…", dialog.accept,
                             kind="danger")
            if is_protected_path(Path(entry.path), self.settings.get("never_touch", [])):
                discard.setEnabled(False)
                discard.setToolTip("Protected. Remove your own rule first if permitted.")
            bar.addWidget(discard)
            layout.addWidget(actions)
            keep.setDefault(True)
            if dialog.exec() == QDialog.Accepted:
                if not is_unchanged(record):
                    self.error("Screenshot changed", "Image was modified after preview. Scan again.")
                    return
                self._approve_recycle(
                    [replace(entry, can_recycle=True, screenshot_reviewed=True)],
                    image_approved=True)
        self.status.setText("Decoding only the screenshot you selected…")
        self.job(lambda _emitter: decode_screenshot_preview(record),
                 ready, error_title="Could not safely preview image")

    def dna_page(self):
        page = self._new("Game DNA", "See how verified game files relate to mods, saves, captures and unknown leftovers.")
        if self._not_scanned(page):
            return
        from game_intelligence import build_game_dna
        dna = build_game_dna(self.inventory.steam, self.inventory.other,
                             self.inventory.mods, self.inventory.saves)
        rowtop = QWidget()
        top = row()
        rowtop.setLayout(top)
        top.addWidget(label("Choose a game", "sectionTitle"))
        choose = QComboBox()
        games = dna.get("games", [])
        choose.addItems([f"{g['game']}  •  {g['launcher']}" for g in games])
        choose.setAccessibleName("Choose game for visual relationship map")
        top.addWidget(choose, 1)
        page.content.addWidget(rowtop)
        visual, visuals = panel()
        visuals.addWidget(section_title("WHERE YOUR GAME'S FILES LIVE",
                                        "Known relationships only"))
        chosen = label("Choose an installed game. No file will be modified.", "subtle", wrap=True)
        visuals.addWidget(chosen)
        diagram = QWidget()
        diaggrid = QGridLayout(diagram)
        diaggrid.setContentsMargins(2, 12, 2, 12)
        diaggrid.setHorizontalSpacing(8)
        diaggrid.setVerticalSpacing(8)
        visuals.addWidget(diagram)
        page.content.addWidget(visual)
        detail, detail_col = panel()
        detail_col.addWidget(section_title("What this means"))
        description = label("", "subtle", wrap=True)
        detail_col.addWidget(description)
        assets_title = label("", "sectionTitle", wrap=True)
        detail_col.addWidget(assets_title)
        page.content.addWidget(detail)
        def show(index):
            from gg_desktop.widgets import destroy_layout
            while diaggrid.count():
                item = diaggrid.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
                elif item.layout():
                    destroy_layout(item.layout())
            if index < 0 or index >= len(games):
                chosen.setText("No verified installed game records.")
                description.setText("Run Scan PC or check supported launcher metadata.")
                assets_title.setText("")
                return
            item = games[index]
            chosen.setText(item["game"] + "  •  " + item["launcher"] +
                           "\n" + item["install_evidence"])
            buckets = [
                ("▣  INSTALLED GAME", "Protected", "Existing game installation"),
                ("♜  MODS", str(len(item["assets"])) + " associated", "Files may still be active"),
                ("▣  SAVES", "Protected", "Ownership not guaranteed"),
                ("▥  RECORDINGS", "Review", "Captured independently of install"),
                ("▧  SCREENSHOTS", "Preview", "Actual images require consent"),
                ("♱  LEFTOVERS", "Unverified", "Absence of launcher manifest proves nothing"),
            ]
            for i, (name, value, meaning) in enumerate(buckets):
                metric = MetricCard(name, value, meaning,
                                    tone="cyan" if i in (3, 4) else
                                         "amber" if i in (1, 2, 5) else "text")
                diaggrid.addWidget(metric, i // 3, i % 3)
            description.setText(
                "Game DNA matches files only with verified install directories or "
                "source-specific IDs. Mods, screenshots and saves remain protected "
                "until independently reviewed. A missing link is UNKNOWN, not permission to delete.")
            assets_title.setText(
                f"{len(item['assets'])} directly associated mod/storage locations. "
                f"{len(dna.get('unresolved', []))} unresolved findings stay protected.")
        choose.currentIndexChanged.connect(show)
        show(choose.currentIndex())
        if not games:
            _box_notice(page, "No Game DNA relationships available. Unknown files stay protected.")

    def mods_page(self):
        page = self._new("Mods", "Mod Radar shows potential mod storage without touching profiles, saves or managed assets.")
        if self._not_scanned(page):
            return
        p, contents = panel()
        contents.addWidget(section_title("Detected mod and manager storage",
                                         str(len(self.inventory.mods)) + " findings"))
        table = data_table(["LOCATION", "SOURCE", "EVIDENCE", "APPARENT SIZE"])
        table.setColumnWidth(0, 305)
        table.setColumnWidth(1, 150)
        table.setColumnWidth(2, 240)
        table.setRowCount(min(len(self.inventory.mods), 400))
        for i, m in enumerate(self.inventory.mods[:400]):
            fields = (str(getattr(m, "path", "")),
                      str(getattr(m, "source", "Unknown")),
                      str(getattr(m, "status", "Protected")),
                      readable_bytes(getattr(m, "apparent_bytes", None)))
            for j, val in enumerate(fields):
                _table_text(table, i, j, val)
        contents.addWidget(table)
        controls = QWidget()
        tools = row()
        controls.setLayout(tools)
        def inspect_selected():
            indexes = _selected_indices(table)
            if not indexes:
                self.info("Choose a mod location", "Select one inventory row.")
                return
            m = self.inventory.mods[indexes[0]]
            self.info("Why this mod is protected",
                      "LOCATION: " + str(getattr(m, "path", "")) +
                      "\n\nSOURCE: " + str(getattr(m, "source", "Unknown")) +
                      "\n\nEVIDENCE: " + str(getattr(m, "status", "Unknown")) +
                      "\n\nGame Grave will never delete a mod-manager "
                      "profile or active mod based on an old timestamp.")
        def mod_context_menu(point):
            index = self._right_clicked_row(table, point)
            if index is None or index >= min(len(self.inventory.mods), 400):
                return
            item = self.inventory.mods[index]
            location = str(getattr(item, "path", ""))
            protection, why = protection_action(
                location, list(self.settings.get("never_touch", [])))
            menu = QMenu(table)
            menu.addAction("Inspect mod location", inspect_selected)
            menu.addAction("Open mod folder", lambda: self._open_folder(location))
            if protection == "Protect":
                menu.addAction("Protect this location",
                    lambda: self._set_personal_protection(
                        location, protect=True, return_route="Mods"))
            elif protection == "Unprotect":
                menu.addAction("Remove personal protection…",
                    lambda: self._set_personal_protection(
                        location, protect=False, return_route="Mods"))
            else:
                locked = menu.addAction("Game/mod protection cannot be bypassed")
                locked.setEnabled(False)
            menu.addSeparator()
            disabled = menu.addAction("Remove mod folder (not safe from Mod Radar)")
            disabled.setEnabled(False)
            menu.addAction("Why protected?",
                lambda: self.info("Mod Radar protection", why +
                "\n\nMod Radar is for review, not deleting active managed mods."))
            menu.exec(table.viewport().mapToGlobal(point))
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(mod_context_menu)
        tools.addWidget(button("Explain selected source", inspect_selected))
        tools.addWidget(button("Game DNA", lambda: self.navigate("Game DNA")))
        tools.addWidget(button("Open classic Mod Radar tools",
                               self._launch_classic_tools))
        tools.addStretch()
        contents.addWidget(controls)
        page.content.addWidget(p)
        page.content.addWidget(label(
            "All managed mod locations remain protected. Read-only inventory "
            "cannot establish whether a mod is unused.", "warning", wrap=True))

    def old_files_page(self):
        page = self._new("Old Files",
                         "Review older ordinary files in the folder you selected. Never removes a folder automatically.")
        p, contents = panel()
        root = str(self.settings.get("scan_folder", ""))
        heading = label("Reviewed folder: " + root, "subtle", wrap=True)
        contents.addWidget(heading)
        actions = QWidget()
        top = row()
        actions.setLayout(top)
        top.addWidget(button("Change scan folder", self._choose_scan_folder))
        top.addWidget(button("Rescan", self.start_scan))
        top.addStretch()
        contents.addWidget(actions)
        if self._not_scanned(page):
            page.content.addWidget(p)
            return
        table = data_table(["FILE", "SIZE", "MODIFIED", "PROTECTION"])
        table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        table.setRowCount(min(len(self.inventory.files), 500))
        table.setColumnWidth(0, 350)
        table.setColumnWidth(1, 120)
        table.setColumnWidth(2, 140)
        rows = self.inventory.files[:500]
        for i, old in enumerate(rows):
            fields = (str(Path(old.path).name), human_size(old.size),
                      datetime.fromtimestamp(old.modified).strftime("%Y-%m-%d"),
                      "Protected" if is_protected_path(Path(old.path),
                                                      self.settings.get("never_touch", []))
                      else "Reviewable (not proven unused)")
            for j, value in enumerate(fields):
                _table_text(table, i, j, value)
        contents.addWidget(table)
        def remove():
            if self.scanning or self.cleaning:
                self.info("Game Grave is busy", "Finish the current operation first.")
                return
            indexes = _selected_indices(table)
            selected = [rows[i] for i in indexes if i < len(rows)]
            if not selected or len(selected) > 200:
                self.info("Choose files", "Select between 1 and 200 individual files.")
                return
            if any(is_protected_path(Path(f.path),
                                     self.settings.get("never_touch", [])) for f in selected):
                self.error("Protected items selected",
                           "The Old Files view cannot override Never Touch. "
                           "Review a personal rule in Settings first.")
                return
            if not self.confirm("Move selected Old Files to Recycle Bin?",
                f"Reviewing {len(selected)} specific files in:\n{root}\n\n"
                "Every identity, age, folder scope and Windows recovery safety check "
                "runs again. No permanent deletion; no immediate disk space reclaimed.",
                destructive=True):
                return
            self.cleaning = True
            rules = tuple(self.settings.get("never_touch", []))
            reviewed_root = root
            days = int(self.settings.get("files_stale_days", 180))
            session = "crimson-old-" + uuid.uuid4().hex[:10]
            def complete(outcome):
                self.cleaning = False
                self.status.setText(f"{outcome['completed']} old file(s) moved to Recycle Bin. "
                                    "They may still occupy disk space.")
                self._remove_missing_inventory()
                refresh_graveyard(self.inventory, self.settings)
                self.navigate("Old Files")
                self.info("Old Files review completed",
                          f"{outcome['completed']} moved to Recycle Bin, "
                          f"{len(outcome['skipped'])} skipped." +
                          ("\n" + "\n".join(outcome["skipped"][:8])
                           if outcome["skipped"] else ""))
            self.job(lambda _progress: recycle_old_files(
                selected, rules, session, review_root=reviewed_root,
                min_age_days=days), complete, error_title="Old Files cleanup blocked")
        def old_file_context_menu(point):
            row_idx = self._right_clicked_row(table, point)
            if row_idx is None or row_idx >= len(rows):
                return
            item = rows[row_idx]
            action, reason = protection_action(
                item.path, list(self.settings.get("never_touch", [])))
            menu = QMenu(table)
            move = menu.addAction("Move to Recycle Bin…", remove)
            move.setEnabled(not is_protected_path(
                Path(item.path), self.settings.get("never_touch", [])))
            if action == "Protect":
                menu.addAction("Protect this file (Never Touch)",
                               lambda: self._set_personal_protection(
                                   item.path, protect=True, return_route="Old Files"))
            elif action == "Unprotect":
                menu.addAction("Unprotect this file…",
                               lambda: self._set_personal_protection(
                                   item.path, protect=False, return_route="Old Files"))
            else:
                locked = menu.addAction("Protection cannot be changed here")
                locked.setEnabled(False)
            menu.addSeparator()
            menu.addAction("Open containing folder",
                           lambda: self._open_folder(str(Path(item.path).parent)))
            menu.addAction("Explain protection",
                           lambda: self.info("Old Files safety", reason))
            menu.exec(table.viewport().mapToGlobal(point))
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(old_file_context_menu)
        contents.addWidget(button("Move reviewed individual files to Recycle Bin…",
                                  remove, kind="danger"))
        page.content.addWidget(p)
        page.content.addWidget(label(
            "File age does not prove disuse. Old Files never removes installed games or "
            "managed profile folders. Recycle Bin is reversible only while Windows holds a matching item.",
            "warning", wrap=True))

    def screenshots_page(self):
        """Automatic metadata discovery; preview/deletion still individually authorized."""
        page = self._new(
            "Screenshots", "Automatically find in-game captures without browsing your personal photos.")
        if self._not_scanned(page):
            return
        p, col = panel()
        shots = sorted(self.inventory.screenshots,
                       key=lambda x: (-x.modified, x.path.casefold()))
        col.addWidget(section_title("Discovered in-game screenshots",
                                    str(len(shots)) + " detected"))
        col.addWidget(label(
            "Scans check Steam screenshot directories, Windows/Game Bar captures, "
            "supported gaming capture locations, and dedicated screenshot folders "
            "for games detected on this PC. Only filenames, file sizes, and dates "
            "are inspected automatically. Image contents are opened only if you "
            "choose Preview. Personal photo folders are excluded.",
            "subtle", wrap=True))
        bar = QWidget()
        brow = row(spacing=10)
        bar.setLayout(brow)
        brow.addWidget(button("Rescan screenshots", self.start_scan, kind="primary"))
        brow.addWidget(button("Review old screenshots in Graveyard",
                              lambda: self.navigate("Graveyard")))
        brow.addStretch()
        col.addWidget(bar)
        table = data_table(["SCREENSHOT", "SIZE", "MODIFIED", "FOLDER"])
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setMinimumHeight(460)
        table.setColumnWidth(0, 310)
        table.setColumnWidth(1, 105)
        table.setColumnWidth(2, 140)
        rows = shots[:700]
        table.setRowCount(len(rows))
        for i, shot in enumerate(rows):
            for c, value in enumerate((
                    Path(shot.path).name,
                    human_size(shot.size),
                    datetime.fromtimestamp(shot.modified).strftime("%Y-%m-%d %H:%M"),
                    str(Path(shot.path).parent))):
                _table_text(table, i, c, value)
            table.setRowHeight(i, 36)
        col.addWidget(table)
        if not rows:
            col.addWidget(label(
                "No screenshots discovered in supported locations yet. "
                "Try Scan PC, or add a custom screenshot folder in Settings.",
                "subtle", wrap=True))
        def selected_shot():
            indices = _selected_indices(table)
            return rows[indices[0]] if indices and indices[0] < len(rows) else None
        def inspect_shot():
            shot = selected_shot()
            if shot is None:
                self.info("Select a screenshot", "Choose one screenshot row to preview it.")
                return
            self._preview_capture(shot)
        def open_location():
            shot = selected_shot()
            if shot is not None:
                self._open_folder(str(Path(shot.path).parent))
        controls = QWidget()
        ctrls = row()
        controls.setLayout(ctrls)
        ctrls.addWidget(button("Preview selected screenshot…", inspect_shot,
                               kind="primary"))
        ctrls.addWidget(button("Open screenshot folder", open_location))
        ctrls.addStretch()
        col.addWidget(controls)
        def screenshot_context(point):
            idx = self._right_clicked_row(table, point)
            if idx is None or idx >= len(rows):
                return
            record = rows[idx]
            menu = QMenu(table)
            menu.addAction("Preview screenshot / review Recycle Bin move…",
                           lambda: self._preview_capture(record))
            menu.addAction("Open containing folder",
                           lambda: self._open_folder(str(Path(record.path).parent)))
            menu.addSeparator()
            status = menu.addAction(
                "Bulk deletion disabled: individual image review required")
            status.setEnabled(False)
            menu.exec(table.viewport().mapToGlobal(point))
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(screenshot_context)
        table.cellDoubleClicked.connect(
            lambda idx, _col: self._preview_capture(rows[idx])
            if 0 <= idx < len(rows) else None)
        page.content.addWidget(p)
        page.content.addWidget(label(
            "No screenshot is deleted automatically. To remove one, preview the "
            "exact image and separately approve Windows Recycle Bin recovery.",
            "warning", wrap=True))

    def undo_page(self):
        page = self._new("Undo Center",
                         "Check whether Windows still holds recycled files, then approve restoration.")
        entries = list(reversed(get_records()))[:300]
        p, contents = panel()
        contents.addWidget(section_title("Local recovery records",
                                         str(len(entries)) + " recent"))
        table = data_table(["ORIGINAL LOCATION", "SIZE", "RECORDED", "STATE"])
        table.setColumnWidth(0, 360)
        table.setColumnWidth(1, 110)
        table.setColumnWidth(2, 165)
        table.setRowCount(len(entries))
        for i, e in enumerate(entries):
            values = (e.get("path", "Unknown"), readable_bytes(e.get("size")),
                      e.get("time", "Unknown"), e.get("state", "Not checked"))
            for j, val in enumerate(values):
                _table_text(table, i, j, val)
        contents.addWidget(table)
        buttons = QWidget()
        line = row()
        buttons.setLayout(line)
        def selected_record():
            idx = _selected_indices(table)
            return entries[idx[0]] if idx else None
        def check():
            record = selected_record()
            if not record:
                self.info("Choose a record", "Select an Undo Center entry first.")
                return
            self.job(lambda _emitter: check_restore(record["id"]),
                     lambda outcome: (
                         self.info("Windows restore availability",
                                   str(outcome) + "\n\nOnly a real unique Recycle Bin match is restorable."),
                         self.navigate("Undo Center")),
                     error_title="Cannot check recovery")
        def undo():
            if self.cleaning or self.scanning:
                self.info("Busy", "Finish the current operation first.")
                return
            rec = selected_record()
            if not rec:
                self.info("Choose a record", "Select a recovery record.")
                return
            if not self.confirm("Restore from Windows Recycle Bin?",
                "Attempt to restore the exact matching recycled item to:\n" +
                str(rec.get("path", "Unknown")) +
                "\n\nWindows will refuse uncertain or conflicting entries. "
                "Game Grave will not overwrite a current file."):
                return
            self.cleaning = True
            def finished(value):
                self.cleaning = False
                self.info("Restore result", str(value))
                self.navigate("Undo Center")
            self.job(lambda _progress: restore_recycled(rec["id"]), finished,
                     error_title="Restore could not be verified")
        line.addWidget(button("Check restore availability", check))
        line.addWidget(button("Restore selected…", undo, kind="primary"))
        line.addWidget(button("Refresh records", lambda: self.navigate("Undo Center")))
        contents.addWidget(buttons)
        page.content.addWidget(p)
        _box_notice(page, "Undo depends on a unique matching Windows Recycle Bin item. "
                    "Emptying the Recycle Bin or source path conflicts may prevent recovery.",
                    warning=True)

    def _choose_scan_folder(self):
        chosen = QFileDialog.getExistingDirectory(self, "Select ordinary Old Files scan folder",
                                str(self.settings.get("scan_folder", str(Path.home()))))
        if not chosen:
            return
        target = Path(chosen)
        if not safe_scan_root(target) or is_protected_path(target, []):
            self.error("Folder not allowed",
                       "Choose a normal local documents/download folder, not a drive root, "
                       "game install, mod manager or protected system directory.")
            return
        self.settings["scan_folder"] = str(target)
        try:
            save_settings(self.settings)
        except OSError as exc:
            self.error("Cannot save folder preference", str(exc))
            return
        self.status.setText("Scan folder saved. Scan PC before reviewing files.")
        self.navigate("Settings")

    def settings_page(self):
        page = self._new("Settings", "Appearance, scan folders, Never Touch rules and local-only privacy controls.")
        p, contents = panel()
        contents.addWidget(section_title("Scan preferences"))
        contents.addWidget(label(
            "Old Files: " + str(self.settings.get("scan_folder", "")),
            "subtle", wrap=True))
        contents.addWidget(button("Choose Old Files folder…", self._choose_scan_folder))
        contents.addWidget(label(
            "Automatic cleanup remains OFF. Every actual Recycle Bin move "
            "requires separate approval.", "warning", wrap=True))
        page.content.addWidget(p)

        p, stack = panel()
        stack.addWidget(section_title("Never Touch", "User-controlled rules"))
        stack.addWidget(label(
            "Exact personal rules can be unprotected directly in Graveyard. "
            "Removing a PARENT folder rule affects all its children, so it is only "
            "allowed here with a separate warning. Built-in safety cannot be disabled.",
            "subtle", wrap=True))
        self.never_list = QListWidget()
        self.never_list.setMinimumHeight(135)
        rules = list(self.settings.get("never_touch", []))
        self.never_list.addItems([str(x) for x in rules])
        focus_rule = getattr(self, "_focus_never_touch_rule", None)
        if focus_rule and focus_rule in rules:
            self.never_list.setCurrentRow(rules.index(focus_rule))
        stack.addWidget(self.never_list)
        buttons = QWidget()
        br = row()
        buttons.setLayout(br)
        def add_rule():
            chosen = QFileDialog.getExistingDirectory(self, "Protect an ordinary personal folder")
            if not chosen:
                return
            try:
                self.settings = add_never_touch_path(self.settings, chosen)
                refresh_graveyard(self.inventory, self.settings)
                self.navigate("Settings")
            except (OSError, ValueError) as exc:
                self.error("Cannot add rule", str(exc))
        def remove_rule():
            item = self.never_list.currentItem()
            if not item:
                self.info("Choose a rule", "Select your personal Never Touch rule to remove.")
                return
            rule = item.text()
            if not self.confirm("Remove protected folder rule?",
                    "This removes a personal Never Touch rule for:\n" + rule +
                    "\n\nEvery child file beneath this folder may become reviewable "
                    "if it otherwise meets safety rules. NOTHING is deleted now. "
                    "Built-in protection remains active.", destructive=True):
                return
            try:
                updated = list(self.settings.get("never_touch", []))
                updated.remove(rule)
                new_settings = dict(self.settings)
                new_settings["never_touch"] = updated
                save_settings(new_settings)
                self.settings = new_settings
                refresh_graveyard(self.inventory, self.settings)
                self.navigate("Settings")
            except (OSError, ValueError) as exc:
                self.error("Could not remove rule", str(exc))
        br.addWidget(button("Protect a folder", add_rule))
        br.addWidget(button("Remove selected personal rule…", remove_rule, kind="danger"))
        stack.addWidget(buttons)
        page.content.addWidget(p)

        p, stack = panel()
        stack.addWidget(section_title("In-game screenshots", "Optional locations"))
        stack.addWidget(label(
            "Steam screenshot folders and common game capture locations are scanned by metadata. "
            "Your general Pictures directory isn't automatically browsed. "
            "Image contents load only when you request an individual preview.",
            "subtle", wrap=True))
        self.shot_roots = QListWidget()
        self.shot_roots.addItems(list(self.settings.get("screenshot_roots", [])))
        self.shot_roots.setMinimumHeight(80)
        stack.addWidget(self.shot_roots)
        buttons = QWidget()
        br = row()
        buttons.setLayout(br)
        def modify_shots(remove=False):
            if remove:
                current = self.shot_roots.currentItem()
                if current is None:
                    return
                roots = list(self.settings.get("screenshot_roots", []))
                if current.text() in roots:
                    roots.remove(current.text())
            else:
                folder = QFileDialog.getExistingDirectory(self, "Select personal game capture folder")
                if not folder:
                    return
                if not safe_scan_root(Path(folder)) or is_protected_path(Path(folder), []):
                    self.error("Not allowed", "Choose an ordinary screenshot folder.")
                    return
                roots = list(self.settings.get("screenshot_roots", []))
                if folder in roots:
                    return
                if len(roots) >= 30:
                    self.error("Too many folders", "Maximum 30 custom screenshot folders.")
                    return
                roots.append(folder)
            new = dict(self.settings)
            new["screenshot_roots"] = roots
            try:
                save_settings(new)
                self.settings = new
                self.navigate("Settings")
            except OSError as exc:
                self.error("Could not save screenshot folder", str(exc))
        br.addWidget(button("Add game capture folder", lambda: modify_shots()))
        br.addWidget(button("Remove selected", lambda: modify_shots(True)))
        stack.addWidget(buttons)
        page.content.addWidget(p)

        p, ai_stack = panel()
        ai_stack.addWidget(section_title("AI Assistant", "Optional • fully automatic setup"))
        ai_stack.addWidget(label(
            "When you enable AI, Game Grave downloads and installs the local AI engine "
            "and model for you. No extra program, terminal, or account required. "
            "AI remains off by default, runs on this PC, and cannot delete files.",
            "subtle", wrap=True))
        from ai_bundle import INSTALL_MESSAGE, is_ai_installed
        from PySide6.QtWidgets import QProgressBar
        ai_status = label("AI installed." if is_ai_installed() else
                          "Not installed. Around 1.2 GB on first enable.", "subtle", wrap=True)
        ai_bar = QProgressBar()
        ai_bar.setRange(0, 100)
        ai_bar.setValue(0)
        ai_bar.hide()
        ai_toggle = QCheckBox("Enable AI Assistant")
        ai_toggle.setChecked(self.settings.get("ai_assistant_enabled") is True)
        def open_ai_chat():
            from gg_desktop.ai_dialog import open_local_ai_dialog
            open_local_ai_dialog(self)
        ai_open = button("Open AI Assistant", open_ai_chat)
        ai_open.setEnabled(ai_toggle.isChecked() and is_ai_installed())
        ai_stack.addWidget(ai_toggle)
        ai_stack.addWidget(ai_status)
        ai_stack.addWidget(ai_bar)
        ai_stack.addWidget(ai_open)
        ai_stack.addWidget(label(
            "The optional model is downloaded only with your permission, checked "
            "for integrity, and stored under your local Game Grave data folder. "
            "Normal cleanup and scans never depend on AI.",
            "subtle", wrap=True))
        def restore_toggle(value):
            ai_toggle.blockSignals(True)
            ai_toggle.setChecked(value)
            ai_toggle.blockSignals(False)
        def save_enabled(value):
            changed = dict(self.settings)
            changed["ai_assistant_enabled"] = bool(value)
            save_settings(changed)
            self.settings = changed
        def still_visible():
            # Navigating away destroys the Qt Settings page during long model downloads.
            # Keep the approved background operation valid even when its widgets vanish.
            try:
                from shiboken6 import isValid
                return all(isValid(w) for w in (ai_toggle, ai_status, ai_bar, ai_open))
            except (RuntimeError, ImportError):
                return False
        def setup_finished(result):
            ok, detail = result
            if ok:
                try:
                    save_enabled(True)
                except (OSError, ValueError) as exc:
                    ok, detail = False, str(exc)
            if still_visible():
                ai_bar.hide()
                ai_toggle.setEnabled(True)
                restore_toggle(bool(ok))
                ai_open.setEnabled(bool(ok))
                ai_status.setText(
                    "AI installed and ready. Open the assistant to begin." if ok else
                    "AI not installed. Normal Game Grave features are unchanged.")
            if not ok:
                self.error("AI setup could not finish", detail)
            elif not still_visible():
                self.status.setText("AI installed and ready. Open Settings to use it.")
        def set_ai_enabled(checked):
            if not checked:
                try:
                    save_enabled(False)
                except (OSError, ValueError) as exc:
                    restore_toggle(True)
                    self.error("Could not disable AI", str(exc))
                    return
                from ai_bundle import stop_ai
                stop_ai()
                ai_open.setEnabled(False)
                ai_status.setText("AI disabled. You can enable it any time.")
                return
            if is_ai_installed():
                try:
                    save_enabled(True)
                except (OSError, ValueError) as exc:
                    restore_toggle(False)
                    self.error("Could not enable AI", str(exc))
                    return
                ai_open.setEnabled(True)
                ai_status.setText("AI ready. All processing stays on this PC.")
                return
            if not self.confirm("Install AI Assistant?", INSTALL_MESSAGE):
                restore_toggle(False)
                return
            restore_toggle(False)
            ai_toggle.setEnabled(False)
            ai_open.setEnabled(False)
            ai_bar.setValue(0)
            ai_bar.show()
            ai_status.setText("Installing AI automatically. Do not close Game Grave.")
            def work(emit):
                from ai_bundle import AiSetupError, install_ai
                try:
                    install_ai(lambda stage, fraction:
                               emit(int(fraction * 100), stage))
                    return True, ""
                except (AiSetupError, OSError, ValueError) as exc:
                    return False, str(exc)
                except Exception:
                    return False, "Unexpected installation error. Existing files remain unchanged."
            def show_progress(percent, stage):
                if still_visible():
                    ai_bar.setValue(percent)
                    ai_status.setText(stage + " • " + str(percent) + "%")
            self.job(work, setup_finished, progress=show_progress,
                     error_title="AI setup failed")
        ai_toggle.toggled.connect(set_ai_enabled)
        if self.settings.get("ai_assistant_enabled") and not is_ai_installed():
            ai_status.setText("AI not installed. Disable and re-enable to set up automatically.")
        page.content.addWidget(p)

        p, stack = panel()
        stack.addWidget(section_title("Appearance and privacy"))
        stack.addWidget(label(
            "Crimson Command is a local UI preview. No account, telemetry, "
            "external images or automatic server polling. Older appearance themes "
            "remain available in the original Game Grave interface.",
            "subtle", wrap=True))
        stack.addWidget(button("Open classic appearance and advanced settings",
                               self._launch_classic_tools))
        page.content.addWidget(p)

    def tools_page(self):
        page = self._new("More Tools", "All existing advanced Game Grave capabilities remain available.")
        p, stack = panel()
        stack.addWidget(label("YOUR SAVES AND RESURRECTION KITS REMAIN PROTECTED", "eyebrow"))
        stack.addWidget(label(
            "The classic Game Grave interface still contains Save Vault, "
            "Resurrection Kits, Living Kits, Time Machine, PC transfer, "
            "Make Room, Activity, schedules and advanced options. "
            "This visual preview does not replace the trusted workflow yet.",
            "subtle", wrap=True))
        actions = QWidget()
        buttons = QGridLayout(actions)
        buttons.setContentsMargins(0, 5, 0, 4)
        buttons.setSpacing(9)
        links = [
            ("Save Vault: back up a selected folder", self._create_save_backup),
            ("Create verified Resurrection Kit", self._create_kit),
            ("Inspect and restore Kit to NEW folder", self._restore_kit),
            ("Rehearse Kit recovery in isolation", self._rehearse_kit),
            ("Check Kit missing pieces", self._missing_pieces),
            ("Compare two Kit snapshots", self._compare_kits),
            ("Prepare portable PC-to-PC transfer", self._transfer_kit),
            ("Browse Time Machine snapshots", self._kit_versions),
        ]
        for i, (caption, callback) in enumerate(links):
            buttons.addWidget(button(caption, callback,
                                     kind="primary" if i == 1 else ""),
                              i // 2, i % 2)
        stack.addWidget(actions)
        stack.addWidget(button("Open classic Mod Organizer, advanced backup and update tools",
                               self._launch_classic_tools))
        page.content.addWidget(p)
        p, stack = panel()
        stack.addWidget(section_title("What is safe to do here?"))
        for detail in (
            "Read-only scans and evidence-backed game/mod discovery",
            "Inspect and unprotect only your exact personal Never Touch items",
            "Review individual screenshots locally before a separate approval",
            "Move ordinary reviewed files to Windows Recycle Bin after verified safety check",
            "View and request restoration from a unique Windows recovery entry",
        ):
            stack.addWidget(label("✓  " + detail, "subtle", wrap=True))
        page.content.addWidget(p)
        _box_notice(page, "This Qt presentation is a preview, not Game Grave 1.0. "
                    "Native Windows acceptance, full advanced UI parity and "
                    "third-party Qt commercial redistribution review are pending.",
                    warning=True)

    def _launch_classic_tools(self):
        entry = Path(__file__).resolve().parent.parent / "launcher.py"
        if not entry.is_file():
            self.error("Classic tools unavailable in this preview",
                       "Source-based classic tools cannot be opened from this isolated package. "
                       "Use the existing separate Game Grave installation for advanced features.")
            return
        try:
            subprocess.Popen([sys.executable, str(entry)],
                             cwd=str(entry.parent), close_fds=True)
            self.status.setText("Opened the existing classic Game Grave tools.")
        except OSError as exc:
            self.error("Unable to start classic tools", str(exc))

    def _kit_manifest_picker(self, title="Choose a verified Resurrection Kit manifest"):
        chosen, _ = QFileDialog.getOpenFileName(
            self, title, "", "Game Grave Kits (*.ggkit.json);;JSON (*.json)")
        return Path(chosen) if chosen else None

    def _start_safe_backup_task(self, name, fn, *, target: str):
        if self.cleaning or self.scanning:
            self.info("Operation busy", "Finish the current scan or backup first.")
            return
        self.cleaning = True
        self.status.setText(name + "… Existing game, mod and save files stay untouched.")
        def finish(report):
            self.cleaning = False
            self.status.setText(name + " complete. Original files untouched.")
            # Reports contain on-device user file names; never upload any result.
            lines = [f"{key}: {val}" for key, val in report.items()
                     if isinstance(val, (int, float, bool, str))]
            self.info(name + " completed",
                      "\n".join(lines[:14])[:1800] +
                      "\n\nYour existing game/mod/save files were not modified.")
        self.job(lambda _progress: fn(), finish, error_title=name + " failed")

    def _create_save_backup(self):
        from save_vault import create_backup
        if self.scanning or self.cleaning:
            self.info("Game Grave is busy", "Finish the current operation first.")
            return
        source = QFileDialog.getExistingDirectory(self,
            "Choose exact save / game profile folder to preserve")
        if not source:
            return
        output, _ = QFileDialog.getSaveFileName(
            self, "Create a NEW verified Save Vault ZIP",
            str(Path(source).parent / (Path(source).name + "_SaveVault.zip")),
            "ZIP archives (*.zip)")
        if not output:
            return
        if not output.casefold().endswith(".zip"):
            output += ".zip"
        if not self.confirm("Back up this selected save or profile folder?",
            "Source: " + source + "\n\nNew ZIP: " + output +
            "\n\nOnly this one folder is copied. The destination must not exist. "
            "Game Grave will never delete or overwrite source files. "
            "Close the game first for a consistent snapshot."):
            return
        self._start_safe_backup_task(
            "Save Vault backup", lambda: create_backup(Path(source), Path(output)),
            target=output)

    def _create_kit(self):
        from resurrection_v2 import create_complete_kit
        if self.scanning or self.cleaning:
            self.info("Game Grave is busy", "Finish the current operation first.")
            return
        game, okay = QInputDialog.getText(
            self, "Preserve a gaming setup", "Game title (for the kit manifest):")
        if not okay or not game.strip():
            return
        save = QFileDialog.getExistingDirectory(
            self, "Choose exact Saves or Profile folder for the kit")
        if not save:
            return
        sources = {"Saves": Path(save)}
        if self.confirm("Include your mod setup?",
                        "Do you want to preserve one additional Mods folder? "
                        "The kit will only contain folders you explicitly choose."):
            mod = QFileDialog.getExistingDirectory(
                self, "Choose your exact mod or mod-manager profile folder")
            if not mod:
                return
            sources["Mods"] = Path(mod)
        output, _ = QFileDialog.getSaveFileName(
            self, "Save a NEW Resurrection Kit ZIP",
            str(Path(save).parent / (game.strip().replace("/", "_") + "_Resurrection.zip")),
            "ZIP archives (*.zip)")
        if not output:
            return
        if not output.casefold().endswith(".zip"):
            output += ".zip"
        folders = "\n".join(f"• {role}: {path}" for role, path in sources.items())
        if not self.confirm("Create verified Resurrection Kit?",
            f"Game: {game.strip()}\n\n" + folders + "\n\nZIP: " + output +
            "\n\nThis archives ONLY the selected folders. It does not include "
            "game installation binaries or automatically activate mods. "
            "Existing files are untouched. Continue?"):
            return
        self._start_safe_backup_task(
            "Verified Resurrection Kit",
            lambda: create_complete_kit(game.strip(), sources, Path(output)),
            target=output)

    def _restore_kit(self):
        from resurrection_v2 import inspect_restore, restore_kit
        if self.scanning or self.cleaning:
            self.info("Game Grave is busy", "Finish the current operation first.")
            return
        manifest = self._kit_manifest_picker("Inspect a Resurrection Kit before safe restore")
        if manifest is None:
            return
        destination = QFileDialog.getExistingDirectory(
            self, "Choose parent folder for a NEW restored setup (existing files are never overwritten)")
        if not destination:
            return
        self.status.setText("Verifying kit archive digest and safe NEW restore destination…")
        def ready(plan):
            target = str(plan.get("target", "new unique restore folder"))
            message = ("This will restore the verified kit into a BRAND-NEW folder:\n" +
                       target + "\n\nExisting game, save and mod files are not overwritten. "
                       "No mod manager is automatically reconfigured or activated. "
                       "The restore is separate from game installation. Continue?")
            if not self.confirm("Approve restoring this checked kit?", message):
                self.status.setText("Restore canceled. No files changed.")
                return
            self._start_safe_backup_task("Staged Resurrection recovery",
                lambda: restore_kit(manifest, Path(destination), approved=True),
                target=target)
        self.job(lambda _progress: inspect_restore(manifest, Path(destination)),
                 ready, error_title="Kit cannot be safely restored")

    def _rehearse_kit(self):
        from resurrection_lab import rehearse_kit
        if self.scanning or self.cleaning:
            self.info("Game Grave is busy", "Finish the current operation first.")
            return
        manifest = self._kit_manifest_picker("Choose kit to rehearse safely")
        if manifest is None:
            return
        dest = QFileDialog.getExistingDirectory(
            self, "Choose ordinary folder for isolated temporary rehearsal")
        if not dest:
            return
        if not self.confirm("Rehearse without touching active game files?",
            "Kit: " + str(manifest) + "\n\nTemporary rehearsal location: " + dest +
            "\n\nGame Grave creates and deletes ONLY its own disposable rehearsal "
            "files, then compares extracted byte hashes. "
            "No live saves, profiles or game installs are changed."):
            return
        self._start_safe_backup_task("Isolated Resurrection rehearsal",
            lambda: rehearse_kit(manifest, Path(dest), record=False), target=dest)

    def _missing_pieces(self):
        from resurrection_lab import missing_pieces
        manifest = self._kit_manifest_picker("Check the kit's missing dependencies")
        if manifest is None:
            return
        self.status.setText("Inspecting verified kit manifest and dependencies…")
        def present(report):
            import json
            # Display-only. Avoid hidden side effects and keep output bounded.
            self.info("Missing Pieces (diagnostic, not proof of completeness)",
                json.dumps(report, indent=2, ensure_ascii=False)[:2200] +
                "\n\nEven a verified ZIP may not represent a complete working game setup.")
        self.job(lambda _progress: missing_pieces(manifest), present,
                 error_title="Kit dependency check failed")

    def _compare_kits(self):
        from resurrection_lab import compare_kits
        older = self._kit_manifest_picker("Choose the older kit manifest")
        if older is None:
            return
        newer = self._kit_manifest_picker("Choose the newer kit manifest")
        if newer is None:
            return
        self.status.setText("Comparing kit manifests and verified archive content…")
        def present(report):
            import json
            self.info("Time Machine: verified kit comparison",
                      json.dumps(report, indent=2, ensure_ascii=False)[:2800] +
                      "\n\nNo game files were changed.")
        self.job(lambda _progress: compare_kits(older, newer), present,
                 error_title="Kit comparison failed")

    def _kit_versions(self):
        from resurrection_lab import list_snapshots
        folder = QFileDialog.getExistingDirectory(self, "Choose folder containing your saved kit versions")
        if not folder:
            return
        def present(rows):
            if not rows:
                self.info("Time Machine", "No verified Kit manifests found in this folder.")
            else:
                lines = []
                for rec in rows[:25]:
                    lines.append(str(rec.get("game", "Unknown game")) +
                                 "  •  " + str(rec.get("manifest", "Manifest")) +
                                 "  •  " + str(rec.get("modified", "")))
                self.info("Verified kit snapshots (newest first)",
                          "\n\n".join(lines)[:2600] +
                          "\n\nSelecting a snapshot never performs a live rollback.")
        self.job(lambda _progress: list_snapshots(Path(folder)), present,
                 error_title="Cannot list kit versions")

    def _transfer_kit(self):
        from resurrection_lab import prepare_pc_transfer
        if self.scanning or self.cleaning:
            self.info("Game Grave is busy", "Finish the current operation first.")
            return
        manifest = self._kit_manifest_picker("Choose kit to prepare for another PC")
        if manifest is None:
            return
        dest = QFileDialog.getExistingDirectory(self,
                    "Choose an EMPTY destination parent for a new portable transfer folder")
        if not dest:
            return
        if not self.confirm("Prepare a new portable PC-to-PC kit folder?",
            f"Kit: {manifest}\n\nTransfer parent: {dest}\n\n"
            "A separate new folder with verified ZIP and manifest will be created. "
            "Nothing is copied to a cloud service or sent over a network. "
            "Game binaries and licensed storefront installs are NOT included."):
            return
        self._start_safe_backup_task("Portable Kit transfer",
            lambda: prepare_pc_transfer(manifest, Path(dest), approved=True),
            target=dest)
