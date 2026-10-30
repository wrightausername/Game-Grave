"""M1 no-overwrite and symlink-ancestor regression tests.

Tests use disposable temporary files, never the user's Recycle Bin or games.
Windows live Shell verification is a separate manual QA requirement.
"""
import os
import tempfile
import unittest
from pathlib import Path

import core
from resurrection_v2 import (_ordinary_ancestry, _publish_no_replace,
                             _relative_name, create_complete_kit, inspect_restore)


class MilestoneOneSafetyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_windows_reserved_superscript_device_names_rejected(self):
        for alias in ("COM¹", "COM².txt", "COM³.bin",
                      "LPT¹", "LPT².jpg", "LPT³.7z"):
            with self.subTest(alias=alias), self.assertRaises(ValueError):
                _relative_name("Mods/" + alias)
        self.assertEqual(_relative_name("Saves/合法文件.txt"),
                         ("Saves", "合法文件.txt"))

    def test_atomic_no_replace_never_clobbers_preexisting_target(self):
        new = self.root / "partial"
        existing = self.root / "already exists.zip"
        new.write_text("new")
        existing.write_text("user's irreplaceable old archive")
        with self.assertRaises(FileExistsError):
            _publish_no_replace(new, existing)
        self.assertEqual(existing.read_text(), "user's irreplaceable old archive")
        self.assertEqual(new.read_text(), "new")

    def test_atomic_publication_preserves_file_bytes(self):
        staged = self.root / "snapshot.partial"
        published = self.root / "snapshot.zip"
        staged.write_bytes(b"verified archive bytes")
        _publish_no_replace(staged, published)
        self.assertFalse(staged.exists())
        self.assertEqual(published.read_bytes(), b"verified archive bytes")

    def test_ordinary_kit_still_creates_and_verifies(self):
        saves = self.root / "Game Saves"
        saves.mkdir()
        (saves / "slot.sav").write_bytes(b"safe")
        kit = create_complete_kit("Example", {"Saves": saves},
                                  self.root / "example.zip")
        self.assertTrue(inspect_restore(Path(kit["manifest"]))["verified"])

    def test_parent_symlink_rejected_by_recycle_preflight_and_kit_validation(self):
        safe = self.root / "Safe"
        safe.mkdir()
        (safe / "save.dat").write_bytes(b"game progress")
        link = self.root / "Redirect"
        try:
            link.symlink_to(safe, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("This Windows runner does not allow test symlinks")
        self.assertTrue(core._has_reparse_component(link / "save.dat"))
        self.assertFalse(_ordinary_ancestry(link / "save.dat"))
        self.assertFalse(_ordinary_ancestry(link, directory=True))
        with self.assertRaises(ValueError):
            create_complete_kit("Bad", {"Saves": link}, self.root / "bad.zip")
        self.assertFalse((self.root / "bad.zip").exists())

    def test_no_reparse_component_on_an_ordinary_file(self):
        ordinary = self.root / "ordinary.txt"
        ordinary.write_bytes(b"example")
        self.assertFalse(core._has_reparse_component(ordinary))
        self.assertTrue(_ordinary_ancestry(ordinary))


if __name__ == "__main__":
    unittest.main()
