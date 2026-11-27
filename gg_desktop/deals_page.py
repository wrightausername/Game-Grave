"""Deals tab (Library): search any PC game, see every store's price cheapest first, key reseller prices (labelled, with
the user's own GG.deals key), and a wishlist that Game Grave checks while it runs and mentions quietly when a price drops.

Rules live in `deals_core` (tested), network calls in `deals_net`. This module is the screen and the background watch.
Game Grave never buys anything: "Open store" opens the store's own page in the browser.
"""
from __future__ import annotations

from types import SimpleNamespace
import time

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QDoubleSpinBox, QFrame, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
from shiboken6 import isValid

from gg_desktop import deals_core as dc
from gg_desktop.header_banner import HeaderBannerArtwork

SUBTITLE = "Cheapest prices for any game, plus a wishlist that watches them."
FIRST_WATCH_MS = 2 * 60 * 1000
WATCH_TICK_MS = 30 * 60 * 1000

STYLE = """
QFrame#dealsCard { background:#09121a; border:1px solid #1b2836; border-radius:12px; }
QFrame#dealsWarn { background:rgba(246,190,36,18); border:1px solid rgba(246,190,36,90); border-radius:10px; }
QLabel#dealsSection { color:#8C9AA9; font-size:11px; font-weight:800; letter-spacing:1.6px; }
QLabel#dealsTitle { font-size:20px; font-weight:800; color:#ffffff; }
QLabel#dealsBest { font-size:15px; font-weight:700; color:#32d67a; }
QLabel#dealsNote { font-size:12px; color:#8fa0b3; }
QLabel#dealsText { font-size:13px; color:#d6dee8; }
QListWidget#dealsList { background:#070d13; border:1px solid #1b2836; border-radius:10px; padding:4px; color:#e8eef5; }
QListWidget#dealsList::item { padding:6px; border-radius:6px; }
QListWidget#dealsList::item:selected { background:#2a0f17; }
QListWidget#dealsList::item:hover { background:#0f1a24; }
QTableWidget#dealsTable { background:#070d13; border:1px solid #1b2836; border-radius:10px; color:#e8eef5;
                          gridline-color:#111c26; }
QLineEdit#dealsSearch { font-size:14px; padding:8px 10px; }
QFrame#dealCard { background:#0b131b; border:1px solid #1b2836; border-radius:12px; }
QFrame#dealCard:hover { border:1px solid rgba(255,40,74,150); background:#0f1923; }
QLabel#dealCardTitle { font-size:13px; font-weight:700; color:#f2f5f8; }
QLabel#dealPrice { font-size:15px; font-weight:800; color:#32d67a; }
QLabel#dealFree { font-size:15px; font-weight:800; color:#f6be24; }
QLabel#dealOld { font-size:12px; color:#6f8091; }
QLabel#dealBadge { background:#1d7a45; color:#ffffff; font-size:12px; font-weight:800; border-radius:6px; padding:1px 6px; }
QLabel#dealBadgeFree { background:#a86f00; color:#ffffff; font-size:12px; font-weight:800; border-radius:6px; padding:1px 6px; }
QLabel#dealStore { font-size:11px; color:#8fa0b3; }
QLabel#dealRating { font-size:11px; color:#7fd7ff; }
QLabel#dealsRowTitle { font-size:17px; font-weight:800; color:#ffffff; }
QPushButton#dealsBack { padding:4px 10px; }
"""


def state(window):
    if not hasattr(window, "_deals"):
        window._deals = SimpleNamespace(hits=[], game=None, keyshops=None, images={}, timer=None, checking=False,
                                        query="", pending_images=set(), front={}, front_at=0.0, front_error="",
                                        icons={}, loading_front=False)
    return window._deals


def _section(text):
    widget = QLabel(text.upper())
    widget.setObjectName("dealsSection")
    return widget


def _text(value, role="dealsText", wrap=True):
    widget = QLabel(value)
    widget.setObjectName(role)
    widget.setWordWrap(wrap)
    widget.setTextFormat(Qt.PlainText)
    return widget


def _button(caption, action, primary=False, tip=""):
    control = QPushButton(caption)
    control.setAccessibleName(caption.replace("…", ""))
    control.setCursor(Qt.PointingHandCursor)
    if primary:
        control.setObjectName("primary")
    if tip:
        control.setToolTip(tip)
    control.clicked.connect(action)
    return control


def open_url(url):
    if url.startswith("https://"):
        QDesktopServices.openUrl(QUrl(url))


def _run(window, work, done, title="Deals"):
    """Network work off the screen's thread; a failure comes back as a sentence for the page."""
    from gg_desktop import deals_net

    def job(_progress):
        try:
            return "ok", work()
        except deals_net.DealsError as exc:
            return "error", str(exc)
        except Exception as exc:  # anything unexpected is still shown, never raised into the window
            return "error", f"Something went wrong while getting prices: {type(exc).__name__}"
    window.job(job, lambda packet: done(*packet), error_title=title)


# ------------------------------------------------------------------ pictures
def picture(window, url, size, label=None, fallback=""):
    st = state(window)
    if not url:
        if fallback:
            picture(window, fallback, size, label)
        return
    if url in st.images:
        pix = st.images[url]
        if label is not None and not pix.isNull() and isValid(label):
            label.setPixmap(pix.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        return
    if url in st.pending_images:
        return
    st.pending_images.add(url)
    from gg_desktop import deals_net

    def done(kind, data):
        st.pending_images.discard(url)
        pix = QPixmap()
        if kind == "ok" and data:
            pix.loadFromData(data)
        st.images[url] = pix
        if pix.isNull() and fallback and fallback != url:
            picture(window, fallback, size, label)      # no Steam header for this game: use the store's picture
            return
        if label is not None and isValid(label) and not pix.isNull():
            label.setPixmap(pix.scaled(size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                            .copy(0, 0, size.width(), size.height()) if size.width() > 60 else
                            pix.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        if window.current_route == "Deals":
            refresh_pictures(window)
    _run(window, lambda: deals_net.image(url), done)


def refresh_pictures(window):
    page = getattr(window, "deals_page_widgets", None)
    if page is None or not isValid(page.results):
        return
    st = state(window)
    for n in range(page.results.count()):
        item = page.results.item(n)
        pix = st.images.get(item.data(Qt.UserRole + 1) or "")
        if pix is not None and not pix.isNull():
            item.setIcon(QIcon(pix))
    for n in range(page.wish.count()):
        item = page.wish.item(n)
        pix = st.images.get(item.data(Qt.UserRole + 1) or "")
        if pix is not None and not pix.isNull():
            item.setIcon(QIcon(pix))
    for r in range(page.table.rowCount()):
        cell = page.table.item(r, 0)
        if cell is not None and cell.icon().isNull():
            pix = st.images.get(st.icons.get(str(cell.data(Qt.UserRole) or ""), ""))
            if pix is not None and not pix.isNull():
                cell.setIcon(QIcon(pix))


# ------------------------------------------------------------------ storefront pieces
CARD_W, ART_H = 214, 100


class DealCard(QFrame):
    """One game on the storefront: its picture, discount badge, price, usual price, store and Steam rating."""
    clicked = Signal(str)

    def __init__(self, window, deal):
        super().__init__()
        self.deal = deal
        self.setObjectName("dealCard")
        self.setFixedWidth(CARD_W)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName(f"{deal.title}, {dc.price_text(deal.price)} at {deal.store}")
        self.setToolTip(f"{deal.title}: every store's price")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 10)
        lay.setSpacing(5)
        self.art = QLabel()
        self.art.setFixedSize(CARD_W - 2, ART_H)
        self.art.setAlignment(Qt.AlignCenter)
        self.art.setStyleSheet("background:#111b25;border-top-left-radius:11px;border-top-right-radius:11px;")
        lay.addWidget(self.art)
        self.art_url = dc.art_url(deal.steam_app_id, deal.thumb)
        picture(window, self.art_url, QSize(CARD_W - 2, ART_H), self.art, fallback=deal.thumb)
        inner = QVBoxLayout()
        inner.setContentsMargins(10, 0, 10, 0)
        inner.setSpacing(3)
        title = _text(deal.title, "dealCardTitle")
        title.setFixedHeight(36)
        title.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        inner.addWidget(title)
        prices = QHBoxLayout()
        prices.setSpacing(6)
        free = deal.price == 0
        badge = _text("FREE" if free else f"-{deal.savings}%", "dealBadgeFree" if free else "dealBadge", wrap=False)
        if deal.savings or free:
            prices.addWidget(badge)
        prices.addWidget(_text(dc.price_text(deal.price), "dealFree" if free else "dealPrice", wrap=False))
        if deal.retail and deal.retail > deal.price:
            old = _text(dc.price_text(deal.retail), "dealOld", wrap=False)
            font = old.font()
            font.setStrikeOut(True)
            old.setFont(font)
            prices.addWidget(old)
        prices.addStretch(1)
        inner.addLayout(prices)
        store = QHBoxLayout()
        store.setSpacing(5)
        self.store_icon = QLabel()
        self.store_icon.setFixedSize(16, 16)
        store.addWidget(self.store_icon)
        icon_url = state(window).icons.get(deal.store_id, "")
        if icon_url:
            picture(window, icon_url, QSize(16, 16), self.store_icon)
        store.addWidget(_text(deal.store, "dealStore", wrap=False), 1)
        if deal.rating:
            store.addWidget(_text(f"{deal.rating}", "dealRating", wrap=False))
        inner.addLayout(store)
        lay.addLayout(inner)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.deal.game_id)
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.clicked.emit(self.deal.game_id)
            return
        super().keyPressEvent(event)


class DealMeter(QWidget):
    """Lowest ever on the left, the usual price on the right, today's best price marked between them."""

    def __init__(self):
        super().__init__()
        self.values = None
        self.setFixedHeight(46)
        self.setAccessibleName("Deal meter")

    def set_values(self, values):
        self.values = values
        if values:
            now, usual, low = values
            self.setToolTip(f"Today {dc.price_text(now)} · usual {dc.price_text(usual)} · lowest ever {dc.price_text(low)}")
        self.setVisible(values is not None)
        self.update()

    def paintEvent(self, _event):
        if not self.values:
            return
        now, usual, low = self.values
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(6, 20, self.width() - 12, 8)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#1b2836"))
        p.drawRoundedRect(r, 4, 4)
        span = max(0.01, usual - low)
        where = min(1.0, max(0.0, (now - low) / span))
        good = QColor("#32d67a") if where <= .25 else QColor("#f6be24") if where <= .6 else QColor("#ff6b7e")
        p.setBrush(good)
        p.drawRoundedRect(QRectF(r.left(), r.top(), max(8, r.width() * (1 - where)), r.height()), 4, 4)
        x = r.left() + r.width() * where
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(x - 6, r.center().y() - 6, 12, 12))
        small = QFont(self.font())
        small.setPixelSize(11)
        p.setFont(small)
        p.setPen(QColor("#8fa0b3"))
        p.drawText(QRectF(0, 30, 160, 16), Qt.AlignLeft, "Lowest ever " + dc.price_text(low))
        p.drawText(QRectF(self.width() - 160, 30, 160, 16), Qt.AlignRight, "Usual " + dc.price_text(usual))
        p.setPen(good)
        bold = QFont(small)
        bold.setBold(True)
        p.setFont(bold)
        p.drawText(QRectF(min(max(0, x - 60), self.width() - 120), 0, 120, 16), Qt.AlignCenter, "Today " + dc.price_text(now))
        p.end()


def build_front(window, holder):
    """Fill the storefront: three rows of cards from CheapShark, loaded once an hour while Game Grave runs."""
    st = state(window)
    clear_layout(holder)
    if st.loading_front and not st.front:
        holder.addWidget(_text("Loading today's deals from 30+ stores…", "dealsNote"))
        return
    if not any(st.front.values()):
        holder.addWidget(_text(st.front_error or "Today's deals show here.", "dealsNote"))
        retry = _button("Try again", lambda: load_front(window, force=True))
        holder.addWidget(retry, 0, Qt.AlignLeft)
        return
    from gg_desktop.insight_widgets import ActionFlow
    for key, title, note, _params in dc.FRONT:
        deals = st.front.get(key) or []
        if not deals:
            continue
        head = QHBoxLayout()
        head.addWidget(_text(title, "dealsRowTitle", wrap=False))
        head.addStretch(1)
        holder.addLayout(head)
        holder.addWidget(_text(note, "dealsNote"))
        flow = ActionFlow(spacing=10)
        for deal in deals:
            card = DealCard(window, deal)
            card.setFocusPolicy(Qt.StrongFocus)
            card.clicked.connect(lambda game_id: pick(window, game_id))
            flow.addWidget(card)
        box = QWidget()
        box.setLayout(flow)
        holder.addWidget(box)
    holder.addWidget(_text("Prices in US dollars, as CheapShark reports them. Pick a card for every store's price. "
                           "Game Grave never buys anything.", "dealsNote"))
    holder.addStretch(1)


def load_front(window, force=False):
    st = state(window)
    if st.loading_front or (not force and st.front and time.time() - st.front_at < 3600):
        return
    from gg_desktop import deals_net
    st.loading_front = True
    w = widgets(window)
    if w is not None:
        build_front(window, w.front_lay)

    def work():
        return deals_net.front(), deals_net.store_icons()

    def done(kind, value):
        st.loading_front = False
        if kind == "error":
            st.front_error = value
        else:
            st.front, st.icons = value
            st.front_at, st.front_error = time.time(), ""
        w2 = widgets(window)
        if w2 is not None:
            build_front(window, w2.front_lay)
    _run(window, work, done)


def show_front(window):
    w = widgets(window)
    if w is not None:
        w.stack.setCurrentIndex(0)
        w.results.clearSelection()


# ------------------------------------------------------------------ the page
def build(window):
    self = window
    st = state(self)
    page = self._insight_page("Deals", SUBTITLE, "games", "tag", 66)
    page.banner_artwork = HeaderBannerArtwork(self, page, page.content.itemAt(0).widget(), route="Deals",
                                              scene="games", source=(900, 0, 380, 110), excluded=((1090, 0, 190, 40),))
    page.setStyleSheet(STYLE)
    w = SimpleNamespace()
    self.deals_page_widgets = w

    bar = QHBoxLayout()
    bar.setSpacing(8)
    w.search = QLineEdit(st.query)
    w.search.setObjectName("dealsSearch")
    w.search.setPlaceholderText("Search any PC game, for example Elden Ring")
    w.search.setAccessibleName("Search for a game's price")
    w.search.returnPressed.connect(lambda: search(self))
    bar.addWidget(w.search, 1)
    w.go = _button("Find prices", lambda: search(self), primary=True)
    bar.addWidget(w.go)
    page.content.addLayout(bar)
    w.status = _text("Official stores come from CheapShark (prices in US dollars). Key reseller prices need your free "
                     "GG.deals key. Game Grave never buys anything; it opens the store's page.", "dealsNote")
    page.content.addWidget(w.status)

    main = QHBoxLayout()
    main.setSpacing(12)
    left = QVBoxLayout()
    left.setSpacing(6)
    left.addWidget(_section("Results"))
    w.results = QListWidget()
    w.results.setObjectName("dealsList")
    w.results.setAccessibleName("Games found")
    w.results.setIconSize(QSize(92, 34))
    w.results.setWordWrap(True)
    w.results.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    w.results.setTextElideMode(Qt.ElideRight)
    w.results.setMinimumHeight(220)
    w.results.currentItemChanged.connect(lambda cur, _old: cur is not None and pick(self, cur.data(Qt.UserRole)))
    left.addWidget(w.results, 3)
    left.addWidget(_section("Your wishlist"))
    w.wish = QListWidget()
    w.wish.setObjectName("dealsList")
    w.wish.setAccessibleName("Wishlist")
    w.wish.setIconSize(QSize(92, 34))
    w.wish.setWordWrap(True)
    w.wish.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    w.wish.setTextElideMode(Qt.ElideRight)
    w.wish.setMinimumHeight(170)
    w.wish.setSelectionMode(QAbstractItemView.SingleSelection)
    w.wish.itemDoubleClicked.connect(lambda item: pick(self, item.data(Qt.UserRole)))
    w.wish.currentItemChanged.connect(lambda cur, _old: sync_wish_buttons(self))
    left.addWidget(w.wish, 2)
    wish_buttons = QHBoxLayout()
    w.check = _button("Check prices now", lambda: check_wishlist(self, manual=True),
                      tip="Asks CheapShark for today's prices of every game on your wishlist.")
    w.show_wish = _button("Show", lambda: w.wish.currentItem() and pick(self, w.wish.currentItem().data(Qt.UserRole)))
    w.remove_wish = _button("Remove", lambda: remove_from_wishlist(self))
    for control in (w.check, w.show_wish, w.remove_wish):
        wish_buttons.addWidget(control)
    left.addLayout(wish_buttons)
    w.checked = _text("", "dealsNote")
    left.addWidget(w.checked)
    from PySide6.QtWidgets import QCheckBox
    w.free_alerts = QCheckBox("Tell me when a game is free to keep")
    w.free_alerts.setAccessibleName("Free game alerts")
    w.free_alerts.setToolTip("Checked every 6 hours while Game Grave runs, never while you play. One quiet notice per "
                             "new giveaway. Game Grave never claims anything for you.")
    w.free_alerts.setChecked(dc.free_alerts_on(self.settings))
    w.free_alerts.toggled.connect(lambda on: toggle_free_alerts(self, on))
    left.addWidget(w.free_alerts)
    holder = QWidget()
    holder.setLayout(left)
    holder.setMinimumWidth(250)
    holder.setMaximumWidth(340)
    main.addWidget(holder)

    card = QFrame()
    card.setObjectName("dealsCard")
    right = QVBoxLayout(card)
    right.setContentsMargins(16, 14, 16, 14)
    right.setSpacing(8)
    top = QHBoxLayout()
    top.setSpacing(14)
    w.art = QLabel()
    w.art.setFixedSize(300, 140)
    w.art.setAlignment(Qt.AlignCenter)
    w.art.setStyleSheet("background:#111b25;border-radius:8px;")
    top.addWidget(w.art, 0, Qt.AlignTop)
    words = QVBoxLayout()
    words.setSpacing(4)
    w.back = _button("‹  Back to deals", lambda: show_front(self))
    w.back.setObjectName("dealsBack")
    words.addWidget(w.back, 0, Qt.AlignLeft)
    w.title = _text("Search for a game", "dealsTitle")
    w.best = _text("Every store's price shows here, cheapest first.", "dealsBest")
    w.summary = _text("", "dealsNote")
    for widget in (w.title, w.best, w.summary):
        words.addWidget(widget)
    words.addStretch(1)
    top.addLayout(words, 1)
    right.addLayout(top)
    w.meter = DealMeter()
    w.meter.setVisible(False)
    right.addWidget(w.meter)

    w.table = QTableWidget(0, 5)
    w.table.setObjectName("dealsTable")
    w.table.setAccessibleName("Prices by store")
    w.table.setHorizontalHeaderLabels(["Store", "Price", "Usual price", "Off", ""])
    w.table.verticalHeader().setVisible(False)
    w.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    w.table.setSelectionMode(QAbstractItemView.NoSelection)
    head = w.table.horizontalHeader()
    head.setSectionResizeMode(0, QHeaderView.Stretch)
    for col in (1, 2, 3):
        head.setSectionResizeMode(col, QHeaderView.ResizeToContents)
    head.setSectionResizeMode(4, QHeaderView.Fixed)
    w.table.setColumnWidth(4, 118)
    w.table.verticalHeader().setDefaultSectionSize(38)
    w.table.setMinimumHeight(200)
    w.table.setMinimumWidth(0)
    right.addWidget(w.table, 1)

    from gg_desktop.insight_widgets import ActionFlow
    actions = ActionFlow(spacing=8)          # wraps onto a second line in a narrow window
    w.buy = _button("Open the cheapest store", lambda: st.game and st.game.best and open_url(st.game.best.url), primary=True,
                    tip="Opens the store's own page in your browser. Game Grave doesn't buy anything.")
    actions.addWidget(w.buy)
    target_label = _text("Tell me under", "dealsNote", wrap=False)
    actions.addWidget(target_label)
    w.target = QDoubleSpinBox()
    w.target.setAccessibleName("Target price for the wishlist")
    w.target.setPrefix("$")
    w.target.setRange(0, 999)
    w.target.setDecimals(2)
    w.target.setSpecialValueText("any drop")
    w.target.setToolTip("Optional. With a target, the wishlist also tells you when the price reaches it. "
                        "Leave at 'any drop' to hear about real price drops.")
    actions.addWidget(w.target)
    w.watch = _button("Add to wishlist", lambda: add_to_wishlist(self))
    actions.addWidget(w.watch)
    action_holder = QWidget()
    action_holder.setLayout(actions)
    right.addWidget(action_holder)

    w.resellers = QFrame()
    w.resellers.setObjectName("dealsWarn")
    box = QVBoxLayout(w.resellers)
    box.setContentsMargins(12, 10, 12, 10)
    box.setSpacing(6)
    box.addWidget(_section("Key resellers"))
    w.keyshop = _text("", "dealsText")
    box.addWidget(w.keyshop)
    box.addWidget(_text(dc.RESELLER_WARNING, "dealsNote"))
    w.reseller_row = ActionFlow(spacing=6)
    reseller_holder = QWidget()
    reseller_holder.setLayout(w.reseller_row)
    box.addWidget(reseller_holder)
    right.addWidget(w.resellers)
    w.stack = QStackedWidget()
    front = QWidget()
    w.front_lay = QVBoxLayout(front)
    w.front_lay.setContentsMargins(0, 0, 0, 0)
    w.front_lay.setSpacing(6)
    w.stack.addWidget(front)
    w.stack.addWidget(card)
    main.addWidget(w.stack, 1)
    page.content.addLayout(main, 1)

    fill_results(self)
    fill_wishlist(self)
    show_game(self)
    build_front(self, w.front_lay)
    w.stack.setCurrentIndex(1 if st.game is not None and getattr(st, "showing_game", False) else 0)
    load_front(self)
    if not st.hits and not st.game:
        w.search.setFocus()
    return page


def widgets(window):
    w = getattr(window, "deals_page_widgets", None)
    return w if w is not None and isValid(w.results) else None


def search(window):
    w = widgets(window)
    if w is None:
        return
    st = state(window)
    st.query = w.search.text().strip()
    if len(st.query) < 2:
        w.status.setText("Type at least two letters of the game's name.")
        return
    from gg_desktop import deals_net
    w.status.setText(f"Looking up prices for “{st.query}”…")
    w.go.setEnabled(False)

    def done(kind, value):
        w2 = widgets(window)
        if w2 is None:
            return
        w2.go.setEnabled(True)
        if kind == "error":
            w2.status.setText(value)
            return
        st.hits = value
        w2.status.setText(f"{len(value)} games match “{st.query}”. Pick one to see every store's price."
                          if value else f"No game matches “{st.query}” in CheapShark's stores. Check the spelling.")
        fill_results(window)
        if value:
            w2.results.setCurrentRow(0)
    _run(window, lambda: deals_net.search(st.query), done)


def fill_results(window):
    w = widgets(window)
    if w is None:
        return
    st = state(window)
    w.results.blockSignals(True)
    w.results.clear()
    for hit in st.hits:
        item = QListWidgetItem(f"{hit.title}\nfrom {dc.price_text(hit.cheapest)}")
        item.setData(Qt.UserRole, hit.game_id)
        item.setData(Qt.UserRole + 1, hit.thumb)
        item.setToolTip(hit.title)
        w.results.addItem(item)
        picture(window, hit.thumb, QSize(92, 34))
        if st.game is not None and st.game.game_id == hit.game_id:
            w.results.setCurrentItem(item)
    w.results.blockSignals(False)
    refresh_pictures(window)


def pick(window, game_id):
    st = state(window)
    w = widgets(window)
    if w is None or not game_id:
        return
    from gg_desktop import deals_net
    w.best.setText("Getting every store's price…")
    w.stack.setCurrentIndex(1)
    key = deals_net.load_key()

    def work():
        found = deals_net.game(game_id)
        shops, problem = None, ""
        if key and found.steam_app_id:
            try:
                shops = deals_net.keyshops(found.steam_app_id, key)
            except deals_net.DealsError as exc:
                problem = str(exc)
        return found, shops, problem

    def done(kind, value):
        if widgets(window) is None:
            return
        if kind == "error":
            widgets(window).best.setText(value)
            return
        st.game, st.keyshops, st.keyshop_problem = value
        show_game(window)
    _run(window, work, done)


def show_game(window):
    w = widgets(window)
    if w is None:
        return
    st = state(window)
    g = st.game
    w.table.setRowCount(0)
    for control in (w.buy, w.watch, w.target):
        control.setEnabled(g is not None)
    clear_layout(w.reseller_row)
    if g is None:
        w.resellers.setVisible(False)
        return
    w.stack.setCurrentIndex(1)
    st.showing_game = True
    w.title.setText(g.title)
    w.meter.set_values(dc.meter(g))
    best = g.best
    w.best.setText(f"{dc.price_text(best.price)} at {best.store}" if best else "Not on sale in CheapShark's stores right now")
    w.summary.setText(dc.summary(g) + "  Prices as CheapShark reports them, in US dollars.")
    w.buy.setText(f"Open {best.store}" if best else "Open the cheapest store")
    w.buy.setEnabled(best is not None)
    w.table.setRowCount(len(g.offers))
    for r, offer in enumerate(g.offers):
        cells = (offer.store, dc.price_text(offer.price), dc.price_text(offer.retail), f"{offer.savings}%" if offer.savings else "")
        for c, value in enumerate(cells):
            cell = QTableWidgetItem(value)
            if c == 0:
                cell.setData(Qt.UserRole, offer.store_id)
                icon_url = st.icons.get(offer.store_id, "")
                pix = st.images.get(icon_url)
                if pix is not None and not pix.isNull():
                    cell.setIcon(QIcon(pix))
                elif icon_url:
                    picture(window, icon_url, QSize(16, 16))
            if r == 0 and c in (0, 1):
                cell.setForeground(QColor("#32d67a"))
            w.table.setItem(r, c, cell)
        control = _button("Open store", lambda _=False, u=offer.url: open_url(u),
                          tip=f"Opens {offer.store}'s page for {g.title} in your browser.")
        control.setMinimumWidth(104)
        w.table.setCellWidget(r, 4, control)
    on_list = dc.on_wishlist(dc.wishlist(window.settings), g.game_id)
    w.watch.setText("Update wishlist" if on_list else "Add to wishlist")
    current = next((i for i in dc.wishlist(window.settings) if i["game_id"] == g.game_id), None)
    w.target.setValue((current["target"] or 0) if current else 0)
    w.art.clear()
    picture(window, dc.art_url(g.steam_app_id, g.thumb), QSize(300, 140), w.art, fallback=g.thumb)

    # Key resellers
    w.resellers.setVisible(True)
    from gg_desktop import deals_net
    has_key = bool(deals_net.load_key())
    shops = st.keyshops
    if shops is not None and (shops.current is not None or shops.lowest is not None):
        line = f"GG.deals lists key resellers from {dc.price_text(shops.current, shops.currency)} now"
        if shops.lowest is not None:
            line += f" (lowest seen {dc.price_text(shops.lowest, shops.currency)})"
        w.keyshop.setText(line + ". The individual shop offers are on GG.deals.")
        if shops.url.startswith("https://"):
            w.reseller_row.addWidget(_button("See reseller offers", lambda _=False, u=shops.url: open_url(u)))
    elif has_key:
        problem = getattr(st, "keyshop_problem", "")
        w.keyshop.setText(problem or ("GG.deals has no key reseller price for this game." if g.steam_app_id else
                                      "Key reseller prices need a Steam version of the game; search the shops below."))
    else:
        w.keyshop.setText("Key reseller prices need a free GG.deals API key (gg.deals > Settings > API). "
                          "Until then, search the shops yourself:")
    if not (shops is not None and shops.url):
        for name, url in dc.reseller_links(g.title):
            w.reseller_row.addWidget(_button(name, lambda _=False, u=url: open_url(u),
                                             tip=f"Searches {name} for {g.title} in your browser. Game Grave reads nothing from it."))
    if has_key:
        w.reseller_row.addWidget(_button("Remove GG.deals key", lambda: remove_key(window)))
    else:
        w.reseller_row.addWidget(_button("Add GG.deals key…", lambda: add_key(window), primary=True))


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget() is not None:
            item.widget().deleteLater()
        elif item.layout() is not None:          # rows of the storefront are layouts inside the layout
            clear_layout(item.layout())
            item.layout().deleteLater()


def add_key(window):
    from gg_desktop import deals_net
    key, ok = QInputDialog.getText(window, "GG.deals API key",
                                   "Paste your GG.deals API key (free: sign in at gg.deals, Settings, API).\n"
                                   "It's kept on this PC, encrypted for your Windows account, and sent only to api.gg.deals.",
                                   QLineEdit.Password)
    if not ok or not key.strip():
        return
    try:
        deals_net.save_key(key)
    except deals_net.DealsError as exc:
        window.error("Key not saved", str(exc))
        return
    st = state(window)
    if st.game is not None:
        pick(window, st.game.game_id)


def remove_key(window):
    from gg_desktop import deals_net
    if window.confirm("Remove GG.deals key", "Remove your GG.deals API key from this PC? Key reseller prices stop showing."):
        deals_net.forget_key()
        state(window).keyshops = None
        show_game(window)


# ------------------------------------------------------------------ wishlist
def _save(window, settings):
    from core import save_settings
    try:
        save_settings(settings)
    except (OSError, ValueError) as exc:
        window.error("Wishlist not saved", str(exc))
        return False
    window.settings = settings
    return True


def add_to_wishlist(window):
    st, w = state(window), widgets(window)
    if st.game is None or w is None:
        return
    target = w.target.value() or None
    try:
        items = dc.add_item(dc.wishlist(window.settings), st.game, target)
    except ValueError as exc:
        window.error("Wishlist is full", str(exc))
        return
    if _save(window, dc.with_wishlist(window.settings, items)):
        w.status.setText(f"{st.game.title} is on your wishlist. Game Grave checks its price every few hours while it runs "
                         "and tells you quietly when it drops.")
        fill_wishlist(window)
        show_game(window)


def remove_from_wishlist(window):
    w = widgets(window)
    item = w.wish.currentItem() if w else None
    if item is None:
        return
    items = dc.remove_item(dc.wishlist(window.settings), item.data(Qt.UserRole))
    if _save(window, dc.with_wishlist(window.settings, items)):
        fill_wishlist(window)
        show_game(window)


def fill_wishlist(window):
    w = widgets(window)
    if w is None:
        return
    items = dc.wishlist(window.settings)
    w.wish.clear()
    for i in items:
        line = f"{i['title']}\n{dc.price_text(i['best'])}" + (f" at {i['store']}" if i["store"] else "")
        if i["target"]:
            line += f"  ·  target {dc.price_text(i['target'])}"
        item = QListWidgetItem(line)
        item.setData(Qt.UserRole, i["game_id"])
        item.setData(Qt.UserRole + 1, i["thumb"])
        item.setToolTip("Double-click to see every store's price.")
        w.wish.addItem(item)
        picture(window, i["thumb"], QSize(92, 34))
    if not items:
        empty = QListWidgetItem("Nothing yet. Pick a game, then Add to wishlist.")
        empty.setFlags(Qt.NoItemFlags)
        w.wish.addItem(empty)
    when = window.settings.get(dc.CHECKED_KEY)
    w.checked.setText(("Last checked " + time.strftime("%b %d, %I:%M %p", time.localtime(float(when))) +
                       f". Checked every {dc.WATCH_HOURS} hours while Game Grave runs, never while you play.")
                      if when else f"Checked every {dc.WATCH_HOURS} hours while Game Grave runs, never while you play.")
    w.check.setEnabled(bool(items) and not state(window).checking)
    sync_wish_buttons(window)
    refresh_pictures(window)


def sync_wish_buttons(window):
    w = widgets(window)
    if w is None:
        return
    chosen = w.wish.currentItem() is not None and bool(w.wish.currentItem().data(Qt.UserRole))
    w.show_wish.setEnabled(chosen)
    w.remove_wish.setEnabled(chosen)


def check_wishlist(window, manual=False):
    """Ask CheapShark for every wishlist game's price, update the list, and post a quiet notice for real drops."""
    st = state(window)
    items = dc.wishlist(window.settings)
    if st.checking or not items:
        return False
    from gg_desktop import deals_net
    st.checking = True
    _save(window, dict(window.settings, **{dc.CHECKED_KEY: time.time()}))
    w = widgets(window)
    if w is not None:
        w.check.setEnabled(False)
        w.checked.setText("Checking wishlist prices…")
    ids = [i["game_id"] for i in items]

    def done(kind, value):
        st.checking = False
        if kind == "error":
            fill_wishlist(window)
            if manual and widgets(window) is not None:
                widgets(window).checked.setText(value)
            return
        fresh, news = dc.refreshed(dc.wishlist(window.settings), value)
        _save(window, dc.with_wishlist(window.settings, fresh))
        fill_wishlist(window)
        notify_drops(window, news, manual)
    _run(window, lambda: deals_net.games(ids), done)
    return True


def notify_drops(window, news, manual=False):
    from gg_desktop import comfort
    if news:
        _save(window, dc.remember_drops(window.settings, news))
    if not news:
        if manual and widgets(window) is not None:
            widgets(window).status.setText("No price drops on your wishlist since the last check.")
        return
    if len(news) <= 2:
        for title, message in news:
            comfort.notify(window, f"Price drop: {title}", message, "good", "tab:Deals")
    else:
        names = ", ".join(t for t, _ in news[:3]) + (f" and {len(news) - 3} more" if len(news) > 3 else "")
        comfort.notify(window, f"Price drops on {len(news)} wishlist games", names + ". Open Deals to see them.", "good",
                       "tab:Deals")


def install(window):
    """The quiet wishlist watch: first look 2 minutes after start, then every 30 minutes, and it only asks for prices when
    the last check is 6+ hours old, the wishlist isn't empty, and no game, scan or clean-up is running."""
    if getattr(window, "reference_preview", False):
        return
    st = state(window)
    st.timer = QTimer(window)
    st.timer.setInterval(WATCH_TICK_MS)
    st.timer.timeout.connect(lambda: watch_tick(window))
    st.timer.start()
    QTimer.singleShot(FIRST_WATCH_MS, lambda: watch_tick(window))


def watch_tick(window, now=None):
    """Wishlist prices and free game alerts, each at most every 6 hours, never while a game, scan or clean-up runs."""
    try:
        from gg_desktop.autopsy_ui import game_running
        busy = window.scanning or window.cleaning or game_running(window)
    except Exception:
        busy = True
    if busy:
        return False
    ran = False
    if dc.free_alerts_on(window.settings) and dc.free_due(window.settings, now):
        ran = check_free(window, now) or ran
    if dc.wishlist(window.settings) and dc.due(window.settings, now):
        ran = check_wishlist(window) or ran
    return ran


def check_free(window, now=None):
    """Free game alerts (owner, 2026-11-27): one quiet notice when a store starts giving a game away."""
    st = state(window)
    if getattr(st, "checking_free", False):
        return False
    from gg_desktop import comfort, deals_net
    st.checking_free = True
    _save(window, dict(window.settings, **{dc.FREE_CHECKED_KEY: now if now is not None else time.time()}))

    def done(kind, value):
        st.checking_free = False
        if kind == "error":
            return
        updated, fresh = dc.free_update(window.settings, value, now)
        _save(window, updated)
        message = dc.free_message(fresh)
        if message:
            comfort.notify(window, message[0], message[1], "good", "tab:Deals")
    _run(window, deals_net.free_now, done)
    return True


def toggle_free_alerts(window, on):
    _save(window, dict(window.settings, **{dc.FREE_ALERTS_KEY: bool(on)}))
    w = widgets(window)
    if w is not None:
        w.status.setText("Game Grave will tell you quietly when a store gives a game away." if on else
                         "Free game alerts are off. The Free to keep row still shows today's giveaways.")
