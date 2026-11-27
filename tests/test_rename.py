"""Batch Rename engine: naming, conflict checks, transactions, crash recovery and undo, on real temp folders."""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from gg_desktop import rename_core as rc

NOW = time.mktime((2026, 11, 27, 9, 0, 0, 0, 0, -1))


class Folder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name) / "files"
        self.dir.mkdir()
        self.store_dir = Path(self.tmp.name) / "store"

    def make(self, *names, folder=None):
        folder = Path(folder or self.dir)
        items = []
        for i, n in enumerate(names):
            p = folder / n
            p.write_text("content of " + n, encoding="utf-8")
            items.append(rc.Item(str(p), False, NOW + i * 60))
        return items

    def names(self, folder=None):
        return sorted(os.listdir(folder or self.dir))

    def read(self, name):
        return (self.dir / name).read_text(encoding="utf-8")


class Naming(unittest.TestCase):
    def test_typing_ww_gives_ww_01_02_03_and_keeps_extensions(self):
        o = rc.Options(base_name="WW")
        items = [rc.Item("/x/a.png"), rc.Item("/x/b.PNG"), rc.Item("/x/c.jpeg")]
        got = [rc.new_name(it, i, 3, o, NOW) for i, it in enumerate(items)]
        self.assertEqual(got, ["WW_01.png", "WW_02.PNG", "WW_03.jpeg"])

    def test_padding_grows_with_the_batch(self):
        self.assertEqual(rc.number(0, 150, rc.Options()), "001")
        self.assertEqual(rc.number(2, 10, rc.Options(start=7, padding=4)), "0009")
        self.assertEqual(rc.number(0, 1, rc.Options(start=0, padding=1)), "0")

    def test_advanced_options(self):
        o = rc.Options(find="img", replace="Shot", prefix="GG-", suffix="-final", remove="#", case=rc.CASE_UPPER)
        self.assertEqual(rc.new_name(rc.Item("/x/IMG#cool.png"), 0, 1, o, NOW), "GG-SHOTCOOL-final.png")
        o = rc.Options(base_name="trip", date=rc.DATE_TODAY, separator="-")
        self.assertEqual(rc.new_name(rc.Item("/x/a.png"), 0, 1, o, NOW), "trip-2026-11-27-01.png")
        o = rc.Options(case=rc.CASE_TITLE)
        self.assertEqual(rc.new_name(rc.Item("/x/my cool_file.txt"), 0, 1, o, NOW), "My Cool_File.txt")
        self.assertEqual(rc.new_name(rc.Item("/x/My.Folder", True), 0, 1, rc.Options(base_name="F"), NOW), "F_01")
        o = rc.Options(base_name="WW", separator="")
        self.assertEqual(rc.new_name(rc.Item("/x/a.png"), 0, 1, o, NOW), "WW01.png")

    def test_file_date_uses_creation_time(self):
        o = rc.Options(base_name="s", date=rc.DATE_FILE)
        made = time.mktime((2024, 3, 5, 12, 0, 0, 0, 0, -1))
        self.assertEqual(rc.new_name(rc.Item("/x/a.png", False, made), 0, 1, o, NOW), "s_2024-03-05_01.png")

    def test_windows_name_rules(self):
        for bad in ("a?.png", "con.txt", "COM1", "x.", "x ", "", "a|b"):
            self.assertFalse(rc.valid_name(bad)[0], bad)
        for good in ("WW_01.png", "console.txt", "COMX.txt"):
            self.assertTrue(rc.valid_name(good)[0], good)

    def test_sort_oldest_first_then_natural(self):
        items = [rc.Item("img10.png", False, 5), rc.Item("img2.png", False, 5), rc.Item("z.png", False, 1)]
        self.assertEqual([Path(i.path).name for i in rc.sort_by_created(items)], ["z.png", "img2.png", "img10.png"])

    def test_options_from_saved_settings_ignore_bad_values(self):
        o = rc.Options.from_dict({"base_name": "WW", "start": -4, "padding": 99, "case": "shout", "date": "today"})
        self.assertEqual((o.base_name, o.start, o.padding, o.case, o.date), ("WW", 1, 2, rc.CASE_KEEP, rc.DATE_TODAY))
        self.assertEqual(rc.Options.from_dict(None), rc.Options())


class Checks(Folder):
    def test_existing_file_and_duplicates_block(self):
        items = self.make("a.png", "b.png")
        (self.dir / "WW_01.png").write_text("someone else's", encoding="utf-8")
        plans = rc.plan(items, rc.Options(base_name="WW"), NOW)
        self.assertEqual([p.status for p in plans], [rc.EXISTS, rc.OK])
        self.assertEqual(rc.problems(plans), 1)
        plans = rc.plan(items, rc.Options(find="a", replace="b"), NOW)
        self.assertEqual([p.status for p in plans], [rc.DUPLICATE, rc.DUPLICATE])

    def test_target_owned_by_another_file_in_the_batch_is_fine(self):
        items = self.make("q.png", "WW_01.png")
        plans = rc.plan(items, rc.Options(base_name="WW"), NOW)
        self.assertEqual(rc.problems(plans), 0)

    def test_unchanged_missing_invalid(self):
        items = self.make("WW_01.png", "x.png")
        plans = rc.plan(items[:1], rc.Options(base_name="WW"), NOW)
        self.assertEqual(plans[0].status, rc.UNCHANGED)
        os.remove(items[1].path)
        self.assertEqual(rc.plan(items[1:], rc.Options(base_name="WW"), NOW)[0].status, rc.MISSING)
        self.assertEqual(rc.plan(items[:1], rc.Options(base_name="W?"), NOW)[0].status, rc.INVALID)

    def test_nested_inside_a_renamed_folder(self):
        sub = self.dir / "Old.Stuff"
        sub.mkdir()
        (sub / "f.txt").write_text("x")
        items = [rc.Item(str(sub), True), rc.Item(str(sub / "f.txt"))]
        plans = rc.plan(items, rc.Options(base_name="Folder"), NOW)
        self.assertEqual(plans[0].name, "Folder_01")
        self.assertEqual(plans[1].status, rc.NESTED)


class Transactions(Folder):
    def test_swap_and_chain_then_undo_exactly(self):
        items = self.make("WW_02.png", "WW_01.png", "x.png")
        plans = rc.plan(items, rc.Options(base_name="WW"), NOW)
        self.assertEqual(rc.problems(plans), 0)
        store = rc.Store(self.store_dir)
        store.apply(rc.ops_of(plans))
        self.assertEqual(self.names(), ["WW_01.png", "WW_02.png", "WW_03.png"])
        self.assertEqual(self.read("WW_01.png"), "content of WW_02.png")
        self.assertEqual(self.read("WW_03.png"), "content of x.png")
        store.undo_last()
        self.assertEqual(self.names(), ["WW_01.png", "WW_02.png", "x.png"])
        self.assertEqual(self.read("WW_02.png"), "content of WW_02.png")
        self.assertFalse(store.can_undo())

    def test_two_thousand_files_and_undo_after_restart(self):
        names = [f"photo {i:04d} {chr(97 + i % 26)}.jpg" for i in range(2000)]
        items = self.make(*names)
        plans = rc.plan(items, rc.Options(base_name="Trip"), NOW)
        calls = []
        rc.Store(self.store_dir).apply(rc.ops_of(plans), progress=lambda d, t: calls.append(d))
        self.assertTrue(calls)
        self.assertIn("Trip_0001.jpg", self.names())
        self.assertIn("Trip_2000.jpg", self.names())
        again = rc.Store(self.store_dir)
        self.assertTrue(again.can_undo())
        self.assertFalse(again.recovered)
        again.undo_last()
        self.assertEqual(self.names(), sorted(names))

    def test_a_file_created_after_the_preview_is_never_overwritten(self):
        items = self.make("a.png", "b.png")
        plans = rc.plan(items, rc.Options(base_name="N"), NOW)
        (self.dir / "N_02.png").write_text("precious", encoding="utf-8")
        with self.assertRaises(rc.RenameError) as caught:
            rc.Store(self.store_dir).apply(rc.ops_of(plans))
        self.assertTrue(caught.exception.rolled_back)
        self.assertIn("Nothing was changed", str(caught.exception))
        self.assertEqual(self.read("N_02.png"), "precious")
        self.assertEqual(self.names(), ["N_02.png", "a.png", "b.png"])

    def test_failure_half_way_puts_everything_back(self):
        items = self.make("a.png", "b.png", "c.png")
        ops = [rc.Op(items[0].path, str(self.dir / "1.png")), rc.Op(items[1].path, str(self.dir / "2.png")),
               rc.Op(items[2].path, str(self.dir / "missing" / "3.png"))]
        store = rc.Store(self.store_dir)
        with self.assertRaises(rc.RenameError) as caught:
            store.apply(ops)
        self.assertTrue(caught.exception.rolled_back)
        self.assertEqual(self.names(), ["a.png", "b.png", "c.png"])
        self.assertFalse(store.can_undo())
        self.assertFalse(store.journal.exists())

    def test_power_loss_mid_rename_is_put_back_on_next_start(self):
        self.store_dir.mkdir()
        (self.dir / "b.png").write_text("A", encoding="utf-8")
        (self.dir / "t1.tmp").write_text("B", encoding="utf-8")
        journal = {"id": "x", "phase": 2, "steps": [
            {"src": str(self.dir / "a.png"), "temp": str(self.dir / "t0.tmp"), "dst": str(self.dir / "b.png")},
            {"src": str(self.dir / "b.png"), "temp": str(self.dir / "t1.tmp"), "dst": str(self.dir / "a.png")}]}
        (self.store_dir / "rename-journal.json").write_text(json.dumps(journal), encoding="utf-8")
        store = rc.Store(self.store_dir)
        self.assertTrue(store.recovered)
        self.assertEqual(store.recover_problem, "")
        self.assertEqual((self.read("a.png"), self.read("b.png")), ("A", "B"))
        self.assertFalse(store.journal.exists())

    def test_undo_when_a_file_was_deleted_since(self):
        items = self.make("a.png", "b.png")
        store = rc.Store(self.store_dir)
        store.apply(rc.ops_of(rc.plan(items, rc.Options(base_name="Z"), NOW)))
        os.remove(self.dir / "Z_02.png")
        ready, bad = store.undo_plan()
        self.assertEqual((len(ready), bad), (1, 1))
        with self.assertRaises(ValueError):
            store.undo_last()
        store.undo_last(skip_unavailable=True)
        self.assertEqual(self.names(), ["a.png"])

    def test_folder_rename(self):
        sub = self.dir / "Old.Stuff"
        sub.mkdir()
        (sub / "f.txt").write_text("x")
        plans = rc.plan([rc.Item(str(sub), True)], rc.Options(base_name="Folder"), NOW)
        rc.Store(self.store_dir).apply(rc.ops_of(plans))
        self.assertTrue((self.dir / "Folder_01" / "f.txt").exists())

    def test_history_keeps_fifty(self):
        store = rc.Store(self.store_dir)
        item = self.make("f0.txt")[0]
        current = item.path
        for i in range(55):
            nxt = str(self.dir / f"f{i + 1}.txt")
            store.apply([rc.Op(current, nxt)])
            current = nxt
        self.assertEqual(len(rc.Store(self.store_dir).history), rc.MAX_HISTORY)

    def test_move_never_replaces(self):
        a, b = self.make("a.txt", "b.txt")
        with self.assertRaises(FileExistsError):
            rc.move_no_replace(a.path, b.path)
        self.assertEqual(self.read("b.txt"), "content of b.txt")


class Collect(Folder):
    def test_a_folder_adds_its_files_or_itself(self):
        self.make("a.png", "b.txt")
        sub = self.dir / "inner"
        sub.mkdir()
        (sub / "deep.png").write_text("x")
        got = rc.scan_paths([str(self.dir)])
        self.assertEqual(sorted(Path(i.path).name for i in got), ["a.png", "b.txt"])
        got = rc.scan_paths([str(self.dir)], rename_folders=True)
        self.assertEqual([(i.is_dir, Path(i.path).name) for i in got], [(True, "files")])
        self.assertEqual(rc.scan_paths([str(self.dir / "gone.png")]), [])


if __name__ == "__main__":
    unittest.main()
