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
    # Keep the existing real interactive map, inspector and verified actions.
    # Remove preview wizard chrome so the relationship workspace is visible
    # near the top of the approved cinematic composition.
    window.dna_page()
    page = window.page
    if not window.inventory.scanned_at:
        return page
    page.content.setSpacing(8)
    page.content.setContentsMargins(11, 6, 11, 13)
    for strip in page.findChildren(FeatureStrip):
        page.content.removeWidget(strip)
        strip.hide()
        strip.deleteLater()

    from gg_desktop.reference_hero import ReferenceHero
    for hero in page.findChildren(ReferenceHero):
        hero.setMinimumHeight(139)
        hero.setMaximumHeight(139)

    selectors = [
        obj for obj in page.findChildren(QComboBox)
        if obj.accessibleName() == "Game for digital relationship analysis"
    ]
    if selectors:
        selector = selectors[0]
        # The selector already opens real game records. Make the row compact;
        # the mockup's fake game cover, scan timer and status are not copied.
        selection = page.content.itemAt(1)
        selection_card = selection.widget() if selection else None
        if selection_card is not None:
            selection_card.layout().setContentsMargins(12, 7, 12, 7)
            selection_card.layout().setSpacing(3)
            first = selection_card.layout().itemAt(0)
            if first and first.widget():
                first.widget().hide()

    from game_intelligence import build_game_dna
    data = build_game_dna(
        window.inventory.steam, window.inventory.other,
        window.inventory.mods, window.inventory.saves)
    games = data.get("games", [])
    bar = QWidget()
    bar.setObjectName("approvedDNABand")
    layout = row(spacing=7)
    bar.setLayout(layout)
    metrics = (
        ("Installed games", str(len(games)), "Verified launcher records", "#E8EAF2"),
        ("Linked locations", "Unknown", "For selected game", "#77D9EE"),
        ("Manager profiles", "Unknown", "Exact install root matches", "#D7A4EA"),
        ("Unresolved", str(len(data.get("unresolved", []))),
         "Global • stay protected", "#E6BA7F"),
        ("Save locations", str(len(window.inventory.saves)),
         "Global • not game-attributed", "#80DAB1"),
        ("Capture files", str(len(window.inventory.screenshots) +
                              len(window.inventory.recordings)),
         "Global • ownership unknown", "#B9B4F1"),
    )
    dynamic = {}
    for title, value, hint, color in metrics:
        card, widget = _metric(title, value, hint, color)
        layout.addWidget(card, 1)
        dynamic[title] = widget
    # Hero > live game selector > metrics > dominant map & inspector.
    page.content.insertWidget(2, bar)

    for graph in page.findChildren(RelationshipMap):
        graph.setMinimumHeight(470)
        graph.setToolTip(
            "Interactive evidence map. Click a node for source information, "
            "drag background to pan, use wheel or +/- to zoom. "
            "Dashed links mean the relationship was not verified.")

    if selectors:
        selector = selectors[0]
        def update(index):
            if 0 <= index < len(games):
                record = games[index]
                dynamic["Linked locations"].setText(
                    str(len(record.get("assets", []))))
                dynamic["Manager profiles"].setText(
                    str(len(record.get("manager_profiles", []))))
            else:
                dynamic["Linked locations"].setText("Unknown")
                dynamic["Manager profiles"].setText("Unknown")
        selector.currentIndexChanged.connect(update)
        update(selector.currentIndex())

    # Important ownership warning remains visible, but below the forensic
    # workspace rather than above and crowding out the interactive map.
    notice = label(
        "DNA links use installed-game and mod-manager evidence. Saves, caches, "
        "media and unknown leftovers stay protected without verified ownership. "
        "Ghost Watch and Patch Fallout are manual observations, not automated "
        "compatibility or FPS measurements.",
        "caption", wrap=True)
    notice.setObjectName("approvedDNAEvidenceNotice")
    notice.setStyleSheet(
        "background:transparent; color:#A6B6C5; font-size:11px; "
        "border-left:2px solid #C83250; padding-left:9px;")
    page.content.addWidget(notice)
    return page
