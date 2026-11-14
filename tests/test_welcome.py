import unittest

from gg_desktop import welcome_data as w


class WelcomeTourTests(unittest.TestCase):
    def test_shows_at_startup_until_turned_off(self):
        self.assertTrue(w.should_show({}))
        self.assertTrue(w.should_show({w.STARTUP_KEY: True}))
        self.assertFalse(w.should_show({w.STARTUP_KEY: False}))

    def test_not_in_reference_preview_or_minimized(self):
        self.assertFalse(w.should_show({}, reference_preview=True))
        self.assertFalse(w.should_show({"start_minimized": True}))
        self.assertFalse(w.should_show(None))

    def test_skip_keeps_it_finishing_or_the_box_turns_it_off(self):
        self.assertTrue(w.startup_after(finished=False, dont_show=False, current=True))
        self.assertFalse(w.startup_after(finished=False, dont_show=False, current=False))
        self.assertFalse(w.startup_after(finished=True, dont_show=False, current=True))
        self.assertFalse(w.startup_after(finished=False, dont_show=True, current=True))

    def test_with_startup_keeps_other_keys(self):
        self.assertEqual(w.with_startup({"scan_on_launch": True}, False), {"scan_on_launch": True, w.STARTUP_KEY: False})

    def test_tour_covers_every_sidebar_group(self):
        self.assertGreaterEqual(len(w.STEPS), 7)
        text = " ".join(s["title"] + " " + s["body"] + " " + " ".join(a + " " + b for a, b in s["points"]) for s in w.STEPS)
        from gg_desktop import nav_groups
        for route in nav_groups.routes():
            shown = nav_groups.display_name(route)
            if route in ("Settings",):
                continue
            self.assertIn(shown, text, route)
        for step in w.STEPS:
            self.assertTrue(2 <= len(step["points"]) <= w.MAX_POINTS <= 4)

    def test_buttons(self):
        self.assertEqual(w.next_label(0), "Next")
        self.assertEqual(w.next_label(w.LAST), "Scan my games")
        self.assertEqual(w.close_label(0), "Skip intro")
        self.assertEqual(w.close_label(w.LAST), "Close")
        self.assertEqual(w.step_caption(0), f"1 of {len(w.STEPS)}")
        self.assertEqual(w.clamp(-4), 0)
        self.assertEqual(w.clamp(99), w.LAST)

    def test_honest_wording(self):
        text = " ".join(s["title"] + " " + s["body"] + " " + " ".join(a + " " + b for a, b in s["points"])
                        for s in w.STEPS).lower()
        for banned in ("safe to", "freed", "guarantee", "—", "–"):
            self.assertNotIn(banned, text)


if __name__ == "__main__":
    unittest.main()
