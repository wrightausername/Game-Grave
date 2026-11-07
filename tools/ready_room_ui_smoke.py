"""Exercise the exact Ready Room design surface and its native controls."""
from __future__ import annotations
import argparse
from dataclasses import asdict
import os
from pathlib import Path
import sys
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=Path("_ci_temp"))
    args = parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton
    from core import default_settings
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.ready_room import ReadyRoomPage
    app = QApplication.instance() or QApplication([])
    def settle():
        QTest.qWait(40)
        app.processEvents()
    def click(window,widget):
        point = window.page.reference_point(widget,widget.rect().center())
        viewport = window.page.viewport()
        QTest.mouseClick(viewport,Qt.LeftButton,pos=viewport.mapFrom(window,point))
        settle()
    def button(window,text):
        return next(b for b in window.page.findChildren(QPushButton) if b.text()==text)
    with patch("gg_desktop.app.load_settings",side_effect=default_settings), \
         patch.object(CrimsonWindow,"start_scan") as scan, \
         patch.object(CrimsonWindow,"_create_save_backup") as backup, \
         patch.object(CrimsonWindow,"info") as info, \
         patch.object(CrimsonWindow,"showMinimized") as minimize, \
         patch.object(CrimsonWindow,"_toggle_maximize") as maximize, \
         patch.object(CrimsonWindow,"close") as close:
        window=CrimsonWindow(reference_preview=True)
        window.show()
        settle()
        assert isinstance(window.page,ReadyRoomPage)
        initial=asdict(window.inventory)
        for width,height in ((1280,720),(1536,864),(1440,810),(960,650),(1600,720)):
            window.resize(width,height)
            settle()
            page=window.page
            scale=min(width/1280,height/720)
            assert abs(page.transform().m11()-scale)<.001
            assert page.horizontalScrollBar().maximum()==0
            assert page.verticalScrollBar().maximum()==0
            point=page.reference_point(page.patches)
            assert abs(point.x()-230*scale)<=1 and abs(point.y()-215*scale)<=1,(point,width)
            point=page.reference_point(page.mod_panel)
            assert abs(point.x()-230*scale)<=1 and abs(point.y()-498*scale)<=1,(point,width)
            assert len(page.visible_patches)==len(page.visible_games)==5
            assert not window.nav_rail.isVisible() and not window.top_bar.isVisible()
            assert window.grab().save(str(args.output/f"ready-room-reference-{width}.png"))
        window.resize(1536,864)
        settle()
        window.activateWindow()
        QTest.keyClick(window,Qt.Key_K,Qt.ControlModifier)
        settle()
        assert window.page.search.hasFocus(),"Ctrl+K did not focus the scaled native search"
        window.page.search.setText("WITCHER")
        assert len(window.page.visible_patches)==len(window.page.visible_games)==1
        QTest.keyClick(window.page.search,Qt.Key_Escape)
        settle()
        assert not window.page.search.text()
        assert len(window.page.visible_patches)==5
        patch_row=window.page.patches.findChild(QPushButton,"readyItem")
        click(window,patch_row)
        info.assert_called()
        info.reset_mock()
        click(window,window.page.metric_buttons[0])
        info.assert_called()
        click(window,button(window,"Run Mod Scan"))
        scan.assert_called_once()
        click(window,button(window,"Backup Now"))
        backup.assert_called_once()
        for name,mock in (("Minimize",minimize),("Maximize or restore",maximize),("Close",close)):
            control=next(b for b in window.page.findChildren(QPushButton) if b.accessibleName()==name)
            click(window,control)
            mock.assert_called_once()
        click(window,button(window,"View Mods  →"))
        assert window.current_route=="Mods"
        assert window.nav_rail.isVisible() and window.top_bar.isVisible()
        assert window.global_search.isVisible()
        QTest.keyClick(window,Qt.Key_K,Qt.ControlModifier)
        settle()
        assert window.global_search.hasFocus(),"Shared search shortcut was not restored"
        window.navigate("Ready Room")
        settle()
        click(window,button(window,"Manage Saves  →"))
        assert window.current_route=="More Tools"
        assert asdict(window.inventory)==initial
        QMainWindow.close(window)
    print("PASS: Ready Room reference rectangles at five sizes, actual scaled mouse targets, search/keyboard, metric and row actions, mod scan, backup, native window controls and shell restoration. No live scan or source-file changes.")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
