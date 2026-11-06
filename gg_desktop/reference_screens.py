"""Connected Chromium Command screens: true data, no fake cleanup claims."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import datetime
from pathlib import Path
import os
import shutil
import subprocess
import sys
import uuid

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QProgressBar, QPushButton, QSizePolicy, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)
from core import (
    human_size, age_text, is_game_neglected, is_protected_path, is_unchanged,
    safe_scan_root, save_settings,
)
from graveyard import build_graveyard
from graveyard_protection import protection_action
from cleanup_actions import recycle_reviewed_entries, recycle_old_files
from recovery import get_records, restore as restore_recycled, check_restore
from screenshot_preview import decode_screenshot_preview
from gg_desktop.backend import refresh_graveyard, unprotect_exact_personal_item, add_never_touch_path
from gg_desktop.models import (
    readable_bytes, reported_game_bytes, unique_launcher_counts,
    graveyard_protection_decision, graveyard_totals,
)
from gg_desktop.widgets import (
    ActionCard, HeroBanner, LandscapeArt, MetricCard, ScrollPage, StorageRing,
    button, column, data_table, label, page_heading, panel, row, section_title,
)


def _table_text(table: QTableWidget, r: int, c: int, value) -> None:
    cell = QTableWidgetItem(str(value))
    cell.setToolTip(str(value))
    table.setItem(r, c, cell)


def _selected_indices(table: QTableWidget) -> list[int]:
    return sorted(set(idx.row() for idx in table.selectionModel().selectedRows()))


def _safe_open_path(target: str) -> bool:
    from core import _has_reparse_component
    path = Path(target)
    if not path.is_dir() or _has_reparse_component(path):
        return False
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def _box_notice(parent, message: str, *, warning=False):
    frame, stack = panel(padding=12)
    label_widget = label(message, "warning" if warning else "subtle", wrap=True)
    stack.addWidget(label_widget)
    parent.content.addWidget(frame)
    return frame


from gg_desktop.reference_library import LibraryScreens
from gg_desktop.recovery_screens import RecoveryScreens
from gg_desktop.storage_screens import StorageScreens
from gg_desktop.reference_overview import OverviewScreens


class ScreenMethods(OverviewScreens, RecoveryScreens, StorageScreens, LibraryScreens):
    """These methods are deliberately UI-only; the existing backend is authoritative."""

    def _new(self, title: str, subtitle: str) -> ScrollPage:
        page = self.page_for(title)
        page_heading(page, title, subtitle)
        if self.inventory.warnings:
            _box_notice(page, "Partial scan: " + " ".join(self.inventory.warnings), warning=True)
        return page

    def _not_scanned(self, page):
        if self.inventory.scanned_at:
            return False
        frame, stack = panel(padding=18)
        stack.addWidget(label("YOUR STORAGE. YOUR DECISION.", "eyebrow"))
        stack.addWidget(label("Run Scan PC to see what's actually installed. "
                              "Game Grave does not invent activity or disk usage.", "subtle", wrap=True))
        stack.addWidget(button("Scan PC now", self.start_scan, kind="primary"))
        page.content.addWidget(frame)
        return True

    def ready_room_page(self):
        page = self._new("Ready Room", "Prepare your library and storage for your next game.")
        frame, contents = panel()
        contents.addWidget(section_title("Get ready to play"))
        contents.addWidget(label("Scan your library, check reported installation sizes, or open the existing Make Room planner.", "subtle", wrap=True))
        contents.addWidget(button("Scan PC", self.start_scan, kind="primary"))
        contents.addWidget(button("Browse Games", lambda: self.navigate("Games")))
        contents.addWidget(button("Open classic Make Room tools", self._launch_classic_tools))
        page.content.addWidget(frame)
        page.content.addStretch()



    def assistant_page(self):
        page = self._new("AI Assistant", "Local evidence and explanations for your library.")
        frame, contents = panel()
        contents.addWidget(section_title("Understand your scan"))
        contents.addWidget(label("A conversational AI service is not connected in this preview. You can inspect the local evidence behind each finding without sending your files anywhere.", "subtle", wrap=True))
        contents.addWidget(button("Explain game relationships", lambda: self.navigate("Game DNA")))
        contents.addWidget(button("Inspect mod source evidence", lambda: self.navigate("Mods")))
        contents.addWidget(button("Why is this file protected?", lambda: self.navigate("Graveyard")))
        page.content.addWidget(frame)
        page.content.addStretch()


    def _go_launcher(self, launcher):
        self._pending_launcher_filter = launcher
        self.navigate("Games")

    def _steam_uninstall(self, game):
        if ("steam_uninstall" not in game.capabilities or game.launcher != "Steam"
                or not game.app_id or not game.app_id.isdecimal()):
            return
        if not self.confirm("Open Steam uninstall?", f"Open Steam's own uninstall dialog for\n\n{game.name}?\n\n"
                            "Game Grave will not remove the installation directly.", destructive=True):
            return
        if sys.platform != "win32":
            self.error("Windows only", "Steam uninstall shortcut requires Windows.")
            return
        try:
            os.startfile("steam://uninstall/" + game.app_id)
        except OSError as exc:
            self.error("Steam unavailable", str(exc))

    def _open_folder(self, path: str):
        if not _safe_open_path(path):
            self.error("Folder unavailable", "The directory is missing, redirected, or refused by Windows.")

    def _go_grave_item(self, key):
        self._pending_grave_key = key
        self.navigate("Graveyard")





    def _unprotect_grave(self, entry):
        if self.scanning or self.cleaning:
            self.info("Game Grave is busy", "Finish the current operation before changing protection.")
            return
        action, reason = protection_action(entry.path, list(self.settings.get("never_touch", [])))
        if action != "Unprotect":
            self.error("Protection stays on", reason)
            return
        if not self.confirm("Remove your protection?",
                            "Remove only the exact Never Touch rule for:\n" + entry.path +
                            "\n\nThis does NOT delete anything. Game Grave will run "
                            "all safety checks again before a separate Recycle Bin approval."):
            return
        try:
            self.settings = unprotect_exact_personal_item(self.settings, entry.path)
            refresh_graveyard(self.inventory, self.settings)
            self.status.setText("Exact personal rule removed. No files were moved.")
            self.navigate("Graveyard")
        except (OSError, ValueError) as exc:
            self.error("Protection not changed", str(exc))

    def _manage_parent_rule(self, entry):
        for rule in self.settings.get("never_touch", []):
            if (isinstance(rule, str) and
                    is_protected_path(Path(entry.path), [rule]) and
                    os.path.normcase(os.path.abspath(rule)) !=
                    os.path.normcase(os.path.abspath(entry.path))):
                self._focus_never_touch_rule = rule
                break
        self.navigate("Settings")


    def _delete_grave_selected(self):
        selected = self._selected_grave_entries()
        if not selected:
            self.info("Nothing selected", "Select ordinary reviewable files. "
                      "Screenshots must each be previewed individually.")
            return
        if any((not e.can_recycle or e.category == "Old game screenshot") for e in selected):
            self.error("Protected items in selection",
                       "Protected findings and screenshots cannot be batch deleted. "
                       "Select an item to unprotect or individually preview it.")
            return
        self._approve_recycle(selected)

    def _approve_recycle(self, selected, *, image_approved=False):
        if self.cleaning or self.scanning:
            self.info("Game Grave is busy", "Finish the scan or cleanup before choosing another action.")
            return
        if not selected or len(selected) > 200:
            self.error("Review too large", "Choose between 1 and 200 files at a time.")
            return
        if any(not e.can_recycle for e in selected):
            self.error("Not approved", "One or more files remain protected.")
            return
        if any(e.category == "Old game screenshot" for e in selected):
            if (len(selected) != 1 or not image_approved or
                    not selected[0].screenshot_reviewed):
                self.error("Preview required", "You must preview this exact image first.")
                return
        names = "\n".join(" • " + e.name[:100] for e in selected[:12])
        if len(selected) > 12:
            names += f"\n • ...and {len(selected) - 12} additional explicitly selected files"
        summary = ("Move these " + str(len(selected)) +
                   " reviewed file(s) to Windows Recycle Bin?\n\n" + names +
                   "\n\nNo permanent deletion. This does NOT immediately free disk space. "
                   "Windows restoration must be verified for each file first. "
                   "If a file changed, it will be skipped.")
        if not self.confirm("Move reviewed files to Recycle Bin?", summary, destructive=True):
            return
        self.cleaning = True
        rules = tuple(self.settings.get("never_touch", []))
        reviewed = tuple(selected)
        session = "crimson-" + uuid.uuid4().hex[:10]
        self.status.setText("Windows is validating Recycle Bin recovery for each approved file…")
        def success(report):
            self.cleaning = False
            self.status.setText(
                f"{report['completed']} item(s) moved to Recycle Bin; "
                f"{len(report['skipped'])} skipped. This is NOT reclaimed disk space.")
            if report["completed"]:
                self._remove_missing_inventory()
                refresh_graveyard(self.inventory, self.settings)
                self.navigate("Graveyard")
            self.info("Reviewed cleanup finished",
                      f"{report['completed']} moved to Recycle Bin, {len(report['skipped'])} not moved. "
                      f"{report['recovery_warnings']} Undo log warnings. "
                      "\n\nRecycle Bin may still occupy space."
                      + ("\n\n" + "\n".join(report["skipped"][:6]) if report["skipped"] else ""))
        self.job(lambda _emitter: recycle_reviewed_entries(reviewed, rules, session),
                 success, error_title="Recycling failed")

    def _remove_missing_inventory(self):
        # Recycle operation has completed. Filter stale entries; never infer
        # that an item disappeared from a previous partial scan.
        self.inventory.files = [f for f in self.inventory.files if is_unchanged(f)]
        self.inventory.recordings = [f for f in self.inventory.recordings if is_unchanged(f)]
        self.inventory.screenshots = [f for f in self.inventory.screenshots if is_unchanged(f)]

    def _preview_capture(self, record):
        e = next((e for e in self.inventory.graveyard if e.old_file == record
                  and e.category == "Old game screenshot"), None)
        if e is not None:
            self._preview_grave_image(e)
        else:
            self.info("Screenshot not eligible",
                      "This image is not in the reviewed old-screenshot inventory. "
                      "Nothing was loaded or deleted.")

    def _preview_grave_image(self, entry):
        if entry.old_file is None or not is_unchanged(entry.old_file):
            self.error("Screenshot changed", "This image differs from the scanned file. Scan again.")
            return
        record = entry.old_file
        def ready(image):
            qimage = QImage(image.tobytes(), image.width, image.height,
                            image.width * 3, QImage.Format_RGB888).copy()
            dialog = QDialog(self)
            dialog.setWindowTitle("Game Grave  •  Preview before removing an image")
            dialog.resize(920, 710)
            layout = column(spacing=12, margins=(18, 18, 18, 18))
            dialog.setLayout(layout)
            layout.addWidget(label(entry.name, "sectionTitle", wrap=True))
            picture = QLabel()
            picture.setAlignment(Qt.AlignCenter)
            picture.setPixmap(QPixmap.fromImage(qimage).scaled(
                870, 535, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            layout.addWidget(picture, 1)
            layout.addWidget(label(
                "This image was decoded locally only after your request. "
                "A screenshot may be a personal memory. Keep it unless you're certain.",
                "subtle", wrap=True))
            actions = QWidget()
            bar = row()
            actions.setLayout(bar)
            keep = button("Keep screenshot", dialog.reject)
            bar.addWidget(keep)
            discard = button("Review moving THIS image to Recycle Bin…", dialog.accept,
                             kind="danger")
            if is_protected_path(Path(entry.path), self.settings.get("never_touch", [])):
                discard.setEnabled(False)
                discard.setToolTip("Protected. Remove your own rule first if permitted.")
            bar.addWidget(discard)
            layout.addWidget(actions)
            keep.setDefault(True)
            if dialog.exec() == QDialog.Accepted:
                if not is_unchanged(record):
                    self.error("Screenshot changed", "Image was modified after preview. Scan again.")
                    return
                self._approve_recycle(
                    [replace(entry, can_recycle=True, screenshot_reviewed=True)],
                    image_approved=True)
        self.status.setText("Decoding only the screenshot you selected…")
        self.job(lambda _emitter: decode_screenshot_preview(record),
                 ready, error_title="Could not safely preview image")



    def _choose_scan_folder(self):
        chosen = QFileDialog.getExistingDirectory(self, "Select ordinary Old Files scan folder",
                                str(self.settings.get("scan_folder", str(Path.home()))))
        if not chosen:
            return
        target = Path(chosen)
        if not safe_scan_root(target) or is_protected_path(target, []):
            self.error("Folder not allowed",
                       "Choose a normal local documents/download folder, not a drive root, "
                       "game install, mod manager or protected system directory.")
            return
        self.settings["scan_folder"] = str(target)
        try:
            save_settings(self.settings)
        except OSError as exc:
            self.error("Cannot save folder preference", str(exc))
            return
        self.status.setText("Scan folder saved. Scan PC before reviewing files.")
        self.navigate("Settings")

    def settings_page(self):
        page = self._new("Settings", "Appearance, scan folders, Never Touch rules and local-only privacy controls.")
        p, contents = panel()
        contents.addWidget(section_title("Scan preferences"))
        contents.addWidget(label(
            "Old Files: " + str(self.settings.get("scan_folder", "")),
            "subtle", wrap=True))
        contents.addWidget(button("Choose Old Files folder…", self._choose_scan_folder))
        contents.addWidget(button("Game Libraries & Scan Locations…", self.open_scan_locations))
        artwork_downloads = QCheckBox("Download missing Steam artwork automatically")
        artwork_downloads.setChecked(self.settings.get("steam_artwork_downloads", True))
        artwork_downloads.setToolTip("Uses public Steam cover images and keeps a local cache for offline use.")
        def set_artwork_downloads(enabled):
            updated = dict(self.settings, steam_artwork_downloads=enabled)
            try:
                save_settings(updated)
            except (OSError, ValueError) as exc:
                self.error("Artwork preference not saved", str(exc))
                return
            self.settings = updated
            self.artwork.allow_downloads = enabled
            self.artwork.retry()
        artwork_downloads.toggled.connect(set_artwork_downloads)
        contents.addWidget(artwork_downloads)
        contents.addWidget(label(
            "Automatic cleanup remains OFF. Every actual Recycle Bin move "
            "requires separate approval.", "warning", wrap=True))
        page.content.addWidget(p)

        p, stack = panel()
        stack.addWidget(section_title("Never Touch", "User-controlled rules"))
        stack.addWidget(label(
            "Exact personal rules can be unprotected directly in Graveyard. "
            "Removing a PARENT folder rule affects all its children, so it is only "
            "allowed here with a separate warning. Built-in safety cannot be disabled.",
            "subtle", wrap=True))
        self.never_list = QListWidget()
        self.never_list.setMinimumHeight(135)
        rules = list(self.settings.get("never_touch", []))
        self.never_list.addItems([str(x) for x in rules])
        focus_rule = getattr(self, "_focus_never_touch_rule", None)
        if focus_rule and focus_rule in rules:
            self.never_list.setCurrentRow(rules.index(focus_rule))
        stack.addWidget(self.never_list)
        buttons = QWidget()
        br = row()
        buttons.setLayout(br)
        def add_rule():
            chosen = QFileDialog.getExistingDirectory(self, "Protect an ordinary personal folder")
            if not chosen:
                return
            try:
                self.settings = add_never_touch_path(self.settings, chosen)
                refresh_graveyard(self.inventory, self.settings)
                self.navigate("Settings")
            except (OSError, ValueError) as exc:
                self.error("Cannot add rule", str(exc))
        def remove_rule():
            item = self.never_list.currentItem()
            if not item:
                self.info("Choose a rule", "Select your personal Never Touch rule to remove.")
                return
            rule = item.text()
            if not self.confirm("Remove protected folder rule?",
                    "This removes a personal Never Touch rule for:\n" + rule +
                    "\n\nEvery child file beneath this folder may become reviewable "
                    "if it otherwise meets safety rules. NOTHING is deleted now. "
                    "Built-in protection remains active.", destructive=True):
                return
            try:
                updated = list(self.settings.get("never_touch", []))
                updated.remove(rule)
                new_settings = dict(self.settings)
                new_settings["never_touch"] = updated
                save_settings(new_settings)
                self.settings = new_settings
                refresh_graveyard(self.inventory, self.settings)
                self.navigate("Settings")
            except (OSError, ValueError) as exc:
                self.error("Could not remove rule", str(exc))
        br.addWidget(button("Protect a folder", add_rule))
        br.addWidget(button("Remove selected personal rule…", remove_rule, kind="danger"))
        stack.addWidget(buttons)
        page.content.addWidget(p)

        p, stack = panel()
        stack.addWidget(section_title("In-game screenshots", "Optional locations"))
        stack.addWidget(label(
            "Steam screenshot folders and common game capture locations are scanned by metadata. "
            "Your general Pictures directory isn't automatically browsed. "
            "Image contents load only when you request an individual preview.",
            "subtle", wrap=True))
        self.shot_roots = QListWidget()
        self.shot_roots.addItems(list(self.settings.get("screenshot_roots", [])))
        self.shot_roots.setMinimumHeight(80)
        stack.addWidget(self.shot_roots)
        buttons = QWidget()
        br = row()
        buttons.setLayout(br)
        def modify_shots(remove=False):
            if remove:
                current = self.shot_roots.currentItem()
                if current is None:
                    return
                roots = list(self.settings.get("screenshot_roots", []))
                if current.text() in roots:
                    roots.remove(current.text())
            else:
                folder = QFileDialog.getExistingDirectory(self, "Select personal game capture folder")
                if not folder:
                    return
                if not safe_scan_root(Path(folder)) or is_protected_path(Path(folder), []):
                    self.error("Not allowed", "Choose an ordinary screenshot folder.")
                    return
                roots = list(self.settings.get("screenshot_roots", []))
                if folder in roots:
                    return
                if len(roots) >= 30:
                    self.error("Too many folders", "Maximum 30 custom screenshot folders.")
                    return
                roots.append(folder)
            new = dict(self.settings)
            new["screenshot_roots"] = roots
            try:
                save_settings(new)
                self.settings = new
                self.navigate("Settings")
            except OSError as exc:
                self.error("Could not save screenshot folder", str(exc))
        br.addWidget(button("Add game capture folder", lambda: modify_shots()))
        br.addWidget(button("Remove selected", lambda: modify_shots(True)))
        stack.addWidget(buttons)
        page.content.addWidget(p)

        p, stack = panel()
        stack.addWidget(section_title("Appearance and privacy"))
        stack.addWidget(label(
            "Crimson Command is a local UI preview. No account, telemetry, "
            "external images or automatic server polling. Older appearance themes "
            "remain available in the original Game Grave interface.",
            "subtle", wrap=True))
        stack.addWidget(button("Open classic appearance and advanced settings",
                               self._launch_classic_tools))
        page.content.addWidget(p)

    def tools_page(self):
        page = self._new("More Tools", "All existing advanced Game Grave capabilities remain available.")
        p, stack = panel()
        stack.addWidget(label("YOUR SAVES AND RESURRECTION KITS REMAIN PROTECTED", "eyebrow"))
        stack.addWidget(label(
            "The classic Game Grave interface still contains Save Vault, "
            "Resurrection Kits, Living Kits, Time Machine, PC transfer, "
            "Make Room, Activity, schedules and advanced options. "
            "This visual preview does not replace the trusted workflow yet.",
            "subtle", wrap=True))
        actions = QWidget()
        buttons = QGridLayout(actions)
        buttons.setContentsMargins(0, 5, 0, 4)
        buttons.setSpacing(9)
        links = [
            ("Save Vault: back up a selected folder", self._create_save_backup),
            ("Create verified Resurrection Kit", self._create_kit),
            ("Inspect and restore Kit to NEW folder", self._restore_kit),
            ("Rehearse Kit recovery in isolation", self._rehearse_kit),
            ("Check Kit missing pieces", self._missing_pieces),
            ("Compare two Kit snapshots", self._compare_kits),
            ("Prepare portable PC-to-PC transfer", self._transfer_kit),
            ("Browse Time Machine snapshots", self._kit_versions),
        ]
        for i, (caption, callback) in enumerate(links):
            buttons.addWidget(button(caption, callback,
                                     kind="primary" if i == 1 else ""),
                              i // 2, i % 2)
        stack.addWidget(actions)
        stack.addWidget(button("Open classic Mod Organizer, advanced backup and update tools",
                               self._launch_classic_tools))
        page.content.addWidget(p)
        p, stack = panel()
        stack.addWidget(section_title("What is safe to do here?"))
        for detail in (
            "Read-only scans and evidence-backed game/mod discovery",
            "Inspect and unprotect only your exact personal Never Touch items",
            "Review individual screenshots locally before a separate approval",
            "Move ordinary reviewed files to Windows Recycle Bin after verified safety check",
            "View and request restoration from a unique Windows recovery entry",
        ):
            stack.addWidget(label("✓  " + detail, "subtle", wrap=True))
        page.content.addWidget(p)
        _box_notice(page, "This Qt presentation is a preview, not Game Grave 1.0. "
                    "Native Windows acceptance, full advanced UI parity and "
                    "third-party Qt commercial redistribution review are pending.",
                    warning=True)

    def _launch_classic_tools(self):
        entry = Path(__file__).resolve().parent.parent / "launcher.py"
        if not entry.is_file():
            self.error("Classic tools unavailable in this preview",
                       "Source-based classic tools cannot be opened from this isolated package. "
                       "Use the existing separate Game Grave installation for advanced features.")
            return
        try:
            subprocess.Popen([sys.executable, str(entry)],
                             cwd=str(entry.parent), close_fds=True)
            self.status.setText("Opened the existing classic Game Grave tools.")
        except OSError as exc:
            self.error("Unable to start classic tools", str(exc))

    def _kit_manifest_picker(self, title="Choose a verified Resurrection Kit manifest"):
        chosen, _ = QFileDialog.getOpenFileName(
            self, title, "", "Game Grave Kits (*.ggkit.json);;JSON (*.json)")
        return Path(chosen) if chosen else None

    def _start_safe_backup_task(self, name, fn, *, target: str):
        if self.cleaning or self.scanning:
            self.info("Operation busy", "Finish the current scan or backup first.")
            return
        self.cleaning = True
        self.status.setText(name + "… Existing game, mod and save files stay untouched.")
        def finish(report):
            self.cleaning = False
            self.status.setText(name + " complete. Original files untouched.")
            # Reports contain on-device user file names; never upload any result.
            lines = [f"{key}: {val}" for key, val in report.items()
                     if isinstance(val, (int, float, bool, str))]
            self.info(name + " completed",
                      "\n".join(lines[:14])[:1800] +
                      "\n\nYour existing game/mod/save files were not modified.")
        self.job(lambda _progress: fn(), finish, error_title=name + " failed")

    def _create_save_backup(self):
        from save_vault import create_backup
        if self.scanning or self.cleaning:
            self.info("Game Grave is busy", "Finish the current operation first.")
            return
        source = QFileDialog.getExistingDirectory(self,
            "Choose exact save / game profile folder to preserve")
        if not source:
            return
        output, _ = QFileDialog.getSaveFileName(
            self, "Create a NEW verified Save Vault ZIP",
            str(Path(source).parent / (Path(source).name + "_SaveVault.zip")),
            "ZIP archives (*.zip)")
        if not output:
            return
        if not output.casefold().endswith(".zip"):
            output += ".zip"
        if not self.confirm("Back up this selected save or profile folder?",
            "Source: " + source + "\n\nNew ZIP: " + output +
            "\n\nOnly this one folder is copied. The destination must not exist. "
            "Game Grave will never delete or overwrite source files. "
            "Close the game first for a consistent snapshot."):
            return
        self._start_safe_backup_task(
            "Save Vault backup", lambda: create_backup(Path(source), Path(output)),
            target=output)

    def _create_kit(self):
        from resurrection_v2 import create_complete_kit
        if self.scanning or self.cleaning:
            self.info("Game Grave is busy", "Finish the current operation first.")
            return
        game, okay = QInputDialog.getText(
            self, "Preserve a gaming setup", "Game title (for the kit manifest):")
        if not okay or not game.strip():
            return
        save = QFileDialog.getExistingDirectory(
            self, "Choose exact Saves or Profile folder for the kit")
        if not save:
            return
        sources = {"Saves": Path(save)}
        if self.confirm("Include your mod setup?",
                        "Do you want to preserve one additional Mods folder? "
                        "The kit will only contain folders you explicitly choose."):
            mod = QFileDialog.getExistingDirectory(
                self, "Choose your exact mod or mod-manager profile folder")
            if not mod:
                return
            sources["Mods"] = Path(mod)
        output, _ = QFileDialog.getSaveFileName(
            self, "Save a NEW Resurrection Kit ZIP",
            str(Path(save).parent / (game.strip().replace("/", "_") + "_Resurrection.zip")),
            "ZIP archives (*.zip)")
        if not output:
            return
        if not output.casefold().endswith(".zip"):
            output += ".zip"
        folders = "\n".join(f"• {role}: {path}" for role, path in sources.items())
        if not self.confirm("Create verified Resurrection Kit?",
            f"Game: {game.strip()}\n\n" + folders + "\n\nZIP: " + output +
            "\n\nThis archives ONLY the selected folders. It does not include "
            "game installation binaries or automatically activate mods. "
            "Existing files are untouched. Continue?"):
            return
        self._start_safe_backup_task(
            "Verified Resurrection Kit",
            lambda: create_complete_kit(game.strip(), sources, Path(output)),
            target=output)

    def _restore_kit(self):
        from resurrection_v2 import inspect_restore, restore_kit
        if self.scanning or self.cleaning:
            self.info("Game Grave is busy", "Finish the current operation first.")
            return
        manifest = self._kit_manifest_picker("Inspect a Resurrection Kit before safe restore")
        if manifest is None:
            return
        destination = QFileDialog.getExistingDirectory(
            self, "Choose parent folder for a NEW restored setup (existing files are never overwritten)")
        if not destination:
            return
        self.status.setText("Verifying kit archive digest and safe NEW restore destination…")
        def ready(plan):
            target = str(plan.get("target", "new unique restore folder"))
            message = ("This will restore the verified kit into a BRAND-NEW folder:\n" +
                       target + "\n\nExisting game, save and mod files are not overwritten. "
                       "No mod manager is automatically reconfigured or activated. "
                       "The restore is separate from game installation. Continue?")
            if not self.confirm("Approve restoring this checked kit?", message):
                self.status.setText("Restore canceled. No files changed.")
                return
            self._start_safe_backup_task("Staged Resurrection recovery",
                lambda: restore_kit(manifest, Path(destination), approved=True),
                target=target)
        self.job(lambda _progress: inspect_restore(manifest, Path(destination)),
                 ready, error_title="Kit cannot be safely restored")

    def _rehearse_kit(self):
        from resurrection_lab import rehearse_kit
        if self.scanning or self.cleaning:
            self.info("Game Grave is busy", "Finish the current operation first.")
            return
        manifest = self._kit_manifest_picker("Choose kit to rehearse safely")
        if manifest is None:
            return
        dest = QFileDialog.getExistingDirectory(
            self, "Choose ordinary folder for isolated temporary rehearsal")
        if not dest:
            return
        if not self.confirm("Rehearse without touching active game files?",
            "Kit: " + str(manifest) + "\n\nTemporary rehearsal location: " + dest +
            "\n\nGame Grave creates and deletes ONLY its own disposable rehearsal "
            "files, then compares extracted byte hashes. "
            "No live saves, profiles or game installs are changed."):
            return
        self._start_safe_backup_task("Isolated Resurrection rehearsal",
            lambda: rehearse_kit(manifest, Path(dest), record=False), target=dest)

    def _missing_pieces(self):
        from resurrection_lab import missing_pieces
        manifest = self._kit_manifest_picker("Check the kit's missing dependencies")
        if manifest is None:
            return
        self.status.setText("Inspecting verified kit manifest and dependencies…")
        def present(report):
            import json
            # Display-only. Avoid hidden side effects and keep output bounded.
            self.info("Missing Pieces (diagnostic, not proof of completeness)",
                json.dumps(report, indent=2, ensure_ascii=False)[:2200] +
                "\n\nEven a verified ZIP may not represent a complete working game setup.")
        self.job(lambda _progress: missing_pieces(manifest), present,
                 error_title="Kit dependency check failed")

    def _compare_kits(self):
        from resurrection_lab import compare_kits
        older = self._kit_manifest_picker("Choose the older kit manifest")
        if older is None:
            return
        newer = self._kit_manifest_picker("Choose the newer kit manifest")
        if newer is None:
            return
        self.status.setText("Comparing kit manifests and verified archive content…")
        def present(report):
            import json
            self.info("Time Machine: verified kit comparison",
                      json.dumps(report, indent=2, ensure_ascii=False)[:2800] +
                      "\n\nNo game files were changed.")
        self.job(lambda _progress: compare_kits(older, newer), present,
                 error_title="Kit comparison failed")

    def _kit_versions(self):
        from resurrection_lab import list_snapshots
        folder = QFileDialog.getExistingDirectory(self, "Choose folder containing your saved kit versions")
        if not folder:
            return
        def present(rows):
            if not rows:
                self.info("Time Machine", "No verified Kit manifests found in this folder.")
            else:
                lines = []
                for rec in rows[:25]:
                    lines.append(str(rec.get("game", "Unknown game")) +
                                 "  •  " + str(rec.get("manifest", "Manifest")) +
                                 "  •  " + str(rec.get("modified", "")))
                self.info("Verified kit snapshots (newest first)",
                          "\n\n".join(lines)[:2600] +
                          "\n\nSelecting a snapshot never performs a live rollback.")
        self.job(lambda _progress: list_snapshots(Path(folder)), present,
                 error_title="Cannot list kit versions")

    def _transfer_kit(self):
        from resurrection_lab import prepare_pc_transfer
        if self.scanning or self.cleaning:
            self.info("Game Grave is busy", "Finish the current operation first.")
            return
        manifest = self._kit_manifest_picker("Choose kit to prepare for another PC")
        if manifest is None:
            return
        dest = QFileDialog.getExistingDirectory(self,
                    "Choose an EMPTY destination parent for a new portable transfer folder")
        if not dest:
            return
        if not self.confirm("Prepare a new portable PC-to-PC kit folder?",
            f"Kit: {manifest}\n\nTransfer parent: {dest}\n\n"
            "A separate new folder with verified ZIP and manifest will be created. "
            "Nothing is copied to a cloud service or sent over a network. "
            "Game binaries and licensed storefront installs are NOT included."):
            return
        self._start_safe_backup_task("Portable Kit transfer",
            lambda: prepare_pc_transfer(manifest, Path(dest), approved=True),
            target=dest)
