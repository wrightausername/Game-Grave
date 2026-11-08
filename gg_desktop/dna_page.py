"""Game DNA page: the owner's photo layout on evidence Game Grave already has.

Each game's profile lists only what the data proves (install folder, mods in or tied to it, the Steam shader cache
named for its app ID, Steam's per-game screenshots) plus folders you link yourself. Saves and configs are never
matched by name. Analyze is a read-only walk. Cleanup is never done here: Review & Clean opens the tab that owns
the removal, filtered to the game, where that tab's own confirmation and re-checks apply.
"""
from __future__ import annotations

import csv
import io
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QRect, QSignalBlocker, QSize, QUrl, Qt
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication, QPainter
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QHeaderView, QInputDialog, QListWidget,
                               QListWidgetItem, QStackedWidget, QStyledItemDelegate)
from shiboken6 import isValid

from core import human_size, save_settings
from game_intelligence import build_game_dna
from gg_desktop import dna_actions as actions
from gg_desktop import dna_data as data
from gg_desktop.grave_page import CheckRow
from gg_desktop.header_banner import HeaderBannerArtwork
from gg_desktop.insight_models import capture_items
from gg_desktop.insight_widgets import FootprintRing
from gg_desktop.models import _path_key, readable_bytes
from gg_desktop.reference_library import _detail_scroll, _search, _split, _table, _text, _widget
from gg_desktop.reference_widgets import CoverArt, DetailPanel, MetricStrip, TabStrip, cover_icon, detail_line, detail_section, icon, tool
from gg_desktop.widgets import button, column, destroy_layout, label, panel, row

SUBTITLE = ("A complete storage DNA profile for each game. See everything it uses, where it's located, "
            "and review what you don't need.")


class BarDelegate(QStyledItemDelegate):
    """Size text with a thin bar underneath whose length is the share of the game's footprint (Qt.UserRole)."""

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        share = index.data(Qt.UserRole)
        if not isinstance(share, (int, float)) or share <= 0:
            return
        rect = option.rect.adjusted(6, 0, -6, -4)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#1b2733"))
        track = QRect(rect.left(), rect.bottom() - 2, rect.width(), 3)
        painter.drawRoundedRect(track, 1.5, 1.5)
        painter.setBrush(QColor("#ff2346"))
        painter.drawRoundedRect(QRect(track.left(), track.top(), max(2, int(track.width() * min(1.0, share))), 3), 1.5, 1.5)
        painter.restore()


def state_of(window):
    if not hasattr(window, "_dna_state"):
        window._dna_state = SimpleNamespace(
            tab="Storage DNA", game_key=None, profile=None, analysis={}, busy=False, cancel=threading.Event(),
            model=None, model_key=None, captures=None, captures_key=None, rows=[], shown=[], suggestion_rows=[],
            message="")
    return window._dna_state


def live(window):
    return (window.current_route == "Game DNA" and hasattr(window, "dna_games") and isValid(window.dna_games)
            and hasattr(window.page, "dna_ready"))


def guarded(fn):
    def run(progress):
        try:
            return "ok", fn(progress)
        except InterruptedError:
            return "canceled", None
        except Exception as exc:  # reported on the page
            return "error", f"{type(exc).__name__}: {str(exc)[:300]}"
    return run


def never_touch(window):
    return window.settings.get("never_touch", [])


# ------------------------------------------------------------------ data
def _inventory_key(window):
    inv = window.inventory
    return (id(inv.steam), len(inv.steam), id(inv.mods), len(inv.mods), id(inv.saves), len(inv.saves), len(inv.other))


def dna_model(window):
    state = state_of(window)
    key = _inventory_key(window)
    if state.model_key != key:
        inv = window.inventory
        state.model = build_game_dna(inv.steam, inv.other, inv.mods, inv.saves)
        state.model_key = key
    return state.model


def capture_rows(window):
    state = state_of(window)
    inv = window.inventory
    key = (id(getattr(inv, "screenshots", None)), len(getattr(inv, "screenshots", [])),
           id(getattr(inv, "recordings", None)), len(getattr(inv, "recordings", [])), _inventory_key(window))
    if state.captures_key != key:
        state.captures = capture_items(inv)
        state.captures_key = key
    return state.captures


def assets_for(window, game):
    if len(game.claimed_by) != 1 or not game.status.startswith("Installed"):
        return []
    match = next((g for g in dna_model(window)["games"] if _path_key(g["install_path"]) == _path_key(game.install_path)
                  and g["launcher"] == game.launcher), None)
    return match["assets"] if match else []


def profile_for(window, game):
    state = state_of(window)
    return data.build_profile(
        game, assets=assets_for(window, game), steam=window.inventory.steam, captures=capture_rows(window),
        saves=window.inventory.saves, links=actions.links_for(window.settings, game.key),
        graveyard=window.inventory.graveyard, analysis=state.analysis.get(game.key))


def games_now(window):
    query = window.dna_search.text().strip().casefold()
    return [g for g in window.inventory.games if not query or query in (g.name + " " + g.launcher).casefold()]


def current_game(window):
    state = state_of(window)
    return next((g for g in state.shown if g.key == state.game_key), None)


# ------------------------------------------------------------------ page
def build(window):
    self = window
    state = state_of(self)
    state.tab = state.tab if state.tab in {n for n, _ in data.TABS} else "Storage DNA"
    page = self._insight_page("Game DNA", SUBTITLE, "dna", None, 74)
    page.banner_artwork = HeaderBannerArtwork(self, page, page.content.itemAt(0).widget(), route="Game DNA",
                                              scene="dna", source=(700, 0, 580, 126), excluded=((1090, 0, 190, 40),))
    self.dna_metrics = MetricStrip([
        ("game", "—", "Game DNA Profile", "#ff2245"), ("storage", "—", "Total Footprint", "#16c9eb"),
        ("folder", "—", "Locations", "#eac329"), ("box", "—", "Total Items", "#dd73e6"),
        ("clock", "—", "Last Accessed", "#ff244b"), ("check", "—", "Analysis", "#3ad371")], compact=True)
    self.dna_metrics.values[0].setStyleSheet("font-size:16px;font-weight:650;")
    page.content.addWidget(self.dna_metrics)

    sidebar, filters = panel(kind="fileFilterPanel", padding=9, spacing=7)
    sidebar.setFixedWidth(205 if self.width() >= 1100 else 180)
    filters.addWidget(label("Select Game", "sectionTitle"))
    self.dna_search = _search("Search your games…", "Search Game DNA games")
    filters.addWidget(self.dna_search)
    self.dna_games = QListWidget()
    self.dna_games.setObjectName("sourceFilters")
    self.dna_games.setIconSize(QSize(28, 32))
    self.dna_games.setAccessibleName("Select Game DNA profile")
    filters.addWidget(self.dna_games, 1)

    right = _widget(column(spacing=7))
    self.dna_game_header, self.dna_game_header_content = panel(kind="fileResults", padding=7, spacing=3)
    right.layout().addWidget(self.dna_game_header)
    self.dna_tabs = TabStrip(list(data.TABS), selected=state.tab)
    for control in self.dna_tabs.buttons.values():
        control.setStyleSheet("font-size:11px; padding:4px 3px;")
        control.setIconSize(QSize(15, 15))
    right.layout().addWidget(self.dna_tabs)

    footprint, chart = panel(kind="fileResults", padding=10, spacing=7)
    self.dna_chart_heading = label("Storage Footprint", "sectionTitle")
    chart.addWidget(self.dna_chart_heading)
    self.dna_chart_stack = QStackedWidget()
    chart.addWidget(self.dna_chart_stack, 1)
    ringbox = row(spacing=8)
    self.dna_ring = FootprintRing(caption="TOTAL FOOTPRINT")
    ringbox.addWidget(self.dna_ring, 1)
    self.dna_legend = _widget(column(spacing=4))
    ringbox.addWidget(self.dna_legend, 1)
    self.dna_chart_stack.addWidget(_widget(ringbox))
    listing = column(spacing=5)
    self.dna_asset_table = _table(["Location", "Evidence", "Items", "Size"])
    self.dna_asset_table.setSelectionBehavior(QAbstractItemView.SelectRows)
    self.dna_asset_table.setSelectionMode(QAbstractItemView.SingleSelection)
    self.dna_asset_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
    for c, width in ((1, 78), (2, 62), (3, 76)):
        self.dna_asset_table.setColumnWidth(c, width)
    listing.addWidget(self.dna_asset_table, 1)
    actions_row = row(spacing=6)
    self.dna_link_button = tool("Link Folder…", "folder", lambda: link_folder(self), tip="Tell Game Grave a folder belongs to this game")
    self.dna_unlink_button = tool("Unlink", "undo", lambda: unlink_folder(self), tip="Remove your link. The folder is not touched")
    self.dna_open_button = tool("Open", "folder", lambda: open_selected(self), tip="Open the selected location")
    for control in (self.dna_link_button, self.dna_unlink_button, self.dna_open_button):
        actions_row.addWidget(control)
    actions_row.addStretch(1)
    listing.addWidget(_widget(actions_row))
    self.dna_chart_stack.addWidget(_widget(listing))
    self.dna_summary = DetailPanel()
    self.dna_summary.setMinimumWidth(220)
    self.dna_summary.setMaximumWidth(300)
    right.layout().addWidget(_split(footprint, _detail_scroll(self.dna_summary), [460, 290]), 1)
    page.content.addWidget(_split(sidebar, right, [205, 820]), 1)

    bottom = row(spacing=8)
    locations, loc = panel(kind="fileResults", padding=8, spacing=5)
    title = row(spacing=5)
    self.dna_locations_heading = label("Top Locations", "sectionTitle")
    title.addWidget(self.dna_locations_heading, 1)
    title.addWidget(button("View All Locations", lambda: set_tab(self, "Files & Locations"), kind="link"))
    loc.addWidget(_widget(title))
    self.dna_locations = _table(["", "Location", "Reported Size"])
    self.dna_locations.setMinimumHeight(90)
    self.dna_locations.setMaximumHeight(112)
    self.dna_locations.setColumnWidth(0, 24)
    self.dna_locations.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
    self.dna_locations.setColumnWidth(2, 120)
    self.dna_locations.setItemDelegateForColumn(2, BarDelegate(self.dna_locations))
    loc.addWidget(self.dna_locations)
    bottom.addWidget(locations, 5)

    suggestions, suggest = panel(kind="fileResults", padding=9, spacing=5)
    suggest.addWidget(label("Cleanup Suggestions", "sectionTitle"))
    self.dna_suggest_body = _widget(column(spacing=1))
    suggest.addWidget(self.dna_suggest_body)
    self.dna_suggest_note = label("", "caption", wrap=True)
    suggest.addWidget(self.dna_suggest_note)
    buttons = row(spacing=6)
    self.dna_review_button = tool("Review & Clean", "sparkles", lambda: review_and_clean(self), kind="primary",
                                  tip="Opens the tab that owns removal, filtered to this game. Nothing is removed here")
    self.dna_graveyard_button = tool("Add to Graveyard", "grave", lambda: add_to_graveyard(self),
                                     tip="Opens this game's Graveyard entry")
    buttons.addWidget(self.dna_review_button)
    buttons.addWidget(self.dna_graveyard_button)
    suggest.addWidget(_widget(buttons))
    bottom.addWidget(suggestions, 3)
    page.content.addWidget(_widget(bottom))

    page.dna_ready = True
    self.dna_search.textChanged.connect(lambda *_: fill_games(self))
    self.dna_games.currentRowChanged.connect(lambda *_: pick_game(self))
    self.dna_tabs.changed.connect(lambda name: set_tab(self, name))
    self.dna_asset_table.itemSelectionChanged.connect(lambda: sync_buttons(self))
    fill_games(self)


# ------------------------------------------------------------------ games list
def fill_games(window):
    if not live(window):
        return
    state = state_of(window)
    state.shown = window._shown_dna_games = games_now(window)
    pending = getattr(window, "_pending_dna_game_key", None)
    with QSignalBlocker(window.dna_games):
        window.dna_games.clear()
        for g in state.shown:
            item = QListWidgetItem(cover_icon(g.name), g.name + "\n" + readable_bytes(g.size_bytes))
            item.setToolTip(g.name + "\n" + g.install_path)
            window.dna_games.addItem(item)
        if state.shown:
            wanted = pending or state.game_key
            row_index = next((i for i, g in enumerate(state.shown) if g.key == wanted), 0)
            window.dna_games.setCurrentRow(row_index)
    window._pending_dna_game_key = None
    pick_game(window)


def pick_game(window):
    if not live(window):
        return
    state = state_of(window)
    index = window.dna_games.currentRow()
    state.game_key = state.shown[index].key if 0 <= index < len(state.shown) else None
    show_game(window)


def set_tab(window, name):
    state = state_of(window)
    state.tab = name
    if live(window):
        window.dna_tabs.select(name)
        show_game(window)


# ------------------------------------------------------------------ profile views
def date_text(timestamp):
    return time.strftime("%b %d, %Y", time.localtime(timestamp))


def show_game(window):
    if not live(window):
        return
    state = state_of(window)
    header = window.dna_game_header_content
    contents = window.dna_summary.content
    for layout in (header, contents, window.dna_legend.layout()):
        destroy_layout(layout)
    window.dna_asset_table.setRowCount(0)
    window.dna_locations.setRowCount(0)
    game = current_game(window)
    if game is None:
        state.profile = None
        header.addWidget(label("Select a detected game", "detailTitle"))
        contents.addWidget(label("Scan PC to build evidence-backed game profiles.", "subtle", wrap=True))
        window.dna_ring.set_segments([], "Unknown")
        for i in range(6):
            window.dna_metrics.set_value(i, "—")
        window.dna_chart_stack.setCurrentIndex(0)
        render_suggestions(window, None)
        window.dna_link_button.setEnabled(False)
        window.dna_unlink_button.setEnabled(False)
        window.dna_open_button.setEnabled(False)
        return
    profile = profile_for(window, game)
    state.profile = profile
    total, segments, unknown = data.footprint(profile)
    items = data.total_items(profile)
    days = data.days_since(game.last_played_at)
    analysis = "Not run" if not profile.analyzed else ("Partial" if any(l.partial for l in profile.locations) else "Complete")
    if state.busy:
        analysis = "Running"
    for i, value in enumerate((game.name, human_size(total) if segments else "Unknown", len(profile.locations),
                               f"{items:,}" if items is not None else "—",
                               f"{days:,} Days" if days is not None else "Unknown", analysis)):
        window.dna_metrics.set_value(i, value)
    render_header(window, game)
    render_chart(window, profile, total, segments, unknown)
    render_summary(window, profile, total, items, days, unknown)
    render_top_locations(window, profile, total)
    render_suggestions(window, profile)


def render_header(window, game):
    header = window.dna_game_header_content
    from gg_desktop.artwork import game_app_id
    intro = row(spacing=10)
    art = CoverArt(game.name, height=80, artwork=window.artwork, app_id=game_app_id(game))
    art.setMaximumWidth(270)
    intro.addWidget(art, 1)
    text = column(spacing=4)
    title = label(game.name, "detailTitle", wrap=True)
    title.setTextFormat(Qt.PlainText)
    text.addWidget(title)
    text.addWidget(label(f"{game.launcher} | {game.status}", "caption", wrap=True))
    path = label(game.install_path, "caption", wrap=True)
    path.setTextFormat(Qt.PlainText)
    text.addWidget(path)
    intro.addLayout(text, 1)
    buttons = column(spacing=4)
    play = tool("Open Game", "play", lambda: window._launch_game(game), kind="primary")
    play.setEnabled("steam_uninstall" in game.capabilities)
    play.setToolTip("Starts the game through Steam" if play.isEnabled() else "Game Grave can only start Steam games it manages")
    buttons.addWidget(play)
    folder = tool("Open Folder", "folder", lambda: window._open_folder(game.install_path))
    folder.setEnabled("open_folder" in game.capabilities)
    buttons.addWidget(folder)
    url = actions.steam_url(game)
    steam = tool("View in Steam", "game", lambda: QDesktopServices.openUrl(QUrl(url)))
    steam.setEnabled(bool(url))
    steam.setToolTip("Opens this game's Steam page" if url else "Only Steam games have a Steam page")
    buttons.addWidget(steam)
    intro.addLayout(buttons)
    header.addWidget(_widget(intro))


def render_chart(window, profile, total, segments, unknown):
    state = state_of(window)
    tab = state.tab
    window.dna_chart_heading.setText("Storage Footprint" if tab == "Storage DNA" else tab)
    window.dna_chart_stack.setCurrentIndex(0 if tab == "Storage DNA" else 1)
    legend = window.dna_legend.layout()
    window.dna_ring.set_segments(segments, human_size(total) if segments else "Unknown")
    shown = {name: amount for name, amount, _ in segments}
    for category in data.CATEGORIES:
        amount = shown.get(category)
        text = "—" if amount is None else f"{human_size(amount)}  ({data.percent(amount, total):.0f}%)"
        info = label(f"●  {category}   {text}", "subtle", wrap=True)
        info.setStyleSheet(("color:" + data.COLORS[category] if amount else "color:#566271") + ";font-size:11px;")
        legend.addWidget(info)
    note = ("Locations inside the install folder are counted once. Saves, configs and recordings appear only when you "
            "link them." + (f" {unknown} location(s) have no size yet. Press Analyze." if unknown else ""))
    legend.addWidget(label(note, "caption", wrap=True))
    legend.addStretch()
    fill_asset_table(window, profile)


def fill_asset_table(window, profile):
    state = state_of(window)
    table = window.dna_asset_table
    category = data.TAB_CATEGORY.get(state.tab)
    locations = [l for l in profile.locations if category is None or l.category == category]
    hints = profile.hints if state.tab in {"Saves", "Config / Settings", "Files & Locations"} else []
    state.rows = [("location", l) for l in locations] + [("hint", h) for h in hints]
    table.setRowCount(0)
    for i, (kind, entry) in enumerate(state.rows):
        table.insertRow(i)
        if kind == "location":
            _text(table, i, 0, f"{entry.label}  ·  {entry.path}")
            table.item(i, 0).setToolTip(f"{entry.path}\n{entry.why}")
            _text(table, i, 1, entry.evidence)
            _text(table, i, 2, "—" if entry.items is None else f"{entry.items:,}")
            _text(table, i, 3, "Not measured" if entry.size is None else readable_bytes(entry.size) + ("+" if entry.partial else ""))
        else:
            _text(table, i, 0, f"Suggested  ·  {entry.path}")
            table.item(i, 0).setToolTip(f"{entry.path}\n{entry.why}")
            _text(table, i, 1, "Name hint")
            _text(table, i, 2, "—")
            _text(table, i, 3, "Not linked")
        table.setRowHeight(i, 30)
    if not state.rows and state.tab in data.EMPTY:
        table.setRowCount(1)
        _text(table, 0, 0, data.EMPTY[state.tab])
        table.setSpan(0, 0, 1, 4)
    elif table.rowCount():
        table.selectRow(0)
    linkable = state.tab in {"Files & Locations", "Saves", "Mods & Addons", "Caches", "Config / Settings",
                             "Screenshots", "Recordings"}
    window.dna_link_button.setVisible(linkable)
    window.dna_unlink_button.setVisible(linkable)
    window.dna_open_button.setVisible(state.tab != "Storage DNA")
    window.dna_link_button.setEnabled(not state.busy)
    window.dna_unlink_button.setEnabled(not state.busy)
    window.dna_open_button.setEnabled(bool(state.rows))
    sync_buttons(window)


def selected_entry(window):
    state = state_of(window)
    index = window.dna_asset_table.currentRow()
    return state.rows[index] if 0 <= index < len(state.rows) else None


def sync_buttons(window):
    if not live(window):
        return
    entry = selected_entry(window)
    kind, value = entry if entry else ("", None)
    window.dna_unlink_button.setEnabled(kind == "location" and value.source == "link" and not state_of(window).busy)
    window.dna_open_button.setEnabled(entry is not None)
    hint = kind == "hint"
    window.dna_link_button.setText("Link Suggested" if hint else "Link Folder…")


def render_summary(window, profile, total, items, days, unknown):
    game = profile.game
    contents = window.dna_summary.content
    detail_section(contents, "Game DNA Summary")
    last = "Unknown" if days is None else f"{date_text(game.last_played_at)} ({days:,} days ago)"
    created = "Unknown" if profile.created is None else f"Folder created {date_text(profile.created)}"
    for symbol, name, value in (
            ("storage", "Total Size", human_size(total) if total else "Unknown"),
            ("box", "Total Items", f"{items:,}" if items is not None else "Not counted. Press Analyze"),
            ("folder", "Locations", str(len(profile.locations))),
            ("clock", "Last Accessed", last), ("clock", "Install Date", created), ("game", "Game Status", game.status)):
        detail_line(contents, symbol, name, value)
    state = state_of(window)
    contents.addWidget(tool("Analyzing…" if state.busy else "Analyze Storage", "sparkles", lambda: analyze(window),
                            tip="Measures this game's folders. Read-only; nothing is changed"))
    detail_section(contents, "What It Is")
    contents.addWidget(label(
        "Every location here is tied to the game by a record Game Grave read, or by you. Last accessed is Steam's "
        "last-play record. Install date is when the install folder was created, not a purchase date. "
        "Unproven data is never counted.", "subtle", wrap=True))
    if profile.hints:
        contents.addWidget(label(f"{len(profile.hints)} possible save or profile location(s) resemble this game's name. "
                                 "They are listed under Saves and are not counted until you link them.", "caption", wrap=True))
    contents.addStretch()


def render_top_locations(window, profile, total):
    table = window.dna_locations
    ranked = sorted(profile.locations, key=lambda l: (-l.sort_size, l.label))
    window.dna_locations_heading.setText(f"Top Locations ({len(profile.locations)})")
    window.dna_top = ranked[:5]
    table.setRowCount(0)
    for i, loc in enumerate(window.dna_top):
        table.insertRow(i)
        check = _text(table, i, 0, "")
        check.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
        check.setCheckState(Qt.Unchecked)
        _text(table, i, 1, loc.path)
        size = _text(table, i, 2, "Not measured" if loc.size is None else readable_bytes(loc.size))
        size.setData(Qt.UserRole, 0 if not total or loc.size is None else loc.size / total)
        table.setRowHeight(i, 24)
    if table.rowCount():
        table.selectRow(0)


def render_suggestions(window, profile):
    state = state_of(window)
    body = window.dna_suggest_body.layout()
    destroy_layout(body)
    state.suggestion_rows = []
    suggestions = profile.suggestions if profile else []
    for s in suggestions:
        line = CheckRow(s.title + (f"  ({human_size(s.size)})" if s.size else ""), True)
        line.setToolTip(s.detail)
        line.count.setText("")
        state.suggestion_rows.append((s, line))
        body.addWidget(line)
    if not suggestions:
        body.addWidget(label("Nothing is suggested for this game. Game Grave only lists items it can tie to the game.",
                             "caption", wrap=True))
    window.dna_suggest_note.setText(
        "Review & Clean opens the tab that owns removal, filtered to this game. Nothing is removed from this page, "
        "and nothing here is called safe to remove." if suggestions else "")
    entry = next((s for s in suggestions if s.route == "Graveyard"), None)
    window.dna_review_button.setEnabled(bool(suggestions))
    window.dna_graveyard_button.setEnabled(entry is not None)
    window.dna_graveyard_button.setToolTip("Opens this game's Graveyard entry" if entry else
                                           "This game is not in the Graveyard. Steam's last-play record does not list it as neglected")


# ------------------------------------------------------------------ actions
def open_selected(window):
    entry = selected_entry(window)
    if entry is None:
        window.info("Choose a location", "Select a row first.")
        return
    window._open_folder(entry[1].path)


def analyze(window):
    state = state_of(window)
    profile = state.profile
    if state.busy or profile is None:
        return
    if window.scanning or window.cleaning:
        window.info("Game Grave is busy", "Finish the current operation before analyzing storage.")
        return
    game = profile.game
    state.busy, state.cancel = True, threading.Event()
    cancel = state.cancel
    paths = actions.analysis_paths(profile)

    def work(progress):
        return actions.analyze(paths, canceled=cancel.is_set, progress=lambda text: progress(0, text))

    def progress(_, text):
        window.status.setText(text)

    def done(outcome):
        status, result = outcome
        state.busy = False
        if status == "error":
            window.status.setText("Analysis failed. Nothing was changed.")
            window.error("Analysis failed", result)
        elif status == "canceled":
            window.status.setText("Analysis canceled.")
        else:
            state.analysis[game.key] = result
            window.status.setText(f"Analyzed {game.name}. Nothing was changed.")
        if live(window):
            show_game(window)

    window.job(guarded(work), done, error_title="Game DNA analysis failed", progress=progress)
    if live(window):
        show_game(window)


def link_folder(window):
    state = state_of(window)
    profile = state.profile
    if profile is None or state.busy:
        return
    game = profile.game
    entry = selected_entry(window)
    path, category = "", data.TAB_CATEGORY.get(state.tab, "")
    if entry and entry[0] == "hint":
        path = entry[1].path
        category = category or "Saves"
    else:
        path = QFileDialog.getExistingDirectory(window, f"Choose a folder that belongs to {game.name}")
        if not path:
            return
    if not category:
        choices = list(data.LINK_CATEGORIES)
        category, ok = QInputDialog.getItem(window, "What does this folder hold?", "Folder type:", choices, 0, False)
        if not ok:
            return
    existing = actions.links_for(window.settings, game.key)
    problem = actions.check_link(path, category, game, existing, never_touch(window))
    if problem:
        window.error("Cannot link this folder", problem)
        return
    if not window.confirm("Link this folder?", f"{path}\n\nGame Grave will treat it as {category} for {game.name}. "
                          "This only records your statement. No file is moved or removed."):
        return
    updated = actions.with_link(window.settings, game.key, path, category)
    if updated is None:
        window.error("Link list full", "Unlink a game's folders before linking more.")
        return
    try:
        save_settings(updated)
    except OSError as exc:
        window.error("Link not saved", str(exc))
        return
    window.settings = updated
    state.analysis.pop(game.key, None)
    window.status.setText(f"Linked {Path(path).name or path} to {game.name}. Press Analyze to measure it.")
    show_game(window)


def unlink_folder(window):
    state = state_of(window)
    entry = selected_entry(window)
    if state.profile is None or entry is None or entry[0] != "location" or entry[1].source != "link":
        window.info("Choose a linked folder", "Select a folder you linked yourself. Proven locations cannot be unlinked.")
        return
    game, loc = state.profile.game, entry[1]
    if not window.confirm("Remove this link?", f"{loc.path}\n\nOnly your link is removed. The folder is not touched."):
        return
    updated = actions.without_link(window.settings, game.key, loc.path)
    try:
        save_settings(updated)
    except OSError as exc:
        window.error("Link not removed", str(exc))
        return
    window.settings = updated
    state.analysis.pop(game.key, None)
    show_game(window)


def review_and_clean(window):
    state = state_of(window)
    picked = [s for s, line in state.suggestion_rows if line.box.isChecked()]
    if not picked:
        window.info("Choose suggestions", "Check the items you want to review.")
        return
    first = picked[0]
    window.status.setText(f"Opening {first.route} for {first.search}. Nothing is removed until you confirm there."
                          + (f" {len(picked) - 1} more checked item(s) are in other tabs." if len(picked) > 1 else ""))
    if first.pending_key:
        window._pending_grave_key = first.pending_key
    window.navigate(first.route)
    window._search_current_page(first.search)


def add_to_graveyard(window):
    state = state_of(window)
    entry = next((s for s, _ in state.suggestion_rows if s.route == "Graveyard"), None)
    if entry is None:
        window.info("Not in the Graveyard", "Steam's last-play record does not list this game as neglected.")
        return
    window._pending_grave_key = entry.pending_key
    window.navigate("Graveyard")


def export_csv(window):
    profile = state_of(window).profile
    if profile is None:
        return
    buffer = io.StringIO()
    csv.writer(buffer).writerows(actions.csv_rows(profile))
    QGuiApplication.clipboard().setText(buffer.getvalue())
    window.status.setText("Locations copied as CSV text.")
