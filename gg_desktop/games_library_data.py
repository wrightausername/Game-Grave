"""Games-owned local facts, account-library composition and playtime ledger."""
from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import time

from core import _has_reparse_component, read_vdf
from gg_desktop.games_account_store import read_document, write_document
from gg_desktop.games_native import epic_installations, installed_facts
from gg_desktop.games_providers import identifier, number
from gg_desktop.games_sources import launcher_bucket
from gg_desktop.models import GameRecord, _path_key

STEAM_BASE = 76561197960265728


def _integer(value):
    try:
        result = int(value)
        return result if 0 <= result <= 10**13 else None
    except (ValueError, TypeError, OverflowError):
        return None


def local_facts(games, roots, snapshots=None):
    facts = {}
    epic_records = epic_installations() if any(launcher_bucket(game.launcher) == "Epic" for game in games) else {}
    for game in games:
        if not game.install_path or not Path(game.install_path).is_dir() or _has_reparse_component(game.install_path):
            facts[game.key] = dict(installed=False, source="Installation unavailable")
            continue
        try:
            facts[game.key] = installed_facts(game, roots, epic_records=epic_records)
            facts[game.key]["installed"] = game.status.startswith("Installed")
        except (OSError, ValueError, TypeError):
            facts[game.key] = dict(source="Installation metadata unavailable", installed=game.status.startswith("Installed"))
    account_id = str((snapshots or {}).get("Steam", {}).get("account_id", ""))
    for root in roots[:12]:
        root = Path(root)
        if not account_id:
            users = read_vdf(root/"config/loginusers.vdf").get("users", {})
            if isinstance(users, dict):
                recent = [(key, row) for key, row in users.items() if isinstance(row, dict) and str(row.get("mostrecent")) == "1"]
                if len(recent) == 1:
                    account_id = str(recent[0][0])
        account32 = str(int(account_id) - STEAM_BASE) if account_id.isdigit() and int(account_id) >= STEAM_BASE else ""
        directories = [root/"userdata"/account32] if account32 else []
        if not directories:
            try:
                if not _has_reparse_component(root/"userdata"):
                    directories = [path for path in (root/"userdata").iterdir() if path.name.isdecimal() and path.is_dir() and not _has_reparse_component(path)]
                    if len(directories) != 1:
                        directories = []  # Never combine different people's playtime.
            except OSError:
                directories = []
        for directory in directories:
            path = directory/"config/localconfig.vdf"
            config = read_vdf(path)
            store = config.get("userlocalconfigstore", config)
            apps = store.get("software", {}).get("valve", {}).get("steam", {}).get("apps", {}) if isinstance(store, dict) else {}
            if not isinstance(apps, dict):
                continue
            for game in games:
                if game.launcher != "Steam":
                    continue
                data = apps.get(str(game.app_id), {})
                if not isinstance(data, dict):
                    continue
                minutes, last = _integer(data.get("playtime")), _integer(data.get("lastplayed"))
                if minutes is not None:
                    facts[game.key].update(playtime_seconds=minutes*60, playtime_source="Steam local profile")
                if last:
                    facts[game.key]["last_played_at"] = last
    return facts


def compose(installed, native, snapshots, *, links=None, tracked=None):
    """Merge by provider IDs or an explicit user link, never title similarity."""
    records = list(installed)
    output = {game.key: dict(native.get(game.key, {})) for game in records}
    links = links if isinstance(links, dict) else {}
    tracked = tracked if isinstance(tracked, dict) else {}
    identities, user_links = {}, {}
    for game in installed:
        if len(game.claimed_by) != 1:
            continue
        bucket = launcher_bucket(game.launcher)
        local = native.get(game.key, {})
        ids = {identifier(local.get("product_id"))}
        ids.update(identifier(value) for value in local.get("aliases", []) if isinstance(value, str))
        if bucket in ("Steam", "Epic", "GOG"):
            ids.add(identifier(game.app_id))
        for ident in ids - {""}:
            identities.setdefault((bucket, ident), []).append(game)
        link = links.get(game.key, {})
        if isinstance(link, dict) and not local.get("product_id") and link.get("install_key") == _path_key(game.install_path):
            user_links.setdefault((bucket, link.get("account_id"), link.get("product_id")), []).append(game)
    for provider, snapshot in snapshots.items():
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get("items"), list):
            continue
        account_id = identifier(snapshot.get("account_id"))
        if not account_id:
            continue
        bucket = launcher_bucket(provider)
        for item in snapshot["items"][:10000]:
            if not isinstance(item, dict) or not identifier(item.get("id")) or not isinstance(item.get("title"), str):
                continue
            product = item["id"]
            aliases = {identifier(value) for value in item.get("aliases", [])[:100] if isinstance(value, str)} if isinstance(item.get("aliases"), list) else set()
            aliases.add(product)
            match_map = {game.key: game for alias in aliases for game in identities.get((bucket, alias), ())}
            match_map.update({game.key: game for game in user_links.get((bucket, account_id, product), ())})
            matches = list(match_map.values())
            if not matches:
                key = f"{provider}:owned:{account_id}:{product}"
                game = GameRecord(key, item["title"][:170], provider, product, "",
                    "Owned game returned by the connected " + provider + " account", None, "Not installed",
                    item.get("last_played_at"), provider + " account", "Not installed (connected library)", ("inspect", "install"), (provider,))
                records.append(game)
                output[key] = dict(installed=False, product_id=product, source=provider + " account")
                matches = [game]
            for game in matches:
                fact = output.setdefault(game.key, {})
                original_id = fact.get("product_id", "")
                fact.update(owned=True, account_id=account_id, account_name=str(snapshot.get("account_name", provider))[:160],
                    ownership_source=provider + " connected library", checked_at=number(snapshot.get("checked_at")) or 0,
                    artwork_url=item.get("artwork_url", ""), remote_product_id=product)
                fact["identity_aliases"] = [alias for alias in aliases if alias]
                # Existing installations retain their native identity. Only
                # EA's verified content->offer association changes its launch ID.
                if not original_id or provider == "EA":
                    fact["product_id"] = product
                for field in ("namespace", "catalog_id", "latest_version"):
                    value = item.get(field)
                    if isinstance(value, str) and value:
                        fact[field] = value[:300]
                seconds = number(item.get("playtime_seconds"))
                if seconds is not None:
                    bases = item.get("tracked_bases", {})
                    floors = item.get("display_floors", {})
                    fact.update(playtime_seconds=seconds, playtime_source=provider + " account",
                                tracked_base=number(bases.get(game.key)) or 0 if isinstance(bases, dict) else 0,
                                display_floor=number(floors.get(game.key)) or seconds if isinstance(floors, dict) else seconds)
                last = number(item.get("last_played_at"))
                if last:
                    fact["last_played_at"] = last
                if provider == "Epic Games" and fact.get("installed_version") and fact.get("latest_version"):
                    changed = fact["installed_version"] != fact["latest_version"]
                    fact.update(update_available=changed, update_label="Update available" if changed else "Up to date",
                                update_source="Epic live Windows assets", update_checked_at=snapshot.get("checked_at"))
    for game in records:
        fact = output.setdefault(game.key, {})
        counter = tracked.get(game.key, {})
        seconds = number(counter.get("seconds")) or 0
        baseline = number(fact.get("playtime_seconds"))
        if baseline is not None:
            if fact.get("playtime_source", "").endswith("account"):
                fact["display_playtime"] = max(number(fact.get("display_floor")) or baseline,
                    baseline + max(0, seconds - (number(fact.get("tracked_base")) or 0)))
            else:
                fact["display_playtime"] = max(baseline, seconds)
        else:
            fact.update(display_playtime=seconds, playtime_source="Tracked in Game Grave")
        fact["last_played_at"] = max(number(fact.get("last_played_at")) or 0,
                                     number(counter.get("last_played_at")) or 0,
                                     number(game.last_played_at) or 0) or None
    return sorted(records, key=lambda game: (game.name.casefold(), game.key)), output


class PlaytimeLedger:
    def __init__(self):
        data = read_document("playtime.json", {})
        self.records = {key: row for key, row in data.items() if isinstance(key, str) and isinstance(row, dict)
                        and number(row.get("seconds")) is not None}
        self.active = set()
        self.previous_tick = None

    def sample(self, active, *, monotonic=None, now=None):
        tick = time.monotonic() if monotonic is None else monotonic
        now = time.time() if now is None else now
        elapsed = tick - self.previous_tick if self.previous_tick is not None else 0
        # Do not charge an unobserved period, such as laptop sleep or app exit.
        delta = elapsed if 0 <= elapsed <= 20 else 0
        for key in set(active):
            row = self.records.setdefault(key, {"seconds": 0})
            if key in self.active:
                row["seconds"] = (number(row.get("seconds")) or 0) + delta
            row["last_played_at"] = now
        changed = bool(active or self.active)
        self.active, self.previous_tick = set(active), tick
        if changed:
            write_document("playtime.json", self.records)
        return changed


def running_games(games, processes):
    active = set()
    ignored = ("launcher", "unins", "crash", "installer", "setup", "anticheat", "battleye", "touchup", "helper", "config", "settings")
    for path in processes:
        name = Path(path).name.casefold()
        if not name.endswith(".exe") or any(word in name for word in ignored) or name in ("steam.exe", "galaxyclient.exe", "eadesktop.exe"):
            continue
        child = _path_key(path)
        if any(part in ("__installer", "_commonredist", "redist", "support", "tools") for part in child.split("\\")):
            continue
        for game in games:
            if "open_folder" in game.capabilities and game.install_path and not _has_reparse_component(game.install_path):
                if child.startswith(_path_key(game.install_path).rstrip("\\") + "\\"):
                    active.add(game.key)
    return active


def windows_process_paths():
    if os.name != "nt":
        return []
    import ctypes
    from ctypes import wintypes
    class Entry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", wintypes.LONG), ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR*260)]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        return []
    paths, entry = [], Entry()
    entry.dwSize = ctypes.sizeof(entry)
    try:
        ok = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            handle = kernel.OpenProcess(0x1000, False, entry.th32ProcessID)
            if handle:
                try:
                    length = wintypes.DWORD(32768)
                    buffer = ctypes.create_unicode_buffer(length.value)
                    if kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length)):
                        paths.append(buffer.value)
                finally:
                    kernel.CloseHandle(handle)
            ok = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    return paths
