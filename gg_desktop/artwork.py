"""Steam covers from local metadata caches, then bounded public CDN requests.

Reads only Steam artwork folders and Game Grave's own artwork cache. Downloads
use numeric Steam app IDs, never installation paths, account IDs or credentials.
The dedicated pool keeps image/network work independent of library scans.
"""
from __future__ import annotations

from collections import OrderedDict, deque
from itertools import islice
from pathlib import Path
import os
import tempfile
import threading
import time
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QObject, QRunnable, QSize, QThreadPool, Signal, Slot, Qt
from PySide6.QtGui import QImage, QImageReader, QPixmap

from core import _has_reparse_component, config_dir

MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_CACHE_BYTES = 128 * 1024 * 1024
CDN_HOSTS = ("cdn.akamai.steamstatic.com", "shared.fastly.steamstatic.com")


def valid_app_id(value):
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal() or len(value) > 10:
        return None
    return str(int(value)) if 0 < int(value) <= 4294967295 else None


def game_app_id(game):
    return valid_app_id(game.app_id) if game.launcher == "Steam" else None


def artwork_urls(app_id, kind="cover"):
    app_id = valid_app_id(app_id)
    if app_id is None or kind not in {"cover", "header"}:
        return ()
    names = ("library_600x900.jpg", "header.jpg") if kind == "cover" else ("header.jpg", "library_600x900.jpg")
    return tuple(f"https://{host}/{'store_item_assets/steam/apps' if host.startswith('shared.') else 'steam/apps'}/{app_id}/{name}"
                 for name in names for host in CDN_HOSTS)


def local_artwork_paths(roots, app_id, kind="cover"):
    """Legacy and current hashed Steam caches, plus per-game Steam grid art."""
    app_id = valid_app_id(app_id)
    if app_id is None or kind not in {"cover", "header"}:
        return []
    found = []
    patterns = ("library_600x900", "library_capsule", "header") if kind == "cover" else ("header", "library_hero", "library_600x900")
    for raw in roots:
        root = Path(raw)
        if not root.is_absolute() or _has_reparse_component(root):
            continue
        cache = root / "appcache/librarycache"
        for pattern in patterns:
            found.extend(cache / f"{app_id}_{pattern}{ext}" for ext in (".jpg", ".png", ".webp"))
        current = cache / app_id
        if current.is_dir() and not _has_reparse_component(current):
            try:
                entries = list(islice(current.iterdir(), 80))
                for pattern in patterns:
                    found.extend(p for p in entries if pattern in p.stem.casefold() and p.suffix.casefold() in {".jpg", ".jpeg", ".png", ".webp"})
            except OSError:
                pass
        userdata = root / "userdata"
        if userdata.is_dir() and not _has_reparse_component(userdata):
            try:
                for account in islice(userdata.iterdir(), 60):
                    if account.name.isdecimal():
                        stem = app_id + ("p" if kind == "cover" else "")
                        found[0:0] = [account / "config/grid" / (stem + ext) for ext in (".png", ".jpg", ".webp")]
            except OSError:
                pass
    return found


def decode_artwork(data, kind="cover"):
    if not data or len(data) > MAX_IMAGE_BYTES:
        return QImage()
    buffer = QBuffer()
    buffer.setData(QByteArray(data))
    buffer.open(QIODevice.ReadOnly)
    reader = QImageReader(buffer)
    reader.setDecideFormatFromContent(True)
    size = reader.size()
    if (not size.isValid() or min(size.width(), size.height()) < 16 or
            max(size.width(), size.height()) > 8192 or size.width() * size.height() > 24_000_000):
        return QImage()
    reader.setAutoTransform(True)
    target = QSize(360, 540) if kind == "cover" else QSize(640, 360)
    reader.setScaledSize(size.scaled(target, Qt.KeepAspectRatio))
    return reader.read()


def _read_image(path, kind):
    try:
        if _has_reparse_component(path) or not path.is_file() or path.stat().st_size > MAX_IMAGE_BYTES:
            return QImage()
        with path.open("rb") as source:
            return decode_artwork(source.read(MAX_IMAGE_BYTES + 1), kind)
    except (OSError, ValueError):
        return QImage()


class SteamRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, target):
        url = urlparse(target)
        if url.scheme != "https" or url.hostname not in CDN_HOSTS or url.username or url.password:
            raise ValueError("Artwork redirect outside Steam CDN")
        return super().redirect_request(request, fp, code, message, headers, target)


def fetch_artwork(url, canceled):
    if canceled():
        return b""
    request = Request(url, headers={"User-Agent": "GameGrave/0.1.2 (Steam artwork)", "Accept": "image/*"})
    deadline = time.monotonic() + 10
    with build_opener(SteamRedirects()).open(request, timeout=5) as response:
        if not response.headers.get_content_type().startswith("image/"):
            return b""
        if int(response.headers.get("Content-Length", "0")) > MAX_IMAGE_BYTES:
            return b""
        chunks, length = [], 0
        while not canceled() and time.monotonic() < deadline:
            chunk = response.read(min(65536, MAX_IMAGE_BYTES + 1 - length))
            if not chunk:
                return b"".join(chunks)
            length += len(chunk)
            if length > MAX_IMAGE_BYTES:
                return b""
            chunks.append(chunk)
    return b""


def _save_image(image, target):
    """Only Game Grave's own cache; never writes to Steam or a game folder."""
    temporary = None
    try:
        ancestor = target.parent
        while not ancestor.exists() and not ancestor.is_symlink() and ancestor != ancestor.parent:
            ancestor = ancestor.parent
        if not target.is_absolute() or _has_reparse_component(ancestor):
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        if _has_reparse_component(target.parent):
            return
        with tempfile.NamedTemporaryFile(prefix="cover-", suffix=".tmp", dir=target.parent, delete=False) as temp:
            temporary = Path(temp.name)
        if not image.save(str(temporary), "PNG"):
            return
        temporary.replace(target)
        entries = []
        for entry in islice(target.parent.glob("*.png"), 2000):
            if not _has_reparse_component(entry):
                state = entry.stat()
                entries.append((state.st_mtime, state.st_size, entry))
        total = sum(size for _, size, _ in entries)
        for _, size, entry in sorted(entries):
            if total <= MAX_CACHE_BYTES:
                break
            if entry != target:
                entry.unlink(missing_ok=True)
                total -= size
    except (OSError, ValueError):
        pass
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def load_artwork(app_id, kind, roots, cache_root, allow_downloads, canceled, fetch=fetch_artwork):
    app_id = valid_app_id(app_id)
    if app_id is None or kind not in {"cover", "header"}:
        return QImage(), "Unavailable"
    target = cache_root / f"{app_id}-{kind}.png"
    for path in [target, *local_artwork_paths(roots, app_id, kind)]:
        if canceled():
            return QImage(), "Canceled"
        image = _read_image(path, kind)
        if not image.isNull():
            return image, "Cached"
    if allow_downloads:
        for url in artwork_urls(app_id, kind):
            if canceled():
                break
            try:
                image = decode_artwork(fetch(url, canceled), kind)
                if not image.isNull():
                    _save_image(image, target)
                    return image, "Downloaded"
            except (OSError, ValueError):
                continue
    alternate = cache_root / f"{app_id}-{'header' if kind == 'cover' else 'cover'}.png"
    image = _read_image(alternate, kind)
    if not image.isNull():
        return image, "Cached"
    return QImage(), "Unavailable" if allow_downloads else "Not cached"


class ArtworkSignals(QObject):
    loaded = Signal(str, str, object, str)


class ArtworkJob(QRunnable):
    def __init__(self, args):
        super().__init__()
        self.args = args
        self.signals = ArtworkSignals()

    def run(self):
        try:
            image, status = load_artwork(*self.args)
        except Exception:
            image, status = QImage(), "Unavailable"
        try:
            self.signals.loaded.emit(self.args[0], self.args[1], image, status)
        except RuntimeError:
            pass  # The application may have closed while a request was finishing.


class SteamArtwork(QObject):
    changed = Signal(str, str)

    def __init__(self, parent=None, *, cache_root=None, allow_downloads=True):
        super().__init__(parent)
        self.cache_root = Path(cache_root) if cache_root else config_dir() / "artwork/steam"
        self.allow_downloads = allow_downloads
        self.roots, self.allowed_ids = (), set()
        self.images, self.states, self.failed = OrderedDict(), {}, {}
        self.queue, self.active, self.pending = deque(), {}, set()
        self.closed = threading.Event()
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(3)

    def set_library(self, games, roots):
        self.allowed_ids = {app_id for game in games if (app_id := game_app_id(game))}
        updated = tuple(dict.fromkeys(str(Path(p)) for p in roots if p))
        if self.roots != updated:
            self.roots = updated
            self.failed.clear()

    def pixmap(self, app_id, kind="cover"):
        app_id = valid_app_id(app_id)
        key = (app_id, kind)
        if app_id not in self.allowed_ids or kind not in {"cover", "header"}:
            return None
        if key in self.images:
            self.images.move_to_end(key)
            return self.images[key]
        if (not self.closed.is_set() and key not in self.pending and
                self.failed.get(key, 0) <= time.monotonic() and len(self.pending) < 64):
            self.pending.add(key)
            self.queue.append(key)
            self._pump()
        return None

    def _pump(self):
        while self.queue and len(self.active) < 3 and not self.closed.is_set():
            key = self.queue.popleft()
            job = ArtworkJob((*key, self.roots, self.cache_root, self.allow_downloads, self.closed.is_set))
            job.signals.loaded.connect(self._loaded)
            self.active[key] = job
            self.pool.start(job)

    @Slot(str, str, object, str)
    def _loaded(self, app_id, kind, image, status):
        key = (app_id, kind)
        self.active.pop(key, None)
        self.pending.discard(key)
        if not self.closed.is_set():
            self.states[key] = status
            if not image.isNull():
                self.images[key] = QPixmap.fromImage(image)
                self.images.move_to_end(key)
                while len(self.images) > 64:
                    self.images.popitem(last=False)
            else:
                self.failed[key] = time.monotonic() + 300
            self.changed.emit(app_id, kind)
            self._pump()

    def retry(self):
        self.failed.clear()
        self.changed.emit("", "")

    def close(self):
        self.closed.set()
        self.queue.clear()
