"""Customization controls must never affect cleanup eligibility or integrity."""
import unittest
from core import SteamGame, OldFile
from graveyard import GraveyardEntry
from view_options import (filter_sort_graveyard, sort_games, sort_files,
                          sort_mods, sanitize_saved_views)


def record(key, size, days, category, reviewable, relationship="Game association unknown"):
    return GraveyardEntry(key, key, "C:/Games/"+key, category, size, days,
                          relationship, "Old item found", "Review required", reviewable)


class SortAndFilterTests(unittest.TestCase):
    def setUp(self):
        self.items = [
            record("a.zip", 5*1024**3, 1000, "Archives", True),
            record("b.zip", 40*1024**2, 400, "Archives", False),
            record("c", 20*1024**3, 800, "Installed game", False),
            record("z", 2*1024**3, None, "Uncertain mods", False),
        ]

    def test_size_sorted_numerically_not_as_formatted_text(self):
        self.assertEqual([x.key for x in filter_sort_graveyard(self.items)],
                         ["c", "a.zip", "z", "b.zip"])
        self.assertEqual([x.key for x in filter_sort_graveyard(self.items, order="Ascending")],
                         ["b.zip", "z", "a.zip", "c"])

    def test_age_ascending_and_descending_unknown_always_last(self):
        self.assertEqual([x.key for x in filter_sort_graveyard(self.items, sort="Age")],
                         ["a.zip", "c", "b.zip", "z"])
        self.assertEqual([x.key for x in filter_sort_graveyard(self.items, sort="Age", order="Ascending")],
                         ["b.zip", "c", "a.zip", "z"])

    def test_combined_filters_do_not_expand_cleanup_eligibility(self):
        output = filter_sort_graveyard(self.items, search="zip", category="Archives",
                                      minimum="1 GB+", status="Reviewable archives")
        self.assertEqual([x.key for x in output], ["a.zip"])
        self.assertEqual(sum(x.can_recycle for x in self.items), 1)
        self.assertFalse(self.items[2].can_recycle)

    def test_relationship_search_and_protected_filter(self):
        result = filter_sort_graveyard(self.items, search="unknown", status="Protected / review only")
        self.assertEqual({x.key for x in result}, {"b.zip", "c", "z"})

    def test_stable_sort_and_invalid_choice_fallback(self):
        result = filter_sort_graveyard(self.items, sort="garbage", order="not real")
        self.assertEqual([x.key for x in result], ["c", "a.zip", "z", "b.zip"])

    def test_saved_presets_reject_malformed_values(self):
        presets = sanitize_saved_views({"Old and Large": {"graveyard_sort": "Age",
                                  "graveyard_days": 1095, "graveyard_status": "Reviewable archives"},
                                  "broken": "not a dict", "": {}})
        self.assertEqual(list(presets), ["Old and Large"])
        self.assertEqual(presets["Old and Large"]["graveyard_days"], 1095)
        self.assertEqual(presets["Old and Large"]["graveyard_order"], "Descending")

    def test_gamers_can_sort_by_name_size_and_last_play(self):
        games = [SteamGame("1", "Zelda", "lib", "p", 80, 100, "Steam"),
                 SteamGame("2", "Apex", "lib", "p", 500, 400, "Steam"),
                 SteamGame("3", "Unknown", "lib", "p", 1000, None, "Steam")]
        self.assertEqual([g.name for g in sort_games(games)], ["Zelda", "Apex", "Unknown"])
        self.assertEqual([g.name for g in sort_games(games, "Largest first")],
                         ["Unknown", "Apex", "Zelda"])
        self.assertEqual([g.name for g in sort_games(games, "Name A-Z")],
                         ["Apex", "Unknown", "Zelda"])

    def test_old_file_sorting(self):
        files=[OldFile("/a/aaa.zip", 100, 300), OldFile("/a/zzz.zip", 200, 100)]
        self.assertEqual([x.path for x in sort_files(files, "Oldest first")],
                         ["/a/zzz.zip", "/a/aaa.zip"])
        self.assertEqual([x.path for x in sort_files(files, "Name A-Z")],
                         ["/a/aaa.zip", "/a/zzz.zip"])


if __name__ == "__main__":
    unittest.main()
