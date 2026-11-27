"""Overview's Today strip: only saved facts, each line opens its tab, all quiet when nothing needs you."""
import unittest

from gg_desktop import deals_core as dc
from gg_desktop import today_core as tc
from gg_desktop.space_core import Drive

NOW = 1_800_000_000
GB = 1024 ** 3


class Today(unittest.TestCase):
    def test_all_quiet(self):
        lines = tc.items({}, now=NOW)
        self.assertEqual([(l.key, l.route) for l in lines], [("quiet", "")])

    def test_free_drops_space_news(self):
        settings = {dc.FREE_NOW_KEY: [{"title": "Hades"}], dc.FREE_CHECKED_KEY: NOW - 3600,
                    dc.DROPS_KEY: [{"title": "Doom", "message": "$3 at Steam", "at": NOW - 86400},
                                   {"title": "Old", "message": "x", "at": NOW - 30 * 86400}]}
        drives = [Drive("D:\\", 12 * GB, 1000 * GB), Drive("C:\\", 400 * GB, 1000 * GB)]
        news = [{"game": "Elden Ring", "timestamp": NOW - 3600}, {"game": "Elden Ring", "timestamp": NOW - 99 * 86400}]
        lines = tc.items(settings, drives, news, now=NOW)
        self.assertEqual([l.key for l in lines], ["free", "drops", "space", "news"])
        self.assertEqual(lines[0].text, "Free to keep: Hades")
        self.assertEqual(lines[1].text, "Price drop: Doom")
        self.assertTrue(lines[2].text.startswith("D: is low on space"))
        self.assertEqual(lines[3].text, "News for Elden Ring")
        self.assertEqual([l.route for l in lines], ["Deals", "Deals", "Graveyard", "Ready Room"])
        for line in lines:
            self.assertNotIn("safe", (line.text + line.tip).casefold())

    def test_stale_free_list_is_not_shown(self):
        settings = {dc.FREE_NOW_KEY: [{"title": "Hades"}, {"title": "Doom"}], dc.FREE_CHECKED_KEY: NOW - 5 * 86400}
        self.assertEqual([l.key for l in tc.items(settings, now=NOW)], ["quiet"])
        settings[dc.FREE_CHECKED_KEY] = NOW
        self.assertEqual(tc.items(settings, now=NOW)[0].text, "2 games free to keep")


if __name__ == "__main__":
    unittest.main()
