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
        (local / "Skyrim Special Edition").mkdir()
        (local / "Skyrim Special Edition" / "plugins.txt").write_text("*SkyUI_SE.esp\n*Patch.esp\n", encoding="utf-8")
        (root / "Roaming" / "Vortex").mkdir(parents=True)
        game = SteamGame("489830", "Skyrim Special Edition", str(library), str(install), 100, None, "Unknown")
        env = {"LOCALAPPDATA": str(local), "APPDATA": str(root / "Roaming")}
        opened = []
        with patch.dict(os.environ, env), \
             patch("gg_desktop.app.load_settings", side_effect=default_settings), \
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
            assert "Scan your PC" in live(window).summary.text() and not live(window).read_button.isEnabled()

            window.inventory.steam = [game]
            window.inventory.games = merge_games([game], [])
            window.inventory.scanned_at = "Disposable Squad QA"
            window.navigate("Ready Room")
            settle(300)
            body = live(window)
            assert body.games.count() == 1 and body.read_button.isEnabled()
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

            friend = sq.Setup("Skyrim Special Edition", [
                sq.Item("workshop", "1111111", "w", "1700000000"), sq.Item("workshop", "2222222", "w", "1700009999"),
                sq.Item("workshop", "3333333", "w", "1700000000"), sq.Item("mo2", "skyui", "SkyUI"),
                sq.Item("plugin", "skyui_se.esp", "SkyUI_SE.esp")], read_any=True)
            with patch("gg_desktop.squad_ui.QInputDialog.getText", return_value=(sq.make_code(friend), True)):
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
            with patch.object(window, "confirm", return_value=False):
                body.open_button.click()
            assert opened == []
            with patch.object(window, "confirm", return_value=True) as confirm:
                body.open_button.click()
                assert "does not subscribe" in confirm.call_args[0][1]
            assert opened == ["steam://url/CommunityFilePage/3333333"], opened

            # A code for another game and a junk code are refused in words.
            wrong = sq.make_code(sq.Setup("Fallout 4", [sq.Item("mo2", "a", "A")], read_any=True))
            with patch("gg_desktop.squad_ui.QInputDialog.getText", return_value=(wrong, True)):
                body.import_button.click()
            assert "This code is for Fallout 4" in error.call_args[0][1]
            with patch("gg_desktop.squad_ui.QInputDialog.getText", return_value=("nonsense", True)):
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

            # A page rebuild keeps the game, the setup and the newest comparison.
            window.navigate("Ready Room")
            settle(300)
            body = live(window)
            assert body.setup is not None and body.comparison is not None
            assert body.result_summary.text().startswith("Nothing is missing")
    print("Squad Sync smoke passed")


if __name__ == "__main__":
    main()
