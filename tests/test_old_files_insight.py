"""Qt-free checks for Old Files classification, evidence, tabs and folder groups."""
from __future__ import annotations

import time
import unittest

from core import OldFile
from gg_desktop import old_files_insight as oi
from gg_desktop.old_files_data import ScanPlan, ScanResult

DAY = 86400


def make(path, size=100, days=400, links=1):
    return OldFile(path, size, time.time() - days * DAY, 1, 1, 1, links)


class InsightTests(unittest.TestCase):
    def setUp(self):
        self.root = "/data/user"
        self.files = [
            make("/data/user/Downloads/Nexus/skyrim-texture-pack-mod.zip", 700),
            make("/data/user/Downloads/setup.exe", 300),
            make("/data/user/Downloads/notes.txt", 5),
            make("/data/user/Documents/Cache/blob.bin", 50),
            make("/data/user/Documents/crash.log", 20),
            make("/data/user/Documents/clip.mp4", 2 * 1024 ** 3),
            make("/data/user/Documents/Reports/a.pdf", 10),
            make("/data/user/Documents/Reports/b.pdf", 10),
        ]
        plan = ScanPlan(self.root, "folder", 365, (self.root,), (1, 1), ())
        self.result = ScanResult(plan, list(self.files))
        self.entries = [(f, oi.classify(f.path)) for f in self.files]

    def pills(self):
        return {f.path.rsplit("/", 1)[-1]: i.pill for f, i in self.entries}

    def test_classification_uses_extension_then_path_evidence(self):
        p = self.pills()
        self.assertEqual(p["skyrim-texture-pack-mod.zip"], "Game")
        self.assertEqual(p["setup.exe"], "Installer")
        self.assertEqual(p["notes.txt"], "Downloads")
        self.assertEqual(p["blob.bin"], "Cache")
        self.assertEqual(p["crash.log"], "Logs")
        self.assertEqual(p["clip.mp4"], "Media")
        self.assertEqual(p["a.pdf"], "Other")

    def test_filter_groups_cover_every_pill(self):
        for pill, group in oi.GROUP_OF.items():
            self.assertIn(group, oi.FILTER_GROUPS)

    def test_metrics_count_only_established_facts(self):
        m = oi.metrics(self.entries)
        self.assertEqual(m["total"], 8)
        self.assertEqual(m["possible_game"], 1)
        self.assertEqual(m["downloads_archives"], 1)  # notes.txt; the game-like zip is counted once, as game
        self.assertEqual(m["other"], 6)
        self.assertGreaterEqual(m["oldest_days"], 400)

    def test_tabs(self):
        rows, note = oi.tab_entries("Downloads", self.entries)
        self.assertEqual(len(rows), 3)
        rows, _ = oi.tab_entries("Large Files", self.entries)
        self.assertEqual([f.path.rsplit("/", 1)[-1] for f, _ in rows], ["clip.mp4"])
        rows, note = oi.tab_entries("Unused Installers", self.entries)
        self.assertEqual(len(rows), 1)
        self.assertIn("cannot establish", note)
        rows, note = oi.tab_entries("By Game", self.entries)
        self.assertEqual(len(rows), 1)
        self.assertIn("not verified", note)

    def test_filter_and_sort(self):
        rows = oi.filter_entries(self.entries, groups={"Other"}, min_days=0)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0][0].path.rsplit("/", 1)[-1], "clip.mp4")
        none = oi.filter_entries(self.entries, groups=set())
        self.assertEqual(none, [])
        young = oi.filter_entries(self.entries, groups=set(oi.FILTER_GROUPS), min_days=1000)
        self.assertEqual(young, [])
        by_query = oi.filter_entries(self.entries, groups=set(oi.FILTER_GROUPS), query="crash")
        self.assertEqual(len(by_query), 1)

    def test_evidence_never_claims_safety(self):
        f, info = self.entries[0]
        lines = oi.evidence(f, info, self.result, ())
        text = " ".join(t for t, _ in lines).casefold()
        self.assertNotIn("safe", text)
        self.assertNotIn("unused", text)
        self.assertTrue(any("Last modified" in t for t, _ in lines))
        protected = oi.evidence(f, info, self.result, ("/data/user/Downloads",))
        self.assertFalse(protected[-1][1])

    def test_folder_groups_are_review_only_and_bounded(self):
        groups = oi.group_folders(self.entries, [self.root])
        names = {g.name for g in groups}
        self.assertIn("Downloads", names)
        self.assertIn("Documents", names)
        docs = next(g for g in groups if g.name == "Documents")
        self.assertEqual(docs.count, 5)
        self.assertEqual(docs.pill, "Media")
        self.assertTrue(docs.selectable)
        big = [(make(f"/data/user/Big/f{i}.bin"), oi.classify("x.bin")) for i in range(201)]
        self.assertFalse(oi.group_folders(big, [self.root])[0].selectable)

    def test_age_label(self):
        self.assertEqual(oi.age_label(21), "21 days ago")
        self.assertEqual(oi.age_label(120), "4 months ago")
        self.assertEqual(oi.age_label(400), "1 year ago")
        self.assertEqual(oi.age_label(800), "2 years ago")


if __name__ == "__main__":
    unittest.main()
