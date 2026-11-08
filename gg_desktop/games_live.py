"""Live library services used only by the Games controller."""
from __future__ import annotations

from pathlib import Path
import threading
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QLabel, QMenu
from shiboken6 import isValid

from core import age_text
from gg_desktop.games_account_store import PROVIDERS, load_secret, load_snapshots, read_document, save_secret, save_snapshot, update_secret_if_current, write_document
from gg_desktop.games_connections import Connections
from gg_desktop.games_library_data import compose, local_facts
from gg_desktop.games_native import CLIENT_NAMES, executable
from gg_desktop.games_providers import FETCHERS
from gg_desktop.games_sources import LAUNCHERS, combine_games, launcher_bucket, registered_games
from gg_desktop.games_tracking import tracker_for
from gg_desktop.models import _path_key


def duration(seconds):
    seconds = max(0, int(seconds or 0))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds//60}m"
    return f"{seconds//3600}h {(seconds%3600)//60}m"


class LiveGames:
    def initialize_live(self):
        self.base_records = list(self.records)
        self.native, self.facts = {}, {}
        self.snapshots = load_snapshots()
        self.sync_cancel = threading.Event()
        self.syncing = self.local_loading = False
        self.connections_dialog = None
        self.provider_errors = {}
        self.tracker = tracker_for(self.window)
        self.tracker.register(self.base_records)
        self.tracker.changed.connect(self.tracking_changed)
        self.last_active = set()
        self.last_sync = 0
        self.identities = read_document("identity-index.json", {})
        self.live_timer = QTimer(self.page)
        self.live_timer.setInterval(60000)
        self.live_timer.timeout.connect(self.periodic_refresh)
        self.live_timer.start()

    def fact(self, game):
        return self.facts.get(game.key, {}) if game else {}

    def is_installed(self, game):
        return self.fact(game).get("installed", game.status.startswith("Installed"))

    def last_played(self, game):
        return self.fact(game).get("last_played_at") or game.last_played_at

    def identity_keys(self, game):
        facts = self.fact(game)
        ids = {facts.get("product_id"), facts.get("remote_product_id")}
        ids.update(facts.get("identity_aliases", []))
        return {launcher_bucket(game.launcher)+":"+str(value) for value in ids if isinstance(value, str) and value}

    def favorite_aliases(self, game):
        result = {game.key}
        for key in self.identity_keys(game):
            aliases = self.identities.get(key, [])
            if isinstance(aliases, list):
                result.update(value for value in aliases if isinstance(value, str) and len(value) <= 4096)
        return result

    def is_favorite(self, game):
        return bool(self.favorite_aliases(game) & set(self.window.settings.get("desktop_favorites", [])))

    def status_text(self, game):
        if game.key in self.tracker.ledger.active:
            return "Playing now"
        installed = self.is_installed(game)
        if self.fact(game).get("owned"):
            return ("✓ Installed" if installed else "Not installed") + " · In " + game.launcher + " library"
        if not installed and game.status.startswith("Installed"):
            return "Installation unavailable · Scan PC"
        return "✓ Installed" if installed else game.status

    def values(self, game):
        facts = self.fact(game)
        played = self.last_played(game)
        return dict(status=self.status_text(game), playtime=duration(facts.get("display_playtime", 0)),
                    last_played="Playing now" if game.key in self.tracker.ledger.active else age_text(played) if played else "Not yet recorded",
                    updates=facts.get("update_label") or "Managed by " + game.launcher)

    def source_text(self, game, field):
        facts = self.fact(game)
        if field == "playtime":
            source = facts.get("playtime_source", "Tracked in Game Grave while the application is running")
            return source + (" plus Game Grave tracking on this PC since refresh" if source.endswith("account") else "")
        if field == "updates":
            source, stamp = facts.get("update_source", "Game launcher"), facts.get("update_checked_at")
        else:
            source, stamp = facts.get("ownership_source", facts.get("source", game.install_evidence)), facts.get("checked_at")
        return str(source) + (" · refreshed " + age_text(stamp) if stamp else "")

    def _compose(self, *, refresh=True):
        options = read_document("options.json", {})
        self.records, self.facts = compose(self.base_records, self.native, self.snapshots,
            links=options.get("links", {}), tracked=self.tracker.ledger.records)
        changed = False
        for game in self.records:
            keys = self.identity_keys(game)
            aliases = self.favorite_aliases(game)
            for key in keys:
                values = sorted(aliases)
                if self.identities.get(key) != values:
                    self.identities[key] = values
                    changed = True
        if changed:
            try:
                write_document("identity-index.json", self.identities)
            except (OSError, ValueError):
                pass  # Per-installation favorites continue using their own store.
        self.tracker.register(self.base_records)
        self.page.game_artwork.set_library(self.records, self.page.game_artwork.roots)
        if refresh:
            self.update_library_controls()
            self.window._fill_games()

    def update_library_controls(self):
        metrics = self.window.game_metrics
        metrics.set_value(0, len(self.records))
        for index, (bucket, _, _) in enumerate(LAUNCHERS, 1):
            metrics.set_value(index, sum(launcher_bucket(game.launcher) == bucket for game in self.records))
        favorites = set(self.window.settings.get("desktop_favorites", []))
        values = {"All Games": len(self.records), "Installed": sum(self.is_installed(game) for game in self.records),
                  "Not Installed": sum(self.fact(game).get("owned", False) and not self.is_installed(game) for game in self.records),
                  "Updates": sum(self.fact(game).get("update_available") is True for game in self.records),
                  "Favorites": sum(self.is_favorite(game) for game in self.records)}
        for name, control in self.window.game_chips.buttons.items():
            category = name.split(" (")[0]
            if category in values:
                unknown = sum(self.is_installed(game) and self.fact(game).get("update_available") is None for game in self.records) if category == "Updates" else 0
                control.setText(f"{category} ({values[category]}{'+' if unknown else ''})")
                if category == "Updates":
                    control.setToolTip(f"{values[category]} updates reported; {unknown} installations are managed by their launcher.")
        selected = self.window.game_filter.currentText()
        combo = self.window.game_filter
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(["All launchers"] + sorted({game.launcher for game in self.records}))
        if self.bucket:
            combo.addItem(self.bucket + " games", self.bucket)
            combo.setCurrentIndex(combo.count()-1)
        elif combo.findText(selected) >= 0:
            combo.setCurrentText(selected)
        combo.blockSignals(False)

    def refresh_sources(self):
        if not self._valid() or self.local_loading:
            return
        self.local_loading = True
        accepted = tuple(self.window.inventory.games)
        scanned = bool(self.window.inventory.scanned_at)
        roots, snapshots, closed = self.page.game_artwork.roots, self.snapshots, self.closed
        def work(_progress):
            extra = registered_games(canceled=closed.is_set) if scanned else []
            records = combine_games(accepted, extra)
            return records, local_facts(records, list(roots), snapshots)
        def finish(result, error):
            self.local_loading = False
            if error:
                self.window.status.setText("Some launcher metadata is unavailable. The previous library is retained.")
                return
            self.base_records, self.native = result
            self._compose()
            self.page.game_artwork.failed.clear()
            if self.last_sync == 0:
                self.sync_libraries(automatic=True)
        self._task(work, finish)

    def periodic_refresh(self):
        if self._valid():
            self.refresh_sources()
            if time.time()-self.last_sync > 300:
                self.sync_libraries(automatic=True)

    def reload_libraries(self):
        if self._valid():
            self.snapshots = load_snapshots()
            self._compose()

    def sync_libraries(self, providers=None, *, automatic=False):
        if not self._valid() or self.syncing:
            return
        providers = [provider for provider in (providers or PROVIDERS) if provider in FETCHERS and load_secret(provider)]
        if not providers:
            if not automatic:
                self.connections()
            return
        self.syncing = True
        self.last_sync = time.time()
        self.sync_cancel.clear()
        self.window.status.setText("Refreshing connected game libraries…")
        stopped, closed = self.sync_cancel, self.closed
        previous = self.snapshots
        inputs = {provider: load_secret(provider) for provider in providers}
        def work(progress):
            results, errors = {}, {}
            for provider in providers:
                if stopped.is_set() or closed.is_set():
                    break
                try:
                    snapshot, secret = FETCHERS[provider](inputs[provider], canceled=lambda: stopped.is_set() or closed.is_set(),
                        previous=previous.get(provider), progress=lambda amount, stage: progress(min(100, amount), stage),
                        on_credentials=lambda secret, provider=provider: update_secret_if_current(provider, secret, inputs[provider].get("connection_id")))
                    if stopped.is_set() or closed.is_set():
                        break
                    results[provider] = (snapshot, secret)
                except InterruptedError:
                    break
                except (ValueError, OSError, TypeError, KeyError) as exc:
                    # Provider errors are intentionally generic and never echo
                    # token responses, cookie contents or authenticated URLs.
                    errors[provider] = str(exc)[:180] if isinstance(exc, ValueError) else "The library could not be refreshed. Previous data retained."
            return results, errors
        def progress(amount, stage):
            self.window.status.setText(stage + f" ({amount}%)")
        def finish(packet, error):
            self.syncing = False
            if error:
                self.window.error("Library refresh incomplete", "The previous libraries were retained. Try connecting again.")
                return
            results, errors = packet
            committed = []
            if not stopped.is_set():
                for provider, (snapshot, secret) in results.items():
                    current = load_secret(provider)
                    if not current or current.get("connection_id") != inputs[provider].get("connection_id"):
                        continue  # Sign-out or account switching won the race.
                    if current.get("account_id") and current["account_id"] != secret.get("account_id"):
                        continue
                    try:
                        # Anchor account totals to this PC's current tracked
                        # counters so later sessions do not double-charge time.
                        for item in snapshot["items"]:
                            matches = [game for game in self.base_records if launcher_bucket(game.launcher) == launcher_bucket(provider)
                                and self.native.get(game.key, {}).get("product_id") in set(item.get("aliases", []) + [item["id"]])]
                            item["tracked_bases"] = {game.key: self.tracker.ledger.records.get(game.key, {}).get("seconds", 0) for game in matches}
                            item["display_floors"] = {game.key: max(item.get("playtime_seconds") or 0,
                                self.facts.get(game.key, {}).get("display_playtime", 0) if self.fact(game).get("account_id") == snapshot["account_id"] else 0) for game in matches}
                        save_secret(provider, secret)
                        save_snapshot(provider, snapshot)
                        committed.append(provider)
                    except (OSError, ValueError):
                        errors[provider] = "This library could not be saved. Previous data retained."
            self.provider_errors = errors
            self.reload_libraries()
            if self.connections_dialog is not None and isValid(self.connections_dialog):
                self.connections_dialog.refresh_status()
            if stopped.is_set():
                self.window.status.setText("Library refresh canceled. Previous libraries retained.")
            elif errors:
                self.window.status.setText("Library refresh incomplete: " + "; ".join(provider + ": " + message for provider, message in errors.items()))
            else:
                self.window.status.setText("Libraries refreshed: " + ", ".join(committed) + ".")
            self.page.game_artwork.failed.clear()
            self.window.game_grid.viewport().update()
        self._task(work, finish, progress=progress)

    def tracking_changed(self):
        if not self._valid():
            return
        active = set(self.tracker.ledger.active)
        self._compose(refresh=False)
        if active != self.last_active and not QApplication.activeModalWidget() and not QApplication.activePopupWidget():
            self.window._fill_games()
        else:
            game = self.selected()
            if game:
                values = self.values(game)
                for label in self.window.game_details.findChildren(QLabel):
                    field = label.property("gamesLiveField")
                    if field in values:
                        label.setText(values[field])
                        label.setToolTip(self.source_text(game, field))
        self.last_active = active

    def connections(self):
        if self.connections_dialog is None or not isValid(self.connections_dialog):
            self.connections_dialog = Connections(self)
        self.connections_dialog.refresh_status()
        self.connections_dialog.show()
        self.connections_dialog.raise_()

    def choose_launcher(self):
        choices = list(CLIENT_NAMES)
        provider, accepted = QInputDialog.getItem(self.window, "Choose launcher", "Launcher", choices, 0, False)
        if not accepted:
            return
        path, _ = QFileDialog.getOpenFileName(self.window, "Choose " + provider + " launcher", "", "Windows launcher (*.exe)")
        if not path:
            return
        try:
            target = executable(path)
            if Path(target).name.casefold() not in {name.casefold() for name in CLIENT_NAMES[provider]}:
                raise ValueError("Choose the launcher's own executable: " + ", ".join(CLIENT_NAMES[provider]))
            options = read_document("options.json", {})
            options.setdefault("launcher_paths", {})[provider] = target
            write_document("options.json", options)
            self.window.status.setText(provider + " launcher saved.")
        except (OSError, ValueError) as exc:
            self.window.error("Launcher not saved", str(exc))

    def link_owned(self, game):
        provider = next((name for name in PROVIDERS if launcher_bucket(name) == launcher_bucket(game.launcher)), None)
        snapshot = self.snapshots.get(provider, {})
        items = snapshot.get("items", [])
        if not items:
            self.connections()
            return
        choices = [str(item.get("title", "Unknown")) + " · " + str(item.get("id", "")) for item in items]
        choice, accepted = QInputDialog.getItem(self.window, "Link this installation to an owned game", game.name + "\nChoose its exact entry in your connected library:", choices, 0, False)
        if not accepted:
            return
        item = items[choices.index(choice)]
        options = read_document("options.json", {})
        options.setdefault("links", {})[game.key] = dict(provider=provider, account_id=snapshot["account_id"],
            product_id=item["id"], install_key=_path_key(game.install_path))
        write_document("options.json", options)
        self._compose()

    def library_options(self, position=None):
        menu = QMenu(self.page)
        menu.setStyleSheet("QMenu {background:#0b1118;color:#edf1f7;} QMenu::item:selected {background:#7d1529;}")
        menu.addAction("Connect game libraries…", self.connections)
        menu.addAction("Refresh library data", lambda: self.sync_libraries())
        cancel = menu.addAction("Cancel library refresh", self.sync_cancel.set)
        cancel.setEnabled(self.syncing)
        menu.addSeparator()
        auto = menu.addAction("Download missing artwork automatically")
        auto.setCheckable(True)
        auto.setChecked(read_document("options.json", {}).get("automatic_artwork", True))
        def toggle(checked):
            options = read_document("options.json", {})
            options["automatic_artwork"] = checked
            write_document("options.json", options)
            self.page.game_artwork.automatic_paused = not checked
            self.page.game_artwork.retry()
        auto.toggled.connect(toggle)
        menu.addAction("Download missing artwork now", lambda: self.download_artwork(tuple(self.records), missing_only=True))
        menu.exec(position or self.window.game_grid.mapToGlobal(self.window.game_grid.rect().topRight()))
        menu.deleteLater()
