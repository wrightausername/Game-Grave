"""Evidence boundaries behind the second group of reference layouts."""
from dataclasses import replace
from types import SimpleNamespace
import unittest

from core import ModFolder, OldFile
from gg_desktop.backend import Inventory
from gg_desktop.insight_models import capture_items, capture_owner, dna_footprint, history_items, storage_items


class InsightModelTests(unittest.TestCase):
    def test_storage_does_not_double_count_nested_cache_records(self):
        parent = ModFolder("Shaders", "/library/shadercache/42", "", "Shader cache", (), 1000, 10, False, "Steam shader cache")
        child = replace(parent, name="Nested", path="/library/shadercache/42/subfolder", apparent_bytes=600)
        unrelated = OldFile("/downloads/report.log", 75, 0)
        inv = Inventory(mods=[child, parent], files=[unrelated])
        rows = storage_items(inv)
        self.assertEqual(sum(r.size for r in rows), 1075)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(not hasattr(r, "can_recycle") for r in rows))

    def test_capture_ownership_never_uses_a_game_title_in_filename(self):
        game = SimpleNamespace(library="/Steam", app_id="1091500", name="Cyberpunk 2077")
        self.assertEqual(capture_owner(OldFile("/downloads/Cyberpunk 2077.png", 10, 0), [game])[0], "Unverified")
        valid = OldFile("/Steam/userdata/123/760/remote/1091500/screenshots/clip.png", 10, 0)
        self.assertEqual(capture_owner(valid, [game])[0], "Cyberpunk 2077")
        spoof = replace(valid, path="/not-Steam/userdata/123/760/remote/1091500/screenshots/clip.png")
        self.assertEqual(capture_owner(spoof, [game])[0], "Unverified")

    def test_capture_inventory_deduplicates_paths(self):
        f = OldFile("/captures/game.png", 100, 0)
        self.assertEqual(len(capture_items(Inventory(screenshots=[f, f], recordings=[f]))), 1)

    def test_dna_keeps_nested_mod_bytes_inside_install_total(self):
        game = SimpleNamespace(install_path="/Games/Test", size_bytes=1000)
        assets = [{"path": "/Games/Test/mods", "apparent_bytes": 600},
                  {"path": "/Workshop/42", "apparent_bytes": 200},
                  {"path": "/Workshop/42/nested", "apparent_bytes": 100}]
        total, segments, external = dna_footprint(game, assets)
        self.assertEqual(total, 1200)
        self.assertEqual(sum(value for _, value, _ in segments), 1200)
        self.assertEqual(len(external), 1)
        game.size_bytes = None
        self.assertEqual(dna_footprint(game, [assets[0]])[:2], (0, []))

    def test_history_deduplicates_audit_events_by_recovery_id(self):
        records = [{"id": "exact-id", "path": "/Downloads/file.zip", "size": 50, "time": "2026-11-05T12:00:00Z"}]
        events = [{"kind": "Manual recycled", "recovery_id": "exact-id", "size_bytes": 50},
                  {"kind": "Cleanup finished", "details": "One recycled"},
                  {"kind": "Protection removed", "details": "Exact personal rule", "date": "2026-11-04"}]
        rows = history_items(records, events)
        self.assertEqual(len(rows), 2)
        self.assertEqual(sum(r.size or 0 for r in rows), 50)
        self.assertIsNone(rows[1].recovery_id)
        self.assertEqual(rows[0].state, "Not checked")


if __name__ == "__main__":
    unittest.main()
