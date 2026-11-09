import tempfile
import unittest
from pathlib import Path

from gg_desktop import autopsy_core as au


def frames(ms, count=1200, spike=None, every=100):
    out = [ms] * count
    if spike:
        for i in range(0, count, every):
            out[i] = spike
    return out


def csv_text(values, column="MsBetweenPresents"):
    rows = ["Application,ProcessID," + column + ",Dropped"]
    rows += [f"game.exe,42,{v},0" for v in values]
    return "\n".join(rows) + "\n"


class AutopsyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, text, encoding="utf-8"):
        path = self.root / name
        path.write_bytes(text.encode(encoding))
        return path

    def test_reads_columns_bom_and_skips_junk(self):
        path = self.write("a.csv", "﻿" + csv_text([16.0, "n/a", -3, 0, 17.0]) + "short\n", "utf-8")
        self.assertEqual(au.read_capture(path), [16.0, 17.0])
        self.assertEqual(au.read_capture(self.write("b.csv", csv_text([10.0], "FrameTime"))), [10.0])

    def test_refuses_things_that_are_not_captures(self):
        with self.assertRaises(au.CaptureError):
            au.read_capture(self.write("c.csv", "a,b\n1,2\n"))
        with self.assertRaises(au.CaptureError):
            au.read_capture(self.write("d.csv", ""))
        with self.assertRaises(au.CaptureError):
            au.read_capture(self.write("e.csv", csv_text(["x", "y"])))
        with self.assertRaises(au.CaptureError):
            au.read_capture(self.root / "missing.csv")

    def test_stats_are_plain_arithmetic(self):
        s = au.stats_for(frames(10.0))
        self.assertAlmostEqual(s.avg_fps, 100.0)
        self.assertAlmostEqual(s.low1_fps, 100.0)
        self.assertEqual((s.spikes, s.wobble), (0, 0.0))
        spiky = au.stats_for(frames(10.0, spike=50.0, every=50))
        self.assertEqual(spiky.spikes, 24)
        self.assertEqual(spiky.longest_ms, 50.0)
        self.assertLess(spiky.low1_fps, spiky.avg_fps)

    def test_downsample_keeps_the_spike(self):
        data = frames(10.0, spike=80.0, every=500)
        small = au.downsample_max(data, 50)
        self.assertEqual(len(small), 50)
        self.assertEqual(max(small), 80.0)
        self.assertEqual(au.downsample_max([1.0, 2.0], 50), [1.0, 2.0])
        self.assertEqual(au.downsample_max([], 5), [])

    def test_clear_improvement_is_called_better(self):
        c = au.compare(au.stats_for(frames(16.7, spike=40.0)), au.stats_for(frames(11.1, spike=20.0)))
        self.assertTrue(c.comparable)
        verdicts = {r.metric: r.verdict for r in c.rows}
        self.assertEqual(verdicts["Average FPS"], "better")
        self.assertEqual(verdicts["Median frame time (ms)"], "better")
        self.assertIn("One capture each", c.summary)

    def test_identical_captures_are_within_noise(self):
        c = au.compare(au.stats_for(frames(12.0)), au.stats_for(frames(12.1)))
        self.assertTrue(all(r.verdict == "within noise" for r in c.rows if r.metric == "Average FPS"))
        self.assertIn("no difference it can stand behind", c.summary)

    def test_a_wobbly_capture_widens_the_noise(self):
        wobbly = [10.0] * 600 + [12.5] * 600
        steady = frames(10.0)
        c = au.compare(au.stats_for(steady), au.stats_for(wobbly))
        average = next(r for r in c.rows if r.metric == "Average FPS")
        self.assertEqual(average.verdict, "within noise")

    def test_short_captures_are_not_compared(self):
        c = au.compare(au.stats_for(frames(10.0, count=100)), au.stats_for(frames(10.0)))
        self.assertFalse(c.comparable)
        self.assertEqual(c.rows, [])
        self.assertIn("will not draw a conclusion", c.summary)

    def test_report_text_names_files_and_keeps_caveat(self):
        c = au.compare(au.stats_for(frames(16.7)), au.stats_for(frames(11.1)))
        text = au.report_text("Soulbind applied", "before.csv", "after.csv", c)
        self.assertIn("Change: Soulbind applied", text)
        self.assertIn("Average FPS", text)
        self.assertIn("One capture each", text)


if __name__ == "__main__":
    unittest.main()
