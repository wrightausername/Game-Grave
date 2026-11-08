"""One continuous Games header scene, behind the existing native controls.

The reference photo is never edited. Both header widgets use the same image
transform; reference search/window controls are excluded from the artwork.
"""
from PySide6.QtCore import QObject, QEvent, QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QRegion
from PySide6.QtWidgets import QWidget

from gg_desktop.reference_widgets import reference

BACKGROUND = QColor("#02070a")
SOURCE = QRectF(655, 0, 625, 144)


class _HeaderBackground(QWidget):
    def __init__(self, owner):
        super().__init__(owner.window.top_bar)
        self.owner = owner
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAccessibleName("Games banner artwork")

    def paintEvent(self, event):
        if self.owner.active():
            self.owner.paint(self, top=True)


class GamesBannerArtwork(QObject):
    def __init__(self, window, page, banner):
        super().__init__(page)
        self.window, self.page, self.banner = window, page, banner
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
        return self.window.page is self.page and self.window.current_route == "Games"

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

    def paint(self, widget, *, top=False):
        origin = widget.mapTo(self.window, QPoint())
        banner_origin = self.banner.mapTo(self.window, QPoint())
        header_top = self.window.top_bar.mapTo(self.window, QPoint()).y()
        header_bottom = banner_origin.y() + self.banner.height()
        scale = (header_bottom - header_top) / SOURCE.height()
        right = banner_origin.x() + self.banner.width()
        target = QRectF(right - SOURCE.width()*scale - origin.x(), header_top - origin.y(),
                        SOURCE.width()*scale, SOURCE.height()*scale)
        painter = QPainter(widget)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.fillRect(widget.rect(), BACKGROUND)
        if top:
            # The photo includes its own search and window controls. They must
            # never be painted underneath the app's real, clickable controls.
            safe = QRegion(widget.rect())
            for excluded in (QRectF(655, 0, 45, 46), QRectF(1077, 0, 203, 38)):
                mask = QRectF(target.left() + (excluded.left()-SOURCE.left())*scale,
                              target.top() + excluded.top()*scale,
                              excluded.width()*scale, excluded.height()*scale)
                safe -= QRegion(mask.toAlignedRect())
            painter.setClipRegion(safe)
        painter.drawPixmap(target, reference("games"), SOURCE)
        painter.setClipping(False)
        edge = QLinearGradient(target.left(), 0, target.left()+110*scale, 0)
        edge.setColorAt(0, BACKGROUND)
        edge.setColorAt(1, QColor(2, 7, 10, 0))
        painter.fillRect(widget.rect(), edge)
        # Apply one horizontal fade in window coordinates to both widgets.
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
