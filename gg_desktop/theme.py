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
/* Approved Crimson Command tab system. Same shell, distinct vector scenes. */
QFrame#sceneHeader {
    background: #0D1924; border: 1px solid #304758; border-radius: 11px;
}
QLabel#sceneTitle {
    color: #F5F9FC; font-size: 30px; font-weight: 900;
    letter-spacing: .4px; background: transparent;
}
QLabel#sceneDescription {
    color: #B2C4D2; font-size: 12px; background: transparent;
}
QLabel#sceneKicker {
    color: #43D6F2; font-size: 10px; font-weight: 800;
    letter-spacing: 2px; background: transparent;
}
QFrame#graphicCard {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #10212C, stop:1 #0B1520);
    border: 1px solid #315065; border-radius: 9px;
}
QLabel#graphicValue {
    color: #F4F8FB; font-size: 20px; font-weight: 800;
}
QFrame#featureStep {
    background: #111E29; border: 1px solid #2B4456; border-radius: 8px;
}
QLabel#featureNumber {
    color: #43D6F2; font-size: 20px; font-weight: 800;
}
QFrame#radarFocus {
    background: #0B2831; border: 1px solid #236477; border-radius: 10px;
}
QFrame#gameCover {
    background: #10212C; border: 1px solid #315064;
    border-radius: 9px; padding:0;
}
QFrame#gameCover:hover { border: 2px solid #43D6F2; }

/* Approved artwork-first library and the evidence-backed right inspectors. */
QFrame#premiumInspector {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #21121E, stop:.25 #14131D, stop:1 #09131B);
    border:1px solid #A42A43;
    border-radius:12px;
}
QFrame#premiumInspector QLabel {
    background:transparent;
}
QLabel#premiumTitle {
    color:#F7F8FD; font-size:21px; font-weight:850;
}
QLabel#premiumMetric {
    color:#F9F9FE; font-size:26px; font-weight:900;
}
QLabel#premiumState {
    color:#62E6A0; font-size:12px; font-weight:700;
}
QLabel#premiumPath {
    color:#C4D5E4; font-size:11px;
    background:#0D1A25;
    border:1px solid #304858;
    border-radius:7px; padding:9px;
}
QFrame#premiumInspector QPushButton#primary {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #A41936,stop:.5 #C52843,stop:1 #7E162B);
    color:#FFF;
    border:1px solid #FF5069;
    min-height:27px;
}
QFrame#premiumInspector QPushButton:hover {
    border:1px solid #FF6578;
}
QFrame#modLocationCard {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #261726, stop:.58 #152434, stop:1 #111721);
    border:1px solid #7A3449;
    border-radius:11px;
}
QFrame#modLocationCard:hover {
    background:#2B2031;
    border:2px solid #FF4C65;
}
QFrame#gameCover {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #271622, stop:.45 #192A39, stop:1 #0B1520);
    border:1px solid #714053;
    border-radius:10px;
}
QFrame#gameCover:hover {
    border:2px solid #FF4B63;
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

# Reference-fidelity layer: screenshots are a visual contract, not static UI.
STYLE += r"""
QWidget {font-size:13px;}
QFrame#referenceHero {background:#100B14; border:1px solid #9A2238; border-radius:12px;}
QFrame#referenceLibrary {
    background:#0B0A10; border:1px solid #331724; border-radius:12px;
}
QFrame#referenceLibrary QLabel#sectionTitle {
    font-size:17px;font-weight:850;color:#F6F4F7;
}
QFrame#gameCover {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #2B1421, stop:.68 #10121C,stop:1 #070A10);
    border:1px solid #663344; border-radius:12px; padding:0;
}
QFrame#gameCover:hover {
    background:#2F1724;
    border:2px solid #FF3D59;
}
QFrame#modLocationCard {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #31121F,stop:.62 #12151D,stop:1 #070A10);
    border:1px solid #673145;border-radius:12px;
}
QFrame#modLocationCard:hover {border:2px solid #FF3F5F;}
QFrame#gameCover QLabel#findingTitle,
QFrame#modLocationCard QLabel#findingTitle {
    color:#FCF8FA;font-size:14px;font-weight:850;
}
QFrame#premiumInspector {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #230D1B,stop:.36 #150E17,stop:1 #080B13);
    border:1px solid #A32942;border-radius:13px;
}
QFrame#premiumInspector QLabel#premiumTitle {
    font-size:21px;font-weight:850;color:#FFFFFF;
}
QLabel#premiumMetric {font-size:25px;font-weight:850;color:#FFFFFF;}
QPushButton#referenceSecondary {
    background:#180F19;color:#EBDBE5;border:1px solid #7B293E;
    border-radius:9px;font-size:12px;font-weight:750;
    min-height:28px;text-align:left;padding:11px 14px;
}
QPushButton#referenceSecondary:hover {
    background:#331521;border:1px solid #F3445D;color:white;
}
QPushButton#navButton {
    color:#DBD5DF;font-size:14px;
    padding:10px 12px; min-height:26px;
}
QPushButton#navButton[active="true"] {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #7E1028,stop:.58 #3A101F,stop:1 #140C15);
    border:1px solid #DF2E4C;border-radius:8px;
    color:#FFFFFF;font-weight:800;
}
QComboBox, QLineEdit {
    background:#140F19;color:#F5EAF0;
    border:1px solid #513045;border-radius:8px;
    min-height:28px;font-size:12px;padding:7px 10px;
}
QComboBox:focus,QLineEdit:focus {border:1px solid #F5425D;}
"""

# Final owner-approved cinematic design overlay; changes presentation only.
# It deliberately does not restyle confirmation/error dialogs into low contrast.
STYLE += r"""
QMainWindow, QWidget#appRoot, QWidget#scrollBody {
    background: #070E16; color: #F5F7FB;
}
QWidget { font-family: "Segoe UI Variable", "Segoe UI", Arial; font-size: 13px; }
QFrame#navRail, QWidget#navBody, QScrollArea#navScroll {
    background: #080F18; border: none;
}
QScrollArea#navScroll QWidget#qt_scrollarea_viewport {
    background: #080F18; border: none;
}
QLineEdit#globalSearch {
    min-height: 26px; padding: 9px 15px;
    border: 1px solid #384651; border-radius: 11px;
    color: #F5F7FB; background: #0C141D; font-size: 14px;
}
QLineEdit#globalSearch:focus { border-color: #F3435B; }
QPushButton#navButton {
    min-height: 29px; padding: 8px 15px;
    border: none; background: transparent; border-radius: 3px;
    color: #E3E8EE; text-align: left; font-size: 14px;
}
QPushButton#navButton:hover { background: #1B2430; color: white; }
QPushButton#navButton[active="true"] {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #71172A, stop:.58 #391722, stop:1 #111822);
    border: none; border-left: 3px solid #FF3D54;
    border-radius: 3px; color: #FFFFFF; font-weight: 800;
}
QFrame#referenceHero, QFrame#hero {
    background: #09151F; border: none; border-radius: 10px;
}
QFrame#panel, QFrame#dashboardPanel {
    background: #0C1721;
    border: 1px solid #273846; border-radius: 10px;
}
QFrame#metricCard, QFrame#heroMetric {
    background: #0B1720; border: 1px solid #253844; border-radius: 9px;
}
QFrame#actionCard {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #131D27, stop:1 #0B141E);
    border: 1px solid #2E404C; border-radius: 10px;
}
QFrame#actionCard:hover {
    background: #19252E; border: 1px solid #AD4354;
}
QFrame#actionCardPrimary {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #2D1420, stop:1 #121A24);
    border: 1px solid #9E354A; border-radius: 11px;
}
QPushButton#primary {
    background: #A71C34; color: #FFFFFF; border: 1px solid #FF4057;
    border-radius: 9px; min-height: 30px; font-weight: 750;
}
QPushButton#primary:hover { background: #C52B43; }
QPushButton#danger { background: #8A1F30; border: 1px solid #E73A4B; }
QLabel#sectionTitle { color: #F7F9FD; font-size: 16px; font-weight: 800; }
QLabel#caption { color: #A5B7C8; font-size: 11px; }
QLabel#eyebrow { color: #F26275; font-size: 11px; font-weight: 750; }
QTableWidget { background: #0A151F; border: 1px solid #273846; }
QTableWidget::item { padding: 8px; border-bottom: 1px solid #182A37; }
QTableWidget::item:selected { color: white; background: #58192B; }
QHeaderView::section {
    background: #14222C; color: #D0E0EC;
    border: none; border-bottom: 1px solid #2E4453;
    padding: 10px; font-weight: 700;
}
"""

# Owner-locked November 2 visual override. Keep these scoped to the desktop
# shell and structural surfaces; do not alter native dark safety prompts.
# Separating fidelity overrides from older preview styling makes future
# screenshot differences auditable without silently changing the theme.
STYLE += r"""
QMainWindow, QWidget#appRoot, QWidget#scrollBody { background: #090B0F; }
QFrame#navRail, QWidget#navBody, QScrollArea#navScroll {
    background: #0A0D12; border-color: #191E25;
}
QPushButton#navButton {
    background: transparent; border: none; border-radius: 5px;
    color: #BAC5D0; font-weight: 550; font-size: 12px;
    min-height: 20px; padding: 8px 14px;
}
QPushButton#navButton:hover { background: #1C1C25; color: #FFFFFF; }
QPushButton#navButton[active="true"] {
    background: #4B1826; color: #FFFFFF;
    border-left: 2px solid #F34B65; font-weight: 750;
}
QLineEdit#globalSearch {
    background: #10141A; color: #F5F6FA;
    border: 1px solid #292F37; border-radius: 6px;
    min-height: 26px; padding: 4px 13px; font-size: 12px;
}
QLineEdit#globalSearch:focus { border: 1px solid #B53449; }
QPushButton#chromeButton {
    background: transparent; color: #C6CED9;
    border: 0; border-radius: 5px;
    min-width: 29px; max-width: 29px; min-height: 29px;
    padding: 3px; font-size: 17px;
}
QPushButton#chromeButton:hover { background: #24202A; color: white; }
QLabel#scanStatus {
    background: #12151C; color: #BEC8D2;
    border-bottom: 1px solid #272C34; padding: 4px 16px;
}
QFrame#referenceHero, QFrame#sceneHeader {
    border-radius: 7px; border: 1px solid #20242C;
}
QWidget#graveyardSummary { background: transparent; }
QFrame#dashboardPanel, QFrame#panel, QFrame#metricCard,
QFrame#actionCard, QFrame#infoCard {
    background: #10141B; border: 1px solid #242B34;
    border-radius: 7px;
}
QFrame#premiumInspector { border: 1px solid #743045; border-radius: 8px; }
QFrame#graphicCard {
    background: #11161D; border: 1px solid #2C343E;
    border-radius: 7px;
}
QTableWidget {
    background: #0C1117; border: 1px solid #28313B;
    gridline-color: #1B2530;
}
QTableWidget::item { padding: 5px 7px; border-bottom: 1px solid #202831; }
QTableWidget::item:selected { background: #532235; color: #FFFFFF; }
QHeaderView::section {
    background: #161A22; color: #BCC8D4;
    padding: 7px 8px; border-bottom: 1px solid #303640;
}
QFrame#landscapeArt { border: 0; border-radius: 0; }
"""


# Owner-locked functional workspaces, applied after all older preview rules.
STYLE += r"""
QFrame#approvedOverviewPanel {
    background:#10141B; border:1px solid #222A33; border-radius:6px;
}
QPushButton#approvedMetric {
    background:#10151D; border:0;
    border-bottom:2px solid #282F3B; border-radius:4px;
    text-align:left; padding:5px;
}
QPushButton#approvedMetric:hover {
    background:#19202B; border-bottom:2px solid #D53C57;
}
QPushButton#approvedAction {
    background:transparent; border:0; border-bottom:1px solid #262E38;
    text-align:left; border-radius:0; font-size:12px;
    color:#DCE5F0; padding:5px 8px; min-height:20px;
}
QPushButton#approvedAction:hover {
    background:#231824; color:white; border-bottom-color:#C33750;
}
QPushButton#approvedCover {
    background:#131721; border:1px solid #2E2D39;
    border-radius:5px; text-align:center; padding:1px;
}
QPushButton#approvedCover:hover {border:1px solid #F0475E;background:#211A27;}
QScrollArea#approvedLibraryScroll {background:transparent; border:none;}
QFrame#approvedGraveStat, QFrame#approvedUndoStat, QFrame#approvedDNAMetric {
    background:#10151D; border:1px solid #292B34; border-radius:5px;
}
QFrame#approvedSettingsTabs {
    background:#10151B; border:1px solid #282C34; border-radius:6px;
}
QPushButton#approvedSettingsTab {
    color:#BBC6D2; background:#171B23; border:1px solid #31313C;
    border-radius:5px; padding:6px 7px; font-size:11px;
    min-height:26px; font-weight:650;
}
QPushButton#approvedSettingsTab:hover {
    color:white; background:#32202C; border-color:#974057;
}
QPushButton#approvedSettingsTab[active="true"] {
    color:white; background:#5B1D30; border:1px solid #D8415B;
    font-weight:850;
}
QFrame#approvedDNABand { background:transparent; }
"""

# November 2 locked composition pass: remove the heavy box outlines left over
# from the engineering preview. Only passive surfaces are affected; danger
# prompts, selection contrast, and actionable buttons keep visible borders.
STYLE += r"""
QFrame#approvedOverviewPanel {
    background: transparent; border: 0; border-radius: 0;
    border-right: 1px solid #29303B;
}
QFrame#approvedGraveStat, QFrame#approvedUndoStat, QFrame#approvedDNAMetric {
    background: transparent; border: 0; border-radius: 0;
    border-right: 1px solid #30303C;
}
QPushButton#approvedMetric {
    background: transparent; border: 0; border-radius: 0;
    border-bottom: 2px solid #34313E;
    padding: 8px 10px; text-align: left;
}
QPushButton#approvedMetric:hover {
    background: #191922; border-bottom: 2px solid #D84259;
}
QFrame#referenceHero, QFrame#hero {
    background: transparent; border: 0; border-radius: 0;
}
QFrame#landscapeArt {background:transparent;border:0;border-radius:0;}
"""

# Owner visual-system calibration: geometry, spacing and contrast are treated as
# shared design tokens. No fake controls, metrics or behavior is introduced.
STYLE += r"""
QMainWindow, QWidget#appRoot, QWidget#scrollBody { background:#080D13; color:#F3F6FA; }
QWidget { font-family:"Segoe UI Variable", "Segoe UI", Arial; font-size:13px; }
QFrame#navRail, QWidget#navBody, QScrollArea#navScroll { background:#091019; }
QPushButton#navButton {
    font-size:15px; font-weight:550; color:#DEE4EB;
    padding:7px 14px; min-height:29px;
    text-align:left; border:0; border-radius:2px;
}
QPushButton#navButton:hover { background:#2A1722; color:#FFFFFF; }
QPushButton#navButton[active="true"] {
    color:#FFFFFF; font-weight:750; background:#631729;
    border:0; border-left:3px solid #F34256;
}
QLineEdit#globalSearch {
    background:#0B111A; color:#F1F5FB; font-size:14px;
    min-height:31px; padding:6px 15px;
    border:1px solid #303A47; border-radius:8px;
}
QLineEdit#globalSearch:focus {border:1px solid #A63248;}
QFrame#panel, QFrame#dashboardPanel {
    background:#0D141D; border:1px solid #293340; border-radius:9px;
}
QFrame#approvedOverviewPanel {background:transparent;border:0;border-right:1px solid #2A3340;border-radius:0;}
QFrame#approvedOverviewPanel:last-child {border-right:0;}
QFrame#approvedGraveStat,QFrame#approvedUndoStat,QFrame#approvedDNAMetric {
    background:transparent;border:0;border-right:1px solid #2B3441;border-radius:0;
}
QFrame#approvedSettingsTabs {background:transparent;border:0;border-radius:0;}
QPushButton#approvedSettingsTab {
    font-size:13px; font-weight:700; min-height:31px;
    border:1px solid #46515D; background:#111B26;
    border-radius:7px;padding:7px 9px;color:#E6ECF3;
}
QPushButton#approvedSettingsTab[active="true"] {
    border:1px solid #F24B5E; background:#A21E36; color:white;
}
QPushButton#approvedSettingsTab:hover {border-color:#E83E55;background:#40202F;color:white;}
QPushButton#primary { min-height:33px; font-size:13px; font-weight:800;
    background:#A51C32; border:1px solid #E4495E; color:white; }
QPushButton#primary:hover { background:#C42C43; }
QPushButton#danger {min-height:32px;font-weight:700;}
QLabel#sectionTitle {color:#F3F5F9;font-size:16px;font-weight:800;}
QLabel#eyebrow {font-size:12px;font-weight:800;color:#FF5971;}
QLabel#caption {font-size:12px;color:#B0BBCB;}
QLabel#subtle {font-size:12px;color:#ADB9C9;}
QTableWidget {background:#090F18;border:1px solid #2D3B49;alternate-background-color:#111B27;}
QTableWidget::item {padding:8px 9px;border-bottom:1px solid #25303A;}
QTableWidget::item:selected {background:#8B2339;color:white;}
QHeaderView::section {font-size:12px;font-weight:800;background:#121D27;color:#D9E5F0;
    border-bottom:1px solid #3D4C5B;padding:8px;}
QFrame#ggAccentPanel {
    background:#111923;border:1px solid #303B48;border-radius:9px;
}
QFrame#ggAccentPanel[accent="red"] {border-top:2px solid #DB314D;}
QFrame#ggAccentPanel[accent="cyan"] {border-top:2px solid #31D1DC;}
QFrame#ggAccentPanel[accent="purple"] {border-top:2px solid #A86BE1;}
QFrame#ggAccentPanel[accent="amber"] {border-top:2px solid #F1B154;}
QFrame#ggAccentPanel[accent="green"] {border-top:2px solid #3BDB91;}
QFrame#ggActionStrip {background:#101820;border:1px solid #263644;border-radius:9px;}
QFrame#ggToolBanner {background:#0C1420;border:1px solid #5F344A;border-radius:9px;}
QFrame#ggStatusChip {background:#131E29;border:1px solid #314454;border-radius:6px;}
QFrame#ggEmptyHero {background:#101721;border:1px solid #30404C;border-radius:10px;}
QFrame#ggAssistantCard {background:#0F1722;border:1px solid #354150;border-radius:9px;}
"""

# Cinematic feature-specific controls: live buttons, no decorative toggles.
STYLE += r"""
QPushButton#approvedAIModeActive {
    border:1px solid #ED4059;border-radius:8px;
    background:#7B1730;color:white;text-align:left;
    min-height:36px;padding:9px 12px;font-size:14px;font-weight:850;
}
QPushButton#approvedAIWorkflow {
    border:1px solid #293846;border-radius:5px;
    background:#101A25;color:#E5EDF5;text-align:left;
    min-height:32px;padding:8px 11px;font-size:13px;
}
QPushButton#approvedAIWorkflow:hover {
    background:#271A2A;border-color:#B43A51;color:white;
}
QPushButton#approvedAIQuickTile {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #30172C,stop:1 #0D1B29);
    color:#F1F5FA;border:1px solid #69415E;border-radius:7px;
    min-height:44px;font-size:13px;font-weight:700;padding:8px;
}
QPushButton#approvedAIQuickTile:hover {
    background:#541E37;border-color:#F14960;
}
QFrame#ggAssistantWelcomeArt {border:0;background:transparent;}
QFrame#approvedSettingsStatusPage {background:#101925;border:1px solid #314252;border-radius:8px;}
"""

# Source-backed feature metric bands; hues are category accents, not alerts.
STYLE += r"""
QFrame#metricCard {background:#101824;border:1px solid #303B48;border-radius:8px;}
QFrame#metricCard[tone="cyan"] {border-bottom:2px solid #4DCFE7;}
QFrame#metricCard[tone="amber"] {border-bottom:2px solid #E6B06B;}
QFrame#metricCard[tone="green"] {border-bottom:2px solid #4DD4A8;}
QFrame#metricCard[tone="purple"] {border-bottom:2px solid #BB93E8;}
QFrame#metricCard[tone="red"] {border-bottom:2px solid #F0455F;}
QLabel#metricValue {font-size:25px;font-weight:850;color:#F5F8FF;}
QFrame#metricCard QLabel#caption {font-size:11px;color:#B7C5D2;}
"""
