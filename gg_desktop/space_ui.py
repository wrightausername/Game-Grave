"""Never run out of space, in the Graveyard: a card when a drive that holds games is low, and a window to put long-unplayed
games to rest (a Resurrection Kit on another drive, then the launcher's own uninstall, which asks). Bringing one back is
Fix Kit's Restore a game. Reading drives is one quick call per drive; nothing runs in the background."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame

from core import human_size
from gg_desktop import space_core as sp
from gg_desktop.widgets import button, column, label, row

CARD = ("QFrame#spaceCard{background:#1d1606;border:1px solid #6d5512;border-radius:10px;}")


def enabled():
    return os.environ.get("GAME_GRAVE_SPACE_CARD", "1") != "0"      # off in CI, where C: is often small


def low_drive(window):
    if not enabled():
        return None, [], []
    games = list(getattr(window.inventory, "games", []) or [])
    drives = sp.game_drives(games)
    for drive in sorted((d for d in drives if d.low), key=lambda d: d.free):
        return drive, drives, sp.suggestions(games, drive)
    return None, drives, []


def add_card(window, layout):
    """The Graveyard's space card (only when a game drive is low). Returns it or None."""
    try:
        drive, drives, picks = low_drive(window)
    except Exception:
        return None
    if drive is None:
        return None
    card = QFrame()
    card.setObjectName("spaceCard")
    card.setStyleSheet(CARD)
    line = row(spacing=12, margins=(14, 10, 14, 10))
    card.setLayout(line)
    words = column(spacing=2)
    title = label(f"{drive.root} is almost full", "readyGameTitle")
    title.setStyleSheet("color:#f6be24;")
    words.addWidget(title)
    words.addWidget(label(sp.headline(drive, picks), "caption", wrap=True))
    line.addLayout(words, 1)
    if picks:
        line.addWidget(button("Review and free up space", lambda: open_review(window, drive, drives, picks),
                              kind="primary"), 0, Qt.AlignVCenter)
    window.space_card = card
    layout.addWidget(card)
    return card


def notify_if_low(window):
    """After a scan: one notice a day when a game drive is low."""
    if window.settings.get("low_space_notice", True) is False or not sp.notice_due(window.settings):
        return
    try:
        drive, _drives, picks = low_drive(window)
    except Exception:
        return
    if drive is None:
        return
    import time
    from core import save_settings
    from gg_desktop import comfort
    updated = dict(window.settings, **{sp.NOTICE_KEY: time.strftime("%Y-%m-%d")})
    try:
        save_settings(updated)
        window.settings = updated
    except OSError:
        pass
    comfort.notify(window, f"{drive.root} is almost full", sp.headline(drive, picks), "warn", "Graveyard")


def open_review(window, drive, drives, picks):
    dialog = QDialog(window)
    dialog.setWindowTitle("Free up space")
    dialog.setMinimumWidth(620)
    box = column(spacing=10, margins=(20, 18, 20, 16))
    dialog.setLayout(box)
    box.addWidget(label(f"Free up space on {drive.root}", "sectionTitle"))
    need = sum(p.size for p in picks)
    target = sp.rest_drive(drives, drive.root, need)
    folder = os.path.join(target.root, "Game Grave Kits") if target else ""
    box.addWidget(label(
        "Putting a game to rest: Game Grave saves the whole game as a Resurrection Kit " +
        (f"on {target.root} ({human_size(target.free)} free)" if target else "(no other drive has room, so pick a folder "
                                                                             "in the kit window, such as an external drive)") +
        ", checks it, then asks your launcher to uninstall the game. To play again, use Fix Kit > Restore a game.",
        "readyDetail", wrap=True))
    for pick in picks:
        card = QFrame()
        card.setObjectName("restCard")
        card.setStyleSheet("QFrame#restCard{background:#0b1118;border:1px solid #1f2c3a;border-radius:8px;}")
        line = row(spacing=10, margins=(12, 8, 12, 8))
        card.setLayout(line)
        words = column(spacing=2)
        words.addWidget(label(pick.game.name, "readyGameTitle"))
        months = pick.days // 30
        words.addWidget(label(f"{human_size(pick.size)} · last played {months} months ago · {pick.game.launcher}",
                              "caption"))
        line.addLayout(words, 1)
        go = button("Put to rest", None, kind="primary")
        go.clicked.connect(lambda _=False, p=pick, b=go: put_to_rest(window, p, folder, b))
        line.addWidget(go, 0, Qt.AlignVCenter)
        box.addWidget(card)
    foot = row(spacing=8)
    foot.addWidget(button("Close", dialog.reject))
    foot.addStretch()
    box.addLayout(foot)
    window.space_dialog = dialog
    dialog.show()
    return dialog


def put_to_rest(window, pick, folder, control=None):
    """Step 1: the kit (the usual window, game picked, folder on the other drive). Step 2, once it is saved and checked:
    the launcher's uninstall, after asking."""
    from gg_desktop import kit_easy_ui

    def after(result):
        uninstall(window, pick.game, result.get("archive", ""), control)
    kit_easy_ui.open_easy_setup(window, pick.game, folder or None, after)


def uninstall(window, game, archive, control=None):
    from core import log_event
    link = sp.uninstall_link(game)
    where = f"The kit is saved at:\n{archive}\n\n" if archive else ""
    if not link:
        window.info("Uninstall it in your launcher", where + f"Uninstall {game.name} in {game.launcher or 'its launcher'}. "
                    "To play again later, use Fix Kit > Restore a game with this kit.")
        return False
    if not window.confirm(f"Uninstall {game.name}?", where + f"Steam will ask to uninstall {game.name} "
                          f"({link}). Your kit stays where it is; Fix Kit > Restore a game brings the game back."):
        return False
    os.startfile(link)
    log_event("game_put_to_rest", f"Kit made and Steam asked to uninstall {game.name}", path=archive or None,
              source="Graveyard")
    if control is not None:
        control.setEnabled(False)
        control.setText("Steam is uninstalling")
    window.status.setText(f"Steam is asking to uninstall {game.name}. The kit is kept for when you want it back.")
    return True
