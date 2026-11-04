"""Owner-locked cinematic Settings control center with real local actions.

This dashboard is not a decorative settings screenshot. Navigation opens the
existing on-disk preference controls. Unimplemented publisher services, FPS
measurements, subscriptions and launcher connections are never faked.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget,
    QStackedWidget, QVBoxLayout, QWidget,
)
from gg_desktop.widgets import button, label, row
from gg_desktop.visuals import nav_icon


def _status_page(heading, explanation, actions):
    frame = QFrame()
    frame.setObjectName("approvedSettingsStatusPage")
    col = QVBoxLayout(frame)
    col.setContentsMargins(15, 16, 15, 16)
    col.setSpacing(12)
    col.addWidget(label(heading, "sectionTitle"))
    col.addWidget(label(explanation, "subtle", wrap=True))
    for text, callback in actions:
        col.addWidget(button(text, callback))
    col.addStretch()
    return frame


def _card(heading, info, facts, tone, route_icon, actions, *, compact=False):
    """A native, data-backed settings tile with real navigation/actions."""
    shell = QFrame()
    shell.setObjectName("ggAccentPanel")
    shell.setProperty("accent", tone)
    shell.setMinimumHeight(190 if compact else 244)
    col = QVBoxLayout(shell)
    col.setContentsMargins(14, 12, 14, 12)
    col.setSpacing(7)
    title_bar = QWidget()
    headings = QHBoxLayout(title_bar)
    headings.setContentsMargins(0, 0, 0, 0)
    headings.setSpacing(8)
    icon = QLabel()
    icon.setPixmap(nav_icon(route_icon).pixmap(27, 27))
    icon.setFixedSize(28, 28)
    headings.addWidget(icon)
    text_title = label(heading, "sectionTitle", wrap=True)
    headings.addWidget(text_title, 1)
    col.addWidget(title_bar)
    description = label(info, "caption", wrap=True)
    col.addWidget(description)
    for name, value, color in facts:
        line = QWidget()
        line_layout = QHBoxLayout(line)
        line_layout.setContentsMargins(0, 0, 0, 0)
        line_layout.setSpacing(5)
        left = QLabel(str(name))
        left.setStyleSheet("background:transparent;color:#C9D4DF;font-size:12px;")
        left.setWordWrap(True)
        right = QLabel(str(value))
        right.setStyleSheet(
            "background:transparent;color:" + color +
            ";font-size:12px;font-weight:750;")
        right.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        right.setWordWrap(True)
        line_layout.addWidget(left, 2)
        line_layout.addWidget(right, 1)
        col.addWidget(line)
    col.addStretch(1)
    for title, callback in actions:
        col.addWidget(button(title, callback))
    return shell


def _mini_card(title, facts, tone, route_icon, action=None):
    """Compact reference-style status column with verified local values."""
    frame = QFrame()
    frame.setObjectName("ggAccentPanel")
    frame.setProperty("accent", tone)
    col = QVBoxLayout(frame)
    col.setContentsMargins(12, 8, 12, 8)
    col.setSpacing(3)
    heading = QWidget()
    line = QHBoxLayout(heading)
    line.setContentsMargins(0, 0, 0, 0)
    icon = QLabel()
    icon.setFixedSize(22, 22)
    icon.setPixmap(nav_icon(route_icon).pixmap(21, 21))
    line.addWidget(icon)
    title_widget = label(title, "sectionTitle")
    title_widget.setStyleSheet(
        "font-size:14px;color:#F2F5F8;font-weight:800;background:transparent;")
    line.addWidget(title_widget, 1)
    col.addWidget(heading)
    for key, value in facts:
        pair = QWidget()
        item = QHBoxLayout(pair)
        item.setContentsMargins(0,0,0,0)
        item.setSpacing(4)
        left = QLabel(str(key))
        left.setStyleSheet("color:#B9C6D2;font-size:11px;background:transparent;")
        right = QLabel(str(value))
        right.setStyleSheet(
            "color:#D6E5F0;font-size:11px;font-weight:800;background:transparent;")
        right.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        item.addWidget(left, 1)
        item.addWidget(right)
        col.addWidget(pair)
    if action:
        col.addWidget(button(action[0], action[1]))
    return frame


def render_approved_settings(window):
    window.settings_page()
    page = window.page
    page.content.setContentsMargins(11, 7, 11, 16)
    page.content.setSpacing(8)
    navs = page.findChildren(QListWidget, "settingsCategories")
    stacks = page.findChildren(QStackedWidget, "settingsPanels")
    if not navs or not stacks:
        raise RuntimeError("Settings category controls unavailable")
    nav, stack = navs[0], stacks[0]
    if stack.count() != 8:
        raise RuntimeError("Original Settings control count changed")
    nav.hide()

    perf_idx = stack.addWidget(_status_page(
        "GAMING PERFORMANCE GUARD",
        "Game-aware suspension and low CPU/disk priority are safety "
        "requirements, not optional high-impact background features. "
        "Actual FPS and 1%-low results are not measured here.",
        (("Configure scans", lambda: select(1)),
         ("Open Games", lambda: window.navigate("Games")))))
    notices_idx = stack.addWidget(_status_page(
        "NOTIFICATIONS & READY ROOM",
        "Only local scan warnings are available in this engineering preview. "
        "Official Patch Watch publisher feeds have not been connected.",
        (("Open Ready Room", lambda: window.navigate("Ready Room")),
         ("Review scan warnings", window._show_notifications))))

    settings_root = stack.parentWidget()
    overview = None
    # The original six summary cards are duplicated by the faithful, fuller
    # control-center workspace below; keep their real preference widgets.
    for i in range(page.content.count()):
        item = page.content.itemAt(i)
        widget = item.widget() if item else None
        if widget is None:
            continue
        if widget is not settings_root and widget is not page.content.itemAt(0).widget():
            if widget.findChildren(QGridLayout) and not widget.findChildren(QStackedWidget):
                overview = widget
                break
    if overview is not None:
        overview.hide()

    tabs = QFrame()
    tabs.setObjectName("approvedSettingsTabs")
    controls = row(spacing=6, margins=(3, 2, 3, 2))
    tabs.setLayout(controls)
    names = (
        ("General", 0), ("Libraries", 1), ("Safety", 2),
        ("Performance", perf_idx), ("AI Assistant", 4),
        ("Notifications", notices_idx), ("Advanced", 6),
    )

    def select(index):
        if index < 8:
            nav.setCurrentRow(index)
        stack.setCurrentIndex(index)
        window._settings_category_index = index

    choices = []
    for name, index in names:
        action = button(name, lambda _=False, target=index: select(target),
                        kind="approvedSettingsTab")
        action.setAccessibleName("Settings category " + name)
        action.setMinimumHeight(33)
        action.setProperty("categoryIndex", index)
        controls.addWidget(action, 1)
        choices.append(action)
    page.content.insertWidget(1, tabs)

    advanced = stack.widget(6)
    if advanced is not None and advanced.layout() is not None:
        for name, index in (
            ("Capture folders", 3),
            ("Appearance & Privacy", 5),
            ("About / App Version", 7),
        ):
            advanced.layout().addWidget(
                button(name, lambda _=False, target=index: select(target)))

    dashboard = QWidget()
    grid = QGridLayout(dashboard)
    grid.setSpacing(10)
    grid.setContentsMargins(1, 2, 1, 2)
    data = dict(window.settings)
    ai_on = data.get("ai_assistant_enabled") is True
    from ai_bundle import is_ai_installed
    ai_installed = is_ai_installed()
    library_roots = len(data.get("steam_extra_roots", [])) + len(
        data.get("other_library_roots", []))
    never_touch = len(data.get("never_touch", []))
    captures = len(data.get("screenshot_roots", []))
    scan_folder = str(data.get("scan_folder", "")).strip()
    scan_label = Path(scan_folder).name if scan_folder else "Not set"

    cards = [
        _card("Libraries & Detection",
              "Verified launcher records and owner-selected scan roots.",
              (("Extra game roots", str(library_roots), "#74D9E9"),
               ("Capture locations", str(captures), "#BFA7E9"),
               ("Old Files scope", scan_label, "#D9E2EC")),
              "cyan", "Games",
              (("Manage libraries", lambda: select(1)),)),
        _card("Protection & Cleanup",
              "Built-in protection cannot be bypassed.",
              (("Recycle Bin", "Required", "#55D9AA"),
               ("Delete confirmation", "Required", "#55D9AA"),
               ("Never Touch rules", str(never_touch), "#EAC090")),
              "amber", "Graveyard",
              (("Manage protection", lambda: select(2)),)),
        _card("Gaming Performance",
              "No intrusive game overlays or continuous heavy scans.",
              (("Pause heavy work", "On", "#55D9AA"),
               ("Background priority", "Low", "#55D9AA"),
               ("FPS measured here", "Not available", "#EBC18B")),
              "red", "Game DNA",
              (("Performance details", lambda: select(perf_idx)),)),
        _card("System Status",
              "Health indicators from this preview, not invented telemetry.",
              (("CPU / memory", "Not sampled", "#D0B9DE"),
               ("Disk activity", "Not sampled", "#D0B9DE"),
               ("Edition", "Engineering preview", "#EEB97C")),
              "green", "Other Storage",
              (("View local scans", window._show_notifications),), compact=True),
        _card("AI Assistant",
              "Optional local help. Off until explicitly enabled.",
              (("AI", "On" if ai_on else "Off",
                "#58DCB1" if ai_on else "#F2BE87"),
               ("Local engine", "Installed" if ai_installed else "Not installed",
                "#58DCB1" if ai_installed else "#F2BE87")),
              "purple", "AI Assistant",
              (("Configure local AI", lambda: select(4)),)),
        _card("Ready Room & Notices",
              "Local warnings are real; official patch feeds are pending.",
              (("Scan notifications", "On demand", "#6ED2ED"),
               ("Official Patch Watch", "Not connected", "#F0BD80")),
              "amber", "Ready Room",
              (("Notification details", lambda: select(notices_idx)),)),
        _card("Privacy & Data",
              "Your game list, file paths and saves stay local.",
              (("File uploads", "None", "#55D9AA"),
               ("Optional AI", "Local only", "#72D5EA"),
               ("Delete authority", "User only", "#D5B2EA")),
              "green", "Settings",
              (("Open privacy controls", lambda: select(5)),)),
        _card("Paths & Quick Actions",
              "Open the existing tools; no fake switches.",
              (("Scan locations", str(library_roots + (1 if scan_folder else 0)),
                "#78D6E9"),),
              "cyan", "Old Files",
              (("Scan now", window.start_scan),
               ("Backup & restore", lambda: select(6))), compact=True),
    ]
    # The locked reference has THREE large functional columns and a narrow
    # stack of compact status panels. Equal 4x2 cards were visibly wrong.
    if window.devicePixelRatioF() >= 1.12:
        # At 125/150% DPI use scrollable two-column layout with no clipping.
        for i, card in enumerate(cards):
            grid.addWidget(card, i // 2, i % 2)
        for i in range(2):
            grid.setColumnStretch(i, 1)
    else:
        # Main top row: libraries / protection / gaming performance.
        for index in range(3):
            cards[index].setMinimumHeight(285)
            grid.addWidget(cards[index], 0, index)
        # Bottom row: optional AI / notices / privacy.
        for index in range(3):
            cards[index + 4].setMinimumHeight(226)
            grid.addWidget(cards[index + 4], 1, index)

        sidebar_top = QWidget()
        narrow_top = QVBoxLayout(sidebar_top)
        narrow_top.setContentsMargins(0,0,0,0)
        narrow_top.setSpacing(7)
        narrow_top.addWidget(_mini_card(
            "System Status",
            (("Scan", "Complete" if window.inventory.scanned_at else "Not run"),
             ("CPU/FPS", "Not sampled")),
            "red", "Other Storage",
            ("Review", window._show_notifications)))
        narrow_top.addWidget(_mini_card(
            "Storage Paths",
            (("Extra roots", str(library_roots)),
             ("Old Files", scan_label)),
            "amber", "Old Files",
            ("Manage", lambda: select(1))))
        narrow_top.addWidget(_mini_card(
            "Connected Services",
            (("Steam / Epic / EA", "Scan evidence only"),
             ("Publisher feeds", "Not connected")),
            "cyan", "Games"))
        grid.addWidget(sidebar_top, 0, 3)

        sidebar_bottom = QWidget()
        narrow_bottom = QVBoxLayout(sidebar_bottom)
        narrow_bottom.setContentsMargins(0,0,0,0)
        narrow_bottom.setSpacing(7)
        narrow_bottom.addWidget(_mini_card(
            "License / Edition",
            (("Current", "Unsigned preview"),),
            "amber", "Settings"))
        narrow_bottom.addWidget(cards[7], 1)
        grid.addWidget(sidebar_bottom, 1, 3)
        for idx, stretch in enumerate((4, 4, 4, 3)):
            grid.setColumnStretch(idx, stretch)
    page.content.insertWidget(2, dashboard)

    def active(_index=None):
        selected = stack.currentIndex()
        highlight = 6 if selected in (3, 5, 7) else selected
        for tab in choices:
            tab.setProperty("active", tab.property("categoryIndex") == highlight)
            tab.style().unpolish(tab)
            tab.style().polish(tab)
        dashboard.setVisible(selected == 0)
        # Original General preference remains below the overview in General.
    stack.currentChanged.connect(active)
    target = getattr(window, "_settings_category_index", 0)
    select(target if 0 <= target < stack.count() else 0)
    active()
    page.content.addWidget(label(
        "Changes to actual preferences save when selected. Game Grave never "
        "reports simulated connected services, FPS measurements, or Pro licenses.",
        "caption", wrap=True))
    return page
