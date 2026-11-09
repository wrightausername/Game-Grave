"""Native Qt check of Exhume, Black Box, Autopsy (More Tools) and the Ready Room Soulbind and Squad sub-tabs.

Windows' registry, crash log, process list and PresentMon are fakes. Only throw-away temp folders are touched."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch
import zipfile

MODS_YML = """- manifestVersion: 1
  name: BepInEx-BepInExPack
  versionNumber:
    major: 5
    minor: 4
    patch: 2100
  enabled: true
- manifestVersion: 1
  name: notnotnotswipez-MoreCompany
  versionNumber:
    major: 1
    minor: 9
    patch: 1
  enabled: true
"""

EVENT = """<Event xmlns='http://schemas.microsoft.com/win/2004/08/events/event'><System><Provider Name='Application Error'/>
<EventID>1000</EventID><TimeCreated SystemTime='{when}'/></System><EventData><Data>Game.exe</Data><Data>1.0</Data>
<Data>0</Data><Data>CoolMod.dll</Data><Data>2.0</Data><Data>0</Data><Data>c0000005</Data><Data>0x1</Data><Data>0x1</Data>
<Data>0x1</Data><Data>{app}</Data><Data>{module}</Data><Data>id</Data></EventData></Event>"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("_ci_temp"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    root_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root_dir))
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from gg_desktop import exhume, tools_windows as tw, winpc
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.models import GameRecord

    app = QApplication.instance() or QApplication([])

    def wait_for(test, seconds=10):
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents()
            if test():
                return
            QTest.qWait(20)
        raise AssertionError("timed out")

    def snap(widget, name):
        widget.show()
        QTest.qWait(100)
        app.processEvents()
        assert widget.grab().save(str(args.output / name))

    with tempfile.TemporaryDirectory(prefix="GG-new-") as temp:
        root = Path(temp)
        game_dir = root / "Games" / "Cool Game"
        (game_dir / "Mods").mkdir(parents=True)
        (game_dir / "Mods" / "CoolMod.dll").write_bytes(b"dll")
        (game_dir / "Game.exe").write_bytes(b"MZ")
        crash_when = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(time.time() + 120))
        local, appdata, home = root / "Local", root / "Roaming", root / "Home"
        ue = local / "CoolUnreal" / "Saved" / "Config" / "Windows"
        ue.mkdir(parents=True)
        (ue / "GameUserSettings.ini").write_text("[x]\n")
        engine = ue / "Engine.ini"
        engine.write_text("[Core.System]\nPaths=a\n")
        profile = appdata / "r2modmanPlus-local" / "LethalCompany" / "profiles" / "Friday"
        (profile / "BepInEx" / "config").mkdir(parents=True)
        (profile / "mods.yml").write_text(MODS_YML)
        (profile / "BepInEx" / "config" / "MoreCompany.cfg").write_text("players = 8\n")
        (home / "Downloads").mkdir(parents=True)
        config = root / "Config"

        path = (exhume.DISPLAY_CLASS + "\\0000").lower()
        registry = SimpleNamespace(read=lambda hive, p, name: {
            "DriverDesc": ("NVIDIA GeForce RTX 4070", 1), "DriverVersion": ("32.0.15.6094", 1),
            "DriverDate": ("10-1-2024", 1), "ProviderName": ("NVIDIA", 1)}.get(name) if p.lower() == path else None)
        captured = []

        class FakeRunner:
            def run(self, argv, **kw):
                captured.append(list(argv))
                if argv[0] == "wevtutil":
                    return winpc.RunResult(0, EVENT.format(when=crash_when, app=str(game_dir / "Game.exe"),
                                                           module=str(game_dir / "Mods" / "CoolMod.dll")))
                if argv[0] == "tasklist":
                    return winpc.RunResult(0, '"Game.exe","4242","Console","1","1,200,000 K"\n')
                if "--output_file" in argv:
                    out = Path(argv[argv.index("--output_file") + 1])
                    ms = "10.0" if "before" in out.name else "8.0"
                    out.write_text("Application,ProcessID,MsBetweenPresents\n" + f"Game.exe,4242,{ms}\n" * 300)
                    return winpc.RunResult(0, "")
                return winpc.RunResult(0, "")

        logged, asked, shown, opened = [], [], [], []
        stack = ExitStack()
        stack.enter_context(patch.dict(os.environ, {"LOCALAPPDATA": str(local), "APPDATA": str(appdata),
                                                    "USERPROFILE": str(home), "HOME": str(home)}))
        for target, options in (
            ("core.config_dir", dict(return_value=config)),
            ("gg_desktop.tools_extra.config_dir", dict(return_value=config)),
            ("gg_desktop.ready_room_tabs.config_dir", dict(return_value=config)),
            ("gg_desktop.tools_page.get_activity", dict(return_value=[])),
            ("gg_desktop.recovery_screens.get_records", dict(return_value=[])),
            ("gg_desktop.recovery_screens.get_activity", dict(return_value=[])),
            ("gg_desktop.undo_page.get_records", dict(return_value=[])),
            ("gg_desktop.undo_page.get_activity", dict(return_value=[])),
            ("gg_desktop.assistant_page.get_records", dict(return_value=[])),
            ("gg_desktop.assistant_page.get_activity", dict(return_value=[])),
            ("gg_desktop.settings_page.get_records", dict(return_value=[])),
            ("gg_desktop.ready_room_services.config_dir", dict(return_value=root / "Preferences")),
            ("gg_desktop.ready_room_services.fetch_one", dict(side_effect=OSError("offline QA"))),
            ("gg_desktop.winpc.default_registry", dict(return_value=registry)),
            ("gg_desktop.winpc.Runner", dict(return_value=FakeRunner())),
            ("gg_desktop.winpc.activity", dict(side_effect=lambda kind, details, **kw: logged.append((kind, details)))),
            ("gg_desktop.tools_extra.open_device_manager", dict(side_effect=lambda: opened.append("devmgmt"))),
            ("gg_desktop.tools_extra._open_url", dict(side_effect=opened.append)),
            ("gg_desktop.autopsy.find_presentmon", dict(return_value="C:\\Tools\\PresentMon-2.3.1-x64.exe")),
        ):
            stack.enter_context(patch(target, **options))
        errors = stack.enter_context(patch.object(CrimsonWindow, "error"))
        stack.enter_context(patch.object(CrimsonWindow, "info"))
        stack.enter_context(patch.object(CrimsonWindow, "confirm", side_effect=lambda t, m, **kw: asked.append((t, m)) or True))
        stack.enter_context(patch.object(tw.WinDialog, "exec", lambda self: shown.append(self) or 0))
        with stack:
            window = CrimsonWindow()
            window.resize(1280, 820)
            window.show()
            window.inventory.games = [GameRecord(key="cool", name="Cool Game", launcher="Steam", app_id=None,
                                                 install_path=str(game_dir), install_evidence="manifest", size_bytes=1,
                                                 size_source="QA", last_played_at=None, last_played_source="",
                                                 status="Installed", capabilities=())]
            window.navigate("More Tools")
            app.processEvents()
            for gone in ("temp_files", "storage_analyzer", "advanced_cleanup"):
                assert gone not in window.tools_tiles, gone

            def open_tool(key):
                before = len(shown)
                window.tools_tiles[key].click()
                wait_for(lambda: len(shown) > before)
                return shown[-1]

            # Exhume: reads the driver, records history, only the owner marks known good.
            dialog = open_tool("exhume")
            wait_for(lambda: dialog.listing.count() == 1)
            assert "560.94" in dialog.listing.item(0).text()
            assert "nothing to go back to" in dialog.detail.text()
            dialog.good_button.click()
            assert "You marked this driver as known good" in dialog.detail.text()
            history = exhume.load_history(config / exhume.HISTORY_NAME)
            assert len(history) == 1 and history[0].known_good
            dialog.vendor_button.click()
            dialog.devices_button.click()
            assert opened[-2] == "https://www.nvidia.com/en-us/drivers/" and opened[-1] == "devmgmt"
            assert logged[-1][0] == "Exhume"
            snap(dialog, "tools-exhume.png")
            dialog.hide()

            # Black Box: the crash is matched to the scanned game by its folder; the report hides the user.
            dialog = open_tool("black_box")
            wait_for(lambda: dialog.listing.count() == 1)
            assert captured[-1][:3] == ["wevtutil", "qe", "Application"]
            assert "Cool Game" in dialog.listing.item(0).text() and "CoolMod.dll" in dialog.listing.item(0).text()
            assert "inside the game's folder" in dialog.detail.text()
            dialog.changes_button.click()
            wait_for(lambda: "CoolMod.dll" in dialog.detail.text() and "Changed in the" in dialog.detail.text())
            report = root / "report.txt"
            with patch("gg_desktop.tools_extra.QFileDialog.getSaveFileName", return_value=(str(report), "")):
                dialog.report_button.click()
            text = report.read_text(encoding="utf-8")
            assert "Black Box report" in text and "lead, not proof" in text
            assert logged[-1][0] == "Black Box"
            # Saving without pressing "What changed" first looks for changes off the window's thread, then saves.
            dialog.all_box.setChecked(True)
            app.processEvents()
            assert dialog.findings is None
            report2 = root / "report2.txt"
            with patch("gg_desktop.tools_extra.QFileDialog.getSaveFileName", return_value=(str(report2), "")):
                dialog.report_button.click()
                wait_for(report2.exists)
            assert "CoolMod.dll" in report2.read_text(encoding="utf-8")
            assert (game_dir / "Mods" / "CoolMod.dll").read_bytes() == b"dll"
            snap(dialog, "tools-black-box.png")
            dialog.hide()

            # Autopsy: two captures with PresentMon (fake) and a plain verdict.
            dialog = open_tool("autopsy")
            assert dialog.process_box.currentData() == "Game.exe"
            dialog.before_button.click()
            wait_for(lambda: "Before" in dialog.captures)
            dialog.after_button.click()
            wait_for(lambda: "After" in dialog.captures)
            assert "Verdict: better" in dialog.results.text(), dialog.results.text()
            pm = [c for c in captured if "--output_file" in c]
            assert pm and pm[-1][0].endswith("PresentMon-2.3.1-x64.exe") and "--process_name" in pm[-1]
            assert asked[-1][0] == "Start an Autopsy capture"
            assert not list((config / "autopsy" / "raw").glob("*.csv"))
            snap(dialog, "tools-autopsy.png")
            dialog.hide()

            # Ready Room: News is the approved page; Soulbind and Squad are new sub-tabs.
            window.navigate("Ready Room")
            wait_for(lambda: hasattr(window.page, "ready_tabs"))
            page = window.page
            assert page.ready_tabs["news"].isChecked() and page.patches.isVisible()
            assert not page.soulbind_view.isVisible() and not page.squad_view.isVisible()

            page.ready_tabs["soulbind"].click()
            app.processEvents()
            view = page.soulbind_view
            assert view.isVisible() and not page.patches.isVisible()
            assert view.list.count() == 1 and "CoolUnreal" in view.list.item(0).text()
            view.checks["motion_blur"].setChecked(True)
            view.checks["lens_flare"].setChecked(True)
            view.apply_button.click()
            assert asked[-1][0] == "Soulbind" and "r.MotionBlurQuality=0" in asked[-1][1]
            assert "r.MotionBlurQuality=0" in engine.read_text() and "Paths=a" in engine.read_text()
            assert "Soulbound" in view.list.item(0).text()
            snap(window, "ready-room-soulbind.png")
            view.restore_button.click()
            assert engine.read_text() == "[Core.System]\nPaths=a\n"
            assert logged[-1][0] == "Soulbind"
            shared = root / "mine.soulbind.json"
            with patch("gg_desktop.ready_room_tabs.QFileDialog.getSaveFileName", return_value=(str(shared), "")):
                view.export_button.click()
            view.checks["lens_flare"].setChecked(False)
            with patch("gg_desktop.ready_room_tabs.QFileDialog.getOpenFileName", return_value=(str(shared), "")):
                view.import_button.click()
            assert view.checks["lens_flare"].isChecked() and "Imported" in view.mine_note.text()

            page.ready_tabs["squad"].click()
            app.processEvents()
            squad = page.squad_view
            assert squad.isVisible() and not view.isVisible()
            assert squad.share_box.count() == 1 and "Friday" in squad.share_box.itemText(0)
            squad.code_button.click()
            code = squad.code.toPlainText()
            assert code.startswith("GGSQ1.")
            squad_file = root / "Squad - Friday.r2z"
            with patch("gg_desktop.ready_room_tabs.QFileDialog.getSaveFileName", return_value=(str(squad_file), "")):
                squad.file_button.click()
            assert "1 config files" in squad.share_note.text(), squad.share_note.text()
            with patch("gg_desktop.ready_room_tabs.QFileDialog.getOpenFileName", return_value=(str(squad_file), "")):
                squad.open_button.click()
            assert "You match" in squad.result_line.text(), squad.result_line.text()
            squad.paste.setPlainText(code)
            squad.compare_button.click()
            assert "You match" in squad.result_line.text(), squad.result_line.text()
            squad.match_button.click()
            files = list((home / "Downloads").glob("*.r2z"))
            assert len(files) == 1, files
            with zipfile.ZipFile(files[0]) as archive:
                assert "notnotnotswipez-MoreCompany" in archive.read("export.r2x").decode()
            assert "Import / Update" in squad.steps.text()
            # Ready Room rebuilds itself after news and checks; the sub-tab and what was typed must survive.
            squad.paste.setPlainText("hello " + code)
            window.ready_reload()
            app.processEvents()
            page = window.page
            assert page.ready_tab == "squad" and page.ready_tabs["squad"].isChecked() and page.squad_view is squad
            assert squad.isVisible() and not page.patches.isVisible() and squad.paste.toPlainText() == "hello " + code
            assert (profile / "mods.yml").read_text() == MODS_YML
            snap(window, "ready-room-squad.png")

            page.ready_tabs["news"].click()
            app.processEvents()
            assert page.patches.isVisible() and not squad.isVisible()
            assert errors.call_count == 0, errors.call_args_list
            window.close()
    print("PASS: Exhume, Black Box and Autopsy open from their tiles and work with fake Windows data; Ready Room keeps "
          "News and adds Soulbind (apply and restore Engine.ini) and Squad (code, compare, match file).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
