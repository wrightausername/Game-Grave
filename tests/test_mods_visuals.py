import unittest

from gg_desktop.mods_visuals import (count_tone, hue_for, initials, lit_segments, mix_parts, order_window,
                                     pill_colors, rail_fraction, share_parts, size_fraction, split_fractions)


class ModsVisualsTests(unittest.TestCase):
    def test_hue_is_stable_and_in_range(self):
        self.assertEqual(hue_for("Mountain Textures"), hue_for("mountain textures"))
        for name in ("a", "Skyrim", "Ünïcode", ""):
            self.assertTrue(0 <= hue_for(name) < 360)

    def test_initials(self):
        self.assertEqual(initials("Mountain Textures"), "MT")
        self.assertEqual(initials("framework"), "F")
        self.assertEqual(initials("  --  "), "?")
        self.assertEqual(initials("A B C D"), "AB")

    def test_segments_never_claim_more_than_the_counts(self):
        self.assertEqual(lit_segments(0, 5), 0)
        self.assertEqual(lit_segments(3, 5), 6)
        self.assertEqual(lit_segments(5, 5), 10)
        self.assertEqual(lit_segments(1, 400), 1, "one turned-on mod still lights a segment")
        self.assertEqual(lit_segments(3, 0), 0)
        self.assertEqual(lit_segments(9, 5), 10)

    def test_size_bar_needs_a_known_size(self):
        self.assertIsNone(size_fraction(None, 100))
        self.assertIsNone(size_fraction(5, 0))
        self.assertEqual(size_fraction(100, 100), 1.0)
        self.assertEqual(size_fraction(50, 100), 0.5)
        self.assertGreaterEqual(size_fraction(1, 10_000), 0.04)

    def test_share_parts_sum_to_one(self):
        parts = share_parts([842, 516, 38, 12, 96, None, 0])
        self.assertEqual(len(parts), 5)
        self.assertAlmostEqual(sum(parts), 1.0)
        self.assertEqual(parts, sorted(parts[:4], reverse=True) + parts[4:])
        self.assertEqual(share_parts([None, 0]), [])
        self.assertEqual(len(share_parts([5, 4, 3])), 3)

    def test_order_window(self):
        self.assertEqual(order_window(1, 12), (1, 5))
        self.assertEqual(order_window(6, 12), (4, 8))
        self.assertEqual(order_window(12, 12), (8, 12))
        self.assertEqual(order_window(2, 3), (1, 3))
        self.assertEqual(order_window(1, 0), (0, 0))

    def test_pill_colors(self):
        self.assertNotEqual(pill_colors("On"), pill_colors("Off"))
        self.assertEqual(pill_colors("Storage folder"), pill_colors("Not recorded"))


class TabGraphicsHelperTests(unittest.TestCase):
    def test_split_fractions_sum_to_one_and_need_mods(self):
        self.assertIsNone(split_fractions(0, 0, 0))
        on, off, unknown = split_fractions(3, 2, 0)
        self.assertAlmostEqual(on + off + unknown, 1.0)
        self.assertAlmostEqual(on, 0.6)
        self.assertEqual(split_fractions(1, 0), (1.0, 0.0, 0.0))

    def test_rail_fraction(self):
        self.assertEqual(rail_fraction(1, 5), 0.0)
        self.assertEqual(rail_fraction(5, 5), 1.0)
        self.assertEqual(rail_fraction(3, 5), 0.5)
        self.assertEqual(rail_fraction(1, 1), 0.5)
        for bad in (("-", 5), (0, 5), (6, 5), (None, 5), (2, 0)):
            self.assertIsNone(rail_fraction(*bad))

    def test_count_tone_is_quiet_for_zero_and_dash(self):
        self.assertEqual(count_tone("3", "amber"), "amber")
        self.assertEqual(count_tone("0", "amber"), "muted")
        self.assertEqual(count_tone("—", "amber"), "muted")

    def test_mix_parts_keep_every_count_true(self):
        parts = mix_parts({"Mod Organizer 2": 4, "Vortex": 0, "Added by you": 1, "A": 1, "B": 1, "C": 1, "D": 1})
        self.assertEqual(parts[0][:2], ("Mod Organizer 2", 4))
        self.assertEqual(parts[-1][:2], ("Other", 2))
        self.assertEqual(sum(p[1] for p in parts), 9)
        self.assertAlmostEqual(sum(p[2] for p in parts), 1.0)
        self.assertNotIn("Vortex", [p[0] for p in parts])
        self.assertEqual(mix_parts({}), [])


if __name__ == "__main__":
    unittest.main()
