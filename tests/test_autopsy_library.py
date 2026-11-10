import csv
import os
import tempfile
import time
import unittest
from pathlib import Path

from gg_desktop import autopsy_core as au
from gg_desktop import autopsy_library as lib


def write_capture(path, fps=60.0, seconds=30, spike=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = int(fps * seconds)
    with path.open("w", newline="") as handle:
        out = csv.writer(handle)
        out.writerow(["Application", "MsBetweenPresents"])
        for i in range(frames):
            out.writerow(["game.exe", 1000.0 / fps * (3 if spike and i % spike == 0 else 1)])
    return path


def stamp(i):
    return f"2024-05-{i + 1:02d}T101010"


class Capture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = self.root / "store"
        self.docs = self.root / "PresentMon"

    def tearDown(self):
        self.temp.cleanup()

    def make(self, name, age_days=0, **kw):
        path = write_capture(self.docs / name, **kw)
        stamp = time.time() - age_days * 86400
        os.utime(path, (stamp, stamp))
        return path


class Names(unittest.TestCase):
    def test_game_guess_drops_tool_words_and_dates(self):
        self.assertEqual(lib.guess_game("PresentMon-2024-05-02T213311-Cyberpunk2077.csv"), "Cyberpunk2077")
        self.assertEqual(lib.guess_game("FrameView_Hades_20240502_101010_Log.csv"), "Hades")
        self.assertEqual(lib.guess_game("20240502.csv"), "Unknown game")

    def test_default_roots_are_the_known_capture_tools(self):
        roots = [str(p).replace("\\", "/") for p in lib.default_roots(Path("/home/x"))]
        self.assertTrue(any(r.endswith("Documents/PresentMon") for r in roots))
        self.assertTrue(any(r.endswith("CapFrameX/Captures") for r in roots))


class Library(Capture):
    def test_new_captures_are_found_read_once_and_kept(self):
        self.make(f"PresentMon-Hades-{stamp(1)}.csv", age_days=2)
        self.make(f"PresentMon-Hades-{stamp(2)}.csv", age_days=1, fps=75)
        result = lib.refresh([self.docs], root=self.store)
        self.assertEqual(len(result.added), 2)
        again = lib.refresh([self.docs], root=self.store)
        self.assertEqual(again.added, [])
        before, after = lib.pair_for(lib.load(self.store))
        self.assertLess(before.mtime, after.mtime)
        comparison = au.compare(before.stats_obj(), after.stats_obj())
        self.assertTrue(comparison.comparable)
        self.assertIn("better", lib.headline(comparison))

    def test_only_ten_are_kept_and_the_oldest_is_replaced_but_never_deleted_from_disk(self):
        paths = [self.make(f"PresentMon-Hades-{stamp(i)}.csv", age_days=20 - i, seconds=12) for i in range(12)]
        for _ in range(8):
            lib.refresh([self.docs], root=self.store, limit=2)
        kept = lib.load(self.store)
        self.assertEqual(len(kept), 10)
        self.assertEqual(kept[0].name, f"PresentMon-Hades-{stamp(11)}.csv")
        self.assertNotIn(f"PresentMon-Hades-{stamp(0)}.csv", [e.name for e in kept])
        self.assertTrue(all(p.exists() for p in paths), "the owner's capture files are never removed")

    def test_a_pass_reads_at_most_two_and_skips_big_old_tiny_and_non_captures(self):
        for i in range(5):
            self.make(f"PresentMon-A-{stamp(i)}.csv", age_days=i, seconds=12)
        self.make("old.csv", age_days=400, seconds=12)
        (self.docs / "tiny.csv").write_text("MsBetweenPresents\n16\n")
        (self.docs / "notes.txt").write_text("x" * 100000)
        result = lib.refresh([self.docs], root=self.store)
        self.assertEqual(len(result.added), 2)
        self.assertEqual([e.name for e in result.added], [f"PresentMon-A-{stamp(0)}.csv", f"PresentMon-A-{stamp(1)}.csv"])
        big = lib.refresh([self.docs], root=self.store, max_bytes=1000)
        self.assertTrue(any("bigger than" in n for n in big.notes))

    def test_a_file_that_is_not_a_capture_becomes_a_note_not_a_crash(self):
        bad = self.docs / "PresentMon-Bad.csv"
        bad.parent.mkdir(parents=True)
        bad.write_text("a,b\n" + "1,2\n" * 30000)
        result = lib.refresh([self.docs], root=self.store)
        self.assertEqual(result.added, [])
        self.assertTrue(any("Skipped PresentMon-Bad.csv" in n for n in result.notes))

    def test_pairs_use_the_game_of_the_newest_capture(self):
        self.make(f"PresentMon-Hades-{stamp(1)}.csv", age_days=5, seconds=12)
        self.make(f"PresentMon-Doom-{stamp(1)}.csv", age_days=3, seconds=12)
        self.make(f"PresentMon-Hades-{stamp(2)}.csv", age_days=2, seconds=12)
        self.make(f"PresentMon-Doom-{stamp(2)}.csv", age_days=1, seconds=12)
        lib.refresh([self.docs], root=self.store, limit=10)
        before, after = lib.pair_for(lib.load(self.store))
        self.assertEqual((before.game, after.game), ("Doom", "Doom"))
        self.assertEqual(lib.pair_for(lib.load(self.store)[:1]), (None, None))

    def test_a_stray_capture_of_another_game_does_not_hide_a_possible_comparison(self):
        self.make(f"PresentMon-Hades-{stamp(1)}.csv", age_days=3, seconds=12)
        self.make(f"PresentMon-Hades-{stamp(2)}.csv", age_days=2, seconds=12)
        self.make(f"PresentMon-Doom-{stamp(3)}.csv", age_days=0, seconds=12)
        lib.refresh([self.docs], root=self.store, limit=10)
        before, after = lib.pair_for(lib.load(self.store))
        self.assertEqual((before.game, after.game), ("Hades", "Hades"))

    def test_add_by_hand_counts_toward_the_ten(self):
        path = self.make(f"PresentMon-Hand-{stamp(1)}.csv", seconds=12)
        entry, dropped = lib.add_by_hand(path, root=self.store)
        self.assertEqual(dropped, [])
        self.assertEqual([e.id for e in lib.load(self.store)], [entry.id])

    def test_a_damaged_library_loads_as_empty(self):
        self.store.mkdir()
        (self.store / "library.json").write_text("{not json")
        self.assertEqual(lib.load(self.store), [])

    def test_passes_are_spaced_out(self):
        self.assertTrue(lib.due(None))
        self.assertFalse(lib.due(100.0, 100.0 + 60))
        self.assertTrue(lib.due(100.0, 100.0 + lib.MIN_GAP_SECONDS))


if __name__ == "__main__":
    unittest.main()
