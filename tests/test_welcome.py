import unittest

from gg_desktop import welcome_data


class WelcomeDataTests(unittest.TestCase):
    def test_shown_once(self):
        self.assertTrue(welcome_data.should_show({}))
        self.assertFalse(welcome_data.should_show(welcome_data.mark_seen({})))

    def test_not_shown_in_reference_preview_or_minimized(self):
        self.assertFalse(welcome_data.should_show({}, reference_preview=True))
        self.assertFalse(welcome_data.should_show({"start_minimized": True}))
        self.assertFalse(welcome_data.should_show(None))

    def test_mark_seen_keeps_other_keys(self):
        result = welcome_data.mark_seen({"scan_on_launch": True})
        self.assertEqual(result, {"scan_on_launch": True, "welcome_seen": True})

    def test_three_steps_three_points_last_button_scans(self):
        self.assertEqual(len(welcome_data.STEPS), 3)
        for step in welcome_data.STEPS:
            self.assertEqual(len(step["points"]), 3)
        self.assertEqual(welcome_data.next_label(0), "Next")
        self.assertEqual(welcome_data.next_label(welcome_data.LAST), "Scan my games")
        self.assertEqual(welcome_data.clamp(-4), 0)
        self.assertEqual(welcome_data.clamp(99), welcome_data.LAST)

    def test_honest_wording(self):
        text = " ".join(step["title"] + " " + step["body"] + " " + " ".join(a + " " + b for a, b in step["points"])
                        for step in welcome_data.STEPS).lower()
        for banned in ("safe to", "freed", "guarantee", "—", "–"):
            self.assertNotIn(banned, text)


if __name__ == "__main__":
    unittest.main()
