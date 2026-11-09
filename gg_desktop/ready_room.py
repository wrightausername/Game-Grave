"""The reference Ready Room, built from real, keyboard-accessible Qt widgets.

Artwork is local; no screenshot is used as an interactive surface. Reference
fixtures are available only via the explicit design-preview launch option.
"""
from __future__ import annotations

from pathlib import Path
import shutil

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QColor, QFont, QFontDatabase, QKeySequence, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QShortcut,
)
from PySide6.QtWidgets import (
    QBoxLayout, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy,
    QWidget,
)

from gg_desktop.reference_widgets import brand_scaled, brand_source  # noqa: F401
from gg_desktop.ready_room_icons import icon, icon_label
from gg_desktop.ready_room_data import live_ready_room, reference_ready_room
from gg_desktop.ready_room_actions import ReadyRoomActions
from gg_desktop.widgets import ScrollPage, button, column, label, row

ASSETS = Path(__file__).parent / "assets" / "ready_room"
TONES = {
    "red": "#F32D47", "purple": "#C175D8", "amber": "#DFAC46",
    "cyan": "#4DD8E2", "blue": "#6CAFE6", "green": "#35DC7C",
    "muted": "#9AA4AC",
}

READY_STYLE = """
QWidget#readyBody, QScrollArea#readyRoom, QScrollArea#readyRoom > QWidget > QWidget {
    background: transparent; border: none;
}
QLabel#readyTitle { font-family: Arial; font-size: 36px; font-weight: 700; }
QLabel#readySubtitle { font-size: 16px; color: #E0E1E3; }
QLabel#readyHeading { font-size: 20px; font-weight: 700; color: #F2F1F3; }
QLabel#readyDetail { font-size: 12px; color: #C8C9CD; }
QLabel#readyGameTitle { font-size: 15px; font-weight: 700; color: #F3F2F4; }
QLabel#readyWhen { font-size: 12px; color: #CACBD0; }
QLabel#readyMetricValue { font-size: 22px; font-weight: 600; }
QLabel#readyMetricCaption { font-size: 13px; color: #D5D7DB; }
QLabel#readyState { font-size: 23px; font-weight: 600; }
QLabel#readyBackupTitle { font-size: 20px; font-weight: 500; }
QLabel#readyEmptyTitle { font-size: 19px; font-weight: 600; }
QLabel#readyEmptyDetail { font-size: 14px; color: #AAB4BE; }
QPushButton#readyMetric { background: transparent; border: none; border-radius: 0; padding: 0; min-height: 0; }
QPushButton#readyMetric:hover { background: rgba(255,255,255,5); }
QPushButton#readyMetric:focus { border: 1px solid #4DD8E2; }
QPushButton#readyLink {
    font-size: 12px; font-weight: 400; background: transparent;
    border: none; padding: 0; min-height: 20px;
}
QPushButton#readyLink:hover { color: #FF5269; }
QPushButton#readyLink:focus { border-bottom: 1px solid #4DD8E2; }
QPushButton#readyButton, QPushButton#readyPrimary {
    font-size: 14px; font-weight: 400; min-height: 30px; max-height: 30px; padding: 0 8px;
    border: 1px solid #414B56; border-radius: 6px;
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #192129,stop:1 #090F15);
}
QPushButton#readyButton:hover { border-color: #718393; background: #1C2831; }
QPushButton#readyPrimary {
    border-color: #E32C43;
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #F52F48,stop:.08 #B9162D,stop:.55 #730A18,stop:.92 #960D25,stop:1 #EB2544);
}
QPushButton#readyPrimary:hover { background: #AC172A; border-color: #FF5269; }
QPushButton#readyButton:focus, QPushButton#readyPrimary:focus { border: 2px solid #4DD8E2; }
QPushButton#readyItem { background: transparent; border: none; border-radius: 3px; padding: 0; }
QPushButton#readyItem:hover { background: rgba(120,150,175,16); }
QPushButton#readyItem:focus { border: 1px solid #4DD8E2; }
"""


def fitted_text(text, role, *, wrap=False):
    result = label(text, role, wrap=wrap)
    result.setTextFormat(Qt.PlainText)
    result.setMinimumWidth(0)
    result.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    result.setToolTip(text)
    return result


class ReadyRoomBackground(QWidget):
    """Gaming-room picture behind the title: the same full-width HD picture as the top bar, continued below it."""
    ART = "banner_ready_room.jpg"
    ART_HEIGHT = 98

    def __init__(self):
        super().__init__()
        self.setObjectName("mainCanvas")

    def paintEvent(self, event):
        from gg_desktop.header_banner import paint_slice
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#05090C"))
        bar = getattr(getattr(self.window(), "top_bar", None), "height", lambda: 46)()
        area = QRectF(0, 0, self.width(), self.ART_HEIGHT)
        painter.save()
        painter.setClipRect(area)
        paint_slice(painter, self.ART, area, top_height=bar, total_height=bar + self.ART_HEIGHT,
                    dpr=self.devicePixelRatioF(), is_top=False)
        painter.restore()
        bottom = QLinearGradient(0, 60, 0, 99)
        bottom.setColorAt(0, QColor(5, 9, 12, 0))
        bottom.setColorAt(1, QColor("#05090C"))
        painter.fillRect(QRectF(0, 60, self.width(), 40), bottom)


class ReadyPanel(QFrame):
    def __init__(self, title, subtitle, glyph, *, artwork="", trailing=None):
        super().__init__()
        self.setObjectName("readyPanel")
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.art = QPixmap(str(ASSETS / (artwork + ".png"))) if artwork else QPixmap()
        self.primary_glow = glyph in ("puzzle", "save")
        self.stack = column(spacing=0)
        self.setLayout(self.stack)
        header = QWidget()
        header.setFixedHeight(48 if not artwork else 51)
        heading = row(spacing=18 if glyph == "gamepad" else 15,
                      margins=(12 if glyph == "gamepad" else 14,
                               7 if artwork else 5, 13, 5 if artwork else 4))
        header.setLayout(heading)
        heading.addWidget(icon_label(glyph, TONES["red"], 38 if glyph == "gamepad" else 30))
        words = column(spacing=0)
        title_label = fitted_text(title, "readyHeading")
        title_label.setFixedHeight(24)
        detail_label = fitted_text(subtitle, "readyDetail")
        detail_label.setFixedHeight(15)
        words.addWidget(title_label)
        words.addWidget(detail_label)
        heading.addLayout(words, 1)
        if trailing:
            heading.addWidget(trailing)
        self.stack.addWidget(header)
        self.body = QWidget()
        self.body_layout = column(spacing=0, margins=(12, 3, 11, 7))
        self.body.setLayout(self.body_layout)
        self.stack.addWidget(self.body, 1)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        area = QRectF(self.rect()).adjusted(.5, .5, -.5, -.5)
        clip = QPainterPath()
        clip.addRoundedRect(area, 12, 12)
        painter.setClipPath(clip)
        bg = QLinearGradient(0, 0, 0, self.height())
        bg.setColorAt(0, QColor("#101418"))
        bg.setColorAt(.23, QColor("#080E12"))
        bg.setColorAt(1, QColor("#050A0E"))
        painter.fillRect(area, bg)
        if not self.art.isNull():
            target = QRectF(self.width() - self.art.width() - 1, 1,
                            self.art.width(), 50)
            painter.drawPixmap(target, self.art, QRectF(self.art.rect()))
            fade = QLinearGradient(target.left(), 0, target.right(), 0)
            fade.setColorAt(0, QColor("#0D1317"))
            fade.setColorAt(.55, QColor(8, 14, 18, 110))
            fade.setColorAt(1, QColor(8, 14, 18, 8))
            painter.fillRect(target, fade)
        painter.setPen(QColor("#30353C"))
        painter.drawLine(12, 48 if self.art.isNull() else 51,
                         self.width() - 12, 48 if self.art.isNull() else 51)
        if self.primary_glow:
            glow = QRectF(self.width()/2 + 6, self.height()-44, self.width()/2-18, 32)
            painter.setBrush(Qt.NoBrush)
            for spread, alpha in ((12, 5), (8, 9), (4, 16), (1, 30)):
                painter.setPen(QPen(QColor(255, 19, 51, alpha), spread))
                painter.drawRoundedRect(glow, 6, 6)
        edge = QLinearGradient(0, 0, self.width(), self.height())
        edge.setColorAt(0, QColor("#904052"))
        edge.setColorAt(.25, QColor("#41464F"))
        edge.setColorAt(1, QColor("#36424C"))
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(edge, 1))
        painter.drawRoundedRect(area, 12, 12)
        painter.setPen(QColor(255, 255, 255, 10))
        painter.drawRoundedRect(area.adjusted(2, 2, -2, -2), 10, 10)


class MetricButton(QPushButton):
    def __init__(self, caption, value, glyph, tone, action):
        super().__init__()
        self.setObjectName("readyMetric")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAccessibleName(caption + ": " + value)
        self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(action)
        self.color = TONES[tone]
        self.setFocusPolicy(Qt.StrongFocus)
        contents = row(spacing=17, margins=(40, 0, 6, 9))
        self.setLayout(contents)
        contents.addWidget(icon_label(glyph, self.color, 30))
        words = column(spacing=0)
        words.addWidget(label(value, "readyMetricValue"))
        words.addWidget(label(caption, "readyMetricCaption"))
        contents.addLayout(words, 1)
        for child in self.findChildren(QWidget):
            child.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        line = QLinearGradient(16, 0, self.width() - 16, 0)
        line.setColorAt(0, QColor(0, 0, 0, 0))
        line.setColorAt(.5, QColor(self.color))
        line.setColorAt(1, QColor(0, 0, 0, 0))
        for width, alpha in ((8, .025), (5, .06), (3, .16), (1.5, .9)):
            painter.setOpacity(alpha)
            painter.setPen(QPen(line, width))
            painter.drawLine(24, self.height() - 7, self.width() - 16, self.height() - 7)
        painter.setOpacity(1)
        painter.setPen(QColor("#30343A"))
        painter.drawLine(self.width() - 1, 12, self.width() - 1, 44)


def thumbnail(artwork, kind, width, height):
    result = QLabel()
    result.setFixedSize(width, height)
    if artwork:
        result.setPixmap(QPixmap(str(ASSETS / f"{artwork}_{kind}.png")).scaled(
            width, height, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
    else:
        result.setPixmap(icon("gamepad", "#778993", 28).pixmap(QSize(28, 28)))
        result.setAlignment(Qt.AlignCenter)
        result.setStyleSheet("background:#111B23;border:1px solid #33414D;border-radius:5px;")
    return result


def status_badge(text, tone, glyph, *, bordered=True):
    frame = QFrame()
    color = TONES[tone]
    rgb = QColor(color)
    frame.setFixedSize(108 if bordered else 106, 29)
    if bordered:
        frame.setStyleSheet(
            f"QFrame {{ border:1px solid rgba({rgb.red()},{rgb.green()},{rgb.blue()},115);"
            f"border-radius:6px; background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            f"stop:0 rgba({rgb.red()},{rgb.green()},{rgb.blue()},28),stop:1 #080e12); }}"
            "QLabel { border:none;background:transparent; }")
    contents = row(spacing=7, margins=(7 if bordered else 3, 0, 3, 0))
    frame.setLayout(contents)
    contents.addWidget(icon_label(glyph, color, 18))
    words = label(text)
    size = 11 if len(text) > 13 else 12
    words.setStyleSheet(f"color:{color};font-size:{size}px;font-weight:500;")
    contents.addWidget(words, 1)
    frame.setAccessibleName(text)
    return frame


def item_button(action, name):
    control = button("", action, kind="readyItem")
    control.setAccessibleName(name)
    control.setToolTip(name)
    control.setMinimumHeight(40)
    control.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    control.setCursor(Qt.PointingHandCursor)
    return control


def action_button(text, action, glyph="", *, primary=False):
    result = button(text, action, kind="readyPrimary" if primary else "readyButton")
    result.setFixedHeight(32)
    if glyph:
        result.setIcon(icon(glyph, "#E9D8DE" if primary else "#D6DDE2", 20))
        result.setIconSize(QSize(20, 20))
    return result


class HealthGauge(QWidget):
    def __init__(self, score, *, caption="System Ready", note="", action=None):
        super().__init__()
        self.score = score
        self.caption = caption
        self.action = action
        self.setFixedSize(123, 119)
        self.setAccessibleName(f"{caption}: {score}%" if score is not None
                               else "System health has not been verified")
        self.setToolTip(note)
        if action:
            self.setFocusPolicy(Qt.StrongFocus)
            self.setCursor(Qt.PointingHandCursor)
            self.setAccessibleDescription("Open the local check results. " + note)

    def mouseReleaseEvent(self, event):
        if self.action and event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.action()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if self.action and event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.action()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        arc = QRectF(12, 12, 98, 98)
        painter.setPen(QPen(QColor("#222F36"), 8))
        painter.drawArc(arc, 225 * 16, -270 * 16)
        if self.score is not None:
            for size, opacity in ((18, .025), (13, .08), (8, 1)):
                painter.setOpacity(opacity)
                gradient = QLinearGradient(12, 98, 100, 15)
                gradient.setColorAt(0, QColor("#7BE500"))
                gradient.setColorAt(.5, QColor("#13E50A"))
                gradient.setColorAt(1, QColor("#40D70B"))
                painter.setPen(QPen(gradient, size))
                painter.drawArc(arc, 225 * 16, -int(270 * 16 * self.score / 100))
            painter.setOpacity(1)
        painter.setPen(QColor("#F5F3F6"))
        font = QFont("Roboto Condensed")
        font.setPixelSize(27)
        font.setWeight(QFont.DemiBold)
        painter.setFont(font)
        painter.drawText(QRectF(9, 36, 107, 37), Qt.AlignCenter,
                         f"{self.score}%" if self.score is not None else "—")
        font.setPixelSize(11)
        font.setWeight(QFont.Normal)
        painter.setFont(font)
        painter.setPen(QColor("#D0D3D9"))
        painter.drawText(QRectF(7, 71, 110, 16), Qt.AlignCenter,
                         self.caption if self.score is not None else "Not verified")


def data_is_reference(data):
    return bool(getattr(data, "reference", False))


class ReadyRoomContent(ScrollPage):
    def __init__(self, window, data, search=None):
        super().__init__()
        self.setObjectName("readyRoom")
        font_id = QFontDatabase.addApplicationFont(str(ASSETS / "RobotoCondensed.ttf"))
        if font_id >= 0:
            self.destroyed.connect(lambda: QFontDatabase.removeApplicationFont(font_id))
        self.setStyleSheet('QWidget { font-family: "Roboto Condensed"; }' + READY_STYLE)
        old_body = self.takeWidget()
        old_body.deleteLater()
        self.body = ReadyRoomBackground()
        self.body.setObjectName("readyBody")
        self.content = column(spacing=0)
        self.body.setLayout(self.content)
        self.setWidget(self.body)
        self.viewport().setAutoFillBackground(False)
        self.body.setAutoFillBackground(False)
        self.window_owner = window
        self.data = data
        self.content.setContentsMargins(11, 6, 9, 30)
        self.content.setSpacing(0)
        header = QWidget()
        header.setFixedHeight(52)
        header_row = row(spacing=12, margins=(10, 12, 10, 8))
        header.setLayout(header_row)
        search_box = QFrame()
        search_box.setObjectName("readySearchBox")
        search_box.setFixedHeight(31)
        search_box.setMaximumWidth(452)
        search_box.setStyleSheet(
            'QFrame#readySearchBox {background:rgba(5,9,12,215);border:1px solid #3B424B;border-radius:8px;}'
            'QLineEdit {background:transparent;border:none;padding:0;font-size:14px;}'
            'QLabel {background:transparent;}')
        search_row = row(spacing=12, margins=(10, 2, 6, 2))
        search_box.setLayout(search_row)
        search_row.addWidget(icon_label("search", "#E0E1E5", 18))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search Ready Room…")
        self.search.setAccessibleName("Search Ready Room")
        self.search.textChanged.connect(self.filter_rows)
        search_row.addWidget(self.search, 1)
        hint = label("Ctrl + K")
        hint.setStyleSheet("font-size:12px;color:#D0D3D9;background:#181E24;border-radius:4px;padding:2px 6px;")
        search_row.addWidget(hint)
        header_row.addWidget(search_box, 1)
        if data.reference:
            tag = label("REFERENCE PREVIEW · SAMPLE DATA")
            tag.setStyleSheet("font-size:10px;color:#AAB1BA;")
            header_row.addWidget(tag)
        header_row.addStretch()
        self.content.addWidget(header)
        if search is not None:
            header.hide()
            self.search = search
            search.textChanged.connect(self.filter_rows)
        elif hasattr(window, "global_search"):
            header.hide()
            window.global_search.textChanged.connect(self.filter_rows)
        self.search_shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        self.search_shortcut.activated.connect(window.global_search.setFocus if hasattr(window, "global_search") else self.search.setFocus)
        if search is not None:
            self.search_shortcut.setEnabled(False)
        self.clear_search_shortcut = QShortcut(QKeySequence("Escape"), self)
        self.clear_search_shortcut.activated.connect(self.search.clear)
        self.scan_shortcut = QShortcut(QKeySequence("F5"), self)
        self.scan_shortcut.activated.connect(window.start_scan)
        if hasattr(window, "global_search"):
            self.scan_shortcut.setEnabled(False)
            self.clear_search_shortcut.setEnabled(False)
        hero = QWidget()
        hero.setFixedHeight(94)
        hero_row = row(spacing=12, margins=(13, 8, 0, 0))
        hero.setLayout(hero_row)
        slash = label("/")
        slash.setStyleSheet("color:#F02640;font-family:Arial;font-weight:700;font-size:52px;")
        slash.setFixedWidth(21)
        slash.setAlignment(Qt.AlignTop)
        hero_row.addWidget(slash)
        words = column(spacing=0)
        words.addWidget(label("Ready Room", "readyTitle"))
        words.addWidget(label("Your mission hub for updates, patches, mod alerts, and a\n"
                              "live pulse on your games.", "readySubtitle"))
        words.addStretch()
        hero_row.addLayout(words)
        hero_row.addStretch()
        self.content.addWidget(hero)

        self.metrics = QWidget()
        self.metrics.setFixedHeight(58)
        self.metrics_grid = QGridLayout(self.metrics)
        self.metrics_grid.setContentsMargins(0, 0, 0, 0)
        self.metrics_grid.setSpacing(0)
        self.metric_buttons = []
        self.compact = False
        for caption, value, glyph, tone, stretch in zip(
                ("Game Updates", "Mod Alerts", "Maintenance", "New Releases", "Followed Games"),
                data.counts, ("megaphone", "cube", "calendar", "download", "star"),
                ("red", "purple", "amber", "cyan", "blue"), (223, 200, 200, 209, 210)):
            metric = MetricButton(caption, value, glyph, tone,
                lambda _=False, c=caption: window.ready_metric_details(c))
            metric.setToolTip("Open " + caption + ". " +
                             ("Counts use saved official posts, not pending installations."
                              if caption in ("Game Updates", "Maintenance", "New Releases") else ""))
            self.metric_buttons.append(metric)
            self.metrics_grid.addWidget(metric, 0, len(self.metric_buttons) - 1)
            self.metrics_grid.setColumnStretch(len(self.metric_buttons) - 1, stretch)
        self.content.addWidget(self.metrics)
        self.news_bar = None
        if data.reference:
            self.content.addSpacing(11)
        else:
            self.news_bar = QWidget()
            self.news_bar.setFixedHeight(26)
            news_row = row(spacing=10, margins=(2, 3, 2, 0))
            self.news_bar.setLayout(news_row)
            self.news_status = label("", "readyWhen")
            self.news_status.setTextFormat(Qt.PlainText)
            self.news_status.setMinimumWidth(0)
            self.news_status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            news_row.addWidget(self.news_status, 1)
            self.news_refresh = button("Refresh", window.ready_refresh_news, kind="readyLink")
            self.news_refresh.setAccessibleName("Refresh official Steam news")
            news_row.addWidget(self.news_refresh)
            self.content.addWidget(self.news_bar)
            self.content.addSpacing(4)
            self.update_news_status()

        self.middle = QHBoxLayout()
        self.middle.setSpacing(12)
        self.patches = ReadyPanel("Patch Watch", "Official updates, hotfixes, and maintenance for your games.",
                                 "layers", trailing=button("View All Updates  →",
                                  window.ready_updates, kind="readyLink"))
        self.games = ReadyPanel("Your Games – At a Glance", "Your top played games and what’s happening with them.",
                               "gamepad")
        self.patches.setMinimumHeight(269)
        self.games.setMinimumHeight(269)
        self.middle.addWidget(self.patches, 626)
        self.middle.addWidget(self.games, 404)
        self.content.addLayout(self.middle, 7)
        self.content.addSpacing(14)

        self.bottom = QHBoxLayout()
        self.bottom.setSpacing(12)
        self.mod_panel = self._mod_card()
        self.save_panel = self._save_card()
        self.health_panel = self._health_card()
        for card, stretch in ((self.mod_panel, 354), (self.save_panel, 334), (self.health_panel, 330)):
            card.setMinimumHeight(192)
            self.bottom.addWidget(card, stretch)
        self.content.addLayout(self.bottom, 5)
        self.soulbind = None
        self.blackbox = None
        self.autopsy = None
        if not data.reference:
            # Owner-requested Soulbind panel; the locked photo reference preview never shows it.
            from gg_desktop.soulbind_ui import build_panel
            self.soulbind = build_panel(ReadyPanel, window)
            self.content.addSpacing(14)
            self.content.addWidget(self.soulbind)
            from gg_desktop.blackbox_ui import build_panel as build_blackbox
            self.blackbox = build_blackbox(ReadyPanel, window)
            self.content.addSpacing(14)
            self.content.addWidget(self.blackbox)
            from gg_desktop.autopsy_ui import build_panel as build_autopsy
            self.autopsy = build_autopsy(ReadyPanel, window)
            self.content.addSpacing(14)
            self.content.addWidget(self.autopsy)
        self.filter_rows("")

    def update_news_status(self):
        owner = self.window_owner
        if self.news_bar is None:
            return
        text, busy = owner.ready_news_status()
        self.news_status.setText(text)
        self.news_status.setToolTip(text)
        self.news_refresh.setEnabled(not busy)
        self.news_refresh.setText("Checking…" if busy else "Refresh")

    def filter_rows(self, query):
        for layout in (self.patches.body_layout, self.games.body_layout):
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().hide()
                    item.widget().deleteLater()
        query = query.strip().casefold()
        patches = [p for p in self.data.patches if query in (p.game + " " + p.detail).casefold()]
        games = [g for g in self.data.games if query in g.name.casefold()]
        self.visible_patches = patches
        self.visible_games = games[:5]
        for index, notice in enumerate(patches[:5]):
            control = item_button(lambda _=False, p=notice: self.window_owner.ready_patch_details(p),
                                  notice.game + ": " + notice.status)
            control.setFixedHeight(41)
            contents = row(spacing=12)
            control.setLayout(contents)
            contents.addWidget(thumbnail(notice.artwork, "logo", 140, 38))
            words = column(spacing=0)
            words.addWidget(fitted_text(notice.game, "readyGameTitle"))
            words.addWidget(fitted_text(notice.detail, "readyDetail"))
            contents.addLayout(words, 1)
            when = label(notice.when, "readyWhen")
            when.setFixedWidth(70)
            when.setAlignment(Qt.AlignCenter)
            contents.addWidget(when)
            contents.addWidget(status_badge(notice.status, notice.tone, notice.glyph))
            for child in control.findChildren(QWidget):
                child.setAttribute(Qt.WA_TransparentForMouseEvents)
            self.patches.body_layout.addWidget(control, 1)
            if index < len(patches[:5]) - 1:
                self._separator(self.patches.body_layout)
        for index, game in enumerate(games[:5]):
            control = item_button(lambda _=False, g=game: self.window_owner.ready_game_details(g),
                                  game.name + ": " + game.status)
            control.setFixedHeight(41)
            contents = row(spacing=9)
            control.setLayout(contents)
            contents.addWidget(thumbnail(game.artwork, "portrait", 74, 36))
            contents.addWidget(fitted_text(game.name, "readyGameTitle"), 1)
            played = QWidget()
            played.setFixedWidth(62)
            played.setToolTip("Recorded Steam playtime: highest value among local accounts. Unknown stays unknown.")
            played_row = row(spacing=4)
            played.setLayout(played_row)
            played_row.addWidget(icon_label("clock", "#C9CCD0", 15))
            played_row.addWidget(label(game.hours, "readyWhen"))
            contents.addWidget(played)
            contents.addWidget(status_badge(game.status, game.tone, game.glyph,
                                            bordered=game.tone in ("purple", "amber")))
            for child in control.findChildren(QWidget):
                child.setAttribute(Qt.WA_TransparentForMouseEvents)
            self.games.body_layout.addWidget(control, 1)
            if index < len(games[:5]) - 1:
                self._separator(self.games.body_layout)
        if patches:
            self.patches.body_layout.addStretch()
        if games:
            self.games.body_layout.addStretch()
        if not patches:
            self._empty(self.patches.body_layout,
                        "No matching updates" if query else "Your watch starts here",
                        "Try another game or keyword." if query else
                        self.data.news_note,
                        "Open Patch Watch", self.window_owner.ready_updates)
        if not games:
            self._empty(self.games.body_layout,
                        "No matching games" if query else "Make room for your games",
                        "Try another game title." if query else "Scan your PC to see your installed games here.",
                        "Scan PC", self.window_owner.start_scan)

    @staticmethod
    def _separator(layout):
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background:#222A30;")
        layout.addWidget(line)

    @staticmethod
    def _empty(layout, title, detail, action_text, action):
        box = QWidget()
        words = column(spacing=10, margins=(15, 22, 15, 20))
        box.setLayout(words)
        words.addStretch()
        words.addWidget(label(title, "readyEmptyTitle"))
        words.addWidget(label(detail, "readyEmptyDetail", wrap=True))
        words.addWidget(button(action_text + "  →", action, kind="readyLink"), 0, Qt.AlignLeft)
        words.addStretch()
        layout.addWidget(box, 1)

    def _mod_card(self):
        card = ReadyPanel("Mod Radar", "Mod manager and mod health monitoring.",
                          "puzzle", artwork="mod_landscape")
        card.body_layout.setContentsMargins(13, 8, 12, 12)
        summary = row(spacing=12)
        state_box = QWidget()
        state_box.setFixedWidth(146)
        state = column(spacing=0)
        state.setAlignment(Qt.AlignVCenter)
        state_box.setLayout(state)
        reviewed = self.data.reference or self.data.mod_state == "Reviewed"
        state.addWidget(icon_label("check" if reviewed else "scan",
                                   TONES["green"] if reviewed else TONES["cyan"], 36),
                        0, Qt.AlignHCenter)
        state.addWidget(label(self.data.mod_state, "readyState"), 0, Qt.AlignHCenter)
        note = label(self.data.mod_note, "readyDetail")
        note.setStyleSheet("font-size:11px;color:#D0D1D5;")
        state.addWidget(note, 0, Qt.AlignHCenter)
        summary.addWidget(state_box)
        divider = QFrame()
        divider.setFixedWidth(1)
        divider.setStyleSheet("background:#30373D;")
        summary.addWidget(divider)
        stats = column(spacing=5)
        stats.setAlignment(Qt.AlignVCenter)
        for (value, caption), glyph in zip(self.data.mod_stats, ("cube", "sync", "warning")):
            line = row(spacing=8)
            line.addWidget(icon_label(glyph, "#F1C13E" if glyph == "warning" else "#D6DAE0", 16))
            amount = label(value, "readyGameTitle")
            amount.setFixedWidth(25)
            line.addWidget(amount)
            detail = label(caption, "readyDetail")
            detail.setStyleSheet("font-size:11px;color:#D0D1D5;")
            line.addWidget(detail, 1)
            stats.addLayout(line)
        summary.addLayout(stats, 1)
        card.body_layout.addLayout(summary, 1)
        card.body_layout.addSpacing(10)
        controls = row(spacing=11)
        controls.addWidget(action_button("View Mods  →", lambda: self.window_owner.navigate("Mods")), 152)
        controls.addWidget(action_button("Run Mod Scan", self.window_owner.start_scan, "scan", primary=True), 166)
        card.body_layout.addLayout(controls)
        return card

    def _save_card(self):
        card = ReadyPanel("Save Vault", "Protect and manage your game saves.",
                          "save", artwork="vault_landscape")
        card.body_layout.setContentsMargins(13, 8, 12, 12)
        summary = row(spacing=18, margins=(35, 0, 0, 20))
        summary.addWidget(icon_label("database", "#45DFB1", 40))
        words = column(spacing=2)
        words.addStretch()
        words.addWidget(fitted_text(self.data.backup_title, "readyBackupTitle"))
        note = row(spacing=6)
        note.addWidget(icon_label("check" if self.data.reference else "clock", "#35CD78", 15))
        note.addWidget(fitted_text(self.data.backup_note, "readyDetail"), 1)
        words.addLayout(note)
        words.addStretch()
        summary.addLayout(words, 1)
        card.body_layout.addLayout(summary, 1)
        controls = row(spacing=11)
        controls.addWidget(action_button("Manage Saves  →", self.window_owner.ready_manage_saves), 153)
        controls.addWidget(action_button("Backup Now", self.window_owner._create_save_backup if self.data.reference
                                         else self.window_owner.ready_backup_now, "cloud", primary=True), 144)
        card.body_layout.addLayout(controls)
        return card

    def _health_card(self):
        card = ReadyPanel("System & Game Health", "Quick checks to keep everything running smooth.",
                          "pulse", artwork="health_landscape")
        card.body_layout.setContentsMargins(9, 0, 12, 12)
        summary = row(spacing=12)
        summary.addWidget(HealthGauge(self.data.health_score, caption=self.data.health_caption,
                                      note=self.data.health_note, action=self.window_owner.ready_health_details))
        checks = column(spacing=10, margins=(0, 10, 0, 15))
        checks.setAlignment(Qt.AlignVCenter)
        for title, tone in self.data.health:
            line = row(spacing=8)
            line.addWidget(icon_label("check" if tone == "green" else "help", TONES[tone], 17))
            line.addWidget(fitted_text(title, "readyDetail"), 1)
            checks.addLayout(line)
        summary.addLayout(checks, 1)
        card.body_layout.addLayout(summary, 1)
        return card

    def resizeEvent(self, event):
        compact = event.size().width() < 900
        direction = QBoxLayout.TopToBottom if compact else QBoxLayout.LeftToRight
        if hasattr(self, "middle"):
            self.middle.setDirection(direction)
            self.bottom.setDirection(direction)
            if compact != self.compact:
                self.compact = compact
                self.metrics.setFixedHeight(116 if compact else 58)
                for metric in self.metric_buttons:
                    self.metrics_grid.removeWidget(metric)
                for index in range(5):
                    self.metrics_grid.setColumnStretch(index, 0)
                for index, metric in enumerate(self.metric_buttons):
                    columns = 3 if compact else 5
                    self.metrics_grid.addWidget(metric, index // columns, index % columns)
                    self.metrics_grid.setColumnStretch(index % columns,
                        1 if compact else (223, 200, 200, 209, 210)[index])
        super().resizeEvent(event)


class ReadyRoomPage(ReadyRoomContent):
    """Use the app's native shell and scale, like every other tab."""
    def __init__(self, window, data):
        super().__init__(window, data, window.global_search)
        self._released = False
        self.reference_note = None
        if data.reference:
            self.reference_note = QLabel("REFERENCE PREVIEW · SAMPLE DATA", self.body)
            self.reference_note.setStyleSheet("font-size:9px;color:#72808c;background:transparent;")
            self.reference_note.setAttribute(Qt.WA_TransparentForMouseEvents)
            self._position_reference_note()

    def _position_reference_note(self):
        if self.reference_note is not None:
            self.reference_note.setGeometry(12, max(0, self.body.height()-18), 220, 13)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "reference_note"):
            self._position_reference_note()

    def release_ready_shell(self):
        # The shell never moves. Disconnect only this page's search listener.
        if not self._released:
            self._released = True
            self.search.textChanged.disconnect(self.filter_rows)

    def reference_point(self, widget, point=QPoint()):
        return widget.mapTo(self.window_owner, point)


class ReadyRoomMethods(ReadyRoomActions):
    def ready_room_page(self):
        self.ready_init()
        try:
            disk = shutil.disk_usage(Path.home())
            free_percent = disk.free * 100 / disk.total if disk.total else None
        except OSError:
            free_percent = None
        data = reference_ready_room() if self.reference_preview else live_ready_room(
            self.inventory, disk_free_percent=free_percent, state=self._ready_state,
            evidence=self._ready_evidence if self._ready_evidence_inventory is self.inventory else {})
        self.page_for("Ready Room", page=ReadyRoomPage(self, data))
        self.page.setFocusPolicy(Qt.StrongFocus)
        self.page.setFocus()

        if (not self.reference_preview and self.inventory.scanned_at
                and self._ready_evidence_inventory is not self.inventory and not self._ready_checks_busy):
            QTimer.singleShot(0, self.ready_refresh_checks)
        self.ready_start_live_news()
