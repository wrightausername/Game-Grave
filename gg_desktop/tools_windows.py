"""Screens for the Windows tools. Each one shows exactly what it will change, asks first, and writes the activity log.

The logic and every outside effect live in `winpc` (tested without a real PC). This module is only dialogs, all built on
`tools_shell.ToolDialog`: plain words up front, numbered steps, the exact technical lines folded under "Show technical
details" (and always repeated in the confirmation), a coloured result banner, Close on the left and the main action on
the right.
"""
from __future__ import annotations

from pathlib import Path
import re

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QComboBox, QFileDialog, QInputDialog, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit
from shiboken6 import isValid

from core import human_size
from gg_desktop import tools_shell as shell, tools_words as words, winpc
from gg_desktop.widgets import button, row

BACKUP_NAME = "game-optimizer-backup.json"


class WinDialog(shell.ToolDialog):
    """The one dialog class for these tools (also lets tests open them without blocking)."""


def _dialog(window, key, title, symbol, width=600):
    dialog = WinDialog(window, key, title, symbol, width=width)
    return dialog, dialog.body


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


def _show(window, dialog):
    window._tools_dialog = dialog
    dialog.exec()


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
    dialog, box = _dialog(window, "windows_cleanup", "Windows Cleanup", "trash")
    dialog.step(1)
    frame, inner = shell.card(spacing=8, margins=(14, 12, 14, 12))
    count = f"{len(plan.items):,}{'+' if plan.truncated else ''}"
    if plan.items:
        lead = f"{count} old temporary files, {human_size(plan.total)}"
        note = (f"None of these have changed for {winpc.MIN_AGE_DAYS} days. They are deleted for good, not sent to the "
                "Recycle Bin. Anything Windows or an app is using is skipped, never forced.")
    else:
        lead = "Nothing to clear"
        note = f"No temporary files older than {winpc.MIN_AGE_DAYS} days were found."
    inner.addWidget(shell.text(lead, "toolLead"))
    inner.addWidget(shell.text(note))
    names = QListWidget()
    names.setAccessibleName("Files that would be deleted")
    names.setMaximumHeight(180)
    for item in sorted(plan.items, key=lambda i: -i.size)[:40]:
        entry = QListWidgetItem(f"{Path(item.path).name}    {human_size(item.size)}")
        entry.setToolTip(str(item.path))
        names.addItem(entry)
    if len(plan.items) > 40:
        names.addItem(f"…and {len(plan.items) - 40:,} more")
    names.setVisible(bool(plan.items))
    inner.addWidget(names)
    box.addWidget(frame)
    dialog.details.set_lines(["Folders searched:"] + [str(r) for r in roots] +
                             [f"Only files unchanged for {winpc.MIN_AGE_DAYS}+ days. Each is checked again just before it "
                              "is deleted."])
    delete = button(("Delete " + words.plain_count(len(plan.items), "file")) if plan.items else "Delete", kind="danger")
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
        dialog.step(2)
        dialog.result("Deleting…", words.WORKING)
        items = list(plan.items)

        def finished(result, err):
            if err:
                window.error("Windows Cleanup stopped", err)
                if isValid(dialog):
                    dialog.result("Windows Cleanup stopped: " + err, words.BAD)
                return
            text = (f"Deleted {words.plain_count(result.removed, 'file')} ({human_size(result.reported_bytes)} reported). "
                    f"{result.skipped:,} skipped because they changed, were in use or could not be removed.")
            winpc.activity("Windows Cleanup", text, size_bytes=result.reported_bytes, result="Permanently deleted")
            window.status.setText("Windows Cleanup finished. " + text)
            if isValid(dialog):
                dialog.step(3)
                dialog.result(text, words.GOOD if result.removed else words.WARN)
        _job(window, lambda: winpc.run_cleanup(items, roots), finished, "Windows Cleanup")
    delete.clicked.connect(go)
    dialog.delete_button = delete
    dialog.add_actions(delete)
    _show(window, dialog)


# ------------------------------------------------------------------ 2. Game Optimizer
def game_optimizer(window):
    if _busy(window):
        return
    reg, runner = winpc.default_registry(), winpc.Runner()
    if reg is None:
        window.info("Game Optimizer needs Windows", "These settings only exist on Windows.")
        return
    backup = _config_file(BACKUP_NAME)
    dialog, box = _dialog(window, "game_optimizer", "Game Optimizer", "play")
    frame, holder = shell.card()
    box.addWidget(frame)
    box.addWidget(shell.text("Your current values are saved first, so Undo puts them back exactly. Game Grave does not "
                             "promise any speed gain."))
    dialog.details.set_lines([spec["title"] + ":\n  " + spec["detail"] for spec in winpc.OPTIMIZER_SETTINGS])
    checks = {}
    undo = button("Undo my changes…")
    undo.setAccessibleName("Undo Game Optimizer changes")
    apply_button = button("Apply", kind="primary")
    apply_button.setAccessibleName("Apply selected")

    def recount():
        picked = sum(1 for c in checks.values() if c.isChecked())
        apply_button.setText(words.apply_label(picked) + ("…" if picked else ""))
        apply_button.setEnabled(bool(picked))
        dialog.step(0)

    def refresh():
        while holder.count():
            item = holder.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        checks.clear()
        states = winpc.read_optimizer(reg, runner)
        for n, state in enumerate(states):
            spec = next(s for s in winpc.OPTIMIZER_SETTINGS if s["key"] == state.key)
            values = [winpc._dword(reg, target) for target, _want in spec["targets"]]
            now, tone = words.optimizer_state(state.key, values, state.current, state.applied)
            name, plain = words.optimizer_plain(state.key)
            line = shell.ChoiceRow(name, plain + ("  Already set." if state.applied else ""), now, tone,
                                   last=n == len(states) - 1, accessible=state.title)
            line.check.setEnabled(not state.applied)
            line.check.toggled.connect(recount)
            holder.addWidget(line)
            checks[state.key] = line.check
        undo.setEnabled(winpc.has_backup(backup))
        recount()

    def apply():
        keys = {k for k, c in checks.items() if c.isChecked()}
        if not keys:
            dialog.result("Tick at least one setting first.", words.WARN)
            return
        lines = [spec["title"] + ": " + spec["detail"] for spec in winpc.OPTIMIZER_SETTINGS if spec["key"] in keys]
        dialog.step(1)
        if not window.confirm("Change Windows settings", "Game Grave will change:\n\n" + "\n\n".join(lines) +
                              "\n\nYour current values are saved first so Undo can restore them."):
            dialog.step(0)
            return
        try:
            notes = winpc.apply_optimizer(reg, runner, keys, backup)
        except Exception as exc:
            window.error("Game Optimizer stopped", str(exc)[:300])
            dialog.result("Game Optimizer stopped: " + str(exc)[:300], words.BAD)
            return
        winpc.activity("Game Optimizer", "Applied: " + "; ".join(spec["title"] for spec in winpc.OPTIMIZER_SETTINGS
                                                                   if spec["key"] in keys), result="Changed")
        refresh()
        dialog.step(3)
        problem = any(re.search(r"\bnot\b", n, re.IGNORECASE) for n in notes)
        dialog.result(" ".join(notes) + ("" if problem else " Undo puts it back any time."),
                      words.WARN if problem else words.GOOD)

    def undo_all():
        if not window.confirm("Undo Game Optimizer", "Put every setting Game Grave changed back to the value it had "
                              "before, including the previous power plan?"):
            return
        notes = winpc.undo_optimizer(reg, runner, backup)
        winpc.activity("Game Optimizer", "Undone: " + " ".join(notes), result="Restored")
        refresh()
        dialog.details.set_lines([spec["title"] + ":\n  " + spec["detail"] for spec in winpc.OPTIMIZER_SETTINGS] +
                                 ["", "Last undo:"] + notes)
        problem = any(re.search(r"\bnot\b", n, re.IGNORECASE) for n in notes)
        dialog.result("Some settings could not be put back. Open the technical details to see which." if problem else
                      "Your previous settings are back, exactly as they were.", words.WARN if problem else words.GOOD)
    apply_button.clicked.connect(apply)
    undo.clicked.connect(undo_all)
    dialog.apply_button, dialog.undo_button, dialog.checks = apply_button, undo, checks
    dialog.add_actions(undo, apply_button)
    refresh()
    _show(window, dialog)


# ------------------------------------------------------------------ 3. Memory Optimizer
def memory_optimizer(window):
    if _busy(window):
        return
    runner = winpc.Runner()
    dialog, box = _dialog(window, "memory_optimizer", "Memory Optimizer", "storage")
    head = row(spacing=10)
    usage = shell.text("Reading open apps…", "toolLead", wrap=False)
    memory_pill = shell.pill("Memory …", words.IDLE)
    head.addWidget(usage, 1)
    head.addWidget(memory_pill)
    box.addLayout(head)
    box.addWidget(shell.text("Each app is asked to close normally, like pressing its X, so anything unsaved can still ask "
                             "you first. Windows itself and Game Grave are never listed."))
    listing = QListWidget()
    listing.setAccessibleName("Open apps")
    listing.setMinimumHeight(220)
    box.addWidget(listing, 1)
    dialog.details.set_lines(["Each ticked app gets:  taskkill /PID <its id>", "No /F, so nothing is forced closed.",
                              "The list comes from:  tasklist (your own session only)"])
    close_button = button("Close selected apps", kind="primary")
    close_button.setAccessibleName("Close selected apps")
    refresh_button = button("Refresh list")

    def recount(*_):
        picked = sum(1 for i in range(listing.count()) if listing.item(i).checkState() == Qt.Checked)
        close_button.setText(words.close_label(picked) + ("…" if picked else ""))
        close_button.setEnabled(listing.count() > 0)
    listing.itemChanged.connect(recount)

    def fill(procs, error=""):
        if not isValid(dialog):
            return
        listing.blockSignals(True)
        listing.clear()
        for proc in procs[:40]:
            item = QListWidgetItem(f"{proc.name}    {_mb(proc.kb)}")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            item.setData(Qt.UserRole, (proc.pid, proc.name))
            item.setToolTip(f"{proc.name}, process ID {proc.pid}, {_mb(proc.kb)} in use")
            listing.addItem(item)
        listing.blockSignals(False)
        from gg_desktop import tools_system
        percent = tools_system.memory_percent()
        usage.setText(words.plain_count(len(procs), "app") + " open" if procs else "No apps to list")
        if percent is None:
            shell.set_pill(memory_pill, "Memory use unknown", words.IDLE)
        else:
            shell.set_pill(memory_pill, f"Memory {percent}% used",
                           words.BAD if percent >= 90 else words.WARN if percent >= 75 else words.GOOD)
        recount()
        if error:
            dialog.result(error, words.BAD)

    def load():
        _job(window, lambda: winpc.list_processes(runner), lambda procs, err: fill(procs or [], err), "Memory Optimizer")

    def close_selected():
        chosen = [listing.item(i).data(Qt.UserRole) for i in range(listing.count())
                  if listing.item(i).checkState() == Qt.Checked]
        if not chosen:
            dialog.result("Tick at least one app first.", words.WARN)
            return
        names = "\n".join(f"{name} (PID {pid})" for pid, name in chosen)
        dialog.step(1)
        if not window.confirm("Close apps", f"Ask these {len(chosen)} apps to close?\n\n{names}\n\n"
                              "They are asked politely, not forced. Save your work first."):
            dialog.step(0)
            return
        pids = [pid for pid, _ in chosen]
        dialog.result("Asking " + words.plain_count(len(pids), "app") + " to close…", words.WORKING)

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
            text = f"Asked {words.plain_count(len(pids), 'app')} to close; {left} still running. " + (
                "An app can stay open to ask about unsaved work." if left else "")
            winpc.activity("Memory Optimizer", "Asked to close: " + ", ".join(n for _p, n in chosen) + ". " + text,
                           result="Closed" if not left else "Some still running")
            if isValid(dialog):
                load()
                dialog.step(3)
                dialog.result(text.strip(), words.WARN if left else words.GOOD)
        _job(window, work, finished, "Memory Optimizer")
    close_button.clicked.connect(close_selected)
    refresh_button.clicked.connect(load)
    dialog.listing, dialog.close_button = listing, close_button
    dialog.fill = fill
    dialog.add_actions(refresh_button, close_button)
    load()
    _show(window, dialog)


# ------------------------------------------------------------------ 4. Command Runner
def command_runner(window):
    if _busy(window):
        return
    runner = winpc.Runner()
    dialog, box = _dialog(window, "command_runner", "Command Runner", "list", 660)
    presets = QComboBox()
    presets.setAccessibleName("Example commands")
    presets.addItem("Pick a ready-made command…", "")
    for title, command in winpc.PRESETS:
        presets.addItem(title, command)
    box.addWidget(presets)
    line = QLineEdit()
    line.setPlaceholderText("Or type one, for example: ipconfig /all")
    line.setAccessibleName("Command to run")
    box.addWidget(line)
    box.addWidget(shell.text("You see the exact line and confirm before it runs. It has the same permissions as Game "
                             "Grave and can change your PC if the command does. Nothing runs in the background."))
    output = QPlainTextEdit()
    output.setReadOnly(True)
    output.setAccessibleName("Command output")
    output.setPlaceholderText("What the command prints shows up here.")
    output.setMinimumHeight(190)
    box.addWidget(output, 1)
    dialog.details.set_lines(["Runs through:  cmd.exe /d /s /c <your line>", "Stops after 2 minutes.",
                              "Output is kept to the first 64 KB."])
    run_button = button("Run…", kind="primary")
    run_button.setAccessibleName("Run")

    def picked():
        if presets.currentData():
            line.setText(presets.currentData())
        dialog.step(0)
    presets.currentIndexChanged.connect(picked)

    def go():
        text = line.text().strip()
        reason = winpc.validate_command(text)
        if reason:
            dialog.result(reason, words.WARN)
            return
        dialog.step(1)
        if not window.confirm("Run this command", "Game Grave will run exactly this line:\n\n    " + text +
                              "\n\nIt runs through cmd.exe with your own permissions and can change your PC if the "
                              "command does. Only continue if you understand it.", destructive=True):
            dialog.step(0)
            return
        run_button.setEnabled(False)
        output.setPlainText("")
        dialog.result("Running " + text[:80] + "…", words.WORKING)

        def finished(result, error):
            if isValid(dialog):
                run_button.setEnabled(True)
            if error:
                window.error("Command Runner stopped", error)
                if isValid(dialog):
                    dialog.result("Command Runner stopped: " + error, words.BAD)
                return
            tail = ("\n\n[Stopped after 2 minutes]" if result.timed_out else "") + (
                "\n\n[Output shortened to 64 KB]" if result.truncated else "")
            summary = "Finished with exit code " + str(result.code) + "." if not result.timed_out else "Stopped after 2 minutes."
            winpc.activity("Command Runner", f"Ran: {text[:300]}. {summary}", result=summary)
            if isValid(dialog):
                output.setPlainText((result.output or "(no output)") + tail)
                dialog.step(3)
                plain = summary + (" That usually means it worked." if result.code == 0 and not result.timed_out else
                                   " A code other than 0 usually means the command reported a problem; read the output.")
                dialog.result(plain, words.GOOD if result.code == 0 and not result.timed_out else words.WARN)
        _job(window, lambda: winpc.run_command(runner, text), finished, "Command Runner")
    run_button.clicked.connect(go)
    line.returnPressed.connect(go)
    dialog.line, dialog.output, dialog.run_button = line, output, run_button
    dialog.add_actions(run_button)
    _show(window, dialog)


# ------------------------------------------------------------------ 5. File Associations
def file_associations(window):
    reg = winpc.default_registry()
    if reg is None:
        window.info("File Associations needs Windows", "File associations only exist on Windows.")
        return
    dialog, box = _dialog(window, "file_associations", "File Associations", "file")
    pick = row(spacing=8)
    kind = QComboBox()
    kind.setEditable(True)
    kind.setAccessibleName("File extension")
    kind.addItems(winpc.COMMON_EXTENSIONS)
    lookup = button("Look up", kind="primary")
    pick.addWidget(kind, 1)
    pick.addWidget(lookup)
    box.addLayout(pick)
    frame, inner = shell.card(spacing=4, margins=(14, 12, 14, 12))
    answer = shell.text("Choose or type a file type, then press Look up.", "toolLead")
    answer.setAccessibleName("File Associations answer")
    source = shell.text("")
    inner.addWidget(answer)
    inner.addWidget(source)
    box.addWidget(frame)
    box.addWidget(shell.text("Windows only lets you change this yourself, so Game Grave opens the right Windows page for "
                             "you. Nothing is changed here."))

    def look():
        try:
            found = winpc.read_association(reg, kind.currentText())
        except ValueError as exc:
            answer.setText(str(exc))
            source.setText("")
            dialog.details.set_lines("")
            dialog.step(0)
            return
        answer.setText(f"{found.ext} opens with: {found.app}")
        source.setText(found.source)
        dialog.details.set_lines(("Starts:  " + found.command) if found.command else "")
        dialog.step(2)

    def settings_page():
        if not QDesktopServices.openUrl(QUrl("ms-settings:defaultapps")):
            window.error("Could not open Windows Settings", "Open Settings, then Apps, then Default apps yourself.")
    lookup.clicked.connect(look)
    kind.lineEdit().returnPressed.connect(look)
    dialog.kind, dialog.answer, dialog.lookup = kind, answer, lookup
    dialog.add_actions(button("Change it in Windows", settings_page,
                              tip="Opens Windows Settings, Apps, Default apps. Game Grave changes nothing."))
    look()
    _show(window, dialog)


# ------------------------------------------------------------------ 6. Junction Manager
def junction_manager(window):
    if _busy(window):
        return
    runner = winpc.Runner()
    dialog, box = _dialog(window, "junction_manager", "Junction Manager", "folder", 660)
    pick = row(spacing=8)
    where = shell.text("No folder chosen yet.", "toolLead")
    choose = button("Choose folder…", kind="primary")
    choose.setAccessibleName("Choose folder")
    pick.addWidget(where, 1)
    pick.addWidget(choose)
    box.addLayout(pick)
    box.addWidget(shell.text("A link makes one folder show up in a second place, for example a game moved to another "
                             "drive. Removing a link deletes only the link, never the folder it points to."))
    listing = QListWidget()
    listing.setAccessibleName("Links found")
    listing.setMinimumHeight(200)
    box.addWidget(listing, 1)
    dialog.details.set_lines(["New links are made with:  mklink /J <link> <target>",
                              "Removing uses the link itself only; the target folder is never opened for deleting.",
                              "Real folders and Never Touch places are refused."])
    state = {"root": ""}
    remove = button("Remove link…", kind="danger")
    remove.setAccessibleName("Remove selected link")
    remove.setEnabled(False)
    create = button("Create junction…")
    create.setAccessibleName("Create junction")
    listing.currentItemChanged.connect(lambda current, _old: remove.setEnabled(current is not None))

    def fill(links, error=""):
        if not isValid(dialog):
            return
        listing.clear()
        for link in links:
            status = "points to" if link.exists else "BROKEN, points to"
            item = QListWidgetItem(f"{Path(link.path).name}   ({link.kind})\n    {status}  {link.target or 'unknown'}")
            item.setToolTip(link.path)
            item.setData(Qt.UserRole, link)
            listing.addItem(item)
        remove.setEnabled(False)
        note = state.pop("note", "")
        dialog.step(3 if note else 1 if links else 0)
        if note and not error:
            dialog.result(note + " " + words.plain_count(len(links), "link") + " here now.", words.GOOD)
        elif error:
            dialog.result(error, words.BAD)
        elif links:
            broken = sum(1 for link in links if not link.exists)
            dialog.result(words.plain_count(len(links), "link") + " found." + (f" {broken} broken (the folder it pointed to is gone)."
                                                           if broken else " Select one to remove it."),
                          words.WARN if broken else words.INFO)
        else:
            dialog.result("No junctions or links found there.", words.INFO)

    def scan(root):
        state["root"] = root
        where.setText(root)
        where.setToolTip(root)
        dialog.result("Looking for links…", words.WORKING)
        _job(window, lambda: winpc.scan_links(root), lambda links, err: fill(links or [], err), "Junction Manager")

    def pick_folder():
        root = QFileDialog.getExistingDirectory(window, "Choose a folder to look in", state["root"] or str(Path.home()))
        if root:
            scan(root)

    def remove_selected():
        item = listing.currentItem()
        if item is None:
            dialog.result("Select a link first.", words.WARN)
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
            dialog.result("Link not removed: " + str(exc), words.BAD)
            return
        text = f"Removed the link {link.path}. " + ("Its target is untouched." if kept else "Its target was not found.")
        winpc.activity("Junction Manager", text, path=link.path, result="Link removed")
        if state["root"]:
            state["note"] = text
            scan(state["root"])
        else:
            dialog.step(3)
            dialog.result(text, words.GOOD)

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
        state["note"] = text
        scan(parent)
    choose.clicked.connect(pick_folder)
    remove.clicked.connect(remove_selected)
    create.clicked.connect(create_one)
    dialog.listing, dialog.fill, dialog.remove_button, dialog.create_button = listing, fill, remove, create
    dialog.scan = scan
    dialog.add_actions(create, remove)
    _show(window, dialog)


def open_startup_tab(window):
    """One place for startup apps: Hardware, Drivers & Startup (it also covers all-users apps, Store apps and sign-in tasks)."""
    window.hardware_tab = "Drivers & Startup"
    window.navigate("Hardware")


HANDLERS = {"windows_cleanup": windows_cleanup, "game_optimizer": game_optimizer, "memory_optimizer": memory_optimizer,
            "startup_manager": open_startup_tab, "command_runner": command_runner, "file_associations": file_associations,
            "junction_manager": junction_manager}
