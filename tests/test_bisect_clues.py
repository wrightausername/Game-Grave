import random
import unittest
from datetime import datetime

from gg_desktop import bisect_clues as bcl
from gg_desktop.bisect_core import Session, Unit, Verdict

NOW = 1_800_000_000.0
DAY = 86400.0


class Crash:
    def __init__(self, when, module):
        self.when, self.module = when, module


def units(n=40):
    return [Unit(f"m{i}", f"Mod {i}", added=NOW - (100 - i) * DAY, kind="code" if i % 5 == 0 else "assets")
            for i in range(n)]


def files(n=40):
    return {f"m{i}": [f"plugins/thing{i}.dll", f"data/tex{i}.dds", "readme.txt"] for i in range(n)}


class Reading(unittest.TestCase):
    def test_files_named_in_reports_count_once_per_report(self):
        reports = [("Exception in thing7.dll at 0x00\nloaded tex7.dds and thing7.dll again", NOW),
                   ("stack: Thing7.DLL -> thing9.dll", NOW + 60), ("no mods here", None)]
        c = bcl.read_reports(units(), {k: v for k, v in files().items()}, reports)
        self.assertEqual(c.hits, {"m7": 2, "m9": 1})
        self.assertEqual(c.reports_read, 3)
        self.assertEqual(c.hint_keys[0], "m7")

    def test_a_file_name_shared_by_two_mods_is_not_blamed_on_either(self):
        c = bcl.read_reports(units(), files(), [("readme.txt was open", NOW)])
        self.assertEqual(c.hits, {})
        self.assertEqual(c.ambiguous, 1)

    def test_folder_names_in_paths_are_matched_but_generic_ones_are_not(self):
        us = units(5) + [Unit("data", "Data")]
        text = r"C:\Games\X\mods\Mod 3\scripts\a.pex failed; C:\Games\X\Data\other.esp"
        c = bcl.read_reports(us, {}, [(text, None)])
        self.assertEqual(c.hits, {"m3": 1})

    def test_faulting_module_from_windows_records_leads_the_hints(self):
        crashes = [Crash(datetime(2026, 11, 2, 20, 0), "thing12.dll"), Crash(datetime(2026, 11, 5, 9, 0), "ntdll.dll")]
        c = bcl.read_reports(units(), files(), [("thing3.dll", None), ("thing3.dll", None)], crashes)
        self.assertEqual(c.fault_keys, ("m12",))
        self.assertEqual(c.hint_keys, ("m12", "m3"))
        self.assertEqual(c.crash_count, 2)
        self.assertLess(c.first_crash, c.last_crash)
        self.assertTrue(any("not always the mod that caused it" in n for n in c.notes))

    def test_empty_and_unhelpful_input_says_so(self):
        self.assertIn("No crash reports", bcl.read_reports(units(), files()).notes[0])
        c = bcl.read_reports(units(), files(), [("totally unrelated text", None)])
        self.assertIn("did not name a file", c.notes[0])
        self.assertEqual(c.hint_keys, ())

    def test_garbage_input_does_not_crash(self):
        bcl.read_reports(units(), files(), [(None, None), ("\x00\xff" * 5000, 5.0)], [Crash(None, None)])

    def test_apply_hits_and_started_after(self):
        us = units()
        c = bcl.read_reports(us, files(), [("thing4.dll", NOW - 3 * DAY)])
        applied = bcl.apply_hits(us, c)
        self.assertEqual([u.crash_hits for u in applied if u.key == "m4"], [1])
        self.assertEqual(sum(u.crash_hits for u in applied), 1)
        recent = bcl.started_after(us, c, days=2)
        self.assertEqual(set(recent), {u.key for u in us if NOW - 5 * DAY <= u.added <= NOW - 3 * DAY})
        self.assertEqual(bcl.started_after(us, bcl.Clues()), ())


class InTheSearch(unittest.TestCase):
    def run_search(self, session, truth):
        n = 0
        while True:
            step = session.next_step()
            if isinstance(step, Verdict):
                return step, n
            n += 1
            session.record(step, "crash" if truth <= step.enabled else "ok")

    def test_a_right_report_clue_saves_launches_and_names_why(self):
        us = units(200)
        truth = {"m150"}
        plain, slow = self.run_search(Session(us, now=NOW), truth)
        s = Session(us, now=NOW, fault_keys=("m150",))
        self.assertIn("Windows recorded the crash inside one of its files", s.reasons["m150"])
        fast_v, fast = self.run_search(s, truth)
        self.assertEqual(fast_v.keys, ("m150",))
        self.assertLess(fast, slow)

    def test_a_wrong_report_clue_never_changes_the_answer(self):
        us = units(120)
        truth = {"m3", "m4", "m77"}
        c = bcl.Clues(hits={"m100": 3, "m101": 2}, fault_keys=("m110",))
        s = Session(bcl.apply_hits(us, c), now=NOW, fault_keys=c.fault_keys)
        verdict, _ = self.run_search(s, truth)
        self.assertEqual(set(verdict.keys), truth)

    def test_logged_mods_become_the_first_split_when_nothing_else_is_known(self):
        us = [Unit(f"m{i}", f"Mod {i}", crash_hits=2 if i in (5, 6) else 0) for i in range(30)]
        s = Session(us, now=NOW)
        self.assertEqual(s.priority, {"m5", "m6"})

    def test_random_clues_over_many_cases_never_give_a_wrong_answer(self):
        rng = random.Random(3)
        for _ in range(40):
            n = rng.choice([12, 50, 130])
            us = units(n)
            truth = set(f"m{i}" for i in rng.sample(range(n), rng.randint(1, 4)))
            c = bcl.Clues(hits={f"m{i}": rng.randint(1, 3) for i in rng.sample(range(n), 4)},
                          fault_keys=tuple(f"m{i}" for i in rng.sample(range(n), rng.randint(0, 2))))
            s = Session(bcl.apply_hits(us, c), now=NOW, fault_keys=c.fault_keys)
            verdict, _ = self.run_search(s, truth)
            self.assertEqual(set(verdict.keys), truth)


if __name__ == "__main__":
    unittest.main()
