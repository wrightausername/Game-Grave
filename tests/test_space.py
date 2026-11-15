import unittest
from types import SimpleNamespace as NS

from gg_desktop import space_core as sp

GB = 1024 ** 3
NOW = 2_000_000_000.0


def game(name, path, size, days_ago, launcher="Steam", app_id="1"):
    played = None if days_ago is None else NOW - days_ago * 86400
    return NS(name=name, install_path=path, size_bytes=size, last_played_at=played, launcher=launcher, app_id=app_id,
              key=name)


class Space(unittest.TestCase):
    def test_low_and_target(self):
        low = sp.Drive("C:\\", 20 * GB, 1000 * GB)
        self.assertTrue(low.low)
        self.assertEqual(low.target, (100 + 20 - 20) * GB)
        self.assertFalse(sp.Drive("D:\\", 300 * GB, 1000 * GB).low)

    def test_suggestions_only_long_unplayed_with_known_times(self):
        games = [game("Big Old", r"C:\Steam\Big", 120 * GB, 200), game("Recent", r"C:\Steam\Recent", 90 * GB, 3),
                 game("Unknown", r"C:\Steam\U", 80 * GB, None), game("Other drive", r"D:\G", 70 * GB, 400),
                 game("Small Old", r"C:\Steam\Small", 10 * GB, 150)]
        drive = sp.Drive("C:\\", 20 * GB, 1000 * GB)
        picks = sp.suggestions(games, drive, now=NOW)
        self.assertEqual([p.game.name for p in picks], ["Big Old"])
        all_picks = sp.suggestions(games, drive, now=NOW, need=0)
        self.assertEqual([p.game.name for p in all_picks], ["Big Old", "Small Old"])
        self.assertIn("Resurrection Kit", sp.headline(drive, picks))
        self.assertNotIn("safe", sp.headline(drive, picks).lower())

    def test_rest_drive_and_links(self):
        drives = [sp.Drive("C:\\", 20 * GB, 1000 * GB), sp.Drive("D:\\", 50 * GB, 500 * GB), sp.Drive("E:\\", 900 * GB, 2000 * GB)]
        self.assertEqual(sp.rest_drive(drives, "C:\\", 120 * GB).root, "E:\\")
        self.assertIsNone(sp.rest_drive(drives[:2], "C:\\", 120 * GB))
        self.assertEqual(sp.uninstall_link(game("A", "C:\\a", 1, 1, app_id="440")), "steam://uninstall/440")
        self.assertEqual(sp.uninstall_link(game("A", "C:\\a", 1, 1, launcher="Epic", app_id="")), "")
        self.assertTrue(sp.notice_due({}, "2026-11-15"))
        self.assertFalse(sp.notice_due({sp.NOTICE_KEY: "2026-11-15"}, "2026-11-15"))


if __name__ == "__main__":
    unittest.main()
