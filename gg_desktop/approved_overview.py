"""Native dashboard calibrated to the owner's supplied full-size Overview photo.

Only geometry, light and decoration follow the image; all facts remain local.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import math
import os

from PySide6.QtCore import Qt, QRectF, QPointF, QSize, QTimer
from PySide6.QtGui import (QColor, QImageReader, QPainter, QPen, QPixmap, QFont,
                          QLinearGradient, QRadialGradient, QConicalGradient, QPainterPath)
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                              QScrollArea, QVBoxLayout, QWidget)

from core import human_size, get_activity, friendly_activity
from recovery import get_records
from gg_desktop.widgets import HeroBanner, button, label
from gg_desktop.responsive import ResponsiveGrid, ResponsiveRow
from gg_desktop.reference_chrome import icon_pixmap, outline_icon, paint_focus

COLORS = ('#54DCEC', '#D59BEA', '#F2B970', '#4EE4DC', '#D5A5EC')
STORAGE_RED = '#F32742'


def _font(size, bold=False):
    f=QFont('Segoe UI'); f.setPixelSize(size)
    f.setWeight(QFont.DemiBold if bold else QFont.Normal)
    f.setStyleStrategy(QFont.PreferAntialias | QFont.NoSubpixelAntialias)
    return f


def _line(parent, *, margin=(0,0,0,0), gap=10):
    layout=QHBoxLayout(parent); layout.setContentsMargins(*margin); layout.setSpacing(gap)
    return layout


def _stack(parent, *, margin=(0,0,0,0), gap=8):
    layout=QVBoxLayout(parent); layout.setContentsMargins(*margin); layout.setSpacing(gap)
    return layout


def _txt(text, size=14, color='#E4E8ED', bold=False, wrap=False):
    w=QLabel(str(text)); w.setWordWrap(wrap)
    w.setStyleSheet(f'background:transparent;color:{color};font-size:{size}px;font-weight:{650 if bold else 400};')
    w.setMinimumWidth(0); w.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return w


class DashboardHero(HeroBanner):
    def __init__(self, title='Overview', subtitle='Your games. All their baggage. Under control.', height=128):
        super().__init__(title=title,subtitle=subtitle,detail='')
        self.setFixedHeight(height)
        self.setAccessibleName(title+'. '+subtitle)

    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor('#FA263F'),7,Qt.SolidLine,Qt.RoundCap))
        top=32 if self.title=='Overview' else 25
        p.drawLine(QPointF(15,top),QPointF(-2,top+50))
        p.setFont(_font(46,True)); p.setPen(QColor('#F1F2F4'))
        p.drawText(QRectF(34,top-17,self.width()-42,62),Qt.AlignVCenter,self.title)
        p.setFont(_font(18)); p.setPen(QColor('#DFE4E9'))
        p.drawText(QRectF(35,top+38,min(570,self.width()-45),53),
                   Qt.AlignLeft|Qt.AlignTop|Qt.TextWordWrap,self.subtitle)


class MetricButton(QPushButton):
    def __init__(self,title,value,accent,icon,handler,description='',value_first=False,padding=22):
        super().__init__(); self.accent=accent
        self.preferred_padding=padding; self.icon_name=icon
        self.setObjectName('approvedMetric'); self.setFixedHeight(78)
        self.setStyleSheet('QPushButton#approvedMetric{background:transparent;border:0;padding:0;min-height:78px;max-height:78px;}')
        self.setAccessibleName(title+': '+str(value)+'. '+description)
        self.setToolTip(description); self.clicked.connect(handler)
        layout=_line(self,margin=(padding,5,9,12),gap=22)
        glyph=QLabel(); glyph.setFixedSize(54,54)
        glyph.setPixmap(icon_pixmap(icon,accent,54,True)); layout.addWidget(glyph)
        self.metric_layout=layout; self.metric_glyph=glyph
        words=QWidget(); col=_stack(words,gap=0)
        heading=_txt(title,13); number=_txt(value,26,bold=True)
        self.value_label=number
        for widget in ((number,heading) if value_first else (heading,number)):
            col.addWidget(widget)
        layout.addWidget(words,1)
        for child in self.findChildren(QWidget): child.setAttribute(Qt.WA_TransparentForMouseEvents)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if not hasattr(self,'value_label'): return
        tight=event.size().width()<215
        size=44 if tight else 54
        self.metric_layout.setContentsMargins(10 if tight else self.preferred_padding,5,5 if tight else 9,12)
        self.metric_layout.setSpacing(10 if tight else 22)
        self.metric_glyph.setFixedSize(size,size)
        self.metric_glyph.setPixmap(icon_pixmap(self.icon_name,self.accent,size,True))
        self.value_label.setStyleSheet(f'background:transparent;color:#E4E8ED;font-size:{23 if tight else 26}px;font-weight:650;')

    def paintEvent(self,event):
        p=QPainter(self); w,h=self.width(),self.height()
        if self.underMouse(): p.fillRect(self.rect(),QColor(55,62,69,35))
        glow=QLinearGradient(0,0,w,0)
        c=QColor(self.accent)
        for x,a in ((0,0),(.12,220),(.42,150),(.82,35),(1,0)):
            t=QColor(c); t.setAlpha(a); glow.setColorAt(x,t)
        for y,alpha in ((h-6,.10),(h-5,.20),(h-4,.38),(h-3,1),(h-2,.28)):
            p.setOpacity(alpha); p.fillRect(QRectF(0,y,w,2),glow)
        p.setOpacity(1); p.setPen(QPen(QColor('#41474E'),1))
        p.drawLine(w-1,17,w-1,59)
        paint_focus(p,self)


class EdgeAction(QPushButton):
    def __init__(self,title,handler,icon=None,height=44):
        super().__init__(title); self.icon_name=icon or title
        self.setAccessibleName(title); self.clicked.connect(handler)
        self.setToolTip(title)
        self.setObjectName('referenceEdgeAction'); self.setFixedHeight(height)
        self.setStyleSheet(f'QPushButton#referenceEdgeAction{{background:transparent;border:0;padding:0;min-height:{height}px;max-height:{height}px;}}')

    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        if self.underMouse(): p.fillRect(self.rect(),QColor(91,39,51,45))
        p.setPen(QPen(QColor('#2C3239'),1)); p.drawLine(0,self.height()-1,self.width(),self.height()-1)
        p.drawPixmap(5,(self.height()-28)//2,28,28,icon_pixmap(self.icon_name,'#EFF0F2',28))
        p.setFont(_font(14 if self.width()<240 else 16)); p.setPen(QColor('#E8E9EC'))
        text=p.fontMetrics().elidedText(self.text(),Qt.ElideRight,max(40,self.width()-78))
        p.drawText(QRectF(53,0,self.width()-77,self.height()),Qt.AlignVCenter,text)
        p.drawPixmap(self.width()-24,(self.height()-17)//2,17,17,icon_pixmap('chevron','#DFE2E6',17))
        paint_focus(p,self)


class CleanupButton(QPushButton):
    def __init__(self,handler,title='Run Cleanup',icon='ai assistant'):
        super().__init__(title); self.icon_name=icon
        self.setObjectName('approvedCleanupCTA'); self.setFixedHeight(43)
        self.setStyleSheet('QPushButton#approvedCleanupCTA{background:transparent;border:0;padding:0;min-height:43px;max-height:43px;}')
        self.setAccessibleName('Review Cleanup' if title=='Run Cleanup' else title)
        self.setToolTip('Open the explicit review workflow; no files are changed by this button.')
        self.clicked.connect(handler)

    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        rect=QRectF(self.rect()).adjusted(1,1,-1,-1)
        fill=QLinearGradient(0,0,0,self.height())
        fill.setColorAt(0,QColor('#9F1828')); fill.setColorAt(.45,QColor('#7A101D')); fill.setColorAt(1,QColor('#A51A29'))
        p.setBrush(fill); p.setPen(QPen(QColor('#E12C42'),1.2)); p.drawRoundedRect(rect,8,8)
        p.save(); clip=QPainterPath(); clip.addRoundedRect(rect,8,8); p.setClipPath(clip)
        glow=QRadialGradient(self.width()*.52,self.height()*1.2,self.width()*.52)
        glow.setColorAt(0,QColor(255,33,56,110 if self.underMouse() else 75)); glow.setColorAt(1,QColor(240,25,42,0))
        p.fillRect(rect,glow); p.restore()
        p.setFont(_font(20,True)); p.setPen(QColor('#FFFFFF'))
        length=p.fontMetrics().horizontalAdvance(self.text())
        start=(self.width()-length-40)/2
        p.drawPixmap(round(start),9,26,26,icon_pixmap(self.icon_name,'#FFFFFF',26))
        p.drawText(QRectF(start+40,0,length+4,self.height()),Qt.AlignVCenter,self.text())
        if self.hasFocus():
            p.setBrush(Qt.NoBrush); p.setPen(QPen(QColor('#FFC5CE'),1,Qt.DotLine)); p.drawRoundedRect(rect.adjusted(3,3,-3,-3),5,5)


class RecycledRing(QWidget):
    """Shaded decorative ring around actual logged bytes, not a progress score."""
    def __init__(self,amount,parent=None):
        super().__init__(parent); self.amount=max(0,amount)
        self.setFixedSize(184,184)
        self.setToolTip('Recorded Recycle Bin moves this month, not confirmed free space. Ring shading is decorative, not a percentage.')

    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        halo=QRadialGradient(92,99,96); halo.setColorAt(0,QColor(237,22,46,0)); halo.setColorAt(.72,QColor(237,22,46,14)); halo.setColorAt(1,QColor(237,22,46,0))
        p.fillRect(self.rect(),halo)
        ring=QRectF(16,12,152,152)
        gradient=QConicalGradient(92,88,90)
        for stop,color in ((0,'#F8364B'),(.20,'#AB1027'),(.48,'#CF1530'),(.73,'#FF304A'),(.84,'#342C3A'),(.97,'#222930'),(1,'#F8364B')):
            gradient.setColorAt(stop,QColor(color))
        p.setBrush(Qt.NoBrush); p.setPen(QPen(gradient,24)); p.drawEllipse(ring)
        p.setPen(QPen(QColor(255,98,119,95),1)); p.drawEllipse(ring.adjusted(-12,-12,12,12))
        p.setFont(_font(25,True)); p.setPen(QColor('#F7F8FA'))
        p.drawText(QRectF(20,65,144,39),Qt.AlignCenter,human_size(self.amount))
        p.setFont(_font(12)); p.setPen(QColor('#D6D5DB'))
        p.drawText(QRectF(20,104,144,23),Qt.AlignCenter,'Logged moves')


def load_cover(game):
    from gg_desktop.local_art import game_cover_path, game_banner_path
    source=game_cover_path(game) or game_banner_path(game)
    if not source: return QPixmap()
    reader=QImageReader(source); reader.setAutoTransform(True); size=reader.size()
    if (not size.isValid() or min(size.width(),size.height())<1 or max(size.width(),size.height())>8192 or size.width()*size.height()>32_000_000):
        return QPixmap()
    scale=min(1,720/max(size.width(),size.height()))
    if scale<1: reader.setScaledSize(QSize(round(size.width()*scale),round(size.height()*scale)))
    return QPixmap.fromImage(reader.read())


def associated_game(event,games):
    path=str(event.get('path','')).strip()
    if not path: return None
    for game in games:
        root=str(game.install_path or '').strip()
        if not root: continue
        try:
            if os.path.commonpath((os.path.normcase(os.path.abspath(path)),os.path.normcase(os.path.abspath(root))))==os.path.normcase(os.path.abspath(root)):
                return game
        except (ValueError,OSError): pass
    return None


def relative_time(raw):
    try:
        stamp=datetime.fromisoformat(str(raw).replace('Z','+00:00'))
        now=datetime.now().astimezone()
        if stamp.tzinfo is None: stamp=stamp.astimezone()
        age=max(0,(now-stamp).total_seconds())
        if age<60: return 'Just now'
        if age<3600: return f'{int(age//60)} min ago'
        if age<86400: return f'{int(age//3600)} hr ago'
        return stamp.strftime('%b %d')
    except (ValueError,TypeError,OverflowError): return 'Unknown time'


class ActivityRow(QPushButton):
    def __init__(self,event,game,handler):
        friendly=friendly_activity(event)
        super().__init__(); self.title=game.name if game else str(friendly['title'])
        self.detail=str(event.get('details','')) or str(friendly['explanation'])
        self.stamp=relative_time(event.get('date'))
        self.art=load_cover(game) if game else QPixmap()
        self.route='Mods' if 'mod' in str(event.get('kind','')).lower() else 'Undo Center'
        kind=str(event.get('kind','')).lower()
        self.state_icon=('mods' if 'mod' in kind else 'graveyard' if 'recycl' in kind
                         else 'check' if friendly.get('status')=='Done' else 'activity')
        self.state_color=('#F34D60' if 'recycl' in kind else '#4DDDB8'
                          if self.state_icon=='check' else '#CBD5DE')
        self.setFixedHeight(56); self.setObjectName('referenceActivityRow')
        self.setAccessibleName(self.title+'. '+self.detail)
        self.setToolTip(self.title+'\n'+self.detail); self.clicked.connect(handler)
        self.setStyleSheet('QPushButton#referenceActivityRow{background:transparent;border:0;padding:0;min-height:56px;max-height:56px;}')

    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing); p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setPen(QPen(QColor('#30363D'),1)); p.drawLine(0,55,self.width(),55)
        box=QRectF(5,5,58,46)
        if not self.art.isNull():
            p.save(); clip=QPainterPath(); clip.addRoundedRect(box,7,7); p.setClipPath(clip)
            scale=max(box.width()/self.art.width(),box.height()/self.art.height())
            sw,sh=box.width()/scale,box.height()/scale
            p.drawPixmap(box,self.art,QRectF((self.art.width()-sw)/2,(self.art.height()-sh)/2,sw,sh)); p.restore()
        else:
            p.drawPixmap(18,13,31,31,icon_pixmap(self.route,'#B2C5CF',31))
        width=max(60,self.width()-180)
        p.setFont(_font(16,True)); p.setPen(QColor('#F0F1F4'))
        p.drawText(QRectF(82,5,width,24),Qt.AlignVCenter,p.fontMetrics().elidedText(self.title,Qt.ElideRight,width))
        p.setFont(_font(13)); p.setPen(QColor('#BFC8D1'))
        p.drawText(QRectF(82,29,width,22),Qt.AlignVCenter,p.fontMetrics().elidedText(self.detail,Qt.ElideRight,width))
        p.setFont(_font(12)); p.setPen(QColor('#C5CBD3'))
        p.drawText(QRectF(self.width()-96,0,65,56),Qt.AlignRight|Qt.AlignVCenter,self.stamp)
        p.drawPixmap(self.width()-24,17,22,22,icon_pixmap(self.state_icon,self.state_color,22))
        paint_focus(p,self)


class LibraryCover(QPushButton):
    def __init__(self,game,pixmap,open_game,official):
        super().__init__(); self.game=game; self.art=pixmap; self.has_cover=official
        self.setObjectName('approvedCover'); self.setFixedHeight(210); self.setMinimumWidth(150)
        self.setAccessibleName('Inspect '+game.name); self.setToolTip(game.name+' · '+game.launcher+('' if official else '\nArtwork not loaded'))
        self.clicked.connect(lambda:open_game(game))

    def sizeHint(self): return QSize(200,210)
    def minimumSizeHint(self): return QSize(150,210)

    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing); p.setRenderHint(QPainter.SmoothPixmapTransform)
        card=QRectF(1,1,self.width()-2,170)
        clip=QPainterPath(); clip.addRoundedRect(card,9,9)
        p.save(); p.setClipPath(clip); p.fillRect(card,QColor('#0E141B'))
        crop=QPixmap()
        if self.has_cover and not self.art.isNull():
            crop=self.art.scaled(card.size().toSize(),Qt.KeepAspectRatioByExpanding,Qt.SmoothTransformation)
            p.drawPixmap(card,crop,QRectF((crop.width()-card.width())/2,(crop.height()-card.height())/2,card.width(),card.height()))
        else:
            p.setFont(_font(15,True)); p.setPen(QColor('#D6DDE5'))
            p.drawText(card.adjusted(12,12,-12,-35),Qt.AlignCenter|Qt.TextWordWrap,self.game.name)
            p.setFont(_font(10)); p.setPen(QColor('#8B9BA9'))
            p.drawText(card.adjusted(6,130,-6,-4),Qt.AlignCenter,'Cover not loaded')
        p.restore(); p.setBrush(Qt.NoBrush); p.setPen(QPen(QColor('#A44A5B' if self.hasFocus() or self.underMouse() else '#35404B'),1))
        p.drawRoundedRect(card,9,9)
        if not crop.isNull():
            reflection=QPixmap(crop.size()); reflection.fill(Qt.transparent)
            rp=QPainter(reflection); rp.translate(0,crop.height()); rp.scale(1,-1); rp.drawPixmap(0,0,crop); rp.end()
            p.save(); p.setOpacity(.16)
            p.drawPixmap(QRectF(1,178,self.width()-2,27),reflection,QRectF((crop.width()-card.width())/2,0,card.width(),min(35,crop.height())))
            p.setOpacity(1); fade=QLinearGradient(0,178,0,205); fade.setColorAt(0,QColor(9,13,16,0)); fade.setColorAt(1,QColor('#090D10'))
            p.fillRect(QRectF(0,178,self.width(),29),fade); p.restore()


class CoverShelf(QWidget):
    def __init__(self,games,inspect):
        super().__init__(); self.setObjectName('referenceCoverShelf')
        self.setMinimumHeight(232); self.cards=[]; self.visible_count=6
        col=_stack(self,gap=0); line=QWidget(); r=_line(line,gap=10)
        col.setAlignment(Qt.AlignTop)
        line.setFixedHeight(212)
        self.scroll=QScrollArea(); self.scroll.setObjectName('approvedLibraryScroll')
        self.scroll.setFrameShape(QFrame.NoFrame); self.scroll.setWidgetResizable(False)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFixedHeight(212); r.addWidget(self.scroll,1)
        r.setAlignment(self.scroll,Qt.AlignTop)
        self.body=QWidget(); self.body.setStyleSheet('background:transparent;')
        self.row=_line(self.body,gap=10)
        self.row.setAlignment(Qt.AlignLeft|Qt.AlignTop)
        for game in games[:24]:
            art=load_cover(game); card=LibraryCover(game,art,inspect,not art.isNull())
            self.cards.append(card); self.row.addWidget(card)
        self.scroll.setWidget(self.body)
        arrows=QWidget(); arrows.setFixedHeight(172); ar=_line(arrows,gap=5)
        for symbol,delta in (('back',-1),('chevron',1)):
            control=button('',lambda _=False,d=delta:self.advance(d))
            control.setAccessibleName(('Previous' if delta<0 else 'Next')+' library page')
            control.setIcon(outline_icon(symbol)); control.setIconSize(QSize(17,17)); control.setFixedSize(28,30)
            control.setStyleSheet('QPushButton{border:1px solid #333C45;border-radius:14px;padding:0;background:#131A21;}')
            ar.addWidget(control)
        r.addWidget(arrows); r.setAlignment(arrows,Qt.AlignTop); col.addWidget(line)
        self.dots=QWidget(); self.dotrow=_line(self.dots,gap=7)
        self.dots.setParent(self)
        self.dotrow.setAlignment(Qt.AlignCenter)
        self.scroll.horizontalScrollBar().valueChanged.connect(self.update_dots)
        QTimer.singleShot(0,self.arrange)

    def resizeEvent(self,event):
        super().resizeEvent(event); self.arrange()

    def minimumSizeHint(self): return QSize(0,232)

    def arrange(self):
        width=max(150,self.scroll.viewport().width())
        self.visible_count=max(1,min(6,(width+10)//180))
        card_width=max(150,(width-(self.visible_count-1)*10)//self.visible_count)
        self.page_stride=self.visible_count*(card_width+10)
        for card in self.cards: card.setFixedWidth(card_width)
        count=max(1,math.ceil(len(self.cards)/self.visible_count))
        self.body.setFixedSize((count-1)*self.page_stride+width,210)
        if self.dotrow.count()!=count:
            while self.dotrow.count(): self.dotrow.takeAt(0).widget().deleteLater()
            for index in range(count):
                dot=button('',lambda _=False,i=index:self.goto(i))
                dot.setAccessibleName(f'Library page {index+1}'); dot.setFixedSize(17,8)
                self.dotrow.addWidget(dot)
        self.update_dots()
        self.dots.setGeometry(0,194,self.width(),18)
        self.dots.raise_()

    def goto(self,index):
        self.scroll.horizontalScrollBar().setValue(index*self.page_stride)

    def advance(self,delta):
        bar=self.scroll.horizontalScrollBar()
        self.goto(round(bar.value()/max(1,self.page_stride))+delta)

    def update_dots(self,*_):
        index=round(self.scroll.horizontalScrollBar().value()/max(1,getattr(self,'page_stride',1)))
        for i in range(self.dotrow.count()):
            dot=self.dotrow.itemAt(i).widget(); color='#F52D48' if i==index else '#454B52'
            dot.setStyleSheet(f'QPushButton{{background:{color};border:0;border-radius:4px;padding:0;min-height:0;min-width:0;}}')


def _section(title,icon,trailing=None):
    frame=QFrame(); frame.setObjectName('approvedOverviewPanel')
    frame.setStyleSheet('QFrame#approvedOverviewPanel{background:transparent;border:0;}')
    col=_stack(frame,gap=7); header=QWidget(); h=_line(header,gap=12)
    glyph=QLabel(); glyph.setPixmap(icon_pixmap(icon,'#F42F48',33,True)); glyph.setFixedSize(34,36)
    h.addWidget(glyph); h.addWidget(_txt(title,22,bold=True),1)
    if trailing is not None: h.addWidget(trailing)
    header.setFixedHeight(40); col.addWidget(header)
    return frame,col


def _link(text,handler,accessible=None):
    b=button(text,handler); b.setAccessibleName(accessible or text)
    b.setStyleSheet('QPushButton{background:transparent;border:0;padding:3px;font-size:14px;font-weight:400;} QPushButton:hover{color:#FFFFFF;}')
    return b


def _monthly_moves():
    now = datetime.now().astimezone()
    amount, count = 0, 0
    recent = []
    for record in reversed(get_records()):
        if not isinstance(record, dict):
            continue
        try:
            when = datetime.fromisoformat(str(record["time"]))
            size = record["size"]
            if type(size) is not int or size < 0:
                continue
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if when.year == now.year and when.month == now.month:
            amount += size
            count += 1
        if len(recent) < 6:
            recent.append(record)
    return amount, count, recent



def render_approved_overview(window):
    page=window.page_for('Overview')
    page.content.setContentsMargins(37,0,27,11); page.content.setSpacing(0)
    page.content.addWidget(DashboardHero())
    inventory=window.inventory; found=bool(inventory.scanned_at)
    metrics=ResponsiveGrid(columns=((0,1),(430,2),(970,5)),spacing=0,
                           stretches={5:(17,20,20,20,20)})
    metrics.setObjectName('approvedMetrics')
    values=(
        ('Games',str(len(inventory.games)) if found else '—','Games','Verified installed game records'),
        ('Mods',str(len(inventory.mods)) if found else '—','Mods','Discovered mod locations, not individual mods'),
        ('Old Files',human_size(sum(max(0,f.size) for f in inventory.files)) if found else '—','Old Files','Apparent bytes, not confirmed reclaimable space'),
        ('Other Storage','Explore','Other Storage','Analyze other storage explicitly'),
        ('Captures',str(len(inventory.screenshots)+len(inventory.recordings)) if found else '—','Captures','Discovered screenshot and recording files'))
    for index,(title,value,route,explanation) in enumerate(values):
        if not found and route!='Other Storage': explanation='Not scanned. '+explanation
        metrics.addWidget(MetricButton(title,value,COLORS[index],route,
            lambda _=False,r=route:window.navigate(r),explanation,padding=22 if index==0 else 44))
    page.content.addWidget(metrics); page.content.addSpacing(25)
    center=ResponsiveRow(breakpoint=970,spacing=28,horizontal_height=300)
    center.setObjectName('referenceOverviewColumns')
    history=_link('View History  →',lambda:window.navigate('Undo Center'),'Undo Center · View History')
    activity_panel,activity=_section('Recent Activity','activity',history)
    events=get_activity(limit=4)
    if events:
        for event in events:
            game=associated_game(event,inventory.games)
            kind=str(event.get('kind','')).lower()
            route='Mods' if 'mod' in kind else 'Undo Center' if 'recycl' in kind or 'restor' in kind else 'Games'
            activity.addWidget(ActivityRow(event,game,lambda _=False,r=route:window.navigate(r)))
    else:
        activity.addWidget(_txt('Your local scan and review history will appear here.',15,color='#ACB8C5',wrap=True))
        activity.addWidget(_link('Scan your library  →',window.start_scan,'Scan Library'))
    activity.addStretch(); center.addWidget(activity_panel,27)
    amount,count,_=_monthly_moves()
    reclaim,rc=_section('Space Reclaimed','other storage')
    rc.setContentsMargins(7,0,25,0)
    body=QWidget(); ringrow=_line(body,gap=17)
    ringrow.addWidget(RecycledRing(amount))
    facts=QWidget(); fc=_stack(facts,gap=12)
    data=(('Old Files',human_size(sum(max(0,f.size) for f in inventory.files)) if found else 'Unknown','#F2B163'),
          ('Other Storage','Not analyzed','#3AE2D1'),
          ('Mod locations',str(len(inventory.mods)) if found else 'Unknown','#C886DE'),
          ('Captures',human_size(sum(max(0,f.size) for f in inventory.screenshots+inventory.recordings)) if found else 'Unknown','#728FFF'))
    for title,value,color in data:
        line=QWidget(); line_layout=_line(line,gap=7)
        dot=_txt('●',12,color=color); dot.setFixedWidth(12); line_layout.addWidget(dot)
        line_layout.addWidget(_txt(title,13),1); line_layout.addWidget(_txt(value,13,bold=True))
        fc.addWidget(line)
    ringrow.addWidget(facts,1); rc.addWidget(body,1)
    rc.addWidget(_txt('Moved this month · not confirmed free space',11,color='#AAB7C3'))
    rc.addWidget(CleanupButton(lambda:window.navigate('Graveyard')))
    center.addWidget(reclaim,25)
    quick,qc=_section('Quick Actions','quick')
    for name,callback in (('Scan Library',window.start_scan),
        ('Find Unused Mods',lambda:window.navigate('Mods')),
        ('Review Old Files',lambda:window.navigate('Old Files')),
        ('Manage Captures',lambda:window.navigate('Captures')),
        ('Open Graveyard',lambda:window.navigate('Graveyard'))):
        qc.addWidget(EdgeAction(name,callback))
    qc.addStretch(); center.addWidget(quick,16)
    page.content.addWidget(center); page.content.addSpacing(13)
    library=QFrame(); library.setObjectName('referenceLibrarySection')
    library.setStyleSheet('QFrame#referenceLibrarySection{background:transparent;border:0;border-top:1px solid #2C343D;}')
    lc=_stack(library,margin=(0,8,0,0),gap=10)
    header=QWidget(); hl=_line(header,gap=18)
    glyph=QLabel(); glyph.setFixedSize(36,38); glyph.setPixmap(icon_pixmap('Games','#F0F2F5',36)); hl.addWidget(glyph)
    hl.addWidget(_txt('Your Library',24,bold=True),1)
    if any(g.launcher=='Steam' and load_cover(g).isNull() for g in inventory.games[:24]):
        hl.addWidget(_link('Get Steam Covers',window._download_game_covers))
    hl.addWidget(_link('View All Games  →',lambda:window.navigate('Games'),'View all games'))
    header.setFixedHeight(42); lc.addWidget(header)
    if found and inventory.games:
        def inspect(game):
            window._pending_game_query=game.name; window.navigate('Games')
        lc.addWidget(CoverShelf(inventory.games,inspect))
    else:
        lc.addWidget(_txt('Your verified game library appears after a scan.',15,color='#B8C3CF'))
        lc.addWidget(_link('Scan your library  →',window.start_scan,'Scan Library'))
    page.content.addWidget(library)
    if inventory.warnings:
        page.content.addWidget(_txt('Scan coverage: '+' '.join(str(w) for w in inventory.warnings[:3]),11,color='#E8B97A',wrap=True))
    return page
