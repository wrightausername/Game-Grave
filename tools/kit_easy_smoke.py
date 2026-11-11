"""Native Qt check of the easy Resurrection Kit flow on disposable files: set up, create, restore, cancel."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import os
from pathlib import Path
import sys
import tempfile
import zipfile
import faulthandler
from types import SimpleNamespace
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("_ci_temp"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    faulthandler.dump_traceback_later(240, exit=True)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication, QCheckBox
    from core import SteamGame, default_settings
    from gg_desktop import kit_easy_ui as ui
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.models import merge_games

    app = QApplication.instance() or QApplication([])

    def settle(ms=0):
        end = datetime.now() + timedelta(milliseconds=ms)
        while True:
            app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            if datetime.now() >= end:
                break

    def wait_for(test, what, seconds=40):
        end = datetime.now() + timedelta(seconds=seconds)
        while not test():
            settle(25)
            assert datetime.now() < end, "Timed out waiting for " + what

    with tempfile.TemporaryDirectory(prefix="GG-kit-easy-") as temp:
        root = Path(temp)
        library = root / "Steam" / "steamapps"
        install = library / "common" / "Skyrim Special Edition"
        (install / "Data").mkdir(parents=True)
        (install / "SkyrimSE.exe").write_bytes(b"MZ" + b"e" * 20000)
        (install / "Data" / "Skyrim.esm").write_bytes(b"esm" * 20000)
        (install / "Data" / "Textures.bsa").write_bytes(b"bsa" * 20000)
        (library / "appmanifest_489830.acf").write_text('"AppState" {}')
        profile = root / "User"
        local = profile / "AppData" / "Local"
        saves = profile / "Documents" / "My Games" / "Skyrim Special Edition" / "Saves"
        saves.mkdir(parents=True)
        (saves / "Save1.ess").write_bytes(b"progress")
        (local / "Skyrim Special Edition").mkdir(parents=True)
        (local / "Skyrim Special Edition" / "plugins.txt").write_text("*SkyUI.esp\n")
        name = "The Elder Scrolls V: Skyrim Special Edition"
        game = SteamGame("489830", name, str(library), str(install), 60000, None, "Steam manifest")
        env = {"USERPROFILE": str(profile), "LOCALAPPDATA": str(local), "APPDATA": str(profile / "AppData" / "Roaming")}
        kits = root / "Kits"
        # Windows caches its answer for the Documents folder inside one process, so this check, which pretends to be
        # two PCs in one run, reads it from the pretend profile instead. The real call is covered by test_kit_install.
        def pretend_documents(environ=None):
            source = os.environ if environ is None else environ
            return Path(source["USERPROFILE"]) / "Documents"
        with patch.dict(os.environ, env), patch("gg_desktop.app.load_settings", side_effect=default_settings), \
             patch("resurrection_v2.documents_dir", side_effect=pretend_documents), \
             patch("kit_easy.documents_dir", side_effect=pretend_documents), \
             patch("core.config_dir", return_value=root / "Prefs"), \
             patch.object(CrimsonWindow, "confirm", return_value=True), patch.object(CrimsonWindow, "info"), \
             patch.object(CrimsonWindow, "error") as error:
            window = CrimsonWindow()
            window.resize(1280, 790)
            window.show()
            window.inventory.steam = [game]
            window.inventory.games = merge_games([game], [])
            window.inventory.saves = [SimpleNamespace(game=name, path=str(saves), kind="Saves", reason="test")]
            settle(200)

            # ---- set up and create
            dialog = ui.EasySetup(window)
            dialog.folder.setText(str(kits))
            dialog.show()
            wait_for(lambda: dialog.plan is not None, "the kit plan")
            titles = {c.accessibleName(): c for c in dialog.findChildren(QCheckBox)}
            assert {"Game install", "Saves", "Steam install record", "Plugin load order"} <= set(titles), sorted(titles)
            assert all(c.isChecked() for c in titles.values())
            assert "about" in dialog.summary.text() and "Free space" in dialog.summary.text(), dialog.summary.text()
            assert dialog.create_button.isEnabled()
            assert dialog.grab().save(str(args.output / "kit-easy-setup.png"))
            titles["Saves"].setChecked(False)
            settle(50)
            titles["Saves"].setChecked(True)
            dialog.create_button.click()
            wait_for(lambda: "Kit saved and checked" in dialog.status.text(), "the kit to finish")
            assert not window.cleaning
            made = sorted(kits.glob("*.zip"))
            assert len(made) == 1, made
            with zipfile.ZipFile(made[0]) as z:
                names = set(z.namelist())
            assert {"Game/SkyrimSE.exe", "Game/Data/Skyrim.esm", "Saves/Save1.ess", "LoadOrder/plugins.txt",
                    "Launcher/appmanifest_489830.acf"} <= names, names
            assert dialog.grab().save(str(args.output / "kit-easy-created.png"))
            dialog.close()

            # ---- a cancelled kit leaves nothing behind
            second = ui.EasySetup(window)
            second.folder.setText(str(root / "Cancelled"))
            second.show()
            wait_for(lambda: second.plan is not None, "the second plan")
            real = ui.engine.create_complete_kit
            with patch.object(ui.engine, "create_complete_kit",
                              side_effect=lambda *a, **k: real(*a, **dict(k, cancel=lambda: True))):
                second.create_button.click()
                wait_for(lambda: "Cancelled" in second.status.text(), "the cancel")
            assert list((root / "Cancelled").glob("*")) == [], list((root / "Cancelled").glob("*"))
            second.close()

            # ---- restore onto a "new PC" library
            new_library = root / "NewPC" / "steamapps" / "common"
            new_library.mkdir(parents=True)
            new_profile = root / "NewUser"
            new_env = {"USERPROFILE": str(new_profile), "LOCALAPPDATA": str(new_profile / "AppData" / "Local"),
                       "APPDATA": str(new_profile / "AppData" / "Roaming")}
            new_profile.mkdir()
            with patch.dict(os.environ, new_env):
                restore = ui.EasyRestore(window)
                restore.manifest = Path(str(made[0]) + ".ggkit.json")
                restore.kit_label.setText(str(restore.manifest))
                restore.library.setEditText(str(new_library))
                restore.show()
                restore.preview()
                assert restore.plan is not None and not restore.plan["blocked"], restore.plan
                assert "Game: new folder" in restore.preview_label.text()
                assert restore.go.isEnabled()
                assert restore.grab().save(str(args.output / "kit-easy-restore.png"))
                restore.go.click()
                wait_for(lambda: "Restored" in restore.status.text(), "the restore")
                assert (new_library / "Skyrim Special Edition" / "SkyrimSE.exe").read_bytes()[:2] == b"MZ"
                assert (new_library.parent / "appmanifest_489830.acf").is_file()
                assert (new_profile / "Documents" / "My Games" / "Skyrim Special Edition" / "Saves" / "Save1.ess").read_bytes() == b"progress"
                assert (new_profile / "AppData" / "Local" / "Skyrim Special Edition" / "plugins.txt").is_file()
                assert not window.cleaning
                restore.close()
                # Doing it again is refused, and nothing changes.
                again = ui.EasyRestore(window)
                again.manifest = restore.manifest
                again.library.setEditText(str(new_library))
                again.preview()
                assert again.plan["blocked"] and not again.go.isEnabled()
                again.close()
            # the originals were only read
            assert (install / "SkyrimSE.exe").read_bytes()[:2] == b"MZ"
            error.assert_not_called()
    print("Kit easy smoke passed")


if __name__ == "__main__":
    main()
