"""Scan results stay until the owner scans again, with the time they were taken."""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core import ModFolder, OldFile, SteamGame
from gg_desktop import scan_cache as cache
from gg_desktop.backend import Inventory
from gg_desktop.models import merge_games
from gg_desktop.old_files_data import ScanPlan, ScanResult
from gg_desktop.other_storage_data import StorageEntry, StorageReport


class ScanCacheTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        os.environ.pop("GAME_GRAVE_SCAN_CACHE", None)

    def inventory(self):
        steam = [SteamGame("1", "Starfield", "C:\\Steam", "C:\\Steam\\common\\Starfield", 120, 1700000000.0, "Steam")]
        mods = [ModFolder("Texture Pack", "C:\\mods\\tex", "C:\\Steam", "Mod folder", ("a", "b"), 2, 4, False,
                          "Steam game folder", "Review manually")]
        files = [OldFile(str(self.base / "kept.log"), 5, 1.0, hardlinks=1), OldFile(str(self.base / "gone.log"), 5, 1.0)]
        (self.base / "kept.log").write_text("x")
        return Inventory(steam=steam, games=merge_games(steam, []), mods=mods, files=files, scanned_at="2026-11-14 17:40",
                         warnings=["one source was busy"])

    def test_round_trip_keeps_every_record(self):
        inv = self.inventory()
        self.assertTrue(cache.keep("inventory", inv, self.base))
        report = StorageReport([StorageEntry("k", "Shader cache", "C:\\x", "Cache", "", 10, 2, None, False, "s", "e", "n")],
                               scanned_at=1700000000.0, checked=3)
        self.assertTrue(cache.keep("storage", report, self.base))
        back = cache.read_all(self.base)
        got, saved = back["inventory"]
        self.assertGreater(saved, 0)
        self.assertEqual(got.steam, inv.steam)
        self.assertEqual(got.games, inv.games)
        self.assertEqual(got.mods[0].files if hasattr(got.mods[0], "files") else got.mods, inv.mods[0].files
                         if hasattr(inv.mods[0], "files") else inv.mods)
        self.assertIsInstance(got.mods[0], ModFolder)
        self.assertEqual(got.files, inv.files)
        self.assertEqual(got.scanned_at, "2026-11-14 17:40")
        self.assertEqual(back["storage"][0].entries[0].name, "Shader cache")
        # Writing one slot keeps the others.
        cache.keep("storage", StorageReport(scanned_at=5.0), self.base)
        self.assertEqual(cache.read_all(self.base)["inventory"][0].steam, inv.steam)

    def test_only_game_grave_records_and_damage_is_harmless(self):
        with self.assertRaises(TypeError):
            cache.encode(SimpleNamespace(a=1))
        path = cache.cache_path(self.base)
        path.write_text(json.dumps({"version": 1, "inventory": {"data": {"__t": "os.system", "v": {"command": "x"}}},
                                    "storage": {"data": {"__t": "gg_desktop.other_storage_data.StorageReport",
                                                         "v": {"scanned_at": 3.0}}}}))
        back = cache.read_all(self.base)
        self.assertNotIn("inventory", back)
        self.assertEqual(back["storage"][0].scanned_at, 3.0)
        path.write_text("not json")
        self.assertEqual(cache.read_all(self.base), {})
        path.write_text(json.dumps({"version": 99}))
        self.assertEqual(cache.read_all(self.base), {})

    def test_restore_puts_results_back_and_drops_files_that_are_gone(self):
        inv = self.inventory()
        cache.keep("inventory", inv, self.base)
        plan = ScanPlan("C:\\Downloads", "folder", 180, ("C:\\Downloads",), (1, 2), ())
        cache.keep("old_files", ScanResult(plan, files=list(inv.files), scanned_at=1700000000.0), self.base)
        window = SimpleNamespace(inventory=Inventory(), settings={})
        stand_in = SimpleNamespace(OldFilesSession=lambda w: SimpleNamespace(result=None, message=""))
        with patch.dict(sys.modules, {"gg_desktop.old_files": stand_in}):
            back = cache.restore(window, self.base)
        self.assertEqual(back, ["inventory", "old_files"])
        self.assertEqual([Path(f.path).name for f in window.inventory.files], ["kept.log"])
        self.assertEqual([Path(f.path).name for f in window._old_files_session.result.files], ["kept.log"])
        os.environ["GAME_GRAVE_SCAN_CACHE"] = "0"
        try:
            self.assertEqual(cache.restore(SimpleNamespace(inventory=Inventory(), settings={}), self.base), [])
            self.assertIsNone(cache.keep_async("inventory", inv, self.base))
        finally:
            os.environ.pop("GAME_GRAVE_SCAN_CACHE")

    def test_scan_time_words(self):
        now = datetime(2026, 11, 14, 18, 0)
        self.assertEqual(cache.when_text("2026-11-14 17:40", now), "Today 5:40 PM")
        self.assertEqual(cache.when_text(datetime(2026, 11, 13, 9, 5).timestamp(), now), "Yesterday 9:05 AM")
        self.assertEqual(cache.when_text(datetime(2026, 11, 3, 20, 0), now), "Tue 3 Nov, 8:00 PM")
        self.assertEqual(cache.when_text(datetime(2025, 1, 2, 8, 0), now), "2 Jan 2025, 8:00 AM")
        self.assertEqual(cache.when_text("", now), "")
        self.assertEqual(cache.label_for("Overview", "2026-11-14 17:40", {}, now), "Last scan Today 5:40 PM")
        self.assertEqual(cache.label_for("Games", "", {}, now), "Not scanned yet")
        self.assertEqual(cache.label_for("Other Storage", "2026-11-14 17:40", {}, now), "Not scanned yet")
        self.assertEqual(cache.label_for("Captures", "", {"captures": datetime(2026, 11, 14, 9, 0).timestamp()}, now),
                         "Scanned Today 9:00 AM")
        self.assertEqual(cache.label_for("Old Files", "2026-11-14 17:40", {}, now), "Last scan Today 5:40 PM")
        self.assertEqual(cache.label_for("Graveyard", "2026-11-14 17:40", {"grave": datetime(2026, 11, 14, 12).timestamp()},
                                         now), "Leftovers scanned Today 12:00 PM")


if __name__ == "__main__":
    unittest.main()
