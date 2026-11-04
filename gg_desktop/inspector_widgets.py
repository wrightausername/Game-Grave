"""Compact native evidence components shared by the locked workspaces."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout


class InspectorFacts(QFrame):
    """Aligned, selectable facts with no implied health or confidence score."""

    def __init__(self, facts=()):
        super().__init__()
        self.setObjectName("inspectorFacts")
        self.rows = QVBoxLayout(self)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(0)
        self.set_facts(facts)

    def set_facts(self, facts):
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for key, value in facts:
            frame = QFrame()
            frame.setObjectName("inspectorFactRow")
            line = QHBoxLayout(frame)
            line.setContentsMargins(0, 5, 0, 5)
            line.setSpacing(8)
            name = QLabel(str(key))
            name.setObjectName("factKey")
            name.setWordWrap(True)
            data = QLabel(str(value))
            data.setObjectName("factValue")
            data.setWordWrap(True)
            data.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            data.setTextInteractionFlags(Qt.TextSelectableByMouse)
            line.addWidget(name, 1)
            line.addWidget(data, 1)
            self.rows.addWidget(frame)


def detail_section(title):
    heading = QLabel(title.upper())
    heading.setObjectName("detailSection")
    return heading
