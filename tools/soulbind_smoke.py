"""Native Qt check of Soulbind: the Ready Room panel, apply with backup, undo, share code, Games card badge."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch


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
    import core
    from core import SteamGame, default_settings
    from gg_desktop import soulbind_core as sb
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.models import merge_games
    from gg_desktop.reference_widgets import CARD_ROLE
    from gg_desktop.ready_room_services import parse_news

    app = QApplication.instance() or QApplication([])

    def settle():
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()

    skyrim = ("[Controls]\r\nbInvertYValues=0\r\n[Display]\r\nfDefaultWorldFOV=75.0000\r\n")
    with tempfile.TemporaryDirectory(prefix="GG-soulbind-") as temp:
        root = Path(temp)
        docs = root / "Documents"
        ini = docs / "My Games" / "Skyrim Special Edition" / "SkyrimPrefs.ini"
        ini.parent.mkdir(parents=True)
        ini.write_bytes(skyrim.encode())
        install, other_install = root / "Skyrim", root / "Cyberpunk"
        install.mkdir()
        other_install.mkdir()
        game = SteamGame("489830", "The Elder Scrolls V: Skyrim Special Edition", str(root), str(install), 100, None, "Unknown")
        other = SteamGame("1091500", "Cyberpunk 2077", str(root), str(other_install), 100, None, "Unknown")
        env = {"LOCALAPPDATA": str(root / "Local")}
        with patch.dict(os.environ, env), \
             patch("gg_desktop.app.load_settings", side_effect=default_settings), \
             patch("gg_desktop.ready_room_services.config_dir", return_value=root / "Prefs"), \
             patch("gg_desktop.ready_room_services.fetch_one",
                   side_effect=lambda sid, name: parse_news({"appnews": {"appid": int(sid), "newsitems": []}}, sid, name)), \
             patch("gg_desktop.soulbind_core.default_roots", return_value={"documents": [docs], "appdata": [root / "none"]}), \
             patch.object(CrimsonWindow, "info"), patch.object(CrimsonWindow, "error") as error:
            window = CrimsonWindow()
            window.resize(1280, 790)
            window.show()
            window.inventory.steam = [game, other]
            window.inventory.games = merge_games([game, other], [])
            window.inventory.scanned_at = "Disposable Soulbind QA"
            window.navigate("Ready Room")
            settle()
            panel = window.page.soulbind
            assert panel is not None, "Soulbind panel is missing from Ready Room"
            body = panel.soulbind
            assert body.profile == {}
            assert [r[2].text for r in body.rows] == ["No profile"], [r[2].text for r in body.rows]
            assert not body.copy_button.isEnabled()
            assert not [b for b in panel.findChildren(QPushButton) if b.text() == "Apply"]

            body.uses["invert_y"].setChecked(True)
            body.controls["invert_y"].setCurrentIndex(body.controls["invert_y"].findData(True))
            body.uses["subtitles"].setChecked(True)
            settle()
            assert body.profile == {"invert_y": True, "subtitles": True}, body.profile
            assert sb.load_profile() == body.profile, "Profile is saved"
            assert [r[2].text for r in body.rows] == ["1 to apply"], [r[2].text for r in body.rows]
            assert "not supported" in body.rows[0][2].detail
            assert body.copy_button.isEnabled()
            window.page.ensureWidgetVisible(panel)
            settle()
            assert window.grab().save(str(args.output / "ready-room-soulbind-1280.png"))

            # Declining the confirmation changes nothing.
            with patch.object(window, "confirm", return_value=False):
                next(b for b in panel.findChildren(QPushButton) if b.text() == "Apply").click()
            assert ini.read_bytes() == skyrim.encode()
            # Applying edits only the value, saves a backup, writes the activity log.
            with patch.object(window, "confirm", return_value=True) as confirm:
                next(b for b in panel.findChildren(QPushButton) if b.text() == "Apply").click()
                shown = confirm.call_args[0][1]
                assert str(ini) in shown, shown
            settle()
            assert ini.read_bytes() == skyrim.replace("bInvertYValues=0", "bInvertYValues=1").encode()
            assert [r[2].text for r in body.rows] == ["Soulbound"], [r[2].text for r in body.rows]
            entry = sb.ledger()[-1]
            assert Path(entry["backup"]).read_bytes() == skyrim.encode()
            assert any(e["kind"] == "soulbind_apply" for e in core.get_activity())
            assert window.grab().save(str(args.output / "ready-room-soulbind-applied-1280.png"))

            # The Games card shows a badge that matches the file.
            window.navigate("Games")
            settle()
            badges = [window.game_grid.item(i).data(CARD_ROLE).get("soulbind") for i in range(window.game_grid.count())]
            assert badges.count(("Soulbound", "green")) == 1 and badges.count(None) == 1, badges
            assert window.grab().save(str(args.output / "games-soulbind-1280.png"))

            # Undo restores the file; a later change blocks the undo.
            window.navigate("Ready Room")
            settle()
            body = window.page.soulbind.soulbind
            with patch.object(window, "confirm", return_value=True):
                next(b for b in window.page.soulbind.findChildren(QPushButton) if b.text() == "Undo").click()
            settle()
            assert ini.read_bytes() == skyrim.encode()
            assert sb.ledger()[-1]["reverted"] is True

            # Share codes round-trip and junk is refused.
            code = sb.make_code(body.profile)
            with patch("gg_desktop.soulbind_ui.QInputDialog.getText", return_value=("nonsense", True)):
                body.import_code()
            error.assert_called()
            with patch("gg_desktop.soulbind_ui.QInputDialog.getText", return_value=(sb.make_code({"fov": 100}), True)), \
                 patch.object(window, "confirm", return_value=True):
                body.import_code()
            settle()
            assert body.profile == {"fov": 100}
            assert body.uses["fov"].isChecked() and not body.uses["invert_y"].isChecked()
            assert sb.read_code(code) == {"invert_y": True, "subtitles": True}
    print("Soulbind smoke passed")


if __name__ == "__main__":
    main()
