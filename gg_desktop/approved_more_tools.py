"""Owner-locked More Tools visual hierarchy over functional recovery utilities.

Resurrection Kit and Save Vault remain real user-invoked workflows, not
marketing tiles. Quick Access and the diagnostic shortcuts remain usable.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QHBoxLayout, QVBoxLayout, QWidget
from gg_desktop.widgets import ActionCard
from gg_desktop.cinematic_art import CinematicToolArtwork
from gg_desktop.visuals import nav_icon


def render_approved_more_tools(window):
    window.tools_page()
    page = window.page
    page.content.setContentsMargins(11, 7, 11, 15)
    page.content.setSpacing(9)

    def illustrated_feature(panel, kind, accessible_name):
        # The locked cards place big atmospheric art BESIDE their title and
        # actions. A narrow illustration stacked between buttons was wrong.
        original = panel.layout()
        if original is None:
            return
        saved = []
        while original.count():
            part = original.takeAt(0)
            if part.widget() is not None:
                saved.append(part.widget())
        split = QWidget()
        split.setObjectName("approvedFeaturedTool")
        horizontal = QHBoxLayout(split)
        horizontal.setContentsMargins(0, 0, 0, 0)
        horizontal.setSpacing(8)
        left = QWidget()
        left_col = QVBoxLayout(left)
        left_col.setContentsMargins(0, 0, 0, 0)
        left_col.setSpacing(8)
        for widget in saved:
            left_col.addWidget(widget)
        left_col.addStretch()
        graphic = CinematicToolArtwork(kind)
        graphic.setObjectName(accessible_name)
        graphic.setMinimumWidth(136)
        graphic.setMaximumWidth(205)
        horizontal.addWidget(left, 3)
        horizontal.addWidget(graphic, 2)
        original.addWidget(split)
        panel.setMinimumHeight(196)

    prominent = page.findChildren(QFrame, "actionCardPrimary")
    if prominent:
        illustrated_feature(prominent[0], "kit", "approvedKitArt")

    vault = None
    for frame in page.findChildren(QFrame):
        if prominent and frame is prominent[0]:
            continue
        if frame.objectName() not in ("actionCard", "panel"):
            continue
        labels = [x.text() for x in frame.findChildren(QLabel)]
        if any("SAVE VAULT" in x for x in labels):
            vault = frame
            break
    if vault is not None:
        illustrated_feature(vault, "vault", "approvedVaultArt")

    tile_styles = (
        ("Make Room", "#D8A75C"),
        ("Storage Explorer", "#5AD0CD"),
        ("Ghost Watch", "#B3A0F2"),
        ("Capture Studio", "#C18EF0"),
        ("Game Exodus", "#50D5BD"),
        ("Diagnostics", "#E7B36E"),
    )
    for tile in page.findChildren(ActionCard):
        for name, accent in tile_styles:
            if tile.accessibleName().startswith(name + "."):
                glyph = tile.layout().itemAt(0).widget()
                if isinstance(glyph, QLabel):
                    glyph.setText("")
                    glyph.setPixmap(nav_icon({
                        "Make Room": "Graveyard", "Storage Explorer": "Other Storage",
                        "Ghost Watch": "Game DNA", "Capture Studio": "Captures",
                        "Game Exodus": "Games", "Diagnostics": "Settings",
                    }[name]).pixmap(27, 27))
                    glyph.setFixedSize(30, 30)
                tile.layout().setContentsMargins(10, 8, 10, 8)
                tile.layout().itemAt(1).widget().layout().setAlignment(Qt.AlignVCenter)
                tile.setProperty("toolAccent", name.replace(" ", ""))
                tile.setStyleSheet(
                    "QFrame#actionCard{background:#121720;"
                    "border:1px solid #2A2D37;"
                    f"border-left:2px solid {accent};border-radius:4px;}}"
                    "QFrame#actionCard:hover{"
                    "border:1px solid #794154;"
                    f"border-left:2px solid {accent};background:#1A1D2A;}}")
                break
    return page
