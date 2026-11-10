import json
import tempfile
import unittest
from pathlib import Path

from gg_desktop import bisect_store as store


class Store(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_round_trip_and_forget(self):
        self.assertIsNone(store.load(self.root, "p"))
        self.assertTrue(store.save(self.root, "p", {"answers": ["crash"]}))
        self.assertEqual(store.load(self.root, "p"), {"answers": ["crash"]})
        self.assertTrue(store.forget(self.root, "p"))
        self.assertIsNone(store.load(self.root, "p"))
        self.assertTrue(store.forget(self.root, "never-saved"))

    def test_damaged_oversized_or_wrong_shape_files_are_ignored(self):
        path = self.root / "bisect" / "runs.json"
        path.parent.mkdir()
        for text in ("{broken", "[1, 2]", json.dumps({"p": [1]}), "x" * (store.MAX_BYTES + 10)):
            path.write_text(text, encoding="utf-8")
            self.assertIsNone(store.load(self.root, "p"))
        self.assertTrue(store.save(self.root, "p", {"a": 1}))
        self.assertEqual(store.load(self.root, "p"), {"a": 1})

    def test_only_the_newest_runs_are_kept(self):
        for i in range(store.MAX_RUNS + 5):
            store.save(self.root, f"p{i}", {"i": i})
        runs = store.load_all(self.root)
        self.assertEqual(len(runs), store.MAX_RUNS)
        self.assertNotIn("p0", runs)
        self.assertIn(f"p{store.MAX_RUNS + 4}", runs)

    def test_too_big_to_store_returns_false_and_keeps_the_old_file(self):
        store.save(self.root, "p", {"a": 1})
        self.assertFalse(store.save(self.root, "q", {"x": "y" * store.MAX_BYTES}))
        self.assertEqual(store.load(self.root, "p"), {"a": 1})

    def test_no_temp_files_are_left(self):
        store.save(self.root, "p", {"a": 1})
        self.assertEqual([p.name for p in (self.root / "bisect").iterdir()], ["runs.json"])


if __name__ == "__main__":
    unittest.main()
