"""Native Qt check of the Mods gallery: poster wall, banner, card rows, selection, Gallery/List switch, search, no file changes."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import time
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
    from PySide6.QtWidgets import QApplication, QLabel
    from core import default_settings
    from gg_desktop.app import CrimsonWindow
    from gg_desktop import mods_gallery as mg
    from gg_desktop import mods_gallery_data as gd
    from tests.test_mods_functionality import mo2_fixture

    app = QApplication.instance() or QApplication([])

    def settle():
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()

    def wait_for(predicate, what="Mods did not finish its task"):
        deadline = time.monotonic() + 20
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
            time.sleep(.004)
        assert predicate(), what
        settle()

    def tree_bytes(folder):
        return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in folder.rglob("*") if p.is_file()}

    def cards(window):
        return window.mod_gallery.findChildren(mg.ModCard)

    def card_named(window, name):
        return next(c for c in cards(window) if c.c.facts.name == name)

    def posters(window):
        return window.mod_gallery.findChildren(mg.PosterTile)

    with tempfile.TemporaryDirectory(prefix="GG-mods-gallery-") as temp:
        root = Path(temp)
        inventory, storage, profiles, ini = mo2_fixture(root)
        (storage / "MountainTextures" / "meta.ini").write_text("[General]\nversion=2.0\nnewestVersion=2.5\n", encoding="utf-8")
        before = tree_bytes(ini.parent)
        settings = default_settings()
        settings["mod_extra_roots"] = []
        with patch("gg_desktop.app.load_settings", side_effect=lambda: dict(settings)), \
             patch("gg_desktop.ready_room_services.config_dir", return_value=root / "Preferences"), \
             patch("gg_desktop.mods_page.save_settings"), \
             patch.object(CrimsonWindow, "info"), \
             patch.object(CrimsonWindow, "error") as errors, \
             patch.object(CrimsonWindow, "confirm", return_value=True), \
             patch.object(CrimsonWindow, "start_scan"):
            window = CrimsonWindow()
            window.resize(1280, 790)
            window.show()
            window.inventory = inventory
            window.settings = dict(settings)
            window.navigate("Mods")
            wait_for(lambda: not window.workers and window.page.mods.report is not None)
            wait_for(lambda: window._mod_updates_scanned and not window.workers, "Update evidence never finished")
            control = window.page.mods
            settle()

            # The Library opens as a gallery; the table and the filter column step aside, the view bar shows.
            assert mg.is_gallery(window)
            assert window.mod_gallery.isVisible() and window.mod_view_bar.isVisible()
            assert not window.mod_table.isVisible() and not window.mod_game_filters.isVisible()
            assert window.mod_view_bar.gallery_button.isChecked() and not window.mod_view_bar.list_button.isChecked()
            assert window.grab().save(str(args.output / "mods-gallery-1280.png"))

            # Poster wall: All Games first, then one poster per game that has mods, each with its real count.
            tiles = posters(window)
            names = [t.tile.name for t in tiles]
            assert names[0] == gd.ALL_GAMES, names
            assert set(names[1:]) == {v.game for v in window._mod_views}, names
            assert tiles[0].tile.count == len(window._mod_views)
            assert tiles[0].picked and not any(t.picked for t in tiles[1:]), "All Games is the picked poster at first"
            assert all(t.accessibleName() for t in tiles)

            # Cards come from real facts: the recorded update and the file-sharing check both show, and nothing else does.
            expected_flagged = {e.name for e in control.catalog.entries if e.kind == "mod" and control.findings(e)}
            updates = {e.name for e in control.catalog.entries if e.kind == "mod"
                       and window._mod_updates.get(e.key) and window._mod_updates[e.key].outdated}
            assert "Mountain Textures" in updates, updates
            by_label = {}
            for c in cards(window):
                by_label.setdefault(c.c.label, set()).add(c.c.facts.name)
            assert by_label.get("Conflict", set()) == expected_flagged, (by_label, expected_flagged)
            assert by_label.get("Update ready", set()) == updates - expected_flagged, (by_label, updates)
            assert by_label.get("Off") and "Framework" in by_label["Off"], by_label
            assert not any("safe" in c.c.note.casefold() or c.c.action not in ("", "Review", "Details") for c in cards(window))
            mountain = card_named(window, "Mountain Textures")
            assert "2.5" in mountain.c.version_text and mountain.c.action in ("Review", "Details")
            assert mountain.accessibleName().startswith("Mountain Textures,")
            assert mountain.focusPolicy() == Qt.StrongFocus

            # Clicking a card selects that row, fills the inspector and marks only that card.
            QTest.mouseClick(mountain, Qt.LeftButton)
            settle()
            assert window.mod_table.currentRow() == mountain.c.facts.index
            assert window._shown_mods[window.mod_table.currentRow()].name == "Mountain Textures"
            marked = [c for c in cards(window) if c.property("selected")]
            assert [c.c.facts.name for c in marked] == ["Mountain Textures"], [c.c.facts.name for c in marked]
            assert len(window.mod_details.findChildren(mg.ArtHero)) == 1
            text = " ".join(w.text() for w in window.mod_details.findChildren(QLabel))
            assert "Mountain Textures" in text and "2.5" in text, text
            assert window.grab().save(str(args.output / "mods-gallery-selected-1280.png"))

            # Keyboard: a card takes focus and the space bar picks it.
            other = card_named(window, "Framework")
            other.setFocus()
            QTest.keyClick(other, Qt.Key_Space)
            settle()
            assert window._shown_mods[window.mod_table.currentRow()].name == "Framework"

            # Review on a conflict card goes to the Conflicts tab; the gallery gives way to that tab's table.
            flagged = [c for c in cards(window) if c.c.label == "Conflict"]
            if flagged:
                flagged[0].reviewed.emit(flagged[0].c.facts.index)
                settle()
                assert window._mod_tab == "Conflicts" and window.mod_table.isVisible() and not window.mod_gallery.isVisible()
                assert not window.mod_view_bar.isVisible()
                window.mod_tabs.buttons["Library"].click()
                settle()
                assert mg.is_gallery(window) and window.mod_gallery.isVisible() and not window.mod_table.isVisible()

            # Choosing a poster filters to that game through the same filter the list uses.
            game_tile = next(t for t in posters(window) if t.tile.name != gd.ALL_GAMES)
            game_tile.click()
            settle()
            assert window.mod_game_filters.currentItem().data(Qt.UserRole) == game_tile.tile.name
            assert all(c.c.facts.game == game_tile.tile.name for c in cards(window))
            assert next(t for t in posters(window) if t.tile.name == game_tile.tile.name).picked
            banner_text = " ".join(w.text() for w in window.mod_gallery.findChildren(QLabel))
            assert game_tile.tile.name in banner_text and "SELECTED GAME" in banner_text, banner_text
            posters(window)[0].click()
            settle()
            assert window.mod_game_filters.currentRow() == 0

            # Search through the gallery's own box drives the same search the list uses.
            search = window.mod_view_bar.search
            search.setFocus()
            QTest.keyClicks(search, "Mountain")
            settle()
            assert window.mod_search.text() == "Mountain"
            assert {c.c.facts.name for c in cards(window)} == {"Mountain Textures"}, [c.c.facts.name for c in cards(window)]
            search.clear()
            settle()
            assert window.mod_search.text() == "" and len(cards(window)) > 1

            # Manager chips are the manager check boxes.
            if window.mod_manager_checks:
                chips = [b for b in window.mod_gallery.findChildren(mg.QPushButton) if b.objectName() == "chip"]
                assert chips and chips[0].text() == "All managers" and chips[0].isChecked()
                chips[1].click()
                settle()
                assert any(c.isChecked() for c in window.mod_manager_checks)
                chips = [b for b in window.mod_gallery.findChildren(mg.QPushButton) if b.objectName() == "chip"]
                chips[0].click()
                settle()
                assert not any(c.isChecked() for c in window.mod_manager_checks)

            # List view is the old table, with the filter column back; switching back restores the gallery.
            window.mod_view_bar.list_button.click()
            settle()
            assert not mg.is_gallery(window) and window.mod_table.isVisible() and window.mod_game_filters.isVisible()
            assert not window.mod_gallery.isVisible() and window.mod_view_bar.list_button.isChecked()
            assert window.mod_table.columnCount() == 7 and window.mod_table.rowCount() >= 4
            window.mod_view_bar.gallery_button.click()
            settle()
            assert mg.is_gallery(window) and window.mod_gallery.isVisible() and not window.mod_table.isVisible()

            # Other widths keep every part reachable.
            for width, height in ((960, 650), (1536, 864)):
                window.resize(width, height)
                settle()
                assert window.mod_gallery.isVisible()
                assert window.grab().save(str(args.output / f"mods-gallery-{width}.png"))
            window.resize(1280, 790)
            settle()

            assert tree_bytes(ini.parent) == before, "The gallery only reads: manager files must stay identical"
            errors.assert_not_called()
            window.close()
            settle()
    print("PASS: Mods gallery poster wall, banner, status cards from real facts, selection, keyboard, Review, "
          "game filter, search, manager chips, List switch and untouched manager files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
