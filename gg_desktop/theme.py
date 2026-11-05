"""Crimson Command design tokens and a local Qt Widgets stylesheet."""
from __future__ import annotations
from pathlib import Path

COLORS = {
    "canvas": "#090D12",
    "sidebar": "#0B111A",
    "panel": "#10151C",
    "raised": "#181F28",
    "border": "#2B323C",
    "text": "#F4F7FC",
    "muted": "#A3B4C5",
    "red": "#FF4357",
    "cyan": "#42D4F2",
    "green": "#69DEA7",
    "amber": "#FFD08E",
    "pale": "#D7E1ED",
}

# One shared system for the shell, native controls and evidence workspaces.
# Keep photographic imagery in the supplied heroes; functional surfaces stay flat.
STYLE = r"""
QWidget {font-family:"Segoe UI Variable", "Segoe UI", Arial; font-size:12px; color:#E8EDF2;}
QMainWindow, QWidget#appRoot, QWidget#scrollBody, QScrollArea {background:#090D12;}
QFrame {border:0;}
QLabel {background:transparent;}
QDialog, QMessageBox, QInputDialog, QFileDialog, QDialogButtonBox {background:#11161D;color:#F0F3F7;}
QDialog QLabel {color:#E8EDF2;}
QFrame#navRail, QWidget#navRail, QWidget#navBody, QScrollArea#navScroll {background:#0B1017;border-right:1px solid #2B3038;}
QPushButton#navButton {
    border:0;border-radius:0;background:transparent;color:#D8DFE7;text-align:left;
    font-size:15px;font-weight:550;padding:7px 14px;min-height:29px;
}
QPushButton#navButton:hover {background:#251720;color:white;}
QPushButton#navButton[active="true"] {background:#491724;border-left:3px solid #F34256;color:white;font-weight:700;}
QLabel#brand {font-size:22px;font-weight:800;letter-spacing:.3px;}
QLabel#brandKicker {font-size:10px;color:#9EAAB8;letter-spacing:1px;}
QLineEdit#globalSearch {background:#0C1118;border:1px solid #3D4652;border-radius:7px;min-height:31px;padding:6px 15px;font-size:14px;}
QPushButton#chromeButton {border:0;background:transparent;min-width:24px;padding:4px;color:#B6C3CF;}
QPushButton#chromeButton:hover {background:#28212A;color:white;}
QFrame#hero, QFrame#referenceHero, QFrame#landscapeArt {background:transparent;border:0;}
QLabel#heroTitle, QLabel#pageTitle, QLabel#sceneTitle {font-size:30px;font-weight:750;color:#F5F6F8;}
QLabel#sceneDescription {font-size:12px;color:#B9C1CD;}
QLabel#sectionTitle {font-size:14px;font-weight:700;color:#F0F2F5;}
QLabel#eyebrow, QLabel#sceneKicker {font-size:10px;font-weight:700;color:#E36A7B;letter-spacing:1px;}
QLabel#caption, QLabel#helper {font-size:11px;color:#A2ADBA;}
QLabel#subtle {font-size:12px;color:#BCC5D0;}
QLabel#warning {font-size:11px;color:#E8BD82;}
QLabel#successText {color:#77C9A1;}
QLabel#dangerText {color:#F28594;}
QFrame#panel, QFrame#dashboardPanel, QFrame#infoCard,
QFrame#graphicCard, QFrame#ggAccentPanel, QFrame#approvedSettingsMiniCard,
QFrame#approvedSettingsStatusPage, QFrame#premiumInspector, QFrame#contextPanel {
    background:#10151C;border:1px solid #2B323C;border-radius:4px;
}
QFrame#ggAccentPanel[accent="red"] {border-top:1px solid #9C3C50;}
QFrame#ggAccentPanel[accent="cyan"] {border-top:1px solid #376A78;}
QFrame#ggAccentPanel[accent="green"] {border-top:1px solid #366B58;}
QFrame#ggAccentPanel[accent="purple"] {border-top:1px solid #665474;}
QFrame#ggAccentPanel[accent="amber"] {border-top:1px solid #826441;}
QFrame#ggActionStrip, QFrame#ggToolBanner {background:#10151C;border:1px solid #303741;border-radius:4px;}
QFrame#ggStatusChip {background:transparent;border:0;border-right:1px solid #303640;border-radius:0;}
QFrame#ggEmptyHero, QFrame#ggAssistantCard {background:#10151C;border:1px solid #2B323C;border-radius:4px;}
QFrame#approvedOverviewPanel {background:transparent;border:0;border-right:1px solid #29313B;border-radius:0;}
QFrame#approvedGraveStat, QFrame#approvedUndoStat, QFrame#approvedDNAMetric {background:transparent;border:0;border-right:1px solid #303640;border-radius:0;}
QFrame#approvedDNABand, QWidget#approvedMetrics, QFrame#approvedSettingsTabs {background:transparent;border:0;}
QPushButton {
    background:#181F28;color:#E1E7EE;border:1px solid #35404D;border-radius:4px;
    min-height:20px;padding:5px 9px;font-size:12px;font-weight:550;
}
QPushButton:hover {background:#24232C;border-color:#7C4658;color:white;}
QPushButton:pressed {background:#38202B;}
QPushButton:disabled {background:#141920;border-color:#29303A;color:#75808F;}
QPushButton:focus {border-color:#C25A70;}
QPushButton#primary, QPushButton#approvedCleanupCTA {
    background:#9C253B;border:1px solid #C8475D;color:white;font-weight:700;
    min-height:22px;padding:6px 10px;
}
QPushButton#primary:hover, QPushButton#approvedCleanupCTA:hover {background:#B73048;border-color:#EA6277;}
QPushButton#danger {background:#652233;border:1px solid #B44057;color:#FFDEE3;min-height:22px;padding:6px 10px;font-weight:700;}
QPushButton#danger:hover {background:#8D283F;color:white;}
QPushButton#primary:disabled, QPushButton#danger:disabled, QPushButton#approvedCleanupCTA:disabled {
    background:#141920;border-color:#29303A;color:#75808F;
}
QPushButton#link, QPushButton#launcherLink, QPushButton#queueLink {background:transparent;border:0;color:#8DCDD9;padding:4px;}
QPushButton#link:hover, QPushButton#launcherLink:hover, QPushButton#queueLink:hover {color:#DAF5FA;}
QPushButton#approvedAction, QPushButton#contextAction {background:transparent;border:0;border-bottom:1px solid #2A3039;border-radius:0;text-align:left;min-height:22px;padding:6px 3px;font-size:12px;}
QPushButton#approvedAction:hover, QPushButton#contextAction:hover {background:#241B24;color:white;}
QPushButton#approvedMetric {background:transparent;border:0;border-bottom:2px solid #303844;border-radius:0;text-align:left;padding:6px 9px;}
QPushButton#approvedMetric:hover {background:#151C25;border-bottom-color:#D7465C;}
QPushButton#approvedCover {background:#0B1017;border:1px solid #2B333E;border-radius:4px;padding:0;text-align:center;}
QPushButton#approvedCover:hover {border:1px solid #CC4058;background:#211922;}
QPushButton#approvedDiscoveryTile {background:#10151C;border:1px dashed #46515F;border-radius:4px;font-size:12px;color:#D7E4EE;}
QPushButton#approvedDiscoveryTile:hover {background:#211923;border-color:#C74A60;}
QPushButton#approvedSettingsTab {background:transparent;border:0;border-bottom:2px solid #303640;border-radius:0;min-height:23px;padding:5px 8px;font-size:12px;font-weight:650;}
QPushButton#approvedSettingsTab[active="true"] {background:#5C2031;border-bottom:2px solid #E64B62;color:white;}
QPushButton#approvedAIModeActive {background:#662136;border:0;border-left:2px solid #E54B62;border-radius:2px;text-align:left;padding:7px 8px;font-size:12px;font-weight:700;}
QPushButton#approvedAIWorkflow {background:transparent;border:0;border-bottom:1px solid #29303A;border-radius:0;text-align:left;padding:7px 8px;font-size:12px;}
QPushButton#approvedAIWorkflow:hover {background:#231B25;}
QPushButton#approvedAIQuickTile {background:#141A23;border:1px solid #353442;border-radius:4px;padding:8px;font-size:12px;}
QPushButton#approvedAIQuickTile:hover {background:#2F1D2B;border-color:#AF405A;}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background:#0C1118;color:#E1E7EE;border:1px solid #333C48;border-radius:3px;
    min-height:21px;padding:5px 8px;font-size:12px;selection-background-color:#632C41;selection-color:white;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {border-color:#B94A60;}
QComboBox::drop-down {border:0;width:20px;}
QComboBox::down-arrow {image:url("ASSET_ROOT/control-chevron.svg");width:10px;height:7px;}
QComboBox QAbstractItemView {background:#151C25;color:#E8EDF2;selection-background-color:#632C41;}
QPlainTextEdit, QTextEdit, QTextBrowser {background:#0C1118;color:#D5DFE9;border:1px solid #333B47;border-radius:3px;padding:8px;font-size:12px;selection-background-color:#632C41;}
QTableWidget, QTreeWidget, QListWidget {background:#0C1118;alternate-background-color:#101820;color:#DDE5ED;border:1px solid #2C3540;border-radius:3px;padding:0;gridline-color:#222B35;font-size:12px;selection-background-color:#542336;selection-color:white;}
QTableWidget::item, QTreeWidget::item {padding:4px 6px;border-bottom:1px solid #222B35;}
QTableWidget::item:selected, QTreeWidget::item:selected {background:#542336;color:white;}
QHeaderView::section {background:#151C25;color:#B4C0CE;border:0;border-bottom:1px solid #35404D;padding:6px;font-size:10px;font-weight:650;}
QTableCornerButton::section {background:#151C25;border:0;}
QListWidget::item {padding:7px;border-bottom:1px solid #29313B;}
QListWidget::item:selected {background:#542336;color:white;}
QScrollArea {border:0;}
QScrollArea#approvedLibraryScroll {background:transparent;border:0;}
QWidget#qt_scrollarea_viewport {background:transparent;}
QScrollBar:vertical {background:#10151C;width:8px;margin:0;}
QScrollBar::handle:vertical {background:#39424F;min-height:30px;border-radius:4px;}
QScrollBar::handle:vertical:hover {background:#626778;}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {height:0;}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {background:transparent;}
QScrollBar:horizontal {background:#10151C;height:8px;margin:0;}
QScrollBar::handle:horizontal {background:#39424F;min-width:30px;border-radius:4px;}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {width:0;}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {background:transparent;}
QCheckBox {spacing:7px;font-size:12px;}
QCheckBox::indicator, QAbstractItemView::indicator {width:13px;height:13px;border:1px solid #667180;border-radius:2px;background:#0C1118;}
QCheckBox::indicator:checked, QAbstractItemView::indicator:checked {background:#AB354C;border-color:#F17A8E;image:url("ASSET_ROOT/control-check.svg");}
QCheckBox::indicator:disabled {border-color:#4D5865;}
QProgressBar {background:#252D38;border:0;border-radius:3px;text-align:center;min-height:8px;font-size:10px;}
QProgressBar::chunk {background:#52B8C9;border-radius:3px;}
QMenu {background:#141A23;color:#E1E7EF;border:1px solid #46515E;padding:4px;}
QMenu::item {padding:7px 25px 7px 10px;}
QMenu::item:selected {background:#542336;color:white;}
QMenu::item:disabled {color:#778392;}
QMenu::separator {height:1px;background:#303945;margin:5px;}
QToolTip {background:#18202A;color:#EDF3F8;border:1px solid #586576;padding:5px;}
QTabWidget::pane {background:#10151C;border:1px solid #303945;border-radius:3px;}
QTabBar::tab {background:#141B24;color:#ACB9C8;border:0;border-bottom:2px solid #303945;padding:7px 14px;font-size:12px;}
QTabBar::tab:selected {background:#391C2B;border-bottom-color:#E34B62;color:white;}
QSplitter::handle {background:#242E39;}
QSplitter::handle:hover {background:#AD4259;}
QFrame#actionCard, QFrame#referenceLibrary, QFrame#gameCover, QFrame#modLocationCard {background:#11171F;border:1px solid #303743;border-radius:4px;}
QFrame#actionCard:hover, QFrame#gameCover:hover, QFrame#modLocationCard:hover {background:#211A25;border-color:#A7445A;}
QFrame#actionCardPrimary {background:#23151E;border:1px solid #7F3449;border-radius:4px;}
QFrame#actionCardPrimary:hover {background:#311A27;border-color:#D9516A;}
QLabel#gameCoverArt {background:#0A1017;border:0;}
QLabel#gameCoverTitle {font-size:13px;color:#F0F3F7;font-weight:700;}
QLabel#gameCoverLauncher {font-size:10px;color:#ABB7C6;}
QLabel#premiumTitle {font-size:17px;font-weight:700;color:#F0F3F7;}
QLabel#premiumMetric, QLabel#graphicValue {font-size:22px;font-weight:700;color:#EAF0F5;}
QLabel#premiumState {font-size:11px;font-weight:650;color:#80CDB0;}
QLabel#premiumPath {background:#0C1118;border:1px solid #303945;border-radius:3px;padding:7px;color:#B7C5D3;font-size:11px;}
QFrame#metricCard, QFrame#heroMetric {background:transparent;border:0;border-right:1px solid #303945;border-radius:0;}
QLabel#metricValue, QLabel#statBold, QLabel#heroMetric {font-size:24px;font-weight:750;color:#F0F3F7;}
QFrame#findingRow, QFrame#queueRow {background:transparent;border:0;border-bottom:1px solid #29333D;border-radius:0;}
QLabel#findingTitle {font-size:12px;font-weight:650;}
QLabel#queuePill {background:#203126;color:#9AD7AF;border:1px solid #395944;border-radius:3px;padding:3px;font-size:10px;}
QFrame#featureStep, QFrame#radarFocus, QFrame#reclaimBand, QFrame#alertCard {background:#111A21;border:1px solid #31404C;border-radius:4px;}
QLabel#featureNumber {font-size:20px;color:#73C7D6;font-weight:700;}
QFrame#inspectorFacts {background:transparent;border:0;}
QFrame#inspectorFactRow {background:transparent;border:0;border-bottom:1px solid #272F39;}
QLabel#factKey {font-size:11px;color:#A6B2C0;}
QLabel#factValue {font-size:11px;color:#DCE5EE;font-weight:600;}
QLabel#detailSection {font-size:10px;font-weight:700;color:#A3AFBF;letter-spacing:.5px;}
QFrame#detailRule {background:#2B333D;min-height:1px;max-height:1px;}
"""
STYLE = STYLE.replace("ASSET_ROOT", (Path(__file__).resolve().parent / "assets").as_posix())

STYLE += r'''
QWidget#referencePageBody, QScrollArea#referencePage {background:transparent;border:0;}
QFrame#referenceSearch {background:rgba(13,17,21,210);border:1px solid #4A5058;border-radius:12px;}
QFrame#referenceSearch QLineEdit#globalSearch {background:transparent;border:0;padding:0;min-height:25px;font-size:16px;color:#EEF0F3;}
QLabel#referenceKeycap {font-size:14px;background:rgba(106,111,117,55);border:1px solid #42474C;border-radius:6px;color:#F0F0F2;}
QPushButton#chromeButton {border:0;border-radius:5px;padding:0;background:transparent;}
QPushButton#chromeButton:hover {background:rgba(105,56,69,95);}
QFrame#referenceGlassPanel {background:transparent;border:0;}
'''
STYLE += r'''
QPushButton#navButton {min-height:46px;max-height:46px;padding:0;border:0;background:transparent;}
'''
STYLE += r'''
QWidget#navBody, QScrollArea#navScroll {border:0;}
'''
