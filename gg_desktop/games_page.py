"""Games-only version of the locked photo layout and its live controls.

Shared builders, widgets, artwork services and other tabs remain unchanged.
"""
from collections import Counter
from PySide6.QtCore import Qt, QSignalBlocker, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QLabel, QListWidgetItem
from core import age_text, save_settings
from gg_desktop import soulbind_core as sb
from gg_desktop.models import readable_bytes
from gg_desktop.artwork import game_app_id
from gg_desktop.games import artwork_roots
from gg_desktop.games_sources import LAUNCHERS, launcher_bucket
from gg_desktop.games_data import launch_uri
from gg_desktop.games_controls import GamesActions, GamesArtwork, GamesCoverDelegate
from gg_desktop.header_banner import HeaderBannerArtwork
from gg_desktop.photo_integration import ResponsiveInspector
from gg_desktop.reference_library import _search, _combo, _view_switch, _widget, _split, _detail_scroll, destroy_layout
from gg_desktop.reference_widgets import CARD_ROLE, CoverArt, CoverGrid, DetailPanel, MetricStrip, TabStrip, detail_line, detail_section, icon, tool, tile_action
from gg_desktop.widgets import label, panel, row


class GamesScreens:
    def games_page(self):
        page = self._reference_page("Games", "Your complete game library. All launchers, one place. Manage, clean, and\nkeep your games running at their best.", "games")
        page.banner_artwork = HeaderBannerArtwork(self, page, page.content.itemAt(0).widget(), route="Games")
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
        from gg_desktop import games_fit
        games_fit.install(self.game_metrics, self.game_tabs)   # whole words at 1280 instead of cut ones
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
        preferred = getattr(self, "_pending_launcher_filter", None)
        if preferred:
            idx = self.game_filter.findText(preferred)
            self.game_filter.setCurrentIndex(max(0, idx))
        self._pending_launcher_filter = None
        def toggle_filters():
            self.game_filter_box.setVisible(not self.game_filter_box.isVisible())
        searchbar.addWidget(tool("Filters", "filter", toggle_filters,
                                 tip="Launcher and size filters. The tabs above pick installed, favourites and more."))
        self.game_library_options = tool("Library options", "more", lambda: page.games.library_options(),
                                         tip="Connect game libraries (Epic, GOG, Xbox…), refresh library data and artwork")
        self.game_library_options.setAccessibleName("Game library options")
        searchbar.addWidget(self.game_library_options)
        contents.addWidget(_widget(searchbar))
        from PySide6.QtWidgets import QCheckBox
        filters = row(spacing=10)
        filters.addWidget(label("Launcher:", "caption"))
        self.game_filter.setVisible(True)
        filters.addWidget(self.game_filter)
        self.game_large = QCheckBox("Only large games (100 GB or more)")
        self.game_large.toggled.connect(lambda on: (setattr(self, "_game_chip", "Large" if on else "All Games"),
                                                    self._fill_games()))
        filters.addWidget(self.game_large)
        filters.addStretch(1)
        self.game_filter_box = _widget(filters)
        self.game_filter_box.setVisible(bool(preferred))
        contents.addWidget(self.game_filter_box)
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
        chip_row = _widget(library_options)
        chip_row.hide()          # one row of tabs: the tabs carry the counts, size is in Filters
        contents.addWidget(chip_row)
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
        QShortcut(QKeySequence("Ctrl+O"), self.game_grid, activated=lambda: GamesScreens._open_selected_install(self)).setContext(Qt.WidgetShortcut)
        page.photo_inspector = ResponsiveInspector(page, self.game_details.parentWidget().parentWidget())
        QTimer.singleShot(0, page.games.refresh_sources)

    def _set_game_tab(self, name):
        self._game_tab = name.split(" (")[0]
        self._game_chip = "Large" if getattr(self, "game_large", None) is not None and self.game_large.isChecked() \
            else "All Games"
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
        soulbind_profile = sb.load_profile()
        with QSignalBlocker(self.game_grid):
            self.game_grid.clear()
            for g in rows:
                item = QListWidgetItem(g.name)
                item.setToolTip(g.name + "\n" + g.launcher + " · " + g.status)
                item.setData(CARD_ROLE, {"name": g.name, "size": readable_bytes(g.size_bytes),
                                        "source": g.launcher, "steam_app_id": game_app_id(g), "favorite": self.page.games.is_favorite(g),
                                        "status_icon": "check" if g.status.startswith("Installed") else "shield"})
                badge = sb.badge_for(g.name, soulbind_profile)
                if badge is not None:
                    item.setData(CARD_ROLE, {**item.data(CARD_ROLE), "soulbind": (badge.text, badge.tone)})
                    item.setToolTip(item.toolTip() + "\nSoulbind: " + badge.text + ". " + badge.detail)
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
        from gg_desktop import next_step
        first = (not rows and not self.inventory.scanned_at and not self.page.games.records
                 and "Not Installed" not in active and "Updates" not in active)
        next_step.show(self.game_empty, "Scan PC (F5)" if first and not self.scanning else "", self.start_scan,
                       "Finds installed games, mods, saves and captures. Reads only; nothing is changed.")
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
        for item in self.game_details.findChildren(QLabel):
            if item.objectName() == "detailKey":
                item.setFixedWidth(104)        # "Tracked Playtime" and "Install Location" in full
        GamesScreens._add_place_buttons(self, contents, game)
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
            quick = tile_action("Verify" if action == "validate" else "DLC", symbol,
                                lambda _=False, action=action: self._steam_game_action(game, action))
            quick.setAccessibleName(caption.rstrip("…"))
            quick.setProperty("gameNativeAction", action)
            quick.setEnabled(control.is_installed(game) or action == "details" and control.fact(game).get("owned", False))
            quick.setToolTip(("Verify files: opens " if action == "validate" else "Manage DLC: opens ") + game.launcher
                             + ("'s file check for this game. " if action == "validate" else "'s page for this game's add-ons. ")
                             + game.launcher + " does the work; Game Grave changes nothing.")
            actions.addWidget(quick)
        uninstall = tile_action("Uninstall", "trash", lambda: self._steam_uninstall(game))
        uninstall.setAccessibleName("Uninstall" if game.launcher == "Steam" else "Uninstall in launcher")
        uninstall.setProperty("gameNativeAction", "uninstall")
        uninstall.setEnabled(control.is_installed(game) and "open_folder" in game.capabilities)
        uninstall.setToolTip("Opens " + game.launcher + "'s own uninstall for this game. Nothing is removed until you confirm there.")
        actions.addWidget(uninstall)
        contents.addWidget(_widget(actions))
        contents.addStretch()

    def _one_line_path(self, row_widget):
        """The install path on one line, shortened in the middle (drive and folder name both show), full path on hover."""
        from PySide6.QtGui import QFontMetrics
        from PySide6.QtWidgets import QSizePolicy

        class MiddleElided(QLabel):
            def __init__(self, full):
                super().__init__(full)
                self.full = full
                self.setObjectName("detailValue")
                self.setToolTip(full)
                self.setMinimumWidth(0)
                self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
                self.setAccessibleName("Install location: " + full)

            def resizeEvent(self, event):
                super().resizeEvent(event)
                self.setText(QFontMetrics(self.font()).elidedText(self.full, Qt.ElideMiddle, max(20, self.width())))

        for value in row_widget.findChildren(QLabel):
            if value.objectName() == "detailValue" and value.wordWrap():
                lay = row_widget.layout()
                index = lay.indexOf(value)
                if index < 0:
                    return
                short = MiddleElided(value.toolTip() or value.text())
                value.hide()
                lay.insertWidget(index, short, 1)
                self.game_install_path = short
                return

    def _add_place_buttons(self, contents, game):
        """Open buttons right where the paths are: on the Install Location line, and a Saves line when the save scanner
        labeled folders with this game."""
        from PySide6.QtWidgets import QPushButton
        from gg_desktop import games_places as places
        install = places.install_place(game)
        for n in range(contents.count()):
            row_widget = contents.itemAt(n).widget()
            keys = [l.text() for l in row_widget.findChildren(QLabel) if l.objectName() == "detailKey"] if row_widget else []
            if keys == ["Install Location"]:
                GamesScreens._one_line_path(self, row_widget)
            if keys == ["Install Location"] and install is not None:
                opener = QPushButton("Open")
                opener.setObjectName("placeOpen")
                opener.setIcon(icon("folder", "#e8eef5", 14))
                opener.setFixedHeight(24)
                opener.setCursor(Qt.PointingHandCursor)
                opener.setToolTip("Open the install folder in File Explorer:\n" + install.path)
                opener.setAccessibleName("Open install folder")
                opener.setStyleSheet("QPushButton#placeOpen{padding:0 8px;font-size:11px;border-radius:6px;"
                                     "background:#1a2633;border:1px solid #2e4154;color:#e8eef5;}"
                                     "QPushButton#placeOpen:hover{border-color:#ff3b57;}")
                opener.clicked.connect(lambda _=False, p=install.path: self._open_folder(p))
                row_widget.layout().addWidget(opener)
                self.game_open_install = opener
                at = n + 1
                saves = places.save_places(game, getattr(self.inventory, "saves", []))
                if saves:
                    detail_line_at = contents.count()
                    detail_line(contents, "storage", "Saves", ("1 folder" if len(saves) == 1 else f"{len(saves)} folders"))
                    line = contents.takeAt(detail_line_at).widget()
                    contents.insertWidget(at, line)
                    save_open = QPushButton("Open")
                    save_open.setObjectName("placeOpen")
                    save_open.setIcon(icon("folder", "#e8eef5", 14))
                    save_open.setFixedHeight(24)
                    save_open.setCursor(Qt.PointingHandCursor)
                    save_open.setStyleSheet(opener.styleSheet())
                    save_open.setAccessibleName("Open save folder")
                    save_open.setToolTip("Open " + ("the save folder" if len(saves) == 1 else "a save folder") +
                                         " the save scanner labeled with this game:\n" + "\n".join(p.path for p in saves))
                    save_open.clicked.connect(lambda _=False, g=game: GamesScreens._open_saves(self, g, save_open))
                    for key in line.findChildren(QLabel):
                        if key.objectName() == "detailKey":
                            key.setFixedWidth(104)
                    line.layout().addWidget(save_open)
                    self.game_open_saves = save_open
                break

    def _open_saves(self, game, anchor=None):
        from PySide6.QtWidgets import QMenu
        from gg_desktop import games_places as places
        saves = places.save_places(game, getattr(self.inventory, "saves", []))
        if len(saves) == 1:
            self._open_folder(saves[0].path)
            return
        menu = QMenu(self)
        menu.setStyleSheet("QMenu {background:#0b1118;color:#e5e8ee;border:1px solid #49535e;} QMenu::item:selected {background:#7d1529;}")
        for place in saves:
            menu.addAction(places.short(place.path, 70), lambda p=place.path: self._open_folder(p))
        menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()) if anchor is not None else self.cursor().pos())
        menu.deleteLater()

    def _open_selected_install(self):
        game = self._current_game()
        from gg_desktop import games_places as places
        place = places.install_place(game) if game is not None else None
        if place is not None:
            self._open_folder(place.path)

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

