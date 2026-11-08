"""Qt-free checks for the read-only Mods views: statuses, load order, updates, coverage."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from gg_desktop.mod_conflicts import inspect_conflicts
from gg_desktop.mods_data import build_catalog
from gg_desktop import mods_insight as mi
from tests.test_mods_functionality import mo2_fixture


class InsightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="GG-insight-")
        self.root = Path(self.temp.name)
        self.inventory, self.storage, self.profiles, self.ini = mo2_fixture(self.root)
        self.catalog = build_catalog(self.inventory)

    def tearDown(self):
        self.temp.cleanup()

    def entry(self, folder):
        return next(e for e in self.catalog.entries if e.path == str(self.storage / folder))

    def test_status_uses_selected_profile_only(self):
        # Default (selected): Mountain +, Snow +, Framework -, Disabled -.  Separate: opposite for first three.
        self.assertEqual(mi.entry_status(self.entry("MountainTextures"), self.catalog).text, "Enabled")
        self.assertEqual(mi.entry_status(self.entry("Framework"), self.catalog).text, "Disabled")
        self.assertEqual(mi.entry_status(self.entry("Disabled"), self.catalog).text, "Disabled")

    def test_status_mixed_without_selected_profile(self):
        for p in self.catalog.profiles:
            object.__setattr__(p, "selected", False) if p.__dataclass_params__.frozen else setattr(p, "selected", False)
        self.assertEqual(mi.entry_status(self.entry("MountainTextures"), self.catalog).text, "Mixed")
        self.assertEqual(mi.entry_status(self.entry("Disabled"), self.catalog).text, "Disabled")

    def test_locations_stay_protected_and_unlisted_mod_unknown(self):
        location = next(e for e in self.catalog.entries if e.kind == "location")
        self.assertEqual(mi.entry_status(location, self.catalog).text, "Protected")
        loner = self.entry("Framework")
        loner.profiles.clear()
        self.assertEqual(mi.entry_status(loner, self.catalog).text, "Unknown")

    def test_version_compare_is_conservative(self):
        self.assertTrue(mi.compare_versions("1.0", "1.0.1"))
        self.assertTrue(mi.compare_versions("v1.9", "1.10"))
        self.assertFalse(mi.compare_versions("2.0", "2.0.0"))
        self.assertFalse(mi.compare_versions("2.1", "2.0"))
        self.assertIsNone(mi.compare_versions("1.0-beta", "1.0"))
        self.assertIsNone(mi.compare_versions("", "1.0"))

    def test_update_info_reads_only_manager_saved_fields(self):
        folder = self.storage / "MountainTextures"
        (folder / "meta.ini").write_text("[General]\nversion=2.0\nnewestVersion=2.5\n", encoding="utf-8")
        info = mi.read_update_info(self.entry("MountainTextures"))
        self.assertTrue(info.outdated)
        self.assertEqual(info.newest, "2.5")
        (folder / "meta.ini").write_text("[General]\nversion=2.0\nnewestVersion=2.5\nignoredVersion=2.5\n", encoding="utf-8")
        self.assertFalse(mi.read_update_info(self.entry("MountainTextures")).outdated)
        (folder / "meta.ini").write_text("[General]\nversion=2.0\n", encoding="utf-8")
        self.assertIsNone(mi.read_update_info(self.entry("MountainTextures")).outdated)
        self.assertIsNone(mi.read_update_info(self.entry("SnowTextures")))  # no meta.ini

    def test_outdated_metric_unknown_without_evidence(self):
        self.assertIsNone(mi.metrics(self.catalog, None, {})["outdated"])
        (self.storage / "SnowTextures" / "meta.ini").write_text("[General]\nversion=1.2\nnewestVersion=1.3\n")
        updates = mi.scan_updates(self.catalog.entries)
        self.assertEqual(mi.metrics(self.catalog, None, updates)["outdated"], 1)

    def test_load_order_is_relative_and_reversed(self):
        default = next(p for p in self.catalog.profiles if p.name == "Default")
        rows, note = mi.load_order(self.catalog, default.key)
        names = [e.name for _, e, _ in rows]
        # modlist.txt lists highest priority first; position 1 is the last line of the file.
        self.assertEqual(names, ["MissingFolder", "Disabled mod", "Framework", "Snow Textures", "Mountain Textures"])
        self.assertEqual([p for p, _, _ in rows], [1, 2, 3, 4, 5])
        self.assertIn("relative", note)

    def test_unreferenced_needs_complete_profiles(self):
        stray = self.storage / "Stray"
        stray.mkdir()
        (stray / "manifest.json").write_text(json.dumps({"name": "Stray"}))
        catalog = build_catalog(self.inventory)
        names = [e.name for e in mi.unreferenced(catalog)]
        self.assertEqual(names, ["Stray"])
        for p in catalog.profiles:
            p.incomplete = True
        self.assertEqual(mi.unreferenced(catalog), [])
        self.assertIsNone(mi.metrics(catalog, None, {})["unreferenced"])

    def test_conflict_rows_and_profile_counts(self):
        report = inspect_conflicts(self.catalog)
        rows = mi.conflict_rows(self.catalog, report)
        self.assertEqual(len(rows), len(report.findings))
        self.assertTrue(all(r["profile"] != "Unknown profile" for r in rows))
        self.assertIsNone(mi.conflict_rows(self.catalog, None) or None)
        counts = mi.profile_rows(self.catalog, report)
        self.assertEqual(sum(r["findings"] for r in counts), len(report.findings))
        self.assertTrue(all(r["findings"] is None for r in mi.profile_rows(self.catalog, None)))

    def test_export_selection_states_scope(self):
        report = inspect_conflicts(self.catalog)
        payload = mi.export_selection([self.entry("MountainTextures")], self.catalog, report, {})
        self.assertEqual(payload["count"], 1)
        self.assertIn("unverified", payload["scope"])
        self.assertTrue(payload["mods"][0]["findings"])
        json.loads(mi.dumps(payload))

    def test_cleanup_never_offers_removal_of_unreferenced(self):
        stray = self.storage / "Stray"
        stray.mkdir()
        catalog = build_catalog(self.inventory)
        rows = mi.cleanup_rows(catalog, self.inventory)
        stray_rows = [r for r in rows if r["source"] == "unreferenced"]
        self.assertTrue(stray_rows)
        self.assertFalse(any(r["removable"] for r in stray_rows))

    def test_source_rows_mark_custom_roots(self):
        rows = mi.source_rows(self.inventory, [str(self.root / "Extra")])
        self.assertEqual([r["custom"] for r in rows].count(True), 1)


if __name__ == "__main__":
    unittest.main()
