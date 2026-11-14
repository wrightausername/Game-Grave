import unittest

from gg_desktop import nav_groups


class NavGroupTests(unittest.TestCase):
    def test_five_groups_every_tab_once(self):
        self.assertEqual([h for h, _ in nav_groups.GROUPS], ["Home", "Library", "Clean Up", "Fix and Protect", "PC and Help"])
        routes = nav_groups.routes()
        self.assertEqual(len(routes), len(set(routes)))
        self.assertEqual(set(routes), {"Overview", "Ready Room", "Games", "Mods", "Captures", "Old Files", "Other Storage",
                                       "Graveyard", "Fix Kit", "Game DNA", "Undo Center", "Hardware", "More Tools",
                                       "AI Assistant", "Settings"})
        self.assertEqual(routes[-1], "Settings")

    def test_every_tab_has_a_short_plain_line(self):
        for route in nav_groups.routes():
            sub = nav_groups.subtitle(route)
            self.assertTrue(sub, route)
            self.assertLessEqual(len(sub), 36, route)
            for banned in ("—", "–", "safe to"):
                self.assertNotIn(banned, sub.lower())

    def test_shown_names(self):
        self.assertEqual(nav_groups.display_name("More Tools"), "Toolbox")
        self.assertEqual(nav_groups.display_name("Games"), "Games")
        self.assertEqual(nav_groups.group_of("Fix Kit"), "Fix and Protect")
        self.assertEqual(nav_groups.group_of("Nope"), "")

    def test_dropdown_accordion(self):
        self.assertEqual(nav_groups.toggled("Home", "Library"), "Library")
        self.assertEqual(nav_groups.toggled("Library", "Library"), "")
        self.assertEqual(nav_groups.toggled("", "Clean Up"), "Clean Up")
        self.assertEqual(nav_groups.open_for("Hardware", "Home"), "PC and Help")
        self.assertEqual(nav_groups.open_for("Nope", "Home"), "Home")

    def test_every_route_has_a_symbol_and_banner(self):
        import re
        from pathlib import Path
        root = Path(__file__).resolve().parents[1] / "gg_desktop"
        widgets = (root / "reference_widgets.py").read_text(encoding="utf-8")
        banners = (root / "header_banner.py").read_text(encoding="utf-8")
        for route in nav_groups.routes():
            self.assertRegex(widgets, re.escape(f'"{route}":'), route)
            self.assertIn(f'"{route}":', banners, route)


if __name__ == "__main__":
    unittest.main()
