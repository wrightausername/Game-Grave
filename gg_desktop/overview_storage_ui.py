"""Live behavior for the existing Overview, isolated from the locked tabs."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import threading
import weakref

from PySide6.QtCore import QObject, QEvent, Qt, QTimer, Signal
from PySide6.QtWidgets import QComboBox, QDialog, QLineEdit, QListWidget, QListWidgetItem, QTableWidget
from shiboken6 import isValid

from core import friendly_activity, human_size, save_settings
from gg_desktop.overview_storage import CATEGORIES, inventory_key, measure_storage, path_key
from gg_desktop.reference_library import _table, _text
from gg_desktop.reference_widgets import CARD_ROLE
from gg_desktop.widgets import button, column, label, row


def coverage_reports(inventory, settings):
    """Describe accepted evidence without inventing successful source scans."""
    reports, groups = [], defaultdict(list)
    for game in inventory.games:
        groups[game.launcher].append(game)
    for source, games in sorted(groups.items()):
        reports.append(dict(source=source, status="Detected", count=len(games),
            paths=sorted({g.install_path for g in games if g.install_path}),
            detail="Accepted installation records. Folder sizes are measured separately in Storage Overview."))
    for source, records in (("Mod locations", inventory.mods), ("Old Files", inventory.files),
                            ("Screenshots", inventory.screenshots), ("Recordings", inventory.recordings)):
        reports.append(dict(source=source, status="Detected" if records else "No findings" if inventory.scanned_at else "Not scanned",
            count=len(records), paths=sorted({r.path for r in records}),
            detail="Accepted scan findings within the configured scope; no findings does not prove an entire drive was inspected."))
    if inventory.warnings:
        reports.append(dict(source="Scan warnings", status="Partial", count=len(inventory.warnings), paths=[],
                            detail="\n".join(inventory.warnings)))
    return reports


class OverviewStorageController(QObject):
    changed = Signal()

    def __init__(self, window, page):
        super().__init__(page)
        self.window, self.page = window, page
        self.active = threading.Event()
        self.active.set()
        self.cancel = threading.Event()
        active, cancel = self.active, self.cancel
        page.destroyed.connect(lambda: (active.clear(), cancel.set()))
        self.storage_busy = False
        self.snapshot = None
        self.message = "Scan PC to detect your game libraries and mod locations."
        self.legend_targets = {}

    def valid(self):
        return (isValid(self) and self.active.is_set() and isValid(self.window)
                and self.window.page is self.page and self.window.current_route == "Overview")

    def bind_native(self):
        w = self.window
        w.overview_ring.activated.connect(self.storage_details)
        w.overview_ring.setAccessibleName("Measured game and mod storage; press Enter for breakdown")
        for name, (caption, value, _) in w.overview_legend.items():
            for widget in (caption, value):
                widget.setCursor(Qt.PointingHandCursor)
                widget.setFocusPolicy(Qt.StrongFocus)
                widget.setAccessibleName("Inspect " + name + " storage")
                widget.installEventFilter(self)
                self.legend_targets[widget] = name
        w.scan_button.installEventFilter(self)
        w.cancel_button.installEventFilter(self)
        w.overview_library.favoriteRequested.connect(self.favorite)
        bar = w.overview_library.horizontalScrollBar()
        bar.rangeChanged.connect(self.sync_pager)
        bar.valueChanged.connect(self.sync_pager)
        w.global_search.textChanged.connect(self.search)
        w.global_search.returnPressed.connect(self.search_results)
        # Small UI sync only: storage is measured once per accepted inventory or
        # explicit refresh, never recursively rescanned every timer tick.
        self.timer = QTimer(self)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self.sync_controls)
        self.timer.start()
        self.sync_controls()
        self.sync_pager()
        QTimer.singleShot(0, self.refresh_storage)

    def eventFilter(self, target, event):
        category = self.legend_targets.get(target)
        if category and ((event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton)
                or (event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space))):
            self.storage_details(category)
            return True
        if event.type() == QEvent.EnabledChange:
            self.sync_controls()
        return False

    def sync_controls(self):
        if not self.valid():
            return
        w = self.window
        for control in (w.overview_hero.scan, w.overview_quick_scan):
            control.setEnabled(not w.scanning and not w.cleaning)
        w.overview_hero.locations.setEnabled(not w.cleaning)
        w.overview_cancel.setVisible(w.scanning)
        w.overview_cancel.setEnabled(w.scanning and not w.cancel.is_set())
        w.overview_scan_status.setText(w.status.text())

    def sync_pager(self, *_):
        if self.valid():
            w = self.window
            bar = w.overview_library.horizontalScrollBar()
            w.overview_previous.setEnabled(bar.value() > bar.minimum())
            w.overview_next.setEnabled(bar.value() < bar.maximum())

    def refresh_storage(self, force=False):
        if not self.valid() or self.storage_busy:
            return
        inventory = self.window.inventory
        if not inventory.scanned_at:
            self.render()
            return
        key = inventory_key(inventory)
        cached = getattr(self.window, "_overview_storage_cache", None)
        if not force and cached and cached[0] == key:
            self.snapshot = cached[1]
            self.message = self.snapshot_message()
            self.render()
            return
        self.storage_busy = True
        self.cancel.clear()
        self.message = "Measuring detected game and mod folders…"
        self.render()
        owner, active, cancel = weakref.ref(self), self.active, self.cancel
        def run(progress):
            try:
                snapshot = measure_storage(inventory, canceled=lambda: cancel.is_set() or not active.is_set(),
                    progress=lambda checked, message: progress(checked, message))
                return snapshot, ""
            except InterruptedError:
                return None, "Measurement canceled. Previous reading retained."
            except Exception as exc:
                return None, "Measurement unavailable: " + (str(exc)[:250] or type(exc).__name__)
        def finish(packet):
            control = owner()
            if control is None or not isValid(control) or not control.valid():
                return
            control.storage_busy = False
            result, error = packet
            if control.window.inventory is not inventory:
                return
            if result is not None and not cancel.is_set():
                control.snapshot = result
                control.window._overview_storage_cache = (key, result)
                control.message = control.snapshot_message()
            else:
                control.message = error or "Measurement canceled. Previous reading retained."
            control.render()
        def progress(_checked, message):
            control = owner()
            if control is not None and isValid(control) and control.valid():
                control.message = message
                control.window.overview_storage_note.setText(message)
                control.changed.emit()
        # Errors are data: an Overview measurement cannot reset another scan's
        # flags through the shared worker's failure handler.
        self.window.job(run, finish, progress=progress)

    def snapshot_message(self):
        s = self.snapshot
        state = "Partial measurement" if s.partial else "Measured files"
        return f"{state} · {s.files:,} unique files · {s.shared_files:,} shared links counted once."

    def render(self):
        if not self.valid():
            return
        w, s = self.window, self.snapshot
        w.overview_storage_note.setText(self.message)
        if s is None:
            title = "Measuring…" if self.storage_busy else "Unavailable" if w.inventory.scanned_at else "Not scanned"
            w.overview_ring.set_segments([(name, 0, color) for name, color in CATEGORIES], title)
            for caption, value, _ in w.overview_legend.values():
                value.setText("Measuring…" if self.storage_busy else "Not measured")
                value.setToolTip(self.message)
            if w.inventory.scanned_at:
                w.overview_metrics["Mods"].set_value("…" if self.storage_busy else "Unknown", "Mods")
                for i in range(w.overview_library.count()):
                    item = w.overview_library.item(i)
                    data = dict(item.data(CARD_ROLE))
                    data["size"] = "Measuring…" if self.storage_busy else "Unknown"
                    item.setData(CARD_ROLE, data)
        else:
            unavailable = bool(s.roots) and not any(r.valid for r in s.roots)
            title = "Unavailable" if unavailable else human_size(s.total)
            w.overview_ring.caption = "PARTIAL FILES" if s.partial else "MEASURED FILES"
            w.overview_ring.set_segments(s.segments, title)
            detail = ("Measured logical file bytes in detected locations, across all detected drives. "
                "Nested paths and hardlinks count once. Mods deployed as hardlinks are attributed to Mods. "
                "Old files already inside a game/mod count in their owning category. "
                "Captures cover accepted screenshot/recording findings. Saves and other unscanned folders are outside this chart. "
                "Compressed/sparse physical allocation and reclaimable space are not inferred.\n"
                + self.message + "\nChecked: " + s.measured_at)
            w.overview_ring.setToolTip(detail + "\nClick for folders, coverage and drive readings.")
            w.overview_ring._base_tip = w.overview_ring.toolTip()
            w.overview_storage_note.setToolTip(detail)
            for name, (caption, value, color) in w.overview_legend.items():
                amount = s.totals[name]
                percentage = "<0.1%" if s.total and 0 < amount/s.total < .001 else f"{amount/s.total:.1%}" if s.total else "0%"
                partial = s.category_partial(name)
                category_roots = [r for r in s.roots if r.category == name]
                unknown = bool(category_roots) and not any(r.valid for r in category_roots)
                value.setText("Unknown" if unknown else human_size(amount) + " · " + percentage + (" *" if partial else ""))
                tip = (f"{name}: {amount:,} measured bytes. " + ("Incomplete coverage. " if partial else "")
                       + "Percentage of measured files, not total drive capacity. Click to inspect folders.")
                caption.setToolTip(tip)
                value.setToolTip(tip)
            w.overview_metrics["Games"].set_value(str(s.game_count))
            w.overview_metrics["Mods"].set_value(str(s.mod_count) + ("+" if s.mod_count_partial else ""), s.mod_unit)
            w.overview_metrics["Mods"].setToolTip("Present individual packages from local manager metadata. + indicates incomplete catalog coverage, including missing folders. Where individual packages cannot be identified, the count is labeled Mod locations. Click to inspect Mods.")
            game_roots = {r.key: r for r in s.roots if r.category == "Games"}
            for i, game in enumerate(w._overview_games):
                root = game_roots.get(path_key(game.install_path))
                item = w.overview_library.item(i)
                data = dict(item.data(CARD_ROLE))
                data["size"] = (human_size(root.listed_bytes) + (" *" if root.problems or s.limited else "")) if root and root.valid else "Unknown"
                item.setData(CARD_ROLE, data)
                item.setToolTip(game.name + " · " + game.launcher + "\n" + game.install_path +
                    "\nMeasured installation file sizes: " + data["size"] +
                    ". Includes mod files inside this folder; the pie attributes shared mod files once to Mods. * indicates incomplete coverage.")
            for category in ("Old Files", "Other Storage"):
                roots = [r for r in s.roots if r.category == category]
                unknown = bool(roots) and not any(r.valid for r in roots)
                # Metrics describe accepted findings, including overlaps. Pie
                # shows disjoint bytes; the dialog explains the difference.
                paths = {r.key: r.listed_bytes for r in roots}
                text = "Unknown" if unknown else human_size(sum(paths.values())) + (" *" if s.category_partial(category) else "")
                w.overview_metrics[category].set_value(text)
                w.overview_metrics[category].setToolTip("Measured bytes in detected findings; overlapping categories are deduplicated in the pie. * indicates partial coverage. Click to inspect.")
            captures = {path_key(f.path) for f in (*w.inventory.screenshots, *w.inventory.recordings)}
            w.overview_metrics["Captures"].set_value(str(len(captures)))
            w.overview_metrics["Captures"].setToolTip("Accepted capture findings within the scan's age and folder settings. Click to inspect Captures.")
        self.changed.emit()

    def storage_details(self, category=""):
        if not self.valid():
            return
        dialog = QDialog(self.window)
        dialog.setWindowTitle("Game Grave · Measured Storage Breakdown")
        dialog.resize(1000, 650)
        box = column(margins=(18, 18, 18, 18))
        dialog.setLayout(box)
        box.addWidget(label("Storage Overview", "sectionTitle"))
        status = label(self.message, "subtle", wrap=True)
        status.setTextFormat(Qt.PlainText)
        box.addWidget(status)
        box.addWidget(label("Folders may overlap. “Counted once” is the pie contribution after shared paths and hardlinks are removed. "
            "Sizes are logical file bytes; unavailable locations stay unknown. Drive capacity is shown separately below.", "subtle", wrap=True))
        filters = row()
        choice = QComboBox()
        choice.addItems(["All categories"] + [c for c, _ in CATEGORIES])
        if category in dict(CATEGORIES):
            choice.setCurrentText(category)
        search = QLineEdit()
        search.setPlaceholderText("Filter folder or game…")
        filters.addWidget(choice)
        filters.addWidget(search, 1)
        box.addLayout(filters)
        table = _table(["Name", "Category", "Path", "Listed bytes", "Counted once", "Coverage"])
        table.setAccessibleName("Measured storage folders and coverage")
        box.addWidget(table, 1)
        page_line, volumes = label("", "caption"), label("", "subtle", wrap=True)
        volumes.setTextFormat(Qt.PlainText)
        box.addWidget(page_line)
        box.addWidget(volumes)
        actions = row()
        previous, following = button("Previous"), button("Next")
        refresh = button("Refresh measurement", lambda: self.refresh_storage(force=True))
        cancel = button("Cancel measurement", self.cancel.set)
        folder = button("Open folder")
        inspect = button("Inspect selected")
        for control in (previous, following, refresh, cancel, folder, inspect):
            actions.addWidget(control)
        actions.addStretch()
        actions.addWidget(button("Close", dialog.accept))
        box.addLayout(actions)
        offset, shown = [0], []
        def selected():
            i = table.currentRow()
            return shown[i] if 0 <= i < len(shown) else None
        def selection():
            root = selected()
            folder.setEnabled(bool(root and Path(root.path).exists()))
            inspect.setEnabled(bool(root))
        def populate(reset=False):
            if not isValid(dialog):
                return
            if reset:
                offset[0] = 0
            status.setText(self.message)
            s = self.snapshot
            rows = [] if s is None else [r for r in s.roots if
                (choice.currentIndex() == 0 or r.category == choice.currentText()) and
                search.text().casefold() in (r.name + " " + r.path).casefold()]
            offset[0] = min(offset[0], max(0, ((len(rows)-1)//200)*200))
            shown[:] = rows[offset[0]:offset[0]+200]
            table.setRowCount(len(shown))
            for i, root in enumerate(shown):
                values = (root.name, root.category, root.path,
                    f"{root.listed_bytes:,}" if root.valid else "Unknown",
                    f"{root.counted_bytes:,}" if root.valid else "Unknown", root.status)
                for col, text in enumerate(values):
                    _text(table, i, col, text)
                    table.item(i, col).setToolTip(root.path + "\n" + "\n".join(root.problems)
                        + (f"\nLauncher reported {root.reported_bytes:,} bytes; chart uses the measured files." if root.reported_bytes is not None else ""))
            table.setColumnWidth(0, 165)
            table.setColumnWidth(1, 100)
            table.setColumnWidth(2, 260)
            table.setColumnWidth(3, 100)
            table.setColumnWidth(4, 105)
            total = human_size(s.total) if s else "Not measured"
            page_line.setText(f"{total} counted once · {len(rows):,} locations · showing {offset[0]+1 if shown else 0}–{offset[0]+len(shown)}")
            volumes.setText("\n".join(f"Drive {v.path}: " + (v.error or
                f"{human_size(v.used)} used · {human_size(v.free)} free · {human_size(v.total)} capacity") for v in s.volumes) if s else "")
            refresh.setEnabled(not self.storage_busy and bool(self.window.inventory.scanned_at))
            cancel.setEnabled(self.storage_busy and not self.cancel.is_set())
            previous.setEnabled(offset[0] > 0)
            following.setEnabled(offset[0]+200 < len(rows))
            selection()
        def move(direction):
            offset[0] = max(0, offset[0]+direction*200)
            populate()
        def open_folder():
            root = selected()
            if root:
                path = Path(root.path)
                self.window._open_folder(str(path if path.is_dir() else path.parent))
        def inspect_selected():
            root = selected()
            if root:
                dialog.accept()
                self.inspect(root.category, root.game_key, root.path)
        previous.clicked.connect(lambda: move(-1))
        following.clicked.connect(lambda: move(1))
        folder.clicked.connect(open_folder)
        inspect.clicked.connect(inspect_selected)
        table.itemDoubleClicked.connect(lambda _: inspect_selected())
        table.itemSelectionChanged.connect(selection)
        choice.currentTextChanged.connect(lambda _: populate(True))
        search.textChanged.connect(lambda _: populate(True))
        self.changed.connect(populate)
        populate()
        dialog.exec()
        if isValid(self):
            self.changed.disconnect(populate)
        dialog.deleteLater()

    def favorite(self, index):
        if not self.valid() or not 0 <= index < len(self.window._overview_games):
            return
        w = self.window
        game = w._overview_games[index]
        favorites = set(w.settings.get("desktop_favorites", []))
        favorites.symmetric_difference_update({game.key})
        updated = dict(w.settings, desktop_favorites=sorted(favorites))
        try:
            save_settings(updated)
        except (OSError, ValueError) as exc:
            w.error("Favorite not saved", str(exc))
            return
        w.settings = updated
        item = w.overview_library.item(index)
        data = dict(item.data(CARD_ROLE))
        data["favorite"] = game.key in favorites
        item.setData(CARD_ROLE, data)
        w.overview_library.viewport().update()

    def search(self, text):
        if not self.valid():
            return
        w, query = self.window, text.strip().casefold()
        for i, game in enumerate(w._overview_games):
            w.overview_library.item(i).setHidden(query not in (game.name+" "+game.launcher+" "+game.install_path).casefold())
        for entry, date, event in w.overview_activity:
            visible = query in (entry.text()+" "+str(event)).casefold()
            entry.setVisible(visible)
            date.setVisible(visible)
        w.overview_library.doItemsLayout()
        self.sync_pager()

    def search_results(self):
        if not self.valid():
            return
        query = self.window.global_search.text().strip().casefold()
        if not query:
            return
        records = [(g.name, g.install_path, "Games", g.key) for g in self.window.inventory.games]
        mods = self.snapshot.catalog.entries if self.snapshot else self.window.inventory.mods
        records += [(m.name, m.path, "Mods", "") for m in mods]
        records += [(Path(f.path).name, f.path, category, "") for category, files in
            (("Old Files", self.window.inventory.files), ("Captures", [*self.window.inventory.screenshots, *self.window.inventory.recordings])) for f in files]
        matches = [r for r in records if query in " ".join(r[:3]).casefold()]
        dialog = QDialog(self.window)
        dialog.setWindowTitle("Game Grave · Overview Search")
        dialog.resize(740, 480)
        box = column(margins=(18, 18, 18, 18))
        dialog.setLayout(box)
        box.addWidget(label(f"{len(matches):,} matching scan findings", "sectionTitle"))
        entries = QListWidget()
        entries.setAccessibleName("Overview search results")
        box.addWidget(entries, 1)
        # Keep very large accepted inventories responsive; users can narrow the
        # query. No hidden first-500 limit on the library itself.
        for record in matches[:2000]:
            item = QListWidgetItem(f"{record[0]} · {record[2]}")
            item.setToolTip(record[1])
            item.setData(Qt.UserRole, record)
            entries.addItem(item)
        if len(matches) > 2000:
            box.addWidget(label("Showing 2,000 results. Narrow the search to inspect more.", "subtle"))
        def inspect(*_):
            item = entries.currentItem()
            if item:
                _, path, category, key = item.data(Qt.UserRole)
                dialog.accept()
                self.inspect(category, key, path)
        entries.itemActivated.connect(inspect)
        actions = row()
        open_button = button("Inspect selected", inspect)
        open_button.setEnabled(False)
        entries.currentRowChanged.connect(lambda i: open_button.setEnabled(i >= 0))
        actions.addWidget(open_button)
        actions.addStretch()
        actions.addWidget(button("Close", dialog.accept))
        box.addLayout(actions)
        dialog.exec()
        dialog.deleteLater()

    def inspect(self, category, game_key, path):
        w = self.window
        w.navigate(category)
        if category == "Games":
            w.game_search.setText(path)
            for index, game in enumerate(w._shown_games):
                if game.key == game_key:
                    w.game_grid.setCurrentRow(index)
                    break
        else:
            # Reuse the destination's existing search behavior unchanged.
            w.global_search.setText(path)

    def activity_details(self, event):
        if not self.valid():
            return
        info = friendly_activity(event)
        dialog = QDialog(self.window)
        dialog.setWindowTitle("Game Grave · Activity Details")
        dialog.resize(640, 370)
        box = column(margins=(18, 18, 18, 18))
        dialog.setLayout(box)
        for text, role in ((info["title"], "sectionTitle"), (info["date"]+" · "+info["status"], "subtle"),
                           (info["explanation"], "subtle"), (info["details"], "subtle")):
            field = label(text, role, wrap=True)
            field.setTextFormat(Qt.PlainText)
            field.setTextInteractionFlags(Qt.TextSelectableByMouse)
            box.addWidget(field)
        box.addStretch()
        actions = row()
        def history():
            dialog.accept()
            self.window.navigate("Undo Center")
        actions.addWidget(button("View History", history))
        if event.get("path") and Path(event["path"]).parent.is_dir():
            actions.addWidget(button("Open containing folder", lambda: self.window._open_folder(str(Path(event["path"]).parent))))
        actions.addStretch()
        actions.addWidget(button("Close", dialog.accept))
        box.addLayout(actions)
        dialog.exec()
        dialog.deleteLater()
