"""Hardware > Registry Cleanup: Scan, review grouped results with ticks, then back up and fix with one confirmation.
A System Restore point is ticked by default, every key is exported first, and Undo puts the last fix back."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QCheckBox, QHeaderView, QTreeWidget, QTreeWidgetItem, QWidget

from core import log_event
from gg_desktop import registry_core as rc
from gg_desktop.tools_shell import Banner, Steps
from gg_desktop.widgets import button, column, label, panel, row

STEPS = ("Scan", "Review what's ticked", "Back up and fix")


class RegistryTab(QWidget):
    def __init__(self, window, backend=None):
        super().__init__()
        self.window_owner = window
        if backend is None:
            from gg_desktop import registry_win as backend
        self.backend = backend
        self.findings, self.busy = [], False
        outer = column(spacing=10)
        self.setLayout(outer)
        frame, lay = panel(kind="libraryPanel", padding=14, spacing=10)
        outer.addWidget(frame, 1)
        head = row(spacing=8)
        head.addWidget(label("Registry Cleanup", "sectionTitle"), 1)
        lay.addLayout(head)
        lay.addWidget(label("Finds registry entries that point to programs and files no longer on this PC, like the "
                            "registry cleaner in CCleaner, and removes them carefully.", "caption", wrap=True))
        note = label(rc.HONEST_NOTE, "caption", wrap=True)
        note.setStyleSheet("color:#8fa3b8;")
        lay.addWidget(note)
        self.steps = Steps(STEPS, "#38bdf8")
        lay.addWidget(self.steps)
        bar = row(spacing=8)
        self.scan_button = button("Scan the registry", self.scan, kind="primary",
                                  tip="Reads the registry and checks each path it names. Changes nothing.")
        self.restore_box = QCheckBox("Make a System Restore point first")
        self.restore_box.setChecked(True)
        self.restore_box.setToolTip("Windows makes at most one restore point every 24 hours; if one was made recently, "
                                    "Windows keeps that one instead. The registry backup is made either way.")
        self.fix_button = button("Fix 0 entries", self.fix, kind="primary")
        self.fix_button.setEnabled(False)
        self.undo_button = button("Undo last fix", self.undo, tip="Puts back everything the last fix removed, from "
                                                                   "its backup.")
        self.folder_button = button("Open backups", self.open_backups, kind="actionLink")
        bar.addWidget(self.scan_button)
        bar.addWidget(self.restore_box)
        bar.addStretch(1)
        bar.addWidget(self.folder_button)
        bar.addWidget(self.undo_button)
        bar.addWidget(self.fix_button)
        lay.addLayout(bar)
        self.banner = Banner("Registry Cleanup result")
        self.banner.setText("Press Scan to look for leftovers. Nothing changes until you press Fix and say yes.", "info")
        lay.addWidget(self.banner)
        self.tree = QTreeWidget()
        self.tree.setAccessibleName("Registry entries found")
        self.tree.setHeaderLabels(["Entry", "Points to (gone)", "Where in the registry"])
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Interactive)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Interactive)
        self.tree.header().setStretchLastSection(True)
        self.tree.setColumnWidth(0, 260)
        self.tree.setColumnWidth(1, 300)
        self.tree.setStyleSheet(
            "QTreeWidget{background:#0b1118;color:#e8eef5;border:1px solid #1b2633;border-radius:8px;font-size:13px;}"
            "QTreeWidget::item{padding:4px 2px;}"
            "QTreeWidget::item:selected{background:#16324a;color:#ffffff;}"
            "QTreeWidget::indicator{width:14px;height:14px;border:1px solid #4a5a6d;border-radius:3px;background:#0b1118;}"
            "QTreeWidget::indicator:checked{background:#e8264a;border-color:#ff5a73;}"
            "QTreeWidget::indicator:indeterminate{background:#6b2232;border-color:#e8264a;}"
            "QHeaderView::section{background:#0f1720;color:#9fb0c3;border:none;border-bottom:1px solid #1b2633;"
            "padding:6px;font-weight:600;}")
        self.tree.itemChanged.connect(lambda *_: self.count())
        lay.addWidget(self.tree, 1)
        self.refresh_undo()

    # ------------------------------------------------------------ scan
    def scan(self):
        if self.busy:
            return
        self.busy = True
        self.scan_button.setEnabled(False)
        self.fix_button.setEnabled(False)
        self.banner.setText("Scanning the registry… this reads only.", "working")
        self.steps.set(0)

        def work(_progress):
            return self.backend.scan()

        def done(found):
            self.busy = False
            self.scan_button.setEnabled(True)
            self.show_findings(found)

        def failed(*_):
            self.busy = False
            self.scan_button.setEnabled(True)
        try:
            self.window_owner.job(work, done, error_title="Registry scan not finished")
        except Exception as problem:
            failed()
            self.banner.setText("The scan couldn't run: " + str(problem)[:200], "bad")

    def show_findings(self, found):
        self.findings = list(found)
        ticked = rc.default_ticked(self.findings)
        self.tree.blockSignals(True)
        self.tree.clear()
        for cat, title, words, items in rc.grouped(self.findings):
            top = QTreeWidgetItem([f"{title} ({len(items)})", words, ""])
            top.setToolTip(0, words)
            top.setFirstColumnSpanned(False)
            fixable = cat != "review"
            if fixable:
                top.setFlags(top.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
            else:                                  # review only: no tick box at all
                top.setFlags(top.flags() & ~Qt.ItemIsUserCheckable)
            self.tree.addTopLevelItem(top)
            for f in items:
                where = f.full_key + ("" if f.value is None else f"  [{f.value or '(Default)'}]")
                child = QTreeWidgetItem([f.name or f.target, f.target, where])
                child.setData(0, Qt.UserRole, f.ident)
                child.setToolTip(0, f.note or rc.what_changes(f))
                child.setToolTip(2, where)
                if fixable:
                    child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                    child.setCheckState(0, Qt.Checked if f.ident in ticked else Qt.Unchecked)
                else:
                    child.setFlags(child.flags() & ~Qt.ItemIsUserCheckable)
                    child.setForeground(0, Qt.gray)
                    child.setText(1, f"{f.target}  ({f.note})" if f.note else f.target)
                top.addChild(child)
            top.setExpanded(cat not in ("review", "installer_folders") and len(items) <= 30)
        self.tree.blockSignals(False)
        self.banner.setText(rc.summary(self.findings), "good" if not self.findings else "warn")
        self.steps.set(1 if self.findings else 0)
        self.count()

    def chosen(self):
        idents = set()
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            for j in range(top.childCount()):
                child = top.child(j)
                if child.flags() & Qt.ItemIsUserCheckable and child.checkState(0) == Qt.Checked:
                    idents.add(child.data(0, Qt.UserRole))
        return [f for f in self.findings if f.ident in idents and f.fixable]

    def count(self):
        n = len(self.chosen())
        self.fix_button.setText(f"Fix {n} entr{'y' if n == 1 else 'ies'}")
        self.fix_button.setEnabled(n > 0 and not self.busy)

    # ------------------------------------------------------------ fix and undo
    def fix(self):
        chosen = self.chosen()[:rc.MAX_FIX]
        if not chosen or self.busy:
            return
        folder = str(self.backend.backup_root())
        restore = self.restore_box.isChecked()
        if not self.window_owner.confirm("Fix registry entries?", rc.confirmation(chosen, restore, folder)):
            return
        self.busy = True
        self.fix_button.setEnabled(False)
        self.scan_button.setEnabled(False)
        self.steps.set(2)
        self.banner.setText("Backing up, then fixing… Windows may ask you to allow it.", "working")

        def work(_progress):
            return self.backend.fix(chosen, restore_point=restore)

        def done(result):
            self.busy = False
            self.scan_button.setEnabled(True)
            done_n, kept, failed = len(result["done"]), len(result["kept"]), len(result["failed"])
            words = [f"Fixed {done_n} entr{'y' if done_n == 1 else 'ies'}."]
            if kept:
                words.append(f"{kept} left alone because their file came back.")
            if failed:
                unsafe = len(result.get("not_backed_up") or [])
                words.append(f"{failed} couldn't be changed" + (" (Windows wouldn't let them be backed up, so they were "
                             "left alone)" if unsafe else " (Windows refused)") + "; nothing else was affected.")
            if restore:
                made = result.get("restore") == "made"
                words.append("A restore point was made." if made else
                             "Windows didn't make a new restore point" + (f" ({result['restore'][:120]})"
                                                                         if result.get("restore") else "") +
                             "; the registry backup was made either way.")
            words.append("Undo last fix puts it all back.")
            log_event("registry_fix", f"Registry Cleanup removed {done_n} entries (kept {kept}, failed {failed}); "
                      f"backup {result['folder']}", source="Hardware")
            self.banner.setText(" ".join(words), "warn" if failed else "good")
            self.steps.set(3)
            self.refresh_undo()
            remaining = {*result["kept"], *result["failed"]}
            self.show_findings([f for f in self.findings if f.ident not in set(result["done"]) or f.ident in remaining])
            self.banner.setText(" ".join(words), "warn" if failed else "good")

        try:
            self.window_owner.job(work, done, error_title="Registry fix not finished")
        except Exception as problem:
            self.busy = False
            self.scan_button.setEnabled(True)
            self.banner.setText(str(problem)[:300], "bad")
        self._watch_failure()

    def _watch_failure(self):
        """A job that raises shows its own error box; make sure the buttons come back."""
        from PySide6.QtCore import QTimer

        def check():
            if self.busy and not self.window_owner.workers:
                self.busy = False
                self.scan_button.setEnabled(True)
                self.count()
                self.refresh_undo()
            elif self.busy:
                QTimer.singleShot(1000, check)
        QTimer.singleShot(1000, check)

    def latest(self):
        for folder, count, undone in self.backend.backups():
            if not undone:
                return folder, count
        return None, 0

    def refresh_undo(self):
        try:
            folder, count = self.latest()
        except Exception:
            folder, count = None, 0
        self.undo_button.setEnabled(folder is not None and not self.busy)
        self.undo_button.setToolTip(f"Puts back the {count} entries removed on {folder.name}." if folder else
                                    "Nothing to undo yet.")

    def undo(self):
        folder, count = self.latest()
        if folder is None or self.busy:
            return
        if not self.window_owner.confirm("Undo the last registry fix?", f"Put back the {count} registry entries removed "
                                         f"on {folder.name}?\n\nGame Grave imports the backup made just before that fix "
                                         f"({folder}). Entries for all users need you to allow it in the Windows "
                                         "prompt."):
            return
        self.busy = True

        def work(_progress):
            return self.backend.undo(folder)

        def done(failed):
            self.busy = False
            log_event("registry_undo", f"Registry Cleanup put back {count} entries from {folder}", source="Hardware")
            self.banner.setText("Put back." if not failed else "Put back, except: " + ", ".join(failed[:5]),
                                "good" if not failed else "warn")
            self.refresh_undo()
        self.window_owner.job(work, done, error_title="Undo not finished")
        self._watch_failure()

    def open_backups(self):
        root = self.backend.backup_root()
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        if os.name == "nt":
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(root)))
