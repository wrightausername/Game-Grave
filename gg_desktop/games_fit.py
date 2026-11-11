"""Games tab only: keep header words whole in a narrow window.

At 1280 pixels the launcher strip and the tab row have less room than their words need, and Qt cuts them mid-word.
This swaps a long caption for a shorter whole word while the room is short and puts the long one back when there is
room. The full name always stays in the tooltip and the screen-reader name. No other tab uses it.
"""
from __future__ import annotations

try:
    from PySide6.QtCore import QEvent, QObject, QTimer
except ImportError:          # the pure helper below is tested without Qt
    QEvent = QTimer = None
    QObject = object

CAPTION_SHORT = {"Total Games": "Games", "Xbox (PC)": "Xbox", "Battle.net": "B.net"}
TAB_SHORT = {"Recently Played": "Recent"}
CELL_CHROME = 55      # strip cell: margins, the launcher mark and the gap before the words
TAB_CHROME = 50       # tab button: its symbol, the gap and both paddings


def choose(full: str, short: str, need: int, room: int) -> str:
    """The full words when they fit, else the short form (or the full words when there is no short form)."""
    return full if need <= room or not short else short


class Fitter(QObject):
    def __init__(self, strip, tabs):
        super().__init__(strip)
        self.strip, self.tabs = strip, tabs
        self.captions = [(caption, caption.text()) for caption in strip.captions]
        self.buttons = [(button, name) for name, button in tabs.buttons.items()]
        for button, name in self.buttons:
            button.setAccessibleName(name)
            if not button.toolTip():
                button.setToolTip(name)
        strip.installEventFilter(self)
        tabs.installEventFilter(self)
        QTimer.singleShot(0, self.apply)

    def eventFilter(self, target, event):
        if event.type() == QEvent.Resize:
            QTimer.singleShot(0, self.apply)
        return False

    def apply(self):
        try:
            for caption, full in self.captions:
                cell = caption.parentWidget()
                room = (cell.width() if cell else 0) - CELL_CHROME
                wanted = choose(full, CAPTION_SHORT.get(full, ""), caption.fontMetrics().horizontalAdvance(full), room)
                if caption.text() != wanted:
                    caption.setText(wanted)
            for button, full in self.buttons:
                wanted = choose(full, TAB_SHORT.get(full, ""), button.fontMetrics().horizontalAdvance(full),
                                button.width() - TAB_CHROME)
                if button.text() != wanted:
                    button.setText(wanted)
        except RuntimeError:
            pass  # the page was rebuilt


def install(strip, tabs):
    strip._games_fitter = Fitter(strip, tabs)
    return strip._games_fitter
