"""Approved, restrained Crimson Command Ready Room for real user information.

One screen: a selectable lineup, a compact right watch column, a real Recap
Center, and private Game Memory / one-click session launch. The larger legacy
diagnostic workflows remain accessible on a separate detail screen, not piled
onto the approved dashboard. Nothing here simulates telemetry or plays a game.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import os

from PySide6.QtCore import Qt, QSize, QUrl, QTimer
from PySide6.QtGui import QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPlainTextEdit,
    QPushButton, QWidget,
)
from shiboken6 import isValid

from core import human_size
from gg_desktop.widgets import button, column, label, panel, row, section_title
from gg_desktop.premium_panels import _load_local_art
from gg_desktop.ready_room_data import (
    game_news_batch, launch_guard_summary, official_patch_source_for,
    prioritize_games, tonight_pick,
)
from gg_desktop.ready_room_memory import read_game_memory, save_game_memory
from gg_desktop.ready_room_sessions import (
    active_session, start_session, finish_session, read_sessions, recap,
    captured_during,
)
from gg_desktop.ready_room_visuals import PlaytimeTimeline
from gg_desktop.steam_artwork import verified_steam_id, prime_visible_covers
from gg_desktop.performance_watch import read_benchmarks, benchmark_summary
from gg_desktop.storage_watch import (
    load_history, describe_storage_history, sample_on_ready_room_open,
)
from performance_guard import GameActivityDetector

_DARK = "#17181D"
_TEXT = "#F4F4F6"
_MUTED = "#B1B6C1"


def _card(title: str, subtitle: str = "", *, min_height: int = 0):
    frame, layout = panel(padding=13, spacing=8)
    frame.setObjectName("readyRoomCard")
    if min_height:
        frame.setMinimumHeight(min_height)
    title_text = label(title, "sectionTitle")
    title_text.setStyleSheet(
        "color:#F8F6F7;background:transparent;font-size:15px;font-weight:800;")
    layout.addWidget(title_text)
    if subtitle:
        description = label(subtitle, "caption", wrap=True)
        description.setStyleSheet("color:#AEB9C4;background:transparent;")
        layout.addWidget(description)
    return frame, layout


def _metric(label_text, *, big="—", note=""):
    frame, col = panel(padding=10, spacing=2)
    frame.setObjectName("readyRoomMetric")
    title_text = label(label_text, "caption")
    title_text.setStyleSheet(
        "color:#C1C4CC;background:transparent;font-size:11px;")
    value = label(big, "readyRoomMetricValue", wrap=True)
    value.setStyleSheet(
        "color:#F8F8FA;background:transparent;font-size:18px;font-weight:800;")
    col.addWidget(title_text)
    col.addWidget(value)
    if note:
        col.addWidget(label(note, "caption", wrap=True))
    return frame, value


def _duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours, minutes = divmod(seconds // 60, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


def render_ready_room(window):
    page = window._new(
        "Ready Room",
        "Prepare, remember and launch your next session. "
        "Only verified local records appear here.")

    # The red-moon header matches the locked reference, but the lineup and
    # recap, rather than the hero banner, deserve the available screen space.
    header = page.content.itemAt(0)
    if header and header.widget():
        hero = header.widget()
        if hero.objectName() == "referenceHero":
            hero.setMinimumHeight(116)
            hero.setMaximumHeight(116)

    favorites = tuple(window.settings.get("ready_room_favorites", ()))
    selected_games = prioritize_games(window.inventory.games, favorites, limit=9)
    display_games = selected_games[:5]
    state = {"game": display_games[0] if display_games else None,
             "news": [], "period": "This Year", "daily_offset": 0,
             "capture_cache": None}
    window._ready_room_version = "approved-2026-recap-and-memory"
    if window.inventory.warnings:
        warning = label(
            "Partial library scan. Some games, captures, mods or playtime "
            "sources may be missing.", "warning", wrap=True)
        page.content.addWidget(warning)

    top = QWidget()
    top_row = row(spacing=12)
    top.setLayout(top_row)
    left = QWidget()
    left_col = column(spacing=12)
    left_col.setAlignment(Qt.AlignTop)
    left.setLayout(left_col)
    top_row.addWidget(left, 7)
    right = QWidget()
    right_col = column(spacing=12)
    right.setLayout(right_col)
    top_row.addWidget(right, 3)
    page.content.addWidget(top)

    lineup, lineup_col = _card(
        "★  YOUR LINEUP",
        "Your pinned and most recently played installed games.", min_height=345)
    lineup.setFixedHeight(365)
    lineup_col.setAlignment(Qt.AlignTop)
    left_col.addWidget(lineup)
    left_col.addStretch(1)

    art_strip = QWidget()
    art_row = row(spacing=8)
    art_strip.setLayout(art_row)
    art_strip.setFixedHeight(166)
    art_buttons = []
    for index, game in enumerate(display_games):
        entry = QWidget()
        entry_col = column(spacing=4)
        entry.setLayout(entry_col)
        picture = QPushButton()
        picture.setObjectName("readyRoomGameCover")
        picture.setFixedSize(105, 117)
        picture.setAccessibleName("Select " + game.name)
        picture.setToolTip(game.name + " (" + game.launcher + ")")
        art = _load_local_art(game, 99, 110)
        if not art.isNull():
            picture.setIcon(QIcon(art))
            picture.setIconSize(QSize(98, 110))
        else:
            picture.setText("NO OFFICIAL\nCOVER")
        text_name = label(game.name, "caption", wrap=True)
        text_name.setAlignment(Qt.AlignCenter)
        text_name.setMaximumHeight(32)
        text_name.setMinimumWidth(104)
        entry_col.addWidget(picture)
        entry_col.addWidget(text_name)
        art_row.addWidget(entry, 1)
        art_buttons.append((game, picture))
    art_row.addStretch(1)
    lineup_col.addWidget(art_strip)

    chosen_row = QWidget()
    chosen_body = row(spacing=13)
    chosen_row.setLayout(chosen_body)
    chosen_row.setFixedHeight(129)
    cover = QLabel()
    cover.setObjectName("readyRoomSelectedCover")
    cover.setFixedSize(100, 126)
    cover.setAlignment(Qt.AlignCenter)
    cover.setStyleSheet(
        "background:#10131B;color:#B0BBC5;border:1px solid #58414A;"
        "border-radius:8px;")
    chosen_body.addWidget(cover)
    selected_info = QWidget()
    info_col = column(spacing=5)
    selected_info.setLayout(info_col)
    selected_title = label("Choose a game", "sectionTitle", wrap=True)
    selected_title.setStyleSheet("font-size:17px;font-weight:800;color:#FFFFFF;")
    selected_status = label("Run Scan PC to discover installed games.",
                            "caption", wrap=True)
    guard_text = label("", "caption", wrap=True)
    info_col.addWidget(selected_title)
    info_col.addWidget(selected_status)
    info_col.addWidget(guard_text)
    action_row = QWidget()
    actions = row(spacing=8)
    action_row.setLayout(actions)
    play = button("Launch", kind="primary")
    play.setObjectName("readyRoomLaunchGame")
    play.setMinimumHeight(40)
    open_folder = button("Open Folder")
    tools = button("Game Tools", lambda _=False:
                   window.ready_room_diagnostics_page())
    actions.addWidget(play)
    actions.addWidget(open_folder)
    actions.addWidget(tools)
    actions.addStretch()
    info_col.addWidget(action_row)
    chosen_body.addWidget(selected_info, 1)
    lineup_col.addWidget(chosen_row)

    patch, patch_col = _card("PATCH WATCH", "Official news for your selected game.")
    patch_title = label("Not checked", "findingTitle", wrap=True)
    patch_col.addWidget(patch_title)
    patch_actions = QWidget()
    patch_row = row(spacing=7)
    patch_actions.setLayout(patch_row)
    refresh_news = button("Check updates", kind="primary")
    official_link = button("Publisher page")
    patch_row.addWidget(refresh_news)
    patch_row.addWidget(official_link)
    patch_col.addWidget(patch_actions)
    right_col.addWidget(patch)

    perf, perf_col = _card(
        "PERFORMANCE WATCH", "Your benchmarks. No invented live FPS.")
    perf_text = label("No benchmark data yet.", "findingTitle", wrap=True)
    perf_col.addWidget(perf_text)
    perf_col.addWidget(button(
        "Benchmark details", lambda _=False: window.ready_room_diagnostics_page()))
    right_col.addWidget(perf)

    storage, storage_col = _card(
        "STORAGE WATCH", "Verified free space on game drives.")
    storage_text = label("No drive sample yet.", "findingTitle", wrap=True)
    storage_col.addWidget(storage_text)
    storage_col.addWidget(button(
        "Explore Other Storage", lambda _=False: window.navigate("Other Storage")))
    right_col.addWidget(storage)
    right_col.addStretch()

    recap_panel, recap_col = _card(
        "▥  RECAP CENTER", "Your measured gaming year, sessions and moments.")
    recap_panel.setObjectName("readyRoomRecapCenter")
    periods = QWidget()
    period_row = row(spacing=7)
    periods.setLayout(period_row)
    period_row.addStretch()
    period_buttons = []
    for name in ("This Year", "This Month", "This Session"):
        item = button(name)
        item.setObjectName("readyRoomPeriod")
        item.setAccessibleName("Recap Center " + name)
        period_row.addWidget(item)
        period_buttons.append((name, item))
    recap_col.addWidget(periods)

    metrics = QWidget()
    metrics_row = row(spacing=10)
    metrics.setLayout(metrics_row)
    total_box, total_value = _metric("TRACKED TIME")
    average_box, average_value = _metric("AVERAGE SESSION")
    sessions_box, sessions_value = _metric("SESSIONS RECORDED")
    most_box, most_value = _metric("MOST PLAYED GAME")
    for metric in (total_box, average_box, sessions_box, most_box):
        metrics_row.addWidget(metric, 1)
    recap_col.addWidget(metrics)
    evidence_note = label(
        "This recap uses only Game Grave sessions that you explicitly "
        "started and finished. It is not complete historical Steam playtime.",
        "caption", wrap=True)
    recap_col.addWidget(evidence_note)

    visuals = QWidget()
    visual_row = row(spacing=14)
    visuals.setLayout(visual_row)
    timeline_panel, timeline_col = _card(
        "PLAYTIME TIMELINE", "Tracked session hours by month.")
    timeline = PlaytimeTimeline()
    timeline_col.addWidget(timeline)
    visual_row.addWidget(timeline_panel, 5)
    media_panel, media_col = _card(
        "SESSION CAPTURES", "Actual files detected during a tracked time window.")
    capture_summary = label(
        "No linked timestamp-window captures.", "subtle", wrap=True)
    media_col.addWidget(capture_summary)
    capture_preview = QWidget()
    preview_col = column(spacing=4)
    capture_preview.setLayout(preview_col)
    media_col.addWidget(capture_preview)
    media_actions = QWidget()
    media_row = row(spacing=8)
    media_actions.setLayout(media_row)
    preview_capture = button("Preview screenshot")
    media_row.addWidget(preview_capture)
    media_row.addWidget(button(
        "All Captures", lambda _=False: window.navigate("Captures")))
    media_row.addStretch()
    media_col.addWidget(media_actions)
    visual_row.addWidget(media_panel, 5)
    recap_col.addWidget(visuals)

    tracker = QWidget()
    tracker_row = row(spacing=9)
    tracker.setLayout(tracker_row)
    session_control = button("Start Session & Launch", kind="primary")
    session_control.setObjectName("readyRoomSessionControl")
    session_control.setMinimumHeight(41)
    session_status = label(
        "Session tracking is off until you explicitly start it.", "caption", wrap=True)
    discard = button("Discard timer")
    tracker_row.addWidget(session_control)
    tracker_row.addWidget(discard)
    tracker_row.addWidget(session_status, 1)
    recap_col.addWidget(tracker)
    page.content.addWidget(recap_panel)

    feature_nav = QWidget()
    feature_row = row(spacing=12)
    feature_nav.setLayout(feature_row)
    for title, details, action in (
        ("GAME TIME MACHINE", "Your Resurrection Kit snapshots",
         window._kit_versions),
        ("LAUNCH GUARD", "Installed-file evidence and drive health",
         lambda: window.ready_room_diagnostics_page()),
        ("MOD RADAR", "Linked mods and review tools",
         lambda: window.navigate("Mods")),
    ):
        tile, tile_col = _card(title, details)
        jump = button("Open " + title.title() + "  ›", action)
        tile_col.addWidget(jump)
        feature_row.addWidget(tile, 1)
    page.content.addWidget(feature_nav)

    bottom = QWidget()
    bottom_row = row(spacing=12)
    bottom.setLayout(bottom_row)
    notes, notes_col = _card(
        "GAME MEMORY", "Your private notes, next goal and preferred setup.")
    note_title = label("Choose a game", "findingTitle", wrap=True)
    note_body = label("Nothing recorded yet.", "subtle", wrap=True)
    notes_col.addWidget(note_title)
    notes_col.addWidget(note_body)
    edit_memory = button("Edit Game Memory…", kind="primary")
    notes_col.addWidget(edit_memory)
    bottom_row.addWidget(notes, 1)

    pick, pick_col = _card(
        "DAILY GAME SUGGESTION",
        "A little inspiration from games actually installed on your PC.")
    pick_name = label("No installed game found.", "findingTitle", wrap=True)
    pick_col.addWidget(pick_name)
    pick_actions = QWidget()
    pick_row = row(spacing=8)
    pick_actions.setLayout(pick_row)
    another = button("Choose another")
    go_pick = button("View game", kind="primary")
    pick_row.addWidget(another)
    pick_row.addWidget(go_pick)
    pick_row.addStretch()
    pick_col.addWidget(pick_actions)
    bottom_row.addWidget(pick, 1)
    page.content.addWidget(bottom)

    diagnostics = button(
        "Advanced mod health, benchmarks and Resurrection Kit tools…",
        lambda _=False: window.ready_room_diagnostics_page())
    diagnostics.setObjectName("readyRoomDiagnostics")
    page.content.addWidget(diagnostics)

    def page_valid():
        return (window.page is page and isValid(page))

    def refresh_watch():
        game = state["game"]
        if game is None:
            patch_title.setText("No selected game.")
            perf_text.setText("No game selected.")
            official_link.setEnabled(False)
            refresh_news.setEnabled(False)
            return
        perf_text.setText(benchmark_summary(read_benchmarks(game)))
        official = official_patch_source_for(game)
        official_link.setEnabled(bool(official))
        official_link.setVisible(bool(official))
        refresh_news.setEnabled(bool(verified_steam_id(game)))
        refresh_news.setVisible(bool(verified_steam_id(game)))
        if state["news"]:
            patch_title.setText(state["news"][0][1].title)
        else:
            patch_title.setText(
                "Check verified Steam announcements" if verified_steam_id(game)
                else "No verified Steam ID for news; use publisher site if available.")

    def update_buttons():
        active = active_session()
        if active:
            session_control.setText("Finish Tracked Session")
            discard.setEnabled(True)
            duration = max(0, int(datetime.now(timezone.utc).timestamp())
                           - active["start"])
            session_status.setText(
                "Manual timer running: " + active["name"] + " · " +
                _duration(duration) + ". Actual gameplay not verified.")
        else:
            discard.setEnabled(False)
            game = state["game"]
            session_control.setText(
                "Start Session & Launch" if game and verified_steam_id(game)
                else "Start Session Timer")
            session_control.setEnabled(bool(
                game and "Installed" in str(getattr(game, "status", ""))))
            session_status.setText(
                "Optional timer. Only explicitly finished sessions enter recaps; "
                "idle time may be included.")
        if active:
            session_control.setEnabled(True)

    def choose_game(game):
        if not page_valid():
            return
        state["game"] = game
        state["news"] = []
        for g, pic in art_buttons:
            chosen = g.key == game.key
            pic.setStyleSheet(
                "QPushButton { background:#10131B;color:#BFC9D3;"
                "border:" + ("2px solid #F34860;" if chosen
                             else "1px solid #41434B;") +
                "border-radius:9px;font-size:9px; }")
        art = _load_local_art(game, 100, 126)
        cover.setPixmap(QPixmap())
        if not art.isNull():
            cover.setText("")
            cover.setPixmap(art)
        else:
            cover.setText("NO OFFICIAL\nCOVER")
        selected_title.setText(game.name)
        status, evidence = launch_guard_summary(game)
        selected_status.setText(game.launcher + " · " + status +
                                " (launch/mod compatibility unverified)")
        guard_text.setText(evidence)
        steam_ready = bool(verified_steam_id(game))
        play.setText("Launch in Steam" if steam_ready else "Open Game Folder")
        play.setEnabled(bool(
            steam_ready or "open_folder" in game.capabilities))
        # Do not present two different buttons that both only open a folder.
        open_folder.setVisible(steam_ready)
        open_folder.setEnabled(steam_ready and "open_folder" in game.capabilities)
        note_title.setText(game.name)
        memory = read_game_memory(game)
        old_notes = window.settings.get("ready_room_notes", {})
        legacy = (old_notes.get(game.key, "")
                  if isinstance(old_notes, dict) else "")
        note_body.setText(
            "LAST TIME  " + (memory["where"] or legacy or "Not recorded")[:180] +
            "\nNEXT GOAL  " + (memory["next"] or "Not recorded")[:180] +
            "\nSESSION SETUP  " + (memory["profile"] or "Not recorded")[:150])
        refresh_watch()
        update_buttons()

    def launch_game(game):
        if not game:
            return False
        app_id = verified_steam_id(game)
        if app_id:
            opened = QDesktopServices.openUrl(QUrl("steam://rungameid/" + app_id))
            if not opened:
                window.error("Steam launch unavailable",
                             "Steam could not accept this launch link. "
                             "No session timer was started.")
            return bool(opened)
        window._open_folder(game.install_path)
        return False  # Opening a folder never proves the game launched.

    def start_or_end():
        active = active_session()
        if active is not None:
            try:
                finished = finish_session()
            except (OSError, ValueError) as exc:
                window.error("Tracked session not completed", str(exc))
                return
            window.status.setText(
                "Recorded " + _duration(finished["end"] - finished["start"]) +
                " of manually tracked session time.")
            update_buttons()
            update_recap()
            return
        game = state["game"]
        if game is None:
            return
        if verified_steam_id(game) and not launch_game(game):
            return
        try:
            start_session(game, mode=(
                "steam_launch_requested" if verified_steam_id(game)
                else "manual_timer"))
        except (OSError, ValueError) as exc:
            window.error("Could not start session timer", str(exc))
            return
        update_buttons()
        window.status.setText(
            "Optional session timer started. Return to Game Grave and "
            "finish it when you stop playing.")

    def discard_timer():
        if not active_session():
            return
        if not window.confirm(
            "Discard unverified timer?",
            "The running timer will be removed without adding any playtime "
            "to your recap. Your previous completed sessions remain."):
            return
        try:
            finish_session(discard=True)
        except (OSError, ValueError) as exc:
            window.error("Could not discard timer", str(exc))
            return
        update_buttons()

    def edit_game_memory():
        game = state["game"]
        if game is None:
            return
        current = read_game_memory(game)
        dialog = QDialog(window)
        dialog.setWindowTitle("Game Memory · " + game.name)
        dialog.setMinimumWidth(510)
        cols = column(spacing=9, margins=(18, 18, 18, 18))
        dialog.setLayout(cols)
        fields = []
        for heading, key in (
            ("Where I left off", "where"),
            ("What I want to do next", "next"),
            ("My preferred session setup / mod profile", "profile"),
        ):
            cols.addWidget(label(heading, "sectionTitle"))
            edit = QPlainTextEdit()
            edit.setAccessibleName(heading)
            edit.setPlainText(current.get(key, ""))
            edit.setMaximumHeight(91)
            cols.addWidget(edit)
            fields.append(edit)
        cols.addWidget(label(
            "Only information you enter is saved on this PC. "
            "Game Grave does not modify mod-manager profiles.", "caption", wrap=True))
        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        cols.addWidget(buttons)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            save_game_memory(
                game, where=fields[0].toPlainText(),
                next_goal=fields[1].toPlainText(),
                profile=fields[2].toPlainText())
        except (OSError, ValueError) as exc:
            window.error("Game Memory not saved", str(exc))
            return
        choose_game(game)
        window.status.setText("Game Memory saved locally for " + game.name)

    def update_pick():
        game = tonight_pick(
            window.inventory.games,
            day=datetime.now().strftime("%Y-%m-%d"),
            offset=state["daily_offset"])
        state["pick"] = game
        pick_name.setText(
            game.name + " · " + game.launcher if game else
            "No verified installed games yet.")
        go_pick.setEnabled(game is not None)

    def view_pick():
        game = state.get("pick")
        if game is None:
            return
        for available in display_games:
            if available.key == game.key:
                choose_game(available)
                page.verticalScrollBar().setValue(0)
                return
        window.navigate("Games")

    def refresh_storage(history):
        if not page_valid() or not isValid(storage_text):
            return
        lines = describe_storage_history(history)
        storage_text.setText(
            "\n".join(lines[:2]) if lines else
            "No observed local game-drive space yet.")

    def request_news():
        game = state["game"]
        if game is None or not verified_steam_id(game):
            return
        refresh_news.setEnabled(False)
        patch_title.setText("Checking Steam announcements on demand…")
        key = game.key
        def completed(items):
            if not page_valid() or not isValid(refresh_news):
                return
            if state["game"] and state["game"].key == key:
                state["news"] = items
                patch_title.setText(
                    items[0][1].title if items else
                    "No available official Steam news for this game.")
                refresh_news.setEnabled(True)
        window.job(
            lambda _progress: game_news_batch([game], limit=1, force=True),
            completed, error_title="Steam announcements unavailable")

    def publisher_page():
        game = state["game"]
        result = official_patch_source_for(game) if game else None
        if result:
            QDesktopServices.openUrl(QUrl(result[1]))

    def update_recap():
        data = recap(read_sessions(), state["period"])
        total_value.setText(_duration(data["seconds"]) if data["sessions"] else "0h")
        average_value.setText(
            _duration(data["average_seconds"]) if data["sessions"] else "—")
        sessions_value.setText(str(data["sessions"]))
        most_value.setText(data["most_played"])
        timeline.set_seconds(data["monthly_seconds"])
        for name, control in period_buttons:
            is_selected = name == state["period"]
            control.setStyleSheet(
                "QPushButton { background:" +
                ("#B72540" if is_selected else "#222329") +
                "; color:#F4F5F6; border:1px solid " +
                ("#EB5269" if is_selected else "#48424B") +
                "; border-radius:7px; padding:7px 11px;"
                "font-weight:700; }")
        since = data["tracked_since"]
        if since is not None:
            stamped = datetime.fromtimestamp(
                since, timezone.utc).strftime("%b %d, %Y")
            evidence_note.setText(
                f"Tracked since {stamped}. These are only sessions recorded "
                "and finished in Game Grave; idle time may be included. "
                "Untracked game hours cannot be reconstructed.")
        else:
            evidence_note.setText(
                "No tracked sessions yet. Game Grave cannot reconstruct "
                "2026 playtime you never recorded; start a session to build a recap.")

        def clear_previews():
            from gg_desktop.widgets import destroy_layout
            destroy_layout(preview_col)
        clear_previews()
        latest = data["latest"]
        shots = captured_during(latest, window.inventory.screenshots)
        videos = captured_during(latest, window.inventory.recordings)
        state["capture_cache"] = (shots, videos)
        preview_capture.setEnabled(bool(shots))
        if latest is None:
            capture_summary.setText(
                "No completed session in this period. "
                "Captures remain available separately under Captures.")
            return
        beginning = datetime.fromtimestamp(
            latest["start"], timezone.utc).strftime("%b %d · %H:%M UTC")
        capture_summary.setText(
            latest["name"] + " · " + beginning + "\n" +
            f"{len(shots)} screenshot(s) and {len(videos)} recording(s) "
            "with timestamps inside the tracked window.")
        for rec in [*shots[:2], *videos[:2]]:
            extension = Path(rec.path).suffix.casefold()
            kind = "VIDEO" if extension in (
                ".mp4", ".mkv", ".mov", ".avi", ".webm") else "IMAGE"
            name = Path(rec.path).name
            preview_col.addWidget(label(
                kind + "  •  " + name[:58], "caption", wrap=True))
        preview_col.addWidget(label(
            "Timestamp overlap only. A file's modified time is not proof "
            "it came from that particular game or session.",
            "caption", wrap=True))

    def load_preview():
        if GameActivityDetector().active():
            window.status.setText("Image decoding paused during gameplay.")
            return
        shots = (state.get("capture_cache") or ([], []))[0]
        if not shots:
            return
        from gg_desktop.capture_image import ScreenshotImage, request_screenshot
        capture = shots[0]
        widget = ScreenshotImage(height=120)
        preview_col.insertWidget(0, widget)
        request_screenshot(window, capture, widget)

    def change_period(name):
        state["period"] = name
        update_recap()

    def tick_session():
        if page_valid() and active_session():
            update_buttons()

    for index, (game, artwork) in enumerate(art_buttons):
        artwork.clicked.connect(lambda _=False, g=game: choose_game(g))
    play.clicked.connect(lambda _=False: launch_game(state["game"]))
    open_folder.clicked.connect(
        lambda _=False: state["game"] and
        window._open_folder(state["game"].install_path))
    session_control.clicked.connect(start_or_end)
    discard.clicked.connect(discard_timer)
    edit_memory.clicked.connect(edit_game_memory)
    refresh_news.clicked.connect(request_news)
    official_link.clicked.connect(publisher_page)
    preview_capture.clicked.connect(load_preview)
    for name, action in period_buttons:
        action.clicked.connect(lambda _=False, k=name: change_period(k))
    another.clicked.connect(lambda _=False: (
        state.__setitem__("daily_offset", state["daily_offset"] + 1),
        update_pick()))
    go_pick.clicked.connect(view_pick)
    ticker = QTimer(page)
    ticker.setInterval(30_000)
    ticker.timeout.connect(tick_session)
    ticker.start()

    update_recap()
    update_pick()
    if state["game"]:
        choose_game(state["game"])
    else:
        play.setEnabled(False)
        open_folder.setEnabled(False)
        tools.setEnabled(False)
        edit_memory.setEnabled(False)
        session_control.setEnabled(False)
        discard.setEnabled(False)
        preview_capture.setEnabled(False)
        refresh_watch()
    refresh_storage(load_history())
    # Sample only OS disk counters, in a low-priority worker, capped to once
    # every 6 hours per drive; no file crawl and never during gameplay.
    window.job(
        lambda _emit: sample_on_ready_room_open(
            tuple(window.inventory.games)),
        refresh_storage, error_title="Storage sample unavailable")
    def artwork_loaded(count):
        if not page_valid() or not count:
            return
        for game, pic in art_buttons:
            if not isValid(pic):
                continue
            art = _load_local_art(game, 99, 110)
            if not art.isNull():
                pic.setText("")
                pic.setIcon(QIcon(art))
                pic.setIconSize(QSize(98, 110))
        if state["game"]:
            current = state["game"]
            choose_game(current)
    if display_games:
        window.job(
            lambda _emit: prime_visible_covers(display_games, limit=5),
            artwork_loaded, error_title="Official game cover unavailable")
    return page
