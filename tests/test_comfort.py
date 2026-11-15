"""Back, notices, shortcuts and diagnostics rules."""
import unittest

from gg_desktop import comfort_core as core


class ComfortTest(unittest.TestCase):
    def test_back_history(self):
        h = core.History()
        for route in ("Overview", "Games", "Games", "Mods", "Hardware"):
            h.visit(route)
        self.assertTrue(h.can_back())
        self.assertEqual(h.back(), "Mods")
        h.visit("Mods", going_back=True)
        self.assertEqual(h.back(), "Games")
        h.visit("Games", going_back=True)
        self.assertEqual(h.back(), "Overview")
        h.visit("Overview", going_back=True)
        self.assertFalse(h.can_back())
        self.assertEqual(h.back(), "")

    def test_notices_keep_newest_forty_and_survive_bad_settings(self):
        notices = []
        for n in range(45):
            notices = core.add_notice(notices, core.notice(f"Job {n}", "done", now=1000 + n))
        self.assertEqual(len(notices), core.MAX_NOTICES)
        self.assertEqual(notices[0].title, "Job 44")
        self.assertEqual(core.unread(notices), 40)
        settings = core.with_notices({}, core.mark_read(notices))
        back = core.load_notices(settings)
        self.assertEqual(core.unread(back), 0)
        self.assertEqual(core.load_notices({"notices": [{"bad": 1}, "junk", {"title": "ok", "at": 5}]})[0].title, "ok")
        self.assertEqual(core.notice("t", "x", tone="weird").tone, "info")

    def test_ago(self):
        self.assertEqual(core.ago(100, 130), "just now")
        self.assertEqual(core.ago(0, 600), "10 min ago")
        self.assertEqual(core.ago(0, 3600), "1 hour ago")
        self.assertEqual(core.ago(0, 3 * 86400), "3 days ago")

    def test_shortcuts_and_numbers(self):
        order = ("Overview", "Ready Room", "Games", "Mods", "Captures", "Old Files", "Other Storage", "Graveyard",
                 "Game DNA", "Fix Kit", "Undo Center")
        self.assertEqual(core.numbered_routes(order, set(order) - {"Ready Room"})[:3], ["Overview", "Games", "Mods"])
        self.assertEqual(len(core.numbered_routes(order, set(order))), 9)
        for keys, what in core.SHORTCUTS:
            self.assertTrue(keys and what)
            self.assertNotIn("—", what)

    def test_diagnostics_hide_the_user_name(self):
        text = core.diagnostics_text("0.2.1", "Windows-11", {"scanned_at": "2026-11-14 17:40", "games": 3},
                                     [r"Old Files folder C:\Users\alex\Downloads unavailable"],
                                     [r"Kit failed: D:\Other\alex\kit.zip"], [], {"autopilot_on": True},
                                     home=r"C:\Users\alex", user="alex")
        self.assertNotIn("alex", text)
        self.assertIn("%USERPROFILE%", text)
        self.assertIn("autopilot_on=on", text)
        self.assertIn("games: 3", text)

    def test_paused_text(self):
        self.assertEqual(core.paused_text([]), "")
        self.assertEqual(core.paused_text(["Elden Ring"]), "Paused while you play Elden Ring")
        self.assertEqual(core.paused_text(["Elden Ring", "Doom"]), "Paused while you play Elden Ring +1")
        self.assertEqual(core.run_command(r"C:\GG\GameGrave.exe"), '"C:\\GG\\GameGrave.exe" --minimized')


if __name__ == "__main__":
    unittest.main()


class ScrubOtherProfiles(unittest.TestCase):
    def test_any_profile_name_goes(self):
        from gg_desktop.comfort_core import scrub
        out = scrub(r"Old Files folder C:\Users\someone\Downloads unavailable", home=r"C:\Users\me", user="me")
        self.assertNotIn("someone", out)
        self.assertIn(r"C:\Users\<user>\Downloads", out)
        self.assertIn(r"C:\Users\Public", scrub(r"C:\Users\Public\Games", home="", user=""))

