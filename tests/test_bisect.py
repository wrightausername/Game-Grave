import itertools
import math
import random
import unittest

from gg_desktop import bisect_core as bc
from gg_desktop.bisect_core import Session, Unit, Verdict

NOW = 1_800_000_000.0
DAY = 86400.0
HOUR = 3600.0


def make_units(n, **kw):
    return [Unit(f"m{i}", f"Mod {i}", added=NOW - (200 - i % 150) * DAY, kind="assets", **kw) for i in range(n)]


def drive(session, causes, flaky=None, limit=400):
    """Answer every proposed test from an oracle. A setup crashes when it holds every mod of any cause."""
    causes = [set(c) for c in causes]
    launches = 0
    for _ in range(limit):
        step = session.next_step()
        if isinstance(step, Verdict):
            return step, launches
        launches += 1
        crashed = any(c <= step.enabled for c in causes)
        if flaky is not None and crashed:
            crashed = any(flaky.random() < session.detect for _ in range(step.runs))
        session.record(step, "crash" if crashed else "ok")
    raise AssertionError("did not finish")


class Clues(unittest.TestCase):
    def test_recent_first_with_reasons_and_unknown_last(self):
        units = [Unit("a", "Old", added=NOW - 300 * DAY), Unit("b", "New", added=NOW - 2 * DAY), Unit("c", "Mystery"),
                 Unit("d", "Mid", added=NOW - 40 * DAY)]
        rows = bc.recent_order(units, last_good=NOW - 100 * DAY, now=NOW)
        self.assertEqual([u.key for u, _ in rows], ["b", "d", "a", "c"])
        self.assertIn("after the game last worked", rows[0][1])
        self.assertIn("before the game last worked", rows[2][1])
        self.assertEqual(rows[3][1], "install date unknown")

    def test_batches_find_a_pack_installed_together(self):
        pack = [Unit(f"p{i}", f"Pack {i}", added=NOW - 10 * DAY + i * 60) for i in range(40)]
        single = [Unit("s", "Solo", added=NOW - 2 * DAY)]
        old = [Unit(f"o{i}", f"Old {i}", added=NOW - 300 * DAY + i * DAY) for i in range(3)]
        found = bc.batches(pack + single + old + [Unit("u", "Undated")])
        self.assertEqual(found[0].keys, ("s",))
        self.assertEqual(len(found[1].keys), 40)
        self.assertEqual(sum(len(b.keys) for b in found), 44)
        self.assertGreater(found[0].end, found[1].end)

    def test_suspicion_uses_only_stated_facts(self):
        s = Session([Unit("a", "A", added=NOW - 5 * DAY, kind="code", crash_hits=2),
                     Unit("b", "B", added=NOW - 5 * DAY, kind="assets"), Unit("c", "C")], last_good=NOW - 30 * DAY, now=NOW)
        self.assertGreater(s.weights["a"], s.weights["b"])
        self.assertGreater(s.weights["b"], s.weights["c"])
        self.assertIn("named in 2 crash logs", s.reasons["a"])
        self.assertEqual(s.reasons["c"], ["install date unknown"])

    def test_hints_say_why_they_matter(self):
        s = Session(make_units(5), now=NOW, hint_keys=("m1",), window=(NOW - 300 * DAY, NOW - 190 * DAY))
        self.assertIn("you said the crashes started after adding it", s.reasons["m1"])
        self.assertTrue(any("added in the time you named" in r for r in s.reasons.values()))


class Dependencies(unittest.TestCase):
    def test_closure_and_dependents(self):
        s = Session([Unit("fw", "Framework"), Unit("a", "A", requires=("fw",)), Unit("b", "B", requires=("a",)),
                     Unit("c", "C", requires=("ghost",))])
        self.assertEqual(s.closure({"b"}), {"b", "a", "fw"})
        self.assertEqual(s.dependents("fw"), {"fw", "a", "b"})
        self.assertEqual(s.closure({"c"}), {"c"})

    def test_no_test_ever_switches_on_a_mod_without_what_it_needs(self):
        units = make_units(30)
        units[5] = Unit("m5", "Mod 5", added=units[5].added, requires=("m20",))
        units[20] = Unit("m20", "Mod 20", added=units[20].added, requires=("m21",))
        s = Session(units, now=NOW)
        verdict, _ = drive(s, [{"m5"}])
        self.assertIn("m5", verdict.keys)
        for test, _ in s.tests:
            for key in test.enabled:
                self.assertTrue(set(s._requires[key]) <= test.enabled, (key, test.purpose))

    def test_always_on_mod_that_needs_a_mod_does_not_loop(self):
        units = make_units(12) + [Unit("fw", "Framework", pinned=True, requires=("m0",))]
        verdict, launches = drive(Session(units, now=NOW), [{"m5"}])
        self.assertEqual(verdict.keys, ("m5",))
        self.assertLess(launches, 20)

    def test_pinned_framework_is_on_in_every_test(self):
        units = make_units(20) + [Unit("fw", "Script extender", pinned=True)]
        s = Session(units, now=NOW)
        verdict, _ = drive(s, [{"m3"}])
        self.assertEqual(verdict.keys, ("m3",))
        self.assertTrue(all("fw" in t.enabled for t, _ in s.tests))

    def test_mods_that_need_each_other_are_named_together(self):
        units = make_units(10)
        units[2] = Unit("m2", "Mod 2", added=units[2].added, requires=("m3",))
        units[3] = Unit("m3", "Mod 3", added=units[3].added, requires=("m2",))
        verdict, launches = drive(Session(units, now=NOW), [{"m2"}])
        self.assertEqual(set(verdict.keys), {"m2", "m3"})
        self.assertIn("switched together", verdict.text)
        self.assertLessEqual(launches, 25)


class OneMod(unittest.TestCase):
    def test_every_position_is_found(self):
        units = make_units(33)
        for i in range(33):
            verdict, launches = drive(Session(units, now=NOW), [{f"m{i}"}])
            self.assertEqual((verdict.kind, verdict.keys, verdict.confidence), ("culprit", (f"m{i}",), 1.0), i)
            self.assertLessEqual(launches, 2 * math.ceil(math.log2(33)) + 6)

    def test_single_mod_is_found_in_few_launches(self):
        verdict, launches = drive(Session(make_units(64), now=NOW), [{"m41"}])
        self.assertEqual(verdict.keys, ("m41",))
        self.assertLessEqual(launches, 18)


class ManyMods(unittest.TestCase):
    def test_two_three_and_six_mods_that_only_crash_together(self):
        units = make_units(120)
        for size in (2, 3, 4, 6):
            rng = random.Random(size)
            truth = set(f"m{i}" for i in rng.sample(range(120), size))
            verdict, _ = drive(Session(units, now=NOW), [truth])
            self.assertEqual((verdict.kind, set(verdict.keys)), ("interaction", truth), size)
            self.assertEqual(verdict.groups, (tuple(sorted(truth)),))
            self.assertEqual(set(verdict.fixes), truth)       # any one of them off is enough
            self.assertIn("together", verdict.text)

    def test_reliable_for_any_subset_of_a_small_list(self):
        units = make_units(7)
        keys = [u.key for u in units]
        for size in range(1, 8):
            for truth in itertools.combinations(keys, size):
                verdict, _ = drive(Session(units, now=NOW), [set(truth)])
                self.assertEqual(set(verdict.keys), set(truth), truth)
                self.assertNotEqual(verdict.kind, "undetermined", truth)

    def test_several_unrelated_causes_are_all_found(self):
        units = make_units(150)
        causes = [{"m10"}, {"m70", "m71"}, {"m100", "m33", "m140"}]
        verdict, _ = drive(Session(units, now=NOW), causes)
        self.assertEqual(verdict.kind, "multiple")
        self.assertEqual(sorted(map(set, verdict.groups), key=min), sorted(causes, key=min))
        self.assertIn("3 separate causes", verdict.text)

    def test_overlapping_causes_report_the_one_mod_that_fixes_both(self):
        units = make_units(60)
        verdict, _ = drive(Session(units, now=NOW), [{"m5", "m9"}, {"m5", "m40"}])
        self.assertEqual(verdict.fixes, ("m5",))
        self.assertIn("just Mod 5 is enough", verdict.text)

    def test_a_wrong_group_is_never_named_for_random_cases(self):
        rng = random.Random(7)
        for trial in range(60):
            n = rng.choice([8, 30, 90])
            units = make_units(n)
            causes = [set(f"m{i}" for i in rng.sample(range(n), rng.randint(1, 4))) for _ in range(rng.randint(1, 3))]
            verdict, _ = drive(Session(units, now=NOW), causes)
            found = {frozenset(g) for g in verdict.groups}
            hit = set().union(*causes)
            self.assertTrue(set(verdict.keys) <= hit, (causes, verdict.keys))
            self.assertTrue(all(any(c <= set(g) for c in causes) for g in found), (causes, verdict.groups))


class Clue(unittest.TestCase):
    def test_a_right_hint_saves_launches(self):
        units = make_units(200)
        truth = {"m150", "m151"}
        plain, slow = drive(Session(units, now=NOW), [truth])
        hinted, fast = drive(Session(units, now=NOW, hint_keys=("m150", "m151", "m120")), [truth])
        self.assertEqual(set(plain.keys), truth)
        self.assertEqual(set(hinted.keys), truth)
        self.assertLess(fast, slow)

    def test_a_wrong_hint_costs_launches_but_never_the_answer(self):
        units = make_units(200)
        truth = {"m3", "m4", "m5"}
        verdict, _ = drive(Session(units, now=NOW, hint_keys=("m190", "m191", "m192")), [truth])
        self.assertEqual(set(verdict.keys), truth)
        self.assertEqual(verdict.kind, "interaction")

    def test_last_good_date_and_window_only_order_the_search(self):
        units = make_units(100)
        truth = {"m60", "m1"}                       # one recent, one old
        for kwargs in ({"last_good": NOW - 60 * DAY}, {"window": (NOW - 60 * DAY, NOW)},
                       {"last_good": NOW + 5 * DAY}):
            verdict, _ = drive(Session(units, now=NOW, **kwargs), [truth])
            self.assertEqual(set(verdict.keys), truth, kwargs)

    def test_first_test_checks_the_hinted_mods_on_their_own(self):
        units = make_units(50)
        s = Session(units, now=NOW, hint_keys=("m7", "m8"))
        for _ in range(2):
            step = s.next_step()
            s.record(step, "crash" if step.purpose == "baseline" else "ok")
        step = s.next_step()
        self.assertEqual(step.purpose, "narrow")
        self.assertEqual(set(step.under_test), {"m7", "m8"})


class NotAMod(unittest.TestCase):
    def test_crash_with_every_mod_off_is_reported_as_not_a_mod(self):
        verdict, launches = drive(Session(make_units(20), now=NOW), [set()])
        self.assertEqual(verdict.kind, "outside")
        self.assertEqual(launches, 2)
        self.assertIn("not one of the mods", verdict.text)

    def test_no_crash_at_the_start_means_nothing_to_search(self):
        verdict, launches = drive(Session(make_units(20), now=NOW), [])
        self.assertEqual((verdict.kind, launches), ("unreproducible", 1))

    def test_unreproducible_message_gives_the_miss_chance(self):
        verdict, _ = drive(Session(make_units(6), now=NOW, detect=0.5, runs=2), [])
        self.assertEqual(verdict.kind, "unreproducible")
        self.assertIn("less than 1%", verdict.text)
        self.assertIn("10 launches", verdict.text)


class Intermittent(unittest.TestCase):
    def test_flaky_crashes_for_one_and_many_mods(self):
        rng = random.Random(11)
        right = 0
        trials = 20
        for trial in range(trials):
            n = rng.choice([20, 60])
            truth = set(f"m{i}" for i in rng.sample(range(n), rng.choice([1, 2, 3])))
            s = Session(make_units(n), now=NOW, detect=0.7, runs=3)
            verdict, _ = drive(s, [truth], flaky=rng)
            right += set(verdict.keys) == truth
        self.assertGreaterEqual(right, trials - 1)

    def test_flaky_verdict_states_its_uncertainty(self):
        s = Session(make_units(10), now=NOW, detect=0.7, runs=3)
        verdict, _ = drive(s, [{"m4"}], flaky=random.Random(2))
        self.assertEqual(verdict.kind, "culprit")
        self.assertIn("not certain", verdict.text)
        self.assertLess(verdict.confidence, 1.0)
        self.assertGreater(verdict.confidence, 0.9)

    def test_the_final_checks_use_more_runs_than_the_narrowing(self):
        s = Session(make_units(10), now=NOW, detect=0.6, runs=1)
        drive(s, [{"m4"}], flaky=random.Random(5))
        narrow = [t.runs for t, _ in s.tests if t.purpose == "narrow"]
        checks = [t.runs for t, _ in s.tests if t.expected == "ok"]
        self.assertTrue(narrow and checks)
        self.assertGreater(min(checks), min(narrow))


class Mistakes(unittest.TestCase):
    def test_undo_rewinds_to_the_earlier_question(self):
        s = Session(make_units(16), now=NOW)
        a = s.next_step()
        s.record(a, "crash")
        b = s.next_step()
        s.record(b, "ok")
        c = s.next_step()
        self.assertTrue(s.undo())
        self.assertEqual(s.next_step(), b)
        self.assertTrue(s.undo())
        self.assertEqual(s.next_step(), a)
        self.assertFalse(s.undo())

    def test_unsure_adds_no_evidence_and_repeats_the_test(self):
        s = Session(make_units(16), now=NOW)
        first = s.next_step()
        s.record(first, "unsure")
        self.assertEqual(s.next_step(), first)
        self.assertEqual(s.unsure, 1)

    def test_a_wrong_tap_is_caught_by_the_checks(self):
        units = make_units(40)
        truth = {"m10", "m22"}
        for flip_at in range(2, 12):
            s = Session(units, now=NOW)
            verdict, i = None, 0
            for _ in range(300):
                step = s.next_step()
                if isinstance(step, Verdict):
                    verdict = step
                    break
                crashed = truth <= step.enabled
                if i == flip_at:
                    crashed = not crashed
                i += 1
                s.record(step, "crash" if crashed else "ok")
            self.assertIsNotNone(verdict)
            if verdict.kind in ("culprit", "interaction", "multiple"):
                self.assertTrue(set(verdict.keys) <= truth or truth <= set(verdict.keys), (flip_at, verdict.keys))

    def test_bad_result_word_is_refused(self):
        s = Session(make_units(4), now=NOW)
        with self.assertRaises(ValueError):
            s.record(s.next_step(), "maybe")


class Limits(unittest.TestCase):
    def test_running_out_of_launches_reports_how_far_it_got(self):
        units = make_units(80)
        s = Session(units, now=NOW)
        original = bc.MAX_TESTS
        bc.MAX_TESTS = 6
        try:
            verdict, _ = drive(s, [{"m1", "m30", "m60"}])
        finally:
            bc.MAX_TESTS = original
        self.assertEqual(verdict.kind, "undetermined")
        self.assertIn("narrow", verdict.text)
        self.assertEqual(verdict.confidence, 0.0)

    def test_progress_and_suspects_shrink_as_it_narrows(self):
        s = Session(make_units(64), now=NOW)
        start = s.progress()
        self.assertEqual((start["launches"], start["suspects"], start["of"]), (0, 64, 64))
        for _ in range(4):
            step = s.next_step()
            s.record(step, "crash" if {"m9"} <= step.enabled else "ok")
        later = s.progress()
        self.assertLess(later["suspects"], 64)
        rows = s.suspects()
        self.assertEqual(len(rows), later["suspects"])
        self.assertAlmostEqual(sum(share for _, share, _ in rows), 1.0)

    def test_report_lists_answers_and_does_not_overclaim(self):
        s = Session(make_units(8), now=NOW)
        drive(s, [{"m1"}])
        text = s.report()
        self.assertIn("baseline", text)
        self.assertIn("Only your test answers count as proof", text)
        self.assertNotIn("safe", text.lower())

    def test_empty_and_tiny_lists_do_not_crash(self):
        for units in ([], [Unit("only", "Only")]):
            s = Session(units, now=NOW)
            for _ in range(10):
                step = s.next_step()
                if isinstance(step, Verdict):
                    break
                s.record(step, "crash" if "only" in step.enabled else "ok")


if __name__ == "__main__":
    unittest.main()
