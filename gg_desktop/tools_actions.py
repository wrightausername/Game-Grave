"""More Tools actions. Each one either hands off to the tab that owns the work or does one real, honest job here.

The seven Windows tools live in `tools_windows.py` (owner-approved: each names what it changes and asks first).
Nothing else in this module deletes, moves or edits an existing file. Reports are written to a new file the owner names, and
the hash checker only reads. Backups and kits go through the existing, verified Save Vault and Resurrection Kit code.
"""
from __future__ import annotations

from datetime import datetime
import threading
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QDialog, QFileDialog, QLabel, QLineEdit

from gg_desktop import tools_data as data
from gg_desktop import tools_system as system
from gg_desktop.widgets import button, column, label, row

KIT_METHODS = {"create": "_create_kit", "restore": "_restore_kit", "rehearse": "_rehearse_kit",
               "missing": "_missing_pieces", "compare": "_compare_kits", "versions": "_kit_versions",
               "transfer": "_transfer_kit"}


def stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def busy(window) -> bool:
    if window.scanning or window.cleaning:
        window.info("Game Grave is busy", "Finish the current operation first.")
        return True
    return False


def run_tile(window, tile):
    """The single entry point for a tile click, whatever its kind."""
    if tile.kind == data.GO:
        window.navigate(tile.target)
    elif tile.kind == data.RUN:
        run_action(window, tile.target)
    else:
        window.info(tile.title + " is not offered", tile.note or data.OFF_REASON)


def run_action(window, key):
    handler = {"save_vault": lambda: window._create_save_backup(),
               "kit_menu": lambda: open_kit_menu(window),
               "game_report": lambda: export_games(window),
               "mod_report": lambda: export_mods(window),
               "system_report": lambda: export_system(window),
               "hash": lambda: choose_hash_file(window),
               "mod_shield": lambda: _open_shield(window),
               "exhume": lambda: _open_extra(window, "open_exhume"),
               "autopsy": lambda: _open_extra(window, "open_autopsy"),
               "black_box": lambda: _open_extra(window, "open_black_box")}.get(key)
    if handler is None:
        from gg_desktop import tools_windows
        handler = (lambda: tools_windows.HANDLERS[key](window)) if key in tools_windows.HANDLERS else None
    if handler:
        handler()


def _open_shield(window):
    from gg_desktop import tools_shield
    return tools_shield.open_shield(window)


def _open_extra(window, name):
    from gg_desktop import tools_extra
    return getattr(tools_extra, name)(window)


def run_quick(window, key):
    if key == "scan":
        if window.scanning or window.cleaning:
            window.info("Game Grave is busy", "Finish the current operation first.")
        else:
            window.start_scan()
    elif key == "size_report":
        export_games(window)
    elif key == "caches":
        window.navigate("Other Storage")
    elif key == "saves":
        window._create_save_backup()
    elif key == "kit":
        open_kit_menu(window)


# ------------------------------------------------------------------ reports
def _ask_save(window, title, name, pattern):
    chosen, _filter = QFileDialog.getSaveFileName(window, title, str(Path.home() / name), pattern)
    return chosen or ""


def _needs_scan(window, noun):
    if window.inventory.scanned_at:
        return False
    window.info("Nothing to report yet", "No scan has finished in this session, so there are no " + noun +
                " to list. Run Scan This PC first. Game Grave does not invent rows.")
    return True


def export_games(window):
    if _needs_scan(window, "games"):
        return None
    if not window.inventory.games:
        window.info("No games found", "The last scan found no game installs, so there is nothing to put in the report.")
        return None
    path = _ask_save(window, "Save the game size report", "game-grave-games.csv", "CSV files (*.csv)")
    if not path:
        return None
    return _write(window, path, lambda: data.write_csv(path, data.GAME_HEADER, data.game_rows(window.inventory.games)),
                  "game", "Sizes are what the scan reported. They are not a promise of space freed.")


def export_mods(window):
    if _needs_scan(window, "mod or game folders"):
        return None
    if not window.inventory.mods:
        window.info("No mod folders found", "The last scan found no mod or game folders, so there is nothing to put in the report.")
        return None
    path = _ask_save(window, "Save the mod report", "game-grave-mods.csv", "CSV files (*.csv)")
    if not path:
        return None
    return _write(window, path, lambda: data.write_csv(path, data.MOD_HEADER, data.mod_rows(window.inventory.mods)),
                  "folder", "Nothing was changed. A listed folder is not a suggestion to remove it.")


def export_system(window):
    path = _ask_save(window, "Save the system report", "game-grave-system-report.txt", "Text files (*.txt)")
    if not path:
        return None
    from gg_desktop import tools_page
    cpu = tools_page.state_of(window).cpu_value
    text = data.system_report_text(inventory=window.inventory, system=system.report_lines(cpu), settings=window.settings,
                                   generated=stamp())
    return _write(window, path, lambda: data.write_text(path, text), "line", "It stays on this PC. Nothing was sent anywhere.")


def _write(window, path, writer, noun, note):
    try:
        count = writer()
    except (OSError, ValueError) as exc:
        window.error("The report was not saved", str(exc))
        return None
    plural = "" if count == 1 else "s"
    window.status.setText(f"Saved a report with {count} {noun}{plural}.")
    window.info("Report saved", f"{count} {noun}{plural} written to:\n{path}\n\n{note}")
    return count


# ------------------------------------------------------------------ resurrection kit menu
class KitMenu(QDialog):
    """Every kit action in one place. Each one opens the existing verified workflow and confirms before it changes anything."""

    def __init__(self, window):
        super().__init__(window)
        self.window_ = window
        self.setWindowTitle("Resurrection Kit")
        self.setModal(True)
        self.setMinimumWidth(420)
        box = column(spacing=8, margins=(16, 14, 16, 14))
        self.setLayout(box)
        box.addWidget(label("Resurrection Kit", "sectionTitle"))
        box.addWidget(label("Kits are built and restored by the existing verified workflow. Nothing is overwritten and "
                            "every step asks you first.", "subtle", wrap=True))
        self.buttons = {}
        for key, title, hint in data.KIT_ACTIONS:
            control = button(title, lambda _=False, k=key: self.pick(k), kind="primary" if key == "create" else "", tip=hint)
            control.setAccessibleName(title)
            self.buttons[key] = control
            box.addWidget(control)
        box.addWidget(button("Close", self.reject))

    def pick(self, key):
        self.accept()
        getattr(self.window_, KIT_METHODS[key])()


def open_kit_menu(window):
    window._tools_kit_menu = KitMenu(window)
    window._tools_kit_menu.exec()


# ------------------------------------------------------------------ hash checker
class HashResult(QDialog):
    """Shows a checksum and compares it with one the owner pastes. A match proves the bytes, not that the file is good."""

    def __init__(self, window, path, size, digest):
        super().__init__(window)
        self.digest = digest
        self.setWindowTitle("Hash Checker")
        self.setMinimumWidth(520)
        box = column(spacing=8, margins=(16, 14, 16, 14))
        self.setLayout(box)
        box.addWidget(label("SHA-256 checksum", "sectionTitle"))
        name = label(Path(path).name, "detailValue", wrap=True)
        name.setTextFormat(Qt.PlainText)
        name.setToolTip(str(path))
        box.addWidget(name)
        from core import human_size
        box.addWidget(label(human_size(size) + " read. Nothing was changed.", "caption"))
        self.value = QLineEdit(digest)
        self.value.setReadOnly(True)
        self.value.setAccessibleName("SHA-256 checksum")
        box.addWidget(self.value)
        box.addWidget(button("Copy checksum", self.copy))
        box.addWidget(label("Compare with a checksum you were given", "caption"))
        self.expected = QLineEdit()
        self.expected.setPlaceholderText("Paste the publisher's SHA-256 here")
        self.expected.setAccessibleName("Expected checksum")
        self.expected.textChanged.connect(self.compare)
        box.addWidget(self.expected)
        self.verdict = QLabel("")
        self.verdict.setWordWrap(True)
        self.verdict.setAccessibleName("Comparison result")
        box.addWidget(self.verdict)
        box.addWidget(button("Close", self.accept))
        self.compare()

    def copy(self):
        QGuiApplication.clipboard().setText(self.digest)

    def compare(self):
        state, message = data.compare_hash(self.digest, self.expected.text())
        color = {"match": "#32d67a", "different": "#ff5f78", "invalid": "#f6be24"}.get(state, "#8fa0b3")
        self.state = state
        self.verdict.setText(message)
        self.verdict.setStyleSheet(f"color:{color};")


def choose_hash_file(window):
    from gg_desktop import tools_page
    state = tools_page.state_of(window)
    if state.hash_name:
        window.info("A check is already running", "Wait for the current checksum or cancel it from Active Tasks.")
        return
    chosen, _filter = QFileDialog.getOpenFileName(window, "Choose a file to check", str(Path.home()))
    if not chosen:
        return
    path = Path(chosen)
    if not path.is_file():
        window.error("Not a file", "Choose a file, not a folder.")
        return
    start_hash(window, path)


def start_hash(window, path):
    from gg_desktop import tools_page
    state = tools_page.state_of(window)
    state.hash_name, state.hash_percent = path.name, 0
    state.hash_cancel = threading.Event()
    cancel = state.hash_cancel
    window.status.setText("Reading " + path.name + " to compute its checksum. The file is not changed.")

    def work(emit):
        last = [-1]

        def progress(done, total):
            percent = int(done * 100 / total) if total else 100
            if percent != last[0]:
                last[0] = percent
                emit(percent, path.name)
        try:
            digest = data.sha256_file(path, cancel.is_set, progress)
            return digest, path.stat().st_size
        except InterruptedError:
            return None
        except Exception as exc:  # unreadable or removed mid-read; report it here so the task row never gets stuck
            return "error", str(exc)

    def moved(percent, _name):
        state.hash_percent = percent

    def done(result):
        state.hash_name, state.hash_percent = "", 0
        if result is None:
            window.status.setText("Hash check canceled.")
            return
        if result[0] == "error":
            window.status.setText("The file could not be read.")
            window.error("The file could not be read", str(result[1]))
            return
        digest, size = result
        window.status.setText("Checksum ready for " + path.name + ".")
        window._tools_hash_dialog = HashResult(window, path, size, digest)
        window._tools_hash_dialog.exec()

    window.job(work, done, error_title="The file could not be read", progress=moved)


def cancel_hash(window):
    from gg_desktop import tools_page
    state = tools_page.state_of(window)
    if state.hash_cancel:
        state.hash_cancel.set()
