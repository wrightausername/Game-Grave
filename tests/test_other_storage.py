"""Other Storage: read-only discovery, honest categories and the verified-only cleanup rule."""
from __future__ import annotations

from pathlib import Path
import os
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from gg_desktop import other_storage_data as data
from gg_desktop import other_storage_insight as insight
from gg_desktop.insight_models import STORAGE_TYPES, StorageItem


def make(path, size=10, age=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    moment = time.time() - age * 86400
    os.utime(path, (moment, moment))
    return path


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="GG-other-storage-")
        self.root = Path(self.temp.name)
        self.home = self.root / "Home"
        self.local = self.root / "Local"
        self.data = self.root / "ProgramData"
        self.env = {"LOCALAPPDATA": str(self.local), "PROGRAMDATA": str(self.data), "USERPROFILE": str(self.home)}
        self.library = self.root / "SteamLibrary"
        self.steam = self.root / "Steam"

    def tearDown(self):
        self.temp.cleanup()

    def scan(self, **kwargs):
        return data.discover(env=self.env, home=self.home, steam_roots=[self.steam], libraries=[self.library], **kwargs)


class DiscoveryTests(Fixture):
    def test_only_existing_locations_with_files_appear(self):
        make(self.local / "D3DSCache" / "a.bin", 100)
        make(self.local / "NVIDIA" / "DXCache" / "b.bin", 300)
        (self.local / "AMD" / "DxCache").mkdir(parents=True)  # empty folder is not reported
        report = self.scan()
        names = {e.name: e for e in report.entries}
        self.assertEqual(set(names), {"DirectX Shader Cache", "NVIDIA DirectX Cache"})
        self.assertEqual(names["NVIDIA DirectX Cache"].size, 300)
        self.assertEqual(names["NVIDIA DirectX Cache"].items, 1)
        self.assertEqual([e.name for e in report.entries], ["NVIDIA DirectX Cache", "DirectX Shader Cache"])
        self.assertTrue(report.checked > 10)

    def test_categories_and_kinds(self):
        make(self.local / "D3DSCache" / "a.bin")
        make(self.local / "Battle.net" / "Cache" / "c.dat")
        make(self.local / "CrashDumps" / "game.exe.123.dmp")
        make(self.home / "Documents" / "My Games" / "Skyrim" / "Skyrim.ini")
        make(self.library / "steamapps" / "temp" / "t.tmp")
        make(self.steam / "logs" / "bootstrap.txt")
        report = self.scan()
        kinds = {e.name: (e.category, e.kind, e.badge) for e in report.entries}
        self.assertEqual(kinds["DirectX Shader Cache"], ("Shader Cache", "review", "Review only"))
        self.assertEqual(kinds["Battle.net Cache"][0], "Caches")
        self.assertEqual(kinds["Windows Crash Dumps"][0], "Logs / Reports")
        self.assertEqual(kinds["Skyrim"], ("Config / Settings", "settings", "Protected"))
        self.assertEqual(kinds["Steam Temp"][0], "Temporary Files")
        self.assertEqual(kinds["Steam Logs"][0], "Logs / Reports")
        self.assertTrue(all(c in STORAGE_TYPES for c, _, _ in kinds.values()))

    def test_wildcard_and_children_locations(self):
        make(self.local / "EpicGamesLauncher" / "Saved" / "webcache_4147" / "x.bin", 7)
        make(self.local / "EpicGamesLauncher" / "Saved" / "webcache_4430" / "y.bin", 9)
        make(self.home / "Saved Games" / "Game A" / "save1")
        make(self.home / "Saved Games" / "Game B" / "save1")
        report = self.scan()
        names = sorted(e.name for e in report.entries)
        self.assertEqual(names, ["Game A", "Game B", "webcache_4147", "webcache_4430"])

    def test_steam_shader_cache_ownership_is_proven_by_installed_app_id(self):
        make(self.library / "steamapps" / "shadercache" / "1091500" / "a.bin", 50)
        make(self.library / "steamapps" / "shadercache" / "999999" / "b.bin", 70)
        game = SimpleNamespace(app_id="1091500", name="Cyberpunk 2077")
        report = self.scan(games=[game])
        by_name = {e.name: e for e in report.entries}
        known = by_name["Cyberpunk 2077 Shader Cache"]
        self.assertEqual((known.related, known.app_id, known.kind, known.badge), ("Cyberpunk 2077", "1091500", "steam-shader", "Review only"))
        self.assertFalse(known.cleanable, "steamapps is protected by Game Grave's core rules")
        orphan = by_name["Steam app 999999 Shader Cache"]
        self.assertEqual((orphan.related, orphan.app_id, orphan.kind), ("No installed game", "", "steam-shader"))
        self.assertFalse(orphan.cleanable)
        self.assertIn("No installed game", orphan.evidence)

    def test_links_are_never_entered(self):
        outside = make(self.root / "Outside" / "secret.bin", 1000)
        cache = self.local / "D3DSCache"
        make(cache / "real.bin", 5)
        try:
            os.symlink(outside.parent, cache / "linked", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks need privileges on this machine")
        report = self.scan()
        entry = next(e for e in report.entries if e.name == "DirectX Shader Cache")
        self.assertEqual((entry.size, entry.items), (5, 1))

    def test_a_linked_location_is_not_measured(self):
        target = self.root / "Elsewhere"
        make(target / "x.bin", 500)
        self.local.mkdir(parents=True)
        try:
            os.symlink(target, self.local / "D3DSCache", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks need privileges on this machine")
        self.assertFalse([e for e in self.scan().entries if e.name == "DirectX Shader Cache"])

    def test_large_folders_report_partial_and_scans_can_cancel(self):
        for i in range(30):
            make(self.local / "D3DSCache" / f"{i}.bin", 1)
        with patch.object(data, "MAX_ENTRIES", 10):
            report = self.scan()
        entry = next(e for e in report.entries if e.name == "DirectX Shader Cache")
        self.assertTrue(entry.partial and report.partial)
        with self.assertRaises(InterruptedError):
            self.scan(canceled=lambda: True)

    def test_discovery_changes_nothing(self):
        files = [make(self.local / "D3DSCache" / "a.bin", 100, age=3), make(self.local / "NVIDIA" / "DXCache" / "b.bin", 5)]
        before = {str(p): (p.stat().st_size, p.stat().st_mtime_ns, p.read_bytes()) for p in files}
        self.scan()
        after = {str(p): (p.stat().st_size, p.stat().st_mtime_ns, p.read_bytes()) for p in files}
        self.assertEqual(before, after)


class MergeTests(Fixture):
    def item(self, path, category="Logs / Reports", old=None):
        return StorageItem(data.path_key(path), Path(path).name, str(path), category, 40, 1, "Selected file folder", "evidence", old)

    def test_inventory_entries_fill_gaps_without_double_counting(self):
        make(self.local / "CrashDumps" / "a.dmp", 30)
        scanned = self.scan().entries
        inside = self.item(self.local / "CrashDumps" / "a.dmp")
        outside = self.item(self.root / "Elsewhere" / "game.log", old=SimpleNamespace(modified=1.0))
        merged = data.merge(scanned, data.from_inventory([inside, outside]))
        self.assertEqual([e.name for e in merged if e.old_file is None], [e.name for e in scanned])
        loose = [e for e in merged if e.name == "game.log"]
        self.assertEqual(len(loose), 1)
        self.assertFalse(loose[0].cleanable)
        self.assertEqual(loose[0].badge, "Review only")
        self.assertEqual(len(merged), len(scanned) + 1)


class InsightTests(Fixture):
    def entries(self):
        make(self.local / "D3DSCache" / "a.bin", 600)
        make(self.local / "NVIDIA" / "DXCache" / "b.bin", 200)
        make(self.local / "Battle.net" / "Cache" / "c.dat", 150)
        make(self.local / "CrashDumps" / "d.dmp", 50)
        make(self.library / "steamapps" / "shadercache" / "1" / "e.bin", 900)
        return self.scan(games=[SimpleNamespace(app_id="1", name="Game One")]).entries


    def test_totals_shares_and_tabs(self):
        entries = self.entries()
        totals = insight.totals(entries)
        self.assertEqual(totals["Shader Cache"], 600 + 200 + 900)
        self.assertEqual(totals["Caches"], 150)
        shares = {k: p for k, _, p in insight.shares(entries)}
        self.assertEqual(shares["Shader Cache"], f"{1700 * 100 / 1900:.1f}%")
        self.assertEqual(shares["Other"], "0.0%")
        rows, notice = insight.tab_rows("Cleanup Assistant", entries)
        self.assertEqual([e.name for e in rows], ["Battle.net Cache", "Windows Crash Dumps"])
        self.assertIn("review only", notice)
        rows, _ = insight.tab_rows("Shader Cache", entries)
        self.assertEqual(len(rows), 3)
        rows, notice = insight.tab_rows("By Game", entries)
        self.assertEqual(rows[0].related, "Battle.net")
        self.assertIn("proves", notice)
        self.assertEqual(len(insight.tab_rows("Storage Breakdown", entries)[0]), len(entries))

    def test_filter_and_sort(self):
        entries = self.entries()
        rows = insight.filter_rows(entries, category="Shader Cache", sort="Size (Largest)")
        self.assertEqual([e.size for e in rows], sorted((e.size for e in rows), reverse=True))
        self.assertEqual([e.name for e in insight.filter_rows(entries, query="nvidia")], ["NVIDIA DirectX Cache"])
        self.assertEqual([e.name for e in insight.filter_rows(entries, query="game one")], ["Game One Shader Cache"])
        names = [e.name for e in insight.filter_rows(entries, sort="Name (A–Z)")]
        self.assertEqual(names, sorted(names, key=str.casefold))

    def test_delete_is_enabled_only_for_verified_shader_caches(self):
        entries = self.entries()
        cache = next(e for e in entries if e.cleanable)
        driver = next(e for e in entries if e.name == "DirectX Shader Cache")
        steam = next(e for e in entries if e.name == "Game One Shader Cache")
        self.assertTrue(insight.selection_state([cache], False)[0])
        self.assertFalse(insight.selection_state([], False)[0])
        self.assertFalse(insight.selection_state([cache, driver], False)[0])
        self.assertFalse(insight.selection_state([steam], False)[0])
        self.assertFalse(insight.selection_state([cache], True)[0])
        for i in range(data.MAX_FILES):
            make(self.local / "Ubisoft Game Launcher" / "cache" / f"{i}.bin", 1)
        big = next(e for e in self.scan().entries if e.name == "Ubisoft Connect Cache")
        make(self.local / "Ubisoft Game Launcher" / "cache" / "extra.bin", 1)
        too_big = next(e for e in self.scan().entries if e.name == "Ubisoft Connect Cache")
        self.assertTrue(big.cleanable and not too_big.cleanable)
        self.assertFalse(insight.selection_state([big, cache], False)[0], "combined files above the cap")
        make(self.home / "Documents" / "My Games" / "Save" / "s.sav")
        settings = next(e for e in self.scan().entries if e.protected_kind)
        self.assertFalse(insight.selection_state([settings], False)[0])
        self.assertIn("never removed", insight.selection_state([settings], False)[1])

    def test_notes_never_claim_safety(self):
        for text in (data.DRIVER_NOTE, data.LAUNCHER_NOTE, data.LOG_NOTE, data.SETTINGS_NOTE, data.STAGING_NOTE,
                     data.SHADER_NOTE, data.LOOSE_NOTE, insight.CLEANUP_NOTICE, insight.BY_GAME_NOTICE):
            self.assertNotIn("safe to clear", text.casefold())
            self.assertNotIn("safe to remove", text.casefold())
            self.assertNotIn("safe to delete", text.casefold())


class CleanupTests(Fixture):
    def entry(self, relative, files):
        for name, size in files.items():
            make(self.local / relative / name, size)
        return next(e for e in self.scan().entries if Path(e.path) == self.local / relative)

    def test_only_verified_files_in_the_scanned_folder_move(self):
        from gg_desktop import other_storage_actions as actions
        cache = self.entry("Battle.net/Cache", {"a.dat": 3, "sub/b.dat": 4})
        outside = make(self.local / "Battle.net" / "keep.txt", 9)
        driver = make(self.local / "D3DSCache" / "d.bin", 5)
        found = actions.inspect([cache])
        entry, plan, reason = found[0]
        self.assertEqual((reason, len(plan.files), plan.size), ("", 2, 7))
        bin_dir = self.root / "Bin"
        bin_dir.mkdir()
        moved = []
        def fake_recycle(path):
            moved.append(Path(path).name)
            os.replace(path, bin_dir / Path(path).name)
        with patch.object(actions, "recycle_file", side_effect=fake_recycle), \
             patch.object(actions, "register_recycle", return_value="r1"), patch.object(actions, "log_event"):
            outcome = actions.recycle([plan], [], "session-1")
        self.assertEqual((outcome["completed"], outcome["skipped"], outcome["requested"]), (2, [], 2))
        self.assertEqual(sorted(moved), ["a.dat", "b.dat"])
        self.assertTrue(outside.exists() and driver.exists(), "Nothing outside the verified folder may be touched")

    def test_changed_protected_and_oversized_runs_are_skipped_or_refused(self):
        from gg_desktop import other_storage_actions as actions
        cache = self.entry("Battle.net/Cache", {"a.dat": 3, "b.dat": 4})
        _, plan, _ = actions.inspect([cache])[0]
        (self.local / "Battle.net" / "Cache" / "b.dat").write_bytes(b"changed after the scan")
        keep = str(self.local / "Battle.net" / "Cache" / "a.dat")
        with patch.object(actions, "recycle_file") as recycle, patch.object(actions, "register_recycle", return_value="r"), \
             patch.object(actions, "log_event"):
            outcome = actions.recycle([plan], [keep], "session-2")
        recycle.assert_not_called()
        self.assertEqual(outcome["completed"], 0)
        self.assertEqual(len(outcome["skipped"]), 2)
        self.assertTrue((self.local / "Battle.net" / "Cache" / "a.dat").exists())
        big = actions.Plan(cache, plan.root, plan.files * (data.MAX_FILES), 0)
        with patch.object(actions, "recycle_file") as recycle:
            with self.assertRaises(ValueError):
                actions.recycle([big], [], "session-3")
        recycle.assert_not_called()

    def test_ineligible_entries_are_refused_before_anything_moves(self):
        from gg_desktop import other_storage_actions as actions
        make(self.local / "D3DSCache" / "d.bin", 5)
        make(self.home / "Documents" / "My Games" / "Game" / "s.sav", 5)
        make(self.library / "steamapps" / "shadercache" / "123" / "a.bin", 3)
        entries = self.scan(games=[SimpleNamespace(app_id="123", name="G")]).entries
        for entry in entries:
            _, plan, reason = actions.inspect([entry])[0]
            self.assertIsNone(plan, entry.name)
            self.assertIn("launcher cache or log folder", reason)

    def test_a_folder_that_becomes_a_link_is_refused(self):
        from gg_desktop import other_storage_actions as actions
        cache = self.entry("Battle.net/Cache", {"a.dat": 3})
        target = self.root / "Elsewhere"
        make(target / "x.bin", 5)
        import shutil
        shutil.rmtree(self.local / "Battle.net" / "Cache")
        try:
            os.symlink(target, self.local / "Battle.net" / "Cache", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks need privileges on this machine")
        entry, plan, reason = actions.inspect([cache])[0]
        self.assertIsNone(plan)
        self.assertTrue(reason)
        self.assertTrue((target / "x.bin").exists())


if __name__ == "__main__":
    unittest.main()
