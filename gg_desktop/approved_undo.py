"""Approved Undo Center: genuine recovery ledger, verified restore and inspector.

No automatic restore, no file overwrite, no invented retention periods, and no
assumption that a logged move is free disk space or a recoverable file.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from core import human_size
from recovery import get_records, check_restore, restore as restore_recycled
from gg_desktop.reference_hero import ReferenceHero
from gg_desktop.visuals import RecoveryRoute
from gg_desktop.widgets import button, data_table, label, panel, row


def _text(text, color="#C3CDD7", *, size=11, bold=False, wrap=True):
    w = label(str(text), "caption", wrap=wrap)
    w.setStyleSheet(f"background:transparent;color:{color};font-size:{size}px;"
                    + ("font-weight:800;" if bold else ""))
    w.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return w


def _stat(title, value, tone):
    from gg_desktop.visuals import nav_icon
    frame = QFrame()
    frame.setObjectName("approvedUndoStat")
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(10, 6, 10, 7)
    layout.setSpacing(9)
    icon_route = {
        "Actions logged": "Undo Center",
        "Files recorded": "Old Files",
        "Logged moves": "Other Storage",
        "Verified available": "Settings",
        "Not yet checked": "Graveyard",
    }.get(title, "Undo Center")
    icon = QLabel()
    icon.setPixmap(nav_icon(icon_route).pixmap(30, 30))
    icon.setFixedSize(31,31)
    layout.addWidget(icon)
    text = QWidget()
    col = QVBoxLayout(text)
    col.setContentsMargins(0, 0, 0, 0)
    col.setSpacing(2)
    col.addWidget(_text(title.upper(), "#BEC7D3", size=11, bold=True))
    col.addWidget(_text(value, tone, size=23, bold=True))
    layout.addWidget(text, 1)
    return frame


def _timestamp(record):
    return str(record.get("time", "Unknown"))[:19]


def _bytes(record):
    size = record.get("size")
    return size if type(size) is int and size >= 0 else 0


def render_approved_undo(window):
    page = window.page_for("Undo Center")
    page.content.setContentsMargins(11, 7, 11, 17)
    page.content.setSpacing(9)
    page.content.addWidget(ReferenceHero(
        "undo", "Undo Center",
        "Review previous cleanup actions and restore items safely."))

    records = list(reversed(get_records()))[:500]
    moved = sum(_bytes(r) for r in records)
    restored = sum(r.get("state") == "Restored" for r in records)
    known_available = sum(r.get("state") == "Available" for r in records)
    unknown = sum(r.get("state") in ("Not checked", None, "") for r in records)

    metrics = QWidget()
    m = row(spacing=7)
    metrics.setLayout(m)
    for title, value, tone in (
        ("Actions logged", str(len(records)), "#6DD9E9"),
        ("Files recorded", str(len(records)), "#D4B4EA"),
        ("Logged moves", human_size(moved), "#ECC18B"),
        ("Verified available", str(known_available), "#82D8B1"),
        ("Not yet checked", str(unknown), "#F6B078"),
    ):
        m.addWidget(_stat(title, value, tone), 1)
    page.content.addWidget(metrics)

    filter_bar = QWidget()
    filters = row(spacing=8)
    filter_bar.setLayout(filters)
    status = QComboBox()
    status.addItems(["All states", "Available", "Not checked", "Not found",
                     "Needs review", "Restored"])
    status.setAccessibleName("Filter recovery state")
    filters.addWidget(status, 1)
    action = QComboBox()
    action.addItems(["All actions"] + sorted({str(r.get("action", "Unknown"))
                      for r in records}))
    action.setAccessibleName("Filter recovery action")
    filters.addWidget(action, 1)
    search = QLineEdit()
    search.setPlaceholderText("Search operations and original paths…")
    search.setAccessibleName("Search the recovery ledger")
    filters.addWidget(search, 3)
    filters.addWidget(button("Refresh", lambda: window.navigate("Undo Center")))
    page.content.addWidget(filter_bar)

    workspace = QWidget()
    wrow = row(spacing=9)
    workspace.setLayout(wrow)

    history, hcol = panel(padding=8, spacing=7)
    hcol.addWidget(_text("CLEANUP HISTORY", "#FAFAFB", size=14, bold=True))
    table = data_table([
        "ORIGINAL LOCATION", "ACTION", "SIZE", "RECORDED", "WINDOWS STATUS"])
    table.setAccessibleName("Real Game Grave recovery ledger")
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    for idx, width in enumerate((255, 125, 95, 152, 115)):
        table.setColumnWidth(idx, width)
    table.horizontalHeader().setStretchLastSection(True)
    table.setMinimumHeight(310)
    hcol.addWidget(table, 1)
    summary = _text("Select a record to check recoverability.", "#A7B7C4")
    hcol.addWidget(summary)
    wrow.addWidget(history, 7)

    details, dcol = panel(padding=12, spacing=6)
    dcol.addWidget(_text("RESTORE DETAILS", "#F5F5FB", size=14, bold=True))
    heading = _text("Choose an operation", "#FFFFFF", size=13, bold=True)
    dcol.addWidget(heading)
    path_detail = _text("No record selected.", "#AFC6D6")
    dcol.addWidget(path_detail)
    meta = _text("", "#A9B6C6")
    dcol.addWidget(meta)
    recovery_state = _text("Availability has not been verified.",
                           "#F0B57E", bold=True)
    dcol.addWidget(recovery_state)
    route = RecoveryRoute()
    route.setMinimumHeight(150)
    dcol.addWidget(route)
    wrow.addWidget(details, 3)
    page.content.addWidget(workspace)

    def chosen():
        selected = table.selectionModel().selectedRows()
        if not selected:
            return None
        index = selected[0].row()
        return current[index] if 0 <= index < len(current) else None

    def refresh_details():
        rec = chosen()
        if rec is None:
            heading.setText("Choose an operation")
            path_detail.setText("Select a record to inspect its original path.")
            meta.setText("")
            recovery_state.setText("Not verified")
            route.set_record("Choose an operation", "Not checked")
            return
        path = str(rec.get("path", "Unknown"))
        heading.setText(Path(path).name or "Recorded operation")
        path_detail.setText(path)
        meta.setText(
            f"{rec.get('action', 'Manual')} • {_bytes(rec):,} bytes • {_timestamp(rec)}")
        state = str(rec.get("state", "Not checked"))
        recovery_state.setText(
            "Previous check: " + state +
            "\nThis status may have changed in Windows since it was recorded.")
        route.set_record(path, state)

    def refill():
        nonlocal current
        query = search.text().strip().casefold()
        state = status.currentText()
        kind = action.currentText()
        current = [
            record for record in records
            if (state == "All states" or record.get("state", "Not checked") == state)
            and (kind == "All actions" or record.get("action", "Unknown") == kind)
            and (not query or query in (
                str(record.get("path", "")) + " " +
                str(record.get("action", "")) + " " +
                str(record.get("state", ""))).casefold())
        ]
        table.blockSignals(True)
        table.clearContents()
        table.setRowCount(len(current))
        for idx, rec in enumerate(current):
            state_text = str(rec.get("state", "Not checked"))
            cols = (
                Path(str(rec.get("path", ""))).name or "Unknown",
                rec.get("action", "Manual"), human_size(_bytes(rec)),
                _timestamp(rec), state_text,
            )
            for col, value in enumerate(cols):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(rec.get("path", "")) if col == 0 else str(value))
                if col == 4:
                    item.setForeground(QBrush(QColor(
                        "#81D6AB" if state_text == "Available" else
                        "#E5AB75" if state_text == "Not checked" else
                        "#CCB2BF")))
                table.setItem(idx, col, item)
        if current:
            table.selectRow(0)
        table.blockSignals(False)
        summary.setText(
            f"{len(current)} matching recorded actions. "
            "Unverified entries may no longer exist in Windows Recycle Bin.")
        refresh_details()

    current = []
    table.itemSelectionChanged.connect(refresh_details)
    status.currentTextChanged.connect(refill)
    action.currentTextChanged.connect(refill)
    search.textChanged.connect(refill)
    refill()

    def verify():
        rec = chosen()
        if not rec:
            window.info("Select an action", "Select one recorded item first.")
            return
        item_id = rec.get("id")
        if not isinstance(item_id, str) or not item_id:
            window.error("Recovery record incomplete",
                         "This record has no valid ID and cannot be verified.")
            return
        window.job(lambda _progress: check_restore(item_id),
                   lambda outcome: (window.info(
                       "Windows Recycle Bin verification", str(outcome) +
                       "\n\nThe next restore still requires revalidation."),
                       window.navigate("Undo Center")),
                   error_title="Cannot verify Windows recovery")

    def restore():
        if window.cleaning or window.scanning:
            window.info("Game Grave is busy", "Finish the current operation first.")
            return
        rec = chosen()
        if not rec:
            window.info("Select an action", "Select an individual record first.")
            return
        item_id = rec.get("id")
        if not isinstance(item_id, str) or not item_id:
            window.error("Recovery record incomplete",
                         "This record has no valid ID and cannot be restored.")
            return
        if not window.confirm(
            "Restore this exact item from Windows Recycle Bin?",
            "Restore to its original location?\n" +
            str(rec.get("path", "Unknown")) +
            "\n\nAn existing file will never be overwritten. A unique matching "
            "Windows Recycle Bin item must still be present."):
            return
        window.cleaning = True
        def finished(result):
            window.cleaning = False
            window.info("Restore result", str(result))
            window.navigate("Undo Center")
        window.job(lambda _progress: restore_recycled(item_id), finished,
                   error_title="Restore could not be verified")

    actions = QWidget()
    ar = row(spacing=8)
    actions.setLayout(ar)
    ar.addWidget(button("Verify exact Windows match", verify))
    ar.addWidget(button("Restore selected…", restore, kind="primary"))
    ar.addWidget(button("Open Cleanup History", lambda: window.navigate("Undo Center")))
    ar.addStretch()
    # Restore controls appear below the recovery-safety/insights modules, as
    # in the locked image, rather than interrupting the evidence inspector.
    safety, sc = panel(padding=13, spacing=7)
    sc.addWidget(_text("RECOVERY SAFETY  •  CHECK BEFORE RESTORING",
                       "#97D4AF", size=12, bold=True))
    sc.addWidget(_text(
        "Game Grave will not silently overwrite an existing file or guess a "
        "Recycle Bin match. Emptying the bin, system cleanup and duplicate "
        "paths can make restoration impossible. No countdown is guaranteed.",
        "#BDC9D7", wrap=True))
    safety.setObjectName("ggAccentPanel")
    safety.setProperty("accent", "green")
    sc.addWidget(_text(
        "An exact Windows Recycle Bin match must still exist. A previous "
        "successful check is not a promise that restoration remains possible.",
        "#A1D8C1", size=11, wrap=True))

    insight, ic = panel(padding=13, spacing=6)
    insight.setObjectName("ggAccentPanel")
    insight.setProperty("accent", "amber")
    ic.addWidget(_text("UNDO INSIGHTS  /  RECORDED STATE",
                       "#F1CA80", size=14, bold=True))
    for heading, value, tone in (
        ("Available at last verification", known_available, "#75DCB3"),
        ("Not yet checked", unknown, "#EFB979"),
        ("Already restored", restored, "#8BCCE8"),
    ):
        metric = QWidget()
        line = row(spacing=8)
        metric.setLayout(line)
        line.addWidget(_text(heading, "#BFC9D5", size=12), 1)
        line.addWidget(_text(str(value), tone, size=16, bold=True))
        ic.addWidget(metric)
    ic.addWidget(_text(
        "Windows Recycle Bin items have no predictable expiration that "
        "Game Grave can promise. Use Save Vault or Resurrection Kit when "
        "you need independently verified backups.",
        "#AFC0D0", size=11, wrap=True))

    assurance = QWidget()
    assurance_row = row(spacing=10)
    assurance.setLayout(assurance_row)
    assurance_row.addWidget(safety, 1)
    assurance_row.addWidget(insight, 1)
    page.content.addWidget(assurance)

    actions.setObjectName("ggActionStrip")
    actions.layout().setContentsMargins(11, 9, 11, 9)
    page.content.addWidget(actions)

    if not records:
        path_detail.setText(
            "No recovery operations have been logged. "
            "Game Grave will record future approved Recycle Bin moves.")
    return page
