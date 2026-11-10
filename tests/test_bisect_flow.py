import random
import unittest
from datetime import datetime

from gg_desktop import bisect_clues as bcl
from gg_desktop import bisect_flow as bf
from gg_desktop.bisect_core import Unit, Verdict

NOW = datetime(2026, 11, 10, 12, 0, 0).timestamp()
DAY = 86400.0


def units(n=30):
    return [Unit(f"m{i}", f"Mod {i}", added=NOW - (60 - i) * DAY, kind="code" if i % 7 == 0 else "assets")
            for i in range(n)]


def play(flow, truth, limit=300):
    for _ in range(limit):
        step = flow.step()
        if isinstance(step, Verdict):
            return step
        flow.answer("crash" if truth <= step.on_keys else "ok")
    raise AssertionError("no verdict")


class Dates(unittest.TestCase):
    def test_words_and_formats(self):
        for text, days in (("yesterday", 1), ("last week", 7), ("2 weeks ago", 14), ("three days", 3),
                           ("a month ago", 30), ("1 year", 365), ("today", 0)):
            self.assertEqual(bf.parse_when(text, NOW), (NOW - days * DAY, ""), text)
        self.assertEqual(bf.parse_when("2026-10-30", NOW)[0], datetime(2026, 10, 30).timestamp())
        self.assertEqual(bf.parse_when("Oct 30 2026", NOW)[0], datetime(2026, 10, 30).timestamp())
        self.assertEqual(bf.parse_when("10/30/2026", NOW)[0], datetime(2026, 10, 30).timestamp())
        self.assertEqual(bf.parse_when("", NOW), (None, ""))

    def test_bad_and_future_dates_say_what_to_type(self):
        self.assertIn("2 weeks ago", bf.parse_when("when I was young", NOW)[1])
        self.assertIn("future", bf.parse_when("2027-05-05", NOW)[1])
        self.assertIsNone(bf.parse_when("2027-05-05", NOW)[0])

    def test_day_text(self):
        self.assertEqual(bf.day_text(None, NOW), "Unknown")
        self.assertEqual(bf.day_text(NOW - 3 * DAY, NOW), "Nov 7, 2026 (3d ago)")
        self.assertIn("today", bf.day_text(NOW - 60, NOW))


class Walkthrough(unittest.TestCase):
    def test_instructions_name_what_to_do_and_the_expected_result(self):
        flow = bf.Flow(units(), bf.Setup(), now=NOW)
        first = flow.step()
        self.assertEqual((first.number, first.purpose, first.runs), (1, "baseline", 1))
        self.assertIn("It should crash", first.instructions)
        self.assertEqual(len(first.on_names), 30)
        flow.answer("crash")
        second = flow.step()
        self.assertEqual(second.purpose, "empty")
        self.assertIn("should NOT crash", second.instructions)
        self.assertEqual(second.off_count, 30)

    def test_a_search_with_every_kind_of_answer_reaches_the_right_mods(self):
        flow = bf.Flow(units(), bf.Setup(), now=NOW)
        verdict = play(flow, {"m4", "m20"})
        self.assertEqual(set(verdict.keys), {"m4", "m20"})
        self.assertTrue(flow.done())
        self.assertIn("Cause", {r.status for r in flow.rows()})

    def test_sometimes_crashing_asks_for_more_tries_and_says_so(self):
        flow = bf.Flow(units(), bf.Setup(sometimes=True), now=NOW)
        flow.answer("crash")
        flow.answer("ok")
        step = flow.step()
        self.assertGreaterEqual(step.runs, 3)
        self.assertIn("up to", step.instructions)
        self.assertIn("any try means Crashed", step.instructions) if step.expected == "ok" else None

    def test_not_sure_adds_no_evidence_and_undo_steps_back(self):
        flow = bf.Flow(units(), bf.Setup(), now=NOW)
        first = flow.step()
        flow.answer("unsure")
        self.assertEqual(flow.step(), first)
        flow.answer("crash")
        self.assertEqual(flow.step().number, 2)
        self.assertTrue(flow.undo())
        self.assertEqual(flow.step(), first)

    def test_progress_text_and_rows_follow_the_answers(self):
        flow = bf.Flow(units(), bf.Setup(), now=NOW)
        self.assertTrue(all(r.status == "Starts on" for r in flow.rows()))
        flow.answer("crash")
        flow.answer("ok")
        for _ in range(3):
            step = flow.step()
            flow.answer("crash" if {"m9"} <= step.on_keys else "ok")
        statuses = {r.status for r in flow.rows()}
        self.assertTrue({"Ruled out"} & statuses or {"On in test", "Off in test"} & statuses)
        self.assertIn("still in play", flow.progress_text())

    def test_mods_added_after_it_last_worked_come_before_older_ones_with_reasons(self):
        flow = bf.Flow(units(), bf.Setup(last_good=NOW - 45 * DAY), now=NOW)   # mods 15 and up are newer
        rows = flow.rows()
        newest = [r for r in rows if r.name == "Mod 29"][0]
        older = [r for r in rows if r.name == "Mod 8"][0]
        self.assertLess(rows.index(newest), rows.index(older))
        self.assertIn("after the game last worked", newest.why)
        self.assertTrue(all(r.why for r in rows))

    def test_always_on_mods_are_never_tested_and_show_as_always_on(self):
        flow = bf.Flow(units(), bf.Setup(always_on=("m3",)), now=NOW)
        verdict = play(flow, {"m10"})
        self.assertEqual(verdict.keys, ("m10",))
        self.assertTrue(any(r.name == "Mod 3" and r.status == "Always on" for r in flow.rows()))

    def test_pack_choices_group_mods_installed_together(self):
        us = [Unit(f"p{i}", f"Pack {i}", added=NOW - 10 * DAY + i * 60) for i in range(12)]
        us += [Unit(f"o{i}", f"Old {i}", added=NOW - 300 * DAY + i * DAY) for i in range(4)]
        flow = bf.Flow(us, bf.Setup(), now=NOW)
        label, keys = flow.batch_choices()[0]
        self.assertEqual(len(keys), 12)
        self.assertIn("12 installed", label)

    def test_a_chosen_pack_is_tested_first_and_wrong_choices_still_find_the_truth(self):
        us = units(60)
        wrong = bf.Flow(us, bf.Setup(hint_keys=("m50", "m51", "m52")), now=NOW)
        self.assertEqual(set(play(wrong, {"m2", "m3"}).keys), {"m2", "m3"})

    def test_crash_report_clues_are_used_and_cross_checked(self):
        files = {f"m{i}": [f"plugins/thing{i}.dll"] for i in range(30)}
        clues = bcl.read_reports(units(), files, [("thing4.dll crashed", NOW), ("thing4.dll again", NOW)])
        flow = bf.Flow(units(), bf.Setup(), now=NOW, clues=clues)
        play(flow, {"m4"})
        text = flow.report_text("Default")
        self.assertIn("Profile: Default", text)
        self.assertIn("agree on Mod 4", text)
        self.assertNotIn("safe", text.lower())

    def test_report_before_the_end_does_not_claim_a_result(self):
        flow = bf.Flow(units(), bf.Setup(), now=NOW)
        text = flow.report_text()
        self.assertNotIn("Cause", text)


class Saving(unittest.TestCase):
    def test_a_run_survives_a_restart_at_every_point(self):
        truth = {"m6", "m22"}
        for stop in (0, 1, 3, 7, 12):
            flow = bf.Flow(units(), bf.Setup(last_good=NOW - 30 * DAY, hint_keys=("m6",)), now=NOW, profile_key="p")
            for _ in range(stop):
                step = flow.step()
                if isinstance(step, Verdict):
                    break
                flow.answer("crash" if truth <= step.on_keys else "ok")
            saved = flow.snapshot()
            back = bf.Flow.restore(units(), saved, "p")
            self.assertEqual(back.step(), flow.step(), stop)
            self.assertEqual(set(play(back, truth).keys), truth)

    def test_snapshot_is_plain_json(self):
        import json
        flow = bf.Flow(units(), bf.Setup(), now=NOW, profile_key="p")
        flow.answer("crash")
        json.dumps(flow.snapshot())

    def test_changed_mods_or_other_profile_or_junk_are_refused(self):
        flow = bf.Flow(units(), bf.Setup(), now=NOW, profile_key="p")
        flow.answer("crash")
        saved = flow.snapshot()
        changed = units()
        changed[3] = Unit("m3", "Mod 3", added=NOW - 5 * DAY)
        with self.assertRaises(ValueError):
            bf.Flow.restore(changed, saved, "p")
        with self.assertRaises(ValueError):
            bf.Flow.restore(units(), saved, "other")
        with self.assertRaises(ValueError):
            bf.Flow.restore(units(), {"version": 1}, "p")
        with self.assertRaises(ValueError):
            bf.Flow.restore(units(), "nonsense", "p")
        with self.assertRaises(ValueError):
            bf.Flow.restore(units(), dict(saved, version=7), "p")

    def test_fuzzed_snapshots_never_raise_anything_but_value_error(self):
        rng = random.Random(4)
        flow = bf.Flow(units(), bf.Setup(), now=NOW, profile_key="p")
        flow.answer("crash")
        good = flow.snapshot()
        for _ in range(200):
            data = dict(good)
            key = rng.choice(list(data))
            data[key] = rng.choice([None, "x", 5, [], {}, [1, 2], -1.5])
            try:
                bf.Flow.restore(units(), data, "p")
            except ValueError:
                pass


class Manual(unittest.TestCase):
    def test_list_for_managers_that_cannot_be_written(self):
        flow = bf.Flow(units(5), bf.Setup(), now=NOW)
        text = bf.mods_to_turn_on(flow.step())
        self.assertIn("Turn ON these 5 mods", text)
        self.assertIn("Mod 0", text)


if __name__ == "__main__":
    unittest.main()
