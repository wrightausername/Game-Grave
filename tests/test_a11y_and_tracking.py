"""Pure parts of the accessibility pass and the game-tracker pacing."""
import unittest

from gg_desktop.a11y import derive_name


class Names(unittest.TestCase):
    def test_text_then_placeholder_then_tooltip(self):
        self.assertEqual(derive_name("&Scan PC"), "Scan PC")
        self.assertEqual(derive_name("", "Opens the folder. Nothing is changed."), "Opens the folder")
        self.assertEqual(derive_name("", "", "Search mods…"), "Search mods")
        self.assertEqual(derive_name("", "", "", "Choice list"), "Choice list")
        self.assertEqual(derive_name("…", ""), "")
        self.assertLessEqual(len(derive_name("x" * 300)), 80)


class Pacing(unittest.TestCase):
    def test_intervals_stay_under_the_playtime_gap(self):
        import importlib.util
        if importlib.util.find_spec("PySide6") is None:
            self.skipTest("PySide6 is not installed here")
        from gg_desktop import games_tracking as t
        self.assertEqual(t.next_interval({"a"}, 0), t.PLAYING)
        self.assertEqual(t.next_interval(set(), 0), t.FAST)
        self.assertEqual(t.next_interval(set(), t.QUIET_AFTER), t.QUIET)
        self.assertTrue(all(ms <= 20000 for ms in (t.FAST, t.PLAYING, t.QUIET)))


if __name__ == "__main__":
    unittest.main()
