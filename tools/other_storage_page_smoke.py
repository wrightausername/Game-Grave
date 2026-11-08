"""Native Qt check of the Other Storage page: scan, categories, tabs, filters, protection and the verified Recycle Bin path."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
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
    from core import SteamGame, default_settings, human_size
    from gg_desktop import other_storage_insight as oi
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.backend import Inventory

    app = QApplication.instance() or QApplication([])

    def settle():
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()

    def wait_for(predicate, what="Other Storage did not finish its task"):
        deadline = time.monotonic() + 30
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
            time.sleep(.004)
        assert predicate(), what
        settle()

    def make(path, size=64):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * size)
        os.utime(path, (1700000000, 1700000000))
        return path

    def tree_bytes(folder):
        return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in folder.rglob("*") if p.is_file()}

    def names(window):
        return [window.storage_table.item(i, 1).text() for i in range(window.storage_table.rowCount())]

    def row_of(window, name):
        return names(window).index(name)

    def open_tab(window, name):
        window.storage_tabs.buttons[name].click()
        settle()
        assert window._storage_tab == name, name

    def check(window, name, on=True):
        window.storage_table.item(row_of(window, name), 0).setCheckState(Qt.Checked if on else Qt.Unchecked)
        settle()

    with tempfile.TemporaryDirectory(prefix="GG-other-storage-page-") as temp:
        root = Path(temp)
        local, program_data, home = root / "Local", root / "ProgramData", root / "Home"
        library, steam_root = root / "SteamLibrary", root / "Steam"
        for folder in (local, program_data, home, library, steam_root):
            folder.mkdir()
        for index in range(3):
            make(local / "D3DSCache" / f"d{index}.bin", 1000)
        for index in range(2):
            make(local / "NVIDIA" / "DXCache" / f"n{index}.bin", 500)
        cache_files = [make(local / "Battle.net" / "Cache" / f"c{index}.dat", 300) for index in range(3)]
        log_files = [make(local / "Battle.net" / "Logs" / f"l{index}.log", 200) for index in range(2)]
        dumps = make(local / "CrashDumps" / "game.exe.1.dmp", 400)
        settings_file = make(home / "Documents" / "My Games" / "Skyrim" / "Skyrim.ini", 100)
        owned = make(library / "steamapps" / "shadercache" / "1091500" / "a.bin", 700)
        orphan = make(library / "steamapps" / "shadercache" / "999999" / "x.bin", 600)
        temp_file = make(library / "steamapps" / "temp" / "t.tmp", 50)
        before = tree_bytes(root)
        game = SteamGame("1091500", "Cyberpunk 2077", str(steam_root), str(library / "steamapps" / "common" / "Cyberpunk 2077"),
                         120000000, None, "Scope fixture")
        settings = default_settings()
        settings["never_touch"] = []
        saved = []
        env = {"LOCALAPPDATA": str(local), "PROGRAMDATA": str(program_data), "USERPROFILE": str(home)}
        shell_bin = root / "DisposableShell"
        shell_bin.mkdir()
        recycled = []

        def fake_recycle(path):
            recycled.append(Path(path))
            shutil.move(str(path), str(shell_bin / (str(len(recycled)) + "-" + Path(path).name)))

        with patch.dict(os.environ, env), \
             patch("gg_desktop.app.load_settings", return_value=settings), \
             patch("gg_desktop.other_storage_page.steam_context", return_value=([steam_root], [library])), \
             patch("core.save_settings", side_effect=saved.append), \
             patch("gg_desktop.other_storage_page.save_settings", side_effect=saved.append), \
             patch("gg_desktop.reference_library.save_settings"), \
             patch("gg_desktop.ready_room_services.config_dir", return_value=root / "Preferences"), \
             patch("gg_desktop.game_artwork.artwork_dir", return_value=root / "Artwork"), \
             patch("gg_desktop.game_artwork._request", side_effect=AssertionError("No automatic network")), \
             patch.object(CrimsonWindow, "info") as info, patch.object(CrimsonWindow, "error") as errors, \
             patch.object(CrimsonWindow, "confirm", return_value=False) as confirm:
            window = CrimsonWindow()
            window.inventory = Inventory(steam=[game], scanned_at="2026-11-06 12:00")
            window.show()
            window.resize(1280, 720)
            window.navigate("Other Storage")
            settle()

            # Before a scan nothing is claimed.
            assert window.storage_table.rowCount() == 0
            assert "Scan Other Storage" in window.storage_notice.text(), window.storage_notice.text()
            assert window.storage_metrics.values[0].text() == human_size(0)
            assert not window.storage_delete.isEnabled()

            from gg_desktop.other_storage_page import state_of
            state = state_of(window)
            window.storage_scan.click()
            wait_for(lambda: not state.busy and not window.workers)
            found = set(names(window))
            expected = {"DirectX Shader Cache", "NVIDIA DirectX Cache", "Battle.net Cache", "Battle.net Logs",
                        "Windows Crash Dumps", "Skyrim", "Cyberpunk 2077 Shader Cache", "Steam app 999999 Shader Cache",
                        "Steam Temp"}
            assert expected <= found, expected - found
            assert window.storage_table.rowCount() == len(found) == 9, names(window)  # two Steam shader folders

            # Metrics and the ring come from the scan only.
            total = sum(e.size for e in window._storage)
            assert window.storage_metrics.values[0].text() == human_size(total), window.storage_metrics.values[0].text()
            shader_total = sum(e.size for e in window._storage if e.category == "Shader Cache")
            assert window.storage_metrics.values[2].text() == human_size(shader_total)
            assert shader_total == 3000 + 1000 + 700 + 600, shader_total
            assert sum(v for _, v, _ in window.storage_ring.segments) == total
            assert window.grab().save(str(args.output / "other-storage-results-1280.png"))

            # Details are evidence, never a safe-to-clear claim.
            window.storage_table.selectRow(row_of(window, "DirectX Shader Cache"))
            settle()
            text = " ".join(w.text() for w in window.storage_details.findChildren(QLabel))
            assert "Review only" in text and "Safe to Clear" not in text and "safe to clear" not in text.lower(), text
            window.storage_table.selectRow(row_of(window, "Skyrim"))
            settle()
            text = " ".join(w.text() for w in window.storage_details.findChildren(QLabel))
            assert "Protected" in text, text

            # Steam shader ownership is proven by an installed app ID only.
            related = {window.storage_table.item(i, 2).text() for i in range(window.storage_table.rowCount())}
            assert "Cyberpunk 2077" in related and "No installed game" in related, related
            open_tab(window, "By Game")
            assert window.storage_notice.text().startswith("Ownership is shown only"), window.storage_notice.text()
            ordered = [window.storage_table.item(i, 2).text() for i in range(window.storage_table.rowCount())]
            assert ordered.index("No installed game") > ordered.index("Cyberpunk 2077"), ordered

            # Category tabs fill from the scan.
            for tab, kind in (("Caches", "Caches"), ("Shader Cache", "Shader Cache"), ("Configs", "Config / Settings"),
                              ("Logs", "Logs / Reports"), ("Temporary", "Temporary Files")):
                open_tab(window, tab)
                assert names(window) and all(e.category == kind for e in window._shown_storage), (tab, names(window))
            open_tab(window, "Cleanup Assistant")
            assert set(names(window)) == {"Battle.net Cache", "Battle.net Logs", "Windows Crash Dumps"}, names(window)
            assert window.storage_notice.text() == oi.CLEANUP_NOTICE
            open_tab(window, "Storage Breakdown")

            # Category list, search, sort and density.
            window.storage_categories.setCurrentRow(1 + 1)
            settle()
            assert names(window) and all(e.category == "Shader Cache" for e in window._shown_storage), names(window)
            assert window.storage_categories.currentItem().data(Qt.UserRole) == "Shader Cache"
            window.storage_categories.setCurrentRow(0)
            settle()
            window.global_search.setText("nvidia")
            settle()
            assert names(window) == ["NVIDIA DirectX Cache"], names(window)
            window.global_search.clear()
            window.storage_sort.setCurrentText("Name (A–Z)")
            settle()
            assert names(window) == sorted(names(window), key=str.casefold)
            window.storage_sort.setCurrentText("Size (Largest)")
            window.storage_view_list.click()
            settle()
            assert window.storage_table.rowHeight(0) < 41
            window.storage_view_grid.click()
            settle()
            assert window.storage_table.rowHeight(0) == 41

            # Settings folders can be protected or reviewed, never cleared.
            check(window, "Skyrim")
            assert not window.storage_delete.isEnabled()
            assert "protected" in window.storage_delete.toolTip().lower(), window.storage_delete.toolTip()
            check(window, "Skyrim", False)
            check(window, "DirectX Shader Cache")
            assert not window.storage_delete.isEnabled() and "launcher cache and log" in window.storage_delete.toolTip()
            check(window, "DirectX Shader Cache", False)
            check(window, "Steam Temp")
            assert not window.storage_delete.isEnabled()
            check(window, "Steam Temp", False)
            assert window.storage_selection.text().startswith("0 selected")

            # Protect saves a Never Touch rule and moves nothing.
            check(window, "Windows Crash Dumps")
            assert window.storage_delete.isEnabled()
            window._protect_paths([r.path for r in window._selected_storage()], window._fill_storage)
            settle()
            assert any("CrashDumps" in str(rule) for rule in window.settings["never_touch"]), window.settings["never_touch"]
            assert not window.storage_delete.isEnabled(), "Protected folders cannot be cleared"
            check(window, "Windows Crash Dumps", False)
            assert dumps.exists()

            # Add to Graveyard refuses plain folders honestly.
            check(window, "DirectX Shader Cache")
            window._watch_storage()
            assert info.called
            check(window, "DirectX Shader Cache", False)

            # Delete: declined first, then approved into a disposable shell bin.
            check(window, "Battle.net Cache")
            check(window, "Battle.net Logs")
            assert window.storage_delete.isEnabled()
            window._review_storage()
            wait_for(lambda: not window.cleaning and not window.workers)
            assert confirm.called and all(p.exists() for p in cache_files + log_files), "Declined must change nothing"
            confirm.return_value = True
            with patch("gg_desktop.other_storage_actions.recycle_file", side_effect=fake_recycle), \
                 patch("gg_desktop.other_storage_actions.register_recycle", return_value="test"), \
                 patch("gg_desktop.other_storage_actions.log_event"):
                window._review_storage()
                wait_for(lambda: not window.cleaning and not window.workers)
            assert len(recycled) == 5, recycled
            for moved in cache_files + log_files:
                assert not moved.exists(), moved
            for survivor in (dumps, settings_file, owned, orphan, temp_file, local / "D3DSCache" / "d0.bin",
                             local / "NVIDIA" / "DXCache" / "n0.bin"):
                assert survivor.exists(), survivor
            assert "Battle.net Cache" not in names(window) and "Battle.net Logs" not in names(window), names(window)
            assert window.grab().save(str(args.output / "other-storage-cleared-1280.png"))

            # A rescan sees the same truth; the page survives leaving and narrower windows.
            window.storage_scan.click()
            wait_for(lambda: not state.busy and not window.workers)
            assert "Battle.net Cache" not in names(window)
            window.navigate("Overview")
            settle()
            window.navigate("Other Storage")
            settle()
            assert window.storage_table.rowCount() == 7, "The page forgot the last scan"
            for width, height in ((1280, 720), (1440, 900), (960, 650)):
                window.resize(width, height)
                settle()
                assert window.page.horizontalScrollBar().maximum() == 0, (width, height)
                assert window.grab().save(str(args.output / f"other-storage-page-{width}.png"))
            errors.assert_not_called()
            window.close()
            settle()
        after = tree_bytes(root)
        removed = {k for k in before if k not in after and not k.startswith("DisposableShell")}
        assert len(removed) == 5, removed
        assert all("Battle.net" in k for k in removed), removed
    print("PASS: Other Storage page: scan-only metrics and ring, evidence without safe-to-clear claims, proven Steam ownership, "
          "all tabs, filters, protection, settings never clearable, and a confirmed Recycle Bin move of exactly the checked launcher folders.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
