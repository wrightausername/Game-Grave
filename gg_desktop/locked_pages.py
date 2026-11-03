"""Ready Room and AI Assistant pages in the approved cinematic Game Grave shell.

No invented patches, file names, metrics, or deletion/repair authority.
The independent local AI engine remains optional and defaults to OFF.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QGridLayout, QTableWidget,
    QTableWidgetItem, QWidget,
)

from core import age_text
from gg_desktop.models import readable_bytes
from gg_desktop.cinematic_art import CinematicToolArtwork
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
        page = self._new("Ready Room",
                         "Your lineup, patch-watch status and helpful gaming shortcuts.")
        if self._not_scanned(page):
            return

        metrics = QWidget()
        bar = row(spacing=11)
        metrics.setLayout(bar)
        values = (
            ("GAMES FOUND", len(self.inventory.games),
             "Launcher records, not guesses", "cyan"),
            ("MOD LOCATIONS", len(self.inventory.mods),
             "Locations, not individual mod count", "amber"),
            ("PROTECTED SAVES", len(self.inventory.saves),
             "Candidate save locations remain protected", "green"),
            ("GRAVEYARD", len(self.inventory.graveyard),
             "Manual review candidates", "text"),
        )
        for name, value, detail, color in values:
            bar.addWidget(MetricCard(name, str(value), detail, tone=color))
        page.content.addWidget(metrics)

        workspace = QWidget()
        body = row(spacing=12)
        workspace.setLayout(body)
        left, stack = panel()
        stack.addWidget(section_title("YOUR LINEUP", "Recently played when known"))
        games = sorted(self.inventory.games,
                       key=lambda g: (g.last_played_at is None,
                                      -(g.last_played_at or 0), g.name.casefold()))[:250]
        table = QTableWidget(len(games), 4)
        table.setHorizontalHeaderLabels(["GAME", "LAUNCHER", "LAST PLAYED", "SIZE"])
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(37)
        table.setColumnWidth(0, 255)
        table.setColumnWidth(1, 140)
        table.setColumnWidth(2, 140)
        table.horizontalHeader().setStretchLastSection(True)
        table.setMinimumHeight(334)
        for i, g in enumerate(games):
            for j, value in enumerate((
                g.name, g.launcher,
                age_text(g.last_played_at) if g.last_played_at is not None else "Unknown",
                readable_bytes(g.size_bytes),
            )):
                _text(table, i, j, value)
        stack.addWidget(table)
        actions = QWidget()
        ab = row()
        actions.setLayout(ab)
        def inspect():
            chosen = table.selectionModel().selectedRows()
            if not chosen:
                self.info("Choose a game", "Select a recorded installation first.")
                return
            selected = games[chosen[0].row()]
            self._pending_game_query = selected.name
            self.navigate("Games")
        ab.addWidget(button("Inspect selected game", inspect, kind="primary"))
        ab.addWidget(button("Game DNA", lambda: self.navigate("Game DNA")))
        stack.addWidget(actions)
        body.addWidget(left, 7)

        right, right_col = panel()
        right.setObjectName("ggAccentPanel")
        right.setProperty("accent", "cyan")
        right_col.addWidget(section_title("PATCH WATCH", "Official source status"))
        signal = CinematicToolArtwork("scanner")
        signal.setMinimumHeight(95)
        signal.setMaximumHeight(95)
        right_col.addWidget(signal)
        status = label("OFFICIAL FEEDS: NOT CONNECTED", "eyebrow")
        status.setStyleSheet(
            "color:#F1C083;background:transparent;font-size:12px;font-weight:800;")
        right_col.addWidget(status)
        right_col.addWidget(label(
            "Official patch feeds have not been connected to this engineering preview. "
            "Game Grave will never invent game versions, developer notes, "
            "maintenance windows, or compatibility warnings.",
            "subtle", wrap=True))
        right_col.addWidget(label(
            "Once verified official sources are integrated, prioritize "
            "frequently played games and favorites, then link notices to Mod Radar.",
            "caption", wrap=True))
        right_col.addWidget(section_title("ATTENTION", "Current local evidence"))
        if self.inventory.warnings:
            for warning in self.inventory.warnings[:5]:
                right_col.addWidget(label("⚠ " + str(warning), "warning", wrap=True))
        else:
            right_col.addWidget(label(
                "No scan coverage warnings. This does not certify every mod compatible.",
                "subtle", wrap=True))
        right_col.addWidget(button("Open Mod Radar", lambda: self.navigate("Mods")))
        right_col.addWidget(button("Review Graveyard", lambda: self.navigate("Graveyard")))
        right_col.addStretch()
        body.addWidget(right, 3)
        page.content.addWidget(workspace)

        section, shortcuts = panel()
        shortcuts.addWidget(section_title("QUICK LAUNCH", "Related features"))
        quick = QWidget()
        grid = QGridLayout(quick)
        grid.setSpacing(9)
        for i, (name, info, destination) in enumerate((
            ("Mod Radar", "Inspect detected mods and manager locations", "Mods"),
            ("Save Vault", "Access backup and protection tools", "More Tools"),
            ("Game DNA", "Map verified game-storage relationships", "Game DNA"),
            ("Captures", "Review screenshots and recordings", "Captures"),
            ("Graveyard", "Review old data with evidence", "Graveyard"),
            ("Undo Center", "Verify recoverable cleanup actions", "Undo Center"),
        )):
            grid.addWidget(
                ActionCard("✧", name, info,
                           lambda dest=destination: self.navigate(dest)),
                i // 3, i % 3)
        shortcuts.addWidget(quick)
        page.content.addWidget(section)

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
