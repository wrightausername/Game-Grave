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


# Owner-locked cinematic shell: restrained red brand, minimal separators,
# independent colored data accents and practical hover/focus feedback.
STYLE += r"""
QMainWindow, QWidget#appRoot, QWidget#scrollBody, QScrollArea {
    background: #070D15; color: #F5F7FB;
}
QWidget { font-family: "Segoe UI Variable", "Segoe UI", Arial;
    font-size: 13px; color: #F5F7FB; }
QWidget#navRail, QWidget#navBody, QScrollArea#navScroll {
    background: #091019; border: none;
}
QFrame#panel, QFrame#infoCard, QFrame#metricCard {
    background: #0C1721; border: 1px solid #20303B; border-radius: 10px;
}
QFrame#actionCard {
    background: #101B24; border: 1px solid #283945; border-radius: 9px;
}
QFrame#actionCard:hover {
    background: #17232E; border: 1px solid #6C3947;
}
QPushButton#navButton {
    background: transparent; border: 0; text-align: left; color: #D8E0E8;
    border-radius: 4px; padding: 8px 12px; min-height: 23px;
    font-size: 14px;
}
QPushButton#navButton:hover { background: #18222D; color: #FFFFFF; }
QPushButton#navButton[active="true"] {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #691629, stop:.68 #361621, stop:1 #101822);
    color: #FFFFFF; border: 0; border-left: 3px solid #FF4055;
}
QLineEdit#globalSearch {
    color: #EDF3F8; background: #0C151E;
    border: 1px solid #37444F; border-radius: 11px;
    padding: 11px 16px; font-size: 14px; min-height: 22px;
}
QLineEdit#globalSearch:focus { border-color: #F44A5F; }
QFrame#hero { border: none; background: #0A141E; }
QLabel#sectionTitle { font-size: 16px; font-weight: 750; }
QLabel#metricValue { font-size: 25px; font-weight: 850; }
QLabel#caption { color: #A5B6C5; font-size: 11px; }
QLabel#eyebrow { color: #F66A78; font-size: 11px; }
QPushButton#primary { background: #A5233B; color: #FFFFFF;
    border: 1px solid #EC435B; border-radius: 8px; }
QPushButton#primary:hover { background: #C72D47; }
QTableWidget { background: #0A151E; border: 1px solid #223540; }
QTableWidget::item { padding: 7px; border-bottom: 1px solid #172B36; }
QTableWidget::item:selected { color: #FFFFFF; background: #581A2B; }
QHeaderView::section { color: #C5D2DB; background: #14212B;
    padding: 10px; border: none; border-bottom: 1px solid #293B46; }
QScrollBar:vertical { background: #0B1520; width: 9px; }
QScrollBar::handle:vertical { background: #334756; min-height: 38px;
    border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""
