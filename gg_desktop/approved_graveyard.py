"""Approved Graveyard workspace: evidence, filtering, protection and explicit consent.

This is an alternative view over the existing verified scanner and cleanup
backend, not a second deletion implementation. All mutation flows delegate to
ScreenMethods, which requires exact-item checks, Recycle Bin and Undo.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFrame,
    QHBoxLayout, QLineEdit, QScrollArea, QTableWidgetItem, QVBoxLayout, QWidget,
)

from core import human_size
from graveyard_protection import protection_action
from gg_desktop.reference_hero import ReferenceHero
from gg_desktop.widgets import button, data_table, label, panel, row
from gg_desktop.cinematic_art import CinematicImpactTrack


def _label(text, color="#BDCAD7", size=11, bold=False):
    result = label(str(text), "caption", wrap=True)
    result.setStyleSheet(
        "color:" + color + f";font-size:{size}px;"
        + ("font-weight:800;" if bold else "")
        + "background:transparent;")
    return result


def _stat(title, value, color):
    from gg_desktop.visuals import nav_icon
    frame = QFrame()
    frame.setObjectName("approvedGraveStat")
    line = QHBoxLayout(frame)
    line.setContentsMargins(11, 6, 11, 6)
    line.setSpacing(10)
    icons = {
        "Candidates": "Graveyard", "Potential size": "Other Storage",
        "Reviewable": "Undo Center", "Protected": "Settings",
    }
    image = label("", "caption")
    image.setPixmap(nav_icon(icons.get(title, "Graveyard")).pixmap(32,32))
    image.setFixedSize(34,34)
    line.addWidget(image)
    text = QWidget()
    col = QVBoxLayout(text)
    col.setContentsMargins(0,0,0,0)
    col.setSpacing(1)
    col.addWidget(_label(title.upper(), "#BBC8D5", 11, True))
    col.addWidget(_label(value, color, 22, True))
    line.addWidget(text,1)
    return frame


def _size(entry):
    return max(0, int(entry.apparent_bytes))


def _age(entry):
    return (str(entry.age_days) + " days"
            if entry.age_days is not None else "Unknown")


def render_approved_graveyard(window):
    """Use the exact original safety logic with an improved review workspace."""
    page = window.page_for("Graveyard")
    page.content.setContentsMargins(11, 7, 11, 16)
    page.content.setSpacing(10)
    hero = ReferenceHero(
        "graveyard", "Graveyard",
        "Find and review old gaming files. You decide what gets removed.")
    hero.setMinimumHeight(151)
    hero.setMaximumHeight(151)
    page.content.addWidget(hero)
    if not window.inventory.scanned_at:
        window._not_scanned(page)
        return page

    entries = window.inventory.graveyard
    counts = QWidget()
    count_row = row(spacing=7)
    counts.setLayout(count_row)
    for title, value, color in (
        ("Candidates", str(len(entries)), "#E8E8F3"),
        ("Potential size", human_size(sum(_size(e) for e in entries)), "#4ED0ED"),
        ("Reviewable", str(sum(bool(e.can_recycle) for e in entries)), "#E6A764"),
        ("Protected", str(sum(not e.can_recycle for e in entries)), "#83DAB0"),
    ):
        count_row.addWidget(_stat(title, value, color), 1)
    count_row.addWidget(button("Scan Graveyard", window.start_scan, kind="primary"))
    page.content.addWidget(counts)
    page.content.addWidget(_label(
        "Potential size is the apparent size of candidates, not verified free space. "
        "Age by itself does not mean a file is safe to delete.", "#9EAFBF"))

    filters = QWidget()
    controls = row(spacing=7)
    filters.setLayout(controls)
    window.grave_search = QLineEdit()
    window.grave_search.setPlaceholderText(
        "Search item, path, launcher, source or detection evidence…")
    window.grave_search.setAccessibleName("Search Graveyard evidence")
    window.grave_search.setText(getattr(window, "_pending_grave_query", ""))
    window._pending_grave_query = ""
    controls.addWidget(window.grave_search, 4)

    window.grave_type = QComboBox()
    window.grave_type.addItems(
        ["All types"] + sorted({e.category for e in entries}))
    window.grave_type.setAccessibleName("Filter by finding type")
    controls.addWidget(window.grave_type, 2)

    window.grave_state = QComboBox()
    window.grave_state.addItems([
        "All findings", "Ready for review", "Protected / preview only"])
    window.grave_state.setAccessibleName("Filter by protection state")
    controls.addWidget(window.grave_state, 2)

    window.grave_drive = QComboBox()
    window.grave_drive.addItems(
        ["All drives"] + sorted({Path(e.path).anchor.upper()
                                 for e in entries if Path(e.path).anchor}))
    window.grave_drive.setAccessibleName("Filter by drive")
    controls.addWidget(window.grave_drive, 1)

    window.grave_age = QComboBox()
    window.grave_age.addItems(["All ages", "1+ year", "2+ years", "3+ years"])
    window.grave_age.setAccessibleName("Filter by last modified age")
    controls.addWidget(window.grave_age, 1)

    window.grave_sort = QComboBox()
    window.grave_sort.addItems([
        "Largest first", "Oldest first", "Newest first", "Name A–Z"])
    window.grave_sort.setAccessibleName("Sort Graveyard candidates")
    controls.addWidget(window.grave_sort, 1)
    page.content.addWidget(filters)

    main = QWidget()
    main_row = row(spacing=8)
    main.setLayout(main_row)
    browser, bcol = panel(padding=9, spacing=7)
    bcol.addWidget(_label("CANDIDATE FILES", "#F4F6F9", 14, True))
    window.grave_table = data_table([
        "ITEM", "SOURCE / TYPE", "GAME / RELATIONSHIP",
        "SIZE", "AGE", "REVIEW STATUS"])
    window.grave_table.setSelectionBehavior(QAbstractItemView.SelectRows)
    window.grave_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
    for idx, width in enumerate((178, 112, 150, 80, 95, 143))
        window.grave_table.setColumnWidth(idx, width)
    window.grave_table.horizontalHeader().setStretchLastSection(True)
    window.grave_table.setMinimumHeight(292)
    window.grave_table.setAccessibleName("Graveyard discovered candidates table")
    bcol.addWidget(window.grave_table, 1)

    main_row.addWidget(browser, 7)

    inspector, icol = panel(padding=12, spacing=6)
    icol.addWidget(_label("ITEM DETAILS", "#F6F3F7", 14, True))
    # Paths and evidence can be arbitrarily long. Without a separate
    # inspector scroll area, Qt compresses the labels until they overlap.
    details_scroll = QScrollArea()
    details_scroll.setObjectName("approvedGraveInspectorScroll")
    details_scroll.setWidgetResizable(True)
    details_scroll.setFrameShape(QFrame.NoFrame)
    details_body = QWidget()
    details_body.setObjectName("approvedGraveInspectorBody")
    details_col = QVBoxLayout(details_body)
    details_col.setContentsMargins(2, 2, 2, 2)
    details_col.setSpacing(7)
    details_scroll.setWidget(details_body)
    icol.addWidget(details_scroll, 1)
    window.grave_detail = details_col
    main_row.addWidget(inspector, 3)
    main.setFixedHeight(353)
    page.content.addWidget(main)

    def selected():
        rows = window.grave_table.selectionModel().selectedRows()
        if len(rows) != 1:
            return None
        i = rows[0].row()
        return window._shown_graves[i] if 0 <= i < len(window._shown_graves) else None

    def _personal_rule():
        entry = selected()
        if entry is None:
            window.info("Choose one item", "Select exactly one Graveyard item.")
            return None, None
        action, reason = protection_action(
            entry.path, list(window.settings.get("never_touch", [])))
        return entry, action

    def protect():
        entry, action = _personal_rule()
        if entry is None:
            return
        if action != "Protect":
            window.info("Protection", "This entry cannot have a new personal "
                        "rule from here. Check its existing protection first.")
            return
        window._set_personal_protection(
            entry.path, protect=True, return_route="Graveyard")

    def unprotect():
        entry, action = _personal_rule()
        if entry is None:
            return
        if action != "Unprotect":
            window.info("Protection", "Only an exact personal Never Touch "
                        "rule can be removed. Built-in game and save safeguards remain.")
            return
        window._unprotect_grave(entry)

    def open_path():
        entry = selected()
        if entry:
            window._open_folder(str(Path(entry.path).parent))
        else:
            window.info("Choose one item", "Select a file or folder first.")

    # The locked action strip belongs immediately under the review table.
    # All three mutations still delegate to the existing confirmation/safety
    # code. A protection override never implicitly deletes anything.
    actions = QFrame()
    actions.setObjectName("ggActionStrip")
    action_layout = row(spacing=8, margins=(12, 9, 12, 9))
    actions.setLayout(action_layout)
    window.grave_counter = _label("No items selected.", "#DBE4ED", 12, True)
    action_layout.addWidget(window.grave_counter, 2)
    action_layout.addWidget(button("Select reviewable", window._select_eligible))
    action_layout.addWidget(button("Protect", protect))
    action_layout.addWidget(button("Unprotect", unprotect))
    action_layout.addWidget(button("Open Path", open_path))
    action_layout.addWidget(button(
        "Delete selected…", window._delete_grave_selected, kind="danger"), 1)
    page.content.addWidget(actions)

    total_apparent = sum(_size(item) for item in entries)
    can_review = sum(_size(item) for item in entries if item.can_recycle)
    protected = total_apparent - can_review
    impact = QFrame()
    impact.setObjectName("ggAccentPanel")
    impact.setProperty("accent", "red")
    impact_row = row(spacing=15, margins=(15, 11, 15, 10))
    impact.setLayout(impact_row)
    impact_left = QWidget()
    left_col = QVBoxLayout(impact_left)
    left_col.setContentsMargins(0, 0, 0, 0)
    left_col.setSpacing(4)
    left_col.addWidget(_label("STORAGE IMPACT  /  CANDIDATE SIZES",
                              "#F4F7FB", 14, True))
    left_col.addWidget(CinematicImpactTrack(can_review, protected))
    left_col.addWidget(_label(
        human_size(can_review) + " reviewable   •   " +
        human_size(protected) + " protected   •   " +
        "not confirmed reclaimed space", "#A8C0CE", 11))
    impact_row.addWidget(impact_left, 5)
    def impact_stat(title, value, color):
        col = QWidget()
        body = QVBoxLayout(col)
        body.setContentsMargins(4, 1, 4, 1)
        body.setSpacing(4)
        body.addWidget(_label(title.upper(), "#ACBDCA", 10, True))
        body.addWidget(_label(value, color, 17, True))
        return col
    impact_row.addWidget(impact_stat(
        "Games", str(len(window.inventory.games)), "#64D5EC"), 1)
    impact_row.addWidget(impact_stat(
        "Mod locations", str(len(window.inventory.mods)), "#CC9BF3"), 1)
    impact_row.addWidget(impact_stat(
        "Captures", str(len(window.inventory.screenshots) +
                        len(window.inventory.recordings)), "#D0A4EA"), 1)
    impact_row.addWidget(impact_stat(
        "Potential", human_size(total_apparent), "#EFBB7A"), 1)
    page.content.addWidget(impact)

    recovery_row = QWidget()
    recovery = row(spacing=8)
    recovery_row.setLayout(recovery)
    recovery.addWidget(_label(
        "Manual review only  •  Recycle Bin + Undo  •  Saved games protected",
        "#A2CDBE", 11))
    recovery.addStretch()
    recovery.addWidget(button(
        "Test Recycle Bin recovery", window._test_recycle_bin_safely))
    recovery.addWidget(button(
        "Open Old Files", lambda: window.navigate("Old Files")))
    page.content.addWidget(recovery_row)

    def refresh():
        query = window.grave_search.text().strip().casefold()
        chosen_type = window.grave_type.currentText()
        chosen_state = window.grave_state.currentText()
        chosen_drive = window.grave_drive.currentText()
        threshold = {"All ages": 0, "1+ year": 365,
                     "2+ years": 730, "3+ years": 1095}[
                         window.grave_age.currentText()]
        result = [
            e for e in window.inventory.graveyard
            if (chosen_type == "All types" or e.category == chosen_type)
            and (chosen_state == "All findings"
                 or chosen_state == "Ready for review" and e.can_recycle
                 or chosen_state == "Protected / preview only" and not e.can_recycle)
            and (chosen_drive == "All drives"
                 or Path(e.path).anchor.upper() == chosen_drive)
            and (not threshold or
                 e.age_days is not None and e.age_days >= threshold)
            and (not query or query in (
                e.name + " " + e.path + " " + e.relationship + " " +
                e.finding + " " + e.category).casefold())
        ]
        order = window.grave_sort.currentText()
        if order == "Oldest first":
            result.sort(key=lambda e: (
                e.age_days is None, -(e.age_days or 0), e.name.casefold()))
        elif order == "Newest first":
            result.sort(key=lambda e: (
                e.age_days is None, e.age_days or 0, e.name.casefold()))
        elif order == "Name A–Z":
            result.sort(key=lambda e: e.name.casefold())
        else:
            result.sort(key=lambda e: (-_size(e), e.name.casefold()))

        window._shown_graves = result[:500]
        table = window.grave_table
        table.blockSignals(True)
        table.clearContents()
        table.setRowCount(len(window._shown_graves))
        for idx, entry in enumerate(window._shown_graves):
            rule, _reason = protection_action(
                entry.path, list(window.settings.get("never_touch", [])))
            status = ("Personal rule: unprotect" if rule == "Unprotect"
                      else "Reviewable" if entry.can_recycle
                      else "Preview required" if entry.category == "Old game screenshot"
                      else "Protected")
            cols = (entry.name, entry.category, entry.relationship,
                    human_size(_size(entry)), _age(entry), status)
            for col, value in enumerate(cols):
                cell = QTableWidgetItem(str(value))
                cell.setToolTip(entry.path if col == 0 else
                                entry.finding if col in (1, 2) else str(value))
                if col == 5:
                    cell.setForeground(QBrush(QColor(
                        "#88D9B1" if entry.can_recycle else
                        "#EFAB6D" if rule == "Unprotect" else "#D7B7BC")))
                table.setItem(idx, col, cell)
            if rule == "Unprotect":
                unlock = button(
                    "Unprotect", lambda _=False, e=entry: window._unprotect_grave(e))
                unlock.setAccessibleName("Unprotect your personal rule for " + entry.name)
                unlock.setToolTip("Remove only your own Never Touch rule. No deletion.")
                table.setCellWidget(idx, 5, unlock)
                table.setRowHeight(idx, 42)
            else:
                table.setRowHeight(idx, 32)
        pending = getattr(window, "_pending_grave_key", None)
        if pending:
            for i, e in enumerate(window._shown_graves):
                if e.key == pending:
                    table.selectRow(i)
                    table.scrollToItem(table.item(i, 0))
                    break
        window._pending_grave_key = None
        if window._shown_graves and not table.selectionModel().selectedRows():
            table.selectRow(0)
        table.blockSignals(False)
        update_details()

    def update_details():
        window._grave_details()
        entries = window._selected_grave_entries()
        window.grave_counter.setText(
            (str(len(entries)) + " selected | " +
             human_size(sum(_size(e) for e in entries)) + " apparent bytes")
            if entries else
            (f"{len(window._shown_graves)} matching candidates. "
             "Select one to inspect why it was flagged."))
        if not entries:
            return
        if len(entries) == 1:
            entry = entries[0]
            rule, _ = protection_action(
                entry.path, list(window.settings.get("never_touch", [])))
            if rule == "Protect":
                window.grave_detail.insertWidget(
                    1, button("Protect this item (Never Touch)",
                              lambda _=False, e=entry:
                              window._set_personal_protection(
                                  e.path, protect=True, return_route="Graveyard")))

    for choice in (
        window.grave_search.textChanged,
        window.grave_type.currentTextChanged,
        window.grave_state.currentTextChanged,
        window.grave_drive.currentTextChanged,
        window.grave_age.currentTextChanged,
        window.grave_sort.currentTextChanged,
    ):
        choice.connect(refresh)
    window.grave_table.itemSelectionChanged.connect(update_details)
    window.grave_table.cellDoubleClicked.connect(
        lambda i, _c: window._inspect_grave_entry(window._shown_graves[i])
        if 0 <= i < len(window._shown_graves) else None)
    window.grave_table.setContextMenuPolicy(Qt.CustomContextMenu)
    window.grave_table.customContextMenuRequested.connect(
        window._graveyard_context_menu)
    refresh()
    return page
