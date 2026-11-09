"""One continuous header scene across the native top bar and a page banner.

Same technique the Games header uses, parameterised so other tabs can share it
without touching Games. The owner's reference photo is never edited; both header
widgets draw the same image with the same transform, and the photo's own search and
window controls are excluded so they never show under the app's real controls.
"""
from PySide6.QtCore import QObject, QEvent, QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import QWidget

from gg_desktop.reference_widgets import brand_cover, brand_source, reference

BACKGROUND = QColor("#02070a")

# One panoramic HD picture per tab (tools/make_banner_art.py). Every tab fills its full header width with it.
ROUTE_ART = {
    "Overview": "banner_overview.jpg", "Ready Room": "banner_ready_room.jpg", "Games": "banner_games.jpg",
    "Mods": "banner_mods.jpg", "Old Files": "banner_old_files.jpg", "Other Storage": "banner_other_storage.jpg",
    "Captures": "banner_captures.jpg", "Graveyard": "banner_graveyard.jpg", "Game DNA": "banner_dna.jpg",
    "Undo Center": "banner_undo.jpg", "Settings": "banner_settings.jpg", "AI Assistant": "banner_assistant.jpg",
    "More Tools": "banner_more_tools.jpg",
}


def paint_slice(painter, art, rect, *, top_height, total_height, dpr, is_top):
    """Draw part of a full-width header picture: `is_top` is the native top bar, otherwise the area under it.

    Both parts are slices of the same picture, so the seam between them is invisible. Used by Ready Room, whose
    page is not a normal banner widget.
    """
    painter.fillRect(rect, BACKGROUND)
    width = rect.width()
    picture = brand_cover(art, width, total_height, round(dpr, 2), 1.0, .5)
    if not picture.isNull():
        painter.drawPixmap(0, 0 if is_top else -top_height, picture)
    if is_top:
        calm = QLinearGradient(width - 235, 0, width, 0)
        calm.setColorAt(0, QColor(2, 7, 10, 0))
        calm.setColorAt(1, QColor(2, 7, 10, 150))
        painter.fillRect(QRectF(width - 235, 0, 235, rect.height()), calm)
    fade = QLinearGradient(0, 0, width, 0)
    fade.setColorAt(0, BACKGROUND)
    fade.setColorAt(.30, QColor(2, 7, 10, 215))
    fade.setColorAt(.55, QColor(2, 7, 10, 70))
    fade.setColorAt(1, QColor(2, 7, 10, 0))
    painter.fillRect(rect, fade)


class _HeaderBackground(QWidget):
    def __init__(self, owner):
        super().__init__(owner.window.top_bar)
        self.owner = owner
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAccessibleName(owner.route + " banner artwork")

    def paintEvent(self, event):
        if self.owner.active():
            self.owner.paint(self, top=True)


class HeaderBannerArtwork(QObject):
    INSET = 175  # width of the window-control strip that is dimmed so the controls stay readable

    def __init__(self, window, page, banner, *, route, scene=None, source=(0, 0, 1, 1), excluded=(), art=None):
        super().__init__(page)
        self.art = art or ROUTE_ART.get(route)
        self.window, self.page, self.banner = window, page, banner
        self.route, self.scene = route, scene
        self.source = QRectF(*source)
        self.excluded = [QRectF(*rect) for rect in excluded]
        self.background = _HeaderBackground(self)
        self.background.setGeometry(window.top_bar.rect())
        self.background.lower()
        self.background.show()
        window.top_bar.installEventFilter(self)
        window.progress.installEventFilter(self)
        page.installEventFilter(self)
        banner.installEventFilter(self)
        page.destroyed.connect(self.background.hide)
        page.destroyed.connect(self.background.deleteLater)

    def active(self):
        return self.window.page is self.page and self.window.current_route == self.route

    def eventFilter(self, target, event):
        if target is self.page and event.type() == QEvent.Hide:
            self.background.hide()
        elif target is self.page and event.type() == QEvent.Show and self.active():
            self.background.show()
            self.background.lower()
        elif target is self.window.top_bar and event.type() == QEvent.Resize:
            self.background.setGeometry(self.window.top_bar.rect())
            self.background.lower()
            self.banner.update()
        elif target is self.window.progress and event.type() in (QEvent.Show, QEvent.Hide, QEvent.Resize):
            self.background.update()
            self.banner.update()
        elif target is self.banner:
            if event.type() in (QEvent.Move, QEvent.Resize):
                self.background.update()
            elif event.type() == QEvent.Paint and self.active():
                self.paint(self.banner)
                return True
        return False

    def paint_art(self, widget, *, top=False):
        """Draw the panoramic HD picture once across top bar and banner, filling the full width at any window size."""
        origin = widget.mapTo(self.window, QPoint())
        banner_origin = self.banner.mapTo(self.window, QPoint())
        header_top = self.window.top_bar.mapTo(self.window, QPoint()).y()
        height = banner_origin.y() + self.banner.height() - header_top
        width = self.banner.width()
        painter = QPainter(widget)
        painter.fillRect(widget.rect(), BACKGROUND)
        left = banner_origin.x() - origin.x()
        if height > 0 and width > 0:
            picture = brand_cover(self.art, width, height, round(widget.devicePixelRatioF(), 2), 1.0, .5)
            if not picture.isNull():
                painter.drawPixmap(left, header_top - origin.y(), picture)
        # Quiet the strip behind the window controls so they stay legible on any picture.
        if top:
            right = left + width
            calm = QLinearGradient(right - self.INSET - 60, 0, right, 0)
            calm.setColorAt(0, QColor(2, 7, 10, 0))
            calm.setColorAt(1, QColor(2, 7, 10, 150))
            painter.fillRect(QRectF(right - self.INSET - 60, 0, self.INSET + 60, widget.height()), calm)
        # Title side: dark enough to read the heading, then the picture opens up.
        fade = QLinearGradient(left, 0, left + width, 0)
        fade.setColorAt(0, BACKGROUND)
        fade.setColorAt(.30, QColor(2, 7, 10, 215))
        fade.setColorAt(.55, QColor(2, 7, 10, 70))
        fade.setColorAt(1, QColor(2, 7, 10, 0))
        painter.fillRect(widget.rect(), fade)
        if not top:
            bottom = QLinearGradient(0, 0, 0, self.banner.height())
            bottom.setColorAt(0, QColor(2, 7, 10, 0))
            bottom.setColorAt(.8, QColor(2, 7, 10, 0))
            bottom.setColorAt(1, BACKGROUND)
            painter.fillRect(widget.rect(), bottom)
        painter.end()

    def paint(self, widget, *, top=False):
        if self.art and not brand_source(self.art).isNull():
            return self.paint_art(widget, top=top)
        source = self.source
        origin = widget.mapTo(self.window, QPoint())
        banner_origin = self.banner.mapTo(self.window, QPoint())
        header_top = self.window.top_bar.mapTo(self.window, QPoint()).y()
        header_bottom = banner_origin.y() + self.banner.height()
        scale = (header_bottom - header_top) / source.height()
        right = banner_origin.x() + self.banner.width()
        target = QRectF(right - source.width()*scale - origin.x(), header_top - origin.y(),
                        source.width()*scale, source.height()*scale)
        painter = QPainter(widget)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.fillRect(widget.rect(), BACKGROUND)
        photo = reference(self.scene)
        painter.drawPixmap(target, photo, source)
        if top:
            # The photo has its own search and window icons. Replace those areas with a heavily
            # blurred patch of the same photo so the real controls sit on matching colour, not a box.
            for excluded in self.excluded:
                mask = QRectF(target.left() + (excluded.left()-source.left())*scale,
                              target.top() + excluded.top()*scale,
                              excluded.width()*scale, excluded.height()*scale)
                piece = photo.copy(excluded.toAlignedRect())
                small = piece.scaled(max(2, int(excluded.width() // 16)), max(2, int(excluded.height() // 16)),
                                     Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                painter.drawPixmap(mask, small, QRectF(small.rect()))
        edge = QLinearGradient(target.left(), 0, target.left()+110*scale, 0)
        edge.setColorAt(0, BACKGROUND)
        edge.setColorAt(1, QColor(2, 7, 10, 0))
        painter.fillRect(widget.rect(), edge)
        fade = QLinearGradient(banner_origin.x()-origin.x(), 0, right-origin.x(), 0)
        fade.setColorAt(0, BACKGROUND)
        fade.setColorAt(.3, QColor(2, 7, 10, 245))
        fade.setColorAt(.58, QColor(2, 7, 10, 80))
        fade.setColorAt(1, QColor(2, 7, 10, 0))
        painter.fillRect(widget.rect(), fade)
        if not top:
            bottom = QLinearGradient(0, 0, 0, self.banner.height())
            bottom.setColorAt(0, QColor(2, 7, 10, 0))
            bottom.setColorAt(.8, QColor(2, 7, 10, 0))
            bottom.setColorAt(1, BACKGROUND)
            painter.fillRect(widget.rect(), bottom)
        painter.end()
