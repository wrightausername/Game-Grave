"""Native Qt navigation regression tests, no user file or registry changes."""
from __future__ import annotations
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    from core import default_settings
    from gg_desktop.app import CrimsonWindow
    QT_OK = True
except ImportError:
    QT_OK = False


@unittest.skipUnless(QT_OK, "Qt UI dependencies unavailable")
class RouteHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_window(self):
        with patch("gg_desktop.app.load_settings", return_value=default_settings()):
            window = CrimsonWindow()
        self.addCleanup(window.close)
        return window

    def test_every_page_has_persistent_navigation(self):
        w = self.make_window()
        for route in ("Games", "Mods", "Old Files", "Other Storage",
                      "Captures", "Graveyard", "Game DNA", "Undo Center"):
            w.navigate(route)
            self.assertIsNotNone(w.back_button)
            self.assertTrue(w.back_button.isEnabled(), route)
            self.assertIn(route.upper(), w.breadcrumbs.text())
            self.assertEqual(w.back_button.parent().objectName(), "routeNavigationBar")
            self.assertTrue(w.home_button.isEnabled())

    def test_back_and_home_use_real_stack(self):
        w = self.make_window()
        self.assertEqual(w.current_route, "Overview")
        self.assertFalse(w.back_button.isEnabled())
        w.navigate("Games")
        w.navigate("Mods")
        w.navigate("Other Storage")
        self.assertEqual(w._navigation_history[-1], "Mods")
        w.go_back()
        self.assertEqual(w.current_route, "Mods")
        w.go_back()
        self.assertEqual(w.current_route, "Games")
        w.go_back()
        self.assertEqual(w.current_route, "Overview")
        self.assertFalse(w.back_button.isEnabled())
        w.navigate("Ready Room")
        self.assertFalse(w.home_button.isEnabled())

    def test_same_route_does_not_duplicate_back_history(self):
        w = self.make_window()
        w.navigate("Games")
        count = len(w._navigation_history)
        w.navigate("Games")
        self.assertEqual(len(w._navigation_history), count)


if __name__ == "__main__":
    unittest.main()
