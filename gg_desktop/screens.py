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
    QAbstractItemView, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QProgressBar, QPushButton, QSizePolicy, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)
from core import (
    human_size, age_text, is_game_neglected, is_protected_path, is_unchanged,
    safe_scan_root, save_settings,
)
from graveyard import build_graveyard
from graveyard_protection import protection_action
from cleanup_actions import recycle_reviewed_entries, recycle_old_files
from recovery import get_records, restore as restore_recycled, check_restore
from screenshot_preview import decode_screenshot_preview
from gg_desktop.backend import refresh_graveyard, unprotect_exact_personal_item, add_never_touch_path
from gg_desktop.models import (
    readable_bytes, reported_game_bytes, unique_launcher_counts,
    graveyard_protection_decision, graveyard_totals,
)
from gg_desktop.widgets import (
    ActionCard, HeroBanner, MetricCard, ScrollPage, StorageRing,
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
        page.content.addWidget(HeroBanner(
            title="YOUR GAMES.", subtitle="A CLEANER TOMORROW.",
            detail="Find what your games leave behind across launchers. Review everything; keep what matters."))
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
            grid.addWidget(ActionCard(symbol, title, explanation, action),
                           index // (2 if compact else 4), index % (2 if compact else 4))
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
                opening = button(name, lambda _=False, n=name: self.navigate("Games"), kind="link")
                inner.addWidget(opening)
                inner.addStretch()
                amount = (human_size(reported[name]) + " known" if reported[name] else "Size unknown")
                inner.addWidget(label(f"{count}  •  {amount}", "caption"))
                launcher_col.addWidget(line)
        launcher_col.addStretch()
        r.addWidget(launcher, 3)

        recent, recent_col = panel()
        recent_col.addWidget(section_title("Recent Findings", "Last scan"))
        findings = self.inventory.graveyard[:5]
        if not findings:
            recent_col.addWidget(label("No review findings yet. Scan first or adjust the age threshold.", "subtle", wrap=True))
        for item in findings:
            ctl = button(item.name[:39] + "  ›",
                         lambda _=False: self.navigate("Graveyard"), kind="link")
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
        cap_col.addWidget(section_title("Latest Screenshot", "Private and on-device"))
        if self.inventory.screenshots:
            latest = max(self.inventory.screenshots, key=lambda x: x.modified)
            cap_col.addWidget(label("▧", "metricValue"))
            cap_col.addWidget(label(Path(latest.path).name, "sectionTitle", wrap=True))
            cap_col.addWidget(label(human_size(latest.size) +
                                   "  •  Content not opened automatically", "caption", wrap=True))
            cap_col.addWidget(button("Preview this image", lambda _=False, e=latest: self._preview_capture(e)))
        else:
            cap_col.addWidget(label(
                "No old in-game screenshots recorded. Personal photos are never browsed by default.",
                "subtle", wrap=True))
        cap_col.addStretch()
        bottom_row.addWidget(capture, 2)

        queue, queue_col = panel()
        queue_col.addWidget(section_title("Graveyard Review Queue",
                                          f"{len(self.inventory.graveyard)} findings"))
        for item in self.inventory.graveyard[:4]:
            ctl = button(item.name[:43] + "  ›",
                         lambda _=False: self.navigate("Graveyard"), kind="link")
            queue_col.addWidget(ctl)
            queue_col.addWidget(label(item.category + "  •  " +
                                      human_size(item.apparent_bytes) +
                                      " apparent, not reclaimed", "caption", wrap=True))
        if not self.inventory.graveyard:
            queue_col.addWidget(label("Nothing queued. No cleanup is ever automatic.", "subtle", wrap=True))
        queue_col.addStretch()
        queue_col.addWidget(button("Review all findings", lambda: self.navigate("Graveyard"), kind="primary"))
        bottom_row.addWidget(queue, 2)

        attention, alert_col = panel(kind="alertCard")
        alert_col.addWidget(section_title("Needs Review"))
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
        page.content.addWidget(label(
            "IMPORTANT: User-added protection can be removed here. Built-in game/save/mod safeguards "
            "cannot. No permanent-delete fallback. Images require individual preview.", "warning", wrap=True))
        self.grave_search.textChanged.connect(self._fill_graveyard)
        self.grave_type.currentTextChanged.connect(self._fill_graveyard)
        self.grave_state.currentTextChanged.connect(self._fill_graveyard)
        self.grave_table.itemSelectionChanged.connect(self._grave_details)
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
            self.grave_table.setRowHeight(i, 37)
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
        self.grave_detail.addWidget(label("WHY THIS IS PROTECTED", "eyebrow"))
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

    def _select_eligible(self):
        self.grave_table.clearSelection()
        for i, entry in enumerate(self._shown_graves):
            if entry.can_recycle and entry.old_file is not None and (
                    entry.category != "Old game screenshot") and (
                    not is_protected_path(Path(entry.path),
                                          self.settings.get("never_touch", []))):
                self.grave_table.selectRow(i)

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
        self.job(lambda _emitter: recycle_reviewed_entries(reviewed, rules, session),
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
        else:
            self.info("Screenshot not eligible",
                      "This image is not in the reviewed old-screenshot inventory. "
                      "Nothing was loaded or deleted.")

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
