"""Ready Room's isolated 1280×720 design surface and scaled native controls.

The shared shell is restored before leaving this page. Other tabs never use
these widgets, fonts, dimensions or styles.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QKeySequence, QLinearGradient, QPainter, QPen, QPixmap, QShortcut, QTransform
from PySide6.QtWidgets import (
    QFrame, QGraphicsScene, QGraphicsView, QLabel, QLineEdit, QPushButton,
    QSizePolicy, QWidget,
)

from gg_desktop.ready_room_icons import icon, icon_label
from gg_desktop.theme import STYLE
from gg_desktop.widgets import row

ASSETS = Path(__file__).parent / "assets"
REFERENCE_WIDTH, REFERENCE_HEIGHT = 1280, 720
RAIL_WIDTH, CHROME_HEIGHT = 219, 46


class NavigationButton(QPushButton):
    def __init__(self, title, symbol, owner, parent):
        super().__init__(parent)
        self.title, self.symbol = title, symbol
        self.active = title == "Ready Room"
        self.setAccessibleName(title + " page")
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.clicked.connect(lambda: owner.navigate(title))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.active:
            glow = QLinearGradient(0, 0, self.width(), 0)
            for stop, color in ((0, "#18080e"), (.18, "#6a0717"),
                                (.45, "#b90b27"), (.72, "#410b17"), (1, "#05090d")):
                glow.setColorAt(stop, QColor(color))
            p.fillRect(self.rect(), glow)
            edge = QLinearGradient(0, 0, self.width(), 0)
            edge.setColorAt(0, QColor(255, 25, 57, 0))
            edge.setColorAt(.4, QColor(255, 40, 65, 220))
            edge.setColorAt(1, QColor(255, 25, 57, 0))
            for y in (1, self.height()-2):
                p.setPen(QPen(edge, 1))
                p.drawLine(0, y, self.width(), y)
        elif self.underMouse():
            p.fillRect(self.rect(), QColor(255, 255, 255, 12))
        glyph = icon(self.symbol, "#eeeeef", 24)
        glyph.paint(p, 35, (self.height()-24)//2, 24, 24)
        font = QFont("Roboto Condensed")
        font.setPixelSize(16)
        font.setWeight(QFont.Medium if self.active else QFont.Normal)
        font.setHintingPreference(QFont.PreferNoHinting)
        p.setFont(font)
        p.setPen(QColor("#f5f4f5" if self.active else "#dedee1"))
        p.drawText(QRectF(80, 0, 130, self.height()), Qt.AlignVCenter, self.title)
        if self.title == "More Tools":
            icon("chevron", "#dddde3", 15).paint(p, 192, 10, 15, 15)
        if self.hasFocus():
            p.setPen(QPen(QColor("#56d3ed"), 1, Qt.DotLine))
            p.drawRect(self.rect().adjusted(2, 2, -3, -3))


class Chrome(QWidget):
    def __init__(self, owner, parent):
        super().__init__(parent)
        self.owner = owner
        self.setGeometry(RAIL_WIDTH, 0, REFERENCE_WIDTH-RAIL_WIDTH, CHROME_HEIGHT)
        self.search_box = QFrame(self)
        self.search_box.setObjectName("readyChromeSearch")
        self.search_box.setGeometry(20, 12, 454, 32)
        self.search_box.setStyleSheet("""
            QFrame#readyChromeSearch {
                background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #101316,stop:.15 #05090b,stop:1 #080d11);
                border:1px solid #41464c; border-radius:7px;
            }
            QLineEdit { background:transparent; border:0; padding:0;
                        color:#efeff0; font-family:"Roboto Condensed"; font-size:14px; }
            QLabel { background:transparent; border:0; }
            QLabel#readyChromeKey { color:#d9dce0; font-size:12px; padding:1px 5px;
                border:1px solid #343b43; border-radius:4px;
                background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #2b3138,stop:1 #10161c); }
        """)
        contents = row(spacing=11, margins=(10, 2, 6, 2))
        self.search_box.setLayout(contents)
        contents.addWidget(icon_label("search", "#e8e9ec", 19))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search games, mods, files, and more...")
        self.search.setAccessibleName("Search Ready Room")
        self.search.setClearButtonEnabled(True)
        contents.addWidget(self.search, 1)
        key = QLabel("Ctrl + K")
        key.setObjectName("readyChromeKey")
        contents.addWidget(key)
        for x, symbol, title, action in (
            (862, "bell", "Notifications", lambda: owner.info("Ready Room status",
                ("REFERENCE PREVIEW · SAMPLE DATA\n\n" if owner.reference_preview else "") + owner.status.text())),
            (900, "help", "Help", lambda: owner.info("Ready Room",
                "Patch Watch opens official game news. Choose a game to inspect its installation.\n\n"
                "View Mods opens Mod Radar. Manage Saves opens backup history. Backup Now creates a verified save archive.\n\n"
                "Ctrl+K: search. F5: scan. Escape: cancel the active scan or clear search.")),
            (952, "minus", "Minimize", owner.showMinimized),
            (986, "square", "Maximize or restore", owner._toggle_maximize),
            (1021, "close", "Close", owner.close),
        ):
            control = QPushButton(self)
            control.setGeometry(x, 7, 28, 28)
            control.setIcon(icon(symbol, "#e9e9ee", 19))
            control.setIconSize(QSize(19, 19))
            control.setAccessibleName(title)
            control.setToolTip(title)
            control.setCursor(Qt.PointingHandCursor)
            control.setStyleSheet("QPushButton{background:transparent;border:0;padding:0;min-height:0;}"
                                 "QPushButton:hover{background:#25252b;border-radius:4px;}"
                                 "QPushButton:focus{border:1px solid #56d3ed;}")
            control.clicked.connect(action)

    def paintEvent(self, event):
        p = QPainter(self)
        art = QPixmap(str(ASSETS / "ready_room/gaming_room.png"))
        p.drawPixmap(QRectF(481, 0, 370, 46), art, QRectF(80, 0, 370, 46))
        p.setPen(QColor("#44434a"))
        p.drawLine(941, 11, 941, 33)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#f9213e"))
        p.drawEllipse(QRectF(879, 12, 6, 6))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.owner.windowHandle():
            self.owner.windowHandle().startSystemMove()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.owner._toggle_maximize()


class ReadySurface(QWidget):
    def __init__(self, owner, data):
        super().__init__()
        self.setFixedSize(REFERENCE_WIDTH, REFERENCE_HEIGHT)
        self.setObjectName("readyReferenceSurface")
        self.setStyleSheet(STYLE + "QWidget#readyReferenceSurface {background:#03080b;}")
        self.reference_photo = QPixmap(str(ASSETS / "references/games.jpg"))
        self.chrome = Chrome(owner, self)
        for index, (title, symbol) in enumerate((
            ("Overview", "home"), ("Ready Room", "radio"), ("Games", "gamepad"),
            ("Mods", "puzzle"), ("Old Files", "archive"), ("Other Storage", "database"),
            ("Captures", "camera"), ("Graveyard", "grave"), ("Game DNA", "dna"),
            ("Undo Center", "undo"), ("AI Assistant", "sparkles"),
            ("Settings", "settings"), ("More Tools", "grid"),
        )):
            control = NavigationButton(title, symbol, owner, self)
            control.setGeometry(0, 83 + 35*index + (3 if index else 0), RAIL_WIDTH-1, 35)
        from gg_desktop.ready_room import ReadyRoomContent
        self.contents = ReadyRoomContent(owner, data, self.chrome.search)
        self.contents.setParent(self)
        self.contents.setGeometry(RAIL_WIDTH, CHROME_HEIGHT, REFERENCE_WIDTH-RAIL_WIDTH, REFERENCE_HEIGHT-CHROME_HEIGHT)
        if data.reference:
            # A visible sample-mode label stays below the reference's working area.
            sample = QLabel("REFERENCE PREVIEW · SAMPLE DATA", self)
            sample.setGeometry(12, 702, 205, 13)
            sample.setStyleSheet('font-family:"Roboto Condensed";font-size:9px;color:#72808c;background:transparent;')

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor("#03080b"))
        p.drawPixmap(QRectF(28, 15, 177, 44), self.reference_photo, QRectF(26, 14, 184, 45))
        p.drawPixmap(QRectF(0, 541, 218, 179), self.reference_photo, QRectF(0, 541, 217, 179))
        fade = QLinearGradient(0, 529, 0, 552)
        fade.setColorAt(0, QColor("#03080b"))
        fade.setColorAt(1, QColor(3, 8, 11, 0))
        p.fillRect(QRectF(0, 529, 218, 24), fade)
        p.setPen(QColor("#192127"))
        p.drawLine(218, 0, 218, 720)


class ReadyRoomPage(QGraphicsView):
    """A real widget surface at one reference scale, isolated to this route."""
    def __init__(self, owner, data):
        super().__init__()
        self.owner, self.data = owner, data
        self.surface = ReadySurface(owner, data)
        self.contents = self.surface.contents
        self.search = self.surface.chrome.search
        self.compact = False
        self._ready_shell_active = False
        self.setObjectName("readyRoom")
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet("QGraphicsView#readyRoom{background:#03080b;border:0;}")
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        self.scene_owner = QGraphicsScene(self)
        self.setScene(self.scene_owner)
        self.proxy = self.scene_owner.addWidget(self.surface)
        self.scene_owner.setSceneRect(0, 0, REFERENCE_WIDTH, REFERENCE_HEIGHT)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.search_shortcut = QShortcut(QKeySequence("Ctrl+K"), owner)
        self.search_shortcut.setEnabled(False)
        self.search_shortcut.activated.connect(self.focus_search)

    def __getattr__(self, name):
        contents = self.__dict__.get("contents")
        if contents is not None:
            return getattr(contents, name)
        raise AttributeError(name)

    def findChildren(self, *args, **kwargs):
        return super().findChildren(*args, **kwargs) + self.surface.findChildren(*args, **kwargs)

    def findChild(self, *args, **kwargs):
        return super().findChild(*args, **kwargs) or self.surface.findChild(*args, **kwargs)

    def enter_ready_shell(self):
        self.saved_search = self.owner.global_search
        self.owner.global_search = self.search
        self.hidden_shell = [(widget, widget.isHidden()) for widget in (self.owner.nav_rail, self.owner.top_bar)]
        for widget, _ in self.hidden_shell:
            widget.hide()
        self.disabled_shortcuts = []
        for shortcut in self.owner.findChildren(QShortcut):
            if shortcut is not self.search_shortcut and shortcut.isEnabled() and shortcut.key() == QKeySequence("Ctrl+K"):
                shortcut.setEnabled(False)
                self.disabled_shortcuts.append(shortcut)
        self._ready_shell_active = True
        self.search_shortcut.setEnabled(True)
        self.progress_parent = self.owner.progress.parentWidget()
        self.progress_layout = self.progress_parent.layout()
        self.progress_index = self.progress_layout.indexOf(self.owner.progress)
        was_hidden = self.owner.progress.isHidden()
        self.owner.progress.setParent(self.surface)
        self.owner.progress.setGeometry(230, 704, 1040, 3)
        self.owner.progress.setVisible(not was_hidden)
        self._fit_reference()

    def release_ready_shell(self):
        if not self._ready_shell_active:
            return
        self._ready_shell_active = False
        self.search_shortcut.setEnabled(False)
        self.search_shortcut.deleteLater()
        self.owner.global_search = self.saved_search
        for widget, hidden in self.hidden_shell:
            widget.setVisible(not hidden)
        for shortcut in self.disabled_shortcuts:
            shortcut.setEnabled(True)
        was_hidden = self.owner.progress.isHidden()
        self.owner.progress.setParent(self.progress_parent)
        self.progress_layout.insertWidget(self.progress_index, self.owner.progress)
        self.owner.progress.setVisible(not was_hidden)

    def focus_search(self):
        self.setFocus()
        self.proxy.setFocus()
        self.search.setFocus(Qt.ShortcutFocusReason)

    def reference_point(self, widget, point=QPoint()):
        local = widget.mapTo(self.surface, point)
        return self.viewport().mapTo(self.owner, self.mapFromScene(local))

    def _fit_reference(self):
        scale = max(.1, min(self.viewport().width() / REFERENCE_WIDTH,
                            self.viewport().height() / REFERENCE_HEIGHT))
        self.setTransform(QTransform.fromScale(scale, scale))
        self.horizontalScrollBar().setValue(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_reference()

    def mousePressEvent(self, event):
        point = self.mapTo(self.owner, event.position().toPoint())
        if event.button() == Qt.LeftButton and not self.owner.isMaximized():
            edges = Qt.Edges()
            if point.x() < 5:
                edges |= Qt.LeftEdge
            elif point.x() > self.owner.width()-6:
                edges |= Qt.RightEdge
            if point.y() < 5:
                edges |= Qt.TopEdge
            elif point.y() > self.owner.height()-6:
                edges |= Qt.BottomEdge
            if edges and self.owner.windowHandle():
                self.owner.windowHandle().startSystemResize(edges)
                return
        super().mousePressEvent(event)
