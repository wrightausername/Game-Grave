"""Batch Rename window (Toolbox > Files). Drag files in, type a name, Rename All.

All rules live in `rename_core` (tested without Qt). This module is the window: a list that takes dropped files and
folders and can be reordered by dragging, a live preview of every new name with thumbnails, the name / start / digits
boxes, advanced options folded away, Undo, and the result banner. Built on `tools_shell.ToolDialog` like every other
Toolbox window. Only file names change; contents are never opened for writing, and nothing is ever overwritten.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from PySide6.QtCore import QObject, QRect, QRunnable, QSize, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QImage, QImageReader, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFileIconProvider, QFrame, QGridLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QProgressBar, QPushButton, QSpinBox, QStyle, QStyledItemDelegate,
)
from PySide6.QtCore import QFileInfo
from shiboken6 import isValid

from gg_desktop import rename_core as rc
from gg_desktop import tools_shell as shell, tools_words as words
from gg_desktop.widgets import button, column, row

TITLE = "Batch Rename"
ROW_H = 56
THUMB = 40
TEXT, DIM, FAINT, BAD, ACCENT = "#e8eef5", "#8fa0b3", "#5f6f80", "#ff6b7e", "#ff284a"
LOCAL_STYLE = (
    "QSpinBox{background:#0a1118;color:#e8eef5;border:1px solid #243242;border-radius:8px;padding:6px 8px;"
    "font-size:13px;min-height:22px;}"
    "QSpinBox::up-button,QSpinBox::down-button{width:16px;border:none;background:transparent;}"
    "QLineEdit#renameName{font-size:15px;font-weight:600;padding:8px 10px;}"
    "QLineEdit:focus,QSpinBox:focus,QComboBox:focus{border-color:#ff284a;}"
    "QLabel#renameLabel{color:#8fa0b3;font-size:12px;font-weight:700;letter-spacing:1px;}"
    "QListWidget#renameList{background:#070d13;border:1px solid #1b2836;border-radius:12px;padding:2px;}"
    "QListWidget#renameList::item{padding:0;margin:0;border-radius:0;}"
    "QListWidget#renameList::item:selected,QListWidget#renameList::item:hover{background:transparent;}"
    "QFrame#renameAdvanced{background:#09121a;border:1px solid #1b2836;border-radius:12px;}"
)


def store_dir() -> Path:
    from core import config_dir
    return Path(config_dir()) / "Batch Rename"


def load_prefs():
    try:
        data = json.loads((store_dir() / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    return rc.Options.from_dict(data.get("options")), bool(data.get("advanced_open")), bool(data.get("rename_folders"))


def save_prefs(options, advanced_open, rename_folders):
    try:
        folder = store_dir()
        folder.mkdir(parents=True, exist_ok=True)
        rc._write_json(folder / "settings.json", {"options": options.to_dict(), "advanced_open": bool(advanced_open),
                                                  "rename_folders": bool(rename_folders)})
    except OSError:
        pass   # preferences are a convenience; the rename itself never depends on them


def plural(n, one, many=None):
    return f"{n:,} {one if n == 1 else (many or one + 's')}"


# ------------------------------------------------------------------ thumbnails
class _ThumbSignals(QObject):
    ready = Signal(str, QImage)


class _ThumbJob(QRunnable):
    def __init__(self, path, size, signals):
        super().__init__()
        self.path, self.size, self.signals = path, size, signals
        self.setAutoDelete(True)

    def run(self):
        image = QImage()
        try:
            reader = QImageReader(self.path)
            reader.setAutoTransform(True)
            source = reader.size()
            if source.isValid() and source.width() > 0 and source.height() > 0:
                reader.setScaledSize(source.scaled(self.size, self.size, Qt.KeepAspectRatio))
            image = reader.read()
        except Exception:  # an unreadable picture just keeps its file icon
            image = QImage()
        try:
            self.signals.ready.emit(self.path, image)
        except RuntimeError:
            pass   # the window closed while this was loading


class Thumbs(QObject):
    """Pictures load on two background threads, only for rows on screen; everything else gets its Windows file icon."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.IMAGE = {bytes(f).decode().lower() for f in QImageReader.supportedImageFormats()}
        self.cache, self.pending = {}, set()
        self.icons = QFileIconProvider()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self.signals = _ThumbSignals()
        self.signals.ready.connect(self._ready)

    def get(self, path, is_dir, size):
        if path in self.cache:
            return self.cache[path]
        ext = Path(path).suffix.lower().lstrip(".")
        if not is_dir and ext in self.IMAGE:
            if path not in self.pending:
                self.pending.add(path)
                self.pool.start(_ThumbJob(path, size, self.signals))
        else:
            self.cache[path] = self.icons.icon(QFileInfo(path))      # a QIcon: painted at the tile's size
            return self.cache[path]
        return self.icons.icon(QFileIconProvider.Folder if is_dir else QFileIconProvider.File)

    def _ready(self, path, image):
        self.pending.discard(path)
        if image.isNull():
            self.cache[path] = self.icons.icon(QFileInfo(path))
        else:
            self.cache[path] = QPixmap.fromImage(image)
        self.changed.emit()

    def move(self, old, new):
        if old in self.cache:
            self.cache[new] = self.cache.pop(old)

    def forget(self, path):
        self.cache.pop(path, None)


# ------------------------------------------------------------------ the list
class RowPainter(QStyledItemDelegate):
    """One row: number, thumbnail, old name over its folder and date, arrow, new name over its status."""

    def __init__(self, dialog):
        super().__init__(dialog)
        self.dialog = dialog

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), ROW_H)

    def paint(self, p, option, index):
        d = self.dialog
        path = index.data(Qt.UserRole)
        info = d.rows.get(path)
        if info is None:
            return
        entry, planned, number = info
        r = option.rect
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        selected = bool(option.state & QStyle.State_Selected)
        hover = bool(option.state & QStyle.State_MouseOver)
        if selected:
            p.fillRect(r, QColor("#2a0f17"))
            p.fillRect(QRect(r.left(), r.top(), 3, r.height()), QColor(ACCENT))
        elif hover:
            p.fillRect(r, QColor("#0f1a24"))
        p.setPen(QColor("#111c26"))
        p.drawLine(r.left() + 14, r.bottom(), r.right() - 14, r.bottom())

        small, normal, bold = QFont(d.font()), QFont(d.font()), QFont(d.font())
        small.setPixelSize(12)
        normal.setPixelSize(13)
        bold.setPixelSize(13)
        bold.setWeight(QFont.DemiBold)

        p.setFont(small)
        p.setPen(QColor(FAINT))
        p.drawText(QRect(r.left() + 4, r.top(), 34, r.height()), Qt.AlignRight | Qt.AlignVCenter, str(number))

        tile = QRect(r.left() + 48, r.top() + (r.height() - THUMB) // 2, THUMB, THUMB)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#111b25"))
        p.drawRoundedRect(tile, 6, 6)
        pix = d.thumbs.get(entry.path, entry.is_dir, THUMB * 2)
        if isinstance(pix, QIcon):
            pix.paint(p, tile.adjusted(6, 6, -6, -6))
        elif pix is not None and not pix.isNull():
            scaled = pix.scaled(THUMB, THUMB, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            p.drawPixmap(tile.left() + (THUMB - scaled.width()) // 2, tile.top() + (THUMB - scaled.height()) // 2, scaled)

        left = tile.right() + 14
        right = r.right() - 14
        span = max(60, right - left - 34)
        col = span // 2
        arrow_x = left + col
        new_x = arrow_x + 34
        top = r.top() + 9

        def line(x, y, width, text, font, color):
            p.setFont(font)
            p.setPen(QColor(color))
            elided = QFontMetrics(font).elidedText(text, Qt.ElideMiddle, max(10, width))
            p.drawText(QRect(x, y, width, 20), Qt.AlignLeft | Qt.AlignVCenter, elided)

        line(left, top, col - 10, Path(entry.path).name, normal, DIM)
        line(left, top + 19, col - 10, d.sub(entry), small, FAINT)

        pen = QPen(QColor(FAINT))
        pen.setWidthF(1.4)
        p.setPen(pen)
        ay = r.top() + r.height() // 2
        p.drawLine(arrow_x + 8, ay, arrow_x + 22, ay)
        p.drawLine(arrow_x + 22, ay, arrow_x + 17, ay - 4)
        p.drawLine(arrow_x + 22, ay, arrow_x + 17, ay + 4)

        if planned is None:
            new_color, note, note_color = DIM, "", FAINT
        elif planned.blocking:
            new_color, note, note_color = BAD, planned.message, BAD
        elif planned.status == rc.UNCHANGED:
            new_color, note, note_color = DIM, "No change", FAINT
        else:
            new_color, note, note_color = TEXT, ("Folder" if entry.is_dir else ""), FAINT
        line(new_x, top, right - new_x, planned.name if planned else "", bold, new_color)
        line(new_x, top + 19, right - new_x, note, small, note_color)
        p.restore()


class RenameList(QListWidget):
    """Takes files and folders dropped from Explorer, and rows dragged within it to change the order."""

    dropped = Signal(list)
    reordered = Signal()
    remove_pressed = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("renameList")
        self.setAccessibleName("Files to rename")
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDropIndicatorShown(True)
        self.setMouseTracking(True)
        self.setUniformItemSizes(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setMinimumHeight(260)

    def _external(self, event):
        return event.mimeData().hasUrls() and event.source() is not self

    def dragEnterEvent(self, event):
        if self._external(event):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self._external(event):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if self._external(event):
            paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
            event.acceptProposedAction()
            self.dropped.emit(paths)
            return
        super().dropEvent(event)
        self.reordered.emit()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.remove_pressed.emit()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.count():
            return
        p = QPainter(self.viewport())
        p.setRenderHint(QPainter.Antialiasing)
        r = self.viewport().rect().adjusted(14, 14, -14, -14)
        pen = QPen(QColor("#2a3a4c"))
        pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.drawRoundedRect(r, 10, 10)
        big = QFont(self.font())
        big.setPixelSize(18)
        big.setWeight(QFont.DemiBold)
        p.setFont(big)
        p.setPen(QColor("#ffffff"))
        mid = r.center().y()
        p.drawText(QRect(r.left(), mid - 30, r.width(), 28), Qt.AlignCenter, "Drop files or folders here")
        small = QFont(self.font())
        small.setPixelSize(13)
        p.setFont(small)
        p.setPen(QColor(DIM))
        p.drawText(QRect(r.left(), mid + 2, r.width(), 22), Qt.AlignCenter,
                   "Then type a name and press Rename All. Or use Add files.")


# ------------------------------------------------------------------ the window
class RenameDialog(shell.ToolDialog):
    def __init__(self, window, paths=None):
        super().__init__(window, "batch_rename", TITLE, "file", width=900)
        self.window_ = window
        self.setStyleSheet(self.styleSheet() + LOCAL_STYLE)
        self.setMinimumHeight(760)
        self.setAcceptDrops(True)
        self.close_button.setAutoDefault(False)
        self.options, advanced_open, self.rename_folders = load_prefs()
        self.store = rc.Store(store_dir())
        self.items: list[rc.Item] = []
        self.plans: list[rc.Planned] = []
        self.rows = {}
        self.manual_order = False
        self.busy = False
        self.dir_cache = {}
        self.thumbs = Thumbs(self)
        self.thumbs.changed.connect(lambda: self.listing.viewport().update())

        # Add / sort / remove
        tools = row(spacing=8)
        self.add_files = button("Add files…", self.pick_files)
        self.add_folder = button("Add folder…", self.pick_folder)
        self.sort_button = button("Sort by date", self.sort_by_date, tip="Oldest first, the way files are sorted when added.")
        self.remove_button = button("Remove from list", self.remove_selected, tip="Takes the selected rows off the list. "
                                    "The files are not touched.")
        self.clear_button = button("Clear list", self.clear_list)
        self.count_pill = shell.pill("No files yet", words.IDLE)
        for control in (self.add_files, self.add_folder):
            tools.addWidget(control)
        tools.addWidget(self.count_pill)
        tools.addStretch(1)
        for control in (self.sort_button, self.remove_button, self.clear_button):
            tools.addWidget(control)
        self.body.addLayout(tools)

        self.listing = RenameList()
        self.listing.setItemDelegate(RowPainter(self))
        self.listing.dropped.connect(self.add_paths)
        self.listing.reordered.connect(self.reordered)
        self.listing.remove_pressed.connect(self.remove_selected)
        self.listing.itemSelectionChanged.connect(self.sync_buttons)
        self.body.addWidget(self.listing, 1)

        # Name, start, digits
        names = QGridLayout()
        names.setHorizontalSpacing(10)
        names.setVerticalSpacing(4)
        self.name = QLineEdit(self.options.base_name)
        self.name.setObjectName("renameName")
        self.name.setPlaceholderText("Type a name, for example WW")
        self.name.setAccessibleName("New name")
        self.name.setMaxLength(200)
        self.start = QSpinBox()
        self.start.setRange(0, 9_999_999)
        self.start.setValue(self.options.start)
        self.start.setAccessibleName("Start number")
        self.digits = QSpinBox()
        self.digits.setRange(1, 9)
        self.digits.setValue(self.options.padding)
        self.digits.setAccessibleName("Digits")
        self.digits.setToolTip("Minimum digits. More are added when the batch needs them, so files still sort in order.")
        for col, (text, widget, stretch) in enumerate((("NEW NAME", self.name, 1), ("START", self.start, 0),
                                                       ("DIGITS", self.digits, 0))):
            label = QLabel(text)
            label.setObjectName("renameLabel")
            names.addWidget(label, 0, col)
            names.addWidget(widget, 1, col)
            names.setColumnStretch(col, stretch)
        self.start.setFixedWidth(110)
        self.digits.setFixedWidth(80)
        self.hint = shell.text("", "toolNote", wrap=False)
        self.hint.setMinimumHeight(18)
        names.addWidget(self.hint, 2, 0, 1, 3)
        self.body.addLayout(names)

        # Advanced options, folded
        self.adv_toggle = QPushButton()
        self.adv_toggle.setObjectName("toolDetails")
        self.adv_toggle.setCursor(Qt.PointingHandCursor)
        self.adv_toggle.setAccessibleName("Advanced options")
        self.adv_toggle.setMinimumHeight(26)
        self.adv_toggle.clicked.connect(lambda: self.open_advanced(not self.advanced.isVisible()))
        self.body.addWidget(self.adv_toggle, 0, Qt.AlignLeft)
        self.advanced = QFrame()
        self.advanced.setObjectName("renameAdvanced")
        grid = QGridLayout(self.advanced)
        grid.setContentsMargins(14, 12, 14, 12)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)
        self.find = self._field("Text to find", self.options.find)
        self.replace = self._field("Replace with", self.options.replace)
        self.prefix = self._field("Added to the front", self.options.prefix)
        self.suffix = self._field("Added before the extension", self.options.suffix)
        self.remove = self._field("For example #()", self.options.remove)
        self.separator = self._field("none", self.options.separator)
        self.separator.setMaxLength(5)
        self.case = QComboBox()
        self.case.addItems(["Keep as typed", "lowercase", "UPPERCASE", "Title Case"])
        self.case.setCurrentIndex(rc.CASES.index(self.options.case))
        self.case.setAccessibleName("Capitalization")
        self.date = QComboBox()
        self.date.addItems(["No date", "Today's date", "Date the file was created"])
        self.date.setCurrentIndex(rc.DATES.index(self.options.date))
        self.date.setAccessibleName("Add date")
        self.folders = QCheckBox("Rename dropped folders themselves")
        self.folders.setChecked(self.rename_folders)
        self.folders.setToolTip("Off: a dropped folder adds the files inside it. On: the folder itself is renamed.")
        cells = (("FIND", self.find), ("REPLACE WITH", self.replace), ("PREFIX", self.prefix), ("SUFFIX", self.suffix),
                 ("REMOVE CHARACTERS", self.remove), ("SEPARATOR", self.separator), ("CAPITALIZATION", self.case),
                 ("ADD DATE", self.date))
        for n, (text, widget) in enumerate(cells):
            r, c = divmod(n, 4)
            label = QLabel(text)
            label.setObjectName("renameLabel")
            grid.addWidget(label, r * 2, c)
            grid.addWidget(widget, r * 2 + 1, c)
            widget.setAccessibleName(text.title())
        grid.addWidget(self.folders, 4, 0, 1, 4)
        self.body.addWidget(self.advanced)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        self.body.addWidget(self.progress)

        self.details.set_lines(["Only file names change. Contents are never opened for writing.",
                                "Nothing is overwritten: a taken name blocks Rename All, and Windows itself refuses to "
                                "replace a file during the move.",
                                "Each batch renames to temporary names first, then to the final names, with a journal; "
                                "a failure or power cut puts every file back.",
                                "Undo history (last 50 batches) and preferences: " + str(store_dir())])

        self.undo_button = button("Undo last rename", self.undo, tip="Puts the names from the last Batch Rename back, "
                                  "even after Game Grave was closed.")
        self.rename_button = button("Rename All", self.do_rename, kind="primary")
        self.rename_button.setDefault(True)
        self.add_actions(self.undo_button, self.rename_button)

        for edit in (self.name, self.find, self.replace, self.prefix, self.suffix, self.remove, self.separator):
            edit.textChanged.connect(self.refresh)
        for spin in (self.start, self.digits):
            spin.valueChanged.connect(self.refresh)
        for combo in (self.case, self.date):
            combo.currentIndexChanged.connect(self.refresh)
        self.folders.toggled.connect(self._folders_changed)
        self.open_advanced(advanced_open)
        if self.store.recovered:
            if self.store.recover_problem:
                self.result("A rename was interrupted last time and some files could not be put back: "
                            + self.store.recover_problem, words.BAD)
            else:
                self.result("A rename was interrupted last time. Every file was put back to its old name.", words.INFO)
        if paths:
            self.add_paths(paths)
        self.refresh()
        self.name.setFocus()

    def _field(self, hint, value):
        edit = QLineEdit(value)
        edit.setPlaceholderText(hint)
        edit.setMaxLength(200)
        return edit

    # -- dropping onto the window anywhere, not only the list
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            event.acceptProposedAction()
            self.add_paths(paths)

    # -- options
    def read_options(self):
        o = rc.Options(base_name=self.name.text(), start=self.start.value(), padding=self.digits.value(),
                       separator=self.separator.text(), find=self.find.text(), replace=self.replace.text(),
                       prefix=self.prefix.text(), suffix=self.suffix.text(), remove=self.remove.text(),
                       case=rc.CASES[max(0, self.case.currentIndex())], date=rc.DATES[max(0, self.date.currentIndex())])
        self.options = o
        return o

    def open_advanced(self, opened):
        self.advanced.setVisible(opened)
        self.adv_toggle.setText("▾  Hide advanced options" if opened else
                                "▸  Advanced options: find and replace, prefix, suffix, capitalization, date")

    def _folders_changed(self, on):
        self.rename_folders = bool(on)
        self.result("Dropped folders will be renamed themselves." if on else
                    "Dropped folders add the files inside them.", words.INFO)
        self.save()

    def save(self):
        save_prefs(self.read_options(), self.advanced.isVisible(), self.rename_folders)

    # -- the list
    def exists(self, path):
        folder = os.path.dirname(path)
        names = self.dir_cache.get(folder)
        if names is None:
            try:
                names = {n.casefold() for n in os.listdir(folder)}
            except OSError:
                names = set()
            self.dir_cache[folder] = names
        return os.path.basename(path).casefold() in names

    def sub(self, item):
        from datetime import datetime
        folder = Path(item.path).parent.name or str(Path(item.path).parent)
        when = datetime.fromtimestamp(item.created).strftime("%b %d, %Y  %I:%M %p") if item.created else "date unknown"
        return f"{folder}  ·  {when}"

    def add_paths(self, paths):
        if self.busy or not paths:
            return
        have = {rc.key(i.path) for i in self.items}
        fresh = []
        for item in rc.scan_paths(paths, self.rename_folders):
            k = rc.key(item.path)
            if k not in have:
                have.add(k)
                fresh.append(item)
        if not fresh:
            self.result("No new files to add. Files already in the list are not added twice.", words.WARN)
            return
        fresh = rc.sort_by_created(fresh)
        self.items.extend(fresh)
        if not self.manual_order:
            self.items = rc.sort_by_created(self.items)
        self.dir_cache.clear()
        self.rebuild()
        self.result("Added " + plural(len(fresh), "file") + ". Sorted by date created, oldest first. Drag rows to change "
                    "the order.", words.INFO)
        self.name.setFocus()

    def pick_files(self):
        chosen, _ = QFileDialog.getOpenFileNames(self, "Add files to rename", str(Path.home()))
        self.add_paths(chosen)

    def pick_folder(self):
        chosen = QFileDialog.getExistingDirectory(self, "Add a folder", str(Path.home()))
        if chosen:
            self.add_paths([chosen])

    def sort_by_date(self):
        if self.busy:
            return
        self.items = rc.sort_by_created(self.items)
        self.manual_order = False
        self.rebuild()

    def remove_selected(self):
        if self.busy:
            return
        chosen = {it.data(Qt.UserRole) for it in self.listing.selectedItems()}
        if not chosen:
            return
        self.items = [i for i in self.items if i.path not in chosen]
        for path in chosen:
            self.thumbs.forget(path)
        self.rebuild()

    def clear_list(self):
        if self.busy:
            return
        self.items = []
        self.manual_order = False
        self.thumbs.cache.clear()
        self.rebuild()
        self.result("", words.IDLE)

    def reordered(self):
        order = [self.listing.item(n).data(Qt.UserRole) for n in range(self.listing.count())]
        by_path = {i.path: i for i in self.items}
        new = [by_path[p] for p in order if p in by_path]
        if [i.path for i in new] != [i.path for i in self.items]:
            self.items = new
            self.manual_order = True
            self.refresh()

    def rebuild(self):
        selected = {it.data(Qt.UserRole) for it in self.listing.selectedItems()}
        self.listing.clear()
        for item in self.items:
            row_item = QListWidgetItem()
            row_item.setData(Qt.UserRole, item.path)
            row_item.setSizeHint(QSize(100, ROW_H))
            row_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled)
            row_item.setToolTip(item.path)
            self.listing.addItem(row_item)
            row_item.setSelected(item.path in selected)
        self.refresh()

    # -- preview
    def refresh(self, *_):
        o = self.read_options()
        self.plans = rc.plan(self.items, o, exists=self.exists)
        self.rows = {i.path: (i, p, n + 1) for n, (i, p) in enumerate(zip(self.items, self.plans))}
        self.listing.viewport().update()
        count = len(self.items)
        changes = len(rc.ops_of(self.plans))
        problems = rc.problems(self.plans)
        if count:
            shell.set_pill(self.count_pill, plural(count, "file"), words.INFO)
        else:
            shell.set_pill(self.count_pill, "No files yet", words.IDLE)
        if not count:
            self.hint.setText("")
        elif not o.base_name.strip() and not changes:
            self.hint.setText("Type a name to number every file.")
        elif changes:
            first = next((p.name for p in self.plans if p.status == rc.OK), "")
            self.hint.setText(f"{first}  …  {plural(changes, 'file')} will be renamed")
        else:
            self.hint.setText("Every name is already the same.")
        self.rename_button.setText("Rename All" if not changes else f"Rename All ({changes:,})")
        self.step(0 if not count else 1 if not changes else 2)
        if problems and not self.busy:
            first = next(p for p in self.plans if p.blocking)
            self.result(f"{plural(problems, 'name')} need{'s' if problems == 1 else ''} attention before renaming. "
                        f"First: {Path(first.src).name}: {first.message}.", words.WARN)
        elif self.result_line.tone == words.WARN and "need" in self.result_line.text():
            self.result("", words.IDLE)
        self.sync_buttons()

    def sync_buttons(self):
        busy = self.busy
        changes = len(rc.ops_of(self.plans)) if self.plans else 0
        self.rename_button.setEnabled(not busy and changes > 0 and rc.problems(self.plans) == 0)
        self.undo_button.setEnabled(not busy and self.store.can_undo())
        has = bool(self.items)
        self.remove_button.setEnabled(not busy and bool(self.listing.selectedItems()))
        for control in (self.sort_button, self.clear_button):
            control.setEnabled(not busy and has)
        for control in (self.add_files, self.add_folder, self.listing):
            control.setEnabled(not busy)

    def first_problem(self):
        for n, p in enumerate(self.plans):
            if p.blocking:
                self.listing.setCurrentRow(n)
                self.listing.scrollToItem(self.listing.item(n))
                return

    # -- rename and undo
    def do_rename(self):
        if self.busy:
            return
        if not self.items:
            self.result("Drop some files in first, or use Add files.", words.WARN)
            return
        self.dir_cache.clear()
        self.refresh()
        if rc.problems(self.plans):
            self.first_problem()
            return
        ops = rc.ops_of(self.plans)
        if not ops:
            self.result("Nothing to rename: the names are already the same.", words.INFO)
            return
        self.save()
        self._start(lambda progress: self.store.apply(ops, progress).ops, undo=False)

    def undo(self):
        if self.busy:
            return
        try:
            ready, bad = self.store.undo_plan()
        except rc.NothingToUndo:
            self.result("Nothing to undo.", words.INFO)
            self.sync_buttons()
            return
        skip = False
        if bad:
            message = (f"{plural(bad, 'file')} from the last rename can't be put back: moved, renamed or deleted since, "
                       f"or the old name is taken now.\n\nPut back the other {len(ready):,}?" if ready else
                       f"None of the files from the last rename can be put back (moved, renamed or deleted since).\n\n"
                       "Remove it from the undo history?")
            if not self.window_.confirm("Undo last rename", message):
                return
            skip = True
        self._start(lambda progress: self.store.undo_last(skip, progress), undo=True)

    def _start(self, work, undo):
        self.busy = True
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.show()
        self.result("Putting the old names back…" if undo else "Renaming…", words.WORKING)
        self.sync_buttons()

        def run(emit):
            try:
                return "ok", work(lambda done, total: emit(int(done * 100 / max(1, total)), ""))
            except (rc.RenameError, rc.NothingToUndo, ValueError, OSError) as exc:
                return "error", str(exc) or type(exc).__name__

        def moved(percent, _text):
            if isValid(self):
                self.progress.setValue(percent)

        self.window_.job(run, lambda packet: self._finished(packet, undo), error_title=TITLE, progress=moved)

    def _finished(self, packet, undo):
        if not isValid(self):
            return
        self.busy = False
        self.progress.hide()
        kind, value = packet
        self.dir_cache.clear()
        if kind == "error":
            self.refresh()
            self.result(("Undo stopped. " if undo else "Rename stopped. ") + value, words.BAD)
            return
        moved = {rc.key(op.src): op.dst for op in value}
        self.items = [rc.Item(moved.get(rc.key(i.path), i.path), i.is_dir, i.created) for i in self.items]
        for old, new in ((op.src, op.dst) for op in value):
            self.thumbs.move(old, new)
        self.rebuild()
        n = len(value)
        folder = str(Path(value[0].dst).parent) if value else ""
        from core import log_event
        if undo:
            log_event("Batch Rename undo", f"Put back the old names of {plural(n, 'file')} with Batch Rename.",
                      path=folder, result="Names restored")
            self.result(f"Undo finished: {plural(n, 'name')} put back.", words.GOOD)
            self.step(0 if not self.items else 1)
        else:
            log_event("Batch Rename", f"Renamed {plural(n, 'file')} with Batch Rename (first: {Path(value[0].src).name} "
                      f"to {Path(value[0].dst).name}).", path=folder, result="Renamed")
            self.result(f"Renamed {plural(n, 'file')}. Undo last rename puts the old names back.", words.GOOD)
            self.step(3)
        self.sync_buttons()

    def done(self, code):
        if self.busy:
            self.result("Please wait until renaming finishes.", words.WARN)
            return
        self.save()
        super().done(code)

    def reject(self):
        self.done(0)


def open_batch_rename(window, paths=None):
    dialog = RenameDialog(window, paths)
    window._tools_dialog = dialog
    dialog.exec()
    return dialog
