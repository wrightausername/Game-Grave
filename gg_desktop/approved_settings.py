"""Locked Settings control-center shell over real local preferences.

The seven owner-approved categories are visible. Original preference controls
remain reachable, including Captures, Privacy and About from Advanced.
Performance and Notifications are honest read-only status views until a real
user-configurable setting or publisher feed exists.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QListWidget, QStackedWidget, QVBoxLayout,
)
from gg_desktop.widgets import button, row, label


def _status_page(heading, explanation, actions):
    frame = QFrame()
    frame.setObjectName("approvedSettingsStatusPage")
    contents = QVBoxLayout(frame)
    contents.setContentsMargins(15, 16, 15, 16)
    contents.setSpacing(12)
    contents.addWidget(label(heading, "sectionTitle"))
    contents.addWidget(label(explanation, "subtle", wrap=True))
    for text, callback in actions:
        contents.addWidget(button(text, callback))
    contents.addStretch()
    return frame


def render_approved_settings(window):
    window.settings_page()
    page = window.page
    page.content.setContentsMargins(11, 7, 11, 16)
    page.content.setSpacing(9)
    navs = page.findChildren(QListWidget, "settingsCategories")
    stacks = page.findChildren(QStackedWidget, "settingsPanels")
    if not navs or not stacks:
        raise RuntimeError("Settings category controls unavailable")
    nav, stack = navs[0], stacks[0]
    if stack.count() != 8:
        raise RuntimeError("Original Settings controls changed unexpectedly")
    nav.hide()

    # Use working controls rather than fake screenshot toggles. These two
    # status tabs are informational and never weaken the FPS or safety guard.
    performance_index = stack.addWidget(_status_page(
        "GAMING PERFORMANCE GUARD",
        "The guard is always active in this preview: low CPU and disk priority "
        "during scans, cooperative pause while a game is detected, and no "
        "game injection or overlay. Real game FPS and 1%-low benchmarks "
        "are still required before a stable release.",
        (
            ("Open scanning preferences",
             lambda: _select(1)),
            ("Open Games", lambda: window.navigate("Games")),
        )))
    notifications_index = stack.addWidget(_status_page(
        "NOTIFICATIONS & READY ROOM",
        "Game Grave shows verified local scan warnings on demand. Official "
        "publisher Patch Watch feeds have not been connected; no patch "
        "warnings or game compatibility verdicts are invented.",
        (
            ("Open Ready Room", lambda: window.navigate("Ready Room")),
            ("View scan status", window._show_notifications),
        )))

    tabs = QFrame()
    tabs.setObjectName("approvedSettingsTabs")
    line = row(spacing=5, margins=(5, 5, 5, 5))
    tabs.setLayout(line)
    names = (
        ("General", 0), ("Libraries", 1), ("Safety", 2),
        ("Performance", performance_index), ("AI Assistant", 4),
        ("Notifications", notifications_index), ("Advanced", 6),
    )

    def _select(index):
        if index < 8:
            nav.setCurrentRow(index)
        stack.setCurrentIndex(index)
        window._settings_category_index = index

    buttons = []
    for title, index in names:
        tab = button(title, lambda _=False, i=index: _select(i),
                     kind="approvedSettingsTab")
        tab.setAccessibleName("Settings category " + title)
        tab.setProperty("categoryIndex", index)
        tab.setMinimumHeight(27)
        line.addWidget(tab, 1)
        buttons.append(tab)
    page.content.insertWidget(1, tabs)

    advanced = stack.widget(6)
    if advanced is not None and advanced.layout() is not None:
        for title, destination in (
            ("Captures settings", 3),
            ("Appearance & Privacy", 5),
            ("About / App Version", 7),
        ):
            advanced.layout().addWidget(
                button(title, lambda _=False, i=destination: _select(i)))

    def active(_index=None):
        selected = stack.currentIndex()
        # Captures / Privacy / About live behind the Advanced category.
        if selected in (3, 5, 7):
            selected = 6
        for tab in buttons:
            tab.setProperty("active", tab.property("categoryIndex") == selected)
            tab.style().unpolish(tab)
            tab.style().polish(tab)
    stack.currentChanged.connect(active)
    desired = getattr(window, "_settings_category_index", 0)
    if 0 <= desired < stack.count():
        _select(desired)
    active()
    page.content.addWidget(label(
        "Settings changes save when selected. Built-in game, system and "
        "save protections cannot be disabled. Performance and notifications "
        "report actual capabilities, not mockup values.",
        "caption", wrap=True))
    return page
