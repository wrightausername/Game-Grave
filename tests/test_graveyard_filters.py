"""Pure Graveyard filters: unknown evidence stays unknown; protections stay intact."""
import unittest

from graveyard import GraveyardEntry
from gg_desktop.graveyard_filters import (
    AGE_OPTIONS, available_drives, evidence_drive, select_graveyard_entries,
)


def candidate(name, path, age, size, reviewable, kind="Archive"):
    return GraveyardEntry(
        key=name, name=name, path=path, category=kind,
        apparent_bytes=size, age_days=age, relationship="Unverified",
        finding="From scanned evidence", protection="Review required",
        can_recycle=reviewable,
    )


class GraveyardFilteringTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            candidate("Large", "C:/Games/large.zip", 900, 300, True),
            candidate("Small", "D:/Captures/old.mp4", 100, 10, False, "Recording"),
            candidate("Unknown", "C:/Games/live", None, 100, False, "Game"),
            candidate("Medium", "D:/Mods/mid.zip", 600, 200, True),
        ]

    def test_path_labels(self):
        self.assertEqual(available_drives(self.rows), ["C:", "D:"])
        self.assertEqual(evidence_drive("/home/user/game"), "/")
        self.assertEqual(evidence_drive("file.txt"), "Unknown drive")

    def test_numeric_sorts(self):
        self.assertEqual([r.name for r in select_graveyard_entries(
            self.rows, sort_by="Largest first")],
            ["Large", "Medium", "Unknown", "Small"])
        self.assertEqual([r.name for r in select_graveyard_entries(
            self.rows, sort_by="Smallest first")],
            ["Small", "Unknown", "Medium", "Large"])

    def test_unknown_age_at_end(self):
        self.assertEqual([r.name for r in select_graveyard_entries(
            self.rows, sort_by="Newest evidence first")],
            ["Small", "Medium", "Large", "Unknown"])
        self.assertEqual([r.name for r in select_graveyard_entries(
            self.rows, sort_by="Oldest evidence first")],
            ["Large", "Medium", "Small", "Unknown"])

    def test_combined_filters(self):
        match = select_graveyard_entries(
            self.rows, drive="D:", query="mod", category="Archive",
            state="Ready for review",
            min_age_days=AGE_OPTIONS["1+ year"])
        self.assertEqual([r.name for r in match], ["Medium"])
        self.assertEqual(select_graveyard_entries(
            self.rows, min_age_days=AGE_OPTIONS["3+ years"]), [])

    def test_protection_never_changes(self):
        before = [(r.key, r.can_recycle) for r in self.rows]
        result = select_graveyard_entries(
            self.rows, state="Protected / preview only")
        self.assertEqual({r.name for r in result}, {"Small", "Unknown"})
        self.assertTrue(all(not r.can_recycle for r in result))
        self.assertEqual([(r.key, r.can_recycle) for r in self.rows], before)


if __name__ == "__main__":
    unittest.main()
