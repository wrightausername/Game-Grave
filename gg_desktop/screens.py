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
    QMenu, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSizePolicy, QTabWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QStackedWidget,
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
from gg_desktop.visuals import SceneHeader, FeatureStrip, RelationshipMap, RecoveryRoute
from gg_desktop.tab_panels import (
    game_gallery, mod_radar_panel, old_files_categories, graveyard_overview,
    graveyard_mix_panel, old_file_age_chart, clear_empty_panel,
)
from gg_desktop.premium_panels import GameInspector, ModInspector, mod_gallery
from gg_desktop.reference_hero import ReferenceHero


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
        themes = {
            "Games": ("games", "YOUR GAME LIBRARY"),
            "Mods": ("mods", "MOD RADAR"),
            "Old Files": ("oldfiles", "ARCHIVE CLEANUP"),
            "Graveyard": ("graveyard", "REVIEW • PROTECT • RECOVER"),
            "Game DNA": ("dna", "DIGITAL FORENSICS"),
            "Undo Center": ("undo", "RESTORE • VERIFY • RECOVER"),
            "Settings": ("settings", "CUSTOMIZE GAME GRAVE"),
            "Captures": ("captures", "YOUR GAMING CAPTURES"),
        }
        if title == "Games":
            actual_size, unknown = reported_game_bytes(self.inventory.games)
            metrics = (
                ("Installed games", len(self.inventory.games), "Verified records"),
                ("Known game size", human_size(actual_size), "Reported by launchers"),
                ("Launchers", len({g.launcher for g in self.inventory.games}),
                 "Detected sources"),
                ("Unknown sizes", unknown, "Not assumed empty"),
            )
            page.content.addWidget(ReferenceHero(
                "games", "Games", subtitle, metrics))
        elif title == "Mods":
            from gg_desktop.premium_panels import group_mod_locations
            groups, _unmatched = group_mod_locations(
                self.inventory.games, self.inventory.mods)
            metrics = (
                ("Mod locations", len(self.inventory.mods), "Discovered locations"),
                ("Linked games", len(groups), "Verified path matches"),
                ("Sources", len({str(getattr(m, "source", "Unknown"))
                                 for m in self.inventory.mods}), "Reported sources"),
                ("Protection", "ON", "No automatic deletion"),
            )
            page.content.addWidget(ReferenceHero(
                "mods", "Mods", subtitle, metrics))
        elif title in themes:
            scene, kicker = themes[title]
            page.content.addWidget(ReferenceHero(scene, title, subtitle))
        else:
            page_heading(page, title, subtitle)
        if self.inventory.warnings and title != "Settings":
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
        """Render the reference-matched dashboard without fictional metrics."""
        from gg_desktop.dashboard import render_dashboard
        render_dashboard(self)

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

        # The artwork-led library and the selection inspector share one
        # workspace. All detail actions still call the existing safe APIs.
        game_workspace = QWidget()
        game_workspace_row = row(spacing=14)
        game_workspace.setLayout(game_workspace_row)
        game_left = QWidget()
        game_left_col = column(spacing=12)
        game_left.setLayout(game_left_col)
        self.game_left_col = game_left_col
        game_workspace_row.addWidget(game_left, 1)
        self.game_inspector = GameInspector(
            self._inspect_game_record,
            lambda g: self._open_folder(g.install_path),
            lambda: self.navigate("Mods"),
            lambda: self.navigate("Captures"))
        game_workspace_row.addWidget(self.game_inspector, 0, Qt.AlignTop)
        # Start empty and populate once from the same filtered/sorted rows as
        # the table. No mismatch between search results and visible covers.
        self.game_gallery_frame = game_gallery(
            [], lambda game: self._focus_game_from_gallery(game), limit=9)
        self._gallery_keys = None
        game_left_col.addWidget(self.game_gallery_frame)
        page.content.addWidget(game_workspace)
        p, pcol = panel()
        self.game_table = data_table(["GAME", "LAUNCHER", "SIZE", "LAST PLAYED", "EVIDENCE"])
        self.game_table.setColumnWidth(0, 245)
        self.game_table.setColumnWidth(1, 150)
        self.game_table.setColumnWidth(2, 106)
        self.game_table.setColumnWidth(3, 145)
        self.game_table.setMinimumHeight(370)
        pcol.addWidget(self.game_table)
        # Advanced inventory stays available on demand, instead of displacing
        # the visual game library at the top of the screen.
        self.game_detail_toggle = button(
            "▤  Show advanced inventory list",
            lambda: self._toggle_games_inventory())
        self.game_detail_toggle.setObjectName("referenceSecondary")
        game_left_col.addWidget(self.game_detail_toggle)
        self.game_inventory_panel = p
        p.setVisible(False)
        game_left_col.addWidget(p)
        self.game_details = panel()[0]
        self.game_details_col = self.game_details.layout()
        self.game_details.setVisible(False)
        game_left_col.addWidget(self.game_details)
        # Keep the visual gallery flush with its heading even when the
        # selected-game inspector is taller than the current game row count.
        game_left_col.addStretch(1)
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

    def _refresh_games_gallery(self, rows):
        keys = tuple(g.key for g in rows[:9])
        if keys == getattr(self, "_gallery_keys", None):
            return
        old = self.game_gallery_frame
        index = self.game_left_col.indexOf(old)
        self.game_left_col.removeWidget(old)
        old.hide()
        old.setParent(None)
        old.deleteLater()
        self.game_gallery_frame = game_gallery(
            rows, lambda game: self._focus_game_from_gallery(game), limit=9,
            empty_message=("No installed games match the selected filters."
                           if self.inventory.games else
                           "No verified games yet. Run Scan PC to check your library."))
        self.game_left_col.insertWidget(max(0, index), self.game_gallery_frame)
        self._gallery_keys = keys

    def _toggle_games_inventory(self):
        shown = not self.game_inventory_panel.isVisible()
        self.game_inventory_panel.setVisible(shown)
        self.game_details.setVisible(shown)
        self.game_detail_toggle.setText(
            "▤  Hide advanced inventory list" if shown
            else "▤  Show advanced inventory list")

    def _focus_game_from_gallery(self, game):
        """Select the exact verified game row, preserving its existing actions."""
        if not hasattr(self, "game_table"):
            return
        self.game_search.setText("")
        self.game_filter.setCurrentIndex(0)
        self.game_sort.setCurrentText("Name A to Z")
        for index, item in enumerate(getattr(self, "_shown_games", [])):
            if item.key == game.key:
                self.game_table.selectRow(index)
                target = self.game_table.item(index, 0)
                if target is not None:
                    self.game_table.scrollToItem(target)
                self._game_details()
                return
        self.info("Game not in this view",
                  "The selected installation is outside the first 500 rows. "
                  "Use its exact name in the Games search filter.")

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
        self._refresh_games_gallery(rows)
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
            if hasattr(self, "game_inspector"):
                self.game_inspector.set_game(None)
            self.game_details_col.addWidget(label("Select a game to see source evidence and safe actions.", "subtle"))
            return
        game = self._shown_games[selected[0]]
        if hasattr(self, "game_inspector"):
            self.game_inspector.set_game(game)
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
        from graveyard_override import manual_game_entry, override_eligibility
        advanced_entry = manual_game_entry(game)
        eligible, reason = override_eligibility(advanced_entry, self.inventory)
        advanced_button = button(
            "Advanced override (Recycle Bin)…",
            lambda _=False, e=advanced_entry: self._override_protected_grave_entry(e),
            kind="danger")
        advanced_button.setEnabled(eligible)
        advanced_button.setToolTip(reason)
        bar.addWidget(advanced_button)
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

    def _send_mod_to_graveyard(self, mod):
        """Make any discovered mod reviewable, even when recently modified."""
        path = str(getattr(mod, "path", "")).strip()
        if (not path or
                not any(str(m.path) == path for m in self.inventory.mods)):
            self.error("Mod entry changed", "Scan again before selecting this location.")
            return
        if not self.confirm(
            "Review this mod folder in the Graveyard?",
            "Add the detected mod location to your manual Graveyard review list?\n\n"
            + path + "\n\n"
            "Nothing will be removed. It will remain protected by default; "
            "an Advanced override requires its own typed confirmation."):
            return
        updated = dict(self.settings)
        queue = [x for x in updated.get("graveyard_watchlist", [])
                 if isinstance(x, str)]
        if not any(os.path.normcase(x) == os.path.normcase(path) for x in queue):
            queue.append(path)
        updated["graveyard_watchlist"] = queue
        try:
            save_settings(updated)
        except (OSError, ValueError) as exc:
            self.error("Cannot save Graveyard review list", str(exc))
            return
        self.settings = updated
        refresh_graveyard(self.inventory, self.settings)
        self._pending_grave_key = "mod:" + str(Path(path)).casefold()
        # Never steal focus or destroy the current page after queuing.
        # Only a deliberate "Open Graveyard" action changes tabs.
        self.status.setText(
            "Added to Graveyard review queue. You can continue working here; "
            "nothing was deleted or moved.")
        if hasattr(self, "mod_inspector"):
            self.mod_inspector.review_btn.setText("Queued for Graveyard review")

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
            notice = menu.addAction(
                "Built-in safety active (one-time override below if eligible)")
            notice.setEnabled(False)
        # Advanced one-time override is separate from the ordinary recycle
        # workflow. It never changes the customer's permanent safety settings.
        if not entry.can_recycle and entry.category != "Old game screenshot":
            from graveyard_override import override_eligibility
            allowed, explanation = override_eligibility(entry, self.inventory)
            override = menu.addAction(
                "Override protection & move to Recycle Bin…",
                lambda: self._override_protected_grave_entry(entry))
            override.setEnabled(allowed)
            override.setToolTip(explanation)
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
            notice = menu.addAction("Launcher uninstall unavailable")
            notice.setEnabled(False)
        from graveyard_override import manual_game_entry, override_eligibility
        review = manual_game_entry(game)
        permitted, reason = override_eligibility(review, self.inventory)
        advanced = menu.addAction(
            "Advanced override: Recycle installed game folder…",
            lambda: self._override_protected_grave_entry(review))
        advanced.setEnabled(permitted)
        advanced.setToolTip(reason)
        menu.exec(self.game_table.viewport().mapToGlobal(point))

    def _go_grave_item(self, key):
        self._pending_grave_key = key
        self.navigate("Graveyard")

    def graveyard_page(self):
        page = self._new("Graveyard",
                         "Review apparent storage, understand protections, and approve individual Recycle Bin moves.")
        if self._not_scanned(page):
            return
        page.content.addWidget(graveyard_overview(self.inventory.graveyard))
        page.content.addWidget(graveyard_mix_panel(self.inventory.graveyard))
        page.content.addWidget(FeatureStrip([
            ("FIND", "Scanned game clutter"),
            ("UNDERSTAND", "Review evidence"),
            ("PROTECT", "Keep what matters"),
            ("RECOVER", "Recycle with Undo checks"),
        ]))

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
            "Installed games, managed mods and saves are protected by default. "
            "Advanced override is available for recognized items after typed confirmation. "
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
                "You may explicitly override Game Grave's default protection "
                "for a verified item, but Windows system locations and unsafe "
                "links cannot be overridden. Using the launcher is safer.")))
        guidance_col.addWidget(button(
            "Test Windows Recycle Bin with a disposable file…",
            self._test_recycle_bin_safely))
        page.content.addWidget(guidance)
        page.content.addWidget(label(
            "IMPORTANT: One-time protected-item override requires typing RECYCLE "
            "and separate confirmation. Never Touch settings remain intact. "
            "Windows/system folders, redirects and unverified recovery stay blocked. "
            "No permanent-delete fallback. Images require individual preview.", "warning", wrap=True))
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
                "Default protection prevents accidental deletion. If you deliberately "
                "want to remove this exact item, use Advanced override below. "
                "Windows and filesystem safety checks still apply.",
                "warning", wrap=True))
        if not e.can_recycle and e.category != "Old game screenshot":
            from graveyard_override import override_eligibility
            override_ok, override_reason = override_eligibility(e, self.inventory)
            advanced = button(
                "Override protection & recycle this item…",
                lambda _=False, entry=e: self._override_protected_grave_entry(entry),
                kind="danger")
            advanced.setEnabled(override_ok)
            advanced.setToolTip(override_reason)
            self.grave_detail.addWidget(advanced)
            if not override_ok:
                self.grave_detail.addWidget(label(override_reason, "subtle", wrap=True))
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

    def _override_protected_grave_entry(self, entry):
        """Typed, one-shot exception for selected game/mod folder or scanned file."""
        from graveyard_override import (
            ACKNOWLEDGEMENT, override_eligibility, recycle_selected_override,
        )
        if self.cleaning or self.scanning:
            self.info("Game Grave is busy", "Finish the current scan or cleanup first.")
            return
        allowed, detail = override_eligibility(entry, self.inventory)
        if not allowed:
            self.error("This override isn't available", detail)
            return
        warning = (
            "YOU ARE OVERRIDING GAME GRAVE'S PROTECTION FOR THIS ITEM.\n\n"
            + entry.name + "\n" + entry.path + "\n\n"
            "This may remove an installed game, active mods, saves, profiles, "
            "or related settings and could break your game or destroy progress.\n\n"
            "The operation is a one-time move to Windows Recycle Bin. "
            "It does NOT permanently disable protection. "
            "There is no permanent-delete fallback. "
            "Windows may refuse the operation or recovery may later be unavailable.\n\n"
            "Consider using your game's launcher or creating a Resurrection Kit first.\n\n"
            "Type " + ACKNOWLEDGEMENT + " below to proceed."
        )
        typed, accepted = QInputDialog.getText(
            self, "Advanced override: protected content", warning)
        if not accepted or typed.strip() != ACKNOWLEDGEMENT:
            return
        if not self.confirm(
            "Final confirmation: Move protected item to Recycle Bin?",
            "You are explicitly authorizing Game Grave to recycle this exact "
            "protected item:\n\n" + entry.path +
            "\n\nThis may remove every file inside the selected game/mod directory. "
            "The app will recheck its identity, filesystem links, and the Windows "
            "Recycle Bin before moving anything. No permanent deletion.",
            destructive=True):
            return
        self.cleaning = True
        snapshot = self.inventory
        rules = tuple(self.settings.get("never_touch", ()))
        session = "override-" + uuid.uuid4().hex[:12]
        self.status.setText("Verifying protected-item override and Windows recovery…")
        def finished(result):
            self.cleaning = False
            self._remove_missing_inventory()
            if result.get("recovery_verified"):
                message = (
                    "Moved your selected protected item to Windows Recycle Bin.\n\n"
                    f"Files and folders examined: {result['entries']}\n"
                    f"Reported contents: {human_size(result['size_bytes'])}\n\n"
                    "The exact Recycle Bin entry was found. It is NOT yet freed disk space."
                )
            else:
                message = (
                    "Windows reports the protected item was moved, but Game Grave "
                    "could not verify its Recycle Bin recovery entry. "
                    "Check the Windows Recycle Bin immediately before emptying it."
                )
            if result.get("recovery_warning"):
                message += "\n\n" + result["recovery_warning"]
            self.info("Advanced override result", message)
            # Rebuild ownership evidence instead of showing a removed game as
            # still installed from an earlier scan.
            self.start_scan()
        self.job(
            lambda _progress: recycle_selected_override(
                entry, snapshot, rules, session, acknowledged=True),
            finished, error_title="Protected-item override blocked")

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
        page = self._new(
            "Game DNA",
            "Digital forensics for your games: explore real installation links, mods, saves and uncertain data.")
        if self._not_scanned(page):
            return
        from game_intelligence import build_game_dna
        from gg_desktop.widgets import destroy_layout
        dna = build_game_dna(
            self.inventory.steam, self.inventory.other,
            self.inventory.mods, self.inventory.saves)
        games = dna.get("games", [])
        page.content.addWidget(FeatureStrip([
            ("ANALYZE", "Verified installations"),
            ("DETECT", "Source-aware mod links"),
            ("MAP", "Interactive relationships"),
            ("EXPLAIN", "Why files are protected"),
            ("REVIEW", "No automatic cleanup"),
        ]))
        selection, selection_col = panel(padding=12)
        selection_col.addWidget(section_title(
            "SELECT AN INSTALLED GAME", f"{len(games)} supported game records"))
        selector_row = QWidget()
        select_line = row(spacing=11)
        selector_row.setLayout(select_line)
        choose = QComboBox()
        choose.setMinimumWidth(280)
        choose.setAccessibleName("Game for digital relationship analysis")
        choose.addItems([
            f"{game['game']}  •  {game['launcher']}" for game in games
        ])
        select_line.addWidget(choose, 3)
        select_line.addWidget(button(
            "See game installations", lambda: self.navigate("Games")))
        select_line.addStretch(1)
        selection_col.addWidget(selector_row)
        page.content.addWidget(selection)

        # This screen is an interactive relationship map, NOT another stats
        # dashboard with invented percentages or fictional game disk sizes.
        workspace = QWidget()
        board_row = row(spacing=12)
        workspace.setLayout(board_row)
        overview, overview_col = panel(padding=10)
        overview_col.addWidget(section_title(
            "GAME DNA  /  RELATIONSHIP MAP", "Tap any file group to inspect"))
        relationship = RelationshipMap()
        overview_col.addWidget(relationship)
        board_row.addWidget(overview, 7)

        inspector, inspector_col = panel(padding=14)
        inspector_col.addWidget(section_title("EVIDENCE INSPECTOR"))
        game_title = label("Select a game", "sectionTitle", wrap=True)
        inspector_col.addWidget(game_title)
        relation_title = label("INSTALLED GAME", "eyebrow", wrap=True)
        inspector_col.addWidget(relation_title)
        meaning = label("", "subtle", wrap=True)
        inspector_col.addWidget(meaning)
        evidence = label("", "caption", wrap=True)
        inspector_col.addWidget(evidence)
        tools = QWidget()
        tline = column(spacing=8)
        tools.setLayout(tline)
        open_install = button(
            "Open verified install folder",
            lambda: self._open_folder(games[choose.currentIndex()]["install_path"])
            if 0 <= choose.currentIndex() < len(games) else None)
        tline.addWidget(open_install)
        tline.addWidget(button("Review associated mods", lambda: self.navigate("Mods")))
        tline.addWidget(button("Open Graveyard safeguards", lambda: self.navigate("Graveyard")))
        inspector_col.addWidget(tools)
        inspector_col.addStretch(1)
        board_row.addWidget(inspector, 3)
        page.content.addWidget(workspace)

        associations, a_col = panel(padding=13)
        a_col.addWidget(section_title("DIRECTLY LINKED FILE LOCATIONS"))
        linked_text = label("", "subtle", wrap=True)
        a_col.addWidget(linked_text)
        page.content.addWidget(associations)

        explanations = {
            "Install": "Existing launcher installation. It is protected by default. "
                       "Files within it are not automatically considered unused.",
            "Mods": "Associated mod storage uses game install path or trusted Steam "
                    "Workshop identifiers. A relationship does not prove the mod is inactive.",
            "Saves": "Save/profile ownership has not been verified. "
                     "Discovered saves stay protected even when their names match a game.",
            "Captures": "Screenshots and recordings are scanned independently. "
                        "They are NOT assumed to belong to this game from filenames alone.",
            "Configs": "Configuration and settings files can be required to run "
                       "the game. Game DNA does not mark them disposable from age alone.",
            "Leftovers": "Leftovers cannot be established by a missing game manifest "
                         "alone. Unmatched files stay protected until reviewed.",
        }

        def inspect_node(name):
            relation_title.setText(name.upper() + "  /  EVIDENCE")
            meaning.setText(explanations.get(name, "No verified relationship."))
            if not games or choose.currentIndex() < 0:
                evidence.setText("No verified game inventory.")
                return
            game = games[choose.currentIndex()]
            if name == "Mods":
                evidence.setText(
                    f"{len(game['assets'])} directly associated mod/storage location(s). "
                    "Nothing here is marked safe to delete.")
            elif name == "Install":
                evidence.setText(
                    "Install: " + str(game["install_path"]) +
                    "\nSource: " + str(game["launcher"]))
            else:
                evidence.setText(
                    "Not automatically attributed to this game. "
                    "Check source evidence before acting.")

        def show(index):
            if not (0 <= index < len(games)):
                game_title.setText("No Game DNA records found")
                relationship.set_game("No game found", {})
                meaning.setText(
                    "Run Scan PC and verify a supported launcher installation.")
                linked_text.setText("No associated locations to display.")
                open_install.setEnabled(False)
                return
            game = games[index]
            game_title.setText(game["game"])
            associated = len(game["assets"])
            relationship.set_game(game["game"], {
                "Install": "Verified record",
                "Mods": f"{associated} linked",
                "Saves": "Unverified",
                "Captures": "Independent",
                "Configs": "Protected",
                "Leftovers": "Unknown",
            })
            linked_text.setText(
                (("\n\n").join(
                    str(asset["source"]) + "  •  " + str(asset["path"]) +
                    "\n" + str(asset.get("evidence", "Source association only"))
                    for asset in game["assets"][:12]) or
                 "No mod or add-on locations could be directly matched to this game.")
                + f"\n\n{len(dna.get('unresolved', []))} unresolved global finding(s) "
                "remain protected, not assumed removable.")
            open_install.setEnabled(True)
            inspect_node("Install")
        relationship.selected.connect(inspect_node)
        choose.currentIndexChanged.connect(show)
        show(choose.currentIndex())
        if not games:
            _box_notice(page,
                        "No verified Game DNA relationships yet. Unknown files stay protected.")

    def mods_page(self):
        page = self._new("Mods", "Trace detected mod managers, addons and game storage without changing a single file.")
        if self._not_scanned(page):
            return
        mod_workspace = QWidget()
        mod_workspace_row = row(spacing=14)
        mod_workspace.setLayout(mod_workspace_row)
        gallery, matched, external = mod_gallery(
            self.inventory.games, self.inventory.mods,
            lambda game, locations, source: self.mod_inspector.set_group(
                game, locations, source), limit=9)
        gallery.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        mod_workspace_row.addWidget(gallery, 1, Qt.AlignTop)
        self.mod_inspector = ModInspector(
            lambda m: self._open_folder(str(getattr(m, "path", ""))),
            self._send_mod_to_graveyard, self.start_scan)
        mod_workspace_row.addWidget(self.mod_inspector, 0, Qt.AlignTop)
        if matched:
            self.mod_inspector.set_group(matched[0][0], matched[0][1])
        elif external:
            self.mod_inspector.set_group(
                None, external, "External / unattributed sources")
        page.content.addWidget(mod_workspace)
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
                notice = menu.addAction("Default game/mod protection active")
                notice.setEnabled(False)
            menu.addSeparator()
            menu.addAction("Send to Graveyard for Advanced review…",
                           lambda: self._send_mod_to_graveyard(item))
            disabled = menu.addAction("Immediate removal disabled (use Graveyard)")
            disabled.setEnabled(False)
            menu.addAction("Why protected?",
                lambda: self.info("Mod Radar protection", why +
                "\n\nMod Radar is for review, not deleting active managed mods."))
            menu.exec(table.viewport().mapToGlobal(point))
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(mod_context_menu)
        def sync_mod_inspector():
            selected = _selected_indices(table)
            if selected and selected[0] < len(self.inventory.mods):
                m = self.inventory.mods[selected[0]]
                self.mod_inspector.set_group(
                    None, [m], str(getattr(m, "source", "Unknown")))
        table.itemSelectionChanged.connect(sync_mod_inspector)
        tools.addWidget(button("Explain selected source", inspect_selected))
        def queue_selected_mod():
            selected = _selected_indices(table)
            if selected and selected[0] < len(self.inventory.mods):
                self._send_mod_to_graveyard(self.inventory.mods[selected[0]])
            else:
                self.info("Select a mod folder", "Choose a mod location to review.")
        tools.addWidget(button("Send to Graveyard…", queue_selected_mod))
        tools.addWidget(button("Game DNA", lambda: self.navigate("Game DNA")))
        tools.addWidget(button("Open classic Mod Radar tools",
                               self._launch_classic_tools))
        tools.addStretch()
        contents.addWidget(controls)
        # Put the engineering inventory below the artwork-led mod workspace.
        # Nothing is guessed or exposed as a one-click cleanup action.
        more_mods = button("▤  Show detailed mod storage findings",
                           lambda: toggle_mod_inventory())
        more_mods.setObjectName("referenceSecondary")
        page.content.addWidget(more_mods)
        p.setVisible(False)
        def toggle_mod_inventory():
            visible = not p.isVisible()
            p.setVisible(visible)
            more_mods.setText(
                "▤  Hide detailed mod storage findings" if visible
                else "▤  Show detailed mod storage findings")
        page.content.addWidget(p)
        page.content.addWidget(mod_radar_panel(self.inventory.mods))
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
        from old_files_scope import is_fixed_drive_root
        top.addWidget(button("Choose folder…", self._choose_scan_folder))
        if is_fixed_drive_root(Path("C:/")):
            top.addWidget(button(
                "Select C: drive…", self._choose_old_files_c_drive))
        old_mode = QComboBox()
        old_mode.addItems(["Quick Scan", "Full Scan"])
        old_mode.setAccessibleName("Old Files scan depth")
        old_mode.setCurrentText(getattr(self, "_old_files_scan_mode", "Quick Scan"))
        top.addWidget(old_mode)
        def run_old_scan():
            self._old_files_scan_mode = old_mode.currentText()
            self.start_scan(old_files_full=(self._old_files_scan_mode == "Full Scan"))
        top.addWidget(button("Scan selected location", run_old_scan, kind="primary"))
        top.addWidget(button("Cancel scan", self.cancel_scan))
        top.addStretch()
        contents.addWidget(actions)
        drive_scope = is_fixed_drive_root(Path(root))
        if drive_scope:
            contents.addWidget(label(
                "Whole-drive mode: only safe non-system folders are inspected, "
                "Quick Scan: 160,000 entries / 15,000 matches / 25 seconds. "
                "Full Scan: no arbitrary entry, match, depth or time limit; "
                "it may take longer. Both skip system, installed games and "
                "protected locations. "
                "No files are deleted by scanning.",
                "warning", wrap=True))
        if self._not_scanned(page):
            page.content.addWidget(p)
            return
        previous_root = str(getattr(self.inventory, "old_files_scan_root", ""))
        if previous_root and previous_root != root:
            note, note_col = panel(padding=18)
            note_col.addWidget(section_title("Ready to scan the selected location"))
            note_col.addWidget(label(
                "Your scan location changed from " + (previous_root or "the previous default") +
                " to " + root +
                ". Click Scan selected location to view actual results. "
                "Previous results are not displayed as if they came from this location.",
                "subtle", wrap=True))
            note_col.addWidget(button("Scan this location", run_old_scan,
                                      kind="primary"))
            page.content.addWidget(p)
            page.content.addWidget(note)
            return
        state = str(getattr(self.inventory, "old_files_scan_status", "complete"))
        status_message = str(getattr(self.inventory, "old_files_scan_message", ""))
        if state != "complete" or not self.inventory.files:
            empty, stack = panel(padding=18)
            if state == "complete":
                stack.addWidget(label("✓  NO OLD FILES FOUND", "sectionTitle"))
                stack.addWidget(label(
                    f"No files older than {self.settings.get('files_stale_days', 180)} "
                    f"days were detected in {root}. "
                    "Nothing to review or move to the Recycle Bin.",
                    "subtle", wrap=True))
            elif state == "partial":
                stack.addWidget(label("SCAN INCOMPLETE", "sectionTitle"))
                stack.addWidget(label(
                    "Game Grave couldn't inspect every eligible location. "
                    "The findings below are partial, and zero matches do not "
                    "mean the drive is completely clear. " + status_message,
                    "warning", wrap=True))
            else:
                stack.addWidget(label("OLD FILES SCAN COULD NOT FINISH",
                                      "sectionTitle"))
                stack.addWidget(label(
                    "The selected location was not fully scanned. "
                    "No clean-results claim is being made. " + status_message,
                    "warning", wrap=True))
            stack.addWidget(button("Rescan Old Files", run_old_scan,
                                   kind="primary"))
            page.content.addWidget(p)
            page.content.addWidget(empty)
            if not self.inventory.files:
                return
        page.content.addWidget(old_files_categories(self.inventory.files))
        page.content.addWidget(old_file_age_chart(self.inventory.files))
        sorter = QWidget()
        sort_row = row(spacing=9)
        sorter.setLayout(sort_row)
        sort_row.addWidget(label("Sort by", "subtle"))
        sort_choice = QComboBox()
        sort_choice.setAccessibleName("Sort Old Files by size, name or modified date")
        sort_choice.addItems([
            "Largest first", "Smallest first", "Name A to Z", "Name Z to A",
            "Newest modified", "Oldest modified"])
        sort_choice.setCurrentText(getattr(self, "_old_files_sort", "Largest first"))
        sort_row.addWidget(sort_choice)
        sort_row.addWidget(label(
            f"{len(self.inventory.files):,} found; showing up to 500 rows. "
            "Results are never deleted automatically.", "caption"))
        sort_row.addStretch()
        contents.addWidget(sorter)
        table = data_table(["FILE", "SIZE", "MODIFIED", "PROTECTION"])
        table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        table.setColumnWidth(0, 350)
        table.setColumnWidth(1, 120)
        table.setColumnWidth(2, 140)
        rows = []
        def refill(*_):
            self._old_files_sort = sort_choice.currentText()
            options = {
                "Largest first": lambda f: (-f.size, f.path.casefold()),
                "Smallest first": lambda f: (f.size, f.path.casefold()),
                "Name A to Z": lambda f: (Path(f.path).name.casefold(), f.path.casefold()),
                "Name Z to A": lambda f: (Path(f.path).name.casefold(), f.path.casefold()),
                "Newest modified": lambda f: (-f.modified, f.path.casefold()),
                "Oldest modified": lambda f: (f.modified, f.path.casefold()),
            }
            ordered = sorted(self.inventory.files,
                             key=options.get(self._old_files_sort,
                                             options["Largest first"]),
                             reverse=self._old_files_sort == "Name Z to A")
            rows[:] = ordered[:500]
            table.setRowCount(len(rows))
            for i, old in enumerate(rows):
                fields = (str(Path(old.path).name), human_size(old.size),
                          datetime.fromtimestamp(old.modified).strftime("%Y-%m-%d %H:%M"),
                          "Protected" if is_protected_path(Path(old.path),
                                                          self.settings.get("never_touch", []))
                          else "Reviewable (not proven unused)")
                for j, value in enumerate(fields):
                    _table_text(table, i, j, value)
                table.setRowHeight(i, 36)
        sort_choice.currentTextChanged.connect(refill)
        refill()
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
            managed_paths = tuple(
                str(game.install_path) for game in self.inventory.games
                if getattr(game, "install_path", None))
            managed_paths += tuple(
                str(mod.path) for mod in self.inventory.mods
                if getattr(mod, "path", None))
            self.job(lambda _progress: recycle_old_files(
                selected, rules, session, review_root=reviewed_root,
                min_age_days=days, managed_roots=managed_paths),
                complete, error_title="Old Files cleanup blocked")
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

    def other_storage_page(self):
        """Explain 'Other used' with an explicitly approved, read-only scan."""
        from collections import defaultdict
        from shiboken6 import isValid
        from gg_desktop.dashboard import _drive_choices, _game_on_drive

        page = self._new(
            "Other Storage",
            "See which folders contribute to storage outside the games Game Grave has identified.")
        intro, intro_col = panel(padding=14)
        intro_col.addWidget(section_title("What is 'Other' storage?"))
        intro_col.addWidget(label(
            "'Other' in Storage Overview is your drive's used space minus known "
            "launcher-reported game sizes. It can contain Windows, applications, "
            "documents, media, caches, and games with unknown sizes. It is NOT "
            "necessarily junk, and this difference is not a verified folder breakdown.",
            "subtle", wrap=True))
        intro_col.addWidget(label(
            "Choose Analyze to examine local file and folder metadata, without "
            "opening file contents, uploading anything, or deleting anything. "
            "Results are estimated file sizes, not an exact accounting of physical disk usage.",
            "warning", wrap=True))
        page.content.addWidget(intro)

        selection, sc = panel(padding=14)
        sc.addWidget(section_title("Analyze another part of your drive"))
        selectors = QWidget()
        rowline = row(spacing=9)
        selectors.setLayout(rowline)
        disk_choices = QComboBox()
        for drv in _drive_choices():
            disk_choices.addItem("Local drive (" + drv.rstrip("\\") + ")", drv)
        chosen = str(getattr(self, "_other_selected_drive", "") or "")
        ix = disk_choices.findData(chosen)
        if ix >= 0:
            disk_choices.setCurrentIndex(ix)
        disk_choices.setAccessibleName("Choose a local fixed disk to examine")
        rowline.addWidget(disk_choices)
        scan_mode = QComboBox()
        scan_mode.addItems(["Quick Scan", "Full Scan"])
        scan_mode.setAccessibleName("Other Storage scan depth")
        scan_mode.setToolTip("Quick: 220,000 entries / 25 seconds. Full: no entry/time cap.")
        rowline.addWidget(scan_mode)
        run_scan = button("Analyze Other storage…", kind="primary")
        rowline.addWidget(run_scan)
        stop_scan = button("Cancel scan")
        stop_scan.setEnabled(False)
        rowline.addWidget(stop_scan)
        rowline.addStretch()
        sc.addWidget(selectors)
        sc.addWidget(label(
            "Quick Scan: up to 220,000 entries or 25 seconds. "
            "Full Scan: no artificial entry/time limit, until completed or canceled. "
            "Both pause during gameplay, skip inaccessible and linked locations, "
            "and never modify files.", "subtle", wrap=True))

        overview = label("", "subtle", wrap=True)
        sc.addWidget(overview)
        progress = QProgressBar()
        progress.setRange(0, 100)
        progress.setValue(0)
        progress.hide()
        sc.addWidget(progress)
        scan_state = label("Not analyzed yet. Nothing is scanned automatically.", "caption", wrap=True)
        sc.addWidget(scan_state)
        page.content.addWidget(selection)

        summary, summary_col = panel(padding=14)
        summary_col.addWidget(section_title("Folder and category breakdown"))
        summary_col.addWidget(label(
            "These are possible contributors to the 'Other' estimate, not "
            "confirmed portions of it. Known installed-game folders are excluded "
            "where detected. Protected/system locations or incomplete scans "
            "may leave substantial unclassified space.",
            "subtle", wrap=True))
        categories = label("Choose Analyze to see folder category totals.", "subtle", wrap=True)
        summary_col.addWidget(categories)
        report_stats = label("", "caption", wrap=True)
        summary_col.addWidget(report_stats)
        table = data_table(["FOLDER / ROOT FILE", "CATEGORY", "APPARENT SIZE", "FILES COUNTED"])
        table.setMinimumHeight(430)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setColumnWidth(0, 250)
        table.setColumnWidth(1, 230)
        table.setColumnWidth(2, 135)
        table.setRowCount(0)
        summary_col.addWidget(table)
        buttonbar = QWidget()
        br = row(spacing=8)
        buttonbar.setLayout(br)
        inspect = button("Analyze selected folder…")
        open_folder = button("Open folder in Explorer")
        back = button("Analyze entire drive again…")
        br.addWidget(inspect)
        br.addWidget(open_folder)
        br.addWidget(back)
        br.addStretch()
        summary_col.addWidget(buttonbar)
        page.content.addWidget(summary)

        import threading
        from performance_guard import GameActivityDetector, CooperativeGameplayPause
        current = {"report": None, "root": None}
        active_scan = getattr(self, "_other_storage_cancel_event", None)
        if active_scan is None:
            active_scan = threading.Event()
            self._other_storage_cancel_event = active_scan
        stop_scan.clicked.connect(active_scan.set)
        if getattr(self, "_other_storage_running", False):
            scan_state.setText("An Other Storage scan is still running. Cancel remains available.")
            run_scan.setEnabled(False)
            stop_scan.setEnabled(True)
            scan_mode.setEnabled(False)
            progress.setRange(0, 0)
            progress.show()
        def get_drive():
            return disk_choices.currentData()
        def refresh_drive(_=None):
            target = get_drive()
            self._other_selected_drive = target
            try:
                usage = shutil.disk_usage(target)
                guessed = sum(max(0, g.size_bytes or 0)
                              for g in self.inventory.games
                              if _game_on_drive(g.install_path, target))
                guessed = min(guessed, usage.used)
                other = max(0, usage.used - guessed)
                overview.setText(
                    f"Drive: {target}  •  Used: {human_size(usage.used)}  •  "
                    f"Known game sizes: up to {human_size(guessed)}  •  "
                    f"OTHER ESTIMATE: {human_size(other)}. "
                    "Launcher sizes may be missing or overlap.")
            except (OSError, ValueError):
                overview.setText("Could not read local drive capacity.")
            present = getattr(self, "_other_storage_report", None)
            previous_drive = getattr(self, "_other_storage_report_drive", None)
            if present is not None and previous_drive == target:
                show_report(present)
            else:
                current["report"] = None
                table.setRowCount(0)
                categories.setText("Not scanned. Choose Analyze.")
                report_stats.setText("Scan only starts after explicit approval.")
                scan_state.setText("Read-only, on-device category analysis.")
                inspect.setEnabled(False)
                open_folder.setEnabled(False)
                back.setEnabled(False)

        def show_report(report):
            if not isValid(table):
                return
            current["report"] = report
            current["root"] = report.root
            lines = defaultdict(int)
            for item in report.folders:
                lines[item.category] += item.apparent_bytes
            categories.setText(
                "\n".join(
                    f"{name}: {human_size(total)} apparent"
                    for name, total in sorted(lines.items(), key=lambda x: -x[1])
                ) or "No measurable folders found.")
            shown = report.folders[:150]
            table.setRowCount(len(shown))
            for index, item in enumerate(shown):
                for colno, value in enumerate((
                    item.name, item.category,
                    human_size(item.apparent_bytes),
                    f"{item.files_seen:,}",
                )):
                    _table_text(table, index, colno, value)
                table.setRowHeight(index, 35)
                table.item(index, 0).setToolTip(item.path)
            report_stats.setText(
                f"Scope: {report.root}  •  {report.entries_seen:,} entries examined  •  "
                f"{human_size(report.analyzed_bytes)} apparent bytes measured  •  "
                f"{report.skipped_entries:,} entries inaccessible/skipped  •  "
                f"{report.excluded_games:,} recognized game directories excluded.\n"
                f"Coverage: {report.limitation}")
            scan_state.setText(
                ("Read-only storage analysis completed. " if report.complete
                 else "Partial coverage: " + report.limitation + " ")
                + "No files modified.")
            progress.hide()
            run_scan.setEnabled(not getattr(self, "_other_storage_running", False))
            inspect.setEnabled(bool(shown))
            open_folder.setEnabled(bool(shown))
            back.setEnabled(report.root != get_drive())

        def selected_folder():
            idx = _selected_indices(table)
            data = current["report"]
            if not idx or data is None or idx[0] >= len(data.folders):
                return None
            return data.folders[idx[0]]

        def analyze(scope=None):
            if getattr(self, "_other_storage_running", False):
                scan_state.setText("Already analyzing Other Storage. Cancel the current scan first.")
                return
            drive = get_drive()
            if not drive:
                self.error("No drive found", "Select a connected local fixed drive.")
                return
            full_scan = scan_mode.currentText() == "Full Scan"
            mode_name = "Full Scan" if full_scan else "Quick Scan"
            proposed = str(scope or drive)
            terms = ("No entry or time limit. Can run a long time; Cancel is always available."
                     if full_scan else "Stops after 220,000 entries or 25 seconds.")
            if not self.confirm(
                "Start " + mode_name + "?",
                "Read-only file/folder metadata under:\n" + proposed
                + "\n\n" + terms
                + "\n\nPauses while games run. Inaccessible/linked locations remain excluded."
                + "\nNothing is opened, uploaded, modified, or deleted."):
                return
            from other_storage import analyze_other_storage
            selected_games = tuple(
                g.install_path for g in self.inventory.games
                if getattr(g, "install_path", None))
            active_scan.clear()
            self._other_storage_running = True
            scan_state.setText(mode_name + ": examining local metadata…")
            progress.setRange(0, 0 if full_scan else 100)
            if not full_scan:
                progress.setValue(0)
            progress.show()
            run_scan.setEnabled(False)
            stop_scan.setEnabled(True)
            scan_mode.setEnabled(False)
            drive_at_start = drive

            def job(emitter):
                try:
                    detector = GameActivityDetector()
                    # Suspend the walk while a game is detected. A user's
                    # Cancel input immediately terminates a paused scan.
                    gate = CooperativeGameplayPause(
                        active_scan.is_set, detector=detector,
                        on_pause=lambda paused: emitter(
                            0, "Paused for gameplay. Cancel remains available."
                            if paused else "Resuming low-priority scan"))
                    return True, analyze_other_storage(
                        drive_at_start, selected_games, scope=scope,
                        max_entries=None if full_scan else 220_000,
                        max_seconds=None if full_scan else 25,
                        cancel=gate.checkpoint, notify=emitter)
                except Exception as exc:
                    return False, type(exc).__name__ + ": " + str(exc)[:250]

            def progress_cb(percent, message):
                if isValid(scan_state):
                    if full_scan:
                        progress.setRange(0, 0)
                    elif "Paused for gameplay" not in message:
                        progress.setRange(0, 100)
                        progress.setValue(percent)
                    scan_state.setText(message)

            def done(outcome):
                self._other_storage_running = False
                if isValid(run_scan):
                    run_scan.setEnabled(True)
                    stop_scan.setEnabled(False)
                    scan_mode.setEnabled(True)
                    progress.hide()
                success, response = outcome
                if not success:
                    if isValid(scan_state):
                        scan_state.setText("Analysis failed. Choose Retry or another drive.")
                    self.error("Other Storage analysis incomplete", response)
                    return
                # Retain partial results, including deliberate cancellation.
                report = response
                self._other_storage_report = report
                self._other_storage_report_drive = drive_at_start
                if (isValid(table) and disk_choices.currentData() == drive_at_start):
                    show_report(report)
                else:
                    self.status.setText(
                        "Other Storage analysis ended; open that tab to inspect the results.")
            self.job(job, done, progress=progress_cb,
                     error_title="Other Storage analysis could not finish")

        def analyze_selected():
            entry = selected_folder()
            if entry is None:
                self.info("Choose a folder", "Select a row to inspect in more detail.")
                return
            path = Path(entry.path)
            if not path.is_dir():
                self.info("Root-level file", "This is a file, not a folder. Open its containing folder.")
                return
            analyze(scope=path)

        def open_selected():
            entry = selected_folder()
            if entry is not None:
                path = Path(entry.path)
                self._open_folder(str(path if path.is_dir() else path.parent))

        run_scan.clicked.connect(lambda _=False: analyze())
        inspect.clicked.connect(analyze_selected)
        open_folder.clicked.connect(open_selected)
        back.clicked.connect(lambda _=False: analyze())
        disk_choices.currentIndexChanged.connect(refresh_drive)
        refresh_drive()
        # refresh_drive may have cleared the disabled state of an ongoing job.
        if getattr(self, "_other_storage_running", False):
            run_scan.setEnabled(False)
            stop_scan.setEnabled(True)
            scan_mode.setEnabled(False)
            progress.setRange(0, 0)
            progress.show()
            scan_state.setText("Other Storage scan running. Cancel remains available.")

    def captures_page(self):
        """One Captures destination with distinct Screenshots and Videos panels.

        The normal scan discovers both automatically in known gaming locations.
        Filenames, sizes and times are metadata; no screenshot or video pixels
        are sent to any network service, and videos are not decoded by scanners.
        """
        page = self._new(
            "Captures", "Your gaming screenshots and recordings, organized separately.")
        if self._not_scanned(page):
            return
        shots = sorted(self.inventory.screenshots,
                       key=lambda x: (-x.modified, x.path.casefold()))
        recordings = sorted(self.inventory.recordings,
                            key=lambda x: (-x.modified, x.path.casefold()))
        counts = QWidget()
        statrow = row(spacing=10)
        counts.setLayout(statrow)
        statrow.addWidget(MetricCard(
            "SCREENSHOTS", str(len(shots)),
            "Recognized game captures • metadata only", tone="cyan"))
        statrow.addWidget(MetricCard(
            "VIDEOS / RECORDINGS", str(len(recordings)),
            "Known capture sources • metadata only", tone="text"))
        page.content.addWidget(counts)

        tabs = QTabWidget()
        tabs.setObjectName("captureTabs")
        tabs.setDocumentMode(True)
        tabs.setTabPosition(QTabWidget.North)
        tabs.setAccessibleName("Separate screenshot and video capture panels")
        page.content.addWidget(tabs)

        def build_panel(title, description):
            tab = QWidget()
            stack = column(spacing=12, margins=(12, 14, 12, 14))
            tab.setLayout(stack)
            header, body = panel(padding=16)
            header.setObjectName("dashboardPanel")
            body.addWidget(section_title(title))
            body.addWidget(label(description, "subtle", wrap=True))
            stack.addWidget(header)
            tabs.addTab(tab, title)
            return stack, body

        # ---------- SCREENSHOT PANEL ----------
        screenshot_stack, photo_col = build_panel(
            f"▧  Screenshots  ({len(shots)})",
            "Game Grave automatically finds game screenshots in supported Steam, "
            "launcher, capture and game-named screenshot folders. "
            "The dashboard shows your newest actual image. "
            "No personal Pictures-folder crawl; photos are decoded locally only "
            "for previews. Every Recycle Bin move requires separate approval.")
        actions = QWidget()
        controls = row(spacing=9)
        actions.setLayout(controls)
        controls.addWidget(button("Scan PC again", self.start_scan, kind="primary"))
        controls.addWidget(button("Review old screenshots in Graveyard",
                                  lambda: self.navigate("Graveyard")))
        controls.addStretch()
        photo_col.addWidget(actions)
        photos = shots[:700]
        photo_table = data_table(["SCREENSHOT", "SIZE", "MODIFIED", "LOCATION"])
        photo_table.setSelectionMode(QAbstractItemView.SingleSelection)
        photo_table.setMinimumHeight(350)
        photo_table.setColumnWidth(0, 285)
        photo_table.setColumnWidth(1, 105)
        photo_table.setColumnWidth(2, 135)
        photo_table.setRowCount(len(photos))
        for i, shot in enumerate(photos):
            for colno, value in enumerate((
                Path(shot.path).name, human_size(shot.size),
                datetime.fromtimestamp(shot.modified).strftime("%Y-%m-%d %H:%M"),
                str(Path(shot.path).parent),
            )):
                _table_text(photo_table, i, colno, value)
            photo_table.setRowHeight(i, 37)
        photo_col.addWidget(photo_table)
        from gg_desktop.capture_image import ScreenshotImage, request_screenshot
        photo_col.addWidget(label(
            "SELECTED SCREENSHOT  •  ACTUAL IMAGE FROM YOUR PC",
            "eyebrow"))
        selected_photo_image = ScreenshotImage(height=215)
        photo_col.addWidget(selected_photo_image)
        if not shots:
            photo_col.addWidget(label(
                "No in-game screenshots found yet. Scan PC or add a specific "
                "capture folder under Settings. No sample image will be substituted.",
                "subtle", wrap=True))

        def current_photo():
            indices = _selected_indices(photo_table)
            return photos[indices[0]] if indices and indices[0] < len(photos) else None

        def update_photo_thumbnail():
            item = current_photo()
            if item is None:
                selected_photo_image.set_status("Choose a screenshot to see its real thumbnail")
            else:
                request_screenshot(self, item, selected_photo_image)
        photo_table.itemSelectionChanged.connect(update_photo_thumbnail)
        if photos:
            photo_table.selectRow(0)

        def preview_photo():
            record = current_photo()
            if record is None:
                self.info("Choose one screenshot", "Select a screenshot before previewing it.")
            else:
                self._preview_capture(record)

        def folder_photo():
            record = current_photo()
            if record is not None:
                self._open_folder(str(Path(record.path).parent))

        photo_buttons = QWidget()
        photo_buttons_row = row(spacing=8)
        photo_buttons.setLayout(photo_buttons_row)
        photo_buttons_row.addWidget(button(
            "Preview selected screenshot…", preview_photo, kind="primary"))
        photo_buttons_row.addWidget(button("Open folder", folder_photo))
        photo_buttons_row.addStretch()
        photo_col.addWidget(photo_buttons)
        photo_table.cellDoubleClicked.connect(
            lambda index, _column: self._preview_capture(photos[index])
            if 0 <= index < len(photos) else None)

        def photo_menu(point):
            index = self._right_clicked_row(photo_table, point)
            if index is None or index >= len(photos):
                return
            item = photos[index]
            menu = QMenu(photo_table)
            menu.addAction("Preview screenshot and review Recycle Bin move…",
                           lambda: self._preview_capture(item))
            menu.addAction("Open containing folder",
                           lambda: self._open_folder(str(Path(item.path).parent)))
            action, reason = protection_action(
                item.path, list(self.settings.get("never_touch", [])))
            if action in ("Protect", "Unprotect"):
                menu.addAction(
                    "Protect screenshot" if action == "Protect" else "Remove personal protection…",
                    lambda: self._set_personal_protection(
                        item.path, protect=(action == "Protect"), return_route="Captures"))
            else:
                locked = menu.addAction("Protection cannot be changed here")
                locked.setEnabled(False)
            menu.addSeparator()
            notice = menu.addAction("Bulk image deletion unavailable: preview individually")
            notice.setEnabled(False)
            menu.exec(photo_table.viewport().mapToGlobal(point))
        photo_table.setContextMenuPolicy(Qt.CustomContextMenu)
        photo_table.customContextMenuRequested.connect(photo_menu)

        # ---------- VIDEO PANEL ----------
        video_stack, video_col = build_panel(
            f"▣  Videos / Recordings  ({len(recordings)})",
            "Game Grave detects gaming clips, highlights and recordings from "
            "recognized capture locations, including recent files. "
            "Videos stay in their original folders; click Open in player "
            "to use your Windows default media app. No video bytes are "
            "decoded or uploaded during scanning.")
        video_actions = QWidget()
        va = row(spacing=8)
        video_actions.setLayout(va)
        va.addWidget(button("Scan PC again", self.start_scan, kind="primary"))
        va.addWidget(button("Review old recordings in Graveyard",
                            lambda: self.navigate("Graveyard")))
        va.addStretch()
        video_col.addWidget(video_actions)

        clips = recordings[:700]
        video_table = data_table(["VIDEO / RECORDING", "SIZE", "MODIFIED", "LOCATION"])
        video_table.setSelectionMode(QAbstractItemView.SingleSelection)
        video_table.setMinimumHeight(350)
        video_table.setColumnWidth(0, 285)
        video_table.setColumnWidth(1, 105)
        video_table.setColumnWidth(2, 135)
        video_table.setRowCount(len(clips))
        for i, clip in enumerate(clips):
            for colno, value in enumerate((
                Path(clip.path).name, human_size(clip.size),
                datetime.fromtimestamp(clip.modified).strftime("%Y-%m-%d %H:%M"),
                str(Path(clip.path).parent),
            )):
                _table_text(video_table, i, colno, value)
            video_table.setRowHeight(i, 37)
        video_col.addWidget(video_table)
        if not recordings:
            video_col.addWidget(label(
                "No game recordings detected yet. Scan PC or add a capture "
                "folder in Settings. Personal videos are not categorized as games "
                "based only on file extension.",
                "subtle", wrap=True))

        def current_clip():
            indices = _selected_indices(video_table)
            return clips[indices[0]] if indices and indices[0] < len(clips) else None

        def open_clip(clip):
            from recordings import RECORDING_EXTENSIONS
            from core import _has_reparse_component
            file = Path(clip.path)
            if (clip not in self.inventory.recordings
                    or not is_unchanged(clip)
                    or _has_reparse_component(file)
                    or file.suffix.casefold() not in RECORDING_EXTENSIONS):
                self.error("Recording changed", "Scan PC again before opening this recording.")
                return
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(file))):
                self.error("Could not open recording",
                           "Windows could not open the recording in its default video player.")

        def selected_video():
            item = current_clip()
            if item is None:
                self.info("Select a recording", "Choose a video row first.")
            else:
                open_clip(item)

        def selected_folder():
            item = current_clip()
            if item is not None:
                self._open_folder(str(Path(item.path).parent))

        clip_controls = QWidget()
        clip_buttons = row(spacing=8)
        clip_controls.setLayout(clip_buttons)
        clip_buttons.addWidget(button("Open recording in player…", selected_video,
                                       kind="primary"))
        clip_buttons.addWidget(button("Open folder", selected_folder))
        clip_buttons.addStretch()
        video_col.addWidget(clip_controls)
        video_table.cellDoubleClicked.connect(
            lambda index, _column: open_clip(clips[index])
            if 0 <= index < len(clips) else None)

        def video_menu(point):
            index = self._right_clicked_row(video_table, point)
            if index is None or index >= len(clips):
                return
            item = clips[index]
            menu = QMenu(video_table)
            menu.addAction("Open in default video player…", lambda: open_clip(item))
            menu.addAction("Open containing folder",
                           lambda: self._open_folder(str(Path(item.path).parent)))
            action, reason = protection_action(
                item.path, list(self.settings.get("never_touch", [])))
            if action in ("Protect", "Unprotect"):
                menu.addAction(
                    "Protect this recording" if action == "Protect" else
                    "Remove personal protection…",
                    lambda: self._set_personal_protection(
                        item.path, protect=(action == "Protect"), return_route="Captures"))
            else:
                notice = menu.addAction("Protection cannot be changed here")
                notice.setEnabled(False)
            menu.addSeparator()
            note = menu.addAction("Cleanup requires Graveyard review and confirmation")
            note.setEnabled(False)
            menu.exec(video_table.viewport().mapToGlobal(point))
        video_table.setContextMenuPolicy(Qt.CustomContextMenu)
        video_table.customContextMenuRequested.connect(video_menu)

        # The two media types are intentionally separate panels/tabs.
        # A previous route alias can select the appropriate panel on entry.
        if getattr(self, "_show_capture_videos", False):
            tabs.setCurrentIndex(1)
            self._show_capture_videos = False
        else:
            tabs.setCurrentIndex(0)

    def screenshots_page(self):
        """Backwards-compatible method for existing screenshot navigation."""
        return self.captures_page()

    def undo_page(self):
        page = self._new("Undo Center",
                         "Check whether Windows still holds recycled files, then approve restoration.")
        entries = list(reversed(get_records()))[:300]
        page.content.addWidget(FeatureStrip([
            ("RECORDED", "Game Grave action log"),
            ("VERIFIED", "Check Windows match"),
            ("RESTORE", "Approve exact path"),
            ("CONFIRM", "No silent overwrite"),
        ]))
        recovery_visual, recovery_col = panel(padding=12)
        recovery_col.addWidget(section_title("RECOVERY ROUTE", "Select a row to examine"))
        recovery_path = RecoveryRoute()
        recovery_col.addWidget(recovery_path)
        page.content.addWidget(recovery_visual)
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
        def update_route():
            rec = selected_record()
            recovery_path.set_record(
                str(rec.get("path", "Select a recovery record")) if rec else
                "Select a recovery record",
                "Requires Windows check" if rec else "Not checked")
        table.itemSelectionChanged.connect(update_route)
        if entries:
            table.selectRow(0)
        else:
            contents.addWidget(clear_empty_panel(
                "No recovery records",
                "Game Grave has not recorded a Recycle Bin cleanup yet. "
                "Nothing to restore from this list."))
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
        line.addWidget(button("Verify exact Windows match", check))
        line.addWidget(button("Restore selected…", undo, kind="primary"))
        line.addWidget(button("Refresh records", lambda: self.navigate("Undo Center")))
        contents.addWidget(buttons)
        page.content.addWidget(p)
        _box_notice(page, "Undo depends on a unique matching Windows Recycle Bin item. "
                    "Emptying the Recycle Bin or source path conflicts may prevent recovery.",
                    warning=True)

    def _choose_old_files_c_drive(self):
        """Deliberately opt in to a read-only bounded C-drive scan."""
        from old_files_scope import is_fixed_drive_root
        root = Path("C:/")
        if not is_fixed_drive_root(root):
            self.error("C: is unavailable", "Only an existing local fixed C: drive can be scanned.")
            return
        if not self.confirm(
            "Select your entire C: drive for Old Files?",
            "Game Grave will READ file names, sizes and modified dates across "
            "permitted parts of C:\\\\. "
            "Windows folders, installed programs, Game Grave's protected "
            "locations, junctions and known game installs are excluded. "
            "The scan is limited to 25 seconds or 160,000 entries and "
            "may return partial findings. Old does not mean unused. "
            "Nothing is deleted automatically."):
            return
        updated = dict(self.settings)
        updated["scan_folder"] = str(root)
        try:
            save_settings(updated)
        except (OSError, ValueError) as exc:
            self.error("Cannot save C: scan choice", str(exc))
            return
        self.settings = updated
        self.status.setText("C: selected. Use Scan selected location to inspect old files.")
        self.navigate("Old Files")

    def _choose_scan_folder(self):
        chosen = QFileDialog.getExistingDirectory(self, "Select ordinary Old Files scan folder",
                                str(self.settings.get("scan_folder", str(Path.home()))))
        if not chosen:
            return
        from old_files_scope import accepted_old_files_scope, is_fixed_drive_root
        target = Path(chosen)
        if is_fixed_drive_root(target):
            self._choose_old_files_c_drive() if str(target).upper().startswith("C:") else (
                self.info("Choose a regular folder",
                          "Drive-wide review is currently available through the C: button."))
            return
        if not accepted_old_files_scope(target):
            self.error("Folder not allowed",
                       "Choose an ordinary local downloads/documents folder, "
                       "not a game install, mod manager, redirected path or Windows directory.")
            return
        updated = dict(self.settings)
        updated["scan_folder"] = str(target)
        try:
            save_settings(updated)
        except (OSError, ValueError) as exc:
            self.error("Cannot save folder preference", str(exc))
            return
        self.settings = updated
        self.status.setText("Old Files folder saved. Select Scan to inspect it.")
        self.navigate("Old Files")

    def settings_page(self):
        page = self._new(
            "Settings",
            "Customize Game Grave, scanning, protected paths, optional AI and appearance.")
        # Real Settings controls, grouped into a consistent two-column hub.
        # No fake launch/tray/update switches from the visual reference.
        settings_root = QWidget()
        settings_row = row(spacing=13)
        settings_root.setLayout(settings_row)
        category_nav = QListWidget()
        category_nav.setObjectName("settingsCategories")
        category_nav.setMaximumWidth(240)
        category_nav.setMinimumWidth(205)
        category_nav.setSpacing(5)
        category_nav.addItems([
            "General", "Scan & Cleanup", "Never Touch",
            "Captures", "AI Assistant", "Appearance & Privacy",
            "Backup & Restore", "About",
        ])
        settings_pages = QStackedWidget()
        settings_pages.setObjectName("settingsPanels")
        settings_row.addWidget(category_nav, 1)
        settings_row.addWidget(settings_pages, 3)
        page.content.addWidget(settings_root)

        general, general_col = panel(padding=16)
        general_col.setAlignment(Qt.AlignTop)
        general_col.addWidget(section_title("GENERAL  /  STARTUP"))
        launch_scan = QCheckBox("Scan local gaming inventory when Game Grave starts")
        launch_scan.setChecked(bool(self.settings.get("scan_on_launch", False)))
        general_col.addWidget(launch_scan)
        general_col.addWidget(label(
            "Scan on launch is read-only. Automatic file deletion remains disabled, "
            "and every Recycle Bin action requires separate authorization.",
            "subtle", wrap=True))
        def save_scan_on_launch(value):
            updated = dict(self.settings)
            updated["scan_on_launch"] = bool(value)
            try:
                save_settings(updated)
                self.settings = updated
            except (OSError, ValueError) as exc:
                launch_scan.blockSignals(True)
                launch_scan.setChecked(not bool(value))
                launch_scan.blockSignals(False)
                self.error("Could not save startup preference", str(exc))
        launch_scan.toggled.connect(save_scan_on_launch)
        general_col.addWidget(button("Scan PC now", self.start_scan, kind="primary"))
        settings_pages.addWidget(general)

        p, contents = panel()
        contents.addWidget(section_title("Scan preferences"))
        contents.addWidget(label(
            "Old Files: " + str(self.settings.get("scan_folder", "")),
            "subtle", wrap=True))
        contents.addWidget(button("Choose Old Files folder…", self._choose_scan_folder))
        from old_files_scope import is_fixed_drive_root
        if is_fixed_drive_root(Path("C:/")):
            contents.addWidget(button("Select C: for Old Files…",
                                      self._choose_old_files_c_drive))
        contents.addWidget(label(
            "Automatic cleanup remains OFF. Every actual Recycle Bin move "
            "requires separate approval.", "warning", wrap=True))
        p.layout().setAlignment(Qt.AlignTop)
        settings_pages.addWidget(p)

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
        p.layout().setAlignment(Qt.AlignTop)
        settings_pages.addWidget(p)

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
        p.layout().setAlignment(Qt.AlignTop)
        settings_pages.addWidget(p)

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
            self.open_ai_companion()
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
            else:
                self.status.setText("Local AI installed. Companion is available across tabs.")
                self.open_ai_companion()
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
                companion = getattr(self, "_ai_companion", None)
                if companion is not None:
                    companion.hide()
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
                self.open_ai_companion()
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
        p.layout().setAlignment(Qt.AlignTop)
        settings_pages.addWidget(p)

        p, stack = panel()
        stack.addWidget(section_title("Appearance and privacy"))
        stack.addWidget(label(
            "Crimson Command is a local UI preview. No account, telemetry, "
            "external images or automatic server polling. Older appearance themes "
            "remain available in the original Game Grave interface.",
            "subtle", wrap=True))
        stack.addWidget(button("Open classic appearance and advanced settings",
                               self._launch_classic_tools))
        p.layout().setAlignment(Qt.AlignTop)
        settings_pages.addWidget(p)

        backup, backup_col = panel(padding=16)
        backup_col.setAlignment(Qt.AlignTop)
        backup_col.addWidget(section_title("BACKUP & RESTORE"))
        backup_col.addWidget(label(
            "Undo Center restores only exact matching Windows Recycle Bin items. "
            "Resurrection Kits are separate backups and must be verified "
            "before restoration.", "subtle", wrap=True))
        backup_col.addWidget(button("Open Undo Center",
                                    lambda: self.navigate("Undo Center")))
        backup_col.addWidget(button("Open Resurrection Kit tools",
                                    lambda: self.navigate("More Tools")))
        settings_pages.addWidget(backup)

        about, about_col = panel(padding=16)
        about_col.setAlignment(Qt.AlignTop)
        about_col.addWidget(section_title("GAME GRAVE  /  CRIMSON COMMAND"))
        about_col.addWidget(label(
            "Gaming-aware, safety-first Windows storage inventory. "
            "Local-only scans, optional local AI, user-approved Recycle Bin "
            "cleanup, and readable Undo logs. This is still an engineering "
            "preview; it is not the stable 1.0 release.",
            "subtle", wrap=True))
        about_col.addWidget(button("Open More Tools",
                                   lambda: self.navigate("More Tools")))
        settings_pages.addWidget(about)

        def select_category(index):
            if 0 <= index < settings_pages.count():
                settings_pages.setCurrentIndex(index)
                self._settings_category_index = index
        category_nav.currentRowChanged.connect(select_category)
        category_nav.setCurrentRow(max(0, min(
            getattr(self, "_settings_category_index", 0),
            settings_pages.count() - 1)))

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
