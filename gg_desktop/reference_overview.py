"""Live Overview matching the archived owner-approved dashboard composition."""
from __future__ import annotations

from datetime import datetime
from math import atan2, degrees, hypot
from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QSize, Signal, QEvent
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen, QFontMetrics
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFrame,
    QGridLayout, QLabel, QLayout, QListWidget, QPushButton, QSizePolicy, QWidget,
)
from core import get_activity, friendly_activity, human_size, save_settings
from recovery import get_records
from gg_desktop.insight_models import storage_items
from gg_desktop.overview_storage import CATEGORIES
from gg_desktop.insight_widgets import FootprintRing
from gg_desktop.artwork import game_app_id
from gg_desktop.reference_library import _table, _text, _widget
from gg_desktop.reference_widgets import (
    CARD_ROLE, CoverGrid, draw_crop, icon, pixel_font, tool,
)
from gg_desktop.widgets import button, column, label, row


class OverviewHero(QWidget):
    def __init__(self, window):
        super().__init__()
        self.setObjectName("overviewHero")
        self.setMinimumHeight(128)
        box = row(spacing=15, margins=(7, 14, 8, 8))
        self.setLayout(box)
        slash = label("╱")
        slash.setFixedWidth(24)
        slash.setStyleSheet("color:#ff2348;font-size:48px;font-weight:900;")
        box.addWidget(slash)
        text = column(spacing=3)
        heading = label("Overview")
        heading.setStyleSheet("font-size:40px;font-weight:700;background:transparent;")
        heading.setFixedHeight(50)
        text.addWidget(heading)
        subtitle = label("Your games. All their baggage. Under control.", wrap=True)
        subtitle.setStyleSheet("font-size:14px;color:#d8e1e9;background:transparent;")
        text.addWidget(subtitle)
        text.setAlignment(Qt.AlignVCenter)
        box.addLayout(text, 1)
        actions = column(spacing=5)
        self.scan = tool("Scan PC", "search", window.start_scan, kind="primary")
        self.scan.setProperty("overviewScanPC", True)
        self.scan.setAccessibleName("Scan PC from Overview")
        self.scan.setMinimumSize(140, 36)
        actions.addWidget(self.scan)
        self.locations = tool("Scan Locations", "folder", window.open_scan_locations)
        self.locations.setAccessibleName("Manage scan locations and coverage")
        actions.addWidget(self.locations)
        box.addLayout(actions)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        area = QRectF(self.rect())
        p.fillRect(area, QColor("#020609"))
        draw_crop(p, QRectF(self.width() * .24, -8, self.width() * .76, self.height() + 8),
                  "overview_hero", (0, 0, 835, 150))
        fade = QLinearGradient(0, 0, self.width(), 0)
        fade.setColorAt(0, QColor("#020609"))
        fade.setColorAt(.27, QColor(2, 6, 9, 242))
        fade.setColorAt(.58, QColor(2, 6, 9, 70))
        fade.setColorAt(1, QColor(2, 6, 9, 15))
        p.fillRect(area, fade)
        bottom = QLinearGradient(0, self.height() * .6, 0, self.height())
        bottom.setColorAt(0, QColor(2, 6, 9, 0))
        bottom.setColorAt(1, QColor("#020609"))
        p.fillRect(area, bottom)


class OverviewMetric(QPushButton):
    def __init__(self, title, value, symbol, color, action):
        super().__init__()
        self.color, self.title = color, title
        self.setObjectName("overviewMetric")
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setFixedHeight(76)
        self.setAccessibleName(title + ": " + value)
        self.clicked.connect(action)
        box = row(spacing=12, margins=(13, 7, 6, 12))
        self.setLayout(box)
        glyph = QLabel()
        glyph.setFixedSize(32, 32)
        glyph.setPixmap(icon(symbol, color, 32).pixmap(32, 32))
        box.addWidget(glyph)
        words = column(spacing=3)
        self.caption_label = label(title, "overviewMetricCaption")
        self.value_label = label(value, "overviewMetricValue")
        self._value_pixels = 25
        self.value_label.installEventFilter(self)
        words.addWidget(self.caption_label)
        words.addWidget(self.value_label)
        box.addLayout(words, 1)
        for child in self.findChildren(QWidget):
            child.setAttribute(Qt.WA_TransparentForMouseEvents)

    def sizeHint(self):
        return QSize(140, 76)

    def set_value(self, value, caption=None):
        self.value_label.setText(value)
        self.caption_label.setText(caption or self.title)
        self.setAccessibleName(self.caption_label.text() + ": " + value)
        self._fit_value()

    def eventFilter(self, target, event):
        if target is self.value_label and event.type() == QEvent.Resize:
            self._fit_value()
        return super().eventFilter(target, event)

    def _fit_value(self):
        font = self.value_label.font()
        pixels = 25
        font.setPixelSize(pixels)
        while pixels > 12 and QFontMetrics(font).horizontalAdvance(self.value_label.text()) > self.value_label.width():
            pixels -= 1
            font.setPixelSize(pixels)
        if pixels != self._value_pixels:
            self._value_pixels = pixels
            self.value_label.setStyleSheet(f"font-size:{pixels}px;")

    def minimumSizeHint(self):
        return QSize(0, 76)

    def paintEvent(self, event):
        p = QPainter(self)
        if self.underMouse():
            p.fillRect(self.rect(), QColor(40, 55, 66, 55))
        glow = QLinearGradient(0, 0, self.width(), 0)
        glow.setColorAt(0, QColor(0, 0, 0, 0))
        glow.setColorAt(.3, QColor(self.color))
        glow.setColorAt(1, QColor(0, 0, 0, 0))
        p.setOpacity(.65)
        p.fillRect(QRectF(0, self.height() - 4, self.width(), 2), glow)
        p.setOpacity(1)
        p.setPen(QColor("#303943"))
        p.drawLine(self.width() - 1, 17, self.width() - 1, self.height() - 17)
        if self.hasFocus():
            p.setPen(QPen(QColor("#58d4ef"), 1, Qt.DotLine))
            p.drawRect(self.rect().adjusted(2, 2, -3, -3))


class OverviewRing(FootprintRing):
    activated = Signal(str)

    def __init__(self, segments, *, scanned=False):
        super().__init__(caption="DETECTED STORAGE")
        self.setMinimumSize(170, 178)
        self.setMaximumWidth(190)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        total = sum(size for _, size, _ in segments)
        self.set_segments(segments, human_size(total) if total else "No size data" if scanned else "Not scanned")
        self.setToolTip("Detected storage by reported bytes; nested locations count once.\n" +
            "\n".join(f"{name}: {human_size(size)} ({size / total:.1%})" for name, size, _ in segments if total))

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            dx, dy = event.position().x()-self.width()/2, event.position().y()-self.height()/2
            scale = min(self.width(), self.height())/220
            total = sum(value for _, value, _ in self.segments)
            category = ""
            if total and 78 <= hypot(dx, dy)/max(scale, .01) <= 101:
                angle, end = degrees(atan2(dx, -dy)) % 360, 0
                for name, value, _ in self.segments:
                    end += value/total*360
                    if value and angle < end:
                        category = name
                        break
            self.activated.emit(category)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.activated.emit("")
            event.accept()
        else:
            super().keyPressEvent(event)


def section(title, symbol, trailing=None):
    frame = QFrame()
    frame.setObjectName("overviewSection")
    contents = column(spacing=8)
    frame.setLayout(contents)
    header = row(spacing=8)
    image = QLabel()
    image.setPixmap(icon(symbol, "#ff2c4c", 24).pixmap(24, 24))
    header.addWidget(image)
    title_label = label(title, "overviewSectionTitle")
    title_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    header.addWidget(title_label, 1)
    if trailing:
        header.addWidget(trailing)
    contents.addWidget(_widget(header))
    return frame, contents


class OverviewPanels(QWidget):
    def __init__(self, panels):
        super().__init__()
        self.panels = panels
        self.mode = None
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(22)
        self.grid.setSizeConstraint(QLayout.SetNoConstraint)

    def minimumSizeHint(self):
        return QSize(0, 305)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        mode = 3 if self.width() >= 890 else 2 if self.width() >= 605 else 1
        if self.mode == mode:
            return
        self.mode = mode
        for panel in self.panels:
            self.grid.removeWidget(panel)
        for i in range(3):
            self.grid.setColumnStretch(i, 0)
        if mode == 3:
            for i, panel in enumerate(self.panels):
                self.grid.addWidget(panel, 0, i)
                self.grid.setColumnStretch(i, (29, 31, 21)[i])
            self.setFixedHeight(305)
        elif mode == 2:
            self.grid.addWidget(self.panels[0], 0, 0)
            self.grid.addWidget(self.panels[1], 0, 1)
            self.grid.addWidget(self.panels[2], 1, 0, 1, 2)
            self.grid.setColumnStretch(0, 1)
            self.grid.setColumnStretch(1, 1)
            self.setFixedHeight(590)
        else:
            for i, panel in enumerate(self.panels):
                self.grid.addWidget(panel, i, 0)
            self.setFixedHeight(880)


class OverviewLibrary(CoverGrid):
    def __init__(self):
        super().__init__()
        self.setWrapping(False)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setMinimumHeight(186)
        self.setMaximumHeight(201)

    def _fit(self):
        width = max(140, self.viewport().width() - 2)
        count = max(1, width // 170)
        self.setGridSize(QSize(width // count, 185))


class OverviewScreens:
    def overview_page(self):
        page = self.page_for("Overview")
        page.content.setContentsMargins(30, 0, 24, 16)
        page.content.setSpacing(12)
        self.overview_hero = OverviewHero(self)
        page.content.addWidget(self.overview_hero)
        found = bool(self.inventory.scanned_at)
        other_bytes = sum(r.size for r in storage_items(self.inventory))
        values = [
            ("Games", str(len(self.inventory.games)), "game", "#4dd2e9", "Games"),
            ("Mods", str(len(self.inventory.mods)), "mods", "#ce8fe5", "Mods"),
            ("Old Files", human_size(sum(f.size for f in self.inventory.files)), "archive", "#f0bc78", "Old Files"),
            ("Other Storage", human_size(other_bytes), "storage", "#40d8d3", "Other Storage"),
            ("Captures", str(len(self.inventory.screenshots) + len(self.inventory.recordings)), "camera", "#cb95e4", "Captures"),
        ]
        metric_row = row(spacing=0)
        self.overview_metrics = {}
        for title, value, symbol, color, route in values:
            metric = OverviewMetric(title, value if found else "—", symbol, color, lambda _=False, route=route: self.navigate(route))
            metric.setToolTip("Detected results from the last scan. Click to inspect " + title.lower() + ".")
            metric_row.addWidget(metric, 1)
            self.overview_metrics[title] = metric
        metric_band = _widget(metric_row)
        metric_band.setFixedHeight(76)
        page.content.addWidget(metric_band)
        scanline = row(spacing=8)
        self.overview_scan_status = label("", "subtle", wrap=True)
        self.overview_scan_status.setStyleSheet("color:#bfccd9;font-size:12px;")
        scanline.addWidget(self.overview_scan_status, 1)
        scanline.addWidget(button("Scan Results & Locations", self.open_scan_locations, kind="link"))
        self.overview_cancel = tool("Cancel Scan", "close", lambda: self.page.overview.cancel_current())
        scanline.addWidget(self.overview_cancel)
        page.content.addWidget(_widget(scanline))

        activity, recent = section("Recent Activity", "clock", button("View History →", lambda: self.navigate("Undo Center"), kind="link"))
        events = get_activity(limit=4)
        self.overview_activity = []
        for event in events:
            info = friendly_activity(event)
            entry = button(info["title"], lambda _=False, event=event: self.page.overview.activity_details(event), kind="overviewActivity")
            entry.setToolTip(str(event.get("details", "")))
            entry.setIcon(icon("check" if info["status"] == "Done" else "clock", "#62d3bc", 22))
            entry.setMinimumHeight(37)
            recent.addWidget(entry)
            date_label = label(info["date"], "caption")
            recent.addWidget(date_label)
            self.overview_activity.append((entry, date_label, event))
        if not events:
            recent.addWidget(label("Your local scan and review history will appear here.", "subtle", wrap=True))
            recent.addWidget(button("Scan your library →", self.start_scan, kind="link"))
        recent.addStretch()

        storage, contents = section("Storage Overview", "storage")
        now = datetime.now().astimezone()
        amount = 0
        for record in get_records():
            if not isinstance(record, dict):
                continue
            try:
                when = datetime.fromisoformat(record.get("time", ""))
                if (when.year, when.month) == (now.year, now.month) and type(record.get("size")) is int:
                    amount += max(0, record["size"])
            except (ValueError, TypeError):
                continue
        chart = row(spacing=9)
        segments = [(name, 0, color) for name, color in CATEGORIES]
        total = sum(size for _, size, _ in segments)
        self.overview_ring = OverviewRing(segments, scanned=found)
        chart.addWidget(self.overview_ring)
        legend = column(spacing=12)
        self.overview_legend = {}
        for name, size, color in segments:
            line = row(spacing=6)
            swatch = label("●")
            swatch.setStyleSheet("color:" + color + ";font-size:14px;")
            line.addWidget(swatch)
            name_label = label(name, "caption")
            line.addWidget(name_label, 1)
            percent = "<0.1%" if total and 0 < size / total < .001 else f"{size / total:.1%}" if total else "0%"
            value_label = label((human_size(size) + " · " + percent) if found else "Not scanned", "subtle")
            value_label.setStyleSheet("color:" + color + ";font-size:11px;")
            line.addWidget(value_label)
            legend.addWidget(_widget(line))
            self.overview_legend[name] = (name_label, value_label, color)
        chart.addLayout(legend, 1)
        contents.addWidget(_widget(chart), 1)
        self.overview_storage_note = label("Measure detected game and mod folders after Scan PC.", "caption", wrap=True)
        self.overview_storage_note.setToolTip("Logged moves this month: " + human_size(amount) + ". Not confirmed free space.")
        contents.addWidget(self.overview_storage_note)
        contents.addWidget(tool("Review Cleanup", "sparkles", lambda: self.navigate("Graveyard"), kind="primary"))

        actions, quick = section("Quick Actions", "sparkles")
        self.overview_quick_scan = tool("Scan PC   ›", "search", self.start_scan, kind="overviewQuick")
        self.overview_quick_scan.setAccessibleName("Scan PC from Quick Actions")
        quick.addWidget(self.overview_quick_scan)
        for name, symbol, route in (("Find Mods", "mods", "Mods"), ("Review Old Files", "archive", "Old Files"),
            ("Manage Captures", "camera", "Captures"), ("Open Graveyard", "grave", "Graveyard")):
            control = tool(name + "   ›", symbol, lambda _=False, route=route: self.navigate(route), kind="overviewQuick")
            quick.addWidget(control)
        quick.addStretch()
        page.content.addWidget(OverviewPanels((activity, storage, actions)))

        library, shelf = section("Your Library", "game", button("View All Games →", lambda: self.navigate("Games"), kind="link"))
        self.overview_library = OverviewLibrary()
        self.overview_library.set_artwork(self.artwork)
        self.overview_library.setAccessibleName("Your detected game library")
        games = list(self.inventory.games)
        for game in games:
            from PySide6.QtWidgets import QListWidgetItem
            item = QListWidgetItem(game.name)
            item.setToolTip(game.name + " · " + game.launcher)
            item.setData(CARD_ROLE, {"name": game.name, "source": game.launcher, "steam_app_id": game_app_id(game),
                "size": "Measuring…" if found else "Not measured",
                "favorite": game.key in self.settings.get("desktop_favorites", [])})
            self.overview_library.addItem(item)
        self.overview_library.itemActivated.connect(self._overview_inspect_game)
        self.overview_library.itemClicked.connect(self._overview_inspect_game)
        self.overview_search_hint = label("", "subtle", wrap=True)
        self.overview_search_hint.setAccessibleName("Overview search help")
        self.overview_search_hint.hide()
        shelf.addWidget(self.overview_search_hint)
        shelf.addWidget(self.overview_library)
        pager = row(spacing=6)
        pager.addStretch()
        self.overview_previous = tool("Previous", "minus", lambda: self._overview_library_move(-1))
        self.overview_next = tool("Next", "chevron", lambda: self._overview_library_move(1))
        pager.addWidget(self.overview_previous)
        pager.addWidget(self.overview_next)
        shelf.addWidget(_widget(pager))
        self._overview_games = games
        if not games:
            shelf.addWidget(label("No games detected yet. Scan PC, or add a missing library in Scan Locations.", "subtle", wrap=True))
        page.content.addWidget(library)
        self.overview_library.doItemsLayout()
        from gg_desktop.overview_storage_ui import OverviewStorageController
        page.overview = OverviewStorageController(self, page)
        page.overview.bind_native()
        self._sync_scan_controls()

    def _overview_library_move(self, direction):
        bar = self.overview_library.horizontalScrollBar()
        bar.setValue(bar.value() + direction * self.overview_library.viewport().width())

    def _overview_inspect_game(self, item):
        if self.current_route != "Overview":
            return
        index = self.overview_library.row(item)
        if not 0 <= index < len(self._overview_games):
            return
        game = self._overview_games[index]
        self.navigate("Games")
        self.game_search.setText(game.install_path)
        match = next((i for i, g in enumerate(self._shown_games) if g.key == game.key), -1)
        if match >= 0:
            self.game_grid.setCurrentRow(match)

    def open_scan_locations(self):
        from gg_desktop.overview_storage_ui import OverviewDialog, coverage_reports
        dialog = OverviewDialog(self, "Scan Results & Locations", (840, 650))
        contents = column(spacing=10, margins=(16, 16, 16, 16))
        dialog.setLayout(contents)
        contents.addWidget(label("Scan Results & Locations", "sectionTitle"))
        contents.addWidget(label("Add missing libraries here. Steam and Xbox folders are verified from their local installation metadata; other custom folders stay labeled unverified.", "subtle", wrap=True))
        table = _table(["Source", "Status", "Found", "Locations / Coverage"])
        table.setMinimumHeight(180)
        reports = self.inventory.source_reports or coverage_reports(self.inventory, self.settings)
        table.setRowCount(len(reports))
        for i, result in enumerate(reports):
            for c, value in enumerate((result["source"], result["status"], str(result["count"]),
                                       "; ".join(result.get("paths", [])) or result["detail"])):
                _text(table, i, c, value)
            table.item(i, 3).setToolTip(result["detail"] + "\n" + "\n".join(result.get("paths", [])))
        table.setColumnWidth(0, 130)
        table.setColumnWidth(1, 90)
        table.setColumnWidth(2, 55)
        contents.addWidget(table, 1)
        groups = {"Steam libraries": "steam_extra_roots", "Other / Xbox libraries": "other_library_roots",
                  "Mod locations": "mod_extra_roots", "Screenshot folders": "screenshot_roots",
                  "Recording folders": "recording_roots"}
        choice = QComboBox()
        choice.addItems(list(groups))
        contents.addWidget(choice)
        roots = QListWidget()
        roots.setMinimumHeight(90)
        contents.addWidget(roots)
        pending = {key: list(self.settings.get(key, [])) for key in groups.values()}
        def refresh():
            roots.clear()
            roots.addItems(pending[groups[choice.currentText()]])
        choice.currentTextChanged.connect(refresh)
        refresh()
        def add():
            path = QFileDialog.getExistingDirectory(dialog, "Choose " + choice.currentText())
            if not path:
                return
            self._add_scan_location(groups[choice.currentText()], path, pending, refresh)
        def remove():
            if roots.currentItem():
                pending[groups[choice.currentText()]].remove(roots.currentItem().text())
                refresh()
        actions = row()
        actions.addWidget(tool("Add Folder…", "folder", add))
        actions.addWidget(tool("Remove Selected", "minus", remove))
        actions.addStretch()
        contents.addWidget(_widget(actions))
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        busy = self.scanning or self.cleaning
        buttons.button(QDialogButtonBox.Save).setEnabled(not busy)
        for control in actions.parentWidget().findChildren(QPushButton) if actions.parentWidget() else []:
            control.setEnabled(not busy)
        contents.addWidget(buttons)
        if dialog.exec() == QDialog.Accepted:
            updated = dict(self.settings, **pending)
            try:
                save_settings(updated)
            except (OSError, ValueError) as exc:
                self.error("Scan locations not saved", str(exc))
                return
            self.settings = updated
            self.start_scan()

    def _add_scan_location(self, key, raw, pending, refresh):
        from core import _has_reparse_component, safe_scan_root
        path = Path(raw).expanduser()
        if key == "steam_extra_roots" and path.name.casefold() == "steamapps":
            path = path.parent
        allowed = (path.is_dir() and path.is_absolute() and path != Path(path.anchor)
                   and not _has_reparse_component(path))
        if key == "steam_extra_roots":
            allowed = allowed and (path / "steamapps").is_dir()
        else:
            allowed = allowed and safe_scan_root(path)
        if not allowed:
            self.error("Folder not allowed", "Choose a normal local library folder. A Steam folder must contain steamapps.")
            return
        if str(path) not in pending[key]:
            pending[key].append(str(path))
        refresh()
