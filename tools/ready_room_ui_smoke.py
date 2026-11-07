"""Verify Ready Room uses the native app scale without zooming on navigation."""
from __future__ import annotations
import argparse
from dataclasses import asdict
import os
from pathlib import Path
import sys
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('_ci_temp'))
    args = parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    if sys.platform.startswith('linux'):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QGraphicsView, QLabel, QMainWindow, QPushButton, QScrollArea
    from core import default_settings
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.ready_room import ReadyRoomPage
    app = QApplication.instance() or QApplication([])
    def settle():
        QTest.qWait(50)
        app.processEvents()
    def click(widget):
        QTest.mouseClick(widget,Qt.LeftButton)
        settle()
    def button(window,text):
        return next(b for b in window.page.findChildren(QPushButton) if b.text()==text)
    def shell(window):
        return (window.size().toTuple(),window.nav_rail.width(),window.top_bar.height(),
            window.brand.geometry().getRect(),window.global_search.font().toString(),
            # The shared active-tab border adds two pixels to its button height.
            tuple((name,control.width(),control.font().toString(),control.iconSize().toTuple())
                  for name,control in window.nav_buttons.items()))
    def reachable(window):
        page=window.page
        assert page.horizontalScrollBar().maximum()==0
        page.verticalScrollBar().setValue(page.verticalScrollBar().maximum())
        settle()
        bottom=page.health_panel.mapTo(page.viewport(),QPoint(0,page.health_panel.height()-1)).y()
        assert 0<=bottom<page.viewport().height(),('Footer unreachable',bottom)
        page.verticalScrollBar().setValue(0)
        settle()
    with patch('gg_desktop.app.load_settings',side_effect=default_settings), \
         patch.object(CrimsonWindow,'start_scan') as scan, \
         patch.object(CrimsonWindow,'_create_save_backup') as backup, \
         patch.object(CrimsonWindow,'info') as info, \
         patch.object(CrimsonWindow,'showMinimized') as minimize, \
         patch.object(CrimsonWindow,'_toggle_maximize') as maximize, \
         patch.object(CrimsonWindow,'close') as close:
        window=CrimsonWindow(reference_preview=True)
        window.show()
        settle()
        initial=asdict(window.inventory)
        shared_search=window.global_search
        progress_parent=window.progress.parentWidget()
        for width,height in ((1280,720),(1536,864),(1450,900),(960,650),(1600,720)):
            window.navigate('Games')
            window.resize(width,height)
            settle()
            original=shell(window)
            for _ in range(2):
                click(window.nav_buttons['Ready Room'])
                page=window.page
                assert isinstance(page,ReadyRoomPage) and isinstance(page,QScrollArea)
                assert not isinstance(page,QGraphicsView)
                assert window.global_search is shared_search and page.search is shared_search
                assert window.progress.parentWidget() is progress_parent
                assert window.nav_rail.isVisible() and window.top_bar.isVisible()
                assert shell(window)==original,'Tab click changed app geometry or font scale'
                assert window.nav_rail.width()==219 and window.top_bar.height()==46
                assert page.findChild(QLabel,'readyTitle').font().pixelSize()==36
                assert all(row.height()==41 for row in page.findChildren(QPushButton,'readyItem'))
                point=page.reference_point(page.patches)
                assert point==QPoint(230,273 if page.compact else 215),(point,width)
                assert len(page.visible_patches)==len(page.visible_games)==5
                reachable(window)
                for modifier in (Qt.NoModifier,Qt.ControlModifier):
                    local=QPoint(8,8)
                    event=QWheelEvent(QPointF(local),QPointF(page.viewport().mapToGlobal(local)),QPoint(),QPoint(0,120),
                        Qt.NoButton,modifier,Qt.NoScrollPhase,False)
                    QApplication.sendEvent(page.viewport(),event)
                    settle()
                    assert shell(window)==original,'Wheel event changed app scale'
                    assert page.findChild(QLabel,'readyTitle').font().pixelSize()==36
                page.verticalScrollBar().setValue(0)
                assert window.grab().save(str(args.output/f'ready-room-reference-{width}.png'))
                click(window.nav_buttons['Games'])
                assert shell(window)==original
        window.resize(1536,864)
        click(window.nav_buttons['Ready Room'])
        size=window.size()
        window.activateWindow()
        QTest.keyClick(window,Qt.Key_K,Qt.ControlModifier)
        settle()
        assert window.page.search.hasFocus()
        window.page.search.setText('WITCHER')
        assert len(window.page.visible_patches)==len(window.page.visible_games)==1
        QTest.keyClick(window.page.search,Qt.Key_Escape)
        settle()
        assert not window.page.search.text()
        click(window.page.patches.findChild(QPushButton,'readyItem'))
        info.assert_called()
        assert window.size()==size,'Panel click resized the app'
        info.reset_mock()
        click(window.page.metric_buttons[0])
        info.assert_called()
        click(button(window,'Run Mod Scan'))
        scan.assert_called_once()
        click(button(window,'Backup Now'))
        backup.assert_called_once()
        for name,mock in (('Minimize',minimize),('Maximize or restore',maximize),('Close',close)):
            control=next(b for b in window.findChildren(QPushButton) if b.accessibleName()==name)
            click(control)
            mock.assert_called_once()
        click(button(window,'View Mods  →'))
        assert window.current_route=='Mods'
        QTest.keyClick(window,Qt.Key_K,Qt.ControlModifier)
        settle()
        assert window.global_search is shared_search and shared_search.hasFocus()
        click(window.nav_buttons['Ready Room'])
        click(button(window,'Manage Saves  →'))
        assert window.current_route=='More Tools'
        assert asdict(window.inventory)==initial
        QMainWindow.close(window)
        normal=CrimsonWindow()
        normal.show()
        normal.resize(1450,900)
        settle()
        expected=shell(normal)
        click(normal.nav_buttons['Ready Room'])
        assert not normal.page.data.reference and shell(normal)==expected
        normal.ready_reload()
        settle()
        assert shell(normal)==expected,'Live refresh changed app scale'
        assert normal.page.reference_note is None
        QMainWindow.close(normal)
    print('PASS: Ready Room uses the same native sidebar/header, geometry and font scale across five sizes. Repeated tab clicks, panel clicks, live refresh, wheel/Ctrl+wheel do not zoom or resize the app; responsive footer, search, window controls and existing actions pass.')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
