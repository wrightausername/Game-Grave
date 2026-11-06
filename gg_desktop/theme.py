"""Crimson Command design tokens and a local Qt Widgets stylesheet."""
from __future__ import annotations

COLORS = {
    "canvas": "#080C13",
    "sidebar": "#0B111A",
    "panel": "#111922",
    "raised": "#17222D",
    "border": "#2A3541",
    "text": "#F4F7FC",
    "muted": "#A3B4C5",
    "red": "#FF4357",
    "cyan": "#42D4F2",
    "green": "#69DEA7",
    "amber": "#FFD08E",
    "pale": "#D7E1ED",
}

STYLE = r"""
QMainWindow, QWidget#appRoot, QScrollArea, QWidget#scrollBody { background: #080C13; color: #F4F7FC; }
QWidget { font-family: "Segoe UI Variable", "Segoe UI", Arial; font-size: 12px; color: #F4F7FC; }
QWidget#navRail { background: #0B111A; border-right: 1px solid #25303C; }
QFrame#panel, QFrame#metricCard, QFrame#actionCard, QFrame#infoCard, QFrame#heroBottom {
    background: #111922; border: 1px solid #2A3541; border-radius: 11px;
}
QFrame#actionCard:hover, QFrame#metricCard:hover { border: 1px solid #415569; background: #18232E; }
QFrame#alertCard { background: #20151D; border: 1px solid #9D3548; border-radius: 12px; }
QFrame#hero { background: #111923; border-radius: 11px; }
QLabel#brand { font-size: 22px; font-weight: 900; letter-spacing: 1px; }
QLabel#brandKicker { font-size: 10px; letter-spacing: 2px; color: #A3B4C5; }
QLabel#heroTitle { font-size: 29px; font-weight: 900; color: #F6FAFF; }
QLabel#pageTitle { font-size: 27px; font-weight: 800; color: #F6FAFF; }
QLabel#sectionTitle { font-size: 17px; font-weight: 750; color: #F4F7FC; }
QLabel#metricValue { font-size: 25px; font-weight: 850; color: #F4F7FC; }
QLabel#subtle, QLabel#helper { color: #A3B4C5; }
QLabel#eyebrow { color: #42D4F2; font-size: 11px; font-weight: 700; letter-spacing: 2px; }
QLabel#caption { color: #A3B4C5; font-size: 11px; }
QLabel#warning { color: #FFD08E; }
QLabel#dangerText { color: #FF7A8A; }
QLabel#successText { color: #69DEA7; }
QPushButton {
    color: #EAF4FC; background: #17222D; border: 1px solid #384755;
    border-radius: 8px; padding: 9px 12px; min-height: 21px; font-weight: 600;
}
QPushButton:hover { background: #233344; border: 1px solid #5D7A94; }
QPushButton:pressed { background: #314457; }
QPushButton:disabled { color: #778594; background: #151C25; border: 1px solid #29333D; }
QPushButton:focus { border: 2px solid #42D4F2; }
QPushButton#primary { background: #A91E38; border: 1px solid #FF5269; color: white; }
QPushButton#primary:hover { background: #D3314A; }
QPushButton#danger { background: #381924; border: 1px solid #9E3449; color: #FF9EAB; }
QPushButton#danger:hover { background: #55202E; }
QPushButton#navButton {
    border: none; background: transparent; color: #B0BECD; text-align: left;
    border-radius: 9px; font-size: 13px; padding: 11px 15px; min-height: 25px;
}
QPushButton#navButton:hover { background: #162230; color: #FFFFFF; }
QPushButton#navButton[active="true"] {
    background: #2A171F; border-left: 3px solid #FF4357; color: #FFFFFF;
}
QPushButton#link { background: transparent; border: none; color: #64D9FF; padding: 5px; }
QPushButton#link:hover { color: #B2F0FF; text-decoration: underline; }
QLineEdit, QComboBox, QSpinBox, QListWidget, QTableWidget {
    background: #0D141D; border: 1px solid #34414F; border-radius: 7px;
    padding: 7px; selection-background-color: #2E5667; selection-color: white;
}
QLineEdit:focus, QComboBox:focus, QListWidget:focus, QTableWidget:focus {
    border: 2px solid #42D4F2;
}
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: #192431; selection-background-color: #2B5264; }
QTableWidget { gridline-color: #263440; background: #0E161F; border: 1px solid #2E3A46; }
QTableWidget::item { padding: 7px; border-bottom: 1px solid #1F2B36; }
QTableWidget::item:selected { background: #2E3C4D; color: white; }
QHeaderView::section {
    background: #18232D; color: #B5C7D6; padding: 10px;
    font-size: 11px; font-weight: bold; border: 0; border-bottom: 1px solid #2A3541;
}
QListWidget::item { padding: 9px; border-bottom: 1px solid #263440; }
QListWidget::item:selected { background: #243C4F; }
QTabBar::tab { color: #A8B7C4; padding: 9px 15px; }
QTabBar::tab:selected { color: #FFFFFF; border-bottom: 2px solid #FF4357; }
QScrollBar:vertical { background: #111922; width: 10px; }
QScrollBar::handle:vertical { background: #344556; min-height: 36px; border-radius: 5px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QCheckBox { spacing: 7px; }
QProgressBar { background: #24303D; border: none; border-radius: 5px; text-align: center; min-height: 10px; }
QProgressBar::chunk { background: #42D4F2; border-radius: 5px; }
QToolTip { color: white; background: #172633; border: 1px solid #5C7D92; padding: 6px; }
"""
