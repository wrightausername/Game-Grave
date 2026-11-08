"""One continuous header scene across the native top bar and a page banner.

Same technique the Games header uses, parameterised so other tabs can share it
without touching Games. The owner's reference photo is never edited; both header
widgets draw the same image with the same transform, and the photo's own search and
window controls are excluded so they never show under the app's real controls.
"""
from PySide6.QtCore import QObject, QEvent, QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QRegion
from PySide6.QtWidgets import QWidget

from gg_desktop.reference_widgets import reference

BACKGROUND = QColor("#02070a")


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
    def __init__(self, window, page, banner, *, route, scene, source, excluded):
        super().__init__(page)
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

    def paint(self, widget, *, top=False):
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
        if top:
            safe = QRegion(widget.rect())
            for excluded in self.excluded:
                mask = QRectF(target.left() + (excluded.left()-source.left())*scale,
                              target.top() + excluded.top()*scale,
                              excluded.width()*scale, excluded.height()*scale)
                safe -= QRegion(mask.toAlignedRect())
            painter.setClipRegion(safe)
        painter.drawPixmap(target, reference(self.scene), source)
        painter.setClipping(False)
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
