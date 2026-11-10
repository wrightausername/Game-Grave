"""Interactive reference layouts, backed by the existing read-only inventory."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
import time
import uuid

from PySide6.QtCore import Qt, QSize, QSignalBlocker
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QFileDialog,
    QFrame, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QRadioButton, QScrollArea, QSizePolicy, QSplitter, QTableWidgetItem, QWidget,
)
from core import age_text, human_size, is_protected_path, save_settings, safe_scan_root
from cleanup_actions import recycle_old_files
from screenshots import looks_like_screenshot
from ui_paging import page_window
from gg_desktop.backend import refresh_graveyard
from gg_desktop import mods_sort
from gg_desktop.artwork import game_app_id
from gg_desktop.library_models import launcher_bucket, file_kind, mod_view, old_file_rows
from gg_desktop.models import readable_bytes, _path_key
from gg_desktop.reference_widgets import (
    CARD_ROLE, CoverArt, CoverGrid, DetailPanel, InventoryPager, MetricStrip, PageBanner, TabStrip,
    cover_icon, detail_line, detail_section, icon, tile_action, tool,
)
from gg_desktop.widgets import button, column, data_table, destroy_layout as _destroy, label, panel, row


def destroy_layout(layout):
    def hide(current):
        for index in range(current.count()):
            item = current.itemAt(index)
            if item.widget():
                item.widget().hide()
            elif item.layout():
                hide(item.layout())
    hide(layout)
    _destroy(layout)


def _combo(values, accessible):
    control = QComboBox()
    control.addItems(values)
    control.setAccessibleName(accessible)
    control.setFixedHeight(28)
    control.setMinimumWidth(65)
    control.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    return control


def _search(placeholder, accessible):
    control = QLineEdit()
    control.setPlaceholderText(placeholder)
    control.setAccessibleName(accessible)
    control.setFixedHeight(28)
    control.addAction(icon("search", "#aeb8c2", 17), QLineEdit.LeadingPosition)
    control.setClearButtonEnabled(True)
    return control


def _widget(layout):
    widget = QWidget()
    widget.setLayout(layout)
    widget.setMinimumWidth(0)
    return widget


def _table(headers):
    table = data_table(headers)
    table.setObjectName("referenceTable")
    table.setMinimumHeight(120)
    table.horizontalHeader().setStretchLastSection(False)
    table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
    table.horizontalHeader().setMinimumSectionSize(24)
    return table


def _text(table, r, c, text, symbol=None, color="#d7dfe7"):
    item = QTableWidgetItem(str(text))
    item.setToolTip(str(text))
    if symbol:
        item.setIcon(icon(symbol, color, 23))
    table.setItem(r, c, item)
    return item


def _check(table, r):
    item = QTableWidgetItem()
    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
    item.setCheckState(Qt.Unchecked)
    item.setToolTip("Select this specific row")
    table.setItem(r, 0, item)


def _checked(table):
    return [i for i in range(table.rowCount())
            if table.item(i, 0) and table.item(i, 0).checkState() == Qt.Checked]


def _detail_scroll(detail):
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setWidget(detail)
    scroll.setMinimumWidth(248)
    scroll.setMaximumWidth(332)
    return scroll


def _split(left, right, sizes):
    split = QSplitter(Qt.Horizontal)
    split.setChildrenCollapsible(False)
    split.setHandleWidth(10)
    split.addWidget(left)
    split.addWidget(right)
    split.setStretchFactor(0, 1)
    split.setStretchFactor(1, 0)
    split.setSizes(sizes)
    return split


def _view_switch(callback):
    box = row(spacing=1)
    group = QButtonGroup()
    controls = []
    for mode, symbol in (("grid", "grid"), ("list", "list")):
        control = tool("", symbol, kind="viewToggle", tip=mode.title() + " view")
        control.setAccessibleName(mode.title() + " view")
        control.setCheckable(True)
        control.setChecked(mode == "grid")
        control.clicked.connect(lambda _=False, mode=mode: callback(mode))
        group.addButton(control)
        box.addWidget(control)
        controls.append(control)
    widget = _widget(box)
    group.setParent(widget)
    widget.group = group
    widget.controls = controls
    return widget


class LibraryScreens:
    def _reference_page(self, title, subtitle, scene, symbol=None):
        page = self.page_for(title)
        page.content.setContentsMargins(16, 0, 8, 10)
        page.content.setSpacing(8)
        banner = PageBanner(title, subtitle, scene=scene, symbol=symbol)
        if scene == "old_files":
            banner.setFixedHeight(70)
        page.content.addWidget(banner)
        if self.inventory.warnings:
            warning = label("Partial scan · " + " ".join(self.inventory.warnings), "warning", wrap=True)
            page.content.addWidget(warning)
        return page

    def games_page(self):
        page = self._reference_page("Games", "Your complete game library. All launchers, one place. Manage, clean, and\nkeep your games running at their best.", "games")
        games = self.inventory.games
        counts = Counter(launcher_bucket(g.launcher) for g in games)
        page.content.addWidget(MetricStrip([
            ("game", len(games), "Total Games", "#ff183b"),
            ("steam", counts["Steam"], "Steam", "#13a7ef"),
            ("epic", counts["Epic"], "Epic", "#e2e4e7"),
            ("ea", counts["EA"], "EA", "#fa284a"),
            ("battlenet", counts["Battle.net"], "Battle.net", "#3ba9ed"),
            ("ubisoft", counts["Ubisoft"], "Ubisoft", "#d9e2f0"),
            ("xbox", counts["Xbox (PC)"], "Xbox (PC)", "#33d34d"),
            ("gog", counts["GOG"], "GOG", "#bc64ee"),
            ("plus", counts["Other"], "Other", "#dadfe6"),
        ], compact=True))
        library, contents = panel(kind="libraryPanel", padding=8, spacing=8)
        self.game_tabs = TabStrip([
            ("Library", "grid"), ("Installed", "download"), ("Favorites", "star"),
            ("Recently Played", "clock"), ("Not Installed", "archive"), ("Updates", "refresh"),
        ])
        contents.addWidget(self.game_tabs)
        searchbar = row(spacing=8)
        self.game_search = _search("Search your games…", "Search installed games")
        searchbar.addWidget(self.game_search, 1)
        searchbar.addWidget(label("Sort By:", "caption"))
        self.game_sort = _combo(["Recently played", "Name A to Z", "Largest known size", "Smallest known size", "Oldest played", "Launcher"], "Sort games")
        self.game_sort.setFixedWidth(120)
        searchbar.addWidget(self.game_sort)
        self.game_grid = CoverGrid()
        self.game_grid.set_artwork(self.artwork)
        self.game_grid.setAccessibleName("Game library covers")
        searchbar.addWidget(label("View:", "caption"))
        searchbar.addWidget(_view_switch(self.game_grid.set_mode))
        self.game_filter = _combo(["All launchers"] + sorted({g.launcher for g in games}), "Filter by launcher")
        self.game_filter.setVisible(False)
        preferred = getattr(self, "_pending_launcher_filter", None)
        if preferred:
            idx = self.game_filter.findText(preferred)
            self.game_filter.setCurrentIndex(max(0, idx))
            self.game_filter.show()
        self._pending_launcher_filter = None
        searchbar.addWidget(tool("Filters", "filter", lambda: self.game_filter.setVisible(not self.game_filter.isVisible())))
        contents.addWidget(_widget(searchbar))
        contents.addWidget(self.game_filter)
        favorites = set(self.settings.get("desktop_favorites", []))
        self.game_chips = TabStrip([
            (f"All Games ({len(games)})", "game"),
            (f"Installed ({sum(g.status.startswith('Installed') for g in games)})", "download"),
            ("Not Installed (—)", "archive"), ("Updates (—)", "refresh"),
            (f"Favorites ({sum(g.key in favorites for g in games)})", "star"),
            ("Large (≥100 GB)", "storage"),
        ], framed=False)
        contents.addWidget(self.game_chips)
        self.game_empty = label("", "emptyState", wrap=True)
        contents.addWidget(self.game_empty)
        contents.addWidget(self.game_grid, 1)
        self.game_count = label("", "caption")
        contents.addWidget(self.game_count)
        art_controls = row(spacing=6)
        self.game_artwork_status = label("Steam artwork loads automatically from cache or Steam.", "caption", wrap=True)
        art_controls.addWidget(self.game_artwork_status, 1)
        art_controls.addWidget(tool("Reload Artwork", "refresh", self._reload_game_artwork))
        contents.addWidget(_widget(art_controls))
        self.game_details = DetailPanel()
        self.game_details_col = self.game_details.content
        page.content.addWidget(_split(library, _detail_scroll(self.game_details), [740, 282]), 1)
        self._game_tab = "Library"
        self._game_chip = "All Games"
        self.game_search.textChanged.connect(self._fill_games)
        self.game_filter.currentTextChanged.connect(self._fill_games)
        self.game_sort.currentTextChanged.connect(self._fill_games)
        self.game_tabs.changed.connect(self._set_game_tab)
        self.game_chips.changed.connect(self._set_game_chip)
        self.game_grid.currentRowChanged.connect(self._game_details)
        self.game_grid.itemDoubleClicked.connect(lambda _: self._launch_selected_game())
        self.game_grid.favoriteRequested.connect(lambda i: self._toggle_favorite(self._shown_games[i]))
        self._fill_games()

    def _set_game_tab(self, name):
        self._game_tab = name
        self._game_chip = "All Games"
        self.game_chips.select(next(iter(self.game_chips.buttons)))
        self._fill_games()

    def _set_game_chip(self, name):
        self._game_chip = name.split(" (")[0]
        self._fill_games()

    def _fill_games(self, *_):
        query = self.game_search.text().strip().casefold()
        launcher = self.game_filter.currentText()
        active = {self._game_tab, self._game_chip}
        favorites = set(self.settings.get("desktop_favorites", []))
        current = self._current_game()
        rows = [g for g in self.inventory.games
                if (launcher == "All launchers" or g.launcher == launcher)
                and (not query or query in (g.name + " " + g.launcher + " " + g.install_path).casefold())
                and ("Favorites" not in active or g.key in favorites)
                and ("Installed" not in active or g.status.startswith("Installed"))
                and ("Recently Played" not in active or g.last_played_at is not None)
                and ("Large" not in active or (g.size_bytes is not None and g.size_bytes >= 100 * 1024 ** 3))]
        unavailable = bool({"Not Installed", "Updates"} & active)
        if unavailable:
            rows = []
        sort = self.game_sort.currentText()
        if sort == "Name A to Z":
            rows.sort(key=lambda g: g.name.casefold())
        elif sort == "Launcher":
            rows.sort(key=lambda g: (g.launcher.casefold(), g.name.casefold()))
        elif sort in ("Recently played", "Oldest played"):
            rows.sort(key=lambda g: (g.last_played_at is None,
                                     -(g.last_played_at or 0) if sort == "Recently played" else g.last_played_at or 0,
                                     g.name.casefold()))
        else:
            rows.sort(key=lambda g: (g.size_bytes is None,
                                     (g.size_bytes or 0) * (-1 if sort == "Largest known size" else 1), g.name.casefold()))
        self._shown_games = rows
        with QSignalBlocker(self.game_grid):
            self.game_grid.clear()
            for g in rows:
                item = QListWidgetItem(g.name)
                item.setToolTip(g.name + "\n" + g.launcher + " · " + g.status)
                item.setData(CARD_ROLE, {"name": g.name, "size": readable_bytes(g.size_bytes),
                                        "source": g.launcher, "steam_app_id": game_app_id(g), "favorite": g.key in favorites,
                                        "status_icon": "check" if g.status.startswith("Installed") else "shield"})
                self.game_grid.addItem(item)
            selected = next((i for i, g in enumerate(rows) if current and g.key == current.key), 0)
            if rows:
                self.game_grid.setCurrentRow(selected)
        message = ("Launcher ownership and update status are not available from this local scan."
                   if unavailable else "No games match these filters." if self.inventory.scanned_at
                   else "Your library starts here. Use Scan PC (F5) to find your installed games.")
        self.game_empty.setText(message if not rows else "")
        self.game_empty.setVisible(not rows)
        self.game_count.setText(f"{len(rows):,} games shown · Local library" if self.inventory.scanned_at else "No scan yet · Nothing has been changed")
        self._game_details()
        self.game_grid.doItemsLayout()
        self._update_game_artwork_status()

    def _reload_game_artwork(self):
        self.artwork.retry()
        self.game_grid.viewport().update()
        self._game_details()

    def _update_game_artwork_status(self):
        ids = {app_id for g in self._shown_games if (app_id := game_app_id(g))}
        ready = sum((app_id, "cover") in self.artwork.images for app_id in ids)
        missing = sum((app_id, "cover") in self.artwork.failed for app_id in ids)
        pending = sum((app_id, "cover") in self.artwork.pending for app_id in ids)
        self.game_artwork_status.setText(f"Steam artwork: {ready} ready · {pending} loading" +
            (f" · {missing} unavailable — Reload Artwork to retry" if missing else "") if ids else "Steam artwork loads automatically for detected Steam games.")

    def _current_game(self):
        index = self.game_grid.currentRow() if hasattr(self, "game_grid") else -1
        games = getattr(self, "_shown_games", [])
        return games[index] if 0 <= index < len(games) else None

    def _game_details(self, *_):
        contents = self.game_details_col
        contents.setSpacing(4)
        destroy_layout(contents)
        game = self._current_game()
        if game is None:
            contents.addWidget(CoverArt("Game Grave", height=112))
            contents.addWidget(label("Your game, at a glance", "detailTitle", wrap=True))
            contents.addWidget(label("Select a game to see its installation, launcher, source evidence and available actions.", "subtle", wrap=True))
            contents.addStretch()
            return
        contents.addWidget(CoverArt(game.name, height=101, artwork=self.artwork, app_id=game_app_id(game)))
        heading = row(spacing=4)
        heading.addWidget(label(game.name, "detailTitle", wrap=True), 1)
        favorite = game.key in self.settings.get("desktop_favorites", [])
        fav = tool("", "star", lambda: self._toggle_favorite(game), tip="Remove favorite" if favorite else "Add favorite")
        fav.setIcon(icon("star", "#ffcb21" if favorite else "#a1a6ad"))
        fav.setAccessibleName("Remove favorite" if favorite else "Add favorite")
        heading.addWidget(fav)
        contents.addWidget(_widget(heading))
        contents.addWidget(label("✓  Installed" if game.status.startswith("Installed") else game.status,
                                 "successText" if game.status.startswith("Installed") else "warning", wrap=True))
        play = tool("Play", "play", lambda: self._launch_game(game), kind="primary")
        play.setEnabled(game.launcher == "Steam" and game.app_id is not None and game.app_id.isdecimal()
                        and "steam_uninstall" in game.capabilities)
        play.setToolTip("Launch via Steam" if play.isEnabled() else "Launch this game in its own launcher; no verified launch shortcut is available.")
        play_row = row(spacing=6)
        play_row.addWidget(play, 1)
        play_row.addWidget(tool("", "more", lambda: self.page.games.options(game), tip="Game options"))
        contents.addWidget(_widget(play_row))
        for symbol, title, value in (
            ("refresh", "Launcher", game.launcher), ("folder", "Install Location", game.install_path),
            ("storage", "Install Size", readable_bytes(game.size_bytes)),
            ("clock", "Last Played", age_text(game.last_played_at) if game.last_played_at is not None else "Unknown"),
            ("clock", "Total Playtime", "Unknown"), ("sparkles", "Updates", "Unknown"),
        ):
            detail_line(contents, symbol, title, value)
        actions = row(spacing=5)
        actions.addWidget(tile_action("Game DNA", "dna", lambda: self._photo_game_dna(game)))
        actions.addWidget(tile_action("Mods", "mods", lambda: self.navigate("Mods")))
        actions.addWidget(tile_action("Save Vault", "storage", self._create_save_backup))
        contents.addWidget(_widget(actions))
        detail_section(contents, "Quick Actions")
        actions = row(spacing=5)
        folder = tile_action("Open Folder", "folder", lambda: self._open_folder(game.install_path))
        folder.setEnabled("open_folder" in game.capabilities)
        actions.addWidget(folder)
        for text, symbol, action in (("Verify Files…", "check", "validate"), ("Manage DLC…", "box", "details")):
            control = tile_action(text, symbol, lambda _=False, action=action: self._steam_game_action(game, action))
            control.setEnabled("steam_uninstall" in game.capabilities)
            control.setToolTip("Open this game's Steam controls" if control.isEnabled() else "Manage this game in its own launcher")
            actions.addWidget(control)
        uninstall = tile_action("Uninstall…", "trash", lambda: self._steam_uninstall(game))
        uninstall.setEnabled("steam_uninstall" in game.capabilities)
        uninstall.setToolTip("Open Steam's own uninstall confirmation" if uninstall.isEnabled() else "Manage this installation in its launcher")
        actions.addWidget(uninstall)
        contents.addWidget(_widget(actions))
        contents.addStretch()

    def _toggle_favorite(self, game):
        values = set(self.settings.get("desktop_favorites", []))
        values.discard(game.key) if game.key in values else values.add(game.key)
        updated = dict(self.settings, desktop_favorites=sorted(values))
        try:
            save_settings(updated)
        except (OSError, ValueError) as exc:
            self.error("Favorite not saved", str(exc))
            return
        self.settings = updated
        count = sum(g.key in values for g in self.inventory.games)
        for name, control in self.game_chips.buttons.items():
            if name.startswith("Favorites"):
                control.setText(f"Favorites ({count})")
        self._fill_games()

    def _launch_selected_game(self):
        game = self._current_game()
        if game:
            self._launch_game(game)

    def _steam_game_action(self, game, action):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        if (game.launcher != "Steam" or not game.app_id or not game.app_id.isdecimal()
                or "steam_uninstall" not in game.capabilities or action not in {"validate", "details"}):
            return
        uri = "steam://validate/" if action == "validate" else "steam://nav/games/details/"
        if not QDesktopServices.openUrl(QUrl(uri + game.app_id)):
            self.error("Steam unavailable", "Steam could not open this game's controls.")

    def _launch_game(self, game):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        if (game.launcher != "Steam" or not game.app_id or not game.app_id.isdecimal()
                or "steam_uninstall" not in game.capabilities):
            self.info("Open your launcher", "This scan does not provide a verified launch shortcut. Open the game in its launcher.")
            return
        if not QDesktopServices.openUrl(QUrl("steam://rungameid/" + game.app_id)):
            self.error("Steam unavailable", "Steam could not open this game's launch shortcut.")

    def mods_page(self):
        page = self._reference_page("Mods", "Discover, manage, and optimize your mods, all in one place.\nMore performance. Fewer conflicts. A cleaner game.", "mods", "mods")
        mods = self.inventory.mods
        known_size = sum(max(0, m.apparent_bytes) for m in mods)
        from gg_desktop.mods_words import FOLDERS_CAPTION, FOLDERS_TIP, TILE_TIPS
        unknown_tip = "Game Grave has not read this from your mod manager yet."
        page.content.addWidget(MetricStrip([
            ("mods", len(mods), FOLDERS_CAPTION, "#df83ec", FOLDERS_TIP),
            ("check", "—", TILE_TIPS[1][0], "#27dc74", TILE_TIPS[1][1] + " " + unknown_tip),
            ("warning", "—", TILE_TIPS[2][0], "#f7b737", TILE_TIPS[2][1] + " " + unknown_tip),
            ("refresh", "—", TILE_TIPS[3][0], "#fa2245", TILE_TIPS[3][1] + " " + unknown_tip),
            ("shield", "—", TILE_TIPS[4][0], "#9ca8bd", TILE_TIPS[4][1] + " " + unknown_tip),
            ("storage", human_size(known_size), TILE_TIPS[5][0], "#9bcde4", TILE_TIPS[5][1]),
        ]))
        left = _widget(column(spacing=8))
        self.mod_tabs = TabStrip([("Library", "archive"), ("Mod Radar", "radio"),
                                  ("Load Order", "list"), ("Profiles", "search"),
                                  ("Conflicts", "warning"), ("Cleanup", "refresh"),
                                  ("Bisect", "scan")])
        left.layout().addWidget(self.mod_tabs)
        sidebar, filters = panel(kind="filterPanel", padding=9, spacing=7)
        sidebar.setFixedWidth(202)
        filters.addWidget(label("Game Filters", "filterHeading"))
        self.mod_search = _search("Search mods…", "Search mod storage")
        filters.addWidget(self.mod_search)
        self._mod_views = [mod_view(m, self.inventory.games) for m in mods]
        self.mod_game_filters = QListWidget()
        self.mod_game_filters.setObjectName("sourceFilters")
        self.mod_game_filters.setAccessibleName("Filter mods by game")
        self.mod_game_filters.setMinimumHeight(100)
        game_counts = Counter(m.game for m in self._mod_views)
        for name, count in [("All Games", len(mods))] + sorted(game_counts.items()):
            item = QListWidgetItem(icon("game" if name != "All Games" else "mods", "#e15e78", 18), f"{name}  ({count})")
            item.setData(Qt.UserRole, name)
            item.setToolTip(name)
            self.mod_game_filters.addItem(item)
        self.mod_game_filters.setCurrentRow(0)
        filters.addWidget(self.mod_game_filters, 1)
        filters.addWidget(label("Mod Manager Filters", "filterHeading"))
        self.mod_manager_checks = []
        for manager, count in sorted(Counter(m.manager for m in self._mod_views).items()):
            control = QCheckBox(f"{manager}  ({count})")
            control.setToolTip(manager)
            control.setProperty("manager", manager)
            control.toggled.connect(self._fill_mods)
            filters.addWidget(control)
            self.mod_manager_checks.append(control)
        filters.addWidget(button("Clear All", self._clear_mod_filters, kind="link"))
        library, contents = panel(kind="libraryPanel", padding=8, spacing=6)
        toolbar = row(spacing=6)
        toolbar.addWidget(label("Sort by", "caption"))
        self.mod_sort = _combo(list(mods_sort.OPTIONS), "Sort mod locations")
        toolbar.addWidget(self.mod_sort, 1)
        toolbar.addWidget(label("Filter", "caption"))
        self.mod_type = _combo(["All Types", "Manager storage", "Game folders"], "Filter mod source type")
        toolbar.addWidget(self.mod_type, 1)
        contents.addWidget(_widget(toolbar))
        self.mod_notice = label("", "caption", wrap=True)
        contents.addWidget(self.mod_notice)
        self.mod_table = _table(["", "Name", "Game", "Manager", "Size", "Status", "Modified"])
        self.mod_table.setIconSize(QSize(48, 30))
        for i, width in enumerate([25, 170, 110, 100, 62, 92, 84]):
            self.mod_table.setColumnWidth(i, width)
        self.mod_table.horizontalHeader().setSectionsClickable(True)
        self.mod_table.horizontalHeader().sectionClicked.connect(self._sort_mods_by_header)
        self.mod_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        contents.addWidget(self.mod_table, 1)
        self.mod_pager = InventoryPager()
        self.mod_pager.changed.connect(lambda page: self._fill_mods(requested_page=page))
        contents.addWidget(self.mod_pager)
        footer = row(spacing=5)
        self.mod_selection = label("0 selected", "caption")
        self.mod_selection.setMinimumWidth(0)
        self.mod_selection.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        footer.addWidget(self.mod_selection, 1)
        footer.addWidget(tool("Add Source", "download", self._add_mod_source))
        footer.addWidget(tool("Scan for Mods", "refresh", self.start_scan, kind="primary"))
        contents.addWidget(_widget(footer))
        left.layout().addWidget(_split(sidebar, library, [202, 530]), 1)
        self.mod_details = DetailPanel()
        page.content.addWidget(_split(left, _detail_scroll(self.mod_details), [740, 282]), 1)
        self._mod_tab = "Library"
        self.mod_tabs.changed.connect(self._set_mod_tab)
        self.mod_search.textChanged.connect(self._fill_mods)
        self.mod_game_filters.currentRowChanged.connect(self._fill_mods)
        self.mod_sort.currentTextChanged.connect(self._fill_mods)
        self.mod_type.currentTextChanged.connect(self._fill_mods)
        self.mod_table.itemSelectionChanged.connect(self._mod_details)
        self.mod_table.itemChanged.connect(self._mod_selection_count)
        self._fill_mods()

    def _set_mod_tab(self, name):
        self._mod_tab = name
        self._fill_mods()

    def _sort_mods_by_header(self, column):
        if self._mod_tab != "Library":
            return
        option = mods_sort.header_option(column, self.mod_sort.currentText())
        if option:
            self.mod_sort.setCurrentText(option)

    def _clear_mod_filters(self):
        self.mod_search.clear()
        self.mod_game_filters.setCurrentRow(0)
        for control in self.mod_manager_checks:
            control.setChecked(False)
        self.mod_type.setCurrentIndex(0)
        self.mod_sort.setCurrentIndex(0)
        self._fill_mods()

    def _fill_mods(self, *_, requested_page=0):
        query = self.mod_search.text().casefold().strip()
        game_item = self.mod_game_filters.currentItem()
        game = game_item.data(Qt.UserRole) if game_item else "All Games"
        managers = {c.property("manager") for c in self.mod_manager_checks if c.isChecked()}
        kind = self.mod_type.currentText()
        rows = [m for m in self._mod_views
                if (game == "All Games" or game == m.game)
                and (not managers or m.manager in managers)
                and (not query or query in (m.name + " " + m.manager + " " + m.game + " " + str(m.record.path)).casefold())
                and (kind == "All Types" or (kind == "Game folders") == (m.game != "Unverified"))]
        rows = mods_sort.sort_views(rows, self.mod_sort.currentText())
        tab = self._mod_tab
        notice = {"Library": "", "Mod Radar": "Read-only source evidence · All detected storage remains protected.",
                  "Load Order": "Load order decides which mod wins when two change the same file. Open your mod manager to view or change it.",
                  "Profiles": "Profiles remain protected. Manage them in their original mod manager.",
                  "Conflicts": "Conflict detection is unavailable. This scan cannot establish that there are no conflicts.",
                  "Cleanup": "Managed mods and profiles remain protected. Review standalone archives in Old Files.",
                  "Bisect": "Find which mod is crashing your game. Your own profile is never changed."}[tab]
        if tab == "Conflicts":
            rows = []
        self.mod_notice.setText(notice or ("No mod locations match these filters." if self.inventory.scanned_at
                                          else "Scan PC to discover local mod storage.") if not rows else notice)
        self.mod_notice.setVisible(bool(self.mod_notice.text()))
        window = page_window(rows, requested_page)
        self.mod_pager.update_window(window)
        rows = list(window.items)
        self._shown_mods = rows
        with QSignalBlocker(self.mod_table):
            self.mod_table.setRowCount(0)
            self.mod_table.setRowCount(len(rows))
            for i, m in enumerate(rows):
                _check(self.mod_table, i)
                item = _text(self.mod_table, i, 1, m.name)
                raw_name = str(getattr(m.record, "name", ""))
                if raw_name and raw_name != m.name:
                    item.setToolTip(f"{m.name}\nFolder name on disk: {raw_name}")
                item.setIcon(cover_icon(m.game if m.game != "Unverified" else m.name))
                for c, value in enumerate((m.game, m.manager, mods_sort.size_text(m.size), "Storage folder"), 2):
                    _text(self.mod_table, i, c, value)
                _text(self.mod_table, i, 6, mods_sort.date_text(mods_sort.modified_time(str(m.record.path))))
                self.mod_table.setRowHeight(i, 40)
            if rows:
                self.mod_table.selectRow(0)
        self._mod_selection_count()
        self._mod_details()

    def _mod_selection_count(self, *_):
        self.mod_selection.setText(f"{len(_checked(self.mod_table))} selected · {self.mod_table.rowCount()} locations")

    def _mod_details(self):
        contents = self.mod_details.content
        contents.setSpacing(5)
        destroy_layout(contents)
        index = self.mod_table.currentRow()
        rows = self._shown_mods
        if not 0 <= index < len(rows):
            contents.addWidget(CoverArt("Game Grave"))
            contents.addWidget(label("Select a mod location", "detailTitle", wrap=True))
            contents.addWidget(label("Inspect its source and protection details here.", "subtle", wrap=True))
            contents.addStretch()
            return
        m = rows[index]
        contents.addWidget(CoverArt(m.game if m.game != "Unverified" else m.name, height=84))
        contents.addWidget(label(m.name, "detailTitle", wrap=True))
        contents.addWidget(label("◇  Protected storage", "successText"))
        contents.addWidget(label(m.evidence, "subtle", wrap=True))
        for symbol, title, value in (
            ("game", "Game", m.game), ("shield", "Manager", m.manager),
            ("help", "Version", "Unknown"), ("storage", "Apparent Size", readable_bytes(m.size)),
            ("file", "Files", str(m.record.file_count)),
            *((("folder", "Folder name", str(m.record.name)),) if str(m.record.name) != m.name else ()),
            ("folder", "Location", str(m.record.path)),
        ):
            detail_line(contents, symbol, title, value)
        contents.addWidget(tool("Open Folder", "folder", lambda: self._open_folder(str(m.record.path)), kind="primary"))
        contents.addWidget(tool("Open Mod Manager Tools", "mods", self._launch_classic_tools))
        detail_section(contents, "Mod Status")
        for symbol, title in (("list", "Load Order"), ("help", "Dependencies"), ("warning", "Conflicts"), ("shield", "Used By")):
            detail_line(contents, symbol, title, "Unknown")
        detail_section(contents, "Source Evidence")
        indicators = ", ".join(str(s) for s in m.record.indicators) or "No individual mod metadata"
        contents.addWidget(label(indicators, "subtle", wrap=True))
        contents.addWidget(label(str(m.record.advice), "caption", wrap=True))
        contents.addWidget(label("Managed content stays protected. Age alone cannot establish that a mod is unused.", "warning", wrap=True))
        contents.addStretch()

    def _add_mod_source(self):
        chosen = QFileDialog.getExistingDirectory(self, "Add a read-only mod scan source")
        if not chosen:
            return
        target = Path(chosen)
        from core import _has_reparse_component
        if not safe_scan_root(target) or _has_reparse_component(target):
            self.error("Source not allowed", "Choose a normal local directory, not a drive root or redirected path.")
            return
        roots = list(self.settings.get("mod_extra_roots", []))
        if chosen not in roots:
            updated = dict(self.settings, mod_extra_roots=roots + [chosen])
            try:
                save_settings(updated)
            except (OSError, ValueError) as exc:
                self.error("Source not saved", str(exc))
                return
            self.settings = updated
        self.start_scan()

    def old_files_page(self):
        page = self._reference_page("Old Files", "Find and manage old, unused, and forgotten files taking up space on your drives.", "old_files")
        current_root = str(self.settings.get("scan_folder", ""))
        inventory_root = self.inventory.file_scan_root
        self._old_root = inventory_root or current_root
        self._old_days = self.inventory.file_scan_days if self.inventory.file_scan_days is not None else int(self.settings.get("files_stale_days", 180))
        self._old_source = list(self.inventory.files) if not inventory_root or _path_key(inventory_root) == _path_key(current_root) else []
        files = self._old_source
        size = sum(f.size for f in files)
        oldest = max((int((time.time() - f.modified) / 86400) for f in files), default=None)
        counts = Counter(file_kind(f.path) for f in files)
        page.content.addWidget(MetricStrip([
            ("folder", f"{len(files):,}", "Old Files Found", "#dd76ea"),
            ("storage", human_size(size), "Apparent Size", "#13d5e2"),
            ("clock", f"{oldest // 30}+ Months" if oldest is not None else "—", "Oldest Modified", "#f7c327"),
            ("game", "—", "Game Relation Unknown", "#fb173d"),
            ("download", counts["Archives"] + counts["Installers"], "Archives / Installers", "#15b9f5"),
            ("file", len(files) - counts["Archives"] - counts["Installers"], "Other Files", "#d4d9e2"),
        ], compact=True))
        self.old_tabs = TabStrip([("File Scan", "search"), ("Results", "list"), ("By Game", "game"),
                                  ("Downloads", "download"), ("Archives", "file"),
                                  ("Unused Installers", "box"), ("Large Files", "storage"), ("Settings", "settings")])
        self.old_tabs.setFixedHeight(39)
        page.content.addWidget(self.old_tabs)
        filters, scan = panel(kind="fileFilterPanel", padding=9, spacing=7)
        self.old_filters = filters
        filters.setFixedWidth(190 if self.width() >= 1100 else 176)
        scan.addWidget(label("Scan & Filter", "sectionTitle"))
        detail_section(scan, "Scan Location")
        scan.addWidget(label(current_root or "Choose a folder", "subtle", wrap=True))
        scan.addWidget(tool("Change Folder", "folder", self._choose_scan_folder))
        detail_section(scan, "Age (Last Modified)")
        self.old_age_group = QButtonGroup(filters)
        self.old_age_controls = []
        for text, days in (("All scanned files", 0), ("30+ Days", 30), ("3+ Months", 90), ("6+ Months", 180), ("12+ Months", 365)):
            control = QRadioButton(text)
            control.setProperty("days", days)
            control.setChecked(days == 0)
            self.old_age_group.addButton(control)
            control.toggled.connect(self._fill_old_files)
            scan.addWidget(control)
            self.old_age_controls.append(control)
        detail_section(scan, "File Type")
        self.old_type_controls = []
        for kind in ("Archives", "Installers", "Logs / Crash Reports", "Media", "Other"):
            control = QCheckBox(kind)
            control.setChecked(True)
            control.toggled.connect(self._fill_old_files)
            scan.addWidget(control)
            self.old_type_controls.append(control)
        scan.addStretch()
        scan.addWidget(label(f"Scan includes files modified {self._old_days}+ days ago. Age is not proof of disuse.", "caption", wrap=True))
        scan.addWidget(tool("Scan Now", "refresh", self._old_scan, kind="primary"))
        results, contents = panel(kind="fileResults", padding=8, spacing=6)
        toolbar = row(spacing=3)
        heading = column(spacing=0)
        heading.addWidget(label("Scan Results", "sectionTitle"))
        self.old_result_count = label("", "caption")
        heading.addWidget(self.old_result_count)
        toolbar.addLayout(heading, 1)
        toolbar.addWidget(label("Sort By:", "caption"))
        self.old_sort = _combo(["Size (Largest)", "Name (A–Z)", "Oldest Modified", "Newest Modified"], "Sort old files")
        self.old_sort.setFixedWidth(110)
        toolbar.addWidget(self.old_sort)
        contents.addWidget(_widget(toolbar))
        self.old_search = _search("Search files, folders, or file types…", "Search old files")
        contents.addWidget(self.old_search)
        self.old_notice = label("", "caption", wrap=True)
        contents.addWidget(self.old_notice)
        self.old_table = _table(["", "Name", "Location", "Last Modified", "Size", "Type"])
        for i, width in enumerate((24, 178, 122, 86, 65, 62)):
            self.old_table.setColumnWidth(i, width)
        self.old_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.old_table.setSelectionMode(QAbstractItemView.SingleSelection)
        contents.addWidget(self.old_table, 1)
        self.old_pager = InventoryPager()
        self.old_pager.changed.connect(lambda page: self._fill_old_files(requested_page=page))
        contents.addWidget(self.old_pager)
        footer = row(spacing=3)
        self.old_select_all = QCheckBox("Select All")
        self.old_select_all.setAccessibleName("Select all visible old files")
        self.old_select_all.toggled.connect(self._select_old_visible)
        footer.addWidget(self.old_select_all)
        self.old_selection = label("0 selected", "caption")
        self.old_selection.setMinimumWidth(0)
        self.old_selection.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        footer.addWidget(self.old_selection, 1)
        footer.addWidget(tool("Add to Graveyard", "grave", self._add_old_to_graveyard))
        footer.addWidget(tool("Protect", "shield", self._protect_old_selected))
        self.old_delete = tool("Recycle…", "trash", self._recycle_old_selected, kind="danger",
                               tip="Review selected individual files before moving to Windows Recycle Bin")
        footer.addWidget(self.old_delete)
        contents.addWidget(_widget(footer))
        left = _split(filters, results, [190, 532])
        self.old_details = DetailPanel()
        page.content.addWidget(_split(left, _detail_scroll(self.old_details), [740, 292]), 1)
        self._old_tab = "File Scan"
        self.old_sort.currentTextChanged.connect(self._fill_old_files)
        self.old_search.textChanged.connect(self._fill_old_files)
        self.old_tabs.changed.connect(self._set_old_tab)
        self.old_table.itemSelectionChanged.connect(self._old_details)
        self.old_table.itemChanged.connect(self._old_selection_count)
        self._fill_old_files()

    def _set_old_tab(self, name):
        if name == "Settings":
            self.navigate("Settings")
            return
        self._old_tab = name
        self._fill_old_files()

    def _fill_old_files(self, *_, requested_page=0):
        if not hasattr(self, "old_table") or self.current_route != "Old Files":
            return
        days = next((c.property("days") for c in self.old_age_controls if c.isChecked()), 0)
        kinds = {c.text() for c in self.old_type_controls if c.isChecked()}
        rows = old_file_rows(self._old_source, query=self.old_search.text(), kinds=kinds,
                             days=days, sort=self.old_sort.currentText()) if kinds else []
        tab = self._old_tab
        notice = ""
        if tab == "Archives":
            rows = [f for f in rows if file_kind(f.path) == "Archives"]
        elif tab == "Unused Installers":
            rows = [f for f in rows if file_kind(f.path) == "Installers"]
            notice = "Installer files · This scan does not establish whether they are unused."
        elif tab == "Large Files":
            rows = [f for f in rows if f.size >= 1024 ** 3]
            notice = "Files of 1 GB or more."
        elif tab == "By Game":
            rows = []
            notice = "Game ownership is unverified in this scan. Inspect Game DNA for available relationship evidence."
        elif tab == "Downloads":
            notice = "Showing the selected scan folder. Choose your Downloads folder and rescan to inspect it."
        if not rows and not notice:
            notice = "No files match these filters." if self.inventory.scanned_at else "Choose a scan folder and use Scan Now. No files have been changed."
        checked_paths = {str(self._shown_old_files[i].path) for i in _checked(self.old_table)
                         if i < len(getattr(self, "_shown_old_files", []))}
        current_row = self.old_table.currentRow()
        previous = getattr(self, "_shown_old_files", [])
        current_path = str(previous[current_row].path) if 0 <= current_row < len(previous) else None
        self.old_result_count.setText(f"{len(rows):,} files  ({human_size(sum(f.size for f in rows))})")
        window = page_window(rows, requested_page)
        self.old_pager.update_window(window)
        rows = list(window.items)
        self._shown_old_files = rows
        with QSignalBlocker(self.old_table):
            self.old_table.setRowCount(0)
            self.old_table.setRowCount(len(rows))
            for i, f in enumerate(rows):
                _check(self.old_table, i)
                if str(f.path) in checked_paths:
                    self.old_table.item(i, 0).setCheckState(Qt.Checked)
                kind = file_kind(f.path)
                symbol, color = {"Archives": ("storage", "#d67ee9"), "Installers": ("box", "#e7be1f"),
                                 "Logs / Crash Reports": ("file", "#c5d5e2"), "Media": ("camera", "#70db65")}.get(kind, ("file", "#ccd7e0"))
                _text(self.old_table, i, 1, Path(f.path).name, symbol, color)
                _text(self.old_table, i, 2, str(Path(f.path).parent))
                _text(self.old_table, i, 3, datetime.fromtimestamp(f.modified).strftime("%b %d, %Y"))
                _text(self.old_table, i, 4, human_size(f.size))
                _text(self.old_table, i, 5, kind)
                self.old_table.setRowHeight(i, 41)
            if rows:
                selected = next((i for i, f in enumerate(rows) if str(f.path) == current_path), 0)
                self.old_table.selectRow(selected)
        self.old_notice.setText(notice)
        self.old_notice.setVisible(bool(notice))
        self._old_selection_count()
        self._old_details()

    def _select_old_visible(self, selected):
        with QSignalBlocker(self.old_table):
            for i in range(self.old_table.rowCount()):
                self.old_table.item(i, 0).setCheckState(Qt.Checked if selected else Qt.Unchecked)
        self._old_selection_count()

    def _selected_old(self):
        return [self._shown_old_files[i] for i in _checked(self.old_table) if i < len(self._shown_old_files)]

    def _old_selection_count(self, *_):
        selected = self._selected_old()
        self.old_selection.setText(f"{len(selected)} selected ({human_size(sum(f.size for f in selected))})")
        with QSignalBlocker(self.old_select_all):
            self.old_select_all.setChecked(bool(self.old_table.rowCount()) and len(selected) == self.old_table.rowCount())
        self.old_delete.setEnabled(bool(selected) and len(selected) <= 200 and
                                   not any(is_protected_path(Path(f.path), self.settings.get("never_touch", []))
                                           or looks_like_screenshot(Path(f.path)) for f in selected))
        self.old_delete.setToolTip("Images need individual preview in Captures or Graveyard." if any(
            looks_like_screenshot(Path(f.path)) for f in selected) else
            "Review selected files before moving them to Windows Recycle Bin")

    def _old_details(self):
        contents = self.old_details.content
        destroy_layout(contents)
        index = self.old_table.currentRow()
        if not 0 <= index < len(self._shown_old_files):
            contents.addWidget(label("Select a file", "detailTitle"))
            contents.addWidget(label("Review its location, last modified date and protection before deciding what to keep.", "subtle", wrap=True))
            contents.addStretch()
            return
        f = self._shown_old_files[index]
        protected = is_protected_path(Path(f.path), self.settings.get("never_touch", []))
        contents.addWidget(label(Path(f.path).name, "detailTitle", wrap=True))
        contents.addWidget(label("◇  Protected" if protected else "Review required", "successText" if protected else "warning"))
        # Ownership is deliberately not inferred from filenames or decorative art.
        contents.addWidget(CoverArt(Path(f.path).name, height=83))
        detail_section(contents, "Details")
        for symbol, title, value in (
            ("game", "Related Game", "Unverified"), ("folder", "Location", str(f.path)),
            ("clock", "Last Modified", datetime.fromtimestamp(f.modified).strftime("%b %d, %Y")),
            ("storage", "Size", human_size(f.size)), ("file", "Type", file_kind(f.path)),
        ):
            detail_line(contents, symbol, title, value)
        detail_section(contents, "Why It's Flagged")
        age = max(0, int((time.time() - f.modified) / 86400))
        contents.addWidget(label(f"Last modified {age:,} days ago. This does not establish when the file was last used.", "subtle", wrap=True))
        contents.addWidget(label("Protected content cannot be recycled here." if protected else
                                 "Individual file review, confirmation and Windows safety checks are still required.", "warning", wrap=True))
        detail_section(contents, "Quick Actions")
        contents.addWidget(tool("Open Containing Folder", "folder", lambda: self._open_folder(str(Path(f.path).parent))))
        contents.addWidget(tool("Review in Graveyard", "grave", lambda: self.navigate("Graveyard")))
        if looks_like_screenshot(Path(f.path)):
            contents.addWidget(tool("Preview This Screenshot", "camera", lambda: self._preview_capture(f)))
        contents.addStretch()

    def _protect_old_selected(self):
        if self.scanning or self.cleaning:
            self.info("Game Grave is busy", "Finish the current operation before changing protection.")
            return
        selected = self._selected_old()
        if not selected:
            self.info("Choose files", "Check the individual files you want to protect.")
            return
        from graveyard_protection import set_item_protection
        rules = list(self.settings.get("never_touch", []))
        try:
            for f in selected:
                if not is_protected_path(Path(f.path), rules):
                    rules = set_item_protection(rules, f.path, protect=True)
            updated = dict(self.settings, never_touch=rules)
            save_settings(updated)
        except (OSError, ValueError) as exc:
            self.error("Protection not saved", str(exc))
            return
        self.settings = updated
        refresh_graveyard(self.inventory, self.settings)
        self._old_selection_count()
        self._old_details()
        self.status.setText(f"Protected {len(selected)} selected file(s). Manage personal rules in Settings.")

    def _recycle_old_selected(self):
        if self.scanning or self.cleaning:
            self.info("Game Grave is busy", "Finish the current operation first.")
            return
        selected = tuple(self._selected_old())
        if not selected or len(selected) > 200:
            self.info("Choose files", "Check between 1 and 200 individual files.")
            return
        if any(is_protected_path(Path(f.path), self.settings.get("never_touch", [])) for f in selected):
            self.error("Protected items selected", "Old Files cannot override protection. Review your personal Never Touch rules in Settings.")
            return
        if any(looks_like_screenshot(Path(f.path)) for f in selected):
            self.error("Preview required", "Images must be individually previewed and approved in Captures or Graveyard. They cannot be included in an Old Files batch.")
            return
        root, days = self._old_root, self._old_days
        if _path_key(root) != _path_key(str(self.settings.get("scan_folder", ""))):
            self.error("Scan folder changed", "Scan the selected folder again before reviewing files.")
            return
        if not self.confirm("Move selected Old Files to Recycle Bin?",
                            f"Reviewing {len(selected)} specific files ({human_size(sum(f.size for f in selected))}) in:\n{root}\n\n"
                            "Every identity, age, folder scope and Windows recovery check runs again. "
                            "No permanent deletion; files in Recycle Bin may still occupy disk space.", destructive=True):
            return
        self.cleaning = True
        rules = tuple(self.settings.get("never_touch", []))
        session = "crimson-old-" + uuid.uuid4().hex[:10]

        def complete(outcome):
            self.cleaning = False
            self.status.setText(f"{outcome['completed']} old file(s) moved to Recycle Bin. They may still occupy disk space.")
            self._remove_missing_inventory()
            refresh_graveyard(self.inventory, self.settings)
            self.navigate("Old Files")
            self.info("Old Files review completed", f"{outcome['completed']} moved to Recycle Bin, {len(outcome['skipped'])} skipped." +
                      ("\n" + "\n".join(outcome["skipped"][:8]) if outcome["skipped"] else ""))
        self.job(lambda _progress: recycle_old_files(selected, rules, session,
                 review_root=root, min_age_days=days), complete, error_title="Old Files cleanup blocked")
