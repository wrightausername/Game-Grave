"""Bring real Settings controls into the owner-locked horizontal control-center shell.

No decorative toggles, fake launcher connections, or bypass of built-in
protection. The eight existing functional categories stay accessible.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QPushButton, QStackedWidget, QWidget,
)
from gg_desktop.widgets import button, row, label


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
        raise RuntimeError("Settings category count changed unexpectedly")
    nav.hide()
    tabs = QFrame()
    tabs.setObjectName("approvedSettingsTabs")
    line = row(spacing=5, margins=(5, 5, 5, 5))
    tabs.setLayout(line)
    names = (
        ("General", 0), ("Libraries", 1), ("Safety", 2),
        ("Captures", 3), ("AI Assistant", 4),
        ("Privacy", 5), ("Advanced", 6),
    )
    buttons = []
    for title, index in names:
        tab = button(title, lambda _=False, i=index: nav.setCurrentRow(i),
                     kind="approvedSettingsTab")
        tab.setAccessibleName("Settings category " + title)
        tab.setProperty("categoryIndex", index)
        tab.setMinimumHeight(27)
        line.addWidget(tab, 1)
        buttons.append(tab)
    page.content.insertWidget(1, tabs)

    advanced = stack.widget(6)
    if advanced is not None and advanced.layout() is not None:
        advanced.layout().addWidget(
            button("About / App Version",
                   lambda: nav.setCurrentRow(7)))

    def active(_index=None):
        selected = nav.currentRow()
        for tab in buttons:
            tab.setProperty("active", tab.property("categoryIndex") == selected)
            tab.style().unpolish(tab)
            tab.style().polish(tab)
        if selected == 7:
            # Advanced is the owning section for the About subpage.
            buttons[-1].setProperty("active", True)
            buttons[-1].style().unpolish(buttons[-1])
            buttons[-1].style().polish(buttons[-1])
    nav.currentRowChanged.connect(active)
    active()
    page.content.addWidget(label(
        "Every control above opens real local settings. Individual changes save "
        "when selected; built-in game, system and save protections cannot be disabled.",
        "caption", wrap=True))
    return page
