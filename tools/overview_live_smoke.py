"""Exercise the actual photo-layout Overview with disposable files and Qt events."""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import traceback
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("_ci_temp"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PIL import Image
    from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt, QTimer
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QDialogButtonBox, QLabel, QLineEdit, QListWidget, QPushButton, QTableWidget
    from core import OldFile, SteamGame, default_settings
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.backend import Inventory, ScanCanceled
    from gg_desktop.models import merge_games
    from gg_desktop.overview_storage import measure_storage
    from gg_desktop.reference_widgets import CARD_ROLE
    from tests.test_mods_functionality import mo2_fixture

    app = QApplication.instance() or QApplication([])
    def settle():
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
    def wait_for(predicate):
        deadline = time.monotonic()+20
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
            # Yield the Python GIL as well as Qt events on native Windows.
            time.sleep(.004)
        if not predicate():
            for ident, frame in sys._current_frames().items():
                print("Overview QA thread", ident, "".join(traceback.format_stack(frame)[-8:]), flush=True)
        assert predicate(), "Overview operation did not finish"
        settle()
    def click(parent, text):
        control = next(b for b in parent.findChildren(QPushButton) if b.text() == text)
        assert control.isEnabled(), "Disabled Overview button: " + text
        control.click()
        settle()
    def drive_dialog(open_dialog, action):
        errors=[]
        def execute():
            dialog = app.activeModalWidget()
            try:
                assert isinstance(dialog, QDialog), "Missing Overview dialog"
                action(dialog)
            except Exception as exc:
                errors.append(exc)
                if dialog:
                    dialog.reject()
        QTimer.singleShot(20, execute)
        open_dialog()
        if errors:
            raise errors[0]
        settle()
    def record(path):
        st=path.stat()
        return OldFile(str(path),st.st_size,st.st_mtime,st.st_dev,st.st_ino,st.st_mtime_ns,st.st_nlink)

    with tempfile.TemporaryDirectory(prefix="GG-overview-live-") as temp:
        root=Path(temp)
        inventory, storage, profiles, ini=mo2_fixture(root)
        titles=[("1091500","Cyberpunk 2077"),("1086940","Baldur's Gate 3"),
                ("292030","The Witcher 3: Wild Hunt"),("1716740","Starfield"),
                ("489830","Skyrim Special Edition"),("1174180","Red Dead Redemption 2"),
                ("1245620","Elden Ring"),("553850","Helldivers 2")]
        steam_root=root/"Steam"
        (steam_root/"steamapps").mkdir(parents=True)
        games=[]
        for i,(app_id,name) in enumerate(titles):
            path=root/"Games"/app_id
            path.mkdir()
            (path/"base.bin").write_bytes(b"G"*(70000+i*20000))
            games.append(SteamGame(app_id,name,str(steam_root),str(path),0,None,"Disposable QA metadata"))
        ini.write_text(ini.read_text().replace(inventory.games[0].install_path,games[4].install_path))
        inventory.steam=games
        inventory.games=merge_games(games,[])
        payload=storage/"MountainTextures/texture.bin"
        payload.write_bytes(b"M"*450000)
        os.link(payload,Path(games[4].install_path)/"deployed-texture.bin")
        old=root/"Downloads/old-mod.zip"
        old.parent.mkdir()
        old.write_bytes(b"A"*180000)
        image=root/"Captures/old-game.png"
        image.parent.mkdir()
        Image.new("RGB",(320,180),"#374858").save(image)
        inventory.files=[record(old),record(image)]
        inventory.screenshots=[record(image)]
        inventory.scanned_at="Disposable Overview QA"
        before=deepcopy(inventory)
        preferences=default_settings()
        preferences.update(scan_on_launch=False,scan_folder=str(old.parent),steam_extra_roots=[str(steam_root)])
        activity=[dict(kind="Scan completed",date="2026-11-06T12:00:00+00:00",details="Disposable Overview test event")]
        blocked, entered=threading.Event(),threading.Event()
        mode=["cancel"]
        def scan(settings,canceled,progress):
            entered.set()
            progress(20,"Disposable Overview scan")
            while not blocked.is_set() and not canceled():
                time.sleep(.005)
            if canceled():
                raise ScanCanceled("Scan canceled")
            if mode[0]=="failure":
                raise OSError("Synthetic scan failure")
            return inventory
        saved=[]
        with patch("gg_desktop.app.load_settings",side_effect=lambda:dict(preferences)), \
             patch("gg_desktop.app.scan_inventory",side_effect=scan) as scanner, \
             patch("gg_desktop.reference_overview.get_activity",return_value=activity), \
             patch("gg_desktop.reference_overview.get_records",return_value=[]), \
             patch("gg_desktop.overview_storage_ui.save_settings",side_effect=lambda s:saved.append(deepcopy(s))), \
             patch("gg_desktop.reference_overview.save_settings",side_effect=lambda s:saved.append(deepcopy(s))), \
             patch("gg_desktop.ready_room_services.config_dir",return_value=root/"Preferences"), \
             patch("gg_desktop.game_artwork.artwork_dir",return_value=root/"Artwork"), \
             patch("gg_desktop.game_artwork._request",side_effect=AssertionError("Automatic network")) as network, \
             patch.object(CrimsonWindow,"info"), patch.object(CrimsonWindow,"error") as error, \
             patch.object(CrimsonWindow,"_open_folder") as opened, \
             patch.object(CrimsonWindow,"_approve_recycle") as recycle, \
             patch("gg_desktop.app.QMessageBox.warning"):
            window=CrimsonWindow()
            window.resize(1450,900)
            window.show()
            settle()
            def overview():
                window.navigate("Overview")
                QTest.qWait(30)
                wait_for(lambda:not window.workers)
                return window.page.overview
            original=window.inventory
            window.overview_hero.scan.click()
            wait_for(entered.is_set)
            assert not window.overview_hero.scan.isEnabled()
            assert not window.overview_quick_scan.isEnabled()
            window.overview_quick_scan.click()
            assert scanner.call_count==1,"Duplicate scan"
            window.overview_cancel.click()
            assert not window.overview_cancel.isEnabled()
            wait_for(lambda:not window.scanning and not window.workers)
            assert window.inventory is original,"Canceled scan replaced inventory"
            mode[0]="success"
            blocked.set()
            window.activateWindow()
            window.page.setFocus()
            QTest.keyClick(window,Qt.Key_F5)
            wait_for(lambda:window.inventory is inventory and not window.workers)
            wait_for(lambda:window.page.overview.snapshot is not None)
            control=window.page.overview
            expected=measure_storage(inventory)
            assert control.snapshot.totals==expected.totals
            assert expected.shared_files==1
            assert window.overview_metrics["Games"].value_label.text()=="8"
            assert window.overview_metrics["Mods"].value_label.text().rstrip("+")=="4", (window.overview_metrics["Mods"].value_label.text(), expected.catalog.warnings)
            assert window.overview_metrics["Mods"].caption_label.text()=="Mods"
            assert [n for n,_,_ in window.overview_ring.segments]==["Games","Mods","Other Storage","Captures","Old Files"]
            assert sum(v for _,v,_ in window.overview_ring.segments)==expected.total
            assert window.inventory==before,"Overview mutated accepted evidence"

            def breakdown(dialog):
                table=dialog.findChild(QTableWidget)
                assert table.rowCount()==len(expected.roots)
                assert sum(int(table.item(i,4).text().replace(",","")) for i in range(table.rowCount()) if table.item(i,4).text()!="Unknown")==expected.total
                table.selectRow(0)
                click(dialog,"Open folder")
                opened.assert_called()
                click(dialog,"Close")
            drive_dialog(lambda:QTest.mouseClick(window.overview_ring,Qt.LeftButton),breakdown)
            for category,(caption,value,_) in window.overview_legend.items():
                def check_category(dialog,category=category):
                    choice=dialog.findChild(QComboBox)
                    assert choice.currentText()==category
                    table=dialog.findChild(QTableWidget)
                    assert all(table.item(i,1).text()==category for i in range(table.rowCount()))
                    click(dialog,"Close")
                drive_dialog(lambda c=caption:QTest.keyClick(c,Qt.Key_Return),check_category)
            old_total=control.snapshot.total
            (Path(games[0].install_path)/"added.bin").write_bytes(b"N"*37)
            def refresh(dialog):
                click(dialog,"Refresh measurement")
                wait_for(lambda:not control.storage_busy)
                assert control.snapshot.total==old_total+37
                click(dialog,"Close")
            drive_dialog(control.storage_details,refresh)
            previous=control.snapshot
            with patch("gg_desktop.overview_storage_ui.measure_storage",side_effect=OSError("Synthetic unavailable")):
                control.refresh_storage(force=True)
                wait_for(lambda:not control.storage_busy)
                assert control.snapshot is previous
                assert "unavailable" in control.message
                assert not window.scanning
            gate=threading.Event()
            def slow(_inventory,*,canceled,progress):
                gate.set()
                while not canceled():
                    time.sleep(.002)
                raise InterruptedError()
            with patch("gg_desktop.overview_storage_ui.measure_storage",side_effect=slow):
                def cancel_measurement(dialog):
                    click(dialog,"Refresh measurement")
                    wait_for(gate.is_set)
                    click(dialog,"Cancel measurement")
                    wait_for(lambda:not control.storage_busy)
                    assert control.snapshot is previous
                    assert "canceled" in control.message
                    click(dialog,"Close")
                drive_dialog(control.storage_details,cancel_measurement)
            control.refresh_storage(force=True)
            wait_for(lambda:not control.storage_busy)

            item=window.overview_library.item(0)
            rect=window.overview_library.visualItemRect(item)
            QTest.mouseClick(window.overview_library.viewport(),Qt.LeftButton,pos=QPoint(rect.right()-15,rect.top()+15))
            assert item.data(CARD_ROLE)["favorite"]
            assert inventory.games[0].key in saved[-1]["desktop_favorites"]
            with patch("gg_desktop.overview_storage_ui.save_settings",side_effect=OSError("Synthetic save failure")):
                control.favorite(0)
            assert item.data(CARD_ROLE)["favorite"],"Failed save changed favorite"
            assert error.call_count==1
            error.reset_mock()
            control.favorite(0)
            assert not item.data(CARD_ROLE)["favorite"]
            window.global_search.setText("Baldur")
            assert sum(not window.overview_library.item(i).isHidden() for i in range(8))==1
            target_game=next(g for g in inventory.games if "Baldur" in g.name)
            target_index=inventory.games.index(target_game)
            assert not window.overview_library.item(target_index).isHidden()
            def search_results(dialog):
                entries=dialog.findChild(QListWidget)
                assert entries.count()==1
                entries.setCurrentRow(0)
                click(dialog,"Inspect selected")
            drive_dialog(lambda:QTest.keyClick(window.global_search,Qt.Key_Return),search_results)
            assert window.current_route=="Games"
            assert window._current_game().key==target_game.key
            control=overview()
            def event_details(dialog):
                assert "Activity Details" in dialog.windowTitle()
                assert any("Disposable Overview test event" in l.text() for l in dialog.findChildren(QLabel))
                click(dialog,"Close")
            drive_dialog(window.overview_activity[0][0].click,event_details)
            for title,route in (("Find Mods   ›","Mods"),("Review Old Files   ›","Old Files"),
                                ("Manage Captures   ›","Captures"),("Open Graveyard   ›","Graveyard"),
                                ("Review Cleanup","Graveyard"),("View All Games →","Games"),("View History →","Undo Center")):
                click(window.page,title)
                assert window.current_route==route,title
                control=overview()
            for title in list(window.overview_metrics):
                window.overview_metrics[title].click()
                settle()
                assert window.current_route==title
                control=overview()
            def locations(dialog):
                table=dialog.findChild(QTableWidget)
                assert table.rowCount()>=5,"Empty coverage report"
                assert any(table.item(i,0).text()=="Steam" for i in range(table.rowCount()))
                dialog.reject()
            for open_dialog in (window.overview_hero.locations.click,lambda:click(window.page,"Scan Results & Locations")):
                drive_dialog(open_dialog,locations)
            scans=scanner.call_count
            drive_dialog(window.open_scan_locations,lambda d:d.findChild(QDialogButtonBox).button(QDialogButtonBox.Save).click())
            QTest.qWait(30)
            wait_for(lambda:not window.workers)
            assert scanner.call_count==scans+1 and saved
            control=window.page.overview
            pending={"steam_extra_roots":[]}
            window._add_scan_location("steam_extra_roots",str(steam_root/"steamapps"),pending,lambda:None)
            assert pending["steam_extra_roots"]==[str(steam_root)]
            window._add_scan_location("steam_extra_roots",str(old.parent),pending,lambda:None)
            assert error.call_count==1
            error.reset_mock()
            # The shelf must reach installations past 500, including equal titles.
            many=replace(inventory,games=inventory.games+[replace(inventory.games[0],key="extra"+str(i),name="Same title",install_path=str(root/"Missing"/str(i))) for i in range(505)])
            window.inventory=many
            control=overview()
            assert window.overview_library.count()==513
            assert window.overview_next.isEnabled() and not window.overview_previous.isEnabled()
            window.overview_next.click()
            settle()
            assert window.overview_previous.isEnabled()
            window.overview_library.scrollToItem(window.overview_library.item(512))
            settle()
            window.overview_next.click()
            settle()
            assert not window.overview_next.isEnabled()
            window._overview_inspect_game(window.overview_library.item(512))
            settle()
            assert window._current_game().key=="extra504"
            window.inventory=inventory
            control=overview()
            mode[0]="failure"
            window.overview_quick_scan.click()
            wait_for(lambda:not window.workers)
            assert window.inventory is inventory and not window.scanning
            assert window.overview_hero.scan.isEnabled()
            mode[0]="success"
            window.status.setText("DISPOSABLE QA FIXTURE · Actual measured file bytes · No personal data")
            control=overview()
            for width,height in ((1450,900),(1280,720),(1536,864),(960,650)):
                window.resize(width,height)
                QTest.qWait(80)
                window.page.verticalScrollBar().setValue(0)
                settle()
                for metric in window.overview_metrics.values():
                    value=metric.value_label
                    assert QFontMetrics(value.font()).horizontalAdvance(value.text()) <= value.width()+1, "Clipped Overview value"
                assert window.grab().save(str(args.output/f"overview-functional-{width}.png"))
            summary=dict(totals=control.snapshot.totals,total=control.snapshot.total,
                         files=control.snapshot.files,hardlinks=control.snapshot.shared_files,
                         games=control.snapshot.game_count,mods=control.snapshot.mod_count)
            (args.output/"overview-measurement.json").write_text(json.dumps(summary,indent=2))
            network.assert_not_called()
            recycle.assert_not_called()
            assert inventory==before,"Overview changed scan or cleanup findings"
            assert not error.called
            wait_for(lambda:not window.workers)
            window.close()
            settle()
    print("PASS: Overview measured games/mods across roots; unique bytes/hardlinks, unknown coverage, refresh/cancel/failure, all metrics/quick actions, scan/F5/cancel/locations, favorites/search/activity, 513-game shelf, four viewports. Other tabs unchanged; no automatic network or cleanup.")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
