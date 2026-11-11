"""Native Qt check of Squad Sync with fixture mod sources: read, squad code, comparison, Steam links, snapshot, refusals."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch

ACF = ('"AppWorkshop"\n{\n\t"appid"\t"489830"\n\t"WorkshopItemsInstalled"\n\t{\n'
       '\t\t"1111111"\n\t\t{\n\t\t\t"timeupdated"\t"1700000000"\n\t\t}\n'
       '\t\t"2222222"\n\t\t{\n\t\t\t"timeupdated"\t"1700000500"\n\t\t}\n\t}\n}\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("_ci_temp"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication, QPushButton
    from core import SteamGame, default_settings
    from gg_desktop import squad_core as sq
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.models import merge_games
    from gg_desktop.ready_room_services import parse_news

    app = QApplication.instance() or QApplication([])

    def settle(ms=0):
        end = datetime.now() + timedelta(milliseconds=ms)
        while True:
            app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            if datetime.now() >= end:
                break

    def wait_for(test, label, seconds=20):
        end = datetime.now() + timedelta(seconds=seconds)
        while not test():
            settle(20)
            assert datetime.now() < end, "Timed out waiting for " + label

    def live(window):
        return window.page.squad.squad

    def buttons(window, text):
        return [b for b in live(window).findChildren(QPushButton) if b.text() == text]

    with tempfile.TemporaryDirectory(prefix="GG-squad-") as temp:
        root = Path(temp)
        library = root / "Steam"
        (library / "steamapps" / "workshop").mkdir(parents=True)
        (library / "steamapps" / "workshop" / "appworkshop_489830.acf").write_text(ACF, encoding="utf-8")
        install = library / "steamapps" / "common" / "Skyrim"
        install.mkdir(parents=True)
        local = root / "Local"
        mo2 = local / "ModOrganizer" / "Skyrim SE"
        (mo2 / "profiles" / "Co-op").mkdir(parents=True)
        (mo2 / "ModOrganizer.ini").write_text("[General]\ngameName=Skyrim Special Edition\nselected_profile=@ByteArray(Co-op)\n", encoding="utf-8")
        (mo2 / "profiles" / "Co-op" / "modlist.txt").write_text("+SkyUI\n-Off\n+USSEP\n", encoding="utf-8")
        (mo2 / "mods" / "SkyUI").mkdir(parents=True)
        (mo2 / "mods" / "SkyUI" / "meta.ini").write_text("[General]\ngameName=skyrimspecialedition\nmodid=12604\n", encoding="utf-8")
        (local / "Skyrim Special Edition").mkdir()
        (local / "Skyrim Special Edition" / "plugins.txt").write_text("*SkyUI_SE.esp\n*Patch.esp\n", encoding="utf-8")
        (root / "Roaming" / "Vortex").mkdir(parents=True)
        game = SteamGame("489830", "Skyrim Special Edition", str(library), str(install), 100, None, "Unknown")
        env = {"LOCALAPPDATA": str(local), "APPDATA": str(root / "Roaming")}
        opened = []
        with patch.dict(os.environ, env), \
             patch("gg_desktop.app.load_settings", side_effect=default_settings), \
             patch("core.config_dir", return_value=root / "Prefs"), \
             patch("gg_desktop.ready_room_services.config_dir", return_value=root / "Prefs"), \
             patch("gg_desktop.ready_room_services.fetch_one",
                   side_effect=lambda sid, name: parse_news({"appnews": {"appid": int(sid), "newsitems": []}}, sid, name)), \
             patch("gg_desktop.squad_ui.QDesktopServices.openUrl", side_effect=lambda url: opened.append(url.toString())), \
             patch.object(CrimsonWindow, "info"), patch.object(CrimsonWindow, "error") as error:
            window = CrimsonWindow()
            window.resize(1280, 790)
            window.show()
            window.navigate("Ready Room")
            settle(300)
            assert window.page.squad is not None, "Squad Sync panel is missing from Ready Room"
            strip = window.page.squad
            assert not strip.strip_open and strip.maximumHeight() <= 50, "Squad Sync starts as one slim line"
            strip.strip_toggle.click()
            settle(80)
            assert strip.strip_open
            assert "Scan your PC" in live(window).summary.text() and not live(window).read_button.isEnabled()

            window.inventory.steam = [game]
            window.inventory.games = merge_games([game], [])
            window.inventory.scanned_at = "Disposable Squad QA"
            window.navigate("Ready Room")
            settle(300)
            body = live(window)
            assert body.games.count() == 1 and body.read_button.isEnabled()
            assert body.setup is not None and body.setup.read_any, "the setup is read as soon as a game is there"
            assert "mod items read for Skyrim Special Edition" in window.page.squad.detail_label.text()
            body.read_button.click()
            settle(100)
            body = live(window)
            assert body.setup.read_any and len(body.setup.items) == 6, [i.label for i in body.setup.items]
            assert body.summary.text().startswith("Found 6 mod items for Skyrim Special Edition"), body.summary.text()
            assert "Vortex" in body.summary.text()
            assert body.copy_button.isEnabled() and body.snapshot_button.isEnabled() and body.import_button.isEnabled()
            assert not body.compare_snapshot_button.isEnabled(), "No snapshot yet"
            body.copy_button.click()
            code = QApplication.clipboard().text()
            assert code.startswith("GGSQ1-") and str(root) not in code
            assert {i.label: i.nexus for i in sq.read_code(code).items}["SkyUI"] == "skyrimspecialedition/12604"
            # The host is told what to do with the code.
            assert "paste it to your friends" in body.share_note.text() and "Paste a friend's code" in body.share_note.text()
            saved = root / "my-code.txt"
            with patch("gg_desktop.squad_ui.QFileDialog.getSaveFileName", return_value=(str(saved), "")):
                body.save_code_button.click()
            assert sq.read_code_file(saved) == code and "Send that file" in body.share_note.text()
            # My own code on the clipboard is not "a friend's code": the paste box is asked instead.

            friend = sq.Setup("Skyrim Special Edition", [
                sq.Item("workshop", "1111111", "w", "1700000000"), sq.Item("workshop", "2222222", "w", "1700009999"),
                sq.Item("workshop", "3333333", "w", "1700000000"), sq.Item("mo2", "skyui", "SkyUI"),
                sq.Item("plugin", "skyui_se.esp", "SkyUI_SE.esp")], read_any=True)
            with patch("gg_desktop.squad_ui.QInputDialog.getMultiLineText", return_value=(sq.make_code(friend), True)):
                body.import_button.click()
            settle(100)
            body = live(window)
            result = body.comparison
            assert [i.key for i in result.missing] == ["3333333"] and len(result.different) == 1, result.summary
            assert "1 missing" in body.result_summary.text() and "updated at a different time" in body.result_summary.text()
            assert len(buttons(window, "Open in Steam")) == 2 and body.open_button.isVisibleTo(body)
            window.page.ensureWidgetVisible(window.page.squad)
            settle(80)
            assert window.grab().save(str(args.output / "ready-room-squad-1280.png"))

            buttons(window, "Open in Steam")[0].click()
            assert opened == ["steam://url/CommunityFilePage/3333333"], opened
            opened.clear()
            # One press gets what is missing: no confirmation for opening pages.
            body.open_button.click()
            settle(60)
            assert opened == ["steam://url/CommunityFilePage/3333333"], opened
            assert "Press Subscribe" in body.fetch_note.text(), body.fetch_note.text()
            opened.clear()
            body.console_button.click()
            assert QApplication.clipboard().text() == "workshop_download_item 489830 3333333", QApplication.clipboard().text()
            assert opened == ["steam://nav/console"], opened
            opened.clear()

            # A joiner presses one button: the code is read straight from the clipboard, even inside a chat message.
            QApplication.clipboard().setText("yo paste this in game grave: " + sq.make_code(friend) + " cya tonight")
            with patch("gg_desktop.squad_ui.QInputDialog.getMultiLineText") as asked:
                live(window).import_button.click()
                asked.assert_not_called()
            settle(100)
            assert live(window).result_summary.text().startswith("Read the code from your clipboard."), live(window).result_summary.text()
            assert live(window).next_label.isVisibleTo(live(window)) and live(window).next_label.text().startswith("Next:")
            # ...or opens the file the host sent.
            sent = root / "message.txt"
            sent.write_text("squad code\n" + sq.make_code(friend), encoding="utf-8")
            with patch("gg_desktop.squad_ui.QFileDialog.getOpenFileName", return_value=(str(sent), "")):
                live(window).open_file_button.click()
            settle(100)
            assert "Read the code from message.txt." in live(window).result_summary.text()
            QApplication.clipboard().setText("")
            body = live(window)

            # Nexus: a mod with a Nexus reference gets its own page; no key means pages, never a download.
            nexus_friend = sq.Setup("Skyrim Special Edition", [
                sq.Item("workshop", "3333333", "w", "1700000000"),
                sq.Item("mo2", "extra mod", "Extra Mod", "", "skyrimspecialedition/999"),
                sq.Item("mo2", "no source", "No Source")], read_any=True)
            with patch("gg_desktop.squad_ui.QInputDialog.getMultiLineText", return_value=(sq.make_code(nexus_friend), True)):
                body.import_button.click()
            settle(100)
            body = live(window)
            assert len(buttons(window, "Open on Nexus")) == 1 and len(buttons(window, "Open in Steam")) == 1
            assert window.page.squad.detail_label.text().startswith("3 missing"), window.page.squad.detail_label.text()
            assert body.nexus_label.text() == "Nexus: not signed in"
            body.open_button.click()
            settle(1300)
            assert opened == ["steam://url/CommunityFilePage/3333333",
                              "https://www.nexusmods.com/skyrimspecialedition/mods/999?tab=files"], opened
            assert "Slow download" in body.fetch_note.text() and "no download source" in body.fetch_note.text()
            opened.clear()

            # Sign in with a key: it is checked with Nexus, saved, and shown by name.
            from gg_desktop import nexus_core as nx
            key = "abcdEFGH1234567890abcdEFGH1234567890"
            with patch("gg_desktop.squad_ui.QInputDialog.getText", return_value=(key, True)), \
                 patch("gg_desktop.squad_ui.nx.validate", return_value=nx.Account("Alex", True)):
                body.nexus_button.click()
                wait_for(lambda: live(window).nexus_label.text().startswith("Nexus: Alex"), "the Nexus sign-in")
            body = live(window)
            assert body.nexus_label.text() == "Nexus: Alex · Premium" and nx.load_key() == key
            assert body.nexus_button.text() == "Sign out of Nexus"
            opened.clear()

            # Premium: declining the confirmation opens pages; accepting downloads new files only.
            fake_choice = nx.FileChoice(7, "Extra Mod.zip", "1.0", 10)
            def fake_download(url, folder, name, **kw):
                target = Path(folder) / name
                Path(folder).mkdir(parents=True, exist_ok=True)
                import zipfile
                with zipfile.ZipFile(target, "w") as z:
                    z.writestr("Extra Mod 1.0/Data/ExtraMod.esp", b"plugin")
                    z.writestr("Extra Mod 1.0/Data/meshes/extra.nif", b"mesh")
                return target
            with patch.object(window, "confirm", return_value=False):
                body.open_button.click()
            settle(1300)
            assert opened[-1].startswith("https://www.nexusmods.com/") and not (mo2 / "downloads").exists()
            opened.clear()
            with patch.object(window, "confirm", return_value=True) as confirm, \
                 patch("gg_desktop.squad_ui.nx.validate", return_value=nx.Account("Alex", True)), \
                 patch("gg_desktop.squad_ui.nx.main_file", return_value=fake_choice), \
                 patch("gg_desktop.squad_ui.nx.download_url", return_value="https://x.nexus-cdn.com/a.zip"), \
                 patch("gg_desktop.squad_ui.nx.download", side_effect=fake_download):
                body.open_button.click()
                assert "nothing is overwritten" in confirm.call_args[0][1] and "switched off" in confirm.call_args[0][1]
                wait_for(lambda: "Downloaded 1 file" in live(window).fetch_note.text(), "the Nexus download")
                note = live(window).fetch_note.text()
                assert "Installed 1 as new mod, switched off" in note and "press F5" in note, note
            assert (mo2 / "downloads" / "Extra Mod.zip").is_file(), "saved into the Mod Organizer 2 downloads folder"
            assert (mo2 / "mods" / "Extra Mod" / "ExtraMod.esp").read_bytes() == b"plugin", "installed as a new mod folder"
            assert (mo2 / "mods" / "Extra Mod" / "meshes" / "extra.nif").is_file()
            assert nx.read_meta(mo2 / "mods" / "Extra Mod" / "meta.ini") == "skyrimspecialedition/999"
            assert (mo2 / "profiles" / "Co-op" / "modlist.txt").read_text(encoding="utf-8") == "+SkyUI\n-Off\n+USSEP\n", \
                "the profile and load order are never touched"
            opened.clear()

            # Last step: a NEW Mod Organizer 2 profile with the friend's mods on in the friend's order.
            body = live(window)
            assert body.profile_button.isVisibleTo(body)
            with patch.object(window, "confirm", return_value=True) as confirm:
                body.profile_button.click()
                assert "is only read and is not changed" in confirm.call_args[0][1]
            made = mo2 / "profiles" / "GG Squad - Co-op"
            assert made.is_dir() and (made / "gg-squad.json").is_file()
            assert (made / "modlist.txt").read_text(encoding="utf-8") == "+Extra Mod\n-SkyUI\n-Off\n-USSEP\n", \
                (made / "modlist.txt").read_text(encoding="utf-8")
            assert (mo2 / "profiles" / "Co-op" / "modlist.txt").read_text(encoding="utf-8") == "+SkyUI\n-Off\n+USSEP\n"
            assert "Your own profile was not changed" in body.fetch_note.text() and "1 is not installed here yet" in body.fetch_note.text()
            assert body.next_label.text() == 'Last step: open Mod Organizer 2 and pick the profile "GG Squad - Co-op".', body.next_label.text()
            assert "1 of the missing is installed but switched off" in body.result_summary.text(), body.result_summary.text()
            assert window.grab().save(str(args.output / "ready-room-squad-flow-1280.png"))

            # A free account is told so and gets the page instead.
            other = sq.Setup("Skyrim Special Edition", [
                sq.Item("mo2", "another mod", "Another Mod", "", "skyrimspecialedition/1000")], read_any=True)
            with patch("gg_desktop.squad_ui.QInputDialog.getMultiLineText", return_value=(sq.make_code(other), True)):
                live(window).import_button.click()
            settle(100)
            with patch.object(window, "confirm", return_value=True), \
                 patch("gg_desktop.squad_ui.nx.validate", return_value=nx.Account("Sam", False)):
                live(window).open_button.click()
                wait_for(lambda: "not Premium" in live(window).fetch_note.text(), "the free-account message")
            settle(1300)
            assert "https://www.nexusmods.com/skyrimspecialedition/mods/1000?tab=files" in opened, opened
            live(window).nexus_button.click()
            assert nx.load_key() == "" and live(window).nexus_label.text() == "Nexus: not signed in"

            # A code for another game and a junk code are refused in words.
            wrong = sq.make_code(sq.Setup("Fallout 4", [sq.Item("mo2", "a", "A")], read_any=True))
            with patch("gg_desktop.squad_ui.QInputDialog.getMultiLineText", return_value=(wrong, True)):
                body.import_button.click()
            assert "This code is for Fallout 4" in error.call_args[0][1]
            with patch("gg_desktop.squad_ui.QInputDialog.getMultiLineText", return_value=("nonsense", True)):
                body.import_button.click()
            assert "not a Squad Sync code" in error.call_args[0][1]

            # A snapshot of my own list matches my list exactly.
            body.snapshot_button.click()
            settle(100)
            assert body.compare_snapshot_button.isEnabled()
            label = f"{sq.list_snapshots('Skyrim Special Edition')[0][1]} · 6 items"
            with patch("gg_desktop.squad_ui.QInputDialog.getItem", return_value=(label, True)):
                body.compare_snapshot_button.click()
            settle(100)
            assert body.comparison.summary.startswith("Nothing is missing"), body.comparison.summary
            assert not body.open_button.isVisibleTo(body)
            assert window.page.squad.detail_label.text().startswith("Nothing is missing")

            # A page rebuild keeps the game, the setup and the newest comparison.
            window.navigate("Ready Room")
            settle(300)
            body = live(window)
            assert body.setup is not None and body.comparison is not None
            assert body.result_summary.text().startswith("Nothing is missing")
    print("Squad Sync smoke passed")


if __name__ == "__main__":
    main()
