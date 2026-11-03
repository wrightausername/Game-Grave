"""Owner-locked More Tools visual hierarchy over functional recovery utilities.

Resurrection Kit and Save Vault remain real user-invoked workflows, not
marketing tiles. Quick Access and the diagnostic shortcuts remain usable.
"""
from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel
from gg_desktop.widgets import LandscapeArt, ActionCard


def render_approved_more_tools(window):
    window.tools_page()
    page = window.page
    page.content.setContentsMargins(11, 7, 11, 15)
    page.content.setSpacing(9)

    # Add distinct high-DPI cinematic art to the two prominent real tools.
    # The imagery contains no fabricated scan results or sample game metrics.
    prominent = page.findChildren(QFrame, "actionCardPrimary")
    if prominent:
        panel = prominent[0]
        artwork = LandscapeArt(121, scene="sunset",
                               note="Resurrection Kit • Backup before you change a setup")
        artwork.setObjectName("approvedKitArt")
        panel.layout().insertWidget(2, artwork)

    vault = None
    for frame in page.findChildren(QFrame):
        if frame is prominent[0] if prominent else False:
            continue
        if frame.objectName() not in ("actionCard", "panel"):
            continue
        labels = [x.text() for x in frame.findChildren(QLabel)]
        if any("SAVE VAULT" in x for x in labels):
            vault = frame
            break
    if vault is not None:
        artwork = LandscapeArt(121, scene="fog",
                               note="Save Vault • Your local game progress")
        artwork.setObjectName("approvedVaultArt")
        vault.layout().insertWidget(2, artwork)

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
                tile.setProperty("toolAccent", name.replace(" ", ""))
                tile.setStyleSheet(
                    "QFrame#actionCard{background:#121720;"
                    f"border:1px solid {accent}44;border-radius:7px;}}"
                    "QFrame#actionCard:hover{"
                    f"border:1px solid {accent};background:#1A1D2A;}}")
                break
    return page
