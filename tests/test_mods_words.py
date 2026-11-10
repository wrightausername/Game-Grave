import unittest

from gg_desktop import mods_words as w


class ModsWordsTests(unittest.TestCase):
    def test_status_words_are_plain(self):
        self.assertEqual([w.status_word(x) for x in ("Enabled", "Disabled", "Mixed", "Unknown", "Protected")],
                         ["On", "Off", "On in some", "Not recorded", "Storage folder"])
        self.assertEqual(w.status_word("Something else"), "Something else")

    def test_summary_says_what_is_known_and_what_is_partial(self):
        m = {"total": 5, "total_label": "Total Mods", "enabled": 3, "mixed": 0, "disabled": 2,
             "outdated": 1, "conflicts": 2, "conflicts_limited": True}
        self.assertEqual(w.summary(m, games=2),
                         "You have 5 mods for 2 games, 3 turned on, 1 update available, 2 conflicts found (some may be missed).")

    def test_summary_without_evidence_does_not_guess(self):
        m = {"total": 4, "total_label": "Mod Locations", "enabled": 0, "mixed": 0, "disabled": 0,
             "outdated": None, "conflicts": None, "conflicts_limited": False}
        self.assertEqual(w.summary(m), "You have 4 mod folders.")
        self.assertIn("Scan your PC", w.summary({"total": 0}))

    def test_detail_lines(self):
        self.assertEqual(w.order_text(5, 12, "Default"), "#5 of 12 · Default")
        self.assertEqual(w.requires_text([], False), "Doesn't list any other mods it needs")
        self.assertEqual(w.requires_text(["A", "B"], True), "Needs 3 other mods: A, B …")
        self.assertEqual(w.conflicts_text(0, True, True), "None found (the check was partial)")
        self.assertEqual(w.conflicts_text(1, False, True), "1 conflict found")
        self.assertEqual(w.conflicts_text(0, False, False), "Not checked yet")
        self.assertEqual(w.profiles_text([]), "Not in any saved profile")
        self.assertEqual(w.profiles_text(["Default"]), "In 1 profile: Default")
        self.assertEqual(w.update_text("2.5", "2.0", True, ""), "Version 2.5 is available (you have 2.0)")


if __name__ == "__main__":
    unittest.main()


class ReadableNames(unittest.TestCase):
    class Game:
        def __init__(self, name, app_id):
            self.name, self.app_id = name, app_id

    def test_workshop_app_numbers_are_named_only_when_the_game_is_scanned(self):
        games = [self.Game("Skyrim Special Edition", "489830")]
        path = r"D:\Steam\steamapps\workshop\content\489830"
        self.assertEqual(w.readable_name("489830", path, "Steam Workshop", games), "Skyrim Special Edition Workshop items")
        self.assertEqual(w.readable_name("294100", path, "Steam Workshop", games), "Steam Workshop items (app 294100)")
        self.assertEqual(w.readable_name("12345", r"D:\Mods\12345", "Other", games), "Folder 12345")

    def test_download_names_lose_their_id_version_and_stamp(self):
        self.assertEqual(w.readable_name("SkyUI_5_2_SE-12604-5-2SE-1564405049"), "SkyUI 5 2 SE")
        self.assertEqual(w.readable_name("Unofficial Patch-266-4-3-3a-1604000000"), "Unofficial Patch")
        self.assertEqual(w.readable_name("My Texture Pack 1700000000"), "My Texture Pack")

    def test_hex_walls_are_shortened_and_ordinary_names_are_untouched(self):
        self.assertEqual(w.readable_name("3f2a9c1d-1111-2222-3333-444455556666"), "Folder 3f2a9c1d…")
        for plain in ("SkyUI", "Better Combat 2", "RimWorld Reborn v1-2", "ENB 2026", ""):
            self.assertEqual(w.readable_name(plain), plain or "Mod storage")
