"""Steam Workshop items with real names instead of numbers.

Steam keeps each Workshop item in a folder named by its number (steamapps/workshop/content/<game>/<item>), with a record
of what is installed in steamapps/workshop/appworkshop_<game>.acf (size, the item's update time when Steam downloaded it).
Titles, pictures and descriptions live on Steam: they come from Steam's public Web API
(ISteamRemoteStorage/GetPublishedFileDetails, no account or key needed), up to 100 items per request, and are cached in
Game Grave's folder so each item is asked once. "Steam has a newer version" means Steam's update time is later than the
one recorded when your copy was downloaded; Steam installs it itself. Unsubscribing is done on the item's Steam page.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import time
import urllib.parse
import urllib.request

import core

API = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
HOSTS = ("api.steampowered.com",)
PREVIEW_HOSTS = ("steamuserimages-a.akamaihd.net", "images.steamusercontent.com", "steamusercontent-a.akamaihd.net",
                 "shared.akamai.steamstatic.com", "shared.fastly.steamstatic.com", "steamcdn-a.akamaihd.net")
BATCH = 100
MAX_ITEMS = 2000
CACHE_DAYS = 3


class WorkshopError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkshopItem:
    item_id: str
    app_id: str
    folder: Path
    size: int
    installed_updated: int     # Steam's update time recorded when this copy was downloaded
    title: str = ""
    description: str = ""
    preview: str = ""
    steam_updated: int = 0
    tags: tuple = ()
    removed: bool = False      # Steam no longer lists it (taken down or private)

    @property
    def name(self):
        return self.title or f"Workshop item {self.item_id}"

    @property
    def update_waiting(self):
        return bool(self.steam_updated and self.installed_updated and self.steam_updated > self.installed_updated)

    @property
    def page(self):
        return f"steam://url/CommunityFilePage/{self.item_id}"

    @property
    def web_page(self):
        return f"https://steamcommunity.com/sharedfiles/filedetails/?id={self.item_id}"


def _items_record(acf: dict, key: str) -> dict:
    root = acf.get("appworkshop", acf) if isinstance(acf, dict) else {}
    lowered = {str(k).casefold(): v for k, v in root.items()} if isinstance(root, dict) else {}
    value = lowered.get(key.casefold(), {})
    return value if isinstance(value, dict) else {}


def _int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def local_items(libraries, app_id: str):
    """Installed Workshop items for one game across Steam libraries, from the folders and Steam's own record."""
    found = {}
    for library in libraries:
        workshop = Path(library) / "steamapps" / "workshop"
        content = workshop / "content" / str(app_id)
        if not content.is_dir():
            continue
        record = _items_record(core.read_vdf(workshop / f"appworkshop_{app_id}.acf"), "WorkshopItemsInstalled")
        record = {str(k): v for k, v in record.items()}
        try:
            folders = [p for p in content.iterdir() if p.is_dir() and p.name.isdecimal()]
        except OSError:
            folders = []
        for folder in folders[:MAX_ITEMS]:
            info = record.get(folder.name, {}) if isinstance(record.get(folder.name), dict) else {}
            info = {str(k).casefold(): v for k, v in info.items()}
            found[folder.name] = WorkshopItem(folder.name, str(app_id), folder, _int(info.get("size")),
                                              _int(info.get("timeupdated")))
    return sorted(found.values(), key=lambda i: i.item_id)


def workshop_games(libraries):
    """App IDs that have Workshop content on this PC."""
    ids = set()
    for library in libraries:
        content = Path(library) / "steamapps" / "workshop" / "content"
        try:
            ids |= {p.name for p in content.iterdir() if p.is_dir() and p.name.isdecimal()}
        except OSError:
            pass
    return sorted(ids)


# ------------------------------------------------------------------ names from Steam (cached)
def cache_path() -> Path:
    return core.config_dir() / "workshop_names.json"


def load_cache(path: Path | None = None) -> dict:
    try:
        data = json.loads((path or cache_path()).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_cache(cache: dict, path: Path | None = None):
    target = path or cache_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    temp.replace(target)


def stale(entry: dict, now=None) -> bool:
    return not entry or (now or time.time()) - float(entry.get("fetched", 0)) > CACHE_DAYS * 86400


def parse_details(text: str) -> dict:
    data = json.loads(text)
    out = {}
    for d in (data.get("response") or {}).get("publishedfiledetails") or []:
        item = str(d.get("publishedfileid") or "")
        if not item.isdecimal():
            continue
        if int(d.get("result") or 0) != 1:
            out[item] = {"removed": True}
            continue
        out[item] = {"title": str(d.get("title") or "")[:200], "description": str(d.get("description") or "")[:600],
                     "preview": str(d.get("preview_url") or "")[:500], "updated": _int(d.get("time_updated")),
                     "size": _int(d.get("file_size")),
                     "tags": [str(t.get("tag") or "") for t in d.get("tags") or [] if isinstance(t, dict)][:8]}
    return out


def fetch_details(item_ids, opener=None, timeout=20) -> dict:
    """Ask Steam's public Web API for these items' titles, pictures and update times (100 per request)."""
    ids = [i for i in item_ids if str(i).isdecimal()][:MAX_ITEMS]
    out = {}
    for start in range(0, len(ids), BATCH):
        chunk = ids[start:start + BATCH]
        body = {"itemcount": str(len(chunk))}
        body.update({f"publishedfileids[{n}]": i for n, i in enumerate(chunk)})
        request = urllib.request.Request(API, data=urllib.parse.urlencode(body).encode("ascii"),
                                         headers={"User-Agent": "GameGrave", "Content-Type": "application/x-www-form-urlencoded"})
        try:
            with (opener or urllib.request.urlopen)(request, timeout=timeout) as response:
                out.update(parse_details(response.read(8_000_000).decode("utf-8", "replace")))
        except (OSError, ValueError) as problem:
            raise WorkshopError("Steam didn't answer, so Workshop names couldn't be read right now.") from problem
    return out


def refresh_names(items, cache: dict, fetch=fetch_details, now=None) -> dict:
    """Fetch names for items not cached (or cached more than a few days ago). Returns the updated cache."""
    now = now or time.time()
    wanted = [i.item_id for i in items if stale(cache.get(i.item_id, {}), now)]
    if not wanted:
        return cache
    fresh = fetch(wanted)
    merged = dict(cache)
    for item_id, details in fresh.items():
        merged[item_id] = dict(details, fetched=now)
    return merged


def with_names(items, cache: dict):
    out = []
    for item in items:
        e = cache.get(item.item_id) or {}
        out.append(WorkshopItem(item.item_id, item.app_id, item.folder, item.size or _int(e.get("size")),
                                item.installed_updated, str(e.get("title") or ""), str(e.get("description") or ""),
                                str(e.get("preview") or ""), _int(e.get("updated")), tuple(e.get("tags") or ()),
                                bool(e.get("removed"))))
    return out


def preview_allowed(url: str) -> bool:
    parts = urllib.parse.urlsplit(url or "")
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and any(host == h or host.endswith("." + h) for h in PREVIEW_HOSTS)
