"""Games-only version of the locked photo layout and its live controls.

Shared builders, widgets, artwork services and other tabs remain unchanged.
"""
from collections import Counter
from PySide6.QtCore import Qt, QSignalBlocker, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QLabel, QListWidgetItem
from core import age_text, save_settings
from gg_desktop.models import readable_bytes
from gg_desktop.artwork import game_app_id
from gg_desktop.games import artwork_roots
from gg_desktop.games_sources import LAUNCHERS, launcher_bucket
from gg_desktop.games_data import launch_uri
from gg_desktop.games_controls import GamesActions, GamesArtwork, GamesCoverDelegate
from gg_desktop.games_banner import GamesBannerArtwork
from gg_desktop.photo_integration import ResponsiveInspector
from gg_desktop.reference_library import _search, _combo, _view_switch, _widget, _split, _detail_scroll, destroy_layout
from gg_desktop.reference_widgets import CARD_ROLE, CoverArt, CoverGrid, DetailPanel, MetricStrip, TabStrip, detail_line, detail_section, icon, tool, tile_action
from gg_desktop.widgets import label, panel, row


class GamesScreens:
    def games_page(self):
        page = self._reference_page("Games", "Your complete game library. All launchers, one place. Manage, clean, and\nkeep your games running at their best.", "games")
        page.banner_artwork = GamesBannerArtwork(self, page, page.content.itemAt(0).widget())
        page.games = GamesActions(self, page)
        page.game_artwork = GamesArtwork(self, page)
        page.game_artwork.set_library(page.games.records, artwork_roots(self.inventory, self.settings))
        games = page.games.records
        counts = Counter(launcher_bucket(g.launcher) for g in games)
        metrics = [("game", len(games), "Total Games", "#ff183b")]
        metrics += [(symbol, counts[bucket], bucket, color) for bucket, symbol, color in LAUNCHERS]
        self.game_metrics = MetricStrip(metrics, compact=True)
        self.page.games.bind_metrics(self.game_metrics)
        page.content.addWidget(self.game_metrics)
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
        self.game_grid.delegate = GamesCoverDelegate(self.game_grid)
        self.game_grid.setItemDelegate(self.game_grid.delegate)
        self.game_grid.set_artwork(self.page.game_artwork)
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
        library_options = row(spacing=4)
        library_options.addWidget(self.game_chips, 1)
        self.game_library_options = tool("", "more", page.games.library_options, tip="Library options and account connections")
        self.game_library_options.setAccessibleName("Game library options")
        self.game_library_options.setFixedSize(26, 28)
        library_options.addWidget(self.game_library_options)
        contents.addWidget(_widget(library_options))
        self.game_empty = label("", "emptyState", wrap=True)
        contents.addWidget(self.game_empty)
        contents.addWidget(self.game_grid, 1)
        self.game_count = label("", "caption")
        contents.addWidget(self.game_count)
        art_controls = row(spacing=6)
        self.game_artwork_status = label("Artwork is available for every launcher. Game options can download or choose a cover.", "caption", wrap=True)
        art_controls.addWidget(self.game_artwork_status, 1)
        art_controls.addWidget(tool("Reload Artwork", "refresh", self._reload_game_artwork))
        contents.addWidget(_widget(art_controls))
        self.game_details = DetailPanel()
        self.game_details_col = self.game_details.content
        page.content.addWidget(_split(library, _detail_scroll(self.game_details), [740, 282]), 1)
        self._game_tab = "Library"
        self._game_chip = "All Games"
        self.game_search.textChanged.connect(self._fill_games)
        self.game_filter.currentTextChanged.connect(page.games.launcher_changed)
        self.game_sort.currentTextChanged.connect(self._fill_games)
        self.game_tabs.changed.connect(self._set_game_tab)
        self.game_chips.changed.connect(self._set_game_chip)
        self.game_grid.currentRowChanged.connect(self._game_details)
        self.game_grid.itemDoubleClicked.connect(lambda _: self._launch_selected_game())
        self.game_grid.favoriteRequested.connect(lambda i: self._toggle_favorite(self._shown_games[i]))
        self._fill_games()
        self.game_table = self.game_grid
        self.game_count.hide()
        self.game_artwork_status.parentWidget().hide()
        self.game_grid.setContextMenuPolicy(Qt.CustomContextMenu)
        self.game_grid.customContextMenuRequested.connect(page.games.context_menu)
        QShortcut(QKeySequence("Shift+F10"), page, activated=page.games.keyboard_options)
        QShortcut(QKeySequence("Return"), self.game_grid, activated=self._launch_selected_game).setContext(Qt.WidgetShortcut)
        QShortcut(QKeySequence("Enter"), self.game_grid, activated=self._launch_selected_game).setContext(Qt.WidgetShortcut)
        page.photo_inspector = ResponsiveInspector(page, self.game_details.parentWidget().parentWidget())
        QTimer.singleShot(0, page.games.refresh_sources)

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
        rows = [g for g in self.page.games.records
                if (launcher == "All launchers" or self.page.games.bucket is not None or g.launcher == launcher)
                and (not self.page.games.bucket or launcher_bucket(g.launcher) == self.page.games.bucket)
                and all(word in (g.name + " " + g.launcher + " " + g.install_path).casefold() for word in query.split())
                and ("Favorites" not in active or self.page.games.is_favorite(g))
                and ("Installed" not in active or self.page.games.is_installed(g))
                and ("Not Installed" not in active or self.page.games.fact(g).get("owned") and not self.page.games.is_installed(g))
                and ("Updates" not in active or self.page.games.fact(g).get("update_available") is True)
                and ("Recently Played" not in active or self.page.games.last_played(g) is not None)
                and ("Large" not in active or (g.size_bytes is not None and g.size_bytes >= 100 * 1024 ** 3))]
        sort = self.game_sort.currentText()
        if sort == "Name A to Z":
            rows.sort(key=lambda g: g.name.casefold())
        elif sort == "Launcher":
            rows.sort(key=lambda g: (g.launcher.casefold(), g.name.casefold()))
        elif sort in ("Recently played", "Oldest played"):
            rows.sort(key=lambda g: (self.page.games.last_played(g) is None,
                                     -(self.page.games.last_played(g) or 0) if sort == "Recently played" else self.page.games.last_played(g) or 0,
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
                                        "source": g.launcher, "steam_app_id": game_app_id(g), "favorite": self.page.games.is_favorite(g),
                                        "status_icon": "check" if g.status.startswith("Installed") else "shield"})
                self.game_grid.addItem(item)
            selected = next((i for i, g in enumerate(rows) if current and g.key == current.key), 0)
            if rows:
                self.game_grid.setCurrentRow(selected)
        message = (("No uninstalled games were returned by the connected libraries. Refresh library data to check again." if self.page.games.snapshots else "Connect a library from the … menu to include owned games that are not installed.") if "Not Installed" in active else
                   "No updates are reported by the current sources. Refresh library data from the … menu to check again." if "Updates" in active else
                   "No games match these filters." if self.inventory.scanned_at or self.page.games.records else
                   "Your library starts here. Scan PC (F5), or use the … menu to connect your game libraries.")
        self.game_empty.setText(message if not rows else "")
        self.game_empty.setVisible(not rows)
        self.game_count.setText(f"{len(rows):,} games shown · Local library" if self.inventory.scanned_at else "No scan yet · Nothing has been changed")
        self._game_details()
        self.game_grid.doItemsLayout()
        self._update_game_artwork_status()

    def _reload_game_artwork(self):
        self.page.games.download_artwork(tuple(self._shown_games), missing_only=True)

    def _update_game_artwork_status(self):
        ready = sum((g.key, "cover") in self.page.game_artwork.images for g in self._shown_games)
        self.game_artwork_status.setText(f"Artwork: {ready} cached covers · {len(self._shown_games)} games · all launchers")

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
        contents.addWidget(CoverArt(game.name, height=101, artwork=self.page.game_artwork, app_id=game_app_id(game)))
        heading = row(spacing=4)
        heading.addWidget(label(game.name, "detailTitle", wrap=True), 1)
        favorite = self.page.games.is_favorite(game)
        fav = tool("", "star", lambda: self._toggle_favorite(game), tip="Remove favorite" if favorite else "Add favorite")
        fav.setIcon(icon("star", "#ffcb21" if favorite else "#a1a6ad"))
        fav.setAccessibleName("Remove favorite" if favorite else "Add favorite")
        heading.addWidget(fav)
        contents.addWidget(_widget(heading))
        control = self.page.games
        live = control.values(game)
        status = label(live["status"], "successText" if control.is_installed(game) else "warning", wrap=True)
        status.setProperty("gamesLiveField", "status")
        status.setToolTip(control.source_text(game, "status"))
        status.setTextFormat(Qt.PlainText)
        contents.addWidget(status)
        install = not control.is_installed(game) and control.fact(game).get("owned")
        play = tool("Install" if install else "Play", "download" if install else "play", lambda: self._launch_game(game), kind="primary")
        play.setEnabled(bool(install) or control.is_installed(game) and "open_folder" in game.capabilities)
        play.setToolTip(("Install with " if install else "Launch with ") + game.launcher)
        play_row = row(spacing=6)
        play_row.addWidget(play, 1)
        play_row.addWidget(tool("", "more", lambda: self.page.games.options(game), tip="Game options"))
        contents.addWidget(_widget(play_row))
        for symbol, title, value in (
            ("refresh", "Launcher", game.launcher), ("folder", "Install Location", game.install_path or "Not installed"),
            ("storage", "Install Size", readable_bytes(game.size_bytes)),
            ("clock", "Last Played", live["last_played"]),
            ("clock", "Tracked Playtime" if control.fact(game).get("playtime_source", "").startswith("Tracked") or control.fact(game).get("playtime_seconds") is None else "Total Playtime", live["playtime"]),
            ("sparkles", "Updates", live["updates"]),
        ):
            detail_line(contents, symbol, title, value)
            field = {"Last Played": "last_played", "Total Playtime": "playtime", "Tracked Playtime": "playtime", "Updates": "updates"}.get(title)
            if field:
                row_widget = contents.itemAt(contents.count()-1).widget()
                for item in row_widget.findChildren(QLabel) if row_widget else ():
                    if item.objectName() == "detailValue":
                        item.setProperty("gamesLiveField", field)
                        item.setToolTip(control.source_text(game, field))
        actions = row(spacing=5)
        actions.addWidget(tile_action("Game DNA", "dna", lambda: self.page.games.show_dna(game)))
        actions.addWidget(tile_action("Mods", "mods", lambda: self.navigate("Mods")))
        actions.addWidget(tile_action("Save Vault", "storage", self._create_save_backup))
        contents.addWidget(_widget(actions))
        detail_section(contents, "Quick Actions")
        actions = row(spacing=5)
        folder = tile_action("Open Folder", "folder", lambda: self._open_folder(game.install_path))
        folder.setEnabled(control.is_installed(game) and "open_folder" in game.capabilities)
        actions.addWidget(folder)
        for text, symbol, action in (("Verify Files…", "check", "validate"), ("Manage DLC…", "box", "details")):
            caption = text if game.launcher == "Steam" else ("Verify in launcher…" if action == "validate" else "DLC in launcher…")
            quick = tile_action(caption, symbol, lambda _=False, action=action: self._steam_game_action(game, action))
            quick.setProperty("gameNativeAction", action)
            quick.setEnabled(control.is_installed(game) or action == "details" and control.fact(game).get("owned", False))
            quick.setToolTip("Open this game's " + game.launcher + " controls")
            actions.addWidget(quick)
        uninstall = tile_action("Uninstall…" if game.launcher == "Steam" else "Uninstall in launcher…", "trash", lambda: self._steam_uninstall(game))
        uninstall.setProperty("gameNativeAction", "uninstall")
        uninstall.setEnabled(control.is_installed(game) and "open_folder" in game.capabilities)
        uninstall.setToolTip("Open this game's native uninstall controls")
        actions.addWidget(uninstall)
        contents.addWidget(_widget(actions))
        contents.addStretch()

    def _toggle_favorite(self, game):
        values = set(self.settings.get("desktop_favorites", []))
        if self.page.games.is_favorite(game):
            values.difference_update(self.page.games.favorite_aliases(game))
        else:
            values.add(game.key)
        updated = dict(self.settings, desktop_favorites=sorted(values))
        try:
            save_settings(updated)
        except (OSError, ValueError) as exc:
            self.error("Favorite not saved", str(exc))
            return
        self.settings = updated
        count = sum(self.page.games.is_favorite(g) for g in self.page.games.records)
        for name, control in self.game_chips.buttons.items():
            if name.startswith("Favorites"):
                control.setText(f"Favorites ({count})")
        self._fill_games()

