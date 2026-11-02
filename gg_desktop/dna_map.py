"""Interactive, evidence-constrained Qt Game DNA relationship map.

Visual lines mean detected relationships; dashed lines indicate UNKNOWN ownership.
No node grants any cleanup permission. No game hooks or background polling.
"""
from __future__ import annotations

import math
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView,
)


class DNAMap(QGraphicsView):
    node_selected = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.TextAntialiasing)
        self.setMinimumHeight(440)
        self.setBackgroundBrush(QBrush(QColor("#0A111A")))
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.scene_graph = QGraphicsScene(self)
        self.setScene(self.scene_graph)
        self.scene_graph.selectionChanged.connect(self._notify_selection)
        self._positions = []
        self._nodes = []

    @staticmethod
    def _bounded_text(s, limit=35):
        s = str(s)
        return s if len(s) <= limit else s[:limit - 1] + "…"

    def populate(self, game: dict, unresolved: list | None = None):
        """Populate a single-game view using only attributed evidence."""
        self.scene_graph.clear()
        self._nodes = []
        unresolved = unresolved or []
        assets = game.get("assets", [])
        profiles = game.get("manager_profiles", [])

        core = {
            "title": "GAME CORE",
            "value": self._bounded_text(game.get("game", "Unknown game"), 28),
            "source": game.get("launcher", "Unknown"),
            "path": game.get("install_path", ""),
            "reason": game.get("install_evidence", "Inventory record"),
            "relationship": "Verified game installation record",
            "protected": True,
            "confidence": "Manifest / inventory evidence",
        }
        linked_count = len(assets)
        buckets = [
            {
                "title": "MOD STORAGE",
                "value": f"{linked_count} linked locations",
                "source": "Mod Radar",
                "path": assets[0].get("path", "") if assets else "",
                "reason": "Only locations within verified install roots or source-specific Workshop IDs count as linked.",
                "relationship": "Detected" if assets else "None confirmed",
                "protected": True,
                "confidence": "Path / ID association only" if assets else "Unknown",
                "color": "#C884F7", "linked": bool(assets),
            },
            {
                "title": "MANAGER PROFILES",
                "value": f"{len(profiles)} matched profiles",
                "source": "Local manager evidence",
                "path": profiles[0].get("source", "") if profiles else "",
                "reason": "A profile is linked only when its manager-reported game directory exactly matches the installation.",
                "relationship": "Detected" if profiles else "None confirmed",
                "protected": True,
                "confidence": "Exact install-path association" if profiles else "Unknown",
                "color": "#60CEFD", "linked": bool(profiles),
            },
            {
                "title": "SAVE VAULT",
                "value": "Ownership unresolved",
                "source": "Protected saves",
                "path": "",
                "reason": "Save paths require independent game-owner verification. They are never assigned by a guessed folder name.",
                "relationship": "Unverified / dashed line",
                "protected": True,
                "confidence": "Unknown",
                "color": "#66DAA4", "linked": False,
            },
            {
                "title": "CAPTURES",
                "value": "Not linked by name",
                "source": "Screenshots & recordings",
                "path": "",
                "reason": "Captures live in separate scans; filenames are not enough to prove which game owns them.",
                "relationship": "Unverified / dashed line",
                "protected": True,
                "confidence": "Unknown",
                "color": "#5AC5EE", "linked": False,
            },
            {
                "title": "CACHES",
                "value": "Not independently attributed",
                "source": "GPU/launcher caches",
                "path": "",
                "reason": "A graphics cache can be shared across games and is not assigned without separate source evidence.",
                "relationship": "Unverified / dashed line",
                "protected": True,
                "confidence": "Unknown",
                "color": "#F8B659", "linked": False,
            },
            {
                "title": "UNRESOLVED",
                "value": f"{len(unresolved)} protected findings",
                "source": "Unmatched local data",
                "path": "",
                "reason": "Unresolved items may belong to another game or manager. This map does not mark them as deletable.",
                "relationship": "Unverified / dashed line",
                "protected": True,
                "confidence": "Unknown",
                "color": "#FF6677", "linked": False,
            },
        ]
        cx, cy = 460, 240
        # Fixed scene coordinates keep node geometry stable across DPI scaling.
        around = [(120, 82), (465, 53), (785, 94),
                  (120, 340), (465, 392), (785, 338)]
        self._node(cx - 103, cy - 47, 206, 96, "#FF4055", core, central=True)
        for item, (x, y) in zip(buckets, around):
            p1 = (cx, cy)
            p2 = (x + 86, y + 33)
            path = QPainterPath()
            path.moveTo(*p1)
            path.cubicTo((p1[0] + p2[0]) / 2, p1[1],
                         (p1[0] + p2[0]) / 2, p2[1], *p2)
            pen = QPen(QColor(item["color"]), 2 if item["linked"] else 1.2)
            if not item["linked"]:
                pen.setStyle(Qt.DashLine)
            self.scene_graph.addPath(path, pen)
            self._node(x, y, 172, 66, item["color"], item)
        self.scene_graph.setSceneRect(0, 0, 980, 470)
        self.reset_map()

    def _node(self, x, y, w, h, color, data, central=False):
        rect = QGraphicsRectItem(x, y, w, h)
        rect.setPen(QPen(QColor(color), 2 if central else 1.2))
        rect.setBrush(QBrush(QColor("#2A1020" if central else "#13202A")))
        rect.setFlag(QGraphicsItem.ItemIsSelectable, True)
        rect.setToolTip(data.get("reason", ""))
        rect.setData(0, data)
        rect.setZValue(5)
        self.scene_graph.addItem(rect)
        title = self.scene_graph.addText(self._bounded_text(data.get("title", ""), 24))
        title.setDefaultTextColor(QColor("#F6F8FC"))
        title.setFont(QFont("Segoe UI", 10, QFont.Bold))
        title.setParentItem(rect)
        title.setPos(10, 6)
        value = self.scene_graph.addText(self._bounded_text(data.get("value", ""), 29))
        value.setDefaultTextColor(QColor(color))
        value.setFont(QFont("Segoe UI", 9))
        value.setParentItem(rect)
        value.setPos(10, 31)
        self._nodes.append(rect)

    def _notify_selection(self):
        for item in self.scene_graph.selectedItems():
            data = item.data(0)
            if isinstance(data, dict):
                self.node_selected.emit(dict(data))
                return

    def reset_map(self):
        if self.scene_graph.sceneRect().isValid():
            self.fitInView(self.scene_graph.sceneRect(), Qt.KeepAspectRatio)

    def zoom_in(self):
        self.scale(1.2, 1.2)

    def zoom_out(self):
        self.scale(1 / 1.2, 1 / 1.2)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.scene_graph.selectedItems():
            self.reset_map()
