import unittest
from types import SimpleNamespace as NS

from gg_desktop import first_scan_core as core


def inv(**kw):
    base = dict(games=[], mods=[], files=[], screenshots=[], recordings=[], saves=[], graveyard=[])
    base.update(kw)
    return NS(**base)


class FirstScan(unittest.TestCase):
    def test_headline_and_steps(self):
        i = inv(games=[1, 2], mods=[1], files=[NS(size=2048)])
        self.assertEqual(core.headline(i), "Found 2 games, 1 mod location, 1 old file.")
        steps = core.next_steps(i)
        self.assertEqual([s[3] for s in steps], ["tab:Mods", "kit:easy", "tab:Old Files"])
        self.assertTrue(all("safe" not in s[1].lower() for s in steps))

    def test_empty_scan(self):
        steps = core.next_steps(inv())
        self.assertEqual([s[3] for s in steps], ["tab:Other Storage", "tour"])
        self.assertIn("nothing", core.headline(inv()))

    def test_once(self):
        self.assertTrue(core.should_show({}))
        self.assertFalse(core.should_show({core.SEEN_KEY: True}))
        self.assertFalse(core.should_show({}, quick=True))
        self.assertFalse(core.should_show({}, reference_preview=True))


if __name__ == "__main__":
    unittest.main()
