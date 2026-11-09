import unittest

from gg_desktop.scan_clock import ScanClock, clock_text, eta_text


class ScanClockTests(unittest.TestCase):
    def test_no_estimate_until_something_finishes(self):
        clock = ScanClock(5)
        clock.start(100.0)
        self.assertIsNone(clock.remaining(103.0))
        self.assertEqual(eta_text(None), "Estimating time left…")

    def test_estimate_from_finished_stages(self):
        clock = ScanClock(5)
        clock.start(0.0)
        clock.advance(20, 10.0)          # first stage took 10 s
        self.assertAlmostEqual(clock.remaining(10.0), 40.0)
        self.assertAlmostEqual(clock.remaining(15.0), 35.0)

    def test_long_stage_is_not_almost_done(self):
        clock = ScanClock(5)
        clock.start(0.0)
        clock.advance(20, 10.0)
        left = clock.remaining(60.0)     # 50 s into a stage that usually takes 10 s
        self.assertGreater(left, 30.0)

    def test_previous_scan_seeds_the_first_estimate(self):
        clock = ScanClock(5, last_total=50.0)
        clock.start(0.0)
        self.assertAlmostEqual(clock.remaining(0.0), 50.0)

    def test_bar_never_runs_into_the_next_stage_and_finishes_at_one(self):
        clock = ScanClock(5)
        clock.start(0.0)
        clock.advance(40, 20.0)
        self.assertLess(clock.fraction(400.0), .6)
        self.assertGreaterEqual(clock.fraction(400.0), .4)
        clock.advance(100, 30.0)
        self.assertEqual(clock.fraction(31.0), 1.0)
        self.assertEqual(clock.remaining(31.0), 0.0)

    def test_text(self):
        self.assertEqual(clock_text(75), "1:15")
        self.assertEqual(eta_text(3), "A few seconds left")
        self.assertEqual(eta_text(42), "About 40 s left")
        self.assertEqual(eta_text(125), "About 2 min 05 s left")
        self.assertEqual(eta_text(120), "About 2 min left")


if __name__ == "__main__":
    unittest.main()
