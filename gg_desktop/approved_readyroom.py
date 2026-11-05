"""Ready Room reference composition over the existing local evidence workflows.

Official patch feeds, mod compatibility, backup coverage and health percentages
are not available. Preserve the pictured hierarchy without inventing them.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QSize, QTimer
from PySide6.QtGui import QColor,QPainter,QPen,QPainterPath,QFont,QRadialGradient
from PySide6.QtWidgets import QFrame,QWidget,QLabel,QPushButton,QTableWidget,QVBoxLayout

from core import human_size
from gg_desktop.approved_overview import (
    DashboardHero,MetricButton,CleanupButton,EdgeAction,load_cover,
    _font,_line,_stack,_txt,_link)
from gg_desktop.reference_hero import ReferenceHero
from gg_desktop.reference_chrome import GlassPanel,icon_pixmap
from gg_desktop.responsive import ResponsiveRow,ResponsiveGrid


class RoomHero(ReferenceHero):
    def __init__(self):
        super().__init__('readyroom','Ready Room','')
        self.title='Ready Room'
        self.subtitle='Your mission hub for updates, patches, mod alerts, and a live pulse on your games.'
        for child in self.findChildren(QWidget): child.hide()
        self.setFixedHeight(123)

    paintEvent=DashboardHero.paintEvent


class RoomGameRow(QPushButton):
    def __init__(self,game,handler,patch=False):
        super().__init__(); self.game=game; self.patch=patch; self.art=load_cover(game)
        self.setObjectName('referenceRoomGameRow'); self.setFixedHeight(55)
        self.setStyleSheet('QPushButton#referenceRoomGameRow{min-height:55px;max-height:55px;background:transparent;border:0;padding:0;}')
        self.setAccessibleName(game.name+('. Official update status not connected.' if patch else '. '+game.status))
        self.setToolTip('Official update and compatibility status has not been verified.\n'+game.install_path)
        self.clicked.connect(lambda:handler(game))

    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing); p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setPen(QPen(QColor('#303840'),1)); p.drawLine(0,54,self.width(),54)
        art_width=min(180,self.width()*.235) if self.patch else 94
        box=QRectF(0,4,art_width,46)
        if not self.art.isNull():
            p.save(); clip=QPainterPath(); clip.addRoundedRect(box,7,7); p.setClipPath(clip)
            scale=max(box.width()/self.art.width(),box.height()/self.art.height()); sw,sh=box.width()/scale,box.height()/scale
            p.drawPixmap(box,self.art,QRectF((self.art.width()-sw)/2,(self.art.height()-sh)/2,sw,sh)); p.restore()
        else:
            p.setBrush(QColor('#111B22')); p.setPen(QPen(QColor('#36434D'),1)); p.drawRoundedRect(box,7,7)
            p.drawPixmap(round(art_width/2-16),11,32,32,icon_pixmap('games','#A5BCCB',32))
        x=art_width+17; badge_width=120 if self.patch else 112
        remaining=max(70,self.width()-x-badge_width-20)
        p.setFont(_font(17,True)); p.setPen(QColor('#F0F2F5'))
        p.drawText(QRectF(x,2,remaining,26),Qt.AlignVCenter,p.fontMetrics().elidedText(self.game.name,Qt.ElideRight,round(remaining)))
        p.setFont(_font(13)); p.setPen(QColor('#C4CCD5'))
        detail='Official update source not connected' if self.patch else self.game.launcher+' · '+(human_size(self.game.size_bytes) if self.game.size_bytes is not None else 'Size unknown')
        p.drawText(QRectF(x,28,remaining,23),Qt.AlignVCenter,p.fontMetrics().elidedText(detail,Qt.ElideRight,round(remaining)))
        badge=QRectF(self.width()-badge_width,12,badge_width-1,31)
        p.setPen(QPen(QColor('#786139' if self.patch else '#375A4E'),1)); p.setBrush(QColor('#201C14' if self.patch else '#10201B'))
        p.drawRoundedRect(badge,7,7); p.setPen(QColor('#DEBA78' if self.patch else '#72D7AC')); p.setFont(_font(13))
        status='Installed' if str(self.game.status).lower().startswith('installed') else 'Review record'
        p.drawText(badge,Qt.AlignCenter,'Not connected' if self.patch else status)


def _room_panel(title,subtitle,icon,accent='#A13C4C',trailing=None):
    frame=GlassPanel(accent); col=_stack(frame,margin=(16,6,14,8),gap=0)
    header=QWidget(); h=_line(header,gap=12)
    glyph=QLabel(); glyph.setFixedSize(44,49); glyph.setPixmap(icon_pixmap(icon,'#F43A51',44,True)); h.addWidget(glyph)
    copy=QWidget(); words=_stack(copy,gap=0); words.addWidget(_txt(title,23,bold=True)); words.addWidget(_txt(subtitle,13))
    h.addWidget(copy,1)
    if trailing is not None: h.addWidget(trailing)
    header.setFixedHeight(55); col.addWidget(header)
    return frame,col


class HealthDial(QWidget):
    def __init__(self):
        super().__init__(); self.setFixedSize(151,151)
        self.setAccessibleName('Overall game health has not been assessed. No percentage is available.')

    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        halo=QRadialGradient(75,75,75); halo.setColorAt(0,QColor(45,184,109,0)); halo.setColorAt(.75,QColor(45,184,109,14)); halo.setColorAt(1,QColor(45,184,109,0)); p.fillRect(self.rect(),halo)
        p.setBrush(Qt.NoBrush); p.setPen(QPen(QColor('#34473E'),11)); p.drawArc(QRectF(13,13,125,125),-35*16,250*16)
        p.setPen(QPen(QColor('#60816C'),1)); p.drawArc(QRectF(7,7,137,137),-35*16,250*16)
        p.setFont(_font(35,True)); p.setPen(QColor('#F1F4F7')); p.drawText(QRectF(13,43,125,51),Qt.AlignCenter,'—')
        p.setFont(_font(12)); p.setPen(QColor('#B7C6BF')); p.drawText(QRectF(7,90,137,24),Qt.AlignCenter,'Not assessed')


def render_approved_readyroom(window):
    # Retain the existing sortable/searchable library intact as a disclosed
    # advanced view; its filters also drive the two reference summary lists.
    window.ready_room_page()
    page=window.page
    retained=None
    for i in reversed(range(page.content.count())):
        item=page.content.takeAt(i); widget=item.widget()
        if widget is None: continue
        if widget.findChildren(QTableWidget,'readyRoomTable'):
            retained=widget; widget.hide()
        else:
            widget.hide(); widget.setParent(None); widget.deleteLater()
    page.content.setContentsMargins(18,0,12,10); page.content.setSpacing(0)
    page.content.addWidget(RoomHero())
    def feed_status():
        window.info('Patch Watch sources','Official update, release and maintenance feeds are not connected.\n\nInstalled game records and local scan warnings remain available. No patch or compatibility verdict is inferred from those records.')
    metrics=ResponsiveGrid(columns=((0,1),(520,2),(970,5)),spacing=0)
    for title,icon,color in (
        ('Game Updates','updates','#FF4C5C'),('Mod Alerts','cube','#DA9AE8'),
        ('Maintenance','maintenance','#F1B357'),('New Releases','download','#47E7E0'),
        ('Followed Games','star','#71C3FF')):
        metrics.addWidget(MetricButton(title,'—',color,icon,feed_status,
            'This source has not been connected or assessed; no count is available.',True))
    page.content.addWidget(metrics); page.content.addSpacing(10)
    workspace=ResponsiveRow(breakpoint=1050,spacing=16,horizontal_height=350)
    workspace.setObjectName('referenceReadyRoomLists')
    patch,patch_col=_room_panel('Patch Watch','Official updates, hotfixes, and maintenance for your games.','layers',
        trailing=_link('View All Updates  →',feed_status))
    patch_rows=QWidget(); pl=_stack(patch_rows,gap=0); patch_col.addWidget(patch_rows,1)
    glance,glance_col=_room_panel('Your Games - At a Glance',"Your installed games and the latest local evidence.",'games')
    glance_rows=QWidget(); gl=_stack(glance_rows,gap=0); glance_col.addWidget(glance_rows,1)
    workspace.addWidget(patch,61); workspace.addWidget(glance,39)
    page.content.addWidget(workspace); page.content.addSpacing(18)
    def inspect(game):
        window._pending_game_query=game.name; window.navigate('Games')
    table=page.findChild(QTableWidget,'readyRoomTable') if retained is None else retained.findChild(QTableWidget,'readyRoomTable')
    def refresh_lists():
        lookup={game.key:game for game in window.inventory.games}
        games=[]
        if table is not None:
            games=[lookup.get(table.item(row,0).data(Qt.UserRole)) for row in range(min(5,table.rowCount()))]
            games=[game for game in games if game is not None]
        else: games=list(window.inventory.games[:5])
        for layout in (pl,gl):
            while layout.count():
                item=layout.takeAt(0)
                if item.widget(): item.widget().hide(); item.widget().deleteLater()
        if games:
            for game in games:
                pl.addWidget(RoomGameRow(game,inspect,True)); gl.addWidget(RoomGameRow(game,inspect))
        else:
            for layout in (pl,gl):
                layout.addWidget(_txt('Scan your library to populate this view.',15,color='#A6B7C7',wrap=True))
                layout.addWidget(_link('Scan library  →',window.start_scan))
        pl.addStretch(); gl.addStretch()
    refresh_lists()
    if table is not None:
        timer=QTimer(page); timer.setSingleShot(True); timer.timeout.connect(refresh_lists)
        for signal in (table.model().dataChanged,table.model().rowsInserted,table.model().modelReset):
            signal.connect(lambda *_:timer.start(0))
    lower=ResponsiveRow(breakpoint=1060,spacing=16,horizontal_height=252)
    lower.setObjectName('referenceReadyRoomTools')
    mods,mc=_room_panel('Mod Radar','Detected managers and local scan evidence.','mods')
    mod_body=QWidget(); mr=_line(mod_body,gap=16)
    status=QWidget(); sc=_stack(status,gap=2)
    symbol=QLabel(); symbol.setAlignment(Qt.AlignCenter); symbol.setPixmap(icon_pixmap('mods','#A5AFC6',53,True)); sc.addWidget(symbol)
    review=_txt('Review',22,bold=True); review.setAlignment(Qt.AlignCenter); sc.addWidget(review)
    sc.addWidget(_txt('Compatibility unverified',11,color='#AFBACA')); mr.addWidget(status,1)
    facts=QWidget(); fc=_stack(facts,gap=10)
    for value,title in ((str(len(window.inventory.mods)) if window.inventory.scanned_at else '—','Detected locations'),('—','Update checks'),('—','Compatibility checks')):
        pair=QWidget(); h=_line(pair,gap=9); h.addWidget(_txt(value,18,bold=True)); h.addWidget(_txt(title,12),1); fc.addWidget(pair)
    mr.addWidget(facts,1); mc.addWidget(mod_body,1)
    mod_actions=QWidget(); ma=_line(mod_actions,gap=12)
    ma.addWidget(_link('View Mods  →',lambda:window.navigate('Mods')))
    ma.addWidget(CleanupButton(window.start_scan,'Run Mod Scan','ready room'))
    mc.addWidget(mod_actions); lower.addWidget(mods,35)
    saves,sc=_room_panel('Save Vault','Protect and manage your game saves.','save')
    save_body=QWidget(); sr=_line(save_body,gap=14)
    disk=QLabel(); disk.setFixedSize(83,83); disk.setPixmap(icon_pixmap('other storage','#5DECB3',83,True)); sr.addWidget(disk)
    copy=QWidget(); vc=_stack(copy,gap=7)
    vc.addWidget(_txt((str(len(window.inventory.saves))+' Save Locations')
        if window.inventory.scanned_at else 'Not scanned',21,bold=True,wrap=True))
    vc.addWidget(_txt('Backup coverage not verified',13,color='#B5C4CC',wrap=True)); sr.addWidget(copy,1)
    sc.addWidget(save_body,1)
    save_actions=QWidget(); sa=_line(save_actions,gap=12)
    sa.addWidget(_link('Manage Saves  →',lambda:window.navigate('More Tools')))
    sa.addWidget(CleanupButton(window._create_save_backup,'Backup Now','save'))
    sc.addWidget(save_actions); lower.addWidget(saves,33)
    health,hc=_room_panel('System & Game Health','Quick checks to keep everything running smoothly.','activity')
    health_body=QWidget(); hr=_line(health_body,gap=8); hr.addWidget(HealthDial())
    facts=QWidget(); fc=_stack(facts,gap=9)
    for text,confirmed in (
        ('Inventory scanned',bool(window.inventory.scanned_at)),
        (str(len(window.inventory.warnings))+' scan warnings',not bool(window.inventory.warnings) and bool(window.inventory.scanned_at)),
        ('Save protection enabled',True),('Game files not verified',False)):
        line=QWidget(); line_layout=_line(line,gap=8)
        icon=QLabel(); icon.setFixedSize(21,21); icon.setPixmap(icon_pixmap('check' if confirmed else 'help','#55DC9B' if confirmed else '#D5B16D',21)); line_layout.addWidget(icon)
        line_layout.addWidget(_txt(text,12,color='#D6DFE5',wrap=True),1); fc.addWidget(line)
    hr.addWidget(facts,1); hc.addWidget(health_body,1); lower.addWidget(health,33)
    page.content.addWidget(lower)
    if retained is not None:
        toggle=_link('Search and sort installed games  ›',lambda:retained.setVisible(not retained.isVisible()))
        toggle.setAccessibleName('Show or hide searchable Ready Room game inventory')
        page.content.addWidget(toggle); page.content.addWidget(retained); retained.hide()
    return page
