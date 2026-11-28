"""The sidebar (Qt). Owner, 2026-11-27: organised and more professional (see nav_groups.py for the layout and words).

One line per entry, icon and name, the plain description on hover. Quiet section labels that never fold. Home and Free up
space hold more than one tab: their tabs show indented under them while you are in one. Assistant, Undo and Settings sit
at the bottom with Collapse, which shrinks the sidebar to icons (remembered). Buttons are kept in window.nav_buttons by
route key, so navigation, the active highlight and the optional AI Assistant switch work as before.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from gg_desktop import nav_groups
from gg_desktop.reference_widgets import ROUTE_SYMBOLS, icon

ITEM_WIDTH = 195          # fixed, so rows never change size when the scroll bar comes and goes
ITEM_HEIGHT = 36
SUB_HEIGHT = 30
WIDE, NARROW = 219, 64    # the rail's width open and collapsed

STYLE = """
QScrollArea#navScroll, QWidget#navList, QWidget#navPinned, QWidget#navHubBody { background: transparent; border: none; }
QScrollArea#navScroll QScrollBar:vertical { width: 6px; background: transparent; margin: 2px; }
QScrollArea#navScroll QScrollBar::handle:vertical { background: #2A3541; border-radius: 3px; min-height: 30px; }
QScrollArea#navScroll QScrollBar::add-line:vertical, QScrollArea#navScroll QScrollBar::sub-line:vertical { height: 0; }
QLabel#navSection { color: #6F7C8A; font-size: 11px; font-weight: 600; background: transparent; padding-left: 12px; }
QPushButton#navItem, QPushButton#navSubItem { border: none; background: transparent; border-radius: 8px; padding: 0;
                                              text-align: left; }
QPushButton#navItem { min-height: 36px; max-height: 36px; }
QPushButton#navSubItem { min-height: 30px; max-height: 30px; }
QPushButton#navItem:hover, QPushButton#navSubItem:hover { background: #151D26; }
QPushButton#navItem[active="true"] { background: #24161B; }
QPushButton#navSubItem[active="true"] { background: #1E1418; }
QPushButton#navItem:focus, QPushButton#navSubItem:focus { border: 1px solid #42D4F2; }
QLabel#navTitle { color: #C3CDD8; font-size: 13px; font-weight: 600; background: transparent; }
QLabel#navTitle[active="true"] { color: #FFFFFF; }
QLabel#navSubTitle { color: #8D99A6; font-size: 12px; background: transparent; }
QLabel#navSubTitle[active="true"] { color: #FFFFFF; }
QFrame#navMark { background: transparent; border: none; border-radius: 2px; }
QFrame#navMark[active="true"] { background: #FF4357; }
QFrame#navRule { background: #1C232B; border: none; min-height: 1px; max-height: 1px; }
"""


def _restyle(*widgets):
    for widget in widgets:
        widget.style().unpolish(widget)
        widget.style().polish(widget)


class NavItem(QPushButton):
    """One sidebar entry: icon and name. A hub entry (more than one tab) shows a small count of its tabs."""

    def __init__(self, entry, routes, on_click):
        super().__init__()
        self.entry, self.routes = entry, tuple(routes)
        self.route = self.routes[0]                     # older code reads .route
        self.setObjectName("navItem")
        self.setFixedHeight(ITEM_HEIGHT)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(entry + " page")
        self.setToolTip(nav_groups.tip(entry))
        line = QHBoxLayout(self)
        line.setContentsMargins(0, 0, 8, 0)
        line.setSpacing(0)
        self.mark = QFrame()
        self.mark.setObjectName("navMark")
        self.mark.setFixedSize(3, 18)
        line.addWidget(self.mark, 0, Qt.AlignVCenter)
        line.addSpacing(10)
        self.glyph = QLabel()
        self.glyph.setFixedSize(20, 20)
        symbol = nav_groups.ENTRY_ICON.get(entry, ROUTE_SYMBOLS.get(self.route, "game"))
        self.symbol = symbol
        self.glyph.setPixmap(icon(symbol, "#AEB8C3", 20).pixmap(20, 20))
        line.addWidget(self.glyph, 0, Qt.AlignVCenter)
        line.addSpacing(12)
        self.title = QLabel(entry)
        self.title.setObjectName("navTitle")
        self.title.setTextFormat(Qt.PlainText)
        line.addWidget(self.title, 1)
        for widget in (self.mark, self.glyph, self.title):
            widget.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.clicked.connect(lambda _checked=False: on_click(entry))
        self._active = None
        self.set_active(False)

    def set_active(self, active: bool):
        if self._active == active:
            return
        self._active = active
        self.glyph.setPixmap(icon(self.symbol, "#FF5A6B" if active else "#AEB8C3", 20).pixmap(20, 20))
        for widget in (self, self.title, self.mark):
            widget.setProperty("active", active)
        _restyle(self, self.title, self.mark)

    def set_collapsed(self, collapsed: bool):
        self.title.setVisible(not collapsed)
        self.setFixedWidth(NARROW - 12 if collapsed else ITEM_WIDTH)


class SubItem(QPushButton):
    """One tab inside a hub entry, indented under it."""

    def __init__(self, route, on_click):
        super().__init__()
        self.route = route
        self.setObjectName("navSubItem")
        self.setFixedHeight(SUB_HEIGHT)
        self.setFixedWidth(ITEM_WIDTH)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(nav_groups.display_name(route) + " page")
        self.setToolTip(nav_groups.display_name(route) + ": " + nav_groups.subtitle(route))
        line = QHBoxLayout(self)
        line.setContentsMargins(45, 0, 8, 0)
        self.title = QLabel(nav_groups.display_name(route))
        self.title.setObjectName("navSubTitle")
        self.title.setTextFormat(Qt.PlainText)
        self.title.setAttribute(Qt.WA_TransparentForMouseEvents)
        line.addWidget(self.title, 1)
        self.clicked.connect(lambda _checked=False: on_click(route))
        self._active = None
        self.set_active(False)

    def set_active(self, active: bool):
        if self._active == active:
            return
        self._active = active
        for widget in (self, self.title):
            widget.setProperty("active", active)
        _restyle(self, self.title)


def _section_label(text):
    label = QLabel(text)
    label.full_text = text
    label.setObjectName("navSection")
    label.setTextFormat(Qt.PlainText)
    label.setFixedHeight(26)
    label.setAlignment(Qt.AlignLeft | Qt.AlignBottom)
    return label


def build(window, rail_layout):
    """Fill the rail under the logo. Returns {route: button} in sidebar order (a hub's tabs map to their own rows)."""
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
    column.setSpacing(2)
    buttons, entries, hubs, sections = {}, {}, {}, {}

    def add_entry(layout, entry, routes):
        item = NavItem(entry, routes, lambda e: go(window, e))
        item.setFixedWidth(ITEM_WIDTH)
        layout.addWidget(item)
        entries[entry] = item
        if len(routes) > 1:
            body = QWidget()
            body.setObjectName("navHubBody")
            inner = QVBoxLayout(body)
            inner.setContentsMargins(0, 0, 0, 2)
            inner.setSpacing(1)
            for route in routes:
                sub = SubItem(route, window.navigate)
                inner.addWidget(sub)
                buttons[route] = sub
            body.hide()
            layout.addWidget(body)
            hubs[entry] = body
        else:
            buttons[routes[0]] = item

    for label, items in nav_groups.SECTIONS:
        if label:
            head = _section_label(label)
            column.addSpacing(6)
            column.addWidget(head)
            sections[label] = (head, [e for e, _r in items])
        for entry, routes in items:
            add_entry(column, entry, routes)
    column.addStretch(1)
    scroll.setWidget(holder)
    rail_layout.addWidget(scroll, 1)

    pinned = QWidget()
    pinned.setObjectName("navPinned")
    pinned.setStyleSheet(STYLE)
    bottom = QVBoxLayout(pinned)
    bottom.setContentsMargins(6, 4, 6, 0)
    bottom.setSpacing(2)
    rule = QFrame()
    rule.setObjectName("navRule")
    bottom.addWidget(rule)
    bottom.addSpacing(4)
    for entry, routes in nav_groups.PINNED:
        add_entry(bottom, entry, routes)
    collapse = NavItem("Collapse", ("Settings",), lambda _e: set_collapsed(window, not window.nav_collapsed))
    collapse.symbol = "sidebar"
    collapse.glyph.setPixmap(icon("sidebar", "#7F8B98", 20).pixmap(20, 20))
    collapse.setToolTip("Collapse the sidebar to icons (more room for the page)")
    collapse.setAccessibleName("Collapse the sidebar")
    collapse.set_active = lambda _a: None
    collapse.setFixedWidth(ITEM_WIDTH)
    bottom.addWidget(collapse)
    rail_layout.addWidget(pinned)

    window.nav_scroll, window.nav_entries, window.nav_hubs = scroll, entries, hubs
    window.nav_sections, window.nav_collapse_button, window.nav_rule = sections, collapse, rule
    settings = getattr(window, "settings", {}) or {}
    last = settings.get(nav_groups.HUB_KEY)
    window.nav_hub_last = dict(last) if isinstance(last, dict) else {}
    window.nav_collapsed = False
    window.nav_open_groups = frozenset()                 # older checks read it; nothing folds now
    if settings.get(nav_groups.COLLAPSED_KEY) is True:
        set_collapsed(window, True, remember=False)
    return buttons


def go(window, entry):
    """A click on an entry: its tab, or for Home / Free up space the tab you last used inside it."""
    target = nav_groups.hub_target(entry, getattr(window, "nav_hub_last", {}))
    if target:
        window.navigate(target)


def follow(window, route):
    """Called on every navigation: light the entry (and the tab row inside a hub), show only the active hub's tabs."""
    current = nav_groups.entry_of(route)
    for entry, item in getattr(window, "nav_entries", {}).items():
        item.set_active(entry == current)
    for entry, body in getattr(window, "nav_hubs", {}).items():
        body.setVisible(entry == current and not window.nav_collapsed)
    if nav_groups.is_hub(current) and window.nav_hub_last.get(current) != route:
        window.nav_hub_last[current] = route
        # Kept with the settings in memory (saved the next time Game Grave saves settings), never written on its own,
        # so moving between tabs never writes to disk.
        window.settings = dict(getattr(window, "settings", {}) or {}, **{nav_groups.HUB_KEY: dict(window.nav_hub_last)})


def set_collapsed(window, collapsed, remember=True):
    """Icons only (collapsed) or icons and names. Section labels and a hub's tab rows hide while collapsed."""
    window.nav_collapsed = bool(collapsed)
    for item in list(getattr(window, "nav_entries", {}).values()) + [window.nav_collapse_button]:
        item.set_collapsed(window.nav_collapsed)
    button = window.nav_collapse_button
    button.symbol = "sidebar_open" if collapsed else "sidebar"
    button.glyph.setPixmap(icon(button.symbol, "#7F8B98", 20).pixmap(20, 20))
    button.title.setText("Collapse")
    button.setToolTip("Show the sidebar's names again" if collapsed else
                      "Collapse the sidebar to icons (more room for the page)")
    button.setAccessibleName("Expand the sidebar" if collapsed else "Collapse the sidebar")
    for head, _entries in getattr(window, "nav_sections", {}).values():
        head.setText("" if collapsed else head.full_text)
    sync_groups(window)
    if hasattr(window, "top_bar"):              # during start-up the shell isn't built yet; page_for applies it
        window._sync_shell_layout()
    elif hasattr(window, "nav_rail"):
        window.nav_rail.setFixedWidth(rail_width(window))
    follow(window, getattr(window, "current_route", "") or "")
    if hasattr(window, "brand"):
        window.brand.update()
    if remember:
        _save(window, nav_groups.COLLAPSED_KEY, window.nav_collapsed)


def rail_width(window) -> int:
    return NARROW if getattr(window, "nav_collapsed", False) else WIDE


def _save(window, key, value):
    window.settings = dict(getattr(window, "settings", {}) or {}, **{key: value})
    try:
        from core import save_settings
        save_settings(window.settings)
    except Exception:
        pass             # remembering is a convenience; the sidebar works the same without it


def sync_groups(window):
    """A section label hides when every entry under it is hidden (or while collapsed); an entry whose only tab is hidden
    (the AI Assistant while it is off) hides too."""
    for entry, item in getattr(window, "nav_entries", {}).items():
        routes = item.routes
        if len(routes) == 1:
            continue
        item.setVisible(any(not window.nav_buttons[r].isHidden() for r in routes if r in getattr(window, "nav_buttons", {})))
    for label, (head, names) in getattr(window, "nav_sections", {}).items():
        shown = any(not window.nav_entries[n].isHidden() for n in names)
        head.setVisible(shown and not getattr(window, "nav_collapsed", False))


def show_groups(window, groups, *, animate=True):
    """Older checks call this; nothing folds in this sidebar, so it only keeps the value."""
    window.nav_open_groups = frozenset(groups)


def toggle(window, heading):
    show_groups(window, nav_groups.toggled(window.nav_open_groups, heading))


def visible_routes(window):
    """Tabs a person can reach from the sidebar right now (a hub's tabs count even while its rows are folded)."""
    out = []
    for route in nav_groups.routes():
        control = getattr(window, "nav_buttons", {}).get(route)
        if control is None or control.isHidden():
            continue
        entry = window.nav_entries.get(nav_groups.entry_of(route))
        if entry is not None and entry.isHidden():
            continue
        out.append(route)
    return out
