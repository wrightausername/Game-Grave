"""M2 Ghost Watch never asserts removals from incomplete filesystem coverage."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from game_intelligence import capture_mod_observation, compare_observations


def source(path: Path):
    return SimpleNamespace(path=str(path))


class GhostWatchCoverageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "Mods"
        self.root.mkdir()
        (self.root / "loaded.dll").write_bytes(b"mod bytes")

    def test_complete_scan_without_subdirectory_limits_is_not_partial(self):
        report = capture_mod_observation([source(self.root)])
        self.assertEqual(report["skipped_entries"], 0)
        self.assertFalse(report["truncated"])
        self.assertEqual(report["scan_errors"], 0)
        self.assertEqual(len(report["entries"]), 1)

    def test_linked_child_dir_makes_missing_comparison_uncertain(self):
        outside = Path(self.temp.name) / "Elsewhere"
        outside.mkdir()
        (outside / "not-ours.dll").write_bytes(b"private")
        link = self.root / "Shortcut"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Link creation unavailable on this runner")
        after = capture_mod_observation([source(self.root)])
        self.assertGreaterEqual(after["skipped_entries"], 1)
        self.assertTrue(after["truncated"])
        self.assertFalse(any("not-ours" in item for item in after["entries"]))
        before = {
            "schema": 1, "roots": after["roots"],
            "entries": {"missing-from-scan.dll": [1, 2]},
            "truncated": False,
        }
        comparison = compare_observations(before, after)
        removed = [change for change in comparison["changes"]
                   if "missing" in change["path"]]
        self.assertEqual(removed[0]["change"], "not observed (incomplete comparison)")
        self.assertTrue(comparison["unreliable_missing_inference"])

    def test_omitted_deep_subtree_marks_incomplete(self):
        deep = self.root / "A" / "B" / "C" / "D"
        deep.mkdir(parents=True)
        (deep / "mod.esp").write_bytes(b"unknown")
        report = capture_mod_observation([source(self.root)])
        self.assertTrue(report["truncated"])
        self.assertGreater(report["skipped_entries"], 0)
        self.assertFalse(any("mod.esp" in x for x in report["entries"]))

    def test_file_symlink_never_discovered_and_makes_partial(self):
        outside = Path(self.temp.name) / "outside"
        outside.write_bytes(b"secret")
        link = self.root / "linked.dll"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("Link creation unavailable")
        report = capture_mod_observation([source(self.root)])
        self.assertTrue(report["truncated"])
        self.assertGreater(report["skipped_entries"], 0)
        self.assertFalse(any("linked.dll" in x for x in report["entries"]))

    def test_walk_permission_error_marks_partial(self):
        original = __import__("game_intelligence").os.walk
        def interrupted_walk(*args, **kwargs):
            kwargs["onerror"](PermissionError("synthetic permission issue"))
            yield from original(*args, **kwargs)
        with patch("game_intelligence.os.walk", side_effect=interrupted_walk):
            report = capture_mod_observation([source(self.root)])
        self.assertEqual(report["scan_errors"], 1)
        self.assertTrue(report["truncated"])

    def test_capped_entries_never_misrepresent_removed_mods(self):
        (self.root / "another.esp").write_bytes(b"a")
        report = capture_mod_observation([source(self.root)], max_entries=1)
        self.assertTrue(report["truncated"])
        self.assertEqual(len(report["entries"]), 1)


if __name__ == "__main__":
    unittest.main()
