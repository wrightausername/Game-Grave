import time
import unittest
from datetime import datetime, timedelta

from gg_desktop import undo_actions as actions
from gg_desktop import undo_data as data
from gg_desktop import undo_insight as insight

NOW = datetime(2026, 11, 8, 12, 0).astimezone()


def iso(days_ago):
    return (NOW - timedelta(days=days_ago)).isoformat(timespec="seconds")


def record(rid, path, days=1, size=1000, state="Not checked", action="Old Files"):
    return {"id": rid, "path": path, "size": size, "time": iso(days), "action": action, "state": state,
            "note": "n"}


def event(kind, days=1, **extra):
    base = {"date": iso(days), "kind": kind, "details": extra.pop("details", "d")}
    base.update(extra)
    return base


class Build(unittest.TestCase):
    def setUp(self):
        self.now = NOW.timestamp()
        self.records = [record("a", "C:\\Stash\\clip.mp4", 1, 5000, "Available", "Graveyard"),
                        record("b", "C:\\Stash\\old.zip", 10, 2000, "Not found"),
                        record("c", "C:\\Stash\\pic.png", 40, 300, "Restored", "Captures"),
                        {"id": "a", "path": "dup"}, {"nope": 1}, "bad", {"id": ""}]
        self.events = [
            event("Manual recycled", 1, path="C:\\Stash\\clip.mp4", recovery_id="a", session_id="s1", size_bytes=5000),
            event("Cleanup skipped", 2, path="C:\\x\\f.tmp", result="Changed since scan", session_id="s1"),
            event("Restored from Recycle Bin", 40, details="C:\\Stash\\pic.png", path="C:\\Stash\\pic.png"),
            event("Scan completed", 3), event("Scan failed", 4, result="Scan failed: disk"),
            event("Cleanup started"), event("Cleanup finished"),
            event("Automation enabled", 5), event("Something odd", 6),
            event("Steam uninstall opened", 7, details="Game"),
        ]
        self.entries = data.build_entries(self.records, self.events)

    def test_junk_and_duplicates_dropped_and_internal_events_skipped(self):
        keys = [e.key for e in self.entries]
        self.assertEqual(len([k for k in keys if k.startswith("recovery:")]), 3)
        self.assertEqual(len(keys), len(set(keys)))
        self.assertFalse(any(e.action.startswith("Cleanup started") or e.action == "Cleanup finished" for e in self.entries))

    def test_restore_event_not_double_counted_with_restored_record(self):
        self.assertEqual(sum(1 for e in self.entries if e.category == "Restored"), 1)

    def test_categories_and_status(self):
        by = {e.key: e for e in self.entries}
        self.assertEqual(by["recovery:a"].status, "Available")
        self.assertEqual(by["recovery:a"].category, "Recycled")
        self.assertEqual(by["recovery:b"].tone, "amber")
        self.assertEqual(by["recovery:c"].category, "Restored")
        failed = [e for e in self.entries if e.tone == "red"]
        self.assertEqual([e.action for e in failed], ["Scan failed"])
        self.assertIn("Skipped", {e.status for e in self.entries})
        self.assertEqual(by["recovery:a"].session, "s1")

    def test_restorable_only_with_record_and_not_restored(self):
        by = {e.key: e for e in self.entries}
        self.assertTrue(by["recovery:a"].restorable)
        self.assertFalse(by["recovery:c"].restorable)
        self.assertFalse(next(e for e in self.entries if e.action == "Scan completed").restorable)

    def test_honest_reversible_text(self):
        by = {e.key: e for e in self.entries}
        self.assertTrue(data.reversible_text(by["recovery:a"]).startswith("Yes"))
        self.assertIn("emptied", data.reversible_text(by["recovery:b"]))
        self.assertEqual(data.reversible_text(by["recovery:c"]), "Already restored")
        self.assertEqual(data.reversible_text(next(e for e in self.entries if e.action == "Scan completed")), "No recovery record")
        for e in self.entries:
            self.assertNotIn("100%", data.reversible_text(e))

    def test_file_type(self):
        by = {e.key: e for e in self.entries}
        self.assertEqual(by["recovery:a"].file_type, "Video")
        self.assertEqual(by["recovery:b"].file_type, "Archive")
        self.assertEqual(by["recovery:c"].file_type, "Image")

    def test_run_members(self):
        by = {e.key: e for e in self.entries}
        self.assertEqual(len(data.run_members(self.entries, by["recovery:a"])), 2)
        self.assertEqual(data.run_members(self.entries, by["recovery:b"]), [by["recovery:b"]])

    def test_metrics_never_call_recycled_bytes_freed(self):
        m = insight.metrics(self.entries, set())
        self.assertEqual(m["recycled"], 3)
        self.assertEqual(m["restored"], 1)
        self.assertEqual(m["bytes"], 5000 + 2000)
        self.assertEqual(m["available"], 1)
        self.assertEqual(m["failed"], 1)
        hidden = {"recovery:a"}
        self.assertEqual(insight.metrics(self.entries, hidden)["recycled"], 2)

    def test_filters_and_facets(self):
        f = insight.Filters()
        rows = insight.apply(self.entries, f, set(), now=self.now)
        self.assertEqual(len(rows), len(self.entries))
        f.range_name = "Last 7 Days"
        week = insight.apply(self.entries, f, set(), now=self.now)
        self.assertTrue(all(e.when >= self.now - 7 * data.DAY for e in week))
        counts = insight.range_counts(self.entries, insight.Filters(), set(), self.now)
        self.assertEqual(counts["All Time"], len(self.entries))
        self.assertLessEqual(counts["Last 24 Hours"], counts["Last 7 Days"])
        f2 = insight.Filters(categories={"Recycled"})
        cats = insight.category_counts(self.entries, f2, set(), self.now)
        self.assertEqual(cats["Restored"], 1, "facet counts ignore the category filter itself")
        f3 = insight.Filters(sources={"Graveyard"})
        self.assertEqual([e.key for e in insight.apply(self.entries, f3, set(), now=self.now)], ["recovery:a"])
        self.assertEqual(insight.source_counts(self.entries, f3, set(), self.now)["Old Files"], 1)
        q = insight.Filters(query="clip")
        self.assertEqual(len(insight.apply(self.entries, q, set(), now=self.now)), 1)

    def test_custom_range_and_hidden(self):
        f = insight.Filters(range_name="Custom Range", start=self.now - 12 * data.DAY, end=self.now - 5 * data.DAY)
        keys = {e.key for e in insight.apply(self.entries, f, set(), now=self.now)}
        self.assertIn("recovery:b", keys)
        self.assertNotIn("recovery:a", keys)
        hidden = {"recovery:b"}
        self.assertNotIn("recovery:b", {e.key for e in insight.apply(self.entries, insight.Filters(), hidden, now=self.now)})
        shown = insight.Filters(show_hidden=True)
        self.assertIn("recovery:b", {e.key for e in insight.apply(self.entries, shown, hidden, now=self.now)})

    def test_sorting(self):
        f = insight.Filters(categories={"Recycled", "Restored"})
        big = insight.apply(self.entries, f, set(), "Size (Largest)", self.now)
        self.assertEqual(big[0].key, "recovery:a")
        old = insight.apply(self.entries, f, set(), "Date (Oldest)", self.now)
        self.assertEqual(old[0].key, "recovery:c")
        name = insight.apply(self.entries, f, set(), "Name (A-Z)", self.now)
        self.assertEqual([e.name for e in name], ["clip.mp4", "old.zip", "pic.png"])

    def test_csv_blocks_formulas(self):
        e = data.build_entries([record("z", "C:\\=cmd.txt")], [])[0]
        e.name = "=SUM(1)"
        rows = insight.csv_rows([e])
        self.assertTrue(rows[1][1].startswith("'"))


class Actions(unittest.TestCase):
    def setUp(self):
        self.entries = data.build_entries([record("a", "C:\\f\\a.zip", state="Available"),
                                           record("c", "C:\\f\\c.zip", state="Restored")],
                                          [event("Scan completed")])

    def test_plan_refuses_unrestorable(self):
        usable, problems = actions.plan(self.entries)
        self.assertEqual([e.recovery_id for e in usable], ["a"])
        self.assertEqual(len(problems), 2)
        self.assertEqual(actions.plan([])[1], ["Nothing is selected."])

    def test_plan_batch_limit(self):
        many = data.build_entries([record(str(i), f"C:\\f\\{i}.zip") for i in range(25)], [])
        usable, problems = actions.plan(many)
        self.assertEqual(len(usable), actions.MAX_BATCH)
        self.assertTrue(any("at most" in p for p in problems))

    def test_restore_checks_first_and_only_restores_available(self):
        calls = []
        states = {"a": "AVAILABLE", "b": "NOT_FOUND", "c": "AMBIGUOUS"}

        def check(rid):
            calls.append(("check", rid))
            return states[rid]

        def restore(rid):
            calls.append(("restore", rid))
            return "RESTORED"
        entries = data.build_entries([record(k, f"C:\\f\\{k}.zip") for k in "abc"], [])
        entries.sort(key=lambda e: e.recovery_id)
        result = actions.restore(entries, check, restore)
        self.assertEqual([c for _, c in result], ["RESTORED", "NOT_FOUND", "AMBIGUOUS"])
        self.assertEqual([c for c in calls if c[0] == "restore"], [("restore", "a")])
        self.assertLess(calls.index(("check", "a")), calls.index(("restore", "a")))
        text = actions.summarize(result)
        self.assertTrue(text.startswith("1 of 3 restored."))
        self.assertIn("Windows may have emptied", text)

    def test_one_failure_does_not_stop_the_rest(self):
        def check(rid):
            if rid == "a":
                raise ValueError("boom")
            return "AVAILABLE"
        entries = data.build_entries([record("a", "C:\\f\\a.zip"), record("b", "C:\\f\\b.zip")], [])
        entries.sort(key=lambda e: e.recovery_id)
        result = actions.restore(entries, check, lambda rid: "RESTORED")
        self.assertTrue(result[0][1].startswith("ERROR"))
        self.assertEqual(result[1][1], "RESTORED")
        self.assertIn("boom", actions.summarize(result))

    def test_cancel(self):
        with self.assertRaises(InterruptedError):
            actions.restore(self.entries, lambda r: "AVAILABLE", lambda r: "RESTORED", canceled=lambda: True)

    def test_hidden_roundtrip_never_mutates_input(self):
        settings = {}
        s1 = actions.with_hidden(settings, ["recovery:a", "audit:1"])
        self.assertEqual(actions.hidden_keys(s1), {"recovery:a", "audit:1"})
        s2 = actions.without_hidden(s1, ["audit:1"])
        self.assertEqual(actions.hidden_keys(s2), {"recovery:a"})
        self.assertEqual(settings, {})
        self.assertEqual(actions.hidden_keys({"undo_hidden": "bad"}), set())
        self.assertEqual(actions.hidden_keys({"undo_hidden": [1, "x"]}), {"x"})

    def test_hidden_limit(self):
        self.assertIsNone(actions.with_hidden({}, [f"k{i}" for i in range(data.MAX_HIDDEN + 1)]))


if __name__ == "__main__":
    unittest.main()
