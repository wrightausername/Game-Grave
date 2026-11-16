"""Whole words in a narrow window, for any page with a MetricStrip, a TabStrip and a table.

When there is too little room, Qt cuts captions and tab names mid-word ("Shader Cach", "Storage Breakdo"). This swaps in
a shorter whole word while room is short and puts the full words back when there is room again; the full words always
stay in the tooltip and the screen-reader name. Below `narrow`, chosen table columns step aside so the important ones
stay readable without a sideways scroll bar. Display only.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QTimer

CELL_CHROME = 55
TAB_CHROME = 42


def choose(full, short, need, room):
    return full if need <= room or not short else short


class NarrowFit(QObject):
    def __init__(self, page, strip=None, tabs=None, *, captions=None, tab_names=None, table=None, hide=(), narrow=1100):
        super().__init__(page)
        self.page, self.strip, self.tabs, self.table = page, strip, tabs, table
        self.short_captions, self.short_tabs = captions or {}, tab_names or {}
        self.hide, self.narrow = tuple(hide), narrow
        self.captions = [(c, c.text()) for c in getattr(strip, "captions", [])]
        self.buttons = [(b, name) for name, b in getattr(tabs, "buttons", {}).items()]
        for button, name in self.buttons:
            button.setAccessibleName(name)
            if not button.toolTip():
                button.setToolTip(name)
        page.installEventFilter(self)
        QTimer.singleShot(0, self.apply)

    def eventFilter(self, target, event):
        if event.type() in (QEvent.Resize, QEvent.Show):
            QTimer.singleShot(0, self.apply)
        return False

    def apply(self):
        try:
            for caption, full in self.captions:
                cell = caption.parentWidget()
                room = (cell.width() if cell else 0) - CELL_CHROME
                wanted = choose(full, self.short_captions.get(full, ""), caption.fontMetrics().horizontalAdvance(full), room)
                if caption.text() != wanted:
                    caption.setText(wanted)
                caption.setToolTip(full)
            for button, full in self.buttons:
                wanted = choose(full, self.short_tabs.get(full, ""), button.fontMetrics().horizontalAdvance(full),
                                button.width() - TAB_CHROME)
                if button.text() != wanted:
                    button.setText(wanted)
            if self.table is not None:
                tight = self.page.width() < self.narrow
                for column in self.hide:
                    self.table.setColumnHidden(column, tight)
        except RuntimeError:
            pass          # the page was rebuilt


def install(page, strip=None, tabs=None, **options):
    page._narrow_fit = NarrowFit(page, strip, tabs, **options)
    return page._narrow_fit
