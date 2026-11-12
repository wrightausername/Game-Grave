"""The one layout every More Tools window uses, so each tool reads the same way:

    [icon] Title                      one plain sentence under it
    (1) Step --- (2) Step --- (3) Step
    content cards
    > Show technical details           (exact registry values and commands, folded)
    [result banner]                    green done, amber needs you, red stopped, blue working
    Close                 secondary  [Primary]

Display only: it changes nothing on the PC. The tools keep their own logic, confirmations and activity log.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QProgressBar, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from gg_desktop import tools_words as words
from gg_desktop.widgets import button, column, row

HEX = {"red": "#ff3b57", "cyan": "#13bcf5", "purple": "#b455ff", "magenta": "#df50c8", "blue": "#288cff",
       "yellow": "#f6be24", "green": "#32d67a"}
BANNER = {words.GOOD: ("#32d67a", "check"), words.WARN: ("#f6be24", "warning"), words.BAD: ("#ff5a6e", "warning"),
          words.INFO: ("#13bcf5", "help"), words.WORKING: ("#13bcf5", "refresh"), words.IDLE: ("#8b98aa", "help")}
PILL = {words.GOOD: "#32d67a", words.WARN: "#f6be24", words.BAD: "#ff5a6e", words.INFO: "#13bcf5", words.IDLE: "#8b98aa",
        words.WORKING: "#13bcf5"}

STYLE = (
    "QDialog{background:#05090c;color:#e8eef5;}"
    "QLabel{color:#e8eef5;background:transparent;}"
    "QCheckBox{color:#e8eef5;spacing:10px;font-size:14px;font-weight:600;}"
    "QCheckBox:disabled{color:#8b98aa;}"
    "QCheckBox::indicator,QListView::indicator{width:18px;height:18px;border:1px solid #6b7788;background:#0a1118;border-radius:4px;}"
    "QCheckBox::indicator:checked,QListView::indicator:checked{background:#ff284a;border-color:#ff284a;}"
    "QCheckBox::indicator:disabled{background:#14202b;border-color:#2c3a48;}"
    "QListWidget,QPlainTextEdit,QComboBox,QLineEdit{background:#0a1118;color:#e8eef5;border:1px solid #243242;"
    "border-radius:8px;padding:6px 8px;font-size:13px;}"
    "QComboBox{min-height:22px;} QLineEdit{min-height:22px;}"
    "QListWidget{padding:4px;} QListWidget::item{padding:7px 6px;border-radius:6px;margin:1px 0;}"
    "QListWidget::item:hover{background:#0f1a24;} QListWidget::item:selected{background:#2a0f17;color:#ffffff;}"
    "QPlainTextEdit{font-family:Consolas,monospace;} QComboBox QAbstractItemView{background:#0a1118;color:#e8eef5;}"
    "QFrame#toolCard{background:#09121a;border:1px solid #1b2836;border-radius:12px;}"
    "QFrame#toolRow{background:transparent;border:none;border-bottom:1px solid #15212c;}"
    "QFrame#toolRowLast{background:transparent;border:none;}"
    "QToolButton#toolDetails{color:#8fa0b3;background:transparent;border:none;font-size:12px;padding:2px 0;}"
    "QToolButton#toolDetails:hover{color:#e8eef5;}"
    "QPushButton#toolDetails{color:#8fa0b3;background:transparent;border:none;font-size:12px;padding:2px 0;min-height:0;}"
    "QPushButton#toolDetails:hover{color:#e8eef5;}"
    "QLabel#toolTech{color:#9fb0c2;background:#070d13;border:1px solid #17222d;border-radius:8px;padding:8px 10px;"
    "font-family:Consolas,monospace;font-size:11px;}"
    "QLabel#toolTitle{font-size:20px;font-weight:800;color:#ffffff;}"
    "QLabel#toolSummary{font-size:13px;color:#b6c2cf;}"
    "QLabel#toolLead{font-size:14px;font-weight:700;color:#ffffff;}"
    "QLabel#toolNote{font-size:12px;color:#8fa0b3;}"
    "QProgressBar{background:#0c1620;border:none;border-radius:2px;max-height:4px;}"
    "QProgressBar::chunk{background:#13bcf5;border-radius:2px;}"
)


def rgba(hex_color, alpha):
    c = QColor(hex_color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"


def text(value="", role="toolNote", wrap=True):
    item = QLabel(value)
    item.setTextFormat(Qt.PlainText)
    item.setObjectName(role)
    item.setWordWrap(wrap)
    item.setMinimumWidth(0)
    item.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return item


def badge(symbol, color, size=46):
    from gg_desktop.reference_widgets import icon
    box = QLabel()
    box.setFixedSize(size, size)
    box.setAlignment(Qt.AlignCenter)
    inner = int(size * .5)
    box.setPixmap(icon(symbol, color, inner).pixmap(inner, inner))
    box.setStyleSheet(f"background:{rgba(color, 40)};border:1px solid {rgba(color, 120)};border-radius:{size // 2}px;")
    return box


def pill(value, tone=words.IDLE):
    color = PILL.get(tone, PILL[words.IDLE])
    tag = QLabel(value)
    tag.setObjectName("toolPill")
    tag.setTextFormat(Qt.PlainText)
    tag.setStyleSheet(f"color:{color};background:{rgba(color, 34)};border:1px solid {rgba(color, 100)};border-radius:11px;"
                      "padding:0px 10px;font-size:11px;font-weight:700;")
    tag.setFixedHeight(22)
    tag.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
    return tag


def set_pill(tag, value, tone):
    color = PILL.get(tone, PILL[words.IDLE])
    tag.setText(value)
    tag.setStyleSheet(f"color:{color};background:{rgba(color, 34)};border:1px solid {rgba(color, 100)};border-radius:11px;"
                      "padding:0px 10px;font-size:11px;font-weight:700;")


def header(symbol, title, summary, color):
    """The icon badge, title and one plain sentence that open every tool window."""
    head = row(spacing=14)
    head.addWidget(badge(symbol, color), 0, Qt.AlignTop)
    words_box = column(spacing=3)
    words_box.addWidget(text(title, "toolTitle", wrap=False))
    words_box.addWidget(text(summary, "toolSummary"))
    head.addLayout(words_box, 1)
    return head


class Steps(QWidget):
    """Numbered steps. Finished steps show a tick, the current one is lit, the rest wait in grey."""

    def __init__(self, names, color):
        super().__init__()
        self.names, self.color, self.current = tuple(names), color, 0
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(8)
        self.dots, self.labels = [], []
        for n, name in enumerate(self.names):
            if n:
                line = QFrame()
                line.setFixedHeight(2)
                line.setMinimumWidth(18)
                line.setStyleSheet("background:#1f2c3a;border:none;")
                lay.addWidget(line, 1)
            dot = QLabel(str(n + 1))
            dot.setFixedSize(24, 24)
            dot.setAlignment(Qt.AlignCenter)
            name_label = QLabel(name)
            lay.addWidget(dot)
            lay.addWidget(name_label)
            self.dots.append(dot)
            self.labels.append(name_label)
        self.setAccessibleName("Steps: " + ", ".join(self.names))
        self.set(0)

    def set(self, index):
        self.current = max(0, min(index, len(self.names)))
        for n, (dot, name) in enumerate(zip(self.dots, self.labels)):
            if n < self.current:
                dot.setText("✓")
                dot.setStyleSheet("background:#123322;color:#32d67a;border:1px solid #32d67a;border-radius:12px;"
                                  "font-size:12px;font-weight:800;")
                name.setStyleSheet("color:#9fe3bc;font-size:12px;font-weight:600;")
            elif n == self.current:
                dot.setText(str(n + 1))
                dot.setStyleSheet(f"background:{self.color};color:#05090c;border:1px solid {self.color};border-radius:12px;"
                                  "font-size:12px;font-weight:800;")
                name.setStyleSheet("color:#ffffff;font-size:12px;font-weight:700;")
            else:
                dot.setText(str(n + 1))
                dot.setStyleSheet("background:transparent;color:#6b7788;border:1px solid #2c3a48;border-radius:12px;"
                                  "font-size:12px;font-weight:700;")
                name.setStyleSheet("color:#6b7788;font-size:12px;")


class Details(QWidget):
    """'Show technical details': the exact lines, folded. Starts closed."""

    def __init__(self, lines=""):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.toggle = QToolButton()
        self.toggle.setObjectName("toolDetails")
        self.toggle.setCursor(Qt.PointingHandCursor)
        self.toggle.setAccessibleName("Show technical details")
        self.body = text("", "toolTech")
        self.body.hide()
        lay.addWidget(self.toggle, 0, Qt.AlignLeft)
        lay.addWidget(self.body)
        self.toggle.clicked.connect(lambda: self.open(not self.body.isVisibleTo(self)))
        self.set_lines(lines)
        self.open(False)

    def set_lines(self, lines):
        value = "\n".join(lines) if isinstance(lines, (list, tuple)) else str(lines or "")
        self.body.setText(value)
        self.setVisible(bool(value.strip()))

    def open(self, opened):
        self.body.setVisible(opened)
        self.toggle.setText(("▾  Hide technical details" if opened else "▸  Show technical details"))
        window = self.window()
        if window is not None and window is not self:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: window.isVisible() and window.adjustSize())


class Banner(QFrame):
    """The result line, coloured by outcome. Keeps QLabel's text()/setText() so older code and checks still work."""

    def __init__(self, accessible="Result"):
        super().__init__()
        self.setObjectName("toolBanner")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 9, 12, 9)
        lay.setSpacing(6)
        line = QHBoxLayout()
        line.setSpacing(10)
        self.mark = QLabel()
        self.mark.setFixedSize(18, 18)
        self.label = text("", "toolBannerText")
        self.label.setAccessibleName(accessible)
        line.addWidget(self.mark, 0, Qt.AlignTop)
        line.addWidget(self.label, 1)
        lay.addLayout(line)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setTextVisible(False)
        self.bar.hide()
        lay.addWidget(self.bar)
        self.tone = words.IDLE
        self.setText("")

    def text(self):
        return self.label.text()

    def setText(self, value, tone=None):
        value = str(value or "")
        self.tone = tone or words.guess_tone(value)
        self.label.setText(value)
        color, symbol = BANNER.get(self.tone, BANNER[words.INFO])
        from gg_desktop.reference_widgets import icon
        self.mark.setPixmap(icon(symbol, color, 18).pixmap(18, 18))
        self.setStyleSheet(f"QFrame#toolBanner{{background:{rgba(color, 26)};border:1px solid {rgba(color, 90)};"
                           f"border-radius:10px;}} QLabel#toolBannerText{{color:#eef3f8;font-size:13px;}}")
        self.bar.setVisible(self.tone == words.WORKING)
        self.setVisible(bool(value.strip()))

    def show_result(self, value, tone):
        self.setText(value, tone)


def card(spacing=0, margins=(14, 6, 14, 6)):
    frame = QFrame()
    frame.setObjectName("toolCard")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    return frame, lay


class ChoiceRow(QFrame):
    """A tickable choice: name, one plain line, and its current state as a pill on the right."""

    def __init__(self, title, plain, state, tone, *, last=False, accessible=""):
        super().__init__()
        self.setObjectName("toolRowLast" if last else "toolRow")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 10, 0, 10)
        lay.setSpacing(12)
        left = QVBoxLayout()
        left.setSpacing(3)
        self.check = QCheckBox(title)
        self.check.setAccessibleName(accessible or title)
        self.note = text(plain)
        self.note.setContentsMargins(28, 0, 0, 0)
        left.addWidget(self.check)
        left.addWidget(self.note)
        lay.addLayout(left, 1)
        side = QVBoxLayout()
        side.setSpacing(2)
        caption = text("Now", "toolNote", wrap=False)
        caption.setAlignment(Qt.AlignRight)
        self.state = pill(state, tone)
        side.addWidget(caption, 0, Qt.AlignRight)
        side.addWidget(self.state, 0, Qt.AlignRight)
        lay.addLayout(side)


class ToolDialog(QDialog):
    """Header, steps, body, details, banner and a footer with Close on the left and the main action on the right."""

    def __init__(self, parent, key, title, symbol, *, width=600, summary=None, step_names=None, color=None):
        super().__init__(parent)
        self.setStyleSheet(STYLE)
        self.setWindowTitle("Game Grave · " + title)
        self.setMinimumWidth(width)
        self.key = key
        self.color = color or HEX.get(words.tone(key), HEX["red"])
        outer = column(spacing=12, margins=(20, 18, 20, 16))
        self.setLayout(outer)
        head = row(spacing=14)
        head.addWidget(badge(symbol, self.color), 0, Qt.AlignTop)
        words_box = column(spacing=3)
        self.title_label = text(title, "toolTitle", wrap=False)
        self.summary_label = text(summary if summary is not None else words.summary(key), "toolSummary")
        words_box.addWidget(self.title_label)
        words_box.addWidget(self.summary_label)
        head.addLayout(words_box, 1)
        outer.addLayout(head)
        names = step_names if step_names is not None else words.steps(key)
        self.steps = Steps(names, self.color) if names else None
        if self.steps:
            outer.addWidget(self.steps)
        self.body = column(spacing=10)
        outer.addLayout(self.body)
        self.details = Details()
        outer.addWidget(self.details)
        self.result_line = Banner(title + " result")
        outer.addWidget(self.result_line)
        outer.addStretch(1)
        self.footer = row(spacing=8)
        self.close_button = button("Close", self.accept)
        self.close_button.setAccessibleName("Close " + title)
        self.footer.addWidget(self.close_button)
        self.footer.addStretch()
        outer.addLayout(self.footer)

    def add_actions(self, *controls):
        """Secondary actions first, the main action last (it lands on the right)."""
        for control in controls:
            self.footer.addWidget(control)

    def step(self, index):
        if self.steps:
            self.steps.set(index)

    def result(self, value, tone=None):
        self.result_line.setText(value, tone)
