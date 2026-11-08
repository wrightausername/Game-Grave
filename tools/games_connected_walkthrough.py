"""Real Qt journeys for connected libraries, using explicit fake HTTP results.

No personal accounts, authentication cookies or real game processes are used.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import json
import os
import tempfile
import threading
import time
from uuid import uuid4
from unittest.mock import patch


def walkthrough(output):
    if os.name != "nt":
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PIL import Image
    from PySide6.QtCore import QCoreApplication, QEvent, Qt, QTimer, Signal
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QAbstractButton, QApplication, QDialog, QLabel, QMenu, QPushButton, QVBoxLayout
    import core
    from gg_desktop.app import CrimsonWindow
    from gg_desktop.backend import Inventory
    from gg_desktop.game_artwork import Artwork, _save_picture
    from gg_desktop.games_account_store import load_secret, load_snapshots, read_document, save_secret, save_snapshot, write_document
    from gg_desktop.games_providers import fetch_steam
    from gg_desktop.models import merge_games
    from launchers import LauncherGame
    app = QApplication.instance() or QApplication([])
    output.mkdir(parents=True, exist_ok=True)
    cases = []
    def passed(name):
        cases.append(dict(name=name, result="passed"))
        (output/"games-connected-journeys.json").write_text(json.dumps(cases, indent=2), encoding="utf-8")
    def settle():
        QTest.qWait(25)
        time.sleep(.004)
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    def wait(predicate):
        end = time.monotonic()+15
        while not predicate() and time.monotonic() < end:
            settle()
        assert predicate(), "Connected Games UI did not finish"
    def idle(window):
        # A completed refresh schedules the next queued account on a zero-time
        # Qt timer. Require idle across two event-loop turns, not its gap.
        for _ in range(2):
            settle()
            wait(lambda: not window.workers and not window.page.games.syncing and not window.page.games.pending_sync
                 and not window.page.game_artwork.busy and not window.page.game_artwork.queue)
    def click(control):
        assert control.isEnabled(), control.text()
        QTest.mouseClick(control, Qt.LeftButton)
        settle()
    def detail_button(window, name=None, action=None):
        return next(button for button in window.game_details.findChildren(QAbstractButton)
                    if name and button.text() == name or action and button.property("gameNativeAction") == action)
    def select(window, *, provider=None, product=None, installed=None):
        window.page.games.filter_bucket(None)
        game = next(game for game in window._shown_games if (provider is None or game.launcher == provider)
            and (product is None or game.app_id == product) and (installed is None or window.page.games.is_installed(game) == installed))
        window.game_grid.setCurrentRow(next(i for i, row in enumerate(window._shown_games) if row.key == game.key))
        window.game_grid.scrollToItem(window.game_grid.currentItem())
        settle()
        return game
    def choose_menu(name):
        def choose():
            menu = app.activePopupWidget()
            assert isinstance(menu, QMenu)
            action = next(action for action in menu.actions() if action.text() == name)
            QTest.mouseClick(menu, Qt.LeftButton, pos=menu.actionGeometry(action).center())
        QTimer.singleShot(30, choose)
    with tempfile.TemporaryDirectory(prefix="Games-Connected-QA-") as temp:
        root = Path(temp)
        steam_root = root/"Steam"
        installed = steam_root/"steamapps/common/Cyberpunk"
        installed.mkdir(parents=True)
        (steam_root/"steamapps/appmanifest_1091500.acf").write_text('"AppState" {"appid" "1091500" "installdir" "Cyberpunk" "StateFlags" "6" "buildid" "100" "TargetBuildID" "101"}')
        Image.new("RGB", (80, 120), "#273f65").save(installed/"cover.png")
        steam = [core.SteamGame("1091500", "Cyberpunk 2077", str(steam_root), str(installed), 123000, None, "Disposable QA")]
        ea_path, rock_path, gog_path = (root/name for name in ("EA game", "Rockstar game", "GOG game"))
        for path in (ea_path, rock_path, gog_path):
            path.mkdir()
            Image.new("RGB", (80, 120), "#35264c").save(path/"cover.png")
        (ea_path/"__Installer").mkdir()
        (ea_path/"__Installer/installerdata.xml").write_text('<game><contentID>ea1234</contentID></game>')
        (rock_path/"RDR2.exe").write_bytes(b"MZ fixture - never executed")
        (gog_path/"unins000.exe").write_bytes(b"MZ fixture - never executed")
        other = [LauncherGame("Dragon Age: The Veilguard", "EA", str(ea_path), "registry-ea", None, "Registered fixture"),
                 LauncherGame("Red Dead Redemption 2", "Rockstar Games", str(rock_path), "rdr2", None, "Registered fixture"),
                 LauncherGame("The Witcher 3: Wild Hunt", "GOG", str(gog_path), "1234567", None, "Registered fixture")]
        inventory = Inventory(steam=steam, other=other, games=merge_games(steam, other), scanned_at="Explicit connected-library QA")
        shared_before = list(inventory.games)
        sid = "76561198000000001"
        accounts = {"Steam": sid, "Epic Games": "epic-fixture", "EA": "ea-fixture", "GOG": "gog-fixture"}
        state = dict(steam_minutes=120, fail=False)
        started, released = threading.Event(), threading.Event()
        calls = []
        def steam_get(_url, **_kwargs):
            if state["fail"]:
                from gg_desktop.games_http import ProviderError
                raise ProviderError("Offline fixture. Previous data retained.")
            return {"response": {"game_count": 2, "games": [dict(appid=1091500, name="Cyberpunk 2077", playtime_forever=state["steam_minutes"]),
                                                            dict(appid=620, name="Portal 2", playtime_forever=30)]}}
        def fake_fetch(provider):
            def fetch(secret, **kwargs):
                calls.append((provider, secret["account_id"]))
                if state.get("block") == provider:
                    state["block"] = None
                    started.set()
                    assert released.wait(10), "Fixture release timed out"
                if provider == "Steam":
                    return fetch_steam(secret, get=steam_get, **kwargs)
                items = {
                    "Epic Games": [dict(id="fortnite", title="Fortnite", aliases=["fortnite"], namespace="fn", catalog_id="catalog-fn", playtime_seconds=3600)],
                    "EA": [dict(id="Origin.OFR.50.123", title="Dragon Age: The Veilguard", aliases=["Origin.OFR.50.123", "ea1234"], content_id="ea1234"),
                           dict(id="Origin.OFR.50.456", title="Mass Effect Legendary Edition", aliases=["Origin.OFR.50.456"])],
                    "GOG": [dict(id="1234567", title="The Witcher 3: Wild Hunt", aliases=["1234567"], playtime_seconds=7200),
                            dict(id="7654321", title="Baldur's Gate 3", aliases=["7654321"], playtime_seconds=0)],
                }[provider]
                return dict(provider=provider, account_id=secret["account_id"], account_name="Disposable " + provider,
                            checked_at=time.time(), items=items), secret
            return fetch
        fetchers = {provider: fake_fetch(provider) for provider in accounts}
        class TestSignIn(QDialog):
            connected = Signal(str, object)
            def __init__(self, control, provider):
                super().__init__(control.window)
                self.setWindowTitle("Explicit sign-in boundary fixture")
                self.setAttribute(Qt.WA_DeleteOnClose)
                self.provider = provider
                self.setLayout(QVBoxLayout())
                finish = QPushButton("Complete fixture sign-in")
                def complete():
                    self.connected.emit(provider, dict(account_id=accounts[provider], account_name="Disposable " + provider,
                        access_token="FAKE-TEST-ONLY", connection_id=str(uuid4())))
                    self.accept()
                finish.clicked.connect(complete)
                self.layout().addWidget(finish)
                cancel = QPushButton("Cancel")
                cancel.clicked.connect(self.reject)
                self.layout().addWidget(cancel)
        def fixture_poster(game, facts=None, **kwargs):
            if kwargs.get("canceled", lambda: False)():
                return Artwork()
            image = Image.new("RGB", (80, 120), "#276548")
            _save_picture(game, image, "catalogue")
            return Artwork(image, "Explicit QA artwork response")
        with patch("core.config_dir", return_value=root/"Settings"), \
             patch("gg_desktop.app.load_settings", side_effect=lambda: dict(core.load_settings(), scan_on_launch=False)), \
             patch("gg_desktop.game_artwork.artwork_dir", return_value=root/"Private"), \
             patch("gg_desktop.games_live.registered_games", return_value=[]), \
             patch("gg_desktop.games_live.FETCHERS", fetchers), \
             patch("gg_desktop.games_connections.SignIn", TestSignIn), \
             patch("gg_desktop.games_controls.QDesktopServices.openUrl", return_value=True) as open_url, \
             patch.object(CrimsonWindow, "error") as errors:
            write_document("options.json", {"automatic_artwork": False})
            window = CrimsonWindow()
            window.show()
            window.resize(1450, 900)
            window.inventory = inventory
            window.navigate("Games")
            idle(window)
            window.page.games.tracker.timer.stop()
            choose_menu("Connect game libraries…")
            click(window.game_library_options)
            dialog = window.page.games.connections_dialog
            assert dialog.isVisible()
            assert all(not values[1].isEnabled() and not values[2].isEnabled() for values in dialog.buttons.values())
            passed("Library options exposes four account connections without changing the main page layout")
            click(dialog.buttons["Steam"][0])
            login = next(view for view in window.findChildren(TestSignIn) if view.isVisible())
            click(next(button for button in login.findChildren(QPushButton) if button.text() == "Cancel"))
            assert load_secret("Steam") == {} and "Steam" not in load_snapshots()
            passed("Canceling sign-in saves no connection and no owned games")
            for provider in accounts:
                click(dialog.buttons[provider][0])
                login = next(view for view in window.findChildren(TestSignIn) if view.isVisible())
                assert login.provider == provider
                click(next(button for button in login.findChildren(QPushButton) if button.text() == "Complete fixture sign-in"))
                idle(window)
                assert load_secret(provider)["account_id"] == accounts[provider]
                assert load_snapshots()[provider]["items"]
                passed("Account sign-in, storage and refresh wiring: " + provider)
            dialog.close()
            settle()
            control = window.page.games
            assert len(control.records) == 8 and inventory.games == shared_before
            assert len([game for game in control.records if control.fact(game).get("owned")]) == 7
            passed("Connected owned games merge by verified IDs while the shared inventory stays unchanged")
            click(window.game_tabs.buttons["Not Installed"])
            assert len(window._shown_games) == 4 and all(not control.is_installed(game) for game in window._shown_games)
            passed("Not Installed shows the four owned uninstalled titles from connected libraries")
            window.grab().save(str(output/"games-owned-not-installed-1450.png"))
            click(window.game_tabs.buttons["Updates"])
            assert [game.app_id for game in window._shown_games] == ["1091500"]
            passed("Updates shows the installation with a real client update flag")
            portal = select(window, provider="Steam", product="620", installed=False)
            click(detail_button(window, name="Install"))
            assert open_url.call_args.args[0].toString() == "steam://install/620"
            assert not detail_button(window, action="uninstall").isEnabled()
            passed("Owned uninstalled Steam game dispatches Install and cannot dispatch Uninstall")
            star = next(button for button in window.game_details.findChildren(QPushButton) if button.accessibleName() == "Add favorite")
            click(star)
            assert control.is_favorite(portal)
            passed("An owned uninstalled game can be favorited")
            # Simulate an accepted PC scan after a native client installed Portal.
            portal_path = steam_root/"steamapps/common/Portal2"
            portal_path.mkdir()
            Image.new("RGB", (80, 120), "#244663").save(portal_path/"cover.png")
            (steam_root/"steamapps/appmanifest_620.acf").write_text('"AppState" {"appid" "620" "installdir" "Portal2" "StateFlags" "4"}')
            steam.append(core.SteamGame("620", "Portal 2", str(steam_root), str(portal_path), 1000, None, "Accepted QA scan"))
            inventory.steam = steam
            inventory.games = merge_games(steam, other)
            control.refresh_sources()
            idle(window)
            portal_installed = select(window, provider="Steam", product="620", installed=True)
            assert control.is_favorite(portal_installed)
            assert len([game for game in control.records if game.launcher == "Steam" and game.app_id == "620"]) == 1
            passed("Owned game becomes Installed without a duplicate card or lost favorite")
            cyberpunk = select(window, provider="Steam", product="1091500", installed=True)
            before_time = control.fact(cyberpunk)["display_playtime"]
            ledger = control.tracker.ledger
            ledger.sample({cyberpunk.key}, monotonic=100, now=1700000100)
            for index in range(1, 14):
                ledger.sample({cyberpunk.key}, monotonic=100+5*index, now=1700000100+5*index)
            control.tracker.changed.emit()
            settle()
            assert control.fact(cyberpunk)["display_playtime"] == before_time+65
            play_label = next(label for label in window.game_details.findChildren(QLabel) if label.property("gamesLiveField") == "playtime")
            assert play_label.text() == "2h 1m"
            assert "Steam" in play_label.toolTip()
            passed("Observed game time updates the inspector live and names its source")
            state["steam_minutes"] = 121
            control.sync_libraries(["Steam"])
            idle(window)
            assert control.fact(cyberpunk)["display_playtime"] >= before_time+65
            passed("Refreshing imported playtime neither double-counts nor loses the tracked session")
            prior = load_snapshots()["Steam"]
            state["fail"] = True
            control.sync_libraries(["Steam"])
            idle(window)
            assert load_snapshots()["Steam"] == prior
            assert "Steam" in control.provider_errors
            state["fail"] = False
            passed("Offline refresh preserves the owned library and its previous timestamp")
            def block(provider):
                started.clear()
                released.clear()
                state["block"] = provider
                control.sync_libraries([provider])
                wait(started.is_set)
            before_calls = len(calls)
            block("Steam")
            control.sync_libraries(["Epic Games"])
            released.set()
            idle(window)
            assert [provider for provider, _ in calls[before_calls:]] == ["Steam", "Epic Games"]
            passed("Refreshing a second account during another sync queues and completes both refreshes")
            prior = load_snapshots()["Steam"]
            block("Steam")
            control.sync_cancel.set()
            released.set()
            idle(window)
            assert load_snapshots()["Steam"] == prior
            passed("Canceling an in-flight refresh retains the last complete catalogue")
            block("Steam")
            old_connection = load_secret("Steam")["connection_id"]
            accounts["Steam"] = str(int(sid)+1)
            control.connections()
            dialog = control.connections_dialog
            click(dialog.buttons["Steam"][0])
            login = next(view for view in window.findChildren(TestSignIn) if view.isVisible())
            click(next(button for button in login.findChildren(QPushButton) if button.text() == "Complete fixture sign-in"))
            assert load_secret("Steam")["connection_id"] != old_connection
            released.set()
            idle(window)
            assert load_snapshots()["Steam"]["account_id"] == accounts["Steam"]
            assert calls[-1] == ("Steam", accounts["Steam"])
            passed("Switching accounts during a refresh cannot restore the old account or drop the new refresh")
            dialog.close()
            settle()
            gog = select(window, provider="GOG", installed=True)
            with patch.object(window, "confirm", return_value=False), patch("gg_desktop.games_controls.execute_native") as dispatch:
                click(detail_button(window, action="uninstall"))
                dispatch.assert_not_called()
            passed("Canceling a native GOG uninstall dispatches nothing")
            with patch.object(window, "confirm", return_value=True), patch("gg_desktop.games_controls.execute_native") as dispatch:
                click(detail_button(window, action="uninstall"))
                assert dispatch.call_args.args[0].argv == (str(gog_path/"unins000.exe"),)
            passed("GOG Uninstall dispatches only that installation's native uninstaller")
            # Automatic artwork is exercised at its HTTP result boundary, not
            # by painting a cover directly into the widget.
            options = read_document("options.json", {})
            options["automatic_artwork"] = True
            write_document("options.json", options)
            with patch("gg_desktop.games_controls.remote_artwork", side_effect=fixture_poster) as artwork:
                control.page.game_artwork.retry()
                game = select(window, provider="Epic Games", installed=False)
                control.page.game_artwork.pixmap(game.key)
                idle(window)
                assert (game.key, "cover") in control.page.game_artwork.images and artwork.called
                assert "open_folder" not in game.capabilities
            passed("Automatic non-Steam artwork loads through the worker without granting installation capabilities")
            control.connections()
            dialog = control.connections_dialog
            click(dialog.buttons["EA"][2])
            assert load_secret("EA") == {} and "EA" not in load_snapshots()
            assert all(not (game.launcher == "EA" and not control.is_installed(game)) for game in control.records)
            assert any(game.launcher == "EA" and control.is_installed(game) for game in control.records)
            passed("Disconnect removes only that account's owned catalogue and keeps local installations")
            dialog.close()
            settle()
            errors.assert_not_called()
            window.grab().save(str(output/"games-connected-library-1450.png"))
            window.close()
            settle()
    print(f"PASS: {len(cases)} connected Games account/data/native-action journeys.", flush=True)
    return cases
