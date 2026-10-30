"""Regression tests for reversible protections and Graveyard context actions."""
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from core import OldFile
from graveyard import build_graveyard
from graveyard_protection import protection_action, set_item_protection
from ui import GameGraveApp


class IndividualProtectionTests(unittest.TestCase):
    def test_protect_then_unprotect_only_exact_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = str(Path(tmp) / "skyrim-mod.zip")
            other = str(Path(tmp) / "fallout-mod.zip")
            self.assertEqual(protection_action(candidate, [])[0], "Protect")
            rules = set_item_protection([], candidate, protect=True)
            self.assertEqual(protection_action(candidate, rules)[0], "Unprotect")
            self.assertEqual(protection_action(other, rules)[0], "Protect")
            self.assertEqual(set_item_protection(rules, candidate, protect=False), [])

    def test_parent_protection_cannot_be_removed_from_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = str(Path(tmp) / "modpack.zip")
            self.assertEqual(protection_action(candidate, [tmp])[0], None)
            with self.assertRaises(ValueError):
                set_item_protection([tmp], candidate, protect=False)

    def test_builtin_protections_cannot_be_toggled(self):
        for protected in ("C:/Games/steamapps/common/game/mod.zip",
                          "C:/Users/Test/Saved Games/mod.zip",
                          "C:/Games/Mods/loadout.zip"):
            self.assertIsNone(protection_action(protected, [])[0])
            with self.assertRaises(ValueError):
                set_item_protection([], protected, protect=True)

    def test_added_protection_rebuilds_eligibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "skyrim-mod.zip"
            p.write_bytes(b"example")
            when = time.time()
            old = OldFile(str(p), p.stat().st_size, when - 900 * 86400)
            before = build_graveyard([], [], [old], 365, now=when)
            self.assertTrue(before[0].can_recycle)
            rules = set_item_protection([], str(p), protect=True)
            after = build_graveyard([], [], [old], 365, rules, now=when)
            self.assertFalse(after[0].can_recycle)


class ContextSafetyTests(unittest.TestCase):
    def test_right_click_selects_clicked_row_not_prior_selection(self):
        tree = Mock()
        tree.identify_row.return_value = "file:next"
        app = SimpleNamespace(grave_tree=tree, graveyard_lookup={"file:next": object()},
                              _grave_show_context=Mock())
        e = SimpleNamespace(y=5, x_root=200, y_root=300)
        GameGraveApp._grave_context_click(app, e)
        tree.selection_set.assert_called_once_with("file:next")
        tree.focus.assert_called_once_with("file:next")
        app._grave_show_context.assert_called_once_with(200, 300)

    def test_recycle_from_context_uses_existing_safe_workflow(self):
        self.assertIn("_grave_recycle_ids", GameGraveApp._grave_recycle_one.__code__.co_names)
        self.assertNotIn("recycle_file", GameGraveApp._grave_context_click.__code__.co_names)
        self.assertNotIn("recycle_file", GameGraveApp._grave_show_context.__code__.co_names)


if __name__ == "__main__":
    unittest.main()
