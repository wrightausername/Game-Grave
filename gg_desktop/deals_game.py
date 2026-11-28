"""Deals: a game's page, laid out like a store page (owner, 2026-11-27: "deals section needs to be prettier... needs to show
photos and video of said game along with a description of the game that doesnt cut off and a list somewhere seperate and
clean of the prices", then "also needs a more clear back button").

Top: a clear Back to deals button (Esc works too), the title and a line with genres, release date and developer.
Left: a big picture area that shows the game's header, then whatever thumbnail you pick: screenshots shown whole, trailers
played right there with sound, pause and a seek bar; Full view opens the large viewer. Under it, the whole description.
Right (below it in a narrow window): the price panel, on its own: today's best price, the price history bar, every store
in a clean list cheapest first with Open buttons, the wishlist target, and key resellers.
The attribute names on `w` are the ones the rest of Deals already uses, so prices, wishlist and resellers work unchanged.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QBoxLayout, QDoubleSpinBox, QFrame, QHBoxLayout, QHeaderView, QLabel,
                               QPushButton, QSizePolicy, QSlider, QStackedWidget, QTableWidget, QVBoxLayout, QWidget)
from shiboken6 import isValid

NARROW = 860          # below this width the price panel moves under the pictures
PANEL_W = 360

STYLE = """
QPushButton#dealsBackBig { background:#141c25; color:#ffffff; border:1px solid #2b3846; border-radius:18px;
                           padding:7px 16px 7px 12px; font-size:13px; font-weight:700; min-height:22px; }
QPushButton#dealsBackBig:hover { background:#1d2833; border:1px solid #ff4357; }
QLabel#dealsGameTitle { font-size:24px; font-weight:800; color:#ffffff; }
QLabel#dealsInfo { font-size:12px; color:#9fb0c2; }
QLabel#dealsAbout { font-size:14px; color:#d9e1ea; line-height:150%; }
QFrame#dealsHero { background:#000000; border:1px solid #1b2836; border-radius:12px; }
QFrame#dealsPanel { background:#0b131b; border:1px solid #1d2a37; border-radius:14px; }
QLabel#dealsPanelHead { font-size:12px; color:#8C9AA9; font-weight:800; letter-spacing:1.4px; }
QLabel#dealsBestBig { font-size:28px; font-weight:800; color:#32d67a; }
QLabel#dealsBestStore { font-size:13px; color:#c9d4e0; }
QTableWidget#dealsPrices { background:transparent; border:none; color:#e8eef5; font-size:13px; }
QTableWidget#dealsPrices::item { border-bottom:1px solid #16212c; padding:0 4px; }
QHeaderView::section { background:transparent; color:#7f8e9e; border:none; font-size:12px; padding:2px 4px; }
QPushButton#heroButton { background:rgba(0,0,0,150); color:#ffffff; border:1px solid rgba(255,255,255,60);
                         border-radius:8px; padding:4px 10px; font-size:12px; }
QPushButton#heroButton:hover { border:1px solid #ff4357; }
"""


def _label(text, name, wrap=True):
    item = QLabel(text)
    item.setObjectName(name)
    item.setWordWrap(wrap)
    item.setTextFormat(Qt.PlainText)
    item.setTextInteractionFlags(Qt.TextSelectableByMouse)
    item.setMinimumWidth(0)
    return item


class Hero(QFrame):
    """The big 16:9 picture or trailer. Keeps the picture it was given and refits it when the page is resized."""

    def __init__(self):
        super().__init__()
        self.setObjectName("dealsHero")
        self.stack = QStackedWidget(self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(1, 1, 1, 1)
        lay.addWidget(self.stack)
        self.picture = QLabel()
        self.picture.setAlignment(Qt.AlignCenter)
        self.picture.setStyleSheet("background:#000;border-radius:11px;")
        self.picture.setMinimumSize(320, 180)
        self.picture.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)   # the picture never pushes the page bigger
        self.stack.addWidget(self.picture)
        self.source = None
        self.player = self.video = self.audio = None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return int(width * 9 / 16)

    def sizeHint(self):
        return QSize(640, 360)

    def show_pixmap(self, pix):
        self.stop()
        self.source = pix
        self.stack.setCurrentWidget(self.picture)
        self._refit()

    def _refit(self):
        if self.source is not None and not self.source.isNull():
            self.picture.setPixmap(self.source.scaled(self.picture.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        want = self.heightForWidth(self.width())
        if abs(want - self.minimumHeight()) > 24:    # a scrollbar coming and going can't start a resize loop
            self.setMinimumHeight(want)
        self._refit()

    def play(self, url, on_fail):
        from gg_desktop import deals_media
        classes = deals_media.video_player()
        if classes is None:
            on_fail()
            return False
        QMediaPlayer, QAudioOutput, QVideoWidget = classes
        if self.player is None:
            self.video = QVideoWidget()
            self.stack.addWidget(self.video)
            self.player = QMediaPlayer(self)
            self.audio = QAudioOutput(self)
            self.audio.setVolume(0.6)
            self.player.setAudioOutput(self.audio)
            self.player.setVideoOutput(self.video)
        try:
            self.player.errorOccurred.disconnect()
        except (RuntimeError, TypeError):
            pass
        self.player.errorOccurred.connect(lambda *_a: on_fail())
        self.stack.setCurrentWidget(self.video)
        self.player.setSource(QUrl(url))
        self.player.play()
        return True

    def stop(self):
        if self.player is not None:
            self.player.stop()


class GamePage(QWidget):
    """Re-arranges itself (side by side or stacked) whenever its width changes. Esc goes back to the deals."""
    w = None
    on_back = None

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and self.on_back is not None:
            self.on_back()
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.w is not None and (self.width() < NARROW) != getattr(self, "_narrow", None):
            self._narrow = self.width() < NARROW         # only re-arrange when it crosses the line
            arrange(self.w, self.width())


def build_view(window, w, st, show_front, open_url, add_to_wishlist, ActionFlow, button, DealMeter):
    """The game page widget. Fills `w` with the names the rest of Deals uses."""
    page = GamePage()
    page.setObjectName("dealsGamePage")
    page.setStyleSheet(STYLE)
    outer = QVBoxLayout(page)
    outer.setContentsMargins(4, 2, 4, 8)
    outer.setSpacing(10)

    head = QHBoxLayout()
    head.setSpacing(14)
    w.back = QPushButton("←  Back to deals")
    w.back.setObjectName("dealsBackBig")
    w.back.setCursor(Qt.PointingHandCursor)
    w.back.setAccessibleName("Back to deals")
    w.back.setToolTip("Back to the deals (Esc)")
    w.back.clicked.connect(lambda: show_front(window))
    head.addWidget(w.back, 0, Qt.AlignTop)
    words = QVBoxLayout()
    words.setSpacing(2)
    w.title = _label("Search for a game", "dealsGameTitle")
    w.info_line = _label("", "dealsInfo")
    words.addWidget(w.title)
    words.addWidget(w.info_line)
    head.addLayout(words, 1)
    outer.addLayout(head)

    w.game_body = QBoxLayout(QBoxLayout.LeftToRight)
    w.game_body.setSpacing(16)
    outer.addLayout(w.game_body, 1)

    # Pictures, trailers and the description
    media_col = QVBoxLayout()
    media_col.setSpacing(10)
    w.hero = Hero()
    w.art = w.hero.picture                 # the header picture shows here first (older code reads w.art)
    media_col.addWidget(w.hero)
    tools = QHBoxLayout()
    tools.setSpacing(8)
    w.hero_caption = _label("", "dealsInfo", wrap=False)
    tools.addWidget(w.hero_caption, 1)
    w.hero_pause = button("Pause", lambda: toggle_pause(w))
    w.hero_pause.hide()
    tools.addWidget(w.hero_pause)
    w.hero_full = button("Full view", lambda: full_view(window, w))
    w.hero_full.setToolTip("Open this picture or trailer large, with Back and Next through all of them.")
    w.hero_full.hide()
    tools.addWidget(w.hero_full)
    media_col.addLayout(tools)
    from gg_desktop import deals_media
    w.media = deals_media.strip(window)
    media_col.addWidget(w.media)
    w.about_line = _label("", "dealsAbout")
    w.about_line.hide()
    media_col.addWidget(w.about_line)
    w.steam_link = button("Open on Steam", lambda: open_url(f"https://store.steampowered.com/app/{w.media.app_id}/"),
                          tip="Steam's store page for this game, in your browser.")
    w.steam_link.hide()
    media_col.addWidget(w.steam_link, 0, Qt.AlignLeft)
    media_col.addStretch(1)
    media_holder = QWidget()
    media_holder.setLayout(media_col)
    media_holder.setMinimumWidth(0)
    w.game_body.addWidget(media_holder, 1)

    # The price panel, on its own
    panel = QFrame()
    panel.setObjectName("dealsPanel")
    w.price_panel = panel
    pl = QVBoxLayout(panel)
    pl.setContentsMargins(16, 14, 16, 14)
    pl.setSpacing(8)
    head_label = QLabel("BEST PRICE TODAY")
    head_label.setObjectName("dealsPanelHead")
    pl.addWidget(head_label)
    w.best_price = _label("", "dealsBestBig", wrap=False)
    pl.addWidget(w.best_price)
    w.best = _label("Every store's price shows here, cheapest first.", "dealsBestStore")
    pl.addWidget(w.best)
    w.buy = button("Open the cheapest store", lambda: st.game and st.game.best and open_url(st.game.best.url),
                   primary=True, tip="Opens the store's own page in your browser. Game Grave doesn't buy anything.")
    pl.addWidget(w.buy)
    w.meter = DealMeter()
    w.meter.setVisible(False)
    pl.addWidget(w.meter)
    w.summary = _label("", "dealsNote")
    pl.addWidget(w.summary)
    stores_head = QLabel("EVERY STORE")
    stores_head.setObjectName("dealsPanelHead")
    pl.addSpacing(4)
    pl.addWidget(stores_head)
    w.table = QTableWidget(0, 5)
    w.table.setObjectName("dealsPrices")
    w.table.setAccessibleName("Prices by store")
    w.table.setHorizontalHeaderLabels(["Store", "Price", "Usual", "Off", ""])
    w.table.verticalHeader().setVisible(False)
    w.table.setShowGrid(False)
    w.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    w.table.setSelectionMode(QAbstractItemView.NoSelection)
    w.table.setFocusPolicy(Qt.NoFocus)
    w.table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    w.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    header = w.table.horizontalHeader()
    header.setSectionResizeMode(0, QHeaderView.Stretch)
    for col in (1, 2, 3):
        header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
    header.setSectionResizeMode(4, QHeaderView.Fixed)
    w.table.setColumnWidth(4, 84)
    w.table.setColumnHidden(2, True)        # the usual price is in the bar above; the list stays clean
    w.table.verticalHeader().setDefaultSectionSize(40)
    w.table.setIconSize(QSize(16, 16))
    pl.addWidget(w.table)
    wish = ActionFlow(spacing=8)
    wish.addWidget(QLabel("Tell me under"))
    w.target = QDoubleSpinBox()
    w.target.setAccessibleName("Target price for the wishlist")
    w.target.setPrefix("$")
    w.target.setRange(0, 999)
    w.target.setDecimals(2)
    w.target.setSpecialValueText("any drop")
    w.target.setToolTip("Optional. With a target, the wishlist also tells you when the price reaches it. "
                        "Leave at 'any drop' to hear about real price drops.")
    wish.addWidget(w.target)
    w.watch = button("Add to wishlist", lambda: add_to_wishlist(window))
    wish.addWidget(w.watch)
    wish_holder = QWidget()
    wish_holder.setLayout(wish)
    pl.addWidget(wish_holder)

    w.resellers = QFrame()
    w.resellers.setObjectName("dealsWarn")
    box = QVBoxLayout(w.resellers)
    box.setContentsMargins(12, 10, 12, 10)
    box.setSpacing(6)
    rh = QLabel("KEY RESELLERS")
    rh.setObjectName("dealsPanelHead")
    box.addWidget(rh)
    w.keyshop = _label("", "dealsText")
    box.addWidget(w.keyshop)
    from gg_desktop import deals_core as dc
    box.addWidget(_label(dc.RESELLER_WARNING, "dealsNote"))
    w.reseller_row = ActionFlow(spacing=6)
    rholder = QWidget()
    rholder.setLayout(w.reseller_row)
    box.addWidget(rholder)
    pl.addWidget(w.resellers)
    pl.addStretch(1)
    w.game_body.addWidget(panel, 0)
    page.w = w
    page.on_back = lambda: show_front(window)
    page.setFocusPolicy(Qt.StrongFocus)
    arrange(w, 1100)
    return page


def arrange(w, width):
    """Side by side when there's room, the price panel under the pictures when the window is narrow."""
    if not isValid(w.price_panel):
        return
    narrow = width < NARROW
    w.game_body.setDirection(QBoxLayout.TopToBottom if narrow else QBoxLayout.LeftToRight)
    if narrow:
        w.price_panel.setMinimumWidth(0)
        w.price_panel.setMaximumWidth(16777215)
    else:
        w.price_panel.setFixedWidth(PANEL_W)
    fit_table(w)


def fit_table(w):
    """The store list is as tall as its rows, so the panel never scrolls inside itself."""
    rows = w.table.rowCount()
    w.table.setFixedHeight(w.table.horizontalHeader().height() + rows * w.table.verticalHeader().defaultSectionSize() + 4)


def show_item(window, w, index, picture, open_url):
    """Put one thumbnail's picture or trailer in the big area."""
    items = getattr(w.media, "items", [])
    if not items:
        return
    index %= len(items)
    w.hero_index = index
    kind, name, thumb, url = items[index]
    w.hero_caption.setText(f"{name} · {index + 1} of {len(items)}")
    w.hero_full.show()
    if kind == "video":
        def failed():
            if isValid(w.hero):
                w.hero.stop()
                w.hero_pause.hide()
                w.hero_caption.setText(f"{name}: couldn't play here, so it opened on Steam's page")
                open_url(f"https://store.steampowered.com/app/{w.media.app_id}/")
        if w.hero.play(url, failed):
            w.hero_pause.setText("Pause")
            w.hero_pause.show()
        return
    w.hero_pause.hide()
    w.hero.stop()
    from gg_desktop.deals_page import state
    st = state(window)
    pix = st.images.get(url)
    if pix is not None and not pix.isNull():
        w.hero.show_pixmap(pix)
        return
    picture(url, QSize(1280, 720), None, None)

    def check(attempt=0):
        p = st.images.get(url)
        if p is not None:
            if not p.isNull() and isValid(w.hero) and getattr(w, "hero_index", -1) == index:
                w.hero.show_pixmap(p)
            return
        if attempt < 100:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(100, lambda: check(attempt + 1))
    check()


def toggle_pause(w):
    player = w.hero.player
    if player is None:
        return
    from PySide6.QtMultimedia import QMediaPlayer
    if player.playbackState() == QMediaPlayer.PlayingState:
        player.pause()
        w.hero_pause.setText("Play")
    else:
        player.play()
        w.hero_pause.setText("Pause")


def full_view(window, w):
    from gg_desktop import deals_media
    from gg_desktop.deals_page import picture
    w.hero.stop()
    w.hero_pause.setText("Play")
    deals_media.open_viewer(window, w.media, w.title.text(), getattr(w, "hero_index", 0),
                            lambda url, size, label, after: picture(window, url, size, label, whole=True, after=after))
