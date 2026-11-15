import unittest
from types import SimpleNamespace as NS

from gg_desktop import search_core as core


class Search(unittest.TestCase):
    def setUp(self):
        self.inv = NS(games=[NS(name="Elden Ring", launcher="Steam"), NS(name="Skyrim Special Edition", launcher="Steam")],
                      mods=[NS(name="SkyUI", path=r"D:\MO2\mods\SkyUI", game="Skyrim")], saves=[],
                      files=[NS(path=r"C:\Users\x\Downloads\skyrim_patch.zip")],
                      screenshots=[NS(path=r"C:\Pics\elden_001.png")], recordings=[])
        self.tabs = [("Old Files", "Old Files", "Older files you can review"), ("More Tools", "Toolbox", "Windows and file utilities")]
        self.features = [NS(title="Hash Checker", keywords=("hash", "checksum"), what="Checks a file. More.",
                            opens="tool:hash", tab="More Tools")]

    def test_groups_and_order(self):
        hits = core.find("sky", self.tabs, self.features, self.inv)
        groups = [h.group for h in hits]
        self.assertEqual(groups, ["Games", "Mods", "Old Files"])
        self.assertEqual(hits[0].target, "tab:Games")
        self.assertEqual(hits[0].search, "Skyrim Special Edition")
        self.assertEqual(hits[1].title, "SkyUI")

    def test_tools_and_tabs(self):
        self.assertEqual(core.find("hash", self.tabs, self.features, self.inv)[0].target, "tool:hash")
        self.assertEqual(core.find("toolbox", self.tabs, self.features, None)[0].target, "tab:More Tools")

    def test_short_and_scoring(self):
        self.assertEqual(core.find("s", self.tabs, self.features, self.inv), [])
        self.assertGreater(core.score("elden", "Elden Ring"), core.score("ring", "Elden Ring"))
        self.assertEqual(core.score("zz", "Elden Ring"), 0)
        self.assertEqual(core.score("ring elden", "Elden Ring"), 30)


if __name__ == "__main__":
    unittest.main()
