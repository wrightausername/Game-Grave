import unittest

from gg_desktop import nav_groups


class NavGroupTests(unittest.TestCase):
    def test_sections_every_tab_once(self):
        self.assertEqual([label for label, _ in nav_groups.SECTIONS], ["", "Keep it running", "More"])
        self.assertEqual([e for _s, e, _r, _p in nav_groups.entries()],
                         ["Home", "Games", "Mods", "Deals", "Fix a game", "Free up space", "My PC", "Captures", "Game DNA",
                          "Toolbox", "Assistant", "Undo", "Settings"])
        routes = nav_groups.routes()
        self.assertEqual(len(routes), len(set(routes)))
        self.assertEqual(set(routes), {"Overview", "Ready Room", "Games", "Deals", "Mods", "Captures", "Old Files", "Other Storage",
                                       "Graveyard", "Fix Kit", "Game DNA", "Undo Center", "Hardware", "More Tools",
                                       "AI Assistant", "Settings"})
        self.assertEqual(routes[-1], "Settings")
        self.assertLessEqual(len(nav_groups.entries()), 13, "the sidebar shows 13 entries at most")

    def test_every_tab_has_a_short_plain_line(self):
        for route in nav_groups.routes():
            sub = nav_groups.subtitle(route)
            self.assertTrue(sub, route)
            self.assertLessEqual(len(sub), 36, route)
            for banned in ("—", "–", "safe to"):
                self.assertNotIn(banned, sub.lower())

    def test_hubs_and_names(self):
        self.assertEqual(nav_groups.routes_of("Free up space"), ("Old Files", "Other Storage", "Graveyard"))
        self.assertEqual(nav_groups.routes_of("Home"), ("Overview", "Ready Room"))
        self.assertTrue(nav_groups.is_hub("Home") and not nav_groups.is_hub("Games"))
        self.assertEqual(nav_groups.entry_of("Graveyard"), "Free up space")
        self.assertEqual(nav_groups.entry_of("Fix Kit"), "Fix a game")
        self.assertEqual(nav_groups.entry_of("Hardware"), "My PC")
        self.assertEqual(nav_groups.display_name("More Tools"), "Toolbox")
        self.assertIn("Fix Kit", nav_groups.tip("Fix a game"))
        self.assertEqual(nav_groups.entry_of("Nope"), "")

    def test_a_hub_remembers_the_last_tab(self):
        self.assertEqual(nav_groups.hub_target("Free up space", {}), "Old Files")
        self.assertEqual(nav_groups.hub_target("Free up space", {"Free up space": "Graveyard"}), "Graveyard")
        self.assertEqual(nav_groups.hub_target("Free up space", {"Free up space": "Games"}), "Old Files", "never outside")
        self.assertEqual(nav_groups.hub_target("Games", {}), "Games")

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
