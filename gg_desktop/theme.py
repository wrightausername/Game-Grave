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
/* All confirmation, destructive-action, text-entry, info and file dialogs
   must have a dark surface and high-contrast text. Without this, native
   Qt dialog panels may render as white with inherited white text. */
QDialog, QMessageBox, QInputDialog, QFileDialog {
    background-color: #111B27;
    color: #F5FAFF;
}
QDialog QLabel, QMessageBox QLabel, QInputDialog QLabel, QFileDialog QLabel {
    background-color: transparent;
    color: #F5FAFF;
    font-size: 12px;
}
QDialog QLineEdit, QInputDialog QLineEdit, QFileDialog QLineEdit {
    background-color: #081522;
    color: #F5FAFF;
    selection-background-color: #31758C;
    border: 1px solid #62798F;
    border-radius: 6px;
    padding: 8px;
}
QDialogButtonBox, QMessageBox QDialogButtonBox {
    background-color: #111B27;
    color: #F5FAFF;
}
QDialog QPushButton, QMessageBox QPushButton, QInputDialog QPushButton {
    background-color: #243446;
    color: #F5FAFF;
    border: 1px solid #577187;
}
QDialog QPushButton:hover, QMessageBox QPushButton:hover, QInputDialog QPushButton:hover {
    background-color: #34526A;
    border-color: #6DD0E8;
}
QDialog QPlainTextEdit, QDialog QTextEdit {
    background-color: #0D1722;
    color: #F5FAFF;
    border: 1px solid #547086;
}
QTabWidget#captureTabs::pane {
    border: 1px solid #304653;
    background: #0C1520;
    border-radius: 8px;
}
QTabWidget#captureTabs QTabBar::tab {
    color: #BDD1E2;
    background: #121E29;
    border: 1px solid #365064;
    border-bottom: none;
    padding: 12px 22px;
    font-weight: 700;
}
QTabWidget#captureTabs QTabBar::tab:selected {
    color: white;
    background: #38202C;
    border-bottom: 3px solid #FF4357;
}
QWidget#navRail { background: #0B111A; border-right: 1px solid #25303C; }
QFrame#panel, QFrame#metricCard, QFrame#actionCard, QFrame#infoCard, QFrame#heroBottom {
    background: #111922; border: 1px solid #2A3541; border-radius: 11px;
}
QFrame#actionCard:hover, QFrame#metricCard:hover { border: 1px solid #415569; background: #18232E; }
QFrame#actionCardPrimary {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #36141F, stop:0.72 #19131D, stop:1 #10141C);
    border: 1px solid #E0364E; border-radius: 11px;
}
QFrame#actionCardPrimary:hover { border: 1px solid #FF5969; background: #381B27; }
QMenu {
    background: #131D28; color: #E6F1FC;
    border: 1px solid #445263; border-radius: 7px; padding: 6px;
}
QMenu::item { padding: 9px 28px 9px 15px; border-radius: 5px; }
QMenu::item:selected { background: #393042; color: #FFFFFF; }
QMenu::item:disabled { color: #7C8794; background: transparent; }
QMenu::separator { height: 1px; background: #34404B; margin: 7px 5px; }
QPlainTextEdit { background: #0D141D; color: #E4EFF9;
                 border: 1px solid #425469; border-radius: 8px;
                 padding: 11px; font-size: 12px; }
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

/* Crimson Command reference dashboard: compact glass panels and high contrast */
QFrame#dashboardPanel, QFrame#heroMetric {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
       stop:0 #0D1A21, stop:1 #080F14);
    border: 1px solid #30434D; border-radius: 9px;
}
QFrame#heroMetric {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
       stop:0 #101B24, stop:1 #071016);
    border-color: #21414D;
}
QFrame#actionCard {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
       stop:0 #151C23, stop:1 #090F14);
    border: 1px solid #2C3A43; border-radius: 8px;
}
QFrame#actionCardPrimary {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
       stop:0 #310E1A, stop:.7 #160E15, stop:1 #0A1016);
    border: 1px solid #FF354F; border-radius: 8px;
}
QFrame#actionCard:hover, QFrame#actionCardPrimary:hover {
    border: 1px solid #FF4A61;
}
QFrame#reclaimBand {
    background: #07191F; border: 1px solid #154350; border-radius: 7px;
}
QFrame#findingRow {
    background: transparent; border-bottom: 1px solid #27353D;
    border-radius: 0;
}
QFrame#queueRow {
    background: #0A1920; border: 1px solid #152932; border-radius: 6px;
}
QFrame#queueRow:hover { border-color:#315A68; background:#11232D; }
QFrame#landscapeArt { border:1px solid #35515B; border-radius:7px; }
QFrame#alertCard {
    background: #160F15; border: 1px solid #973048; border-radius: 9px;
}
QLabel#sectionTitle { font-size: 15px; font-weight: 800; color: #F6F8FA; }
QLabel#findingTitle { font-size: 12px; font-weight: 700; color: #F0F5F9; }
QLabel#statBold { font-size:19px; font-weight:900; color:#F5FBFD; }
QLabel#queuePill {
    background: #39131D; color:#FF6275; border: 1px solid #582130;
    border-radius: 10px; font-weight:bold; padding:3px 9px; font-size:11px;
}
QLabel#trend { color: #6EEB86; font-weight: 800; font-size:12px; }
QPushButton#launcherLink, QPushButton#queueLink {
    background: transparent; border: none; border-radius:3px;
    color:#F1F6FA; padding:2px; text-align:left;
    min-height:20px; font-size: 12px; font-weight:600;
}
QPushButton#launcherLink:hover, QPushButton#queueLink:hover {
    color:#4BD6F5; background:#142731;
}
QPushButton#carouselArrow, QPushButton#ellipsis {
    background:#14232C; border:1px solid #2A4452;
    border-radius:15px; min-height:20px; padding: 4px 8px;
    color:#D8E6F0;
}
QPushButton#carouselArrow:hover,QPushButton#ellipsis:hover {
    border-color:#4AD3EF; color:white;
}
QProgressBar#usageTrack { background:#27343E; border:none;
    min-height:6px; max-height:7px; border-radius:3px; }
QProgressBar#usageTrack::chunk { background:#FF4055; border-radius:3px; }
QComboBox { font-size:11px; border-color:#314A59;
    background:#101C25; min-height:23px; padding:4px 8px; }
QPushButton#danger {
    background:#991B2C; border:1px solid #FF465A; color:#FFFFFF;
}
QPushButton#danger:hover { background:#D12B3E; }
QPushButton#navButton { min-height:23px; padding:9px 11px; }
QPushButton#navButton[active="true"] {
    border-left:3px solid #FF344F;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
      stop:0 #421321, stop:1 #110F15);
    color:#FFFFFF;
}

"""
