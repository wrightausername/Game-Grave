"""Documents can be moved: to OneDrive (including work accounts named "OneDrive - Company") or another drive."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import save_discovery
from gg_desktop import other_storage_data


class DocumentsFolders(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp()) / "Alex"
        (self.home / "Documents").mkdir(parents=True)

    def test_work_onedrive_is_included_without_duplicates(self):
        (self.home / "OneDrive - Contoso Ltd" / "Documents").mkdir(parents=True)
        found = save_discovery.documents_folders(self.home)
        self.assertEqual(found[0], self.home / "Documents")
        self.assertIn(self.home / "OneDrive - Contoso Ltd" / "Documents", found)
        self.assertEqual(len(found), len({str(p).casefold() for p in found}))

    def test_windows_answer_comes_first_for_the_real_home(self):
        moved = Path(tempfile.mkdtemp()) / "D Docs"
        with patch.dict("os.environ", {"USERPROFILE": str(self.home)}), \
                patch.object(save_discovery, "_known_documents", return_value=moved):
            found = save_discovery.documents_folders()
        self.assertEqual(found[0], moved)

    def test_saves_in_onedrive_work_documents_are_found(self):
        saves = self.home / "OneDrive - Contoso Ltd" / "Documents" / "My Games" / "Skyrim Special Edition"
        saves.mkdir(parents=True)
        found = [s.path for s in save_discovery.discover_saves(self.home, local=self.home / "L", roaming=self.home / "R")]
        self.assertIn(str(saves.resolve()), found)

    def test_other_storage_shows_the_my_games_that_exists(self):
        (self.home / "OneDrive" / "Documents" / "My Games").mkdir(parents=True)
        spots = [s for s in other_storage_data.known_spots(env={}, home=self.home) if s.name == "My Games"]
        self.assertEqual(spots[0].path, self.home / "OneDrive" / "Documents" / "My Games")


if __name__ == "__main__":
    unittest.main()
