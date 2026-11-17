"""Documents can be moved: to OneDrive (including work accounts named "OneDrive - Company") or another drive."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import save_discovery


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


if __name__ == "__main__":
    unittest.main()
