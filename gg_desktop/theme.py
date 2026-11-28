"""Crimson Command design tokens and a local Qt Widgets stylesheet."""
from __future__ import annotations

COLORS = {
    "canvas": "#020609",
    "sidebar": "#04090C",
    "panel": "#070D12",
    "raised": "#0C151C",
    "border": "#30383E",
    "text": "#F4F7FC",
    "muted": "#A3B4C5",
    "red": "#FF183B",
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

/* The November reference layouts share the same native app shell. */
QMainWindow, QWidget#appRoot, QScrollArea, QWidget#scrollBody { background:#020609; }
QWidget { font-family:"Segoe UI", "Arial", "Liberation Sans"; font-size:12px; }
QWidget#navRail { background:#04090b; border-right:1px solid #171e25; }
QPushButton#navButton {
    border:0; border-radius:0; padding:4px 30px; min-height:27px;
    background:transparent; color:#d6d8dc; font-size:14px; text-align:left; font-weight:400;
}
QPushButton#navButton:hover { background:#161319; }
QPushButton#navButton[active="true"] {
    border:0; border-top:1px solid #821022; border-bottom:1px solid #821022;
    color:white; background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
      stop:0 #22070e,stop:.38 #bb001f,stop:.62 #640d1c,stop:1 #060b0e);
}
QLabel#referenceTitle { font-size:36px; font-weight:750; color:#f3f3f6; }
QLabel#bannerSubtitle { font-size:12px; color:#d6d6dc; }
QLabel#pageTitle { font-size:30px; }
QFrame#panel, QFrame#infoCard { background:#070d12; border:1px solid #28353f; border-radius:8px; }
QFrame#libraryPanel, QFrame#filterPanel, QFrame#detailPanel {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #080e14,stop:.14 #030a0f,stop:1 #050a0e);
    border:1px solid #27333d; border-radius:9px;
}
QFrame#detailPanel, QFrame#fileFilterPanel, QFrame#fileResults {
    background:#050a0f; border:1px solid #5a1b29; border-radius:9px;
}
QFrame#metricStrip {
    border:1px solid #27353e; border-radius:8px;
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #111b24,stop:.25 #060d13,stop:.82 #040a0e,stop:1 #17222c);
}
QFrame#stripCell { background:transparent; border:0; }
QFrame#metricDivider { background:#30343c; border:0; }
QLabel#stripValue { font-size:18px; font-weight:650; color:#f1f1f5; }
QLabel#stripCaption { font-size:10px; color:#d5d6dd; }
QPushButton {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #16212a,stop:.3 #090f15,stop:1 #04080c);
    border:1px solid #364049; border-radius:5px; padding:4px 8px; min-height:18px;
    font-weight:400;
}
QPushButton:hover { background:#19242e; border-color:#73818d; }
QPushButton:focus { border:1px solid #4ed4ef; }
QPushButton#primary, QPushButton#danger, QPushButton#tabButton:checked, QPushButton#filterChip:checked,
QPushButton#viewToggle:checked {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #ff3048,stop:.13 #b60020,stop:.5 #690212,stop:.86 #a5001b,stop:1 #f91b38);
    border:1px solid #ff2847; color:#fff;
}
QPushButton#primary:hover, QPushButton#danger:hover, QPushButton#tabButton:checked:hover { border-color:#ff8899; }
QPushButton#danger:disabled { background:#1c1016; color:#8a6570; border-color:#58303b; }
QPushButton#tabButton { padding:4px 5px; min-height:23px; font-size:12px; }
QFrame#tabStrip { background:#050c12; border:1px solid #29353e; border-radius:7px; }
QPushButton#filterChip { font-size:10px; padding:3px 4px; min-height:19px; }
QPushButton#toolButton { padding:4px 6px; font-size:11px; }
QPushButton#actionLink { font-size: 12px; font-weight: 600; background: transparent; border: none; border-bottom: 1px solid transparent;
    border-radius: 0; padding: 2px 0; min-height: 20px; color: #64D9FF; }
QPushButton#actionLink:hover { color: #B2F0FF; border-bottom: 1px solid #64D9FF; }
QPushButton#actionLink:focus { border-bottom: 1px solid #4DD8E2; }
QPushButton#actionLink:disabled { color: #5D6B76; border-bottom: 1px solid transparent; }
QToolButton { background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #162129,stop:.3 #080d12,stop:1 #05090c);
    border:1px solid #3b4149; border-radius:5px; padding:3px 1px; color:#e4e7ec; font-size:9px; }
QToolButton:hover { border-color:#c45b70; background:#20131c; }
QToolButton:focus { border-color:#47d1ef; }
QToolButton:disabled { color:#68717c; background:#0a0e13; }
QPushButton#viewToggle { padding:3px; border-radius:4px; min-width:22px; }
QPushButton#chromeButton { background:transparent; border:0; padding:2px; min-height:22px; }
QPushButton#chromeButton:hover { background:#1d252d; }
QPushButton#windowClose:hover { background:#a9122c; }
QLineEdit, QComboBox, QSpinBox {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #020508,stop:1 #0a1219);
    border:1px solid #3a454f; border-radius:5px; padding:4px 7px; font-size:11px;
    selection-background-color:#8b1025;
}
QLineEdit:focus, QComboBox:focus, QListWidget:focus, QTableWidget:focus { border:1px solid #5ccce4; }
QFrame#searchShell { border:1px solid #384048; border-radius:6px; background:#05090c; }
QLineEdit#globalSearch { font-size:12px; padding-left:8px; border:0; background:transparent; }
QLabel#searchKey { border:1px solid #3b424a; border-radius:3px; color:#c0c3cb; font-size:10px; padding:1px 4px; }
QLabel#detailKey { font-size:10px; color:#c3c9d0; }
QLabel#detailValue { font-size:10px; color:#e2e6ea; }
QLabel#detailSection {
    font-size:12px; font-weight:600; padding:5px 2px; border-top:1px solid #48222d;
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #211018,stop:1 #090e13);
}
QLabel#detailTitle { font-size:18px; font-weight:650; }
QLabel#filterHeading { color:#d9e0e7; font-size:11px; font-weight:600; padding:3px 0; }
QLabel#sectionTitle { font-size:15px; }
QLabel#caption, QLabel#subtle { color:#a6b4c2; font-size:10px; }
QLabel#warning { font-size:10px; color:#eab464; }
QLabel#successText { color:#3cda63; font-size:11px; }
QLabel#emptyState { color:#b7c2cd; font-size:13px; padding:12px; }
QListWidget#coverGrid { padding:0; background:transparent; border:0; outline:0; }
QListWidget#coverGrid::item { padding:0; border:0; background:transparent; }
QListWidget#sourceFilters { border:0; border-radius:0; padding:0; background:transparent; font-size:10px; outline:0; }
QListWidget#sourceFilters::item { border:0; padding:5px 5px; margin:0; }
QListWidget#sourceFilters::item:selected {
    color:white; border-left:2px solid #ff1a40;
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #970d26,stop:1 #15101a);
}
QTableWidget#referenceTable {
    background:transparent; border:0; padding:0; border-radius:0; font-size:10px;
    selection-background-color:#3b101d; outline:0;
}
QTableWidget#referenceTable::item { padding:3px 4px; border-bottom:1px solid #1b2833; }
QTableWidget#referenceTable::item:selected { background:#35121e; color:white; }
QTableView::indicator { width:10px; height:10px; border:1px solid #72818e; border-radius:2px; background:#060b0f; }
QTableView::indicator:checked { background:#c30829; border-color:#ff3c59; }
QHeaderView::section { background:#07121a; padding:6px 3px; font-size:10px; color:#9aabbc; font-weight:400; }
QScrollBar:vertical { background:#060b0f; width:7px; margin:0; }
QScrollBar::handle:vertical { background:#44474d; border-radius:3px; min-height:30px; }
QScrollBar:horizontal { background:#060b0f; height:7px; }
QScrollBar::handle:horizontal { background:#44474d; border-radius:3px; min-width:30px; }
QScrollBar::add-page, QScrollBar::sub-page { background:transparent; }
QCheckBox, QRadioButton { spacing:6px; font-size:10px; }
QCheckBox::indicator, QRadioButton::indicator {
    width:10px; height:10px; border:1px solid #798795; border-radius:2px; background:#070b10;
}
QCheckBox::indicator:checked, QRadioButton::indicator:checked { border-color:#ff2d49; background:#c40e2e; }
QSplitter::handle { background:transparent; }
QLabel#overviewMetricCaption { color:#d9dee5; font-size:13px; }
QPushButton#navButton[overview="true"] { font-size:17px; padding-left:42px; }
QLabel#overviewMetricValue { font-size:25px; font-weight:700; color:#f6f7fa; }
QFrame#overviewSection { background:transparent; border:0; }
QLabel#overviewSectionTitle { font-size:20px; font-weight:600; }
QPushButton#overviewQuick, QPushButton#overviewActivity {
    text-align:left; background:transparent; border:0; border-bottom:1px solid #25232c;
    border-radius:0; padding:9px 2px; font-size:13px;
}
QPushButton#overviewQuick:hover, QPushButton#overviewActivity:hover { background:#20101a; color:white; }
QPushButton#overviewQuick:disabled { color:#778594; }

/* Match the condensed, readable type hierarchy in the locked photos. */
QWidget { font-family: "Roboto Condensed", "Arial"; font-size:13px; }
QLabel#referenceTitle { font-family:Arial; font-size:36px; font-weight:700; }
QLabel#stripValue { font-size:20px; }
QLabel#stripCaption { font-size:12px; }
QPushButton#tabButton { font-size:14px; }
QTableWidget#referenceTable { font-size:12px; }
QHeaderView::section { font-size:11px; }
QLabel#detailKey, QLabel#detailValue { font-size:12px; }
QListWidget#sourceFilters { font-size:12px; }
/* Prompts: every dialog and message box is dark with light text. Without this they fall back to the system
   light background while the text stays white, which made them unreadable (for example in the Resurrection Kit). */
QDialog, QMessageBox, QInputDialog, QFileDialog { background:#0B121A; color:#F4F7FC; }
QDialog QLabel, QMessageBox QLabel, QInputDialog QLabel { color:#F4F7FC; background:transparent; font-size:14px; }
QDialog QCheckBox, QDialog QRadioButton, QDialog QGroupBox { color:#F4F7FC; }
QDialog QTextEdit, QDialog QPlainTextEdit, QDialog QTextBrowser, QMessageBox QTextEdit {
    background:#0D141D; color:#F4F7FC; border:1px solid #34414F; border-radius:7px; padding:8px;
    selection-background-color:#2E5667; selection-color:white;
}
QDialog QPushButton, QMessageBox QPushButton { min-width:88px; min-height:26px; padding:6px 16px; }
QDialog QAbstractItemView, QDialog QTreeView, QDialog QListView { background:#0D141D; color:#F4F7FC; }
QMenu { background:#111A23; color:#F4F7FC; border:1px solid #34414F; padding:4px; }
QMenu::item { padding:6px 22px; }
QMenu::item:selected { background:#2B5264; color:white; }
QMenu::item:disabled { color:#778594; }
"""
