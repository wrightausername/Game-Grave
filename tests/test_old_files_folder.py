"""The PC scan's Old Files step never shows a raw "ValueError": it falls back to the real Downloads folder and says why."""
import unittest
from pathlib import Path

from gg_desktop import backend


class OldFilesFolder(unittest.TestCase):
    def test_the_chosen_folder_when_it_works(self):
        folder, note = backend.old_files_folder({"scan_folder": "D:/Stuff"}, ok=lambda p: True, downloads=None)
        self.assertEqual(folder, Path("D:/Stuff"))
        self.assertEqual(note, "")

    def test_moved_downloads_when_the_chosen_folder_cant_be_scanned(self):
        ok = lambda p: str(p).replace("\\", "/") == "E:/Downloads"
        folder, note = backend.old_files_folder({"scan_folder": "C:/"}, ok=ok, downloads=Path("E:/Downloads"))
        self.assertEqual(folder, Path("E:/Downloads"))
        self.assertIn("instead of your chosen folder", note)
        self.assertNotIn("ValueError", note)

    def test_no_choice_uses_downloads_quietly(self):
        folder, note = backend.old_files_folder({}, ok=lambda p: True, downloads=Path("E:/Downloads"))
        self.assertEqual(folder, Path("E:/Downloads"))
        self.assertEqual(note, "")

    def test_nothing_usable_says_so_plainly(self):
        folder, note = backend.old_files_folder({"scan_folder": "C:/"}, ok=lambda p: False, downloads=None)
        self.assertIsNone(folder)
        self.assertTrue(note.startswith("Old Files folder unavailable:"))
        self.assertNotIn("Error", note)


if __name__ == "__main__":
    unittest.main()
