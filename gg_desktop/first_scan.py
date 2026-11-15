"""The window after the first full scan: what was found and three next steps, each opening a tab or tool that already
exists. Shown once (`first_scan_summary_seen`), never in the photo-reference preview or after a quick scan.
GAME_GRAVE_FIRST_SCAN_CARD=0 turns it off (set in CI so other checks are not covered by it)."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame

from gg_desktop import first_scan_core as core
from gg_desktop.widgets import button, column, label, row


def enabled():
    return os.environ.get("GAME_GRAVE_FIRST_SCAN_CARD", "1") != "0"


def after_scan(window, quick=False):
    if not core.should_show(window.settings, getattr(window, "reference_preview", False), quick, enabled()):
        return None
    from core import save_settings
    updated = dict(window.settings, **{core.SEEN_KEY: True})
    try:
        save_settings(updated)
        window.settings = updated
    except OSError:
        pass
    return show(window)


def show(window):
    dialog = QDialog(window)
    dialog.setObjectName("firstScan")
    dialog.setWindowTitle("Here's what Game Grave found")
    dialog.setAttribute(Qt.WA_DeleteOnClose)
    dialog.setMinimumWidth(560)
    dialog.setStyleSheet("QDialog#firstScan{background:#070c11;} QFrame#stepCard{background:#0b1118;"
                         "border:1px solid #1f2c3a;border-radius:10px;}")
    box = column(spacing=12, margins=(22, 20, 22, 18))
    dialog.setLayout(box)
    box.addWidget(label("Here's what Game Grave found", "sectionTitle"))
    found = label(core.headline(window.inventory), "readyDetail", wrap=True)
    box.addWidget(found)
    box.addWidget(label("Three good places to start. Each one asks before it changes anything.", "caption", wrap=True))
    from gg_desktop import autopilot_ui
    for n, (title, why, words, target) in enumerate(core.next_steps(window.inventory), 1):
        card = QFrame()
        card.setObjectName("stepCard")
        line = row(spacing=12, margins=(14, 12, 14, 12))
        card.setLayout(line)
        dot = label(str(n), "")
        dot.setFixedSize(26, 26)
        dot.setAlignment(Qt.AlignCenter)
        dot.setStyleSheet("background:#e5243b;color:#ffffff;border-radius:13px;font-weight:800;")
        line.addWidget(dot, 0, Qt.AlignTop)
        words_box = column(spacing=3)
        words_box.addWidget(label(title, "readyGameTitle"))
        words_box.addWidget(label(why, "caption", wrap=True))
        line.addLayout(words_box, 1)
        go = button(words, lambda _=False, t=target: (dialog.accept(), autopilot_ui.open_target(window, t)), kind="primary")
        line.addWidget(go, 0, Qt.AlignVCenter)
        box.addWidget(card)
    foot = row(spacing=8)
    foot.addWidget(button("Close", dialog.reject))
    foot.addStretch()
    box.addLayout(foot)
    window.first_scan_dialog = dialog
    dialog.show()            # not modal: the window stays usable behind it
    return dialog
