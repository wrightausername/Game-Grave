"""Owner-locked Game DNA layout adapter over the existing truthful map.

Never guesses save ownership, mod compatibility, patch effects or cleanup
eligibility. Keeps the existing interactive relationship map, inspector, Ghost
Watch, and verified backend workflow intact.
"""
from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from gg_desktop.visuals import FeatureStrip, RelationshipMap
from gg_desktop.widgets import row, label


def _metric(title, value, hint, color):
    card = QFrame()
    card.setObjectName("approvedDNAMetric")
    column = QVBoxLayout(card)
    column.setContentsMargins(9, 6, 9, 6)
    column.setSpacing(1)
    a = label(title.upper(), "caption")
    a.setStyleSheet("background:transparent;color:#B7C5D2;font-size:10px;font-weight:750;")
    b = label(str(value), "sectionTitle")
    b.setStyleSheet("background:transparent;color:" + color
                    + ";font-size:18px;font-weight:850;")
    c = label(hint, "caption", wrap=True)
    c.setStyleSheet("background:transparent;color:#9EAEBE;font-size:10px;")
    for w in (a, b, c):
        column.addWidget(w)
    return card, b


def render_approved_dna(window):
    # Reuse the already tested interactive map and click-through inspector.
    # The owner-approved screenshot requires the map to dominate above-fold
    # space, rather than a redundant step-by-step introductory process strip.
    window.dna_page()
    page = window.page
    page.content.setSpacing(9)
    page.content.setContentsMargins(11, 7, 11, 14)
    for strip in page.findChildren(FeatureStrip):
        strip.setVisible(False)

    from game_intelligence import build_game_dna
    data = build_game_dna(
        window.inventory.steam, window.inventory.other,
        window.inventory.mods, window.inventory.saves)
    games = data.get("games", [])
    bar = QWidget()
    bar.setObjectName("approvedDNABand")
    layout = row(spacing=8)
    bar.setLayout(layout)
    metrics = (
        ("Installed games", str(len(games)), "Recorded launchers", "#E8EAF2"),
        ("Linked mods", "Unknown", "For selected game", "#77D9EE"),
        ("Verified profiles", "Unknown", "Matching game roots", "#D7A4EA"),
        ("Unresolved", str(len(data.get("unresolved", []))),
         "Remain protected", "#E6BA7F"),
    )
    dynamic = {}
    for title, value, hint, color in metrics:
        card, widget = _metric(title, value, hint, color)
        layout.addWidget(card, 1)
        dynamic[title] = widget
    page.content.insertWidget(1, bar)

    for graph in page.findChildren(RelationshipMap):
        graph.setMinimumHeight(460)
        graph.setToolTip(
            "Interactive evidence map. Click a node for source information, "
            "drag background to pan, use wheel or +/- to zoom. "
            "Dashed links mean the relationship was not verified.")

    selectors = [
        obj for obj in page.findChildren(QComboBox)
        if obj.accessibleName() == "Game for digital relationship analysis"
    ]
    if selectors:
        selector = selectors[0]
        def update(index):
            if 0 <= index < len(games):
                record = games[index]
                dynamic["Linked mods"].setText(str(len(record.get("assets", []))))
                dynamic["Verified profiles"].setText(
                    str(len(record.get("manager_profiles", []))))
            else:
                dynamic["Linked mods"].setText("Unknown")
                dynamic["Verified profiles"].setText("Unknown")
        selector.currentIndexChanged.connect(update)
        update(selector.currentIndex())

    # Distinguish the real linked file locations from inferred ownership.
    notice = label(
        "DNA links are based on installed-game and manager evidence. "
        "Saves, caches, recordings and unknown leftovers remain protected "
        "unless a source actually establishes ownership.",
        "caption", wrap=True)
    notice.setObjectName("approvedDNAEvidenceNotice")
    notice.setStyleSheet(
        "background:transparent; color:#A6B6C5; font-size:11px; "
        "border-left:2px solid #C83250; padding-left:9px;")
    page.content.insertWidget(2, notice)
    return page
