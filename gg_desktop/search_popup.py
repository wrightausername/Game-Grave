"""The results list under the top search box: everything that matches, grouped (tabs, tools, games, mods, saves, old
files, captures). Typing still filters the page you are on, as before. Down / Up pick a result, then Enter (or a click) opens it,
Esc closes the list. Opening a result goes to its tab (with that tab's search set to it) or opens the tool."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer
from PySide6.QtWidgets import QListWidget, QListWidgetItem
from shiboken6 import isValid

from gg_desktop import search_core as core

STYLE = ("QListWidget{background:#0b1118;border:1px solid #3a4652;border-radius:8px;color:#e5e8ee;padding:4px;outline:0;}"
         "QListWidget::item{padding:5px 8px;border-radius:5px;}"
         "QListWidget::item:selected{background:#7d1529;color:#ffffff;}")
ROLE = Qt.UserRole + 41


def _tabs(window):
    from gg_desktop import nav_groups
    shown = set(getattr(window, "nav_buttons", {}) or {})
    return [(route, nav_groups.display_name(route), line) for _, rows in nav_groups.GROUPS for route, line in rows
            if not shown or route in shown]


class SearchPopup(QObject):
    def __init__(self, window, box):
        super().__init__(window)
        self.window, self.box, self.hits, self.quiet, self.picked = window, box, [], False, False
        self.list = QListWidget(window)
        self.list.setObjectName("searchResults")
        self.list.setAccessibleName("Search results")
        self.list.setStyleSheet(STYLE)
        self.list.setFocusPolicy(Qt.NoFocus)
        self.list.hide()
        self.list.itemClicked.connect(lambda item: self.open_item(item))
        self.timer = QTimer(self, singleShot=True, interval=140)
        self.timer.timeout.connect(self.refresh)
        box.textChanged.connect(lambda _text: None if self.quiet else self.timer.start())
        box.installEventFilter(self)

    def refresh(self):
        text = self.box.text()
        from gg_desktop import assistant_features
        self.hits = core.find(text, _tabs(self.window), assistant_features.FEATURES, self.window.inventory)
        self.list.clear()
        if not self.hits or not self.box.hasFocus():
            self.list.hide()
            return
        group = None
        for hit in self.hits:
            if hit.group != group:
                group = hit.group
                head = QListWidgetItem(group.upper())
                head.setFlags(Qt.NoItemFlags)
                head.setForeground(Qt.gray)
                self.list.addItem(head)
            item = QListWidgetItem(f"{hit.title}    {hit.detail}"[:110])
            item.setData(ROLE, hit)
            item.setToolTip(hit.detail)
            self.list.addItem(item)
        self.place()
        self.list.setCurrentRow(-1)       # nothing picked: Enter keeps doing what it did on this page
        self.picked = False
        self.list.show()
        self.list.raise_()

    def place(self):
        top_left = self.box.mapTo(self.window, QPoint(0, self.box.height() + 4))
        width = max(self.box.width(), 420)
        height = sum(max(22, self.list.sizeHintForRow(i)) for i in range(self.list.count())) + 14
        bottom_room = self.window.height() - top_left.y() - 12
        self.list.setGeometry(top_left.x(), top_left.y(), width, max(60, min(height, 440, bottom_room)))

    def move(self, step):
        row = self.list.currentRow()
        for _ in range(self.list.count()):
            row = (row + step) % max(1, self.list.count())
            if self.list.item(row).flags() & Qt.ItemIsEnabled:
                self.list.setCurrentRow(row)
                return

    def open_item(self, item):
        hit = item.data(ROLE) if item is not None else None
        if hit is None:
            return
        self.open_hit(hit)

    def open_hit(self, hit):
        from gg_desktop import autopilot_ui
        self.list.hide()
        self.quiet = True
        try:
            self.box.clear()
            autopilot_ui.open_target(self.window, hit.target)
            if hit.search and hit.target.startswith("tab:"):
                self.box.setText(hit.search)       # filters that tab, as typing there would
        finally:
            self.quiet = False
        self.window.status.setText(f"Opened {hit.title}.")

    def eventFilter(self, target, event):
        kind = event.type()
        if kind == QEvent.KeyPress and self.list.isVisible():
            key = event.key()
            if key == Qt.Key_Down:
                self.move(1)
                self.picked = True
                return True
            if key == Qt.Key_Up:
                self.move(-1)
                self.picked = True
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter):
                if self.picked and self.list.currentItem() is not None:
                    self.open_item(self.list.currentItem())
                    return True
                self.list.hide()          # the page's own Enter (Overview's search results) still runs
                return False
            if key == Qt.Key_Escape:
                self.list.hide()
                return True
        elif kind == QEvent.FocusOut:
            QTimer.singleShot(150, lambda: isValid(self.list) and not self.box.hasFocus() and self.list.hide())
        elif kind == QEvent.FocusIn and self.box.text():
            self.timer.start()
        return False


def install(window):
    window.search_popup = SearchPopup(window, window.global_search)
    window.global_search.setAccessibleName("Search everything (also filters the current page)")
    return window.search_popup
