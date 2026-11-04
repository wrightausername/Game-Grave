"""User-triggered Game DNA Ghost Watch and patch-sensitive change review.

Local metadata only. No background monitor, external feeds, automatic repair,
unverified 'crash cause', cleanup permission or filesystem mutations.
"""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QPlainTextEdit, QWidget

from gg_desktop.widgets import button, column, label, row


def run_ghost_watch(window, *, patch_only=False):
    if window.scanning or window.cleaning:
        window.info("Game Grave is busy", "Finish the current operation first.")
        return
    if not window.inventory.scanned_at:
        window.info("Scan first", "Scan local inventory before capturing mod observations.")
        return

    from game_intelligence import load_observation
    previous = load_observation()
    if previous is None and patch_only:
        window.info("Baseline required",
                    "Capture a Ghost Watch baseline first. Changes cannot be inferred "
                    "from a single observation.")
        return
    if previous is None and not window.confirm(
            "Capture Ghost Watch baseline?",
            "Record bounded local mod metadata for comparison at your NEXT manual scan? "
            "Nothing in your games changes. Some folders may be skipped, "
            "and missed files will never be treated as proof of deletion."):
        return

    mods = list(window.inventory.mods)

    def worker(_emit):
        from game_intelligence import (
            capture_mod_observation, ghost_watch, patch_fallout,
        )
        from performance_guard import background_worker_priority
        with background_worker_priority():
            snapshot = capture_mod_observation(mods)
        if previous is None:
            return {"mode": "baseline", "snapshot": snapshot}
        report = ghost_watch(previous, snapshot)
        impact = patch_fallout(report)
        return {
            "mode": "compare", "snapshot": snapshot,
            "report": report, "impact": impact,
        }

    def complete(result):
        from game_intelligence import save_observation
        snapshot = result["snapshot"]
        if result["mode"] == "baseline":
            try:
                save_observation(snapshot)
            except (OSError, ValueError) as exc:
                window.error("Could not record observation", str(exc))
                return
            msg = (
                f"Baseline recorded for {len(snapshot.get('entries', {}))} items "
                f"across {len(snapshot.get('roots', []))} local roots.\n"
                "A future manual comparison can identify observed metadata changes.\n"
            )
            if snapshot.get("truncated"):
                msg += ("WARNING: This observation is incomplete because at least "
                        "one root or file was skipped.\n")
            _report(window, "Ghost Watch baseline", msg)
            return

        report = result["report"]
        impact = result["impact"]
        lines = [
            "Comparison of two manual local observations.",
            f"Changed observations: {report.get('count', 0)}",
            f"Patch-sensitive files for review: {impact.get('total_review', 0)}",
            "Ownership, game compatibility and crash causality were NOT verified.",
            "",
        ]
        if report.get("incomplete"):
            lines.append(
                "INCOMPLETE OBSERVATION: some items may not have been scanned. "
                "Missing entries do not establish file deletion.\n")
        for change in report.get("changes", [])[:65]:
            if patch_only and not change.get("patch_sensitive"):
                continue
            lines.append(str(change.get("change", "Observed change")) +
                         " | " + str(change.get("path", "")))
        if patch_only and not impact.get("review_files"):
            lines.append("No patch-sensitive changes observed in the compared subset.")
        if len(report.get("changes", [])) > 65:
            lines.append("Additional observations omitted from this preview.")
        _report(window, "Patch Fallout review" if patch_only else "Ghost Watch comparison",
                "\n".join(lines))
        if window.confirm(
                "Update Ghost Watch baseline?",
                "Save today's observed mod metadata as the reference for your next "
                "manual comparison? This changes only Game Grave's private baseline, "
                "not any mod or game file."):
            try:
                save_observation(snapshot)
            except (OSError, ValueError) as exc:
                window.error("Could not update baseline", str(exc))

    window.job(worker, complete, error_title="Ghost Watch observation failed")


def _report(window, title, text):
    dialog = QDialog(window)
    dialog.setWindowTitle("Game Grave — " + title)
    dialog.resize(770, 555)
    layout = column(spacing=12, margins=(16, 16, 16, 16))
    dialog.setLayout(layout)
    layout.addWidget(label(title, "sectionTitle"))
    transcript = QPlainTextEdit()
    transcript.setReadOnly(True)
    transcript.setPlainText(text)
    layout.addWidget(transcript, 1)
    footer = QWidget()
    buttons = row()
    footer.setLayout(buttons)
    buttons.addStretch()
    buttons.addWidget(button("Close", dialog.accept))
    layout.addWidget(footer)
    dialog.exec()
