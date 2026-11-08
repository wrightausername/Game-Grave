"""Provider contracts and native boundaries; no real sign-in or game launch."""
from dataclasses import replace
from html import escape
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from core import SteamGame
from gg_desktop.game_artwork import Artwork
from gg_desktop.games_account_store import forget, load_secret, load_snapshots, read_document, save_secret, save_snapshot, update_secret_if_current, write_document
from gg_desktop.games_connections import login_url, parse_login_document
from gg_desktop.games_catalogue_artwork import cached_artwork, checked_media, remote_artwork
from gg_desktop.games_http import ProviderError, SignInRequired, checked_url, cookie_header
from gg_desktop.games_library_data import PlaytimeLedger, compose, local_facts, running_games
from gg_desktop.games_native import Action, execute, installed_facts, native_action, registered_uninstaller, split_command
from gg_desktop.games_providers import EPIC_ASSETS, EPIC_AUTH, EPIC_CATALOG, EPIC_LIBRARY, EA_API, exchange_epic_code, fetch_ea, fetch_epic, fetch_gog, fetch_steam, steam_token_from_html
from gg_desktop.models import GameRecord, merge_games
from launchers import LauncherGame

SID = "76561198000000001"


class GamesIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.install = self.root/"Game"
        self.install.mkdir()
        self.steam_root = self.root/"Steam"
        (self.steam_root/"steamapps").mkdir(parents=True)
        self.raw = SteamGame("1091500", "Cyberpunk 2077", str(self.steam_root), str(self.install), 1000, None, "Fixture")
        self.game = merge_games([self.raw], [])[0]
        self.patch = patch("gg_desktop.game_artwork.artwork_dir", return_value=self.root/"Private")
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def other(self, name="Red Dead Redemption 2", launcher="Rockstar Games", app_id="rdr2"):
        return merge_games([], [LauncherGame(name, launcher, str(self.install), app_id, None, "Registered installation")])[0]

    def secret(self, provider="Steam"):
        value = dict(account_id=SID if provider == "Steam" else "account1", access_token="FAKE-TEST-TOKEN", connection_id="fixture-session", expires_at=time.time()+1000)
        save_secret(provider, value)
        return value

    def snapshot(self, provider="Steam", items=None):
        return dict(provider=provider, account_id=SID, account_name="Fixture account", checked_at=time.time(),
                    items=items if items is not None else [dict(id="1091500", aliases=["1091500"], title="Cyberpunk 2077", playtime_seconds=7200)])

    def test_secret_is_encrypted_on_windows_and_session_only_elsewhere(self):
        value = self.secret()
        self.assertEqual(load_secret("Steam"), value)
        path = self.root/"Private/connections.private.json"
        if os.name == "nt":
            self.assertTrue(path.is_file())
            self.assertNotIn(b"FAKE-TEST-TOKEN", path.read_bytes())
            self.assertNotIn(SID.encode(), path.read_bytes())
        else:
            self.assertFalse(path.exists())

    def test_connections_do_not_leak_between_settings_profiles(self):
        self.secret()
        with patch("gg_desktop.game_artwork.artwork_dir", return_value=self.root/"Another profile"):
            self.assertEqual(load_secret("Steam"), {})

    def test_disconnect_erases_connection_and_its_owned_library_only(self):
        self.secret()
        save_snapshot("Steam", self.snapshot())
        self.secret("EA")
        save_snapshot("EA", dict(self.snapshot(), provider="EA", account_id="account1"))
        forget("Steam")
        self.assertEqual(load_secret("Steam"), {})
        self.assertNotIn("Steam", load_snapshots())
        self.assertIn("EA", load_snapshots())

    def test_switching_accounts_hides_the_previous_accounts_cache(self):
        self.secret()
        save_snapshot("Steam", self.snapshot())
        save_secret("Steam", dict(self.secret(), account_id="76561198000000002"))
        self.assertNotIn("Steam", load_snapshots())

    def test_rotated_tokens_are_saved_only_for_the_same_connection(self):
        old = self.secret()
        new = dict(old, access_token="FAKE-ROTATED")
        self.assertTrue(update_secret_if_current("Steam", new, old["connection_id"]))
        self.assertEqual(load_secret("Steam")["access_token"], "FAKE-ROTATED")
        save_secret("Steam", dict(old, connection_id="another-sign-in"))
        self.assertFalse(update_secret_if_current("Steam", new, old["connection_id"]))
        forget("Steam")
        self.assertFalse(update_secret_if_current("Steam", new, old["connection_id"]))
        self.assertEqual(load_secret("Steam"), {})

    def test_sign_in_document_is_bound_to_official_origin_and_request_state(self):
        value = json.dumps(dict(user=dict(logged_in=True, steamid=SID), config=dict(webapi_token="FAKE")))
        self.assertEqual(parse_login_document("Steam", "https://store.steampowered.com/explore/", value, "state")["account_id"], SID)
        self.assertIsNone(parse_login_document("Steam", "https://store.steampowered.com.evil.invalid/explore/", value, "state"))
        self.assertIsNone(parse_login_document("Steam", "http://store.steampowered.com/explore/", value, "state"))
        from gg_desktop.games_providers import EPIC_CLIENT
        url = f"https://www.epicgames.com/id/api/redirect?clientId={EPIC_CLIENT}&responseType=code&state=good"
        self.assertEqual(parse_login_document("Epic Games", url, '{"authorizationCode":"FAKE"}', "good"), {"authorization_code": "FAKE"})
        self.assertIsNone(parse_login_document("Epic Games", url, '{"authorizationCode":"FAKE"}', "wrong"))

    def test_sign_in_rejects_logged_out_and_malformed_site_documents(self):
        for value in ('null', '[]', '{"user":[],"config":{}}', '{"user":{"logged_in":false},"config":{}}'):
            self.assertIsNone(parse_login_document("Steam", "https://store.steampowered.com/explore/", value, "state"))
        self.assertIsNone(parse_login_document("EA", "https://www.ea.com/login", '{"access_token":"FAKE"}', "state"))
        self.assertIsNotNone(parse_login_document("EA", "https://accounts.ea.com/connect/auth", '{"access_token":"FAKE"}', "state"))

    def test_sign_in_start_urls_are_official_https_pages(self):
        from urllib.parse import urlsplit
        expected = {"Steam": "store.steampowered.com", "Epic Games": "www.epicgames.com", "EA": "www.ea.com", "GOG": "www.gog.com"}
        for provider, host in expected.items():
            value = urlsplit(login_url(provider, "state"))
            self.assertEqual(value.scheme, "https")
            self.assertEqual(value.hostname, host)

    def test_linked_connection_storage_is_not_followed(self):
        outside = self.root/"outside.json"
        outside.write_text('{"secret":"not-app-data"}')
        target = self.root/"Private/connections.private.json"
        target.parent.mkdir()
        try:
            target.symlink_to(outside)
        except OSError:
            self.skipTest("Symlinks unavailable")
        self.assertEqual(load_secret("Steam"), {})
        if os.name == "nt":
            with self.assertRaises(ValueError):
                self.secret()
        self.assertEqual(json.loads(outside.read_text()), {"secret": "not-app-data"})

    def test_duplicate_json_keys_are_rejected(self):
        path = self.root/"Private/options.json"
        path.parent.mkdir()
        path.write_text('{"links":{},"links":{"bad":true}}')
        self.assertEqual(read_document("options.json", {}), {})

    def test_authenticated_requests_cannot_redirect_or_use_other_hosts(self):
        for url in ("http://api.steampowered.com/", "https://api.steampowered.com.evil.invalid/", "https://user:pass@api.steampowered.com/", "https://api.steampowered.com:444/"):
            with self.subTest(url=url), self.assertRaises(ProviderError):
                checked_url(url, {"api.steampowered.com"})

    def test_cookie_scope_excludes_unrelated_accounts_and_newlines(self):
        cookies = [dict(name="sid", value="FAKE", domain=".gog.com"), dict(name="ea", value="NO", domain=".ea.com"), dict(name="bad", value="x\r\nInjected: true", domain=".gog.com")]
        self.assertEqual(cookie_header(cookies, "menu.gog.com"), "sid=FAKE")
        self.assertEqual(cookie_header(cookies, "www.gog.com.evil.invalid"), "")

    def test_steam_library_has_real_owned_rows_and_seconds_from_minutes(self):
        response = {"response": {"game_count": 2, "games": [dict(appid=1091500, name="Cyberpunk 2077", playtime_forever=120, rtime_last_played=1700000000), dict(appid=620, name="Portal 2", playtime_forever=0)]}}
        get = Mock(return_value=response)
        snapshot, _ = fetch_steam(self.secret(), get=get)
        self.assertEqual(len(snapshot["items"]), 2)
        self.assertEqual(snapshot["items"][0]["playtime_seconds"], 7200)
        self.assertEqual(get.call_args.kwargs["hosts"], {"api.steampowered.com"})
        records, facts = compose([self.game], {self.game.key: {"product_id": "1091500", "installed": True}}, {"Steam": snapshot})
        self.assertEqual(len(records), 2)
        self.assertTrue(facts[self.game.key]["owned"])
        portal = next(game for game in records if game.app_id == "620")
        self.assertEqual(portal.install_path, "")
        self.assertNotIn("open_folder", portal.capabilities)

    def test_steam_private_or_incomplete_response_does_not_become_empty_library(self):
        for response, error in (({"response": {}}, SignInRequired), ({"response": {"game_count": 2, "games": []}}, ProviderError)):
            with self.subTest(response=response), self.assertRaises(error):
                fetch_steam(self.secret(), get=lambda *_a, **_k: response)

    def test_expired_steam_token_can_refresh_using_its_own_sign_in_cookies(self):
        source = '<div id="application_config" data-userinfo="'+escape(json.dumps(dict(logged_in=True, steamid=SID)), quote=True)+'" data-store_user_config="'+escape(json.dumps(dict(webapi_token="FAKE-NEW")), quote=True)+'"></div>'
        get = Mock(side_effect=[SignInRequired("expired"), {"response": {"game_count": 0}}])
        snapshot, secret = fetch_steam(self.secret(), get=get, raw_get=lambda *_a, **_k: source.encode())
        self.assertEqual(snapshot["items"], [])
        self.assertEqual(secret["access_token"], "FAKE-NEW")

    def test_steam_cookie_refresh_cannot_silently_switch_accounts(self):
        html = '<div id="application_config" data-userinfo=\'{"logged_in":true,"steamid":"76561198000000002"}\' data-store_user_config=\'{"webapi_token":"FAKE"}\'></div>'
        with self.assertRaises(SignInRequired):
            fetch_steam(self.secret(), get=Mock(side_effect=SignInRequired("expired")), raw_get=lambda *_a, **_k: html.encode())

    def test_epic_sign_in_uses_only_its_token_endpoint(self):
        get = Mock(return_value=dict(account_id="account1", displayName="Fixture", access_token="FAKE", refresh_token="FAKE-REFRESH", expires_in=3600))
        result = exchange_epic_code("FAKE-CODE", get=get)
        self.assertEqual(result["account_id"], "account1")
        self.assertEqual(get.call_args.kwargs["hosts"], {EPIC_AUTH})
        self.assertEqual(get.call_args.kwargs["form"]["grant_type"], "authorization_code")

    def test_epic_library_playtime_and_update_versions_use_verified_ids(self):
        def get(url, **kwargs):
            if "/oauth/token" in url:
                return dict(account_id="account1", access_token="FAKE-NEW", refresh_token="FAKE-R", expires_in=3600)
            self.assertEqual(kwargs["headers"]["Authorization"], "Bearer FAKE-TEST-TOKEN")
            if "/library/api/public/items" in url:
                return dict(records=[dict(appName="epic1", namespace="ns1", catalogItemId="catalog1")], responseMetadata={})
            if "/public/assets/" in url:
                return [dict(appName="epic1", buildVersion="2.0")]
            if "/playtime/" in url:
                return [dict(artifactId="epic1", totalTime=9000)]
            if "/bulk/items" in url:
                return {"catalog1": dict(title="Red Dead Redemption 2", keyImages=[dict(type="DieselGameBoxTall", url="https://cdn1.epicgames.com/cover.png")])}
            self.fail("Unexpected Epic endpoint")
        snapshot, _ = fetch_epic(self.secret("Epic Games"), get=get)
        item = snapshot["items"][0]
        self.assertEqual(item["playtime_seconds"], 9000)
        self.assertEqual(item["latest_version"], "2.0")
        epic = self.other(launcher="Epic Games", app_id="epic1")
        records, facts = compose([epic], {epic.key: dict(product_id="epic1", installed=True, installed_version="1.0")}, {"Epic Games": snapshot})
        self.assertEqual(records, [epic])
        self.assertTrue(facts[epic.key]["update_available"])
        self.assertEqual(facts[epic.key]["namespace"], "ns1")

    def test_repeated_epic_cursor_is_rejected(self):
        get = Mock(return_value=dict(records=[], responseMetadata={"nextCursor": "same"}))
        with self.assertRaises(ProviderError):
            fetch_epic(self.secret("Epic Games"), get=get)
        self.assertEqual(get.call_count, 2)

    def test_ea_entitlements_exclude_dlc_and_keep_content_identity(self):
        def get(url, **kwargs):
            self.assertEqual(kwargs["hosts"], {EA_API})
            query = kwargs["data"]["query"]
            if "player{" in query:
                return {"data": {"me": {"player": {"pd": "account1", "displayName": "EA Fixture"}}}}
            if "ownedGameProducts" in query:
                return {"data": {"me": {"ownedGameProducts": {"next": None, "items": [
                    dict(originOfferId="Origin.OFR.50.123", product={"baseItem": {"gameType": "BASE_GAME"}}),
                    dict(originOfferId="dlc1", product={"baseItem": {"gameType": "DLC"}})]}}}}
            return {"data": {"legacyOffers": [dict(offerId="Origin.OFR.50.123", contentId="1234")],
                "gameProducts": {"items": [dict(originOfferId="Origin.OFR.50.123", baseItem=dict(title="Dragon Age", packArt={"largestImage": {"path": "https://media.contentapi.ea.com/cover.png"}}))]}}}
        snapshot, _ = fetch_ea(self.secret("EA"), get=get)
        self.assertEqual(len(snapshot["items"]), 1)
        self.assertEqual(snapshot["items"][0]["aliases"], ["Origin.OFR.50.123", "1234"])
        self.assertNotIn("playtime_seconds", snapshot["items"][0])

    def test_gog_profile_stats_minutes_are_converted_to_seconds(self):
        def get(url, **kwargs):
            if "menu.gog.com" in url:
                return dict(isLoggedIn=True, userId="account1", username="fixture")
            return dict(pages=1, _embedded={"items": [dict(game=dict(id="1207659017", title="The Witcher 3", image="https://images.gog-statics.com/cover.jpg"),
                stats={"account1": {"playtime": 60, "lastSession": "2026-01-01T12:00:00Z"}})]})
        snapshot, _ = fetch_gog(self.secret("GOG"), get=get)
        self.assertEqual(snapshot["items"][0]["playtime_seconds"], 3600)

    def test_gog_signed_out_is_not_interpreted_as_no_owned_games(self):
        with self.assertRaises(SignInRequired):
            fetch_gog(self.secret("GOG"), get=lambda *_a, **_k: dict(isLoggedIn=False))

    def test_cancel_keeps_snapshot_storage_unchanged(self):
        self.secret()
        old = self.snapshot()
        save_snapshot("Steam", old)
        with self.assertRaises(InterruptedError):
            fetch_steam(load_secret("Steam"), canceled=lambda: True, get=Mock())
        self.assertEqual(load_snapshots()["Steam"], old)

    def test_titles_never_assign_ownership_or_launch_identity(self):
        ea = self.other(name="Cyberpunk 2077", launcher="EA", app_id="registry-title")
        snapshot = self.snapshot("EA", [dict(id="offer1", title=ea.name, aliases=["offer1"])])
        records, facts = compose([ea], {ea.key: dict(product_id="")}, {"EA": snapshot})
        self.assertEqual(len(records), 2)
        self.assertNotIn("owned", facts[ea.key])

    def test_explicit_owned_link_is_bound_to_account_and_installation(self):
        ea = self.other(launcher="EA", app_id="registry-title")
        snapshot = self.snapshot("EA", [dict(id="offer1", title=ea.name, aliases=["offer1"])])
        from gg_desktop.models import _path_key
        links = {ea.key: dict(provider="EA", account_id=SID, product_id="offer1", install_key=_path_key(ea.install_path))}
        records, facts = compose([ea], {}, {"EA": snapshot}, links=links)
        self.assertEqual(len(records), 1)
        self.assertTrue(facts[ea.key]["owned"])
        links[ea.key]["account_id"] = "different"
        self.assertEqual(len(compose([ea], {}, {"EA": snapshot}, links=links)[0]), 2)

    def test_steam_native_action_never_uses_an_artwork_or_alias_id(self):
        plan = native_action(self.game, dict(product_id="999999"), "uninstall")
        self.assertEqual(plan.uri, "steam://uninstall/1091500")
        self.assertTrue(plan.confirmation)

    def test_epic_launch_uses_namespace_catalog_and_app_name(self):
        game = self.other(launcher="Epic Games", app_id="app1")
        plan = native_action(game, dict(product_id="app1", namespace="ns1", catalog_id="catalog1"), "launch")
        self.assertEqual(plan.uri, "com.epicgames.launcher://apps/ns1%3Acatalog1%3Aapp1?action=launch&silent=true")
        self.assertTrue(native_action(game, dict(product_id="app1"), "validate").handoff)

    def test_ea_launch_and_ubisoft_uninstall_are_real_native_requests(self):
        ea = self.other(launcher="EA")
        plan = native_action(ea, dict(product_id="Origin.OFR.50.123"), "launch")
        self.assertIn("origin2://game/launch?offerIds=Origin.OFR.50.123", plan.uri)
        ubi = self.other(launcher="Ubisoft Connect")
        plan = native_action(ubi, dict(product_id="123"), "uninstall")
        self.assertEqual(plan.uri, "uplay://uninstall/123")
        self.assertTrue(plan.confirmation)

    def test_rockstar_native_uninstall_has_the_selected_title_id(self):
        exe = self.root/"Launcher.exe"
        exe.write_bytes(b"MZ fixture")
        game = self.other()
        plan = native_action(game, dict(product_id="rdr2"), "uninstall", client_finder=lambda _p: str(exe))
        self.assertEqual(plan.argv, (str(exe), "-enableFullMode", "-uninstall=rdr2"))
        self.assertTrue(plan.confirmation)

    def test_gog_uses_only_its_own_uninstaller(self):
        game = self.other(launcher="GOG", app_id="1207659017")
        exe = self.install/"unins000.exe"
        exe.write_bytes(b"MZ fixture")
        plan = native_action(game, dict(product_id=game.app_id), "uninstall")
        self.assertEqual(plan.argv, (str(exe),))
        self.assertTrue(plan.confirmation)

    def test_native_process_dispatch_passes_argument_array_without_a_shell(self):
        program = self.root/"Launcher.exe"
        program.write_bytes(b"MZ fixture")
        spawn = Mock()
        with patch("gg_desktop.games_native.WINDOWS_NATIVE", True):
            execute(Action("Native", argv=(str(program), "-launchTitleInFolder", str(self.install))), Mock(), spawn=spawn)
        self.assertEqual(spawn.call_args.args[0], [str(program), "-launchTitleInFolder", str(self.install)])
        self.assertIs(spawn.call_args.kwargs["shell"], False)

    def test_uninstalled_owned_game_cannot_uninstall_an_installation(self):
        records, facts = compose([], {}, {"Steam": self.snapshot()})
        game = records[0]
        self.assertEqual(native_action(game, facts[game.key], "install").uri, "steam://install/1091500")
        with self.assertRaises(ValueError):
            native_action(game, facts[game.key], "uninstall")

    def test_uninstaller_command_parser_rejects_ambiguous_or_shell_syntax(self):
        self.assertEqual(split_command('"C:\\Games\\My Game\\unins000.exe" /uninstall "Game id"'), [r"C:\Games\My Game\unins000.exe", "/uninstall", "Game id"])
        self.assertEqual(split_command(r"C:\Games\My Game\unins000.exe"), [])
        self.assertEqual(split_command('"x.exe"\n evil'), [])

    def registry(self, entries):
        from contextlib import nullcontext
        registry = Mock(HKEY_LOCAL_MACHINE=1, HKEY_CURRENT_USER=2, KEY_WOW64_32KEY=32, KEY_WOW64_64KEY=64, KEY_READ=128)
        registry.OpenKey.side_effect = lambda parent, name, *args: nullcontext(name)
        def enum(_parent, index):
            if index >= len(entries):
                raise OSError()
            return list(entries)[index]
        def query(key, field):
            if field not in entries[key]:
                raise OSError()
            return entries[key][field], 1
        registry.EnumKey.side_effect = enum
        registry.QueryValueEx.side_effect = query
        return registry

    def test_registered_uninstaller_requires_exact_title_and_installation(self):
        game = self.other(launcher="Battle.net", name="Fixture Game")
        program = self.install/"uninstall.exe"
        program.write_bytes(b"MZ fixture")
        entry = dict(DisplayName=game.name, InstallLocation=str(self.install), UninstallString='"'+str(program)+'" /uninstall')
        self.assertEqual(registered_uninstaller(game, registry=self.registry({"game": entry})), (str(program), "/uninstall"))
        entry["DisplayName"] = "Another game"
        self.assertIsNone(registered_uninstaller(game, registry=self.registry({"game": entry})))
        entry["DisplayName"], entry["InstallLocation"] = game.name, str(self.root/"Other")
        self.assertIsNone(registered_uninstaller(game, registry=self.registry({"game": entry})))

    def test_registered_uninstaller_refuses_shells_and_conflicting_commands(self):
        game = self.other(name="Fixture Game")
        for name in ("cmd.exe", "powershell.exe", "uninstall.exe", "another.exe"):
            (self.install/name).write_bytes(b"MZ fixture")
        entry = dict(DisplayName=game.name, InstallLocation=str(self.install), UninstallString='"'+str(self.install/"cmd.exe")+'" /c anything')
        self.assertIsNone(registered_uninstaller(game, registry=self.registry({"shell": entry})))
        entry["UninstallString"] = '"'+str(self.install/"uninstall.exe")+'"'
        other = {**entry, "UninstallString": '"'+str(self.install/"another.exe")+'"'}
        self.assertIsNone(registered_uninstaller(game, registry=self.registry({"first": entry, "second": other})))

    def test_msi_uninstall_uses_verified_product_and_system_executable(self):
        game = self.other(name="Fixture Game")
        windows = self.root/"Windows"
        (windows/"System32").mkdir(parents=True)
        program = windows/"System32/msiexec.exe"
        program.write_bytes(b"MZ fixture")
        guid = "{12345678-1234-1234-1234-123456789ABC}"
        entry = dict(DisplayName=game.name, InstallLocation=str(self.install), UninstallString="msiexec.exe /I"+guid)
        with patch.dict(os.environ, {"SystemRoot": str(windows)}):
            self.assertEqual(registered_uninstaller(game, registry=self.registry({guid: entry})), (str(program), "/x", guid))
            self.assertIsNone(registered_uninstaller(game, registry=self.registry({"unrelated-guid": entry})))
            entry.pop("InstallLocation")
            self.assertIsNone(registered_uninstaller(game, registry=self.registry({guid: entry})))

    def test_steam_local_update_and_playtime_are_read_from_selected_profile(self):
        (self.steam_root/"steamapps/appmanifest_1091500.acf").write_text('"AppState" {"appid" "1091500" "installdir" "Game" "StateFlags" "6" "buildid" "100" "TargetBuildID" "101"}')
        profile = self.steam_root/"userdata"/str(int(SID)-76561197960265728)/"config"
        profile.mkdir(parents=True)
        (profile/"localconfig.vdf").write_text('"UserLocalConfigStore" {"Software" {"Valve" {"Steam" {"apps" {"1091500" {"Playtime" "30" "LastPlayed" "1700000000"}}}}}}')
        facts = local_facts([self.game], [self.steam_root], {"Steam": {"account_id": SID}})[self.game.key]
        self.assertEqual(facts["playtime_seconds"], 1800)
        self.assertTrue(facts["update_available"])

    def test_ea_installer_xml_identity_is_read_without_entity_expansion(self):
        game = self.other(launcher="EA", app_id="registry-name")
        installer = self.install/"__Installer"
        installer.mkdir()
        (installer/"installerdata.xml").write_text('<game><contentIDs><contentID>1234</contentID></contentIDs></game>')
        self.assertEqual(installed_facts(game)["product_id"], "1234")
        (installer/"installerdata.xml").write_text('<!DOCTYPE x [<!ENTITY boom "bad">]><game><contentID>&boom;</contentID></game>')
        self.assertEqual(installed_facts(game)["product_id"], "")

    def test_ledger_counts_observed_seconds_and_not_sleep_or_restart_gaps(self):
        ledger = PlaytimeLedger()
        ledger.sample({self.game.key}, monotonic=10, now=1000)
        ledger.sample({self.game.key}, monotonic=15, now=1005)
        self.assertEqual(ledger.records[self.game.key]["seconds"], 5)
        ledger.sample({self.game.key}, monotonic=1000, now=1990)
        self.assertEqual(ledger.records[self.game.key]["seconds"], 5)
        fresh = PlaytimeLedger()
        fresh.sample({self.game.key}, monotonic=2000, now=2990)
        self.assertEqual(fresh.records[self.game.key]["seconds"], 5)

    def test_remote_total_and_tracked_delta_do_not_double_count(self):
        item = dict(id="1091500", title=self.game.name, aliases=["1091500"], playtime_seconds=7200,
                    tracked_bases={self.game.key: 500}, display_floors={self.game.key: 7200})
        _, facts = compose([self.game], {self.game.key: dict(product_id="1091500")}, {"Steam": self.snapshot(items=[item])},
            tracked={self.game.key: dict(seconds=560)})
        self.assertEqual(facts[self.game.key]["display_playtime"], 7260)

    def test_process_matching_uses_directory_boundaries_and_ignores_launchers(self):
        paths = [str(self.install.parent/"Game Other/game.exe"), str(self.install/"Launcher.exe"), str(self.install/"Uninstall.exe")]
        self.assertEqual(running_games([self.game], paths), set())
        self.assertEqual(running_games([self.game], [str(self.install/"bin/game.exe")]), {self.game.key})

    def test_artwork_hosts_reject_credentials_non_https_and_unrelated_redirects(self):
        for url in ("http://cdn1.epicgames.com/a.png", "https://cdn1.epicgames.com.evil.invalid/a.png", "https://user:pass@cdn1.epicgames.com/a.png", "https://images.gog-statics.com/a.png?access_token=secret"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                checked_media(url)

    def test_provider_artwork_is_cached_without_account_headers_or_identity_changes(self):
        game = self.other(launcher="Epic Games", app_id="epic1")
        original = replace(game)
        image = Image.new("RGB", (60, 90), "red")
        get_image = Mock(return_value=image)
        result = remote_artwork(game, dict(artwork_url="https://cdn1.epicgames.com/art.png"), get_image=get_image)
        self.assertIsNotNone(result.image)
        self.assertEqual(get_image.call_args.args, ("https://cdn1.epicgames.com/art.png",))
        self.assertEqual(get_image.call_args.kwargs, {})
        self.assertEqual(game, original)
        self.assertIsNotNone(cached_artwork(game).image)

    def test_owned_uninstalled_artwork_does_not_publish_install_capability(self):
        records, facts = compose([], {}, {"Steam": self.snapshot()})
        game = records[0]
        with patch("gg_desktop.games_catalogue_artwork.official_artwork", return_value=Artwork(Image.new("RGB", (30, 40), "blue"))):
            self.assertIsNotNone(remote_artwork(game, facts[game.key]).image)
        self.assertNotIn("open_folder", game.capabilities)

    def test_ambiguous_wikipedia_page_does_not_supply_an_unrelated_cover(self):
        game = self.other(name="Unmatched Fixture", launcher="EA")
        with patch("gg_desktop.games_catalogue_artwork.official_artwork", return_value=Artwork()):
            get_image = Mock()
            result = remote_artwork(game, get_json=lambda *_a, **_k: {"query": {"pages": {"1": {"title": "Another game", "thumbnail": {"source": "https://upload.wikimedia.org/a.png"}}}}}, get_image=get_image)
        self.assertIsNone(result.image)
        get_image.assert_not_called()


if __name__ == "__main__":
    unittest.main()
