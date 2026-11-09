"""Mod Shield window (More Tools > Utilities). Reads mod folders and lists files worth a look. Changes nothing.

The checks live in `mod_shield` (tested without Qt). This module is only the dialog. Every action here reads, copies a
fingerprint, opens a folder or a web page the owner clicks, or asks Microsoft Defender to report without acting.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QFileDialog, QListWidget, QListWidgetItem
from shiboken6 import isValid

from core import human_size
from gg_desktop import mod_shield as ms
from gg_desktop import winpc
from gg_desktop.tools_windows import _busy, _close_row, _dialog, _job, _text
from gg_desktop.widgets import button, row

INTRO = ("Mod Shield looks through mod folders for files that do not usually belong there: programs, scripts, "
         "disguised names and code libraries outside a mod loader. It only reads files. Nothing is moved, changed or "
         "deleted, and a listed file is a reason to look, not proof of anything.")
NOT_HASHED = "Not computed (the file is over 256 MB, or it is an expected plugin file)."


def open_shield(window):
    if _busy(window):
        return None
    dialog, box = _dialog(window, "Mod Shield", INTRO, width=640)
    dialog.window_ = window
    dialog.report = None
    dialog.roots = []
    dialog.defender_exe = ms.find_defender()
    dialog.scan_roots = ms.mod_roots(window.inventory)

    sources = row(spacing=8)
    count = len(dialog.scan_roots)
    dialog.scan_button = button(f"Check mod folders from the last scan ({count:,})", kind="primary",
                                tip="The mod and game-content folders the last scan recorded")
    dialog.scan_button.setEnabled(bool(count))
    dialog.pick_button = button("Check a folder…", tip="Choose any folder to check")
    sources.addWidget(dialog.scan_button)
    sources.addWidget(dialog.pick_button)
    sources.addStretch()
    box.addLayout(sources)
    if not count:
        box.addWidget(_text("No scan has recorded mod folders yet. Run Scan This PC, or choose a folder.", "caption"))

    dialog.summary = _text("", "detailValue")
    dialog.summary.setAccessibleName("Mod Shield summary")
    box.addWidget(dialog.summary)
    dialog.listing = QListWidget()
    dialog.listing.setAccessibleName("Files worth a look")
    dialog.listing.setMinimumHeight(180)
    dialog.listing.setVisible(False)
    box.addWidget(dialog.listing)
    dialog.detail = _text("", "caption")
    dialog.detail.setAccessibleName("Selected file details")
    box.addWidget(dialog.detail)

    actions = row(spacing=8)
    dialog.show_button = button("Show in folder", tip="Open the folder that holds this file")
    dialog.copy_button = button("Copy fingerprint", tip="Copy the SHA-256 fingerprint")
    dialog.lookup_button = button("Look up on VirusTotal", tip="Opens VirusTotal with the fingerprint only. "
                                                                "The file is never uploaded.")
    for control in (dialog.show_button, dialog.copy_button, dialog.lookup_button):
        control.setEnabled(False)
        actions.addWidget(control)
    actions.addStretch()
    box.addLayout(actions)

    dialog.defender_button = button("Scan with Microsoft Defender…",
                                    tip="Defender reports what it finds and takes no action")
    dialog.defender_button.setEnabled(False)
    dialog.security_button = button("Open Windows Security", tip="Remove or quarantine threats in Windows Security")
    dialog.security_button.setVisible(False)
    dialog.defender_note = _text("" if dialog.defender_exe else
                                 "Microsoft Defender's command line tool was not found on this PC, so only the file "
                                 "checks are available.", "caption")
    box.addWidget(dialog.defender_note)

    dialog.scan_button.clicked.connect(lambda: _check(dialog, list(dialog.scan_roots)))
    dialog.pick_button.clicked.connect(lambda: _pick(dialog))
    dialog.listing.currentRowChanged.connect(lambda index: _select(dialog, index))
    dialog.show_button.clicked.connect(lambda: _show(dialog))
    dialog.copy_button.clicked.connect(lambda: _copy(dialog))
    dialog.lookup_button.clicked.connect(lambda: _lookup(dialog))
    dialog.defender_button.clicked.connect(lambda: _defender(dialog))
    dialog.security_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("windowsdefender:")))
    _close_row(dialog, box, dialog.defender_button, dialog.security_button)
    window._tools_dialog = dialog
    dialog.exec()
    return dialog


def _pick(dialog):
    chosen = QFileDialog.getExistingDirectory(dialog, "Choose a folder for Mod Shield to check", str(Path.home()))
    if chosen:
        _check(dialog, [chosen])


def _set_busy(dialog, busy):
    dialog.scan_button.setEnabled(not busy and bool(dialog.scan_roots))
    dialog.pick_button.setEnabled(not busy)
    dialog.defender_button.setEnabled(not busy and bool(dialog.defender_exe) and bool(dialog.roots))


def _check(dialog, roots):
    window = dialog.window_
    if not roots:
        return
    dialog.roots = [str(r) for r in ms.unique_roots(roots)]
    _set_busy(dialog, True)
    dialog.result_line.setText("Checking. Files are only read; nothing is changed.")
    window.status.setText("Mod Shield is reading mod folders. Nothing is being changed.")

    def finished(report, error):
        window.status.setText("Ready.")
        if not isValid(dialog):
            return
        _set_busy(dialog, False)
        if error:
            dialog.result_line.setText("Mod Shield could not finish: " + error)
            return
        _show_report(dialog, report)
        winpc.activity("Mod Shield", report.summary())
    _job(window, lambda: ms.scan(dialog.roots), finished, "Mod Shield")


def _show_report(dialog, report):
    dialog.report = report
    dialog.summary.setText(report.summary())
    dialog.listing.clear()
    for finding in report.findings:
        item = QListWidgetItem(f"{finding.level}  ·  {finding.name}  ·  {finding.kind}")
        item.setToolTip(finding.path)
        dialog.listing.addItem(item)
    dialog.listing.setVisible(bool(report.findings))
    dialog.detail.setText("" if report.findings else "Nothing stood out in these folders. That is what these checks "
                                                      "found, not a guarantee about every file.")
    dialog.result_line.setText("")
    if report.findings:
        dialog.listing.setCurrentRow(0)
    else:
        _select(dialog, -1)


def _current(dialog):
    report, index = dialog.report, dialog.listing.currentRow()
    if report is None or not 0 <= index < len(report.findings):
        return None
    return report.findings[index]


def _select(dialog, _index):
    finding = _current(dialog)
    dialog.show_button.setEnabled(finding is not None)
    dialog.copy_button.setEnabled(bool(finding and finding.sha256))
    dialog.lookup_button.setEnabled(bool(finding and finding.sha256))
    if finding is None:
        return
    dialog.detail.setText(f"{finding.path}\n{human_size(finding.size)}. {finding.reason}\n"
                          f"SHA-256: {finding.sha256 or NOT_HASHED}")


def _show(dialog):
    finding = _current(dialog)
    if finding:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(finding.path).parent)))


def _copy(dialog):
    finding = _current(dialog)
    if finding and finding.sha256:
        QGuiApplication.clipboard().setText(finding.sha256)
        dialog.result_line.setText("Fingerprint copied.")


def _lookup(dialog):
    finding = _current(dialog)
    if finding and finding.sha256:
        QDesktopServices.openUrl(QUrl(ms.virustotal_url(finding.sha256)))
        dialog.result_line.setText("Opened VirusTotal with the fingerprint only. The file was not uploaded.")


def _defender(dialog):
    window = dialog.window_
    if not (dialog.defender_exe and dialog.roots):
        return
    message = ("Ask Microsoft Defender to scan these folders?\n\n" + "\n".join(dialog.roots) +
               "\n\nDefender runs with remediation turned off: it reports what it finds and does not quarantine, "
               "change or delete anything. A large mod folder can take several minutes.")
    if not window.confirm("Scan with Microsoft Defender", message):
        return
    _set_busy(dialog, True)
    dialog.result_line.setText("Microsoft Defender is scanning. Nothing is being changed.")
    exe, roots = dialog.defender_exe, list(dialog.roots)

    def work():
        runner = winpc.Runner()
        return [ms.defender_scan(runner, exe, folder) for folder in roots]

    def finished(results, error):
        if not isValid(dialog):
            return
        _set_busy(dialog, False)
        if error:
            dialog.result_line.setText("Microsoft Defender could not run: " + error)
            return
        lines = [r.line() for r in results]
        threats = any(r.status == "threats" for r in results)
        if threats:
            lines.append("Game Grave did not remove anything. To deal with a threat, open Windows Security and run a "
                         "scan there.")
        dialog.defender_note.setText("\n".join(lines))
        dialog.security_button.setVisible(threats)
        dialog.result_line.setText("Defender finished.")
        winpc.activity("Mod Shield", "Microsoft Defender scan. " + " ".join(r.line() for r in results))
    _job(window, work, finished, "Mod Shield")
