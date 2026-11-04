"""Resize native workspaces without rebuilding controls or losing selection.

Breakpoints use available logical pixels. Monitor density alone says nothing
about the space available to a window, especially after moving it or resizing.
"""
from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QBoxLayout, QFrame, QGridLayout, QLayout, QSizePolicy, QWidget


class ResponsiveRow(QWidget):
    """A desktop row that becomes a vertical stack when its contents need room."""

    def __init__(self, *, breakpoint=980, spacing=10, margins=(0, 0, 0, 0),
                 horizontal_height=None):
        super().__init__()
        self.breakpoint = breakpoint
        self.horizontal_height = horizontal_height
        self.box = QBoxLayout(QBoxLayout.TopToBottom, self)
        self.box.setContentsMargins(*margins)
        self.box.setSpacing(spacing)
        self.box.setSizeConstraint(QLayout.SetNoConstraint)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def addWidget(self, widget, stretch=0):
        self.box.addWidget(widget, stretch)

    def minimumSizeHint(self):
        return QSize(0, super().minimumSizeHint().height())

    def resizeEvent(self, event):
        direction = (QBoxLayout.LeftToRight if event.size().width() >= self.breakpoint
                     else QBoxLayout.TopToBottom)
        if self.box.direction() != direction:
            self.box.setDirection(direction)
            if self.horizontal_height is not None:
                if direction == QBoxLayout.LeftToRight:
                    self.setFixedHeight(self.horizontal_height)
                else:
                    self.setMinimumHeight(0)
                    self.setMaximumHeight(16777215)
            self.updateGeometry()
        super().resizeEvent(event)


class ResponsiveGrid(QFrame):
    """Reflow existing widgets, optionally using page-specific desktop spans.

``columns`` contains (minimum available width, column count) pairs. Custom
``positions`` map a column count to (row, column, row span, column span) entries
in widget insertion order; this preserves a page's desktop visual hierarchy.
"""

    def __init__(self, *, columns=((0, 1), (600, 2), (1100, 3)),
                 positions=None, stretches=None, spacing=8, margins=(0, 0, 0, 0)):
        super().__init__()
        self.breakpoints = sorted(columns)
        self.positions = positions or {}
        self.stretches = stretches or {}
        self.widgets = []
        self.column_count = 0
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(*margins)
        self.grid.setSpacing(spacing)
        self.grid.setSizeConstraint(QLayout.SetNoConstraint)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def addWidget(self, widget):
        self.widgets.append(widget)
        self._arrange(self.width(), force=True)

    def minimumSizeHint(self):
        return QSize(0, super().minimumSizeHint().height())

    def _arrange(self, width, *, force=False):
        count = next((count for minimum, count in reversed(self.breakpoints)
                      if width >= minimum), 1)
        if count == self.column_count and not force:
            return
        for widget in self.widgets:
            self.grid.removeWidget(widget)
        stretches = self.stretches.get(count, (1,) * count)
        for column in range(max(count, self.column_count)):
            self.grid.setColumnStretch(column, stretches[column] if column < count else 0)
        self.column_count = count
        positions = self.positions.get(count, ())
        for index, widget in enumerate(self.widgets):
            position = (positions[index] if index < len(positions)
                        else (index // count, index % count, 1, 1))
            self.grid.addWidget(widget, *position)
        self.updateGeometry()

    def resizeEvent(self, event):
        self._arrange(event.size().width())
        super().resizeEvent(event)
