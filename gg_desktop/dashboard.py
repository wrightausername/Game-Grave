"""Reference-matched Crimson Command dashboard, built from real data.

The visible layout tracks the approved concept art while remaining an
accessible, resizable Qt application. Every action uses existing safety APIs.
The mockup's fictional game names, recoveries and disk totals are never used.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import os
from pathlib import Path
import shutil
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QMenu, QProgressBar, QSizePolicy, QVBoxLayout, QWidget,
)

from core import human_size, save_settings
from graveyard_protection import protection_action
from gg_desktop.backend import refresh_graveyard
from gg_desktop.widgets import (
    ActionCard, HeroBanner, LandscapeArt, MetricCard, StorageRing,
    button, column, label, panel, row,
)
from recovery import get_records

LAUNCHERS = [
    ("Steam", "#27A6E5", "◉"),
    ("Xbox", "#5DCF69", "✕"),
    ("Epic Games", "#9874E8", "EP"),
    ("EA App", "#FF7255", "EA"),
    ("Ubisoft Connect", "#9C8BEE", "◎"),
    ("GOG Galaxy", "#CF59CF", "G"),
    ("Battle.net", "#35BAED", "❋"),
    ("Other", "#9AA5B4", "▣"),
]


def _heading(name: str, action=None, action_text="See All  ›", count: int | None = None):
    box = QWidget()
    line = row(spacing=7)
    box.setLayout(line)
    line.addWidget(label(name, "sectionTitle"), 1)
    if count is not None:
        pill = label(str(count) + " items", "queuePill")
        line.addWidget(pill)
    if action is not None:
        line.addWidget(button(action_text, action, kind="link"))
    return box


def _pill_icon(text: str, color: str, size=36):
    item = QLabel(text)
    item.setFixedSize(size, size)
    item.setAlignment(Qt.AlignCenter)
    item.setAccessibleName(text + " themed graphic")
    item.setStyleSheet(
        "background: #0B1820; border:1px solid " + color + ";"
        "border-radius:7px; font-weight:900; color:" + color + ";"
        "font-size:" + ("11px" if len(text) > 1 else "19px") + ";")
    return item


def _decorated_item(text: str, subtitle: str, activation, *,
                    glyph: str = "♱", color="#FF4057", fixed_height=47):
    box = QFrame()
    box.setObjectName("findingRow")
    box.setMinimumHeight(fixed_height)
    line = row(spacing=9, margins=(5, 5, 5, 5))
    box.setLayout(line)
    line.addWidget(_pill_icon(glyph, color, 35))
    detail = QWidget()
    stack = column(spacing=1)
    detail.setLayout(stack)
    text_label = label(text[:52], "findingTitle", wrap=False)
    text_label.setToolTip(text)
    stack.addWidget(text_label)
    subtitle_label = label(subtitle[:88], "caption", wrap=False)
    subtitle_label.setToolTip(subtitle)
    stack.addWidget(subtitle_label)
    line.addWidget(detail, 1)
    line.addWidget(button("›", activation, kind="link"))
    return box


def _monthly_recycled() -> tuple[int, int, int, int]:
    """This is *not* disk space reclaimed. May include still-binned files."""
    now = datetime.now().astimezone()
    cur, previous, cur_count, prev_count = 0, 0, 0, 0
    if now.month == 1:
        pm, py = 12, now.year - 1
    else:
        pm, py = now.month - 1, now.year
    for entry in get_records():
        try:
            when = datetime.fromisoformat(str(entry["time"]))
            amount = entry["size"]
            if type(amount) is not int or amount < 0:
                continue
            if when.year == now.year and when.month == now.month:
                cur += amount
                cur_count += 1
            elif when.year == py and when.month == pm:
                previous += amount
                prev_count += 1
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    return cur, previous, cur_count, prev_count


def _drive_choices():
    """Enumerate drive letters without crawling user files."""
    if sys.platform == "win32":
        return [f"{c}:\\" for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                if os.path.isdir(f"{c}:\\")]
    return [str(Path.home().anchor)]


def _game_on_drive(path: str, drive: str):
    if sys.platform != "win32":
        return path.startswith(drive) if drive != "/" else True
    return os.path.normcase(str(path)).startswith(os.path.normcase(drive))


def _pick_game_icon(name: str) -> tuple[str, str]:
    variants = (
        ("#F95760", "♱"), ("#FFB849", "✦"), ("#59C9E9", "◈"),
        ("#9578E8", "◆"), ("#72D88D", "◎"),
    )
    return variants[sum(ord(ch) for ch in name) % len(variants)]


def _enqueue_mod(window, mod):
    """Read-only watchlist action; no file move or protection change."""
    path = str(getattr(mod, "path", ""))
    if not path:
        window.info("No mod location", "This finding has no usable path.")
        return
    if not window.confirm(
            "Add mod folder to Graveyard review?",
            "Mark this folder for review in the Graveyard?\n\n" + path +
            "\n\nNothing is deleted, moved, unprotected, or marked safe. "
            "Managed mod folders remain protected."):
        return
    changed = dict(window.settings)
    current = list(changed.get("graveyard_watchlist", []))
    if path not in current:
        if len(current) >= 250:
            window.error("Review list full", "Remove an older review item first.")
            return
        current.append(path)
    changed["graveyard_watchlist"] = current
    try:
        save_settings(changed)
    except (OSError, ValueError) as exc:
        window.error("Could not save review item", str(exc))
        return
    window.settings = changed
    refresh_graveyard(window.inventory, changed)
    window._pending_grave_key = "mod:" + str(Path(path)).casefold()
    window.navigate("Graveyard")


def render_dashboard(window):
    page = window.page_for("Overview")
    page.content.setSpacing(11)
    # Main header: cinematic scenic artwork and accurate, explicitly scoped
    # recycle history instead of the mockup's fictional "37.8 GB reclaimed".
    top = QWidget()
    top_grid = QHBoxLayout(top)
    top_grid.setContentsMargins(0, 0, 0, 0)
    top_grid.setSpacing(11)
    hero = HeroBanner(
        title="YOUR GAMES.", subtitle="A CLEANER TOMORROW.",
        detail="Find old files, remove what you don't need, and keep your "
               "games in top shape across all launchers.")
    top_grid.addWidget(hero, 7)
    this_month, previous_month, month_count, previous_count = _monthly_recycled()
    status = MetricCard(
        "♢  RECYCLED THIS MONTH", human_size(this_month),
        f"{month_count} reviewed moves • still in Recycle Bin until emptied",
        tone="cyan")
    status.setObjectName("heroMetric")
    status.setToolTip(
        "Game Grave recorded Recycle Bin moves, not storage reclaimed. "
        "The same file could have been restored or removed again.")
    top_grid.addWidget(status, 3)
    top.setMinimumHeight(187)
    page.content.addWidget(top)

    action_row = QWidget()
    actions = QGridLayout(action_row)
    actions.setContentsMargins(0, 0, 0, 0)
    actions.setSpacing(10)
    options = (
        ("⌕", "Scan for Old Files",
         "Find leftover files, mods, and stale data.", window.start_scan),
        ("♱", "Review Graveyard",
         f"{len(window.inventory.graveyard)} items waiting for review",
         lambda: window.navigate("Graveyard")),
        ("↶", "Open Undo Center",
         "Restore files you've previously recycled.",
         lambda: window.navigate("Undo Center")),
        ("⚙", "Quick Settings",
         "Customize scans, exclusions, and appearance.",
         lambda: window.navigate("Settings")),
    )
    cols = 4 if window.width() >= 1200 else 2
    for i, (icon, title, desc, operation) in enumerate(options):
        card = ActionCard(icon, title, desc, operation)
        card.setMinimumHeight(88)
        if i == 0:
            card.setObjectName("actionCardPrimary")
        actions.addWidget(card, i // cols, i % cols)
        actions.setColumnStretch(i % cols, 1)
    page.content.addWidget(action_row)

    # Storage / launcher / recent findings row
    middle = QWidget()
    mid = QHBoxLayout(middle)
    mid.setContentsMargins(0, 0, 0, 0)
    mid.setSpacing(10)

    disk_card, disk_col = panel(padding=14, spacing=8)
    disk_card.setObjectName("dashboardPanel")
    drive_head = QWidget()
    drive_line = row(spacing=7)
    drive_head.setLayout(drive_line)
    drive_line.addWidget(label("Storage Overview", "sectionTitle"), 1)
    drive_picker = QComboBox()
    drives = _drive_choices()
    for drive in drives:
        drive_picker.addItem("Local Drive (" + drive.rstrip("\\") + ")", drive)
    drive_picker.setAccessibleName("Choose local drive for storage overview")
    drive_picker.setMinimumWidth(120)
    drive_line.addWidget(drive_picker)
    disk_col.addWidget(drive_head)
    disk_col.addWidget(QFrame()) if False else None

    disk_visual = QWidget()
    disk_row = row(spacing=8)
    disk_visual.setLayout(disk_row)
    ring = StorageRing()
    disk_row.addWidget(ring, 5)
    legend = QWidget()
    legend_col = column(spacing=6)
    legend.setLayout(legend_col)
    key_colors = ("#FF4357", "#28CFFF", "#959CAC")
    legends = []
    for name, color in zip(("Games", "Other used", "Free space"), key_colors):
        info = QWidget()
        info_line = row(spacing=5)
        info.setLayout(info_line)
        dot = label("●")
        dot.setStyleSheet("color:" + color + ";font-size:16px;")
        info_line.addWidget(dot)
        text_block = QWidget()
        block_col = column(spacing=1)
        text_block.setLayout(block_col)
        block_col.addWidget(label(name, "caption"))
        amount = label("Unknown", "findingTitle")
        block_col.addWidget(amount)
        info_line.addWidget(text_block, 1)
        percent = label("—", "caption")
        info_line.addWidget(percent)
        legend_col.addWidget(info)
        legends.append((amount, percent))
    legend_col.addStretch()
    disk_row.addWidget(legend, 5)
    disk_col.addWidget(disk_visual, 1)

    strip = QProgressBar()
    strip.setFixedHeight(7)
    strip.setTextVisible(False)
    strip.setObjectName("usageTrack")
    disk_col.addWidget(strip)
    banner = QFrame()
    banner.setObjectName("reclaimBand")
    band = row(spacing=10, margins=(9, 8, 9, 8))
    banner.setLayout(band)
    band.addWidget(_pill_icon("▱", "#29D5F5", 38))
    count_label = QWidget()
    count_stack = column(spacing=1)
    count_label.setLayout(count_stack)
    count_stack.addWidget(label(human_size(this_month), "statBold"))
    count_stack.addWidget(label("recycled this month", "caption"))
    band.addWidget(count_label, 1)
    if previous_month > 0:
        diff = 100 * (this_month - previous_month) / previous_month
        band.addWidget(label(f"{diff:+.0f}% vs last month", "trend"))
    else:
        band.addWidget(label("No prior-month comparison", "caption"))
    disk_col.addWidget(banner)
    disclaimer = label(
        "Game sizes are launcher-reported and may overlap. "
        "Recycle Bin moves do not equal freed space.", "caption", wrap=True)
    disk_col.addWidget(disclaimer)

    def update_drive(_=None):
        drive = drive_picker.currentData()
        try:
            usage = shutil.disk_usage(drive)
        except (OSError, ValueError):
            usage = None
        if usage is None:
            ring.update_amounts(0, 0, 0)
            for amount, percent in legends:
                amount.setText("Unknown")
                percent.setText("—")
            strip.setValue(0)
            return
        reported = sum(max(0, g.size_bytes or 0)
                       for g in window.inventory.games
                       if _game_on_drive(g.install_path, drive))
        # The cap prevents a reported size exceeding the independently
        # measured used space; it is not a claim of true filesystem attribution.
        reported = min(reported, usage.used)
        other = usage.used - reported
        ring.update_amounts(usage.total, usage.free, reported)
        for (text, fraction), (amount, percent) in zip(
            ((human_size(reported), reported / usage.total),
             (human_size(other), other / usage.total),
             (human_size(usage.free), usage.free / usage.total)),
            legends):
            amount.setText(text)
            percent.setText(str(round(fraction * 100)) + "%")
        strip.setMaximum(max(1, usage.total // 1024))
        strip.setValue(usage.used // 1024)
        strip.setAccessibleName(f"{human_size(usage.used)} used of {human_size(usage.total)}")
    drive_picker.currentIndexChanged.connect(update_drive)
    update_drive()
    mid.addWidget(disk_card, 39)

    launch_card, launch_col = panel(padding=13, spacing=4)
    launch_card.setObjectName("dashboardPanel")
    la_head = QWidget()
    la_row = row(spacing=5)
    la_head.setLayout(la_row)
    la_row.addWidget(label("Launchers", "sectionTitle"), 1)
    launch_filter = QComboBox()
    launch_filter.addItems(["All Launchers"] + [x[0] for x in LAUNCHERS])
    launch_filter.setAccessibleName("Filter launchers in overview")
    la_row.addWidget(launch_filter)
    launch_col.addWidget(la_head)
    counts = defaultdict(int)
    reported = defaultdict(int)
    unknown = defaultdict(int)
    for game in window.inventory.games:
        src = game.launcher if len(game.claimed_by) == 1 else "Other"
        if src not in {x[0] for x in LAUNCHERS}:
            src = "Other"
        counts[src] += 1
        if game.size_bytes is None:
            unknown[src] += 1
        else:
            reported[src] += game.size_bytes
    launch_list = QWidget()
    launch_stack = column(spacing=5)
    launch_list.setLayout(launch_stack)
    launch_col.addWidget(launch_list, 1)

    def fill_launchers(_=None):
        from gg_desktop.widgets import destroy_layout
        destroy_layout(launch_stack)
        selected = launch_filter.currentText()
        max_bytes = max((reported[n] for n, _, _ in LAUNCHERS), default=1) or 1
        for name, color, icon in LAUNCHERS:
            if selected not in ("All Launchers", name):
                continue
            line = QWidget()
            layout = row(spacing=6)
            line.setLayout(layout)
            logo = _pill_icon(icon, color, 26)
            logo.setToolTip(name)
            layout.addWidget(logo)
            link = button(name, lambda checked=False, n=name: window._go_launcher(n),
                          kind="launcherLink")
            link.setFixedWidth(111)
            link.setToolTip("Open " + name + " games")
            layout.addWidget(link)
            usage_bar = QProgressBar()
            usage_bar.setRange(0, 1000)
            usage_bar.setValue(round(reported[name] / max_bytes * 1000))
            usage_bar.setTextVisible(False)
            usage_bar.setFixedHeight(8)
            usage_bar.setMinimumWidth(34)
            usage_bar.setAccessibleName(name + " reported game storage")
            usage_bar.setStyleSheet(
                "QProgressBar{background:#26323A;border:0;border-radius:3px}"
                "QProgressBar::chunk{background:" + color + ";border-radius:3px}")
            layout.addWidget(usage_bar, 1)
            storage = human_size(reported[name]) if reported[name] else (
                "Unknown" if unknown[name] else "0 B")
            stat = label(storage, "findingTitle")
            stat.setFixedWidth(69)
            layout.addWidget(stat)
            number = label(str(counts[name]) + " games", "caption")
            number.setMinimumWidth(46)
            layout.addWidget(number)
            launch_stack.addWidget(line)
        launch_stack.addStretch()
    launch_filter.currentIndexChanged.connect(fill_launchers)
    fill_launchers()
    mid.addWidget(launch_card, 36)

    recent, recent_col = panel(padding=12, spacing=4)
    recent.setObjectName("dashboardPanel")
    recent_col.addWidget(_heading(
        "Recent Findings", lambda: window.navigate("Graveyard")))
    findings = window.inventory.graveyard[:5]
    for item in findings:
        color, glyph = _pick_game_icon(item.name)
        recent_col.addWidget(_decorated_item(
            item.name,
            human_size(item.apparent_bytes) + " • " + item.category,
            lambda _=False, key=item.key: window._go_grave_item(key),
            glyph=glyph, color=color, fixed_height=49))
    if not findings:
        recent_col.addWidget(label(
            "Nothing flagged yet. Run Scan PC to find game-related storage.",
            "subtle", wrap=True))
    recent_col.addStretch()
    mid.addWidget(recent, 29)
    page.content.addWidget(middle)

    # Screenshot carousel / Graveyard review queue / Needs Review.
    lower = QWidget()
    lower_line = QHBoxLayout(lower)
    lower_line.setContentsMargins(0, 0, 0, 0)
    lower_line.setSpacing(10)

    capture, cap_col = panel(padding=12, spacing=7)
    capture.setObjectName("dashboardPanel")
    cap_col.addWidget(_heading(
        "Latest Screenshot", lambda: window.navigate("Screenshots"),
        action_text="View All  ›"))
    image = LandscapeArt(169, scene="sunset")
    cap_col.addWidget(image)
    shot_title = label("", "findingTitle", wrap=True)
    shot_caption = label("", "caption", wrap=True)
    cap_col.addWidget(shot_title)
    cap_col.addWidget(shot_caption)
    shots = sorted(window.inventory.screenshots,
                   key=lambda s: (-s.modified, s.path.casefold()))
    index = min(getattr(window, "_dashboard_screenshot_index", 0),
                max(0, len(shots) - 1))
    navigation = QWidget()
    nav = row(spacing=9)
    navigation.setLayout(nav)
    left = button("‹", kind="carouselArrow")
    right = button("›", kind="carouselArrow")
    preview = button("Preview actual image", kind="link")
    nav.addWidget(left)
    nav.addWidget(preview, 1)
    nav.addWidget(right)
    cap_col.addWidget(navigation)

    def update_screenshot():
        nonlocal index
        if not shots:
            shot_title.setText("Illustration  •  No captures found")
            shot_caption.setText("Scan PC to discover screenshots. Personal photos are excluded.")
            preview.setEnabled(False)
        else:
            item = shots[index]
            shot_title.setText(Path(item.path).name)
            modified = datetime.fromtimestamp(item.modified).strftime("%b %d, %Y")
            shot_caption.setText(
                f"{human_size(item.size)}  •  {modified}  •  "
                f"{index+1}/{len(shots)}  •  image not opened automatically")
            preview.setEnabled(True)
        left.setEnabled(index > 0)
        right.setEnabled(index < len(shots) - 1)

    def advance(offset):
        nonlocal index
        index = max(0, min(index + offset, len(shots) - 1))
        window._dashboard_screenshot_index = index
        update_screenshot()

    left.clicked.connect(lambda checked=False: advance(-1))
    right.clicked.connect(lambda checked=False: advance(+1))
    def show_current(_=False):
        if shots:
            window._preview_capture(shots[index])
    preview.clicked.connect(show_current)
    update_screenshot()
    lower_line.addWidget(capture, 31)

    queue, queue_col = panel(padding=12, spacing=6)
    queue.setObjectName("dashboardPanel")
    entries = list(window.inventory.graveyard)
    queue_col.addWidget(_heading(
        "Graveyard Review Queue", lambda: window.navigate("Graveyard"),
        action_text="See All  ›", count=len(entries)))
    selections = []
    for entry in entries[:4]:
        line = QFrame()
        line.setObjectName("queueRow")
        wrap = row(spacing=5, margins=(3, 3, 3, 3))
        line.setLayout(wrap)
        box = QCheckBox()
        box.setAccessibleName("Select " + entry.name)
        box.setEnabled(entry.can_recycle and entry.old_file is not None)
        box.setToolTip("Protected items cannot be selected for recycling." if
                       not box.isEnabled() else "Will require confirmation and Windows recovery tests.")
        wrap.addWidget(box)
        color, glyph = _pick_game_icon(entry.name)
        wrap.addWidget(_pill_icon(glyph, color, 32))
        information = QWidget()
        info_layout = column(spacing=1)
        information.setLayout(info_layout)
        show_item = button(entry.name[:42],
                           lambda checked=False, e=entry: window._inspect_grave_entry(e),
                           kind="queueLink")
        show_item.setToolTip(entry.finding)
        info_layout.addWidget(show_item)
        info_layout.addWidget(label(
            human_size(entry.apparent_bytes) + "  •  " + entry.category,
            "caption", wrap=False))
        wrap.addWidget(information, 1)
        more = button("⋮", kind="ellipsis")
        wrap.addWidget(more)
        def actions_for(e, menu_anchor):
            menu = QMenu(menu_anchor)
            menu.addAction("View details…",
                           lambda: window._inspect_grave_entry(e))
            menu.addAction("See in Graveyard",
                           lambda: window._go_grave_item(e.key))
            menu.addSeparator()
            if e.category == "Old game screenshot":
                menu.addAction("Preview screenshot",
                               lambda: window._preview_grave_image(e))
            else:
                move = menu.addAction(
                    "Move to Recycle Bin…",
                    lambda: window._approve_recycle([e]))
                move.setEnabled(e.can_recycle and e.old_file is not None)
            protection, explanation = protection_action(
                e.path, list(window.settings.get("never_touch", [])))
            if protection == "Protect":
                menu.addAction(
                    "Protect (Never Touch)",
                    lambda: window._set_personal_protection(
                        e.path, protect=True, return_route="Graveyard"))
            elif protection == "Unprotect":
                menu.addAction("Unprotect this item…",
                               lambda: window._unprotect_grave(e))
            else:
                locked = menu.addAction("Built-in or inherited protection")
                locked.setEnabled(False)
            menu.addAction("Open containing folder",
                           lambda: window._open_folder(str(Path(e.path).parent)))
            menu.exec(menu_anchor.mapToGlobal(menu_anchor.rect().bottomLeft()))
        more.clicked.connect(
            lambda checked=False, e=entry, anchor=more: actions_for(e, anchor))
        queue_col.addWidget(line)
        selections.append((box, entry))
    if not entries:
        queue_col.addWidget(label(
            "No items waiting for review. Nothing is deleted automatically.",
            "subtle", wrap=True))
    queue_col.addStretch()
    queue_controls = QWidget()
    qtools = row(spacing=7)
    queue_controls.setLayout(qtools)
    choose_all = QCheckBox("Select All")
    eligible = [box for box, _ in selections if box.isEnabled()]
    choose_all.setEnabled(bool(eligible))
    choose_all.toggled.connect(
        lambda checked: [box.setChecked(checked) for box in eligible])
    qtools.addWidget(choose_all, 1)
    qtools.addWidget(button(
        "↶  Restore", lambda: window.navigate("Undo Center"),
        kind="secondary"))
    recycle = button(
        "♱  Delete Selected",
        lambda: window._approve_recycle(
            [entry for box, entry in selections if box.isChecked()]),
        kind="danger")
    recycle.setToolTip("Move eligible files to the Recycle Bin, never permanent delete.")
    recycle.setEnabled(bool(eligible))
    qtools.addWidget(recycle)
    queue_col.addWidget(queue_controls)
    lower_line.addWidget(queue, 42)

    alert, alert_col = panel(kind="alertCard", padding=12, spacing=8)
    unresolved = [m for m in window.inventory.mods
                  if any(word in
                         (str(getattr(m, "status", "")) + " " +
                          str(getattr(m, "source", ""))).casefold()
                         for word in ("unknown", "unmatched", "uncertain", "possible", "orphan"))]
    if not unresolved:
        unresolved = list(window.inventory.mods[:1])
    first = unresolved[0] if unresolved else None
    alert_col.addWidget(_heading("Needs Review", count=len(unresolved)))
    if first is not None:
        alert_col.addWidget(label("⚠  Large mod folder detected" if
                                    getattr(first, "apparent_bytes", 0) >= 1_000_000_000
                                    else "⚠  Mod location needs review",
                                    "findingTitle", wrap=True))
        alert_col.addWidget(label(
            str(getattr(first, "name", "Mod storage"))[:80] + "  •  " +
            human_size(getattr(first, "apparent_bytes", 0)) +
            "  •  Status: " + str(getattr(first, "status", "Unverified")),
            "subtle", wrap=True))
    else:
        alert_col.addWidget(label(
            "No unresolved mod locations. Protected game content remains untouched.",
            "subtle", wrap=True))
    alert_col.addWidget(LandscapeArt(112, scene="fog"))
    alert_controls = QWidget()
    alert_row = row(spacing=7)
    alert_controls.setLayout(alert_row)
    review_button = button(
        "Review Files", lambda: window.navigate("Mods"), kind="primary")
    alert_row.addWidget(review_button, 1)
    add_button = button(
        "Add to Graveyard",
        lambda checked=False, m=first: _enqueue_mod(window, m) if m else None)
    add_button.setEnabled(first is not None)
    add_button.setToolTip("Mark a mod for review only. Never removes protected content.")
    alert_row.addWidget(add_button, 1)
    alert_col.addWidget(alert_controls)
    lower_line.addWidget(alert, 27)
    page.content.addWidget(lower)

    page.content.addWidget(label(
        "All totals are from your own PC or Game Grave's local history. "
        "Illustrations are decorative. Recycle Bin moves are not confirmed freed disk space.",
        "caption", wrap=True))
