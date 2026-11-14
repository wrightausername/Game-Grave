"""The grouped sidebar (Qt): a heading per group, each tab as one button with its name and one plain line under it.

The layout and wording live in nav_groups.py. Buttons are QPushButtons stored in window.nav_buttons by route key, so
navigation, the active highlight and the optional AI Assistant switch keep working the way they did.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from gg_desktop import nav_groups
from gg_desktop.reference_widgets import ROUTE_SYMBOLS, icon

ITEM_HEIGHT = 40

STYLE = """
QScrollArea#navScroll, QWidget#navList { background: transparent; border: none; }
QScrollArea#navScroll QScrollBar:vertical { width: 6px; background: transparent; margin: 2px; }
QScrollArea#navScroll QScrollBar::handle:vertical { background: #2A3541; border-radius: 3px; min-height: 30px; }
QScrollArea#navScroll QScrollBar::add-line:vertical, QScrollArea#navScroll QScrollBar::sub-line:vertical { height: 0; }
QLabel#navGroup { color: #7E8C9B; font-size: 10px; font-weight: 800; letter-spacing: 1.6px; padding: 0 0 0 16px; }
QPushButton#navItem { border: none; background: transparent; border-radius: 9px; padding: 0; text-align: left; }
QPushButton#navItem:hover { background: #162230; }
QPushButton#navItem[active="true"] { background: #2A171F; border-left: 3px solid #FF4357; }
QPushButton#navItem:focus { border: 1px solid #42D4F2; }
QLabel#navTitle { color: #C9D4E0; font-size: 13px; font-weight: 600; background: transparent; }
QLabel#navSub { color: #7E8C9B; font-size: 10.5px; background: transparent; }
QLabel#navTitle[active="true"] { color: #FFFFFF; }
QLabel#navSub[active="true"] { color: #C9A9B2; }
"""


class NavItem(QPushButton):
    def __init__(self, route, on_click):
        super().__init__()
        self.route = route
        self.setObjectName("navItem")
        self.setFixedHeight(ITEM_HEIGHT)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(nav_groups.display_name(route) + " page")
        sub = nav_groups.subtitle(route)
        self.setToolTip(nav_groups.display_name(route) + (": " + sub if sub else ""))
        line = QHBoxLayout(self)
        line.setContentsMargins(13, 3, 8, 3)
        line.setSpacing(11)
        self.glyph = QLabel()
        self.glyph.setFixedSize(22, 22)
        self.glyph.setPixmap(icon(ROUTE_SYMBOLS.get(route, "game"), size=22).pixmap(22, 22))
        line.addWidget(self.glyph, 0, Qt.AlignVCenter)
        words = QVBoxLayout()
        words.setSpacing(0)
        words.setContentsMargins(0, 0, 0, 0)
        self.title = QLabel(nav_groups.display_name(route))
        self.title.setObjectName("navTitle")
        self.sub = QLabel(sub)
        self.sub.setObjectName("navSub")
        for widget in (self.title, self.sub):
            widget.setTextFormat(Qt.PlainText)
        for widget in (self.glyph, self.title, self.sub):
            widget.setAttribute(Qt.WA_TransparentForMouseEvents)
        words.addWidget(self.title)
        words.addWidget(self.sub)
        line.addLayout(words, 1)
        self.clicked.connect(lambda _checked=False: on_click(route))

    def set_active(self, active: bool):
        for widget in (self, self.title, self.sub):
            if widget.property("active") != active:
                widget.setProperty("active", active)
                widget.style().unpolish(widget)
                widget.style().polish(widget)


def build(window, rail_layout):
    """Fill the rail under the logo. Returns {route: NavItem} in sidebar order."""
    scroll = QScrollArea()
    scroll.setObjectName("navScroll")
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setStyleSheet(STYLE)
    holder = QWidget()
    holder.setObjectName("navList")
    holder.setStyleSheet(STYLE)
    column = QVBoxLayout(holder)
    column.setContentsMargins(6, 0, 6, 6)
    column.setSpacing(1)
    buttons = {}
    groups = {}
    for index, (heading, items) in enumerate(nav_groups.GROUPS):
        if index:
            column.addSpacing(9)
        title = QLabel(heading.upper())
        title.setObjectName("navGroup")
        title.setFixedHeight(18)
        column.addWidget(title)
        groups[heading] = title
        for route, _sub in items:
            control = NavItem(route, window.navigate)
            control.set_active(route == window.current_route)
            column.addWidget(control)
            buttons[route] = control
    column.addStretch(1)
    scroll.setWidget(holder)
    rail_layout.addWidget(scroll, 1)
    window.nav_scroll, window.nav_groups = scroll, groups
    return buttons


def sync_groups(window):
    """A heading whose tabs are all hidden (AI Assistant off is never the only one) hides with them."""
    for heading, items in nav_groups.GROUPS:
        label = getattr(window, "nav_groups", {}).get(heading)
        if label is None:
            continue
        label.setVisible(any(not window.nav_buttons[route].isHidden() for route, _ in items if route in window.nav_buttons))
