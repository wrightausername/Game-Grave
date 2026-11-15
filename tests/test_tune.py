import unittest
from types import SimpleNamespace as NS

from gg_desktop import tune_core as tc


def comp(avg, low, comparable=True):
    rows = [NS(metric="Average FPS", verdict=avg[0], change=avg[1]), NS(metric="1% low FPS", verdict=low[0], change=low[1])]
    return NS(comparable=comparable, rows=rows, summary="too short")


class Tune(unittest.TestCase):
    def test_pinned_download(self):
        self.assertTrue(tc.PRESENTMON_URL.startswith("https://github.com/GameTechDev/PresentMon/releases/download/v2.4.1/"))
        self.assertEqual(len(tc.PRESENTMON_SHA256), 64)
        from gg_desktop.local_ai_core import host_allowed
        self.assertTrue(host_allowed(tc.PRESENTMON_URL))

    def test_script(self):
        s = tc.record_script(r"C:\GG\tools\PresentMon.exe", r"C:\Steam\common\ELDEN RING", r"C:\GG\cap's.csv", 120)
        self.assertIn("'C:\\Steam\\common\\ELDEN RING\\'", s)
        self.assertIn("'C:\\GG\\cap''s.csv'", s)
        self.assertIn("'120'", s)
        self.assertIn("-Verb RunAs", s)
        self.assertNotIn("$args =", s)
        self.assertIn("exit 3", s)

    def test_verdicts(self):
        self.assertTrue(tc.verdict(comp(("better", "+9.0%"), ("better", "+14.0%"))).keep)
        self.assertFalse(tc.verdict(comp(("worse", "-6%"), ("within noise", "+1%"))).keep)
        self.assertEqual(tc.verdict(comp(("better", "+5%"), ("worse", "-5%"))).title, "Mixed result")
        self.assertEqual(tc.verdict(comp(("within noise", "+1%"), ("within noise", "0%"))).title, "No real difference")
        self.assertEqual(tc.verdict(comp(("", ""), ("", ""), comparable=False)).title, "Not enough to compare")
        for v in (tc.verdict(comp(("better", "+9%"), ("better", "+1%"))),):
            self.assertNotIn("safe", v.detail.lower())


if __name__ == "__main__":
    unittest.main()
