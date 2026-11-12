"""Old Files list: easy ticking. Double-click a file to tick or untick it, Shift+click to tick every row from the last one
you clicked to this one, Ctrl+click to tick or untick one more. Ticking only marks files for the existing buttons
(Add to Graveyard, Protect, Delete to the Recycle Bin after confirmation); nothing happens to a file from here.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QSignalBlocker, Qt

HINT = "Double-click a file to tick it · Shift+click ticks a range · Ctrl+click adds one"


def rows_between(anchor, row):
    if anchor is None or anchor < 0:
        return [row]
    low, high = sorted((anchor, row))
    return list(range(low, high + 1))


class TickHelper(QObject):
    def __init__(self, table, changed):
        super().__init__(table)
        self.table, self.changed, self.anchor = table, changed, None
        table.viewport().installEventFilter(self)
        table.setToolTip(HINT)

    def _set(self, rows, state):
        table = self.table
        with QSignalBlocker(table):
            for r in rows:
                item = table.item(r, 0)
                if item is not None and item.flags() & Qt.ItemIsUserCheckable:
                    item.setCheckState(state)
        self.changed()

    def _flip(self, row):
        item = self.table.item(row, 0)
        if item is None:
            return
        self._set([row], Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)

    def eventFilter(self, target, event):
        kind = event.type()
        if kind not in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick) or event.button() != Qt.LeftButton:
            return False
        index = self.table.indexAt(event.position().toPoint())
        if not index.isValid():
            return False
        row = index.row()
        mods = event.modifiers()
        if kind == QEvent.MouseButtonDblClick:
            if index.column() == 0:
                return False           # the box itself already flips on a click
            self._flip(row)
            self.anchor = row
            return True
        if mods & Qt.ShiftModifier:
            self._set(rows_between(self.anchor, row), Qt.Checked)
            self.table.setCurrentCell(row, 1)
            self.anchor = row
            return True
        if mods & Qt.ControlModifier:
            self._flip(row)
            self.table.setCurrentCell(row, 1)
            self.anchor = row
            return True
        self.anchor = row
        return False


def install(window):
    window.old_tick_helper = TickHelper(window.old_table, window._old_selection_count)
    return window.old_tick_helper
