"""Ready Room and AI Assistant pages in the approved cinematic Game Grave shell.

No invented patches, file names, metrics, or deletion/repair authority.
The independent local AI engine remains optional and defaults to OFF.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QGridLayout, QTableWidget,
    QTableWidgetItem, QWidget, QLineEdit, QFrame, QLabel,
)

from core import age_text
from gg_desktop.models import readable_bytes
from gg_desktop.cinematic_art import CinematicToolArtwork
from gg_desktop.library_sort import (
    SORT_OPTIONS, DEFAULT_SORT, HEADER_OPTIONS,
    sort_game_records, filter_game_records, next_header_sort,
)
from gg_desktop.library_graphics import LauncherMixGraphic
from gg_desktop.tab_panels import game_gallery
from gg_desktop.widgets import (
    ActionCard, MetricCard, button, label, panel, row, section_title,
)


def _text(table: QTableWidget, r: int, c: int, value) -> None:
    cell = QTableWidgetItem(str(value))
    cell.setToolTip(str(value))
    table.setItem(r, c, cell)


class LockedPagesMixin:
    """Uses the existing app's navigation and backend; contains no scanner."""

    def ready_room_page(self):
        """Actual sortable lineup plus local art and verified notices.

        Clicking any of the four table headings reorders the underlying game
        records numerically where appropriate. The selected game always
        resolves from the *currently displayed* rows, not the old default
        order. Missing sizes/playtime sort last in both directions.
        """
        page = self._new(
            "Ready Room",
            "Your gaming lineup, official update status and quick access to "
            "the tools protecting your installations.")
        if self._not_scanned(page):
            return
        metrics = QWidget()
        m = row(spacing=9)
        metrics.setLayout(m)
        for name, value, detail, tone in (
            ("GAMES FOUND", len(self.inventory.games),
             "Verified launcher installations", "cyan"),
            ("MOD LOCATIONS", len(self.inventory.mods),
             "Discovered folders, not mod count", "amber"),
            ("PROTECTED SAVES", len(self.inventory.saves),
             "Candidate locations, no deletion", "green"),
            ("GRAVEYARD", len(self.inventory.graveyard),
             "Reviewable candidates and safeguards", "text"),
        ):
            m.addWidget(MetricCard(name, str(value), detail, tone=tone))
        page.content.addWidget(metrics)
        page.content.addWidget(LauncherMixGraphic(self.inventory.games))

        workspace = QWidget()
        body = row(spacing=10)
        workspace.setLayout(body)
        left, col = panel(padding=12, spacing=9)
        left.setObjectName("readyRoomLineup")
        col.addWidget(section_title(
            "YOUR LINEUP  /  ALL LAUNCHERS",
            "Click column headings or use the sorting controls"))

        filters = QWidget()
        controls = row(spacing=7)
        filters.setLayout(controls)
        search = QLineEdit()
        search.setObjectName("readyRoomSearch")
        search.setPlaceholderText("Search game, launcher or install path…")
        search.setAccessibleName("Search Ready Room games")
        controls.addWidget(search, 3)
        launcher_filter = QComboBox()
        launcher_filter.setObjectName("readyRoomLauncherFilter")
        launcher_filter.setAccessibleName("Ready Room launcher filter")
        launcher_filter.addItems(["All launchers"] + sorted({
            g.launcher for g in self.inventory.games}))
        controls.addWidget(launcher_filter, 2)
        sort_choice = QComboBox()
        sort_choice.setObjectName("readyRoomSort")
        sort_choice.setAccessibleName("Ready Room game sort order")
        sort_choice.addItems(list(SORT_OPTIONS))
        prior = getattr(self, "_ready_room_sort", DEFAULT_SORT)
        sort_choice.setCurrentText(
            prior if prior in SORT_OPTIONS else DEFAULT_SORT)
        controls.addWidget(sort_choice, 2)
        col.addWidget(filters)

        table = QTableWidget(0, 4)
        table.setObjectName("readyRoomTable")
        table.setAccessibleName("Ready Room sortable game lineup")
        table.setHorizontalHeaderLabels([
            "GAME", "LAUNCHER", "LAST PLAYED", "SIZE"])
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSortingEnabled(False)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(42)
        table.setColumnWidth(0, 230)
        table.setColumnWidth(1, 125)
        table.setColumnWidth(2, 120)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionsClickable(True)
        table.horizontalHeader().setSortIndicatorShown(True)
        table.setMinimumHeight(295)
        shown = []

        count_line = label("", "caption", wrap=True)
        count_line.setObjectName("readyRoomSortStatus")

        def inspect_game(game):
            self._pending_game_query = game.name
            self.navigate("Games")

        def selected_game():
            indices = table.selectionModel().selectedRows()
            if not indices:
                return None
            pos = indices[0].row()
            return shown[pos] if 0 <= pos < len(shown) else None

        def refill(*_):
            nonlocal shown, gallery
            selected = selected_game()
            key = selected.key if selected else None
            candidates = filter_game_records(
                self.inventory.games, search.text(),
                launcher_filter.currentText())
            sort_name = sort_choice.currentText()
            self._ready_room_sort = sort_name
            all_rows = sort_game_records(candidates, sort_name)
            shown = all_rows[:500]
            table.blockSignals(True)
            table.clearContents()
            table.setRowCount(len(shown))
            select_index = -1
            for i, game in enumerate(shown):
                values = (
                    game.name, game.launcher,
                    age_text(game.last_played_at)
                    if game.last_played_at is not None else "Unknown",
                    readable_bytes(game.size_bytes))
                for j, value in enumerate(values):
                    _text(table, i, j, value)
                table.item(i, 0).setData(Qt.UserRole, game.key)
                table.item(i, 2).setToolTip(
                    "Source: " + game.last_played_source)
                table.item(i, 3).setToolTip(
                    "Reported size: " + game.size_source)
                if game.key == key:
                    select_index = i
            if shown:
                table.selectRow(select_index if select_index >= 0 else 0)
            table.blockSignals(False)
            count_line.setText(
                f"{len(shown)} of {len(all_rows)} matching installations"
                + (" • Unknown measurements always sort last." if shown else
                   " • No games match those filters."))
            for column, modes in HEADER_OPTIONS.items():
                if sort_name in modes:
                    table.horizontalHeader().setSortIndicator(
                        column, Qt.AscendingOrder
                        if sort_name == modes[0] else Qt.DescendingOrder)
                    break
        def header_clicked(index):
            if index in HEADER_OPTIONS:
                sort_choice.setCurrentText(
                    next_header_sort(index, sort_choice.currentText()))
        search.textChanged.connect(refill)
        launcher_filter.currentTextChanged.connect(refill)
        sort_choice.currentTextChanged.connect(refill)
        table.horizontalHeader().sectionClicked.connect(header_clicked)
        table.cellDoubleClicked.connect(
            lambda _r, _c: inspect_game(selected_game())
            if selected_game() is not None else None)
        col.addWidget(table)
        col.addWidget(count_line)

        actions = QWidget()
        row_actions = row(spacing=8)
        actions.setLayout(row_actions)
        def inspect():
            game = selected_game()
            if game is None:
                self.info("Choose a game", "Select a verified game first.")
                return
            inspect_game(game)
        row_actions.addWidget(button(
            "Inspect selected game", inspect, kind="primary"))
        row_actions.addWidget(button(
            "Game DNA", lambda: self.navigate("Game DNA")))
        row_actions.addStretch()
        col.addWidget(actions)

        # Portrait artwork is a genuine navigational view of the very same
        # installation records; screenshots never use imaginary game names.
        gallery = game_gallery(
            [], inspect_game, limit=8)
        gallery.setObjectName("readyRoomCoverStrip")
        col.addWidget(gallery)
        body.addWidget(left, 7)

        patch, patch_col = panel(padding=12, spacing=9)
        patch.setObjectName("ggAccentPanel")
        patch.setProperty("accent", "cyan")
        patch_col.addWidget(section_title(
            "PATCH WATCH", "Official update source status"))
        picture = CinematicToolArtwork("scanner")
        picture.setMinimumHeight(105)
        picture.setMaximumHeight(105)
        patch_col.addWidget(picture)
        status = label("OFFICIAL FEEDS: NOT CONNECTED", "eyebrow")
        status.setStyleSheet(
            "color:#F1BE77;background:transparent;"
            "font-size:12px;font-weight:800;")
        patch_col.addWidget(status)
        patch_col.addWidget(label(
            "Official developer patch and maintenance feeds are not yet "
            "connected. No patch versions, notices or compatibility warnings "
            "are fabricated.", "subtle", wrap=True))
        patch_col.addWidget(section_title("ATTENTION", "Local scan evidence"))
        if self.inventory.warnings:
            for warning in self.inventory.warnings[:5]:
                patch_col.addWidget(label(
                    "⚠ " + str(warning), "warning", wrap=True))
        else:
            patch_col.addWidget(label(
                "No scan coverage warnings detected. This is not a "
                "mod compatibility certification.", "subtle", wrap=True))
        patch_col.addWidget(button(
            "Open Mod Radar", lambda: self.navigate("Mods")))
        patch_col.addWidget(button(
            "Review Graveyard", lambda: self.navigate("Graveyard")))
        patch_col.addWidget(button(
            "Browse Game DNA", lambda: self.navigate("Game DNA")))
        patch_col.addStretch()
        body.addWidget(patch, 3)
        page.content.addWidget(workspace)
        refill()

        shortcuts, shortcut_col = panel(padding=12, spacing=9)
        shortcut_col.addWidget(section_title(
            "QUICK ACCESS", "Every control opens a working Game Grave feature"))
        controls = QWidget()
        tiles = QGridLayout(controls)
        tiles.setSpacing(9)
        for i, (title, description, route) in enumerate((
            ("Mod Radar", "Verified installed mod locations", "Mods"),
            ("Save Vault", "Preserve save folders", "More Tools"),
            ("Game DNA", "Visualize linked game data", "Game DNA"),
            ("Captures", "Screenshots and game recordings", "Captures"),
            ("Graveyard", "Review and protect leftovers", "Graveyard"),
            ("Undo Center", "Verify recovery history", "Undo Center"),
        )):
            tiles.addWidget(ActionCard(
                "✧", title, description,
                lambda destination=route: self.navigate(destination)),
                i//3, i%3)
        shortcut_col.addWidget(controls)
        page.content.addWidget(shortcuts)

    def ai_assistant_page(self):
        """Full-page hub that keeps the existing secure dockable AI companion."""
        page = self._new(
            "AI Assistant",
            "Private, optional, local help for games, mods and cleanup decisions.",
        )
        from ai_bundle import is_ai_installed
        enabled = self.settings.get("ai_assistant_enabled") is True
        installed = is_ai_installed()
        stats = QWidget()
        cols = row(spacing=11)
        stats.setLayout(cols)
        for name, value, detail, tone in (
            ("AI ENGINE", "Enabled" if enabled else "Off",
             "Optional; disabled by default", "green" if enabled else "amber"),
            ("LOCAL MODEL", "Installed" if installed else "Not installed",
             "One-time opt-in setup from Settings", "cyan"),
            ("INVENTORY", str(len(self.inventory.games)) if
             self.inventory.scanned_at else "Not scanned",
             "Only anonymous aggregate counts shared", "text"),
        ):
            cols.addWidget(MetricCard(name, value, detail, tone=tone))
        page.content.addWidget(stats)

        hub = QWidget()
        layout = row(spacing=14)
        hub.setLayout(layout)
        workflows, modes = panel()
        modes.addWidget(section_title("ASSISTANT MODES", "Local explanations"))
        for name, desc, route in (
            ("Chat", "Ask about Game Grave and troubleshooting", "AI Assistant"),
            ("Analyze", "Review actual scanned storage in Game DNA", "Game DNA"),
            ("Troubleshoot", "Inspect mod changes and managers", "Mods"),
            ("Cleanup advisor", "See real review candidates", "Graveyard"),
            ("Backups", "Protect saves and prepare recovery", "More Tools"),
        ):
            callback = self.open_ai_companion if route == "AI Assistant" else (
                lambda route=route: self.navigate(route))
            modes.addWidget(ActionCard("✧", name, desc, callback))
        layout.addWidget(workflows, 3)

        center, chat = panel()
        chat.addWidget(section_title("GAME GRAVE AI", "Private local companion"))
        chat.addWidget(label(
            "Ask questions while viewing any page. The assistant can be docked, "
            "resized, or popped out. It explains real findings but has no access "
            "to file contents and cannot delete, unprotect, or repair anything.",
            "subtle", wrap=True))
        if enabled and installed:
            chat.addWidget(button("Open local AI companion",
                                  self.open_ai_companion, kind="primary"))
            chat.addWidget(label("Ready for on-demand questions. No automatic scans or prompts.",
                                 "successText", wrap=True))
        else:
            chat.addWidget(label(
                "The local assistant is currently disabled or not installed. "
                "Core Game Grave features continue to work normally.",
                "warning", wrap=True))
            def setup():
                self._settings_category_index = 4
                self.navigate("Settings")
            chat.addWidget(button("Configure optional local AI in Settings",
                                  setup, kind="primary"))
        chat.addWidget(section_title("BUILT-IN HELP"))
        for title, action in (
            ("Why is a Graveyard item protected?", lambda: self.navigate("Graveyard")),
            ("Which mod profiles were detected?", lambda: self.navigate("Mods")),
            ("Where does a game's data live?", lambda: self.navigate("Game DNA")),
        ):
            chat.addWidget(button(title, action))
        chat.addStretch()
        layout.addWidget(center, 5)

        context, right = panel()
        right.addWidget(section_title("ACTIVE CONTEXT"))
        right.addWidget(label(
            f"{len(self.inventory.games)} games  •  {len(self.inventory.mods)} mod locations"
            if self.inventory.scanned_at else "No inventory scan yet", "sectionTitle", wrap=True))
        right.addWidget(label(
            "Only aggregate counts are passed automatically to local AI. "
            "The assistant never receives your file paths, game names, "
            "screenshots, or save contents.",
            "subtle", wrap=True))
        right.addWidget(section_title("INTELLIGENCE TOOLS"))
        for title, route in (
            ("Mod Radar", "Mods"), ("Game DNA", "Game DNA"),
            ("Save Vault", "More Tools"), ("Undo Center", "Undo Center"),
        ):
            right.addWidget(button(title + "  ›", lambda route=route: self.navigate(route)))
        right.addStretch()
        layout.addWidget(context, 3)
        page.content.addWidget(hub)

        quick, prompt_col = panel()
        prompt_col.addWidget(section_title("QUICK WORKFLOWS", "Read-only until you approve actions"))
        actions = QWidget()
        grid = QGridLayout(actions)
        grid.setSpacing(10)
        for i, (title, detail, route) in enumerate((
            ("Clean my game", "Inspect candidate leftovers", "Graveyard"),
            ("Check my mods", "Review mod-manager evidence", "Mods"),
            ("Improve storage", "Analyze file locations", "Other Storage"),
            ("After a patch", "Check available mod evidence", "Game DNA"),
            ("Backup my setup", "Save Vault / Resurrection Kit", "More Tools"),
            ("Recover changes", "Review recoverable actions", "Undo Center"),
        )):
            grid.addWidget(
                ActionCard("⌁", title, detail, lambda route=route: self.navigate(route)),
                i // 3, i % 3)
        prompt_col.addWidget(actions)
        page.content.addWidget(quick)
