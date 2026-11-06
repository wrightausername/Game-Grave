"""Live Ready Room: public feed boundaries, durable history and real evidence."""
from copy import deepcopy
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from core import SteamGame
from gg_desktop.backend import Inventory
from gg_desktop.models import merge_games
from gg_desktop.ready_room_data import live_ready_room
from gg_desktop.ready_room_services import (
    app_id, backup_receipt, backup_status, inspect_local, load_state, news_targets,
    news_url, parse_news, refresh_news, save_state,
)
from save_vault import create_backup


def payload(steam_id="1091500", title="Patch 2.3", **changes):
    item = dict(gid="123", title=title, date=int(time.time()), contents="<b>Official</b> [url=x]patch notes[/url]",
                feedname="steam_community_announcements", url="https://store.steampowered.com/news/app/1091500/view/123")
    item.update(changes)
    return {"appnews": {"appid": int(steam_id), "newsitems": [item]}}


class NewsTests(unittest.TestCase):
    def test_official_posts_are_plain_text_and_keep_source(self):
        post = parse_news(payload(), "1091500", "Cyberpunk 2077")[0]
        self.assertEqual(post["kind"], "update")
        self.assertEqual(post["detail"], "Official patch notes")
        self.assertEqual(post["app_id"], "1091500")
        self.assertTrue(post["url"].startswith("https://store.steampowered.com/news/"))

    def test_external_press_and_impossible_dates_are_not_official_updates(self):
        for changes in ({"feedname": "pcgamer"}, {"date": True}, {"date": float("inf")},
                        {"date": time.time() + 3 * 86400}, {"gid": "not-an-id"}):
            self.assertEqual(parse_news(payload(**changes), "1091500", "Game"), [])

    def test_response_for_different_app_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_news(payload(), "999", "Other game")

    def test_links_cannot_open_arbitrary_sites_or_local_protocols(self):
        for url in ("file:///private", "steam://uninstall/1", "javascript:alert(1)",
                    "https://store.steampowered.com.evil.test/news/", "https://steamcommunity.com/linkfilter/?url=evil",
                    "https://store.steampowered.com:999/news/", "https://user@store.steampowered.com/news/"):
            self.assertEqual(news_url(url, "1091500"), "https://store.steampowered.com/news/app/1091500")
        self.assertEqual(news_url("file:///private", "invalid"), "")

    def test_targets_use_verified_steam_ids_and_prioritize_followed_games(self):
        games = [SimpleNamespace(launcher="GOG", app_id="1091500", name="GOG game"),
                 SimpleNamespace(launcher="Steam", app_id="1&other=bad", name="Invalid"),
                 SimpleNamespace(launcher="Steam", app_id="2", name="Installed")]
        followed = [dict(launcher="Steam", app_id="3", name="Followed")]
        self.assertEqual(news_targets(games, followed), [("3", "Followed"), ("2", "Installed")])
        self.assertFalse(app_id(True))

    def test_partial_failure_preserves_only_failed_active_cache(self):
        old = parse_news(payload(), "1091500", "Cyberpunk 2077")[0]
        state = load_state(Path(tempfile.gettempdir()) / "gg-nonexistent-news-fixture")
        state["news"] = [old, {**old, "id": "9:123", "app_id": "9"}]
        before = deepcopy(state)
        games = [SimpleNamespace(launcher="Steam", app_id="1091500", name="Cyberpunk 2077"),
                 SimpleNamespace(launcher="Steam", app_id="2", name="Second")]
        def fetch(steam_id, name):
            if steam_id == "1091500":
                raise OSError("offline")
            return parse_news(payload("2", "Scheduled maintenance"), "2", name)
        report = refresh_news(games, state, fetcher=fetch)
        self.assertEqual({p["app_id"] for p in report["news"]}, {"1091500", "2"})
        self.assertEqual(report["succeeded"], 1)
        self.assertEqual(len(report["news_warnings"]), 1)
        self.assertEqual(state, before)

    def test_no_installed_or_followed_games_makes_no_requests(self):
        with patch("gg_desktop.ready_room_services.fetch_one") as request:
            report = refresh_news([], {"followed": [], "news": []})
        request.assert_not_called()
        self.assertEqual(report["succeeded"], 0)


class LocalHistoryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_state_survives_restart_without_touching_settings(self):
        settings = self.root / "settings.json"
        settings.write_text('{"never_touch":["keep"]}')
        state = load_state(self.root)
        state["followed"] = [dict(key="Steam:1", name="My Game", launcher="Steam", app_id="1")]
        save_state(state, self.root)
        self.assertEqual(load_state(self.root), state)
        self.assertEqual(settings.read_text(), '{"never_touch":["keep"]}')

    def test_first_use_creates_only_its_own_private_state(self):
        directory = self.root / "NewPreferences" / "Game Grave"
        state = load_state(directory)
        save_state(state, directory)
        self.assertEqual(load_state(directory), state)
        self.assertEqual({p.name for p in directory.iterdir()}, {"ready-room.json"})

    def test_failed_publish_preserves_prior_history(self):
        state = load_state(self.root)
        save_state(state, self.root)
        original = (self.root / "ready-room.json").read_bytes()
        with patch("os.replace", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                save_state({**state, "news_warnings": ["changed"]}, self.root)
        self.assertEqual((self.root / "ready-room.json").read_bytes(), original)
        self.assertFalse(list(self.root.glob(".ready-room-*.tmp")))

    def test_corrupt_or_wrong_schema_state_does_not_produce_claims(self):
        for raw in ("not JSON", '{"schema":2,"backups":[{"verified":true}]}',
                    '{"schema":1,"news":[null,{},"bad"],"backups":[{}]}'):
            (self.root / "ready-room.json").write_text(raw)
            state = load_state(self.root)
            self.assertEqual(state["news"], [])
            self.assertEqual(state["backups"], [])

    def test_state_refuses_a_symlink_and_does_not_modify_its_target(self):
        target = self.root / "unrelated.json"
        target.write_text("KEEP")
        try:
            (self.root / "ready-room.json").symlink_to(target)
        except OSError:
            self.skipTest("Symlinks unavailable")
        self.assertFalse(load_state(self.root)["backups"])
        with self.assertRaises(ValueError):
            save_state(load_state(self.root), self.root)
        self.assertEqual(target.read_text(), "KEEP")

    def test_only_completed_backups_are_counted_and_changes_are_visible(self):
        source = self.root / "Saves"
        source.mkdir()
        saved = source / "slot.sav"
        saved.write_bytes(b"MY ORIGINAL SAVE")
        with self.assertRaises(ValueError):
            backup_receipt({"verified": False})
        report = create_backup(source, self.root / "backup.zip")
        receipt = backup_receipt(report)
        state = load_state(self.root)
        state["backups"] = [receipt]
        save_state(state, self.root)
        self.assertEqual(backup_status(load_state(self.root)["backups"][0]), "Verified when created")
        self.assertEqual(live_ready_room(Inventory(), state=state).backup_title, "1 Saved Backup")
        with (self.root / "backup.zip").open("ab") as stream:
            stream.write(b"changed")
        self.assertEqual(backup_status(receipt), "Changed: recheck needed")
        self.assertEqual(live_ready_room(Inventory(), state=state).backup_title, "0 Saved Backups")
        self.assertEqual(saved.read_bytes(), b"MY ORIGINAL SAVE")

    def test_local_playtime_is_read_from_records_and_never_added_across_accounts(self):
        steam = self.root / "Steam"
        steam.mkdir()
        for account, minutes in (("1", 120), ("2", 60)):
            directory = steam / "userdata" / account / "config"
            directory.mkdir(parents=True)
            (directory / "localconfig.vdf").write_text('"UserLocalConfigStore" { "Software" { "Valve" { "Steam" { "apps" { "1091500" { "Playtime" "' + str(minutes) + '" } } } } } }')
        bad = steam / "userdata" / "3" / "config"
        bad.mkdir(parents=True)
        (bad / "localconfig.vdf").write_text('"UserLocalConfigStore" "malformed"')
        inventory = Inventory(scanned_at="Synthetic QA")
        with patch("core._steam_roots", return_value=[steam]):
            evidence = inspect_local(inventory)
        self.assertEqual(evidence["playtimes"], {"1091500": 120})

    def test_live_counts_and_gauge_describe_only_their_actual_evidence(self):
        game_path = self.root / "Cyberpunk"
        game_path.mkdir()
        steam = SteamGame("1091500", "Cyberpunk 2077", str(self.root), str(game_path), 0, None, "Unknown")
        inventory = Inventory(steam=[steam], games=merge_games([steam], []), scanned_at="Synthetic QA")
        evidence = dict(audit={"unresolved_records": 2}, profiles={"warnings": ["Incomplete profile"]},
                        playtimes={"1091500": 120}, accessible_games=1, manager_count=0, accessible_managers=0)
        state = load_state(self.root)
        state["news"] = parse_news(payload(title="Hotfix #42"), "1091500", "Cyberpunk 2077")
        state["news_checked"] = {"1091500": int(time.time())}
        data = live_ready_room(inventory, state=state, evidence=evidence, disk_free_percent=50)
        self.assertEqual(data.counts, ("1", "3", "0", "0", "0"))
        self.assertEqual(data.games[0].hours, "2 hrs")
        self.assertEqual(data.games[0].status, "Hotfix news")
        self.assertNotIn("Up to date", data.games[0].status)
        self.assertEqual(data.health_caption, "Local checks")
        self.assertEqual(data.health_score, 100)
        self.assertIn("not verified", data.health_note)


if __name__ == "__main__":
    unittest.main()
