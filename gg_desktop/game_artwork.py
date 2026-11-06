"""Bounded game artwork, exact official identities, and private local preferences.

Reading a Games page never makes network requests. Local launcher art is loaded
first. Official downloads happen only when requested, and cached covers work
offline. Artwork associations never change installation evidence or capabilities.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import re
import tempfile
import warnings
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from core import _has_reparse_component, config_dir

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_METADATA = 512 * 1024
MAX_PIXELS = 24_000_000
CDN = {"shared.fastly.steamstatic.com", "shared.cloudflare.steamstatic.com", "cdn.cloudflare.steamstatic.com"}
HOSTS = CDN | {"api.steampowered.com", "store.steampowered.com"}


def artwork_dir():
    return config_dir() / "Games"


def game_id(game):
    return sha256((game.key + "\n" + game.name).encode("utf-8", errors="replace")).hexdigest()


def _safe_directory(folder):
    existing = folder
    while not existing.exists() and not existing.is_symlink() and existing.parent != existing:
        existing = existing.parent
    if _has_reparse_component(existing):
        raise ValueError("Game artwork storage is redirected.")
    folder.mkdir(parents=True, exist_ok=True)
    if _has_reparse_component(folder):
        raise ValueError("Game artwork storage is redirected.")


def _atomic(target, raw):
    _safe_directory(target.parent)
    if (target.exists() or target.is_symlink()) and _has_reparse_component(target):
        raise ValueError("Game artwork storage is redirected.")
    fd, name = tempfile.mkstemp(prefix=".games-", suffix=".tmp", dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if _has_reparse_component(target.parent) or (target.is_symlink() or target.exists() and _has_reparse_component(target)):
            raise ValueError("Game artwork storage changed.")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def load_preferences():
    target = artwork_dir() / "games.json"
    empty = {"schema": 1, "executables": {}}
    try:
        if _has_reparse_component(target) or not target.is_file() or target.stat().st_size > MAX_METADATA:
            return empty
        with target.open("rb") as stream:
            data = json.loads(stream.read(MAX_METADATA + 1))
        if not isinstance(data, dict) or data.get("schema") != 1 or not isinstance(data.get("executables"), dict):
            return empty
        return {"schema": 1, "executables": {k: v for k, v in data["executables"].items()
                if re.fullmatch(r"[0-9a-f]{64}", k) and isinstance(v, str) and len(v) <= 4096}}
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        return empty


def save_preferences(state):
    raw = json.dumps(state, indent=2).encode("utf-8")
    if len(raw) > MAX_METADATA:
        raise ValueError("Games preferences exceed the local size limit.")
    _atomic(artwork_dir() / "games.json", raw)


def image_from_bytes(raw):
    from PIL import Image, ImageOps
    if not 0 < len(raw) <= MAX_IMAGE_BYTES:
        raise ValueError("Choose game artwork under 8 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as source:
                if source.format not in {"PNG", "JPEG", "WEBP", "BMP"} or source.width * source.height > MAX_PIXELS:
                    raise ValueError("Unsupported or oversized game artwork.")
                frame = ImageOps.exif_transpose(source)
                frame.thumbnail((600, 900), Image.Resampling.LANCZOS)
                return frame.convert("RGB").copy()
    except (OSError, Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise ValueError("Game artwork could not be safely decoded.") from exc


def read_image(path):
    path = Path(path)
    if _has_reparse_component(path) or not path.is_file() or not 0 < path.stat().st_size <= MAX_IMAGE_BYTES:
        raise ValueError("Game artwork is unavailable, linked or too large.")
    with path.open("rb") as stream:
        raw = stream.read(MAX_IMAGE_BYTES + 1)
    return image_from_bytes(raw)


def _save_picture(game, image, kind):
    target = artwork_dir() / (game_id(game) + "." + kind + ".png")
    data = BytesIO()
    image.save(data, format="PNG")
    if data.tell() > MAX_IMAGE_BYTES:
        raise ValueError("Normalized game artwork is too large.")
    _atomic(target, data.getvalue())
    return str(target)


def choose_artwork(game, source):
    return _save_picture(game, read_image(source), "custom")


def clear_artwork(game):
    target = artwork_dir() / (game_id(game) + ".custom.png")
    if target.exists() or target.is_symlink():
        if _has_reparse_component(target):
            raise ValueError("Game artwork storage is redirected.")
        target.unlink()


@dataclass
class Artwork:
    image: object = None
    source: str = "Local fallback · choose or download artwork"


def _local_candidates(game, roots):
    key = game_id(game)
    yield artwork_dir() / (key + ".custom.png"), "Your chosen artwork"
    yield artwork_dir() / (key + ".official.png"), "Cached official Steam artwork"
    ident = str(game.app_id or "")
    if game.launcher == "Steam" and re.fullmatch(r"[1-9][0-9]{0,9}", ident):
        for root in roots[:12]:
            cache = Path(root) / "appcache" / "librarycache"
            for name in (f"{ident}_library_600x900.jpg", f"{ident}_library_600x900.png", f"{ident}_library_600x900.webp", f"{ident}_header.jpg"):
                yield cache / name, "Local Steam library artwork"
            app = cache / ident
            names = ("library_600x900_2x.jpg", "library_600x900.jpg", "library_600x900_2x.png", "library_600x900.png", "library_600x900.webp", "header.jpg")
            for name in names:
                yield app / name, "Local Steam library artwork"
            try:
                if not _has_reparse_component(app) and app.is_dir():
                    from itertools import islice
                    for child in islice(app.iterdir(), 40):
                        if re.fullmatch(r"[0-9a-fA-F]{32,40}", child.name) and child.is_dir() and not _has_reparse_component(child):
                            for name in names:
                                yield child / name, "Local Steam library artwork"
            except OSError:
                pass
            try:
                userdata = Path(root) / "userdata"
                if not _has_reparse_component(userdata) and userdata.is_dir():
                    from itertools import islice
                    for account in islice(userdata.iterdir(), 30):
                        if account.name.isdecimal() and not _has_reparse_component(account):
                            for name in (ident + "p.png", ident + "p.jpg", ident + "p.webp", ident + ".png", ident + ".jpg"):
                                yield account / "config" / "grid" / name, "Your local Steam grid artwork"
            except OSError:
                pass
    folder = Path(game.install_path)
    for name in ("cover.jpg", "cover.png", "poster.jpg", "poster.png", "folder.jpg", "folder.png"):
        yield folder / name, "Local game-folder artwork"


def local_artwork(game, roots=()):
    wide = []
    for path, source in _local_candidates(game, roots):
        if "header" in path.name.casefold():
            wide.append((path, source))
            continue
        try:
            if path.is_file():
                return Artwork(read_image(path), source)
        except (OSError, ValueError, RuntimeError):
            continue
    for path, source in wide:
        try:
            if path.is_file():
                return Artwork(read_image(path), source)
        except (OSError, ValueError, RuntimeError):
            continue
    return Artwork()


class _ArtworkRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _checked_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _checked_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in HOSTS or parsed.port not in (None, 443)
            or parsed.username or parsed.password):
        raise ValueError("Artwork redirected outside the official Steam services.")


def _request(url, limit):
    _checked_url(url)
    with build_opener(_ArtworkRedirects()).open(Request(url, headers={"User-Agent": "GameGrave-Games/0.2", "Accept": "*/*"}), timeout=4) as response:
        _checked_url(response.geturl())
        raw = response.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Official artwork response exceeded its size limit.")
    return raw


def _title(value):
    return "".join(c for c in value.casefold() if c.isalnum())


def official_artwork(game, *, request=None, canceled=lambda: False, steam_id=None):
    """Artwork identity is independent of the game's actual launcher identity."""
    request = request or _request
    if canceled():
        return Artwork()
    ident = str(steam_id or (game.app_id if game.launcher == "Steam" else "") or "")
    if not ident:
        if "open_folder" not in game.capabilities:
            return Artwork()
        query = urlencode({"term": game.name, "l": "english", "cc": "US"})
        data = json.loads(request("https://store.steampowered.com/api/storesearch/?" + query, MAX_METADATA))
        items = data.get("items", []) if isinstance(data, dict) else []
        if not isinstance(items, list):
            return Artwork()
        matches = {str(item.get("id")) for item in items[:50] if isinstance(item, dict)
                   and _title(str(item.get("name", ""))) == _title(game.name)}
        if len(matches) != 1:
            return Artwork()
        ident = matches.pop()
    if not re.fullmatch(r"[1-9][0-9]{0,9}", ident) or canceled():
        return Artwork()
    query = json.dumps({"ids": [{"appid": int(ident)}], "context": {"country_code": "US", "language": "english"},
                        "data_request": {"include_assets": True}}, separators=(",", ":"))
    payload = json.loads(request("https://api.steampowered.com/IStoreBrowseService/GetItems/v1/?input_json=" + quote(query, safe=""), MAX_METADATA))
    container = payload.get("response", {}) if isinstance(payload, dict) else {}
    rows = container.get("store_items", []) if isinstance(container, dict) else []
    if not isinstance(rows, list):
        return Artwork()
    item = next((r for r in rows if isinstance(r, dict) and str(r.get("appid")) == ident), None)
    if not item or canceled():
        return Artwork()
    if game.launcher != "Steam" and steam_id is None and _title(str(item.get("name", ""))) != _title(game.name):
        return Artwork()
    assets = item.get("assets", {})
    filenames = []
    for field in ("library_capsule_2x", "library_capsule", "header"):
        value = assets.get(field) if isinstance(assets, dict) else None
        if isinstance(value, str) and re.fullmatch(r"(?:[0-9a-fA-F]{32,40}/)?(?:library_600x900(?:_2x)?|header)\.(?:jpg|png)", value):
            filenames.append(value)
    filenames.extend(("library_600x900.jpg", "header.jpg"))
    for filename in dict.fromkeys(filenames):
        if canceled():
            break
        try:
            raw = request(f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{ident}/{filename}", MAX_IMAGE_BYTES)
            image = image_from_bytes(raw)
            _save_picture(game, image, "official")
            return Artwork(image, "Official Steam artwork · app " + ident)
        except (OSError, ValueError):
            continue
    return Artwork()
