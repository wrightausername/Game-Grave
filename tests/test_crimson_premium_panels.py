"""Regression checks for scan-grounded Crimson visual grouping."""
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

try:
    from PySide6.QtWidgets import QApplication
    from gg_desktop.premium_panels import (
        GameInspector, ModInspector, group_mod_locations, mod_gallery,
    )
    QT_OK = True
except ImportError:
    QT_OK = False


@unittest.skipUnless(QT_OK, "PySide6 preview dependencies not installed")
class PremiumPanelsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication([])

    def _game(self, root):
        return SimpleNamespace(
            key="Steam:123", name="Example", launcher="Steam",
            app_id="123", install_path=str(root),
            size_bytes=None, size_source="Unknown",
            last_played_at=None, status="Installed",
            capabilities=("inspect", "open_folder"))

    def test_mod_groups_rely_on_verified_root_not_similar_name(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td) / "Example"
            another = Path(td) / "Example-old"
            internal = SimpleNamespace(path=str(folder / "Data" / "Mods"), source="Local")
            external = SimpleNamespace(path=str(another / "Data" / "Mods"), source="External")
            groups, unknown = group_mod_locations([self._game(folder)], [internal, external])
            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0][1], [internal])
            self.assertEqual(unknown, [external])

    def test_game_inspector_does_not_fake_unknown_metrics(self):
        with tempfile.TemporaryDirectory() as td:
            game = self._game(td)
            panel = GameInspector(lambda g: None, lambda g: None,
                                  lambda: None, lambda: None)
            panel.set_game(game)
            self.assertIn("unavailable", panel.size.text().lower())
            self.assertIn("Unknown", panel.last.text())
            self.assertEqual(panel.game, game)
            self.assertTrue(panel.details_btn.isEnabled())
            panel.set_game(None)
            self.assertFalse(panel.details_btn.isEnabled())

    def test_mod_gallery_has_no_fake_card_without_findings(self):
        with tempfile.TemporaryDirectory() as td:
            gallery, groups, unmatched = mod_gallery(
                [self._game(td)], [], lambda *args: None)
            self.assertEqual(groups, [])
            self.assertEqual(unmatched, [])
            inspector = ModInspector(lambda _: None, lambda _: None, lambda: None)
            self.assertFalse(inspector.review_btn.isEnabled())
            self.assertFalse(inspector.open_btn.isEnabled())
            gallery.deleteLater()
