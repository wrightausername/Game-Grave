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



class UndoAfterRemoval(unittest.TestCase):
    def test_only_new_records_are_offered(self):
        from gg_desktop import comfort_core as c
        old = [{"id": "a", "path": r"C:\Games\old.txt", "size": 5}]
        new = old + [{"id": "b", "path": r"D:\Mods\big.zip", "size": 2048}, {"id": "c", "path": r"D:\x", "state": "Restored"}]
        rows = c.new_removals(c.record_ids(old), new)
        self.assertEqual([r["id"] for r in rows], ["b"])
        self.assertIn("big.zip went to the Windows Recycle Bin", c.undo_text(rows))
        self.assertEqual(c.undo_text([]), "")
        self.assertIn("2 items", c.undo_text(rows * 2))

    def test_confirmation_names_paths_and_limit(self):
        from gg_desktop import comfort_core as c
        rows = [{"id": str(i), "path": f"C:\\f{i}"} for i in range(25)]
        text = c.undo_confirmation(rows)
        self.assertIn("C:\\f0", text)
        self.assertNotIn("C:\\f24", text)
        self.assertIn("5 more are in the Undo Center", text)
        self.assertIn("nothing that already exists at the original place is overwritten", text)
        self.assertNotIn("safe to remove", text.lower())


class RememberViews(unittest.TestCase):
    def test_only_sort_and_filter_kept(self):
        from gg_desktop import comfort_core as c
        self.assertTrue(c.remembers("Sort games"))
        self.assertTrue(c.remembers("Filter by launcher"))
        self.assertFalse(c.remembers("Search games"))
        self.assertFalse(c.remembers(None))

    def test_round_trip_and_bounds(self):
        from gg_desktop import comfort_core as c
        s = c.with_view({}, "Games", "Sort games", "Name A to Z")
        self.assertEqual(c.remembered(s, "Games", "Sort games"), "Name A to Z")
        self.assertIsNone(c.remembered(s, "Mods", "Sort games"))
        for i in range(40):
            s = c.with_view(s, f"Tab {i}", "Sort x", "y")
        self.assertLessEqual(len(c.views_of(s)), 30)
        self.assertEqual(c.views_of({c.VIEWS_KEY: ["junk"]}), {})
        self.assertNotIn(c.VIEWS_KEY, c.without_views(s))
