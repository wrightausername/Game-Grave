"""Native Qt check of My Mods: a disposable Mod Organizer 2 setup and Steam Workshop library, driven like a person would.

Fix a problem with one button, Undo, a switch, a drag reorder, refusal while MO2 runs, the Workshop view with real names
from a stand-in Steam answer, and the Advanced switch. Only the disposable profile's modlist.txt may change.
"""
from __future__ import annotations

import argparse
import faulthandler
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import time
from unittest.mock import patch


def plugin(path: Path, masters=()):
    body = b"".join(b"MAST" + struct.pack("<H", len(m) + 1) + m.encode() + b"\0" for m in masters)
    path.write_bytes(b"TES4" + struct.pack("<I", len(body)) + b"\0" * 16 + body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("_ci_temp"))
    args = parser.parse_args()
    faulthandler.dump_traceback_later(300, exit=True)
    args.output.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QCoreApplication, QEvent, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton
    from core import ModFolder, SteamGame, default_settings
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.backend import Inventory
    from gg_desktop.models import merge_games
    from gg_desktop import mymods_core as mc
    from gg_desktop import workshop_core as ws
    from gg_desktop.settings_page import Switch

    app = QApplication.instance() or QApplication([])

    def settle():
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()

    def wait_for(predicate, what):
        deadline = time.monotonic() + 25
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(15)
        if not predicate():
            raise AssertionError(f"{what} | errors={getattr(main, 'errors', None) and main.errors.call_args_list} "
                                 f"| status={getattr(main, 'window', None) and main.window.status.text()} "
                                 f"| banner={getattr(main, 'view', None) and main.view.banner_text.text()}")
        settle()

    def texts(widget):
        return [w.text() for w in widget.findChildren(QLabel)] + [w.text() for w in widget.findChildren(QPushButton)]

    def stage(text):
        print("stage:", text, flush=True)

    with tempfile.TemporaryDirectory(prefix="GG-mymods-") as temp:
        root = Path(temp)
        manager = root / "MO2"
        mods_dir, profile = manager / "mods", manager / "profiles" / "Main"
        profile.mkdir(parents=True)
        game = root / "Games" / "Skyrim"
        (game / "Data").mkdir(parents=True)
        (game / "Data" / "Skyrim.esm").write_bytes(b"x")
        ini = manager / "ModOrganizer.ini"
        ini.write_text(f"[General]\ngameName=Skyrim Special Edition\ngamePath={game}\nselected_profile=@ByteArray(Main)\n"
                       f"[Settings]\nbase_directory={manager}\n", encoding="utf-8")
        for name in ("SkyUI", "Immersive Armors", "Unofficial Skyrim Patch", "Static Mesh Improvement", "Iron Retexture"):
            (mods_dir / name).mkdir(parents=True)
        plugin(mods_dir / "SkyUI" / "SkyUI_SE.esp", ["Skyrim.esm"])
        plugin(mods_dir / "Immersive Armors" / "Hothtrooper44_ArmorCompilation.esp", ["Skyrim.esm", "SkyUI_SE.esp"])
        (mods_dir / "Unofficial Skyrim Patch" / "meta.ini").write_text(
            "[General]\nmodid=266\nversion=4.3.1\nnewestVersion=4.3.2\ngameName=SkyrimSE\n", encoding="utf-8")
        for name in ("Immersive Armors", "Iron Retexture"):
            (mods_dir / name / "textures").mkdir()
            (mods_dir / name / "textures" / "iron.dds").write_bytes(name.encode())
        modlist = profile / "modlist.txt"
        modlist.write_text("# header\n+Iron Retexture\n+Unofficial Skyrim Patch\n+Immersive Armors\n-Static Mesh Improvement\n"
                           "-SkyUI\n", encoding="utf-8")
        (profile / "plugins.txt").write_text("*Hothtrooper44_ArmorCompilation.esp\n", encoding="utf-8")
        original = modlist.read_text(encoding="utf-8")

        steam_root = root / "Steam"
        content = steam_root / "steamapps" / "workshop" / "content" / "255710"
        for item in ("2016612051", "1234567"):
            (content / item).mkdir(parents=True)
        (steam_root / "steamapps" / "workshop" / "appworkshop_255710.acf").write_text(
            '"AppWorkshop"\n{\n "WorkshopItemsInstalled"\n {\n  "2016612051"\n  {\n   "size" "48000000"\n   "timeupdated" "100"\n'
            '  }\n  "1234567"\n  {\n   "size" "900000"\n   "timeupdated" "500"\n  }\n }\n}\n', encoding="utf-8")
        steam_answer = {"2016612051": {"title": "Better Roads and Traffic", "description": "Realistic roads.",
                                       "preview": "", "updated": 200, "size": 48000000, "tags": ["Roads", "Traffic"]},
                        "1234567": {"title": "Metro Station Pack", "preview": "", "updated": 500, "size": 900000, "tags": []}}
        asked = []

        steam = [SteamGame("489830", "Skyrim Special Edition", str(root), str(game), 1000, None, "Unknown"),
                 SteamGame("255710", "Cities: Skylines", str(steam_root), str(root / "Games" / "Cities"), 1000, None, "Unknown")]
        mods = [ModFolder("mods", str(mods_dir), str(manager), "MO2: installed mods", ("MO2 INI: " + str(ini),), 1000, 1,
                          False, "Mod Organizer 2")]
        inventory = Inventory(steam=steam, games=merge_games(steam, []), mods=mods, scanned_at="Disposable mods QA")
        settings = default_settings()
        settings["steam_extra_roots"] = [str(steam_root)]
        running = {"mo2": False}

        with patch("gg_desktop.app.load_settings", side_effect=lambda: dict(settings)), \
             patch("gg_desktop.ready_room_services.config_dir", return_value=root / "Preferences"), \
             patch("gg_desktop.mods_page.save_settings"), \
             patch("core.save_settings"), \
             patch("gg_desktop.mymods_core.snapshot_root", return_value=root / "Snapshots"), \
             patch("gg_desktop.workshop_core.cache_path", return_value=root / "workshop_names.json"), \
             patch("gg_desktop.workshop_core.fetch_details",
                   side_effect=lambda ids: asked.append(list(ids)) or {i: steam_answer[i] for i in ids}), \
             patch("gg_desktop.bisect_apply.mo2_running", side_effect=lambda: running["mo2"]), \
             patch("core._steam_roots", side_effect=lambda extra=None: [Path(p) for p in (extra or [])]), \
             patch.object(CrimsonWindow, "info"), \
             patch.object(CrimsonWindow, "error") as errors, \
             patch.object(CrimsonWindow, "confirm", return_value=True), \
             patch.object(CrimsonWindow, "start_scan"):
            window = CrimsonWindow()
            main.errors, main.window = errors, window
            window.resize(1280, 790)
            window.show()
            window.inventory = inventory
            window.settings = dict(settings)
            window.navigate("Mods")
            settle()
            view = window.mymods_view
            main.view = view

            stage("opens on My Mods, not the number strip")
            assert view.isVisible() and not any(w.isVisible() for w in window.mymods_advanced), "My Mods is the default"
            assert view.game_pick.count() == 2, [view.game_pick.itemText(i) for i in range(view.game_pick.count())]
            assert "Mod Organizer 2" in view.game_pick.currentText()
            wait_for(lambda: view.report is not None and not window.workers, "the profile was read")
            assert view.title.text() == "Skyrim Special Edition"
            assert "5 mods, 3 turned on" in view.subtitle.text(), view.subtitle.text()
            assert view.banner_text.text() == "1 thing needs you. 1 update ready too.", view.banner_text.text()
            names = [view.list.item(i).data(Qt.UserRole) for i in range(view.list.count())]
            assert names == ["SkyUI", "Static Mesh Improvement", "Immersive Armors", "Unofficial Skyrim Patch",
                             "Iron Retexture"], names
            shown = texts(view)
            assert "Update: 4.3.1 → 4.3.2" in shown and "Needs SkyUI on" in shown, shown
            assert any("Iron Retexture wins over Immersive Armors" in t for t in shown), shown
            assert not any(t.isdigit() and len(t) > 6 for t in shown), "no raw numbers as names"
            assert window.grab().save(str(args.output / "mods-mymods-1280.png"))

            stage("one-button fix, then undo")
            view.fix_button.click()
            settle()
            assert view.problem_box.isVisible()
            fix = next(b for b in view.problem_box.findChildren(QPushButton) if b.text() == "Turn on SkyUI")
            assert window.grab().save(str(args.output / "mods-mymods-fix-1280.png"))
            fix.click()
            wait_for(lambda: "+SkyUI" in modlist.read_text(encoding="utf-8") and not window.workers and view.report
                     and not view.report.problems, "the fix turned SkyUI on")
            assert view.banner_text.text().startswith("Your mods look healthy"), view.banner_text.text()
            assert not view.problem_box.isVisible() and view.filter_kind == "", "fixed problems leave the list"
            assert len(mc.snapshots(profile, root / "Snapshots")) == 1
            view.undo_button.click()
            wait_for(lambda: not window.workers and view.report is not None, "undo reloaded")
            assert modlist.read_text(encoding="utf-8") == original, "Undo put the exact list back"

            stage("a switch turns one mod on")
            assert view.filter_kind == "problem" and view.problem_box.isVisible(), "after Undo the problem is back on show"
            view.clear_filter.click()
            settle()
            switches = {s.accessibleName(): s for s in view.findChildren(Switch)}
            switches["Static Mesh Improvement on"].click()
            wait_for(lambda: "+Static Mesh Improvement" in modlist.read_text(encoding="utf-8") and not window.workers,
                     "the switch changed the profile")

            stage("drag reorder")
            wait_for(lambda: view.list.count() == 5 and not view.busy, "list refreshed")
            item = view.list.takeItem(0)
            view.list.addItem(item)
            view.dropped()
            wait_for(lambda: not window.workers and not view.busy, "the reorder finished")
            assert modlist.read_text(encoding="utf-8").splitlines()[1] == "-SkyUI", modlist.read_text(encoding="utf-8")

            stage("refused while Mod Organizer 2 is open")
            before = modlist.read_text(encoding="utf-8")
            running["mo2"] = True
            wait_for(lambda: view.list.count() == 5, "list refreshed")
            switches = {s.accessibleName(): s for s in view.findChildren(Switch)}
            switches["Iron Retexture on"].click()
            wait_for(lambda: errors.called and not window.workers, "the refusal was shown")
            assert "Close Mod Organizer 2 first" in errors.call_args[0][1], errors.call_args
            assert modlist.read_text(encoding="utf-8") == before
            assert switches["Iron Retexture on"].isChecked(), "the switch went back"
            running["mo2"] = False

            stage("Steam Workshop items by name")
            view.game_pick.setCurrentIndex(1)
            wait_for(lambda: any("Better Roads and Traffic" in t for t in texts(view)) and not window.workers,
                     "Workshop names from Steam")
            shown = texts(view)
            assert view.title.text() == "Cities: Skylines", view.title.text()
            assert "Newer version on Steam" in shown and "Metro Station Pack" in shown, shown
            assert view.banner_text.text().startswith("1 item has a newer version on Steam"), view.banner_text.text()
            assert "Open in Steam" in shown
            assert asked == [["1234567", "2016612051"]], asked
            assert json.loads((root / "workshop_names.json").read_text(encoding="utf-8"))["1234567"]["title"]
            assert window.grab().save(str(args.output / "mods-mymods-workshop-1280.png"))
            view.updates.on_click()
            settle()
            assert view.list.count() == 1, "the Updates card shows only items with a newer version"

            stage("Advanced and back")
            view.advanced_button.click()
            settle()
            assert not view.isVisible() and window.mymods_back.isVisible() and window.settings["mods_view"] == "advanced"
            next(b for b in window.mymods_back.findChildren(QPushButton) if b.text() == "Back to My Mods").click()
            settle()
            assert view.isVisible() and window.settings["mods_view"] == "simple"

            assert all((mods_dir / n).is_dir() for n in ("SkyUI", "Immersive Armors")), "mod folders untouched"
            window.close()
            settle()
    print("PASS: My Mods shows real names and plain status, fixes a problem with one button, switches, reorders and "
          "undoes through snapshots, refuses while MO2 is open, names Steam Workshop items, and switches to Advanced.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
