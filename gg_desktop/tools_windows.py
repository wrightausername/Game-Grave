"""Screens for the seven Windows tools. Each one shows exactly what it will change, asks first, and writes the activity log.

The logic and every outside effect live in `winpc` (tested without a real PC). This module is only dialogs.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QInputDialog, QLineEdit, QListWidget, QListWidgetItem,
    QPlainTextEdit,
)
from shiboken6 import isValid

from core import human_size
from gg_desktop import winpc
from gg_desktop.widgets import button, column, label, row

BACKUP_NAME = "game-optimizer-backup.json"


DARK = ("QDialog{background:#05090c;color:#e8eef5;} QLabel{color:#e8eef5;background:transparent;} "
        "QCheckBox{color:#e8eef5;spacing:8px;} "
        "QCheckBox::indicator,QListView::indicator{width:15px;height:15px;border:1px solid #6b7788;background:#0a1118;border-radius:3px;} "
        "QCheckBox::indicator:checked,QListView::indicator:checked{background:#ff284a;border-color:#ff284a;} "
        "QListWidget,QPlainTextEdit,QComboBox,QLineEdit{background:#0a1118;color:#e8eef5;border:1px solid #243242;border-radius:5px;} "
        "QListWidget::item{padding:4px;} QListWidget::item:selected{background:#2a0f17;color:#ffffff;} "
        "QPlainTextEdit{font-family:Consolas,monospace;} QComboBox QAbstractItemView{background:#0a1118;color:#e8eef5;}")


class WinDialog(QDialog):
    """The one dialog class for these tools (also lets tests open them without blocking)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(DARK)


def _text(widget_text, role="subtle", wrap=True):
    item = label(widget_text, role, wrap=wrap)
    item.setTextFormat(Qt.PlainText)
    item.setMinimumWidth(0)
    return item


def _dialog(window, title, intro, width=560):
    dialog = WinDialog(window)
    dialog.setWindowTitle("Game Grave · " + title)
    dialog.setMinimumWidth(width)
    box = column(spacing=8, margins=(16, 14, 16, 14))
    dialog.setLayout(box)
    box.addWidget(label(title, "sectionTitle"))
    box.addWidget(_text(intro))
    dialog.result_line = _text("", "caption")
    dialog.result_line.setAccessibleName(title + " result")
    return dialog, box


def _close_row(dialog, box, *extra):
    actions = row(spacing=8)
    for control in extra:
        actions.addWidget(control)
    actions.addStretch()
    actions.addWidget(button("Close", dialog.accept))
    box.addWidget(dialog.result_line)
    box.addLayout(actions)


def _job(window, work, done, title):
    """Run work off the UI thread; errors come back as text so one tool's failure never disturbs a scan."""
    def run(_progress):
        try:
            return work(), ""
        except Exception as exc:  # shown to the owner in the dialog, never swallowed silently
            return None, str(exc)[:300] or type(exc).__name__
    window.job(run, lambda packet: done(*packet), error_title=title)


def _never_touch(window):
    return list(window.settings.get("never_touch", []))


def _busy(window):
    if window.scanning or window.cleaning:
        window.info("Game Grave is busy", "Finish the current operation first.")
        return True
    return False


def _config_file(name):
    from core import config_dir
    return Path(config_dir()) / name


def _mb(kb):
    return f"{kb / 1024:,.0f} MB"


# ------------------------------------------------------------------ 1. Windows Cleanup
def windows_cleanup(window):
    if _busy(window):
        return
    roots = winpc.cleanup_roots()
    window.status.setText("Looking through Windows temporary folders. Nothing is being changed.")
    never = _never_touch(window)
    _job(window, lambda: winpc.plan_cleanup(roots, never_touch=never),
         lambda plan, error: _cleanup_dialog(window, roots, plan, error), "Windows Cleanup")


def _cleanup_dialog(window, roots, plan, error):
    window.status.setText("Ready.")
    if error:
        window.error("Windows Cleanup could not look", error)
        return
    dialog, box = _dialog(window, "Windows Cleanup",
                          f"Looks only in these temporary folders and lists files that have not changed for "
                          f"{winpc.MIN_AGE_DAYS} days. Files are deleted permanently, not sent to the Recycle Bin. "
                          "Files that Windows or an app is using are skipped, never forced.")
    box.addWidget(_text("\n".join(str(r) for r in roots), "detailValue"))
    if plan.items:
        summary = (f"{len(plan.items):,}{'+' if plan.truncated else ''} files found, {human_size(plan.total)} reported. "
                   "Nothing has been deleted yet.")
    else:
        summary = "No files older than that were found in these folders. Nothing to delete."
    box.addWidget(_text(summary, "detailValue"))
    names = QListWidget()
    names.setAccessibleName("Files that would be deleted")
    names.setMaximumHeight(150)
    for item in sorted(plan.items, key=lambda i: -i.size)[:40]:
        names.addItem(f"{Path(item.path).name}   {human_size(item.size)}")
    names.setVisible(bool(plan.items))
    box.addWidget(names)
    delete = button("Delete these files…", kind="danger")
    delete.setEnabled(bool(plan.items))
    delete.setAccessibleName("Delete the listed temporary files")

    def go():
        message = (f"Permanently delete {len(plan.items):,} temporary files ({human_size(plan.total)} reported)?\n\n"
                   "Folders searched:\n" + "\n".join(str(r) for r in roots) +
                   f"\n\nOnly files unchanged for {winpc.MIN_AGE_DAYS} days or more are deleted. They do not go to the "
                   "Recycle Bin. Files in use are skipped. Each file is checked again before it is deleted.")
        if not window.confirm("Delete temporary files", message, destructive=True):
            return
        delete.setEnabled(False)
        dialog.result_line.setText("Deleting…")
        items = list(plan.items)

        def finished(result, err):
            if err:
                window.error("Windows Cleanup stopped", err)
            else:
                text = (f"Deleted {result.removed:,} files ({human_size(result.reported_bytes)} reported). "
                        f"{result.skipped:,} skipped because they changed, were in use or could not be removed.")
                winpc.activity("Windows Cleanup", text, size_bytes=result.reported_bytes, result="Permanently deleted")
                window.status.setText("Windows Cleanup finished. " + text)
                if isValid(dialog):
                    dialog.result_line.setText(text)
        _job(window, lambda: winpc.run_cleanup(items, roots), finished, "Windows Cleanup")
    delete.clicked.connect(go)
    dialog.delete_button = delete
    _close_row(dialog, box, delete)
    window._tools_dialog = dialog
    dialog.exec()


# ------------------------------------------------------------------ 2. Game Optimizer
def game_optimizer(window):
    if _busy(window):
        return
    reg, runner = winpc.default_registry(), winpc.Runner()
    if reg is None:
        window.info("Game Optimizer needs Windows", "These settings only exist on Windows.")
        return
    backup = _config_file(BACKUP_NAME)
    dialog, box = _dialog(window, "Game Optimizer",
                          "Three Windows settings that can help games. Tick the ones you want. Your current values are "
                          "remembered first, and Undo puts them back exactly. Game Grave does not claim any speed gain.")
    checks = {}
    holder = column(spacing=6)
    box.addLayout(holder)

    def refresh():
        while holder.count():
            item = holder.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        checks.clear()
        for state in winpc.read_optimizer(reg, runner):
            check = QCheckBox(state.title + ("  (already set)" if state.applied else ""))
            check.setEnabled(not state.applied)
            check.setAccessibleName(state.title)
            holder.addWidget(check)
            holder.addWidget(_text(state.detail + "\n" + state.current, "caption"))
            checks[state.key] = check
        undo.setEnabled(winpc.has_backup(backup))
    undo = button("Undo my changes…")
    undo.setAccessibleName("Undo Game Optimizer changes")
    apply_button = button("Apply selected…", kind="primary")

    def apply():
        keys = {k for k, c in checks.items() if c.isChecked()}
        if not keys:
            dialog.result_line.setText("Tick at least one setting first.")
            return
        lines = [spec["title"] + ": " + spec["detail"] for spec in winpc.OPTIMIZER_SETTINGS if spec["key"] in keys]
        if not window.confirm("Change Windows settings", "Game Grave will change:\n\n" + "\n\n".join(lines) +
                              "\n\nYour current values are saved first so Undo can restore them."):
            return
        try:
            notes = winpc.apply_optimizer(reg, runner, keys, backup)
        except Exception as exc:
            window.error("Game Optimizer stopped", str(exc)[:300])
            return
        winpc.activity("Game Optimizer", "Applied: " + "; ".join(spec["title"] for spec in winpc.OPTIMIZER_SETTINGS
                                                                   if spec["key"] in keys), result="Changed")
        dialog.result_line.setText(" ".join(notes))
        refresh()

    def undo_all():
        if not window.confirm("Undo Game Optimizer", "Put every setting Game Grave changed back to the value it had "
                              "before, including the previous power plan?"):
            return
        notes = winpc.undo_optimizer(reg, runner, backup)
        winpc.activity("Game Optimizer", "Undone: " + " ".join(notes), result="Restored")
        dialog.result_line.setText(" ".join(notes))
        refresh()
    apply_button.clicked.connect(apply)
    undo.clicked.connect(undo_all)
    dialog.apply_button, dialog.undo_button, dialog.checks = apply_button, undo, checks
    _close_row(dialog, box, apply_button, undo)
    refresh()
    window._tools_dialog = dialog
    dialog.exec()


# ------------------------------------------------------------------ 3. Memory Optimizer
def memory_optimizer(window):
    if _busy(window):
        return
    runner = winpc.Runner()
    dialog, box = _dialog(window, "Memory Optimizer",
                          "Lists the apps you have open, largest memory first. Tick the ones to close. Each is asked "
                          "to close normally and never forced, so unsaved work can still prompt you. Windows itself and "
                          "Game Grave are never listed.")
    usage = _text("", "detailValue")
    box.addWidget(usage)
    listing = QListWidget()
    listing.setAccessibleName("Open apps")
    listing.setMinimumHeight(190)
    box.addWidget(listing, 1)
    close_button = button("Close selected apps…", kind="primary")
    refresh_button = button("Refresh list")

    def fill(procs, error=""):
        if not isValid(dialog):
            return
        listing.clear()
        for proc in procs[:40]:
            item = QListWidgetItem(f"{proc.name}   ·   {_mb(proc.kb)}   ·   PID {proc.pid}")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            item.setData(Qt.UserRole, (proc.pid, proc.name))
            listing.addItem(item)
        from gg_desktop import tools_system
        percent = tools_system.memory_percent()
        usage.setText(("Memory in use: " + f"{percent}%" if percent is not None else "Memory use could not be read.") +
                      (f"   ·   {len(procs)} apps found" if procs else "   ·   No apps to list"))
        close_button.setEnabled(bool(procs))
        if error:
            dialog.result_line.setText(error)

    def load():
        _job(window, lambda: winpc.list_processes(runner), lambda procs, err: fill(procs or [], err), "Memory Optimizer")

    def close_selected():
        chosen = [listing.item(i).data(Qt.UserRole) for i in range(listing.count())
                  if listing.item(i).checkState() == Qt.Checked]
        if not chosen:
            dialog.result_line.setText("Tick at least one app first.")
            return
        names = "\n".join(f"{name} (PID {pid})" for pid, name in chosen)
        if not window.confirm("Close apps", f"Ask these {len(chosen)} apps to close?\n\n{names}\n\n"
                              "They are asked politely, not forced. Save your work first."):
            return
        pids = [pid for pid, _ in chosen]

        def work():
            notes = winpc.close_processes(runner, pids)
            import time
            time.sleep(1.5)
            still = {p.pid for p in winpc.list_processes(runner)}
            return notes, still

        def finished(result, error):
            if error:
                window.error("Memory Optimizer stopped", error)
                return
            notes, still = result
            left = sum(1 for pid in pids if pid in still)
            text = f"Asked {len(pids)} apps to close; {left} still running. " + (
                "An app can stay open to ask about unsaved work." if left else "")
            winpc.activity("Memory Optimizer", "Asked to close: " + ", ".join(n for _p, n in chosen) + ". " + text,
                           result="Closed" if not left else "Some still running")
            if isValid(dialog):
                dialog.result_line.setText(text)
                load()
        _job(window, work, finished, "Memory Optimizer")
    close_button.clicked.connect(close_selected)
    refresh_button.clicked.connect(load)
    dialog.listing, dialog.close_button = listing, close_button
    dialog.fill = fill
    _close_row(dialog, box, close_button, refresh_button)
    load()
    window._tools_dialog = dialog
    dialog.exec()


# ------------------------------------------------------------------ 4. Startup Manager
def startup_manager(window):
    if _busy(window):
        return
    reg = winpc.default_registry()
    if reg is None:
        window.info("Startup Manager needs Windows", "Startup entries only exist on Windows.")
        return
    dialog, box = _dialog(window, "Startup Manager",
                          "Programs that start when you sign in. Turning one off uses the same switch as Task Manager's "
                          "Startup tab: the entry stays, only its approval flips, and you can turn it back on here. "
                          "Entries for all users need administrator rights and are shown read-only.", 620)
    table = QListWidget()
    table.setAccessibleName("Startup entries")
    table.setMinimumHeight(220)
    table.setSelectionMode(QListWidget.ExtendedSelection)
    box.addWidget(table, 1)
    disable, enable = button("Turn off selected…", kind="primary"), button("Turn on selected…")
    entries = []

    def refresh():
        entries[:] = winpc.list_startup(reg)
        table.clear()
        for entry in entries:
            state = "On" if entry.enabled else "Off"
            lock = "" if entry.can_toggle else "  (all users, read-only)"
            item = QListWidgetItem(f"{state}   ·   {entry.name}   ·   {entry.source}{lock}\n{entry.command[:140]}")
            item.setData(Qt.UserRole, entry)
            item.setToolTip(entry.command)
            table.addItem(item)
        if not entries:
            dialog.result_line.setText("No startup entries were found.")

    def change(target):
        chosen = [i.data(Qt.UserRole) for i in table.selectedItems()]
        chosen = [e for e in chosen if e.can_toggle and e.enabled != target]
        if not chosen:
            dialog.result_line.setText("Select entries that can be changed first (read-only ones are skipped).")
            return
        verb = "on" if target else "off"
        names = "\n".join(f"{e.name} ({e.source})" for e in chosen)
        if not window.confirm("Change startup", f"Turn {verb} these {len(chosen)} startup entries?\n\n{names}\n\n"
                              "Nothing is deleted. Change takes effect the next time you sign in."):
            return
        done = []
        for entry in chosen:
            try:
                winpc.set_startup_enabled(reg, entry, target)
                done.append(entry.name)
            except Exception as exc:
                window.error("Startup change failed", f"{entry.name}: {exc}")
        if done:
            winpc.activity("Startup Manager", f"Turned {verb}: " + ", ".join(done), result="Changed")
            dialog.result_line.setText(f"Turned {verb}: " + ", ".join(done))
        refresh()
    disable.clicked.connect(lambda: change(False))
    enable.clicked.connect(lambda: change(True))
    dialog.table, dialog.disable_button, dialog.enable_button = table, disable, enable
    _close_row(dialog, box, disable, enable)
    refresh()
    window._tools_dialog = dialog
    dialog.exec()


# ------------------------------------------------------------------ 5. Command Runner
def command_runner(window):
    if _busy(window):
        return
    runner = winpc.Runner()
    dialog, box = _dialog(window, "Command Runner",
                          "Runs one command line that you type or pick, with the same permissions as Game Grave. You "
                          "always see the exact line and confirm before it runs. It stops after 2 minutes. Nothing runs "
                          "in the background.", 640)
    presets = QComboBox()
    presets.setAccessibleName("Example commands")
    presets.addItem("Pick an example…", "")
    for title, command in winpc.PRESETS:
        presets.addItem(title, command)
    box.addWidget(presets)
    line = QLineEdit()
    line.setPlaceholderText("Command, for example: ipconfig /all")
    line.setAccessibleName("Command to run")
    box.addWidget(line)
    output = QPlainTextEdit()
    output.setReadOnly(True)
    output.setAccessibleName("Command output")
    output.setMinimumHeight(180)
    box.addWidget(output, 1)
    run_button = button("Run…", kind="primary")
    presets.currentIndexChanged.connect(lambda: line.setText(presets.currentData() or line.text()))

    def go():
        text = line.text().strip()
        reason = winpc.validate_command(text)
        if reason:
            dialog.result_line.setText(reason)
            return
        if not window.confirm("Run this command", "Game Grave will run exactly this line:\n\n    " + text +
                              "\n\nIt runs through cmd.exe with your own permissions and can change your PC if the "
                              "command does. Only continue if you understand it.", destructive=True):
            return
        run_button.setEnabled(False)
        output.setPlainText("Running…")

        def finished(result, error):
            if isValid(dialog):
                run_button.setEnabled(True)
            if error:
                window.error("Command Runner stopped", error)
                return
            tail = ("\n\n[Stopped after 2 minutes]" if result.timed_out else "") + (
                "\n\n[Output shortened to 64 KB]" if result.truncated else "")
            summary = "Finished with exit code " + str(result.code) + "." if not result.timed_out else "Stopped after 2 minutes."
            winpc.activity("Command Runner", f"Ran: {text[:300]}. {summary}", result=summary)
            if isValid(dialog):
                output.setPlainText((result.output or "(no output)") + tail)
                dialog.result_line.setText(summary)
        _job(window, lambda: winpc.run_command(runner, text), finished, "Command Runner")
    run_button.clicked.connect(go)
    line.returnPressed.connect(go)
    dialog.line, dialog.output, dialog.run_button = line, output, run_button
    _close_row(dialog, box, run_button)
    window._tools_dialog = dialog
    dialog.exec()


# ------------------------------------------------------------------ 6. File Associations
def file_associations(window):
    reg = winpc.default_registry()
    if reg is None:
        window.info("File Associations needs Windows", "File associations only exist on Windows.")
        return
    dialog, box = _dialog(window, "File Associations",
                          "Shows which app opens a file type. Windows does not let other apps change your defaults, so "
                          "Game Grave looks the answer up and opens Windows' Default apps page for you to change it. "
                          "Nothing is changed here.")
    kind = QComboBox()
    kind.setEditable(True)
    kind.setAccessibleName("File extension")
    kind.addItems(winpc.COMMON_EXTENSIONS)
    box.addWidget(kind)
    answer = _text("Choose or type an extension, then press Look up.", "detailValue")
    box.addWidget(answer)
    command = _text("", "caption")
    box.addWidget(command)

    def look():
        try:
            found = winpc.read_association(reg, kind.currentText())
        except ValueError as exc:
            answer.setText(str(exc))
            command.setText("")
            return
        answer.setText(f"{found.ext} opens with: {found.app}\n{found.source}")
        command.setText(("Runs: " + found.command) if found.command else "")

    def settings_page():
        if not QDesktopServices.openUrl(QUrl("ms-settings:defaultapps")):
            window.error("Could not open Windows Settings", "Open Settings, then Apps, then Default apps yourself.")
    lookup = button("Look up", look, kind="primary")
    kind.lineEdit().returnPressed.connect(look)
    dialog.kind, dialog.answer, dialog.lookup = kind, answer, lookup
    _close_row(dialog, box, lookup, button("Open Windows Default apps", settings_page))
    look()
    window._tools_dialog = dialog
    dialog.exec()


# ------------------------------------------------------------------ 7. Junction Manager
def junction_manager(window):
    if _busy(window):
        return
    runner = winpc.Runner()
    dialog, box = _dialog(window, "Junction Manager",
                          "A junction makes one folder appear in a second place, for example a game folder moved to "
                          "another drive. Choose a folder to list its links. Removing a link deletes only the link, never "
                          "the folder it points to. Real folders are never removed here.", 640)
    where = _text("No folder chosen yet.", "detailValue")
    box.addWidget(where)
    listing = QListWidget()
    listing.setAccessibleName("Links found")
    listing.setMinimumHeight(190)
    box.addWidget(listing, 1)
    state = {"root": ""}
    remove = button("Remove selected link…")
    create = button("Create junction…")
    choose = button("Choose folder…", kind="primary")

    def fill(links, error=""):
        if not isValid(dialog):
            return
        listing.clear()
        for link in links:
            status = "points to" if link.exists else "BROKEN, points to"
            item = QListWidgetItem(f"{link.kind}   ·   {link.path}\n    {status}  {link.target or 'unknown'}")
            item.setData(Qt.UserRole, link)
            listing.addItem(item)
        dialog.result_line.setText(error or (f"{len(links)} links found." if links else "No junctions or links found there."))

    def scan(root):
        state["root"] = root
        where.setText("Looking in: " + root)
        _job(window, lambda: winpc.scan_links(root), lambda links, err: fill(links or [], err), "Junction Manager")

    def pick():
        root = QFileDialog.getExistingDirectory(window, "Choose a folder to look in", state["root"] or str(Path.home()))
        if root:
            scan(root)

    def remove_selected():
        item = listing.currentItem()
        if item is None:
            dialog.result_line.setText("Select a link first.")
            return
        link = item.data(Qt.UserRole)
        if not window.confirm("Remove link", f"Remove this {link.kind}?\n\n{link.path}\n\nIt points to:\n{link.target}\n\n"
                              "Only the link is removed. The folder it points to and everything inside it stay exactly "
                              "as they are.", destructive=True):
            return
        try:
            target, kept = winpc.remove_link(link.path, never_touch=_never_touch(window))
        except (OSError, ValueError) as exc:
            window.error("Link not removed", str(exc))
            return
        text = f"Removed the link {link.path}. " + ("Its target is untouched." if kept else "Its target was not found.")
        winpc.activity("Junction Manager", text, path=link.path, result="Link removed")
        dialog.result_line.setText(text)
        if state["root"]:
            scan(state["root"])

    def create_one():
        parent = QFileDialog.getExistingDirectory(window, "Choose the folder that will hold the new link",
                                                  state["root"] or str(Path.home()))
        if not parent:
            return
        name, ok = QInputDialog.getText(window, "Name the link", "Name for the new link (a folder name):")
        name = name.strip()
        if not ok or not name or any(c in name for c in '\\/:*?"<>|'):
            if ok:
                window.error("Name not accepted", "Use a plain folder name without \\ / : * ? \" < > |.")
            return
        target = QFileDialog.getExistingDirectory(window, "Choose the existing folder the link should point to", parent)
        if not target:
            return
        link = str(Path(parent) / name)
        reason = winpc.check_new_link(link, target, _never_touch(window))
        if reason:
            window.error("Junction not created", reason)
            return
        if not window.confirm("Create junction", f"Create this junction?\n\nNew link:\n{link}\n\nPoints to:\n{target}\n\n"
                              "Nothing is moved or copied. Programs that open the link will see the target's files."):
            return
        try:
            winpc.create_junction(runner, link, target, never_touch=_never_touch(window))
        except (OSError, ValueError) as exc:
            window.error("Junction not created", str(exc))
            return
        text = f"Created junction {link} pointing to {target}."
        winpc.activity("Junction Manager", text, path=link, result="Junction created")
        dialog.result_line.setText(text)
        scan(parent)
    choose.clicked.connect(pick)
    remove.clicked.connect(remove_selected)
    create.clicked.connect(create_one)
    dialog.listing, dialog.fill, dialog.remove_button, dialog.create_button = listing, fill, remove, create
    dialog.scan = scan
    _close_row(dialog, box, choose, create, remove)
    window._tools_dialog = dialog
    dialog.exec()


HANDLERS = {"windows_cleanup": windows_cleanup, "game_optimizer": game_optimizer, "memory_optimizer": memory_optimizer,
            "startup_manager": startup_manager, "command_runner": command_runner, "file_associations": file_associations,
            "junction_manager": junction_manager}
