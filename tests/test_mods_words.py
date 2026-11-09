import unittest

from gg_desktop import mods_words as w


class ModsWordsTests(unittest.TestCase):
    def test_status_words_are_plain(self):
        self.assertEqual([w.status_word(x) for x in ("Enabled", "Disabled", "Mixed", "Unknown", "Protected")],
                         ["On", "Off", "On in some", "Not recorded", "Storage folder"])
        self.assertEqual(w.status_word("Something else"), "Something else")

    def test_summary_says_what_is_known_and_what_is_partial(self):
        m = {"total": 5, "total_label": "Total Mods", "enabled": 3, "mixed": 0, "disabled": 2,
             "outdated": 1, "conflicts": 2, "conflicts_limited": True}
        self.assertEqual(w.summary(m, games=2),
                         "You have 5 mods for 2 games, 3 turned on, 1 update available, 2 conflicts found (some may be missed).")

    def test_summary_without_evidence_does_not_guess(self):
        m = {"total": 4, "total_label": "Mod Locations", "enabled": 0, "mixed": 0, "disabled": 0,
             "outdated": None, "conflicts": None, "conflicts_limited": False}
        self.assertEqual(w.summary(m), "You have 4 mod folders.")
        self.assertIn("Scan your PC", w.summary({"total": 0}))

    def test_detail_lines(self):
        self.assertEqual(w.order_text(5, 12, "Default"), "#5 of 12 · Default")
        self.assertEqual(w.requires_text([], False), "Doesn't list any other mods it needs")
        self.assertEqual(w.requires_text(["A", "B"], True), "Needs 3 other mods: A, B …")
        self.assertEqual(w.conflicts_text(0, True, True), "None found (the check was partial)")
        self.assertEqual(w.conflicts_text(1, False, True), "1 conflict found")
        self.assertEqual(w.conflicts_text(0, False, False), "Not checked yet")
        self.assertEqual(w.profiles_text([]), "Not in any saved profile")
        self.assertEqual(w.profiles_text(["Default"]), "In 1 profile: Default")
        self.assertEqual(w.update_text("2.5", "2.0", True, ""), "Version 2.5 is available (you have 2.0)")


if __name__ == "__main__":
    unittest.main()
