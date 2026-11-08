"""Mods-only behaviour for the locked Mods photo layout.

The library layout, shell and every other tab are untouched. This module only fills the Mods
page that LibraryScreens already built: real statuses, the five in-page tabs, bulk actions,
source management and detail values. Everything is read-only against mod managers and mod files.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path

from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QFileDialog, QHeaderView, QMenu
from shiboken6 import isValid

from core import save_settings
from gg_desktop import mods_insight as mi
from gg_desktop.mods_data import identity, mod_page, ordinary
from gg_desktop.models import readable_bytes
from gg_desktop.reference_library import (LibraryScreens, _check, _checked, _combo, _text, _widget, destroy_layout)
from gg_desktop.reference_widgets import CoverArt, MetricStrip, detail_line, detail_section, tool
from gg_desktop.widgets import label, row
from ui_paging import page_window

LIBRARY_HEADERS = ("", "Name", "Game", "Manager", "Version", "Status")
LIBRARY_WIDTHS = (25, 180, 90, 63, 48, 65)
COLORS = {"green": "#27dc74", "amber": "#f7b737", "muted": "#9ca8bd", "": "#d7dfe7"}
TAB_NAMES = ("Library", "Mod Radar", "Load Order", "Profiles", "Conflicts", "Cleanup")


@dataclass
class TabRow:
    key: str
    cells: tuple
    payload: object
    hay: str = ""
    kinds: dict = field(default_factory=dict)
    tip: str = ""


# ---------------------------------------------------------------- page setup
def build(window, control):
    """Called once after the photo Mods page and its controller exist."""
    window._mod_updates = {}
    window._mod_updates_for = None
    window._mod_updates_scanned = False
    window._mod_profile_key = ""
    window._mod_tab_rows = []
    table = window.mod_table
    contents = window.mod_notice.parentWidget().layout()
    window.mod_profile = _combo(["—"], "Saved mod profile")
    window.mod_profile.currentIndexChanged.connect(lambda *_: profile_changed(window))
    contents.insertWidget(contents.indexOf(window.mod_notice) + 1, window.mod_profile)
    window.mod_profile.hide()
    footer = window.mod_selection.parentWidget().layout()
    window.mod_actions = tool("Actions", "list", lambda: show_menu(window, window.mod_actions))
    window.mod_actions.setToolTip("Refresh, check conflicts, export or copy the checked mods")
    footer.insertWidget(1, window.mod_actions)
    table.setContextMenuPolicy(Qt.CustomContextMenu)
    table.customContextMenuRequested.connect(lambda pos: show_menu(window, table.viewport(), pos))


def sync_profiles(window, control, include_all):
    combo = window.mod_profile
    profiles = control.catalog.profiles
    want = [("All saved profiles", "")] if include_all else []
    want += [(p.name + " · " + p.manager, p.key) for p in profiles]
    have = [(combo.itemText(i), combo.itemData(i)) for i in range(combo.count())]
    if have != want:
        with QSignalBlocker(combo):
            combo.clear()
            for text, key in want:
                combo.addItem(text, key)
    key = window._mod_profile_key
    index = combo.findData(key)
    if index < 0:
        chosen = next((p.key for p in profiles if p.selected), "")
        index = combo.findData("" if include_all else chosen)
        if index < 0:
            index = 0
    with QSignalBlocker(combo):
        combo.setCurrentIndex(index)
    window._mod_profile_key = combo.itemData(index) or ""
    combo.setEnabled(combo.count() > 0)


def profile_changed(window):
    window._mod_profile_key = window.mod_profile.currentData() or ""
    if window._mod_tab in {"Load Order", "Conflicts"}:
        window._fill_mods()


# ---------------------------------------------------------------- catalog hook
def catalog_changed(window, control):
    """Runs after every controller notification (including progress ticks)."""
    ensure_updates(window, control)
    apply_metrics(window, control)


def ensure_updates(window, control):
    """MO2 meta.ini update fields are read once per catalog, off the UI thread."""
    marker = id(control.catalog)
    if window._mod_updates_for == marker or control.busy:
        return
    window._mod_updates_for = marker
    entries = [e for e in control.catalog.entries if e.kind == "mod"]
    if not entries:
        window._mod_updates, window._mod_updates_scanned = {}, False
        return
    def finish(result, error):
        if error or window._mod_updates_for != marker:
            return
        window._mod_updates, window._mod_updates_scanned = result or {}, True
        if control.valid():
            apply_metrics(window, control)
            if window.current_route == "Mods":
                window._fill_mods(requested_page=window.mod_pager.page)
    control.task(lambda _emit: mi.scan_updates(entries, control.closed.is_set), finish)


def apply_metrics(window, control):
    strip = window.page.findChild(MetricStrip)
    if strip is None:
        return
    m = mi.metrics(control.catalog, control.report, window._mod_updates if window._mod_updates_scanned else {})
    if m["enabled"] or m["mixed"] or m["disabled"]:
        strip.set_value(1, m["enabled"], "Enabled (saved)" if not m["mixed"] else f"Enabled · {m['mixed']} mixed")
    if window._mod_updates_scanned and window._mod_updates:
        strip.set_value(2, m["outdated"], "Outdated (MO2 data)")
    elif window._mod_updates_scanned:
        strip.set_value(2, "—", "Outdated · No update data")
    if m["conflicts"] is not None:
        strip.set_value(3, m["conflicts"], "Findings · partial" if m["conflicts_limited"] else "Conflict Findings")
    if m["unreferenced"] is not None:
        strip.set_value(4, m["unreferenced"], "Not In Any Profile")


# ---------------------------------------------------------------- table filling
def shape(table, headers, widths):
    if getattr(table, "_gg_shape", LIBRARY_HEADERS) == tuple(headers):
        return
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(list(headers))
    for index, width in enumerate(widths):
        table.setColumnWidth(index, width)
    table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
    table._gg_shape = tuple(headers)


def fill(window, *args, **kwargs):
    if not hasattr(window, "mod_table") or window.current_route != "Mods":
        return
    control = getattr(window.page, "mods", None)
    if window._mod_tab == "Library" or control is None:
        library_fill(window, control, *args, **kwargs)
    else:
        # The profile choice must exist before the rows that depend on it are built.
        combo = getattr(window, "mod_profile", None)
        if window._mod_tab in {"Load Order", "Conflicts"} and combo is not None and isValid(combo):
            sync_profiles(window, control, include_all=window._mod_tab == "Conflicts")
        tab_fill(window, control, kwargs.get("requested_page", 0))
    chrome(window, control)


def chrome(window, control):
    # The first fill runs while the page is still being built; a combo left by the previous visit is deleted.
    combo = getattr(window, "mod_profile", None)
    if combo is None or not isValid(combo):
        return
    tab = window._mod_tab
    visible = control is not None and tab in {"Load Order", "Conflicts"}
    window.mod_profile.setVisible(visible)
    window.mod_sort.setEnabled(tab == "Library")
    window.mod_type.setEnabled(tab == "Library")
    if control is None:
        return
    if control.busy:
        text = control.message
        window.mod_notice.setText((window.mod_notice.text() + "\n" if window.mod_notice.text() else "") + text)
        window.mod_notice.setVisible(True)


def library_fill(window, control, *args, **kwargs):
    table = window.mod_table
    shape(table, LIBRARY_HEADERS, LIBRARY_WIDTHS)
    shown = getattr(window, "_shown_mods", [])
    current = table.currentRow()
    prior = shown[current].record.path if 0 <= current < len(shown) else None
    window._mod_tab_rows = []
    LibraryScreens._fill_mods(window, *args, **kwargs)
    if prior:
        selected = next((i for i, v in enumerate(window._shown_mods) if v.record.path == prior), -1)
        if selected >= 0:
            table.selectRow(selected)
    if control is None:
        return
    catalog = control.catalog
    with QSignalBlocker(table):
        for index, view in enumerate(window._shown_mods):
            entry = getattr(view.record, "catalog_entry", None)
            if not entry:
                continue
            for col in range(table.columnCount() - 1):
                cell = table.item(index, col)
                if cell:
                    cell.setToolTip(control.tooltip(entry))
            cell = table.item(index, 5)
            if cell:
                status = mi.entry_status(entry, catalog)
                cell.setText(status.text)
                cell.setToolTip(status.detail)
                cell.setForeground(QColor(COLORS[status.kind]))


def tab_fill(window, control, requested_page=0):
    tab = window._mod_tab
    headers, widths, builder = TABS[tab]
    table = window.mod_table
    shape(table, headers, widths)
    rows, notice = builder(window, control)
    query = window.mod_search.text().casefold().strip()
    if query:
        rows = [r for r in rows if query in r.hay.casefold()]
    previous = selected_row(window)
    previous_key = previous.key if previous else None
    page = page_window(rows, requested_page)
    window.mod_pager.update_window(page)
    shown = list(page.items)
    window._mod_tab_rows = shown
    window._shown_mods = []
    with QSignalBlocker(table):
        table.setRowCount(0)
        table.setRowCount(len(shown))
        for i, item in enumerate(shown):
            _check(table, i)
            for col, value in enumerate(item.cells, 1):
                cell = _text(table, i, col, value)
                if item.tip:
                    cell.setToolTip(item.tip)
                tone = item.kinds.get(col, "")
                if tone:
                    cell.setForeground(QColor(COLORS[tone]))
            table.setRowHeight(i, 34)
        if shown:
            pick = next((i for i, r in enumerate(shown) if r.key == previous_key), 0)
            table.selectRow(pick)
    if not shown and not notice:
        notice = "Nothing matches the search." if query else "Nothing to show here."
    window.mod_notice.setText(notice)
    window.mod_notice.setVisible(bool(notice))
    window._mod_selection_count()
    window._mod_details()


def selection_count(window):
    table = window.mod_table
    noun = {"Library": "locations", "Load Order": "mods"}.get(window._mod_tab, "rows")
    window.mod_selection.setText(f"{len(_checked(table))} selected · {table.rowCount()} {noun}")


def selected_row(window):
    if window._mod_tab == "Library":
        return None
    index = window.mod_table.currentRow()
    rows = getattr(window, "_mod_tab_rows", [])
    return rows[index] if 0 <= index < len(rows) else None


# ---------------------------------------------------------------- tab builders
def radar_tab(window, control):
    extra = list(window.settings.get("mod_extra_roots", []))
    sources = mi.source_rows(window.inventory, extra)
    rows = []
    for s in sources:
        state = s["state"]
        rows.append(TabRow(identity(s["path"]), (s["name"], s["kind"], state), s,
                           hay=" ".join((s["name"], s["path"], s["kind"], state)),
                           kinds={2: "green"} if s["custom"] else {}, tip=s["path"]))
    notice = ("Read-only source evidence. All detected storage remains protected." if rows else
              "No mod sources found yet. Scan for Mods or add a source folder.")
    return rows, notice


def order_tab(window, control):
    rows_, note = mi.load_order(control.catalog, window._mod_profile_key)
    out = []
    for pos, entry, marker in rows_:
        state = {"+": "Enabled", "-": "Disabled"}.get(marker, "Unknown")
        out.append(TabRow(entry.key, (entry.name, str(pos) if pos else "—", state, entry.version or "—"), entry,
                          hay=" ".join((entry.name, entry.author, entry.path)),
                          kinds={3: {"Enabled": "green"}.get(state, "muted")}, tip=control.tooltip(entry)))
    return out, note


def profiles_tab(window, control):
    out = []
    for item in mi.profile_rows(control.catalog, control.report):
        p = item["profile"]
        found = "—" if item["findings"] is None else str(item["findings"])
        flags = [x for x, on in (("selected when inspected", p.selected), ("older than seven days", p.stale),
                                 ("incomplete", p.incomplete)) if on]
        out.append(TabRow(p.key, (p.name + ("  ●" if p.selected else ""), "MO2" if p.manager == "Mod Organizer 2" else p.manager,
                                  str(item["enabled"]), str(item["disabled"]), found), item,
                          hay=" ".join((p.name, p.manager, p.source)), tip=p.source + ("\n" + ", ".join(flags) if flags else "")))
    notice = ("● marks the profile the manager had selected when Game Grave inspected it. Profiles stay protected; "
              "manage them in the original mod manager." if out else
              "No saved profiles were found. Game Grave reads Mod Organizer 2 profiles after Scan for Mods.")
    return out, notice


def conflicts_tab(window, control):
    if control.report is None:
        return [], (control.message if control.busy else
                    "Conflict check has not completed. Use Actions ▸ Check conflicts.")
    out = []
    for item in mi.conflict_rows(control.catalog, control.report, window._mod_profile_key):
        f = item["finding"]
        out.append(TabRow(f"{f.kind}|{f.profile}|{'|'.join(f.mods)}",
                          (f.kind, item["profile"], str(len(f.mods)), str(f.count or len(f.paths))), item,
                          hay=" ".join((f.kind, f.detail, item["profile"], *item["mods"], *f.paths[:10])),
                          kinds={1: "amber"}, tip=f.detail))
    notice = control.report.summary()
    if not out and not control.report.limited:
        notice = "No findings in the completed checks. " + notice
    return out, notice


def cleanup_tab(window, control):
    out = []
    for item in mi.cleanup_rows(control.catalog, window.inventory):
        action = "Review in Graveyard" if item["source"] == "graveyard" and item["removable"] else "Protected"
        out.append(TabRow(identity(item["path"]) + "|" + item["source"],
                          (item["name"], item["kind"], readable_bytes(item["size"]), action), item,
                          hay=" ".join((item["name"], item["kind"], item["path"], item["note"])), tip=item["note"],
                          kinds={4: "muted" if action == "Protected" else "amber"}))
    return out, "Nothing is removed here. Managed mods and profiles stay protected; review archives in Graveyard or Old Files."


TABS = {
    "Mod Radar": (("", "Source", "Type", "State"), (25, 220, 120, 150), radar_tab),
    "Load Order": (("", "Mod", "Position", "Saved", "Version"), (25, 200, 62, 70, 70), order_tab),
    "Profiles": (("", "Profile", "Manager", "Enabled", "Disabled", "Findings"), (25, 170, 60, 62, 62, 62), profiles_tab),
    "Conflicts": (("", "Finding", "Profile", "Mods", "Paths"), (25, 200, 100, 50, 50), conflicts_tab),
    "Cleanup": (("", "Item", "Type", "Size", "Action"), (25, 180, 110, 62, 100), cleanup_tab),
}


def set_tab(window, name):
    window._mod_tab = name if name in TAB_NAMES else "Library"
    window._fill_mods()


# ---------------------------------------------------------------- details
def entry_for_view(window):
    index = window.mod_table.currentRow()
    shown = getattr(window, "_shown_mods", [])
    view = shown[index] if 0 <= index < len(shown) else None
    return view, (getattr(view.record, "catalog_entry", None) if view else None)


def status_lines(window, control, contents, entry):
    catalog = control.catalog
    detail_section(contents, "Mod Status")
    status = mi.entry_status(entry, catalog)
    detail_line(contents, "check", "Status", status.text, tone=COLORS[status.kind] if status.kind != "muted" else "")
    selected = next((p for p in catalog.profiles if p.selected), None)
    position = "Not established"
    if entry.kind == "mod" and selected:
        rows, _note = mi.load_order(catalog, selected.key)
        hit = next((pos for pos, e, _m in rows if e.key == entry.key), None)
        if hit:
            position = f"{hit} of {len(rows)} in {selected.name} (relative)"
        elif selected.manager == "Mod Organizer 2":
            position = "Not listed in " + selected.name
        else:
            position = "Not established for this manager"
    detail_line(contents, "list", "Load Order", position)
    deps = entry.dependencies
    detail_line(contents, "help", "Requires", (f"{len(deps)} declared: " + ", ".join(d.name for d in deps[:5]) +
                                               (" …" if len(deps) > 5 else "")) if deps else "None declared in metadata")
    found = control.findings(entry)
    detail_line(contents, "warning", "Conflicts", (f"{len(found)} finding(s)" + (" (partial coverage)" if control.report.limited else ""))
                if control.report and found else "None found in completed checks" if control.report else "Check pending")
    names = {p.key: p.name for p in catalog.profiles}
    listed = [names[k] for k in entry.profiles if k in names]
    detail_line(contents, "shield", "Listed In", (f"{len(listed)} saved profile(s): " + ", ".join(listed[:4]) +
                                                 (" …" if len(listed) > 4 else "")) if listed else "No saved profile")
    info = window._mod_updates.get(entry.key)
    if info:
        detail_line(contents, "refresh", "Update", f"{info.newest} recorded by MO2 (installed {info.installed or 'unknown'})"
                    if info.outdated else info.note, tone=COLORS["amber"] if info.outdated else "")


def library_details(window):
    control = getattr(window.page, "mods", None)
    view, entry = entry_for_view(window)
    if not entry or not control:
        return LibraryScreens._mod_details(window)
    contents = window.mod_details.content
    destroy_layout(contents)
    contents.addWidget(CoverArt(view.game if view.game != "Unverified" else entry.name, height=84))
    title = label(entry.name, "detailTitle", wrap=True)
    title.setTextFormat(Qt.PlainText)
    contents.addWidget(title)
    description = label(entry.description, "subtle", wrap=True)
    description.setTextFormat(Qt.PlainText)
    contents.addWidget(description)
    for symbol, name, value in (("game", "Game", view.game), ("mods", "Manager", entry.source),
                                ("file", "Version", entry.version), ("help", "Author", entry.author),
                                ("folder", "Location", entry.path)):
        detail_line(contents, symbol, name, value)
    contents.addWidget(tool("Open Folder", "folder", lambda: control.open_folder(entry), kind="primary"))
    actions = row(spacing=4)
    actions.addWidget(tool("Details", "file", lambda: control.explain(entry)))
    page_button = tool("Mod Page", "search", lambda: control.open_page(entry))
    page_button.setEnabled(bool(mod_page(entry.page)))
    actions.addWidget(page_button)
    manager_button = tool("Manager", "mods", lambda: control.open_folder(entry, True))
    manager_button.setEnabled(bool(entry.manager_folder))
    actions.addWidget(manager_button)
    contents.addWidget(_widget(actions))
    status_lines(window, control, contents, entry)
    detail_section(contents, "Saved Profile Evidence")
    contents.addWidget(label(entry.state, "subtle", wrap=True))
    detail_section(contents, "Dependencies & Conflicts")
    findings = control.findings(entry)
    for finding in findings[:4]:
        text = label(finding.kind + ": " + finding.detail, "caption", wrap=True)
        text.setTextFormat(Qt.PlainText)
        contents.addWidget(text)
    if not findings:
        contents.addWidget(label("No findings in the completed checks. Runtime compatibility is unverified." if control.report
                                 else "Checks pending. Runtime compatibility is unverified.", "caption", wrap=True))
    contents.addWidget(tool("Open Mod Radar Tools", "radio", control.open_tools))
    contents.addStretch()


def plain_label(text, style="subtle"):
    item = label(str(text), style, wrap=True)
    item.setTextFormat(Qt.PlainText)
    return item


def busy_buttons(window, control, contents):
    box = row(spacing=4)
    refresh = tool("Refresh", "refresh", control.refresh_catalog)
    refresh.setEnabled(not control.busy)
    check = tool("Check", "radio", control.check_conflicts, kind="primary")
    check.setEnabled(not control.busy)
    box.addWidget(refresh)
    box.addWidget(check)
    contents.addWidget(_widget(box))
    if control.busy:
        cancel = tool("Cancel Checks", "close", control.stop)
        cancel.setEnabled(not control.cancel.is_set())
        contents.addWidget(cancel)


def radar_details(window, control, contents, item):
    contents.addWidget(CoverArt("Game Grave", height=70))
    contents.addWidget(label("Mod Radar", "detailTitle", wrap=True))
    contents.addWidget(plain_label(control.message if control.busy else "Read-only evidence from saved manager files."))
    busy_buttons(window, control, contents)
    if item:
        s = item.payload
        detail_section(contents, "Selected Source")
        contents.addWidget(plain_label(s["name"], "detailValue"))
        detail_line(contents, "mods", "Type", s["kind"])
        detail_line(contents, "shield", "State", s["state"])
        detail_line(contents, "folder", "Location", s["path"])
        open_button = tool("Open Folder", "folder", lambda: open_path(window, s["path"]), kind="primary")
        contents.addWidget(open_button)
        if s["custom"]:
            contents.addWidget(tool("Stop Scanning This Source", "close", lambda: remove_source(window, s["path"])))
            contents.addWidget(plain_label("Removing a source only stops Game Grave scanning it. No file is changed.", "caption"))
    detail_section(contents, "Coverage")
    for name, text, tone in mi.radar_rows(control.catalog, control.report, window.inventory, []):
        contents.addWidget(plain_label(f"{name}: {text}", "caption" if tone == "info" else "warning"))


def order_details(window, control, contents, item):
    if not item:
        contents.addWidget(label("Load Order", "detailTitle", wrap=True))
        contents.addWidget(plain_label("Choose a saved profile above, then select a mod to see its position."))
        return
    entry = item.payload
    contents.addWidget(CoverArt(entry.name, height=70))
    contents.addWidget(plain_label(entry.name, "detailTitle"))
    detail_line(contents, "list", "Position", item.cells[1])
    detail_line(contents, "check", "Saved", item.cells[2])
    detail_line(contents, "file", "Version", entry.version or "Unknown")
    detail_line(contents, "folder", "Location", entry.path)
    contents.addWidget(tool("Details", "file", lambda: control.explain(entry), kind="primary"))
    contents.addWidget(tool("Open Folder", "folder", lambda: control.open_folder(entry)))
    contents.addWidget(plain_label("Position comes from the manager's saved list and is relative. Game Grave never reorders mods.", "caption"))


def profile_details(window, control, contents, item):
    if not item:
        contents.addWidget(label("Profiles", "detailTitle", wrap=True))
        contents.addWidget(plain_label("Select a saved profile to see what it lists."))
        return
    p = item.payload["profile"]
    contents.addWidget(plain_label(p.name, "detailTitle"))
    detail_line(contents, "mods", "Manager", p.manager)
    detail_line(contents, "check", "Enabled", item.payload["enabled"])
    detail_line(contents, "close", "Disabled", item.payload["disabled"])
    if item.payload["unknown"]:
        detail_line(contents, "help", "Unmarked", item.payload["unknown"])
    detail_line(contents, "warning", "Findings", "Not checked yet" if item.payload["findings"] is None else item.payload["findings"])
    detail_line(contents, "folder", "Saved File", p.source)
    for flag, on in (("Selected by the manager when inspected", p.selected), ("Saved list is older than seven days", p.stale),
                     ("Saved list was only partly read", p.incomplete)):
        if on:
            contents.addWidget(plain_label(flag, "warning" if flag.startswith(("Saved",)) else "caption"))
    folder = str(Path(p.source).parent)
    contents.addWidget(tool("Open Profile Folder", "folder", lambda: open_path(window, folder), kind="primary"))
    contents.addWidget(tool("View Load Order", "list", lambda: goto(window, "Load Order", p.key)))
    contents.addWidget(tool("View Conflicts", "warning", lambda: goto(window, "Conflicts", p.key)))
    contents.addWidget(plain_label("Profiles stay protected. Switch or edit them in the original mod manager.", "caption"))


def conflict_details(window, control, contents, item):
    if not item:
        contents.addWidget(label("Conflicts", "detailTitle", wrap=True))
        contents.addWidget(plain_label(control.message if control.busy else
                                       "Select a finding to see the mods and files involved."))
        busy_buttons(window, control, contents)
        return
    f = item.payload["finding"]
    contents.addWidget(plain_label(f.kind, "detailTitle"))
    detail_line(contents, "shield", "Profile", item.payload["profile"])
    contents.addWidget(plain_label(f.detail))
    detail_section(contents, "Mods Involved")
    lookup = {e.key: e for e in control.catalog.entries}
    for key in f.mods[:8]:
        entry = lookup.get(key)
        if entry:
            contents.addWidget(tool(entry.name, "mods", lambda e=entry: control.explain(e)))
    if f.paths:
        detail_section(contents, f"Files ({f.count or len(f.paths)})")
        contents.addWidget(plain_label("\n".join(f.paths[:20]), "caption"))
    contents.addWidget(plain_label("File overlaps may be intentional. Winners and runtime compatibility are unverified.", "caption"))
    export = tool("Export Report…", "download", lambda: control.export(window.page))
    export.setEnabled(control.report is not None)
    contents.addWidget(export)


def cleanup_details(window, control, contents, item):
    if not item:
        contents.addWidget(label("Cleanup", "detailTitle", wrap=True))
        contents.addWidget(plain_label("Review items only. Game Grave removes nothing from this tab."))
        return
    c = item.payload
    contents.addWidget(plain_label(c["name"], "detailTitle"))
    detail_line(contents, "file", "Type", c["kind"])
    detail_line(contents, "storage", "Size", readable_bytes(c["size"]))
    detail_line(contents, "folder", "Location", c["path"])
    contents.addWidget(plain_label(c["note"]))
    contents.addWidget(tool("Open Folder", "folder", lambda: open_path(window, c["path"]), kind="primary"))
    if c["source"] == "graveyard" and c["removable"]:
        contents.addWidget(tool("Review in Graveyard", "grave", lambda: window.navigate("Graveyard")))
    contents.addWidget(plain_label("Managed mods, profiles and saves are never removed by Game Grave.", "caption"))


DETAILS = {"Mod Radar": radar_details, "Load Order": order_details, "Profiles": profile_details,
           "Conflicts": conflict_details, "Cleanup": cleanup_details}


def details(window):
    control = getattr(window.page, "mods", None)
    if window._mod_tab == "Library" or control is None:
        return library_details(window)
    contents = window.mod_details.content
    contents.setSpacing(5)
    destroy_layout(contents)
    DETAILS[window._mod_tab](window, control, contents, selected_row(window))
    contents.addStretch()


# ---------------------------------------------------------------- actions
def goto(window, tab, profile_key=""):
    if profile_key:
        window._mod_profile_key = profile_key
    window.mod_tabs.select(tab)
    set_tab(window, tab)


def open_path(window, path):
    target = Path(path)
    folder = target if ordinary(target, True) else target.parent
    control = getattr(window.page, "mods", None)
    if not ordinary(folder, True):
        window.info("Folder unavailable", "This folder is missing, unreadable or redirected. Run Scan for Mods again if it moved.")
        return
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
        window.error("Could not open folder", "The system did not accept this folder. " + str(folder))


def targets(window, control):
    """Checked rows, else the highlighted row. Only individual catalog entries."""
    table = window.mod_table
    if window._mod_tab == "Library":
        shown = getattr(window, "_shown_mods", [])
        picks = _checked(table) or ([table.currentRow()] if table.currentRow() >= 0 else [])
        found = [getattr(shown[i].record, "catalog_entry", None) for i in picks if 0 <= i < len(shown)]
        return [e for e in found if e]
    rows = getattr(window, "_mod_tab_rows", [])
    picks = _checked(table) or ([table.currentRow()] if table.currentRow() >= 0 else [])
    out, lookup = [], {e.key: e for e in control.catalog.entries}
    for i in picks:
        if not 0 <= i < len(rows):
            continue
        payload = rows[i].payload
        if window._mod_tab == "Load Order":
            out.append(payload)
        elif window._mod_tab == "Conflicts":
            out += [lookup[k] for k in payload["finding"].mods if k in lookup]
    seen, unique = set(), []
    for e in out:
        if e.key not in seen:
            seen.add(e.key)
            unique.append(e)
    return unique


def copy_paths(window, entries):
    if entries:
        QApplication.clipboard().setText("\n".join(e.path for e in entries))
        window.status.setText(f"Copied {len(entries)} path(s).")


def export_destination_ok(window, control, target):
    protected = [e.path for e in control.catalog.entries] + [e.manager_folder for e in control.catalog.entries if e.manager_folder]
    protected += [g.install_path for g in window.inventory.games]
    protected += [str(getattr(s, "path", "")) for s in window.inventory.saves]
    normalized = identity(target)
    for folder in protected:
        root = identity(folder)
        if root and (normalized == root or normalized.startswith(root.rstrip("/\\") + os.sep)):
            raise ValueError("Save exports outside game, mod, manager and save locations.")


def export_selected(window, control, entries):
    if not entries:
        window.info("Choose mods first", "Check one or more mods (or highlight a row), then export.")
        return
    filename, _ = QFileDialog.getSaveFileName(window, "Export selected mods to a new file", "Selected-Mods.json", "JSON (*.json)")
    if not filename:
        return
    try:
        target = Path(filename)
        if not target.suffix:
            target = target.with_suffix(".json")
        if not ordinary(target.parent, True):
            raise ValueError("Choose an existing ordinary destination folder.")
        export_destination_ok(window, control, target)
        payload = mi.dumps(mi.export_selection(entries, control.catalog, control.report, window._mod_updates)).encode("utf-8")
        with target.open("xb") as stream:
            stream.write(payload)
        window.info("Selection exported", f"{target}\nContains local paths, versions and saved-profile evidence for {len(entries)} mod(s).")
    except FileExistsError:
        window.info("Choose a new filename", "That file already exists. Choose a new name to keep both files.")
    except (OSError, ValueError, TypeError) as exc:
        window.error("Could not export", str(exc))


def remove_source(window, root):
    roots = list(window.settings.get("mod_extra_roots", []))
    match = [r for r in roots if identity(r) == identity(root)]
    if not match:
        return
    if not window.confirm("Stop scanning this source?",
                          "Game Grave will stop scanning:\n" + root + "\n\nNo file or folder is changed or removed.", destructive=False):
        return
    updated = dict(window.settings, mod_extra_roots=[r for r in roots if r not in match])
    try:
        save_settings(updated)
    except (OSError, ValueError) as exc:
        window.error("Source not updated", str(exc))
        return
    window.settings = updated
    window.start_scan()


def build_menu(window, control, parent):
    menu = QMenu(parent)
    entries = targets(window, control)
    many = f" ({len(entries)})" if len(entries) > 1 else ""
    inspect = menu.addAction("Inspect details")
    inspect.setEnabled(bool(entries))
    inspect.triggered.connect(lambda: control.explain(entries[0]))
    folder = menu.addAction("Open folder")
    folder.setEnabled(bool(entries) and ordinary(entries[0].path, True))
    folder.triggered.connect(lambda: control.open_folder(entries[0]))
    copy = menu.addAction("Copy path" + ("s" if len(entries) > 1 else "") + many)
    copy.setEnabled(bool(entries))
    copy.triggered.connect(lambda: copy_paths(window, entries))
    export = menu.addAction("Export selected mods…" if len(entries) != 1 else "Export this mod…")
    export.setEnabled(bool(entries))
    export.triggered.connect(lambda: export_selected(window, control, entries))
    menu.addSeparator()
    refresh = menu.addAction("Refresh details")
    refresh.setEnabled(not control.busy)
    refresh.triggered.connect(control.refresh_catalog)
    check = menu.addAction("Check conflicts")
    check.setEnabled(not control.busy)
    check.triggered.connect(control.check_conflicts)
    cancel = menu.addAction("Cancel checks")
    cancel.setEnabled(control.busy and not control.cancel.is_set())
    cancel.triggered.connect(control.stop)
    report = menu.addAction("Export conflict report…")
    report.setEnabled(control.report is not None)
    report.triggered.connect(lambda: control.export(window.page))
    menu.addSeparator()
    tools_action = menu.addAction("Advanced tools window…")
    tools_action.triggered.connect(control.open_tools)
    return menu


def show_menu(window, anchor, pos=None):
    control = getattr(window.page, "mods", None)
    if control is None or not control.valid():
        return
    menu = build_menu(window, control, window.page)
    point = anchor.mapToGlobal(pos) if pos is not None else anchor.mapToGlobal(anchor.rect().bottomLeft())
    menu.exec(point)
    menu.deleteLater()


def activate(window):
    """Double-click or Enter on a row."""
    control = getattr(window.page, "mods", None)
    if control is None:
        return
    if window._mod_tab == "Library":
        _view, entry = entry_for_view(window)
        if entry:
            control.explain(entry)
        return
    row_ = selected_row(window)
    if not row_:
        return
    tab = window._mod_tab
    if tab == "Profiles":
        goto(window, "Load Order", row_.payload["profile"].key)
    elif tab in {"Load Order"}:
        control.explain(row_.payload)
    elif tab == "Conflicts":
        entries = targets(window, control)[:1] or [e for e in control.catalog.entries if e.key in row_.payload["finding"].mods][:1]
        if entries:
            control.explain(entries[0])
    elif tab in {"Mod Radar", "Cleanup"}:
        open_path(window, row_.payload["path"])
