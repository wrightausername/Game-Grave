"""Native Qt check of the Game DNA page: proven locations only, Analyze, linking your own folders, hand-offs to the owning tabs."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("_ci_temp"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QCoreApplication, QEvent, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QFileDialog, QLabel, QWidget
    from core import ModFolder, OldFile, SteamGame, default_settings
    from gg_desktop import dna_data, dna_page
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.backend import Inventory, refresh_graveyard
    from gg_desktop.dna_page import state_of
    from gg_desktop.models import merge_games

    app = QApplication.instance() or QApplication([])
    day = 86400

    def settle():
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()

    def wait_for(predicate, what="Game DNA did not finish its task"):
        deadline = time.monotonic() + 40
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
            time.sleep(.004)
        assert predicate(), what
        settle()

    def make(path, size, age=0):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"d" * size)
        moment = time.time() - age * day
        os.utime(path, (moment, moment))
        return path

    def old(path):
        info = path.stat()
        return OldFile(str(path), info.st_size, info.st_mtime, info.st_dev, info.st_ino, info.st_mtime_ns, info.st_nlink)

    def tree_bytes(folder):
        return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in folder.rglob("*") if p.is_file()}

    def idle(window):
        wait_for(lambda: not state_of(window).busy and not window.workers)

    def choose(window, name):
        state = state_of(window)
        index = next(i for i, g in enumerate(state.shown) if g.name == name)
        window.dna_games.setCurrentRow(index)
        settle()
        assert state.profile.game.name == name

    def tab(window, name):
        window.dna_tabs.buttons[name].click()
        settle()
        assert state_of(window).tab == name

    def table_rows(window):
        table = window.dna_asset_table
        return [[table.item(r, c).text() if table.item(r, c) else "" for c in range(4)] for r in range(table.rowCount())]

    def summary_text(window):
        return " ".join(w.text() for w in window.dna_summary.findChildren(QLabel))

    with tempfile.TemporaryDirectory(prefix="GG-dna-page-") as temp:
        root = Path(temp)
        steam_root, home = root / "Steam", root / "Home"
        steam_root.mkdir()
        home.mkdir()
        install = steam_root / "steamapps" / "common" / "Cyberpunk 2077"
        make(install / "game.bin", 4000)
        make(install / "data" / "a.pak", 3000)
        make(install / "mods" / "bigmod" / "m.dat", 500)
        other = steam_root / "steamapps" / "common" / "Skyrim"
        make(other / "skyrim.exe", 100)
        make(steam_root / "steamapps" / "shadercache" / "1091500" / "s1.bin", 700)
        make(steam_root / "steamapps" / "shadercache" / "1091500" / "s2.bin", 300)
        shots = [make(steam_root / "userdata" / "1" / "760" / "remote" / "1091500" / "screenshots" / f"s{i}.jpg", 250)
                 for i in range(2)]
        saves = home / "Saved Games" / "Cyberpunk 2077"
        make(saves / "slot1.sav", 900)
        unrelated = home / "Saved Games" / "Unrelated Thing"
        make(unrelated / "x.sav", 10)
        before = tree_bytes(root)
        now = time.time()
        cyber = SteamGame("1091500", "Cyberpunk 2077", str(steam_root), str(install), 120000000, now - 500 * day, "Fixture")
        skyrim = SteamGame("72850", "Skyrim", str(steam_root), str(other), 5000, now - 2 * day, "Fixture")
        mod = ModFolder("bigmod", str(install / "mods" / "bigmod"), "", "Installed: possible mods", (), 500, 1, False,
                        "Manual / Other", "Fixture")
        settings = default_settings()
        settings["never_touch"] = []
        saved = []

        def keep(updated):
            saved.append(dict(updated))

        stack = ExitStack()
        for target, options in (
            ("gg_desktop.app.load_settings", dict(return_value=settings)),
            ("core._steam_roots", dict(return_value=[steam_root])),
            ("core.steam_libraries", dict(return_value=[steam_root])),
            ("core.save_settings", dict(side_effect=keep)),
            ("gg_desktop.backend.save_settings", dict(side_effect=keep)),
            ("gg_desktop.backend.log_event", {}),
            ("gg_desktop.dna_page.save_settings", dict(side_effect=keep)),
            ("gg_desktop.recovery_screens.save_settings", dict(side_effect=keep)),
            ("gg_desktop.reference_library.save_settings", {}),
            ("gg_desktop.ready_room_services.config_dir", dict(return_value=root / "Preferences")),
            ("gg_desktop.game_artwork.artwork_dir", dict(return_value=root / "Artwork")),
            ("gg_desktop.game_artwork._request", dict(side_effect=AssertionError("No automatic network"))),
        ):
            stack.enter_context(patch(target, **options))
        stack.enter_context(patch.object(CrimsonWindow, "info"))
        errors = stack.enter_context(patch.object(CrimsonWindow, "error"))
        confirm = stack.enter_context(patch.object(CrimsonWindow, "confirm", return_value=False))
        chooser = stack.enter_context(patch.object(QFileDialog, "getExistingDirectory", return_value=""))
        with stack:
            window = CrimsonWindow()
            hints = [SimpleNamespace(path=str(saves), game="Cyberpunk 2077", kind="Saved Games"),
                     SimpleNamespace(path=str(unrelated), game="Unrelated Thing", kind="Saved Games")]
            window.inventory = Inventory(steam=[cyber, skyrim], games=merge_games([cyber, skyrim], []), mods=[mod],
                                         saves=hints, screenshots=[old(p) for p in shots], scanned_at="2026-11-06 12:00")
            refresh_graveyard(window.inventory, window.settings)
            window.show()
            window.resize(1280, 720)
            window.navigate("Game DNA")
            settle()
            state = state_of(window)
            assert [g.name for g in state.shown] and len(state.shown) == 2, state.shown

            # A hand-off from another tab selects the right game.
            game = next(g for g in window.inventory.games if g.name == "Cyberpunk 2077")
            window._photo_game_dna(game)
            settle()
            assert window.current_route == "Game DNA" and state.profile.game.key == game.key
            assert window._shown_dna_games[window.dna_games.currentRow()].key == game.key

            # Only proven locations, counted once. Saves are a suggestion, never counted.
            profile = state.profile
            kinds = {l.category: l for l in profile.locations}
            assert set(kinds) == {"Game Install", "Mods / Addons", "Caches", "Screenshots"}, set(kinds)
            assert kinds["Mods / Addons"].nested and kinds["Mods / Addons"].evidence == "Location"
            assert kinds["Caches"].evidence == "Direct" and kinds["Screenshots"].items == 2
            assert [h.path for h in profile.hints] == [str(saves)], profile.hints
            total, segments, unknown = dna_data.footprint(profile)
            assert dict((n, v) for n, v, _ in segments)["Mods / Addons"] == 500
            assert total == 120000000 + 500 * 0 + 500 and unknown == 1, (total, unknown)
            assert window.dna_metrics.values[0].text() == "Cyberpunk 2077"
            assert window.dna_metrics.values[5].text() == "Not run" and window.dna_metrics.values[3].text() == "—"
            assert "Not counted" in summary_text(window)
            assert window.dna_metrics.values[4].text() == "500 Days"
            assert window.grab().save(str(args.output / "dna-storage-1280.png"))

            tab(window, "Caches")
            rows = table_rows(window)
            assert len(rows) == 1 and rows[0][1] == "Direct" and "shadercache" in rows[0][0], rows
            tab(window, "Saves")
            rows = table_rows(window)
            assert len(rows) == 1 and rows[0][1] == "Name hint" and rows[0][3] == "Not linked", rows
            assert str(unrelated) not in rows[0][0]
            tab(window, "Recordings")
            assert "linked" in table_rows(window)[0][0].lower(), table_rows(window)
            tab(window, "Screenshots")
            assert table_rows(window)[0][2] == "2"
            tab(window, "Files & Locations")
            assert len(table_rows(window)) == 5  # install, mod, cache, screenshots, one suggestion
            assert window.grab().save(str(args.output / "dna-locations-1280.png"))
            tab(window, "Storage DNA")

            # Cleanup suggestions are hand-offs, never deletions. No "safe" claims anywhere.
            names = [s.title for s, _ in state.suggestion_rows]
            assert names == ["Steam shader cache", "2 Steam screenshots", "In your Graveyard"], names
            for s, _ in state.suggestion_rows:
                assert "safe" not in (s.title + s.detail).lower(), s
            assert window.dna_graveyard_button.isEnabled()

            # Analyze is read-only and fills sizes and counts.
            dna_page.analyze(window)
            wait_for(lambda: not state.busy and not window.workers)
            assert window.dna_metrics.values[5].text() == "Complete", window.dna_metrics.values[5].text()
            install_loc = state.profile.install
            assert install_loc.measured and install_loc.size == 7500 and install_loc.items == 3, (install_loc.size, install_loc.items)
            assert window.dna_metrics.values[3].text() == "7", window.dna_metrics.values[3].text()  # 3 install + 2 cache + 2 screenshots, nested mod counted once
            assert state.profile.created is not None and "Folder created" in summary_text(window)
            assert state.profile.unmeasured == 0
            assert tree_bytes(root) == before, "Analyze changed files"

            # Declining a link changes nothing; accepting links only the chosen folder.
            tab(window, "Saves")
            window.dna_asset_table.selectRow(0)
            settle()
            assert window.dna_link_button.text() == "Link Suggested"
            dna_page.link_folder(window)
            settle()
            assert not saved and not window.settings.get("dna_links")
            confirm.return_value = True
            dna_page.link_folder(window)
            settle()
            confirm.return_value = False
            assert window.settings["dna_links"][game.key] == [{"path": str(saves), "category": "Saves"}]
            assert saved and state.profile.of("Saves")[0].evidence == "Yours" and not state.profile.hints
            assert "Name hint" not in [r[1] for r in table_rows(window)]
            dna_page.analyze(window)
            wait_for(lambda: not state.busy and not window.workers)
            assert state.profile.of("Saves")[0].size == 900 and state.profile.of("Saves")[0].measured
            # A folder picked by hand, with a type chosen from the tab.
            chooser.return_value = str(unrelated)
            confirm.return_value = True
            dna_page.link_folder(window)
            settle()
            assert len(window.settings["dna_links"][game.key]) == 2
            # Unlink removes only the link.
            window.dna_asset_table.selectRow(1)
            settle()
            dna_page.unlink_folder(window)
            settle()
            confirm.return_value = False
            assert len(window.settings["dna_links"].get(game.key, [])) == 1
            assert saves.is_dir() and unrelated.is_dir()
            # Proven rows cannot be unlinked.
            tab(window, "Caches")
            window.dna_asset_table.selectRow(0)
            assert not window.dna_unlink_button.isEnabled()
            tab(window, "Storage DNA")
            assert window.grab().save(str(args.output / "dna-after-link-1280.png"))

            # The other game has none of this game's data.
            choose(window, "Skyrim")
            assert [l.category for l in state.profile.locations] == ["Game Install"] and not state.profile.hints
            assert not state.profile.suggestions and not window.dna_review_button.isEnabled()
            assert not window.dna_graveyard_button.isEnabled()
            assert not window.settings["dna_links"].get(skyrim.app_id)
            window.dna_search.setText("cyber")
            settle()
            assert [g.name for g in state.shown] == ["Cyberpunk 2077"] and state.profile.game.name == "Cyberpunk 2077"
            window.dna_search.setText("")
            settle()
            choose(window, "Cyberpunk 2077")

            # Review & Clean hands off to the tab that owns removal, filtered to the game.
            dna_page.review_and_clean(window)
            settle()
            assert window.current_route == "Other Storage" and window.storage_search.text() == "Cyberpunk 2077"
            window.navigate("Game DNA")
            settle()
            choose(window, "Cyberpunk 2077")
            for s, line in state.suggestion_rows:
                line.box.setChecked(s.route == "Captures")
            dna_page.review_and_clean(window)
            settle()
            assert window.current_route == "Captures" and window.capture_search.text() == "Cyberpunk 2077"
            window.navigate("Game DNA")
            settle()
            choose(window, "Cyberpunk 2077")
            dna_page.add_to_graveyard(window)
            settle()
            assert window.current_route == "Graveyard" and getattr(window, "_pending_grave_key", None) in (None, "steam:1091500")
            window.navigate("Game DNA")
            settle()
            assert tree_bytes(root) == before, "Nothing may be removed or changed by Game DNA"

            wait_for(lambda: not window.workers)
            # Layout at the supported sizes.
            for width, height in ((1280, 720), (1440, 900), (960, 650)):
                window.resize(width, height)
                settle()
                QTest.qWait(40)
                settle()
                if window.page.horizontalScrollBar().maximum() != 0:
                    wide = sorted(((w.minimumSizeHint().width(), type(w).__name__, w.objectName())
                                   for w in window.page.findChildren(QWidget)), reverse=True)[:12]
                    print("Horizontal overflow at", (width, height), "viewport", window.page.viewport().width(), "widest:", wide)
                assert window.page.horizontalScrollBar().maximum() == 0, (width, height)
                bottom = window.dna_review_button.mapTo(window, window.dna_review_button.rect().bottomLeft()).y()
                if height >= 720:
                    assert bottom <= window.height(), ("Review & Clean is cut off", (width, height), bottom)
                assert window.grab().save(str(args.output / f"dna-page-{width}.png"))
            errors.assert_not_called()
            window.close()
            settle()
        assert tree_bytes(root) == before
    print("PASS: Game DNA page: only proven locations counted once, saves as suggestions until you link them, read-only Analyze, "
          "link and unlink your own folders, and hand-offs to Other Storage, Captures and Graveyard with no file changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
