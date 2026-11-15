"""Where a game's files are: only proven places."""
import unittest
from types import SimpleNamespace

from gg_desktop import games_places as places


def game(**over):
    base = dict(name="Elden Ring", launcher="Steam", install_path="D:\\SteamLibrary\\steamapps\\common\\ELDEN RING",
                capabilities=("open_folder",))
    base.update(over)
    return SimpleNamespace(**base)


class GamesPlacesTest(unittest.TestCase):
    def test_install_library_and_labeled_saves(self):
        saves = [SimpleNamespace(game="Elden Ring", path="C:\\Users\\a\\AppData\\Roaming\\EldenRing", reason="Labeled"),
                 SimpleNamespace(game="elden  ring", path="C:\\Users\\a\\AppData\\Roaming\\EldenRing", reason="dup"),
                 SimpleNamespace(game="Elden Ring Nightreign", path="C:\\x", reason="another game")]
        found = places.places(game(), saves)
        self.assertEqual([p.label for p in found], ["Install folder", "Save folder", "Library folder"])
        self.assertEqual(found[2].path, "D:\\SteamLibrary\\steamapps\\common")

    def test_nothing_unproven(self):
        self.assertEqual(places.places(game(capabilities=()), []), [])
        self.assertEqual(places.places(game(install_path=""), []), [])
        self.assertIsNone(places.library_place(game(install_path="D:\\")))

    def test_short(self):
        text = places.short("C:\\" + "a" * 100 + "\\Saves", 30)
        self.assertEqual(len(text), 30)
        self.assertTrue(text.startswith("C:\\") and text.endswith("Saves"))


if __name__ == "__main__":
    unittest.main()
