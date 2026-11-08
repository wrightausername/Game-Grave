"""Mods can be sorted by name, game, manager, size or date in either direction; unknowns never win."""
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from gg_desktop import mods_sort
from gg_desktop.mods_sort import HEADERS, OPTIONS, date_text, header_option, size_text, sort_views


def view(name, game="Skyrim", manager="Vortex", size=100, path="x"):
    return SimpleNamespace(name=name, game=game, manager=manager, size=size, record=SimpleNamespace(path=path))


class SortTests(unittest.TestCase):
    def setUp(self):
        mods_sort.modified_time.cache_clear()

    def names(self, views):
        return [v.name for v in views]

    def test_name_both_directions_ignores_case(self):
        rows = [view("beta"), view("Alpha"), view("gamma")]
        self.assertEqual(self.names(sort_views(rows, "Name (A–Z)")), ["Alpha", "beta", "gamma"])
        self.assertEqual(self.names(sort_views(rows, "Name (Z–A)")), ["gamma", "beta", "Alpha"])

    def test_size_both_directions_with_unknown_always_last(self):
        rows = [view("a", size=5), view("b", size=None), view("c", size=50), view("d", size=0)]
        self.assertEqual(self.names(sort_views(rows, "Size (Largest)")), ["c", "a", "d", "b"])
        self.assertEqual(self.names(sort_views(rows, "Size (Smallest)")), ["d", "a", "c", "b"])

    def test_game_and_manager_both_directions_with_ties_by_name(self):
        rows = [view("z", game="Fallout 4", manager="MO2"), view("a", game="Skyrim", manager="MO2"),
                view("m", game="Fallout 4", manager="Vortex")]
        self.assertEqual(self.names(sort_views(rows, "Game (A–Z)")), ["m", "z", "a"])
        self.assertEqual(self.names(sort_views(rows, "Game (Z–A)")), ["a", "m", "z"])
        self.assertEqual(self.names(sort_views(rows, "Manager (A–Z)")), ["a", "z", "m"])
        self.assertEqual(self.names(sort_views(rows, "Manager (Z–A)")), ["m", "a", "z"])

    def test_date_uses_the_folder_modified_time_and_unreadable_goes_last(self):
        with tempfile.TemporaryDirectory() as temp:
            old, new = Path(temp, "old"), Path(temp, "new")
            old.mkdir()
            new.mkdir()
            os.utime(old, (1_500_000_000, 1_500_000_000))
            os.utime(new, (1_700_000_000, 1_700_000_000))
            rows = [view("gone", path=str(Path(temp, "missing"))), view("old", path=str(old)), view("new", path=str(new))]
            self.assertEqual(self.names(sort_views(rows, "Date (Newest)")), ["new", "old", "gone"])
            self.assertEqual(self.names(sort_views(rows, "Date (Oldest)")), ["old", "new", "gone"])

    def test_unknown_option_falls_back_to_name(self):
        self.assertEqual(self.names(sort_views([view("b"), view("a")], "Nonsense")), ["a", "b"])

    def test_header_clicks_toggle_direction(self):
        self.assertEqual(header_option(1, "Size (Largest)"), "Name (A–Z)")
        self.assertEqual(header_option(1, "Name (A–Z)"), "Name (Z–A)")
        self.assertEqual(header_option(4, "Name (A–Z)"), "Size (Largest)")
        self.assertEqual(header_option(4, "Size (Largest)"), "Size (Smallest)")
        self.assertEqual(header_option(6, "Date (Newest)"), "Date (Oldest)")
        self.assertIsNone(header_option(5, "Name (A–Z)"))
        self.assertTrue(all(o in OPTIONS for pair in HEADERS.values() for o in pair))

    def test_text_helpers(self):
        self.assertEqual(size_text(None), "—")
        self.assertEqual(size_text(2048), "2.0 KB")
        self.assertEqual(date_text(None), "—")
        self.assertRegex(date_text(1_700_000_000), r"^\d{2} \w{3} 20\d{2}$")


if __name__ == "__main__":
    unittest.main()
