"""M4 keyboard navigation and safe scan-cancel shortcuts.

No display, Windows user files, scans, or dialogs are opened by these tests.
"""
import unittest
from types import SimpleNamespace

from ui_shortcuts import PAGE_SHORTCUTS, PAGE_KEYS, ACTION_SHORTCUTS, shortcut_help_text
from ui import GameGraveApp


class FakeApp:
    def __init__(self):
        self.shortcuts = {}
        self.calls = []
        self.scanning = False
        self.nav_buttons = {}
        self.scan_button = SimpleNamespace(focus_set=lambda: self.calls.append("focused scan"))

    def bind(self, key, callback):
        self.shortcuts[key] = callback

    def show_page(self, page):
        self.calls.append(("page", page))

    def scan_all(self):
        self.calls.append("scan")

    def _cancel_active_scan(self):
        self.calls.append("cancel")

    _navigate_shortcut = GameGraveApp._navigate_shortcut
    _shortcut_scan = GameGraveApp._shortcut_scan
    _shortcut_cancel_scan = GameGraveApp._shortcut_cancel_scan
    _open_keyboard_shortcuts = GameGraveApp._open_keyboard_shortcuts


class KeyboardAccessTests(unittest.TestCase):
    def test_every_shortcut_navigates_only_to_known_read_only_page(self):
        self.assertEqual(len(PAGE_SHORTCUTS), 7)
        self.assertEqual(len(set(PAGE_KEYS)), 7)
        all_pages = {name for _, _, name in PAGE_SHORTCUTS}
        self.assertEqual(all_pages, {
            "Overview", "Game DNA", "Game Mods", "The Graveyard",
            "Save Vault", "Resurrection Lab", "Undo Center",
        })
        self.assertNotIn("delete", shortcut_help_text().lower())
        self.assertNotIn("recycle", repr(PAGE_SHORTCUTS).lower())

    def test_bindings_have_7_pages_help_scan_and_cancel(self):
        fake = FakeApp()
        GameGraveApp._install_keyboard_shortcuts(fake)
        self.assertEqual(set(fake.shortcuts), {
            *(f"<Control-KeyPress-{i}>" for i in range(1, 8)),
            "<F1>", "<F5>", "<Escape>",
        })
        fake.shortcuts["<Control-KeyPress-4>"](None)
        self.assertEqual(fake.calls, [("page", "The Graveyard"), "focused scan"])

    def test_f5_uses_explicit_scan_button_logic_and_refuses_double_start(self):
        fake = FakeApp()
        self.assertEqual(GameGraveApp._shortcut_scan(fake), "break")
        self.assertEqual(fake.calls, ["scan"])
        fake.scanning = True
        self.assertEqual(GameGraveApp._shortcut_scan(fake), "break")
        self.assertEqual(fake.calls, ["scan"])

    def test_escape_only_cancels_when_scan_is_running(self):
        fake = FakeApp()
        self.assertIsNone(GameGraveApp._shortcut_cancel_scan(fake))
        self.assertFalse(fake.calls)
        fake.scanning = True
        self.assertEqual(GameGraveApp._shortcut_cancel_scan(fake), "break")
        self.assertEqual(fake.calls, ["cancel"])

    def test_f1_guide_is_readable_and_explains_safe_focus(self):
        guide = shortcut_help_text()
        for shortcut, *_ in PAGE_SHORTCUTS:
            self.assertIn(shortcut, guide)
        for shortcut, _ in ACTION_SHORTCUTS:
            self.assertIn(shortcut, guide)
        self.assertIn("Tab / Shift+Tab", guide)
        self.assertIn("approval dialogs", guide)


if __name__ == "__main__":
    unittest.main()
