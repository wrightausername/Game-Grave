"""Static, subtle light and crisp native chrome from the supplied references."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QSize
from PySide6.QtGui import (QColor, QIcon, QLinearGradient, QPainter, QPen,
                          QPixmap, QRadialGradient, QFont)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget, QPushButton, QFrame

# Outline shapes stay unfilled, including the mod puzzle and storage cylinder.
PATHS = {
    'overview': '<path d="m3 12 10-9 10 9M6 10v13h5v-8h4v8h5V10"/>',
    'ready room': '<circle cx="13" cy="10" r="2"/><path d="M13 14v10M9 5a7 7 0 0 0 0 10M17 5a7 7 0 0 1 0 10M5 2a12 12 0 0 0 0 17M21 2a12 12 0 0 1 0 17"/>',
    'games': '<path d="M8 6h10c3 0 4 3 5 8l1 6c0 3-3 4-5 1l-3-4h-6l-3 4c-2 3-5 2-5-1l1-6c1-5 2-8 5-8ZM7 10v6M4 13h6"/><circle cx="18" cy="11" r=".6"/><circle cx="21" cy="14" r=".6"/>',
    'mods': '<path d="M4 4h6V3a3 3 0 1 1 6 0v1h6v6h-1a3 3 0 1 0 0 6h1v6h-6v-1a3 3 0 1 0-6 0v1H4v-6H3a3 3 0 1 1 0-6h1Z"/>',
    'old files': '<path d="M3 4h20v6H3ZM5 10v13h16V10M9 14h8M10 8v4h6V8"/>',
    'other storage': '<ellipse cx="13" cy="5" rx="10" ry="4"/><path d="M3 5v16c0 6 20 6 20 0V5M3 10c0 6 20 6 20 0M3 15c0 6 20 6 20 0"/>',
    'captures': '<path d="M3 7h5l2-4h6l2 4h5v16H3ZM5 4h3"/><circle cx="13" cy="14" r="5"/>',
    'graveyard': '<path d="M4 24h18M6 24V10a7 7 0 0 1 14 0v14M13 7v10M9 11h8"/>',
    'game dna': '<path d="M8 2c0 9 10 9 10 18v4M18 2c0 9-10 9-10 18v4M8 4h10M9 8h8M9 18h8M8 22h10M10 12l6 2"/>',
    'undo center': '<path d="M3 3v7h7M3 10a10 10 0 1 1-1 8M13 7v7l5 3"/>',
    'ai assistant': '<path d="M11 3c0 7-2 9-8 10 6 1 8 3 8 10 1-7 3-9 9-10-6-1-8-3-9-10ZM21 1v6M18 4h6M22 19v5M20 21h4"/>',
    'settings': '<path d="m10 2-1 3-3 1-3-1-2 4 2 2v4l-2 2 2 4 3-1 3 1 1 3h5l1-3 3-1 3 1 2-4-2-2v-4l2-2-2-4-3 1-3-1-1-3Z"/><circle cx="12.5" cy="13" r="4"/>',
    'more tools': '<rect x="3" y="3" width="8" height="8" rx="1"/><rect x="16" y="3" width="8" height="8" rx="1"/><rect x="3" y="16" width="8" height="8" rx="1"/><rect x="16" y="16" width="8" height="8" rx="1"/>',
    'notifications': '<path d="M5 19h16l-2-4V9a6 6 0 0 0-12 0v6ZM11 23h4M13 1v2"/>',
    'help': '<circle cx="13" cy="13" r="11"/><path d="M10 9a3 3 0 1 1 5 2c-2 1-2 2-2 4M13 19h.01"/>',
    'search': '<circle cx="11" cy="11" r="8"/><path d="m17 17 7 7"/>',
    'activity': '<path d="M1 14h6l3-11 5 21 3-10h7"/>',
    'quick': '<path d="m15 1-12 15h9l-2 10 14-17h-9Z"/>',
    'chevron': '<path d="m9 5 8 8-8 8"/>',
    'back': '<path d="m17 5-8 8 8 8"/>',
    'updates': '<path d="M3 10h5l14-7v20L8 16H3ZM8 16l2 8h5l-2-6M22 8l3-2M23 14h3"/>',
    'cube': '<path d="m13 2 11 6v12l-11 6-11-6V8ZM2 8l11 6 11-6M13 14v12"/>',
    'maintenance': '<rect x="3" y="5" width="21" height="20" rx="2"/><path d="M3 11h21M8 1v8M19 1v8M8 16h2M15 16h2M8 21h2"/>',
    'download': '<path d="M13 1v17m-7-6 7 7 7-7M2 19v6h23v-6"/>',
    'star': '<path d="m13 1 4 9 10 1-8 6 3 10-9-6-9 6 3-10-8-6 10-1Z"/>',
    'save': '<path d="M3 2h17l4 4v19H3ZM8 2v8h11V2M8 25V15h12v10"/>',
    'layers': '<path d="m13 2 12 6-12 6L1 8ZM1 14l12 6 12-6M1 20l12 6 12-6"/>',
    'check': '<circle cx="13" cy="13" r="11"/><path d="m6 13 5 5 10-11"/>',
    'shield': '<path d="m13 2 10 4v7c0 6-5 10-10 13C8 23 3 19 3 13V6ZM8 13l4 4 7-8"/>',
    'minimize': '<path d="M5 13h17"/>',
    'maximize': '<rect x="6" y="6" width="15" height="15" rx="1"/>',
    'close': '<path d="m6 6 15 15M21 6 6 21"/>',
}
ALIASES = {'storage':'other storage','library':'games','space reclaimed':'other storage',
           'scan library':'search','find unused mods':'mods','review old files':'old files',
           'manage captures':'captures','open graveyard':'graveyard','mod radar':'mods',
           'save vault':'save','health':'activity'}


@lru_cache(maxsize=256)
def icon_pixmap(name, color='#E9EBEE', size=28, glow=False):
    name = ALIASES.get(str(name).casefold(), str(name).casefold())
    content = PATHS.get(name, PATHS['more tools'])
    pix = QPixmap(size * 3, size * 3)
    pix.setDevicePixelRatio(3)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    if glow:
        halo = QRadialGradient(size/2, size/2, size*.51)
        tone = QColor(color); tone.setAlpha(26)
        halo.setColorAt(0, tone)
        tone.setAlpha(0); halo.setColorAt(1, tone)
        p.fillRect(QRectF(0,0,size,size), halo)
    inset = size*.15 if glow else size*.06
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-1 -1 29 29"><g fill="none" stroke="{color}" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">{content}</g></svg>'
    QSvgRenderer(svg.encode()).render(p, QRectF(inset,inset,size-inset*2,size-inset*2))
    p.end()
    return pix


def outline_icon(name, color='#E9EBEE'):
    return QIcon(icon_pixmap(name, color))


def paint_focus(painter,widget):
    if widget.hasFocus():
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor('#DA7D8E'),1,Qt.DotLine))
        painter.drawRoundedRect(QRectF(widget.rect()).adjusted(2,2,-2,-2),3,3)


class NavigationButton(QPushButton):
    def __init__(self, route):
        super().__init__(route)
        self.route = route
        self.setObjectName('navButton')
        self.setFixedHeight(46)
        self.setCursor(Qt.PointingHandCursor)
        self.setIcon(outline_icon(route))

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        active = bool(self.property('active'))
        if active or self.underMouse():
            gradient = QLinearGradient(0,0,self.width(),0)
            gradient.setColorAt(0,QColor('#35151B' if active else '#171419'))
            gradient.setColorAt(.48,QColor('#601822' if active else '#2B1820'))
            gradient.setColorAt(1,QColor(24,16,20,0))
            p.fillRect(self.rect(),gradient)
            if active:
                glow = QLinearGradient(0,0,self.width(),0)
                for pos,alpha in ((0,0),(.35,205),(.65,100),(1,0)):
                    glow.setColorAt(pos,QColor(243,39,61,alpha))
                p.fillRect(QRectF(0,self.height()-2,self.width(),2),glow)
        p.drawPixmap(43,9,30,30,icon_pixmap(self.route,'#F0F1F4',30))
        f=QFont('Segoe UI'); f.setPixelSize(18); f.setWeight(QFont.DemiBold if active else QFont.Normal)
        p.setFont(f); p.setPen(QColor('#F0F1F4'))
        p.drawText(QRectF(104,0,self.width()-111,self.height()),Qt.AlignVCenter,self.route)
        if self.hasFocus():
            p.setPen(QPen(QColor('#C96678'),1,Qt.DotLine)); p.setBrush(Qt.NoBrush)
            p.drawRect(self.rect().adjusted(3,3,-3,-3))


class ReferenceSurface(QWidget):
    """One static painted backdrop; no timers, game hooks or external requests."""
    def __init__(self):
        super().__init__()
        self.route=''
        self.offset_y=0
        from gg_desktop.owner_art import load_approved_hero
        self.photo=load_approved_hero('overview')
        self.ready_photo=QPixmap(str(Path(__file__).parent/'assets'/'owner_cinematic_readyroom.jpg'))

    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.fillRect(self.rect(),QColor('#090D10'))
        if self.route not in ('Overview','Ready Room'):
            return
        p.translate(0,-self.offset_y)
        art=self.ready_photo if self.route=='Ready Room' and not self.ready_photo.isNull() else self.photo
        if not art.isNull():
            height=170 if self.route=='Overview' else 160
            origin_y=42 if self.route=='Overview' else 25
            art_width=height*art.width()/art.height()
            x=self.width()*.70-art_width*.48
            target=QRectF(x,origin_y,art_width,height)
            # Feather the supplied crop into the window; avoid a rectangular
            # photographic seam where the source image ends.
            layer=QPixmap(round(art_width),height); layer.fill(Qt.transparent)
            lp=QPainter(layer); lp.setRenderHint(QPainter.SmoothPixmapTransform)
            lp.drawPixmap(QRectF(0,0,art_width,height),art,QRectF(art.rect()))
            lp.setCompositionMode(QPainter.CompositionMode_DestinationIn)
            mask=QLinearGradient(0,0,min(230,art_width*.3),0)
            mask.setColorAt(0,QColor(255,255,255,0)); mask.setColorAt(1,QColor(255,255,255,255))
            lp.fillRect(layer.rect(),mask)
            vertical=QLinearGradient(0,0,0,height)
            for stop,alpha in ((0,0),(.10,255),(.82,255),(1,0)):
                vertical.setColorAt(stop,QColor(255,255,255,alpha))
            lp.fillRect(layer.rect(),vertical); lp.end()
            p.drawPixmap(round(x),origin_y,layer)
            fade=QLinearGradient(0,0,self.width()*.65,0)
            fade.setColorAt(0,QColor('#090D10')); fade.setColorAt(.40,QColor(9,13,16,225)); fade.setColorAt(1,QColor(9,13,16,0))
            p.fillRect(QRectF(0,0,self.width(),height+origin_y),fade)
            foot=QLinearGradient(0,height+origin_y-30,0,height+origin_y+24)
            foot.setColorAt(0,QColor(9,13,16,0)); foot.setColorAt(1,QColor('#090D10'))
            p.fillRect(QRectF(0,height+origin_y-30,self.width(),54),foot)
        for x,y,r,color in ((.29,.5,420,'#2B7880'),(.59,.57,380,'#A5283C'),(.5,.91,560,'#457C85')):
            halo=QRadialGradient(self.width()*x,self.height()*y,r)
            c=QColor(color); c.setAlpha(12); halo.setColorAt(0,c)
            c.setAlpha(0); halo.setColorAt(1,c)
            p.fillRect(self.rect(),halo)


class ChromeBar(QWidget):
    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton and self.window().windowHandle():
            self.window().windowHandle().startSystemMove()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self,event):
        window=self.window()
        window.showNormal() if window.isMaximized() else window.showMaximized()


class SearchFrame(QFrame):
    def mousePressEvent(self,event):
        if self.focusProxy() is not None:
            self.focusProxy().setFocus()
        event.accept()


class GlassPanel(QFrame):
    def __init__(self, accent='#4B555F', rounded=True):
        super().__init__(); self.accent=accent; self.rounded=rounded
        self.setObjectName('referenceGlassPanel')

    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        box=QRectF(self.rect()).adjusted(.5,.5,-.5,-.5)
        fill=QLinearGradient(0,0,0,self.height())
        fill.setColorAt(0,QColor(23,27,31,135)); fill.setColorAt(1,QColor(4,10,13,155))
        p.setBrush(fill); p.setPen(QPen(QColor('#444B53'),1))
        p.drawRoundedRect(box,15,15)
        top=QLinearGradient(0,0,self.width(),0)
        top.setColorAt(0,QColor(self.accent)); top.setColorAt(.65,QColor(70,77,83,80)); top.setColorAt(1,QColor(70,77,83,0))
        p.setPen(QPen(top,1)); p.drawLine(QPointF(15,1),QPointF(self.width()-15,1))
