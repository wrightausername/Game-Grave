"""Fix Kit: every tool for a broken or risky game in one tab (owner instruction, 2026-11-14, grouped sidebar with Fix Kit).

Mod Bisect and Resurrection Kit are cards that open the existing screens (Mods > Bisect, the kit setup / restore windows
and the kit menu). Black Box, Autopsy and Exhume moved here from Ready Room unchanged: the same panels, built by their
own modules, with the same rules. Nothing new is changed on the PC from this page.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout

from gg_desktop.header_banner import HeaderBannerArtwork
from gg_desktop.reference_widgets import icon

SUBTITLE = "Crashes, backups and rollbacks for your games, all in one place."

CARD_STYLE = """
QFrame#fixCard { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 rgba(255,67,87,30), stop:.45 #0B1219, stop:1 #080E14);
                 border: 1px solid #3A2A31; border-radius: 12px; }
QFrame#fixCard:hover { border: 1px solid #7A3644; }
QLabel#fixCardTitle { font-size: 17px; font-weight: 800; color: #F6FAFF; background: transparent; }
QLabel#fixCardText { font-size: 12.5px; color: #B9C6D3; background: transparent; }
QLabel#fixIntro { font-size: 13px; color: #C9D4E0; }
QLabel#fixSection { color: #8C9AA9; font-size: 11px; font-weight: 800; letter-spacing: 1.6px; }
"""

CARDS = (
    ("bisect", "Mod Bisect", "mods",
     "A game crashes with mods on? Mod Bisect finds the mod causing it, one test launch at a time.",
     (("Open Mod Bisect", "bisect", True),)),
    ("kit", "Resurrection Kit", "grave",
     "Back up a whole game: the install, your saves and the load order, so you can bring it back later.",
     (("Set up a kit", "kit_setup", True), ("Restore a game", "kit_restore", False), ("More kit tools", "kit_menu", False))),
)


def open_bisect(window):
    """Mods > Bisect. Bisect lives in the detailed Mods view, so it is shown for this visit without changing the saved
    choice between My Mods and Advanced."""
    window.navigate("Mods")
    try:
        from gg_desktop import mymods_ui
        if mymods_ui.mode(window) != "advanced" and hasattr(window, "mymods_view"):
            window.mymods_view.setVisible(False)
            window.mymods_back.setVisible(True)
            for widget in window.mymods_advanced:
                widget.setVisible(True)
        window._set_mod_tab("Bisect")
    except Exception:
        pass


def run(window, key):
    if key == "bisect":
        open_bisect(window)
    elif key == "kit_setup":
        from gg_desktop import kit_easy_ui
        kit_easy_ui.open_easy_setup(window)
    elif key == "kit_restore":
        from gg_desktop import kit_easy_ui
        kit_easy_ui.open_easy_restore(window)
    elif key == "kit_menu":
        from gg_desktop import tools_actions
        tools_actions.open_kit_menu(window)


def card(window, title, glyph, text, actions):
    frame = QFrame()
    frame.setObjectName("fixCard")
    frame.setAccessibleName(title)
    frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    box = QVBoxLayout(frame)
    box.setContentsMargins(18, 16, 18, 16)
    box.setSpacing(10)
    head = QHBoxLayout()
    head.setSpacing(12)
    mark = QLabel()
    mark.setPixmap(icon(glyph, "#FF4357", 30).pixmap(30, 30))
    mark.setFixedSize(30, 30)
    head.addWidget(mark)
    name = QLabel(title)
    name.setObjectName("fixCardTitle")
    head.addWidget(name, 1)
    box.addLayout(head)
    words = QLabel(text)
    words.setObjectName("fixCardText")
    words.setWordWrap(True)
    box.addWidget(words)
    box.addStretch(1)
    line = QHBoxLayout()
    line.setSpacing(8)
    buttons = {}
    for caption, key, primary in actions:
        control = QPushButton(caption)
        if primary:
            control.setObjectName("primary")
        control.setAccessibleName(caption)
        control.setCursor(Qt.PointingHandCursor)
        control.clicked.connect(lambda _=False, k=key: run(window, k))
        line.addWidget(control)
        buttons[key] = control
    line.addStretch(1)
    box.addLayout(line)
    return frame, buttons


def section(text):
    widget = QLabel(text.upper())
    widget.setObjectName("fixSection")
    return widget


def build(window):
    self = window
    page = self._insight_page("Fix Kit", SUBTITLE, "undo", "wrench", 66)
    page.banner_artwork = HeaderBannerArtwork(self, page, page.content.itemAt(0).widget(), route="Fix Kit",
                                              scene="undo", source=(900, 0, 380, 110), excluded=((1090, 0, 190, 40),))
    page.setStyleSheet(CARD_STYLE)
    intro = QLabel("Something broke, or you want a safety net before you change things? Start here.")
    intro.setObjectName("fixIntro")
    intro.setWordWrap(True)
    page.content.addWidget(intro)

    page.content.addWidget(section("Fix a game"))
    cards = QHBoxLayout()
    cards.setSpacing(10)
    page.fix_buttons = {}
    for _key, title, glyph, text, actions in CARDS:
        frame, buttons = card(self, title, glyph, text, actions)
        cards.addWidget(frame, 1)
        page.fix_buttons.update(buttons)
    page.content.addLayout(cards)

    page.content.addWidget(section("After a crash or a bad update"))
    from gg_desktop.ready_room import ReadyPanel
    from gg_desktop.blackbox_ui import build_panel as build_blackbox
    from gg_desktop.autopsy_ui import build_panel as build_autopsy
    from gg_desktop.exhume_ui import build_panel as build_exhume
    page.blackbox = build_blackbox(ReadyPanel, self)
    page.autopsy = build_autopsy(ReadyPanel, self)
    page.exhume = build_exhume(ReadyPanel, self)
    for panel in (page.blackbox, page.autopsy, page.exhume):
        page.content.addWidget(panel)
    page.content.addStretch(1)
    return page
