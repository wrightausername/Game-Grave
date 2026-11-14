"""The grouped sidebar (Qt): dropdown headings (one open at a time), each tab with its name and one plain line under it.

Owner, 2026-11-14: "make it sleeker and less cluttered on the left ... click it once and it drops down and minimizes".

The layout and wording live in nav_groups.py. Buttons are QPushButtons stored in window.nav_buttons by route key, so
navigation, the active highlight and the optional AI Assistant switch keep working the way they did.
"""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from gg_desktop import nav_groups
from gg_desktop.reference_widgets import ROUTE_SYMBOLS, icon

ITEM_WIDTH = 195   # fixed, so rows never change size when the scroll bar comes and goes
SLIDE_MS = 160
ITEM_HEIGHT = 40   # the QSS above repeats it: the app's global QPushButton min-height would otherwise win

STYLE = """
QScrollArea#navScroll, QWidget#navList { background: transparent; border: none; }
QScrollArea#navScroll QScrollBar:vertical { width: 6px; background: transparent; margin: 2px; }
QScrollArea#navScroll QScrollBar::handle:vertical { background: #2A3541; border-radius: 3px; min-height: 30px; }
QScrollArea#navScroll QScrollBar::add-line:vertical, QScrollArea#navScroll QScrollBar::sub-line:vertical { height: 0; }
QPushButton#navHead { border: none; background: transparent; border-radius: 7px; padding: 0; text-align: left;
                      min-height: 28px; max-height: 28px; }
QPushButton#navHead:hover { background: #121A23; }
QPushButton#navHead:focus { border: 1px solid #42D4F2; }
QLabel#navGroup { color: #7E8C9B; font-size: 10px; font-weight: 800; letter-spacing: 1.6px; background: transparent; }
QPushButton#navHead[open="true"] QLabel#navGroup { color: #E6EDF5; }
QLabel#navChevron { color: #7E8C9B; font-size: 11px; background: transparent; }
QWidget#navGroupBody { background: transparent; }
QPushButton#navItem { border: none; background: transparent; border-radius: 9px; padding: 0; text-align: left;
                      min-height: 40px; max-height: 40px; }
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


class GroupHead(QPushButton):
    """A sidebar heading that opens or folds its tabs with one click."""

    def __init__(self, heading, on_click):
        super().__init__()
        self.heading = heading
        self.setObjectName("navHead")
        self.setFixedHeight(28)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        line = QHBoxLayout(self)
        line.setContentsMargins(12, 0, 12, 0)
        line.setSpacing(6)
        self.words = QLabel(heading.upper())
        self.words.setObjectName("navGroup")
        self.chevron = QLabel()
        self.chevron.setObjectName("navChevron")
        self.chevron.setFixedWidth(14)
        self.chevron.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        for widget in (self.words, self.chevron):
            widget.setAttribute(Qt.WA_TransparentForMouseEvents)
            widget.setTextFormat(Qt.PlainText)
        line.addWidget(self.words, 1)
        line.addWidget(self.chevron)
        self.clicked.connect(lambda _checked=False: on_click(heading))
        self.set_open(False)

    def set_open(self, opened: bool):
        self.chevron.setText("\u25be" if opened else "\u25b8")
        self.setProperty("open", opened)
        self.setAccessibleName(f"{self.heading} group, {'open' if opened else 'closed'}")
        self.setToolTip(("Click to fold away " if opened else "Click to open ") + self.heading)
        for widget in (self, self.words):
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
    column.setSpacing(3)
    buttons, heads, bodies = {}, {}, {}
    for heading, items in nav_groups.GROUPS:
        head = GroupHead(heading, lambda h: toggle(window, h))
        column.addWidget(head)
        body = QWidget()
        body.setObjectName("navGroupBody")
        inner = QVBoxLayout(body)
        inner.setContentsMargins(0, 0, 0, 4)
        inner.setSpacing(1)
        for route, _sub in items:
            control = NavItem(route, window.navigate)
            control.setFixedWidth(ITEM_WIDTH)
            control.set_active(route == window.current_route)
            inner.addWidget(control)
            buttons[route] = control
        column.addWidget(body)
        heads[heading], bodies[heading] = head, body
    column.addStretch(1)
    scroll.setWidget(holder)
    rail_layout.addWidget(scroll, 1)
    window.nav_scroll, window.nav_heads, window.nav_bodies = scroll, heads, bodies
    window.nav_open_group = ""
    show_group(window, nav_groups.group_of(window.current_route), animate=False)
    return buttons


def show_group(window, heading, *, animate=True):
    """Open one group (or none, with ""), fold the others. Opening slides down; folding is instant."""
    window.nav_open_group = heading
    for name, body in getattr(window, "nav_bodies", {}).items():
        opened = name == heading
        window.nav_heads[name].set_open(opened)
        if opened and body.isHidden():
            body.setVisible(True)
            if animate:
                target = body.sizeHint().height()
                body.setMaximumHeight(0)
                anim = QPropertyAnimation(body, b"maximumHeight", body)
                anim.setDuration(SLIDE_MS)
                anim.setStartValue(0)
                anim.setEndValue(target)
                anim.setEasingCurve(QEasingCurve.OutCubic)
                anim.finished.connect(lambda b=body: b.setMaximumHeight(16777215))
                body._slide = anim
                anim.start()
        elif not opened:
            slide = getattr(body, "_slide", None)
            if slide is not None:
                slide.stop()
            body.setMaximumHeight(16777215)
            body.setVisible(False)


def toggle(window, heading):
    show_group(window, nav_groups.toggled(window.nav_open_group, heading))


def follow(window, route):
    """Called on every navigation: the tab you are on is always in an open group."""
    wanted = nav_groups.open_for(route, window.nav_open_group)
    if wanted != window.nav_open_group:
        show_group(window, wanted, animate=False)


def sync_groups(window):
    """A heading whose tabs are all hidden hides with them."""
    for heading, items in nav_groups.GROUPS:
        head = getattr(window, "nav_heads", {}).get(heading)
        if head is None:
            continue
        head.setVisible(any(not window.nav_buttons[route].isHidden() for route, _ in items if route in window.nav_buttons))
