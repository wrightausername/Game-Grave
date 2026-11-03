"""Owner-locked Game DNA layout adapter over the existing truthful map.

Never guesses save ownership, mod compatibility, patch effects or cleanup
eligibility. Keeps the existing interactive relationship map, inspector, Ghost
Watch, and verified backend workflow intact.
"""
from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from gg_desktop.visuals import FeatureStrip, RelationshipMap
from gg_desktop.widgets import row, label, button
from gg_desktop.models import readable_bytes


def _metric(title, value, hint, color):
    from gg_desktop.visuals import nav_icon
    card = QFrame()
    card.setObjectName("approvedDNAMetric")
    column = QVBoxLayout(card)
    column.setContentsMargins(8, 5, 8, 6)
    column.setSpacing(2)
    top = QWidget()
    heading = QHBoxLayout(top)
    heading.setContentsMargins(0,0,0,0)
    heading.setSpacing(6)
    routes = {
        "Installed games": "Games",
        "Linked locations": "Mods",
        "Manager profiles": "Mods",
        "Unresolved": "Graveyard",
        "Save locations": "More Tools",
        "Capture files": "Captures",
    }
    glyph = QLabel()
    glyph.setPixmap(nav_icon(routes.get(title, "Games")).pixmap(25,25))
    glyph.setFixedSize(26,26)
    heading.addWidget(glyph)
    a = label(title.upper(), "caption")
    a.setStyleSheet(
        "background:transparent;color:#B7C5D2;font-size:11px;font-weight:750;")
    heading.addWidget(a,1)
    column.addWidget(top)
    b = label(str(value), "sectionTitle")
    b.setStyleSheet(
        "background:transparent;color:" + color +
        ";font-size:20px;font-weight:850;")
    c = label(hint, "caption", wrap=True)
    c.setStyleSheet("background:transparent;color:#9EAEBC;font-size:10px;")
    column.addWidget(b)
    column.addWidget(c)
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
        graph.setMinimumHeight(312)
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

    # The locked design has separate lower workspaces. Keep only genuine
    # observations, and put manual investigative actions in clean cards rather
    # than a second crowded introductory ribbon.
    from gg_desktop.game_dna_tools import run_ghost_watch
    from PySide6.QtWidgets import QHBoxLayout
    lower = QWidget()
    lower_row = row(spacing=9)
    lower.setLayout(lower_row)

    def info_card(title, desc, tone):
        tile = QFrame()
        tile.setObjectName("ggAccentPanel")
        tile.setProperty("accent", tone)
        col = QVBoxLayout(tile)
        col.setContentsMargins(13, 10, 13, 10)
        col.setSpacing(7)
        heading = label(title, "sectionTitle")
        col.addWidget(heading)
        col.addWidget(label(desc, "caption", wrap=True))
        return tile, col

    storage, storage_col = info_card(
        "STORAGE BREAKDOWN",
        "Only launcher-reported install size is attributed to the selected "
        "game; media and saves remain unassigned without source evidence.",
        "cyan")
    storage_size = label("Unknown", "sectionTitle")
    storage_size.setStyleSheet(
        "background:transparent;color:#66D5E7;font-size:22px;font-weight:850;")
    storage_col.addWidget(storage_size)
    storage_col.addWidget(label("Reported installed-game size", "caption"))
    storage_col.addWidget(button(
        "Inspect game files  ›", lambda: window.navigate("Games")))
    lower_row.addWidget(storage, 4)

    ghost, ghost_col = info_card(
        "GHOST WATCH",
        "Manually compare verified mod locations across scans. Nothing runs "
        "in the background while you're gaming.",
        "green")
    ghost_col.addWidget(button(
        "Compare mod observations  ›",
        lambda: run_ghost_watch(window), kind="primary"))
    ghost_col.addWidget(button(
        "Open Mod Radar  ›", lambda: window.navigate("Mods")))
    lower_row.addWidget(ghost, 4)

    patch, patch_col = info_card(
        "PATCH FALLOUT",
        "Review changed files after a game update. An official patch feed or "
        "compatibility verdict is not available in this preview.",
        "amber")
    patch_col.addWidget(button(
        "Review local file changes  ›",
        lambda: run_ghost_watch(window, patch_only=True)))
    patch_col.addWidget(button(
        "Open Ready Room  ›", lambda: window.navigate("Ready Room")))
    lower_row.addWidget(patch, 4)

    # Original large investigation panel repeated all three actions and
    # pushed the approved lower workspace offscreen; retire only that visual
    # wrapper, never its callable source functions.
    for idx in reversed(range(page.content.count())):
        item = page.content.itemAt(idx)
        candidate = item.widget() if item is not None else None
        if candidate is None or candidate is lower:
            continue
        headings = [x.text() for x in candidate.findChildren(QLabel)]
        if any("INVESTIGATION WORKSPACE" in text for text in headings):
            page.content.removeWidget(candidate)
            candidate.hide()
            candidate.deleteLater()
    # The long raw linked-path evidence belongs after the main actions;
    # it must not push the three approved diagnostic cards below the fold.
    linked_evidence = None
    for idx in range(page.content.count()):
        item = page.content.itemAt(idx)
        w = item.widget() if item is not None else None
        if w is not None:
            labels = [part.text() for part in w.findChildren(QLabel)]
            if any("DIRECTLY LINKED FILE LOCATIONS" in text for text in labels):
                linked_evidence = w
                page.content.removeWidget(w)
                break
    page.content.addWidget(lower)

    action_strip = QFrame()
    action_strip.setObjectName("ggActionStrip")
    actions = row(spacing=9, margins=(11, 9, 11, 9))
    action_strip.setLayout(actions)
    actions.addWidget(button("Refresh local scan", window.start_scan, kind="primary"))
    actions.addWidget(button("Open Save Vault", lambda: window.navigate("More Tools")))
    actions.addWidget(button("View Mod Radar", lambda: window.navigate("Mods")))
    actions.addWidget(button("Review unknown files", lambda: window.navigate("Graveyard")))
    page.content.addWidget(action_strip)
    if linked_evidence is not None:
        page.content.addWidget(linked_evidence)

    # Keep the map/inspector dominant without consuming the lower modules.
    for idx in range(page.content.count()):
        item = page.content.itemAt(idx)
        w = item.widget() if item else None
        if w is not None and w.findChildren(RelationshipMap):
            w.setFixedHeight(408)
            break

    if selectors:
        chooser = selectors[0]
        def update_storage(index):
            if not (0 <= index < len(games)):
                storage_size.setText("Unknown")
                return
            item = games[index]
            recorded = next((
                game for game in window.inventory.games
                if game.name == item.get("game") and
                game.launcher == item.get("launcher")), None)
            count = getattr(recorded, "size_bytes", None) if recorded else None
            storage_size.setText(readable_bytes(count))
        chooser.currentIndexChanged.connect(update_storage)
        update_storage(chooser.currentIndex())

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
