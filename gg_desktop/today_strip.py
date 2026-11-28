"""Overview's Today strip, the Qt part. One compact row under the header: a TODAY label and one chip per line from
`today_core`. A chip only opens its tab. Built with Overview; reads two small saved files and the free space of the drives
that hold games, nothing else."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton

from gg_desktop import today_core

TONES = {"good": "#32d67a", "warn": "#f6be24", "bad": "#ff5a6e", "info": "#13bcf5"}
STYLE = ("QFrame#todayStrip{background:#09121a;border:1px solid #1b2836;border-radius:10px;}"
         "QLabel#todayLabel{color:#8C9AA9;font-size:12px;font-weight:800;letter-spacing:1.6px;}"
         "QPushButton#todayChip{background:#0f1a24;border:1px solid #233243;border-radius:13px;color:#e8eef5;"
         "font-size:12px;padding:3px 12px 3px 10px;text-align:left;}"
         "QPushButton#todayChip:hover{border-color:rgba(255,40,74,160);background:#142230;}"
         "QPushButton#todayChip:disabled{color:#9fb0c2;}")


def gather(window):
    from gg_desktop import space_core
    try:
        drives = space_core.game_drives(window.inventory.games)
    except Exception:
        drives = []
    try:
        from gg_desktop.ready_room_services import load_state
        news = load_state().get("news", [])
    except Exception:
        news = []
    return today_core.items(window.settings, drives, news)


def build(window):
    box = QFrame()
    box.setObjectName("todayStrip")
    box.setStyleSheet(STYLE)
    box.setAccessibleName("Today")
    from gg_desktop.insight_widgets import ActionFlow
    outer = QHBoxLayout(box)
    outer.setContentsMargins(12, 6, 12, 6)
    outer.setSpacing(10)
    title = QLabel("TODAY")
    title.setObjectName("todayLabel")
    outer.addWidget(title, 0, Qt.AlignTop)
    lay = ActionFlow(spacing=8)              # chips wrap onto a second line in a narrow window
    outer.addLayout(lay, 1)
    window.today_chips = []
    for line in gather(window):
        chip = QPushButton(line.text)
        chip.setObjectName("todayChip")
        chip.setToolTip(line.tip)
        chip.setAccessibleName(line.text)
        dot = TONES.get(line.tone, TONES["info"])
        chip.setStyleSheet(f"QPushButton#todayChip{{border-left:3px solid {dot};}}")
        if line.route:
            chip.setCursor(Qt.PointingHandCursor)
            chip.clicked.connect(lambda _=False, r=line.route: window.navigate(r))
        else:
            chip.setEnabled(False)
        chip.setProperty("todayKey", line.key)
        lay.addWidget(chip)
        window.today_chips.append(chip)
    return box
