"""Ready Room's live news cadence and honest status line. No Qt needed."""
from types import SimpleNamespace
import unittest

from gg_desktop.backend import Inventory
from gg_desktop.ready_room_data import live_ready_room
from gg_desktop.ready_room_services import (
    NEWS_INTERVAL, last_checked, news_is_stale, news_status_text,
)

NOW = 1_800_000_000
STEAM = SimpleNamespace(name="Hades", key="steam:1145360", launcher="Steam", app_id="1145360", last_played_at=0)
EPIC = SimpleNamespace(name="Fortnite", key="epic:f", launcher="Epic Games", app_id="", last_played_at=0)


class NewsCadenceTests(unittest.TestCase):
    def test_never_checked_is_stale(self):
        self.assertTrue(news_is_stale({}, 0, now=NOW))

    def test_recent_success_is_not_stale_and_old_one_is(self):
        fresh = {"news_checked": {"1145360": NOW - 60}}
        self.assertFalse(news_is_stale(fresh, 0, now=NOW))
        old = {"news_checked": {"1145360": NOW - NEWS_INTERVAL - 1}}
        self.assertTrue(news_is_stale(old, 0, now=NOW))

    def test_failed_attempt_waits_a_full_interval(self):
        self.assertFalse(news_is_stale({}, NOW - 120, now=NOW))
        self.assertTrue(news_is_stale({}, NOW - NEWS_INTERVAL, now=NOW))

    def test_last_checked_is_the_newest_answer(self):
        self.assertEqual(last_checked({"news_checked": {"1": 5, "2": 9}}), 9)
        self.assertEqual(last_checked({}), 0)


class StatusLineTests(unittest.TestCase):
    def test_busy_and_not_checked(self):
        self.assertIn("Checking", news_status_text({}, [STEAM], busy=True, now=NOW))
        self.assertIn("not checked yet", news_status_text({}, [STEAM], now=NOW))

    def test_last_checked_minutes(self):
        text = news_status_text({"news_checked": {"1145360": NOW - 600}}, [STEAM], now=NOW)
        self.assertIn("10 min ago", text)
        self.assertIn("30 minutes", text)

    def test_non_steam_games_say_there_is_no_official_feed(self):
        text = news_status_text({"news_checked": {"1145360": NOW - 30}}, [STEAM, EPIC], now=NOW)
        self.assertIn("1 non-Steam game has no official feed", text)
        only_epic = news_status_text({}, [EPIC], now=NOW)
        self.assertIn("No official news feed", only_epic)

    def test_failure_is_stated_not_hidden(self):
        text = news_status_text({"news_checked": {"1145360": NOW - 7200}}, [STEAM], failed=True, now=NOW)
        self.assertIn("could not be reached", text)
        self.assertIn("saved posts", text)

    def test_no_games_asks_for_a_scan(self):
        self.assertIn("Scan", news_status_text({}, [], now=NOW))


class GamePulseTests(unittest.TestCase):
    def test_non_steam_game_is_labelled_no_official_feed(self):
        data = live_ready_room(Inventory(games=[STEAM, EPIC], scanned_at="2026-11-08"), state={
            "followed": [], "news": [], "news_checked": {}, "news_warnings": [], "backups": []})
        status = {g.name: g.status for g in data.games}
        self.assertEqual(status["Fortnite"], "No official feed")
        self.assertEqual(status["Hades"], "Recorded install")


if __name__ == "__main__":
    unittest.main()
