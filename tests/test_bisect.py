import math
import random
import unittest

from gg_desktop import bisect_core as bc
from gg_desktop.bisect_core import Session, Test, Unit, Verdict

NOW = 1_800_000_000.0
DAY = 86400.0


def make_units(n, **special):
    units = []
    for i in range(n):
        units.append(Unit(f"m{i}", f"Mod {i}", added=NOW - (200 - i % 150) * DAY, kind="assets"))
    return units


def drive(session, crashes, flaky=None, limit=80):
    """Answer each proposed test from an oracle. crashes(enabled) -> bool. Returns the verdict and the launches used."""
    launches = 0
    for _ in range(limit):
        step = session.next_step()
        if isinstance(step, Verdict):
            return step, launches
        launches += 1
        crashed = crashes(step.enabled)
        if flaky is not None and crashed:
            crashed = any(flaky.random() < session.detect for _ in range(step.runs))
        session.record(step, "crash" if crashed else "ok")
    raise AssertionError("did not finish")


class Ordering(unittest.TestCase):
    def test_recent_first_with_reasons_and_unknown_last(self):
        units = [Unit("a", "Old", added=NOW - 300 * DAY), Unit("b", "New", added=NOW - 2 * DAY), Unit("c", "Mystery"),
                 Unit("d", "Mid", added=NOW - 40 * DAY)]
        rows = bc.recent_order(units, last_good=NOW - 100 * DAY, now=NOW)
        self.assertEqual([u.key for u, _ in rows], ["b", "d", "a", "c"])
        self.assertIn("after the game last worked", rows[0][1])
        self.assertIn("before the game last worked", rows[2][1])
        self.assertEqual(rows[3][1], "install date unknown")

    def test_suspicion_uses_only_stated_facts(self):
        s = Session([Unit("a", "A", added=NOW - 5 * DAY, kind="code", crash_hits=2),
                     Unit("b", "B", added=NOW - 5 * DAY, kind="assets"), Unit("c", "C")], last_good=NOW - 30 * DAY, now=NOW)
        wa, wb, wc = s.weights["a"], s.weights["b"], s.weights["c"]
        self.assertGreater(wa, wb)
        self.assertGreater(wb, wc)
        self.assertIn("named in 2 crash logs", s.reasons["a"])
        self.assertEqual(s.reasons["c"], ["install date unknown"])


class Dependencies(unittest.TestCase):
    def test_closure_and_dependents(self):
        s = Session([Unit("fw", "Framework"), Unit("a", "A", requires=("fw",)), Unit("b", "B", requires=("a",)),
                     Unit("c", "C", requires=("ghost",))])
        self.assertEqual(s.closure({"b"}), {"b", "a", "fw"})
        self.assertEqual(s.dependents("fw"), {"fw", "a", "b"})
        self.assertEqual(s.closure({"c"}), {"c"})

    def test_a_test_never_enables_a_mod_without_what_it_needs(self):
        units = make_units(30)
        units[5] = Unit("m5", "Mod 5", added=units[5].added, requires=("m20",))
        s = Session(units, now=NOW)
        culprit = "m5"
        verdict, _ = drive(s, lambda e: culprit in e)
        self.assertEqual(verdict.keys, ("m5",))
        for test, _ in s.tests:
            if "m5" in test.enabled:
                self.assertIn("m20", test.enabled)


class Search(unittest.TestCase):
    def test_finds_the_culprit_in_few_launches(self):
        units = make_units(64)
        s = Session(units, now=NOW)
        verdict, launches = drive(s, lambda e: "m41" in e)
        self.assertEqual((verdict.kind, verdict.keys), ("culprit", ("m41",)))
        self.assertLessEqual(launches, 6 + 4)        # log2(64) splits + baseline, empty, fix, repro
        self.assertGreaterEqual(verdict.confidence, bc.CONFIDENCE)

    def test_a_recent_script_mod_is_found_faster_than_by_count(self):
        units = make_units(200)
        units[137] = Unit("m137", "Fresh script mod", added=NOW - 2 * DAY, kind="code", crash_hits=1)
        fast = Session(units, last_good=NOW - 20 * DAY, now=NOW)
        verdict, launches = drive(fast, lambda e: "m137" in e)
        self.assertEqual(verdict.keys, ("m137",))
        blind = Session([Unit(u.key, u.name) for u in units])
        _, blind_launches = drive(blind, lambda e: "m137" in e)
        self.assertLess(launches, blind_launches)
        self.assertLessEqual(launches, 4 + 2)

    def test_every_position_is_found(self):
        units = make_units(33)
        for i in range(33):
            verdict, launches = drive(Session(units, now=NOW), lambda e, i=i: f"m{i}" in e)
            self.assertEqual(verdict.keys, (f"m{i}",), i)
            self.assertLessEqual(launches, math.ceil(math.log2(33)) + 6)

    def test_pinned_framework_stays_on_in_every_test(self):
        units = make_units(20) + [Unit("fw", "Script extender", pinned=True)]
        s = Session(units, now=NOW)
        verdict, _ = drive(s, lambda e: "m3" in e)
        self.assertEqual(verdict.keys, ("m3",))
        self.assertTrue(all("fw" in t.enabled for t, _ in s.tests))


class Tangles(unittest.TestCase):
    def test_suspects_that_need_each_other_stop_with_a_clear_message(self):
        units = make_units(10)
        units[2] = Unit("m2", "Mod 2", added=units[2].added, requires=("m3",))
        units[3] = Unit("m3", "Mod 3", added=units[3].added, requires=("m2",))
        verdict, launches = drive(Session(units, now=NOW), lambda e: "m2" in e)
        self.assertLessEqual(launches, 12)
        self.assertTrue(verdict.kind in ("culprit", "undetermined"))
        if verdict.kind == "undetermined":
            self.assertIn("need each other", verdict.text)

    def test_always_on_mod_that_needs_a_mod_does_not_loop(self):
        units = make_units(12) + [Unit("fw", "Framework", pinned=True, requires=("m0",))]
        verdict, launches = drive(Session(units, now=NOW), lambda e: "m5" in e)
        self.assertEqual(verdict.keys, ("m5",))
        self.assertLess(launches, 14)


class NotAMod(unittest.TestCase):
    def test_crash_with_every_mod_off_is_reported_as_not_a_mod(self):
        s = Session(make_units(20), now=NOW)
        verdict, launches = drive(s, lambda e: True)
        self.assertEqual(verdict.kind, "outside")
        self.assertLessEqual(launches, 3)
        self.assertIn("not one of the mods", verdict.text)

    def test_no_crash_at_the_start_means_nothing_to_search(self):
        verdict, launches = drive(Session(make_units(20), now=NOW), lambda e: False)
        self.assertEqual((verdict.kind, launches), ("unreproducible", 1))


class Interaction(unittest.TestCase):
    def test_two_mods_that_only_crash_together_are_found(self):
        units = make_units(40)
        s = Session(units, now=NOW)
        verdict, _ = drive(s, lambda e: "m7" in e and "m31" in e, limit=120)
        self.assertEqual(verdict.kind, "interaction")
        self.assertEqual(set(verdict.keys), {"m7", "m31"})
        self.assertIn("together", verdict.text)

    def test_one_mod_is_not_blamed_for_a_pair(self):
        s = Session(make_units(24), now=NOW)
        verdict, _ = drive(s, lambda e: "m2" in e and "m9" in e, limit=120)
        self.assertNotEqual(verdict.kind, "culprit")


class Intermittent(unittest.TestCase):
    def test_flaky_crash_still_converges_without_clearing_mods_on_one_good_run(self):
        rng = random.Random(11)
        wins = 0
        for trial in range(12):
            s = Session(make_units(32), now=NOW, detect=0.7, runs=3)
            culprit = f"m{rng.randrange(32)}"
            verdict, _ = drive(s, lambda e, c=culprit: c in e, flaky=rng, limit=120)
            wins += verdict.keys == (culprit,)
        self.assertGreaterEqual(wins, 10)

    def test_a_flaky_verdict_states_its_uncertainty(self):
        s = Session(make_units(8), now=NOW, detect=0.7, runs=3)
        verdict, _ = drive(s, lambda e: "m4" in e, flaky=random.Random(2), limit=120)
        self.assertEqual(verdict.kind, "culprit")
        self.assertIn("not certain", verdict.text)

    def test_unreproducible_message_gives_the_miss_chance(self):
        verdict, _ = drive(Session(make_units(6), now=NOW, detect=0.5, runs=2), lambda e: False)
        self.assertEqual(verdict.kind, "unreproducible")
        self.assertIn("25%", verdict.text)

    def test_one_clean_run_does_not_clear_a_mod_when_crashes_are_rare(self):
        s = Session(make_units(10), now=NOW, detect=0.3, runs=1)
        step = s.next_step()
        s.record(step, "crash")
        step = s.next_step()                     # the empty check
        s.record(step, "ok")
        step = s.next_step()
        self.assertEqual(step.purpose, "search")
        s.record(step, "ok")                     # a single clean run at a 30% detection rate
        suspects = {u.key: p for u, p, _ in s.suspects()}
        self.assertTrue(all(p > bc.CLEARED for p in suspects.values()))


class Mistakes(unittest.TestCase):
    def test_undo_restores_the_earlier_belief(self):
        s = Session(make_units(16), now=NOW)
        a = s.next_step()
        s.record(a, "crash")
        before = [(u.key, round(p, 6)) for u, p, _ in s.suspects()]
        b = s.next_step()
        s.record(b, "ok")
        self.assertTrue(s.undo())
        self.assertEqual(before, [(u.key, round(p, 6)) for u, p, _ in s.suspects()])
        self.assertEqual(s.next_step(), b)

    def test_unsure_adds_no_evidence_and_repeats_the_test(self):
        s = Session(make_units(16), now=NOW)
        first = s.next_step()
        s.record(first, "unsure")
        self.assertEqual(s.next_step(), first)
        self.assertEqual(s.unsure, 1)

    def test_a_wrong_answer_is_recovered_not_trusted(self):
        units = make_units(32)
        s = Session(units, now=NOW, detect=0.95)
        wrong_done = False
        verdict = None
        for _ in range(100):
            step = s.next_step()
            if isinstance(step, Verdict):
                verdict = step
                break
            crashed = "m10" in step.enabled
            if step.purpose == "search" and not wrong_done:
                crashed, wrong_done = not crashed, True       # one mis-tap
            s.record(step, "crash" if crashed else "ok")
        self.assertIsNotNone(verdict)
        self.assertNotEqual(verdict.kind, "culprit") if verdict.keys != ("m10",) else None
        self.assertTrue(verdict.keys == ("m10",) or verdict.kind in ("undetermined", "interaction"))

    def test_bad_result_word_is_refused(self):
        s = Session(make_units(4), now=NOW)
        with self.assertRaises(ValueError):
            s.record(s.next_step(), "maybe")


class Report(unittest.TestCase):
    def test_report_lists_answers_and_does_not_overclaim(self):
        s = Session(make_units(8), now=NOW)
        drive(s, lambda e: "m1" in e)
        text = s.report()
        self.assertIn("baseline", text)
        self.assertIn("Only your test answers count as proof", text)
        self.assertNotIn("safe", text.lower())

    def test_empty_and_tiny_sets_do_not_crash(self):
        for units in ([], [Unit("only", "Only")]):
            s = Session(units, now=NOW)
            for _ in range(10):
                step = s.next_step()
                if isinstance(step, Verdict):
                    break
                s.record(step, "crash" if "only" in step.enabled else "ok")


if __name__ == "__main__":
    unittest.main()
